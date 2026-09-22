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
    ap.add_argument('--hub', type=int, default=6, help='alight here if the stop has at least this many services')
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
    if back:
        inv = {v: k for k, v in ABBR.items()}
        END_ST = R.state_names.index(inv[a.end])

    def rides_from(s, t, aboard):
        """The menu at stop s at time t: (alight stop, alight time, trip, states it collects).
        Riding on the trip already boarded needs no transfer; anything else does."""
        out = []
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
                    if nserv.get(to, 0) >= a.hub or st >= 0:
                        out.append((to, float(R.arr[kk]), key, frozenset(got)))
        return out

    best = [None]; limit = [a.target * 3600]; seen_nodes = [0]; t_run = time.time()
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
        key = (stop, collected)
        prev = dom.get(key)
        if prev is not None and prev <= spent: return
        dom[key] = spent
        opts = rides_from(stop, t, aboard)
        opts.sort(key=lambda o: (-len(o[3] - collected), o[1]))
        for to, at, trip, got in opts[:12]:
            new = collected | got
            if len(new) == len(collected) and nserv.get(to, 0) < a.hub: continue
            path.append((trip, stop, to, t, at))
            dfs(to, at, new, trip, path)
            path.pop()

    sys.setrecursionlimit(20000)
    if back:
        print('backward mode needs the reverse connection index; not built yet, running forward from --start')
    if START is None: print('need --start'); return
    dfs(START, T0, frozenset({int(R.state[START])}) if R.state[START] >= 0 else frozenset(), None, [])
    el = time.time() - t_run
    print(f'\n{seen_nodes[0]} nodes in {el:.0f} s ({seen_nodes[0] / max(el, 1):.0f}/s), {len(dom)} distinct (stop, states)')
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
