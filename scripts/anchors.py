"""Anchors: the rides in the known fast routes that cannot be replaced by waiting a little. Leaf script.

HANDOFF 22: every route under the record is a chain of once-daily services with flexible connections
between them, and a saving anywhere else is absorbed by the wait for the next one. So a new shape means a
different chain of anchors. This is step 1 of the anchor-chain method: find the anchors, exactly.

For every ride of every known fast route, the miss cost is asked of the timetable, not estimated: leave the
boarding station one minute after the ride did, and take the earliest arrival at the alighting station by any
combination of services. Miss cost = that arrival minus the ride's own arrival. A ride with a small miss cost
is a connection; a large one is an anchor. The states each ride passes through are read off its connections.

The flag threshold only decides which rows are marked, never which are printed: every ride is listed.

Gated before anything prints: the Southwest Chief (Barstow -> Newton) runs once a day, so missing it must
cost at least 20 h. A version that reports it as cheap to miss is measuring the wrong thing.

    python3 anchors.py            ->  ../out/anchors.txt, ../out/anchors.pkl
"""
import pickle, math
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
from pick import gate
from time_search import Search

FLAG_H = 6.0   # marks a row as an anchor in the report; permissive, and it prunes nothing

R = cached_router(date(2026, 9, 24), 20)
inv = {v: k for k, v in ABBR.items()}
xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float)
CT = ZoneInfo('America/Chicago')


def near(i, r_km):
    lon, lat = R.stop_xy[i]
    d = np.hypot((xy[:, 0] - lon) * 111.3 * math.cos(math.radians(lat)), (xy[:, 1] - lat) * 111.3)
    return np.nonzero(d <= r_km)[0].astype(np.int64)


def earliest(board, t, alight):
    s = near(board, 0.3)
    lon, lat = R.stop_xy[alight]
    _, tm, _ = R._scan_fast(s, np.full(len(s), float(t)), np.full(len(s), -1, dtype=np.int32), f'@~{lon},{lat},1.0')
    return float(tm.min()) if len(tm) else float('inf')


def routes():
    """Each route rebuilt from its state order on this router and gated on its known total. The saved result
    pickles are not used: their trip keys come from an older feed numbering (control's first ride is (3, 't72'),
    which this router does not have), so their legs would name the wrong services."""
    out = {}
    ny, dn = ZoneInfo('America/New_York'), ZoneInfo('America/Denver')
    named = lambda n: [i for i, x in enumerate(R.stop_name) if x == n]

    def build(name, starts, t, order, want, from_clock, days=1):
        check = Search(R, starts[0], t, [], 1)   # 48-state coverage test
        best = None
        for d in range(days):
            for s0 in starts:
                f, legs = R.route(s0, t + d * 86400, order)
                if f is None or check.missing(legs): continue   # a day that skips a state is not a route
                ref = t + d * 86400 if from_clock else next(l[3] for l in legs if l[0] == 'ride')
                if best is None or f - ref < best[0]: best = (f - ref, legs)
        gate(f'{name} rebuilt from its order', lambda: best[0] / 3600 if best else float('inf'), want, 0.1)
        out[name] = best[1]

    ctl = [R.state_names.index(inv[x]) for x in 'WV KY OH MI IN IL TN MS AR MO IA NE SD ND MN WI WY MT ID WA OR UT '
           'AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH VT'.split()]
    build('control', named('Huntington Bus Stop'), datetime(2026, 9, 24, 0, 54, tzinfo=ny).timestamp(), ctl, 237.34, True)
    rec = pickle.load(open('../out/res_record2.pkl', 'rb'))['order']
    build('record', named('White River Junction Bus Station'), datetime(2026, 9, 24, 4, 20, tzinfo=ny).timestamp(),
          rec, 239.08, True)
    spec = 'NV @Albuquerque_Bus_Station LA @Toledo_Bus_Stop WV ND AR FL ME VT'
    xt = [('@' + x[1:].replace('_', ' ')) if x.startswith('@') else R.state_names.index(inv[x]) for x in spec.split()]
    build('X_TOL', named('Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)'),
          datetime(2026, 9, 24, 12, 0, tzinfo=dn).timestamp(), xt, 237.9, False, days=7)
    return out


RT = routes()
want = {l[1] for legs in RT.values() for l in legs if l[0] == 'ride'}
by_trip = defaultdict(list)
for k, key in enumerate(R.ctrip):
    if key in want: by_trip[key].append(k)


def states_on(trip, bt, at):
    got = []
    for k in sorted(by_trip[trip], key=lambda k: R.dep[k]):
        if bt <= R.dep[k] and R.arr[k] <= at:
            for s in (int(R.cfrom[k]), int(R.cto[k])):
                y = int(R.state[s])
                if y >= 0 and ABBR[R.state_names[y]] not in got: got.append(ABBR[R.state_names[y]])
    return got


def finish_of(legs):
    return max(l[5] if l[0] == 'ride' else l[4] for l in legs)


rows = []
for name, legs in RT.items():
    fin = finish_of(legs)
    # the order the route collects states in, and at which leg each is first collected
    first_at = {}
    for i, l in enumerate(legs):
        if l[0] == 'ride':
            got = states_on(l[1], l[3], l[5]) or [ABBR[R.state_names[int(R.state[l[4]])]]]
        else:
            y = int(R.state[l[2]]); got = [ABBR[R.state_names[y]]] if y >= 0 else []
        for ab in got: first_at.setdefault(ab, i)
    seq = sorted(first_at, key=lambda ab: first_at[ab])
    for i, l in enumerate(legs):
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        alt = earliest(bs, bt + 60, al)
        # route miss: from the same stop one minute late, collect everything still owed, in the same order
        owed = [R.state_names.index(inv[ab]) for ab in seq if first_at[ab] >= i]
        try:
            f2, _l2 = R.route(bs, bt + 60, owed)
        except Exception:
            f2 = None
        ag, rt, hs = R.trip_info[(trip[0], trip[1])]
        rows.append(dict(route=name, trip=trip, board=bs, dep=bt, alight=al, arr=at, agency=ag, line=rt or hs,
                         states=states_on(trip, bt, at), miss_h=(alt - at) / 3600,
                         route_miss_h=((f2 - fin) / 3600) if f2 else float('inf')))

chief = [r for r in rows if 'Chief' in str(r['line']) + str(r['agency']) and 'Barstow' in R.stop_name[r['board']]]
gate('Southwest Chief route miss cost is a day', lambda: min(r['route_miss_h'] for r in chief) if chief else 0.0, 24.0, 4.0)

pickle.dump(rows, open('../out/anchors.pkl', 'wb'))
with open('../out/anchors.txt', 'w') as fh:
    fh.write('columns: route miss (finish delay if you are one minute late for this ride and re-route everything still owed), local miss (delay to the same alight station).\n')
    fh.write(f'local miss = next arrival at the alight station leaving 1 min after the ride, minus the ride\'s arrival. '
             f'* = at least {FLAG_H:.0f} h.\n')
    for name in RT:
        fh.write(f'\n== {name}\n')
        for r in rows:
            if r['route'] != name: continue
            f = '*' if r['route_miss_h'] >= FLAG_H else ' '
            dt = datetime.fromtimestamp(r['dep'], CT); at = datetime.fromtimestamp(r['arr'], CT)
            fh.write(f"{f} {r['route_miss_h']:6.1f} {r['miss_h']:6.1f}  {dt:%a %H:%M} {R.stop_name[r['board']][:28]:28s} -> {at:%a %H:%M} "
                     f"{R.stop_name[r['alight']][:28]:28s} {(r['arr'] - r['dep']) / 3600:5.1f} h  "
                     f"{' '.join(r['states']):24s} {str(r['agency'])[:14]} {str(r['line'])[:30]}\n")
    # the union: one line per distinct anchor service, across routes
    fh.write('\n== distinct anchors across all three routes\n')
    seen = {}
    for r in rows:
        if r['route_miss_h'] < FLAG_H: continue
        key = (str(r['agency']), str(r['line']), R.stop_name[r['board']], R.stop_name[r['alight']])
        seen.setdefault(key, []).append(r)
    for (ag, ln, b, a), rs in sorted(seen.items(), key=lambda kv: -max(x['route_miss_h'] for x in kv[1])):
        r = rs[0]; dt = datetime.fromtimestamp(r['dep'], CT)
        fh.write(f"{max(x['route_miss_h'] for x in rs):6.1f} h  {dt:%a %H:%M} CT  {b[:28]:28s} -> {a[:28]:28s} "
                 f"{' '.join(r['states']):24s} {ag[:14]} {ln[:30]}  [{', '.join(sorted({x['route'] for x in rs}))}]\n")
print(open('../out/anchors.txt').read())
