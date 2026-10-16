"""Orphaned services and unused carriers (Nick, Oct 15). Leaf script: nothing imports it.

  py orphans.py [ROUTES_TXT]      # ROUTES_TXT: a file whose text names the agencies the good routes ride (redundancy.txt)

1. Carriers: every intercity agency with its trip count, and whether the good routes ride it.
2. Orphans: pairs of intercity stops 10-40 km apart, served by different carriers, with no footpath between them (the
   router links intercity stops by walk up to 1.5 km and by the modelled local hop up to 10 km, nothing beyond). Each
   end says whether a city transit feed has a stop within 1 km, so 'no feed' marks where a missing local feed is
   the reason the two carriers cannot meet.
"""
import os, sys
from collections import defaultdict
from datetime import date
import numpy as np
from time_router import cached_router, hav

R = cached_router(date(2026, 11, 9), 22, verbose=False)
used_txt = open(sys.argv[1], encoding='utf-8', errors='replace').read() if len(sys.argv) > 1 else ''
nv = R.first_virtual
ag_at = defaultdict(set); trips = defaultdict(set); city_stop = np.zeros(R.N, bool)
for k in range(len(R.ctrip)):
    fi, tid = R.ctrip[k][0], R.ctrip[k][1]
    f = R.feeds[fi]
    if getattr(f, 'city', False):
        city_stop[R.cfrom[k]] = city_stop[R.cto[k]] = True; continue
    ag = R.trip_info[(fi, tid)][0]
    ag_at[int(R.cfrom[k])].add(ag); ag_at[int(R.cto[k])].add(ag); trips[ag].add((fi, tid))

print('== carriers (intercity), trips in the window, ridden by the good routes?')
for ag in sorted(trips, key=lambda a: len(trips[a])):
    print(f'  {len(trips[ag]):6}  {"USED " if ag[:20] in used_txt else "     "} {ag}')

xy = np.asarray(R.stop_xy[:nv], float)
inter = [i for i in ag_at if i < nv]
city_idx = np.where(city_stop[:nv])[0]
def near_city(i):
    if not len(city_idx): return False
    d = np.hypot((xy[city_idx, 0] - xy[i, 0]) * 85, (xy[city_idx, 1] - xy[i, 1]) * 111)
    return bool((d <= 1.0).any())
foot = {i: {j for j, _ in R.foot.get(i, ())} for i in inter}
# carrier pairs that already meet somewhere (same stop, or linked by a walk or local hop): a gap between two of their
# stops is not an orphan. Indian Trails and Jefferson share the Duluth Transportation Center, so the 10.5 km between
# Kirby Plaza and the Indian Trails Superior stop is no gap (the first version listed it; Oct 15).
meet = set()
for i in inter:
    for j in foot[i] | {i}:
        for a in ag_at[i]:
            for b in ag_at.get(j, ()): meet.add((a, b)); meet.add((b, a))
buckets = defaultdict(list)
for i in inter: buckets[(int(xy[i, 0] / 0.4), int(xy[i, 1] / 0.4))].append(i)
seen = {}
for i in inter:
    bx, by = int(xy[i, 0] / 0.4), int(xy[i, 1] / 0.4)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for j in buckets.get((bx + dx, by + dy), ()):
                if j <= i or j in foot[i]: continue
                new = ag_at[j] - ag_at[i]; new_i = ag_at[i] - ag_at[j]
                if not new or not new_i: continue
                if all((a, b) in meet for a in new_i for b in new): continue
                d = hav(R.stop_xy[i], R.stop_xy[j])
                if not float(os.environ.get("ORPHAN_MIN_KM", 10)) < d <= float(os.environ.get("ORPHAN_MAX_KM", 40)): continue
                key = (frozenset(ag_at[i]), frozenset(ag_at[j]))
                if key in seen and seen[key][0] <= d: continue
                seen[key] = (d, i, j)
rows = sorted(seen.values())
print(f'\n== orphan pairs: {len(rows)} (10-40 km, different carriers, no link); "feed" = a city transit stop within 1 km')
for d, i, j in rows:
    ci, cj = near_city(i), near_city(j)
    tag = 'both ends have city transit' if ci and cj else 'NO FEED at ' + ' and '.join(
        x for x, c in ((R.stop_name[i], ci), (R.stop_name[j], cj)) if not c)
    st = R.abbr[i] or '?'
    print(f'{d:5.1f} km {st}  {R.stop_name[i][:34]:34} [{", ".join(sorted(a[:18] for a in ag_at[i]))[:60]}]\n'
          f'          <-> {R.stop_name[j][:34]:34} [{", ".join(sorted(a[:18] for a in ag_at[j]))[:60]}]  {tag}')

# carriers that meet no other intercity carrier at any stop: wholly orphaned, reachable only through city transit
alone = [ag for ag in trips if not any(b != ag for a, b in meet if a == ag)]
print(f'\n== carriers meeting no other intercity carrier ({len(alone)}): reachable only through a city transit feed, if at all')
for ag in sorted(alone): print('  ', ag, f'({len(trips[ag])} trips)')
