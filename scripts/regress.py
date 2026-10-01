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
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, start, t0, S, None, None
    return S


print('settings: MIN_TRANSFER', tr.MIN_TRANSFER // 60, 'min, WALKIN_KM', tr.WALKIN_KM, ', SCAN_SLACK', tr.SCAN_SLACK / 3600, 'h')
R = cached_router(datetime(2026, 9, 23).date(), 18)
t237 = datetime(2026, 9, 24, 0, 30, tzinfo=ET).timestamp()
hun = R.stops_matching('Huntington Bus Stop')[0]


@check('defaults match the search settings (5 min transfers, 1.4 km walk-ins, 24 h slack)')
def _():
    assert (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK) == (300, 1.4, 86400), (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK)


@check('Amtrak times are agency (Eastern) time: CONO Effingham 10:01 PM, Memphis 4:42 AM Central')
def _():
    efg = R.stops_matching('Effingham Amtrak Station')[0]; mem = R.idx['amtrak:MEM']
    day = datetime(2026, 9, 24, tzinfo=CT).timestamp()
    ks = [k for k in range(len(R.dep)) if R.cfrom[k] == efg and day < R.dep[k] < day + 86400
          and R.trip_info[(R.ctrip[k][0], R.ctrip[k][1])][1] == 'City of New Orleans']
    deps = {datetime.fromtimestamp(R.dep[k], CT).strftime('%H:%M') for k in ks}
    assert '22:01' in deps, deps
    k = ks[[datetime.fromtimestamp(R.dep[j], CT).strftime('%H:%M') for j in ks].index('22:01')]
    key = R.ctrip[k]; arr = [R.arr[j] for j in range(k, min(k + 400000, len(R.dep))) if R.ctrip[j] == key and R.cto[j] == mem]
    assert arr and datetime.fromtimestamp(arr[0], CT).strftime('%H:%M') == '04:42', arr


@check('237 route (hun_ms_meteor) is valid: all 48 states, finish <= 238.0 h from the 12:30 AM clock')
def _():
    S = search_for(R, hun, t237)
    f, legs = S.evaluate(pickle.load(open(OUT + 'hun_ms_meteor.pkl', 'rb'))['order'])
    assert S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]
    assert (f - t237) / 3600 <= 238.0, (f - t237) / 3600


@check('router and coverage agree: every state target is collected by a ride or border walk-in (Sunland seed)')
def _():
    st = R.stops_matching('McNutt & Calle Morocco')[0]; t0 = datetime(2026, 9, 23, tzinfo=ZoneInfo('America/Denver')).timestamp()
    S = search_for(R, st, t0)
    inv = {v: k for k, v in ts.ABBR.items()}
    order = [R.state_names.index(inv[x]) for x in 'TX,LA,MS,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,WV,KY,TN,AR,MO,IL,IN,MI,WI,MN,IA,NE,KS,OK,CO,WY,SD,ND,MT,ID,WA,OR,UT,AZ,NV,CA'.split(',')]
    f, legs = S.evaluate(order)
    assert f < float('inf') and S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]


@check('backward report on the 237 result: every layer feasible, slack >= 0, latest start = 12:54 AM Thu')
def _():
    d = pickle.load(open(OUT + 'res_starttest.pkl', 'rb')); order = d['order']; t0 = d['t0']
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
    assert datetime.fromtimestamp(ls, ET).strftime('%a %H:%M') == 'Thu 00:54', datetime.fromtimestamp(ls, ET)


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

    # The Memphis hop is a local-transit proxy link, and the point of it is that it is LONGER than any plain
    # walk: the old bug capped foot weights at a made-up 1200, which is twenty minutes in seconds, and that
    # one number hid every proxy hop the route needs. Asserting the link merely exists would pass with the
    # bug reinstated, so assert the thing the bug destroyed, a usable link costing more than twenty minutes.
    bell = R.stops_matching('BELLEVUE BOULEVARD at CA')[0]
    long_hops = [(j, w) for j, w in R.foot.get(bell, ()) if w > 1200]
    assert long_hops, ('Bellevue at Carr has no foot link over twenty minutes; a walking-speed cap would '
                       'leave this stop looking connected while the hop the route uses is gone')
    assert max(w for _, w in long_hops) > 1200, 'longest link at Bellevue at Carr is under the old 1200 cap'

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
    Sheridan WY that data/extra_trips.csv defines by hand (JL 701, with JL 702 as the return). Drop those
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
               'measuring nothing. data/extra_trips.csv needs the JL 701 and JL 702 rows (7fd3c55).')
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
    t = datetime(2026, 9, 24, 12, 0, tzinfo=ZoneInfo('UTC')).timestamp()
    for q, want in (('South Hammond', '07:00'), ('Window Rock - Bashas Parking Lot', '06:00'), ('Flagstaff', '05:00')):
        s = R.stops_matching(q)[0]; got = R.fmt_time(t, s)
        assert got.endswith(want), (R.stop_name[s], got, want)


@check('every extra_trips row departs at its own stated clock in its own tz column (zones are per row, not per agency)')
def _():
    import csv, os
    # ExtraFeed numbers trips t{k} over every csv row, disabled '#' rows included
    ex = next(f for f in R.feeds if f.name == 'extra'); bad = []; n = 0
    for k, r in enumerate(csv.DictReader(open(os.path.join(tr.DATA_DIR, 'extra_trips.csv'), encoding='utf-8'))):
        t = ex.trips.get(f't{k}')
        if t is None: continue
        n += 1; z = str(ex._tz_for(None, t))
        if z != r['tz']: bad.append((r['agency'], r['route'][:40], r['tz'], z))
    assert n > 100 and not bad, (n, bad[:5])
    # and end to end: AE bus Las Vegas NV leaves at its stated Pacific clock, not an hour early
    fi = R.feeds.index(ex)
    tid = next(k for k, t in ex.trips.items() if t['agency'] == 'AE bus' and 'Las Vegas NV' in t['route'])
    first = ex.trips[tid]['stops'][0][3]   # seconds after midnight, as written in the row
    deps = sorted(R.dep[i] for i, c in enumerate(R.ctrip) if c[0] == fi and c[1] == tid)
    loc = datetime.fromtimestamp(deps[0], ZoneInfo('America/Los_Angeles'))
    assert loc.hour * 3600 + loc.minute * 60 == first, (loc, first)


print()
for name, ok, info in results: print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '\n     ' + info))
print(f'\n{sum(ok for _, ok, _ in results)}/{len(results)} passed')
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
