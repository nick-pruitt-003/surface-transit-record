"""Rebuild the 237 reference pickles from the route documented in docs/HANDOFF.md section 2.

out/ is gitignored, so a fresh checkout of this repo has no out/hun_ms_meteor.pkl and no
out/res_starttest.pkl, and then nothing can be tracked or regression-checked against the 237 route.
The route is documented leg by leg, so its state order can be written down; this script turns that
order into the two pickles the rest of the tooling expects, and refuses to write anything that does
not collect all 48 states.

  python3 rebuild_237.py            # writes ../out/hun_ms_meteor.pkl and ../out/res_starttest.pkl
"""
import os, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds
import time_search as ts
from time_search import Search
from common import ABBR

ET = ZoneInfo('America/New_York')
OUT = '../out/'
START = 'Huntington Bus Stop'
# docs/HANDOFF.md section 2, in the order the route first collects each state. WV is the start;
# KY comes from the Ashland stop on the Barons bus, WY from Gillette on the Billings bus, and
# AZ/NM/CO/KS all from the Southwest Chief between Barstow and Newton.
SEQ = ('WV KY OH MI IN IL TN MS AR MO NE IA SD ND MN WI WY MT ID WA OR UT NV CA AZ NM CO KS '
       'OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH VT').split()
# hun_ms_meteor: the 12:30 AM clock regress.py checks. res_starttest: the latest-start sweep result, which came
# out of a search, so its order has been pruned: WV is not in it. The start stop is in West Virginia and the
# first bus collects the state on the way out, so a target for it is redundant, and prune drops targets a route
# already covers in passing. It is not cosmetic. With WV first, the start stop is itself in layer 0 and the
# backward pass reads the latest start straight off that layer; with WV gone the start has to reach layer 0 by
# boarding, which costs one MIN_TRANSFER. That is the whole difference between 00:59:20 and the 00:54 that
# regress.py records.
CLOCKS = (('hun_ms_meteor.pkl', datetime(2026, 9, 24, 0, 30, tzinfo=ET), False),
          ('res_starttest.pkl', datetime(2026, 9, 24, 0, 54, tzinfo=ET), True))


def main():
    assert len(SEQ) == len(set(SEQ)) == 48, len(SEQ)
    os.makedirs(OUT, exist_ok=True)
    R = TimeRouter(load_feeds(), datetime(2026, 9, 23).date(), 18)
    inv = {v: k for k, v in ABBR.items()}
    full = [R.state_names.index(inv[x]) for x in SEQ]
    start = R.stops_matching(START)[0]
    for name, when, pruned in CLOCKS:
        order = [x for x in full if x != R.state[start]] if pruned else full
        t0 = when.timestamp()
        S = Search(R, start, t0, [], 1)
        ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, start, t0, S, None, None
        f, legs = S.evaluate(order)
        if f == float('inf'):
            print(f'{name}: no finish from {when:%a %H:%M}'); continue
        miss = [ABBR[R.state_names[s]] for s in S.missing(legs)]
        el = (f - t0) / 3600
        print(f'{name}: start {when:%a %H:%M}, {el:.2f} h, finish '
              f'{datetime.fromtimestamp(f, ET):%a %Y-%m-%d %H:%M}, missing {miss or "none"}', flush=True)
        if miss: continue
        pickle.dump(dict(order=order, t0=t0, start=R.stop_name[start], elapsed=f - t0, finish=f),
                    open(OUT + name, 'wb'))
        print('  wrote', OUT + name, flush=True)


if __name__ == '__main__':
    main()
