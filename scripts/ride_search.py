"""Search the rides themselves: stand at a stop at a time, look at what leaves, take one, backtrack when it cannot win.

  forward:   python3 ride_search.py --start "Huntington Bus Stop" --at 2026-09-24T00:54 --tz America/New_York
  backward:  python3 ride_search.py --end VT --by 2026-10-03T22:14 --tz America/New_York --dir backward

This is a different space from build_backward and dfs_backward, which both search orderings of the 48 states
and pick stops afterwards. That abstraction is where their trouble came from: branching is the topk of 6, the
leftover estimate has to price a set of states with no idea where or when you are, and every version of that
estimate failed (HANDOFF sections 9 and 11).

Here a node is a place and a time and what has been collected, and the menu is what actually departs. Measured
along the reference route (`branching.py`), that menu has a median of 2 useful services and is empty at ten of
its thirty-nine points, where the next move is forced. Nothing is aggregated and there is no leftover estimate
at all: a branch dies when the time it has spent already passes the limit, which needs no heuristic to be
correct, plus dominance, which is exact.

  --states N   only require the first N states the search happens to collect, for validating on a small case
"""
import argparse, bisect, pickle, sys, time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, MIN_TRANSFER, N_STATES, WALK_MAX_KM
import backward as B
from common import ABBR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start'); ap.add_argument('--at')
    ap.add_argument('--end'); ap.add_argument('--by')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--dir', default='forward', choices=('forward', 'backward'))
    ap.add_argument('--target', type=float, default=238.0, help='hours the route must come in under')
    ap.add_argument('--states', type=int, default=N_STATES, help='how many states to require (fewer = a test case)')
    ap.add_argument('--horizon', type=float, default=24, help='hours ahead to look for a departure')
    ap.add_argument('--hub', type=int, default=6, help='fallback alight rule when no deadline is given: the stop '
                    'has at least this many services. With --end/--by the deadline tables decide instead.')
    ap.add_argument('--order', default='rate', choices=('rate', 'states', 'early'),
                    help="which ride to try first: 'rate' hours per new state, 'states' most new states, "
                         "'early' earliest arrival")
    ap.add_argument('--width', type=int, default=12, help='rides tried per node')
    ap.add_argument('--span', type=float, default=260, help='hours the deadline tables scan back over')
    ap.add_argument('--budget', type=float, default=900); ap.add_argument('--nodes', type=int, default=2000000)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out')
    a = ap.parse_args()
    back = a.dir == 'backward'
    when = datetime.fromisoformat(a.by if back else a.at).replace(tzinfo=ZoneInfo(a.tz))
    T0 = when.timestamp()
    R = TimeRouter(load_feeds(), (when.date() if not back else (when - __import__('datetime').timedelta(days=12)).date()), a.days)
    ab = lambda x: ABBR[R.state_names[x]] if x >= 0 else '--'
    print(f'{a.dir} from {when:%a %Y-%m-%d %H:%M}, limit {a.target} h, {a.states} states required', flush=True)

    # connections grouped by trip, in order, so boarding a trip and riding on is one move
    t_build = time.time()
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)
    for v in trip_conns.values(): v.sort(key=lambda k: R.dep[k])
    board_at = defaultdict(list)          # stop -> connections departing it, by time
    for k in range(len(R.dep)): board_at[int(R.cfrom[k])].append(k)
    for v in board_at.values(): v.sort(key=lambda k: R.dep[k])
    dep_times = {s: [R.dep[k] for k in v] for s, v in board_at.items()}
    nserv = {s: len({R.trip_info.get(R.ctrip[k], ('', ''))[1] for k in v}) for s, v in board_at.items()}
    print(f'  indexed {len(R.dep)} connections over {len(trip_conns)} trips in {time.time() - t_build:.0f} s', flush=True)

    START = R.stops_matching(a.start)[0] if a.start else None
    inv = {v: k for k, v in ABBR.items()}

    # Both clocks on the same node. Going forward the search knows how long it has been out; these tables give
    # it the other half, how long it has left. One reverse scan from the end at its deadline gives the latest
    # you could be at each stop and still finish; seeding a second scan from a state's stops with those values
    # gives the latest you could be at each stop and still collect THAT state and then finish. So at any node,
    # if the clock is past L[y] for a state y still owed, that branch is already dead. That is a fact rather
    # than an estimate, and after the precompute it costs one array lookup.
    L = None; L_end = None; END_ST = None
    if a.end and a.by:
        END_ST = R.state_names.index(inv[a.end])
        D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
        F = B.RevFast(R)
        st_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
        t_pre = time.time()

        def latest_from(nxt):
            lat, ok, k0, k1 = F.layer(nxt, True, D - a.span * 3600, None)
            eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
            return np.maximum(lat, eff)

        L_end = latest_from({int(s): D for s in st_stops[END_ST]})
        L = np.full((N_STATES, R.N), -np.inf)
        for y in range(N_STATES):
            nxt = {int(s): float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
            if nxt: L[y] = latest_from(nxt)
        ls = L_end[START] if START is not None else -np.inf
        print('  deadline tables built in %.0f s; latest start that still finishes: %s'
              % (time.time() - t_pre, R.fmt_time(float(ls), START) if ls > -np.inf else 'unreachable'), flush=True)

    def alight_ok(to, at, owed_after):
        """Is getting off here survivable? Every state still owed has to remain collectible from this stop at
        this time, and the end has to remain reachable. Exact, straight from the deadline tables.

        This replaces counting services at the stop, which was a guess and a wrong one. The Barstow Amtrak
        depot has two services, and California is already collected by the time the route reaches it, so no
        rule built on busyness or on new states would ever stop there, and the Southwest Chief leaves from
        nowhere else. Conway has five and survives only because Arkansas happens to be new there. Nick named
        both as the tests, and the old rule failed both."""
        if L is None: return nserv.get(to, 0) >= a.hub
        if at > L_end[to]: return False
        col = L[:, to]
        for y in owed_after:
            if at > col[y]: return False
        return True

    def rides_from(s, t, aboard, collected):
        """The menu at stop s at time t: (alight stop, alight time, trip, states it collects).
        Riding on the trip already boarded needs no transfer; anything else does."""
        out = []
        all_states = range(N_STATES)
        for j, w in [(s, 0)] + [(j, w) for j, w in R.foot.get(s, ()) if w <= WALK_MAX_KM * 1000 / 1.25]:
            t_ok = t + w + (0 if j == s else 0)
            times = dep_times.get(j)
            if not times: continue
            i = bisect.bisect_left(times, t_ok)
            seen = set()
            while i < len(times) and times[i] <= t_ok + a.horizon * 3600:
                k = board_at[j][i]; i += 1
                key = R.ctrip[k]
                if key in seen: continue
                if key != aboard and R.dep[k] < t_ok + MIN_TRANSFER: continue
                seen.add(key)
                cs = trip_conns[key]
                p = next((n for n, kk in enumerate(cs) if kk == k), None)
                if p is None: continue
                got = set()
                for kk in cs[p:]:
                    to = int(R.cto[kk]); st = int(R.state[to])
                    if st >= 0: got.add(st)
                    at = float(R.arr[kk])
                    owed = [y for y in all_states if y not in collected and y not in got]
                    if alight_ok(to, at, owed):
                        out.append((to, at, key, frozenset(got)))
        return out

    best = [None]; limit = [a.target * 3600]; seen_nodes = [0]; t_run = time.time(); deepest = [0]
    dom = {}                                   # (stop, collected) -> best time seen, exact pruning
    NEED = a.states

    def dfs(stop, t, collected, aboard, path):
        if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: return
        seen_nodes[0] += 1
        spent = (t - T0) if not back else (T0 - t)
        if spent > limit[0]: return
        if len(collected) >= NEED:
            limit[0] = spent; best[0] = (spent, list(path))
            print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h, {len(collected)} states, '
                  f'{len(path)} rides', flush=True)
            return
        if len(collected) > deepest[0]:
            deepest[0] = len(collected)
            print(f'  [{time.time() - t_run:5.0f}s] {len(collected)}/{NEED} states, {spent / 3600:6.1f} h spent, '
                  f'at {R.stop_name[stop][:28]}, {len(path)} rides, {seen_nodes[0]} nodes', flush=True)
        if L is not None:
            if t > L_end[stop]: return                        # the end is no longer reachable from here
            col = L[:, stop]
            for y in range(N_STATES):
                if y not in collected and t > col[y]: return  # y can no longer be collected before finishing
        key = (stop, collected)
        prev = dom.get(key)
        if prev is not None and prev <= spent: return
        dom[key] = spent
        opts = rides_from(stop, t, aboard, collected)
        # Order by hours per new state, not by how many states a ride collects. Sorting by states collected
        # sends the search onto the longest transcontinental trains first: from Huntington it took Detroit,
        # then New York, then Slidell, reaching 21 states in 6 rides having already spent 137 of its 238 h,
        # which cannot finish. What the route needs is states cheaply, so price each ride by what it costs
        # per state it adds, and let a positioning ride that adds none be judged on how little time it burns.
        # A ride that collects nothing is still sometimes necessary (Spokane to Pasco collects nothing, and
        # without it there is no way south), but it must never be tried first: scored on its own duration a
        # five minute local hop beats every real ride, and the search dithers. So state-collecting rides are
        # ordered ahead of positioning ones in every mode, and the modes differ only in how they rank within
        # those two groups.
        n_new = lambda o: len(o[3] - collected)
        if a.order == 'rate':
            opts.sort(key=lambda o: (n_new(o) == 0, (o[1] - t) / max(1, n_new(o))))
        elif a.order == 'states':
            opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), o[1]))
        else:
            opts.sort(key=lambda o: (n_new(o) == 0, o[1]))
        for to, at, trip, got in opts[:a.width]:
            new = collected | got
            path.append((trip, stop, to, t, at))
            dfs(to, at, new, trip, path)
            path.pop()

    sys.setrecursionlimit(20000)
    if back:
        print('backward mode needs the reverse connection index; not built yet, running forward from --start')
    if START is None: print('need --start'); return
    dfs(START, T0, frozenset({int(R.state[START])}) if R.state[START] >= 0 else frozenset(), None, [])
    el = time.time() - t_run
    print(f'\n{seen_nodes[0]} nodes in {el:.0f} s ({seen_nodes[0] / max(el, 1):.0f}/s), {len(dom)} distinct '
          f'(stop, states); deepest {deepest[0]}/{NEED} states')
    if best[0] is None:
        print(f'nothing reached {NEED} states under {a.target} h in the budget')
    else:
        spent, path = best[0]
        print(f'best {spent / 3600:.2f} h over {len(path)} rides')
        for trip, s, to, t, at in path[:60]:
            info = R.trip_info.get(trip, ('', ''))
            print(f'   {R.fmt_time(t, s)} {R.stop_name[s][:26]:26s} -> {R.fmt_time(at, to)} {R.stop_name[to][:26]:26s} '
                  f'{(info[1] or info[0])[:24]}')
        if a.out: pickle.dump(dict(path=path, spent=spent), open(a.out, 'wb')); print('wrote', a.out)


if __name__ == '__main__':
    main()
