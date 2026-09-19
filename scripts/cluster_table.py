"""Exhaustive cost table for crossing a cluster of states.

For every entry gateway, exit gateway and start hour in one week, try every order of the cluster
states and keep the fastest time from arriving at the entry to arriving at the exit.

usage: python3 cluster_table.py --states "North Dakota,South Dakota" \
         --gateways "Minneapolis,Omaha,Kansas City Bus,Denver,Billings,Spokane,Des Moines,Chicago Bus" \
         --week 2026-09-21 --step 2 --workers 4 --out ../out/cluster_dakotas.csv
"""
import argparse, csv, itertools, statistics
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds

_R = None; _ST = None; _GW = None; _T0 = None; _GW_STOP = None


def _job(job):
    e, h = job; t0 = _T0 + h * 3600; out = []
    for x in _GW:
        best = None
        for p in itertools.permutations(_ST):
            f = _R.finish(_GW_STOP[e], t0, list(p) + ['@' + x])
            if f is not None and (best is None or f < best[0]): best = (f, p)
        out.append((e, x, h, None if best is None else (best[0] - t0) / 3600, None if best is None else best[1]))
    return out


def main():
    global _R, _ST, _GW, _T0, _GW_STOP
    ap = argparse.ArgumentParser()
    ap.add_argument('--states', required=True); ap.add_argument('--gateways', required=True)
    ap.add_argument('--week', required=True); ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--workers', type=int, default=4); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    day = datetime.fromisoformat(a.week).replace(tzinfo=ZoneInfo('America/Chicago'))
    _R = TimeRouter(load_feeds(), day.date(), 14); _T0 = day.timestamp()
    _ST = [_R.state_names.index(s.strip()) for s in a.states.split(',')]
    _GW = [g.strip() for g in a.gateways.split(',')]
    _GW_STOP = {g: _R.stops_matching(g)[0] for g in _GW}
    jobs = [(e, h) for e in _GW for h in range(0, 168, a.step)]
    import multiprocessing as mp
    with mp.get_context('fork').Pool(a.workers) as pool: res = [r for chunk in pool.map(_job, jobs, chunksize=4) for r in chunk]
    with open(a.out, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['entry', 'exit', 'start (h after Mon 00:00 CT)', 'hours', 'order'])
        for e, x, h, hrs, p in res: w.writerow([e, x, h, '' if hrs is None else round(hrs, 2), '' if p is None else ' > '.join(_R.state_names[i] for i in p)])
    print(f"{'entry':18}{'exit':18}{'best':>7}{'median':>8}{'worst':>7}   best start")
    for e in _GW:
        for x in _GW:
            v = [(hrs, h) for ee, xx, h, hrs, p in res if ee == e and xx == x and hrs is not None]
            if not v: continue
            b = min(v); d = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[b[1] // 24]
            print(f'{e:18}{x:18}{b[0]:7.1f}{statistics.median(t for t, _ in v):8.1f}{max(v)[0]:7.1f}   {d} {b[1] % 24:02d}:00')


if __name__ == '__main__':
    main()
