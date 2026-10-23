"""Fetch Tornado Bus timetables from the booking site's own API (Oct 22 2026). Leaf script: nothing imports it.

  py tornado_fetch.py                     # crawl, writes ../out/tornado_api/runs.json
  py tornado_fetch.py --toml              # turn runs.json into data/manual/tornado_api.toml

The site's displayed stop times are unreliable (a time zone shift is applied once somewhere along the route, so
stops appear out of order), but its stop-list endpoint gives every leg's drive time and dwell in seconds. The real
schedule is the departure (local time at the first stop) plus the cumulative seconds, which needs no time zone
guesswork. Stop coordinates and addresses come from the same endpoint.

Crawl: US cities by state search ("NE -"), then a trip search from every US city to a set of hubs on each day of one
week; each run (itinerary alias) is kept with the widest stop span seen, then its stop list is fetched once.
"""
import json, os, sys, time, urllib.request
from datetime import date, timedelta

SEARCH = 'https://api.balancer.search-travel.tornadobustec.com/v1/web'
SALE = 'https://api.balancer.sale.tornadobustec.com/v1/web'
OUT = os.path.join(os.path.dirname(__file__), '..', 'out', 'tornado_api')
STATES = ('AL AR AZ CA CO CT DE FL GA IA ID IL IN KS KY LA MA MD ME MI MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR '
          'PA RI SC SD TN TX UT VA VT WA WI WV WY').split()
WEEK = [date(2026, 11, 16) + timedelta(days=i) for i in range(7)]          # Mon Nov 16 .. Sun Nov 22
PAUSE = 0.8


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'content-type': 'application/json', 'user-agent': 'curl/8.4.0', 'accept': '*/*', 'origin': 'https://webtec.tornadobus.com', 'referer': 'https://webtec.tornadobus.com/'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                out = json.loads(r.read().decode())
            time.sleep(PAUSE)
            return out
        except Exception as e:
            print(f'  retry {attempt + 1}: {e}', flush=True); time.sleep(30 * (attempt + 1) if '429' in str(e) else 3 * (attempt + 1))
    raise RuntimeError(f'gave up on {url}')   # never record a failed search as 'no trips'


def us_cities():
    found = {}
    for st in STATES:
        got = post(f'{SEARCH}/select/origin', {'value': f'{st} -'}).get('data', [])
        if len(got) >= 40:      # the endpoint returns at most 40: split the state by the stop name's first character
            for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
                got += post(f'{SEARCH}/select/origin', {'value': f'{st} - {ch}'}).get('data', [])
        for x in got:
            if f'({st} -' in x['name']: found[x['id']] = x
    return found


def trips(a, b, d):
    body = {'limit': 50, 'page': 1, 'filters': {'date': d.isoformat(), 'city': [a, b], 'passengerNumber': 1,
            'passengerDisabilityNumber': 0, 'orderTravel': 1060, 'orderMaxMinTravel': 1, 'isPoint': False,
            'currencyID': 567, 'externalInitId': 0, 'externalEndId': 0, 'routeID': None, '_rowId': None}}
    return post(f'{SEARCH}/list/departure-travels?isMultiRoute=true&isReturn=false', body).get('data', []) or []


def stops(a, b, itin):
    d = post(f'{SALE}/list/route/map', {'routes': [{'cityEndId': b, 'cityInitId': a, 'itineraryId': itin, 'nOrder': 1}]})
    return (d.get('data') or [{}])[0].get('stops', [])


def crawl():
    os.makedirs(OUT, exist_ok=True)
    cities = us_cities()
    print(f'{len(cities)} US cities', flush=True)
    json.dump(cities, open(os.path.join(OUT, 'us_cities.json'), 'w'), indent=1)
    names = {c['id']: c['name'] for c in cities.values()}
    hubs = [cid for cid, n in names.items() if any(k in n for k in (
        'TBC I-30', 'Lockwood', 'TBC Chicago', 'TBC Doraville', 'TBC Charlotte', 'TBC Raleigh', 'TBC KS',
        'TBC Omaha', 'Minneapolis', 'Maria International', 'Milwaukee', 'TX - TBC El Paso', 'Grand Rapids', 'West Memphis',
        'TBC Nashville', 'South Sioux City', 'Jackson, MS', 'Manassas', 'Indianapolis', 'Orlando', 'Miami',
        'Gainesville', 'Selma', 'Atlanta'))]
    print(f'{len(hubs)} hubs: ' + '; '.join(names[h][:30] for h in hubs), flush=True)
    core = [cid for cid in hubs if any(k in names[cid] for k in ('TBC I-30', 'Lockwood', 'TBC Chicago', 'TBC Doraville',
            'TBC KS', 'Maria International', 'TBC Charlotte', 'South Sioux City'))]
    print(f'{len(core)} core hubs', flush=True)
    main = [cid for cid in core if any(k in names[cid] for k in ('TBC I-30', 'Lockwood', 'TBC Chicago', 'TBC Doraville'))]
    runs = {}          # alias -> {'first': (stp, city), 'last': (stp, city), 'itin': {date: (itin, a, b, dep)}}
    path = os.path.join(OUT, 'pairs.json')
    done = json.load(open(path)) if os.path.exists(path) else {}
    n = 0
    for a in names:
        for b in hubs:
            if a == b: continue
            if b not in core or (a not in core and b not in main): continue
            for d in (WEEK if a in core else WEEK[2:3]):   # core hubs every day; other cities on one day (discovery only)
                key = f'{a}-{b}-{d}'
                if key not in done:
                    done[key] = [{k: t[k] for k in ('id', 'itineraryAlias', 'iniRouteStp', 'endRouteStp', 'routeID',
                                  'dateinit', 'dateEnd', 'cityInitID', 'cityEndID')} for t in trips(a, b, d) if t.get('itineraryAlias')]
                    n += 1
                    if n % 50 == 0: json.dump(done, open(path, 'w')); print(f'  {n} searches', flush=True)
    # reverse discovery: from each core hub to every city on one day, so runs that leave a hub for a non-hub city
    # (Dallas -> Minneapolis, Chicago -> Grand Rapids, Atlanta -> Houston via the coast) are seen to their far end
    for a in core:
        for b in names:
            if b == a or b in core: continue
            key = f'{a}-{b}-{WEEK[2]}'
            if key not in done:
                done[key] = [{k: t[k] for k in ('id', 'itineraryAlias', 'iniRouteStp', 'endRouteStp', 'routeID',
                              'dateinit', 'dateEnd', 'cityInitID', 'cityEndID')} for t in trips(a, b, WEEK[2]) if t.get('itineraryAlias')]
                n += 1
                if n % 50 == 0: json.dump(done, open(path, 'w')); print(f'  {n} searches', flush=True)
    json.dump(done, open(path, 'w'))
    for key, lst in done.items():
        for t in lst:
            r = runs.setdefault(t['itineraryAlias'], {'first': None, 'last': None, 'dates': {}})
            if r['first'] is None or t['iniRouteStp'] < r['first'][0]: r['first'] = (t['iniRouteStp'], t['cityInitID'])
            if r['last'] is None or t['endRouteStp'] > r['last'][0]: r['last'] = (t['endRouteStp'], t['cityEndID'])
    print(f'{len(runs)} runs (itinerary aliases)', flush=True)
    # each run once over its widest span, on every day of the week it runs
    out = {}
    for alias, r in runs.items():
        a, b = r['first'][1], r['last'][1]
        days = {}
        for d in WEEK:
            for t in trips(a, b, d):
                if t.get('itineraryAlias') == alias: days[d.isoformat()] = (t['id'], t['dateinit'])
        if not days: continue
        itin = next(iter(days.values()))[0]
        out[alias] = {'from': names.get(a, a), 'to': names.get(b, b), 'a': a, 'b': b, 'days': days, 'stops': stops(a, b, itin)}
        print(f'{alias}: {names.get(a, a)[:30]} -> {names.get(b, b)[:30]}, {len(days)} days, '
              f'{len(out[alias]["stops"])} legs', flush=True)
    json.dump(out, open(os.path.join(OUT, 'runs.json'), 'w'), indent=1)


# Stop points that override the API's own: the API's address is right but its point is not (or Nick has the
# address). Checked Oct 23 2026 by geocoding every API address with the Census geocoder and OpenStreetMap
# (out/tornado_api/geocheck.json); kept here where both agree and the API point is over 0.5 km away.
POINT_FIX = {
    'La Plazita Latina': (42.50032, -96.42402, '1300 W 4th St, Sioux City IA (Nick; Census + OSM)'),
    'L.A. Fashion - Sioux City': (42.47978, -96.41320, '1021 Dakota Ave, South Sioux City NE (Nick; Census)'),
    'Rio Grande Market': None,   # 511 Lyon St, Carthage MO (Nick's address)
    'LA MICHOACANA #2': (39.94252, -83.09596, '3629 Sullivant Ave, Columbus OH (Nick; Census + OSM)'),
    'Paqueteria Mexico LLC': (37.7246, -97.3360, '114 E 21st St N, Wichita KS (Nick)'),
    'Busy Bee-Live Oak': (30.33191, -82.96037, 'Busy Bee, 6458 US-129, Live Oak FL (Nick, Oct 23 2026)'),
    'El Potro-Lake City': (30.17886, -82.67277, 'El Potro, 2470 US-90, Lake City FL (Nick, Oct 23 2026)'),
    'Exxon Gas Station-Winfield': (33.16188, -95.11143, 'Exxon, Winfield TX (Nick, Oct 23 2026); the API address field says Dallas'),
    'Conoco Gas Station': (28.78201, -96.95865, 'Conoco, 4102 US-59, Victoria TX (Nick, Oct 23 2026)'),
    'La Tropicana-Goldsboro': (35.33818, -78.03066, 'La Tropicana, Goldsboro NC (Nick, Oct 23 2026); the API point was right, both geocoders wrong'),
    'La Vaquita-Port Arthur': (29.92052, -93.90980, 'La Vaquita, 4925 Gulfway Dr, Port Arthur TX (Nick, Oct 23 2026)'),
    'Dolphin Mall-Miami ( Estacionamiento Parada Autobuses Puerta #8)': (25.78994, -80.38273, 'Dolphin Mall bus station (Nick, Oct 23 2026)'),
    'Jackson, MS(Flying J Travel center)': (32.27724, -90.16002, 'Flying J, I-20 exit 47, 685 US-80, Pearl MS (Nick, Oct 23 2026)'),
    'Exit 86-Fwy 65 Pilot-Glendale': (37.59560, -85.86490, 'Pilot at I-65 exit 86, Glendale KY (Nick, Oct 23 2026)'),
    'TBC Omaha': None, 'TBC Office Indianapolis': None, 'BP Gas Station - Ames': None,
    'Waite Park (El Torito Mexican Market)': None,
    'El Charro Mexican Restaurant-Arcadia': None, "Lupita's Grocery-Effingham": None, 'Servicios Guerrero LLC': None,
    'El mercadito schaumburg': None, 'TBC Harrisburg': None, 'TBC Fort Worth': None,
}   # None: take the Census point from geocheck.json


def point_fixes():
    g = os.path.join(OUT, 'geocheck.json')
    geo = json.load(open(g)) if os.path.exists(g) else {}
    out = {}
    for name, fix in POINT_FIX.items():
        if fix: out[name] = fix
        elif geo.get(name, {}).get('geo'): out[name] = (geo[name]['geo'][0], geo[name]['geo'][1], 'Census geocode of the API address; OSM agrees')
    return out


def to_toml():
    """runs.json -> data/manual/tornado_api.toml: stop times are the departure plus the cumulative drive and dwell
    seconds, in the first stop's time zone (one fixed zone per trip, so no display shift can creep in)."""
    import re
    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()
    runs = json.load(open(os.path.join(OUT, 'runs.json')))
    fixes = point_fixes()
    stops, keys, trips = {}, {}, []
    def key(name, lat, lng):
        if name in fixes: lat, lng = fixes[name][:2]
        k = (name, round(float(lat), 5), round(float(lng), 5))
        if k not in keys:
            base = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:40] or 'stop'
            kk = f'tapi_{base}'; i = 2
            while kk in stops: kk = f'tapi_{base}_{i}'; i += 1
            keys[k] = kk; stops[kk] = (name, float(lat), float(lng))
        return keys[k]
    for alias, r in sorted(runs.items()):
        legs = r['stops']
        if not legs: continue
        by_dep = {}
        for d, (itin, dateinit) in r['days'].items():
            by_dep.setdefault(dateinit[11:16], set()).add(date.fromisoformat(d).weekday())
        seq, t = [], 0
        first = legs[0]
        seq.append([key(first['cityInit'], first['cityInitLat'], first['cityInitLng']), 0, 0])
        for g in legs:
            w = g.get('waitTravel') or 0
            seq[-1][2] = t + w                          # dwell at this leg's start stop
            t = seq[-1][2] + (g.get('timeTravel') or 0)
            seq.append([key(g['cityEnd'], g['cityEndLat'], g['cityEndLng']), t, t])
        tz = tf.timezone_at(lat=float(first['cityInitLat']), lng=float(first['cityInitLng'])) or 'America/Chicago'
        for hhmm, wds in sorted(by_dep.items()):
            h0, m0 = int(hhmm[:2]), int(hhmm[3:])
            fmt = lambda s_: f'{(h0 * 3600 + m0 * 60 + s_) // 3600:02d}:{((h0 * 3600 + m0 * 60 + s_) % 3600) // 60:02d}'
            st = [f'{k} {fmt(a)}' + (f'/{fmt(dp)}' if dp != a else '') for k, a, dp in seq]
            days = ''.join('1' if i in wds else '0' for i in range(7))
            trips.append((alias, r['from'], r['to'], hhmm, days, tz, st))
    out = ['agency = "Tornado Bus"', '# Generated by scripts/tornado_fetch.py --toml from the booking site API (Oct 22 2026).',
           '# Times: departure at the first stop + cumulative drive and dwell seconds, in the first stop zone.', '', '[stops]']
    for kk, (name, lat, lng) in stops.items():
        out.append(f'{kk} = {{ name = {json.dumps(name + " (Tornado)")}, lon = {lng:.6f}, lat = {lat:.6f} }}'
                   + (f'   # point: {fixes[name][2]}' if name in fixes else ''))
    for n, (alias, fr, to, hhmm, days, tz, st) in enumerate(trips):
        out += ['', '[[trip]]', f'id = "ta{n}"',
                f'route = {json.dumps(f"Tornado {alias}: {fr} -> {to}, dep {hhmm} (API)")}',
                f'days = "{days}"', f'tz = "{tz}"', 'stops = [' + ', '.join(json.dumps(x) for x in st) + ']']
    dst = os.path.join(os.path.dirname(__file__), '..', 'data', 'manual', 'tornado_api.toml')
    open(dst, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print(f'{len(trips)} trips, {len(stops)} stops -> {dst}')


if __name__ == '__main__':
    to_toml() if '--toml' in sys.argv else crawl()
