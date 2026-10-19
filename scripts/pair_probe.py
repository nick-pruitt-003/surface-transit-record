"""Can a stalled chain still collect its owed states two at a time? Exact, from the deadline tables.

Leaf script: nothing imports it.

ride_search keeps a node alive while every owed state is individually collectable: for each owed y,
L[y][stop] >= t. That is a per-state test, and the census on the deepest bucket showed it passes by
construction. It cannot see a node that can reach Florida in time and Washington in time but not both.

Pairs can be answered exactly with the machinery the search already trusts. L[y] is one reverse scan seeded
from y's stops with L_end. Seed the same scan from y's stops with L[z] instead:

    L[y->z][s] = latest you can be at s and still collect y, then z, then finish

because to collect y then z then finish you must be at some y-stop no later than L[z] there. Nothing is
estimated. A node at (stop, t) is dead if for some owed pair both L[y->z][stop] and L[z->y][stop] are before
t, and the pair that kills it is named.

Falsification: the 237 control finishes at 22:14 on d9, inside the 22:54 deadline, so every node along it
must show zero dead pairs. If a control node fails, this probe is wrong, not the control.

    python3 pair_probe.py --route ../out/long_slack_1h.pkl --control ../out/hun_ms_meteor.pkl
"""
import argparse, pickle, time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
import backward as B
from common import ABBR
from pair_tables import resolve_stop, check_path, leg_states


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-05T00:54', help='the search start, for elapsed hours')
    ap.add_argument('--by', default='2026-11-14T22:54', help='deadline: start + target, as the search uses')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--span', type=float, default=260, help='hours the tables scan back over, as ride_search')
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--route', action='append', default=[],
                    help='ride_search --out pickle (deepest chain or a found route); tests its last node')
    ap.add_argument('--prefixes', type=int, default=None, metavar='K',
                    help='with --route, also test every node along the chain holding at least K states')
    ap.add_argument('--control', help='a time_search route pickle with legs (hun_ms_meteor.pkl); '
                    'tests its nodes as the falsification check')
    ap.add_argument('--control-start', default='Huntington Bus Stop')
    ap.add_argument('--control-at', default='2026-11-05T00:30', help='the control\'s own clock, as regress')
    ap.add_argument('--control-min', type=int, default=28,
                    help='control nodes holding at least this many states are tested')
    ap.add_argument('--nodes', help='pickle of [dict(stop=int|name, t=epoch, collected=[state ids], '
                    'label=str)], e.g. a census bucket')
    ap.add_argument('--show', type=int, default=5, help='tightest pairs listed per node')
    a = ap.parse_args()

    tz = ZoneInfo(a.tz)
    T0 = datetime.fromisoformat(a.at).replace(tzinfo=tz).timestamp()
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    ab = lambda x: ABBR[R.state_names[x]]
    inv = {v: k for k, v in ABBR.items()}
    END_ST = R.state_names.index(inv[a.end])
    st_stops = defaultdict(list)
    for s in range(R.N):
        if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)

    # the same tables ride_search builds, the same way
    F = B.RevFast(R)
    def latest_from(nxt):
        lat, ok, k0, k1 = F.layer(nxt, False, D - a.span * 3600, None)
        eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
        return np.maximum(lat, eff)
    t_ = time.time()
    L_end = latest_from({s: D for s in st_stops[END_ST]})
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        nxt = {s: float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
        if nxt: L[y] = latest_from(nxt)
    print(f'single tables in {time.time() - t_:.0f} s', flush=True)

    pair = {}
    def L2(y, z):
        """latest at each stop to collect y, then z, then finish"""
        if (y, z) not in pair:
            nxt = {s: float(L[z][s]) for s in st_stops[y] if L[z][s] > -np.inf}
            pair[(y, z)] = latest_from(nxt) if nxt else np.full(R.N, -np.inf)
        return pair[(y, z)]

    # a ride collects every state its vehicle passes between boarding and alighting, as ride_search credits it
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)
    def passed(trip, bt, at):
        return {int(R.state[R.cto[k]]) for k in trip_conns.get(trip, ())
                if bt <= R.dep[k] and R.arr[k] <= at and R.state[R.cto[k]] >= 0}
    def walkin_states(stop):
        return {int(R.state[j]) for j, _w in R.foot.get(stop, ()) if j >= R.first_virtual and R.state[j] >= 0}

    nodes = []    # (label, stop, t, frozenset collected)
    for path_ in a.route:
        d = pickle.load(open(path_, 'rb'))
        path = d['path']
        bad = check_path(R, path, d.get('start'))
        if bad:
            print(f'REFUSED {path_}: its stop indices do not fit this router ({len(bad)} problems)')
            for b in bad[:5]: print('   ', b)
            continue
        final = frozenset(d['collected']) if 'collected' in d else None
        st0 = path[0][1]
        have = {int(R.state[st0])} if R.state[st0] >= 0 else set()
        for i, leg in enumerate(path, 1):
            trip, frm, to, bt, at = leg[:5]
            # from 2f4d0de a walk-in names the state it took, and may also carry the ride that brought it
            walk = leg[5] if len(leg) > 5 else None
            if len(leg) > 5 and (walk is not None and walk >= 0 or len(leg) > 6):
                have |= leg_states(R, leg, trip_conns)    # new layouts say exactly what the leg covered
            elif trip is None:
                # the pickle does not say which state a walk-in took before 2f4d0de; the one it took is the
                # one the final set holds and nothing else explains, so read it off that
                extra = walkin_states(to) - have
                if final is not None: extra &= final
                have |= extra
            else:
                have |= passed(trip, bt, at)
                if R.state[to] >= 0: have.add(int(R.state[to]))
            last = i == len(path)
            if last or (a.prefixes is not None and len(have) >= a.prefixes):
                c = final if (last and final is not None) else frozenset(have)
                nodes.append((f'{path_.split("/")[-1]} ride {i}', to, float(at), c))
        if final is not None and frozenset(have) != final:
            print(f'note: reconstructed set for {path_} differs from the saved one by '
                  f'{" ".join(ab(y) for y in frozenset(have) ^ final)}; the last node uses the saved one')
    if a.control:
        d = pickle.load(open(a.control, 'rb'))
        # Re-evaluate the stored state order, as regress does. The stored legs carry stop indices from the
        # router that wrote them, and a different build puts them on different stops: the first version of
        # this read Houston as the final leg and Hanover as Detroit, and every control node looked dead.
        import time_search as ts_
        from time_search import Search
        tc = datetime.fromisoformat(a.control_at).replace(tzinfo=tz).timestamp()
        tried = []
        for hun_ in resolve_stop(R, a.control_start):   # every exact match, not the first; keep the fastest
            S = Search(R, hun_, tc, [], 1)
            ts_.bind(R, hun_, tc, S)
            fin_, legs_ = S.evaluate(d['order'])
            tried.append((fin_, hun_, legs_))
        fin, hun, legs = min(tried, key=lambda x: x[0])
        print(f'control start {a.control_start!r}: stops ' + ', '.join(f'{h} finishes {(f - tc) / 3600:.2f} h'
              for f, h, _ in tried) + f'; using {hun}', flush=True)
        print(f'control re-evaluated: finishes {(fin - tc) / 3600:.2f} h after its own start', flush=True)
        have = {int(R.state[hun])} if R.state[hun] >= 0 else set()
        for i, l in enumerate(legs, 1):
            if l[0] == 'ride':
                _, trip, bs, bt, al, at = l
                if R.state[bs] >= 0: have.add(int(R.state[bs]))
                have |= passed(trip, bt, at)
                if R.state[al] >= 0: have.add(int(R.state[al]))
                stop, t = al, at
            elif l[0] == 'walk':
                _, frm, to, t0w, t1w = l[:5]
                if R.state[to] >= 0: have.add(int(R.state[to]))
                stop, t = (frm if to >= R.first_virtual else to), t1w
            else:
                continue
            if len(have) >= a.control_min and len(have) < N_STATES:
                nodes.append((f'control leg {i}', int(stop), float(t), frozenset(have)))
        # if trip keys did not match this router, rides would credit nothing and the control would look
        # like it owes states it holds, which is exactly a false kill; say so rather than test on it
        print(f'control reconstructs {len(have)}/{N_STATES} states over {len(legs)} legs'
              + ('' if len(have) >= N_STATES - 1 else ' -- INCOMPLETE, control nodes are not a fair test'),
              flush=True)
    if a.nodes:
        for n in pickle.load(open(a.nodes, 'rb')):
            # An int is router-local and a name can be ambiguous, so neither is taken on trust: an int needs
            # the name it had when written, and a name must match exactly one stop.
            if isinstance(n['stop'], int):
                s = n['stop']
                if n.get('stop_name') != (R.stop_name[s] if 0 <= s < R.N else None):
                    raise SystemExit(f'--nodes: stop {s} is {R.stop_name[s] if 0 <= s < R.N else "out of range"!r} '
                                     f'here but {n.get("stop_name")!r} in the file; pass stop_name, or a name')
            else:
                ex = resolve_stop(R, n['stop'])
                if len(ex) > 1:
                    raise SystemExit(f'--nodes: {n["stop"]!r} is {len(ex)} stops here ({ex}); pass the index '
                                     f'with stop_name')
                s = ex[0]
            nodes.append((n.get('label', 'node'), s, float(n['t']), frozenset(n['collected'])))
    if not nodes:
        print('no nodes to test: pass --route, --control or --nodes'); return

    dead_total = 0
    for label, stop, t, col in nodes:
        owed = [y for y in range(N_STATES) if y not in col]
        t_ = time.time()
        print(f'\n{label}: {R.stop_name[stop][:32]} at {R.fmt_time(t, stop)}, {(t - T0) / 3600:.1f} h spent, '
              f'{(D - t) / 3600:.1f} h left, {len(col)} held, owes {len(owed)}: '
              f'{" ".join(ab(y) for y in owed)}', flush=True)
        m_end = (L_end[stop] - t) / 3600
        singles = sorted(((L[y][stop] - t) / 3600, y) for y in owed)
        print(f'  finish margin {m_end:+.1f} h; tightest single {ab(singles[0][1])} {singles[0][0]:+.1f} h'
              if singles else f'  finish margin {m_end:+.1f} h')
        if m_end < 0 or (singles and singles[0][0] < 0):
            print('  DEAD on a single state already (the search should never have kept this node)')
            dead_total += 1; continue
        if len(owed) < 2:
            print('  one state owed, no pairs to test'); continue
        res = []
        for i, y in enumerate(owed):
            for z in owed[i + 1:]:
                yz = (L2(y, z)[stop] - t) / 3600; zy = (L2(z, y)[stop] - t) / 3600
                res.append((max(yz, zy), y, z, yz, zy))
        res.sort()
        dead = [r for r in res if r[0] < 0]
        m = np.array([r[0] for r in res])
        print(f'  {len(res)} pairs, {len(dead)} jointly impossible; pair margin min {m.min():+.1f} h, '
              f'5th pct {np.percentile(m, 5):+.1f} h, median {np.median(m):+.1f} h   [{time.time() - t_:.0f} s, '
              f'{len(pair)} pair tables so far]', flush=True)
        for bm, y, z, yz, zy in (dead if dead else res[:a.show])[:max(a.show, len(dead) if dead else 0)]:
            print(f'    {ab(y)} & {ab(z)}: {ab(y)} then {ab(z)} {yz:+.1f} h, {ab(z)} then {ab(y)} {zy:+.1f} h'
                  + ('   <- neither order fits' if bm < 0 else ''))
        if dead:
            dead_total += 1
            bm, y, z, yz, zy = dead[0]
            print(f'  DEAD: {ab(y)} and {ab(z)} cannot both be collected from here, in either order, and still '
                  f'finish by the deadline (best order misses by {-bm:.1f} h)')
        else:
            print(f'  every pair fits; the tightest clears by {m.min():.1f} h. Pairs cannot kill it; '
                  f'a rollout is the next test, not triples')
    print(f'\n{dead_total} of {len(nodes)} nodes dead on a single state or a pair')


if __name__ == '__main__':
    main()
