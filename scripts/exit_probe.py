"""Which ways out of a node keep the chain alive? Leaf script: nothing imports it.

Nick's rule for Salt Lake City: arriving from Idaho the only exits worth taking are Cheyenne, Denver or
Las Vegas; arriving from Wyoming or Colorado they are Pasco (via Pocatello or Boise) or Las Vegas (via
Saint George); West Wendover never makes sense given where the borders are. That is a claim about joint
feasibility, which the pair tables answer exactly, so test it rather than build it in.

For each exit city: the router's earliest route there from the node's stop and clock, every state that route
passes through credited, then the pair test at the arrival stop against what is still owed. Exits are city
areas (10 km around the centre) because names are not usable: "Las Vegas" matches 135 street stops.

Caveat, stated rather than hidden: the route tested is the EARLIEST arrival. A later arrival that collects a
different set could survive where the earliest dies, so "dead" here means dead on the fastest way there,
not dead on every way there.

    python3 exit_probe.py --route ../out/pp_slack_1h.pkl --leg-stop "Salt Lake City"
"""
import argparse, pickle
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR
from pair_tables import PairTables, check_path, leg_states

EXITS = {   # name: (lat, lon)
    'Pocatello': (42.8713, -112.4455), 'Boise': (43.6150, -116.2023), 'Pasco': (46.2396, -119.1006),
    'Saint George': (37.0965, -113.5684), 'Las Vegas': (36.1699, -115.1398),
    'West Wendover': (40.7391, -114.0733), 'Cheyenne': (41.1400, -104.8202), 'Denver': (39.7392, -104.9903),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True, help='ride_search --out pickle')
    ap.add_argument('--leg-stop', default='Salt Lake City', help='test the node after the LAST leg ending at a '
                    'stop whose name contains this')
    ap.add_argument('--at', default='2026-09-24T00:54'); ap.add_argument('--by', default='2026-10-03T22:54')
    ap.add_argument('--tz', default='America/New_York'); ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--km', type=float, default=10)
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    T0 = datetime.fromisoformat(a.at).replace(tzinfo=tz).timestamp()
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days, verbose=False)
    ab = lambda x: ABBR[R.state_names[x]]
    PT = PairTables(R, D, a.span, verbose=False)      # cache only: refuses to be the thing that builds it here
    d = pickle.load(open(a.route, 'rb'))
    bad = check_path(R, d['path'], d.get('start'))
    if bad: raise SystemExit(f'REFUSED {a.route}: {bad[0]}')
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)

    path = d['path']
    have, seen, node = set(), [], None
    st0 = path[0][1]
    if R.state[st0] >= 0: have.add(int(R.state[st0]))
    for i, leg in enumerate(path, 1):
        have |= leg_states(R, leg, trip_conns)
        seen.append((i, leg[2], leg[4], frozenset(have)))
    for i, stop, t, col in seen:
        if a.leg_stop.lower() in R.stop_name[stop].lower(): node = (i, stop, t, col)
    if node is None: raise SystemExit(f'no leg ends at a stop matching {a.leg_stop!r}')
    i, stop, t, col = node
    came = [ab(y) for y in sorted(seen[i - 2][3] ^ seen[i - 3][3])] if i >= 3 else []
    owed0 = [y for y in range(N_STATES) if y not in col]
    m0, y0, z0 = PT.worst(stop, t, owed0)
    print(f'node after ride {i}: {R.stop_name[stop]} at {R.fmt_time(t, stop)}, {(t - T0) / 3600:.1f} h spent, '
          f'{len(col)} held; the ride before it added {" ".join(came) or "nothing new"}')
    print(f'  owes {len(owed0)}: {" ".join(ab(y) for y in owed0)}')
    print(f'  standing here: tightest pair {ab(y0)} & {ab(z0)} {m0 / 3600:+.1f} h\n')

    print(f'{"exit":14s} {"arrive":>18s} {"hours":>6s}  {"gains":24s} {"tightest pair after":24s} verdict')
    for name, (lat, lon) in EXITS.items():
        tgt = f'@~{lon},{lat},{a.km}'
        try:
            t_end, legs = R._route_fast(np.array([stop]), float(t), [tgt])
        except Exception as e:
            print(f'{name:14s} route failed: {type(e).__name__}: {e}'); continue
        if t_end is None or not np.isfinite(t_end):
            print(f'{name:14s} {"unreachable":>18s}'); continue
        got = set(); last = stop
        for l in legs:
            if l[0] == 'ride':
                _, trip, bs, bt, al, at = l
                got |= leg_states(R, (trip, bs, al, bt, at), trip_conns); last = al
                if R.state[bs] >= 0: got.add(int(R.state[bs]))
            elif l[0] == 'walk':
                _, frm, to, t0w, t1w = l[:5]
                if R.state[to] >= 0: got.add(int(R.state[to]))
                last = frm if to >= R.first_virtual else to
        new = sorted(got - col)
        owed = [y for y in owed0 if y not in got]
        m, y, z = PT.worst(last, float(t_end), owed)
        verdict = 'DEAD' if m < 0 else 'alive'
        pair = f'{ab(y)} & {ab(z)} {m / 3600:+.1f} h' if y >= 0 else '-'
        print(f'{name:14s} {R.fmt_time(float(t_end), last):>18s} {(t_end - t) / 3600:6.1f}  '
              f'{" ".join(ab(x) for x in new)[:24]:24s} {pair:24s} {verdict}', flush=True)


if __name__ == '__main__':
    main()
