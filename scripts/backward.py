"""Work a route backwards from its finish: latest arrival at each state that still makes the deadline, and slack.

Keeps the route's order of targets. Forward pass (earliest arrival at every stop of each target, same layers as
the search) and a reverse Connection Scan from the deadline give, per target, the earliest you can be there and
the latest you can be there and still finish in time. Slack 0 = a binding link (a faster or more frequent service
there moves the finish); big slack = waiting the route absorbs later on. The top line is the latest start.

  python3 backward.py --route ../out/res_starttest.pkl [--end-by 2026-10-03T22:14 --tz America/New_York]
      [--end "Beaver Dam"]    # append a finish stop to the order
"""
import argparse, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, MIN_TRANSFER, N_STATES
from common import ABBR


def forward(R, start, t0, order):
    """Earliest-arrival labels for every target layer: list of {stop: time}."""
    stops = np.array([start]); times = np.array([float(t0)]); trips = np.array([-1], dtype=np.int32); out = []
    for t in order:
        stops, times, trips = R._scan_fast(stops, times, trips, t)
        if len(stops) == 0: return out, t
        out.append(dict(zip(stops.tolist(), times.tolist())))
    return out, None


def backward_layer(R, rev, nxt, tgt_next_state, lo, nxt_stay=None, want=()):
    """Latest time at each stop from which some stop of the next layer is reached by its latest time.
    nxt: {stop: latest}; nxt_stay: {stop: {trip: departure}} = staying on a through vehicle there needs no
    transfer. Mirrors the forward rules: one walk hop around rides, MIN_TRANSFER to change vehicles, and a
    cross-state walk can't land on a state target's stop. Returns (latest list, stay for the stops in want)."""
    nxt_stay = nxt_stay or {}; want = None if want is None else set(want); stay = {}   # want None: every stop
    NEG = float('-inf'); latest = [NEG] * R.N; board = [NEG] * R.N
    for s, L in nxt.items():
        latest[s] = max(latest[s], L)
        for j, w in rev[s]:
            if tgt_next_state and R._crosses(j, s): continue
            latest[j] = max(latest[j], L - w)
    hi = max(nxt.values())
    dep, arr, cfrom, cto, ctrip = R._fa['dep'], R._fa['arr'], R._fa['cfrom'], R._fa['cto'], R._fa['ctrip']
    k1 = int(np.searchsorted(dep, hi, side='right')) - 1; k0 = int(np.searchsorted(dep, lo))
    if k1 < k0: return latest, stay
    D_, A_, F_, T_, C_ = (x[k0:k1 + 1].tolist() for x in (dep, arr, cfrom, cto, ctrip))
    ok = set()
    for k in range(len(D_) - 1, -1, -1):
        tr = C_[k]
        if tr not in ok:
            b = T_[k]
            if A_[k] <= latest[b] or A_[k] <= nxt_stay.get(b, {}).get(tr, NEG): ok.add(tr)
            else: continue
        a = F_[k]
        if want is None or a in want: stay.setdefault(a, {}).setdefault(tr, D_[k])   # descending scan: first seen = latest boarding
        t = D_[k] - MIN_TRANSFER
        # board[a]: latest to board at a itself. Walks chain only onto a boarding (one hop, like the forward
        # scan), never onto another walk, so they relax from board[a], not from latest[a].
        if t > board[a]:
            board[a] = t
            if t > latest[a]: latest[a] = t
            for j, w in rev[a]:
                if t - w > latest[j]: latest[j] = t - w
    return latest, stay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True, help='result pickle (order, start, t0)')
    ap.add_argument('--end-by', help='deadline, ISO in --tz (default: the route\'s own finish)')
    ap.add_argument('--tz', default='America/New_York'); ap.add_argument('--days', type=int, default=18)
    ap.add_argument('--end', help='append this finish stop to the order')
    a = ap.parse_args()
    d = pickle.load(open(a.route, 'rb'))
    order = list(d['order']) + ([f'@{a.end}'] if a.end else [])
    t0 = float(d['t0'])
    R = TimeRouter(load_feeds(), datetime.fromtimestamp(t0, ZoneInfo(a.tz)).date(), a.days)
    start = R.stop_name.index(d['start']) if isinstance(d['start'], str) else int(d['start'])
    fw, bad = forward(R, start, t0, order)
    if bad is not None: print('route cannot reach', bad); return
    finish = min(fw[-1].values())
    D = datetime.fromisoformat(a.end_by).replace(tzinfo=ZoneInfo(a.tz)).timestamp() if a.end_by else finish
    print(f'forward finish {R.fmt_time(finish, min(fw[-1], key=fw[-1].get))}; deadline {"= finish" if not a.end_by else a.end_by}'
          + (f' ({(D - finish) / 3600:+.1f} h vs forward finish)' if a.end_by else ''))
    rev = [[] for _ in range(R.N)]
    for i in range(R.N):
        for j, w in R.foot.get(i, ()): rev[j].append((i, w))
    lat = [None] * len(order); stays = [None] * len(order)
    lat[-1] = {s: D for s in fw[-1]}; stays[-1] = {}
    for k in range(len(order) - 2, -2, -1):
        lo = t0 if k < 0 else min(fw[k].values())
        want = [start] if k < 0 else fw[k]
        latest, stay = backward_layer(R, rev, lat[k + 1], not isinstance(order[k + 1], str), lo, stays[k + 1], want)
        if k < 0: lat_start = max([latest[start]] + [t - MIN_TRANSFER for t in stay.get(start, {}).values()]); break
        # latest arrival that still works: change vehicles there, or stay on a through vehicle
        lat[k] = {s: max([latest[s]] + list(stay.get(s, {}).values())) for s in fw[k]}
        lat[k] = {s: v for s, v in lat[k].items() if v > float('-inf')}; stays[k] = stay
        if not lat[k]: print(f'no stop of target {k} ({order[k]}) makes the deadline'); return
    name = lambda x: ABBR.get(R.state_names[x], R.state_names[x]) if not isinstance(x, str) else ('gateway' if x.startswith('@~') else x[1:])
    first_ok = lat_start > float('-inf')
    print(f'latest start from {R.stop_name[start]}: ' + (R.fmt_time(lat_start, start) if first_ok else 'none (deadline too early)'))
    print(f'\n  {"target":10s} {"stop":34s} {"earliest":>13s} {"latest":>13s} {"slack":>7s}')
    for k, x in enumerate(order):
        both = [(lat[k][s] - fw[k][s], s) for s in fw[k] if lat[k] and s in lat[k] and lat[k][s] >= fw[k][s] - 60]
        if not both:
            print(f'  {name(x)[:10]:10s} {"(no stop makes the deadline)":34s}'); continue
        sl, s = max(both)
        flag = '  <- binding' if sl < 1800 else ''
        print(f'  {name(x)[:10]:10s} {R.stop_name[s][:34]:34s} {R.fmt_time(fw[k][s], s):>13s} {R.fmt_time(lat[k][s], s):>13s} {sl / 3600:6.1f}h{flag}')


if __name__ == '__main__':
    main()
