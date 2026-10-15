"""City routes that serve intercity stops but are left out of a feed's keep_routes allowlist. Leaf script.

  py city_routes.py [--km 0.5]

Nick, Oct 15 2026: where a city feed exists, a transfer between intercity carriers should ride its real routes, not the
router's modelled local hop. For every feed in data/more_gtfs/keep_routes.json this reads the full feed, finds the
routes with a stop within --km of an intercity stop in that metro, and prints those not yet kept, with the intercity
stops each one serves. A route serving two or more intercity stops links carriers; one serving a single stop is a
feeder and matters only if that stop is otherwise reached by a modelled hop.
"""
import csv, io, json, os, sys, zipfile
from collections import defaultdict
from datetime import date
import numpy as np
from time_router import cached_router, hav, DATA_DIR

KM = float(sys.argv[sys.argv.index('--km') + 1]) if '--km' in sys.argv else 0.5
R = cached_router(date(2026, 11, 9), 22, verbose=False)
nv = R.first_virtual
inter = set()
for k in range(len(R.ctrip)):
    if not getattr(R.feeds[R.ctrip[k][0]], 'city', False): inter.add(int(R.cfrom[k])); inter.add(int(R.cto[k]))
inter = sorted(i for i in inter if i < nv)
ixy = np.asarray([R.stop_xy[i] for i in inter], float)
keep = json.load(open(os.path.join(DATA_DIR, 'more_gtfs', 'keep_routes.json'), encoding='utf-8'))
for feed, kept in ([] if '--pairs' in sys.argv else keep.items()):
    p = os.path.join(DATA_DIR, 'more_gtfs', feed + '.zip')
    if not os.path.exists(p): continue
    z = zipfile.ZipFile(p); rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))
    stops = {s['stop_id']: (float(s['stop_lon']), float(s['stop_lat'])) for s in rd('stops.txt') if s.get('stop_lat')}
    if not stops: continue
    xy = np.asarray(list(stops.values())); lo, hi = xy.min(0) - 0.05, xy.max(0) + 0.05
    here = [k for k, (x, y) in enumerate(ixy) if lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]]
    routes = {r['route_id']: r for r in rd('routes.txt')}
    trip_route = {t['trip_id']: t['route_id'] for t in rd('trips.txt')}
    near = {}   # city stop -> intercity stops within KM
    for sid, (x, y) in stops.items():
        hit = [inter[k] for k in here if hav((x, y), tuple(ixy[k])) <= KM]
        if hit: near[sid] = hit
    serves = defaultdict(set)
    for st in rd('stop_times.txt'):
        if st['stop_id'] in near: serves[trip_route.get(st['trip_id'])].update(near[st['stop_id']])
    keptset = set(kept)
    rows = []
    for rid, ics in serves.items():
        r = routes.get(rid, {})
        if keptset & {rid, r.get('route_short_name', ''), r.get('route_long_name', '')}: continue
        names = sorted({R.stop_name[i][:30] for i in ics})
        rows.append((-len(names), r.get('route_short_name') or rid, r.get('route_long_name', '')[:30], names))
    if not rows: continue
    print(f'== {feed}: {len(rows)} routes serve intercity stops but are not kept')
    for n, short, long_, names in sorted(rows)[:25]:
        print(f'   {short:8} {long_:30} {-n} stop(s): {"; ".join(names)[:150]}')


def pairs():
    """--pairs: intercity stop pairs 1.5-10 km apart (past walking, so today a modelled local hop) that no kept route
    serves at both ends, with the most frequent unkept route of the same feed that does. Its output is the allowlist
    addition that replaces those hops with timetables."""
    for feed, kept in keep.items():
        p = os.path.join(DATA_DIR, 'more_gtfs', feed + '.zip')
        if not os.path.exists(p): continue
        z = zipfile.ZipFile(p); rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))
        stops = {s['stop_id']: (float(s['stop_lon']), float(s['stop_lat'])) for s in rd('stops.txt') if s.get('stop_lat')}
        xy = np.asarray(list(stops.values())); lo, hi = xy.min(0) - 0.05, xy.max(0) + 0.05
        here = [inter[k] for k, (x, y) in enumerate(ixy) if lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]]
        routes = {r['route_id']: r for r in rd('routes.txt')}
        trip_route = {t['trip_id']: t['route_id'] for t in rd('trips.txt')}
        near = {}
        for sid, (x, y) in stops.items():
            hit = [i for i in here if hav((x, y), R.stop_xy[i]) <= KM]
            if hit: near[sid] = hit
        serves = defaultdict(set); ntrips = defaultdict(set)
        for st in rd('stop_times.txt'):
            if st['stop_id'] in near:
                rid = trip_route.get(st['trip_id']); serves[rid].update(near[st['stop_id']]); ntrips[rid].add(st['trip_id'])
        keptset = set(kept)
        is_kept = lambda rid: bool(keptset & {rid, routes.get(rid, {}).get('route_short_name', ''), routes.get(rid, {}).get('route_long_name', '')})
        add = defaultdict(list)
        for a in range(len(here)):
            for b in range(a + 1, len(here)):
                i, j = here[a], here[b]
                d = hav(R.stop_xy[i], R.stop_xy[j])
                if not 1.5 < d <= 10: continue
                if any(i in s and j in s for rid, s in serves.items() if is_kept(rid)): continue
                cand = [(len(ntrips[rid]), rid) for rid, s in serves.items() if i in s and j in s and not is_kept(rid)]
                if cand:
                    n, rid = max(cand)
                    add[routes[rid].get('route_short_name') or rid].append(f'{R.stop_name[i][:26]} <-> {R.stop_name[j][:26]} ({d:.1f} km)')
        if add:
            print(f'== {feed}: add {sorted(add)}')
            for r, prs in sorted(add.items()): print(f'   {r}: ' + '; '.join(prs[:4]) + (f' (+{len(prs) - 4} more)' if len(prs) > 4 else ''))


if '--pairs' in sys.argv: pairs()
