"""What does each state cost a route? Drop it from the route's own order and re-evaluate. Leaf script.

The saving is a lower bound on the state's cost: the rest of the order is kept as is, not re-optimised, and a
state the route only passes through (not in its pruned order) shows 0 because the route never goes out of its
way for it. The start state cannot be dropped this way and is reported as such.

  py state_cost.py [--pickle ../out/res_x.pkl] [--router 2026-11-04 27]
"""
import argparse, pickle
from datetime import date
from time_router import cached_router
import time_search as ts
from time_search import Search
from common import ABBR

ap = argparse.ArgumentParser()
ap.add_argument('--pickle', default='../out/res_x.pkl')
ap.add_argument('--router', nargs=2, default=['2026-11-04', '27'])
a = ap.parse_args()
R = cached_router(date.fromisoformat(a.router[0]), int(a.router[1]), verbose=False)
d = pickle.load(open(a.pickle, 'rb'))
st = R.stops_matching(d['start'])[0]
S = Search(R, st, d['t0'], [], 1); ts.bind(R, st, d['t0'], S)
f0, legs0 = S.evaluate(d['order'])
fb = next(l for l in legs0 if l[0] == 'ride')[3]
base = (f0 - fb) / 3600
print(f'{d["start"]}: {base:.2f} h from the first bus; order {len(d["order"])} entries', flush=True)
start_state = int(R.state[st])
rows = []
for x in d['order']:
    if isinstance(x, str): continue                    # '@stop' pins stay where they are
    if x == start_state: rows.append((x, None)); continue
    o = [y for y in d['order'] if y != x]
    f, legs = S.evaluate(o)
    if f >= 1e18 or not legs: rows.append((x, float('nan'))); continue
    fb_ = next(l for l in legs if l[0] == 'ride')[3]
    rows.append((x, base - (f - fb_) / 3600))
listed = {x for x, _ in rows}
for x, s in sorted(rows, key=lambda r: -(r[1] if r[1] == r[1] and r[1] is not None else -1e9)):
    print(f'  {ABBR[R.state_names[x]]:>3}  ' + ('start state' if s is None else 'did not evaluate' if s != s else f'{s:+7.2f} h'))
print('  passed through, not in the order (cost ~0 on this route): '
      + ' '.join(sorted(ABBR[n] for i, n in enumerate(R.state_names) if i not in listed)), flush=True)
print('  pins: ' + ', '.join(x for x in d['order'] if isinstance(x, str)))
