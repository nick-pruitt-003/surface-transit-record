"""A fast riding-time estimate of what a branch still has to do (Oct 30 2026, option 2 of the bound-gap work): from a
stop, collect every owed state and finish in the end state, on min_ride.py's clock-free network (fastest scheduled
ride per hop, instant transfers, walks at walking time). bound_gap.py measured that a 20-wide beam of this tour
exceeds the time left on 28 of 34 branches proofB kept alive for hours, where the pair tables saw nothing; but it
cost 8-30 s a branch. This is the same tour, made cheap enough to rank a frontier:

  - a narrow beam (width 3 by default) instead of 20;
  - shortest-path trees cached per source stop (a search revisits the same stops, and every leg ends at the nearest
    stop of some state, which recurs);
  - estimates cached per (stop, owed set).

It is an estimate, not a bound: a beam can only overshoot the true riding floor, so it ranks but never prunes.

usage (from scripts/):  python3 tour_est.py ../out/proofB.log --limit 326.45 --end MN     # agreement and speed
"""
import time
from collections import OrderedDict
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from time_router import N_STATES


class TourEst:
    def __init__(self, R, end_state, width=3, cache=20000):
        N = R.N; st = np.asarray(R.state)
        key = R.cfrom.astype(np.int64) * N + R.cto.astype(np.int64)
        dur = (R.arr - R.dep).astype(np.float64)
        o = np.lexsort((dur, key)); key, dur = key[o], dur[o]
        first = np.r_[True, key[1:] != key[:-1]]
        k, w = key[first], np.maximum(dur[first], 1.0)
        fr, to = (k // N).astype(np.int64), (k % N).astype(np.int64)
        ff, ft, fw = [], [], []
        for i, edges in R.foot.items():
            for j, s in edges: ff.append(i); ft.append(j); fw.append(max(float(s), 1.0))
        fr = np.r_[fr, ff]; to = np.r_[to, ft]; w = np.r_[w, fw]
        o = np.lexsort((w, fr * N + to)); fr, to, w = fr[o], to[o], w[o]
        keep = np.r_[True, (fr[1:] != fr[:-1]) | (to[1:] != to[:-1])]
        self.G = csr_matrix((w[keep], (fr[keep], to[keep])), shape=(N, N))
        self.st, self.width, self.end = st, width, end_state
        self.state_stops = [np.where(st == y)[0] for y in range(N_STATES)]
        self.to_end = dijkstra(self.G.T.tocsr(), indices=self.state_stops[end_state], min_only=True)
        self._trees, self._est, self._cap = OrderedDict(), {}, cache
        self.calls = self.tree_builds = 0

    def _tree(self, s):
        """(nearest, passed) for source s: nearest[y] = (riding s, stop) to the closest stop of state y, and passed,
        a dict memoising the states each such path runs through. Built once per source; the beam then only looks
        up. Measured Oct 30: a tree is 29 ms, and scanning every owed state's stops per tour per level was the
        other 80% of the cost."""
        t = self._trees.get(s)
        if t is None:
            self.tree_builds += 1
            dist, pred = dijkstra(self.G, indices=s, return_predecessors=True)
            nearest = {}
            for y, ys in enumerate(self.state_stops):
                if not len(ys): continue
                j = int(np.argmin(dist[ys])); d = float(dist[ys[j]])
                if np.isfinite(d): nearest[y] = (d, int(ys[j]))
            t = (nearest, {}, pred)
            self._trees[s] = t
            if len(self._trees) > 2000: self._trees.popitem(last=False)
        else:
            self._trees.move_to_end(s)
        return t

    def _passed(self, tree, s, t):
        """Every state the path s -> t runs through (all of them; the caller intersects with what is owed)."""
        memo = tree[1]
        if t not in memo:
            out, cur, st, pred = set(), t, self.st, tree[2]
            while cur != s and cur >= 0:
                y = int(st[cur])
                if y >= 0: out.add(y)
                cur = pred[cur]
            memo[t] = frozenset(out)
        return memo[t]

    def estimate(self, s, owed):
        """Riding seconds from stop s through every state in owed (an iterable of state ids) and into the end state."""
        owed = frozenset(y for y in owed if y != self.end)
        k = (s, owed)
        if k in self._est: return self._est[k]
        self.calls += 1
        tours, best = [(0.0, s, frozenset())], float('inf')
        while tours:
            nxt = {}
            for cost, u, got in tours:
                left = [y for y in owed if y not in got]
                if not left:
                    best = min(best, cost + float(self.to_end[u])); continue
                tree = self._tree(u); nearest = tree[0]
                for y in left:
                    hit = nearest.get(y)
                    if hit is None: continue
                    d, t = hit
                    g2 = got | (self._passed(tree, u, t) & owed) | {y}
                    c = cost + d; kk = (t, g2)
                    if kk not in nxt or c < nxt[kk][0]: nxt[kk] = (c, t, g2)
            tours = sorted(nxt.values(), key=lambda c: c[0])[:self.width]
        if len(self._est) > self._cap: self._est.clear()
        self._est[k] = best
        return best


if __name__ == '__main__':
    import argparse, re
    from datetime import date
    from time_router import cached_router
    from common import ABBR
    ap = argparse.ArgumentParser()
    ap.add_argument('log'); ap.add_argument('--limit', type=float, required=True); ap.add_argument('--end', default='MN')
    a = ap.parse_args()
    R = cached_router(date(2026, 11, 9), 22)
    code = {ABBR[R.state_names[y]]: y for y in range(N_STATES)}
    t0 = time.time(); E = {w: TourEst(R, code[a.end], width=w) for w in (1, 3, 20)}
    print(f'networks built in {time.time() - t0:.0f} s', flush=True)
    pat = re.compile(r'\[\s*(\d+)s\]\s+(\d+)/48 states,\s+([\d.]+) h spent, at (.+?), \d+ rides.*owes ([A-Z,]+)')
    rows = []
    for line in open(a.log, encoding='utf-8', errors='replace'):
        m = pat.search(line)
        if not m: continue
        n, spent, stop, owes = int(m[2]), float(m[3]), m[4].strip(), m[5].split(',')
        cand = [i for i in range(R.N) if R.stop_name[i] == stop] or [i for i in range(R.N) if R.stop_name[i].startswith(stop)]
        if not cand: continue
        s = max(cand, key=lambda i: E[1].G.indptr[i + 1] - E[1].G.indptr[i])   # the matching stop with any edges
        owed = [code[c] for c in owes if c in code]
        out = []
        for w, e in E.items():
            t1 = time.time(); v = e.estimate(s, owed) / 3600; out.append((v, time.time() - t1))
        left = a.limit - spent; rows.append((left, out))
        print(f'{n:2d}/48 {stop[:24]:24s} left {left:6.1f}  ' + '  '.join(f'w{w} {v:6.1f} h {dt:5.2f} s' for w, (v, dt) in zip(E, out)), flush=True)
    for i, w in enumerate(E):
        print(f'width {w}: {sum(r[1][i][0] > r[0] for r in rows)}/{len(rows)} over the time left; '
              f'mean gap to width 20 {np.mean([r[1][i][0] - r[1][-1][0] for r in rows if np.isfinite(r[1][-1][0])]):+.1f} h; '
              f'mean {np.mean([r[1][i][1] for r in rows]):.2f} s cold')
    # warm: the same queries again hit the estimate cache; a fresh owed set at a known stop reuses the trees
    e = E[3]; t1 = time.time()
    for left, _ in rows: pass
    print(f'width 3 trees built {e.tree_builds}, estimates {e.calls}')
