"""Would an exact triple test kill the dead family the pair test lets through? Offline, on a saved --xprobe
frontier (../out/xprobe_last.pkl). Leaf script; nothing imports it.

The pair table P[stop, y, z] is the latest you can be at stop and still collect y and z (best order) and finish.
Seeding one more reverse scan from x's stops with P[., y, z] gives the latest you can be anywhere and collect x
first, then y and z, then finish. The max over which of the three goes first is the triple bound: exact, built
from the same scans, so a node past it is dead, not estimated dead.

For each queued node in the deep layers it tests the few triples its own pair margins point at (the tightest
pair, plus the owed states tight against both), and reports how many die. X's own nodes go through the same
test and must all survive; one X kill means the test is wrong, not the route.

  py triple_probe.py --at 2026-11-12T22:10 --by 2026-11-22T15:10 --tz America/Denver [--layers 30 31 32]
"""
import argparse, glob, os, pickle, random, time
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from pair_tables import resolve_stop, _latest_from
from common import ABBR
import backward as B

ap = argparse.ArgumentParser()
ap.add_argument('--at', required=True); ap.add_argument('--by', required=True)
ap.add_argument('--tz', required=True); ap.add_argument('--days', type=int, default=20)
ap.add_argument('--span', type=float, default=260)
ap.add_argument('--pairs'); ap.add_argument('--probe', default='../out/xprobe_last.pkl')
ap.add_argument('--layers', type=int, nargs='*')
ap.add_argument('--sample', type=int, default=150, help='nodes per layer')
ap.add_argument('--x-tries', type=int, default=3, help='third states tried per node')
a = ap.parse_args()
when = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz)); T0 = when.timestamp()
D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
R = cached_router(when.date(), a.days, verbose=False)
P = np.load(a.pairs or max(glob.glob('../out/pairs_*.npy'), key=os.path.getmtime), mmap_mode='r')
F = B.RevFast(R)
st_stops = [[] for _ in range(N_STATES)]
for s in range(R.N):
    if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)
idx = {ABBR[n]: i for i, n in enumerate(R.state_names)}
d = pickle.load(open(a.probe, 'rb'))
_ids, _first, _tri = {}, {}, {}
scans = [0]; t_scan = [0.0]


def first_then(x, y, z):
    """latest at every stop to collect x, then y and z in the best order, then finish (absolute seconds)"""
    k = (x, y, z) if y < z else (x, z, y)
    if k not in _first:
        nxt = {s: D + float(P[s, y, z]) for s in st_stops[x] if np.isfinite(P[s, y, z])}
        t1 = time.time()
        _first[k] = _latest_from(F, D, a.span, nxt) if nxt else np.full(R.N, -np.inf)
        scans[0] += 1; t_scan[0] += time.time() - t1
    return _first[k]


def triple(x, y, z):
    k = tuple(sorted((x, y, z)))
    if k not in _tri:
        _tri[k] = np.maximum(np.maximum(first_then(x, y, z), first_then(y, x, z)), first_then(z, x, y))
    return _tri[k]


def test(stopname, t, have):
    """(dead, pair margin h, triple margin h) at the stop of that name that leaves the most room"""
    owed = np.array(sorted(set(range(N_STATES)) - {idx[s] for s in have}), dtype=np.int64)
    if stopname not in _ids: _ids[stopname] = resolve_stop(R, stopname) or []
    best = None
    for s in _ids[stopname]:
        sub = np.asarray(P[s])[np.ix_(owed, owed)] - np.float32(t - D)
        i = int(np.argmin(sub)); y, z = owed[i // len(owed)], owed[i % len(owed)]
        pm = float(sub.flat[i]) / 3600
        # third states tight against both halves of the tightest pair
        tight = sorted((min(float(P[s, x, y]), float(P[s, x, z])), x) for x in owed if x not in (y, z))
        tm = min(float(triple(int(x), int(y), int(z))[s]) - t for _, x in tight[:a.x_tries]) / 3600
        if best is None or tm > best[2]: best = (tm < 0, pm, tm)
    return best


t_all = time.time()
print('X nodes (all must survive):')
for row in d['x']:
    nleg, n, spx, sx, name, st, px, pm = row
    r = test(name, T0 + spx, st)
    if r: print(f'  {n:>2} {name[:30]:<30} pair {r[1]:+7.1f} h  triple {r[2]:+7.1f} h  {"KILLED <- WRONG" if r[0] else "ok"}', flush=True)
layers = a.layers or sorted(k for k in d['items'] if k >= 25)
for k in layers:
    its = d['items'].get(k, [])
    xnames = {r[4] for r in d['x'] if r[1] == k}
    pool = [it for it in its if it[2] not in xnames]
    random.seed(1); smp = random.sample(pool, min(a.sample, len(pool)))
    res = [test(it[2], it[3], it[4]) for it in smp]
    res = [r for r in res if r]
    dead = sum(r[0] for r in res)
    print(f'layer {k}: {dead}/{len(res)} sampled nodes die on the triple test '
          f'(pair margins {min(r[1] for r in res):+.1f}..{max(r[1] for r in res):+.1f} h); '
          f'{scans[0]} scans so far, {t_scan[0] / max(scans[0], 1):.2f} s each, {len(_tri)} triples cached', flush=True)
print(f'done in {time.time() - t_all:.0f} s')
