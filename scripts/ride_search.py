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
    ap.add_argument('--mode', default='best', choices=('best', 'dfs'),
                    help="'best' expands the most promising node anywhere in the frontier; 'dfs' dives and "
                         "backtracks, which cannot recover from a bad first guess inside ten minutes")
    ap.add_argument('--queue', type=int, default=200000, help='frontier cap for --mode best')
    ap.add_argument('--credit', type=float, default=5.0, help='hours a collected state is worth when ordering '
                    'the frontier. Ranking by state count alone plateaus: every node at 23 states has to be '
                    'expanded before any at 22, and there are combinatorially many. The reference route '
                    'averages 237/48 = 4.94 h per state, so crediting about that much turns the priority into '
                    'hours per state, which is the thing being minimised.')
    ap.add_argument('--span', type=float, default=260, help='hours the deadline tables scan back over')
    ap.add_argument('--budget', type=float, default=900); ap.add_argument('--nodes', type=int, default=2000000)
    ap.add_argument('--track', help='reference route pickle: replay its rides through this search and report, '
                    'leg by leg, whether the menu offers them and where they rank. 237 is a control: the test '
                    'is that it reproduces, not that it is beaten.')
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

    # A state is collected by a ride OR by a border walk-in (Nick's rule 1 and 4). Counting only the states a
    # ride's stops sit in misses every state taken on foot, and the reference route takes Mississippi that way:
    # it rides to Holmes at Elvis Presley and walks 1.3 km to the line. Without this the search never collects
    # MS, MS stays owed for the rest of the route, and alight_ok then correctly refuses every stop east of
    # Texas because Mississippi can no longer be reached. time_router already built exactly these links, to the
    # virtual border points at and beyond first_virtual, so read them off rather than invent a rule.
    walkin = {}
    for i in range(R.N):
        near = {}
        for j, w in R.foot.get(i, ()):
            if j >= R.first_virtual and R.state[j] >= 0:
                y = int(R.state[j])
                if y not in near or w < near[y]: near[y] = float(w)
        if near: walkin[i] = tuple(sorted(near.items()))
    print(f'  {len(walkin)} stops can step over a state line on foot', flush=True)

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
        st_arr = {x: np.array(v, dtype=np.int64) for x, v in st_stops.items() if v}
        t_pre = time.time()

        def latest_from(nxt):
            # guard=False on purpose. The guard blocks a walk that crosses a state line into the target's
            # stop, which is a rule about how a search layer may collect a state, not about what is
            # physically possible. These tables are a feasibility bound: being too permissive only means a
            # dead branch survives a little longer, but being too strict prunes the answer. With the guard on
            # it refused the Hanover to Vermont line walk the route ends on, which put L_end[Hanover] one
            # minute before the route's own arrival there, and that one minute compounded backwards into four
            # hours by Houston and made Maine look uncollectable from Texas onwards.
            lat, ok, k0, k1 = F.layer(nxt, False, D - a.span * 3600, None)
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

    def ceiling(collected):
        """Per stop, the latest you could get off there and still owe nothing you cannot collect.

        The same test as looping every owed state for every candidate, but done once for the node instead of
        once per ride: one node offered 1674890 candidate alights, and at up to 48 checks each that was tens
        of millions of comparisons per node, which took the search from 103 nodes/s to 2. numpy takes the
        column-wise minimum over the owed rows in about a millisecond and the answer is identical."""
        owed = [y for y in range(N_STATES) if y not in collected]
        if not owed: return L_end
        return np.minimum(L[owed].min(axis=0), L_end)

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

    def rides_from(s, t, aboard, collected, cap=None):
        """The menu at stop s at time t: (alight stop, alight time, trip, states it collects).
        Riding on the trip already boarded needs no transfer; anything else does."""
        out = []
        all_states = range(N_STATES)
        if cap is None and L is not None: cap = ceiling(collected)
        # Every footpath the router built, with no second opinion. This line used to drop any link costing
        # more than a made-up 1200, which is seconds, so it silently hid every local-transit hop longer than
        # twenty minutes: Memphis to Bellevue at Carr, Salt Lake City Intermodal to the Salt Lake Express
        # shop, Barstow Station to the depot. Those are the hops the reference route cannot do without, and
        # losing the Memphis one cost it Mississippi, after which alight_ok correctly refused every stop from
        # Kansas onward because Mississippi could no longer be collected. time_router already decides what is
        # walkable and what needs local transit; deciding again here only throws its answer away.
        for j, w in [(s, 0)] + list(R.foot.get(s, ())):
            t_ok = t + w + (0 if j == s else 0)
            times = dep_times.get(j)
            if not times: continue
            i = bisect.bisect_left(times, t_ok)
            seen = set()
            while i < len(times) and times[i] <= t_ok + a.horizon * 3600:
                k = board_at[j][i]; i += 1
                key = R.ctrip[k]
                if key in seen: continue
                # staying aboard is free only on the same trip at the same stop; if this came from a stop
                # walked to, the chain got off and walked, so it pays the transfer like anything else
                if not (key == aboard and j == s) and R.dep[k] < t_ok + MIN_TRANSFER: continue
                seen.add(key)
                cs = trip_conns[key]
                p = next((n for n, kk in enumerate(cs) if kk == k), None)
                if p is None: continue
                got = set()
                for kk in cs[p:]:
                    to = int(R.cto[kk]); st = int(R.state[to])
                    if st >= 0: got.add(st)
                    at = float(R.arr[kk])
                    if cap is not None:
                        # the ride's own new states are not owed after it, so they may exceed the ceiling
                        if at > cap[to] and any(at > L[y][to] for y in all_states
                                                if y not in collected and y not in got): continue
                        if at > L_end[to]: continue
                    elif not alight_ok(to, at, [y for y in all_states if y not in collected and y not in got]):
                        continue
                    out.append((to, at, key, frozenset(got)))
                    # Stepping over the line on foot is how the route takes Mississippi, but it is a move, not
                    # a freebie: you get off, walk out, and walk back, and only then carry on. Crediting it at
                    # every stop a ride passes, for nothing, let the search collect states it never visited in
                    # zero time. Charge both directions, leave the vehicle, and offer it as its own option.
                    for y, w in walkin.get(to, ()):
                        if y in got or y in collected: continue
                        at2 = at + 2 * w
                        if cap is not None and (at2 > L_end[to] or at2 > L[y][to]): continue
                        if cap is not None and at2 > cap[to] and any(
                                at2 > L[z][to] for z in all_states if z not in collected and z not in got and z != y):
                            continue
                        out.append((to, at2, None, frozenset(got | {y})))
        return out

    best = [None]; limit = [a.target * 3600]; seen_nodes = [0]; t_run = time.time(); deepest = [0]
    dom = {}       # (stop, collected, aboard) -> best time EXPANDED, read when popping
    queued = {}    # the same key -> best time already SITTING in the frontier, read only when pushing.
                   # These have to stay apart. Writing a pushed node's own time into dom would make it fail
                   # its own check the moment it is popped, so every node would prune itself.
    NEED = a.states

    def dfs(stop, t, collected, aboard, path):
        if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: return
        seen_nodes[0] += 1
        spent = (t - T0) if not back else (T0 - t)
        if spent > limit[0]: return
        if len(collected) >= NEED and (END_ST is None or int(R.state[stop]) == END_ST):
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
        key = (stop, collected, aboard)   # still aboard a through trip is not the same as standing here
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

    def backward_search():
        """The mirror: stand at the end at its deadline, take rides that ARRIVE by now, ride back to where
        they started, and make the start as late as possible.

        Forward and backward differ in one way that is not cosmetic. Forward has both anchors, a start time
        and a deadline, so `L[y][stop]` can be precomputed once: the latest you could be somewhere and still
        collect y and finish. Backward deliberately leaves the start free, which is the whole reason to run
        it, so there is no second anchor to precompute against. The same question is still answerable
        exactly, just not in advance: one reverse scan from where the chain stands says the latest you could
        be at every stop and still get here in time, and a state is still collectible if any of its stops
        clears the earliest start the limit allows. One scan covers all 48 states, and it is a fact rather
        than an estimate, same as forward."""
        import heapq
        T_min = D - a.target * 3600        # no start earlier than this can come in under the limit
        arr_at = defaultdict(list)
        for k in range(len(R.dep)): arr_at[int(R.cto[k])].append(k)
        for v in arr_at.values(): v.sort(key=lambda k: R.arr[k])
        arr_times = {s_: [R.arr[k] for k in v] for s_, v in arr_at.items()}
        print(f'  indexed arrivals at {len(arr_at)} stops; no start before '
              f'{R.fmt_time(T_min, st_stops[END_ST][0])}', flush=True)

        def dense(sp):
            ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
            if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
            return ns_stop, ns_dep

        def still_collectable(stop, t, owed, need_more):
            """Could enough of the owed states still have been collected before standing here at t?

            Enough, not all. Demanding every owed state is only right when all 48 are wanted; with --states N
            fewer are needed and requiring the rest prunes chains that would have finished the test case."""
            if need_more <= 0: return True
            if not owed: return False
            lat, ok, k0, k1 = F.layer({int(stop): float(t)}, False, T_min, None)
            eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
            vals = np.maximum(lat, eff)
            cnt = 0
            for y in owed:
                sa = st_arr.get(y)
                if sa is not None and float(vals[sa].max()) >= T_min:
                    cnt += 1
                    if cnt >= need_more: return True
            return False

        def rides_into(s_, t, aboard, collected):
            """Rides that could have dropped you here by t: (board stop, board time, trip, states collected)."""
            out = []
            for j, w in [(s_, 0)] + list(R.foot.get(s_, ())):
                t_ok = t - w
                times = arr_times.get(j)
                if not times: continue
                i = bisect.bisect_right(times, t_ok) - 1
                seen = set()
                while i >= 0 and times[i] >= t_ok - a.horizon * 3600:
                    k = arr_at[j][i]; i -= 1
                    key = R.ctrip[k]
                    if key in seen: continue
                    # same trip and same stop, or it pays the transfer (see the forward side)
                    if not (key == aboard and j == s_) and R.arr[k] > t_ok - MIN_TRANSFER: continue
                    seen.add(key)
                    cs = trip_conns[key]
                    pos = next((n for n, kk in enumerate(cs) if kk == k), None)
                    if pos is None: continue
                    got = {int(R.state[j])} if R.state[j] >= 0 else set()
                    for n in range(pos, -1, -1):
                        kk = cs[n]
                        frm = int(R.cfrom[kk]); st_ = int(R.state[frm])
                        if st_ >= 0: got.add(st_)
                        bt = float(R.dep[kk])
                        if bt < T_min: break
                        out.append((frm, bt, key, frozenset(got)))
                        for y2, w2 in walkin.get(frm, ()):
                            if y2 in got or y2 in collected: continue
                            if bt - 2 * w2 < T_min: continue
                            out.append((frm, bt - 2 * w2, None, frozenset(got | {y2})))
            return out

        start_c = set()
        if R.state[st_stops[END_ST][0]] >= 0: start_c.add(END_ST)
        seeds = [(int(x), D) for x in st_stops[END_ST]]
        q = []; seq = [0]
        for st0_, t0_ in seeds:
            heapq.heappush(q, (-(D - t0_) + a.credit * 3600 * len(start_c), D - t0_, seq[0], st0_, t0_,
                               frozenset(start_c), None, ()))
            seq[0] += 1
        while q:
            if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: break
            _f, spent, _, stop, t, collected, aboard, path = heapq.heappop(q)
            seen_nodes[0] += 1
            if spent > limit[0]: continue
            if len(collected) >= NEED:
                limit[0] = spent; best[0] = (spent, list(path))
                print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h back to '
                      f'{R.stop_name[stop][:30]}, {len(collected)} states, {len(path)} rides', flush=True)
                continue
            if len(collected) > deepest[0]:
                deepest[0] = len(collected)
                print(f'  [{time.time() - t_run:5.0f}s] {len(collected)}/{NEED} states, {spent / 3600:6.1f} h back, '
                      f'at {R.stop_name[stop][:28]}, {len(path)} rides, {seen_nodes[0]} nodes, '
                      f'{len(q)} in frontier', flush=True)
            key = (stop, collected, aboard)
            prev = dom.get(key)
            if prev is not None and prev <= spent: continue
            dom[key] = spent
            owed = [y for y in range(N_STATES) if y not in collected]
            if not still_collectable(stop, t, owed, NEED - len(collected)): continue
            opts = rides_into(stop, t, aboard, collected)
            n_new = lambda o: len(o[3] - collected)
            if a.order == 'rate': opts.sort(key=lambda o: (n_new(o) == 0, (t - o[1]) / max(1, n_new(o))))
            elif a.order == 'states': opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), -o[1]))
            else: opts.sort(key=lambda o: (n_new(o) == 0, -o[1]))
            for frm, bt, trip, got in opts[:a.width]:
                new = collected | got
                sp2 = D - bt
                if sp2 > limit[0]: continue
                k2 = (frm, new, trip)
                pv = dom.get(k2); qv = queued.get(k2)
                if pv is not None and pv <= sp2: continue
                if qv is not None and qv <= sp2: continue
                queued[k2] = sp2
                seq[0] += 1
                heapq.heappush(q, (sp2 - a.credit * 3600 * len(new), sp2, seq[0], frm, bt, new, trip,
                                   path + ((trip, frm, stop, bt, t),)))

    if a.track:
        import pickle as _pk
        import time_search as ts
        from time_search import Search
        d = _pk.load(open(a.track, 'rb'))
        st0 = R.stop_name.index(d['start'])
        S = Search(R, st0, d['t0'], [], 1)
        ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0, d['t0'], S, None, None
        _, legs = S.evaluate(d['order'])
        rides = [l for l in legs if l[0] == 'ride']
        print(f'\nreplaying {len(rides)} rides of {a.track} through this search '
              f'(order {a.order}, width {a.width})\n', flush=True)
        stop, t, aboard = st0, d['t0'], None
        gone = 0
        _ss = set()
        if R.state[st0] >= 0: _ss.add(int(R.state[st0]))
        collected = frozenset(_ss)
        # the reference takes some states on foot (Mississippi at Holmes, Vermont at Hanover); those are walk
        # legs, and this replay follows rides, so read them off the route's own legs
        by_walk = {}
        for _l in legs:
            if _l[0] == 'walk' and _l[2] >= R.first_virtual and R.state[_l[2]] >= 0:
                by_walk.setdefault(_l[1], set()).add(int(R.state[_l[2]]))
        lost = 0
        for n, l in enumerate(rides, 1):
            _, trip, bs, bt, al, at = l
            opts = rides_from(stop, t, aboard, collected)
            n_new = lambda o: len(o[3] - collected)
            if a.order == 'rate': opts.sort(key=lambda o: (n_new(o) == 0, (o[1] - t) / max(1, n_new(o))))
            elif a.order == 'states': opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), o[1]))
            else: opts.sort(key=lambda o: (n_new(o) == 0, o[1]))
            rank = next((i + 1 for i, o in enumerate(opts) if o[0] == al and o[2] == trip), None)
            got = next((o[3] for o in opts if o[0] == al and o[2] == trip), frozenset())
            info = R.trip_info.get(trip, ('', ''))
            name = (info[1] or info[0])[:22]
            if rank is None:
                # why not: was the trip offered at all, and would getting off there have been allowed?
                offered = any(o[2] == trip for o in opts)
                owed = [y for y in range(N_STATES) if y not in collected]
                ok = alight_ok(al, at, [y for y in owed if y != int(R.state[al])])
                bad = [ab(y) for y in owed if y != int(R.state[al]) and L is not None and at > L[y][al]]
                why = (('alight_ok rejected the stop; no longer collectable from there: ' + ' '.join(bad)) if not ok else
                       'trip offered but not to this stop' if offered else
                       'trip offered nowhere allowed, or not reachable from here')
                print(f'  leg {n:2d} {name:22s} -> {R.stop_name[al][:26]:26s} MISSING: {why}', flush=True)
                lost += 1; gone += 1
            else:
                flag = '' if rank <= a.width else f'  <-- OUTSIDE --width {a.width}'
                print(f'  leg {n:2d} {name:22s} -> {R.stop_name[al][:26]:26s} rank {rank:3d}/{len(opts):4d}'
                      f'  +{" ".join(ab(x) for x in sorted(got - collected)) or "-"}{flag}', flush=True)
                if rank > a.width: lost += 1
            collected = collected | got | frozenset(by_walk.get(al, ()))
            stop, t, aboard = al, at, trip
        print(f'\n{len(rides) - lost}/{len(rides)} rides reproducible within --width {a.width}; '
              f'{len(collected)}/{N_STATES} states collected along the way')
        if lost == 0: print('the control replays end to end: every ride it takes is on the menu and inside the width.')
        if gone:
            print(f'FAIL: {gone} of the control\'s rides are not on the menu at all. A leg below --width is '
                  f'fine, backtracking reaches it; a leg missing is a bug in the search.')
            sys.exit(1)
        return

    def best_first(start_stop, t_start, start_collected):
        """Expand the most promising node in the whole frontier, not the deepest.

        Depth-first commits to its first guess: ordered by hours per new state it dives to 21 states having
        spent 141 of its 238 h, which cannot finish, and then has to climb out of that subtree before trying
        anything else. Ten minutes is nowhere near enough. Best-first keeps every node it has reached and
        always grows the one that looks closest to done, so a bad opening costs one expansion instead of the
        whole budget. Pruning and dominance are unchanged and still exact."""
        import heapq
        q = []; seq = [0]
        pri = lambda spent, n: spent - a.credit * 3600 * n
        heapq.heappush(q, (pri(t_start - T0, len(start_collected)), t_start - T0, 0, start_stop, t_start,
                           start_collected, None, ()))
        while q:
            if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: break
            _f, spent, _, stop, t, collected, aboard, path = heapq.heappop(q)
            seen_nodes[0] += 1
            if spent > limit[0]: continue
            # Collecting every state is not the same as finishing. With an end given, the deadline tables
            # prune the whole way on the assumption the chain still has to reach it, so accepting a chain
            # that is standing somewhere else contradicts the pruning that got it there.
            if len(collected) >= NEED and (END_ST is None or int(R.state[stop]) == END_ST):
                limit[0] = spent; best[0] = (spent, list(path))
                print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h, {len(collected)} states, '
                      f'{len(path)} rides', flush=True)
                continue
            if len(collected) > deepest[0]:
                deepest[0] = len(collected)
                print(f'  [{time.time() - t_run:5.0f}s] {len(collected)}/{NEED} states, {spent / 3600:6.1f} h spent, '
                      f'at {R.stop_name[stop][:28]}, {len(path)} rides, {seen_nodes[0]} nodes, '
                      f'{len(q)} in frontier', flush=True)
            if L is not None and t > L_end[stop]: continue
            key = (stop, collected, aboard)   # still aboard a through trip is not the same as standing here
            prev = dom.get(key)
            if prev is not None and prev <= spent: continue
            dom[key] = spent
            opts = rides_from(stop, t, aboard, collected)
            n_new = lambda o: len(o[3] - collected)
            if a.order == 'rate': opts.sort(key=lambda o: (n_new(o) == 0, (o[1] - t) / max(1, n_new(o))))
            elif a.order == 'states': opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), o[1]))
            else: opts.sort(key=lambda o: (n_new(o) == 0, o[1]))
            for to, at, trip, got in opts[:a.width]:
                new = collected | got
                # Dominance when queuing, not only when popped. Many queued nodes share a stop, a set of
                # states and a boarded trip, and only the earliest of those can ever matter; checking at push
                # keeps the duplicates out of the frontier instead of carrying them until they surface.
                k2 = (to, new, trip); sp_new = at - T0
                pv = dom.get(k2); qv = queued.get(k2)
                if pv is not None and pv <= sp_new: continue
                if qv is not None and qv <= sp_new: continue
                queued[k2] = sp_new
                seq[0] += 1
                heapq.heappush(q, (pri(at - T0, len(new)), at - T0, seq[0], to, at, new, trip,
                                   path + ((trip, stop, to, t, at),)))
            if len(q) > a.queue:
                # Drop only what is provably dead: a node whose clock has passed the limit, or passed the
                # latest it could still collect something it owes. Both are facts. The old rule kept the best
                # half by hours per state, which is the same relative ranking that orders the frontier, and
                # relative pruning is exactly what loses a route that looks inefficient for a long stretch
                # before it pays off. That is the mistake the beam made; it should not come back as a memory
                # detail. If the sweep frees nothing the frontier is genuinely all live, so say so and stop
                # rather than quietly discard a branch that might have been the answer.
                before = len(q)
                alive = []
                for it in q:
                    _f2, sp2, sq2, st2, t2, col2, ab2, pa2 = it
                    if sp2 > limit[0]: continue
                    if L is not None:
                        if t2 > L_end[st2]: continue
                        cl = L[:, st2]
                        if any(t2 > cl[y] for y in range(N_STATES) if y not in col2): continue
                    alive.append(it)
                q = alive; heapq.heapify(q)
                print(f'  [{time.time() - t_run:5.0f}s] frontier swept {before} -> {len(q)} '
                      f'(only provably dead nodes dropped)', flush=True)
                if len(q) > a.queue:
                    print(f'  frontier is {len(q)} and all of it is still live; raise --queue rather than '
                          f'guess which to discard', flush=True)
                    break

    sys.setrecursionlimit(20000)
    if back:
        if L is None:
            print('backward needs --end and --by to anchor the deadline'); return
        print(f'\nbackward from {a.end} at {datetime.fromtimestamp(D, ZoneInfo(a.tz)):%a %Y-%m-%d %H:%M}, '
              f'free start, limit {a.target} h\n', flush=True)
        backward_search()
        el2 = time.time() - t_run
        print(f'\n{seen_nodes[0]} nodes in {el2:.0f} s ({seen_nodes[0] / max(el2, 1):.0f}/s); '
              f'deepest {deepest[0]}/{NEED} states')
        if best[0] is None: print(f'nothing reached {NEED} states under {a.target} h in the budget')
        else:
            spent, path = best[0]
            print(f'best {spent / 3600:.2f} h, starting {R.fmt_time(D - spent, path[-1][1]) if path else "?"}')
            chk = confirm(path[::-1])
            if chk: print(f'  independent check: {chk[0]}' + (f', {chk[1]:.2f} h' if chk[1] is not None else ''))
            for trip, frm, to, bt, at in path[::-1]:
                info = R.trip_info.get(trip, ('', '')) if trip else ('', 'border walk-in')
                print(f'   {R.fmt_time(bt, frm)} {R.stop_name[frm][:26]:26s} -> {R.fmt_time(at, to)} '
                      f'{R.stop_name[to][:26]:26s} {(info[1] or info[0])[:24]}')
        return
    if START is None: print('need --start'); return
    start_states = set()      # a walk-in at the start is a move like any other, and costs its time
    if R.state[START] >= 0: start_states.add(int(R.state[START]))
    if a.mode == 'best': best_first(START, T0, frozenset(start_states))
    else: dfs(START, T0, frozenset(start_states), None, [])
    el = time.time() - t_run
    print(f'\n{seen_nodes[0]} nodes in {el:.0f} s ({seen_nodes[0] / max(el, 1):.0f}/s), {len(dom)} distinct '
          f'(stop, states); deepest {deepest[0]}/{NEED} states')
    def confirm(path_):
        """Hand the route back to the router and see if it agrees. The search must not be the only witness
        to its own result.

        Two bugs tonight produced routes that do not exist: states were credited at every stop a ride passed
        without anyone getting off or any time being charged, and a chain was accepted for collecting all 48
        while standing somewhere that was not the end. Neither could have survived this check, because the
        router evaluates the state order independently and would not have reproduced the finish. Anything the
        search believes and the router will not confirm is a bug in the search, and saying so loudly is worth
        more than the result."""
        if not path_: return None
        rides_ = [x for x in path_ if x[0] is not None]
        if not rides_: return None
        st0_ = rides_[0][1]; t0_ = rides_[0][3]
        order_ = []
        for trip_, frm_, to_, bt_, at_ in path_:
            for st_ in (int(R.state[frm_]), int(R.state[to_])):
                if st_ >= 0 and st_ not in order_: order_.append(st_)
        try:
            import time_search as ts_
            from time_search import Search as S_
            SS = S_(R, st0_, t0_, [], 1)
            ts_._R, ts_._START, ts_._T0, ts_._SELF, ts_._BASE, ts_._END = R, st0_, t0_, SS, None, None
            f_, legs_ = SS.evaluate(order_)
            if f_ == float('inf'): return ('the router cannot follow this order at all', None)
            miss_ = [ab(x) for x in SS.missing(legs_)]
            return (('router confirms' if not miss_ else 'router says it never reaches ' + ' '.join(miss_)),
                    (f_ - t0_) / 3600)
        except Exception as e:
            return (f'could not be checked ({type(e).__name__}: {e})', None)

    if best[0] is None:
        print(f'nothing reached {NEED} states under {a.target} h in the budget')
    else:
        spent, path = best[0]
        print(f'best {spent / 3600:.2f} h over {len(path)} rides')
        chk = confirm(path)
        if chk: print(f'  independent check: {chk[0]}' + (f', {chk[1]:.2f} h' if chk[1] is not None else ''))
        for trip, s, to, t, at in path[:60]:
            info = R.trip_info.get(trip, ('', ''))
            print(f'   {R.fmt_time(t, s)} {R.stop_name[s][:26]:26s} -> {R.fmt_time(at, to)} {R.stop_name[to][:26]:26s} '
                  f'{(info[1] or info[0])[:24]}')
        if a.out: pickle.dump(dict(path=path, spent=spent), open(a.out, 'wb')); print('wrote', a.out)


if __name__ == '__main__':
    main()
