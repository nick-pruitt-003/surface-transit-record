"""Measure each Amtrak route's average great-circle speed between stops from the
GTFS timetable and write data/route_speeds.json (used to weight rail legs)."""
import csv, io, json, math, os, zipfile
from collections import defaultdict
from common import data_path, hav, DATA_DIR


def sec(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + int(s)


def main():
    z = zipfile.ZipFile(data_path('amtrak_gtfs.zip'))
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))
    stops = {s['stop_id']: (float(s['stop_lon']), float(s['stop_lat'])) for s in rd('stops.txt')}
    rt = {r['route_id']: r for r in rd('routes.txt')}
    trip_route = {t['trip_id']: t['route_id'] for t in rd('trips.txt')}
    st = defaultdict(list)
    for r in rd('stop_times.txt'):
        st[r['trip_id']].append((int(r['stop_sequence']), r['stop_id'], sec(r['arrival_time']), sec(r['departure_time'])))
    spd = defaultdict(list)
    for tid, rows in st.items():
        rows.sort(); rid = trip_route[tid]
        if rt[rid]['route_type'] != '2' or len(rows) < 2:
            continue
        d = sum(hav(stops[rows[i][1]], stops[rows[i + 1][1]]) for i in range(len(rows) - 1))
        t = (rows[-1][2] - rows[0][3]) / 3600
        if t > 0.5 and d > 30:
            spd[rt[rid]['route_long_name']].append(d / t)
    out = {k: sum(v) / len(v) for k, v in spd.items()}
    for k, v in sorted(out.items(), key=lambda x: -x[1]):
        print(f'{k:40s} {v:5.1f} km/h')
    json.dump(out, open(os.path.join(DATA_DIR, 'route_speeds.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
