"""How loose is the search's bound on the branches it keeps alive? (Oct 30 2026: proofB ran 8 h one minute under X
and never emptied its queue, stalled at 36/48 in the East.) Reads the "N/48 states, H h spent, at <stop>, ... owes
..." lines a ride_search log prints for each new deepest branch and, for each, compares the hours left before the
deadline with two riding-only figures on the clock-free network of min_ride.py (fastest scheduled ride per hop,
instant transfers, walks at walking time):

  lb    max over owed y of (stop -> nearest y -> nearest end-state stop). A true lower bound on what is left: no
        route can ride less, so lb > left proves the branch dead.
  beam  a beam tour from the stop through every owed state, ending in the end state. Not a bound (a beam is an
        upper estimate of the riding floor); it says how much a tighter admissible bound could hope to kill.

usage (from scripts/):  python3 bound_gap.py ../out/proofB.log --limit 326.45 --end MN [--width 20]
Leaf script: nothing imports it.
"""
import argparse, re, time
from datetime import date
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from time_router import cached_router, N_STATES
from common import ABBR

ap = argparse.ArgumentParser()
ap.add_argument('log')
ap.add_argument('--limit', type=float, required=True, help="the search's own limit in hours on its clock (the log's 'limit')")
ap.add_argument('--end', default='MN')
ap.add_argument('--width', type=int, default=20)
a = ap.parse_args()

R = cached_router(date(2026, 11, 9), 22)
N = R.N; st = np.asarray(R.state)
code = {ABBR[R.state_names[y]]: y for y in range(N_STATES)}

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
G = csr_matrix((w[keep], (fr[keep], to[keep])), shape=(N, N))
state_stops = {y: np.where(st == y)[0] for y in range(N_STATES)}
end_y = code[a.end]
# riding time from every stop to the nearest end-state stop: one Dijkstra on the reversed network from all of them
to_end = dijkstra(G.T.tocsr(), indices=state_stops[end_y], min_only=True)


def path_states(pred, s, t):
    out, cur = set(), t
    while cur != s and cur >= 0:
        if st[cur] >= 0: out.add(int(st[cur]))
        cur = pred[cur]
    return out


def lower_bound(s, owed):
    d = dijkstra(G, indices=s)
    return max(float(np.min(d[state_stops[y]] + to_end[state_stops[y]])) for y in owed) if owed else float(to_end[s])


def beam(s, owed):
    tours = [(0.0, s, frozenset())]
    done = []
    while tours:
        nxt = {}
        for cost, u, got in tours:
            left = [y for y in owed if y not in got]
            if not left:
                done.append(cost + float(to_end[u])); continue
            dist, pred = dijkstra(G, indices=u, return_predecessors=True)
            for y in left:
                ys = state_stops[y]; j = int(np.argmin(dist[ys]))
                if not np.isfinite(dist[ys][j]): continue
                t = int(ys[j]); g2 = got | ((path_states(pred, u, t) | {y}) & owed)
                c = cost + float(dist[t]); kk = (t, g2)
                if kk not in nxt or c < nxt[kk][0]: nxt[kk] = (c, t, g2)
        tours = sorted(nxt.values(), key=lambda c: c[0])[:a.width]
    return min(done) if done else float('inf')


pat = re.compile(r'\[\s*(\d+)s\]\s+(\d+)/48 states,\s+([\d.]+) h spent, at (.+?), \d+ rides.*owes ([A-Z,]+)')
rows = []
for line in open(a.log, encoding='utf-8', errors='replace'):
    m = pat.search(line)
    if not m: continue
    secs, n, spent, stop, owes = int(m[1]), int(m[2]), float(m[3]), m[4].strip(), m[5].split(',')
    cand = [i for i in range(N) if R.stop_name[i].startswith(stop)]
    if not cand: print(f'  no stop matches {stop!r}'); continue
    owed = frozenset(code[c] for c in owes if c in code and code[c] != end_y)
    s = cand[0]; left = a.limit - spent
    t0 = time.time(); lb = lower_bound(s, owed) / 3600; bm = beam(s, owed) / 3600
    rows.append((n, spent, stop, len(owes), left, lb, bm))
    print(f'{n:2d}/48 at {stop[:28]:28s} owes {len(owes):2d}  left {left:6.1f} h   lb {lb:6.1f} h   beam {bm:6.1f} h'
          f'   {"DEAD by lb" if lb > left else ("dead by beam" if bm > left else "alive")}   ({time.time() - t0:.0f} s)', flush=True)

print(f'\n{len(rows)} branches: {sum(r[5] > r[4] for r in rows)} killed by the lower bound, '
      f'{sum(r[6] > r[4] for r in rows)} with a beam tour longer than the time left')
