"""Score candidate lower bounds along the reference route, where the true remaining time is known.

  python3 bound_probe.py --track ../out/res_starttest.pkl --end VT --from 2026-11-14T22:14

Depth-first search with backtracking (dfs_backward.py) prunes a branch only when what it has spent plus a
floor on what is left would pass the time limit. So unlike the beam, it never needs a heuristic that ranks
chains correctly, which is the thing five attempts failed at. It needs one that is never above the truth,
and is as close to it as possible: too low and nothing is ever cut, and the tree is hopeless.

This walks the reference chain, which is the one chain whose true remainder is known at every step, and
prints each candidate floor against it. A floor above the truth is inadmissible and would cut the answer,
so it is reported as a failure however tight it looks.

  tree     spanning tree over the state-to-state matrix, what build_backward uses
  reach    furthest back the node's own scan can still get to a state it has not placed
  win      same, but counting a state the scan could NOT reach as at least a window away, which is a fact
           the scan proves and the current code throws away
  hybrid   spanning tree again, with the edges out of the current state replaced by those measured values
"""
import argparse, pickle
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import time_search as ts
from time_search import Search
import backward as B
import build_backward as BB
from common import ABBR


def mst(M):
    n = len(M)
    if n < 2: return 0.0
    inside = np.zeros(n, bool); inside[0] = True; best = M[0].copy(); tot = 0.0
    for _ in range(n - 1):
        best[inside] = np.inf; j = int(np.argmin(best)); tot += best[j]; inside[j] = True
        best = np.minimum(best, M[j])
    return float(tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--track', default='../out/res_starttest.pkl')
    ap.add_argument('--end', default='VT'); ap.add_argument('--frm', default='2026-11-14T22:14')
    ap.add_argument('--tz', default='America/New_York'); ap.add_argument('--window', type=float, default=110)
    ap.add_argument('--times', default='../out/state_times_real.npy')
    a = ap.parse_args()
    D0 = datetime.fromisoformat(a.frm).replace(tzinfo=ZoneInfo(a.tz)); D = D0.timestamp()
    R = TimeRouter(load_feeds(), (D0 - timedelta(days=12)).date(), 20)
    F = B.RevFast(R)
    ab = lambda x: ABBR[R.state_names[x]]
    inv = {v: k for k, v in ABBR.items()}
    end = R.state_names.index(inv[a.end])
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    st_arr = {x: np.array(state_stops[x], dtype=np.int64) for x in state_stops}
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    dist['M'] = np.array([[dist[x][y] for y in range(N_STATES)] for x in range(N_STATES)])
    T = np.load(a.times) if os.path.exists(a.times) else None
    if T is not None: dist['T'] = T

    d = pickle.load(open(a.track, 'rb')); st0 = R.stop_name.index(d['start'])
    S0 = Search(R, st0, d['t0'], [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0, d['t0'], S0, None, None
    f0, l0 = S0.evaluate(d['order'])
    oracle = BB.visit_sequence(R, S0, l0, st0)[::-1]
    total = (D - d['t0']) / 3600
    print(f'reference: {total:.1f} h end to end, {len(oracle)} states\n')

    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep

    def sparse(ns):
        idx = np.nonzero(ns[0] >= 0)[0]; return idx, ns[0][idx], ns[1][idx]

    nd = dict(picked=[end], left=set(range(N_STATES)) - {end}, cur={int(s): D for s in state_stops[end]}, ns=None)
    rows = []
    for step in range(1, len(oracle)):
        hi = max(nd['cur'].values()); spent = (D - hi) / 3600
        L, ok, k0, k1 = F.layer(nd['cur'], True, hi - a.window * 3600, dense(nd['ns']))
        mask = np.zeros(R.N, bool)
        for x in nd['left']: mask[st_arr[x]] = True
        eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
        h = {}
        for x in nd['left']:
            v = float(vals[st_arr[x]].max())
            if v > -np.inf: h[x] = (hi - v) / 3600
        # measured against this chain's own end, not the forward route's clock: a strict sequential backward
        # chain is a stronger requirement than the route, which collects states in passing (Kentucky twice,
        # Michigan mid-leg), so its latest times run earlier and total - spent goes negative near the start.
        truth = None
        b_tree = BB.strand_cost(nd['left'], nd['picked'][-1], dist) / 3600
        b_reach = max(h.values(), default=0.0)
        b_win = max([h.get(x, a.window) for x in nd['left']], default=0.0)
        left = sorted(nd['left'])
        if T is not None and left:
            M = np.empty((len(left) + 1, len(left) + 1))
            M[1:, 1:] = T[np.ix_(left, left)]
            row = np.array([h.get(x, a.window) for x in left])
            M[0, 1:] = row; M[1:, 0] = row; M[0, 0] = 0.0
            b_hyb = mst(M)
        else: b_hyb = 0.0
        rows.append([step, ab(nd['picked'][-1]), spent, b_tree, b_reach, b_win, b_hyb])
        xo = oracle[step]
        xm = np.zeros(R.N, bool); xm[st_arr[xo]] = True
        eff_x, ns_x = F.through(ok, k0, k1, xm)
        cur = {int(s): float(max(L[s], eff_x[s])) for s in st_arr[xo] if max(L[s], eff_x[s]) > -np.inf}
        if not cur: print('  chain breaks at', ab(xo)); break
        nd = dict(picked=nd['picked'] + [xo], left=nd['left'] - {xo}, cur=cur, ns=sparse(ns_x))

    end_spent = rows[-1][2]
    for r in rows: r[2] = end_spent - r[2]      # true remaining along this chain
    print(f'{"step":4s} {"at":3s} {"true left":>9s} {"tree":>7s} {"reach":>7s} {"win":>7s} {"hybrid":>7s}   best/true')
    bad = {k: 0 for k in ('tree', 'reach', 'win', 'hybrid')}
    ratios = []
    for step, at, truth, t_, r_, w_, hy in rows:
        for k, v in (('tree', t_), ('reach', r_), ('win', w_), ('hybrid', hy)):
            if v > truth + 1e-6: bad[k] += 1
        bestb = max(t_, r_, w_, hy)
        ratios.append(bestb / truth if truth > 0 else 1.0)
        if step % 4 == 1 or step > 43:
            print(f'{step:4d} {at:3s} {truth:9.1f} {t_:7.1f} {r_:7.1f} {w_:7.1f} {hy:7.1f}   {bestb / max(truth, .1):5.0%}')
    print(f'\nadmissibility (times a floor sat above the true remainder, which would cut the answer):')
    for k, v in bad.items(): print(f'   {k:7s} {v}/{len(rows)}' + ('  <-- INADMISSIBLE' if v else '  ok'))
    print(f'\nbest admissible floor averages {np.mean(ratios):.0%} of the truth '
          f'(the tree alone averages {np.mean([t / max(tr, .1) for _, _, tr, t, _, _, _ in rows]):.0%}).')


if __name__ == '__main__':
    main()
