"""Select local transit bus routes worth adding to the graph: those that cross a
state line, or that come within a stop patch of two intercity stops >= 3 km apart.
Writes local_kept.pkl for build_graph.py --layers ...,local."""
import json, math, os, pickle, sqlite3
from collections import defaultdict
import numpy as np, shapely
from common import StateIndex, cell, data_path, STOP_PATCH, DATA_DIR

MIN_STOP_SPREAD_KM = 3.0


def gpkg_geom(blob):
    flags = blob[3]; env = (flags >> 1) & 7
    header = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    return shapely.from_wkb(blob[header:])


def main():
    stops = json.load(open(data_path('NTAD_Intercity_Bus_Atlas_Stops_*.geojson')))['features']
    xy = np.array([s['geometry']['coordinates'] for s in stops])
    cell_stops = defaultdict(set)
    for si, s in enumerate(stops):
        cx, cy = cell(*s['geometry']['coordinates'])
        for dx in range(-STOP_PATCH, STOP_PATCH + 1):
            for dy in range(-STOP_PATCH, STOP_PATCH + 1):
                cell_stops[(cx + dx, cy + dy)].add(si)
    states = StateIndex()
    con = sqlite3.connect(data_path('NTAD_National_Transit_Map_Routes_*.gpkg'))
    q = ("select OBJECTID, SHAPE, ntd_id, agency_id, route_short_name, route_long_name "
         "from National_Transit_Map_Routes where route_type='3'")
    kept = []; n = 0
    for oid, blob, ntd, agency, short, long_ in con.execute(q):
        n += 1
        g = shapely.simplify(gpkg_geom(blob), 0.002)
        coords = shapely.get_coordinates(g)
        if len(coords) < 2:
            continue
        near = set()
        for c in set(cell(x, y) for x, y in coords):
            near |= cell_stops.get(c, set())
        samp = coords[::max(1, len(coords) // 20)]
        st = set(states.of_points(samp).tolist()) - {-1}
        spread = 0.0
        if len(near) >= 2:
            p = xy[list(near)]; lat = math.cos(math.radians(p[:, 1].mean()))
            d = np.sqrt(((p[:, None, 0] - p[None, :, 0]) * lat * 111) ** 2 + ((p[:, None, 1] - p[None, :, 1]) * 111) ** 2)
            spread = d.max()
        if len(st) >= 2 or spread >= MIN_STOP_SPREAD_KM:
            kept.append(dict(oid=oid, agency=agency, short=short, long=long_, ntd=ntd, geom=g, near=near, states=st))
        if n % 5000 == 0:
            print(n, len(kept), flush=True)
    con.close()
    print('bus routes', n, 'kept', len(kept))
    with open(os.path.join(DATA_DIR, 'local_kept.pkl'), 'wb') as f:
        pickle.dump(kept, f)


if __name__ == '__main__':
    main()
