"""Shared pieces of the 48-state routing pipeline: grid snapping, distances,
state lookup, graph assembly and chain contraction."""
import json, math, os, pickle
from collections import defaultdict
import numpy as np
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

GRID = 0.01            # degrees; ~1.1 km. Route points are snapped to this grid.
TRANSFER_COST = 5.0    # km-equivalent per stop-hub edge, i.e. 10 per transfer
WALK_RADIUS_KM = 2.5   # stops this close are linked by a walk/taxi edge
WALK_COST = 40.0       # km-equivalent for that walk (~30 min)
STOP_PATCH = 1         # a stop links to route cells within +/- this many cells
SKIP_STATES = {'Alaska', 'Hawaii', 'Puerto Rico', 'District of Columbia'}
DATA_DIR = os.environ.get('BUS48_DATA', os.path.join(os.path.dirname(__file__), '..', 'data'))

ABBR = {'Alabama':'AL','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT','Delaware':'DE','Florida':'FL','Georgia':'GA','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT','Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY'}


def data_path(pattern):
    """Return the single file in DATA_DIR matching a glob pattern."""
    import glob
    hits = sorted(glob.glob(os.path.join(DATA_DIR, pattern)))
    if not hits:
        raise FileNotFoundError(f'no file matching {pattern} in {DATA_DIR}')
    return hits[-1]


def cell(lon, lat):
    return (round(lon / GRID), round(lat / GRID))


def cell_xy(c):
    return (c[0] * GRID, c[1] * GRID)


def hav(a, b):
    """Great-circle distance in km between two (lon, lat) points."""
    lon1, lat1 = a; lon2, lat2 = b; p = math.pi / 180
    x = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(x))


class StateIndex:
    """Point-in-polygon lookup for the 48 contiguous states."""
    def __init__(self, path=None):
        sj = json.load(open(path or os.path.join(DATA_DIR, 'states.geojson')))
        feats = [f for f in sj['features'] if f['properties']['name'] not in SKIP_STATES]
        self.names = [f['properties']['name'] for f in feats]
        self.polys = [shape(f['geometry']) for f in feats]
        self.tree = STRtree(self.polys)

    def of_points(self, xy):
        """State index per (lon, lat) row, -1 when outside the 48."""
        xy = np.asarray(xy)
        out = np.full(len(xy), -1, dtype=np.int32)
        if len(xy):
            q = self.tree.query(shapely.points(xy[:, 0], xy[:, 1]), predicate='within')
            out[q[0]] = q[1]
        return out

    def abbr_of_point(self, lon, lat):
        i = self.of_points([(lon, lat)])[0]
        return ABBR[self.names[i]] if i >= 0 else None


class GraphBuilder:
    """Accumulates (route, cell) nodes, stop hubs and weighted edges."""
    def __init__(self):
        self.node_key = {}; self.node_xy = []
        self.edges = {}          # (a, b) a<b -> [weight_km, set(route idx)]
        self.routes = []         # idx -> (carrier, short_name, long_name)
        self.stops = []          # idx -> (name, state_abbr, carrier, lon, lat)
        self.cell_stops = defaultdict(set)

    def nid(self, key, xy):
        i = self.node_key.get(key)
        if i is None:
            i = len(self.node_xy); self.node_key[key] = i; self.node_xy.append(xy)
        return i

    def add_edge(self, a, b, w, ri):
        if a == b:
            return
        k = (a, b) if a < b else (b, a)
        e = self.edges.get(k)
        if e is None:
            self.edges[k] = [w, {ri}]
        else:
            e[1].add(ri); e[0] = min(e[0], w)

    def add_stop(self, name, state_abbr, carrier, lon, lat):
        si = len(self.stops)
        self.stops.append((name, state_abbr, carrier, lon, lat))
        self.nid(('s', si), (lon, lat))
        cx, cy = cell(lon, lat)
        for dx in range(-STOP_PATCH, STOP_PATCH + 1):
            for dy in range(-STOP_PATCH, STOP_PATCH + 1):
                self.cell_stops[(cx + dx, cy + dy)].add(si)
        return si

    def add_route(self, carrier, short_name, long_name):
        self.routes.append((carrier, short_name, long_name))
        return len(self.routes) - 1

    def add_shape(self, ri, coords, weight=1.0, cell_hubs=False):
        """Add one polyline of route ri. coords: iterable of (lon, lat).
        Each cell links to every stop whose patch covers it (once per run of
        cells). With cell_hubs, cells also link to a per-cell hub so routes of
        this layer can transfer between themselves anywhere (local transit)."""
        prev = None; last = set()
        for lon, lat in coords:
            ce = cell(lon, lat)
            i = self.nid(('r', ri, ce), cell_xy(ce))
            if prev is not None and prev != i:
                self.add_edge(prev, i, weight * hav(self.node_xy[prev], self.node_xy[i]), ri)
            if prev != i:
                cur = self.cell_stops.get(ce, set())
                for si in cur - last:
                    self.add_edge(i, self.node_key[('s', si)], TRANSFER_COST, -1)
                last = cur
                if cell_hubs:
                    self.add_edge(i, self.nid(('c', ce), cell_xy(ce)), TRANSFER_COST, -1)
            prev = i

    def link_nearby_stops(self):
        """Walking edges between stop hubs within WALK_RADIUS_KM (Greyhound
        depot to Amtrak station, airport stop to downtown stop, ...)."""
        buckets = defaultdict(list)
        for si, (_, _, _, lon, lat) in enumerate(self.stops):
            buckets[(int(lon / 0.05), int(lat / 0.05))].append(si)
        n = 0
        for (bx, by), members in buckets.items():
            cand = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cand += buckets.get((bx + dx, by + dy), [])
            for si in members:
                a = self.stops[si]
                for sj in cand:
                    if sj <= si:
                        continue
                    b = self.stops[sj]
                    if hav((a[3], a[4]), (b[3], b[4])) <= WALK_RADIUS_KM:
                        self.add_edge(self.node_key[('s', si)], self.node_key[('s', sj)], WALK_COST, -1); n += 1
        return n

    def finish(self, states):
        keys = [None] * len(self.node_xy)
        for k, i in self.node_key.items():
            keys[i] = k
        state = states.of_points(self.node_xy)
        return dict(node_xy=self.node_xy, keys=keys, edges=self.edges, routes=self.routes,
                    stops=self.stops, names=states.names, state=state)


def contract(graph):
    """Collapse degree-2 chains. Keeps junctions, hubs and state-change nodes.
    Returns {(a, b): (weight, [original node path a..b])}."""
    keys = graph['keys']; state = graph['state']
    adj = defaultdict(dict)
    for (a, b), (w, _) in graph['edges'].items():
        adj[a][b] = w; adj[b][a] = w
    n = len(graph['node_xy']); keep = np.zeros(n, bool)
    for v in range(n):
        nb = adj[v]
        if len(nb) != 2 or keys[v][0] in ('s', 'c') or any(state[u] != state[v] for u in nb):
            keep[v] = True
    cedges = {}; seen = set()
    for v in np.where(keep)[0]:
        for u in adj[v]:
            if (v, u) in seen:
                continue
            path = [v, u]; w = adj[v][u]; prev, cur = v, u; seen.add((v, u))
            while not keep[cur]:
                nxt = [x for x in adj[cur] if x != prev][0]
                w += adj[cur][nxt]; path.append(nxt); prev, cur = cur, nxt
            seen.add((cur, prev))
            if cur == v:
                continue
            key = (v, cur) if v < cur else (cur, v)
            p = path if v < cur else path[::-1]
            if key not in cedges or cedges[key][0] > w:
                cedges[key] = (w, p)
    return cedges


def save_graph(graph, cedges, name):
    with open(f'{name}.pkl', 'wb') as f:
        pickle.dump(graph, f)
    with open(f'c{name}.pkl', 'wb') as f:
        pickle.dump(cedges, f)


def load_graph(name):
    with open(f'{name}.pkl', 'rb') as f:
        graph = pickle.load(f)
    with open(f'c{name}.pkl', 'rb') as f:
        cedges = pickle.load(f)
    return graph, cedges
