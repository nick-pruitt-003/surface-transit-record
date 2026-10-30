"""Regression checks: facts we already verified, re-checked on the current code and data (~2 min, one router).

  python3 regress.py            # prints PASS/FAIL per check, exits 1 on any failure

Run it before committing router, search or data changes. Add a check whenever a bug is fixed or a fact verified.
"""
import pickle, sys, time, traceback
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import time_router as tr
from time_router import TimeRouter, load_feeds, cached_router, N_STATES
import time_search as ts
from time_search import Search
import backward as B

OUT = '../out/'
ET, CT = ZoneInfo('America/New_York'), ZoneInfo('America/Chicago')
results = []


def check(name):
    def deco(fn):
        t = time.time()
        try: fn(); results.append((name, True, f'{time.time() - t:.0f}s'))
        except Exception as e: results.append((name, False, f'{type(e).__name__}: {e}')); traceback.print_exc()
        return fn
    return deco


def search_for(R, start, t0):
    S = Search(R, start, t0, [], 1)
    ts.bind(R, start, t0, S)
    return S


print('settings: MIN_TRANSFER', tr.MIN_TRANSFER // 60, 'min, WALKIN_KM', tr.WALKIN_KM, ', SCAN_SLACK', tr.SCAN_SLACK / 3600, 'h')
R = cached_router(datetime(2026, 11, 4).date(), 20)   # Nov 4-23: the X control finishes Sunday Nov 22
t237 = datetime(2026, 11, 5, 0, 30, tzinfo=ET).timestamp()
hun = R.stops_matching('Huntington Bus Stop')[0]


@check('defaults match the search settings (5 min transfers, 1.4 km walk-ins, 24 h slack)')
def _():
    assert (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK) == (300, 1.4, 86400), (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK)


@check('Amtrak times are agency (Eastern) time: CONO Effingham 12:01 AM, Memphis 6:42 AM Central (the Oct 7 2026 timetable)')
def _():
    efg = R.stops_matching('Effingham Amtrak Station')[0]; mem = R.idx['amtrak:MEM']
    day = datetime(2026, 11, 5, tzinfo=CT).timestamp()
    ks = [k for k in range(len(R.dep)) if R.cfrom[k] == efg and day < R.dep[k] < day + 86400
          and R.trip_info[(R.ctrip[k][0], R.ctrip[k][1])][1] == 'City of New Orleans']
    deps = {datetime.fromtimestamp(R.dep[k], CT).strftime('%H:%M') for k in ks}
    # Amtrak moved the City of New Orleans two hours later from Oct 7 2026 (Effingham 25:01 Eastern in the feed)
    assert '00:01' in deps, deps
    k = ks[[datetime.fromtimestamp(R.dep[j], CT).strftime('%H:%M') for j in ks].index('00:01')]
    key = R.ctrip[k]; arr = [R.arr[j] for j in range(k, min(k + 400000, len(R.dep))) if R.ctrip[j] == key and R.cto[j] == mem]
    assert arr and datetime.fromtimestamp(arr[0], CT).strftime('%H:%M') == '06:42', arr


@check('control route X (res_x.pkl) is valid: all 48 states, <= 232.2 h (no modelled hops) from the first bus, Sheridan Thu Nov 12 22:10')
def _():
    # X replaced the 237 route as the control on Oct 11 2026: Amtrak moved the City of New Orleans two hours later from
    # Oct 7, and the 237 route finishes at 252 h at best in November. Built by rebuild_x.py.
    d = pickle.load(open(OUT + 'res_x.pkl', 'rb')); st = R.stop_name.index(d['start'])
    S = search_for(R, st, d['t0'])
    f, legs = S.evaluate(d['order'])
    assert S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]
    first = next(l[3] for l in legs if l[0] == 'ride')
    assert (f - first) / 3600 <= 232.2, (f - first) / 3600


@check('router and coverage agree: every state target is collected by a ride or border walk-in (Sunland seed)')
def _():
    st = R.stops_matching('McNutt & Calle Morocco')[0]; t0 = datetime(2026, 11, 4, tzinfo=ZoneInfo('America/Denver')).timestamp()
    S = search_for(R, st, t0)
    inv = {v: k for k, v in ts.ABBR.items()}
    order = [R.state_names.index(inv[x]) for x in 'TX,LA,MS,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,WV,KY,TN,AR,MO,IL,IN,MI,WI,MN,IA,NE,KS,OK,CO,WY,SD,ND,MT,ID,WA,OR,UT,AZ,NV,CA'.split(',')]
    f, legs = S.evaluate(order)
    assert f < float('inf') and S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]


@check('backward report on the X control: every layer feasible, slack >= 0, latest start = 10:15 PM Thu at Sheridan, and forward agrees')
def _():
    # The clock is the pickle's 22:10, ten minutes before the 22:20 Jefferson. A stale clock once read as a backward bug
    # here (the 237 route's Barons bus moved to 00:45 under a 00:54 clock): the check asserts the two passes agree.
    d = pickle.load(open(OUT + 'res_x.pkl', 'rb')); order = d['order']; t0 = d['t0']
    start = R.stop_name.index(d['start'])
    fw, bad = B.forward(R, start, t0, order); assert bad is None, bad
    rev = [[] for _ in range(R.N)]
    for i in range(R.N):
        for j, w in R.foot.get(i, ()): rev[j].append((i, w))
    D = min(fw[-1].values()); lat = {s: D for s in fw[-1]}; stays = {}
    for k in range(len(order) - 2, -2, -1):
        want = [start] if k < 0 else fw[k]
        latest, stay = B.backward_layer(R, rev, lat, not isinstance(order[k + 1], str), t0 if k < 0 else min(fw[k].values()), stays, want)
        if k < 0: ls = max([latest[start]] + [t - tr.MIN_TRANSFER for t in stay.get(start, {}).values()]); break
        lat = {s: max([latest[s]] + list(stay.get(s, {}).values())) for s in fw[k]}
        lat = {s: v for s, v in lat.items() if v > float('-inf')}; stays = stay
        assert lat, f'layer {k} ({order[k]}) empty'
        assert max(v - fw[k][s] for s, v in lat.items()) >= -60, f'layer {k} negative slack'
    assert datetime.fromtimestamp(ls, ZoneInfo('America/Denver')).strftime('%a %H:%M') == 'Thu 22:15', datetime.fromtimestamp(ls, ZoneInfo('America/Denver'))
    # the latest start is exact: forward from it makes the same finish, and one minute later does not
    g, _ = B.forward(R, start, ls, order); assert min(g[-1].values()) == D, 'forward from the latest start misses the finish'
    g, _ = B.forward(R, start, ls + 60, order); assert min(g[-1].values()) > D, 'a later start still makes it: the bound is loose'


@check('the load-bearing sparse stops survive every filter on the default path')
def _():
    """Four times this project has lost the route to a reasonable-sounding rule about what counts as a real
    option, and each time the rule was found by hand, after days. Prose in CLAUDE.md does not fail a build,
    so the geography the route cannot do without is asserted here instead.

    None of these stops is busy. That is the point: busyness, averages and radii all delete them, and the
    route dies quietly at 267 h or 25 states with nothing going red. A stop being sparse is exactly why it
    is load-bearing, because the one service that calls there is the only way through."""
    want = {
        'Barstow': ('Barstow Amtrak', 'the Southwest Chief leaves from nowhere else; the depot has 2 services'),
        'Conway': ('Conway', 'five services, and Arkansas is new there'),
        'Holmes': ('HOLMES at ELVIS PRESLEY', 'Mississippi is taken on foot from here, 1.3 km to the line'),
        'Carr': ('BELLEVUE BOULEVARD at CA', 'the local-transit hop out of Memphis that reaches Holmes'),
    }
    missing = [f'{k} ({why})' for k, (pat, why) in want.items() if not R.stops_matching(pat)]
    assert not missing, 'stops absent from the router entirely: ' + '; '.join(missing)

    # The Mississippi walk-in has to exist as a border link, not merely as a stop.
    holmes = R.stops_matching('HOLMES at ELVIS PRESLEY')[0]
    ms = R.state_names.index('Mississippi')
    over = [j for j, w in R.foot.get(holmes, ()) if j >= R.first_virtual and R.state[j] == ms]
    assert over, 'Holmes no longer steps over the Mississippi line on foot; MS becomes uncollectable there'

    # The Memphis link back from the Mississippi line is LONGER than any plain walk: the old bug capped foot
    # weights at a made-up 1200, twenty minutes in seconds, and that one number hid every long link the route
    # needs. It used to be the modelled hop at Bellevue at Carr; modelled hops are off since Oct 16 2026 (taxis are
    # banned, so a route stands on timetables and walks), and the link is now the measured walk up Airways Blvd from
    # Holmes Rd to the bus station. Assert the thing the bug destroyed: that link, costing more than twenty minutes.
    air = R.idx.get('mata:0:AIRHO1SN')
    assert air is not None, 'Airways Blvd at Holmes Rd is missing; the Memphis walk back to the bus station is gone'
    long_links = [(j, w) for j, w in R.foot.get(air, ()) if w > 1200]
    assert long_links, ('Airways Blvd at Holmes has no foot link over twenty minutes; a walking-speed cap would '
                        'leave it looking connected while the walk the control uses is gone')

    # These stops are quiet, and that is the assertion, not an aside. `if n < 6: pass` was here instead: a
    # comment wearing an assertion's clothes, in the same commit that replaced another check for being a
    # no-op. What the project keeps getting wrong is rules that require a stop to be busy, so state the fact
    # those rules break on: at least one load-bearing stop serves fewer than the six the old --hub rule
    # demanded. If that stops being true the data moved and the rule deserves rechecking, not reinstating.
    # Count what the --hub rule counted: distinct named services, not connections. A first version of this
    # used np.bincount(R.cfrom), which counts one entry per connection over the whole twenty day window, so
    # the Barstow depot came out at 38 and the check failed against its own premise. Two services running
    # daily for twenty days is not thirty-eight services, and the rule that broke here was about services.
    svc = {}
    for k, (pat, why) in want.items():
        i = R.stops_matching(pat)[0]
        names = {R.trip_info.get((R.ctrip[c][0], R.ctrip[c][1]), ('', ''))[1]
                 for c in range(len(R.dep)) if R.cfrom[c] == i}
        svc[k] = len(names - {''})
        assert svc[k] > 0 or names, f'{k} has nothing departing at all, so nothing can board there'
    assert min(svc.values()) < 6, ('every load-bearing stop now runs six or more named services, so the '
                                   f'--hub 6 rule would no longer visibly break here: {svc}')


@check('nothing on the ride-search path picks stops by how busy they are')
def _():
    """`build_gateways` ranks stops by raw departure count, five per state inside a 6 km radius. That is the
    same shape as the alight rule that lost the Barstow depot, and it is blind to most of the geography the
    control needs: Conway and Holmes are not gateways for their states. It is not blind to all of it, which
    the first version of this check asserted and got wrong. Barstow Amtrak falls inside a California gateway
    radius, not because a busyness rule values a two-service depot but because Victor Valley Transit makes
    the nearby bus station busy and the radius is six kilometres. Being covered by accident is not the same
    as being chosen.

    The useful assertion is structural rather than numeric. The gateway list is fine where it is used, as a
    relocation hint for the ordering search; it becomes dangerous the moment it constrains where the ride
    search may stop. So this fails if `ride_search.py` ever starts using it. A count of services or
    departures deciding what is a real option is the single most repeated mistake in this project."""
    import numpy as _np, re
    S = search_for(R, hun, t237)
    gw = S.build_gateways()
    deps = _np.bincount(R.cfrom, minlength=R.N)
    blind = []
    for pat in ('Barstow Amtrak', 'Conway', 'HOLMES at ELVIS PRESLEY'):
        hits = R.stops_matching(pat)
        if not hits: continue
        i = hits[0]; y = int(R.state[i])
        if y < 0: continue
        lon, lat = R.stop_xy[i]
        inside = False
        for g in gw.get(y, []):
            m = re.match(r'@~(-?[\d.]+),(-?[\d.]+),([\d.]+)', g)
            if not m: continue
            a, b, km = float(m.group(1)), float(m.group(2)), float(m.group(3))
            if _np.hypot((lon - a) * 111.3 * _np.cos(_np.radians(lat)), (lat - b) * 111.3) <= km:
                inside = True; break
        if not inside: blind.append(f'{pat} ({int(deps[i])} departures)')
    # Pin which stops the gateways actually cover. Two claims died here. The first version asserted `blind`
    # was non-empty, which passes on any single survivor and says almost nothing. The second asserted all
    # three were outside, which is what the docstring claimed and is false: Barstow Amtrak IS inside a
    # California gateway radius, because Victor Valley Transit makes Barstow Station busy enough to be a
    # gateway and the depot sits within six kilometres of it. So gateways are not uniformly blind to quiet
    # geography, they are blind to Conway and Holmes and happen to cover Barstow for an unrelated reason.
    # Asserting the exact set makes drift in either direction visible.
    assert sorted(b.split(' (')[0] for b in blind) == ['Conway', 'HOLMES at ELVIS PRESLEY'], (
        'which load-bearing stops the busyness gateways reach has changed, and the reasoning that depends '
        f'on it needs rechecking rather than the assertion updating: outside = {blind}')

    src = open('ride_search.py').read()
    assert 'build_gateways' not in src, ('ride_search.py now uses build_gateways, which picks by departure '
                                         'count and does not contain ' + '; '.join(blind))


@check('route X can start, and no gate is guarded by a file nothing writes')
def _():
    """Two halves of the same escape.

    Geography first. Route X is the second forward gate, and it starts at the Jefferson Lines stop in
    Sheridan WY that data/manual/jefferson_lines.toml defines by hand (JL 701, with JL 702 as the return). Drop those
    rows and Wyoming has no Sheridan at all, x_forward.py's name match lands on Hollywood Sheridan Tri-Rail
    in Florida, and a route that costs 238.32 h is reported at 309.98. So assert the stop AND that something
    departs from it, because a stop definition with no service would pass the first half and still not start
    a route.

    Then the wiring. forward_shapes.py used to read its second gate's ordering from ../out/time_238.pkl
    under `if ... os.path.exists(a.record)`. Nothing in this repo has ever written that file and out/ is
    gitignored, so the gate skipped in silence on every fresh checkout and the harness reported one gate as
    two. That is the same shape as the sweep printing "0 of N jointly dead" for a test it never ran. A gate
    whose input can go missing can stop existing without anything saying so; the fix was to import the
    ordering instead, and this asserts nobody reintroduces the guard."""
    x = R.stops_matching('Sheridan WY Taco Bell')
    assert x, ('Sheridan WY is gone from the feed, so route X cannot start and the second forward gate is '
               'measuring nothing. data/manual/jefferson_lines.toml needs the JL 701 and JL 702 trips (7fd3c55).')
    deps = sum(1 for c in range(len(R.dep)) if R.cfrom[c] == x[0])
    assert deps, f'{R.stop_name[x[0]]} exists as a stop but nothing departs from it, so no route starts there'

    src = open('forward_shapes.py').read()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith('if ') and 'os.path.exists' in s and 'no_gate' in s:
            raise AssertionError('a forward_shapes gate is guarded by os.path.exists again, so it will skip '
                                 'silently whenever that file is absent: ' + s)
    assert 'from x_forward import ORDER' in src, ("forward_shapes no longer imports route X's ordering, so "
                                                  'the second gate is reading it from somewhere that can go '
                                                  'missing')


@check('move labels read correctly')
def _():
    S = Search.__new__(Search); S.R = R; n = lambda a: R.state_names.index(a)
    o = [n('Ohio'), n('Michigan'), n('Indiana'), n('Illinois')]
    assert S.move_label(o, [o[0], o[2], o[3], o[1]]) == 'move MI after IL', S.move_label(o, [o[0], o[2], o[3], o[1]])
    assert S.move_label(o, [o[0], o[2], o[1], o[3]]).startswith('reverse'), S.move_label(o, [o[0], o[2], o[1], o[3]])


@check("stop clocks print in the stop's own zone: South Hammond IN is Central, Window Rock (Navajo Nation) Mountain daylight")
def _():
    # noon UTC on Sep 24: 07:00 CDT, 06:00 MDT. A state's zone gives 08:00 (Indiana as Eastern) and 05:00 (Arizona, no DST).
    # Kept in September on purpose, not moved with the timetable window: only under daylight time does the Navajo Nation
    # (DST) differ from the rest of Arizona (none), and fmt_time needs no timetable.
    t = datetime(2026, 9, 24, 12, 0, tzinfo=ZoneInfo('UTC')).timestamp()
    for q, want in (('South Hammond', '07:00'), ('Window Rock - Bashas Parking Lot', '06:00'), ('Flagstaff', '05:00')):
        s = R.stops_matching(q)[0]; got = R.fmt_time(t, s)
        assert got.endswith(want), (R.stop_name[s], got, want)


@check("manual trips (data/manual) run on their own clocks: a tz line for the whole trip, else each stop's local zone")
def _():
    ex = next(f for f in R.feeds if f.name == 'extra'); bad = []; n = 0
    for tid, t in ex.trips.items():
        for _, sid, _, _ in t['stops']:
            n += 1; z = ex._tz_for(sid, t)
            want = t['tz'] if t.get('tz') else ZoneInfo(tr._tz_at(*ex.stops[sid][2:4]) or 'UTC')
            if str(z) != str(want): bad.append((t['route'][:40], ex.stops[sid][1], str(z), str(want)))
    assert n > 500 and not bad, (n, bad[:5])
    # end to end, one of each kind: AE bus Las Vegas NV (tz line, Pacific) leaves at its written clock, and
    # Limo Express LXUS 2101 (local clocks) reaches Deming at 06:00 Mountain after Willcox 03:00 Arizona
    fi = R.feeds.index(ex)
    def conns(tid): return sorted((i for i, c in enumerate(R.ctrip) if c[0] == fi and c[1] == tid), key=lambda i: R.dep[i])
    tid = next(k for k, t in ex.trips.items() if t['agency'] == 'AE bus' and 'Las Vegas NV' in t['route'])
    loc = datetime.fromtimestamp(R.dep[conns(tid)[0]], ZoneInfo('America/Los_Angeles'))
    assert loc.hour * 3600 + loc.minute * 60 == ex.trips[tid]['stops'][0][3], loc
    tid = next(k for k, t in ex.trips.items() if t['route'].startswith('LXUS 2101'))
    c = conns(tid); dem = next(i for i in c if R.stop_name[R.cto[i]] == 'Deming')
    assert R.fmt_time(R.arr[dem], R.cto[dem]).endswith('06:00'), R.fmt_time(R.arr[dem], R.cto[dem])


@check('prefix-shared scoring (finish_many / _finish_block) equals one-at-a-time _finish on all 24 orders of AZ UT CO NM')
def _():
    import itertools
    t0 = datetime(2026, 11, 5, tzinfo=ZoneInfo('America/Denver')).timestamp()
    four = [R.state_names.index(n) for n in ('Arizona', 'Utah', 'Colorado', 'New Mexico')]
    S = Search(R, ts.FREE, t0, [], 1, [s for s in range(N_STATES) if s not in four])
    ts.bind(R, ts.FREE, t0, S)
    perms = [list(p) for p in itertools.permutations(four)]
    a, b = ts._finish_block(perms), [ts._finish(o) for o in perms]
    assert a == b and any(x != float('inf') for x in a), [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y][:3]



@check('a measured walk link collects its state: Sioux City -> Nebraska bank over the Veterans Bridge in 30 min')
def _():
    # The guard against collecting a state by walking into a real stop also caught the end points of
    # walk_links.csv, so every hand-measured border walk (South Sioux City, Big River Crossing, Michiana, the
    # Vermont runs) was silently unable to collect anything, and coverage ignored them too. Both halves fail here.
    sc = R.idx['ibus:339']; ne = R.state_names.index('Nebraska')
    bank = R.stops_matching('Nebraska bank at South Sioux City')[0]
    assert R.walk_collects(bank) and not R._crosses(sc, bank), 'the measured link no longer counts as a walk-in'
    t = datetime(2026, 11, 15, 21, 50, tzinfo=CT).timestamp()
    S = Search(R, sc, t, [], 1, [s for s in range(N_STATES) if s != ne], end=ne)
    ts.bind(R, sc, t, S, end=ne)
    f, legs = S.evaluate([ne])
    assert S.all_states(legs) and f - t <= 3600, (f - t, legs[-1:])



@check('every measured on-foot link ends across a state line from where it starts')
def _():
    # The Moorhead walk's end point sat 200 m west of the Red River, so Nick's measured 83 min walk to Minnesota
    # collected nothing and X waited a day for a bus. A foot link (one with miles) exists to cross a line, unless its note
    # says 'positioning:' (Oct 13: the 2.5 mi run from the 702 Shuttles stop to Barstow Amtrak for the Chief, a fit-run
    # backup inside California; Oct 15: the 6 mi run down Chapman Road from Virginia Breeze at Rural King, Wytheville, to the
    # Barons stop at Fort Chiswell; Express Arrow <-> Outrider in Brush, CO, 1.53 km; Oct 23: Tornado stop <-> another carrier's stop in the
    # same town, Nick's Google walks). Those must still resolve, and there must be no more of them than are named here.
    import csv, os
    bad = []; positioning = []
    for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'walk_links.csv'), encoding='utf-8')):
        if not (r.get('miles') or '').strip(): continue
        # an end point the router cannot resolve drops the link without a word ('walk link: unknown stop'), which is
        # the same failure as an end point on the wrong bank, so it fails here too
        if r['from_uid'] not in R.idx or r['to_uid'] not in R.idx: bad.append(('unresolved', r['from_uid'], r['to_uid'])); continue
        a, b = R.idx[r['from_uid']], R.idx[r['to_uid']]
        if r['note'].startswith('positioning:'): positioning.append(r['to_uid']); continue
        if R.state[a] == R.state[b]: bad.append((R.stop_name[b], R.state_names[R.state[b]]))
    assert not bad, bad
    assert positioning == ['amtrak:BAR', 'ibus:2404', 'outrider:3453956', 'extra:Nampa ID (Maverik)', 'amtrak:BAR', 'flix:bd02b7ef-402c-4319-b4f0-1a1a510bc750', 'amtrak:KNG', 'amtrak:KNG', 'ibus:35', 'amtrak:JOL', 'flix:17bfaec0-6363-4796-82fa-1e8ed8b8c3f1', 'ibus:21', 'flix:c06f6dbc-a18f-4b22-957a-ba3d838f60aa', 'ibus:1996', 'amtrak:RTL', 'flix:8e7198b1-1e4d-449c-b120-a7a77793c5f4', 'amtrak:EFG', 'amtrak:HOP', 'flix:79685b14-530b-47e5-85dc-26ccf93c96cb', 'ibus:2779', 'flix:1a24da03-eee1-497f-a240-ed222380390f', 'ibus:773', 'flix:9e67280f-1256-42f4-9d1d-701cb6fe6ef5', 'ibus:3604', 'amtrak:GNS', 'amtrak:GNS', 'flix:de3e90c2-abad-4730-ad34-376d1b74bcf5', 'ibus:1938', 'amtrak:WLN', 'flix:3d9eca30-6cc0-4c46-b14a-4a3c7f9bc7f3', 'amtrak:JAN', 'flix:87a9cec7-53a2-4aef-b94b-a43b1b1d9ffa', 'ibus:2386', 'flix:38dd6257-00e6-4546-8022-c77c92e1c755', 'ibus:1035', 'flix:a11b3733-35d7-4842-9874-94a35cf8acd1', 'ibus:338', 'ms_cta:4.385 - AUTOMALL @ TIMBER GROVE_4.385 - AUTOMALL @ TIMBER GROVE_30.441061_-88.900001', 'ibus:2342', 'amtrak:MEI', 'flix:7aa2a4ad-52f3-4560-97d4-aa69edfe58b7', 'ibus:1027', 'amtrak:HMD', 'amtrak:SDL', 'flix:2adabb11-c8d8-4a4d-b862-3d9f2831f7e9', 'ibus:2158'], ('positioning foot links changed; review them and update this list', positioning)


@check('the Big River Crossing walk keeps the bridge hours (06:00-22:00): Arkansas by 10:45 from 10:00, not by bridge at 23:00')
def _():
    # A walk link is open at every hour, so the bridge is timetabled walks instead (big_river_crossing.toml) and
    # its mid-bridge point must stay unreachable by any footpath; otherwise a night search walks over a closed bridge.
    mem = R.idx['amtrak:MEM']; ar = R.state_names.index('Arkansas')
    mid = R.stops_matching('Arkansas line on Big River Crossing')[0]
    assert not R.foot.get(mid) and all(j != mid for i in R.foot for j, _ in R.foot[i]), 'mid-bridge point has a footpath'
    def reach(h):
        t = datetime(2026, 11, 11, h, 0, tzinfo=CT).timestamp()
        S = Search(R, mem, t, [], 1, [s for s in range(N_STATES) if s != ar], end=ar)
        ts.bind(R, mem, t, S, end=ar)
        f, legs = S.evaluate([ar]); return f - t, legs
    d, legs = reach(10)
    assert d <= 45 * 60 and any(l[0] == 'ride' and l[4] == mid for l in legs), (d / 60, legs[-1:])
    d, legs = reach(23)
    at_mid = [l[5] if l[0] == 'ride' else l[4] for l in legs if (l[4] if l[0] == 'ride' else l[2]) == mid]
    assert all(6 <= datetime.fromtimestamp(x, CT).hour < 22 for x in at_mid), ('on the bridge while closed', legs)


@check('no walk-in between New York and New Jersey: Manhattan stops do not step into the Hudson (Oct 29 2026)')
def _():
    # The Wonder Bus finish from 120 E Broadway "walked into NJ" from 14 St, to a point mid-Hudson: NY-NJ was not a
    # river border, so 120 such walk-ins existed (97 in the river or harbour). Nick: nobody walks into NY or NJ.
    m14 = [i for i in R.stops_matching('14 St') if R.abbr[i] == 'NY']
    assert m14, 'no 14 St stop in New York: this check would pass by having nothing to test'
    ny_nj = [R.stop_ids[v] for v in range(R.first_virtual, R.N)
             if {R.abbr[v], R.abbr[R.idx[R.stop_ids[v].split(':', 1)[1].rsplit(':', 1)[0]]]} == {'NY', 'NJ'}]
    assert not ny_nj, (len(ny_nj), ny_nj[:3])
    assert R.first_virtual < R.N, 'no walk-ins at all: the rule would be vacuous'


print()
for name, ok, info in results: print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '\n     ' + info))
print(f'\n{sum(ok for _, ok, _ in results)}/{len(results)} passed')
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
