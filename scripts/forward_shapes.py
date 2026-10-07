"""What does a shape actually cost? Measured forward, in hours, with no deadline involved.

Nick: "do it forwards, if it works forward it works."

Everything else tried today measures a proxy. The backward chain measures the latest departure that still
beats a fixed wall-clock deadline, which charges a shape for how badly its services align with Saturday
22:54 as well as for its own duration, and that charge can approach a day. So rotations are not comparable
to each other that way, and reading that table as a ranking was wrong.

Search.evaluate takes a start, a time and an ordering and returns the real arrival. Elapsed is arrival
minus departure. No deadline, no alignment, no bound: the number is the thing being asked about.

It is also 0.2 s against the backward chain's 60 s, because each layer stops early instead of scanning the
full span. Two orders of magnitude cheaper AND exact, which is the whole afternoon's lesson arriving one
more time: the proxy was slower than the thing it stood in for.

Falsification, before running, and there are two of them because one control can pass a harness that is
wrong in a way the control does not exercise. Rotation 0 is the control's own ordering from Huntington at
00:54 and must come back at 237.34 h. Route X's ordering from Sheridan WY at 22:00 MT must come back at
238.32 h; it ends on a border walk-in, which the control never does. If either misses, the harness is wrong
and no other row counts. The second gate used to be the 238.8 record and used to read its ordering from
../out/time_238.pkl under an os.path.exists guard. Nothing in this repo writes that file and out/ is
gitignored, so on every fresh checkout the gate skipped without a word and the run reported one gate as two.

    python3 forward_shapes.py                  every rotation, swept over a day of departures
    python3 forward_shapes.py --rot 0          just the control, to check the harness
"""
import argparse, os, pickle
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR
from pick import choose, gate

_W = {}          # worker state, inherited by fork rather than pickled (pair_tables._W does the same)


def _one(job):
    """(rotation, start stop, departure) -> elapsed hours, or None if the order cannot be completed"""
    k, s0, t0 = job
    R, orders = _W['R'], _W['orders']
    # R.finish, not Search(...).evaluate: the same compiled scan layer by layer, without rebuilding the
    # legs, and without constructing a Search, whose __init__ runs build_gateways (a Python pass over every
    # state's stops) on every call. That constructor was most of phase 1's cost. The rotation-0 gate runs
    # through this function, so if the two ever disagree the run stops before printing a row.
    try:
        fin = R.finish(s0, t0, orders[k])
    except Exception:
        return k, s0, t0, None
    if fin is None or not np.isfinite(fin): return k, s0, t0, None
    return k, s0, t0, (fin - t0) / 3600.0


def main():
    """Parse CLI options, check reference routes, and compare rotated state orders."""
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-09-24T00:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--route', default='../out/res_starttest.pkl')
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--rot', type=int, default=None, help='just this rotation')
    ap.add_argument('--start-stop', default=None, help='force the start stop by exact name, for checking '
                    'the harness against a known answer')
    ap.add_argument('--starts', default=None, help='optional backward rotation table to read a start stop '
                    'per shape from, skipping phase 1. Off by default and it should usually stay off: the '
                    'only such table produced so far was biased by its fixed wall-clock deadline (46 of 48 '
                    'rotations IMPOSSIBLE for alignment rather than duration), and out/ is gitignored so it '
                    'never exists on a fresh checkout. Without it, every stop of each first state is '
                    'evaluated, which is what optimising the start per state means.')
    ap.add_argument('--hours', type=float, default=24, help='sweep departures over this many hours')
    ap.add_argument('--step', type=float, default=2, help='hours between swept departures')
    ap.add_argument('--workers', type=int, default=0)
    ap.add_argument('--no-gate', action='store_true', help='skip the harness checks')
    ap.add_argument('--reverse', action='store_true', help='rotate the REVERSED cycle instead. Rotations of one '
                    'orientation are only half the cyclic reorders of the sequence, and the other half '
                    'includes the record\'s own White River Junction to Huntington direction.')
    ap.add_argument('--record', default=None, help='an extra shape ordering to replay as a further gate, as '
                    '{"order": [...]} in a pickle, with --record-el and --record-start. Optional, and a path '
                    'that does not exist is now a hard failure rather than a skip: this used to default to '
                    '../out/time_238.pkl, which NOTHING IN THIS REPO HAS EVER WRITTEN. out/ is gitignored, '
                    'the file only existed on one machine, and the guard was `if ... os.path.exists(...)`, '
                    'so on every fresh checkout the second gate silently did not run and the harness '
                    'reported one gate as two.')
    ap.add_argument('--record-start', default='White River Junction Bus Station')
    ap.add_argument('--record-at', default='2026-09-24T04:20')
    ap.add_argument('--record-tz', default='America/New_York')
    ap.add_argument('--record-el', type=float, default=239.08, help='hours --record must come back at')
    ap.add_argument('--checkpoint', default='../out/fs_phase1_{tag}.pkl', help='phase 1 results are saved here '
                    'as they arrive and reused on restart, so a kill costs minutes rather than the whole phase')
    a = ap.parse_args()

    tz = ZoneInfo(a.tz)
    t_base = datetime.fromisoformat(a.at).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    ab = lambda x: ABBR[R.state_names[x]]

    # the order the route actually enters states in, connection by connection in departure order. Same
    # derivation as shape_probe: sorted() of a covered-set breaks ties by state index, which asked for
    # Nebraska before Iowa on a train that passes them the other way and called the 237 route impossible.
    import time_search as ts
    from time_search import Search
    d_ = pickle.load(open(a.route, 'rb'))
    st0_ = R.stop_name.index(d_['start'])
    S_ = Search(R, st0_, d_['t0'], [], 1)
    ts.bind(R, st0_, d_['t0'], S_)
    _f, legs_ = S_.evaluate(d_['order'])
    from collections import defaultdict
    tc_ = defaultdict(list)
    for k_ in range(len(R.dep)): tc_[R.ctrip[k_]].append(k_)
    for v_ in tc_.values(): v_.sort(key=lambda k: R.dep[k])
    full = []

    def add_(y_):
        """Append a nonnegative state index to full only on its first visit."""
        if y_ is not None and y_ >= 0 and y_ not in full: full.append(int(y_))

    add_(int(R.state[st0_]))
    for l_ in legs_:
        if l_[0] == 'ride':
            _, trip_, bs_, bt_, al_, at_ = l_
            add_(int(R.state[bs_]))
            for k_ in tc_.get(trip_, ()):
                if bt_ <= R.dep[k_] and R.arr[k_] <= at_:
                    add_(int(R.state[int(R.cfrom[k_])])); add_(int(R.state[int(R.cto[k_])]))
            add_(int(R.state[al_]))
        elif l_[0] == 'walk':
            add_(int(R.state[int(l_[2])]))
    n_ = len(full)
    if a.reverse: full = full[::-1]
    print(f'control order{" (REVERSED)" if a.reverse else ""}: {n_} states, {" ".join(ab(y) for y in full)}\n')

    orders = {k: full[k:] + full[:k] for k in range(n_)}

    # Best start stop per rotation, from the backward table when it exists. Exact within a shape.
    best_stop = {}; multi = {}
    if a.starts and os.path.exists(a.starts):
        for line in open(a.starts):
            p = line.split()
            if len(p) >= 6 and p[0].isdigit() and p[-1] != 'IMPOSSIBLE':
                try:
                    k = int(p[0]); nm = line.split(' h  ', 1)[1].strip()
                except (ValueError, IndexError):
                    continue
                hit = [i for i, s in enumerate(R.stop_name) if s[:40] == nm]
                if hit: best_stop[k] = hit[0]
        print(f'read {len(best_stop)} start stops from {a.starts}')
    for k in range(n_):
        if k not in best_stop:
            # Every stop of the first state, not one of them. The first version took cands[0], the lowest
            # index, which is an arbitrary choice dressed as a default: it started rotation 0 from
            # Charleston instead of Huntington and reported the control at 285.34 h. A silent pick of one
            # element from a set is the same mistake as argmin over a state's stops, and it was written in
            # a file whose docstring complains about proxies.
            cands = [s for s in range(R.N) if R.state[s] == orders[k][0]]
            if cands: multi[k] = cands

    ks = [a.rot] if a.rot is not None else list(range(n_))
    times = [t_base + h * 3600 for h in np.arange(0, a.hours, a.step)]
    if a.start_stop:
        hit = [i for i, n in enumerate(R.stop_name) if n == a.start_stop]
        if not hit: raise SystemExit(f'no stop named exactly {a.start_stop!r}')
        for k in ks: best_stop[k] = hit[0]; multi.pop(k, None)
        print(f'forced start: {a.start_stop!r} ({len(hit)} exact matches, using {hit[0]})')
    _W.update(R=R, orders=orders)
    # The known answer before any row: rotation 0 is the control's own ordering, and from Huntington at 00:54
    # it must come back at 237.34 h. Checked only when the inputs are the control's, since any other route or
    # clock has no known answer to check against.
    control_inputs = a.route == ap.get_default('route') and a.at == ap.get_default('at')
    if not a.no_gate and control_inputs and not a.reverse:
        hun = [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']
        gate('rotation 0 from Huntington 00:54',
             lambda: min(el for el in (_one((0, h, t_base))[3] for h in hun) if el is not None),
             237.34, 0.01)
    def replay(order, start_name, t_start, RR=None):
        """best elapsed hours over every stop of that exact name, or None if none completes the order"""
        RR = RR or R; best = None
        for w in [i for i, n in enumerate(RR.stop_name) if n == start_name]:
            Sr = Search(RR, w, t_start, [], 1)
            ts.bind(RR, w, t_start, Sr)
            f_, lg_ = Sr.evaluate(order)
            if np.isfinite(f_) and Sr.all_states(lg_):
                el_ = (f_ - t_start) / 3600
                best = el_ if best is None else min(best, el_)
        return best

    # Second gate, and one that has to disagree with the first: one control can pass a harness that is wrong
    # in a way the control does not exercise, two that disagree cannot. Route X qualifies and the record does
    # not, for a reason worth stating rather than discovering again. X starts in Wyoming and ends on the
    # Mississippi line at Memphis, so it exercises a ride-licensed border walk-in at the FINISH, which is the
    # exact path 78ada1b fixed in csa.c and which the control, ending at Hanover, never touches. The record
    # shares both of the control's endpoints and is its corridor reversed, so it was always the weaker of the
    # two even when its file existed.
    #
    # And X's ordering is IMPORTED, not unpickled. The record gate read ../out/time_238.pkl, which nothing in
    # this repo has ever written and which out/ ignores, under an os.path.exists guard, so it skipped in
    # silence on every fresh checkout. A gate whose input can go missing is a gate that can stop existing
    # without anything saying so; a gate whose input is a committed literal cannot.
    # Given but missing is a hard failure whatever --no-gate says: a typo should stop the run, not wait for a
    # run with the gates on to be noticed. --no-gate decides only whether the orders get replayed.
    if a.record and not os.path.exists(a.record):
        raise SystemExit(f'--record {a.record} does not exist. Nothing in this repo writes it and out/ '
                         f'is gitignored; pass a path that exists or leave --record off.')
    if not a.no_gate:
        from x_forward import ORDER as X_ORDER
        from datetime import date as _date
        from time_router import SCAN_SLACK
        inv = {v: k for k, v in ABBR.items()}
        t_x = datetime(2026, 9, 26, 22, 0, tzinfo=ZoneInfo('America/Denver')).timestamp()
        # X's departure is fixed, so a router loaded for other dates (--at, --days) may not hold the Sep 26 bus
        # or the ten days after it, and the gate would fail on the calendar rather than the harness. It then
        # runs on the router it was measured on. A router's days run d0 .. d0 + days - 1.
        d0 = datetime.fromisoformat(a.at).date()
        x_end = datetime.fromtimestamp(t_x + 238.32 * 3600 + SCAN_SLACK, ZoneInfo('UTC')).date() + timedelta(days=1)
        RX = R if d0 <= _date(2026, 9, 26) and d0 + timedelta(days=a.days) > x_end else cached_router(_date(2026, 9, 24), 20)
        if RX is not R: print(f'route X gate: this router ({d0}, {a.days} days) does not cover Sep 26 to {x_end}; '
                              f'replaying on the Sep 24, 20-day reference router', flush=True)
        x_order = [RX.state_names.index(inv[s]) for s in X_ORDER]
        gate('route X from Sheridan WY 22:00 MT',
             lambda: replay(x_order, 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)', t_x, RX), 238.32, 0.01)
        del RX
    # An extra shape, if one is supplied.
    if not a.no_gate and a.record:
        rec = pickle.load(open(a.record, 'rb'))['order']
        t_rec = datetime.fromisoformat(a.record_at).replace(tzinfo=ZoneInfo(a.record_tz)).timestamp()
        gate(f'record order from {a.record_start} {a.record_at}',
             lambda: replay(rec, a.record_start, t_rec), a.record_el, 0.01)
    import multiprocessing as mp
    nw = a.workers or max(1, (os.cpu_count() or 2) - 1)

    # Two phases, because every stop of every first state across the whole departure sweep is 237000
    # evaluations. Phase 1 finds each shape's best start stop at ONE departure; phase 2 sweeps departures
    # for that stop. Stated as the limitation it is: the stop is chosen at one departure time, so a shape
    # whose best stop changes with the hour is measured from the wrong one. That is a real gap and it is
    # cheaper to name than to close, at 12x the cost.
    with mp.get_context('fork').Pool(nw) as pool:
        need = [(k, s0, t_base) for k in ks for s0 in multi.get(k, []) if k not in best_stop]
        if need:
            # Checkpointed, keyed on everything that decides a result, because the first full run died 31
            # minutes in with nothing saved and pool.map had printed nothing to say how far it had got.
            tag = f'{"rev" if a.reverse else "fwd"}'
            ck_path = a.checkpoint.format(tag=tag)
            ck_key = (a.route, a.at, a.tz, a.days, a.reverse, tuple(full))
            done = {}
            if os.path.exists(ck_path):
                ck = pickle.load(open(ck_path, 'rb'))
                if ck.get('key') == ck_key: done = ck['done']
                else: print(f'checkpoint {ck_path} is for different inputs; ignoring it', flush=True)
            todo = [j for j in need if (j[0], j[1]) not in done]
            print(f'phase 1: {len(need)} start stops across {len(set(k for k, _, _ in need))} rotations, '
                  f'at one departure, {nw} workers; {len(done)} from checkpoint, {len(todo)} to go', flush=True)
            import time as _time
            t_p1 = _time.time(); n_new = 0
            for k, s0, _t, el in pool.imap_unordered(_one, todo, chunksize=16):
                done[(k, s0)] = el; n_new += 1
                if n_new % 500 == 0 or n_new == len(todo):
                    tmp = ck_path + '.tmp'
                    pickle.dump(dict(key=ck_key, done=done), open(tmp, 'wb')); os.replace(tmp, ck_path)
                    rate = n_new / max(_time.time() - t_p1, 1e-9)
                    print(f'  phase 1: {len(done)}/{len(need)} ({rate:.1f}/s, '
                          f'{(len(todo) - n_new) / max(rate, 1e-9) / 60:.0f} min left)', flush=True)
            got = defaultdict(list)
            for (k, s0), el in done.items():
                if el is not None: got[k].append((el, s0))
            for k in sorted(got):
                best_stop[k] = choose(got[k], key=lambda e: e[0], label=f'  rot {k:2d} start',
                                      show=lambda e: f'{R.stop_name[e[1]][:30]} {e[0]:.2f} h')[1]
            print(f'phase 1 done: {len(got)} rotations have a start that completes at all', flush=True)
        jobs = [(k, best_stop[k], t) for k in ks if k in best_stop for t in times]
        print(f'phase 2: {len(jobs)} evaluations, {len(ks)} rotations x {len(times)} departures\n',
              flush=True)
        res = pool.map(_one, jobs)

    by_k = defaultdict(list)
    for k, s0, t0, el in res:
        if el is not None: by_k[k].append((el, s0, t0))
    rows = []
    for k in ks:
        if by_k.get(k): rows.append((min(by_k[k]), k))
    rows.sort()
    print(f'  {"rot":>3s} {"first":5s} {"last":5s} {"elapsed":>9s}  {"departing":>16s}  start stop')
    for (el, s0, t0), k in rows:
        flag = '   BEATS THE CONTROL' if el < 237.34 else ''
        print(f'  {k:3d} {ab(orders[k][0]):5s} {ab(orders[k][-1]):5s} {el:8.2f} h  '
              f'{datetime.fromtimestamp(t0, tz).strftime("%a %d %b %H:%M"):>16s}  '
              f'{R.stop_name[s0][:38]}{flag}', flush=True)
    dead = [k for k in ks if not by_k.get(k)]
    if dead: print(f'\n  {len(dead)} rotations completed no order at any swept departure: '
                   + ' '.join(f'{k}({ab(orders[k][0])})' for k in dead))
    print('\nElapsed is arrival minus departure, from the router, with no deadline involved. Comparable '
          'across shapes, unlike the backward table. The start stop per rotation comes from the backward '
          'chain and the departure from the sweep, so a shape could do better with a start stop or a '
          'departure minute neither of those offered: these are achieved times, not optima.')


if __name__ == '__main__':
    main()
