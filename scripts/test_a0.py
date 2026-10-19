"""Tier A0 from CLAUDE.md: milliseconds, no router, synthetic fixtures of a few connections.

    python3 test_a0.py        exits 1 on any failure

Each test pins a shape that has already escaped at least once. Put a fixed bug here when a three-stop fixture
can see it, rather than in regress.py where it costs a router and fifteen seconds.
"""
import re, sys, traceback
from collections import defaultdict
from types import SimpleNamespace
import numpy as np

results = []


def test(fn):
    try: fn(); results.append((fn.__name__, True, ''))
    except Exception as e: results.append((fn.__name__, False, f'{type(e).__name__}: {e}')); traceback.print_exc()
    return fn


# ---- pick.py -------------------------------------------------------------------------------------------

@test
def choose_reports_runner_up_and_gap():
    from pick import choose
    said = []
    # Marks Amtrak reached a minute before the Mississippi line at Holmes: the pick must say so
    best = choose([('Holmes MS line', 386), ('Marks Amtrak', 385)], key=lambda e: e[1], label='MS',
                  show=lambda e: e[0], out=said.append)
    assert best[0] == 'Marks Amtrak'
    assert 'runner-up Holmes MS line' in said[0] and 'gap 1' in said[0], said


@test
def choose_flags_ties_and_refuses_empty():
    from pick import choose
    said = []
    choose([3, 3], key=lambda x: x, label='t', out=said.append)
    assert said[0].endswith('TIE'), said
    try: choose([], key=lambda x: x, label='empty', out=said.append)
    except ValueError: pass
    else: raise AssertionError('an empty candidate set must raise, not return None')


@test
def gate_stops_on_a_wrong_control():
    from pick import gate
    assert gate('ok', lambda: 237.34, 237.34, 0.01, out=lambda *_: None) == 237.34
    for bad in (285.34, None):     # 285.34 is the Charleston start that cands[0] once produced
        try: gate('bad', lambda: bad, 237.34, 0.01, out=lambda *_: None)
        except SystemExit: continue
        raise AssertionError(f'gate let {bad} through')


# ---- ride_search leg layouts -----------------------------------------------------------------------------

@test
def final_stop_reads_the_right_index_for_rides_and_walks():
    from ride_search import final_stop
    ride = ('ride', ('f', 't', 0), 10, 0.0, 20, 100.0)       # destination at index 4
    walk = ('walk', 20, 99, 100.0, 1000.0)                    # destination at index 2
    assert final_stop([ride]) == 20
    # the control ends by riding to Hanover and walking over the Vermont line: index 2 of the ride would be
    # where it BOARDED, which is the bug this function exists to prevent
    assert final_stop([ride, walk]) == 99
    assert final_stop([]) is None


@test
def opt_keeps_walk_out_of_the_trip_slot():
    from ride_search import Opt
    o = Opt(5, 1.0, ('f', 't', 0), frozenset({1, 2}), walk=2)
    to, at, trip, got, walk, seg = o
    assert trip == ('f', 't', 0) and walk == 2 and seg == ()
    assert Opt(5, 1.0, ('f', 't', 0), frozenset()).walk is None


# ---- pair_tables.leg_states on a three-stop trip ------------------------------------------------------------

def _three_stop_router():
    """stops 0,1,2 in states 7,8,9 on one trip T; stop 3 is a border point in state 4"""
    return SimpleNamespace(dep=np.array([0.0, 100.0]), arr=np.array([90.0, 190.0]),
                           cfrom=np.array([0, 1]), cto=np.array([1, 2]),
                           state=np.array([7, 8, 9, 4]))


@test
def leg_states_credits_states_passed_through():
    from pair_tables import leg_states
    R = _three_stop_router()
    tc = defaultdict(list, {'T': [0, 1]})
    # boarded at 0, alighted at 2: 8 is passed through mid-ride and must count, not only the ends
    assert leg_states(R, ('T', 0, 2, 0.0, 190.0), tc) == {7, 8, 9}
    # alighted at 1: 9 is never reached and must not be credited
    assert leg_states(R, ('T', 0, 1, 0.0, 90.0), tc) == {7, 8}


@test
def leg_states_adds_the_walked_in_state_and_seg_is_exact():
    from pair_tables import leg_states
    R = _three_stop_router()
    tc = defaultdict(list, {'T': [0, 1]})
    assert leg_states(R, ('T', 0, 1, 0.0, 90.0, 4), tc) == {7, 8, 4}
    # seg = (board conn, alight conn) = (1, 1): only the second stretch was ridden
    assert leg_states(R, ('T', 1, 2, 100.0, 190.0, None, (1, 1)), tc) == {8, 9}


# ---- common.within_km, the one radius helper five scripts share ---------------------------------------------

@test
def within_km_agrees_with_haversine_away_from_the_edge():
    from common import within_km, hav
    rng = np.random.default_rng(7)
    for lat in (25.8, 35.1, 48.9):                     # Miami, Memphis, the 49th parallel
        c = (-90.0, lat)
        xy = np.column_stack([c[0] + rng.uniform(-0.1, 0.1, 400), lat + rng.uniform(-0.1, 0.1, 400)])
        got = set(within_km(xy, *c, 5.0).tolist())
        d = np.array([hav(c, p) for p in xy])
        assert {i for i in range(len(xy)) if d[i] < 4.98} <= got, lat     # flat projection: metres, not km
        assert not got & {i for i in range(len(xy)) if d[i] > 5.02}, lat
        assert within_km(xy, *c, 5.0).dtype == np.int64


# ---- time_router._scan_fast: a horizon cuts the scan without changing anything it keeps ------------------

def _random_router(rng, n=30, n_trips=40):
    """A TimeRouter shell over random trips and footpaths, with only what the compiled scan reads."""
    from time_router import TimeRouter
    conns = []
    for tr in range(n_trips):
        stops = rng.choice(n, size=int(rng.integers(2, 6)), replace=False); t = float(rng.integers(0, 4000))
        for a, b in zip(stops, stops[1:]):
            d = t + float(rng.integers(0, 300)); t = d + float(rng.integers(60, 900))
            conns.append((d, t, int(a), int(b), tr))
    conns.sort()
    foot = defaultdict(list)
    for _ in range(n):
        i, j = (int(x) for x in rng.choice(n, size=2, replace=False)); foot[i].append((j, float(rng.integers(30, 600))))
    ptr = np.zeros(n + 1, dtype=np.int32); to, w = [], []
    for i in range(n):
        for j, x in foot[i]: to.append(j); w.append(x)
        ptr[i + 1] = len(to)
    R = TimeRouter.__new__(TimeRouter)
    R.N, R.first_virtual, R.trip_ids = n, n, {k: k for k in range(n_trips)}
    R.target_set = lambda target: {n - 1}
    col = lambda k, dt: np.ascontiguousarray([c[k] for c in conns], dtype=dt)
    R._fa = dict(dep=col(0, np.float64), arr=col(1, np.float64), cfrom=col(2, np.int32), cto=col(3, np.int32),
                 ctrip=col(4, np.int32), ptr=ptr, to=np.array(to, dtype=np.int32), w=np.array(w, dtype=np.float64),
                 fx=np.zeros(len(to), dtype=np.uint8))
    R._bind_fast()
    assert R._fast is not None, 'csa.so did not load'
    return R


@test
def scan_horizon_keeps_every_label_it_reaches():
    # ride_search --goal scans only to the latest ceiling and calls the answer exact for every stop reached by
    # then. This is that claim: best, and the predecessors replayed from it, equal the full scan's there.
    rng = np.random.default_rng(48)
    for _ in range(200):
        R = _random_router(rng)
        start = int(rng.integers(0, R.N)); t0 = float(rng.integers(0, 2000))
        one = lambda h: R._scan_fast(np.array([start]), np.array([t0]), np.array([-1], dtype=np.int32),
                                     'X', want_pred=True, t_end=h)[3]
        full = one(None)
        for h in rng.integers(0, 8000, size=4).astype(float):
            cut = one(h)
            kept = cut['best'] <= h
            assert np.array_equal(cut['best'][kept], full['best'][kept]), (h, start)
            for k in ('conn', 'walk', 'walk_ride'):
                assert np.array_equal(cut[k][kept], full[k][kept]), (k, h, start)
            # rconn is the ride into a stop, read only through a walk off that ride, which left by the horizon.
            # A later ride can overwrite it in the full scan only for stops whose ride arrived after it.
            arr = R._fa['arr']; rc = full['rconn']
            by_h = (rc >= 0) & (arr[np.maximum(rc, 0)] <= h)
            assert np.array_equal(cut['rconn'][by_h], rc[by_h]), ('rconn', h, start)
            # what it does not keep can only be later in the full scan too, never earlier than the horizon
            assert (full['best'][~kept] > h).all(), (h, start)


# ---- time_search.bind / rebind: a mid-run switch takes start, clock and end from the new search ------------

@test
def rebind_takes_start_clock_and_end_from_the_search():
    import time_search as ts
    from types import SimpleNamespace as NS
    a, b = NS(start=1, t0=100.0, end=None), NS(start=7, t0=900.0, end=3)
    ts.bind('R', a.start, a.t0, a, base='B')
    ts.rebind(b)
    assert (ts._R, ts._BASE) == ('R', 'B'), 'rebind must keep the router and base'
    assert (ts._SELF, ts._START, ts._T0, ts._END) == (b, 7, 900.0, 3)
    ts.rebind(a)
    assert (ts._SELF, ts._START, ts._T0, ts._END) == (a, 1, 100.0, None), 'switching back restores the first search'


# ---- shape_followup's log parser against the exact format forward_shapes prints ------------------------------

@test
def followup_parses_forward_shapes_rows():
    from shape_followup import ROW
    line = f'  {3:3d} {"MI":5s} {"OH":5s} {241.07:8.2f} h  {"Fri 25 Sep 06:10":>16s}  {"Detroit Bus Station":38s}'
    m = ROW.match(line.rstrip())
    assert m and m.group(1) == '3' and m.group(4) == '241.07' and m.group(5) == 'Fri 25 Sep 06:10', line
    assert m.group(6).strip() == 'Detroit Bus Station'
    beat = line.rstrip() + '   BEATS THE CONTROL'
    assert ROW.match(beat).group(7), 'the BEATS flag must be captured separately, not glued onto the stop name'
    assert not ROW.match('  rot  3 start: chose X, runner-up Y, gap 0.5')


if __name__ == '__main__':
    print()
    for name, ok, info in results: print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '\n     ' + info))
    print(f'\n{sum(ok for _, ok, _ in results)}/{len(results)} passed')
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
