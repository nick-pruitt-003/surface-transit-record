"""Build 48-state routes from the end backwards (Nick: plan from the end time, then find the start that makes it).

For an end state and a deadline: a reverse Connection Scan from every stop of the end state gives, for each
unvisited state, the latest time you could be there and still arrive in time. Pick the one reachable latest
(states the route already passes through are nearly free, so they go first), then scan back from that state's
stops, and repeat until all 48 are placed. The last state picked is the start; its latest time is the start you
need. Several deadlines across the week and a few randomized builds (top-3 choice) are tried; every build is
checked forward, and the best are saved as seeds (built for this end, not borrowed from another route).

  python3 build_backward.py --end CA --from 2026-09-26T00:00 --tz America/Los_Angeles [--step 6] [--tries 3]
"""
import argparse, json, os, pickle, random, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import time_router as tr
from time_router import TimeRouter, load_feeds, N_STATES, MIN_TRANSFER
import time_search as ts
from time_search import Search, FREE
import backward as B
from common import ABBR

WINDOWS = (30, 60, 110)
STRAND_KMH = 70   # leftover-work estimate: each unvisited state's distance to its nearest unvisited neighbour, at this speed


def strand_cost(left, here, dist):
    """Seconds of work the unvisited states still imply. A state whose neighbours are all gone (Maine once NH and
    MA are placed) has to be reached from far away, so chains that strand it score worse."""
    pool = set(left) | {here}
    return sum(min(dist[x][y] for y in pool if y != x) for x in left) / STRAND_KMH * 3600   # hours to scan back per step, widened when no unvisited state is reachable


def live_write(R, name, phase, chains, note, best_h=None):
    """Draw the partial backward chains in the live viewer (out/live): best chain red, the others grey."""
    def legs(stops):
        return [dict(kind='ride', a=[*map(float, R.stop_xy[a]), R.stop_name[a]], b=[*map(float, R.stop_xy[b]), R.stop_name[b]],
                     dep='', arr='', how='backward pick') for a, b in zip(stops[1:], stops[:-1])]
    try:
        L = live_write.__dict__.setdefault('L', dict(started=time.time(), evals=0, kick=0, history=[], log=[], budget=0))
        L.update(name=name, phase=phase, now=time.time(), best=legs(chains[0]) if chains else [],
                 current=legs(chains[1]) if len(chains) > 1 else [], best_h=best_h, current_h=None, trying=[], trying_note=note)
        if note: L['log'] = (L['log'] + [[round(time.time() - L['started']), note]])[-14:]
        path = ts.Search.LIVE_PATH; tmp = path + '.tmp'; json.dump(L, open(tmp, 'w')); os.replace(tmp, path)
    except Exception as e: print('live view error (ignored):', e)


def build(R, rev, state_stops, end, D, rng, topk, beam=6, label='', dist=None, near=2):
    """Beam search backwards. A node: states picked (end first), states left, and the latest time at each stop
    of the last state (plus through vehicles there). Each step every node scans back once; its top-k unvisited
    states (latest reachable first) become children; the beam keeps the nodes that are latest overall (least
    time used so far). Returns (order start..end, states nothing could reach)."""
    NEG = float('-inf')
    root = dict(picked=[end], left=set(range(N_STATES)) - {end}, cur={s: D for s in state_stops[end]}, stay={},
                pin=[max(state_stops[end], key=lambda s: 0)])
    nodes = [root]; step = 0
    while nodes[0]['left']:
        step += 1; t_step = time.time(); children = []
        for nd in nodes:
            hi = max(nd['cur'].values()); cands = []
            for W in WINDOWS:
                latest, stay = B.backward_layer(R, rev, nd['cur'], True, hi - W * 3600, nd['stay'], None)
                for x in nd['left']:
                    best_v, best_s = NEG, None
                    for s in state_stops[x]:
                        v = max([latest[s]] + list(stay.get(s, {}).values()))
                        if v > best_v: best_v, best_s = v, s
                    if best_v > NEG: cands.append((best_v, x, best_s))
                if cands: break
            if not cands: children.append(dict(nd, stuck=True)); continue
            cands.sort(reverse=True)
            pick = cands[:topk]
            here = nd['picked'][-1]   # plus the nearest unvisited states, so 'grab Maine now' is always tried
            for c in sorted(cands, key=lambda c: dist[here][c[1]])[:near]:
                if c not in pick: pick.append(c)
            for v, x, s_best in pick:
                cur = {s: max([latest[s]] + list(stay.get(s, {}).values())) for s in state_stops[x]}
                cur = {s: t for s, t in cur.items() if t > NEG}
                children.append(dict(picked=nd['picked'] + [x], left=nd['left'] - {x}, cur=cur,
                                     stay={s: stay[s] for s in cur if s in stay}, pin=nd['pin'] + [s_best]))
        live = [c for c in children if not c.get('stuck')]
        if not live: nodes = [children[0]]; break
        seen = set(); nodes = []
        for c in live: c['score'] = max(c['cur'].values()) - strand_cost(c['left'], c['picked'][-1], dist)
        for c in sorted(live, key=lambda c: -c['score']):
            key = (frozenset(c['left']), c['picked'][-1])
            if key in seen: continue
            seen.add(key); nodes.append(c)
            if len(nodes) >= beam: break
        b0 = nodes[0]; t_b = max(b0['cur'].values()); s_b = b0['pin'][-1]
        tail = ' < '.join(ABBR[R.state_names[x]] for x in b0['picked'][-4:])
        msg = (f'{label} step {step}: ...{tail} | at {R.stop_name[s_b][:24]} {R.fmt_time(t_b, s_b)} '
               f'({(D - t_b) / 3600:.1f} h back, leftover est {strand_cost(b0["left"], b0["picked"][-1], dist) / 3600:.0f} h, {len(b0["left"])} left, {time.time() - t_step:.1f} s)')
        print('   ', msg, flush=True)
        live_write(R, f'build back: {label}', 'building', [n['pin'] for n in nodes[:2]], msg, round((D - t_b) / 3600, 1))
    nd = nodes[0]
    return nd['picked'][::-1], sorted(nd['left'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end', required=True, help='end state abbreviation, e.g. CA')
    ap.add_argument('--from', dest='frm', required=True, help='first deadline to try (ISO, --tz); deadlines run for 7 days from it')
    ap.add_argument('--tz', default='America/New_York'); ap.add_argument('--step', type=float, default=6, help='hours between deadlines')
    ap.add_argument('--tries', type=int, default=1, help='builds per deadline: 1 greedy + randomized top-3')
    ap.add_argument('--beam', type=int, default=6, help='partial chains kept per step')
    ap.add_argument('--keep', type=int, default=3, help='save this many best builds as seeds')
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True, help='prefix for the seed pickles')
    a = ap.parse_args()
    inv = {v: k for k, v in ABBR.items()}
    D0 = datetime.fromisoformat(a.frm).replace(tzinfo=ZoneInfo(a.tz))
    # the router's calendar must cover ~11 days before the earliest deadline through the last one
    R = TimeRouter(load_feeds(), (D0 - timedelta(days=12)).date(), a.days)
    end = R.state_names.index(inv[a.end])
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    rev = [[] for _ in range(R.N)]
    for i in range(R.N):
        for j, w in R.foot.get(i, ()): rev[j].append((i, w))
    rng = random.Random(48); results = []; t_run = time.time()
    n_dl = int(7 * 24 / a.step)
    for di in range(n_dl):
        D = (D0 + timedelta(hours=di * a.step)).timestamp()
        for tri in range(a.tries):
            order, left = build(R, rev, state_stops, end, D, rng, 3, a.beam, f'{a.end} deadline {di + 1}/{n_dl}', dist)
            print('    checking forward: insert leftovers, drop passing states, pick the start day and clock', flush=True)
            # forward: free start in the order's first state, end fixed; insert leftovers at their cheapest
            # spot, drop states covered in passing, then pick the start day and latest clock
            S = Search(R, FREE, D - 12 * 86400, [], 1, end=end)
            ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, FREE, S.t0, S, None, end
            S.sticky = {end}
            order, f, legs = S.repair(order, None)
            if f < float('inf') and S.all_states(legs): order, f, legs = S.prune(order, None)
            b = S.settle(order)
            tag = f'  deadline {R.fmt_time(D, state_stops[end][0])} try {tri}: backward placed {48 - len(left)}' + (f' (inserted {",".join(ABBR[R.state_names[x]] for x in left)})' if left else '')
            if b is None: print(tag, '-> no valid start', flush=True); continue
            el, st, t_lo, f, legs = b
            first = next(l for l in legs if l[0] == 'ride')
            results.append((el / 3600, order, t_lo, first[2], D, f))
            print(tag, f'-> {el / 3600:.1f} h, first bus {R.stop_name[first[2]][:28]} {R.fmt_time(first[3], first[2])}, finish {R.fmt_time(f, state_stops[end][0])}', flush=True)
    results.sort(key=lambda r: r[0])
    print(f'\nBEST ({len(results)} builds, {time.time() - t_run:.0f} s)')
    for i, (el, order, t_start, s_start, D, f) in enumerate(results[:a.keep]):
        print(f'  #{i + 1} {el:.1f} h  start {R.stop_name[s_start]}  '
              + ' > '.join(ABBR[R.state_names[x]] for x in order))
        pickle.dump(dict(order=order, t0=t_start, start=R.stop_name[s_start], elapsed=el * 3600, deadline=D, finish=f),
                    open(f'{a.out}_{i + 1}.pkl', 'wb'))


if __name__ == '__main__':
    main()
