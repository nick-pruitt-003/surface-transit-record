"""Independent check of a ride_search path, leg by leg (Oct 20). Leaf script: nothing imports it.

  py verify_path.py ../out/goalwork/step1b.pkl [--days 20 --d0 2026-11-12]

confirm() hands a state ORDER to Search.evaluate, which collects states greedily one target at a time. That is a
different question from "does this path exist": on step 1's 232.30 h route (X itself) the order without
pass-through states missed WV, and the order with them came back at 256.3 h, because a greedy evaluator chasing
WV, then OH, then IN as separate targets takes other buses. This replays the path itself instead:

- every leg: the router's own CSA scan (time_router.scan, not the search's menus) from where the previous leg
  ended, at that time, must reach the leg's stop no later than the search says (transfers and footpaths applied
  by the router);
- a walk-in on a leg: the stop must have a footpath to a point that collects that state, and the leg's time must
  include the walk out and back;
- the final one-way walk: a footpath of exactly that length to a point in the end state;
- the states: recounted from the connections the legs ride (their seg indices) and the walk points, not from the
  search's own got sets.
"""
import argparse, pickle
from datetime import date
from time_router import cached_router

ap = argparse.ArgumentParser()
ap.add_argument('pkl'); ap.add_argument('--d0', default='2026-11-12'); ap.add_argument('--days', type=int, default=20)
a = ap.parse_args()
d = pickle.load(open(a.pkl, 'rb'))
R = cached_router(date.fromisoformat(a.d0), a.days, verbose=False)
path = d['path']
trip_conns = {}
for k in range(len(R.dep)): trip_conns.setdefault(R.ctrip[k], []).append(k)
for v in trip_conns.values(): v.sort(key=lambda k: R.dep[k])
pos = {k: i for v in trip_conns.values() for i, k in enumerate(v)}
nm = lambda s: R.stop_name[s][:30]
states = set(); bad = []
first = next(p for p in path if p[0] is not None)
cur, t, cur_trip = first[1], first[3] - 1, None        # just before the first boarding
for i, (trip, frm, to, bt, at, walk, seg) in enumerate(path):
    if trip is None:                                   # on foot: the final walk over the end line
        w = dict(R.foot.get(frm, ())).get(to)
        if frm != cur: bad.append(f'leg {i}: walk starts at {nm(frm)}, chain is at {nm(cur)}')
        if w is None: bad.append(f'leg {i}: no footpath {nm(frm)} -> {nm(to)}')
        elif abs(t + w - at) > 1: bad.append(f'leg {i}: walk {w / 60:.0f} min, leg charges {(at - t) / 60:.0f}')
        if R.state[to] >= 0: states.add(int(R.state[to]))
        cur, t, cur_trip = to, at, None
        continue
    w2 = 0.0
    if walk is not None:
        ws = [w for j, w in R.foot.get(to, ()) if R.walk_collects(j) and int(R.state[j]) == walk]
        if not ws: bad.append(f'leg {i}: no walk-in from {nm(to)} to {R.state_names[walk]}')
        else: w2 = 2 * min(ws)
        states.add(int(walk))
    out, _, best = R.scan({cur: (t, cur_trip)}, {to})
    ra = best[to]
    if ra > at - w2 + 1:
        bad.append(f'leg {i}: router reaches {nm(to)} at +{(ra - first[3]) / 3600:.2f} h, path says '
                   f'+{(at - w2 - first[3]) / 3600:.2f} h')
    if seg:
        k_, kk_ = seg
        cs = trip_conns.get(R.ctrip[k_], [])
        i0, i1 = sorted((pos[k_], pos[kk_]))
        for c in cs[i0:i1 + 1]:
            for s_ in (int(R.cfrom[c]), int(R.cto[c])):
                if R.state[s_] >= 0: states.add(int(R.state[s_]))
    for s_ in (frm, to):
        if R.state[s_] >= 0: states.add(int(R.state[s_]))
    cur, t, cur_trip = to, at, (trip if walk is None else None)
miss = sorted(R.state_names[x] for x in range(len(R.state_names)) if x not in states)
end_state = R.state_names[R.state[cur]] if R.state[cur] >= 0 else '?'
print(f'{len(path)} legs, {(t - first[3]) / 3600:.2f} h from the first boarding, ends in {end_state}; '
      f'{len(states)} states' + (f', missing {", ".join(miss)}' if miss else ''))
for b in bad: print('  ' + b)
print('PATH VERIFIED' if not bad and not miss else 'PATH NOT VERIFIED')
