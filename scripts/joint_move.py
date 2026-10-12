"""Joint re-insertion: pull a set of states out of a route and put them back anywhere, together.

The local search relocates one target at a time, so a day held by several states jointly (the blocker
finder's pairs and triples) is invisible to it. This removes the whole set, then re-inserts each state
(as the state or one of its gateway stops) at its best position, for every insertion order, and polishes
with single relocations.

  python3 joint_move.py --route ../out/res_denverV7c.pkl --start Pasco --at 2026-11-05T12:00 \
      --tz America/Los_Angeles --states AL,FL,MS,AR [--out ../out/joint_x.pkl]
"""
import argparse, itertools, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds
from time_search import Search
from blocker_finder import expand, label
from common import ABBR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', required=True); ap.add_argument('--start', required=True)
    ap.add_argument('--at', required=True); ap.add_argument('--tz', required=True)
    ap.add_argument('--states', required=True); ap.add_argument('--days', type=int, default=16)
    ap.add_argument('--out')
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
    R = TimeRouter(load_feeds(), datetime.fromisoformat(a.at).date(), a.days)
    start = R.stops_matching(a.start)[0]; S = Search(R, start, t0, [], 1)
    inv = {v: k for k, v in ABBR.items()}
    move = [R.state_names.index(inv[x.strip()]) for x in a.states.split(',')]
    saved = pickle.load(open(a.route, 'rb'))
    order = saved['order']; f, legs = S.evaluate(order)
    if not S.all_states(legs):   # data changed since the search: put the missing states back where they cost least
        import time_search as ts
        ts._R, ts._START, ts._T0, ts._BASE, ts._SELF = R, start, t0, None, S
        order, f, legs = S.repair(order, None); print('repaired, all states:', S.all_states(legs))
    order = expand(R, S, order, legs)
    fin = lambda o: R.finish(start, t0, o) or float('inf')
    hrs = lambda f: (f - t0) / 3600
    f0 = fin(order); print(f'base {hrs(f0):.1f} h', flush=True)
    opts = {s: [s] + S.gateways.get(s, []) for s in move}
    base = [x for x in order if x not in move]
    best = (f0, order)
    for perm in itertools.permutations(move):
        o = list(base)
        for s in perm:
            cands = [(fin(o[:j] + [g] + o[j:]), j, g) for j in range(len(o) + 1) for g in opts[s]]
            fj, j, g = min(cands, key=lambda c: (c[0], c[1])); o = o[:j] + [g] + o[j:]
        # polish: relocate each moved item anywhere, until no gain
        improved = True
        while improved:
            improved = False; cur = fin(o)
            for g in [x for x in o if x in move or (isinstance(x, str) and x.startswith('@~'))]:
                i = o.index(g); rest = o[:i] + o[i + 1:]
                fj, j = min((fin(rest[:j] + [g] + rest[j:]), j) for j in range(len(rest) + 1))
                if fj < cur - 60: o = rest[:j] + [g] + rest[j:]; cur = fj; improved = True
        fo = fin(o)
        print(f'  {"-".join(ABBR[R.state_names[s]] for s in perm)}: {hrs(fo):.1f} h', flush=True)
        if fo < best[0]: best = (fo, o)
    fb, ob = best
    print(f'\nBEST {hrs(fb):.1f} h (base {hrs(f0):.1f} h, gain {hrs(f0) - hrs(fb):.1f} h)')
    fr, lg = S.evaluate(ob)
    print('all states:', S.all_states(lg)); print(R.describe(lg))
    if a.out: pickle.dump(dict(order=ob, finish=fr, legs=lg), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
