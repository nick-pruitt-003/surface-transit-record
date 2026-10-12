"""Hinge table (Nick, Oct 6): the good routes hang off a few once-daily rides. For each hinge of a route, keep the
route from the hinge on (its tail, re-timed on today's data) and write a front-search job: be at the hinge's boarding
stop by its departure minus the transfer time, holding every state the tail does not collect, from the best start
anywhere in a given state. time_search does the front with --end/--end-by (latest start) and --done (the tail's states).
Total = front + tail.

Leaf script: nothing imports it.   python3 hinge_fronts.py > ../out/hinges/jobs.txt   (from scripts/)
Each line: name|end stop|end-by ISO|tz|done states|tail hours|front seed (states, first = start state)
"""
import sys
from datetime import datetime
import time_search as ts
import time_router as tr
from route_report import R
from common import ABBR

ROUTE = ('X', 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)', datetime(2026, 11, 5, 22, 10).isoformat(), 'America/Denver',
         'OR,AZ,OK,FL,@Hanover (Hanover Inn),ME,WV,MS,MO,WI,MI,ND,MN')
HINGES = ['Southwest Chief', 'Silver Meteor', 'Union Pacific North', 'JL Chicago 21:15']   # substrings of the service
STARTS = ['NH', 'WV', 'WY', 'NV', 'WA', 'ME']   # start states to try for each front (skipped when the tail holds them)


def main():
    name, start_name, at, tzname, order_s = ROUTE
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tzname)
    st = R.stops_matching(start_name)[0]; t0 = datetime.fromisoformat(at).replace(tzinfo=tz).timestamp()
    order = [x if x.startswith('@') else R.state_names.index(next(n for n in R.state_names if ABBR[n] == x)) for x in order_s.split(',')]
    S = ts.Search(R, st, t0, [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st, t0, S, None, None
    f, legs = S.evaluate(order)
    assert f < 1e18 and S.all_states(legs), 'route does not evaluate on today\'s data'
    rides = [(i, l) for i, l in enumerate(legs) if l[0] == 'ride']
    first = rides[0][1][3]
    print(f'# {name}: {(f - first) / 3600:.2f} h on today\'s data', file=sys.stderr)
    # the order states are first collected along the route, for seeding fronts
    seq, got = [], {int(R.state[st])}
    seq.append(int(R.state[st]))
    for l in legs:
        new = (S.covered([l]) if l[0] == 'ride' else ({int(R.state[l[2]])} if R.walk_collects(l[2]) else set())) - got
        seq += sorted(new); got |= new
    for h in HINGES:
        hit = [(i, l) for i, l in rides if h in (R.trip_info[l[1][:2]][1] or R.trip_info[l[1][:2]][2] or '') or h in R.trip_info[l[1][:2]][0]]
        if not hit: print(f'# {h}: not in the route', file=sys.stderr); continue
        i, l = hit[0]
        tail = legs[i:]; tstates = set()
        for x in tail:
            tstates |= (S.covered([x]) if x[0] == 'ride' else ({int(R.state[x[2]])} if R.walk_collects(x[2]) else set()))
        board, dep = l[2], l[3]
        zone = R.stop_zone(board); deadline = datetime.fromtimestamp(dep - tr.MIN_TRANSFER, zone)
        done = sorted(ABBR[R.state_names[s]] for s in tstates)
        front = [ABBR[R.state_names[s]] for s in seq if s not in tstates]
        for s0 in STARTS:
            if s0 in done: continue
            seed = [s0] + [x for x in front if x != s0]
            print('|'.join([f'{name}_{h.split()[-1].lower()}_{s0}', R.stop_name[board], deadline.strftime('%Y-%m-%dT%H:%M'), str(zone),
                            ','.join(done), f'{(f - dep) / 3600:.2f}', ','.join(seed)]))
        print(f'# {h}: board {R.stop_name[board]} {R.fmt_time(dep, board)}, tail {(f - dep) / 3600:.1f} h collects {len(done)}: '
              f'{" ".join(done)}; front owes {len(front)}', file=sys.stderr)


if __name__ == '__main__':
    main()
