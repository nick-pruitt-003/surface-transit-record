"""Joint audit: for each known route, every hub-to-hub segment against the fastest the timetable allows. Leaf script.

Walks the route's legs, notes each joint_table hub it passes (any stop within 1 km), and for consecutive hubs
A -> B asks the router the earliest arrival at B leaving A when the route left A. The excess is what that segment
spends collecting states or waiting for a later connection. Each route is rebuilt from its order on this router
and gated on its known total before anything prints.
"""
import math, pickle
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
from pick import gate
from joint_table import HUBS

R = cached_router(date(2026, 9, 24), 20)
inv = {v: k for k, v in ABBR.items()}
xy = np.asarray(R.stop_xy, dtype=float)


def near(i, km=1.0):
    x, y = R.stop_xy[i]
    for n, lon, lat in HUBS:
        if math.hypot((x - lon) * 111.3 * math.cos(math.radians(lat)), (y - lat) * 111.3) <= km: return n
    return None


def arrive(stops, t, hub):
    n, lon, lat = next(h for h in HUBS if h[0] == hub)
    s = np.asarray(stops, dtype=np.int64)
    _, tm, _ = R._scan_fast(s, np.full(len(s), float(t)), np.full(len(s), -1, dtype=np.int32), f'@~{lon},{lat},1.0')
    return float(tm.min()) if len(tm) else float('inf')


def audit(name, start, t, order, want, from_clock):
    f, legs = min((R.route(s0, t, order) for s0 in start), key=lambda r: r[0] if r[0] is not None else float('inf'))
    first = next(l[3] for l in legs if l[0] == 'ride')
    t_ref = t if from_clock else first   # each known total is quoted from its own reference: the start clock or the first bus
    gate(f'{name} total', lambda: (f - t_ref) / 3600, want, 0.02)
    visits = []   # (hub, arrive time, depart time, stop)
    for l in legs:
        if l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            for s, tt, kind in ((bs, bt, 'dep'), (al, at, 'arr')):
                h = near(s)
                if not h: continue
                if visits and visits[-1][0] == h:
                    if kind == 'dep': visits[-1][2] = tt; visits[-1][3] = s
                    else: visits[-1][1] = min(visits[-1][1], tt)
                else: visits.append([h, tt, tt, s])
    print(f'\n== {name}: {(f - first) / 3600:.2f} h, {len(visits)} hub visits')
    print(f'{"from":18s} {"to":18s} {"route h":>8s} {"fastest h":>9s} {"excess":>7s}  wait at next hub')
    tot = 0.0
    for (a, _, da, sa), (b, ab, db, _) in zip(visits, visits[1:]):
        best = arrive([sa], da, b)
        ex = (ab - best) / 3600 if best < float('inf') else float('nan')
        tot += max(ex, 0) if ex == ex else 0
        print(f'{a:18s} {b:18s} {(ab - da) / 3600:8.1f} {(best - da) / 3600:9.1f} {ex:7.1f}  {(db - ab) / 3600:5.1f}')
    print(f'total excess over hub-to-hub fastest: {tot:.1f} h')


ny, dn = ZoneInfo('America/New_York'), ZoneInfo('America/Denver')
ctl = [R.state_names.index(inv[x]) for x in 'WV KY OH MI IN IL TN MS AR MO IA NE SD ND MN WI WY MT ID WA OR UT AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH VT'.split()]
hun = [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']
audit('control (Huntington -> Hanover)', hun, datetime(2026, 9, 24, 0, 54, tzinfo=ny).timestamp(), ctl, 237.34, True)
# the record re-search's order (out/res_record2.pkl), by name so a fresh checkout without out/ can run this
rec = [R.state_names.index(n) for n in ['Maine', 'Florida', 'Louisiana', 'Missouri', 'Kansas', 'Texas', 'California', 'Idaho',
                                        'Oregon', 'Wyoming', 'Colorado', 'South Dakota', 'North Dakota', 'Michigan', 'West Virginia']]
wrj = [i for i, n in enumerate(R.stop_name) if n == 'White River Junction Bus Station']
audit('record (White River Junction -> Huntington)', wrj, datetime(2026, 9, 24, 4, 20, tzinfo=ny).timestamp(), rec, 239.08, True)
xo = ['Wyoming', 'Montana', 'Arizona', '@Albuquerque Bus Station', 'Louisiana', 'Florida', 'Maine', 'Vermont',
      'West Virginia', 'Kentucky', 'Michigan', 'North Dakota', 'Nebraska', 'Arkansas', 'Mississippi']
she = [i for i, n in enumerate(R.stop_name) if n == 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)']
audit('X (Sheridan -> Southaven)', she, datetime(2026, 9, 26, 12, 0, tzinfo=dn).timestamp(),
      [n if n.startswith('@') else R.state_names.index(n) for n in xo], 239.50, False)
