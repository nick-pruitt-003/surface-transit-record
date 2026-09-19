"""Raw riding-time floor between hubs, ignoring schedules.

Every stop-to-stop hop on any trip in the week becomes an edge weighted by its
fastest ride time; footpaths are edges too. Transfers cost nothing, so the
shortest path is the pure in-vehicle (plus walking) time: the floor a route
between two hubs can reach if every connection were instant. Comparing a
route's real riding time with this floor shows whether time is lost to slow
vehicles or to geometry.

Writes out/hub_table.csv (hours) and prints shape floors from out/hub_shapes.txt
(one shape per line: name: Hub > Hub > ...).
"""
import csv, os, sys
from datetime import date
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from time_router import TimeRouter, load_feeds

HUBS = {   # name: (lon, lat); a hub is every stop within HUB_KM
    'Huntington': (-82.445, 38.419), 'Columbus': (-82.994, 39.962), 'Detroit': (-83.049, 42.337),
    'Toledo': (-83.538, 41.654), 'Pittsburgh': (-79.992, 40.444), 'Indianapolis': (-86.158, 39.762),
    'Chicago': (-87.640, 41.879), 'Milwaukee': (-87.912, 43.034), 'Effingham': (-88.543, 39.120),
    'St. Louis': (-90.205, 38.623), 'Memphis': (-90.052, 35.135), 'Nashville': (-86.781, 36.157),
    'Little Rock': (-92.273, 34.747), 'Kansas City': (-94.586, 39.100), 'Omaha': (-95.935, 41.257),
    'Sioux Falls': (-96.730, 43.545), 'Fargo': (-96.790, 46.877), 'Minneapolis': (-93.270, 44.978),
    'Eau Claire': (-91.498, 44.811), 'Billings': (-108.501, 45.783), 'Cheyenne': (-104.820, 41.140),
    'Rapid City': (-103.231, 44.080), 'Denver': (-105.000, 39.753), 'Salt Lake City': (-111.898, 40.760),
    'Boise': (-116.202, 43.615), 'Spokane': (-117.426, 47.657), 'Pasco': (-119.100, 46.236),
    'Seattle': (-122.330, 47.600), 'Portland OR': (-122.676, 45.529), 'Las Vegas NV': (-115.150, 36.160),
    'Barstow': (-117.030, 34.905), 'Los Angeles': (-118.236, 34.056), 'Phoenix': (-112.074, 33.449),
    'Albuquerque': (-106.648, 35.083), 'Las Vegas NM': (-105.213, 35.593), 'El Paso': (-106.487, 31.759),
    'Newton': (-97.345, 38.047), 'Oklahoma City': (-97.516, 35.467), 'Tulsa': (-95.992, 36.154),
    'Dallas': (-96.797, 32.776), 'Shreveport': (-93.750, 32.513), 'Houston': (-95.370, 29.760), 'New Orleans': (-90.078, 29.946),
    'Birmingham': (-86.811, 33.521), 'Atlanta': (-84.390, 33.755), 'Tallahassee': (-84.281, 30.438),
    'Jacksonville': (-81.656, 30.330), 'Charlotte': (-80.843, 35.227), 'Washington': (-77.006, 38.897),
    'New York': (-73.993, 40.750), 'Boston': (-71.055, 42.352), 'Portland ME': (-70.260, 43.655),
    'Hanover': (-72.289, 43.702),
}
HUB_KM = 4.0


def main():
    R = TimeRouter(load_feeds(), date(2026, 9, 24), 7)
    xy = np.array(R.stop_xy, dtype=float); N = R.N
    # fastest ride per directed stop pair (seconds)
    ride = (R.arr - R.dep).astype(np.int64)
    key = R.cfrom.astype(np.int64) * N + R.cto.astype(np.int64)
    order = np.lexsort((ride, key)); key, ride = key[order], ride[order]
    first = np.ones(len(key), bool); first[1:] = key[1:] != key[:-1]
    key, ride = key[first], np.maximum(ride[first], 1)
    rows, cols, w = list(key // N), list(key % N), list(ride)
    for a, lst in R.foot.items():
        for b, s in lst: rows.append(a); cols.append(b); w.append(max(int(s), 1))
    G = coo_matrix((np.array(w, float), (np.array(rows), np.array(cols))), shape=(N, N)).tocsr()
    print(f'graph: {N} stops, {G.nnz} edges', flush=True)

    names = list(HUBS)
    km = lambda lon, lat: np.hypot((xy[:, 0] - lon) * 111.3 * np.cos(np.radians(lat)), (xy[:, 1] - lat) * 111.3)
    members = {h: np.where(km(*HUBS[h]) < HUB_KM)[0] for h in names}
    for h in names:
        if len(members[h]) == 0: print('no stops near hub', h)
    # multi-source Dijkstra per hub: min over member stops
    T = np.full((len(names), len(names)), np.inf)
    for i, h in enumerate(names):
        if len(members[h]) == 0: continue
        d = dijkstra(G, indices=members[h], min_only=True)
        for j, g in enumerate(names):
            if len(members[g]): T[i, j] = d[members[g]].min() / 3600
    out = os.path.join(os.path.dirname(__file__), '..', 'out', 'hub_table.csv')
    with open(out, 'w', newline='') as f:
        wr = csv.writer(f); wr.writerow(['from'] + names)
        for i, h in enumerate(names): wr.writerow([h] + [f'{x:.1f}' for x in T[i]])
    print('wrote', out)

    shapes = os.path.join(os.path.dirname(__file__), '..', 'out', 'hub_shapes.txt')
    if os.path.exists(shapes):
        ix = {h: i for i, h in enumerate(names)}
        for line in open(shapes):
            if ':' not in line or line.startswith('#'): continue
            nm, seq = line.split(':', 1); seq = [s.strip() for s in seq.split('>')]
            bad = [s for s in seq if s not in ix]
            if bad: print(nm, 'unknown hubs', bad); continue
            hops = [(a, b, T[ix[a], ix[b]]) for a, b in zip(seq, seq[1:])]
            print(f'{nm.strip():12s} floor {sum(h for *_, h in hops):6.1f} h   ' + '  '.join(f'{a[:4]}>{b[:4]} {h:.1f}' for a, b, h in hops))


if __name__ == '__main__':
    main()
