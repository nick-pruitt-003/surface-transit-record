"""How many options does a route actually face, standing at a stop at a time?

  python3 branching.py --route ../out/res_starttest.pkl [--within 24]

Nick's point: at any station at any hour there is a finite number of departures and fewer useful ones, so
the real decision tree is far smaller than searching over orderings of 48 states suggests. Everything built
so far searches that ordering space, which is where the 6^20 arithmetic in section 12 comes from. This
measures the other space, the one the traveller is actually in.

At every point the route alights, and at the time it alights, it counts what leaves from there (and from
anything within walking distance) in the next `--within` hours:

  departures   every connection leaving
  services     distinct routes, so twenty trips on one city bus line count once
  useful       services whose ride reaches a state the route has not collected yet

The useful count is the branching factor a search over departures would actually face.
"""
import argparse, pickle
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, WALK_MAX_KM, WALK_SPEED
import time_search as ts
from time_search import Search
from common import ABBR

ET = ZoneInfo('America/New_York')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', default='../out/res_starttest.pkl')
    ap.add_argument('--within', type=float, default=24, help='hours ahead to count options over')
    ap.add_argument('--days', type=int, default=18)
    a = ap.parse_args()
    d = pickle.load(open(a.route, 'rb'))
    R = TimeRouter(load_feeds(), datetime.fromtimestamp(d['t0'], ET).date(), a.days)
    start = R.stop_name.index(d['start']); t0 = d['t0']
    S = Search(R, start, t0, [], 1)
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, start, t0, S, None, None
    f, legs = S.evaluate(d['order'])
    ab = lambda x: ABBR[R.state_names[x]] if x >= 0 else '--'

    # where each trip goes, so an option can be called useful or not
    dep_idx = defaultdict(list)
    for k in range(len(R.dep)): dep_idx[int(R.cfrom[k])].append(k)
    trip_states = {}

    def states_of(key):
        if key in trip_states: return trip_states[key]
        fi, tid = key[0], key[1]
        f_ = R.feeds[fi]; t = f_.trips.get(tid)
        out = set()
        if t is not None:
            for x in t['stops']:
                i = R.idx.get(f_.stops[x[1]][0])
                if i is not None and R.state[i] >= 0: out.add(int(R.state[i]))
        trip_states[key] = out; return out

    rides = [l for l in legs if l[0] == 'ride']
    collected = set()
    rows = []
    for n, l in enumerate(rides):
        _, trip, bs, bt, al, at = l
        collected |= states_of((trip[0], trip[1]))
        if n + 1 >= len(rides): break
        here, now = al, at
        # foot weights are seconds, and include the 300 s penalty time_router adds beyond 150 m. The old
        # bound compared them against a made-up 1200, which hid every local-transit hop over twenty minutes,
        # the same bug that hid Memphis, Salt Lake City and Barstow from ride_search.
        walk_cap = WALK_MAX_KM * 1000 / WALK_SPEED + 300
        near = [here] + [j for j, w in R.foot.get(here, ()) if w <= walk_cap]
        seen_trip = set(); svc = {}
        for s in near:
            for k in dep_idx.get(s, ()):
                t = R.dep[k]
                if not (now <= t <= now + a.within * 3600): continue
                key = (R.ctrip[k][0], R.ctrip[k][1])
                if key in seen_trip: continue
                seen_trip.add(key)
                info = R.trip_info.get(key)
                name = (info[1] or info[0]) if info else '?'
                new = states_of(key) - collected
                cur = svc.get(name, (0, set()))
                svc[name] = (cur[0] + 1, cur[1] | new)
        useful = {k: v for k, v in svc.items() if v[1]}
        rows.append((n + 1, R.stop_name[here], now, len(seen_trip), len(svc), len(useful),
                     sorted({ab(x) for v in useful.values() for x in v[1]})))

    print(f'\noptions at each place the route gets off, within {a.within:.0f} h, {len(rows)} points\n')
    print(f'{"leg":3s} {"stop":30s} {"deps":>5s} {"services":>8s} {"useful":>6s}  new states they could reach')
    for n, name, now, ndep, nsvc, nuse, sts in rows:
        print(f'{n:3d} {name[:30]:30s} {ndep:5d} {nsvc:8d} {nuse:6d}  {" ".join(sts)[:44]}')
    u = np.array([r[5] for r in rows]); s_ = np.array([r[4] for r in rows])
    print(f'\nservices per stop: median {np.median(s_):.0f}, mean {s_.mean():.1f}, max {s_.max()}')
    print(f'USEFUL per stop:   median {np.median(u):.0f}, mean {u.mean():.1f}, max {u.max()}, '
          f'{(u <= 3).mean():.0%} of stops have 3 or fewer')
    print(f'\nbranching over departures is the median useful count, {np.median(u):.0f}, against the 6 states per '
          f'step the ordering search uses.')


if __name__ == '__main__':
    main()
