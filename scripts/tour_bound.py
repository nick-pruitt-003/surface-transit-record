"""How close can a valid riding-time bound get to the true riding floor of a branch? (Oct 31 2026, step 1 and 2 of
option 1 in docs/proof_attempt.md.) The search keeps branches alive that cannot finish, because pairs and triples of
owed states never see a whole-tour shortfall; bound_gap.py showed a whole-tour figure would kill most of them, but
only as an estimate. This measures, per branch, a feasible tour and a lower bound on the same clock-free network
(min_ride.py's: fastest scheduled ride per hop, instant transfers, walks at walking time), so the true floor is
pinned between them.

The exact problem. Order the owed states by when a route first enters each; the stop where it first enters state y is
the head of an edge crossing into y (an "entry stop": 3363 of 59283 stops). Between consecutive first entries the
route rides at least the shortest path between those two entry stops, and conversely any sequence of one entry stop
per owed state, joined by shortest paths, collects them all. So the floor is a generalised TSP path over entry stops
with the shortest-path metric: start stop -> one entry stop per owed state, in some order -> the end state.

  ub     a feasible tour: the order from the 20-wide beam, entry stops chosen optimally for that order (a layered
         min-plus pass), then improved by moving states and reversing runs until nothing helps. >= the floor.
  lb1    the single worst owed state: min over its entry stops b of (start -> b -> end). <= the floor.
  lbm    the matrix bound: D[A][B] = min over entry stops of A and B of the distance, then the exact best path over
         that matrix (Held-Karp DP). Teleports inside each state, so <= the floor. Over 18 owed states it is the DP
         on the 18 farthest, still a valid bound (fewer states can only need less riding).

A branch is provably dead when a bound exceeds the hours left; ub > left says only that the beam-style estimate
would have pruned it.

usage (from scripts/):  python3 tour_bound.py ../out/proofB.log --limit 326.45 --end MN
Leaf script: nothing imports it.
"""
import argparse, os, re, time
from datetime import date
import numpy as np
from scipy.sparse.csgraph import dijkstra
from time_router import cached_router, N_STATES
from common import ABBR
from tour_est import TourEst

DP_MAX = 18


def entry_matrix(G, st, out_dir):
    """Shortest riding seconds between every pair of entry stops, cached on disk (about 100 s to build)."""
    C = G.tocoo()
    heads = np.unique(C.col[(st[C.row] != st[C.col]) & (st[C.col] >= 0)])
    path = os.path.join(out_dir, f'entry_dd_{G.shape[0]}_{G.nnz}_{len(heads)}.npy')
    if os.path.exists(path):
        return heads, np.load(path)
    t0 = time.time(); DD = np.empty((len(heads), len(heads)), np.float32)
    for i in range(0, len(heads), 200):
        DD[i:i + 200] = dijkstra(G, indices=heads[i:i + 200])[:, heads]
    np.save(path, DD)
    print(f'entry-stop matrix {len(heads)}x{len(heads)} built in {time.time() - t0:.0f} s', flush=True)
    return heads, DD


def order_cost(order, first, DD, last, idx):
    """Exact riding for a fixed order of owed states, entry stops chosen optimally: first[c] is start -> each entry
    stop of the first state, last[c] each entry stop -> end, idx[y] the rows of DD for state y."""
    cur = first[order[0]]
    for a, b in zip(order, order[1:]):
        cur = np.min(cur[:, None] + DD[np.ix_(idx[a], idx[b])], axis=0)
    return float(np.min(cur + last[order[-1]]))


def improve(order, cost_fn):
    """Move one state anywhere, or reverse a run, while it lowers the cost."""
    best, order = cost_fn(order), list(order)
    better = True
    while better:
        better = False
        for i in range(len(order)):
            y, rest = order[i], order[:i] + order[i + 1:]
            for j in range(len(rest) + 1):
                if j == i: continue
                cand = rest[:j] + [y] + rest[j:]
                c = cost_fn(cand)
                if c < best - 1e-6: best, order, better = c, cand, True; break
            if better: break
        if better: continue
        for i in range(len(order) - 1):
            for j in range(i + 2, len(order) + 1):
                cand = order[:i] + order[i:j][::-1] + order[j:]
                c = cost_fn(cand)
                if c < best - 1e-6: best, order, better = c, cand, True; break
            if better: break
    return best, order


def matrix_lb(start, D, end):
    """Exact shortest Hamiltonian path start -> all k nodes -> end over matrix D (k <= DP_MAX)."""
    k = len(start)
    full = 1 << k
    dp = np.full((full, k), np.inf, np.float32)
    for j in range(k): dp[1 << j, j] = start[j]
    pc = np.array([bin(m).count('1') for m in range(full)])
    for size in range(1, k):
        M = np.where(pc == size)[0]
        vals = dp[M]                                           # (m, k): cost ending at i
        cand = np.min(vals[:, :, None] + D[None, :, :], axis=1)  # (m, k): best cost to then step to j
        for j in range(k):
            sel = (M & (1 << j)) == 0
            if not sel.any(): continue
            tgt = M[sel] | (1 << j)
            np.minimum.at(dp[:, j], tgt, cand[sel, j])
    return float(np.min(dp[full - 1] + end))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log'); ap.add_argument('--limit', type=float, required=True); ap.add_argument('--end', default='MN')
    a = ap.parse_args()
    R = cached_router(date(2026, 11, 9), 22)
    code = {ABBR[R.state_names[y]]: y for y in range(N_STATES)}
    E = TourEst(R, code[a.end], width=20)
    st = E.st
    heads, DD = entry_matrix(E.G, st, os.path.join(os.path.dirname(os.path.abspath(a.log))))
    hstate = st[heads]
    idx = {y: np.where(hstate == y)[0] for y in range(N_STATES)}
    to_end_h = E.to_end[heads]
    pat = re.compile(r'\[\s*(\d+)s\]\s+(\d+)/48 states,\s+([\d.]+) h spent, at (.+?), \d+ rides.*owes ([A-Z,]+)')
    rows = []
    for line in open(a.log, encoding='utf-8', errors='replace'):
        m = pat.search(line)
        if not m: continue
        n, spent, stop, owes = int(m[2]), float(m[3]), m[4].strip(), m[5].split(',')
        cands = [i for i in range(R.N) if R.stop_name[i] == stop] or \
                [i for i in range(R.N) if R.stop_name[i].startswith(stop)]
        owed = [code[c] for c in owes if c in code and code[c] != code[a.end]]
        if not cands or not owed: continue
        left = (a.limit - spent) * 3600
        t0 = time.time(); best = None
        # several stops can share a printed name: take the least of each figure over them, so every bound stays valid
        for s in cands:
            dS = dijkstra(E.G, indices=s)
            first = {y: dS[heads[idx[y]]] for y in owed}
            last = {y: to_end_h[idx[y]] for y in owed}
            lb1 = max(float(np.min(first[y] + last[y])) for y in owed)
            Dm = np.array([[0 if x == y else float(np.min(DD[np.ix_(idx[x], idx[y])])) for y in owed] for x in owed],
                          np.float32)
            sv = np.array([float(np.min(first[y])) for y in owed], np.float32)
            ev = np.array([float(np.min(last[y])) for y in owed], np.float32)
            pick = list(range(len(owed)))
            if len(owed) > DP_MAX:
                pick = sorted(pick, key=lambda i: -(sv[i] + ev[i]))[:DP_MAX]
            lbm = matrix_lb(sv[pick], Dm[np.ix_(pick, pick)], ev[pick])
            beam = E.estimate(s, owed)
            # the beam's own order: re-derive it greedily from the matrix is not needed; start from nearest-first
            order = sorted(owed, key=lambda y: float(np.min(first[y])))
            cost = lambda o: order_cost(o, first, DD, last, idx)
            ub = improve(order, cost)[0] if len(owed) <= 30 else float('inf')   # early branches: beam only
            fig = (lb1, max(lb1, lbm), min(ub, beam), beam)
            best = fig if best is None else tuple(min(p, q) for p, q in zip(best, fig))
        lb1, lbm, ub, beam = (v / 3600 for v in best); L = left / 3600
        rows.append((n, L, lb1, lbm, ub, beam))
        print(f'{n:2d}/48 {stop[:26]:26s} owes {len(owed):2d}  left {L:6.1f}  lb1 {lb1:6.1f}  lbm {lbm:6.1f}  '
              f'ub {ub:6.1f}  beam {beam:6.1f}  gap {100 * (ub - lbm) / ub if ub else 0:5.1f}%  {time.time() - t0:5.1f} s',
              flush=True)
    R_ = np.array([r[1:] for r in rows])
    print(f'\n{len(rows)} branches: dead by lb1 {int((R_[:, 1] > R_[:, 0]).sum())}, by lbm {int((R_[:, 2] > R_[:, 0]).sum())}; '
          f'ub over the time left {int((R_[:, 3] > R_[:, 0]).sum())}, beam {int((R_[:, 4] > R_[:, 0]).sum())}; '
          f'median gap ub-lbm {np.median(100 * (R_[:, 3] - R_[:, 2]) / R_[:, 3]):.1f}%')


if __name__ == '__main__':
    main()
