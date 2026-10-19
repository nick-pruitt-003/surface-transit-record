"""Frequency report: which links in the network run only a few times a day.

Two views, both from the loaded timetables (one week):
  1. Every ride leg of a saved route, with how many direct departures a day serve the same boarding and
     alighting area (1 km), so the route's once-daily links stand out.
  2. Every pair of hubs (hub_table.HUBS) joined by a direct trip, with departures a day and fastest ride,
     keeping the sparse ones (<= --max per day). These are the network's structural bottlenecks.

  python3 frequency_report.py --route ../out/hun_ms_meteor.pkl --start "Huntington Bus Stop" \
      --at 2026-11-05T00:30 --tz America/New_York [--max 3] > ../out/frequency_report.txt
"""
import argparse, pickle
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds
from time_search import Search
from hub_table import HUBS
from common import within_km

DAYS = 14   # long enough for a whole route; per-day counts are averaged over it


def near(xy, lon, lat, km):
    return set(within_km(xy, lon, lat, km).tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route'); ap.add_argument('--start'); ap.add_argument('--at'); ap.add_argument('--tz')
    ap.add_argument('--max', type=float, default=3); ap.add_argument('--hub-km', type=float, default=6)
    ap.add_argument('--max-ride', type=float, default=14, help='only hub pairs whose fastest direct ride is at most this (h)')
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), t0.date(), DAYS)
    xy = np.asarray(R.stop_xy, dtype=float)
    # per trip: ordered (stop, dep, arr) from its connections
    trips = defaultdict(list)
    for k, key in enumerate(R.ctrip): trips[key].append(k)
    seq = {}
    for key, ks in trips.items():
        ks.sort(key=lambda k: R.dep[k])
        seq[key] = [(int(R.cfrom[k]), float(R.dep[k])) for k in ks] + [(int(R.cto[ks[-1]]), float(R.arr[ks[-1]]))]
    def agency(key):
        ag, rt, hs = R.trip_info[(key[0], key[1])]
        return f'{ag}: {rt or hs}'

    def direct(A, B):
        """(departures per day, fastest ride h, example service) for trips boarding in A and alighting later in B."""
        deps, best, ex = set(), None, ''
        for key, s in seq.items():
            ia = next((i for i, (st, _) in enumerate(s) if st in A), None)
            if ia is None: continue
            ib = next((j for j in range(ia + 1, len(s)) if s[j][0] in B), None)
            if ib is None: continue
            deps.add(round(s[ia][1] / 300)); ride = (s[ib][1] - s[ia][1]) / 3600
            if best is None or ride < best: best, ex = ride, str(agency(key))[:60]
        return len(deps) / DAYS, best, ex

    if a.route:
        st = R.stops_matching(a.start)[0]; S = Search(R, st, t0.timestamp(), [], 1)
        d = pickle.load(open(a.route, 'rb')); f, legs = S.evaluate(d['order'])
        print(f'ROUTE LEGS ({(f - t0.timestamp()) / 3600:.1f} h from clock start), sparsest first\n')
        rows, prev = [], None
        for l in legs:
            if l[0] != 'ride': prev = l[4] if l[0] == 'walk' else prev; continue
            _, trip, bs, bt, al, at = l
            per_day, ride, _ = direct(near(xy, *xy[bs], 1.0), near(xy, *xy[al], 1.0))
            wait = (bt - prev) / 3600 if prev else 0.0
            rows.append((per_day, R.stop_name[bs], R.stop_name[al], R.fmt_time(bt, bs), (at - bt) / 3600, wait, str(agency(trip))[:45]))
            prev = at
        for per_day, a_, b_, when, ride, wait, how in sorted(rows, key=lambda r: r[0]):
            print(f'  {per_day:4.1f}/day  {a_[:28]:28s} -> {b_[:28]:28s} {when}  ride {ride:4.1f} h  waited {wait:4.1f} h  {how}')
        print()

    print(f'HUB PAIRS WITH <= {a.max:g} DIRECT DEPARTURES A DAY (hub = stops within {a.hub_km:g} km)\n')
    members = {h: near(xy, lon, lat, a.hub_km) for h, (lon, lat) in HUBS.items()}
    stop_hubs = defaultdict(list)
    for h, ms in members.items():
        for s_ in ms: stop_hubs[s_].append(h)
    pair_deps, pair_best = defaultdict(set), {}
    for key, s_ in seq.items():   # one pass: every hub the trip visits, in order, first visit only
        visits, seen = [], set()
        for st_, t in s_:
            for h in stop_hubs.get(st_, ()):
                if h not in seen: seen.add(h); visits.append((h, t))
        for i in range(len(visits)):
            for j in range(i + 1, len(visits)):
                (h, ti), (g, tj) = visits[i], visits[j]
                pair_deps[(h, g)].add(round(ti / 300)); ride = (tj - ti) / 3600
                if (h, g) not in pair_best or ride < pair_best[(h, g)][0]: pair_best[(h, g)] = (ride, agency(key)[:60])
    out = [(len(v) / DAYS, pair_best[k][0], k[0], k[1], pair_best[k][1]) for k, v in pair_deps.items() if len(v) / DAYS <= a.max and pair_best[k][0] <= a.max_ride]
    for per_day, ride, h, g, ex in sorted(out, key=lambda r: (r[0], r[1])):
        print(f'  {per_day:4.1f}/day  {h:15s} -> {g:15s} fastest {ride:5.1f} h  {ex}')


if __name__ == '__main__':
    main()
