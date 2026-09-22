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
from typing import NamedTuple
import numpy as np
from time_router import TimeRouter, load_feeds, cached_router, MIN_TRANSFER, N_STATES, WALK_MAX_KM
import backward as B
from common import ABBR


class Opt(NamedTuple):
    """One thing the chain can do next: ride somewhere, and possibly step over a state line on foot there.

    `walk` is its own field because hiding it anywhere else has cost this project eight bugs. It was first
    absent entirely, so states taken on foot were never collected; then credited free at every stop a ride
    passed, so the search invented routes; then smuggled into the trip slot as a marker, where `trip` was
    sometimes a trip and sometimes not, and every reader that assumed moves are rides had a silent hole.

    A ride is (board, alight, trip, time) and the whole codebase speaks that grammar. A walk-in is getting
    off, leaving the network on foot, coming back, and holding a state never ridden to. It does not fit, and
    dressing it as a ride does not make it fit, it only moves the misfit somewhere nobody is looking. Here
    `trip` is always a trip and `walk` is always the state walked into or None, so a reader that ignores
    `walk` is visibly ignoring it rather than accidentally not seeing it.
    """
    stop: int           # where this move leaves you (forward) or picks you up (backward)
    time: float         # when, already including both directions of any walk
    trip: object        # the trip ridden, never a marker
    got: frozenset      # states this move collects, including the walked-into one
    walk: object = None # the state stepped into on foot, or None


def final_stop(legs):
    """Where a router itinerary actually ends.

    Rides and walks do not agree on where the destination sits in the tuple: a ride is
    ('ride', trip, board, dep, alight, arr) and a walk is ('walk', from, to, t0, t1), so the destination is
    index 4 on one and index 2 on the other. Reading index 2 for both, which the first version of the
    end-of-route check did, silently asks whether the route BOARDED its last ride in the end state. The
    control finishes by riding to Hanover and walking over the Vermont line, so the two readings disagree
    there, which is exactly the case the check exists for.
    """
    for l in reversed(legs):
        if l[0] == 'ride': return int(l[4])
        if l[0] == 'walk': return int(l[2])
    return None


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
    ap.add_argument('--order', default='slack', choices=('rate', 'states', 'early', 'slack'),
                    help="which ride to try first: 'rate' hours per new state, 'states' most new states, "
                         "'early' earliest arrival, 'slack' how much room the move leaves against the "
                         "deadline tables. 'slack' is the default because it is measured better: 25 states "
                         "for 'rate', 28 for slack, 29 with --dedupe as well. It needs --end/--by and falls "
                         "back to 'rate' without them.")
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
    ap.add_argument('--dedupe', action='store_true', help='drop options another option can already do '
                    'everything of, which is most of them: the control\'s forty legs hold 3868010 options '
                    'and 71693 survivors. Still opt-in, because making it the default changes what every '
                    'search sees and that deserves its own measurement, not a coat-tail ride on this one.')
    ap.add_argument('--anatomy', action='store_true', help='with --track, break down each leg\'s option '
                    'list: how many options, how many distinct destinations, and how many survive exact '
                    'dominance. Answers whether a node with a million options has a million choices.')
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out')
    a = ap.parse_args()
    back = a.dir == 'backward'
    when = datetime.fromisoformat(a.by if back else a.at).replace(tzinfo=ZoneInfo(a.tz))
    T0 = when.timestamp()
    R = cached_router((when.date() if not back else (when - __import__('datetime').timedelta(days=12)).date()), a.days)
    ab = lambda x: ABBR[R.state_names[x]] if x >= 0 else '--'
    print(f'{a.dir} from {when:%a %Y-%m-%d %H:%M}, limit {a.target} h, {a.states} states required', flush=True)

    # connections grouped by trip, in order, so boarding a trip and riding on is one move
    t_build = time.time()
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)
    for v in trip_conns.values(): v.sort(key=lambda k: R.dep[k])
    # Where each connection sits in its own trip. Both directions need this to know where boarding or
    # alighting happens along a trip, and both were finding it by walking the trip's connection list from
    # the front for every candidate. On a long-distance train that is a few hundred comparisons, paid once
    # per arrival considered, per node; backward crawled at one node a second because of it. The position
    # never changes, so record it once here and the lookup becomes an array index.
    conn_pos = np.empty(len(R.dep), dtype=np.int32)
    for v in trip_conns.values():
        for n_, k_ in enumerate(v): conn_pos[k_] = n_
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

    class Menu:
        """The option list, deduplicated as it is built rather than afterwards.

        `undominated` applied to a finished list saves the sort and the ranking, but not the building, and
        building is where the profiler put 46% of the search. The fix is only a matter of when the test
        runs: keep a front per destination and offer each candidate to it as the loops produce it, so the
        million never exists. Same rule, same survivors.

        It also moves the expensive part. A candidate's `frozenset(got)` was allocated a million times per
        node; the live set answers the subset test just as well, so only the survivors are frozen, which is
        about a thousand.
        """
        __slots__ = ('front', 'back')

        def __init__(self, back=False):
            self.front = defaultdict(list); self.back = back

        def add(self, where, when_, trip, got, walk=None):
            fr = self.front[where]
            for g, w, _ in fr:
                if (w - MIN_TRANSFER >= when_ if self.back else w + MIN_TRANSFER <= when_) and got <= g:
                    return
            keep = frozenset(got)
            fr[:] = [e for e in fr
                     if not ((when_ - MIN_TRANSFER >= e[1] if self.back else when_ + MIN_TRANSFER <= e[1])
                             and e[0] <= keep)]
            fr.append((keep, when_, Opt(where, when_, trip, keep, walk)))

        def list(self):
            return [e[2] for fr in self.front.values() for e in fr]

    def undominated(cands, back=False):
        """Drop the options that another option can already do everything of.

        A node's menu is mostly the same decision written out many times: three nested loops, over footpath
        neighbours, over trips leaving each, and over every downstream stop of each trip. One node on the
        control offered 1674890 options for 1135 distinct destinations.

        The test has to respect the fact that a node carries the trip it is aboard. A chain still on trip T
        can ride on without paying anything; a chain that reached the same stop on something else has to pay
        MIN_TRANSFER to board T. So arriving earlier with at least as many states is NOT enough to dominate:
        the earlier arrival has to be early enough to have boarded whatever the later one was going to stay
        on. That is exactly MIN_TRANSFER of slack, and with it the rule is safe, because anything the
        discarded option could do next the survivor can do too.

          forward:   A beats B at the same stop when got_A covers got_B and at_A + MIN_TRANSFER <= at_B
          backward:  A beats B at the same stop when got_A covers got_B and bt_A - MIN_TRANSFER >= bt_B

        Backward mirrors it because there a later boarding time is the better one: it leaves the start of
        the route later, which is what backward is maximising.
        """
        front = defaultdict(list)          # stop -> [(states gained, time, option)]
        for o in cands:
            where, when_ = o[0], o[1]
            got = o[3]
            fr = front[where]
            beaten = False
            for g, w, _ in fr:
                if (w - MIN_TRANSFER >= when_ if back else w + MIN_TRANSFER <= when_) and got <= g:
                    beaten = True; break
            if beaten: continue
            fr[:] = [(g, w, oo) for g, w, oo in fr
                     if not ((when_ - MIN_TRANSFER >= w if back else when_ + MIN_TRANSFER <= w) and g <= got)]
            fr.append((got, when_, o))
        return [oo for fr in front.values() for _g, _w, oo in fr]

    def anatomy(opts, al, trip, n_new):
        """How much of a node's option list is choice and how much is the same choice written out again.

        A node on the control offered 1156415 options, of which 1156403 collected nothing, and no ranking
        rescued the one the route needs: Saint George sat 486373rd by hours-per-state and 509148th by slack.
        That is a clue about the representation, not the ranking. The list is built by three nested loops,
        over footpath neighbours, over trips leaving each, and over every downstream stop of each trip, so
        the same physical decision appears once per stop you could ride to.

        Exact dominance says which of those are real. For one destination, only the earliest arrival for
        each distinct set of states gained can ever matter: anything arriving later having gained no more is
        worse in both quantities the search uses, elapsed time and states held, so discarding it cannot lose
        a route. That is the same test already trusted between nodes, applied inside one node's menu.
        """
        by_to = defaultdict(list)
        for o in opts: by_to[o[0]].append(o)
        survivors = undominated(opts)
        kept, ctrl_rank = len(survivors), None
        for i, o in enumerate(sorted(survivors, key=lambda o: (n_new(o) == 0, o[1])), 1):
            if o[0] == al and o[2] == trip and o.walk is None: ctrl_rank = i; break
        print(f'         anatomy: {len(opts)} options -> {len(by_to)} destinations -> {kept} after exact '
              f'dominance ({100.0 * kept / max(1, len(opts)):.2f}%)'
              + (f'; the control\'s ride is {ctrl_rank} of them' if ctrl_rank else ''), flush=True)

    def sort_opts(opts, collected, n_new, t, back=False):
        """Order a node's candidate rides, by slack when asked for it and by the old keys otherwise.

        Slack is how much room a move leaves before the first state it can no longer collect: for a ride
        that puts you at `to` at `at`, the minimum over everything still owed of `L[y][to] - at`, read
        straight off the deadline tables rather than estimated. `ceiling` already returns that minimum per
        stop for the node's owed set, in one numpy pass, so the whole list costs one column-wise min plus a
        subtraction per option.

        It is here because hours per new state, the old key, is a local measure and this route's value is
        not local. Measured against the control it disagrees at twelve of forty legs. The Silver Meteor
        carries Georgia, South Carolina, North Carolina and Virginia in fourteen hours and ranks last of
        thirteen collecting options, beaten by every short hop that takes one state in twenty minutes.
        Saint George, which is the only way south, ranks 486373rd of 1156403 positioning ones because it
        is scored on how little time it burns. Slack asks a different question: after this ride, how close
        am I to losing the state I can least afford to lose. A long haul that collects four states shrinks
        the owed set and can raise it; a five minute hop that goes nowhere cannot.

        The split between rides that collect and rides that do not is kept. The group ranks say it is not
        what binds, and dropping it would let a hop that changes nothing outrank a real ride whenever both
        are comfortable, which is the dithering the old comment warned about.
        """
        if a.order == 'slack' and L is not None:
            cap = ceiling(collected)
            capl = cap.tolist()                      # 1.15M numpy scalar reads per node is not affordable
            endl = L_end.tolist()

            def slack(o):
                to, at, got = o.stop, o.time, o.got     # by name: the tuple has grown once and will again
                if not (got - collected): return capl[to] - at      # owed unchanged, the node's own ceiling
                owed_after = [y for y in range(N_STATES) if y not in collected and y not in got]
                if not owed_after: return endl[to] - at
                return min(float(L[owed_after, to].min()), endl[to]) - at

            opts.sort(key=lambda o: (n_new(o) == 0, -slack(o)))
        elif a.order in ('rate', 'slack'):      # 'slack' lands here only backward, which has no tables
            opts.sort(key=lambda o: (n_new(o) == 0, ((t - o[1]) if back else (o[1] - t)) / max(1, n_new(o))))
        elif a.order == 'states':
            opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), -o[1] if back else o[1]))
        else:
            opts.sort(key=lambda o: (n_new(o) == 0, -o[1] if back else o[1]))
        return opts

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

    def rides_from(s, t, aboard, collected, cap=None, raw=False):
        """The menu at stop s at time t: (alight stop, alight time, trip, states it collects).
        Riding on the trip already boarded needs no transfer; anything else does."""
        menu = Menu() if (a.dedupe and not raw) else None
        out = []
        push = menu.add if menu is not None else (
            lambda w_, t_, k_, g_, wk_=None: out.append(Opt(w_, t_, k_, frozenset(g_), wk_)))
        all_states = range(N_STATES)
        if cap is None and L is not None: cap = ceiling(collected)
        # Plain lists for the two deadline arrays, and only once `cap` is actually filled in: reading them
        # before that line left capl as None while cap was not, and every candidate then died on a
        # subscript. Every check below indexes these once per candidate, and a numpy scalar read is an
        # order slower than a list one, which at hundreds of millions of candidates is tens of seconds.
        capl = cap.tolist() if cap is not None else None
        endl = L_end.tolist() if L is not None else None
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
                p = int(conn_pos[k])
                got = set()
                fresh = False        # has this ride collected anything the chain did not already hold?
                for kk in cs[p:]:
                    to = int(R.cto[kk]); st = int(R.state[to])
                    if st >= 0:
                        got.add(st)
                        if st not in collected: fresh = True
                    at = float(R.arr[kk])
                    if cap is not None:
                        # The ride's own new states are not owed after it, so they may exceed the ceiling,
                        # and that is the only reason this is not simply a lookup. Until the ride collects
                        # something the chain does not already hold, the exception cannot apply and the pair
                        # of tests below is exactly `at > cap[to]`: `any(at > L[y][to] for y in owed)` is
                        # `at > min over owed`, and cap is that same minimum already clamped by L_end.
                        #
                        # The test is whether anything NEW was collected, not whether `got` is empty. `got`
                        # holds every state the ride passes through and every stop sits in a state, so it is
                        # non-empty from the first stop onward and an emptiness test almost never fires. The
                        # first version of this checked emptiness, on the stated reasoning that "most stops
                        # a ride passes add no state", which confuses adding no NEW state with `got` being
                        # empty. It left the generator at 215M calls, barely fewer per node than before.
                        if not fresh:
                            if at > capl[to]: continue
                        else:
                            if at > capl[to] and any(at > L[y][to] for y in all_states
                                                     if y not in collected and y not in got): continue
                            if at > endl[to]: continue
                    elif not alight_ok(to, at, [y for y in all_states if y not in collected and y not in got]):
                        continue
                    push(to, at, key, got)
                    # Stepping over the line on foot is how the route takes Mississippi, but it is a move, not
                    # a freebie: you get off, walk out, and walk back, and only then carry on. Crediting it at
                    # every stop a ride passes, for nothing, let the search collect states it never visited in
                    # zero time. Charge both directions, leave the vehicle, and offer it as its own option.
                    for y, w in walkin.get(to, ()):
                        if y in got or y in collected: continue
                        at2 = at + 2 * w
                        # `L[y][to]` is the latest you can be at `to` and still collect y and finish, and
                        # it already prices the walk. Testing it at at2, after charging 2w, charges the walk
                        # twice and can refuse a walk-in that is comfortably feasible: exactly the shape
                        # that has cost Mississippi before. The question "can I still collect y from here"
                        # is asked at `at`, before walking; the end has to remain reachable at at2, after.
                        if cap is not None and (at2 > endl[to] or at > L[y][to]): continue
                        if cap is not None and at2 > capl[to] and any(
                                at2 > L[z][to] for z in all_states if z not in collected and z not in got and z != y):
                            continue
                        push(to, at2, key, got | {y}, y)
        return menu.list() if menu is not None else out

    best = [None]; limit = [a.target * 3600]; seen_nodes = [0]; t_run = time.time(); deepest = [0]
    last_q = [None]      # the frontier as the budget ran out, for the exit census
    # The deepest chain, win or not. A run that stalls at 31 of 48 is the interesting input for
    # repair_probe: the question it answers is how many of the twenty it still owes are sitting in
    # dead time the chain is already spending. Keeping only completed routes threw that away.
    deep_path = [None]
    beat = [time.time()]

    def heartbeat(n_front):
        """Print every 30 s regardless of progress. Reporting only on new depth makes a search that is
        grinding at a plateau look exactly like one that has hung, which cost a manual check of CPU time."""
        now = time.time()
        if now - beat[0] < 30: return
        beat[0] = now
        print(f'  [{now - t_run:5.0f}s] still {deepest[0]}/{NEED}, {seen_nodes[0]} nodes '
              f'({seen_nodes[0] / max(now - t_run, 1):.0f}/s), {n_front} in frontier, {sum(len(v) for v in dom_stop.values())} kept',
              flush=True)
    # Dominance by proof, not by coincidence. Keying on an identical set of collected states only ever
    # merges two chains that happen to hold exactly the same 48-bit set, so twenty states reached in a
    # different order never merge and the frontier fills with permutations of the same progress: backward
    # sat at 20/48 for ten minutes at full CPU with 3.9 GB of them. What actually licenses discarding a
    # chain is that another one at the same stop, no later, holds AT LEAST its states, because anything the
    # weaker chain can still do the stronger one can do too. States live in a 48-bit int here so the
    # superset test is one AND.
    dom_stop = defaultdict(list)   # stop -> [(states bitmask, elapsed)]

    def bits(cs):
        m = 0
        for y in cs: m |= 1 << y
        return m

    def dominated(stop, mask, spent):
        for m, sp in dom_stop[stop]:
            if sp <= spent and (m & mask) == mask: return True
        return False

    def remember(stop, mask, spent):
        lst = [(m, sp) for m, sp in dom_stop[stop] if not ((mask & m) == m and spent <= sp)]
        lst.append((mask, spent)); dom_stop[stop] = lst

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
            limit[0] = spent; best[0] = (spent, list(path), frozenset(collected))
            print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h, {len(collected)} states, '
                  f'{len(path)} rides', flush=True)
            return
        if len(collected) > deepest[0]:
            deepest[0] = len(collected); deep_path[0] = (spent, list(path), frozenset(collected))
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
        sort_opts(opts, collected, n_new, t)
        for o in opts[:a.width]:
            to, at, trip, got, walk = o
            new = collected | got
            path.append((trip, stop, to, t, at, walk))
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
            menu = Menu(back=True) if a.dedupe else None
            out = []
            push = menu.add if menu is not None else (
                lambda w_, t_, k_, g_, wk_=None: out.append(Opt(w_, t_, k_, frozenset(g_), wk_)))
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
                    pos = int(conn_pos[k])
                    got ={int(R.state[j])} if R.state[j] >= 0 else set()
                    for n in range(pos, -1, -1):
                        kk = cs[n]
                        frm = int(R.cfrom[kk]); st_ = int(R.state[frm])
                        if st_ >= 0: got.add(st_)
                        bt = float(R.dep[kk])
                        if bt < T_min: break
                        push(frm, bt, key, got)
                        for y2, w2 in walkin.get(frm, ()):
                            if y2 in got or y2 in collected: continue
                            if bt - 2 * w2 < T_min: continue
                            push(frm, bt - 2 * w2, key, got | {y2}, y2)
            return menu.list() if menu is not None else out

        start_c = set()
        if R.state[st_stops[END_ST][0]] >= 0: start_c.add(END_ST)
        seeds = [(int(x), D) for x in st_stops[END_ST]]
        q = []; seq = [0]
        for st0_, t0_ in seeds:
            heapq.heappush(q, (-(D - t0_) + a.credit * 3600 * len(start_c), D - t0_, seq[0], st0_, t0_,
                               frozenset(start_c), None, ()))
            seq[0] += 1
        while q:
            last_q[0] = q
            if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: break
            _f, spent, _, stop, t, collected, aboard, path = heapq.heappop(q)
            seen_nodes[0] += 1
            heartbeat(len(q))
            if spent > limit[0]: continue
            if len(collected) >= NEED:
                limit[0] = spent; best[0] = (spent, list(path), frozenset(collected))
                print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h back to '
                      f'{R.stop_name[stop][:30]}, {len(collected)} states, {len(path)} rides', flush=True)
                continue
            if len(collected) > deepest[0]:
                deepest[0] = len(collected); deep_path[0] = (spent, list(path), frozenset(collected))
                print(f'  [{time.time() - t_run:5.0f}s] {len(collected)}/{NEED} states, {spent / 3600:6.1f} h back, '
                      f'at {R.stop_name[stop][:28]}, {len(path)} rides, {seen_nodes[0]} nodes, '
                      f'{len(q)} in frontier', flush=True)
            mk = bits(collected)
            if dominated(stop, mk, spent): continue
            remember(stop, mk, spent)
            owed = [y for y in range(N_STATES) if y not in collected]
            if not still_collectable(stop, t, owed, NEED - len(collected)): continue
            opts = rides_into(stop, t, aboard, collected)
            n_new = lambda o: len(o[3] - collected)
            sort_opts(opts, collected, n_new, t, back=True)
            for o in opts[:a.width]:
                frm, bt, trip, got, walk = o
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
                                   path + ((trip, frm, stop, bt, t, walk),)))

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
            raw_opts = rides_from(stop, t, aboard, collected, raw=True) if a.dedupe else opts
            n_new = lambda o: len(o[3] - collected)
            sort_opts(opts, collected, n_new, t)
            # A control leg is a plain ride, so only a plain ride reproduces it. Before the walk field
            # existed a walk-in carried no trip and could never match here; now it carries the real one,
            # and without this the replay counts the ride-plus-detour variant as the same move. It showed
            # up as the tally rising from 30/40 to 31/40 on a refactor that was meant to change nothing,
            # which is the shape of a gate quietly getting easier to pass.
            same = lambda o: o[0] == al and o[2] == trip and o.walk is None
            rank = next((i + 1 for i, o in enumerate(opts) if same(o)), None)
            got = next((o[3] for o in opts if same(o)), frozenset())
            info = R.trip_info.get(trip, ('', ''))
            name = (info[1] or info[0])[:22]
            if rank is None and a.dedupe:
                # With dominance on, the menu is allowed to carry a different ride in place of the
                # control's, and the whole claim of the filter is that the substitute can do everything the
                # original could. So ask that, rather than asking for the original by name: a survivor at
                # the same stop, at least MIN_TRANSFER earlier, holding at least as many states, leaves
                # every later leg of the control available. Requiring trip identity would fail a menu that
                # is strictly better, which is how this gate read the Memphis leg as missing.
                want = next((o for o in raw_opts if same(o)), None)
                if want is not None:
                    cover = [(i + 1, o) for i, o in enumerate(opts)
                             if o[0] == al and o[1] + MIN_TRANSFER <= want[1] and (want[3] - collected) <= (o[3] - collected)]
                    if cover:
                        rank, (r_, sub) = cover[0][0], cover[0]
                        got = sub[3]
                        print(f'  leg {n:2d} {name:22s} -> {R.stop_name[al][:26]:26s} rank {rank:3d}/{len(opts):4d}'
                              f'  covered by an earlier ride at {R.fmt_time(sub[1], al)}'
                              + ('' if rank <= a.width else f'  <-- OUTSIDE --width {a.width}'), flush=True)
                        if rank > a.width: lost += 1
                        collected = collected | got | frozenset(by_walk.get(al, ()))
                        stop, t, aboard = al, at, trip
                        continue
            if rank is None:
                # why not: was the trip offered at all, and would getting off there have been allowed?
                offered = any(o[2] == trip and o.walk is None for o in opts)
                owed = [y for y in range(N_STATES) if y not in collected]
                ok = alight_ok(al, at, [y for y in owed if y != int(R.state[al])])
                bad = [ab(y) for y in owed if y != int(R.state[al]) and L is not None and at > L[y][al]]
                why = (('alight_ok rejected the stop; no longer collectable from there: ' + ' '.join(bad)) if not ok else
                       'trip offered but not to this stop' if offered else
                       'trip offered nowhere allowed, or not reachable from here')
                print(f'  leg {n:2d} {name:22s} -> {R.stop_name[al][:26]:26s} MISSING: {why}', flush=True)
                # Dominance may legitimately substitute a different ride to the same stop, and this gate
                # matches on trip identity, so say what did survive there and whether it actually covers
                # the control's ride. A survivor arriving at least MIN_TRANSFER earlier holding at least as
                # many states can do anything the control's ride could do next; anything else is a real loss.
                here = [o for o in opts if o[0] == al]
                print(f'         {len(here)} survivor(s) reach that stop; control wanted {R.fmt_time(at, al)}'
                      f' +{" ".join(ab(x) for x in sorted(got - collected)) or "-"}', flush=True)
                for o in sorted(here, key=lambda o: o[1])[:4]:
                    cov = (o[1] + MIN_TRANSFER <= at) and (got - collected) <= (o[3] - collected)
                    print(f'           {R.fmt_time(o[1], al)} +'
                          f'{" ".join(ab(x) for x in sorted(o[3] - collected)) or "-"}'
                          f'  {"covers it" if cov else "does NOT cover it"}', flush=True)
                lost += 1; gone += 1
            else:
                flag = '' if rank <= a.width else f'  <-- OUTSIDE --width {a.width}'
                # Rank within the leg's own group as well as overall. The sort puts every ride that
                # collects a state ahead of every ride that collects none, so a positioning leg's overall
                # rank is mostly the size of the group in front of it and says nothing about how badly it is
                # ranked. The group rank is the number that decides what to do about it: if the control's
                # positioning rides sit near the front of their own group, widening the cut or reserving a
                # few slots reaches them; if they are buried inside it, no reserve is enough and the way
                # positioning rides are ranked against each other has to change.
                mine = n_new(opts[rank - 1]) == 0
                peers = [o for o in opts if (n_new(o) == 0) == mine]
                grank = next((i + 1 for i, o in enumerate(peers) if same(o)), None)
                kind = 'positioning' if mine else 'collecting'
                print(f'  leg {n:2d} {name:22s} -> {R.stop_name[al][:26]:26s} rank {rank:3d}/{len(opts):4d}'
                      f'  +{" ".join(ab(x) for x in sorted(got - collected)) or "-"}{flag}', flush=True)
                print(f'         {kind:11s} {grank}/{len(peers)} within its own group', flush=True)
                if a.anatomy: anatomy(opts, al, trip, n_new)
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
            last_q[0] = q
            if time.time() - t_run > a.budget or seen_nodes[0] > a.nodes: break
            _f, spent, _, stop, t, collected, aboard, path = heapq.heappop(q)
            seen_nodes[0] += 1
            heartbeat(len(q))
            if spent > limit[0]: continue
            # Collecting every state is not the same as finishing. With an end given, the deadline tables
            # prune the whole way on the assumption the chain still has to reach it, so accepting a chain
            # that is standing somewhere else contradicts the pruning that got it there.
            if len(collected) >= NEED and (END_ST is None or int(R.state[stop]) == END_ST):
                limit[0] = spent; best[0] = (spent, list(path), frozenset(collected))
                print(f'  [{time.time() - t_run:5.0f}s] FOUND {spent / 3600:.2f} h, {len(collected)} states, '
                      f'{len(path)} rides', flush=True)
                continue
            if len(collected) > deepest[0]:
                deepest[0] = len(collected); deep_path[0] = (spent, list(path), frozenset(collected))
                print(f'  [{time.time() - t_run:5.0f}s] {len(collected)}/{NEED} states, {spent / 3600:6.1f} h spent, '
                      f'at {R.stop_name[stop][:28]}, {len(path)} rides, {seen_nodes[0]} nodes, '
                      f'{len(q)} in frontier', flush=True)
            # Only the end test here. The owed-state kill dfs runs at pop is already enforced at push:
            # rides_from accepts an alight only when `at <= cap[to]`, and cap is the minimum over owed
            # states of L[y][to] clamped by L_end. L never changes and a queued node never moves, so
            # anything that passed at push passes at pop. That was worth measuring rather than assuming, and
            # the counter said 0 of 13404 pops: the check was redundant and is gone.
            if L is not None and t > L_end[stop]: continue
            mk = bits(collected)
            if dominated(stop, mk, spent): continue
            remember(stop, mk, spent)
            opts = rides_from(stop, t, aboard, collected)
            n_new = lambda o: len(o[3] - collected)
            sort_opts(opts, collected, n_new, t)
            for o in opts[:a.width]:
                to, at, trip, got, walk = o
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
                                   path + ((trip, stop, to, t, at, walk),)))
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

    def route_record(path_, spent_, collected_, complete_, back_=False):
        """A chain in the shape everything downstream already reads.

        repair_probe and Search.evaluate want (start, t0, order); the search's own path is a list of legs.
        The first version of the stalled-chain writer emitted only the legs, so the pickle written for the
        repair test could not be read by the repair test: producer and consumer written an hour apart and
        never run against each other. `complete` still says whether this is a route or a chain that stalled,
        because a caller that cannot tell those apart will eventually treat one as the other.
        """
        legs_ = list(path_[::-1]) if back_ else list(path_)
        order_ = []

        def add_(st_):
            if st_ is not None and st_ >= 0 and st_ not in order_: order_.append(st_)

        for trip_, frm_, to_, bt_, at_, walk_ in legs_:
            # Every state the ride is actually in, not just the two it stops at. The search credits a state
            # when a ride passes through it, which is right, you are in it; deriving the order from
            # endpoints alone dropped the rest. A chain reporting 31 states wrote an order of 17, and
            # repair_probe then re-flew that 17-state ghost and offered back states the real chain already
            # held. The pass-through states are recoverable from the trip itself.
            add_(int(R.state[frm_]))
            cs_ = trip_conns.get(trip_) if trip_ is not None else None
            if cs_:
                on_ = False
                for kk_ in cs_:
                    a_, b_ = int(R.cfrom[kk_]), int(R.cto[kk_])
                    if a_ == frm_: on_ = True
                    if on_:
                        add_(int(R.state[a_])); add_(int(R.state[b_]))
                    if b_ == to_ and on_: break
            add_(int(R.state[to_]))
            add_(walk_)
        st0_ = legs_[0][1] if legs_ else (START if START is not None else 0)
        t0_ = legs_[0][3] if legs_ else T0
        return dict(path=legs_, spent=spent_, collected=sorted(collected_), complete=complete_,
                    start=R.stop_name[st0_], t0=float(t0_), order=order_,
                    service_date=str(R.d0) if hasattr(R, 'd0') else None)

    def census(q):
        """What was still in the queue when the budget ran out.

        `deepest` is printed at pop, before the death tests, so a high-water mark of 31 can be a node that
        died on the next line. Twenty minutes without a 32nd state says only that no surviving expansion
        minted one, and that is consistent with three different situations: a queue full of doomed chains
        nobody has killed yet, a live deep layer the ranking never chooses, and a shallow queue where the
        deep number was one lucky dive. The counters cannot tell them apart. A census can.
        """
        if not q: print('  queue empty at exit'); return
        hist = defaultdict(int)
        for e in q: hist[len(e[5])] += 1
        top = max(hist)
        print(f'  queue at exit: {len(q)} nodes, depth ' +
              ' '.join(f'{d}:{hist[d]}' for d in sorted(hist, reverse=True)[:12]), flush=True)
        if L is None: return
        deep = [e for e in q if len(e[5]) == top]
        live = []
        for e in deep:
            stop_, t_, coll_ = e[3], e[4], e[5]
            if t_ > L_end[stop_]: continue
            col_ = L[:, stop_]
            owed_ = [y for y in range(N_STATES) if y not in coll_]
            if any(t_ > col_[y] for y in owed_): continue
            live.append((stop_, t_, owed_))
        print(f'  of the {len(deep)} nodes at {top} states, {len(live)} can still collect everything they '
              f'owe, which the push-side test guarantees and is therefore not evidence', flush=True)
        for stop_, t_, owed_ in live[:5]:
            print(f'    {R.stop_name[stop_][:30]:30s} owes {" ".join(ab(y) for y in owed_[:18])}', flush=True)

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
        for trip_, frm_, to_, bt_, at_, walk_ in path_:
            for st_ in (int(R.state[frm_]), int(R.state[to_]), walk_):
                if st_ is not None and st_ >= 0 and st_ not in order_: order_.append(st_)
        try:
            import time_search as ts_
            from time_search import Search as S_
            SS = S_(R, st0_, t0_, [], 1)
            ts_._R, ts_._START, ts_._T0, ts_._SELF, ts_._BASE, ts_._END = R, st0_, t0_, SS, None, None
            f_, legs_ = SS.evaluate(order_)
            if f_ == float('inf'): return ('the router cannot follow this order at all', None)
            miss_ = [ab(x) for x in SS.missing(legs_)]
            if miss_: return ('router says it never reaches ' + ' '.join(miss_), (f_ - t0_) / 3600)
            # Finishing somewhere is not finishing at the end. The search refuses a chain that holds all 48
            # while standing somewhere other than END_ST, and this second witness was not checking the same
            # thing, so a route that collected everything and stopped in the wrong state could have been
            # reported as confirmed. Adversarial review found this; it had not bitten yet.
            if END_ST is not None:
                end_stop_ = final_stop(legs_)
                if end_stop_ is None or int(R.state[end_stop_]) != END_ST:
                    where_ = ab(int(R.state[end_stop_])) if end_stop_ is not None else '?'
                    return (f'router reaches every state but finishes in {where_}, not {ab(END_ST)}',
                            (f_ - t0_) / 3600)
            return ('router confirms', (f_ - t0_) / 3600)
        except Exception as e:
            return (f'could not be checked ({type(e).__name__}: {e})', None)

    if back:
        if L is None:
            print('backward needs --end and --by to anchor the deadline'); return
        print(f'\nbackward from {a.end} at {datetime.fromtimestamp(D, ZoneInfo(a.tz)):%a %Y-%m-%d %H:%M}, '
              f'free start, limit {a.target} h\n', flush=True)
        backward_search()
        el2 = time.time() - t_run
        print(f'\n{seen_nodes[0]} nodes in {el2:.0f} s ({seen_nodes[0] / max(el2, 1):.0f}/s); '
              f'deepest {deepest[0]}/{NEED} states')
        census(last_q[0] or [])
        if best[0] is None:
            print(f'nothing reached {NEED} states under {a.target} h in the budget')
            if a.out and deep_path[0] is not None:
                sp_, pa_, co_ = deep_path[0]
                pickle.dump(route_record(pa_, sp_, co_, False, back_=True), open(a.out, 'wb'))
                print(f'wrote {a.out}: the deepest chain, {len(co_)} states over {len(pa_)} rides, '
                      f'{sp_ / 3600:.1f} h. Not a route; the input repair_probe wants.')
        else:
            spent, path, coll_ = best[0]
            print(f'best {spent / 3600:.2f} h, starting {R.fmt_time(D - spent, path[-1][1]) if path else "?"}')
            chk = confirm(path[::-1])
            if chk: print(f'  independent check: {chk[0]}' + (f', {chk[1]:.2f} h' if chk[1] is not None else ''))
            agreed = bool(chk) and chk[0] == 'router confirms'
            if a.out:
                # Backward wrote nothing at all on success, so a route found this way was printed and lost.
                pickle.dump(route_record(path, spent, coll_, agreed, back_=True), open(a.out, 'wb'))
                print('wrote', a.out + ('' if agreed else '  (complete=False: the router did not confirm it)'))
            for trip, frm, to, bt, at, wy in path[::-1]:
                info = R.trip_info.get(trip, ('', '')) if trip else ('', 'border walk-in')
                print(f'   {R.fmt_time(bt, frm)} {R.stop_name[frm][:26]:26s} -> {R.fmt_time(at, to)} '
                      f'{R.stop_name[to][:26]:26s} {(info[1] or info[0])[:24]}'
                      + (f' + walk into {ab(wy)}' if wy is not None else ''))
        return
    if START is None: print('need --start'); return
    start_states = set()      # a walk-in at the start is a move like any other, and costs its time
    if R.state[START] >= 0: start_states.add(int(R.state[START]))
    if a.mode == 'best': best_first(START, T0, frozenset(start_states))
    else: dfs(START, T0, frozenset(start_states), None, [])
    el = time.time() - t_run
    print(f'\n{seen_nodes[0]} nodes in {el:.0f} s ({seen_nodes[0] / max(el, 1):.0f}/s), {sum(len(v) for v in dom_stop.values())} kept '
          f'(stop, states); deepest {deepest[0]}/{NEED} states')
    census(last_q[0] or [])
    if best[0] is None:
        print(f'nothing reached {NEED} states under {a.target} h in the budget')
        if a.out and deep_path[0] is not None:
            sp_, pa_, co_ = deep_path[0]
            pickle.dump(route_record(pa_, sp_, co_, False), open(a.out, 'wb'))
            print(f'wrote {a.out}: the deepest chain, {len(co_)} states over {len(pa_)} rides, '
                  f'{sp_ / 3600:.1f} h. Not a route; the input repair_probe wants.')
    else:
        spent, path, best_states = best[0]
        print(f'best {spent / 3600:.2f} h over {len(path)} rides')
        chk = confirm(path)
        if chk: print(f'  independent check: {chk[0]}' + (f', {chk[1]:.2f} h' if chk[1] is not None else ''))
        agreed = bool(chk) and chk[0] == 'router confirms'
        for trip, s, to, t, at, wy in path[:60]:
            info = R.trip_info.get(trip, ('', ''))
            print(f'   {R.fmt_time(t, s)} {R.stop_name[s][:26]:26s} -> {R.fmt_time(at, to)} {R.stop_name[to][:26]:26s} '
                  f'{(info[1] or info[0])[:24]}' + (f' + walk into {ab(wy)}' if wy is not None else ''))
        if a.out:
            # complete=True means the router agreed, not merely that the search stopped looking. A route it
            # refused is still worth writing, because the disagreement is the interesting artifact, but
            # labelling it complete would hand a reader a route the second witness rejected.
            pickle.dump(route_record(path, spent, best_states, agreed), open(a.out, 'wb'))
            print('wrote', a.out + ('' if agreed else '  (complete=False: the router did not confirm it)'))


if __name__ == '__main__':
    main()
