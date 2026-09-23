"""Joint table: earliest arrival between block-edge hubs, for every departure hour over a week. Leaf script.

A route is a loop of blocks (the Northwest spine, the southern and eastern sweep, the interior) cut open at one
joint; the joints between blocks are what differ between shapes. This asks the router, exactly, what each joint
costs at each hour of the week, so a block order can be priced before any search is spent on it.

A hub is a point. You start at the stops within 0.3 km of it at the departure time (the same station under
several feeds) and have reached a hub at any stop within 1 km of its point. Hubs are points, not names, because
the intercity feed has per-trip copies of stations placed hundreds of km away (Chicago Bus Station 1#1605 sits
at Davenport); taking a name would silently start some departures in the wrong city.

Gated on two joints the known routes ride before anything prints:
  Billings Sun 00:25 -> Spokane by Sun 10:30 (X's first leg, Jefferson 01:30)
  Houston Wed 18:00 -> Tallahassee by Thu 11:00 (the I-10 Greyhound 18:35 in X and the control)

Output: ../out/joints.pkl  {'hubs': [...], 't0': epoch, 'step': s, 'arr': {(a, b): [arrival epoch or inf] * n}}
        ../out/joints.txt  best and worst door-to-door hours per pair
"""
import argparse, pickle, time, math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from pick import gate

HUBS = [  # name, lon, lat
    ('Hanover', -72.288, 43.702), ('WhiteRiverJct', -72.334, 43.647), ('Boston', -71.056, 42.350),
    ('WashingtonDC', -77.006, 38.898), ('Huntington', -82.438, 38.422), ('Toledo', -83.542, 41.638),
    ('Detroit', -83.058, 42.328), ('Chicago', -87.644, 41.875), ('Indianapolis', -86.161, 39.762),
    ('Minneapolis', -93.276, 44.981), ('Fargo', -96.850, 46.891), ('Billings', -108.496, 45.790),
    ('Sheridan', -106.945, 44.774), ('Spokane', -117.415, 47.657), ('Denver', -105.001, 39.754),
    ('LasVegasAirport', -115.148, 36.086), ('BarstowAmtrak', -117.025, 34.905), ('KansasCity', -94.569, 39.100),
    ('Dallas', -96.804, 32.779), ('Houston', -95.302, 29.735), ('Tallahassee', -84.283, 30.444),
    ('JacksonvilleAmtrak', -81.724, 30.366), ('Atlanta', -84.397, 33.748), ('Memphis', -89.993, 35.062),
    ('Shreveport', -93.757, 32.500), ('JacksonMS', -90.191, 32.301), ('Birmingham', -86.808, 33.512),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours', type=int, default=168, help='departure window from Thu Sep 24 00:00 Central')
    ap.add_argument('--step', type=float, default=1.0, help='hours between departures')
    ap.add_argument('--out', default='../out/joints')
    ap.add_argument('--only', default='', help='comma list of hub names to restrict to (testing)')
    a = ap.parse_args()
    R = cached_router(date(2026, 9, 24), 20)
    xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float)
    km = lambda lon, lat: np.hypot((xy[:, 0] - lon) * 111.3 * math.cos(math.radians(lat)), (xy[:, 1] - lat) * 111.3)
    hubs = [h for h in HUBS if not a.only or h[0] in a.only.split(',')]
    origin = {n: np.nonzero(km(lon, lat) <= 0.3)[0].astype(np.int64) for n, lon, lat in hubs}
    target = {n: f'@~{lon},{lat},1.0' for n, lon, lat in hubs}
    for n, _, _ in hubs:
        if len(origin[n]) == 0: raise SystemExit(f'hub {n} has no stop within 0.3 km of its point')
        print(f'{n:18s} {len(origin[n])} origin stops: {sorted({R.stop_name[i] for i in origin[n]})[:3]}', flush=True)

    def arrive(src, dst, t):
        s = origin[src]
        st, tm, _ = R._scan_fast(s, np.full(len(s), float(t)), np.full(len(s), -1, dtype=np.int32), target[dst])
        return float(tm.min()) if len(tm) else float('inf')

    ct = ZoneInfo('America/Chicago')
    if 'Billings' in origin and 'Spokane' in origin:
        t = datetime(2026, 9, 27, 0, 25, tzinfo=ZoneInfo('America/Denver')).timestamp()
        want = datetime(2026, 9, 27, 10, 30, tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
        gate('Billings Sun 00:25 -> Spokane, minutes after the known Sun 10:30', lambda: (arrive('Billings', 'Spokane', t) - want) / 60, 0, 0.5)
    if 'Houston' in origin and 'Tallahassee' in origin:
        t = datetime(2026, 9, 30, 18, 0, tzinfo=ct).timestamp()
        want = datetime(2026, 10, 1, 11, 0, tzinfo=ZoneInfo('America/New_York')).timestamp()
        gate('Houston Wed 18:00 -> Tallahassee, minutes after the known Thu 11:00', lambda: max(0.0, (arrive('Houston', 'Tallahassee', t) - want) / 60), 0, 0.5)

    t0 = datetime(2026, 9, 24, 0, 0, tzinfo=ct).timestamp(); n = int(a.hours / a.step)
    deps = [t0 + k * a.step * 3600 for k in range(n)]
    arr = {}; names = [h[0] for h in hubs]; T = time.time()
    for i, A in enumerate(names):
        for B in names:
            if A != B: arr[(A, B)] = [arrive(A, B, t) for t in deps]
        pickle.dump(dict(hubs=hubs, t0=t0, step=a.step * 3600, arr=arr), open(a.out + '.pkl', 'wb'))
        print(f'{A} done ({i + 1}/{len(names)}, {time.time() - T:.0f} s)', flush=True)

    with open(a.out + '.txt', 'w') as fh:
        fh.write('door-to-door hours from each hub departure hour (Thu Sep 24 00:00 CT + k h): best / median / worst\n')
        for (A, B), v in sorted(arr.items()):
            d = [(x - t) / 3600 for x, t in zip(v, deps) if x < float('inf')]
            if not d: fh.write(f'{A:18s} -> {B:18s}  unreachable\n'); continue
            k = int(np.argmin(d)); bt = datetime.fromtimestamp(deps[k], ct)
            fh.write(f'{A:18s} -> {B:18s}  best {min(d):6.1f} (leave {bt:%a %H:%M} CT)  median {np.median(d):6.1f}  worst {max(d):6.1f}\n')
    print('wrote', a.out + '.pkl/.txt', flush=True)


if __name__ == '__main__':
    main()
