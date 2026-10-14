"""Miss-a-leg redundancy for every saved route: for each ride, miss it by one minute and replay.

  py redundancy.py              # writes ../docs/redundancy.xlsx (one sheet per route) and ../out/redundancy.txt

For each ride the replay starts at the boarding stop one minute after the bus left, with the states collected so far
done, and evaluates the rest of the route two ways: the remaining stops as pins (freest), and the pins with each leg's
states (cannot skip a state the original collected on the way). Cost = best finish minus the planned finish.
cost > 0: that bus is a single point of failure for that many hours; 0: covered; < 0: the backup is faster than the
plan, i.e. a saving the route itself missed. Same method as x_itinerary.py's "If you miss a leg", generalised.
Leaf script: nothing imports it.
"""
import pickle, sys
from datetime import date, datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from time_router import cached_router
import time_search as ts
from common import ABBR

SHIFT = 42 * 86400   # pickles saved before the Nov migration are on September dates
# Windows run well past each finish so a one-day slip still lands inside them (a 20-day window made every miss
# after day 2 read "not recoverable"). Optional explicit start clock (UTC epoch) where the pickle's is stale.
ROUTES = [  # name, pickle, router (first date, days), start override
    ('X', '../out/res_x.pkl', (date(2026, 11, 4), 27), None),
    # Moorhead on the Portal Bridge bound (start Nov 9+): Mon Nov 9 13:00 CST, in time for the Fargo 14:30 Jefferson
    # settled on start days Nov 9-15. Its first bus (Fargo 14:30) is not at the start stop, so finish - elapsed is too late a
    # clock and Mon 00:00 charged 14.5 h of waiting (250.26 h). Start Mon Nov 9 13:00 CST: early enough for the walk to Fargo
    # (14:20 missed the 14:30), so the total matches the 235.8 h route.
    ('Moorhead', '../out/mh_nov/eval9.pkl', (date(2026, 11, 9), 22),
     datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc).timestamp()),
    ('Control', '../out/control_nov/eval_stl.pkl', (date(2026, 11, 4), 27), None),
    # the record itself (Nick's Oct 6 csv): KC -> Tulsa -> Dallas -> El Paso -> LA -> Las Vegas, pinned (out/wide/rec_true.log)
    ('Record', '../out/wide/rec_true.pkl', (date(2026, 11, 19), 20), None),
    # the search's variant of it: Omnibus KC 13:01 -> Tucumcari -> Flagstaff -> Barstow -> Las Vegas, same finish
    ('Record-Omnibus', '../out/wide/rec19f.pkl', (date(2026, 11, 19), 20), None),
]


def same_trip_exists(R, leg, N):
    """Same carrier and route, same stops, same times, N days later (from x_itinerary.py)."""
    import numpy as np
    _, trip, bs, bt, al, at = leg
    key = R.trip_info[(trip[0], trip[1])][:2]
    dep = R._dep_np if hasattr(R, '_dep_np') else np.asarray(R.dep)
    R._dep_np = dep
    t = bt + N * 86400
    for k in range(int(np.searchsorted(dep, t - 60)), int(np.searchsorted(dep, t + 61))):
        if R.cfrom[k] != bs or R.trip_info[R.ctrip[k][:2]][:2] != key: continue
        tr = R.ctrip[k]
        for j in range(k, int(np.searchsorted(dep, at + N * 86400 + 1))):
            if R.ctrip[j] == tr and R.cto[j] == al and abs(R.arr[j] - (at + N * 86400)) <= 60: return True
    return False


def run(name, path, win, t_over, wb, out):
    R = cached_router(*win)
    d = pickle.load(open(path, 'rb'))
    t0 = d['t0']
    # a settled search stores its --at clock as t0; the real start is finish - elapsed. Back off 10 min (CLAUDE.md:
    # a clock on the bus's own minute cannot catch it).
    if 'finish' in d and d['finish'] - d['elapsed'] - t0 > 3600:
        t0 = d['finish'] - d['elapsed'] - 600
    win0 = datetime(win[0].year, win[0].month, win[0].day, tzinfo=timezone.utc).timestamp()
    if t0 < win0: t0 += SHIFT
    if t_over: t0 = t_over
    st = R.stops_matching(d['start'])[0]
    S = ts.Search(R, st, t0, [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st, t0, S, None, None
    f, legs = S.evaluate(d['order'])
    if f >= 1e18 or not S.all_states(legs):
        print(f'{name}: does not evaluate on this window', file=out); return
    fb = next(x for x in legs if x[0] == 'ride')   # the record clock runs from the first bus, not the search clock
    base_h = (f - fb[3]) / 3600
    print(f'\n== {name}: {base_h:.2f} h from first bus {R.fmt_time(fb[3], fb[2])} at {R.stop_name[fb[2]]} '
          f'(clock {R.fmt_time(t0, st)} at {R.stop_name[st]})', file=out)
    ws = wb.create_sheet(name)
    ws.append([f'{name}: {base_h:.2f} h from the first bus. Miss each ride by one minute and replay the rest.'])
    ws['A1'].font = Font(bold=True)
    ws.append(['#', 'missed', 'from', 'to', 'cost h', 'recovery starts with'])
    for c in ws[2]: c.font = Font(bold=True)
    k = 0
    for i, l in enumerate(legs):
        if l[0] != 'ride': continue
        k += 1
        _, trip, bs, bt, al, at = l
        got = S.covered([x for x in legs[:i] if x[0] == 'ride']) | {int(R.state[st])}
        for x in legs[:i]:
            if x[0] == 'walk' and R.walk_collects(x[2]): got.add(int(R.state[x[2]]))
        pins, rem, full, seen = [], [], [], set(got)
        for x in legs[i:]:
            nw = (S.covered([x]) if x[0] == 'ride' else ({int(R.state[x[2]])} if R.walk_collects(x[2]) else set())) - seen
            seen |= nw
            rem += sorted(nw, key=lambda z: R.state_names[z])
            full += sorted(nw, key=lambda z: R.state_names[z])
            pin = f'@#{x[4] if x[0] == "ride" else x[2]}'
            if not pins or pins[-1] != pin: pins.append(pin)
            if not rem or rem[-1] != pin: rem.append(pin)
        best = None
        # own = the route's own pruned order minus what is done, the router choosing the path (validated: X missing
        # the Pasco Greyhound -> Northwestern -> Boise -> SLE -> Saint George, 0.0 h). Pinning every remaining stop
        # (pins/rem) forces local hops the backup bypasses and cascades; kept only as fallbacks.
        visited = {R.stop_name[y] for x in legs[:i] for y in ((x[2], x[4]) if x[0] == 'ride' else (x[1], x[2]))}
        # drop owed-done states and @pins the route already passed (X's @Hanover sent the replay back to Hanover)
        own = [x for x in d['order'] if (isinstance(x, str) and x[1:] not in visited) or (not isinstance(x, str) and x not in got)]
        # full = every owed state in the order the route collects it, no stop pins: reroutes freely (a Sunday without the
        # Las Vegas Thruway takes the 14:00 Greyhound) while still aiming at states the pruned order leaves implicit
        for tgt in (own, pins, rem, full):
            S2 = ts.Search(R, bs, bt + 60, [], 1, done=sorted(got)); ts._SELF, ts._START, ts._T0 = S2, bs, bt + 60
            f2, l2 = S2.evaluate(tgt)
            if f2 < 1e18 and S2.all_states(l2) and (best is None or f2 < best[0]): best = (f2, l2)
        ts._SELF, ts._START, ts._T0 = S, st, t0
        waited = 0
        for N in (1, 2, 3):   # wait: catch the same bus N days later, the router free to substitute after that
            if best is not None and best[0] <= f + N * 86400: break
            tN = bt + N * 86400 - 600
            hit = False
            for tgt in (own, pins, rem, full):   # next-day replay may follow the original path (pins) or re-route (own)
                S3 = ts.Search(R, bs, tN, [], 1, done=sorted(got)); ts._SELF, ts._START, ts._T0 = S3, bs, tN
                f3, l3 = S3.evaluate(tgt)
                if f3 < 1e18 and S3.all_states(l3) and (best is None or f3 < best[0]): best, waited, hit = (f3, l3), N, True
            if not hit and all(same_trip_exists(R, x, N) for x in legs[i:] if x[0] == 'ride'):
                if best is None or f + N * 86400 < best[0]: best, waited = (f + N * 86400, []), N
        ts._SELF, ts._START, ts._T0 = S, st, t0
        ag = R.trip_info[(trip[0], trip[1])][0]
        if best is None:
            cost, how = None, 'not recoverable in the window'
        else:
            cost = round((best[0] - f) / 3600, 1)
            first = next((x for x in best[1] if x[0] == 'ride'), None)
            if waited:
                how = f'wait {waited} day(s) and catch the same bus, then continue'
            elif first:
                how = (f'{R.fmt_time(first[3], first[2])} {R.trip_info[(first[1][0], first[1][1])][0]}: '
                       f'{R.stop_name[first[2]]} -> {R.stop_name[first[4]]}')
            else:
                how = ''
        ws.append([k, f'{R.fmt_time(bt, bs)} {ag}', R.stop_name[bs], R.stop_name[al], cost, how])
        c = ws.cell(ws.max_row, 5)
        fill = 'F8D7DA' if cost is None or cost >= 20 else 'FFF3CD' if cost >= 3 else 'CCE5FF' if cost < -0.05 else 'D4EDDA'
        c.fill = PatternFill('solid', fgColor=fill)
        print(f'{k:3} {R.fmt_time(bt, bs):14} {ag[:22]:22} {R.stop_name[bs][:28]:28} -> {R.stop_name[al][:28]:28} '
              f'{"LOST" if cost is None else f"{cost:+.1f} h"}  {how[:90]}', file=out)
        out.flush()
    for col, w in zip('ABCDEF', (4, 36, 30, 30, 8, 100)): ws.column_dimensions[col].width = w


def main():
    wb = Workbook(); wb.remove(wb.active)
    sfx = ('_' + '_'.join(sys.argv[1:])) if len(sys.argv) > 1 else ''
    with open(f'../out/redundancy{sfx}.txt', 'w', encoding='utf-8') as out:
        for name, path, win, t_over in ROUTES:
            if len(sys.argv) > 1 and name not in sys.argv[1:]: continue
            run(name, path, win, t_over, wb, out)
    if wb.sheetnames: wb.save(f'../docs/redundancy{sfx}.xlsx')


if __name__ == '__main__':
    main()
