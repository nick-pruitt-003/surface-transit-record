"""Three more of the 237 control's structural moves, each tested against the best route that avoids it.
Leaf script: nothing imports it. Companion to corridor_probe.py (the Pacific Northwest corridor).

  memphis   Mississippi on foot from Holmes, inside the Memphis layover, then the Jefferson bus from
            Airways Transit Center. Against every other way of collecting MS and getting back to it.
  meteor    GA SC NC VA from Jacksonville to Washington. With the Silver Meteor against without it.
  stgeorge  From Salt Lake City to Las Vegas collecting AZ and NV. Through Saint George against around it.

Each case is run from the control's own node (re-evaluated through the router, not read from stored legs)
and at every 2 h across that day. "Avoiding" routes come from every order of the targets plus forced
detours through named alternatives, so they are routes the router actually finds, not every conceivable one.

    nice -n 19 python3 corridor_checks.py
"""
import itertools, pickle
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR, within_km
import time_search as ts_
from time_search import Search

TZ = ZoneInfo('America/New_York')


def main():
    R = cached_router(datetime(2026, 9, 24).date(), 20, verbose=False)
    inv = {v: k for k, v in ABBR.items()}
    S = lambda x: R.state_names.index(inv[x])
    xy = np.asarray(R.stop_xy, dtype=float)

    def near(lat, lon, km):
        return set(within_km(xy, lon, lat, km).tolist())
    area = lambda lat, lon, km=10: f'@~{lon},{lat},{km}'
    tc_ = defaultdict(list)
    for k in range(len(R.dep)): tc_[R.ctrip[k]].append(k)

    def rides(legs):
        for l in legs:
            if l[0] == 'ride': yield l

    def passes(legs, stops):
        for l in legs:
            if l[0] == 'ride':
                _, trip, bs, bt, al, at = l
                if bs in stops or al in stops: return True
                for k in tc_.get(trip, ()):
                    if bt <= R.dep[k] and R.arr[k] <= at and (int(R.cfrom[k]) in stops or int(R.cto[k]) in stops):
                        return True
            elif l[0] == 'walk' and (l[1] in stops or l[2] in stops):
                return True
        return False

    # the control's own clock at each case's start, from the router rather than stored indices
    tc = datetime(2026, 9, 24, 0, 30, tzinfo=TZ).timestamp()
    hun = [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']
    best_ = None
    for h in hun:
        Sx = Search(R, h, tc, [], 1)
        ts_.bind(R, h, tc, Sx)
        f, legs = Sx.evaluate(pickle.load(open('../out/hun_ms_meteor.pkl', 'rb'))['order'])
        if best_ is None or f < best_[0]: best_ = (f, legs)
    _, clegs = best_

    def first_arrival(name_part):
        for l in clegs:
            if l[0] == 'ride' and name_part in R.stop_name[l[4]]: return l[4], l[5]
        return None, None

    memphis = near(35.1495, -90.0490, 12)
    jax = near(30.3322, -81.6557, 12)
    slc = near(40.7608, -111.8910, 10)
    stg = near(37.0965, -113.5684, 15)
    airways = area(35.0925, -89.9665, 1.5)          # Airways Transit Center, where the Jefferson bus leaves
    dc = area(38.8973, -77.0063, 3)                  # Washington Union Station
    vegas = area(36.1699, -115.1398, 12)

    def is_walkin_ms(legs):
        return any(l[0] == 'walk' and l[2] >= R.first_virtual and R.state[l[2]] == S('MS') for l in legs)

    # Amtrak trips carry no name in the router (trip_info is empty for them), so read the feed: the first
    # version of this test matched on the name, found none, and filed every Meteor route under "without it".
    import csv, io, zipfile
    z = zipfile.ZipFile('../data/amtrak_gtfs.zip')
    rname = {r['route_id']: r['route_long_name'] for r in csv.DictReader(io.TextIOWrapper(z.open('routes.txt')))}
    amtrak = {r['trip_id']: rname.get(r['route_id'], '') for r in csv.DictReader(io.TextIOWrapper(z.open('trips.txt')))}
    train = lambda trip: amtrak.get(str(trip[1]), '') if isinstance(trip, tuple) and trip[0] == 1 else ''

    def is_meteor(legs):
        return any(train(l[1]) == 'Silver Meteor' for l in rides(legs))

    def meteor_label(legs):
        names = [train(l[1]) for l in rides(legs) if train(l[1])]
        return '+'.join(dict.fromkeys(names)) or 'bus only'

    cases = [
        ('memphis', 'Memphis', memphis,
         [[S('MS'), airways]] + [[area(*c), S('MS'), airways] for c in ((34.2576, -88.7034), (32.2988, -90.1848),
                                                                        (34.9868, -90.0023))],
         is_walkin_ms, 'MS on foot at the Memphis line', 'MS any other way'),
        ('meteor', 'Jacksonville', jax,
         [list(p) + [dc] for p in itertools.permutations([S('GA'), S('SC'), S('NC'), S('VA')])]
         + [[area(33.7490, -84.3880), S('GA'), S('SC'), S('NC'), S('VA'), dc],
            [area(35.2271, -80.8431), S('GA'), S('SC'), S('NC'), S('VA'), dc]],
         is_meteor, 'with the Silver Meteor', 'without it'),
        ('stgeorge', 'Salt Lake City', slc,
         [[S('AZ'), S('NV'), vegas], [S('NV'), S('AZ'), vegas]]
         + [[area(*c), S('AZ'), S('NV'), vegas] for c in ((39.0639, -108.5506), (40.7391, -114.0733), (39.5296, -119.8138))],
         lambda legs: passes(legs, stg), 'through Saint George', 'around it'),
    ]
    for key, where, starts, orders, test, yes, no in cases:
        stop0, t_ctrl = first_arrival(where)
        st = np.array(sorted(starts), dtype=np.int64)
        print(f'\n== {key}: from {where}; the control is there at '
              + (f'{datetime.fromtimestamp(t_ctrl, TZ):%a %H:%M}' if t_ctrl else 'n/a'))
        print(f'   {"leave":11s} {yes:>32s}  {no:>22s}  gap')
        day = datetime.fromtimestamp(t_ctrl, TZ).replace(hour=0, minute=0) if t_ctrl else None
        times = ([t_ctrl] if t_ctrl else []) + ([(day + timedelta(hours=h)).timestamp() for h in range(0, 24, 2)] if day else [])
        gaps = []
        for t0 in times:
            best = {True: np.inf, False: np.inf}; via_ = ['']
            for o in orders:
                try: te, legs = R._route_fast(st, float(t0), o)
                except Exception: continue
                if te is None or not np.isfinite(te): continue
                v = bool(test(legs))
                if (te - t0) / 3600 < best[v]:
                    best[v] = (te - t0) / 3600
                    if key == 'meteor' and not v: via_[0] = meteor_label(legs)
            g = best[False] - best[True]; gaps.append(g)
            tag = ' (control)' if t0 == t_ctrl else ''
            print(f'   {datetime.fromtimestamp(t0, TZ):%a %H:%M}{tag:10s} {best[True]:28.1f} h  {best[False]:20.1f} h  {g:+.1f} h' + (f'   (without: {via_[0]})' if via_[0] else ''),
                  flush=True)
        fin = [g for g in gaps if np.isfinite(g)]
        print(f'   pattern fastest in {sum(g > 0 for g in gaps)}/{len(gaps)}; smallest finite gap '
              + (f'{min(fin):+.1f} h' if fin else 'n/a (no alternative ever finished)'))


if __name__ == '__main__':
    main()
