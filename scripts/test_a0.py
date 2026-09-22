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
