"""Which Tornado stops can the router actually connect to another carrier? Leaf script: nothing imports it.

  py tornado_links.py [--at 2026-11-09 --days 22]

For every stop a Tornado (or El Expreso) trip calls at, scans forward from it using only walks and local transit
(city feeds and the hand-entered local services), at several clock times, and reports the earliest other-carrier
stop it reaches (intercity bus, Amtrak, commuter rail). A stop with no link inside the horizon is flagged when
another carrier stops within 10 km (a hop or a city feed would open a transfer), and when it is a run's first or
last stop in its state and lies near a border (where the state its point falls in decides a start or an end).
Writes out/tornado_links.csv and prints the flagged stops.
"""
import argparse, csv, os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, hav

TORNADO = ('Tornado Bus', 'El Expreso')
LOCAL_MANUAL = ('TCATA', 'MBTA', 'Pittsburgh', 'Weirton', 'Omnitrans', 'TARTA', 'On foot', 'Big River', 'Standing Rock',
                'Navajo', 'UCAP')   # hand-entered agencies that are local transit, not a carrier
HORIZON = 3 * 3600
SAMPLES = [(1, 9), (1, 14), (1, 20), (5, 11)]   # (weekday offset from Monday, local hour): Tue 9/14/20, Sat 11


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-09'); ap.add_argument('--days', type=int, default=22)
    a = ap.parse_args()
    R = cached_router(date.fromisoformat(a.at), a.days, verbose=False)
    feeds = R.feeds
    kind = {}   # trip key -> 'tornado' | 'local' | 'carrier'
    def classify(key):
        key = key[:2]   # connection keys are (feed, trip, day); trip_info is keyed by (feed, trip)
        k = kind.get(key)
        if k: return k
        fi = key[0]; f = feeds[fi]; ag = R.trip_info.get(key, ('',))[0] or ''
        if any(t in ag for t in TORNADO): k = 'tornado'
        elif getattr(f, 'city', False) or any(t in ag for t in LOCAL_MANUAL): k = 'local'
        else: k = 'carrier'
        kind[key] = k; return k
    n = len(R.dep)
    cls = np.array([classify(t) for t in R.ctrip])
    local = cls == 'local'
    carrier_stops = set(R.cfrom[cls == 'carrier'].tolist()) | set(R.cto[cls == 'carrier'].tolist())
    tor = cls == 'tornado'
    tstops = set(R.cfrom[tor].tolist()) | set(R.cto[tor].tolist())
    # first / last stop of each Tornado trip in each state, from the connection order of one day's run per trip
    seq = defaultdict(list)
    for k in np.nonzero(tor)[0]:
        t = R.ctrip[k]
        if len(seq[t]) == 0: seq[t].append(int(R.cfrom[k]))
        seq[t].append(int(R.cto[k]))
    edge = set()
    for t, ss in seq.items():
        for i, s in enumerate(ss):
            st = R.abbr[s]
            if i == 0 or R.abbr[ss[i - 1]] != st: edge.add(s)
            if i == len(ss) - 1 or R.abbr[ss[i + 1]] != st: edge.add(s)
    li = np.nonzero(local)[0]
    ldep, larr, lfrom, lto = R.dep[li], R.arr[li], R.cfrom[li], R.cto[li]
    ltrip = [R.ctrip[k] for k in li]
    d0 = date.fromisoformat(a.at)
    monday = d0 + timedelta(days=(7 - d0.weekday()) % 7)
    rows = []
    for s in sorted(tstops):
        lon, lat = R.stop_xy[s]
        tz = R.stop_zone(s)
        best = None
        for wd, hr in SAMPLES:
            t0 = datetime(monday.year, monday.month, monday.day, hr, tzinfo=tz) + timedelta(days=wd)
            t0 = t0.timestamp()
            bestt = {s: t0}
            for j, w in R.foot.get(s, ()): bestt[j] = min(bestt.get(j, 1e18), t0 + w)
            lo, hi = np.searchsorted(ldep, t0), np.searchsorted(ldep, t0 + HORIZON)
            on = set()
            for k in range(lo, hi):
                tr = ltrip[k]; f = int(lfrom[k])
                if tr not in on:
                    bf = bestt.get(f)
                    if bf is None or bf + 300 > ldep[k]: continue
                    on.add(tr)
                b = int(lto[k]); at = larr[k]
                if at < bestt.get(b, 1e18):
                    bestt[b] = at
                    for j, w in R.foot.get(b, ()):
                        if at + w < bestt.get(j, 1e18): bestt[j] = at + w
            for c, tc in bestt.items():
                if c in carrier_stops and c != s and (best is None or tc - t0 < best[0]):
                    best = (tc - t0, c, f'{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][wd]} {hr:02d}:00')
        near = min(((hav(R.stop_xy[s], R.stop_xy[c]), c) for c in carrier_stops
                    if abs(R.stop_xy[c][1] - lat) < 0.12 and abs(R.stop_xy[c][0] - lon) < 0.16), default=(None, None))
        rows.append(dict(stop=R.stop_name[s], state=R.abbr[s] or '', lat=round(lat, 5), lon=round(lon, 5),
                         link_min=round(best[0] / 60) if best else '', link_to=R.stop_name[best[1]] if best else '',
                         link_when=best[2] if best else '', near_km=round(near[0], 2) if near[0] is not None else '',
                         near_carrier=R.stop_name[near[1]] if near[1] is not None else '', state_edge=s in edge))
    out = os.path.join(os.path.dirname(__file__), '..', 'out', 'tornado_links.csv')
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    linked = [r for r in rows if r['link_min'] != '']
    gap = [r for r in rows if r['link_min'] == '' and r['near_km'] != '' and r['near_km'] <= 10]
    print(f'{len(rows)} Tornado stops; {len(linked)} reach another carrier by walk/local transit within 3 h; '
          f'{len(gap)} do not but have a carrier within 10 km -> {out}')
    print('\nNo link, carrier within 10 km (a hop or city feed would open a transfer):')
    for r in sorted(gap, key=lambda r: r['near_km']):
        print(f"  {r['near_km']:5} km  {r['state']} {r['stop'][:44]:44} -> {r['near_carrier'][:40]}" + ('  [first/last in state]' if r['state_edge'] else ''))
    print('\nLinked, but slowly (over 60 min to the nearest carrier):')
    for r in sorted((r for r in linked if r['link_min'] > 60), key=lambda r: -r['link_min']):
        print(f"  {r['link_min']:4} min {r['state']} {r['stop'][:44]:44} -> {r['link_to'][:40]} ({r['link_when']})")


if __name__ == '__main__':
    main()
