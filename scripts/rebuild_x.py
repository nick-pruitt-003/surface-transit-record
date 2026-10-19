"""Rebuild the control pickle from route X (Nick, Oct 11 2026: X replaces the 237 route as the control).

The 237 route (Huntington -> Vermont line) rode the City of New Orleans on its September timing; Amtrak moved that
train two hours later from Oct 7 2026, and on the November window the route finishes at 252 h at best. X is the best
route on the corrected data, is booked, and evaluates unchanged in November, so the search is now held to it.

  python3 rebuild_x.py            # writes ../out/res_x.pkl

out/ is gitignored, so a fresh checkout runs this before regress.py or a --track replay. Refuses to write a route
that misses a state or that is slower than the bound below, so a stale pickle cannot satisfy the gates.
"""
import os, pickle, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from time_router import cached_router
import time_search as ts
from time_search import Search
from common import ABBR

MT = ZoneInfo('America/Denver')
OUT = '../out/'
START = 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)'
# X's pruned order: the states it has to aim for (the rest come on the way), with Hanover pinned for the VT/NH side trip.
ORDER = 'OR,AZ,OK,FL,@Hanover (Hanover Inn),ME,WV,MS,MO,WI,MI,ND,MN'
# Ten minutes before the 22:20 Jefferson at Sheridan: a clock set to the bus's own minute cannot catch it (CLAUDE.md).
# Thursday Nov 12, X's booked start, not the window's first Thursday: the Portal Bridge cutover keeps Acela 2152
# (Washington 06:50 -> Boston) off the timetable until Nov 18, and a Nov 5 start reaches Washington on Nov 11.
CLOCK = datetime(2026, 11, 12, 22, 10, tzinfo=MT)
DAYS = 20   # Nov 4 -> Nov 23: X finishes Sunday Nov 22
BOUND_H = 232.2   # 232.13 h with no modelled hops (default since Oct 16 2026); 231.68 with them


def main():
    R = cached_router(datetime(2026, 11, 4).date(), DAYS)
    inv = {v: k for k, v in ABBR.items()}
    order = [x if x.startswith('@') else R.state_names.index(inv[x]) for x in ORDER.split(',')]
    start = R.stops_matching(START)[0]
    t0 = CLOCK.timestamp()
    S = Search(R, start, t0, [], 1)
    ts.bind(R, start, t0, S)
    f, legs = S.evaluate(order)
    if f == float('inf') or not legs: sys.exit(f'res_x.pkl not rebuilt: no finish from {CLOCK:%a %H:%M}')
    miss = [ABBR[R.state_names[s]] for s in S.missing(legs)]
    first = next(l[3] for l in legs if l[0] == 'ride')
    el = (f - first) / 3600
    print(f'res_x.pkl: start {CLOCK:%a %H:%M}, {el:.2f} h from the first bus, finish {R.fmt_time(f, start)}, missing {miss or "none"}')
    if miss or el > BOUND_H: sys.exit(f'res_x.pkl not rebuilt ({"misses " + " ".join(miss) if miss else f"{el:.2f} h > {BOUND_H}"}); any existing copy is stale')
    os.makedirs(OUT, exist_ok=True)
    pickle.dump(dict(order=order, t0=t0, start=R.stop_name[start], elapsed=f - first, finish=f), open(OUT + 'res_x.pkl', 'wb'))
    print('  wrote', OUT + 'res_x.pkl')


if __name__ == '__main__':
    main()
