"""Is a whole ordering feasible at all? Not searched, tested.

The search keeps dying on east-first chains and the control goes west-first while the East is still owed.
Nobody knows whether east-first is INFEASIBLE or merely badly ranked, and that is a different question from
anything a search can answer, because a search that never finishes a route says nothing about which shapes
exist.

The pair table is two chained reverse scans: seed from y's stops with L[z] and you get the latest you can
be anywhere and still collect y, then z, then finish. Nothing stops that chaining to 48. Seed from the
first state's stops with L[second -> third -> ... -> end] and the value at the start stop is the latest you
could have left and still collected the whole order in that order and finished by the deadline.

    if that value is before the start time, the ordering is impossible

Definitively. Not estimated, not bounded. The scans are the same ones the search already prunes with and
they are permissive at every seam (guard=False, and `max(lat, eff)` lets a connection be boarded with zero
transfer), so the test can only ever be too generous. A shape it rules out is genuinely ruled out.

This is NOT the ordering search CLAUDE.md declares dead. That one searched the space of orderings guided by
a leftover estimate, and every form of the estimate failed because a spanning tree cannot price a set of
states with no idea where or when you are. This estimates nothing and searches nothing. It takes one shape
as a hypothesis and asks the timetable whether it can exist, for about 48 scans.

Falsification, before running: the control's own order must come back feasible with roughly its own known
slack. If the 237 route reads as impossible, the probe is wrong and nothing else it says counts.

    python3 shape_probe.py
    python3 shape_probe.py --shapes control,reverse,east-first
"""
import argparse, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
import backward as B
from common import ABBR

HERE_SHAPES = ('control', 'reverse', 'east-first', 'west-first', 'halves-swapped')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-09-24T00:54')
    ap.add_argument('--by', default='2026-10-03T22:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--start', default='Huntington Bus Stop')
    ap.add_argument('--route', default='../out/res_starttest.pkl', help='the order to permute')
    ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--shapes', default=','.join(HERE_SHAPES))
    a = ap.parse_args()

    tz = ZoneInfo(a.tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    inv = {v: k for k, v in ABBR.items()}
    ab = lambda x: ABBR[R.state_names[x]]
    F = B.RevFast(R)
    end_st = R.state_names.index(inv[a.end])

    st_stops = [[] for _ in range(N_STATES)]
    for s in range(R.N):
        if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)

    # Every exact match for the start name, because 2955 names in this router map to more than one stop and
    # picking the first silently is how a probe reports on a place nobody asked about.
    starts = [i for i, n in enumerate(R.stop_name) if n == a.start]
    if not starts: raise SystemExit(f'no stop named exactly {a.start!r}')

    def latest_from(nxt):
        lat, ok, k0, k1 = F.layer(nxt, False, D - a.span * 3600, None)
        eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
        return np.maximum(lat, eff)

    L_end = latest_from({s: D for s in st_stops[end_st]})

    def test(order):
        """latest departure from each stop that still does this whole order, and where it dies if it does"""
        cur = L_end
        for i, y in enumerate(reversed(order)):
            nxt = {s: float(cur[s]) for s in st_stops[y] if cur[s] > -np.inf}
            if not nxt:
                return None, f'{ab(y)} (step {len(order) - i} of {len(order)}) is unreachable from anything ' \
                             f'that could still finish'
            cur = latest_from(nxt)
        return cur, None

    # mean longitude per state, from the router's own coordinates rather than a hand list of "western states"
    xy = np.asarray(R.stop_xy, dtype=float)
    lon = {}
    for y in range(N_STATES):
        if st_stops[y]: lon[y] = float(xy[np.asarray(st_stops[y]), 0].mean())

    base = list(pickle.load(open(a.route, 'rb'))['order'])
    body = [y for y in base if y != end_st]

    def shape(name):
        if name == 'control': return list(body)
        if name == 'reverse': return list(reversed(body))
        if name == 'east-first': return sorted(body, key=lambda y: -lon.get(y, 0))
        if name == 'west-first': return sorted(body, key=lambda y: lon.get(y, 0))
        if name == 'halves-swapped':
            h = len(body) // 2
            return body[h:] + body[:h]
        raise SystemExit(f'unknown shape {name!r}; known: {", ".join(HERE_SHAPES)}')

    print(f'start {a.start!r}: {len(starts)} stop(s) with that exact name; departing '
          f'{datetime.fromtimestamp(t0, tz):%a %H:%M}, deadline {datetime.fromtimestamp(D, tz):%a %H:%M}\n')
    print(f'{"shape":16s} {"latest possible departure":>26s} {"margin":>10s}   verdict')
    for name in a.shapes.split(','):
        order = shape(name.strip()) + [end_st]
        cur, dead = test(order)
        if dead is not None:
            print(f'{name:16s} {"-":>26s} {"-":>10s}   IMPOSSIBLE: {dead}')
            continue
        best = max(float(cur[s]) for s in starts)
        if best <= -np.inf:
            print(f'{name:16s} {"unreachable":>26s} {"-":>10s}   IMPOSSIBLE from this start')
            continue
        m = (best - t0) / 3600
        print(f'{name:16s} {datetime.fromtimestamp(best, tz):>26%a %d %b %H:%M} {m:+9.2f} h   '
              f'{"feasible" if m >= 0 else "IMPOSSIBLE, must have left " + f"{-m:.2f} h earlier"}')

    print('\nMargin is how much later than the actual start you could have left and still done the whole '
          'order. Negative means no route exists in that order from this start at this time, which is a '
          'fact about the timetable and not about any search. The scans are permissive at every seam, so a '
          'shape ruled out here is genuinely ruled out; a positive margin is necessary, not sufficient.')


if __name__ == '__main__':
    main()
