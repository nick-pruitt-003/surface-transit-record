"""Route X and its inverse, measured forwards in real hours.

X runs Sheridan WY -> the Mississippi line at Southaven in 238.08 h by hand, against a 238.83 h timetabled
record and a 237.34 h control. Until 78ada1b the forward scan could not reach its ending at all: a 57 min
proxy link labelled Holmes five minutes before the MATA bus arrived, and a walk-derived label does not
license an onward walk, so the 1142 s step over the state line was never relaxed.

    --dir out       Sheridan WY -> MS line          (X as built)
    --dir back      MS line -> Sheridan WY          (the inverse)

The inverse cannot literally start at Southaven: no Southaven stop exists in the feed, and the Mississippi
side of that border is a virtual walk-in point with no departures. So it starts at HOLMES at ELVIS PRESLEY,
walks over the line to collect MS first, and rides away. That is X's ending run in reverse.

The state order is geographic, NOT the spreadsheet's alphabetical grouping. The sheet lists "AL FL LA" for
the Houston to Tallahassee bus, which physically runs TX -> LA -> AL -> FL; feeding alphabetical order to a
layered scan is what made shape_probe declare the real 237 route impossible at step 12. The order below
reproduces the sheet's own cumulative state counts at every leg (2, 4, 6, 8, 9, 10, 12, 13, 14, 17, 21, 29
... 48), which is the check that it has not been mangled. The inverse is that list reversed, which stays
geographically coherent because the corridors run both ways (CORRIDORS.md: the PNW corridor wins in either
direction).
"""
import argparse, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
import time_search as ts
from time_search import Search

ORDER = ('WY MT ID WA OR UT AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH '
         'VT WV OH IN KY MI IL WI MN ND SD IA NE MO AR TN MS').split()


def ev(R, stop, t0, order):
    S = Search(R, stop, t0, [], 1)
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, stop, t0, S, None, None
    return S.evaluate(order)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='out', choices=('out', 'back'))
    ap.add_argument('--at', default=None, help='first departure; default depends on --dir')
    ap.add_argument('--tz', default=None)
    ap.add_argument('--hours', type=float, default=0, help='sweep this many hours of departures')
    ap.add_argument('--step', type=float, default=2)
    ap.add_argument('--days', type=int, default=20)
    a = ap.parse_args()

    R = cached_router(datetime.fromisoformat('2026-09-24T00:54').date(), a.days)
    inv = {v: k for k, v in ABBR.items()}
    ct = ZoneInfo('America/Chicago')

    d = pickle.load(open('../out/res_starttest.pkl', 'rb'))
    fin, _ = ev(R, R.stop_name.index(d['start']), d['t0'], d['order'])
    gate = (fin - d['t0']) / 3600
    print(f'GATE control: {gate:.2f} h (expect 237.34)', flush=True)
    if abs(gate - 237.34) > 0.01:
        print('GATE FAILED, stopping'); return

    if a.dir == 'out':
        names, at, tz = ['Sheridan'], a.at or '2026-09-26T22:20', a.tz or 'America/Denver'
        order = [R.state_names.index(inv[x]) for x in ORDER]
    else:
        names, at, tz = ['HOLMES at ELVIS PRESLEY'], a.at or '2026-09-24T06:00', a.tz or 'America/Chicago'
        order = [R.state_names.index(inv[x]) for x in reversed(ORDER)]
    lab = [ABBR[R.state_names[y]] for y in order]
    print(f'--dir {a.dir}: {len(order)} states, {" ".join(lab)}\n', flush=True)

    t_base = datetime.fromisoformat(at).replace(tzinfo=ZoneInfo(tz)).timestamp()
    times = [t_base + h * 3600 for h in np.arange(0, max(a.hours, a.step), a.step)] if a.hours else [t_base]
    # every matching stop, not the first: taking [0] off a name lookup is how an earlier run started from
    # Charleston and reported the control at 285 h
    cands = [i for n in names for i, s in enumerate(R.stop_name) if n.lower() in s.lower()]
    cands = sorted(set(cands))
    print(f'{len(cands)} start stops x {len(times)} departures', flush=True)
    best = None
    for s in cands:
        for t0 in times:
            try:
                f, legs = ev(R, s, t0, order)
            except Exception as e:
                print(f'   {R.stop_name[s][:40]:40s} error: {e}', flush=True); continue
            if f is None or not np.isfinite(f): continue
            el = (f - t0) / 3600
            if best is None or el < best[0]:
                best = (el, s, t0, f, legs)
                print(f'   {R.stop_name[s][:40]:40s} dep {datetime.fromtimestamp(t0, ct):%a %H:%M} '
                      f'-> {el:7.2f} h', flush=True)
    if best is None:
        print('\nno start completes the order'); return
    el, s, t0, f, legs = best
    print(f'\nBEST {el:.2f} h  from {R.stop_name[s]}')
    print(f'   depart {datetime.fromtimestamp(t0, ct):%a %d %b %H:%M}  '
          f'arrive {datetime.fromtimestamp(f, ct):%a %d %b %H:%M} (Central)')
    for nm, v in (('238.08 X by hand', 238.08), ('238.83 record', 238.83), ('237.34 control', 237.34)):
        print(f'   vs {nm:18s} {"BEATS" if el < v else "misses":6s} ({el - v:+.2f} h)')
    print('\nfirst 4 and last 4 legs:')
    for l in legs[:4] + [('...',)] + legs[-4:]:
        if l[0] == 'ride':
            print(f'   ride {datetime.fromtimestamp(l[3], ct):%a %H:%M} {R.stop_name[l[2]][:34]:34s} -> '
                  f'{datetime.fromtimestamp(l[5], ct):%a %H:%M} {R.stop_name[l[4]][:34]}')
        elif l[0] == 'walk':
            print(f'   walk {datetime.fromtimestamp(l[3], ct):%a %H:%M} {R.stop_name[l[1]][:34]:34s} -> '
                  f'{datetime.fromtimestamp(l[4], ct):%a %H:%M} {R.stop_name[l[2]][:34]}')
        else:
            print('   ...')


if __name__ == '__main__':
    main()
