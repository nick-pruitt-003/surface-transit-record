"""Size of tail_mip's network if city transit collapses into hops between core stops (Nov 18). Leaf script.

Core stops: stops of kept intercity connections, walk-in points, the start, and every city stop on a city edge or
footpath that crosses a state line (so a city path between two core stops with no core stop inside stays in one
state). Prints the counts that decide whether the contraction is worth building, against the uncontracted 78.3 M arcs.

  python3 hop_size.py --stop "#476" --at 2026-11-19T14:35 --tz America/New_York --by 2026-11-22T15:28 --by-tz America/Chicago --end MN
"""
import argparse, time
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
import backward as B

ap = argparse.ArgumentParser()
ap.add_argument('--stop'); ap.add_argument('--at'); ap.add_argument('--tz')
ap.add_argument('--by'); ap.add_argument('--by-tz'); ap.add_argument('--end', default='MN')
ap.add_argument('--d0', default='2026-11-09'); ap.add_argument('--days', type=int, default=22)
a = ap.parse_args()
R = cached_router(date.fromisoformat(a.d0), a.days, verbose=False)
inv = {v: k for k, v in ABBR.items()}; end = R.state_names.index(inv[a.end])
s0 = int(a.stop[1:]); t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.by_tz)).timestamp()
t = time.time()
_, _, ea = R.scan({s0: (t0, None)}, set())
F = B.RevFast(R)
lat, ok_, k0, k1 = F.layer({int(s): D for s in np.where(R.state == end)[0]}, False, t0, None)
eff, _ = F.through(ok_, k0, k1, np.ones(R.N, bool)); lend = np.maximum(lat, eff)
keep = (R.dep >= t0) & (R.arr <= D) & (R.dep >= ea[R.cfrom]) & (R.arr <= lend[R.cto])
K = np.where(keep)[0]
print(f'scans {time.time() - t:.0f} s; kept {len(K)} connections')
city_feed = {fi for fi, f in enumerate(R.feeds) if getattr(f, 'city', False)}
fi = np.fromiter((R.ctrip[k][0] for k in K.tolist()), np.int64, len(K))
is_city = np.isin(fi, list(city_feed))
Kc, Ki = K[is_city], K[~is_city]
print(f'  intercity {len(Ki)}, city {len(Kc)}')
st = np.asarray(R.state)
core = np.zeros(R.N, bool)
core[R.cfrom[Ki]] = True; core[R.cto[Ki]] = True; core[s0] = True
core[R.first_virtual:] = True
cross = st[R.cfrom[Kc]] != st[R.cto[Kc]]
core[R.cfrom[Kc][cross]] = True; core[R.cto[Kc][cross]] = True
city_stop = np.zeros(R.N, bool); city_stop[R.cfrom[Kc]] = True; city_stop[R.cto[Kc]] = True
nfoot_cross = 0
for s in np.where(city_stop)[0].tolist():
    for j, w in R.foot.get(s, ()):
        if st[j] != st[s]: core[s] = True; core[j] = True; nfoot_cross += 1
print(f'  core stops {int(core.sum())} (state-crossing city edges {int(cross.sum())}, footpaths {nfoot_cross})')
# metros: union-find over kept city connections and footpaths between city stops
par = np.arange(R.N)
def find(x):
    while par[x] != x: par[x] = par[par[x]]; x = par[x]
    return x
def uni(x, y):
    x, y = find(x), find(y)
    if x != y: par[x] = y
for x, y in zip(R.cfrom[Kc].tolist(), R.cto[Kc].tolist()): uni(x, y)
for s in np.where(city_stop | core)[0].tolist():
    for j, w in R.foot.get(s, ()):
        if city_stop[j] or core[j]: uni(s, j)
comp = defaultdict(list)
has_city = defaultdict(bool)
for s in np.where(city_stop)[0].tolist(): has_city[find(s)] = True
for s in np.where(core)[0].tolist():
    r = find(s)
    if has_city[r]: comp[r].append(s)
cores_in = {r: len(v) for r, v in comp.items()}
arr_at = np.bincount(R.cto[Ki], minlength=R.N)
dep_at = np.bincount(R.cfrom[Ki], minlength=R.N)
est = 0; big = []
for r, v in comp.items():
    n = len(v); arrs = int(arr_at[v].sum()) + (1 if s0 in v else 0)
    est += arrs * (n - 1)
    big.append((arrs * (n - 1), n, arrs, R.stop_name[v[0]][:30]))
big.sort(reverse=True)
print(f'  metros with a core city stop {len(comp)}; hop arcs upper bound (arrivals x other cores in the metro) {est:,}')
for e, n, arrs, nm in big[:12]:
    print(f'    {e:>12,}  {n:4d} cores  {arrs:7d} arrivals  e.g. {nm}')
print(f'  intercity arcs ~ {3 * len(Ki):,} (board, alight, stay) + timeline waits ~ {len(np.unique(R.cfrom[Ki])) and int(dep_at.sum()):,}')
