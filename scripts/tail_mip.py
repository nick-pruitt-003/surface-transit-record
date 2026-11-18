"""Exact tail solve with OR-Tools (Nov 18 2026): from one search node (a stop, a clock, the states still owed), the
earliest a route can collect every owed state and stand in the end state, or a proof that none can by the deadline.
docs/proof_attempt.md ends on the missing piece: a bound over large owed sets that sees timetable waiting. A MIP over
the time-expanded network is that bound, solved exactly instead of estimated. Leaf script: nothing imports it.

The model is a RELAXATION of the router's rules, never stricter, so "infeasible" and "optimal = T" are proofs about
every real route, and any route it returns must still pass verify_path.py before it is believed. Where it is looser:
  - the start can board at its own clock (no 5 min transfer on the first boarding), whatever trip it arrived on;
  - every stop a used connection touches collects its state (board, alight and ride-through alike), and so does every
    stop a walk ends at, border walk-in point or not;
  - walking is allowed only on arrival (a walk taken later is the same walk followed by a wait at the far end), one
    footpath, or one footpath to a walk-in point plus one onward footpath from it (CHAIN_WALKIN's chains are already
    single footpaths, so this covers them and more).
Where it is exact: every connection, its times, staying aboard a trip, 5 min between vehicles, footpath times.

The network: a node per connection (riding it), per arrival, and a timeline per stop of the moments you could be
ready to board there. Arcs: board, stay aboard to the trip's next connection, alight, walk (arrival -> a timeline
moment at the far stop, transfer included), wait (along a timeline), finish (arrival or walk end in the end state).
One unit of flow from the start to the finish; per owed state, at least one used arc touches it; minimise the finish.
Time only runs forward, so there are no cycles and no subtour constraints.

Pruning, permissive only: a connection is kept when its departure is no earlier than the start can first reach its
stop (one forward CSA scan) and its arrival is no later than the latest you can be at its stop and still finish
(the same L_end reverse scan ride_search's deadline tables use, guard=False). Then nodes off every start->finish path
are dropped by graph reachability.

usage (from scripts/, on a machine that holds the router; ~40 GB was what proof runs used, the model is smaller):
  python3 tail_mip.py --stop "Jacksonville" --at 2026-11-19T08:00 --tz America/New_York --owes GA,SC,... \
      --end MN --by 2026-11-22T15:10 --by-tz America/Denver [--lp] [--time 1800] [--workers 8]
  python3 tail_mip.py --selftest      # synthetic networks, no router, seconds
"""
import argparse, sys, time
from collections import defaultdict
import numpy as np

MIN_TRANSFER = 300


# ---------------------------------------------------------------- the network

class Net:
    """dep, arr, cfrom, cto: arrays over connections; ctrip: trip key per connection; foot: stop -> [(stop, s)];
    state: per stop (-1 none); virtual(j): True for a walk-in point."""
    def __init__(self, dep, arr, cfrom, cto, ctrip, foot, state, virtual=lambda j: False, name=None):
        self.dep, self.arr = np.asarray(dep, float), np.asarray(arr, float)
        self.cfrom, self.cto = np.asarray(cfrom, np.int64), np.asarray(cto, np.int64)
        self.ctrip, self.foot, self.state, self.virtual = list(ctrip), foot, np.asarray(state), virtual
        self.name = name or (lambda s: str(s))


def walks_from(net, b):
    """(stop reached, seconds, states touched) for every walk the model allows on arrival at b, b itself included."""
    out = [(b, 0.0, ())]
    for j, w in net.foot.get(b, ()):
        out.append((j, float(w), (int(net.state[j]),)))
        if net.virtual(j):
            for j2, w2 in net.foot.get(j, ()):
                if j2 != j: out.append((j2, float(w + w2), (int(net.state[j]), int(net.state[j2]))))
    return out


def build(net, s0, t0, D, owed, end, ea=None, lend=None, mt=MIN_TRANSFER, log=print):
    """Arc list of the time-expanded network. Returns dict with arcs (tail, head, kind, cost, states), node count,
    source, sink, and labels for reading a solution back."""
    owed = set(int(y) for y in owed)
    nC = len(net.dep)
    keep = (net.dep >= t0) & (net.arr <= D)
    if ea is not None: keep &= net.dep >= ea[net.cfrom]
    if lend is not None: keep &= net.arr <= lend[net.cto]
    K = np.where(keep)[0]
    log(f'  connections kept {len(K)} of {nC}')
    nodes = {}                       # key -> id
    def node(key):
        v = nodes.get(key)
        if v is None: v = nodes[key] = len(nodes)
        return v
    arcs = []                        # (u, v, kind, cost, states, label)
    src, snk = node(('src',)), node(('snk',))
    timeline = defaultdict(set)      # stop -> moments ready to board
    pending = []                     # (u, stop, moment, states, label): walk arcs into timelines, added after
    ride = {}
    for k in K: ride[int(k)] = node(('c', int(k)))
    # boarding: from the stop's timeline at the departure minute
    for k in K:
        k = int(k); a = int(net.cfrom[k]); timeline[a].add(net.dep[k])
    # stay aboard: consecutive kept connections of a trip
    by_trip = defaultdict(list)
    for k in K: by_trip[net.ctrip[k]].append(int(k))
    for tr, ks in by_trip.items():
        ks.sort(key=lambda k: net.dep[k])
        for k, k2 in zip(ks, ks[1:]):
            if net.cto[k] == net.cfrom[k2] and net.arr[k] <= net.dep[k2]:
                arcs.append((ride[k], ride[k2], 'stay', 0.0, (), None))
    # The states a connection touches are credited on the arcs INTO its ride node (board, stay), so a ride counts
    # however it is left, alighting or staying aboard.
    cstates = {}
    for k in K:
        k = int(k)
        cstates[k] = tuple({int(net.state[net.cfrom[k]]), int(net.state[net.cto[k]])} & owed)
        arcs.append((ride[k], node(('arr', k)), 'alight', 0.0, (), k))
    # walks on arrival
    def end_reached(j): return int(net.state[j]) == end
    for k in K:
        k = int(k); A = nodes[('arr', k)]; b = int(net.cto[k]); t = net.arr[k]
        for j, w, sts in walks_from(net, b):
            sts = tuple(set(sts) & owed)
            if end_reached(j) and t + w <= D:
                arcs.append((A, snk, 'finish', t + w, sts, (k, j)))
            m = t + w + mt
            if j in timeline: pending.append((A, j, m, sts, (k, j)))
    # the start: board at its own clock, walks too (permissive: no transfer)
    for j, w, sts in walks_from(net, s0):
        sts = tuple(set(sts) & owed)
        if end_reached(j) and t0 + w <= D: arcs.append((src, snk, 'finish', t0 + w, sts, ('start', j)))
        if j in timeline: pending.append((src, j, t0 + w, sts, ('start', j)))
    # timelines: insert walk moments, wait arcs, boarding arcs
    tl_node = {}; last = {i: max(ms) for i, ms in timeline.items()}
    pending = [p for p in pending if p[2] <= last[p[1]]]     # a moment after the stop's last departure leads nowhere
    for u, j, m, sts, lab in pending: timeline[j].add(m)
    for i, ms in timeline.items():
        ms = sorted(ms); tl_node[i] = (ms, [node(('tl', i, m)) for m in ms])
        for p, q in zip(tl_node[i][1], tl_node[i][1][1:]): arcs.append((p, q, 'wait', 0.0, (), None))
    for u, j, m, sts, lab in pending:
        ms, ids = tl_node[j]
        x = int(np.searchsorted(ms, m))
        if x < len(ms): arcs.append((u, ids[x], 'walk', 0.0, sts, lab))
    for k in K:
        k = int(k); ms, ids = tl_node[int(net.cfrom[k])]
        x = int(np.searchsorted(ms, net.dep[k]))
        arcs.append((ids[x], ride[k], 'board', 0.0, cstates[k], k))
    # stay arcs carry the states of the connection they enter (so riding through a stop counts once you are aboard)
    rid = {v: k for k, v in ride.items()}
    arcs = [(u, v, kind, c, cstates[rid[v]] if kind == 'stay' else st, lab) for (u, v, kind, c, st, lab) in arcs]
    return prune(dict(arcs=arcs, n=len(nodes), src=src, snk=snk, ride=ride, owed=owed), log)


def prune(M, log):
    """Drop arcs not on any source -> sink path (two BFS over the arc list)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order
    arcs, n = M['arcs'], M['n']
    u = np.array([a[0] for a in arcs], np.int64); v = np.array([a[1] for a in arcs], np.int64)
    G = csr_matrix((np.ones(len(arcs)), (u, v)), shape=(n, n))
    fw = np.zeros(n, bool); fw[breadth_first_order(G, M['src'], directed=True, return_predecessors=False)] = True
    bw = np.zeros(n, bool); bw[breadth_first_order(G.T.tocsr(), M['snk'], directed=True, return_predecessors=False)] = True
    live = fw & bw
    ok = live[u] & live[v]
    M['arcs'] = [a for a, o in zip(arcs, ok) if o]
    M['live'] = live
    log(f'  network: {int(live.sum())} live nodes of {n}, {len(M["arcs"])} arcs of {len(arcs)}')
    return M


# ---------------------------------------------------------------- the solvers

def missing_states(M):
    have = set()
    for a in M['arcs']: have.update(a[4])
    return sorted(M['owed'] - have)


def flow_constraints(M, add_var, add_eq, add_ge):
    arcs, n = M['arcs'], M['n']
    x = [add_var(i) for i in range(len(arcs))]
    out_, in_ = defaultdict(list), defaultdict(list)
    for i, (u, v, *_r) in enumerate(arcs): out_[u].append(i); in_[v].append(i)
    for w in set(out_) | set(in_):
        rhs = 1 if w == M['src'] else (-1 if w == M['snk'] else 0)
        add_eq(out_[w], in_[w], rhs)
    cover = defaultdict(list)
    for i, a in enumerate(arcs):
        for y in a[4]: cover[y].append(i)
    for y in M['owed']: add_ge(cover[y])
    return x


def solve_lp(M, log=print):
    """LP relaxation with GLOP: infeasible here is already a proof; otherwise its value is a lower bound."""
    from ortools.linear_solver import pywraplp
    s = pywraplp.Solver.CreateSolver('GLOP')
    xs = []
    def add_var(i): v = s.NumVar(0, 1, ''); xs.append(v); return v
    def add_eq(o, i_, rhs): s.Add(sum(xs[a] for a in o) - sum(xs[a] for a in i_) == rhs)
    def add_ge(c): s.Add(sum(xs[a] for a in c) >= 1)
    flow_constraints(M, add_var, add_eq, add_ge)
    s.Minimize(sum(xs[i] * a[3] for i, a in enumerate(M['arcs']) if a[2] == 'finish'))
    t = time.time(); r = s.Solve()
    name = {pywraplp.Solver.OPTIMAL: 'OPTIMAL', pywraplp.Solver.INFEASIBLE: 'INFEASIBLE'}.get(r, str(r))
    log(f'  LP {name} in {time.time() - t:.1f} s' + (f', bound {s.Objective().Value():.0f}' if r == 0 else ''))
    return name, (s.Objective().Value() if r == 0 else None)


def solve_cp(M, time_limit=600, workers=8, hint=None, log=print):
    """Exact with CP-SAT. Returns (status, finish seconds or None, bound, chosen arc indices)."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel(); xs = []
    def add_var(i): v = m.NewBoolVar(''); xs.append(v); return v
    def add_eq(o, i_, rhs): m.Add(sum(xs[a] for a in o) - sum(xs[a] for a in i_) == rhs)
    def add_ge(c): m.AddBoolOr([xs[a] for a in c]) if c else m.AddBoolOr([])
    flow_constraints(M, add_var, add_eq, add_ge)
    fin = [(i, a[3]) for i, a in enumerate(M['arcs']) if a[2] == 'finish']
    base = min(c for _, c in fin) if fin else 0
    m.Minimize(sum(xs[i] * int(round(c - base)) for i, c in fin))
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = time_limit; s.parameters.num_workers = workers
    t = time.time(); r = s.Solve(m); name = s.StatusName(r)
    log(f'  CP-SAT {name} in {time.time() - t:.1f} s')
    if r in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = [i for i in range(len(xs)) if s.Value(xs[i])]
        return name, s.ObjectiveValue() + base, s.BestObjectiveBound() + base, chosen
    return name, None, (s.BestObjectiveBound() + base if r != cp_model.INFEASIBLE else None), []


def read_path(M, chosen):
    """Arcs of the solution in travel order (follow the unit of flow from the source)."""
    arcs = M['arcs']; nxt = defaultdict(list)
    for i in chosen: nxt[arcs[i][0]].append(i)
    out, u = [], M['src']
    while u != M['snk'] and nxt[u]:
        i = nxt[u].pop(); out.append(arcs[i]); u = arcs[i][1]
    return out


# ---------------------------------------------------------------- self test (synthetic, no router)

def _bruteforce(net, s0, t0, D, owed, end, mt=MIN_TRANSFER):
    """Enumerate every route on a tiny network under the model's own rules (DFS over boardings): the earliest finish."""
    best = [None]
    trips = defaultdict(list)
    for k in range(len(net.dep)): trips[net.ctrip[k]].append(k)
    for v in trips.values(): v.sort(key=lambda k: net.dep[k])
    def arrive(b, t, got, first):
        for j, w, sts in walks_from(net, b):
            g2 = got | (set(sts) & owed); tt = t + w
            if int(net.state[j]) == end and tt <= D and owed <= g2:
                if best[0] is None or tt < best[0]: best[0] = tt
            ready = tt + (0 if first else mt)
            for tr, ks in trips.items():
                for x, k in enumerate(ks):
                    if net.cfrom[k] != j or net.dep[k] < ready or net.arr[k] > D: continue
                    g3 = set(g2)
                    for k2 in ks[x:]:
                        g3 |= {int(net.state[net.cfrom[k2]]), int(net.state[net.cto[k2]])} & owed
                        arrive(int(net.cto[k2]), net.arr[k2], frozenset(g3), False)
    arrive(s0, t0, frozenset(), True)
    return best[0]


def selftest():
    quiet = lambda *a, **k: None
    ok = True
    def check(name, got, want):
        nonlocal ok
        good = got == want; ok &= good
        print(f'  {"ok  " if good else "FAIL"} {name}: got {got}, want {want}')
    # 0 A(s0) state 0 -- trips -- 1 B state 1 -- 2 C state 2 (end 3 at D)
    # trip t1: A 0 -> B 100 -> C 200 ; trip t2: A 0 -> C 150 (skips B) ; trip t3: C 600 -> D 700 ; t4: C 900 -> D 950
    st = [0, 1, 2, 3]
    net = Net([0, 100, 0, 600, 900], [100, 200, 150, 700, 950], [0, 1, 0, 2, 2], [1, 2, 2, 3, 3],
              ['t1', 't1', 't2', 't3', 't4'], {}, st)
    def run(net, owed, D, s0=0, t0=0, end=3):
        M = build(net, s0, t0, D, owed, end, log=quiet)
        if missing_states(M): return None
        stt, f, b, ch = solve_cp(M, 30, 1, log=quiet)
        return f
    check('ride through B collects it', run(net, {1, 2}, 2000), 700)
    check('matches brute force', run(net, {1, 2}, 2000), _bruteforce(net, 0, 0, 2000, {1, 2}, 3))
    check('deadline under the optimum is infeasible', run(net, {1, 2}, 699), None)
    # transfer: alight at C at 200 and need 5 min: t3 at 600 is fine; make t3 leave 400 (> 200+300=500? no: 400 < 500)
    net2 = Net([0, 100, 400, 900], [100, 200, 450, 950], [0, 1, 2, 2], [1, 2, 3, 3], ['t1', 't1', 't3', 't4'], {}, st)
    check('5 min transfer enforced', run(net2, {1}, 2000), 950)
    check('transfer matches brute force', run(net2, {1}, 2000), _bruteforce(net2, 0, 0, 2000, {1}, 3))
    # walk-in: state 4 only reachable as a walk-in point 5 off stop 2 (C), 60 s each way; virtual
    foot = {2: [(5, 60)], 5: [(2, 60)]}
    # alight C 200, out and back 120 s, transfer 300: ready 620, so the 700 bus, not the 610 one
    net3 = Net([0, 100, 610, 700, 900], [100, 200, 650, 800, 950], [0, 1, 2, 2, 2], [1, 2, 3, 3, 3],
               ['t1', 't1', 't5', 't3', 't4'], foot, [0, 1, 2, 3, -1, 4], virtual=lambda j: j == 5)
    check('walk-in collects state, timed out and back', run(net3, {1, 4}, 2000), 800)
    check('without the walk-in the 610 is caught', run(net3, {1}, 2000), 650)
    check('walk-in matches brute force', run(net3, {1, 4}, 2000), _bruteforce(net3, 0, 0, 2000, {1, 4}, 3))
    # a state nothing reaches: model must report it missing (no solve)
    M = build(net, 0, 0, 2000, {1, 9}, 3, log=quiet)
    check('unreachable state reported', missing_states(M), [9])
    # random networks against brute force
    rng = np.random.default_rng(7); n_ok = 0; n = 40
    for trial in range(n):
        S = 7; states = list(range(S)); conns = []
        for tr in range(9):
            path = rng.choice(S, size=rng.integers(2, 4), replace=False); t = int(rng.integers(0, 2000))
            for a, b in zip(path, path[1:]):
                d = int(rng.integers(50, 400)); conns.append((t, t + d, int(a), int(b), f'r{tr}')); t += d + int(rng.integers(0, 60))
        foot = defaultdict(list)
        for _ in range(3):
            a, b = rng.choice(S, 2, replace=False); w = int(rng.integers(30, 400))
            foot[int(a)].append((int(b), w)); foot[int(b)].append((int(a), w))
        dep, arr, cf, ct, trp = zip(*conns)
        netr = Net(dep, arr, cf, ct, trp, dict(foot), states)
        owed = set(int(y) for y in rng.choice(range(1, S - 1), 2, replace=False))
        want = _bruteforce(netr, 0, 0, 6000, owed, S - 1)
        got = run(netr, owed, 6000, end=S - 1)
        good = (got is None and want is None) or (got is not None and want is not None and abs(got - want) < 1e-6)
        M = build(netr, 0, 0, 6000, owed, S - 1, log=quiet)
        if not missing_states(M):
            lp_name, lp_val = solve_lp(M, log=quiet)
            if want is not None and (lp_val is None or lp_val > want + 1e-6): good = False   # a bound above the optimum
        if good: n_ok += 1
        else: print(f'  FAIL random {trial}: got {got}, want {want}')
    check(f'random networks agree with brute force', n_ok, n)
    print('selftest', 'PASSED' if ok else 'FAILED')
    return ok


# ---------------------------------------------------------------- the real run

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--stop'); ap.add_argument('--at'); ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--owes', help='comma list of state codes still owed (the end state is implied)')
    ap.add_argument('--end', default='MN'); ap.add_argument('--by'); ap.add_argument('--by-tz', default='America/Denver')
    ap.add_argument('--d0', default='2026-11-09'); ap.add_argument('--days', type=int, default=22)
    ap.add_argument('--lp', action='store_true', help='LP relaxation only (a bound, or infeasible = proof)')
    ap.add_argument('--time', type=float, default=1800); ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from time_router import cached_router, N_STATES, MIN_TRANSFER as MT
    from common import ABBR
    import backward as B
    R = cached_router(date.fromisoformat(a.d0), a.days)
    inv = {v: k for k, v in ABBR.items()}; code = lambda c: R.state_names.index(inv[c])
    end = code(a.end); owed = {code(c) for c in a.owes.split(',') if c and c != a.end}
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
    D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.by_tz)).timestamp()
    if a.stop.startswith('#'): s0s = [int(a.stop[1:])]          # an exact stop index, as the error below lists them
    else: s0s = [i for i in R.stops_matching(a.stop) if R.stop_name[i].lower() == a.stop.lower()] or R.stops_matching(a.stop)
    if len(s0s) != 1:
        sys.exit(f'--stop matches {len(s0s)} stops; pass one as #index:\n' +
                 '\n'.join(f'  #{i}  {R.stop_name[i]}  {R.abbr[i]}  {R.stop_ids[i]}' for i in s0s[:20]))
    s0 = s0s[0]
    print(f'from {R.stop_name[s0]} at {R.fmt_time(t0, s0)}, owes {len(owed)}: {a.owes}; end {a.end} by '
          f'{R.fmt_time(D, s0)} ({(D - t0) / 3600:.2f} h)', flush=True)
    t = time.time()
    _, _, ea = R.scan({s0: (t0, None)}, set())
    F = B.RevFast(R)
    lat, ok_, k0, k1 = F.layer({int(s): D for s in np.where(R.state == end)[0]}, False, t0, None)
    eff, _ = F.through(ok_, k0, k1, np.ones(R.N, bool)); lend = np.maximum(lat, eff)
    print(f'  forward and reverse scans {time.time() - t:.0f} s', flush=True)
    net = Net(R.dep, R.arr, R.cfrom, R.cto, R.ctrip, R.foot, R.state, virtual=lambda j: j >= R.first_virtual,
              name=lambda s: R.stop_name[s])
    t = time.time(); M = build(net, s0, t0, D, owed, end, ea=ea, lend=lend, mt=MT)
    print(f'  built in {time.time() - t:.0f} s', flush=True)
    miss = missing_states(M)
    if miss:
        print('PROVED DEAD: no arc on any start->finish path touches', ','.join(ABBR[R.state_names[y]] for y in miss)); return
    if a.lp:
        name, val = solve_lp(M)
        if name == 'INFEASIBLE': print('PROVED DEAD by the LP relaxation')
        elif val is not None: print(f'LP bound: finish no earlier than {R.fmt_time(val, s0)} ({(val - t0) / 3600:.2f} h)')
        return
    name, f, bnd, chosen = solve_cp(M, a.time, a.workers)
    if name == 'INFEASIBLE': print('PROVED DEAD: no route collects the owed states and finishes by the deadline'); return
    if f is None: print(f'UNKNOWN after {a.time:.0f} s' + (f', bound {(bnd - t0) / 3600:.2f} h' if bnd else '')); return
    print(f'{name}: finish {R.fmt_time(f, s0)} ({(f - t0) / 3600:.2f} h), bound {(bnd - t0) / 3600:.2f} h')
    for u, v, kind, c, st, lab in read_path(M, chosen):
        if kind in ('board', 'walk', 'finish'):
            print(f'    {kind:6s} {lab}  {",".join(ABBR[R.state_names[y]] for y in st)}')
    print('  check any route found with verify_path.py before believing it')


if __name__ == '__main__':
    main()
