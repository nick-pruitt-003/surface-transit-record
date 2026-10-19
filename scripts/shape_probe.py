"""Is a whole ordering feasible at all? Not searched, tested.

The search keeps dying on east-first chains and the control goes west-first while the East is still owed.
Nobody knows whether east-first is INFEASIBLE or merely badly ranked, and that is a different question from
anything a search can answer, because a search that never finishes a route says nothing about which shapes
exist.

The pair table is two chained reverse scans: seed from y's stops with L[z] and you get the latest you can
be anywhere and still collect y, then z, then finish. Nothing stops that chaining to 48. Seed from the
first state's stops with L[second -> third -> ... -> end] and the value at the start stop is the latest you
could have left and still collected the whole order in that order and finished by the deadline.

    if that value is before the start time, the ordering is impossible

for that ordering. The scans themselves are permissive at every seam (guard=False, and `max(lat, eff)` lets
a connection be boarded with zero transfer).

**But the test as a whole is STRICTER than reality, and the first run measured by how much.** Chaining
scans through an order demands you visit a stop of each state in strict sequence, while a real route picks
up many states incidentally as it passes through. The control's own targets came back feasible by 36
seconds when the route truly finishes 0.7 h inside the deadline. So the strictness is worth about 0.7 h on
the control, and a shape whose real margin is under that reads as IMPOSSIBLE when a route exists.

An early version of this docstring claimed the opposite, that the test could only ever be too generous and
a shape it ruled out was genuinely ruled out. That was wrong, and it was wrong in the direction that makes
a probe sell a false negative as a fact. Run `--true-order` to derive the order the route actually collects
in: the gap between the two IS the correction, and until it is measured an IMPOSSIBLE verdict is a
statement about this test and not about the timetable.

This is NOT the ordering search CLAUDE.md declares dead. That one searched the space of orderings guided by
a leftover estimate, and every form of the estimate failed because a spanning tree cannot price a set of
states with no idea where or when you are. This estimates nothing and searches nothing. It takes one shape
as a hypothesis and asks the timetable whether it can exist, for about 48 scans.

Falsification, before running: the control's own order must come back feasible with roughly its own known
slack. If the 237 route reads as impossible, the probe is wrong and nothing else it says counts. It came
back feasible, and at 36 seconds rather than the route's real 0.7 h, which is how the strictness above was
found: the falsification passed and the margin it passed by was the finding.

A second lesson from the first run, about choosing shapes rather than about the machinery. `east-first` and
`west-first` sort the states by mean longitude, and BOTH are impossible. They do not fail because of
direction; they fail because a longitude sort is not a route shape at all, forcing you to sweep the height
of the country at every step. Permute at the granularity that preserves local coherence, contiguous blocks
of an order that works, or the answer is about the permutation and not about the shape.

    python3 shape_probe.py
    python3 shape_probe.py --shapes control,reverse,east-first
"""
import argparse, os, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
import backward as B
from common import ABBR

HERE_SHAPES = ('control', 'reverse', 'east-first', 'west-first', 'halves-swapped')

_RW = {}      # worker state, inherited by fork rather than pickled, as pair_tables._W is


def _latest(F, D, span, nxt):
    lat, ok, k0, k1 = F.layer(nxt, False, D - span * 3600, None)
    eff, _ = F.through(ok, k0, k1, np.ones(F.R.N, bool))
    return np.maximum(lat, eff)


def _rot(k):
    """one rotation: its chain, and the stop it could leave latest from"""
    full, st, D, F, span = _RW['full'], _RW['st_stops'], _RW['D'], _RW['F'], _RW['span']
    order = full[k:] + full[:k]
    e_ = order[-1]
    cur = _latest(F, D, span, {s: D for s in st[e_]})
    for y in reversed(order[:-1]):
        nxt = {s: float(cur[s]) for s in st[y] if cur[s] > -np.inf}
        if not nxt: return k, order[0], e_, None, None
        cur = _latest(F, D, span, nxt)
    j = int(np.argmax(cur))
    return k, order[0], e_, float(cur[j]), j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-05T00:54')
    ap.add_argument('--by', default='2026-11-14T22:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--start', default='Huntington Bus Stop')
    ap.add_argument('--route', default='../out/res_starttest.pkl', help='the order to permute')
    ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--shapes', default=','.join(HERE_SHAPES))
    ap.add_argument('--rotations', action='store_true', help='the question the fixed ordering cannot ask. '
                    'Asking which start suits the control ordering is circular, because that ordering is the '
                    'shape built around Huntington and can only answer Huntington. A rotation enters the '
                    'same geographic sequence at a different point and ends where that puts it, so it is a '
                    'different shape with its own natural start and its own end. The deadline is shared, so '
                    'the latest possible departure is directly comparable across all of them: the rotation '
                    'with the latest departure is the fastest shape.')
    ap.add_argument('--workers', type=int, default=0)
    ap.add_argument('--starts', type=int, default=0, help='report the best N start stops for this ordering. '
                    'test() already returns the latest possible departure from EVERY stop, so with the '
                    'deadline fixed, D - cur[s] is the elapsed time of a route starting at s and any stop '
                    'under the control\'s 237.34 h is a start that beats it. One chain answers it for all '
                    '19776 stops; it was being read one element at a time.')
    ap.add_argument('--trace', action='store_true', help='with --true-order, print the margin at every step of the control chain so a slack loss can be localised instead of reported as one number at the end')
    ap.add_argument('--true-order', action='store_true', help='derive the order from the route\'s own legs rather than the pickle\'s target list. The difference between the two IS the strictness this test adds, and until it is measured an IMPOSSIBLE verdict may be a fact about the test rather than about the timetable.')
    a = ap.parse_args()

    tz = ZoneInfo(a.tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    inv = {v: k for k, v in ABBR.items()}
    ab = lambda x: ABBR[R.state_names[x]]
    F = B.RevFast(R)
    end_st = R.state_names.index(inv[a.end])

    st_stops = [[] for _ in range(N_STATES)]
    for s in range(R.N):
        if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)

    # Every exact match for the start name, because 2955 names in this router map to more than one stop and
    # picking the first silently is how a probe reports on a place nobody asked about.
    starts = [i for i, n in enumerate(R.stop_name) if n == a.start]
    if not starts: raise SystemExit(f'no stop named exactly {a.start!r}')

    def latest_from(nxt):
        lat, ok, k0, k1 = F.layer(nxt, False, D - a.span * 3600, None)
        eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
        return np.maximum(lat, eff)

    L_end = latest_from({s: D for s in st_stops[end_st]})

    def test(order, where=None, marg=None):
        """latest departure from each stop that still does this whole order, and where it dies if it does

        With `where` mapping state -> (stop, time) from the route itself, also records the margin at every
        step: standing where the route stands when it first enters that state, at that time, how much room
        is left to do all of it. That localises a slack loss instead of reporting one number at the end.
        The control loses 0.57 h between its real slack (+0.66 h) and what this test grants it (+0.09 h),
        and 0.57 h in a timetable this lumpy is potentially a whole missed connection rather than rounding:
        you make the Silver Meteor or you wait for tomorrow's.
        """
        cur = L_end
        for i in range(len(order) - 1, -1, -1):
            y = order[i]
            nxt = {s: float(cur[s]) for s in st_stops[y] if cur[s] > -np.inf}
            if not nxt:
                return None, f'{ab(y)} (step {i + 1} of {len(order)}) is unreachable from anything ' \
                             f'that could still finish'
            cur = latest_from(nxt)
            if where is not None and marg is not None and i > 0:
                prev = order[i - 1]
                if prev in where:
                    s_, t_ = where[prev]
                    marg.append((i, prev, float(cur[s_]) - t_, s_, t_))
        return cur, None

    # mean longitude per state, from the router's own coordinates rather than a hand list of "western states"
    xy = np.asarray(R.stop_xy, dtype=float)
    lon = {}
    for y in range(N_STATES):
        if st_stops[y]: lon[y] = float(xy[np.asarray(st_stops[y]), 0].mean())

    WHERE = {}
    d_ = pickle.load(open(a.route, 'rb'))
    base = list(d_['order'])
    if a.true_order:
        # The pickle's `order` is a TARGET list fed to the router's layered scan, not the order in which the
        # route actually first collects states. Chaining scans through targets demands you visit a stop of
        # each in strict sequence, while the real route picks up many states incidentally as it passes
        # through. That strictness costs the control 0.7 h: it truly finishes at 237.3 h against a 238 h
        # deadline, so it has about forty minutes of room, and the target chain gives it 36 seconds.
        #
        # That matters far more than the control's own verdict. If strictness costs 0.7 h here it costs
        # something comparable on every other ordering, so a shape whose real margin is +0.5 h reads as
        # IMPOSSIBLE and the probe reports a fact about its own test rather than about the timetable.
        # Deriving the order the route actually collects in is the calibration: run it both ways and the
        # difference IS the correction.
        import time_search as ts
        from time_search import Search
        st0_ = R.stop_name.index(d_['start'])
        S_ = Search(R, st0_, d_['t0'], [], 1)
        ts.bind(R, st0_, d_['t0'], S_)
        _f, legs_ = S_.evaluate(d_['order'])
        from collections import defaultdict as _dd
        tc_ = _dd(list)
        for k_ in range(len(R.dep)): tc_[R.ctrip[k_]].append(k_)
        for v_ in tc_.values(): v_.sort(key=lambda k: R.dep[k])
        seen_ = []

        where_ = {}

        def add_(y_, s_=None, t_=None):
            if y_ is not None and y_ >= 0 and y_ not in seen_:
                seen_.append(int(y_))
                if s_ is not None: where_[int(y_)] = (int(s_), float(t_))

        # In the order the vehicle actually ENTERS each state, connection by connection in departure order.
        # The first version took sorted(S.covered(legs[:i+1])) and appended what was new, which breaks ties
        # WITHIN a leg by state index. One long ride collects several states at once, so that asked for them
        # in an order with no relation to the geography: the chain then demanded Nebraska before Iowa on a
        # train that passes them the other way, and reported the 237 route impossible at step 12. The route
        # exists and regress validates it every run, so that was the probe failing its own falsification.
        add_(int(R.state[st0_]), st0_, d_['t0'])
        for l_ in legs_:
            if l_[0] == 'ride':
                _, trip_, bs_, bt_, al_, at_ = l_
                add_(int(R.state[bs_]), bs_, bt_)
                for k_ in tc_.get(trip_, ()):
                    if bt_ <= R.dep[k_] and R.arr[k_] <= at_:
                        add_(int(R.state[int(R.cfrom[k_])]), int(R.cfrom[k_]), float(R.dep[k_]))
                        add_(int(R.state[int(R.cto[k_])]), int(R.cto[k_]), float(R.arr[k_]))
                add_(int(R.state[al_]), al_, at_)
            elif l_[0] == 'walk':
                add_(int(R.state[int(l_[2])]), int(l_[1]), float(l_[4]))
        base = seen_; WHERE.update(where_)
        print(f'true first-collection order: {len(base)} states, against {len(d_["order"])} targets')
    body = [y for y in base if y != end_st]

    def shape(name):
        if name == 'control': return list(body)
        if name == 'reverse': return list(reversed(body))
        if name == 'east-first': return sorted(body, key=lambda y: -lon.get(y, 0))
        if name == 'west-first': return sorted(body, key=lambda y: lon.get(y, 0))
        if name == 'halves-swapped':
            h = len(body) // 2
            return body[h:] + body[:h]
        raise SystemExit(f'unknown shape {name!r}; known: {", ".join(HERE_SHAPES)}')

    if a.rotations:
        full = body + [end_st]
        n_ = len(full)

        _RW.update(full=full, st_stops=st_stops, D=D, F=F, span=a.span)
        import multiprocessing as mp
        nw = a.workers or max(1, (os.cpu_count() or 2) - 1)
        with mp.get_context('fork').Pool(nw) as pool:
            rows = pool.map(_rot, range(n_))
        ok_rows = [r for r in rows if r[3] is not None]
        ok_rows.sort(key=lambda r: -r[3])
        print(f'{n_} rotations of the control sequence, {nw} workers.\n')
        print('  D-dep is an UPPER BOUND on each rotation\'s minimum elapsed, and NOT a ranking. A route')
        print('  exists from that stop departing then and finishing by the deadline, so its elapsed is at')
        print('  most D-dep. But the deadline is a fixed wall-clock instant, so a rotation whose services')
        print('  only permit a 05:00 start is charged for the misalignment with 22:54 as well as for its')
        print('  own duration, and that charge can approach a day. So:')
        print('     under 237.34 h  ->  a genuinely faster shape, definitive')
        print('     over  237.34 h  ->  nothing follows; it may be fast and badly aligned')
        print('  This run can rule shapes IN and cannot rule any OUT, which is the opposite of the')
        print('  fixed-ordering tests. Removing the bias needs a sweep of deadlines, or Search.evaluate')
        print('  forward from a start, which returns the real finish with no deadline involved.\n')
        print(f'  {"rot":>3s} {"first":5s} {"last":5s} {"latest departure":>18s} {"D-dep":>8s}  best start')
        for k, f_, e_, c_, j_ in ok_rows:
            print(f'  {k:3d} {ab(f_):5s} {ab(e_):5s} '
                  f'{datetime.fromtimestamp(c_, tz).strftime("%a %d %b %H:%M"):>18s} '
                  f'{(D - c_) / 3600:7.2f} h  {R.stop_name[j_][:40]}')
        for k, f_, e_, c_, j_ in rows:
            if c_ is None: print(f'  {k:3d} {ab(f_):5s} {ab(e_):5s} {"IMPOSSIBLE":>18s}')
        print('\nSorted by D-dep, which is not a ranking of the shapes. See the note above.')
        return

    print(f'start {a.start!r}: {len(starts)} stop(s) with that exact name; departing '
          f'{datetime.fromtimestamp(t0, tz):%a %H:%M}, deadline {datetime.fromtimestamp(D, tz):%a %H:%M}\n')
    print(f'{"shape":16s} {"latest possible departure":>26s} {"margin":>10s}   verdict')
    for name in a.shapes.split(','):
        order = shape(name.strip()) + [end_st]
        marg = [] if (a.trace and name.strip() == 'control') else None
        cur, dead = test(order, WHERE if marg is not None else None, marg)
        if marg:
            print('   step  state  margin   where the route stands when it enters it')
            for i_, y_, m_, s_, t_ in sorted(marg):
                print(f'   {i_:4d}  {ab(y_):5s} {m_ / 3600:+7.2f} h  {R.stop_name[s_][:34]:34s} '
                      f'{datetime.fromtimestamp(t_, tz):%a %H:%M}')
        if dead is not None:
            print(f'{name:16s} {"-":>26s} {"-":>10s}   IMPOSSIBLE: {dead}')
            continue
        best = max(float(cur[s]) for s in starts)
        if best <= -np.inf:
            print(f'{name:16s} {"unreachable":>26s} {"-":>10s}   IMPOSSIBLE from this start')
            continue
        m = (best - t0) / 3600
        when = datetime.fromtimestamp(best, tz).strftime('%a %d %b %H:%M')
        if a.starts:
            el = (D - np.asarray(cur)) / 3600.0
            ok_ = np.isfinite(el) & (el > 0)
            idx = np.argsort(el)
            print(f'\n  best starts for the {name} ordering, by elapsed time (D - latest departure).')
            print(f'  A bound, not a route: the scans are permissive at every seam, so these are lower '
                  f'bounds on elapsed and a stop listed here still has to be flown to be believed.')
            print(f'  {"stop":38s} {"latest departure":>18s} {"elapsed":>9s}')
            shown = 0
            for j in idx:
                if not ok_[j]: continue
                print(f'  {R.stop_name[int(j)][:38]:38s} '
                      f'{datetime.fromtimestamp(float(cur[j]), tz).strftime("%a %d %b %H:%M"):>18s} '
                      f'{el[j]:8.2f} h' + ('   BEATS THE CONTROL' if el[j] < 237.34 else ''))
                shown += 1
                if shown >= a.starts: break
            print()
        print(f'{name:16s} {when:>26s} {m:+9.2f} h   '
              f'{"feasible" if m >= 0 else "IMPOSSIBLE, must have left " + f"{-m:.2f} h earlier"}')

    print('\nMargin is how much later than the actual start you could have left and still done the whole '
          'order. Negative means no route exists in that order from this start at this time, which is a '
          'fact about the timetable and not about any search. The scans are permissive at every seam, but the test as a whole is '
          'STRICTER than reality because it demands strict sequencing, so run --true-order to measure that '
          'correction before believing any IMPOSSIBLE.')


if __name__ == '__main__':
    main()
