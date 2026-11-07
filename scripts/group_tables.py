"""Hinge-group deadline tables: the exact latest time at every stop from which a whole group of states can still be
collected (in the best order) and the end reached by the deadline.

A group is a set of states that hang on sparse services in one region (the central Pacific's weekly flights, Central
Africa's). The pair key looks at the tightest pair of owed states; a chain that leaves the Pacific early still has
every Pacific pair in reach, and only the group as a whole is not. These tables measure the group as a whole.

For a group G and every subset S of it, T[S][stop] is built by dynamic programming over subsets, with the same
reverse scan the pair and triple tables use: collecting y first and then the rest of S means reaching one of y's
stops by T[S - y] there, so

    T[{y}] = L[y],   T[S] = max over y in S of latest_from(seeds at y's stops = T[S - y]).

That is exact for collecting S and finishing, and ignores every state outside S, so it can only be later than the
truth: permissive, the bound this project requires. A node's group margin is min over groups of
T[G & owed][stop] - t; below zero the node is dead. Tables are float32 relative to the deadline D, like the pairs.

Cost: a group of k states needs k * 2^(k-1) scans. Built once per (pair-table key, groups) and cached in out/.
"""
import hashlib, json, os, time
import numpy as np
import pair_tables as PTM
from pair_tables import _latest_from

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS_VERSION = 'g1'


def _scan(item):
    key, nxt = item
    W = PTM._W
    return key, (_latest_from(W['F'], W['D'], W['span'], nxt) - W['D']).astype(np.float32)


class GroupTables:
    def __init__(self, PT, L, groups, router_args=None, workers=None, verbose=True):
        """PT: the PairTables (for its scan, deadline, span and cache key). L: the single-state deadline tables
        (absolute times, the ones PairTables was built from). groups: lists of state indices."""
        self.PT, self.D = PT, PT.D
        self.groups = [sorted(set(int(y) for y in g)) for g in groups if len(set(g)) >= 2]
        tag = hashlib.sha1(json.dumps([PT.key, self.groups, GROUPS_VERSION]).encode()).hexdigest()[:12]
        self.path = os.path.join(PT.cache_dir, f'groups_{tag}.npz')
        self.T = []                                   # per group: [2^k, N] float32, row = subset bitmask
        if os.path.exists(self.path):
            with np.load(self.path) as z:
                self.T = [z[f'g{i}'] for i in range(len(self.groups))]
            if verbose: print(f'group tables from cache: {len(self.groups)} groups ({os.path.basename(self.path)})',
                              flush=True)
        else:
            self._build(L, router_args, workers, verbose)
        self.member = [dict((y, b) for b, y in enumerate(g)) for g in self.groups]

    def _build(self, L, router_args, workers, verbose):
        PT, N = self.PT, self.PT.R.N
        t0 = time.time()
        import multiprocessing as mp
        n = workers or max(1, (os.cpu_count() or 2) - 2)
        if 'fork' in mp.get_all_start_methods():
            PTM._W.update(F=PT.F, D=PT.D, span=PT.span)
            pool = mp.get_context('fork').Pool(n)
        elif router_args is not None:
            n = min(n, 12)                            # each spawned worker holds its own router
            pool = mp.get_context('spawn').Pool(n, initializer=PTM._spawn_init,
                                                initargs=(router_args, PT.D, PT.span, None, None))
        else:
            PTM._W.update(F=PT.F, D=PT.D, span=PT.span); pool = None; n = 1
        T = []
        for g in self.groups:
            k = len(g)
            t = np.full((1 << k, N), -np.inf, dtype=np.float32)
            for b, y in enumerate(g):
                t[1 << b] = (np.asarray(L[y], dtype=np.float64) - PT.D).astype(np.float32)
            T.append(t)
        try:
            kmax = max(len(g) for g in self.groups)
            for size in range(2, kmax + 1):          # layer by subset size: each needs only the layer below
                items = []
                for gi, g in enumerate(self.groups):
                    k = len(g)
                    for m in range(1 << k):
                        if bin(m).count('1') != size: continue
                        for b, y in enumerate(g):
                            if not m >> b & 1: continue
                            prev = T[gi][m & ~(1 << b)]
                            nxt = {s: PT.D + float(prev[s]) for s in PT.st_stops[y] if np.isfinite(prev[s])}
                            if nxt: items.append(((gi, m), nxt))
                res = pool.imap_unordered(_scan, items, chunksize=4) if pool else map(_scan, items)
                for (gi, m), row in res:
                    np.maximum(T[gi][m], row, out=T[gi][m])
                if verbose: print(f'  group tables: subsets of {size} done ({len(items)} scans, '
                                  f'{time.time() - t0:.0f} s)', flush=True)
        finally:
            if pool: pool.close(); pool.join()
        self.T = T
        tmp = self.path + f'.{os.getpid()}.tmp.npz'
        np.savez(tmp, **{f'g{i}': t for i, t in enumerate(T)})
        os.replace(tmp, self.path)
        if verbose: print(f'group tables built in {time.time() - t0:.0f} s with {n} workers, cached as '
                          f'{os.path.basename(self.path)}', flush=True)

    def margin(self, stop, t, collected):
        """(seconds, group index) of the tightest owed group at this node; inf when no group has 2+ owed"""
        rel = np.float32(t - self.D)
        best, which = np.inf, -1
        for gi, g in enumerate(self.groups):
            m = 0
            for b, y in enumerate(g):
                if y not in collected: m |= 1 << b
            if m & (m - 1) == 0: continue            # fewer than two owed: the single tables already cover it
            v = float(self.T[gi][m, stop] - rel)
            if v < best: best, which = v, gi
        return best, which
