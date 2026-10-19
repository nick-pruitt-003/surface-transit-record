"""Start at Wheeling WV instead of Huntington, and take the control's own chain from Columbus.

Nick's idea, and the arithmetic is his: the control leaves Huntington at 00:54, reaches Columbus at 04:50
and then SITS THERE until the 06:50 bus to Detroit. Two hours dead at the very start. Anything that reaches
Columbus later than 04:50 but still before 06:50 arrives at the same place in the same chain having spent
less clock, and the finish does not move.

Wheeling does exactly that, and only because of the westbound Ohio Coach entered in 81640e5. Wheeling is in
West Virginia, so WV comes from the start stop rather than from a leg; the coach leaves Wheeling at 03:00
and reaches Columbus at 06:00, fifty minutes clear of the 06:50. Kentucky drops out of the ordering because
the City of New Orleans already calls at Fulton, and Ohio because Columbus is on the way. 48 states, 46
ordered.

    dep 02:55  ->  235 h 19 min     boards the 03:00 passage, from the 21:00 New York departure
    dep 03:55  ->  234 h 19 min     boards the 04:00 passage, from the 22:00 New York departure

Both beat the 237.34 h control, the 238.32 h route X and the 238.83 h record. They are NOT equally solid
and the difference is data, not routing:

  * The 21:00 New York departure is verified: two screenshots from the operator's own site, plus Nick's
    confirmation of which unlabelled arrival is Wheeling and which is Columbus. So 235 h 19 min stands on
    verified timetable.
  * The 20:00 and 22:00 departures are printed on the ticket-office card, but their running times are
    Nick's stated assumption, each transposed by an hour from the 21:00. The ticket office was cash only.
    So 234 h 19 min, which boards the 04:00 passage, rests on that assumption. Quote the 235 until it is
    confirmed.

The finish is Sat 03 Oct 22:14 at the Vermont line from Hanover, identical to the control's, for every
start in the sweep. The whole gain is start-side. Elapsed falls exactly one hour per hour of later
departure across all 48 five-minute steps from 00:00 to 03:55 with no gaps, which is the pinned-arrival
signature: the chain is slack throughout and binds at the end, so there is nothing to win in the interior
and the only question is how late you can leave.

This is a GRAFT, not a search. The tail is the control's ordering, optimised for a Huntington start. It is
the best START TIME for that shape, not the best shape from Wheeling, and a real search from here may do
better still.

    python3 wheeling_start.py             both variants, with per-state attribution
    python3 wheeling_start.py --legs      and the full leg list for the best
"""
import argparse, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
import time_search as ts
from time_search import Search
from pick import gate

START = 'Wheeling 949 Main St (Jaguar)'
VARIANTS = (('02:55', 235.3239, 'verified: 21:00 NY departure, 03:00 Wheeling passage'),
            ('03:55', 234.3239, 'assumed: 22:00 NY departure, 04:00 passage, running times transposed'))


def ev(R, stop, t0, order):
    """Evaluate state indices in order from stop at Unix timestamp t0 using router R.

    Set time_search's global context and return (Search, (finish timestamp, legs)).
    An unreachable order has an infinite finish timestamp.
    """
    S = Search(R, stop, t0, [], 1)
    ts.bind(R, stop, t0, S)
    return S, S.evaluate(order)


def main():
    """Validate the control and Wheeling variants, report states, and optionally save the best."""
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--legs', action='store_true', help='print the full leg list for the best variant')
    ap.add_argument('--write', default=None, help='write the best variant as a --track pickle for '
                    'ride_search.py, so the graft can be replayed leg by leg the way the control is. '
                    'ride_search reads only start/t0/order and re-evaluates, so this is the route, not a '
                    'cached answer. Pair it with a matching --at or the replay measures a different clock.')
    a = ap.parse_args()

    R = cached_router(datetime.fromisoformat('2026-11-05T00:54').date(), a.days)
    et = ZoneInfo('America/New_York')
    inv = {v: k for k, v in ABBR.items()}
    d = pickle.load(open('../out/res_starttest.pkl', 'rb'))

    # Gate first: nothing below is a fact about the timetable until the control reproduces.
    s_ctrl = R.stop_name.index(d['start'])
    gate('control from Huntington 00:54',
         lambda: (ev(R, s_ctrl, d['t0'], d['order'])[1][0] - d['t0']) / 3600, 237.34, 0.01)

    ctrl = [ABBR[R.state_names[y]] for y in d['order']]
    order = [R.state_names.index(inv[x]) for x in ['OH'] + [x for x in ctrl if x not in ('KY', 'OH')]]
    whl = [i for i, n in enumerate(R.stop_name) if n == START]
    if not whl:
        raise SystemExit(f'{START} is not in the feed. data/manual/ needs the Jaguar and Ohio '
                         f'Coach rows (7fd3c55, 81640e5).')
    whl = whl[0]
    print(f'start {R.stop_name[whl]}, state {ABBR[R.state_names[R.state[whl]]]} '
          f'(WV comes from the start stop, not a leg)')
    print(f'ordering {len(order)}: {" ".join(ABBR[R.state_names[y]] for y in order)}\n')

    best = None
    for hhmm, expect, note in VARIANTS:
        h, m = (int(x) for x in hhmm.split(':'))
        t0 = datetime(2026, 11, 5, h, m, tzinfo=et).timestamp()
        S, (f, legs) = ev(R, whl, t0, order)
        el = (f - t0) / 3600
        # Independent of the elapsed figure: attribute every state to the leg that supplies it, and require
        # all 48. Counting what covered() returns in aggregate would pass on a route that never moved.
        seen, attrib = {int(R.state[whl])}, {int(R.state[whl]): 'start stop'}
        for l in legs:
            for y in S.covered([l]) - seen:
                seen.add(y)
                attrib[y] = (f'{R.stop_name[int(l[2])][:26]} -> {R.stop_name[int(l[4])][:26]}'
                             if l[0] == 'ride' else
                             f'walk {R.stop_name[int(l[1])][:26]} -> {R.stop_name[int(l[2])][:26]}')
        ok = len(seen) == len(R.state_names)
        print(f'dep {hhmm}  {el:9.4f} h = {int(el)} h {round((el - int(el)) * 60)} min   '
              f'{len(seen)}/48 states {"OK" if ok else "SHORT"}   {note}')
        print(f'          arrive {datetime.fromtimestamp(f, et):%a %d %b %H:%M} ET')
        if abs(el - expect) > 0.01:
            raise SystemExit(f'  expected {expect} h and got {el}. The data or the chain moved.')
        if not ok:
            raise SystemExit('  missing: ' + ' '.join(ABBR[R.state_names[y]] for y in
                                                      range(len(R.state_names)) if y not in seen))
        if best is None or el < best[0]:
            best = (el, legs, attrib, t0)

    el, legs, attrib, t0 = best
    if a.write:
        import os
        # Written the way ride_search --track reads it: start name, clock, ordering. Nothing cached.
        rec = {'start': START, 't0': t0, 'order': order,
               'elapsed': el * 3600, 'finish': t0 + el * 3600}
        tmp = a.write + f'.{os.getpid()}.tmp'
        with open(tmp, 'wb') as fh: pickle.dump(rec, fh)
        os.replace(tmp, a.write)
        print(f'\nwrote {a.write} for --track '
              f'(match it with --at {datetime.fromtimestamp(t0, et):%Y-%m-%dT%H:%M} --tz America/New_York)')
    print(f'\nper-state attribution for the {el:.2f} h variant, in collection order:')
    for y, how in attrib.items():
        print(f'  {ABBR[R.state_names[y]]}  {how}')
    if a.legs:
        print(f'\nall {len(legs)} legs:')
        for l in legs:
            if l[0] == 'ride':
                print(f'  ride {datetime.fromtimestamp(l[3], et):%a %H:%M} {R.stop_name[int(l[2])][:36]:36s}'
                      f' -> {datetime.fromtimestamp(l[5], et):%a %H:%M} {R.stop_name[int(l[4])][:36]}')
            else:
                print(f'  walk {datetime.fromtimestamp(l[3], et):%a %H:%M} {R.stop_name[int(l[1])][:36]:36s}'
                      f' -> {datetime.fromtimestamp(l[4], et):%a %H:%M} {R.stop_name[int(l[2])][:36]}')


if __name__ == '__main__':
    main()
