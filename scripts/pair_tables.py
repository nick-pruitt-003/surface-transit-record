"""Pair deadline tables: can a node still collect two owed states, in some order, and finish?

ride_search keeps a node while every owed state is collectable on its own, L[y][stop] >= t. The run-1 chain
passed that at every step and was still dead from Denver onward: 21 owed pairs at Denver and 42 at Salt Lake
City could not be collected in either order (pair_probe.py, docs/LONGRUNS.md). The per-state test cannot see
it, so the search spent 2600 s and 83000 nodes below a chain that had already lost.

The pair test is exact and uses nothing but the scans the search already trusts. L[y] is one reverse scan
seeded from y's stops with L_end. Seed it from y's stops with L[z] instead:

    L[y->z][s] = latest you can be at s and still collect y, then z, then finish

A node at (stop, t) owing y and z is dead if t > max(L[y->z][stop], L[z->y][stop]). Nothing is estimated.

Stored as P[stop, y, z] = max of the two orders, as float32 seconds relative to the deadline D (a float32
epoch would round to two minutes; relative to D it is exact to a tenth of a second over the whole span).
The diagonal is +inf so a state is never paired with itself. 48 x 47 scans, run in parallel and cached on
disk under a key of every array the scans read, so a changed router or deadline rebuilds rather than hits.

    python3 pair_tables.py            build or load, then validate: the 237 control must lose nothing and
                                      the run-1 chain must die where pair_probe said it did
"""
import hashlib, os, time
import numpy as np
from collections import OrderedDict
from time_router import N_STATES
import backward as B

HERE = os.path.dirname(os.path.abspath(__file__))

BUILD_VERSION = 'pairs-v1'
_W = {}      # worker state, inherited by fork
_TRI = {}    # n -> upper-triangle index pairs, for worst_and_mean
TRIPLES_VERSION = 'v1'   # in the triples cache name: bump when TripleTables changes how a triple is built


def _latest_from(F, D, span, nxt):
    lat, ok, k0, k1 = F.layer(nxt, False, D - span * 3600, None)
    eff, _ = F.through(ok, k0, k1, np.ones(F.R.N, bool))
    return np.maximum(lat, eff)


def _spawn_init(router_args, D, span, L, st_stops, only=None):
    """Windows has no fork: each spawned worker loads the same cached router and rebuilds the reverse index."""
    from time_router import cached_router
    R = cached_router(*router_args, verbose=False)
    _W.update(F=B.RevFast(R), D=D, span=span, L=L, st_stops=st_stops, only=only)


def _row(y):
    """every L[y->z] for one y, relative to D, float32 (only the z in _W['only'] when that is set)"""
    F, D, span, L, st_stops = _W['F'], _W['D'], _W['span'], _W['L'], _W['st_stops']
    out = np.full((N_STATES, F.R.N), -np.inf, dtype=np.float32)
    for z in (_W.get('only') if _W.get('only') is not None else range(N_STATES)):
        if z == y: continue
        nxt = {s: float(L[z][s]) for s in st_stops[y] if L[z][s] > -np.inf}
        if nxt: out[z] = (_latest_from(F, D, span, nxt) - D).astype(np.float32)
    return y, out


def fingerprint(R, F, D, span, L_end, L):
    h = hashlib.sha1()
    fa = R._fa
    for arr in (fa['dep'], fa['arr'], fa['cfrom'], fa['cto'], fa['ctrip'], np.asarray(R.state), F.ptr, F.frm, F.w, F.x):
        h.update(np.ascontiguousarray(arr).tobytes())
    # L_end and L are the seeds of every _row scan, so hashing them closes a whole class of key gap at once
    # instead of enumerating config and hoping the list is complete. Two gaps it closes, found by review:
    #
    #   --end. END_ST appeared nowhere in the key, so `--end ME` with the same dates produced the same key
    #   and loaded the Vermont table. Every P value then reads "collect y, then z, then reach Vermont" while
    #   pruning a search that has to reach Maine, and the cache hit returns before L_end is even looked at.
    #
    #   BUS48_MIN_TRANSFER. It is applied inside csa_rev at scan time rather than baked into dep/arr/F.w, so
    #   a router rebuilt at a different transfer time yields byte-identical arrays and the old key. A table
    #   built at 5 min and served to a search running at 3 is up to 120 s STRICTER per seam, and the
    #   control's tightest margin is 108 s at Trinidad CO. That run prunes the 237 route and nothing about
    #   the invocation looks like a table change, so no gate re-runs.
    #
    # Both are cheap to hash because both callers already hold L: it is the same tables the search prunes
    # with. Anything that moves a scan (the end state, the transfer time, the span, the deadline, the walk
    # speed, the feed set) moves L, and therefore moves the key.
    for arr in (L_end, L):
        h.update(np.ascontiguousarray(np.asarray(arr, dtype=np.float64)).tobytes())
    h.update(repr((float(D), float(span), N_STATES, BUILD_VERSION)).encode())
    if getattr(F, 'tag', None): h.update(F.tag.encode())   # the mirror scan; absent on RevFast, so old keys hold
    # backward.py and csa.c are the scan; this file's source is not hashed, so a fix to the validation below
    # does not throw away ten minutes of tables. Bump BUILD_VERSION when _row or the P layout changes.
    for src in ('backward.py', 'csa.c'):
        p = os.path.join(HERE, src)
        if os.path.isfile(p): h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


class PairTables:
    def __init__(self, R, D, span=260, L_end=None, L=None, cache_dir=None, workers=None, verbose=True, router_args=None,
                 F=None, only=None):
        """only: the states that can still be owed (hfcyttec, Nov 10). A segment search owes 15-40 of 197 countries
        and has its own deadline, so the full table (197 x 196 scans, cached per deadline) cost hours and was never
        switched on. With `only`, just those rows are scanned (15 owed: 210 scans); every pair touching another
        state is +inf, which can never prune, so asking about a state outside `only` is safe, just uninformative.
        A partial table is kept in memory, not on disk. only=None is the full table, exactly as before."""
        self.R, self.D = R, float(D)
        only = sorted({int(x) for x in only}) if only is not None else None
        self.only = only
        F = F if F is not None else B.RevFast(R)   # rev_tables.FwdNeg for the backward search's mirror tables
        st_stops = [[] for _ in range(N_STATES)]
        for s in range(R.N):
            if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)
        cache_dir = cache_dir or os.path.join(HERE, '..', 'out')
        # Required, not optional, because they are now part of the key. Building them here instead would
        # mean paying for them before every cache hit, which is most of what the cache saves, and both
        # callers already have them in hand: they are the tables the search prunes with.
        if L is None or L_end is None:
            raise ValueError('pass L_end and L. They are what the cache key is built from, because they '
                             'are what encodes the end state, the transfer time, the span and the '
                             'deadline. Without them the key cannot tell a Vermont table from a Maine one.')
        key = fingerprint(R, F, D, span, L_end, L)
        if only is not None:      # never the full table's key: the triple and quad caches are named by it
            key = hashlib.sha1((key + '|only|' + ','.join(map(str, only))).encode()).hexdigest()[:16]
        self.key, self.span, self.F, self.cache_dir = key, span, F, cache_dir
        self.st_stops = st_stops
        path = os.path.join(cache_dir, f'pairs_{key}.npy')
        if only is None and os.path.exists(path):
            self.P = np.load(path, mmap_mode='r')
            if verbose: print(f'pair tables from cache ({os.path.basename(path)})', flush=True)
            return
        t0 = time.time()
        _W.update(F=F, D=float(D), span=span, L=L, st_stops=st_stops, only=only)
        yz = np.full((N_STATES, N_STATES, R.N), -np.inf, dtype=np.float32)
        import multiprocessing as mp
        n = workers or max(1, (os.cpu_count() or 2) - 2)
        # fork where the platform has it (macOS, Linux); on Windows spawn workers that load the cached router
        # (router_args, as passed to cached_router), or one process when the caller cannot say which router
        if 'fork' in mp.get_all_start_methods():
            pool = mp.get_context('fork').Pool(n)
        elif router_args is not None:
            if type(F) is not B.RevFast: raise SystemExit('mirror tables (FwdNeg) need fork: build them on Linux/WSL')
            n = min(n, 12)   # each spawned worker holds its own router
            pool = mp.get_context('spawn').Pool(n, initializer=_spawn_init,
                                                initargs=(router_args, float(D), span, L, st_stops, only))
        else:
            pool = None; n = 1
        ys = range(N_STATES) if only is None else only
        rows = pool.imap_unordered(_row, ys) if pool else map(_row, ys)
        try:
            for k, (y, row) in enumerate(rows, 1):
                yz[y] = row
                if verbose and k % 8 == 0:
                    print(f'  pair tables: {k}/{len(ys)} rows in {time.time() - t0:.0f} s', flush=True)
        finally:
            if pool: pool.close(); pool.join()
        P = np.maximum(yz, yz.transpose(1, 0, 2))            # best order, [y, z, stop]
        del yz
        idx = np.arange(N_STATES); P[idx, idx, :] = np.inf
        if only is not None:
            out_ = np.ones(N_STATES, bool); out_[only] = False
            P[out_, :, :] = np.inf; P[:, out_, :] = np.inf    # not scanned: unknown, so it never prunes
        P = np.ascontiguousarray(P.transpose(2, 0, 1))        # [stop, y, z]: one node reads one 9 KB block
        if only is not None:
            self.P = P                                        # per-search: in memory, nothing written
            if verbose: print(f'pair tables for {len(only)} of {N_STATES} states built in {time.time() - t0:.0f} s '
                              f'with {n} workers ({len(only) * (len(only) - 1)} scans, in memory)', flush=True)
            return
        tmp = path + f'.{os.getpid()}.tmp.npy'
        np.save(tmp, P); os.replace(tmp, path)
        self.P = np.load(path, mmap_mode='r')
        if verbose: print(f'pair tables built in {time.time() - t0:.0f} s with {n} workers, cached as '
                          f'{os.path.basename(path)}', flush=True)

    def worst(self, stop, t, owed):
        """(margin seconds, y, z) of the tightest owed pair at this node; margin < 0 means dead"""
        o = np.asarray(owed, dtype=np.int64)
        if len(o) < 2: return np.inf, -1, -1
        sub = np.asarray(self.P[stop])[np.ix_(o, o)] - np.float32(t - self.D)
        i = int(np.argmin(sub)); a, b = divmod(i, len(o))
        return float(sub.flat[i]), int(o[a]), int(o[b])

    def worst_and_mean(self, stop, t, owed, k):
        """(tightest margin, mean of the k tightest unordered-pair margins), seconds. The first is the exact
        dead test; the second is only a ranking key (--pair-k), so it never prunes anything."""
        o = np.asarray(owed, dtype=np.int64)
        n = len(o)
        if n < 2: return np.inf, np.inf
        # Upper-triangle pairs gathered straight from the stop's flat 48x48 block: one take instead of an
        # np.ix_ submatrix plus a fresh triu_indices per call, which is what cost --pair-k 10 its 15% (Oct 19).
        tri = _TRI.get(n)
        if tri is None:
            i_, j_ = np.triu_indices(n, 1); tri = _TRI[n] = (i_, j_)
        flat = (o[tri[0]] * self.P.shape[2] + o[tri[1]])
        m = np.asarray(self.P[stop]).reshape(-1).take(flat)
        rel = np.float32(t - self.D)
        if k >= len(m): return float(m.min() - rel), float(m.mean() - rel)
        part = np.partition(m, k - 1)[:k]
        return float(part.min() - rel), float(part.mean() - rel)

    def dead(self, stop, t, owed):
        return self.worst(stop, t, owed)[0] < 0


def triple_index():
    """(T, idx) for every x < y < z: T is the (n, 3) array of triples, idx[x, y, z] its row (any order)."""
    from itertools import combinations
    T = np.array(list(combinations(range(N_STATES), 3)), dtype=np.int16)
    idx = np.full((N_STATES,) * 3, -1, dtype=np.int32)
    for i, (a, b, c) in enumerate(T):
        for p in ((a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)): idx[p] = i
    return T, idx


def full_paths(cache_dir, key):
    base = os.path.join(cache_dir, f'triples_full_{TRIPLES_VERSION}_{key}')
    return base + '.npy', base + '_done.npy'


def _tri_init_spawn(router_args, D, span, pairs_path, st_stops):
    from time_router import cached_router
    R = cached_router(*router_args, verbose=False)
    _W.update(F=B.RevFast(R), D=D, span=span, P=np.load(pairs_path, mmap_mode='r'), st_stops=st_stops, N=R.N)


def _tri_row(item):
    """one full triple row, relative to D: the max over which of the three is collected first"""
    i, (a, b, c) = item
    F, D, span, P, st_stops = _W['F'], _W['D'], _W['span'], _W['P'], _W['st_stops']
    out = None
    for x, y, z in ((a, b, c), (b, a, c), (c, a, b)):
        nxt = {s: D + float(P[s, y, z]) for s in st_stops[x] if np.isfinite(P[s, y, z])}
        if not nxt: continue
        r = _latest_from(F, D, span, nxt)
        out = r if out is None else np.maximum(out, r)
    if out is None: return i, np.full(_W['N'], -np.inf, dtype=np.float32)
    return i, (out - D).astype(np.float32)


def build_full_triples(PT, router_args=None, workers=None, verbose=True):
    """Every triple, once, into one memory-mapped (triple, stop) float32 array next to the pair table, so the
    search tests triples by lookup instead of paying three ~1.3 s scans inline for each new one (Oct 19: 4
    nodes/s instead of ~70). Resumable: a done flag per row is saved as rows land, and a restart builds only
    what is missing. Workers fork where the platform has it, else spawn and load the cached router."""
    import multiprocessing as mp
    T, _ = triple_index()
    path, done_path = full_paths(PT.cache_dir, PT.key)
    N = PT.R.N
    full = (np.lib.format.open_memmap(path, mode='r+') if os.path.exists(path) else
            np.lib.format.open_memmap(path, mode='w+', dtype=np.float32, shape=(len(T), N)))
    done = np.load(done_path) if os.path.exists(done_path) else np.zeros(len(T), dtype=bool)
    todo = [(int(i), tuple(int(v) for v in T[i])) for i in np.flatnonzero(~done)]
    if verbose: print(f'triples: {len(T)} in all, {len(todo)} to build, {N} stops, '
                      f'{len(T) * N * 4 / 1e9:.1f} GB at {os.path.basename(path)}', flush=True)
    if not todo: return path
    pairs_path = os.path.join(PT.cache_dir, f'pairs_{PT.key}.npy')
    n = workers or max(1, (os.cpu_count() or 2) - 2)
    if 'fork' in mp.get_all_start_methods():
        _W.update(F=PT.F, D=PT.D, span=PT.span, P=PT.P, st_stops=PT.st_stops, N=N)
        pool = mp.get_context('fork').Pool(n)
    else:
        if router_args is None: raise ValueError('spawn workers need router_args to load the router')
        if type(PT.F) is not B.RevFast: raise SystemExit('mirror tables (FwdNeg) need fork: build them on Linux/WSL')
        n = min(n, 12)
        pool = mp.get_context('spawn').Pool(n, initializer=_tri_init_spawn,
                                            initargs=(router_args, PT.D, PT.span, pairs_path, PT.st_stops))
    t0 = time.time(); last = t0
    try:
        for k, (i, row) in enumerate(pool.imap_unordered(_tri_row, todo, chunksize=4), 1):
            full[i] = row; done[i] = True
            if time.time() - last > 60 or k == len(todo):
                full.flush(); np.save(done_path, done); last = time.time()
                if verbose:
                    el = time.time() - t0
                    print(f'  triples: {k}/{len(todo)} in {el / 60:.0f} min, '
                          f'~{el / k * (len(todo) - k) / 60:.0f} min left', flush=True)
    finally:
        pool.close(); pool.join(); full.flush(); np.save(done_path, done)
    return path


class TripleTables:
    """Exact triple bound, one step past the pairs and built the same way (triple_probe.py, Oct 19).

    P[s, y, z] is the latest you can be at s and still collect y and z in the best order and finish. One more
    reverse scan, seeded from x's stops with P[., y, z], gives the latest anywhere to collect x first, then y
    and z, then finish. The max over which of the three goes first is T[x, y, z][stop]. A node past it is dead,
    not estimated dead. Built lazily: a node tests the few triples its own tightest pair points at (the
    tightest pair, plus the owed states tight against both), each new triple costs three scans (~1.3 s each on
    the Nov window), and the dead family shares owed sets heavily (94 triples served 300 deep nodes). Kept on
    disk next to the pair table under the same fingerprint, so a rerun starts with every triple already built.

    Measured on the saved Oct 19 frontier: X survives at every layer it reaches (triple margin +52 to +16 h);
    23-25% of sampled nodes at 30-32 states die that the pair test let through."""

    def __init__(self, PT, tries=3, verbose=True):
        self.PT, self.tries, self.verbose = PT, tries, verbose
        self.path = os.path.join(PT.cache_dir, f'triples_{TRIPLES_VERSION}_{PT.key}.npz')
        self.T = {}; self.first = {}; self.scans = 0; self.scan_s = 0.0; self.dirty = False
        # The precomputed array (build_triples.py), when there is one. Rows are used where their done flag is
        # set; anything else still falls back to the lazy build. Complete, it makes a triple a lookup, so
        # margin() tests every third state instead of the --triple-tries closest ones.
        self.full = None; self.full_done = None; self.full_complete = False
        fp, dp = full_paths(PT.cache_dir, PT.key)
        if os.path.exists(fp) and os.path.exists(dp):
            self.full = np.load(fp, mmap_mode='r'); self.full_done = np.load(dp)
            self.full_complete = bool(self.full_done.all())
            self.T3, self.idx3 = triple_index()
            # stop-major copy in RAM (4.1 GB, ~20 s): a node reads all 17296 triples at its stop as one row,
            # where the triple-major file would cost a page per triple
            self.by_stop = (np.ascontiguousarray(np.asarray(self.full).T) if self.full_complete else None)
            self._rows_key = None
            if verbose: print(f'triple tables: precomputed {int(self.full_done.sum())}/{len(self.full_done)} '
                              f'({os.path.basename(fp)})', flush=True)
        if os.path.exists(self.path):
            with np.load(self.path) as z:          # closed, or Windows refuses os.replace onto it in save()
                for k in z.files: self.T[tuple(int(v) for v in k.split('_'))] = z[k]
            if verbose: print(f'triple tables from cache: {len(self.T)} ({os.path.basename(self.path)})', flush=True)

    def _first_then(self, x, y, z):
        k = (x,) + ((y, z) if y < z else (z, y))
        if k not in self.first:
            PT = self.PT
            nxt = {s: PT.D + float(PT.P[s, y, z]) for s in PT.st_stops[x] if np.isfinite(PT.P[s, y, z])}
            t1 = time.time()
            self.first[k] = (_latest_from(PT.F, PT.D, PT.span, nxt).astype(np.float64) if nxt
                             else np.full(PT.R.N, -np.inf))
            self.scans += 1; self.scan_s += time.time() - t1
        return self.first[k]

    def table(self, x, y, z):
        if len({int(x), int(y), int(z)}) != 3: raise ValueError(f'triple with a repeated state: {(x, y, z)}')
        if self.full is not None:
            i = int(self.idx3[x, y, z])
            if self.full_done[i]: return self.full[i]
        k = tuple(sorted((int(x), int(y), int(z))))
        if k not in self.T:
            a, b, c = k
            T = np.maximum(np.maximum(self._first_then(a, b, c), self._first_then(b, a, c)), self._first_then(c, a, b))
            self.T[k] = (T - self.PT.D).astype(np.float32); self.dirty = True
            for k1 in ((a, b, c), (b, a, c), (c, a, b)): self.first.pop(k1, None)   # unique to this triple
        return self.T[k]

    def owed_rows(self, owed):
        """rows of the full table whose three states are all owed (complete table only), memoized per owed set"""
        key = tuple(owed)
        if self._rows_key != key:
            m = np.zeros(N_STATES, bool); m[list(owed)] = True
            self._rows_key, self._rows = key, np.flatnonzero(m[self.T3].all(axis=1))
        return self._rows

    def margin(self, stop, t, owed):
        """smallest triple margin (seconds): over every owed triple when the table is complete (one row read),
        else over the triples this node's tightest pair points at"""
        o = np.asarray(owed, dtype=np.int64)
        if len(o) < 3: return np.inf
        if self.full_complete:
            rows = self.owed_rows(owed)
            return float(self.by_stop[stop][rows].min() - np.float32(t - self.PT.D))
        PT = self.PT
        blk = np.asarray(PT.P[stop])
        sub = blk[np.ix_(o, o)]
        i = int(np.argmin(sub)); y, z = int(o[i // len(o)]), int(o[i % len(o)])
        rest = [int(x) for x in o if x != y and x != z]
        rest.sort(key=lambda x: min(float(blk[x, y]), float(blk[x, z])))
        rel = np.float32(t - PT.D)
        third = rest if self.full_complete else rest[:self.tries]      # a lookup each, so all of them
        return min(float(self.table(x, y, z)[stop] - rel) for x in third)

    def dead(self, stop, t, owed):
        return self.margin(stop, t, owed) < 0

    def save(self):
        if not self.dirty: return
        tmp = self.path + f'.{os.getpid()}.tmp.npz'
        np.savez(tmp, **{'_'.join(map(str, k)): v for k, v in self.T.items()})
        os.replace(tmp, self.path); self.dirty = False
        if self.verbose: print(f'triple tables: {len(self.T)} cached to {os.path.basename(self.path)}', flush=True)


QUADS_OPEN_MAX = 2048
try:   # Linux/WSL: lift the soft open-file limit to the hard one (10240 -> 1048576 here), so far more quad rows stay
    import resource   # open; at 41k quads on disk a 2048 cap was reopening rows, 4% of a proof run (Nov 1)
    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if _soft < _hard: resource.setrlimit(resource.RLIMIT_NOFILE, (_hard, _hard)); _soft = _hard
    QUADS_OPEN_MAX = max(QUADS_OPEN_MAX, min(60000, _soft // 4))
except (ImportError, ValueError, OSError):
    pass
QUADS_VERSION = 'v1'   # in the quads cache name


def _quad_init_spawn(router_args, D, span, tri_path, st_stops):
    from time_router import cached_router
    R = cached_router(*router_args, verbose=False)
    _, idx3 = triple_index()
    _W.update(F=B.RevFast(R), D=D, span=span, T3=np.load(tri_path, mmap_mode='r'), idx3=idx3,
              st_stops=st_stops, N=R.N)


def _quad_first(item):
    """w first, then the triple: the latest at every stop, relative to D (quad_probe.py's scan)"""
    w, (a, b, c) = item
    F, D, span, T3, st_stops = _W['F'], _W['D'], _W['span'], _W['T3'], _W['st_stops']
    row = T3[int(_W['idx3'][a, b, c])]
    nxt = {s: D + float(row[s]) for s in st_stops[w] if np.isfinite(row[s])}
    if not nxt: return item, np.full(_W['N'], -np.inf, dtype=np.float32)
    return item, (_latest_from(F, D, span, nxt) - D).astype(np.float32)


class QuadTables:
    """Exact quadruple bound, one step past the triples (quad_probe.py, Oct 31).

    Q[w, x, y, z][stop] is the max over which of the four is collected first of one reverse scan seeded from that
    state's stops with the full triple table of the other three. A node past it is dead, exactly. The full table is
    194580 rows (~46 GB, ~37 h), so quads are built lazily, chosen as quad_probe.py chose them: the --quad-k
    tightest owed triples at the node, each extended by every other owed state. Measured on proofB's logged
    branches (Oct 31) with k = 4: pairs killed 0 of 16 from 19/48 down, full triples 10, these quads all 16
    (median margin -19.6 h), and from 7/48 down 29 of 31.

    Built off the hot path: a node tests the candidate quads already built, queues the missing ones (closest to
    binding first) on a worker pool and moves on; it is not killed by a quad still building, which only lets it
    live, never prunes a live one. Each finished quad is its own .npy file, written atomically and read back
    memory-mapped, so a run killed by hand loses nothing and RAM is the OS page cache, not this process.
    Needs the complete triple table (build_triples.py)."""

    def __init__(self, TT, router_args, k=4, workers=4, inflight=None, verbose=True):
        if not TT.full_complete:
            raise SystemExit('--quads needs the complete triple table for this deadline: run build_triples.py')
        PT = TT.PT
        self.TT, self.PT, self.k, self.verbose = TT, PT, k, verbose
        # named by both versions: every quad is built from the triple table
        self.dir = os.path.join(PT.cache_dir, f'quads_{QUADS_VERSION}_{TRIPLES_VERSION}_{PT.key}')
        os.makedirs(self.dir, exist_ok=True)
        self.have = {tuple(int(v) for v in f[:-4].split('_')) for f in os.listdir(self.dir)
                     if f.endswith('.npy') and '.tmp' not in f}
        self.Q = OrderedDict()        # quad -> memmap row, opened on first use; LRU, since each holds a file open
        self.scans = 0; self.built = 0; self.errors = []
        self.pending = {}             # quad -> the four (w, triple) items it waits on
        self.got = {}                 # (w, triple) -> row, filled by the pool's result thread
        self.inflight = inflight or 2 * workers
        if verbose: print(f'quad tables: {len(self.have)} on disk ({os.path.basename(self.dir)})', flush=True)
        # started on the first new quad: each spawned worker holds its own router (~8 GB)
        self.pool = None; self.workers, self.router_args = workers, router_args

    def _row(self, q):
        r = self.Q.get(q)
        if r is None:
            r = self.Q[q] = np.load(os.path.join(self.dir, '_'.join(map(str, q)) + '.npy'), mmap_mode='r')
            if len(self.Q) > QUADS_OPEN_MAX:   # proofQ died at ~10k open quads on Linux's 10240-file limit (Oct 31)
                self.Q.popitem(last=False)
        else:
            self.Q.move_to_end(q)
        return r

    def _submit(self, q):
        if self.pool is None:
            import multiprocessing as mp
            PT = self.PT; tri_path, _ = full_paths(PT.cache_dir, PT.key)
            if 'fork' in mp.get_all_start_methods():     # Linux/WSL: workers share this process's router
                _W.update(F=PT.F, D=PT.D, span=PT.span, T3=np.load(tri_path, mmap_mode='r'), idx3=self.TT.idx3,
                          st_stops=PT.st_stops, N=PT.R.N)
                self.pool = mp.get_context('fork').Pool(self.workers)
            else:                                        # Windows: each spawned worker loads its own (~8 GB)
                if type(PT.F) is not B.RevFast: raise SystemExit('mirror quads (FwdNeg) need fork: run on Linux/WSL')
                self.pool = mp.get_context('spawn').Pool(self.workers, initializer=_quad_init_spawn,
                                                         initargs=(self.router_args, PT.D, PT.span, tri_path,
                                                                   PT.st_stops))
        items = [(w, tuple(sorted(set(q) - {w}))) for w in q]
        self.pending[q] = items
        for it in items:
            self.pool.apply_async(_quad_first, (it,), callback=lambda r: self.got.__setitem__(r[0], r[1]),
                                  error_callback=self.errors.append)
        self.scans += len(items)

    def _harvest(self, wait=False):
        """finish every quad whose four scans are back (all pending ones, with wait)"""
        while True:
            if self.errors: raise RuntimeError(f'quad worker failed: {self.errors[0]!r}')
            for q, items in list(self.pending.items()):
                if all(it in self.got for it in items):
                    row = np.maximum.reduce([self.got.pop(it) for it in items])
                    f = os.path.join(self.dir, '_'.join(map(str, q)) + '.npy')
                    tmp = f + f'.{os.getpid()}.tmp.npy'
                    np.save(tmp, row); os.replace(tmp, f)
                    del self.pending[q]; self.have.add(q); self.built += 1
            if not wait or not self.pending: return
            time.sleep(0.05)

    def margin_ro(self, stop, t, owed):
        """For a forked --jobs worker: (smallest margin over the built quads, candidates not built). Builds nothing;
        the main process gets the misses and queues them (want). A quad built after the fork is found on disk."""
        if len(owed) < 4: return np.inf, []
        TT = self.TT
        rel = np.float32(t - self.PT.D)
        row = TT.by_stop[stop]
        rows = TT.owed_rows(owed)
        top = rows[np.argsort(row[rows])[:self.k]]
        best, miss = np.inf, []
        for r in top:
            tri = [int(v) for v in TT.T3[r]]
            for w in owed:
                if w in tri: continue
                q = tuple(sorted(tri + [int(w)]))
                if q not in self.have:
                    if not os.path.exists(os.path.join(self.dir, '_'.join(map(str, q)) + '.npy')):
                        miss.append(q); continue
                    self.have.add(q)
                best = min(best, float(self._row(q)[stop] - rel))
                if best < 0: return best, []
        return best, miss

    def want(self, qs):
        """Main process, --jobs: collect finished builds, then queue wanted quads up to the in-flight cap."""
        if self.pending: self._harvest()
        room = max(0, self.inflight - len(self.pending))
        for q in [q for q in qs if q not in self.have and q not in self.pending][:room]:
            self._submit(q)

    def margin(self, stop, t, owed, wait=False):
        """smallest margin (seconds) over the built quads among this node's candidates. Missing ones are queued;
        with wait (the --track gate) they are built first, so the gate tests every candidate."""
        if len(owed) < 4: return np.inf
        TT = self.TT
        if self.pending: self._harvest()
        rel = np.float32(t - self.PT.D)
        row = TT.by_stop[stop]
        rows = TT.owed_rows(owed)
        top = rows[np.argsort(row[rows])[:self.k]]
        cand = {}                     # quad -> closeness: its tightest triple at this stop, for build order
        for r in top:
            tri = [int(v) for v in TT.T3[r]]
            for w in owed:
                if w in tri: continue
                q = tuple(sorted(tri + [int(w)]))
                if q not in cand:
                    cand[q] = min(float(row[TT.idx3[q[i], q[j], q[l]]])
                                  for i, j, l in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)))
        best = np.inf
        for q in cand:
            if q in self.have:
                best = min(best, float(self._row(q)[stop] - rel))
                if best < 0: return best
        miss = sorted((q for q in cand if q not in self.have and q not in self.pending), key=cand.get)
        room = len(miss) if wait else max(0, self.inflight - len(self.pending))
        for q in miss[:room]: self._submit(q)
        if wait and self.pending:
            self._harvest(wait=True)
            best = min([best] + [float(self._row(q)[stop] - rel) for q in miss])
        return best

    def dead(self, stop, t, owed):
        return self.margin(stop, t, owed) < 0

    def close(self):
        """let queued quads finish (each is saved as it lands), then stop the pool"""
        if self.pool is not None:
            self._harvest(wait=True); self.pool.close(); self.pool.join(); self.pool = None


def resolve_stop(R, name):
    """Exact-name matches for a stop, all of them. 2955 names in the router map to more than one stop
    (Huntington Bus Stop is 755 and 3322, one per feed), so `stop_name.index` and `stops_matching()[0]`
    silently pick one. Callers get the list and must decide, out loud."""
    ex = [i for i, n in enumerate(R.stop_name) if n == name]
    if not ex: raise ValueError(f'no stop named exactly {name!r}')
    return ex


def check_path(R, path, start=None):
    """Refuse a pickle whose stop indices belong to a different router.

    Stop indices are router-local. A pickle written by one build and read by another lands every leg on some
    other stop without an error: the first control test in pair_probe read Houston as the final leg and
    Hanover as Detroit, and called every node dead. Trip keys are feed identifiers and survive a rebuild, so
    each ride is checked against this router: its trip must depart `frm` and arrive at `to` at the recorded
    time. A walk must be a footpath this router has. Returns a list of problems, empty when the path fits."""
    from collections import defaultdict
    bad = []
    if start is not None and path and R.stop_name[path[0][1]] != start:
        bad.append(f'first stop is {R.stop_name[path[0][1]]!r}, pickle says {start!r}')
    by_trip = defaultdict(list)
    need = {leg[0] for leg in path if leg[0] is not None}
    for k in range(len(R.dep)):
        if R.ctrip[k] in need: by_trip[R.ctrip[k]].append(k)
    for i, leg in enumerate(path, 1):
        trip, frm, to, bt, at = leg[:5]
        if not (0 <= frm < R.N and 0 <= to < R.N):
            bad.append(f'leg {i}: stop index out of range'); continue
        if trip is None:
            if frm != to and not any(j == to for j, _w in R.foot.get(frm, ())) \
                    and not any(j == frm for j, _w in R.foot.get(to, ())):
                bad.append(f'leg {i}: no footpath {R.stop_name[frm][:24]} -> {R.stop_name[to][:24]}')
            continue
        cs = by_trip.get(trip)
        if not cs: bad.append(f'leg {i}: trip {trip} not in this router'); continue
        seg = leg[6] if len(leg) > 6 else None
        if seg:
            # connection indices are router-local as well: both must be in range and on this trip
            if not all(0 <= int(k) < len(R.dep) and R.ctrip[int(k)] == trip for k in seg):
                bad.append(f'leg {i}: its connections {tuple(seg)} are not trip {trip} in this router')
                continue
        # frm is where the node stood; ride_search boards at it or at any stop a footpath reaches from it
        # (leg 1 of the run-1 chain stands at Huntington 755 and boards at Huntington 3322)
        near = {frm} | {j for j, _w in R.foot.get(frm, ())}
        if not any(int(R.cfrom[k]) in near for k in cs):
            bad.append(f'leg {i}: trip {trip} never leaves {R.stop_name[frm][:24]} or anywhere walkable from it')
        walked = len(leg) > 5 and leg[5] is not None and leg[5] >= 0     # a walk-in's clock includes the walk
        if not any(int(R.cto[k]) == to and (walked or abs(float(R.arr[k]) - at) < 1) for k in cs):
            bad.append(f'leg {i}: trip {trip} does not reach {R.stop_name[to][:24]} at the recorded time')
    return bad


def leg_states(R, leg, trip_conns):
    """Every state a leg is in. From 9081646 a leg carries seg = (board connection, alight connection) and
    that stretch is exact, loops included; older legs fall back to the trip's connections by time."""
    trip, frm, to, bt, at = leg[:5]
    walk = leg[5] if len(leg) > 5 else None
    seg = leg[6] if len(leg) > 6 else None
    out = set()
    if trip is not None:
        if seg:
            lo_, hi_ = sorted((float(R.dep[seg[0]]), float(R.dep[seg[1]])))
            ks = [k for k in trip_conns.get(trip, ()) if lo_ <= R.dep[k] <= hi_]
        else:
            ks = [k for k in trip_conns.get(trip, ()) if bt <= R.dep[k] and R.arr[k] <= at]
        for k in ks:
            for s_ in (int(R.cfrom[k]), int(R.cto[k])):
                if R.state[s_] >= 0: out.add(int(R.state[s_]))
    if R.state[to] >= 0: out.add(int(R.state[to]))
    if walk is not None and walk >= 0: out.add(int(walk))
    return out


def main():
    import argparse, pickle
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from time_router import cached_router
    from common import ABBR
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-05T00:54')
    ap.add_argument('--by', default='2026-11-14T22:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--control', default='../out/hun_ms_meteor.pkl')
    ap.add_argument('--control-at', default='2026-11-05T00:30')
    ap.add_argument('--control-start', default='Huntington Bus Stop')
    ap.add_argument('--route', default='../out/deep31.pkl')
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    router_args = (datetime.fromisoformat(a.at).date(), a.days)
    R = cached_router(*router_args)
    ab = lambda x: ABBR[R.state_names[x]]
    inv = {v: k for k, v in ABBR.items()}
    end_st = R.state_names.index(inv[a.end])
    F = B.RevFast(R)
    st_stops = [[s for s in range(R.N) if R.state[s] == y] for y in range(N_STATES)]
    L_end = _latest_from(F, D, a.span, {s: D for s in st_stops[end_st]})
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        nxt = {s: float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
        if nxt: L[y] = _latest_from(F, D, a.span, nxt)
    PT = PairTables(R, D, a.span, L_end=L_end, L=L, router_args=router_args)

    # Falsification: every node of the control, from its first leg, must survive. It finishes inside D.
    import time_search as ts_
    from time_search import Search
    tc = datetime.fromisoformat(a.control_at).replace(tzinfo=tz).timestamp()
    order = pickle.load(open(a.control, 'rb'))['order']
    tried = []
    for hun_ in resolve_stop(R, a.control_start):      # every exact match, not the first; keep the fastest
        S = Search(R, hun_, tc, [], 1)
        ts_.bind(R, hun_, tc, S)
        fin_, legs_ = S.evaluate(order)
        tried.append((fin_, hun_, legs_))
    fin, hun, legs = min(tried, key=lambda x: x[0])
    print(f'control start {a.control_start!r}: stops ' + ', '.join(f'{h} finishes {(f - tc) / 3600:.2f} h'
          for f, h, _ in tried) + f'; using {hun}', flush=True)
    from collections import defaultdict
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)
    have = {int(R.state[hun])} if R.state[hun] >= 0 else set()
    tight = (np.inf, None)
    n_nodes = killed = 0
    for i, l in enumerate(legs, 1):
        if l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            have |= {int(R.state[R.cto[k]]) for k in trip_conns.get(trip, ()) if bt <= R.dep[k] and R.arr[k] <= at
                     and R.state[R.cto[k]] >= 0}
            for s_ in (bs, al):
                if R.state[s_] >= 0: have.add(int(R.state[s_]))
            stop, t = al, at
        elif l[0] == 'walk':
            _, frm, to, t0w, t1w = l[:5]
            if R.state[to] >= 0: have.add(int(R.state[to]))
            stop, t = (frm if to >= R.first_virtual else to), t1w
        else:
            continue
        owed = [y for y in range(N_STATES) if y not in have]
        m, y, z = PT.worst(stop, t, owed)
        n_nodes += 1
        if m < tight[0]: tight = (m, f'leg {i} {R.stop_name[stop][:24]} {ab(y)}&{ab(z)}' if y >= 0 else '')
        if m < 0:
            killed += 1
            print(f'  CONTROL KILLED at leg {i}: {R.stop_name[stop][:28]}, {ab(y)} & {ab(z)} miss by {-m / 3600:.1f} h')
    print(f'control: {len(have)}/{N_STATES} states, {n_nodes} nodes, {killed} killed; tightest pair margin '
          f'{tight[0] / 3600:+.2f} h ({tight[1]})', flush=True)

    # The run-1 chain must die, and where pair_probe said: Denver, CA & WA by 15.5 h.
    if a.route and os.path.exists(a.route):
        d = pickle.load(open(a.route, 'rb'))
        bad = check_path(R, d['path'], d.get('start'))
        if bad:
            print(f'REFUSED {a.route}: its stop indices do not fit this router ({len(bad)} problems)')
            for b in bad[:5]: print('   ', b)
            return
        have = set()
        for i, leg in enumerate(d['path'], 1):
            trip, frm, to, bt, at = leg[:5]
            if not have and R.state[frm] >= 0: have.add(int(R.state[frm]))
            have |= leg_states(R, leg, trip_conns)
            col = set(d['collected']) if i == len(d['path']) else have
            owed = [y for y in range(N_STATES) if y not in col]
            m, y, z = PT.worst(to, at, owed)
            print(f'  chain ride {i:2d} {R.stop_name[to][:26]:26s} {len(col):2d} held  tightest '
                  + (f'{ab(y)}&{ab(z)} {m / 3600:+.1f} h' if y >= 0 else '-') + ('   DEAD' if m < 0 else ''))


if __name__ == '__main__':
    main()
