"""Minimum riding time through all 48 states if every connection were instant (Nick, Oct 29 2026: "what is the
minimum ride time"). A curiosity, and a floor: no route can ride less than this, so a route's waiting time is its
total minus at least this.

The network is the timetable with the clocks taken out: an edge between two consecutive stops of any trip costs the
fastest scheduled ride over that hop in the router window, plus every footpath and walk-in at its walking time. A
path through it collects every state of every stop it touches (a ride passing through a state counts, as in
verify_path). The tour is found by a beam search: each partial tour (stop, states) is extended by one Dijkstra to
the nearest stop of each state still owed, the path's pass-through states collected on the way, and the best
--width tours per state count are kept. That makes the answer an upper bound on the true minimum, tight in practice
for wide beams; nothing here is an estimate, every number is a sum of scheduled rides and measured walks.

usage (from scripts/):  python3 min_ride.py [--width 40] [--limit 60]
Leaf script: nothing imports it.
"""
import argparse, time
from datetime import date
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from time_router import cached_router, N_STATES
from common import ABBR

ap = argparse.ArgumentParser()
ap.add_argument('--width', type=int, default=40, help='tours kept per number of states collected')
ap.add_argument('--limit', type=float, default=60, help='hours a single Dijkstra looks ahead')
a = ap.parse_args()
R = cached_router(date(2026, 11, 9), 22)
N = R.N; st = np.asarray(R.state)
t0 = time.time()

# fastest ride per (from, to) hop, then the footpaths
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
# duplicate (from, to) pairs between rides and walks: keep the smaller
o = np.lexsort((w, fr * N + to)); fr, to, w = fr[o], to[o], w[o]
keep = np.r_[True, (fr[1:] != fr[:-1]) | (to[1:] != to[:-1])]
G = csr_matrix((w[keep], (fr[keep], to[keep])), shape=(N, N))
print(f'network: {N} stops, {G.nnz} edges in {time.time() - t0:.0f} s', flush=True)

state_stops = {y: np.where(st == y)[0] for y in range(N_STATES)}
name = lambda i: f'{R.stop_name[i]}, {R.abbr[i]}'


def path_states(pred, s, t):
    out, cur = set(), t
    while cur != s and cur >= 0:
        if st[cur] >= 0: out.add(int(st[cur]))
        cur = pred[cur]
    return out


def extend(tour):
    cost, s, got, legs = tour
    dist, pred = dijkstra(G, indices=s, return_predecessors=True, limit=a.limit * 3600)
    kids = []
    for y in range(N_STATES):
        if y in got: continue
        ys = state_stops[y]; d = dist[ys]
        j = int(np.argmin(d))
        if not np.isfinite(d[j]): continue
        t = int(ys[j]); g2 = got | path_states(pred, s, t) | {y}
        kids.append((cost + float(d[j]), t, frozenset(g2), legs + ((s, t, float(d[j]), y),)))
    return kids


# level 0: every state's stops are candidate starts; seed with each state's best-connected stop (most edges)
deg = np.diff(G.indptr)
pending = {n: [] for n in range(1, N_STATES)}
for y in range(N_STATES):
    ys = state_stops[y]
    if len(ys): pending[1].append((0.0, int(ys[np.argmax(deg[ys])]), frozenset({y}), ()))
done = []
for n in range(1, N_STATES):   # one level at a time: a tour with n states only ever extends to more than n
    best = {}
    for c in pending.pop(n):
        kk = (c[1], c[2])
        if kk not in best or c[0] < best[kk][0]: best[kk] = c
    beam = sorted(best.values(), key=lambda c: c[0])[:a.width if n > 1 else len(best)]
    if not beam: continue
    for t in beam:
        for c in extend(t):
            (done if len(c[2]) >= N_STATES else pending[len(c[2])]).append(c)
    print(f'{time.time() - t0:5.0f} s  {n:2d} states: {len(beam)} tours, best {beam[0][0] / 3600:.2f} h; complete so far '
          f'{min((c[0] for c in done), default=float("inf")) / 3600:.2f} h', flush=True)

b = min(done, key=lambda c: c[0])
print(f'\nbeam: {b[0] / 3600:.2f} h ({len(b[3])} hops)', flush=True)

# Cleanup (Nick, Oct 29: "why would you go to West Wendover if you're getting Nevada later anyways"). The beam aims
# each hop at one state and never looks back, so a state it targeted early can be collected for free by a later hop
# passing through (Beaver Dam -> Primm crosses Nevada). Re-time a tour from its state order alone, skipping any state
# a previous hop already passed through, and move or drop states in that order while the total falls.
_cache = {}
def sp(s):
    if s not in _cache:
        if len(_cache) > 4000: _cache.clear()
        _cache[s] = dijkstra(G, indices=s, return_predecessors=True, limit=a.limit * 3600)
    return _cache[s]


def evaluate(start, order):
    s, got, cost, legs = start, {int(st[start])}, 0.0, []
    for y in order:
        if y in got: continue
        dist, pred = sp(s); ys = state_stops[y]; d = dist[ys]; j = int(np.argmin(d))
        if not np.isfinite(d[j]): return float('inf'), None
        t = int(ys[j]); got |= path_states(pred, s, t) | {y}
        cost += float(d[j]); legs.append((s, t, float(d[j]), y)); s = t
    if len(got) < N_STATES: return float('inf'), None
    return cost, legs


start = b[3][0][0]
order = [y for *_, y in b[3]]
order += [y for y in range(N_STATES) if y not in order and y != st[start]]   # the pass-through states, as fallbacks
best_c, best_l = evaluate(start, order)
improved = True
while improved:
    improved = False
    for i in range(len(order)):
        for j in range(len(order)):
            if i == j: continue
            o2 = order[:i] + order[i + 1:]; o2.insert(j, order[i])
            c, l = evaluate(start, o2)
            if c < best_c - 1:
                best_c, best_l, order, improved = c, l, o2, True
                print(f'  move {ABBR[R.state_names[o2[j]]]}: {best_c / 3600:.2f} h', flush=True)
                break
        if improved: break

print(f'\nminimum riding time found: {best_c / 3600:.2f} h ({len(best_l)} hops)')
for s, t, d, y in best_l:
    print(f'  {d / 3600:6.2f} h  {name(s)} -> {name(t)}   (for {ABBR[R.state_names[y]]})')
