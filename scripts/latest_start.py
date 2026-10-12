"""Latest start in a state that keeps a route's finish: sweep every stop in the state and start clock.

  python3 latest_start.py --route ../out/hun_ms_meteor.pkl --state WV --day 2026-11-05 [--from 0 --to 9]

For each stop in the state, the latest start time (10-min steps) whose finish is no later than the
route's own finish, then the actual first boarding of that run. Answers "how late can we leave and still
make the first once-daily departure" without assuming which bus gets there.
"""
import argparse, pickle
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, STATE_TZ
from common import ABBR

ap = argparse.ArgumentParser()
ap.add_argument('--route', required=True); ap.add_argument('--state', required=True); ap.add_argument('--day', required=True)
ap.add_argument('--from', dest='h0', type=float, default=0); ap.add_argument('--to', dest='h1', type=float, default=9)
ap.add_argument('--finish', type=float, help='target finish (unix); default: the saved route finish')
a = ap.parse_args()
d = pickle.load(open(a.route, 'rb')); order = d['order']; target = a.finish or d['finish']
inv = {v: k for k, v in ABBR.items()}
tz = ZoneInfo(STATE_TZ[a.state]); day = datetime.fromisoformat(a.day).replace(tzinfo=tz)
R = TimeRouter(load_feeds(), (day - timedelta(days=1)).date(), 14)
st = R.state_names.index(inv[a.state])
deps = np.bincount(R.cfrom, minlength=R.N)
stops = [i for i in range(R.N) if R.state[i] == st and deps[i] > 0]
print(f'{len(stops)} stops in {a.state} with departures; target finish {datetime.fromtimestamp(target, tz):%a %H:%M}', flush=True)
res = []
for s in stops:
    best = None
    for m in np.arange(a.h0 * 60, a.h1 * 60 + 1, 10):
        t0 = (day + timedelta(minutes=float(m))).timestamp()
        f = R.finish(s, t0, order)
        if f is not None and f <= target + 60: best = t0
    if best: res.append((best, s))
res.sort(reverse=True)
for t0, s in res[:12]:
    f, legs = R.route(s, t0, order)
    rides = [l for l in legs if l[0] == 'ride']
    first = rides[0]; how = R.describe([first]).strip()
    print(f'{R.stop_name[s][:40]:40s} start {datetime.fromtimestamp(t0, tz):%H:%M}  first bus {datetime.fromtimestamp(first[3], tz):%H:%M}  total {(f - first[3]) / 3600:.1f} h | {how[:150]}', flush=True)
