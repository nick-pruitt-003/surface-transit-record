"""Long services no fast route uses, ranked by how rare their LINK is, not the service. Leaf script.

anchors.py counts departures per service, which calls NYC -> Boston rare on any one bus line although a
dozen services run it. What decides whether a ride is a commitment is the link: miss it and how long until
anything at all gets you to the same place. So for each service collecting 3+ states and departing no more
than --max-per-day times a day, take one dated run, leave its first stop one minute after it does, and ask
the timetable for the earliest arrival at its last stop by any combination of services:

    headway = that arrival - the run's own arrival

About a day means the link runs once a day and the service is a real anchor; an hour means the link is busy
and the service is replaceable. Services any known fast route rides (route_anchors.pkl: control, record,
X_TOL) are marked used and listed last.

The per-day filter only trims what is scanned; it is permissive (3) so a daily service on a busy link is still
listed with its short headway rather than dropped.

    python3 unused_links.py           ->  ../out/unused_links.txt
"""
import argparse, collections, pickle
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR, within_km

ap = argparse.ArgumentParser()
ap.add_argument('--min-states', type=int, default=3)
ap.add_argument('--max-per-day', type=float, default=3.0)
a = ap.parse_args()

R = cached_router(date(2026, 9, 24), 20)
ab = lambda y: ABBR[R.state_names[y]]
xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float)
CT = ZoneInfo('America/Chicago')
T_FROM = datetime(2026, 9, 24, tzinfo=CT).timestamp()
DAYS = 20


def near(i, r_km):
    return within_km(xy, *R.stop_xy[i], r_km)


# every dated run: its connections in order (first and last are what the link is measured on)
first_k, last_k = {}, {}
for k, key in enumerate(R.ctrip):
    if key not in first_k or R.dep[k] < R.dep[first_k[key]]: first_k[key] = k
    if key not in last_k or R.arr[k] > R.arr[last_k[key]]: last_k[key] = k
runs = collections.defaultdict(list)          # (feed, trip) -> dated keys
for key in first_k: runs[(key[0], key[1])].append(key)

# group feed trips into services by (route name, states in order); count dated runs per service
svc = collections.defaultdict(lambda: dict(n=0, runs=[], stops=set(), agency=None))
for (fi, tid), keys in runs.items():
    info = R.trip_info.get((fi, tid))
    if not info: continue
    # states along the run, in the feed's stop order
    f = R.feeds[fi]; t = f.trips.get(tid)
    if t is None: continue
    ids = [R.idx.get(f.stops[x[1]][0]) for x in t['stops']]
    ids = [i for i in ids if i is not None]
    sts = []
    for i in ids:
        y = int(R.state[i])
        if y >= 0 and y not in sts: sts.append(y)
    if len(sts) < a.min_states: continue
    s = svc[(info[0], info[1] or info[2], tuple(sts))]
    s['n'] += len(keys); s['runs'] += keys; s['stops'] |= set(ids); s['agency'] = info[0]

used = pickle.load(open('../out/route_anchors.pkl', 'rb'))
used_rides = [(r['agency'], r['board'], r['alight']) for r in used]

rows = []
cand = [(k, v) for k, v in svc.items() if v['n'] / DAYS <= a.max_per_day]
print(f'{len(svc)} services collect {a.min_states}+ states; {len(cand)} run at most {a.max_per_day}/day; scanning', flush=True)
for n_, ((agency, line, sts), v) in enumerate(cand):
    run = min((r for r in v['runs'] if R.dep[first_k[r]] >= T_FROM), key=lambda r: R.dep[first_k[r]], default=None)
    if run is None: continue
    k0, k1 = first_k[run], last_k[run]
    b, al, dep, arr = int(R.cfrom[k0]), int(R.cto[k1]), R.dep[k0], R.arr[k1]
    s = near(b, 0.3); lon, lat = R.stop_xy[al]
    _, tm, _ = R._scan_fast(s, np.full(len(s), float(dep + 60)), np.full(len(s), -1, dtype=np.int32), f'@~{lon},{lat},1.0')
    alt = float(tm.min()) if len(tm) else float('inf')
    is_used = any(ag == agency and bs in v['stops'] and al_ in v['stops'] for ag, bs, al_ in used_rides)
    rows.append(dict(agency=agency, line=line, states=[ab(y) for y in sts], per_day=v['n'] / DAYS,
                     board=b, alight=al, dep=dep, hours=(arr - dep) / 3600, headway=(alt - arr) / 3600, used=is_used))
    if (n_ + 1) % 200 == 0: print(f'  {n_ + 1}/{len(cand)}', flush=True)

rows.sort(key=lambda r: (r['used'], -r['headway'] if r['headway'] == r['headway'] else 0, -len(r['states'])))
with open('../out/unused_links.txt', 'w') as fh:
    fh.write('headway = next arrival at the last stop, leaving the first stop 1 min after this run, by ANY services, '
             'minus this run\'s arrival.\n~24 h = the link runs once a day; ~1 h = a busy link.\n')
    last = None
    for r in rows:
        if r['used'] != last:
            fh.write('\n== ' + ('USED by the control, record or X_TOL' if r['used'] else 'NOT used by any fast route') + '\n')
            fh.write(f'{"headway":>8s} {"ride":>6s} {"/day":>5s}  {"dep CT":9s} from -> to, states, service\n'); last = r['used']
        hw = f"{r['headway']:7.1f}h" if r['headway'] != float('inf') else '   never'
        dt = datetime.fromtimestamp(r['dep'], CT)
        fh.write(f"{hw} {r['hours']:5.1f}h {r['per_day']:5.2f}  {dt:%a %H:%M}  {R.stop_name[r['board']][:26]:26s} -> "
                 f"{R.stop_name[r['alight']][:26]:26s} {' '.join(r['states']):30s} {str(r['agency'])[:14]} {str(r['line'])[:34]}\n")
print('wrote ../out/unused_links.txt', flush=True)
