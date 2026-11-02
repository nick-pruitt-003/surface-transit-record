"""Mirror deadline tables for the backward search: the earliest you can be at a stop having already collected a set
of states, starting anywhere no earlier than T_min (Nov 1 2026).

The forward tables (pair_tables.py) are all built from one primitive, a reverse scan seeded with "latest you can be
here and still finish" times. The backward search fixes the finish and leaves the start free, so its question runs
the other way: could the owed states still have been collected before standing here at t? That is a forward scan
seeded with "earliest you can be here" times, and with the start free the single-state seed is simply T_min at
every stop of the state (starting there is the earliest way to have visited it).

FwdNeg presents that forward scan through RevFast's interface with every time negated (-earliest is a "latest", and
-t > -E is t < E), so PairTables, the full triple build and QuadTables run unchanged on it: pass
PairTables(..., F=FwdNeg(R, t_hi)) with D = -T_min and test nodes at -t. Seeds board with MIN_TRANSFER of credit, so
a chain still aboard the vehicle it reached a state on is never charged a transfer it did not make; the bound is
permissive by up to that much, never strict (CLAUDE.md: permissive thresholds only).

Linux/WSL only: the table builders fork, and a spawned worker would rebuild RevFast, not this.
Kept out of backward.py on purpose: backward.py's source is hashed into every forward table key.
"""
import numpy as np
from time_router import N_STATES, MIN_TRANSFER
import backward as B


class FwdNeg(B.RevFast):
    """Forward earliest-arrival scans, negated. t_hi: no connection departing after it is scanned (the finish)."""
    tag = 'fwdneg-v1'   # in the table fingerprint, so a mirror table never loads as a forward one

    def __init__(self, R, t_hi):
        super().__init__(R)                     # the reverse footpath arrays: fingerprinted, not scanned
        self.t_hi = float(t_hi)
        fa = R._fa
        self.n_end = int(np.searchsorted(fa['dep'], self.t_hi, side='right'))
        self.zero = np.zeros(R.N, dtype=np.uint8)

    def layer(self, nxt, guard, lo, ns=None):
        """nxt {stop: -earliest}; returns (-earliest[N], None, 0, -1). guard and lo are ignored: the tables are
        built with guard=False, and the scan is bounded above by t_hi instead of below by lo."""
        R = self.R; fa = R._fa; p = R._ptrs; D, I, Bt = R._ct
        best = np.full(R.N, np.inf); lt = np.full(R.N, -1, dtype=np.int32)
        for s, L in nxt.items():
            e = -float(L) - MIN_TRANSFER
            if e < best[s]: best[s] = e
        k0 = int(np.searchsorted(fa['dep'], float(best.min())))
        if k0 < self.n_end:
            rc = R._fast.csa_scan(self.n_end, p['dep'], p['arr'], p['cfrom'], p['cto'], p['ctrip'], k0, R.N,
                                  len(R.trip_ids), p['ptr'], p['to'], p['w'], p['fx'], best.ctypes.data_as(D),
                                  lt.ctypes.data_as(I), self.zero.ctypes.data_as(Bt), float(MIN_TRANSFER), np.inf,
                                  *(None,) * 7)
            if rc != 0: raise MemoryError('csa_scan failed')
        return -best, None, 0, -1

    def through(self, ok, k0, k1, mask):
        """Nothing to add: a forward scan already lands on every stop a vehicle reaches, alighting or not."""
        return np.full(self.R.N, -np.inf), None


def single_tables(R, F, T_min, st_stops):
    """(L_end, L) in the negated frame: L_end = -T_min everywhere (the start is free), L[y] = -earliest at each stop
    having visited y."""
    L_end = np.full(R.N, -float(T_min))
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        if st_stops[y]:
            L[y] = F.layer({s: -float(T_min) for s in st_stops[y]}, False, None)[0]
    return L_end, L
