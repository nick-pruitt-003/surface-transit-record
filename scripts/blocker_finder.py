"""Blocker finder: which targets and which missed departures hold a finished route back.

  python3 blocker_finder.py --route ../out/res_fixFargoDenver.pkl --start "White River Junction" \
      --at 2026-11-05T04:20 --tz America/New_York [--days 16] [--gain 3]

Part 1, drop tests. Every target in the route's order (state or @pin) is dropped singly, in pairs, and in
triples of nearby targets, and the route is re-timed. A drop that finishes >= --gain hours earlier means
those targets together hold a once-daily departure; a pair that gains when neither single does is a joint
blocker (like ND+MN+WI in the 237.5 route). Only minimal sets are listed (no gaining subset). States the
route stops covering in passing are named, since they would also have to come from somewhere else.

Part 2, near misses. For each ride leg, the latest earlier departure from the same stop that reaches the
same alighting stop (any trip, within 36 h). "need" is how much earlier you would have to be ready at the
boarding stop to catch it, "gain" how much earlier you would arrive. Small need + big gain = where local
transit or a faster feeder is worth looking for.

One router process; safe alongside nothing else (see run rules in docs/HANDOFF.md).
"""
import argparse, itertools, pickle
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds
from time_search import Search


def label(R, x):
    return x if isinstance(x, str) else R.state_names[x]


def expand(R, S, order, legs):
    """Every state in the order the route first reaches it; pins stay at the leg that first reaches them."""
    pins = [x for x in order if isinstance(x, str)]; pin_sets = {p: R.target_set(p) for p in pins}
    seq, seen, pi = [], set(S.done) | ({int(R.state[S.start])} if R.state[S.start] >= 0 else set()), 0
    for l in legs:
        if l[0] == 'walk':
            stops = [l[2]]
        elif l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            fi, tid, _ = trip; f = R.feeds[fi]; ids = [R.idx[f.stops[s[1]][0]] for s in f.trips[tid]['stops']]
            i, j = ids.index(bs), ids.index(al); stops = ids[i:j + 1] if i <= j else ids[j:i + 1][::-1]
        else: continue
        for s in stops:
            st = int(R.state[s])
            if st >= 0 and st not in seen: seen.add(st); seq.append(st)
            while pi < len(pins) and s in pin_sets[pins[pi]]: seq.append(pins[pi]); pi += 1
    return seq + pins[pi:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True); ap.add_argument('--start', required=True)
    ap.add_argument('--at', required=True); ap.add_argument('--tz', required=True)
    ap.add_argument('--days', type=int, default=16); ap.add_argument('--gain', type=float, default=3.0)
    ap.add_argument('--window', type=int, default=5, help='max position spread for triples')
    a = ap.parse_args()
    Z = ZoneInfo(a.tz); t0 = datetime.fromisoformat(a.at).replace(tzinfo=Z).timestamp()
    R = TimeRouter(load_feeds(), datetime.fromisoformat(a.at).date(), a.days)
    start = R.stops_matching(a.start)[0]
    S = Search(R, start, t0, [], 1)
    saved = pickle.load(open(a.route, 'rb')); order = list(saved['order'])
    hrs = lambda f: (f - t0) / 3600
    f0, legs0 = S.evaluate(order)
    print(f'saved {hrs(saved["finish"]):.1f} h, re-timed on current data {hrs(f0):.1f} h, all states: {S.all_states(legs0)}')
    if not S.all_states(legs0):   # data changed since the search: put the missing states back where they cost least
        print('  missing', [label(R, s) for s in S.missing(legs0)], '-> repairing')
        import time_search as ts
        ts._R, ts._START, ts._T0, ts._BASE, ts._SELF = R, start, t0, None, S
        order, f0, legs0 = S.repair(order, None)
        print(f'  repaired: {hrs(f0):.1f} h, all states: {S.all_states(legs0)}')
    # Expand to every state as an explicit target in first-visit order (pins kept where the route reaches
    # them), so dropping one target frees only that state and the route must still collect all the others.
    order = expand(R, S, order, legs0)
    f1 = R.finish(start, t0, order)
    print(f'expanded to {len(order)} targets: {hrs(f1):.1f} h (pruned route {hrs(f0):.1f} h)')
    f0 = f1
    print('order:', ' > '.join(label(R, x) for x in order), '\n', flush=True)
    fin = lambda o: R.finish(start, t0, o)

    # ---- part 1: drop tests
    n = len(order); gains = {}
    def test(idx):
        o = [x for k, x in enumerate(order) if k not in idx]
        f = fin(o); g = (f0 - f) / 3600 if f is not None else 0.0
        gains[idx] = g; return g
    for k in range(n): test(frozenset([k]))
    for i, j in itertools.combinations(range(n), 2): test(frozenset([i, j]))
    for c in itertools.combinations(range(n), 3):
        if c[-1] - c[0] <= a.window: test(frozenset(c))
    minimal = []
    for idx, g in sorted(gains.items(), key=lambda kv: (len(kv[0]), -kv[1])):
        if g < a.gain: continue
        if any(m < idx and gains[m] >= g - 0.5 for m in minimal): continue   # a subset already explains it
        minimal.append(idx)
    print(f'PART 1: minimal target sets whose drop gains >= {a.gain} h')
    if not minimal: print('  none: no single, pair or nearby triple of targets holds a departure')
    for idx in sorted(minimal, key=lambda m: -gains[m])[:25]:
        names = ' + '.join(label(R, order[k]) for k in sorted(idx))
        tail = '   (end of route: gain is just its own cost)' if max(idx) >= n - len(idx) else ''
        print(f'  -{gains[idx]:5.1f} h  {names}{tail}')
    print(flush=True)

    # ---- part 2: near misses
    by_trip = defaultdict(list)
    for k, key in enumerate(R.ctrip): by_trip[key].append(k)
    from_stop = defaultdict(list)   # stop -> [(dep, trip key, position in trip)]
    for key, ks in by_trip.items():
        ks.sort(key=lambda k: R.dep[k])
        for p, k in enumerate(ks): from_stop[int(R.cfrom[k])].append((float(R.dep[k]), key, p))
    ready = t0; out = []
    fmt = lambda t, s: R.fmt_time(t, s)
    for l in legs0:
        if l[0] == 'walk': ready = l[4]; continue
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        best = None
        for dep, key, p in from_stop.get(bs, ()):
            if not (bt - 36 * 3600 <= dep < bt - 60) or key == trip: continue
            for k in by_trip[key][p:]:
                if int(R.cto[k]) == al:
                    if R.arr[k] < at - 1800 and (best is None or dep > best[0]): best = (dep, float(R.arr[k]))
                    break
        if best:
            need, gain = (ready - best[0]) / 3600, (at - best[1]) / 3600
            out.append((need, gain, bs, al, bt, best))
        ready = at
    print(f'PART 2: earlier departures on the same stop pair (need = hours earlier you must be ready)')
    for need, gain, bs, al, bt, (d2, a2) in sorted([r for r in out if r[1] >= a.gain], key=lambda r: r[0])[:15]:
        print(f'  need {need:5.1f} h -> gain {gain:5.1f} h  {R.stop_name[bs][:30]:30s} -> {R.stop_name[al][:28]:28s} '
              f'took {fmt(bt, bs)}, earlier one {fmt(d2, bs)}')


if __name__ == '__main__':
    main()
