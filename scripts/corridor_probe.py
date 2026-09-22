"""Is Spokane - Pasco - Hermiston/La Grande - Salt Lake City the only efficient way to take WA, OR and ID?
Leaf script: nothing imports it.

Nick's claim, from working the timetable by hand: that corridor, in either direction, beats every other way of
collecting the three Pacific Northwest states by at least five hours. If it holds, the corridor is a single
decision worth three states, and a search that sees it one leg at a time will rank it as three weak moves.

The test asks the router, not a rule. From each start area, at a spread of start times, route every order of
WA OR ID, plus the same orders forced through Portland or Seattle so that routes avoiding the corridor are
actually tried. Each route is classed by whether it passes the corridor (a stop within 15 km of Pasco, or of
Hermiston or La Grande). Reported per start time: the fastest corridor route and the fastest route that avoids
it, and the gap. The claim holds where the gap is at least five hours every time.

    nice -n 19 python3 corridor_probe.py
"""
import argparse, itertools
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR

AREAS = {'Spokane': (47.6588, -117.4260), 'Salt Lake City': (40.7608, -111.8910), 'Boise': (43.6150, -116.2023)}
CORRIDOR = {'Pasco': (46.2396, -119.1006), 'Hermiston': (45.8404, -119.2895), 'La Grande': (45.3246, -118.0877)}
DETOURS = {'Portland': (45.5152, -122.6784), 'Seattle': (47.6062, -122.3321)}


def near(R, lat, lon, km):
    xy = np.asarray(R.stop_xy, dtype=float)
    d = np.hypot((xy[:, 0] - lon) * 111.3 * np.cos(np.radians(lat)), (xy[:, 1] - lat) * 111.3)
    return set(np.where(d <= km)[0].tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--day', default='2026-09-28', help='the day to start on (d5 of the run-1 settings)')
    ap.add_argument('--tz', default='America/Los_Angeles')
    ap.add_argument('--step', type=float, default=2, help='hours between start times')
    ap.add_argument('--days', type=int, default=20)
    a = ap.parse_args()
    R = cached_router(datetime(2026, 9, 24).date(), a.days, verbose=False)
    inv = {v: k for k, v in ABBR.items()}
    st = {x: R.state_names.index(inv[x]) for x in ('WA', 'OR', 'ID')}
    corridor = set().union(*(near(R, la, lo, 15) for la, lo in CORRIDOR.values()))
    day0 = datetime.fromisoformat(a.day).replace(tzinfo=ZoneInfo(a.tz))

    orders = []
    for p in itertools.permutations(('WA', 'OR', 'ID')):
        orders.append((' '.join(p), [st[x] for x in p]))
        for dn, (la, lo) in DETOURS.items():      # force a non-corridor way in, before each state in turn
            for i in range(3):
                o = [st[x] for x in p]; o.insert(i, f'@~{lo},{la},10')
                orders.append((' '.join(p[:i]) + f' [{dn}] ' + ' '.join(p[i:]), o))

    print(f'{"start":15s} {"leave":>11s}  {"corridor best":>13s} {"order":24s} {"avoiding best":>13s} {"order":26s} gap')
    worst_gap = np.inf
    for area, (la, lo) in AREAS.items():
        starts = np.array(sorted(near(R, la, lo, 10)), dtype=np.int64)
        for h in np.arange(0, 24, a.step):
            t0 = (day0 + timedelta(hours=float(h))).timestamp()
            best = {True: (np.inf, ''), False: (np.inf, '')}
            for label, order in orders:
                try:
                    t_end, legs = R._route_fast(starts, t0, order)
                except Exception:
                    continue
                if t_end is None or not np.isfinite(t_end): continue
                touched = set()
                for l in legs:
                    if l[0] == 'ride': touched |= {l[2], l[4]}
                    elif l[0] == 'walk': touched |= {l[1], l[2]}
                # a ride passing through without stopping still counts as the corridor
                via = bool(touched & corridor) or rides_through(R, legs, corridor)
                hrs = (t_end - t0) / 3600
                if hrs < best[via][0]: best[via] = (hrs, label)
            gap = best[False][0] - best[True][0]
            worst_gap = min(worst_gap, gap)
            print(f'{area:15s} {datetime.fromtimestamp(t0, ZoneInfo(a.tz)):%a %H:%M}  {best[True][0]:11.1f} h '
                  f'{best[True][1][:24]:24s} {best[False][0]:11.1f} h {best[False][1][:26]:26s} {gap:+.1f} h',
                  flush=True)
    print(f'\nsmallest gap, corridor ahead of the best route avoiding it: {worst_gap:+.1f} h '
          f'({"holds" if worst_gap >= 5 else "does NOT hold"} at the five hour bar)')


_TC = {}


def rides_through(R, legs, corridor):
    """does any ride in these legs pass a corridor stop between boarding and alighting"""
    if not _TC:
        for k in range(len(R.dep)): _TC.setdefault(R.ctrip[k], []).append(k)
    for l in legs:
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        for k in _TC.get(trip, ()):
            if bt <= R.dep[k] and R.arr[k] <= at and (int(R.cfrom[k]) in corridor or int(R.cto[k]) in corridor):
                return True
    return False


if __name__ == '__main__':
    main()
