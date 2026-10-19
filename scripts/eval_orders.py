"""Evaluate many pinned orders against one router load (no search). Leaf script: nothing imports it.

  py eval_orders.py ORDERS.txt [--legs]

Each non-blank line of ORDERS.txt: name|start stop|clock (YYYY-MM-DDTHH:MM)|tz|first router date|days|order
The order is state abbreviations and @stop pins, as --seed-states takes them. Lines sharing a router window reuse it.
Prints hours from the first bus, finish, missing states, and the rides (agency: from -> to) unless --legs is off.
"""
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from time_router import cached_router
import time_search as ts
from time_search import Search
from common import ABBR

inv = {v: k for k, v in ABBR.items()}
routers = {}
for line in open(sys.argv[1], encoding='utf-8'):
    line = line.strip()
    if not line or line.startswith('#'): continue
    name, start, clock, tz, d0, days, order = line.split('|')
    key = (d0, int(days))
    if key not in routers: routers[key] = cached_router(date.fromisoformat(d0), int(days), verbose=False)
    R = routers[key]
    o = [x if x.startswith('@') else R.state_names.index(inv[x]) for x in order.split(',')]
    st = R.stops_matching(start)
    ex = [i for i in st if R.stop_name[i].lower() == start.lower()]
    st = (ex or st)[0]
    t0 = datetime.fromisoformat(clock).replace(tzinfo=ZoneInfo(tz)).timestamp()
    S = Search(R, st, t0, [], 1)
    ts.bind(R, st, t0, S)
    f, legs = S.evaluate(o)
    if f >= 1e18 or not legs:
        print(f'== {name}: no finish', flush=True); continue
    miss = [ABBR[R.state_names[s]] for s in S.missing(legs)]
    first = next(l for l in legs if l[0] == 'ride')
    print(f'== {name}: {(f - first[3]) / 3600:.2f} h, first bus {R.fmt_time(first[3], first[2])} at {R.stop_name[first[2]]}, '
          f'finish {R.fmt_time(f, st)} at {R.stop_name[legs[-1][4] if legs[-1][0] == "ride" else legs[-1][2]]}, '
          f'missing {" ".join(miss) or "none"}', flush=True)
    if '--legs' in sys.argv:
        for l in legs:
            if l[0] == 'ride':
                ag = R.trip_info[(l[1][0], l[1][1])][0]
                print(f'   {R.fmt_time(l[3], l[2]):14} {ag[:24]:24} {R.stop_name[l[2]][:30]:30} -> {R.stop_name[l[4]][:30]:30} {R.fmt_time(l[5], l[4])}')
        print(flush=True)
