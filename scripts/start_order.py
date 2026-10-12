"""In what order should candidate start stops be tried? Intercity first, nearest the state line first.

Nick's premise. A route has to leave the state, so a stop with long-distance service is a likelier start
than a local bus stop, and among those a stop near a line collects two states quickly. For New Mexico he
expects Las Cruces before the Sunland Park locals.

Both halves come from the timetable rather than a list of carriers:

  reach[s]   the greatest distance spanned by any trip serving s OR any stop walkable from s. The
             footpath closure is the point: Sunland Park's own service is 13 km of local bus, and it walks
             to the Sunset Limited at El Paso at 3099 km, plus a border walk-in into Texas. Scoring it by
             what stops there would bury it. New Mexico sorts to Deming and Lordsburg
             Amtrak at 3099 km (the Sunset Limited), Albuquerque and Gallup at 2832 (the Southwest Chief),
             Las Cruces at 1128 and 923, then a cliff to Las Cruces MVITT at 37, Sunland Park at 26 and 13,
             and the city bus stops at 0.
  dline[s]   kilometres to the nearest stop in a different state, over a KD-tree of every stop.

ORDERING, NOT FILTERING, and the distinction is the whole reason this is allowed to exist. Every candidate
is still evaluated; this only decides what gets evaluated first, so partial results are the useful ones and
an interrupted run has already done the promising work. A threshold in a filter loses the Barstow depot
with two services. A threshold in an ordering costs some wasted minutes and nothing else. That is why
INTERCITY_KM below is tolerable where the same constant in `alight_ok` was a bug.

It is a stated constant rather than a derived split because the derived split does not survive the data.
New Mexico's two largest gaps in sorted reach are 893 km (2021 to 1128) and 886 km (923 to 37), near enough
tied that a largest-gap rule puts Las Cruces in the local tier.

    python3 start_order.py --state NM      the order for one state, to check against expectation
"""
import argparse, hashlib, os, time
import numpy as np
from common import ABBR

HERE = os.path.dirname(os.path.abspath(__file__))
INTERCITY_KM = 100.0     # ordering only; see above


def _km(dlon, dlat, lat):
    return np.hypot(dlon * 111.3 * np.cos(np.radians(lat)), dlat * 111.3)


def build(R, cache_dir=None, verbose=True):
    """(reach, dline) per stop, cached: the reach pass is a minute over 11.2M connections."""
    cache_dir = cache_dir or os.path.join(HERE, '..', 'out')
    h = hashlib.sha1()
    for arr in (R._fa['cfrom'], R._fa['cto'], np.asarray(R.state)):
        h.update(np.ascontiguousarray(arr).tobytes())
    h.update(np.asarray(R.stop_xy, float).tobytes())
    h.update(repr(('start-order-v2-walkreach', INTERCITY_KM)).encode())
    path = os.path.join(cache_dir, f'startorder_{h.hexdigest()[:16]}.npz')
    if os.path.exists(path):
        z = np.load(path)
        if verbose: print(f'start order from cache ({os.path.basename(path)})', flush=True)
        return z['reach'], z['dline']

    t0 = time.time()
    xy = np.asarray(R.stop_xy, float)
    cf, ct = np.asarray(R.cfrom), np.asarray(R.cto)
    # bounding box per trip, then its diagonal: one pass, no per-trip stop lists
    lo, hi = {}, {}
    for k in range(len(R.dep)):
        tr = R.ctrip[k]
        for s in (int(cf[k]), int(ct[k])):
            p = xy[s]
            if tr in lo:
                np.minimum(lo[tr], p, out=lo[tr]); np.maximum(hi[tr], p, out=hi[tr])
            else:
                lo[tr] = p.copy(); hi[tr] = p.copy()
    span = {tr: float(_km(hi[tr][0] - lo[tr][0], hi[tr][1] - lo[tr][1], (hi[tr][1] + lo[tr][1]) / 2))
            for tr in lo}
    reach = np.zeros(R.N)
    for k in range(len(R.dep)):
        v = span[R.ctrip[k]]
        a, b = int(cf[k]), int(ct[k])
        if v > reach[a]: reach[a] = v
        if v > reach[b]: reach[b] = v

    # Reach is about trips serving THIS stop, which scores Sunland Park at 13 km of local bus. It has a
    # border walk-in into Texas and can walk to a stop on a 3099 km trip, the Sunset Limited at El Paso.
    # Clovis, at 597 km of its own service, has one foot-neighbour with no reach at all. So what matters is
    # what you can reach ON FOOT from here, not what stops here: the same error as scoring the Memphis
    # walk-in by when it touches Mississippi rather than by what it opens up. The footpath closure fixes it
    # with no new constant.
    walk_reach = reach.copy()
    for i, nb in R.foot.items():
        m = reach[i]
        for j, _w in nb:
            if reach[j] > m: m = reach[j]
        walk_reach[i] = m
    reach = walk_reach

    # nearest stop in a DIFFERENT state, per stop. Equirectangular about the mean latitude is accurate
    # enough over the distances that decide an ordering, and lets one KD-tree answer it.
    from scipy.spatial import cKDTree
    lat0 = float(np.mean(xy[:, 1]))
    pts = np.column_stack([xy[:, 0] * 111.3 * np.cos(np.radians(lat0)), xy[:, 1] * 111.3])
    st = np.asarray(R.state)
    dline = np.full(R.N, np.inf)
    for y in np.unique(st[st >= 0]):
        mine = np.where(st == y)[0]
        other = np.where(st != y)[0]
        if not len(mine) or not len(other): continue
        d, _i = cKDTree(pts[other]).query(pts[mine], k=1)
        dline[mine] = d
    np.savez(path + f'.{os.getpid()}.tmp.npz', reach=reach, dline=dline)
    os.replace(path + f'.{os.getpid()}.tmp.npz', path)
    if verbose: print(f'start order built in {time.time() - t0:.0f} s, cached as {os.path.basename(path)}',
                      flush=True)
    return reach, dline


def order_for(R, state, reach, dline, include_virtual=False):
    """candidate start stops in that state, intercity first, nearest the line first within each tier"""
    ss = [s for s in range(R.N) if R.state[s] == state and (include_virtual or s < R.first_virtual)]
    return sorted(ss, key=lambda s: (reach[s] < INTERCITY_KM, dline[s], -reach[s]))


def main():
    from datetime import datetime
    from time_router import cached_router
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-05T00:54')
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--state', default='NM')
    ap.add_argument('--n', type=int, default=16)
    a = ap.parse_args()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    inv = {v: k for k, v in ABBR.items()}
    y = R.state_names.index(inv[a.state])
    reach, dline = build(R)
    ss = order_for(R, y, reach, dline)
    n_inter = sum(1 for s in ss if reach[s] >= INTERCITY_KM)
    print(f'\n{a.state}: {len(ss)} real stops, {n_inter} intercity (reach >= {INTERCITY_KM:.0f} km)\n')
    print(f'  {"#":>3s} {"tier":10s} {"to line":>8s} {"reach":>8s}  stop')
    for i, s in enumerate(ss[:a.n], 1):
        print(f'  {i:3d} {"intercity" if reach[s] >= INTERCITY_KM else "local":10s} '
              f'{dline[s]:7.1f} {reach[s]:7.0f}  {R.stop_name[s][:50]}')
    print('\nOrdering only. Every stop is still evaluated; this decides what goes first, so an interrupted '
          'run has already done the promising work.')


if __name__ == '__main__':
    main()
