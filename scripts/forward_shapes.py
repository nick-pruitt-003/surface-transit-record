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

Falsification, before running: rotation 0 is the control's own ordering from Huntington at 00:54 and must
come back at 237.34 h. If it does not, the harness is wrong and no other row counts.

    python3 forward_shapes.py                  every rotation, swept over a day of departures
    python3 forward_shapes.py --rot 0          just the control, to check the harness
"""
import argparse, os, pickle
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR

_W = {}          # worker state, inherited by fork rather than pickled (pair_tables._W does the same)


def _one(job):
    """(rotation, start stop, departure) -> elapsed hours, or None if the order cannot be completed"""
    k, s0, t0 = job
    R, orders = _W['R'], _W['orders']
    import time_search as ts
    from time_search import Search
    S = Search(R, s0, t0, [], 1)
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, s0, t0, S, None, None
    try:
        fin, _legs = S.evaluate(orders[k])
    except Exception:
        return k, s0, t0, None
    if fin is None or not np.isfinite(fin): return k, s0, t0, None
    return k, s0, t0, (fin - t0) / 3600.0


def main():
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
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0_, d_['t0'], S_, None, None
    _f, legs_ = S_.evaluate(d_['order'])
    from collections import defaultdict
    tc_ = defaultdict(list)
    for k_ in range(len(R.dep)): tc_[R.ctrip[k_]].append(k_)
    for v_ in tc_.values(): v_.sort(key=lambda k: R.dep[k])
    full = []

    def add_(y_):
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
    print(f'control order: {n_} states, {" ".join(ab(y) for y in full)}\n')

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
            print(f'phase 1: {len(need)} start stops across {len(set(k for k, _, _ in need))} rotations, '
                  f'at one departure, {nw} workers', flush=True)
            got = defaultdict(list)
            for k, s0, _t, el in pool.map(_one, need):
                if el is not None: got[k].append((el, s0))
            for k, v in got.items(): best_stop[k] = min(v)[1]
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
