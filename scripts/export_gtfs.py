"""Export everything collected by hand as a package other people can check and load (Oct 26 2026).

Writes export/bus48_supplement/ (tracked in git) and export/bus48_supplement_gtfs.zip (the gtfs/ folder):

  gtfs/                 a GTFS feed of every hand-entered trip in data/manual/*.toml, read by the router's own loader
                        (ExtraFeed), so the times are exactly the ones the router uses. Stops that are public-feed
                        stops keep their feed's id (ibus:661, flix:<uuid>, ...) and carry stop_points.csv corrections.
                        trips.txt has two extra columns: source_file (the TOML) and source_note (its route line,
                        which is where each trip says where it came from: carrier site, screenshot, API, date).
                        transfers.txt holds the measured walks from data/walk_links.csv (transfer_type 2).
  walks.csv             the same measured walks, with minutes, miles and the note of how each was measured.
  timed_walks.csv       on-foot crossings modelled as timed departures because the path has opening hours
                        (Big River Crossing, 06:00-22:00), one row per direction: first, last, every N min.
  corrections/          drop_trips.csv: public-feed trips the carrier's own site contradicts, and what replaced
                        them; stop_points.csv: public-feed stops placed in the wrong spot, and the measured point.
  city_routes.csv       which routes of each local transit feed the router keeps (data/more_gtfs/keep_routes.json).
  README.md             what this is and how to use it.

Times: GTFS wants every stop_time in the agency's zone, and a hand-entered trip may give each stop's local clock.
Each trip is written in the zone of its own first stop (or its fixed tz), and the agency is split by zone where a
carrier runs in more than one ("Tornado Bus (America/Chicago)"). Offsets are taken on 2026-11-05, as the router
does; the window has no clock change. Calendars are the trip's weekday pattern from 2026-11-01 to 2026-12-31.

Leaf script: nothing imports it.   python3 export_gtfs.py        (from scripts/; loads all feeds, ~3 min)
"""
import csv, glob, json, os, re, shutil, sys, tomllib, zipfile
from collections import defaultdict
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo
from time_router import load_feeds, DATA_DIR, _tz_at

OUT = os.path.join(os.path.dirname(DATA_DIR), 'export', 'bus48_supplement')   # tracked, so a pull carries it
REF = date(2026, 11, 5)
START, END = '20261101', '20261231'
URLS = {'Tornado Bus': 'https://www.tornadobus.com', 'El Expreso': 'https://www.tornadobus.com',
        'Jefferson Lines': 'https://www.jeffersonlines.com', 'Greyhound': 'https://www.greyhound.com',
        'FlixBus': 'https://www.flixbus.com', 'Amtrak': 'https://www.amtrak.com', 'RedCoach': 'https://www.redcoachusa.com',
        'Vonlane': 'https://www.vonlane.com', 'Salt Lake Express': 'https://saltlakeexpress.com',
        'Dartmouth Coach': 'https://dartmouthcoach.com', 'Concord Coach': 'https://concordcoachlines.com',
        'Omnibus Express': 'https://omnibusexpress.com', 'Express Arrow': 'https://expressarrow.com',
        'Peter Pan': 'https://peterpanbus.com', 'Van Galder': 'https://www.coachusa.com/van-galder',
        'Northwestern Stage Lines': 'https://northwesternstagelines.com', 'Groome': 'https://groometransportation.com'}


def off(zone):   # seconds east of UTC on the reference date
    return datetime(REF.year, REF.month, REF.day, 12, tzinfo=zone).utcoffset().total_seconds()


def hhmmss(s):
    s = int(round(s)); return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def sec(x):
    return sum(int(p) * m for p, m in zip(x.split(':'), (3600, 60, 1)))


def url_for(name):
    return next((u for k, u in URLS.items() if name.lower().startswith(k.lower())), 'https://www.google.com/search?q=' + quote(name))


def main():
    feeds = load_feeds()
    ex = next(f for f in feeds if f.name == 'extra')
    allstops = {uid: (nm, lon, lat) for f in feeds for (uid, nm, lon, lat) in f.stops.values()}
    fixes = {}
    with open(os.path.join(DATA_DIR, 'stop_points.csv'), encoding='utf-8') as fh:
        for r in csv.DictReader(fh): fixes[r['uid']] = (float(r['lon']), float(r['lat']), r['note'])
    # which TOML each trip came from (the loader keeps the id, not the file)
    src = {}
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, 'manual', '*.toml'))):
        stem = os.path.splitext(os.path.basename(fp))[0]
        for n, tr in enumerate(tomllib.load(open(fp, 'rb')).get('trip', [])): src[tr.get('id') or f'{stem}:{n}'] = stem + '.toml'

    if os.path.exists(OUT): shutil.rmtree(OUT)
    G = os.path.join(OUT, 'gtfs'); os.makedirs(G); os.makedirs(os.path.join(OUT, 'corrections'))
    stops = {}   # stop_id -> (name, lat, lon, tz, note)

    def add_stop(uid, nm=None, lon=None, lat=None):
        if uid in stops: return uid
        if nm is None: nm, lon, lat = allstops[uid]
        note = ''
        if uid in fixes: lon, lat, note = fixes[uid]
        stops[uid] = (nm, lat, lon, _tz_at(lon, lat) or '', note)
        return uid

    agencies = {}; routes = {}; trips = []; times = []; cals = {}; timed_walks = []
    for tid, tr in ex.trips.items():
        if not tr['stops'] or ex.cal[tr['service']].get('monday') is None: continue
        days = ''.join(ex.cal[tr['service']][d] for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'))
        if days == '0000000': continue   # stop definitions that never run
        seq = tr['stops']; first = seq[0][1]
        zone = tr['tz'] or tr['zones'].get(first) or ex.agency_tz.get(tr['agency'], ZoneInfo('UTC'))
        rows = []
        for i, sid, a, d in seq:
            if not tr['tz']:   # local clock at the stop -> the first stop's zone
                zs = tr['zones'].get(sid, zone); shift = off(zone) - off(zs)
                a, d = a + shift, d + shift
            uid, nm, lon, lat = ex.stops[sid]
            rows.append((add_stop(uid, nm, lon, lat), a, d))
        if tr['agency'].startswith('On foot'):
            timed_walks.append((tr['agency'], tid, tr['route'], days, str(zone), stops[rows[0][0]][0], hhmmss(rows[0][2]),
                                stops[rows[-1][0]][0], hhmmss(rows[-1][1]), src.get(tid, '')))
            continue
        aid = re.sub(r'[^A-Za-z0-9]+', '_', f"{tr['agency']}_{zone}").strip('_')
        agencies[aid] = (tr['agency'], str(zone), url_for(tr['agency']))
        rid = aid + '_r'; routes[rid] = (aid, tr['agency'])
        cid = 'wk' + days; cals[cid] = days
        trips.append((rid, cid, tid, tr['route'], src.get(tid, '')))
        times += [(tid, hhmmss(a), hhmmss(d), sid, n + 1) for n, (sid, a, d) in enumerate(rows)]
    # an agency split over zones gets the zone in every name, not only the second one seen
    by_name = defaultdict(list)
    for aid, (nm, z, u) in agencies.items(): by_name[nm].append(aid)
    for base, ids in by_name.items():
        for aid in ids: agencies[aid] = (f'{base} ({agencies[aid][1]})' if len(ids) > 1 else base,) + agencies[aid][1:]

    # measured walks
    walks = []
    with open(os.path.join(DATA_DIR, 'walk_links.csv'), encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            for u in (r['from_uid'], r['to_uid']):
                if u.startswith('extra:'):
                    nm = u[6:]; hit = next(((n, lo, la) for (uid, n, lo, la) in ex.stops.values() if uid == u), None)
                    if hit: add_stop(u, *hit)
                elif u in allstops: add_stop(u)
            walks.append(r)

    def w(name, header, rows):
        with open(os.path.join(G, name), 'w', newline='', encoding='utf-8') as fh:
            c = csv.writer(fh); c.writerow(header); c.writerows(rows)
    w('agency.txt', ['agency_id', 'agency_name', 'agency_url', 'agency_timezone'], [(k, n, u, z) for k, (n, z, u) in sorted(agencies.items())])
    w('routes.txt', ['route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_type'],
      [(k, a, '', n, 2 if n.startswith('Amtrak') or 'Commuter Rail' in n else 3) for k, (a, n) in sorted(routes.items())])
    w('calendar.txt', ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'start_date', 'end_date'],
      [(k, *list(d), START, END) for k, d in sorted(cals.items())])
    w('trips.txt', ['route_id', 'service_id', 'trip_id', 'trip_headsign', 'source_file', 'source_note'],
      [(r, c, t, '', f, n) for r, c, t, n, f in trips])
    w('stop_times.txt', ['trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence'], times)
    w('stops.txt', ['stop_id', 'stop_name', 'stop_lat', 'stop_lon', 'stop_timezone', 'location_note'],
      [(k, n, f'{la:.6f}', f'{lo:.6f}', z, note) for k, (n, la, lo, z, note) in sorted(stops.items())])
    w('transfers.txt', ['from_stop_id', 'to_stop_id', 'transfer_type', 'min_transfer_time'],
      [(r['from_uid'], r['to_uid'], 2, int(float(r['minutes']) * 60)) for r in walks
       if r['minutes'] and r['from_uid'] in stops and r['to_uid'] in stops])
    w('feed_info.txt', ['feed_publisher_name', 'feed_publisher_url', 'feed_lang', 'feed_start_date', 'feed_end_date', 'feed_version'],
      [('bus48 (Nick Pruitt), hand-collected', 'https://www.google.com/search?q=48+state+bus+record', 'en', START, END, date.today().isoformat())])

    with open(os.path.join(OUT, 'walks.csv'), 'w', newline='', encoding='utf-8') as fh:
        c = csv.writer(fh); c.writerow(['from_stop_id', 'from_name', 'to_stop_id', 'to_name', 'minutes', 'miles', 'how_measured'])
        for r in walks:
            c.writerow([r['from_uid'], stops.get(r['from_uid'], ('?',))[0], r['to_uid'], stops.get(r['to_uid'], ('?',))[0],
                        r['minutes'], r.get('miles', ''), r['note']])
    groups = defaultdict(list)   # one row per crossing: the same walk repeats every few minutes while the path is open
    for kind, tid, desc, days, tz, a, leave, b, arrive, f in timed_walks:
        dur = (sec(arrive) - sec(leave)) // 60
        groups[(kind, desc, days, tz, a, b, dur, f)].append(sec(leave))
    with open(os.path.join(OUT, 'timed_walks.csv'), 'w', newline='', encoding='utf-8') as fh:
        c = csv.writer(fh); c.writerow(['kind', 'description', 'days_mon_sun', 'timezone', 'from', 'to', 'minutes',
                                        'first_leave', 'last_leave', 'every_min', 'source_file'])
        for (kind, desc, days, tz, a, b, dur, f), ls in sorted(groups.items()):
            ls.sort(); gap = min((y - x for x, y in zip(ls, ls[1:])), default=0) // 60
            c.writerow([kind, desc, days, tz, a, b, dur, hhmmss(ls[0])[:5], hhmmss(ls[-1])[:5], gap or '', f])
    shutil.copy(os.path.join(DATA_DIR, 'drop_trips.csv'), os.path.join(OUT, 'corrections', 'drop_trips.csv'))
    shutil.copy(os.path.join(DATA_DIR, 'stop_points.csv'), os.path.join(OUT, 'corrections', 'stop_points.csv'))
    keep = json.load(open(os.path.join(DATA_DIR, 'more_gtfs', 'keep_routes.json')))
    with open(os.path.join(OUT, 'city_routes.csv'), 'w', newline='', encoding='utf-8') as fh:
        c = csv.writer(fh); c.writerow(['feed', 'routes_kept'])
        for z in sorted(glob.glob(os.path.join(DATA_DIR, 'more_gtfs', '*.zip'))):
            nm = os.path.splitext(os.path.basename(z))[0]; c.writerow([nm, ' '.join(keep[nm]) if nm in keep else '(all)'])

    # checks: every stop_time references a stop, times never go backwards within a trip
    bad = []
    by_trip = defaultdict(list)
    for t, a, d, s, n in times:
        if s not in stops: bad.append(f'{t}: unknown stop {s}')
        by_trip[t].append((n, a, d))
    for t, rs in by_trip.items():
        prev = -1
        for n, a, d in sorted(rs):
            if sec(a) < prev or sec(d) < sec(a): bad.append(f'{t}: time goes backwards at stop {n}')
            prev = sec(d)
    zp = os.path.join(os.path.dirname(OUT), 'bus48_supplement_gtfs.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(G)): z.write(os.path.join(G, f), f)
    shutil.copy(os.path.join(os.path.dirname(OUT), 'README.md'), os.path.join(OUT, 'README.md')) if os.path.exists(os.path.join(os.path.dirname(OUT), 'README.md')) else None
    print(f'{len(agencies)} agencies, {len(routes)} routes, {len(trips)} trips, {len(times)} stop times, {len(stops)} stops, '
          f'{len(walks)} walks, {len(timed_walks)} timed walks')
    print(f'wrote {OUT} and {zp}')
    print(f'{len(bad)} problems' + ''.join('\n  ' + b for b in bad[:20]))


if __name__ == '__main__':
    main()
