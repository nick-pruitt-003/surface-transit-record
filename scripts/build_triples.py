"""Precompute every triple table for one deadline, so ride_search --triples push tests triples by lookup.

Sets up exactly what ride_search does for the same --at/--by/--tz/--end/--days/--span (the same router, the
same deadline tables, so the same pair-table key), then fills triples_full_<version>_<pairkey>.npy next to the
pair table. Resumable: rerun the same command and it builds only the rows not yet done. Leaf script.

  py build_triples.py --at 2026-11-12T22:10 --by 2026-11-22T15:10 --tz America/Denver --end MN
  py build_triples.py ... --back 232.13      the backward search's mirror tables (rev_tables.py): start floor
                                             --by minus that many hours, as ride_search --dir backward --target
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR
import backward as B
from pair_tables import PairTables, _latest_from, build_full_triples

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', required=True); ap.add_argument('--by', required=True)
    ap.add_argument('--tz', required=True); ap.add_argument('--end', required=True)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--workers', type=int)
    ap.add_argument('--back', type=float, help='mirror tables for --dir backward with this --target (hours)')
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    when = datetime.fromisoformat(a.at).replace(tzinfo=tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    router_args = (when.date(), a.days)                 # as ride_search, forward
    R = cached_router(*router_args)
    inv = {v: k for k, v in ABBR.items()}
    end_st = R.state_names.index(inv[a.end])
    st_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    if a.back:
        from rev_tables import FwdNeg, single_tables
        T_min = D - a.back * 3600
        Fm = FwdNeg(R, D)
        Lm_end, Lm = single_tables(R, Fm, T_min, st_stops)
        PT = PairTables(R, -T_min, a.span, L_end=Lm_end, L=Lm, router_args=router_args, F=Fm)
        print(f'pair key {PT.key} (mirror)', flush=True)
        build_full_triples(PT, router_args=router_args, workers=a.workers)
        print('TRIPLES BUILT', flush=True)
        raise SystemExit(0)
    F = B.RevFast(R)
    L_end = _latest_from(F, D, a.span, {int(s): D for s in st_stops[end_st]})
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        nxt = {int(s): float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
        if nxt: L[y] = _latest_from(F, D, a.span, nxt)
    PT = PairTables(R, D, a.span, L_end=L_end, L=L, router_args=router_args)
    print(f'pair key {PT.key}', flush=True)
    build_full_triples(PT, router_args=router_args, workers=a.workers)
    print('TRIPLES BUILT', flush=True)
