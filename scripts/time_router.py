"""Time-aware routing over real GTFS timetables.

Given a start stop and datetime and an ordered list of targets (states or
@stop names), find the earliest-finishing sequence of scheduled rides that
alights at a stop in every target, using a layered Connection Scan.

usage:
  python3 time_router.py --start "Missoula" --at 2026-09-21T07:00 --tz America/Denver \
      --order result.pkl [--prefix "Montana,Idaho,Washington,..."] [--days 14]
"""
import argparse, csv, io, math, os, pickle, sys, time, zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np
from common import StateIndex, ABBR, DATA_DIR, hav

_P = lambda s: [frozenset(x.split('-')) for x in s.split()]
RIVER_BORDERS = set(_P('KY-OH KY-IN KY-IL WV-OH IA-IL IA-WI MO-IL MO-KY MO-TN AR-TN AR-MS LA-MS MN-WI MN-ND IA-NE MO-NE IA-SD '
                       'NJ-PA DE-NJ MD-VA MD-WV NH-VT OR-WA GA-SC OK-TX ID-OR ID-WA IL-IN AL-GA'))
# walkable bridges Nick has accepted (stop-name substrings)
RIVER_OK = {frozenset(('NH', 'VT')): ('Hanover', 'Ledyard', 'Tuck'), frozenset(('MN', 'ND')): ('Fargo', 'Moorhead')}
WALKIN_KM = float(os.environ.get('BUS48_WALKIN_KM', 1.4))   # border walk-ins (Nick's rules); 0 = a state needs a real stop
MIN_TRANSFER = int(os.environ.get('BUS48_MIN_TRANSFER', 5)) * 60       # seconds between different vehicles at the same stop
SCAN_SLACK = float(os.environ.get("BUS48_SCAN_SLACK_H", 24)) * 3600   # keep scanning this long past the first target arrival; 24 lets a state be collected at a later, better-placed stop
WALK_SPEED = 4.5 / 3.6       # m/s
WALK_MAX_KM = 1.5
# Beyond walking: a local transit / shuttle proxy, which is a modelled link and not a service anyone runs.
# Set BUS48_LOCAL_MAX_KM=0 to drop them and keep only real timetables plus walks, which is what a route has
# to stand on before it can be attempted.
LOCAL_MAX_KM = float(os.environ.get('BUS48_LOCAL_MAX_KM', 10.0))
LOCAL_FIXED = 30 * 60      # wait + boarding
LOCAL_SPEED = 15 / 3.6     # m/s effective
# more_gtfs feeds that are intercity carriers; every other feed there is city transit. The 1.5-10 km local-transit
# proxy link is only built when one end is an intercity stop: city-to-city-stop hops are covered by the real
# city routes, and building them for every pair of city stops multiplied the footpaths ~9x (Sep 21 2026).
INTERCITY_MORE = {'concord_coach', 'bustang', 'gobus', 'kimball'}
LOCAL_PROXY_ALL = os.environ.get('BUS48_LOCAL_PROXY', 'intercity') == 'all'
STOP_TZ_LOCAL = os.environ.get('BUS48_STOP_TZ') == '1'
N_STATES = 48
STATE_TZ = {'AL':'America/Chicago','AZ':'America/Phoenix','AR':'America/Chicago','CA':'America/Los_Angeles','CO':'America/Denver','CT':'America/New_York','DE':'America/New_York','FL':'America/New_York','GA':'America/New_York','ID':'America/Boise','IL':'America/Chicago','IN':'America/Indiana/Indianapolis','IA':'America/Chicago','KS':'America/Chicago','KY':'America/New_York','LA':'America/Chicago','ME':'America/New_York','MD':'America/New_York','MA':'America/New_York','MI':'America/Detroit','MN':'America/Chicago','MS':'America/Chicago','MO':'America/Chicago','MT':'America/Denver','NE':'America/Chicago','NV':'America/Los_Angeles','NH':'America/New_York','NJ':'America/New_York','NM':'America/Denver','NY':'America/New_York','NC':'America/New_York','ND':'America/Chicago','OH':'America/New_York','OK':'America/Chicago','OR':'America/Los_Angeles','PA':'America/New_York','RI':'America/New_York','SC':'America/New_York','SD':'America/Chicago','TN':'America/Chicago','TX':'America/Chicago','UT':'America/Denver','VT':'America/New_York','VA':'America/New_York','WA':'America/Los_Angeles','WV':'America/New_York','WI':'America/Chicago','WY':'America/Denver'}


def hms(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + int(s)


class Feed:
    """One GTFS zip. tz_mode: 'agency' (times in agency tz, or stop_timezone when
    present — Amtrak), 'infer' (majority state tz per agency), or 'utc'.
    calendar_mode: 'dates' (honour calendar dates) or 'weekday' (stale feeds)."""
    def __init__(self, path, name, tz_mode, calendar_mode, skip_agencies=(), max_speed=130, keep_routes=None):
        self.name = name; self.tz_mode = tz_mode; self.calendar_mode = calendar_mode; self.max_speed = max_speed
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
        rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig')) if n in names else []
        self.agency = {a.get('agency_id', ''): a for a in rd('agency.txt')}
        tzs = {a.get('agency_timezone') for a in self.agency.values()} - {None, ''}
        self.tz = ZoneInfo(next(iter(tzs))) if tz_mode == 'agency' and tzs else timezone.utc
        self.stops = {}; self.stop_tz = {}
        for s in rd('stops.txt'):
            if s.get('location_type', '0') not in ('', '0'): continue
            try: self.stops[s['stop_id']] = (f"{name}:{s['stop_id']}", s['stop_name'], float(s['stop_lon']), float(s['stop_lat']))
            except ValueError: continue
            tzname = (s.get('stop_timezone') or '').strip()
            if tzname:
                try: self.stop_tz[s['stop_id']] = ZoneInfo(tzname)
                except Exception: pass
        routes = {r['route_id']: r for r in rd('routes.txt')}
        self.trips = {}
        for t in rd('trips.txt'):
            r = routes.get(t['route_id'], {})
            ag = self.agency.get(r.get('agency_id', ''), {}).get('agency_name', r.get('agency_id', ''))
            if ag in skip_agencies: continue
            # big city feeds: keep only the listed routes (matched on id, short or long name)
            if keep_routes is not None and not ({t['route_id'], r.get('route_short_name', ''), r.get('route_long_name', '')} & keep_routes): continue
            self.trips[t['trip_id']] = dict(service=t['service_id'], agency=ag, route=(r.get('route_long_name') or r.get('route_short_name') or ''), headsign=t.get('trip_headsign', ''), stops=[])
        for st in rd('stop_times.txt'):
            t = self.trips.get(st['trip_id'])
            if t is None or st['stop_id'] not in self.stops: continue
            a = st.get('arrival_time') or st.get('departure_time'); d = st.get('departure_time') or a
            if not a: continue
            t['stops'].append((int(st['stop_sequence']), st['stop_id'], hms(a), hms(d)))
        for t in self.trips.values(): t['stops'].sort()
        if keep_routes is not None:   # unused stops only add footpaths
            used = {sid for t in self.trips.values() for _, sid, _, _ in t['stops']}
            self.stops = {k: v for k, v in self.stops.items() if k in used}
            self.stop_tz = {k: v for k, v in self.stop_tz.items() if k in used}
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
        tz_note = f', {len(self.stop_tz)} stop_tz' if self.stop_tz else ''
        print(f'{name}: {len(self.stops)} stops, {len(self.trips)} trips, tz {self.tz}{tz_note}, calendar {calendar_mode}')

    def _tz_for(self, sid, trip):
        """Timezone for a stop time: stop_timezone if set, else agency/feed tz (or UTC)."""
        if self.tz_mode == 'utc': return None
        # GTFS times are in agency_timezone even when stop_timezone is set, and Amtrak's feed follows that:
        # CONO Effingham 23:01 / Memphis 29:42 in the file = 10:01 PM / 4:42 AM Central (Nick, Sep 21 2026).
        # Reading them as stop-local put every western train 1-3 h late. Kept only behind BUS48_STOP_TZ=1.
        if STOP_TZ_LOCAL and sid in self.stop_tz: return self.stop_tz[sid]
        return self.agency_tz.get(trip['agency'], self.tz)

    def sane(self, t):
        """Reject trips whose timetable implies impossible speeds or negative
        segments (some merged-feed carriers carry placeholder times)."""
        if 'sane' in t: return t['sane']
        ok = True; st = t['stops']
        # Fixed service day so DST-correct elapsed time across stop_timezone boundaries
        d = date(2026, 9, 24); bases = {}
        def base_for(tz):
            if tz not in bases:
                bases[tz] = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() if tz is None else (datetime(d.year, d.month, d.day, 12, tzinfo=tz) - timedelta(hours=12)).timestamp()
            return bases[tz]
        for i in range(len(st) - 1):
            dist = hav(self.stops[st[i][1]][2:4], self.stops[st[i + 1][1]][2:4])
            dt = (base_for(self._tz_for(st[i + 1][1], t)) + st[i + 1][2]) - (base_for(self._tz_for(st[i][1], t)) + st[i][3])
            if dt < -60 or (dist > 25 and dist / max(dt, 1) * 3600 > self.max_speed): ok = False; break
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
                key = (trip_base, tid, di)
                st = t['stops']
                if not self.sane(t): continue
                for i in range(len(st) - 1):
                    a = stop_index[self.stops[st[i][1]][0]]; b = stop_index[self.stops[st[i + 1][1]][0]]
                    dep = base_for(self._tz_for(st[i][1], t)) + st[i][3]
                    arr = base_for(self._tz_for(st[i + 1][1], t)) + st[i + 1][2]
                    out.append((dep, arr, a, b, key))
        return out


class TimeRouter:
    def __init__(self, feeds, d0, days):
        self.feeds = feeds; self.d0 = d0
        # stops
        self.stop_ids = []; self.stop_name = []; self.stop_xy = []; city = []
        seen = set(); city_uids = {uid for f in feeds if getattr(f, 'city', False) for uid, *_ in f.stops.values()}
        for f in feeds:
            for sid, (uid, nm, lon, lat) in f.stops.items():
                if uid in seen: continue
                seen.add(uid); self.stop_ids.append(uid); self.stop_name.append(nm); self.stop_xy.append((lon, lat))
                city.append(uid in city_uids)
        self.idx = {u: i for i, u in enumerate(self.stop_ids)}
        self.N = len(self.stop_ids)
        hi = os.path.join(DATA_DIR, 'states_500k.geojson')   # Census 1:500k borders; the coarse file misplaces border stops
        states = StateIndex(hi if os.path.exists(hi) else None); self.state_names = states.names
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
                    if d <= WALK_MAX_KM: self.foot[i].append((j, int(d * 1000 / WALK_SPEED) + (0 if d < 0.15 else 300)))
                    elif d <= LOCAL_MAX_KM and (LOCAL_PROXY_ALL or not (city[i] and city[j])):
                        self.foot[i].append((j, LOCAL_FIXED + int(d * 1000 / LOCAL_SPEED)))
        # walk-ins: a stop within WALKIN_KM of another state's border lets you step across and back
        self.first_virtual = self.N
        if WALKIN_KM > 0:
            from shapely.geometry import Point
            from shapely.ops import nearest_points
            state = list(self.state); deg = WALKIN_KM / 70.0   # 1 deg lon is ~73 km at 49 N
            for i in range(self.N):
                if state[i] < 0: continue
                pt = Point(self.stop_xy[i])
                for j in states.tree.query(pt.buffer(deg)):
                    j = int(j)
                    if j == state[i]: continue
                    # borders that are rivers: a straight-line walk-in is fiction unless a walkable bridge is known
                    pair = frozenset((ABBR[states.names[j]], ABBR[states.names[state[i]]]))
                    if pair in RIVER_BORDERS and not any(k in self.stop_name[i] for k in RIVER_OK.get(pair, ())): continue
                    q = nearest_points(states.polys[j], pt)[0]; d = hav(self.stop_xy[i], (q.x, q.y))
                    if d > WALKIN_KM: continue
                    v = len(self.stop_ids); w = 120 + int(d * 1000 / WALK_SPEED)
                    self.stop_ids.append(f'walkin:{self.stop_ids[i]}:{ABBR[states.names[j]]}'); self.stop_name.append(f'{ABBR[states.names[j]]} state line (walk from {self.stop_name[i]})')
                    self.stop_xy.append((q.x, q.y)); state.append(j); self.abbr.append(ABBR[states.names[j]])
                    self.foot[i].append((v, w)); self.foot[v].append((i, w))
            self.state = np.array(state, dtype=np.int32); self.idx = {u: k for k, u in enumerate(self.stop_ids)}; self.N = len(self.stop_ids)
            print(self.N - self.first_virtual, 'walk-in border points within', WALKIN_KM, 'km')
        # hand-measured walking links (real paths over bridges etc.): data/walk_links.csv from_uid,to_uid,minutes,note
        wl = os.path.join(DATA_DIR, 'walk_links.csv')
        if os.path.exists(wl):
            ix = {u: k for k, u in enumerate(self.stop_ids)}
            with open(wl) as fh: rows = list(csv.DictReader(fh))
            # a hand-made end point is reachable only by its measured link, never by the generic proxies
            only = {ix[r['to_uid']] for r in rows if r['to_uid'].startswith('extra:') and r['to_uid'] in ix}
            for k in list(self.foot):
                self.foot[k] = [] if k in only else [(j, w) for j, w in self.foot[k] if j not in only]
            for r in rows:
                a, b = ix.get(r['from_uid']), ix.get(r['to_uid'])
                if a is None or b is None: print('walk link: unknown stop', r['from_uid'], r['to_uid']); continue
                w = int(float(r['minutes']) * 60); self.foot[a].append((b, w)); self.foot[b].append((a, w))
        # connections
        conns = []; self.trip_info = {}
        for fi, f in enumerate(feeds):
            # start a day early: overnight trips that originate the previous service day (e.g. the 1:00 AM
            # Barons bus through Huntington) would otherwise be missing on day 1
            conns += f.connections(d0 - timedelta(days=1), days + 1, self.idx, fi)
            for tid, t in f.trips.items(): self.trip_info[(fi, tid)] = (t['agency'], t['route'], t['headsign'])
        conns.sort(key=lambda c: c[0])
        self.dep = np.array([c[0] for c in conns]); self.arr = np.array([c[1] for c in conns])
        self.cfrom = np.array([c[2] for c in conns]); self.cto = np.array([c[3] for c in conns])
        self.ctrip = [c[4] for c in conns]
        self._init_fast()
        bad = sum(1 for f in feeds for t in f.trips.values() if t.get('sane') is False)
        print(f'{self.N} stops, {sum(len(v) for v in self.foot.values())} footpaths, {len(conns)} connections over {days} days, {bad} trips rejected as implausible')

    def stops_matching(self, q):
        q = q.lower(); return [i for i, nm in enumerate(self.stop_name) if q in nm.lower()]

    def target_set(self, t):
        if isinstance(t, str) and t.startswith('@~'):   # gateway: '@~lon,lat,km' = every stop within km of a point
            lon, lat, km = map(float, t[2:].split(','))
            xy = np.asarray(self.stop_xy, dtype=float)
            d = np.hypot((xy[:, 0] - lon) * 111.3 * np.cos(np.radians(lat)), (xy[:, 1] - lat) * 111.3)
            return set(np.where(d <= km)[0].tolist())
        if isinstance(t, str) and t.startswith('@#'): return {int(t[2:])}   # one exact stop index
        if isinstance(t, str) and t.startswith('@'): return set(self.stops_matching(t[1:]))
        return set(np.where(self.state == t)[0].tolist())

    def _crosses(self, i, j):
        """Footpath i -> j crosses a state line into a real stop (border walk-in stops are exempt)."""
        return j < self.first_virtual and int(self.state[i]) != int(self.state[j])

    def scan(self, labels, targets, guard=False):
        """CSA from initial labels {stop: (time, trip_key)}; returns arrival labels at
        targets and predecessor info for reconstruction."""
        INF = float('inf'); N = self.N; tgt_ = targets   # guard: a state target, collected by ride or walk-in only
        best = np.full(N, INF); pred = {}; ltrip = {}; ride_best = {}   # ride_best: earliest arrival BY A RIDE
        for s, (t, trip) in labels.items():
            if t < best[s]: best[s] = t; ltrip[s] = trip; pred[s] = None
            for j, w in self.foot[s]:
                if guard and j in tgt_ and self._crosses(s, j): continue
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
            # As csa.c: footpaths are relaxed when a RIDE newly improves b, not only when it improves best[b], so a
            # walk-derived label at b cannot shadow the onward walk the ride licenses (Holmes and the MS line). The
            # ride is kept under ('ride', b), apart from b's own predecessor, and a walk off it carries a 4th field
            # so route() leaves b by that ride rather than by b's walk.
            fresh = at < ride_best.get(b, INF)
            if fresh:
                ride_best[b] = at; pred[('ride', b)] = ('ride', trip, reached[trip][0], reached[trip][1], a, dt)
            if at < best[b]:
                best[b] = at; ltrip[b] = trip; pred[b] = pred[('ride', b)]
                if b in tgt and at < target_best: target_best = at
            if fresh:
                for j, w in self.foot[b]:
                    if guard and j in tgt and self._crosses(b, j): continue
                    if at + w < best[j]: best[j] = at + w; ltrip[j] = None; pred[j] = ('walk', b, at, True)
        out = {s: (best[s], ltrip.get(s)) for s in tgt if best[s] < INF}
        return out, pred, best

    def _route_py(self, start_stop, start_time, order):
        saved, self._fast = self._fast, None
        try: return self.route(start_stop, start_time, order)
        finally: self._fast = saved

    def route(self, start_stop, start_time, order):
        """order: list of targets (state idx or '@name'). Returns (finish, legs)."""
        if getattr(self, '_fast', None) is not None: return self._route_fast(start_stop, start_time, order)
        labels = {int(s): (start_time, None) for s in np.atleast_1d(np.asarray(start_stop, dtype=np.int64))}; layers = []
        for t in order:
            tgt = self.target_set(t)
            out, pred, best = self.scan(labels, tgt, guard=not isinstance(t, str))
            if not out:
                self.last_outs = [o for _, o, _ in layers]
                return None, layers + [('unreachable', t)]
            layers.append((t, out, pred)); labels = out
        self.last_outs = [out for _, out, _ in layers]
        # reconstruct backwards
        t_end, _ = min(labels.values(), key=lambda x: x[0]); end = min(labels, key=lambda s: labels[s][0])
        legs = []
        for t, out, pred in reversed(layers):
            s = end; seg = []; by_ride = False   # True: s was left on foot off a ride into it, not off its own label
            while (p := pred.get(('ride', s) if by_ride else s)) is not None:
                if p[0] == 'walk': seg.append(('walk', p[1], s, p[2], best_time(out, pred, s))); by_ride = len(p) > 3; s = p[1]
                else: seg.append(('ride', p[1], p[2], p[3], s, None)); by_ride = False; s = p[2]
            legs = seg[::-1] + legs; end = s
        return t_end, self._fill(legs)

    def __getstate__(self):
        """Everything except the ctypes handles, which cannot be pickled and cost nothing to remake.

        The point of pickling a router at all is that building one takes about three and a half minutes,
        nearly all of it parsing feeds and assembling eleven million connections. That work is
        deterministic given the same feeds and dates, so paying it once per day instead of once per idea is
        the single biggest thing available for the speed of the loop. What cannot be pickled is the loaded
        shared library and the pointers into the flat arrays; those are rebound on load in milliseconds.
        """
        d = self.__dict__.copy()
        for k in ('_fast', '_ptrs', '_ct', '_masks'): d.pop(k, None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self._fast = None
        if getattr(self, '_fa', None) is not None: self._bind_fast()

    def _bind_fast(self):
        """Load csa.so and point it at the flat arrays. Cheap, and the only part a pickle cannot carry."""
        import ctypes, subprocess
        self._fast = None
        here = os.path.dirname(os.path.abspath(__file__)); so = os.path.join(here, 'csa.so'); src = os.path.join(here, 'csa.c')
        try:
            if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
                subprocess.run(['cc', '-O3', '-shared', '-fPIC', src, '-o', so], check=True)
            lib = ctypes.CDLL(so)
        except Exception as e:
            print('fast scan unavailable:', e); return
        D = ctypes.POINTER(ctypes.c_double); I = ctypes.POINTER(ctypes.c_int); B = ctypes.POINTER(ctypes.c_ubyte)
        lib.csa_scan.argtypes = [ctypes.c_int, D, D, I, I, I, ctypes.c_int, ctypes.c_int, ctypes.c_int, I, I, D, B, D, I, B, ctypes.c_double, ctypes.c_double, I, I, D, I, D, I, B]
        lib.csa_scan.restype = ctypes.c_int
        self._ptrs = {k: v.ctypes.data_as(D if v.dtype == np.float64 else B if v.dtype == np.uint8 else I) for k, v in self._fa.items()}
        self._masks = {}; self._ct = (D, I, B); self._fast = lib

    def _init_fast(self):
        """Flat arrays + compiled scan (csa.c) for finish(); falls back to Python when no compiler."""
        import ctypes, subprocess
        self._fast = None
        here = os.path.dirname(os.path.abspath(__file__)); so = os.path.join(here, 'csa.so'); src = os.path.join(here, 'csa.c')
        try:
            if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
                subprocess.run(['cc', '-O3', '-shared', '-fPIC', src, '-o', so], check=True)
            ctypes.CDLL(so)
        except Exception as e:
            print('fast scan unavailable:', e); return
        self.trip_ids = {}
        ct = np.empty(len(self.ctrip), dtype=np.int32)
        for k, key in enumerate(self.ctrip): ct[k] = self.trip_ids.setdefault(key, len(self.trip_ids))
        ptr = np.zeros(self.N + 1, dtype=np.int32); to = []; w = []; fx = []
        for i in range(self.N):
            for j, x in self.foot.get(i, ()): to.append(j); w.append(x); fx.append(self._crosses(i, j))
            ptr[i + 1] = len(to)
        self._fa = dict(dep=np.ascontiguousarray(self.dep, dtype=np.float64), arr=np.ascontiguousarray(self.arr, dtype=np.float64),
                        cfrom=np.ascontiguousarray(self.cfrom, dtype=np.int32), cto=np.ascontiguousarray(self.cto, dtype=np.int32), ctrip=ct,
                        ptr=ptr, to=np.array(to, dtype=np.int32), w=np.array(w, dtype=np.float64), fx=np.array(fx, dtype=np.uint8))
        self._bind_fast()

    def _scan_fast(self, stops, times, trips, target, want_pred=False):
        """One layer in C. Labels come in and go out as parallel arrays (stop, time, trip index or -1)."""
        D, I, B = self._ct
        mask = self._masks.get(target)
        if mask is None:
            mask = np.zeros(self.N, dtype=np.uint8); ts_ = list(self.target_set(target))
            mask[ts_] = 1 if isinstance(target, str) else 2; mask[self.first_virtual:] = np.minimum(mask[self.first_virtual:], 1)
            self._masks[target] = mask
        best = np.full(self.N, np.inf); lt = np.full(self.N, -1, dtype=np.int32)
        o = np.argsort(-times)                 # so the earliest label wins when a stop repeats
        best[stops[o]] = times[o]; lt[stops[o]] = trips[o]
        k0 = int(np.searchsorted(self._fa['dep'], times.min()))
        p = self._ptrs
        pred = None; pa = (None,) * 7
        if want_pred:
            nt = len(self.trip_ids)
            pred = dict(conn=np.full(self.N, -1, dtype=np.int32), walk=np.full(self.N, -1, dtype=np.int32), walk_t=np.zeros(self.N),
                        bstop=np.full(nt, -1, dtype=np.int32), bdep=np.zeros(nt), best=best,
                        rconn=np.full(self.N, -1, dtype=np.int32), walk_ride=np.zeros(self.N, dtype=np.uint8))
            pa = (pred['conn'].ctypes.data_as(I), pred['walk'].ctypes.data_as(I), pred['walk_t'].ctypes.data_as(D),
                  pred['bstop'].ctypes.data_as(I), pred['bdep'].ctypes.data_as(D),
                  pred['rconn'].ctypes.data_as(I), pred['walk_ride'].ctypes.data_as(B))
        rc = self._fast.csa_scan(len(self._fa['dep']), p['dep'], p['arr'], p['cfrom'], p['cto'], p['ctrip'], k0, self.N, len(self.trip_ids),
                            p['ptr'], p['to'], p['w'], p['fx'], best.ctypes.data_as(D), lt.ctypes.data_as(I), mask.ctypes.data_as(B),
                            float(MIN_TRANSFER), float(SCAN_SLACK), *pa)
        if rc != 0: raise MemoryError(f'csa_scan failed (rc={rc})')
        hit = np.nonzero((mask > 0) & np.isfinite(best))[0]
        if want_pred: return hit.astype(np.int64), best[hit], lt[hit], pred
        return hit.astype(np.int64), best[hit], lt[hit]

    def _route_fast(self, start_stop, start_time, order):
        """route() on the compiled scan: same legs, reconstructed from predecessor arrays."""
        stops = np.atleast_1d(np.asarray(start_stop, dtype=np.int64)); times = np.full(len(stops), float(start_time)); trips = np.full(len(stops), -1, dtype=np.int32)
        layers = []; self.last_outs = []
        for t in order:
            stops, times, trips, pred = self._scan_fast(stops, times, trips, t, want_pred=True)
            if len(stops) == 0: return None, [('unreachable', t)]
            layers.append(pred); self.last_outs.append((stops, times, trips))
        i = int(np.argmin(times)); t_end = float(times[i]); end = int(stops[i]); legs = []
        arr = self._fa['arr']
        for pred in reversed(layers):
            s = end; seg = []; by_ride = False   # True: s was left on foot off a ride into it, not off its best label
            while True:
                if not by_ride and pred['walk'][s] >= 0:
                    f = int(pred['walk'][s]); by_ride = bool(pred['walk_ride'][s])
                    seg.append(('walk', f, s, float(pred['walk_t'][s]), float(pred['best'][s]))); s = f
                elif (k := int(pred['rconn'][s] if by_ride else pred['conn'][s])) >= 0:
                    by_ride = False; key = self.ctrip[k]; ti = self._fa['ctrip'][k]
                    b = int(pred['bstop'][ti]); seg.append(('ride', key, b, float(pred['bdep'][ti]), s, float(arr[k]))); s = b
                else: break
            legs = seg[::-1] + legs; end = s
        merged = []
        for l in legs:
            if l[0] == 'ride' and merged and merged[-1][0] == 'ride' and merged[-1][1] == l[1]:
                m = merged[-1]; merged[-1] = ('ride', m[1], m[2], m[3], l[4], l[5])
            else: merged.append(l)
        return t_end, merged

    def finish(self, start_stop, start_time, order, base=None, profile=False):
        """Finish time; with profile=True returns (finish, mean of the per-target first arrivals)."""
        if getattr(self, '_fast', None) is not None: return self._finish_fast(start_stop, start_time, order, base, profile)
        f = self._finish_py(start_stop, start_time, order, base)
        return (f, f) if profile else f

    @staticmethod
    def _lab_min(lab):
        if isinstance(lab, tuple): return float(lab[1].min()) if len(lab[1]) else float('inf')
        return min(v[0] for v in lab.values()) if lab else float('inf')

    def _finish_fast(self, start_stop, start_time, order, base=None, profile=False):
        k = 0; lab = None; mins = []
        if base:
            bo, bouts = base
            while k < len(order) and k < len(bo) and k < len(bouts) and order[k] == bo[k]: k += 1
            if k: lab = bouts[k - 1]
            if profile: mins = [self._lab_min(bouts[i]) for i in range(k)]
        if lab is None:   # start_stop may be one stop or an array of stops (free start: anywhere in a state)
            stops = np.atleast_1d(np.asarray(start_stop, dtype=np.int64)); times = np.full(len(stops), float(start_time)); trips = np.full(len(stops), -1, dtype=np.int32)
        elif isinstance(lab, tuple): stops, times, trips = lab
        else:
            stops = np.fromiter(lab.keys(), dtype=np.int64, count=len(lab)); times = np.array([v[0] for v in lab.values()], dtype=np.float64)
            trips = np.array([self.trip_ids.get(v[1], -1) if v[1] is not None else -1 for v in lab.values()], dtype=np.int32)
        for t in order[k:]:
            stops, times, trips = self._scan_fast(stops, times, trips, t)
            if len(stops) == 0: return (None, None) if profile else None
            if profile: mins.append(float(times.min()))
        f = float(times.min())
        return (f, sum(mins) / len(mins)) if profile else f

    def _finish_py(self, start_stop, start_time, order, base=None):
        """Finish time only. base=(order, outs) lets a shared prefix reuse cached layer labels."""
        labels = {int(s): (start_time, None) for s in np.atleast_1d(np.asarray(start_stop, dtype=np.int64))}; k = 0
        if base:
            bo, bouts = base
            while k < len(order) and k < len(bo) and k < len(bouts) and order[k] == bo[k]: k += 1
            if k: labels = bouts[k - 1]
        for t in order[k:]:
            labels, _, _ = self.scan(labels, self.target_set(t), guard=not isinstance(t, str))
            if not labels: return None
        return min(v[0] for v in labels.values())

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
    another feed (or give =uid, e.g. =ibus:1304); the first match is used."""
    def __init__(self, path, others):
        self.name = 'extra'; self.stops = {}; self.trips = {}; self.tz_mode = 'agency'; self.calendar_mode = 'weekday'
        self.cal = {}; self.cal_dates = {}; self.agency_tz = {}; self.stop_tz = {}; self.max_speed = 160; self.tz = timezone.utc   # hand-entered times are trusted
        if not os.path.exists(path): return
        allstops = [(uid, nm, lon, lat) for f in others for (uid, nm, lon, lat) in f.stops.values()]
        for k, r in enumerate(csv.DictReader(open(path))):
            if (r.get('agency') or '').startswith('#'): continue   # disabled row, kept for reference
            seq = []
            for i, item in enumerate(r['stops'].split('|')):
                nm, tm = item.split('@'); tm = tm.strip()
                arr, dep = (tm.split('/') + [tm])[:2] if '/' in tm else (tm, tm)
                if nm.strip().startswith('+'):   # new stop: +Name;lon;lat
                    n2, lo, la = nm.strip()[1:].split(';'); hit = ('extra:' + n2, n2, float(lo), float(la))
                else: hit = None
                hit = hit or next((s for s in allstops if nm.strip().startswith('=') and s[0] == nm.strip()[1:]), None) or next((s for s in allstops if s[1].lower() == nm.strip().lower() and not s[0].startswith('amtrak:')), None) or next((s for s in allstops if s[1].lower() == nm.strip().lower()), None) or next((s for s in allstops if nm.strip().lower() in s[1].lower()), None)
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
    sane = Feed.sane; runs_on = Feed.runs_on; connections = Feed.connections; _tz_for = Feed._tz_for


def load_feeds():
    feeds = [
        Feed(os.path.join(DATA_DIR, 'flix_gtfs.zip'), 'flix', 'utc', 'dates'),
        Feed(os.path.join(DATA_DIR, 'amtrak_gtfs.zip'), 'amtrak', 'agency', 'dates', max_speed=220),
        Feed(os.path.join(DATA_DIR, 'intercity_merged_gtfs.zip'), 'ibus', 'infer', 'weekday', skip_agencies=('Greyhound-us', 'FlixBus-us', 'Concord Coach Lines', 'Omnibus Express')),
    ]
    # carriers whose merged-feed times are known to be Eastern (Amtrak-sourced thruway)
    feeds[2].agency_tz['BeeLine Express-Village Travel'] = ZoneInfo('America/New_York')
    # extra agency feeds dropped into data/more_gtfs/ (local time zone from agency.txt, real calendars).
    # They go after the manual-trip feed so feed indexes stored in older result pickles stay valid.
    import glob
    import json
    kp = os.path.join(DATA_DIR, 'more_gtfs', 'keep_routes.json')
    keep = json.load(open(kp)) if os.path.exists(kp) else {}
    more = []
    for z in sorted(glob.glob(os.path.join(DATA_DIR, 'more_gtfs', '*.zip'))):
        nm = os.path.splitext(os.path.basename(z))[0]
        more.append(Feed(z, nm, 'agency', 'dates', max_speed=200, keep_routes=set(keep[nm]) if nm in keep else None))
        more[-1].city = nm not in INTERCITY_MORE
    feeds.append(ExtraFeed(os.path.join(DATA_DIR, 'extra_trips.csv'), feeds + more))
    return feeds + more


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


def cached_router(date, days, cache_dir=None, verbose=True):
    """A TimeRouter for these feeds and dates, built once and reloaded thereafter.

    Building one costs about three and a half minutes, nearly all of it parsing feeds and assembling
    eleven million connections, and it is paid again for every experiment. That is the tax that makes a
    one-line change to a ranking rule a ten minute question, which is most of why wrong ideas survive here:
    checking is expensive enough that it gets skipped.

    The key covers everything the answer depends on: every file under data/ by size and mtime, the dates
    asked for, and the source of this module. A stale cache is worse than no cache, because it would be a
    silent wrong answer in a project whose whole difficulty is that wrong answers look fine, so any change
    to the feeds or to this file produces a different key and a rebuild rather than a hit.
    """
    import hashlib, pickle, glob
    here = os.path.dirname(os.path.abspath(__file__))
    cache_dir = cache_dir or os.path.join(here, '..', 'out')
    files = sorted(glob.glob(os.path.join(here, '..', 'data', '**', '*'), recursive=True))
    # Nanosecond mtimes, because a second is long enough to edit a feed inside and integer seconds would
    # then serve the old world from cache.
    sig = [(os.path.relpath(f, here), os.path.getsize(f), os.stat(f).st_mtime_ns) for f in files if os.path.isfile(f)]
    # Both sources that decide what a router is. common.py carries StateIndex, ABBR and hav, so a change
    # to how a stop is assigned a state, or to the distance function the footpaths are built from, changes
    # every router without changing this file.
    for src in (__file__, os.path.join(here, 'common.py')):
        if os.path.isfile(src): sig.append(hashlib.sha1(open(src, 'rb').read()).hexdigest())
    sig.append((str(date), int(days)))
    # Every knob that changes what a router IS. All six are environment variables, so the same source and
    # the same feeds can still describe different worlds, and a cache that ignored them would hand back the
    # wrong one without a word. BUS48_LOCAL_MAX_KM=5 against a router built at 10 is not an error anyone
    # would see; it is a plausible number from a different universe, which is this project's whole problem.
    sig.append(('cfg', WALKIN_KM, MIN_TRANSFER, SCAN_SLACK, LOCAL_MAX_KM, LOCAL_PROXY_ALL, STOP_TZ_LOCAL,
                WALK_MAX_KM, WALK_SPEED))
    key = hashlib.sha1(repr(sig).encode()).hexdigest()[:16]
    path = os.path.join(cache_dir, f'router_{key}.pkl')
    if os.path.exists(path):
        t0 = time.time()
        try:
            R = pickle.load(open(path, 'rb'))
            try: os.utime(path)     # mtime = last use, so the pruning below keeps the caches in use
            except OSError: pass
            if verbose: print(f'router from cache in {time.time() - t0:.1f} s ({os.path.basename(path)})', flush=True)
            return R
        except Exception as e:
            print(f'cache unreadable, rebuilding: {type(e).__name__}: {e}', flush=True)
    t0 = time.time()
    R = TimeRouter(load_feeds(), date, days)
    os.makedirs(cache_dir, exist_ok=True)
    # Every edit to the feeds or this file makes a new ~650 MB cache and the old ones never become valid again,
    # so without pruning they filled the disk twice (Sep 27 and Sep 28), and a full disk is also where macOS
    # puts swap. Before writing, keep only the most recently used BUS48_ROUTER_CACHES - 1 (default 2 in total,
    # since regress and the searches use different date windows), and drop temp files a dead run left behind.
    keep = max(1, int(os.environ.get('BUS48_ROUTER_CACHES', '2')))
    old = sorted(glob.glob(os.path.join(cache_dir, 'router_*.pkl')), key=os.path.getmtime, reverse=True)
    for f in old[keep - 1:]:
        try: os.remove(f); print(f'pruned old router cache {os.path.basename(f)}', flush=True)
        except OSError: pass
    for f in glob.glob(os.path.join(cache_dir, 'router_*.tmp')):
        try:
            if time.time() - os.path.getmtime(f) > 3600: os.remove(f)
        except OSError: pass
    tmp = path + f'.{os.getpid()}.tmp'
    try:
        with open(tmp, 'wb') as fh: pickle.dump(R, fh, protocol=5)
        os.replace(tmp, path)       # atomic, so two runs racing cannot leave half a router behind
        if verbose: print(f'router built in {time.time() - t0:.0f} s and cached', flush=True)
    except Exception as e:
        print(f'could not cache the router: {type(e).__name__}: {e}', flush=True)
        if os.path.exists(tmp): os.remove(tmp)
    return R
