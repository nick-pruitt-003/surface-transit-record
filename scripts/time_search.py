"""Local search over the state order using real timetables as the objective.

usage: python3 time_search.py --start Missoula --at 2026-11-02T07:00 --tz America/Denver \
         --seed ../out/start_newton.pkl [--prefix "Idaho,Washington"] --budget 900 --workers 8 --out ../out/time_best.pkl
"""
import re, argparse, itertools, json, os, pickle, random, time, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, cached_router, N_STATES
from common import ABBR

_R = None; _START = None; _T0 = None; _BASE = None; _SELF = None; _END = None   # _END: required last target
def bind(R, start, t0, S, base=None, end=None):
    """Make S the search the module-level helpers and workers evaluate with: router, start, clock, base, end."""
    global _R, _START, _T0, _SELF, _BASE, _END
    _R, _START, _T0, _SELF, _BASE, _END = R, start, t0, S, base, end

def rebind(S):
    """Switch to another Search on the same router mid-run. Start, clock and end come from S itself, so the
    helpers can never evaluate one search against another's start; router and base stay as bound."""
    global _START, _T0, _SELF, _END
    _START, _T0, _SELF, _END = S.start, S.t0, S, S.end

FREE = -1   # start value: begin anywhere in the order's first state (the search picks that state)

def _src(start, order):
    """(start stop(s), targets) to route. Free start: every real stop of order[0]'s state, then order[1:]."""
    if start != FREE: return start, order
    x = order[0] if order else None
    if not isinstance(x, (int, np.integer)) or not 0 <= x < N_STATES: return None, order
    ss = _R.__dict__.setdefault('_state_stops', {})
    if x not in ss: ss[x] = np.array([i for i in range(_R.first_virtual) if _R.state[i] == x], dtype=np.int64)
    return ss[x], order[1:]



TIE_W = 0.02   # weight of the mean per-state arrival: breaks ties between equal finishes so partial savings
               # (reaching a once-daily departure with more slack) count and the search can climb toward it

def _finish(order):
    if _END is not None and (not order or order[-1] != _END): return float('inf')
    st, o = _src(_START, order)
    if st is None: return float('inf')
    base = _BASE[:2] if _BASE is not None and _BASE[2] == (order[0] if _START == FREE else None) else None
    f, m = _R.finish(st, _T0, o, base, profile=True)
    return f + TIE_W * (m - _T0) if f is not None else float('inf')

def _finish_block(orders):
    """_finish for a block of orders, sharing scan layers across their common prefixes (TimeRouter.finish_many).
    Orders should be in lexicographic order, as enumerate_all hands them out. A free start groups by first state,
    since that state is where the route starts rather than a layer."""
    out = [float('inf')] * len(orders); groups = {}
    for i, o in enumerate(orders):
        if _END is not None and (not o or o[-1] != _END): continue
        st, rest = _src(_START, o)
        if st is None: continue
        groups.setdefault(o[0] if _START == FREE else None, (st, []))[1].append((i, rest))
    for st, items in groups.values():
        for (i, _), (f, m) in zip(items, _R.finish_many(st, _T0, [r for _, r in items])):
            if f is not None: out[i] = f + TIE_W * (m - _T0)
    return out

def _elapsed_eval(order):
    """Worker side of enumerate_all: hours from the first bus to the finish, routing from the window start.
    inf when the route does not finish or does not cover every state."""
    f, legs = _SELF.evaluate(order)
    if f == float('inf') or not _SELF.all_states(legs): return float('inf')
    first = next((l[3] for l in legs if l[0] == 'ride'), None)
    return f - first if first is not None else float('inf')

def _drop_eval(order):
    """Worker side of prune: finish time and whether the route still covers every state."""
    f, legs = _SELF.evaluate(order)
    return f, (f != float('inf') and _SELF.all_states(legs))


# Where there is no fork (Windows), workers cannot inherit the globals above, and re-creating a pool for every
# incumbent as the fork path does would mean every worker reloading a multi-GB router each kick. Instead the
# pool is spawned once, each worker loads the cached router itself (_ROUTER_ARGS, set by main), and pool_for
# publishes the small part that changes (start, clock, _BASE, the Search's settings) to a file with a
# generation number. A task carries the generation and a worker rereads the file only when it is behind.
_ROUTER_ARGS = None; _GEN = None

def _spawn_init(args):
    global _R
    from time_router import cached_router
    _R = cached_router(*args, verbose=False)

def _spawn_task(job):
    global _START, _T0, _BASE, _END, _SELF, _GEN
    fn, gen, path, order = job
    if _GEN != gen:
        with open(path, 'rb') as fh: st = pickle.load(fh)
        _START, _T0, _BASE, _END = st['start'], st['t0'], st['base'], st['end']
        _SELF = Search.__new__(Search); _SELF.__dict__.update(st['self']); _SELF.R = _R
        _GEN = gen
    return fn(order)

class _SpawnPool:
    """Stands in for multiprocessing.Pool at the call sites: map, close, join."""
    def __init__(self, workers):
        import multiprocessing as mp, tempfile
        self.path = os.path.join(tempfile.gettempdir(), f'bus48_time_search_{os.getpid()}.pkl')
        self.gen = 0
        self.pool = mp.get_context('spawn').Pool(workers, initializer=_spawn_init, initargs=(_ROUTER_ARGS,))

    def publish(self, search):
        keep = {k: v for k, v in search.__dict__.items() if k not in ('R', '_live')}
        tmp = self.path + '.tmp'
        with open(tmp, 'wb') as fh:
            pickle.dump(dict(start=_START, t0=_T0, base=_BASE, end=_END, self=keep), fh, protocol=5)
        os.replace(tmp, self.path); self.gen += 1

    def map(self, fn, items):
        return self.pool.map(_spawn_task, [(fn, self.gen, self.path, o) for o in items])

    def close(self):
        self.pool.close()
        try: os.remove(self.path)
        except OSError: pass

    def join(self): self.pool.join()


class Search:
    def __init__(self, R, start, t0, prefix, workers, done=(), start_opts=(), fixed_start=False, end=None, end_by=None):
        self.R = R; self.start = start; self.t0 = t0; self.workers = workers
        self.start_opts = [start] + [x for x in start_opts if x != start]   # stops the start may move to
        self.day0 = t0   # start windows are [day0 + k days, +24 h)
        self.fixed_start = fixed_start   # keep start and clock as given (e.g. continuing after a forced ride)
        self.end, self.end_by = end, end_by   # route must finish at this target ('@stop'), by this time (epoch s)
        self.patience = 0   # seconds without a new best before stopping early (0 = use the whole budget)
        self.idle_kicks = 10   # stop after this many kicks in a row that score no new order (0 = never)
        self.exhaustive = 7    # score every order when at most this many states are owed (0 = never)
        self.done = set(done)   # states already collected before the start
        self.prefix = []
        for p in prefix:
            self.prefix.append(p if p.startswith('@') else R.state_names.index(p))
        self.P = len(self.prefix)
        self.sticky = set()        # pins from the seed; gateway pins the search adds may be dropped again
        self.gateways = self.build_gateways()

    # ---- live progress for out/live/index.html (never allowed to break the search) ----
    LIVE_PATH = os.environ.get('BUS48_LIVE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'out', 'live', 'live.json'))

    def legs_json(self, legs):
        R = self.R; out = []
        for l in legs:
            if l[0] not in ('ride', 'walk'): continue
            if l[0] == 'ride': _, trip, a, t0, b, t1 = l; ag, rt, hs = R.trip_info[(trip[0], trip[1])]; how = f'{ag}: {rt or hs}'
            else: _, a, b, t0, t1 = l; how = 'walk / local'
            out.append(dict(kind=l[0], a=[*map(float, R.stop_xy[a]), R.stop_name[a]], b=[*map(float, R.stop_xy[b]), R.stop_name[b]],
                            dep=R.fmt_time(t0, a), arr=R.fmt_time(t1, b) if t1 else '', how=how[:70]))
        return out

    def live(self, force=False, note=None, **kw):
        try:
            L = self.__dict__.setdefault('_live', dict(started=time.time(), evals=0, kick=0, history=[], log=[], best_h=None, current_h=None))
            L.update(kw)
            if note: L['log'] = (L['log'] + [[round(time.time() - L['started']), note]])[-14:]
            if not force and time.time() - self.__dict__.get('_live_t', 0) < 2: return
            self._live_t = time.time(); L['now'] = time.time()
            os.makedirs(os.path.dirname(self.LIVE_PATH), exist_ok=True)
            tmp = self.LIVE_PATH + '.tmp'; json.dump(L, open(tmp, 'w')); os.replace(tmp, self.LIVE_PATH)
        except Exception as e:
            print('live view error (ignored):', e, flush=True)

    def _tname(self, x):
        if isinstance(x, str): return 'a gateway' if x.startswith('@~') else x[1:][:28]
        return ABBR.get(self.R.state_names[x], self.R.state_names[x]) if x < N_STATES else str(x)

    def move_label(self, order, cand):
        """Plain-words description of the local-search move that turns order into cand."""
        try:
            if len(order) == len(cand):
                i = next(k for k in range(len(order)) if order[k] != cand[k])
                j = max(k for k in range(len(order)) if order[k] != cand[k])
                if cand[i:j + 1] == order[i:j + 1][::-1]:
                    return f'reverse {self._tname(order[i])} ... {self._tname(order[j])}'
                if i == j: return f'take {self._tname(order[i])} at {self._tname(cand[i])}'
                for x in order[i:j + 1]:
                    if [y for y in order if y != x] == [y for y in cand if y != x]:
                        k = cand.index(x)
                        return f'move {self._tname(x)} ' + (f'after {self._tname(cand[k - 1])}' if k else 'to the front')
            return 'reshape'
        except Exception:
            return 'move'

    def live_trial(self, order, cand, f_try, label=None):
        """At most once a second: route the candidate being tested and show it (costs one route, ~0.1 s)."""
        if time.time() - self.__dict__.get('_trial_t', 0) < 1: return
        self._trial_t = time.time()
        try:
            f, legs = self.evaluate(cand)
            h = None if f == float('inf') else self.el_h(f, legs)
            miss = self.missing(legs)
            if miss: label = (label or self.move_label(order, cand)) + f' (incomplete: misses {", ".join(self._tname(m) for m in miss[:4])})'
            L = self.__dict__.get('_live')
            if L is not None: L['tried'] = L.get('tried', 0) + 1
            self.live(force=True, trying=self.legs_json(legs), trying_h=h, trying_note=label or self.move_label(order, cand))
        except Exception as e:
            print('live view error (ignored):', e, flush=True)

    def el_h(self, f, legs):
        """Hours from the first bus boarded to f: the same scale as the best (the start clock floats)."""
        first = next((l[3] for l in legs if l[0] == 'ride'), self.t0)
        return round((f - first) / 3600, 2)

    def live_point(self, current_h=None, best_h=None):
        L = self.__dict__.get('_live')
        if L is None: return
        if current_h is not None: L['current_h'] = current_h
        if best_h is not None: L['best_h'] = best_h
        L['history'] = (L['history'] + [[round(time.time() - L['started'], 1), L.get('best_h'), L.get('current_h')]])[-3000:]

    def build_gateways(self, per_state=5, sep_km=60, radius_km=6):
        """Busiest stop clusters per state, as '@~lon,lat,km' targets. Replacing a state with one of its
        gateways lets the search collect the state somewhere other than the earliest stop it can reach
        (Mobile instead of Tuscaloosa, the Memphis walk-in instead of Jackson at 3 AM)."""
        R = self.R; xy = np.asarray(R.stop_xy, dtype=float)
        deps = np.bincount(R.cfrom, minlength=R.N)
        out = {}; busiest = [i for i in np.argsort(-deps) if deps[i] > 0]
        for s in range(N_STATES):
            idx = [i for i in busiest if R.state[i] == s]
            picks = []
            for i in idx:
                lon, lat = xy[i]
                if all(np.hypot((lon - a) * 111.3 * np.cos(np.radians(lat)), (lat - b) * 111.3) > sep_km for a, b in picks):
                    picks.append((lon, lat))
                if len(picks) >= per_state: break
            out[s] = [f'@~{a:.4f},{b:.4f},{radius_km}' for a, b in picks]
        return out

    def covered(self, legs):
        """States with an alighting-capable stop anywhere along the ridden trips."""
        seen = set()
        for l in legs:
            if l[0] == 'walk' and self.R.walk_collects(l[2]): seen.add(int(self.R.state[l[2]]))   # border walk-in or measured walk link
            if l[0] != 'ride': continue
            _, trip, bs, bt, al, at = l
            fi, tid, _ = trip; f = self.R.feeds[fi]; t = f.trips[tid]
            ids = [self.R.idx[f.stops[s[1]][0]] for s in t['stops']]
            if bs in ids and al in ids:
                i, j = ids.index(bs), ids.index(al)
                for k in ids[min(i, j):max(i, j) + 1]:
                    if self.R.state[k] >= 0: seen.add(int(self.R.state[k]))
        return seen

    def evaluate(self, order):
        st, o = _src(self.start, order)
        if st is None: return float('inf'), []
        f, legs = self.R.route(st, self.t0, o)
        if f is None: return float('inf'), [l for l in legs if l[0] != 'unreachable']
        return f, legs

    def prune(self, order, pool=None):
        """Drop states the route covers in passing. All single drops are tried at once (in the pool when
        there is one) and the best harmless one is taken, instead of re-routing them one by one."""
        f, legs = self.evaluate(order)
        if f == float('inf'): return order, f, legs
        while len(order) > self.P:
            cands = [order[:j] + order[j + 1:] for j in range(self.P, len(order))]
            res = pool.map(_drop_eval, cands) if pool else [_drop_eval(o) for o in cands]
            ok = [(r[0], k) for k, r in enumerate(res) if r[1] and r[0] <= f and order[self.P + k] not in self.sticky]   # seed pins stay
            if not ok: break
            f2, k = min(ok)
            x = order[self.P + k]
            print('  drop', x if isinstance(x, str) else self.R.state_names[x], '->', round((f2 - self.t0) / 3600, 1), 'h')
            order = cands[k]; f = f2
        f, legs = self.evaluate(order)
        return order, f, legs

    def _base_cov(self, legs):
        s = -1 if self.start == FREE else int(self.R.state[self.start])   # -1 when the start stop lies outside every state
        return self.covered(legs) | self.done | ({s} if s >= 0 else set())

    def all_states(self, legs):
        return len(self._base_cov(legs)) >= N_STATES

    def missing(self, legs):
        cov = self._base_cov(legs)
        return [s for s in range(N_STATES) if s not in cov]

    def repair(self, order, pool):
        """Insert each missing state at the position that finishes earliest."""
        f, legs = self.evaluate(order)
        for m in self.missing(legs):
            cands = [order[:j] + [m] + order[j:] for j in range(self.P, len(order) + 1)]
            fs = self.score(cands, pool)
            j = int(np.argmin(fs)); order = cands[j]
        f, legs = self.evaluate(order)
        return order, f, legs

    def score(self, orders, pool=None):
        """_finish for each order, memoised on (start, clock, order). _finish is a pure function of those three
        for one search (_BASE only speeds it up), so an order is scored once per start however often the local
        search, a kick or a pair move comes back to it. Only unseen orders go to the pool; self._new counts them,
        which is how run() knows a kick taught it nothing. The key needs no more: done and _END are fixed for a
        Search instance, and a moved start or clock is a new (start, t0), so a stale entry is never read."""
        memo = self.__dict__.setdefault('_memo', {})
        key = (int(self.start), self.t0)
        ks = [(key, tuple(o)) for o in orders]
        todo = {k: o for k, o in zip(ks, orders) if k not in memo}
        if todo:
            new = list(todo.values())
            fs = pool.map(_finish, new) if pool and len(new) > 1 else [_finish(o) for o in new]
            memo.update(zip(todo, fs)); self._new = self.__dict__.get('_new', 0) + len(new)
        return [memo[k] for k in ks]

    def score1(self, order, pool=None):
        return self.score([order], pool)[0]

    def moves(self, order):
        n = len(order); P = self.P; out = []
        for i in range(P, n):
            seg = order[i:i + 1]; rest = order[:i] + order[i + 1:]
            for j in range(P, n):                            # relocate anywhere (whole-route moves like GA from Savannah to Atlanta)
                if j != i: out.append(rest[:j] + seg + rest[j:])
        for i in range(P, n - 1):
            for j in range(i + 2, min(n, i + 6) + 1):        # reverse segments of up to 6
                out.append(order[:i] + order[i:j][::-1] + order[j:])
        for i in range(P, n):                                # collect a state at one of its gateways instead
            x = order[i]
            gws = self.gateways.get(x, []) if not isinstance(x, str) else \
                  next((g for g in self.gateways.values() if x in g), [])
            for g in gws:
                if g != x: out.append(order[:i] + [g] + order[i + 1:])
        return out

    def pool_for(self, order, pool):
        """Cache the incumbent's layer labels and fork a fresh pool so workers inherit them."""
        global _BASE
        st, o = _src(self.start, order)
        if st is not None: self.R.route(st, self.t0, o); _BASE = (list(o), self.R.last_outs, order[0] if self.start == FREE else None)
        else: _BASE = None
        if self.workers <= 1: return None
        import multiprocessing as mp
        if 'fork' not in mp.get_all_start_methods():   # Windows: one spawned pool, refreshed through a file
            if pool is None:
                if _ROUTER_ARGS is None:
                    print('no fork and no cached router to load in workers: running with 1 worker', flush=True)
                    self.workers = 1; return None
                pool = _SpawnPool(self.workers)
            pool.publish(self)
            return pool
        if pool: pool.close(); pool.join()
        return mp.get_context('fork').Pool(self.workers)

    def descend(self, order, f, legs, deadline, pool):
        """First-improvement local search from (order, f, legs) until no move helps or time is up.
        Moves are compared on the tie-broken score (_finish), so equal finishes with earlier states still count."""
        improved = True; it = 0; sc = self.score1(order)
        while improved and time.time() < deadline:
            improved = False
            cands = self.moves(order); random.shuffle(cands)
            batch = max(1, self.workers * 2)
            for i in range(0, len(cands), batch):
                if time.time() > deadline: break
                chunk = cands[i:i + batch]
                fs = self.score(chunk, pool)
                it += len(chunk); j = int(np.argmin(fs))
                self.live(evals=self.__dict__.get('_live', {}).get('evals', 0) + len(chunk), phase='descending')
                self.live_trial(order, chunk[j], fs[j])
                if fs[j] < sc - 60:
                    o2, f2, l2 = self.repair(chunk[j], pool)
                    s2 = self.score1(o2)
                    if s2 < sc - 60 and f2 <= f + 60 and self.all_states(l2):
                        order, f, legs, sc = o2, f2, l2, s2; improved = True
                        print('  improve', round((f - self.t0) / 3600, 1), 'h after', it, 'evals', flush=True)
                        self.live_point(current_h=self.el_h(f, legs))
                        self.live(force=True, current=self.legs_json(legs), note=f'improve: {self.el_h(f, legs):.1f} h'); break
            if improved:
                order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool); sc = self.score1(order)
        return order, f, legs, pool

    def joint(self, order, f, legs, deadline, pool, top=4):
        """Pair/triple move for when single moves are stuck: find groups of 2-3 nearby targets whose joint removal
        saves much more than removing any one of them (they hold a day together), then pull each group out and
        re-insert its members one by one at their best positions (state or gateway). Returns (order, f, legs, improved)."""
        fmap = lambda os_: self.score(os_, pool)
        sc = self.score1(order); P = self.P
        free = [i for i in range(P, len(order)) if order[i] not in self.sticky]
        drop = lambda g: [x for k, x in enumerate(order) if k not in g]
        single = dict(zip(free, fmap([drop({i}) for i in free])))
        groups = [set(c) for r in (2, 3) for c in itertools.combinations(free, r) if max(c) - min(c) <= 3]
        self.live(force=True, phase='pair moves', note=f'stuck: testing {len(groups)} state groups')
        if time.time() > deadline: return order, f, legs, False
        gs = fmap([drop(g) for g in groups])
        # joint hold = what the group saves beyond its best single member
        ranked = sorted(((min(single[i] for i in g) - s, g) for s, g in zip(gs, groups)), key=lambda t: -t[0])
        best = (sc, None)
        seen = self.__dict__.setdefault('_joint_seen', set())
        todo = [r for r in ranked if r[0] > 3600 and (tuple(order), frozenset(order[i] for i in r[1])) not in seen][:top]
        if not todo: self.live(note='pair moves: every strong group already tried on this route')
        for hold, g in todo:
            members = [order[i] for i in sorted(g)]; seen.add((tuple(order), frozenset(members)))
            names = '+'.join(self._tname(x) for x in members)
            print(f'  pair move: {names} hold {hold / 3600:.1f} h together', flush=True)
            for perm in (members, members[::-1]):
                if time.time() > deadline: break
                o = drop(g)
                for x in perm:   # greedy placement; states the move knocks out are put back by repair below
                    opts = [x] + (self.gateways.get(x, []) if not isinstance(x, str) else [])
                    cands = [o[:j] + [y] + o[j:] for j in range(P, len(o) + 1) for y in opts]
                    fs = fmap(cands); o = cands[int(np.argmin(fs))]
                o, fo, lo = self.repair(o, pool)   # judge only complete routes: a route that skips states finishes early
                ok = fo != float('inf') and self.all_states(lo)
                s = self.score1(o) if ok else float('inf')
                self.live_trial(order, o, s, label=f'pair move {names}' + ('' if ok else ' (could not cover every state)'))
                if s < best[0] - 60: best = (s, o, fo, lo)
        if best[1] is None: return order, f, legs, False
        o2, f2, l2 = best[1], best[2], best[3]
        if f2 <= f + 60:
            print('  pair move improve', round((f2 - self.t0) / 3600, 1), 'h', flush=True)
            self.live_point(current_h=self.el_h(f2, l2))
            self.live(force=True, current=self.legs_json(l2), note=f'pair move: {self.el_h(f2, l2):.1f} h')
            return o2, f2, l2, True
        return order, f, legs, False

    def local_opt(self, order, f, legs, deadline, pool):
        """Single moves until stuck, then pair moves; repeat while pair moves help."""
        while True:
            order, f, legs, pool = self.descend(order, f, legs, deadline, pool)
            if time.time() > deadline: return order, f, legs, pool
            order, f, legs, ok = self.joint(order, f, legs, deadline, pool)
            if not ok: return order, f, legs, pool
            order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool)

    def latest_start(self, start, t_lo, order, span=24 * 3600, step=600):
        """Latest clock in [t_lo, t_lo + span) that still finishes as early as leaving at t_lo. Finish is
        non-decreasing in the start clock (timetables are FIFO), so a binary search over 10-min steps works."""
        src, order = _src(start, order)
        if src is None: return None
        f0 = self.R.finish(src, t_lo, order)
        if f0 is None: return None
        lo, hi = 0, int(span // step) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            f = self.R.finish(src, t_lo + mid * step, order)
            if f is not None and f <= f0 + 60: lo = mid
            else: hi = mid - 1
        return t_lo + lo * step

    def deadline_for(self, f):
        """The deadline a finish at f is scored against. One fixed end_by unless end_daily: a daily hinge (the I-90
        bus, the Silver Meteor) leaves every day, so a front that arrives a day early takes the earlier departure and
        is not charged the wait to a later deadline (Oct 7: a Thursday arrival scored against Monday read 246.9 h)."""
        d = self.end_by
        if getattr(self, 'end_daily', False):
            while d - 86400 >= f - 60: d -= 86400
        return d

    def settle(self, order):
        """Best start for this order over start stops x 7 start days, each at its latest clock.
        Scored on hours from the first bus boarded to the finish. Returns (elapsed, stop, window start, finish, legs):
        the search keeps running from the window start so later moves may still use an earlier first bus."""
        R = self.R; best = None
        if self.fixed_start:
            f, legs = R.route(self.start, self.day0, order)
            s0 = int(R.state[self.start])
            if f is None or len(self.covered(legs) | self.done | ({s0} if s0 >= 0 else set())) < N_STATES: return None
            if self.end_by is not None and f > self.end_by + 60: return None
            return (f - self.day0, self.start, self.day0, f, legs)
        for st in self.start_opts:
            for k in range(7):
                t_lo = self.day0 + k * 86400
                t = self.latest_start(st, t_lo, order)
                if t is None: continue
                src, o = _src(st, order)
                f, legs = R.route(src, t, o)
                if f is None: continue
                s0 = -1 if st == FREE else int(R.state[st])
                if len(self.covered(legs) | self.done | ({s0} if s0 >= 0 else set())) < N_STATES: continue
                if self.end_by is not None and f > self.end_by + 60: continue   # must be at the end point by end_by
                first = next((l[3] for l in legs if l[0] == 'ride'), t)
                # With a deadline the clock runs to the deadline (a front for a hinge waits there for its train), so
                # the latest start wins, not the shortest front: a front a day early is a day lost (Oct 6, the Silver
                # Meteor front that left Wednesday, reached Jacksonville on Monday and waited 25 h).
                key = (self.deadline_for(f) if self.end_by is not None else f) - first
                if best is None or key < best[0] - 60: best = (key, st, t_lo, f, legs)
        return best

    def start_name(self, legs, st=None):
        """Where the route starts: the fixed start stop, or (free start) the first stop it leaves from."""
        st = self.start if st is None else st
        if st != FREE: return self.R.stop_name[st]
        l = next((l for l in legs if l[0] in ('ride', 'walk')), None)
        return self.R.stop_name[l[2] if l[0] == 'ride' else l[1]] if l else '(free)'

    def set_start(self, st, t, order, pool):
        global _START, _T0
        self.start, self.t0 = st, t; _START, _T0 = st, t

        return self.pool_for(order, pool)

    def adopt(self, order, pool):
        """Move the search to the best start for this order. Returns (elapsed, finish, legs, pool)."""
        b = self.settle(order)
        if b is None:
            f, legs = self.evaluate(order); return float('inf'), f, legs, pool
        el, st, t, f, legs = b
        if (st, t) != (self.start, self.t0):
            first = next((l[3] for l in legs if l[0] == 'ride'), t)
            fb = next((l[2] for l in legs if l[0] == 'ride'), None)
            when = self.R.fmt_time(first, fb) if fb is not None else '?'
            print(f'  start -> {self.start_name(legs, st)}, first bus {when}: {el / 3600:.1f} h', flush=True)
            self.live(note=f'start moved: {self.start_name(legs, st)}, first bus {when}')
            pool = self.set_start(st, t, order, pool)
        return el, f, legs, pool

    def perturb(self, order, k=3):
        """Relocate k random states (after the prefix) to random positions."""
        o = [x for x in order if x != self.end]
        for _ in range(k):
            i = random.randrange(self.P, len(o)); x = o.pop(i)
            o.insert(random.randrange(self.P, len(o) + 1), x)
        return o + ([self.end] if self.end is not None else [])

    def owed(self):
        """States the route still has to collect: not done before the start, and not the required end target."""
        return [x for x in range(N_STATES) if x not in self.done and x != self.end and x not in self.prefix]

    def enumerate_all(self, order, f, legs, pool, top=12):
        """Score every order of the owed states and continue from the best of them, so a small problem (a region
        test) does not depend on the seed or on kicks finding the answer. Scoring ranks on finish from the window
        start, which rewards an order for starting early rather than for being fast, so every order is also
        routed once for hours from its first bus (_elapsed_eval). The top `top` on each key are pruned and settled
        (the objective: hours from the first bus at the best start) and the best of those wins. About 15 ms an order on 4 workers: 7 owed states (5040) is ~75 s,
        8 (40320) would be ~10 min, hence the default cap of 7."""
        t = time.time(); ow = self.owed()
        tail = [self.end] if self.end is not None else []
        perms = [self.prefix + list(p) + tail for p in itertools.permutations(ow)]
        print(f'exhaustive: scoring all {len(perms)} orders of {len(ow)} owed states', flush=True)
        self.live(force=True, phase='exhaustive', note=f'scoring all {len(perms)} orders')
        # contiguous blocks, so each worker's orders share prefixes; about four blocks per worker for balance
        nb = max(1, min(len(perms), 4 * max(1, self.workers)))
        blocks = [perms[i * len(perms) // nb:(i + 1) * len(perms) // nb] for i in range(nb)]
        fs = [f for b in (pool.map(_finish_block, blocks) if pool else map(_finish_block, blocks)) for f in b]
        memo = self.__dict__.setdefault('_memo', {}); key = (int(self.start), self.t0)
        memo.update(((key, tuple(o)), f) for o, f in zip(perms, fs)); self._new = self.__dict__.get('_new', 0) + len(perms)
        es = []
        for i in range(0, len(perms), 2000):
            chunk = perms[i:i + 2000]
            es += pool.map(_elapsed_eval, chunk) if pool else [_elapsed_eval(o) for o in chunk]
        pick = [i for key in (fs, es) for i in np.argsort(key)[:top] if key[i] < float('inf')]
        ranked = [perms[i] for i in dict.fromkeys(pick)]
        cand = []
        for o in ranked:
            o2, f2, l2 = self.prune(o, pool)
            if f2 == float('inf') or not self.all_states(l2): continue
            b = self.settle(o2)
            if b is not None: cand.append((b[0], o2, f2, l2))
        print(f'exhaustive: {len(perms)} scored, {len(cand)} of the top {len(ranked)} settle, '
              f'{time.time() - t:.0f} s', flush=True)
        if not cand: return order, f, legs, pool
        el, o, f2, l2 = min(cand, key=lambda c: c[0])
        b = self.settle(order)
        if b is not None and b[0] <= el: return order, f, legs, pool    # the seed already does as well
        print(f'exhaustive: best {el / 3600:.1f} h from first bus', flush=True)
        return o, f2, l2, self.pool_for(o, pool)

    def run(self, order, budget):
        global _R, _START, _T0, _SELF, _END
        _R, _START, _T0, _SELF, _END = self.R, self.start, self.t0, self, self.end
        order = self.prefix + [x for x in order if x not in self.prefix]
        if self.end is not None: order = [x for x in order if x != self.end] + [self.end]
        self.sticky = {x for x in order if isinstance(x, str)} | ({self.end} if self.end is not None else set())
        pool = self.pool_for(order, None)
        f, legs = self.evaluate(order)
        if not self.all_states(legs):
            print('seed misses', [self.R.state_names[s] for s in self.missing(legs)]); order, f, legs = self.repair(order, pool)
            pool = self.pool_for(order, pool)
        order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool)   # drop states the seed already covers in passing
        print('start', round((f - self.t0) / 3600, 1), 'h, order', len(order), flush=True)
        self.live_point(current_h=self.el_h(f, legs))
        self.live(force=True, budget=budget, phase='starting', current=self.legs_json(legs), note=f'seed: {self.el_h(f, legs):.1f} h')
        deadline = time.time() + budget
        # The seed as given, settled. The descent below ranks on finish from the fixed clock, not on hours from the
        # first bus, and can walk away from a seed whose value only shows once its start day is chosen: a sweep
        # result seeded at 240.5 h came back 243.8 h (Oct 3). Kept as a candidate, as the exhaustive path keeps its own.
        sd = self.settle(order)
        sd = (list(order), sd[3], sd[4], sd[0], sd[1], sd[2]) if sd is not None else None
        ex = None
        if 0 < len(self.owed()) <= self.exhaustive:
            order, f, legs, pool = self.enumerate_all(order, f, legs, pool)
            ex = self.settle(order)    # kept as a candidate: the descent below ranks on finish, not hours from first bus
            if ex is not None: ex = (order, ex[3], ex[4], ex[0], ex[1], ex[2])
        order, f, legs, pool = self.local_opt(order, f, legs, deadline, pool)
        el, f, legs, pool = self.adopt(order, pool)
        for c in (ex, sd):
            if c is not None and c[3] < el - 60:
                order, f, legs, el = c[:4]
                if (self.start, self.t0) != c[4:6]: pool = self.set_start(c[4], c[5], order, pool)
        print('settled', round(el / 3600, 1), 'h from first bus', flush=True)
        self.live_point(best_h=round(el / 3600, 2))
        self.live(force=True, best=self.legs_json(legs), start=self.start_name(legs), note=f'first best: {el / 3600:.1f} h from first bus')
        best = (order, f, legs, el, self.start, self.t0); kick = 0; last_gain = time.time(); idle = 0
        while time.time() < deadline:      # iterated local search: kick the incumbent, descend, keep if better
            if self.patience and time.time() - last_gain > self.patience:
                print(f'converged: no new best for {self.patience:.0f} s, stopping early', flush=True)
                self.live(note='converged, stopping early'); break
            # A kick whose descent scored no order it had not already scored cannot find anything new, so a run of
            # them means the space reachable from here is exhausted. Small problems get here in seconds.
            if self.idle_kicks and idle >= self.idle_kicks:
                print(f'exhausted: {idle} kicks in a row scored no new order ({len(self._memo)} scored), stopping', flush=True)
                self.live(note='exhausted, stopping early'); break
            n0 = self.__dict__.get('_new', 0)
            kick += 1
            if (self.start, self.t0) != best[4:6]: pool = self.set_start(best[4], best[5], best[0], pool)
            o2 = self.perturb(best[0], 2 + kick % 3)
            o2, f2, l2 = self.repair(o2, pool)
            if not self.all_states(l2):
                idle = idle + 1 if self.__dict__.get('_new', 0) == n0 else 0; continue
            pool = self.pool_for(o2, pool)
            print('kick', kick, 'from', round((f2 - self.t0) / 3600, 1), 'h', flush=True)
            self.live_point(current_h=self.el_h(f2, l2))
            self.live(force=True, kick=kick, phase='kicked', current=self.legs_json(l2), note=f'kick {kick}: shake up, restart at {self.el_h(f2, l2):.1f} h')
            o2, f2, l2, pool = self.local_opt(o2, f2, l2, deadline, pool)
            e2, f2, l2, pool = self.adopt(o2, pool)
            idle = idle + 1 if self.__dict__.get('_new', 0) == n0 else 0
            if e2 < best[3] - 60 or (e2 <= best[3] + 60 and f2 <= best[1] + 60 and self.score1(o2) < self.score1(best[0]) - 60):
                best = (o2, f2, l2, e2, self.start, self.t0); last_gain = time.time()
                print('  new best', round(e2 / 3600, 1), 'h from first bus', flush=True)
                self.live_point(best_h=round(e2 / 3600, 2))
                self.live(force=True, best=self.legs_json(l2), start=self.start_name(l2), note=f'NEW BEST {e2 / 3600:.1f} h')
        if pool: pool.close()
        self.live(force=True, phase='done', note=f'done: best {best[3] / 3600:.1f} h')
        self.start, self.t0 = best[4], best[5]
        self.best_elapsed = best[3]
        return best[:3]


def _yield_cpu():
    """Run below normal priority unless BUS48_NICE=0. Sixteen workers at full load starved NordVPN's software
    encryption on the Windows box and throttled Nick's whole connection (Oct 1 2026); at lower priority the
    VPN, browser and calls get the CPU first and the search takes what is left. Workers inherit it."""
    if os.environ.get('BUS48_NICE', '1') == '0': return
    try:
        if os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL
        else: os.nice(10)
    except Exception as e: print('could not lower priority:', e, flush=True)


def main():
    _yield_cpu()
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True, help='start stop name, or "free" / "free:WV" to begin anywhere in the first state of the order'); ap.add_argument('--at', required=True); ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--seed', help='result pickle'); ap.add_argument('--seed-states', help='comma list of state abbreviations (or @stop pins) in visiting order'); ap.add_argument('--prefix', default='')
    ap.add_argument('--budget', type=float, default=900)
    # default 1 (the Mac is shared); a dedicated machine sets BUS48_WORKERS, e.g. 16 on the 24-thread Windows box
    ap.add_argument('--workers', type=int, default=int(os.environ.get('BUS48_WORKERS', 1)))
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True)
    ap.add_argument('--done', default='', help='comma list of state abbreviations already collected before --start')
    ap.add_argument('--seed-pins', action='store_true', help='keep the seed pickle\'s @stop pins (by default only states are kept)')
    ap.add_argument('--patience', type=float, default=0, help='stop early after this many seconds without a new best')
    ap.add_argument('--idle-kicks', type=int, default=10, help='stop after this many kicks in a row that score no order not already scored (0 = never)')
    ap.add_argument('--exhaustive', type=int, default=7, help='score every order of the owed states when there are at most this many (0 = never)')
    ap.add_argument('--end', help='where the route must finish: a state abbreviation ("VT"), a stop name ("Barstow"), or a point "~lon,lat,km"')
    ap.add_argument('--end-by', help='finish deadline at --end, ISO time in --tz; the search works out the latest start that makes it')
    ap.add_argument('--end-daily', action='store_true', help='the --end-by deadline repeats every day (a daily hinge): score against the first one on or after arrival')
    ap.add_argument('--fixed-start', action='store_true', help='keep the start stop and the --at clock exactly as given instead of '
                    'trying 7 start days; for a chain that only connects on some weekdays')
    ap.add_argument('--start-alt', default='', help='semicolon list of other stops the start may move to (each tried on 7 days, latest clock)')
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    global _ROUTER_ARGS
    _ROUTER_ARGS = (t0.date(), a.days)   # spawned workers load the same cached router
    R = cached_router(*_ROUTER_ARGS)
    # '#idx' is one exact stop; a name prefers an exact match ("Jacksonville" is also Jacksonville NC by substring)
    def exact(q):
        if q.startswith('#'):
            i = int(q[1:])
            if not 0 <= i < R.N: sys.exit(f'no stop #{i}')
            return i
        m = R.stops_matching(q)
        if not m: sys.exit(f'no stop matching {q!r}')
        return next((s for s in m if R.stop_name[s] == q), m[0])
    start = FREE if a.start.lower().startswith('free') else exact(a.start)
    from common import ABBR
    inv = {v: k for k, v in ABBR.items()}
    done = [R.state_names.index(inv[x.strip()]) for x in a.done.split(',') if x.strip()]
    if a.seed_states:
        # '@stop' items are pins (e.g. '@Las Vegas Amtrak Station' to leave the Chief for the Denver bus)
        seed = [x.strip() if x.strip().startswith('@') else R.state_names.index(inv[x.strip()]) for x in re.findall(r'@~[^,]+,[^,]+,[^,]+|[^,]+', a.seed_states)]   # an '@~lon,lat,km' pin keeps its commas
    else:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order']
                if (isinstance(x, (int, np.integer)) and x < N_STATES) or (a.seed_pins and isinstance(x, str) and x.startswith('@'))]
    seed = [x for x in seed if x not in done]
    if start == FREE and ':' in a.start:   # --start free:WV puts that state first (the search may still change it)
        s0 = R.state_names.index(inv[a.start.split(':')[1].strip()]); seed = [s0] + [x for x in seed if x != s0]
    alts = [exact(q.strip()) for q in a.start_alt.split(';') if q.strip()]
    end_by = datetime.fromisoformat(a.end_by).replace(tzinfo=ZoneInfo(a.tz)).timestamp() if a.end_by else None
    end = None
    if a.end:   # a state abbreviation (finish anywhere in it) or a stop name
        end = R.state_names.index(inv[a.end]) if a.end in inv else f'@{a.end}'
        if isinstance(end, str) and not end.startswith(('@~', '@#')) and not R.stops_matching(a.end): sys.exit(f'no stop matching --end {a.end!r}')
    S = Search(R, start, t0.timestamp(), [x.strip() for x in a.prefix.split(',') if x.strip()], a.workers, done, alts,
               fixed_start=a.fixed_start, end=end, end_by=end_by)
    S.end_daily = a.end_daily
    S.patience = a.patience; S.idle_kicks = a.idle_kicks; S.exhaustive = a.exhaustive
    S.live(force=True, name=os.path.basename(a.out).replace('.pkl', ''), phase='loading')
    order, f, legs = S.run(seed, a.budget)
    # distinct nonzero exits, so a caller checking status cannot file these as results: 2 unreachable, 3 missed --end-by
    if f == float('inf'): print('FINAL unreachable'); sys.exit(2)
    if S.best_elapsed == float('inf') and not end_by:
        # no deadline, so this is not a miss: no route the search tried collected all 48 states inside the window
        # (sweep 6 run 14 printed "misses --end-by ... nan h late" here, Oct 12)
        print('FINAL incomplete: no route collected all 48 states inside the timetable window; best partial ends',
              R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]))
        print(R.describe(legs)); sys.exit(3)
    if S.best_elapsed == float('inf'):   # nothing made the deadline: say how close the best route got
        late = (f - end_by) / 3600 if end_by else float('nan')
        # the sign is the verdict: a negative "late" is a route that got there first, and must not read as a miss
        # settle() records an elapsed only for a route that is complete AND on time, so an early one failed coverage
        rel = f'{late:.1f} h late' if not late < 0 else f'{-late:.1f} h early, but it does not collect every state'
        print(f'FINAL misses --end-by: best route reaches {a.end} at', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]), f'({rel})')
        print(R.describe(legs)); sys.exit(3)
    # FINAL is hours from the first bus boarded to the finish (the start clock is chosen by the search)
    first = next(l for l in legs if l[0] == 'ride')
    # Under --end-by best_elapsed is the scoring key (deadline minus first bus), not the journey: report the journey
    # (Oct 7: a 147 h front printed FINAL 246.9 h, and the record line compared that).
    elapsed = f - first[3]
    print('FINAL', round(elapsed / 3600, 1), 'h', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]))
    if end_by is not None: print('DEADLINE KEY', round(S.best_elapsed / 3600, 1), 'h (first bus to the deadline it was scored against)')
    print('START', S.start_name(legs), 'first bus', R.fmt_time(first[3], first[2]))
    if a.end: print('END', a.end, 'arrive', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]),
                    f'| record 238.83 h: {"beats it by" if elapsed < 238.83 * 3600 else "misses by"} {abs(238.83 - elapsed / 3600):.1f} h')
    print(' > '.join(R.state_names[x] if isinstance(x, int) else x for x in order))
    print(R.describe(legs))
    pickle.dump(dict(order=order, finish=f, legs=legs, start=S.start_name(legs), t0=S.t0, elapsed=elapsed, key=S.best_elapsed), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
