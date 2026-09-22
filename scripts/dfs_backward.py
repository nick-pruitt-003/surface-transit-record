"""Build 48-state routes from the end by depth-first search with backtracking against a time limit.

  python3 dfs_backward.py --end VT --from 2026-10-03T22:14 --tz America/New_York --target 238

At each step the timetables offer a menu: the states you could still be in, latest first. Take the best one
and go on. When what you have spent plus a floor on what is left would pass the time limit, that branch
cannot win, so back up a step and take the next option; when a step runs out of options, back up again.

This is not the beam in build_backward, and the difference is the point. A beam prunes by comparison: it
keeps the chains that look best against each other right now, which throws away a route whose advantage
comes later. The 237 route is behind for fifteen consecutive steps after it commits to the Southwest Chief
and only collects at the end, and no beam width, candidate width or survival rule holds it (see HANDOFF
section 9). Backtracking prunes by proof instead: a branch is cut only when it cannot come in under the
limit, and being behind some other chain is not that.

It also changes what the estimate has to do. A beam needs one that ranks correctly, which is what every
attempt failed at (sections 9 and 11). Here it only has to never overestimate, because that is what makes a
cut safe. Two are used together, the larger winning: the spanning tree over state-to-state times, and the
furthest-back state the node's own reverse scan can still reach, which was useless for ranking and is a
perfectly good floor.
"""
import argparse, os, pickle, random, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import time_search as ts
from time_search import Search, FREE
import backward as B
import build_backward as BB
from common import ABBR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end', required=True); ap.add_argument('--from', dest='frm', required=True)
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--target', type=float, default=238.0, help='hours the route must come in under')
    ap.add_argument('--window', type=float, default=110, help='hours a node scans back over')
    ap.add_argument('--topk', type=int, default=6, help='options tried per step, latest first')
    ap.add_argument('--nodes', type=int, default=200000, help='node budget')
    ap.add_argument('--budget', type=float, default=1800, help='wall-clock seconds')
    ap.add_argument('--times', default='../out/state_times_real.npy', help='state-to-state matrix (must not overestimate)')
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', help='pickle prefix for what it finds')
    ap.add_argument('--track', help='reference route pickle: report the deepest prefix of it the search reaches')
    a = ap.parse_args()

    inv = {v: k for k, v in ABBR.items()}
    D0 = datetime.fromisoformat(a.frm).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), (D0 - timedelta(days=12)).date(), a.days)
    F = B.RevFast(R)
    end = R.state_names.index(inv[a.end]); D = D0.timestamp()
    ab = lambda x: ABBR[R.state_names[x]]
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    st_arr = {x: np.array(state_stops[x], dtype=np.int64) for x in state_stops}
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    dist['M'] = np.array([[dist[x][y] for y in range(N_STATES)] for x in range(N_STATES)])
    if os.path.exists(a.times): dist['T'] = np.load(a.times)
    else: print('no state-time matrix at', a.times, '- falling back to straight-line km')

    oracle = None
    if a.track:
        d = pickle.load(open(a.track, 'rb')); st0 = R.stop_name.index(d['start'])
        S0 = Search(R, st0, d['t0'], [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0, d['t0'], S0, None, None
        _, l0 = S0.evaluate(d['order'])
        oracle = BB.visit_sequence(R, S0, l0, st0)[::-1]
        print('tracking:', ' < '.join(ab(x) for x in oracle[:6]), '...')

    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep

    def sparse(ns):
        idx = np.nonzero(ns[0] >= 0)[0]; return idx, ns[0][idx], ns[1][idx]

    def options(nd):
        """The menu at this node: (latest time, state, stop, child) per state still to place, latest first,
        plus the floor on the work left that the same scan gives for free."""
        hi = max(nd['cur'].values())
        L, ok, k0, k1 = F.layer(nd['cur'], True, hi - a.window * 3600, dense(nd['ns']))
        mask = np.zeros(R.N, bool)
        for x in nd['left']: mask[st_arr[x]] = True
        eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
        cands = []
        for x in nd['left']:
            v = vals[st_arr[x]]; i = int(np.argmax(v))
            if v[i] > -np.inf: cands.append((float(v[i]), x, int(st_arr[x][i])))
        cands.sort(reverse=True)
        reach = max(((hi - v) / 3600 for v, _, _ in cands), default=0.0)
        return cands, (L, ok, k0, k1), reach

    def child(nd, x, s_best, scan):
        L, ok, k0, k1 = scan
        xm = np.zeros(R.N, bool); xm[st_arr[x]] = True
        eff_x, ns_x = F.through(ok, k0, k1, xm)
        cur = {int(s): float(max(L[s], eff_x[s])) for s in st_arr[x] if max(L[s], eff_x[s]) > -np.inf}
        if not cur: return None
        return dict(picked=nd['picked'] + [x], left=nd['left'] - {x}, cur=cur, ns=sparse(ns_x), pin=nd['pin'] + [s_best])

    best = [None]; limit = [a.target]; seen_nodes = [0]; cut = [0]; deepest = [0]
    t0 = time.time()
    root = dict(picked=[end], left=set(range(N_STATES)) - {end}, cur={int(s): D for s in state_stops[end]},
                ns=None, pin=[state_stops[end][0]])

    def follows(nd):
        """How much of the tracked route this chain still matches, for the progress line."""
        if not oracle: return -1
        n = 0
        for i, x in enumerate(nd['picked']):
            if i < len(oracle) and oracle[i] == x: n += 1
            else: break
        return n

    def dfs(nd):
        if time.time() - t0 > a.budget or seen_nodes[0] > a.nodes: return
        seen_nodes[0] += 1
        spent = (D - max(nd['cur'].values())) / 3600
        if not nd['left']:
            if spent < limit[0]:
                limit[0] = spent; best[0] = dict(nd)
                print(f'  [{time.time() - t0:5.0f}s] FOUND {spent:.1f} h  ' +
                      ' > '.join(ab(x) for x in nd['picked'][::-1]), flush=True)
            return
        cands, scan, reach = options(nd)
        floor = max(BB.strand_cost(nd['left'], nd['picked'][-1], dist) / 3600, reach)
        if spent + floor > limit[0]: cut[0] += 1; return
        k = follows(nd)
        if k > deepest[0]:
            deepest[0] = k
            print(f'  [{time.time() - t0:5.0f}s] reached {k}/{len(oracle)} of the tracked route '
                  f'(...{ab(nd["picked"][-1])}, {spent:.1f} h spent, floor {floor:.0f} h, '
                  f'{seen_nodes[0]} nodes, {cut[0]} cut)', flush=True)
        for v, x, s_best in cands[:a.topk]:
            if spent + floor > limit[0]: cut[0] += 1; return
            kid = child(nd, x, s_best, scan)
            if kid is not None: dfs(kid)

    print(f'depth-first from {a.end} at {D0:%a %Y-%m-%d %H:%M}, limit {a.target} h, topk {a.topk}, '
          f'window {a.window} h\n', flush=True)
    import sys; sys.setrecursionlimit(10000)
    dfs(root)
    el = time.time() - t0
    print(f'\n{seen_nodes[0]} nodes in {el:.0f} s ({seen_nodes[0] / max(el, 1):.0f}/s), {cut[0]} branches cut by the limit')
    if oracle: print(f'deepest prefix of the tracked route reached: {deepest[0]}/{len(oracle)}')
    if best[0] is None:
        print(f'no route under {a.target} h found within the budget')
    else:
        print(f'best {((D - max(best[0]["cur"].values())) / 3600):.1f} h')
        if a.out:
            pickle.dump(dict(order=best[0]['picked'][::-1], deadline=D), open(f'{a.out}_dfs.pkl', 'wb'))
            print('wrote', f'{a.out}_dfs.pkl')


if __name__ == '__main__':
    main()
