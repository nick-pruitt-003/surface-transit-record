"""Is Pasco load-bearing for Washington, and how much does it cost to do without it?

Nick's claim: there is no efficient Washington route that does not go through Pasco. Whether you take the
Empire Builder there or the bus, it is the closest place to the mountain west from Washington that also
grabs Oregon and Idaho in the modal instance.

That is not an opinion the timetable cannot settle. `L[y][s]` is the latest you can be at stop s and still
collect state y and finish, one reverse scan seeded from y's stops with `L_end`. Seed the same scan from
y's stops MINUS Pasco and the difference at any stop is exactly what Pasco is worth there, in hours, with
nothing estimated and no threshold invented.

The claim is about three states, not one, so the triple is asked too: the latest you can be at s and still
collect WA, OR and ID in some order and finish. Chain three scans per order and take the best of all six
orders, because "the modal instance" is a claim about which order the timetable actually rewards and
picking one by hand would assume the answer.

Falsification, stated before running: if Pasco is load-bearing, removing it should cost hours at the
mountain-west stops (Salt Lake City, Denver, Boise) and little or nothing at stops that reach Washington
some other way. If removing it costs about the same everywhere, or nothing anywhere, the claim is wrong and
the WA deaths in the search have some other cause.

This matters because Washington keeps being the state the deep chains cannot pair with anything: the run-1
chain died on CA & WA at Springfield, and the baseline arm's deepest node died on NM & WA at Salt Lake City.

    python3 pasco_probe.py
"""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
import backward as B
from common import ABBR

# Stops to report at. Not Washington ones: the question is what Washington costs from elsewhere.
WATCH = ['Salt Lake City Intermodal', 'Denver', 'Boise', 'Missoula', 'Cheyenne', 'Portland',
         'Sandpoint', 'Chicago', 'Minneapolis', 'Sacramento', 'Springfield Union']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-09-24T00:54')
    ap.add_argument('--by', default='2026-10-03T22:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--without', default='Pasco', help='substring naming the stops to withhold')
    a = ap.parse_args()

    tz = ZoneInfo(a.tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    inv = {v: k for k, v in ABBR.items()}
    ab = lambda x: ABBR[R.state_names[x]]
    F = B.RevFast(R)

    st_stops = [[] for _ in range(N_STATES)]
    for s in range(R.N):
        if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)

    def latest_from(nxt):
        # guard=False, as everywhere else these tables are built: a bound that is too permissive only lets a
        # dead branch live longer, one that is too strict prunes the answer.
        lat, ok, k0, k1 = F.layer(nxt, False, D - a.span * 3600, None)
        eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool))
        return np.maximum(lat, eff)

    end_st = R.state_names.index(inv[a.end])
    L_end = latest_from({s: D for s in st_stops[end_st]})

    WA = R.state_names.index(inv['WA']); OR_ = R.state_names.index(inv['OR'])
    ID = R.state_names.index(inv['ID'])

    # Say out loud which stops are being withheld. A probe that silently picks a subset is how a made-up
    # threshold gets in: the point is that the reader can check the list against what they meant.
    held = [s for s in st_stops[WA] if a.without.lower() in R.stop_name[s].lower()]
    print(f'withholding {len(held)} of {len(st_stops[WA])} Washington stops matching {a.without!r}:')
    for s in held[:12]: print(f'    {R.stop_name[s]}')
    if not held:
        print('nothing matched, so there is nothing to withhold and the two columns will agree by '
              'construction. That is not a result.')
        return
    keep = [s for s in st_stops[WA] if s not in set(held)]

    def chain(order, wa_stops):
        """latest you can be anywhere and still collect these states in this order, then finish"""
        cur = L_end
        for y in reversed(order):
            src = wa_stops if y == WA else st_stops[y]
            nxt = {s: float(cur[s]) for s in src if cur[s] > -np.inf}
            if not nxt: return np.full(R.N, -np.inf)
            cur = latest_from(nxt)
        return cur

    import itertools
    print(f'\nWA alone, and WA+OR+ID best of all six orders. Hours are latest-possible arrival, so a '
          f'later number is better; the cost column is what withholding {a.without} takes away.\n')

    rows = []
    for label, order in [('WA', (WA,))] + [('WA+OR+ID', None)]:
        if order is not None:
            full = chain(order, st_stops[WA]); cut = chain(order, keep)
        else:
            perms = list(itertools.permutations((WA, OR_, ID)))
            full = np.max([chain(p, st_stops[WA]) for p in perms], axis=0)
            cut = np.max([chain(p, keep) for p in perms], axis=0)
        rows.append((label, full, cut))

    for label, full, cut in rows:
        print(f'{label}:')
        print(f'  {"stop":34s} {"with":>10s} {"without":>10s} {"cost":>10s}')
        for want in WATCH:
            hits = [s for s in range(R.N) if want.lower() in R.stop_name[s].lower()]
            if not hits: continue
            s = max(hits, key=lambda x: full[x])      # the best stop of that name, named in the output
            f_, c_ = float(full[s]), float(cut[s])
            fmt = lambda v: 'unreachable' if v <= -np.inf else R.fmt_time(v, s)
            cost = ('n/a' if f_ <= -np.inf else 'LOSES IT' if c_ <= -np.inf else f'{(f_ - c_) / 3600:.1f} h')
            print(f'  {R.stop_name[s][:34]:34s} {fmt(f_):>10s} {fmt(c_):>10s} {cost:>10s}')
        print()

    print('Read it as: "cost" is how many hours earlier you must be at that stop to still collect the '
          'states without using the withheld ones. LOSES IT means the states become uncollectable from '
          'there at any time, which is the strong form of the claim.')


if __name__ == '__main__':
    main()
