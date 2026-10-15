"""Re-evaluate saved routes (result pickles) under the current environment. Leaf script: nothing imports it.

  BUS48_LOCAL_MAX_KM=40 py eval_pickles.py     # what if every intercity stop within 40 km were linked?

Prints each route's hours from the first bus and every ride or modelled hop over 10 km, so a gain names the link.
"""
import pickle
from datetime import date, datetime, timezone
from time_router import cached_router, hav
import time_search as ts
from time_search import Search

ROUTES = [  # name, pickle, router window, start clock override (as redundancy.py)
    ('X', '../out/res_x.pkl', (date(2026, 11, 4), 27), None),
    ('Moorhead', '../out/mh_nov/eval9.pkl', (date(2026, 11, 9), 22), datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc).timestamp()),
    ('Control', '../out/control_nov/eval_stl.pkl', (date(2026, 11, 4), 27), None),
    ('Record', '../out/wide/rec_true.pkl', (date(2026, 11, 19), 20), None),
]
routers = {}
for name, path, win, t_over in ROUTES:
    if win not in routers: routers[win] = cached_router(*win, verbose=False)
    R = routers[win]; d = pickle.load(open(path, 'rb'))
    t0 = d['t0']
    if 'finish' in d and d['finish'] - d['elapsed'] - t0 > 3600: t0 = d['finish'] - d['elapsed'] - 600
    if t_over: t0 = t_over
    st = R.stops_matching(d['start'])[0]
    S = Search(R, st, t0, [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st, t0, S, None, None
    f, legs = S.evaluate(d['order'])
    if f >= 1e18 or not legs: print(f'== {name}: no finish', flush=True); continue
    fb = next(l for l in legs if l[0] == 'ride')
    print(f'== {name}: {(f - fb[3]) / 3600:.2f} h, missing {[R.state_names[s] for s in S.missing(legs)] or "none"}', flush=True)
    for l in legs:
        a, b = (l[2], l[4]) if l[0] == 'ride' else (l[1], l[2])
        if l[0] != 'ride' and a < R.first_virtual and b < R.first_virtual and hav(R.stop_xy[a], R.stop_xy[b]) > 10:
            print(f'   long hop {hav(R.stop_xy[a], R.stop_xy[b]):.1f} km  {R.stop_name[a]} -> {R.stop_name[b]}  at {R.fmt_time(l[3], a)}', flush=True)
