"""Mechanical seed orders for an unguided search sweep: no shape ideas, just many different plausible tours.

Each seed starts in a random state and repeatedly moves to a near unvisited state, picking among the nearest
few with random weights, then straightens the tour with 2-opt, so tours differ but stay geographic (a purely random order of 48 states evaluates to
hundreds of hours and local search cannot climb out of it). Centroids are the mean of each state's stops.

Leaf script: nothing imports it.   python3 random_seeds.py N SEED > seeds.txt   (one comma list per line)
"""
import random, sys
from datetime import date
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR

n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 48)
R = cached_router(date(2026, 9, 24), 20, verbose=False)
xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float); st = np.asarray(R.state[:R.first_virtual])
cen = {s: xy[st == s].mean(axis=0) for s in range(N_STATES)}
km = lambda a, b: float(np.hypot((cen[a][0] - cen[b][0]) * 85, (cen[a][1] - cen[b][1]) * 111))
for _ in range(n):
    cur = rng.randrange(N_STATES); order = [cur]; left = set(range(N_STATES)) - {cur}
    while left:
        near = sorted(left, key=lambda s: km(cur, s))[:4]
        cur = rng.choices(near, weights=[8, 4, 2, 1][:len(near)])[0]
        order.append(cur); left.discard(cur)
    # 2-opt on the open path (start kept fixed): the noisy walk strands far states at the end (SC -> WA -> TX), and a
    # tour like that runs past the router's 20-day window, so every seed straightens out its crossings first
    better = True
    while better:
        better = False
        for i in range(1, len(order) - 1):
            for j in range(i + 1, len(order)):
                a, b = order[i - 1], order[i]; c = order[j]; d = order[j + 1] if j + 1 < len(order) else None
                old = km(a, b) + (km(c, d) if d is not None else 0); new = km(a, c) + (km(b, d) if d is not None else 0)
                if new < old - 1e-6: order[i:j + 1] = order[i:j + 1][::-1]; better = True
    print(','.join(ABBR[R.state_names[s]] for s in order))
