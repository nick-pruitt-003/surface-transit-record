"""How long the 237.3 h control spends on each region of docs/regions.md.

For every state, the first moment the control touches it: the arrival at the first stop in that state on a
ridden segment (the same rule as Search.covered), or a border walk-in's arrival. Three measures per region:

  attributed: each gap between successive first touches is charged to the state(s) collected at its end,
              split evenly when several arrive together. Summed over all 48 states this is first bus to
              finish, so the regions partition the route.
  in-region:  only the gaps that both start and end on a state of the region, so no entry cost. The region
              tests start inside the region for free, so this is the fairer floor; attributed is the ceiling.
  span:       first touch of any region state to the last first touch of one. Includes whatever the control
              does elsewhere in between, so it is an upper bound on what the region "costs" it.

Leaf script: nothing imports it.  python3 region_control.py  (from scripts/, needs ../out/res_starttest.pkl)
"""
import pickle
from datetime import date
from collections import defaultdict
import numpy as np
from time_router import cached_router
from time_search import Search
from common import ABBR

REGIONS = {
    'W7': 'WA,ID,OR,CA,NV,UT,AZ', 'NE': 'ME,NH,VT,MA,RI,CT,NY', 'COAST': 'NJ,PA,DE,MD,VA,NC,SC,GA,FL',
    'SOUTH': 'TN,MS,AR,LA,AL,TX,OK', 'PLAINS': 'MN,WI,ND,SD,NE,IA,KS,MO', 'LAKES': 'IL,IN,MI,OH,KY,WV',
}

R = cached_router(date(2026, 11, 5), 20, verbose=False)
d = pickle.load(open('../out/res_starttest.pkl', 'rb'))
start = R.stop_name.index(d['start'])
S = Search(R, start, d['t0'], [], 1)
f, legs = S.evaluate(d['order'])
assert S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]
rides = [l for l in legs if l[0] == 'ride']
first_bus = rides[0][3]

# per-stop arrival times on each ridden trip, from the router's own connections (one pass)
keys = {l[1] for l in rides}
times = defaultdict(list)          # trip -> [(dep, from, arr, to)]
for k, key in enumerate(R.ctrip):
    if key in keys: times[key].append((R.dep[k], R.cfrom[k], R.arr[k], R.cto[k]))

touch = {int(R.state[start]): first_bus} if R.state[start] >= 0 else {}
for l in legs:
    if l[0] == 'walk' and R.walk_collects(l[2]):
        touch.setdefault(int(R.state[l[2]]), l[4])
    if l[0] != 'ride': continue
    _, trip, bs, bt, al, at = l
    s0 = int(R.state[bs])
    if s0 >= 0: touch.setdefault(s0, bt)
    for dep, a, arr, b in sorted(times[trip]):
        if dep < bt - 1 or arr > at + 1: continue
        s = int(R.state[b])
        if s >= 0: touch[s] = min(touch.get(s, arr), arr)
assert len(touch) == 48, sorted(set(range(48)) - set(touch))

ab = {i: ABBR[n] for i, n in enumerate(R.state_names)}
seq = sorted(touch.items(), key=lambda kv: kv[1])
attr = {}; prev = first_bus; groups = defaultdict(list)
for s, t in seq: groups[t].append(s)
for t in sorted(groups):
    for s in groups[t]: attr[ab[s]] = (t - prev) / 3600 / len(groups[t])
    prev = t
total = (f - first_bus) / 3600
print(f'control: {d["start"]}, first bus {R.fmt_time(first_bus, rides[0][2])}, finish {R.fmt_time(f, rides[-1][4])}, '
      f'{total:.2f} h; last first-touch {(prev - first_bus) / 3600:.2f} h')
print('order of first touches:', ' '.join(f'{ab[s]}@{(t - first_bus) / 3600:.1f}' for s, t in seq))
print()
seq_ab = [ab[s] for s, _ in seq]; seq_t = [t for _, t in seq]
print(f'{"region":7} {"attributed h":>12} {"in-region h":>11} {"span h":>8}  first touch -> last')
for name, sts in REGIONS.items():
    sts = sts.split(','); ts = [touch[next(i for i, a in ab.items() if a == x)] for x in sts]
    a = sum(attr[x] for x in sts)
    inr = sum(seq_t[k] - seq_t[k - 1] for k in range(1, len(seq)) if seq_ab[k] in sts and seq_ab[k - 1] in sts) / 3600
    print(f'{name:7} {a:12.1f} {inr:11.1f} {(max(ts) - min(ts)) / 3600:8.1f}  '
          f'{(min(ts) - first_bus) / 3600:.1f} h -> {(max(ts) - first_bus) / 3600:.1f} h')
print(f'{"others":7} {sum(v for k, v in attr.items() if not any(k in r.split(",") for r in REGIONS.values())):12.1f}')
