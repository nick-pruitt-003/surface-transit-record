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
    def __init__(self, dep, arr, cfrom, cto, ctrip, foot, state, virtual=lambda j: False, name=None, city=None):
        self.city = None if city is None else np.asarray(city, bool)
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


STAY, ALIGHT, FINISH, HOP, WAIT, BOARD = range(6)
KIND = ('stay', 'alight', 'finish', 'hop', 'wait', 'board')


# ---------------------------------------------------------------- city hops (Nov 18)
#
# City transit is collapsed into hops. Intercity connections keep their ride and arrival nodes; everything a traveller
# can do between alighting an intercity vehicle (or starting) and boarding the next one, or finishing, is one hop arc
# from that arrival to a departure slot at an intercity stop, carrying the states it touched. The hop scan (hopscan.c,
# scan_py here) is exact: footpaths and walk-ins as the router allows them, every city connection to the deadline,
# 5 min between vehicles, staying aboard a trip, Pareto labels in (time, states), so a slower path over a state line
# is kept beside a faster one that stays in one state. With no city connections the scans are just the walks, and the
# model is the uncontracted one.

def scan_py(net, b, t, off, D, mt, conns, sbit, outp):
    """Reference for hopscan.c's hs_scan. b: an origin stop, or a list of them (a free start: every one at t, the
    labels merged). conns: (dep, arr, cf, ct, trip) arrays sorted by dep. Returns
    [(stop, time, mask, kind)], kind 0 by ride, 1 on foot, 2 the origin itself, 3 on foot from the origin."""
    AL, WL, BL, TM = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    out = []

    def lv_add(L, t_, m):
        for (u, v) in L:
            if u <= t_ and (m & ~v) == 0: return False
        L[:] = [(u, v) for (u, v) in L if not (t_ <= u and (v & ~m) == 0)] + [(t_, m)]
        return True

    def iv_add(L, m):
        for v in L:
            if (m & ~v) == 0: return False
        L[:] = [v for v in L if (v & ~m) != 0] + [m]
        return True

    def walk_arr(j, t_, m, rdy, kd):
        if not lv_add(WL[j], t_, m): return
        if outp[j]: out.append((j, t_, m, kd))
        lv_add(BL[j], t_ + rdy, m)

    def ride_arr(u, t_, m, origin):
        if not lv_add(AL[u], t_, m): return
        if outp[u]: out.append((u, t_, m, 2 if origin else 0))
        lv_add(BL[u], t_ + (off if origin else mt), m)
        for j, w in net.foot.get(u, ()):
            mm = m | int(sbit[j]); rdy, kd = (off, 3) if origin else (mt, 1)
            walk_arr(j, t_ + w, mm, rdy, kd)
            if net.virtual(j):
                for j2, w2 in net.foot.get(j, ()):
                    if j2 != j: walk_arr(j2, t_ + w + w2, mm | int(sbit[j2]), rdy, kd)

    for b_ in (b if isinstance(b, (list, tuple, np.ndarray)) else [b]): ride_arr(int(b_), t, int(sbit[int(b_)]), True)
    dep, arr, cf, ct, trip = conns
    for k in range(int(np.searchsorted(dep, t)), len(dep)):
        if dep[k] > D: break
        u, tr = int(cf[k]), int(trip[k])
        for (rt, m) in list(BL[u]):
            if rt <= dep[k]: iv_add(TM[tr], m)
        if not TM[tr]: continue
        v = int(ct[k])
        TM[tr][:] = [m | int(sbit[v]) for m in TM[tr]]
        if arr[k] > D: continue
        for m in list(TM[tr]): ride_arr(v, float(arr[k]), m, False)
    return out


_HS = [None]


def hopscan_c(N, NT):
    """hopscan.c through ctypes, compiled with gcc next to this file (name keyed on the source), or None."""
    import ctypes, hashlib, os, subprocess
    here = os.path.dirname(os.path.abspath(__file__)); src = os.path.join(here, 'hopscan.c')
    if not os.path.exists(src) or os.name == 'nt': return None
    h = hashlib.sha1(open(src, 'rb').read()).hexdigest()[:12]
    so = os.path.join(here, f'hopscan_{h}.so')
    if not os.path.exists(so):
        subprocess.run(['gcc', '-O3', '-shared', '-fPIC', src, '-o', so], check=True)
    lib = ctypes.CDLL(so)
    P = np.ctypeslib.ndpointer
    lib.hs_init.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.hs_scan.restype = ctypes.c_int
    lib.hs_scan.argtypes = [ctypes.c_int, P(np.int32), ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                            ctypes.c_int, P(np.float64), P(np.float64), P(np.int32), P(np.int32), P(np.int32),
                            P(np.int64), P(np.uint8), P(np.uint8), P(np.int32), P(np.int32), P(np.float64),
                            ctypes.c_int, P(np.int32), P(np.float64), P(np.int64), P(np.int32)]
    if lib.hs_init(int(N), int(max(NT, 1))) != 0: raise MemoryError('hs_init')
    return lib


def build(net, s0, t0, D, owed, end, ea=None, lend=None, mt=MIN_TRANSFER, log=print, city=None, use_c=None, check=0,
          end_stops=None):
    """The time-expanded network as numpy arc arrays. city: bool per connection (net.city by default); those
    connections are not nodes, they are inside the hops. use_c: hopscan.c (default when it builds); check=n compares
    the C scan against scan_py on the first n origins and stops on a difference.
    s0=None is a free start (Nov 18): any stop at any moment from t0 on, the first boarding without a transfer, a walk
    or walk-in before it counting, as on Moorhead's start. Then t0 is the start cutoff and the question is whether any
    route inside [t0, D] collects the owed states: the source gets every start's hops, one multi-source scan per metro
    (every stop of it at t0, labels merged: which stop a label started from does not matter to the flow).
    end_stops (Nov 19): finish only by standing at one of these stops by D (a segment's end, e.g. X's Harrisburg node),
    instead of anywhere in the end state; `end` is then unused."""
    owed = sorted(set(int(y) for y in owed))
    bit_of = {y: 1 << i for i, y in enumerate(owed)}
    st = np.asarray(net.state, np.int64)
    sbit = np.array([bit_of.get(int(x), 0) for x in st], np.int64)
    city = getattr(net, 'city', None) if city is None else city
    city = np.zeros(len(net.dep), bool) if city is None else np.asarray(city, bool)
    nC = len(net.dep)
    keep = (net.dep >= t0) & (net.arr <= D)
    if ea is not None: keep &= net.dep >= ea[net.cfrom]
    if lend is not None: keep &= net.arr <= lend[net.cto]
    K = np.where(keep & ~city)[0]; nK = len(K)
    KC = np.where(keep & city)[0]
    log(f'  connections kept {nK + len(KC)} of {nC}: intercity {nK}, city {len(KC)} (in hops)')
    dep, arr, cf, ct = net.dep[K], net.arr[K], net.cfrom[K], net.cto[K]
    RIDE0, ARR0 = 2, 2 + nK
    o = np.lexsort((dep, cf)); sk, mk = cf[o], dep[o]
    first = np.ones(nK, bool); first[1:] = (sk[1:] != sk[:-1]) | (mk[1:] != mk[:-1])
    tl_stop, tl_mom = sk[first], mk[first]; nS = len(tl_stop)
    TL0 = ARR0 + nK; n = TL0 + nS
    slot_of = np.empty(nK, np.int64); slot_of[o] = np.cumsum(first) - 1
    stops_tl, tl_lo = np.unique(tl_stop, return_index=True)
    tl_hi = np.append(tl_lo[1:], nS)
    rng_of = dict(zip(stops_tl.tolist(), zip(tl_lo.tolist(), tl_hi.tolist())))
    U, V, KD, C, MK, LK, LJ = [], [], [], [], [], [], []

    def add(u, v, kind, cost=0.0, mask=0, lk=-1, lj=-1):
        u = np.atleast_1d(np.asarray(u, np.int64)); m_ = len(u)
        f = lambda x, dt: np.array(np.broadcast_to(np.asarray(x, dt), (m_,)))
        U.append(u); V.append(f(v, np.int64)); KD.append(f(kind, np.int8)); C.append(f(cost, float))
        MK.append(f(mask, np.int64)); LK.append(f(lk, np.int64)); LJ.append(f(lj, np.int64))

    cmask = (sbit[cf] | sbit[ct]).astype(np.int64)
    idx = np.arange(nK)
    add(TL0 + slot_of, RIDE0 + idx, BOARD, 0.0, cmask, K)
    add(RIDE0 + idx, ARR0 + idx, ALIGHT, 0.0, 0, K)
    ws = np.where(tl_stop[1:] == tl_stop[:-1])[0]
    add(TL0 + ws, TL0 + ws + 1, WAIT)
    tmap = {}
    tid = np.fromiter((tmap.setdefault(net.ctrip[k], len(tmap)) for k in K.tolist()), np.int64, nK)
    ot = np.lexsort((dep, tid)); p, q = ot[:-1], ot[1:]
    sm = (tid[p] == tid[q]) & (ct[p] == cf[q]) & (arr[p] <= dep[q])
    add(RIDE0 + p[sm], RIDE0 + q[sm], STAY, 0.0, cmask[q[sm]])
    nfixed = sum(len(u) for u in U)
    # city connections for the scans, one metro at a time: a metro is a connected component of the kept city
    # connections and every footpath, and a scan can only ever move inside the component of its origin, so giving it
    # that component's connections alone changes nothing but the time it takes
    N = len(st)
    is_end = (st == end) if end_stops is None else np.isin(np.arange(N), np.asarray(list(end_stops), np.int64))
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    fa = [s_ for s_, fl in net.foot.items() for _ in fl]; fb = [j for s_, fl in net.foot.items() for j, _ in fl]
    ea_ = np.concatenate([net.cfrom[KC], np.asarray(fa, np.int64)]); eb_ = np.concatenate([net.cto[KC], np.asarray(fb, np.int64)])
    _, comp = connected_components(coo_matrix((np.ones(len(ea_), np.int8), (ea_, eb_)), shape=(N, N)), directed=False)
    ctm = {}
    ctrip_id = np.fromiter((ctm.setdefault(net.ctrip[k], len(ctm)) for k in KC.tolist()), np.int32, len(KC))
    kcomp = comp[net.cfrom[KC]]
    order = np.lexsort((net.dep[KC], kcomp))
    metro = {}
    if len(order):
        cs_ = kcomp[order]; cut = np.flatnonzero(np.diff(cs_)) + 1
        for g in np.split(np.arange(len(order)), cut):
            oc = order[g]; kk = KC[oc]
            metro[int(cs_[g[0]])] = (np.ascontiguousarray(net.dep[kk], np.float64), np.ascontiguousarray(net.arr[kk], np.float64),
                                     np.ascontiguousarray(net.cfrom[kk], np.int32), np.ascontiguousarray(net.cto[kk], np.int32),
                                     np.ascontiguousarray(ctrip_id[oc], np.int32))
    empty = (np.zeros(0), np.zeros(0), np.zeros(0, np.int32), np.zeros(0, np.int32), np.zeros(0, np.int32))
    big = sorted(((len(c[0]), m) for m, c in metro.items()), reverse=True)[:3]
    log(f'  {len(metro)} metros; largest {", ".join(str(x) for x, _ in big)} city connections')
    outp = np.zeros(N, np.uint8); outp[stops_tl] = 1; outp[is_end] = 1
    lib = None
    if use_c is not False:
        try: lib = hopscan_c(N, len(ctm))
        except Exception as e:
            if use_c: raise
            log(f'  hopscan.c not available ({e}); Python scans')
    if lib is not None:
        fp = np.zeros(N + 1, np.int32); ft, fw = [], []
        for s in range(N):
            fl = net.foot.get(s, ())
            fp[s + 1] = fp[s] + len(fl); ft.extend(j for j, _ in fl); fw.extend(float(w) for _, w in fl)
        ft = np.array(ft, np.int32); fw = np.array(fw, np.float64)
        vir = np.array([1 if net.virtual(s) else 0 for s in range(N)], np.uint8)
        cap = 1 << 20
        bo, bt, bm, bk = (np.zeros(cap, np.int32), np.zeros(cap, np.float64), np.zeros(cap, np.int64),
                          np.zeros(cap, np.int32))
    nck = [0]

    def scan(b, t, off, conns=None):
        srcs = np.atleast_1d(np.asarray(b, np.int32))
        if conns is None: conns = metro.get(int(comp[srcs[0]]), empty)
        if lib is None: return scan_py(net, srcs.tolist() if len(srcs) > 1 else int(srcs[0]), t, off, D, mt, conns, sbit, outp)
        r = lib.hs_scan(len(srcs), srcs, float(t), float(off), float(D), float(mt), len(conns[0]), *conns, sbit, outp, vir,
                        fp, ft, fw, cap, bo, bt, bm, bk)
        if r < 0: raise MemoryError('hopscan output buffer')
        res = list(zip(bo[:r].tolist(), bt[:r].tolist(), bm[:r].tolist(), bk[:r].tolist()))
        if nck[0] < check:
            nck[0] += 1
            ref = scan_py(net, srcs.tolist() if len(srcs) > 1 else int(srcs[0]), t, off, D, mt, conns, sbit, outp)
            if sorted(res) != sorted(ref): sys.exit(f'hopscan C/Python mismatch at stop {b} t {t}')
        return res

    nh = [0, 0]

    def hops(node, b, t, off, lab, conns=None):
        res = scan(b, t, off, conns); nh[0] += 1
        fin = [(s, tt, m) for s, tt, m, kd in res if is_end[s] and tt <= D]
        for s, tt, m in fin: add(node, 1, FINISH, tt, m, lab, s)
        by_stop = defaultdict(list)
        for s, tt, m, kd in res:
            r = rng_of.get(int(s))
            if r is None: continue
            ready = tt + (off if kd in (2, 3) else mt)
            lo, hi = r
            x = int(np.searchsorted(tl_mom[lo:hi], ready))
            if x < hi - lo: by_stop[s].append((x, m))
        for s, L in by_stop.items():
            L.sort(); kept = []
            lo = rng_of[int(s)][0]
            for x, m in L:
                if any((m & ~m2) == 0 for _, m2 in kept): continue       # an earlier slot holds every bit
                kept.append((x, m)); add(node, TL0 + lo + x, HOP, 0.0, m, -1, s); nh[1] += 1

    t1 = time.time()
    for i in range(nK): hops(ARR0 + i, int(ct[i]), float(arr[i]), mt, int(K[i]))
    if s0 is not None: hops(0, int(s0), float(t0), 0.0, -1)
    else:                                                    # free start: every stop at t0, one scan per metro
        allst = np.arange(N); cm = comp[allst]
        inm = np.isin(cm, list(metro)) if metro else np.zeros(N, bool)
        for c_, conns_ in metro.items(): hops(0, allst[cm == c_], float(t0), 0.0, -1, conns_)
        if (~inm).any(): hops(0, allst[~inm], float(t0), 0.0, -1, empty)
    log(f'  hops: {nh[0]} scans, {nh[1]} hop arcs, {time.time() - t1:.0f} s' + (' (C)' if lib is not None else ''))
    cat = lambda L, dt: np.concatenate(L) if L else np.zeros(0, dt)
    M = dict(u=cat(U, np.int64), v=cat(V, np.int64), kind=cat(KD, np.int8), cost=cat(C, float), mask=cat(MK, np.int64),
             lk=cat(LK, np.int64), lj=cat(LJ, np.int64), n=n, src=0, snk=1, owed=set(owed), bit_of=bit_of)
    log(f'  network before pruning: {n} nodes, {len(M["u"])} arcs ({len(M["u"]) - nfixed} hop and finish)')
    return prune(M, log)


def prune(M, log):
    """Drop arcs not on any source -> sink path (two BFS)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import breadth_first_order
    u, v, n = M['u'], M['v'], M['n']
    G = csr_matrix((np.ones(len(u), np.int8), (u, v)), shape=(n, n))
    fw = np.zeros(n, bool); fw[breadth_first_order(G, M['src'], directed=True, return_predecessors=False)] = True
    bw = np.zeros(n, bool); bw[breadth_first_order(G.T.tocsr(), M['snk'], directed=True, return_predecessors=False)] = True
    live = fw & bw
    ok = live[u] & live[v]
    for k in ('u', 'v', 'kind', 'cost', 'mask', 'lk', 'lj'): M[k] = M[k][ok]
    M['live'] = live
    log(f'  network: {int(live.sum())} live nodes of {n}, {len(M["u"])} arcs of {len(ok)}')
    return M


# ---------------------------------------------------------------- the solvers

def arc_states(M, i):
    m = int(M['mask'][i])
    return tuple(y for y, b in M['bit_of'].items() if m & b)


def missing_states(M):
    have = int(np.bitwise_or.reduce(M['mask'])) if len(M['mask']) else 0
    return sorted(y for y, b in M['bit_of'].items() if not have & b)


def flow_constraints(M, add_var, add_eq, add_ge):
    u, v, n = M['u'], M['v'], M['n']
    x = [add_var(i) for i in range(len(u))]
    ou = np.argsort(u, kind='stable'); iv = np.argsort(v, kind='stable')
    oc = np.concatenate([[0], np.cumsum(np.bincount(u, minlength=n))])
    ic = np.concatenate([[0], np.cumsum(np.bincount(v, minlength=n))])
    for w in np.where(M['live'])[0].tolist():
        rhs = 1 if w == M['src'] else (-1 if w == M['snk'] else 0)
        add_eq(ou[oc[w]:oc[w + 1]].tolist(), iv[ic[w]:ic[w + 1]].tolist(), rhs)
    for y, b in M['bit_of'].items(): add_ge(np.where(M['mask'] & b)[0].tolist())
    return x


def solve_lp(M, log=print):
    """LP relaxation with GLOP: infeasible here is already a proof; otherwise its value is a lower bound."""
    from ortools.linear_solver import pywraplp
    s = pywraplp.Solver.CreateSolver('GLOP')
    xs = []
    def add_var(i): v = s.NumVar(0, 1, ''); xs.append(v); return v
    def add_eq(o, i_, rhs):
        c = s.Constraint(rhs, rhs)
        for a in o: c.SetCoefficient(xs[a], 1)
        for a in i_: c.SetCoefficient(xs[a], -1)
    def add_ge(cv):
        c = s.Constraint(1, s.infinity())
        for a in cv: c.SetCoefficient(xs[a], 1)
    t = time.time(); flow_constraints(M, add_var, add_eq, add_ge)
    obj = s.Objective()
    for i in np.where(M['kind'] == FINISH)[0].tolist(): obj.SetCoefficient(xs[i], float(M['cost'][i]))
    obj.SetMinimization()
    log(f'  LP model {len(xs)} vars, {s.NumConstraints()} constraints, built in {time.time() - t:.0f} s')
    t = time.time(); r = s.Solve()
    name = {pywraplp.Solver.OPTIMAL: 'OPTIMAL', pywraplp.Solver.INFEASIBLE: 'INFEASIBLE'}.get(r, str(r))
    log(f'  LP {name} in {time.time() - t:.1f} s' + (f', bound {s.Objective().Value():.0f}' if r == 0 else ''))
    return name, (s.Objective().Value() if r == 0 else None)


def solve_cp(M, time_limit=600, workers=8, hint=None, log=print):
    """Exact with CP-SAT. Returns (status, finish seconds or None, bound, chosen arc indices)."""
    from ortools.sat.python import cp_model
    m = cp_model.CpModel(); xs = []
    def add_var(i): v = m.NewBoolVar(''); xs.append(v); return v
    def add_eq(o, i_, rhs):
        m.Add(cp_model.LinearExpr.Sum([xs[a] for a in o]) - cp_model.LinearExpr.Sum([xs[a] for a in i_]) == rhs)
    def add_ge(c): m.AddBoolOr([xs[a] for a in c])
    t = time.time(); flow_constraints(M, add_var, add_eq, add_ge)
    fin = np.where(M['kind'] == FINISH)[0]
    base = float(M['cost'][fin].min()) if len(fin) else 0.0
    m.Minimize(cp_model.LinearExpr.WeightedSum([xs[i] for i in fin.tolist()],
                                               [int(round(c - base)) for c in M['cost'][fin].tolist()]))
    log(f'  CP-SAT model {len(xs)} vars, built in {time.time() - t:.0f} s')
    s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = time_limit; s.parameters.num_workers = workers
    t = time.time(); r = s.Solve(m); name = s.StatusName(r)
    log(f'  CP-SAT {name} in {time.time() - t:.1f} s')
    if r in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = [i for i in range(len(xs)) if s.Value(xs[i])]
        return name, s.ObjectiveValue() + base, s.BestObjectiveBound() + base, chosen
    return name, None, (s.BestObjectiveBound() + base if r != cp_model.INFEASIBLE else None), []


def read_path(M, chosen):
    """The solution in travel order (follow the unit of flow from the source), as
    (kind, connection index or -1, stop index or -1, states)."""
    nxt = defaultdict(list)
    for i in chosen: nxt[int(M['u'][i])].append(i)
    out, u = [], M['src']
    while u != M['snk'] and nxt[u]:
        i = nxt[u].pop()
        out.append((KIND[M['kind'][i]], int(M['lk'][i]), int(M['lj'][i]), arc_states(M, i)))
        u = int(M['v'][i])
    return out


# ---------------------------------------------------------------- self test (synthetic, no router)

def _bruteforce(net, s0, t0, D, owed, end, mt=MIN_TRANSFER, end_stops=None):
    """Enumerate every route on a tiny network under the model's own rules (DFS over boardings): the earliest finish."""
    best = [None]
    trips = defaultdict(list)
    for k in range(len(net.dep)): trips[net.ctrip[k]].append(k)
    for v in trips.values(): v.sort(key=lambda k: net.dep[k])
    def arrive(b, t, got, first):
        for j, w, sts in walks_from(net, b):
            g2 = got | (set(sts) & owed); tt = t + w
            if (int(net.state[j]) == end if end_stops is None else j in end_stops) and tt <= D and owed <= g2:
                if best[0] is None or tt < best[0]: best[0] = tt
            ready = tt + (0 if first else mt)
            for tr, ks in trips.items():
                for x, k in enumerate(ks):
                    if net.cfrom[k] != j or net.dep[k] < ready or net.arr[k] > D: continue
                    g3 = set(g2)
                    for k2 in ks[x:]:
                        g3 |= {int(net.state[net.cfrom[k2]]), int(net.state[net.cto[k2]])} & owed
                        arrive(int(net.cto[k2]), net.arr[k2], frozenset(g3), False)
    arrive(s0, t0, frozenset({int(net.state[s0])} & owed), True)          # the start's own state counts
    return best[0]


def selftest():
    quiet = lambda *a, **k: None
    global HAVE_C
    try: HAVE_C = hopscan_c(16, 16) is not None
    except Exception as e: print(f'  hopscan.c did not build: {e}'); HAVE_C = False
    print(f'  hopscan.c: {"built" if HAVE_C else "not available, Python scans only"}')
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
    def run(net, owed, D, s0=0, t0=0, end=3, city=None, use_c=False, end_stops=None):
        M = build(net, s0, t0, D, owed, end, log=quiet, city=city, use_c=use_c, check=10 ** 6 if use_c else 0,
                  end_stops=end_stops)
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
    # city hops: the same networks with trips moved inside hops must give the same optimum
    check('ride-through as a city hop', run(net, {1, 2}, 2000, city=[True, True, False, False, False]), 700)
    check('walk-in after a city ride', run(net3, {1, 4}, 2000, city=[True, True, False, False, False]), 800)
    check('everything a city hop', run(net3, {1, 4}, 2000, city=[True] * 5), 800)
    check('transfer inside a hop', run(net2, {1}, 2000, city=[True, True, True, False]), 950)
    check('end stop B: ride to B only', run(net, set(), 2000, end_stops={1}), 100)
    check('end stop C owing B: t1 through B', run(net, {1}, 2000, end_stops={2}), 200)
    check('end stop C owing B by 199 is infeasible', run(net, {1}, 199, end_stops={2}), None)
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
        cityf = rng.random(len(conns)) < 0.5
        trips_city = {trp[i] for i in range(len(conns)) if cityf[i]}
        cityf = np.array([t_ in trips_city for t_ in trp])                 # whole trips are city or not
        got_h = run(netr, owed, 6000, end=S - 1, city=cityf)
        if not ((got_h is None and want is None) or (got_h is not None and want is not None and abs(got_h - want) < 1e-6)):
            good = False; print(f'  FAIL random {trial} with hops: got {got_h}, want {want}')
        if HAVE_C:
            got_c = run(netr, owed, 6000, end=S - 1, city=cityf, use_c=True)
            if got_c != got_h: good = False; print(f'  FAIL random {trial} C hops: got {got_c}, Python {got_h}')
        # free start: the model's earliest finish over every start from t0 = 0 is the best brute force over every stop
        wants = [w for w in (_bruteforce(netr, s_, 0, 6000, owed, S - 1) for s_ in range(S)) if w is not None]
        want_f = min(wants) if wants else None
        for cf_, uc in ((None, False), (cityf, False)) + (((cityf, True),) if HAVE_C else ()):
            got_f = run(netr, owed, 6000, s0=None, end=S - 1, city=cf_, use_c=uc)
            if not ((got_f is None and want_f is None) or (got_f is not None and want_f is not None and abs(got_f - want_f) < 1e-6)):
                good = False; print(f'  FAIL random {trial} free start (hops {cf_ is not None}, C {uc}): got {got_f}, want {want_f}')
        # fixed end stop: finish only at one named stop (any state), fixed and free start
        es = {int(rng.integers(1, S))}
        want_e = _bruteforce(netr, 0, 0, 6000, owed, S - 1, end_stops=es)
        wants_e = [w for w in (_bruteforce(netr, s_, 0, 6000, owed, S - 1, end_stops=es) for s_ in range(S)) if w is not None]
        for s0_, w_ in ((0, want_e), (None, min(wants_e) if wants_e else None)):
            for cf_, uc in ((None, False), (cityf, False)) + (((cityf, True),) if HAVE_C else ()):
                got_e = run(netr, owed, 6000, s0=s0_, end=S - 1, city=cf_, use_c=uc, end_stops=es)
                if not ((got_e is None and w_ is None) or (got_e is not None and w_ is not None and abs(got_e - w_) < 1e-6)):
                    good = False; print(f'  FAIL random {trial} end stop {es} start {s0_} (hops {cf_ is not None}, C {uc}): got {got_e}, want {w_}')
        if good: n_ok += 1
        else: print(f'  FAIL random {trial}: got {got}, want {want}')
    check(f'random networks agree with brute force (plain, hops' + (', C hops' if HAVE_C else '') + '; fixed and free start; '
          'end state and end stop)', n_ok, n)
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
    ap.add_argument('--no-hops', action='store_true', help='city transit as plain connections (the uncontracted model)')
    ap.add_argument('--free-start', action='store_true', help='start anywhere from --at on (the cutoff); --stop unused, '
                    '--owes all by default: is there any route inside [--at, --by]?')
    ap.add_argument('--end-stop', help='finish by standing at this stop (name or #index; several with |) by --by, '
                    'any state; --owes must then list what the segment collects')
    ap.add_argument('--check', type=int, default=0, help='compare hopscan.c with the Python scan on the first N origins')
    a = ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from time_router import cached_router, N_STATES, MIN_TRANSFER as MT
    from common import ABBR
    import backward as B
    R = cached_router(date.fromisoformat(a.d0), a.days)
    inv = {v: k for k, v in ABBR.items()}; code = lambda c: R.state_names.index(inv[c])
    end = code(a.end)
    def one_stop(q):
        if q.startswith('#'): return int(q[1:])
        c = [i for i in R.stops_matching(q) if R.stop_name[i].lower() == q.lower()] or R.stops_matching(q)
        if len(c) != 1:
            sys.exit(f'stop {q!r} matches {len(c)} stops; pass one as #index:\n' +
                     '\n'.join(f'  #{i}  {R.stop_name[i]}  {R.abbr[i]}  {R.stop_ids[i]}' for i in c[:20]))
        return c[0]
    end_stops = None
    if a.end_stop:
        end_stops = [one_stop(q) for q in a.end_stop.split('|')]
        if a.owes in (None, ''): sys.exit('--end-stop needs --owes (the states the segment must collect)')
        owed = {code(c) for c in a.owes.split(',') if c}
        print('end stops: ' + '; '.join(f'#{j} {R.stop_name[j]} {R.abbr[j]}' for j in end_stops))
    else:
        owed = ({y for y in range(len(R.state_names)) if y != end} if a.owes in (None, '', 'all')
                else {code(c) for c in a.owes.split(',') if c and c != a.end})
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
    D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.by_tz)).timestamp()
    if a.free_start:
        s0 = None
        print(f'free start from {datetime.fromtimestamp(t0, ZoneInfo(a.tz))}, owes {len(owed)}; end {a.end} by '
              f'{datetime.fromtimestamp(D, ZoneInfo(a.by_tz))} ({(D - t0) / 3600:.2f} h)', flush=True)
        s0s = [None]
    elif a.stop.startswith('#'): s0s = [int(a.stop[1:])]          # an exact stop index, as the error below lists them
    else: s0s = [i for i in R.stops_matching(a.stop) if R.stop_name[i].lower() == a.stop.lower()] or R.stops_matching(a.stop)
    if len(s0s) != 1:
        sys.exit(f'--stop matches {len(s0s)} stops; pass one as #index:\n' +
                 '\n'.join(f'  #{i}  {R.stop_name[i]}  {R.abbr[i]}  {R.stop_ids[i]}' for i in s0s[:20]))
    s0 = s0s[0]
    if s0 is not None: print(f'from {R.stop_name[s0]} at {R.fmt_time(t0, s0)}, owes {len(owed)}: {a.owes}; end {a.end} by '
          f'{R.fmt_time(D, s0)} ({(D - t0) / 3600:.2f} h)', flush=True)
    t = time.time()
    ref = s0 if s0 is not None else (end_stops[0] if end_stops else int(np.where(R.state == end)[0][0]))      # whose clock to print times on
    ea = R.scan({s0: (t0, None)}, set())[2] if s0 is not None else None
    F = B.RevFast(R)
    ends = end_stops if end_stops is not None else np.where(R.state == end)[0]
    lat, ok_, k0, k1 = F.layer({int(s): D for s in ends}, False, t0, None)
    eff, _ = F.through(ok_, k0, k1, np.ones(R.N, bool)); lend = np.maximum(lat, eff)
    print(f'  forward and reverse scans {time.time() - t:.0f} s', flush=True)
    city_feed = [fi for fi, f in enumerate(R.feeds) if getattr(f, 'city', False)]
    city = np.isin(np.fromiter((k[0] for k in R.ctrip), np.int64, len(R.ctrip)), city_feed)
    if a.no_hops: city[:] = False
    net = Net(R.dep, R.arr, R.cfrom, R.cto, R.ctrip, R.foot, R.state, virtual=lambda j: j >= R.first_virtual,
              name=lambda s: R.stop_name[s], city=city)
    t = time.time(); M = build(net, s0, t0, D, owed, end, ea=ea, lend=lend, mt=MT, check=a.check, end_stops=end_stops)
    print(f'  built in {time.time() - t:.0f} s', flush=True)
    miss = missing_states(M)
    if miss:
        print('PROVED DEAD: no arc on any start->finish path touches', ','.join(ABBR[R.state_names[y]] for y in miss)); return
    if a.lp:
        name, val = solve_lp(M)
        if name == 'INFEASIBLE': print('PROVED DEAD by the LP relaxation')
        elif val is not None: print(f'LP bound: finish no earlier than {R.fmt_time(val, ref)} ({(val - t0) / 3600:.2f} h)')
        return
    name, f, bnd, chosen = solve_cp(M, a.time, a.workers)
    if name == 'INFEASIBLE': print('PROVED DEAD: no route collects the owed states and finishes by the deadline'); return
    if f is None: print(f'UNKNOWN after {a.time:.0f} s' + (f', bound {(bnd - t0) / 3600:.2f} h' if bnd else '')); return
    print(f'{name}: finish {R.fmt_time(f, ref)} ({(f - t0) / 3600:.2f} h), bound {(bnd - t0) / 3600:.2f} h')
    for kind, k, j, st in read_path(M, chosen):
        if kind == 'board':
            print(f'    board  {R.stop_name[R.cfrom[k]][:30]} {R.fmt_time(R.dep[k], R.cfrom[k])} {R.ctrip[k]}  '
                  f'{",".join(ABBR[R.state_names[y]] for y in st)}')
        elif kind in ('hop', 'finish'):
            print(f'    {kind:6s} to {R.stop_name[j][:30]}  {",".join(ABBR[R.state_names[y]] for y in st)}')
    print('  check any route found with verify_path.py before believing it')


if __name__ == '__main__':
    main()
