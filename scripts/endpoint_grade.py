"""Grade states as start/end candidates by what they cost mid-route, measured on our best routes (Oct 24).

A start or end state is entered or left, not both, so a state that is expensive to visit in the middle of a route
is a candidate endpoint. For each route and each state: re-time the same order with that state dropped (held as
done, as route_report's marginal), and record how much earlier the route finishes. States the route only passes
through cost about nothing. Reported per state: median and range across routes, which routes start or end there,
and which of Nick's start/end families already covers it. A high, consistent cost with no family is a missed spot.

Leaf script: nothing imports it.   python3 endpoint_grade.py > ../out/endpoint_grade.md   (from scripts/)
"""
import os, pickle, statistics, sys
END_MODE = '--end' in sys.argv   # move each state to the end of the order instead of dropping it
from datetime import date
from time_router import cached_router, N_STATES
import time_search as ts
from common import ABBR

ROUTES = [  # name, pickle, router window
    ('X', '../out/res_x.pkl', (date(2026, 11, 4), 27)),
    ('Moorhead', '../out/mh_nov/eval9_fargo.pkl', (date(2026, 11, 9), 22)),
    ('Control', '../out/control_nov/eval_stl.pkl', (date(2026, 11, 4), 27)),
    ('Record', '../out/wide/rec_true.pkl', (date(2026, 11, 19), 20)),
    ('Hun Meteor', '../out/hun_ms_meteor.pkl', (date(2026, 11, 4), 27)),   # 265 h on Oct 24 data: drop mode only
    ('Wheeling', '../out/res_wheeling.pkl', (date(2026, 11, 4), 27)),
    ('RX Vegas', '../out/shapes/rx_free_end.pkl', (date(2026, 11, 4), 27)),
    ('RX Primm', '../out/ht2/rx.pkl', (date(2026, 11, 4), 27)),
    ('S9 run33', '../out/sweep9/run_33.pkl', (date(2026, 11, 9), 22)),
    ('S9 run06', '../out/sweep9/run_06.pkl', (date(2026, 11, 9), 22)),
    ('S9 run05f', '../out/sweep9/focus/frun_05.pkl', (date(2026, 11, 9), 22)),
]
FAMILY = {'SD': 'Sioux City', 'IA': 'Sioux City', 'NE': 'Sioux City', 'VT': 'Hanover/WRJ/Portland',
          'NH': 'Hanover/WRJ/Portland', 'ME': 'Hanover/WRJ/Portland', 'WY': 'Sheridan', 'MN': 'Moorhead',
          'ND': 'Moorhead', 'CA': 'Primm', 'WV': 'West Virginia', 'FL': 'Pensacola', 'AL': 'Pensacola'}

cost = {s: {} for s in range(N_STATES)}; ends = {s: [] for s in range(N_STATES)}; base = {}
routers = {}
for name, path, win in ROUTES:
    if END_MODE and name == 'Hun Meteor': continue
    if not os.path.exists(path): print(f'skip {name}: no {path}', file=sys.stderr); continue
    if win not in routers: routers[win] = cached_router(*win, verbose=False)
    R = routers[win]; d = pickle.load(open(path, 'rb'))
    t0 = d['t0']
    if 'finish' in d and 'elapsed' in d and d['finish'] - d['elapsed'] - t0 > 3600: t0 = d['finish'] - d['elapsed'] - 600
    m = R.stops_matching(d['start']); st = next((i for i in m if R.stop_name[i] == d['start']), m[0])
    S = ts.Search(R, st, t0, [], 1); ts.bind(R, st, t0, S)
    f, legs = S.evaluate(d['order'])
    if f >= 1e18 or not legs or not S.all_states(legs): print(f'skip {name}: does not evaluate', file=sys.stderr); continue
    rides = [l for l in legs if l[0] == 'ride']
    base[name] = (f - rides[0][3]) / 3600
    s_first = R.state[rides[0][2]]; last = legs[-1][2] if legs[-1][0] == 'walk' else legs[-1][4]
    ends[s_first].append(f'{name} start'); ends[R.state[last]].append(f'{name} end')
    print(f'{name}: {base[name]:.2f} h', file=sys.stderr, flush=True)
    for s in range(N_STATES):
        if s == s_first: continue   # the start stop is fixed in it: dropping it means nothing
        if END_MODE:   # finish in s: the same order with s moved last; cost = hours saved (negative = slower)
            S2 = ts.Search(R, st, t0, [], 1); ts.rebind(S2)
            f2, l2 = S2.evaluate([x for x in d['order'] if x != s] + [s])
        else:
            S2 = ts.Search(R, st, t0, [], 1, done=[s]); ts.rebind(S2)
            f2, l2 = S2.evaluate([x for x in d['order'] if x != s])
        cost[s][name] = (f - f2) / 3600 if f2 < 1e18 and S2.all_states(l2) else None
    ts.rebind(S)

if END_MODE:
    print('# End grading: each route re-timed finishing in each state\n')
    print('Hours saved when the route is re-timed with the state moved last (negative = slower). Routes: '
          + ', '.join(f'{n} {h:.1f} h' for n, h in base.items()) + '.\n')
else:
    print('# Start/end grading by mid-route state cost\n')
    print('Hours a route finishes earlier with the state dropped (same order, state held as done). Routes: '
          + ', '.join(f'{n} {h:.1f} h' for n, h in base.items()) + '.\n')
print('| rank | state | median h | min | max | routes > 3 h | family | start/end in |')
print('|---|---|---|---|---|---|---|---|')
rows = []
for s in range(N_STATES):
    v = [c for c in cost[s].values() if c is not None]
    if not v: continue
    rows.append((statistics.median(v), min(v), max(v), sum(c > 3 for c in v), len(v), ABBR[R.state_names[s]], s))
for k, (med, lo, hi, n3, n, ab, s) in enumerate(sorted(rows, reverse=True), 1):
    print(f'| {k} | {ab} | {med:.1f} | {lo:.1f} | {hi:.1f} | {n3}/{n} | {FAMILY.get(ab, "")} | {"; ".join(ends[s])} |')
print('\nPer route:\n')
for name in base:
    top = sorted(((c, ABBR[R.state_names[s]]) for s in range(N_STATES) if (c := cost[s].get(name)) is not None and (c > -6 if END_MODE else c > 1)), reverse=True)
    print(f'- {name} ({base[name]:.1f} h): ' + ', '.join(f'{a} {c:.1f}' for c, a in top[:12]))
