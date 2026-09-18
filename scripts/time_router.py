"""Time-aware routing over real GTFS timetables.

Given a start stop and datetime and an ordered list of targets (states or
@stop names), find the earliest-finishing sequence of scheduled rides that
alights at a stop in every target, using a layered Connection Scan.

usage:
  python3 time_router.py --start "Missoula" --at 2026-09-21T07:00 --tz America/Denver \
      --order result.pkl [--prefix "Montana,Idaho,Washington,..."] [--days 14]
"""
import argparse, csv, io, math, os, pickle, sys, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np
from common import StateIndex, ABBR, DATA_DIR, hav

MIN_TRANSFER = 15 * 60       # seconds between different vehicles at the same stop
SCAN_SLACK = 10 * 3600       # keep scanning this long past the first target arrival
WALK_SPEED = 4.5 / 3.6       # m/s
WALK_MAX_KM = 1.5
LOCAL_MAX_KM = 10.0        # beyond walking: local transit / shuttle proxy
LOCAL_FIXED = 30 * 60      # wait + boarding
LOCAL_SPEED = 15 / 3.6     # m/s effective
N_STATES = 48
STATE_TZ = {'AL':'America/Chicago','AZ':'America/Phoenix','AR':'America/Chicago','CA':'America/Los_Angeles','CO':'America/Denver','CT':'America/New_York','DE':'America/New_York','FL':'America/New_York','GA':'America/New_York','ID':'America/Boise','IL':'America/Chicago','IN':'America/Indiana/Indianapolis','IA':'America/Chicago','KS':'America/Chicago','KY':'America/New_York','LA':'America/Chicago','ME':'America/New_York','MD':'America/New_York','MA':'America/New_York','MI':'America/Detroit','MN':'America/Chicago','MS':'America/Chicago','MO':'America/Chicago','MT':'America/Denver','NE':'America/Chicago','NV':'America/Los_Angeles','NH':'America/New_York','NJ':'America/New_York','NM':'America/Denver','NY':'America/New_York','NC':'America/New_York','ND':'America/Chicago','OH':'America/New_York','OK':'America/Chicago','OR':'America/Los_Angeles','PA':'America/New_York','RI':'America/New_York','SC':'America/New_York','SD':'America/Chicago','TN':'America/Chicago','TX':'America/Chicago','UT':'America/Denver','VT':'America/New_York','VA':'America/New_York','WA':'America/Los_Angeles','WV':'America/New_York','WI':'America/Chicago','WY':'America/Denver'}


def hms(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + int(s)


class Feed:
    """One GTFS zip. tz_mode: 'agency' (times in agency tz, converted per date)
    or 'utc'. calendar_mode: 'dates' (honour calendar dates) or 'weekday'
    (only weekday pattern; for stale feeds)."""
    def __init__(self, path, name, tz_mode, calendar_mode, skip_agencies=(), max_speed=130):
        self.name = name; self.tz_mode = tz_mode; self.calendar_mode = calendar_mode; self.max_speed = max_speed
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
        rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig')) if n in names else []
        self.agency = {a.get('agency_id', ''): a for a in rd('agency.txt')}
        tzs = {a.get('agency_timezone') for a in self.agency.values()} - {None, ''}
        self.tz = ZoneInfo(next(iter(tzs))) if tz_mode == 'agency' and tzs else timezone.utc
        self.stops = {}
        for s in rd('stops.txt'):
            if s.get('location_type', '0') not in ('', '0'): continue
            try: self.stops[s['stop_id']] = (f"{name}:{s['stop_id']}", s['stop_name'], float(s['stop_lon']), float(s['stop_lat']))
            except ValueError: pass
        routes = {r['route_id']: r for r in rd('routes.txt')}
        self.trips = {}
        for t in rd('trips.txt'):
            r = routes.get(t['route_id'], {})
            ag = self.agency.get(r.get('agency_id', ''), {}).get('agency_name', r.get('agency_id', ''))
            if ag in skip_agencies: continue
            self.trips[t['trip_id']] = dict(service=t['service_id'], agency=ag, route=(r.get('route_long_name') or r.get('route_short_name') or ''), headsign=t.get('trip_headsign', ''), stops=[])
        for st in rd('stop_times.txt'):
            t = self.trips.get(st['trip_id'])
            if t is None or st['stop_id'] not in self.stops: continue
            a = st.get('arrival_time') or st.get('departure_time'); d = st.get('departure_time') or a
            if not a: continue
            t['stops'].append((int(st['stop_sequence']), st['stop_id'], hms(a), hms(d)))
        for t in self.trips.values(): t['stops'].sort()
        self.agency_tz = {}
        if tz_mode == 'infer':
            # majority timezone of each agency's stops (by state), else feed tz
            from collections import Counter
            states = StateIndex()
            sxy = {sid: (v[2], v[3]) for sid, v in self.stops.items()}
            sids = list(sxy); st_idx = states.of_points([sxy[s] for s in sids])
            stop_tz = {sid: STATE_TZ.get(ABBR[states.names[i]]) if i >= 0 else None for sid, i in zip(sids, st_idx)}
            per = defaultdict(Counter)
            for t in self.trips.values():
                for _, sid, _, _ in t['stops']:
                    if stop_tz.get(sid): per[t['agency']][stop_tz[sid]] += 1
            for ag, c in per.items(): self.agency_tz[ag] = ZoneInfo(c.most_common(1)[0][0])
        self.cal = {c['service_id']: c for c in rd('calendar.txt')}
        self.cal_dates = defaultdict(dict)
        for c in rd('calendar_dates.txt'): self.cal_dates[c['service_id']][c['date']] = c['exception_type']
        print(f'{name}: {len(self.stops)} stops, {len(self.trips)} trips, tz {self.tz}, calendar {calendar_mode}')

    def sane(self, t):
        """Reject trips whose timetable implies impossible speeds or negative
        segments (some merged-feed carriers carry placeholder times)."""
        if 'sane' in t: return t['sane']
        ok = True; st = t['stops']
        for i in range(len(st) - 1):
            d = hav(self.stops[st[i][1]][2:4], self.stops[st[i + 1][1]][2:4])
            dt = st[i + 1][2] - st[i][3]
            if dt < -60 or (d > 25 and d / max(dt, 1) * 3600 > self.max_speed): ok = False; break
        t['sane'] = ok
        return ok

    def runs_on(self, service, d):
        ds = d.strftime('%Y%m%d'); dow = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][d.weekday()]
        exc = self.cal_dates.get(service, {}).get(ds)
        if exc == '1': return True
        if exc == '2': return False
        c = self.cal.get(service)
        if c is None: return False
        if c[dow] != '1': return False
        if self.calendar_mode == 'weekday': return True
        return c['start_date'] <= ds <= c['end_date']

    def connections(self, d0, days, stop_index, trip_base):
        """Yield (dep_time, arr_time, dep_stop, arr_stop, trip_key) in epoch seconds."""
        out = []
        for di in range(days):
            d = d0 + timedelta(days=di)
            bases = {}
            def base_for(tz):
                if tz not in bases:
                    bases[tz] = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() if tz is None else (datetime(d.year, d.month, d.day, 12, tzinfo=tz) - timedelta(hours=12)).timestamp()
                return bases[tz]
            for tid, t in self.trips.items():
                if len(t['stops']) < 2 or not self.runs_on(t['service'], d): continue
                tz = None if self.tz_mode == 'utc' else self.agency_tz.get(t['agency'], self.tz)
                base = base_for(tz)
                key = (trip_base, tid, di)
                st = t['stops']
                if not self.sane(t): continue
                for i in range(len(st) - 1):
                    a = stop_index[self.stops[st[i][1]][0]]; b = stop_index[self.stops[st[i + 1][1]][0]]
                    out.append((base + st[i][3], base + st[i + 1][2], a, b, key))
        return out


class TimeRouter:
    def __init__(self, feeds, d0, days):
        self.feeds = feeds; self.d0 = d0
        # stops
        self.stop_ids = []; self.stop_name = []; self.stop_xy = []
        seen = set()
        for f in feeds:
            for sid, (uid, nm, lon, lat) in f.stops.items():
                if uid in seen: continue
                seen.add(uid); self.stop_ids.append(uid); self.stop_name.append(nm); self.stop_xy.append((lon, lat))
        self.idx = {u: i for i, u in enumerate(self.stop_ids)}
        self.N = len(self.stop_ids)
        states = StateIndex(); self.state_names = states.names
        self.state = states.of_points(self.stop_xy)
        self.abbr = [ABBR[states.names[s]] if s >= 0 else None for s in self.state]
        # footpaths
        buckets = defaultdict(list)
        for i, (lon, lat) in enumerate(self.stop_xy): buckets[(int(lon / 0.1), int(lat / 0.1))].append(i)
        self.foot = defaultdict(list)
        for (bx, by), members in buckets.items():
            cand = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in buckets.get((bx + dx, by + dy), [])]
            for i in members:
                for j in cand:
                    if j == i: continue
                    d = hav(self.stop_xy[i], self.stop_xy[j])
                    if d <= WALK_MAX_KM: self.foot[i].append((j, int(d * 1000 / WALK_SPEED) + 300))
                    elif d <= LOCAL_MAX_KM: self.foot[i].append((j, LOCAL_FIXED + int(d * 1000 / LOCAL_SPEED)))
        # connections
        conns = []; self.trip_info = {}
        for fi, f in enumerate(feeds):
            conns += f.connections(d0, days, self.idx, fi)
            for tid, t in f.trips.items(): self.trip_info[(fi, tid)] = (t['agency'], t['route'], t['headsign'])
        conns.sort(key=lambda c: c[0])
        self.dep = np.array([c[0] for c in conns]); self.arr = np.array([c[1] for c in conns])
        self.cfrom = np.array([c[2] for c in conns]); self.cto = np.array([c[3] for c in conns])
        self.ctrip = [c[4] for c in conns]
        bad = sum(1 for f in feeds for t in f.trips.values() if t.get('sane') is False)
        print(f'{self.N} stops, {sum(len(v) for v in self.foot.values())} footpaths, {len(conns)} connections over {days} days, {bad} trips rejected as implausible')

    def stops_matching(self, q):
        q = q.lower(); return [i for i, nm in enumerate(self.stop_name) if q in nm.lower()]

    def target_set(self, t):
        if isinstance(t, str) and t.startswith('@'): return set(self.stops_matching(t[1:]))
        return set(np.where(self.state == t)[0].tolist())

    def scan(self, labels, targets):
        """CSA from initial labels {stop: (time, trip_key)}; returns arrival labels at
        targets and predecessor info for reconstruction."""
        INF = float('inf'); N = self.N
        best = np.full(N, INF); pred = {}; ltrip = {}
        for s, (t, trip) in labels.items():
            if t < best[s]: best[s] = t; ltrip[s] = trip; pred[s] = None
            for j, w in self.foot[s]:
                if t + w < best[j]: best[j] = t + w; ltrip[j] = None; pred[j] = ('walk', s, t)
        t0 = min(best[s] for s in labels); start = int(np.searchsorted(self.dep, t0))
        reached = {}   # trip_key -> (board stop, board time)
        target_best = INF; tgt = targets
        dep, arr, cfrom, cto, ctrip = self.dep, self.arr, self.cfrom, self.cto, self.ctrip
        for k in range(start, len(dep)):
            dt = dep[k]
            if dt > target_best + SCAN_SLACK: break
            trip = ctrip[k]; a = cfrom[k]
            if trip not in reached:
                ba = best[a]
                if ba == INF: continue
                need = 0 if ltrip.get(a) == trip else MIN_TRANSFER
                if ba + need <= dt: reached[trip] = (a, dt)
                else: continue
            b = cto[k]; at = arr[k]
            if at < best[b]:
                best[b] = at; ltrip[b] = trip; pred[b] = ('ride', trip, reached[trip][0], reached[trip][1], a, dt)
                if b in tgt and at < target_best: target_best = at
                for j, w in self.foot[b]:
                    if at + w < best[j]: best[j] = at + w; ltrip[j] = None; pred[j] = ('walk', b, at)
        out = {s: (best[s], ltrip.get(s)) for s in tgt if best[s] < INF}
        return out, pred, best

    def route(self, start_stop, start_time, order):
        """order: list of targets (state idx or '@name'). Returns (finish, legs)."""
        labels = {start_stop: (start_time, None)}; layers = []
        for t in order:
            tgt = self.target_set(t)
            out, pred, best = self.scan(labels, tgt)
            if not out: return None, layers + [('unreachable', t)]
            layers.append((t, out, pred)); labels = out
        # reconstruct backwards
        t_end, _ = min(labels.values(), key=lambda x: x[0]); end = min(labels, key=lambda s: labels[s][0])
        legs = []
        for t, out, pred in reversed(layers):
            s = end; seg = []
            while pred.get(s) is not None:
                p = pred[s]
                if p[0] == 'walk': seg.append(('walk', p[1], s, p[2], best_time(out, pred, s))); s = p[1]
                else: seg.append(('ride', p[1], p[2], p[3], s, None)); s = p[2]
            legs = seg[::-1] + legs; end = s
        return t_end, self._fill(legs)

    def _fill(self, legs):
        """Fill arrival times of rides from the connection arrays."""
        filled = []
        for l in legs:
            if l[0] == 'ride':
                _, trip, bs, bt, alight, _ = l
                # find arrival at alight on this trip after bt
                ks = [k for k in range(int(np.searchsorted(self.dep, bt)), len(self.dep)) if self.ctrip[k] == trip and self.cto[k] == alight and self.dep[k] >= bt]
                at = self.arr[ks[0]] if ks else None
                filled.append(('ride', trip, bs, bt, alight, at))
            else: filled.append(l)
        # merge consecutive rides on the same trip
        merged = []
        for l in filled:
            if l[0] == 'ride' and merged and merged[-1][0] == 'ride' and merged[-1][1] == l[1]:
                m = merged[-1]; merged[-1] = ('ride', m[1], m[2], m[3], l[4], l[5])
            else: merged.append(l)
        return merged

    def fmt_time(self, ts, stop):
        ab = self.abbr[stop]
        if not ab:   # outside the 48 (border towns): nearest stop with a state
            lon, lat = self.stop_xy[stop]
            j = min((i for i in range(self.N) if self.abbr[i]), key=lambda i: (self.stop_xy[i][0]-lon)**2 + (self.stop_xy[i][1]-lat)**2)
            ab = self.abbr[j]
        tz = ZoneInfo(STATE_TZ.get(ab, 'UTC'))
        d = datetime.fromtimestamp(ts, tz); day = (d.date() - self.d0).days + 1
        return f"d{day} {d.strftime('%a %H:%M')}"

    def describe(self, legs):
        lines = []
        for l in legs:
            if l[0] == 'walk':
                _, a, b, t0, t1 = l
                d = hav(self.stop_xy[a], self.stop_xy[b])
                lines.append(f"  {'walk ' if d <= WALK_MAX_KM else 'local'} {self.stop_name[a]} -> {self.stop_name[b]}  ({d:.1f} km, from {self.fmt_time(t0, a)})")
            else:
                _, trip, bs, bt, al, at = l
                ag, rt, hs = self.trip_info[(trip[0], trip[1])]
                lines.append(f"{self.fmt_time(bt, bs)}  {self.stop_name[bs]}, {self.abbr[bs]}  ->  {self.fmt_time(at, al) if at else '?'}  {self.stop_name[al]}, {self.abbr[al]}   [{ag}: {rt or hs}]")
        return '\n'.join(lines)


def best_time(out, pred, s):
    return None


class ExtraFeed:
    """Manual trips from data/extra_trips.csv (agency,route,days,tz,stops with
    Name@HH:MM or Name@arr/dep separated by |). Stop names must match a stop in
    another feed; the first match is used."""
    def __init__(self, path, others):
        self.name = 'extra'; self.stops = {}; self.trips = {}; self.tz_mode = 'agency'; self.calendar_mode = 'weekday'
        self.cal = {}; self.cal_dates = {}; self.agency_tz = {}; self.max_speed = 130; self.tz = timezone.utc
        if not os.path.exists(path): return
        allstops = [(uid, nm, lon, lat) for f in others for (uid, nm, lon, lat) in f.stops.values()]
        for k, r in enumerate(csv.DictReader(open(path))):
            seq = []
            for i, item in enumerate(r['stops'].split('|')):
                nm, tm = item.split('@'); tm = tm.strip()
                arr, dep = (tm.split('/') + [tm])[:2] if '/' in tm else (tm, tm)
                hit = next((s for s in allstops if s[1].lower() == nm.strip().lower()), None) or next((s for s in allstops if nm.strip().lower() in s[1].lower()), None)
                if hit is None: print('extra trip: no stop named', nm); break
                sid = f'x{k}_{i}'; self.stops[sid] = (hit[0], hit[1], hit[2], hit[3])
                seq.append((i, sid, hms(arr + ':00'), hms(dep + ':00')))
            else:
                svc = f'svc{k}'; days = r['days']
                self.cal[svc] = {d: days[j] for j, d in enumerate(('monday','tuesday','wednesday','thursday','friday','saturday','sunday'))}
                self.cal[svc].update(start_date='20000101', end_date='20991231')
                self.trips[f't{k}'] = dict(service=svc, agency=r['agency'], route=r['route'], headsign='', stops=seq)
                self.agency_tz[r['agency']] = ZoneInfo(r['tz'])
        print(f'extra: {len(self.trips)} manual trips')
    sane = Feed.sane; runs_on = Feed.runs_on; connections = Feed.connections


def load_feeds():
    feeds = [
        Feed(os.path.join(DATA_DIR, 'flix_gtfs.zip'), 'flix', 'utc', 'dates'),
        Feed(os.path.join(DATA_DIR, 'amtrak_gtfs.zip'), 'amtrak', 'agency', 'dates', max_speed=220),
        Feed(os.path.join(DATA_DIR, 'intercity_merged_gtfs.zip'), 'ibus', 'infer', 'weekday', skip_agencies=('Greyhound-us', 'FlixBus-us')),
    ]
    # carriers whose merged-feed times are known to be Eastern (Amtrak-sourced thruway)
    feeds[2].agency_tz['BeeLine Express-Village Travel'] = ZoneInfo('America/New_York')
    feeds.append(ExtraFeed(os.path.join(DATA_DIR, 'extra_trips.csv'), feeds))
    return feeds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True, help='substring of the start stop name')
    ap.add_argument('--at', required=True, help='local start datetime, e.g. 2026-09-21T07:00')
    ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--order', help='result pickle with a state order, or comma list of states/@stops')
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), t0.date(), a.days)
    cands = R.stops_matching(a.start)
    if not cands: sys.exit(f'no stop matching {a.start}')
    start = cands[0]; print('start at', R.stop_name[start], R.abbr[start], 'candidates', [R.stop_name[c] for c in cands[:5]])
    if a.order and a.order.endswith('.pkl'):
        order = [x for x in pickle.load(open(a.order, 'rb'))['order'] if isinstance(x, int) and x < N_STATES]
    else:
        order = [x.strip() if x.strip().startswith('@') else R.state_names.index(x.strip()) for x in a.order.split(',')]
    finish, legs = R.route(start, t0.timestamp(), order)
    if finish is None:
        print('UNREACHABLE at', legs[-1]); return
    print('finish', R.fmt_time(finish, [l for l in legs if l[0]=='ride'][-1][4]), 'elapsed', round((finish - t0.timestamp()) / 3600, 1), 'h')
    print(R.describe(legs))
    if a.out: pickle.dump(dict(finish=finish, legs=legs, order=order), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
