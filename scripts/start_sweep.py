"""Compare start days (and the reverse direction) for one route shape using real timetables.

usage: python3 start_sweep.py --start "White River Junction Bus Station" --tz America/New_York \
         --order "Maine,Florida,..." --week 2026-09-21 [--hours 0,6,12,18]
For each weekday the clock starts at each given hour; the reported time runs from the first
departure actually boarded to the final arrival, so waiting before the first bus is not counted.
"""
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds

ap = argparse.ArgumentParser()
ap.add_argument('--start', required=True); ap.add_argument('--tz', required=True)
ap.add_argument('--order', required=True); ap.add_argument('--week', required=True)
ap.add_argument('--hours', default='0,6,12,18'); ap.add_argument('--days', type=int, default=13)
a = ap.parse_args()
feeds = load_feeds(); Z = ZoneInfo(a.tz); best = {}
for d in range(7):
    day = datetime.fromisoformat(a.week).replace(tzinfo=Z) + timedelta(days=d)
    R = TimeRouter(feeds, day.date(), a.days)
    start = R.stops_matching(a.start)[0]
    order = [x.strip() if x.strip().startswith('@') else R.state_names.index(x.strip()) for x in a.order.split(',')]
    for h in (int(x) for x in a.hours.split(',')):
        t0 = (day + timedelta(hours=h)).timestamp()
        f, legs = R.route(start, t0, order)
        if f is None: print(day.strftime('%a'), h, 'unreachable', flush=True); continue
        first = next((leg[3] for leg in legs if leg[0] == 'ride'), None)
        if first is None: print(day.strftime('%a'), h, 'no ride legs', flush=True); continue
        key = datetime.fromtimestamp(first, Z).strftime('%a %H:%M')
        hrs = round((f - first) / 3600, 1)
        if key not in best or hrs < best[key]: best[key] = hrs
        print('clock', day.strftime('%a'), f'{h:02d}:00', '| first bus', key, '|', hrs, 'h', flush=True)
print('\nBEST BY FIRST DEPARTURE')
for k, v in sorted(best.items(), key=lambda kv: kv[1]): print(f'  {v:6.1f} h  leaving {k}')
