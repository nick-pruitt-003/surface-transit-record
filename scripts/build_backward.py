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
STRAND_KMH = 70
STRAND_W = 1.0   # weight on the timetable leftover estimate (hours of spanning tree)   # leftover-work estimate: each unvisited state's distance to its nearest unvisited neighbour, at this speed


def strand_cost(left, here, dist):
    """Seconds of work the unvisited states still imply: a minimum spanning tree over them plus the current state
    (km at STRAND_KMH). A cluster left behind (NH + ME once MA and VT are placed) pays for the long edge that
    joins it back, which a nearest-neighbour sum missed because NH and ME are each other's neighbours."""
    nodes = [here] + list(left)
    if len(nodes) < 2: return 0.0
    M = dist['T'][np.ix_(nodes, nodes)] * 3600 * STRAND_W if 'T' in dist else dist['M'][np.ix_(nodes, nodes)] / STRAND_KMH * 3600
    inside = np.zeros(len(nodes), bool); inside[0] = True; best = M[0].copy(); total = 0.0
    for _ in range(len(nodes) - 1):
        best[inside] = np.inf; j = int(np.argmin(best)); total += best[j]; inside[j] = True
        best = np.minimum(best, M[j])
    return total


def state_times(R, F, state_stops, D0, cache):
    """Typical hours from each state to each other state on the real timetables: for 8 deadlines across the week,
    a reverse scan from every stop of y gives the latest you can leave each state x and still be in y; hours =
    deadline - that, median over the deadlines (so waits for once-a-day departures count). Cached.

    Border walk-in points are left out of both ends. They are real ways to cross a state line, but a pair of them
    sits either side of the same line, so counting them makes neighbouring states 0.0 h apart: before this, the
    cheapest hop into most states was under 1 h and into several exactly 0, and a spanning tree over 28 states
    came to 45 h. That tree was measuring which states touch, not what it takes to travel between them, and it
    scored two chains the same however differently their remaining states were placed."""
    state_stops = {x: [i for i in state_stops[x] if i < R.first_virtual] or state_stops[x] for x in state_stops}
    if os.path.exists(cache): return np.load(cache)
    T = np.full((N_STATES, N_STATES, 8), np.nan); t0 = time.time()
    st_arr = {x: np.array(state_stops[x], dtype=np.int64) for x in state_stops}
    for y in range(N_STATES):
        for k in range(8):
            D = D0 + k * 21 * 3600   # 21 h apart: covers every time of day over the week
            L, ok, k0, k1 = F.layer({int(s): D for s in state_stops[y]}, True, D - 96 * 3600, None)
            eff, _ = F.through(ok, k0, k1, np.ones(R.N, bool)); vals = np.maximum(L, eff)
            for x in range(N_STATES):
                v = vals[st_arr[x]].max()
                if v > -np.inf: T[x, y, k] = (D - v) / 3600
        print(f'  state times: {y + 1}/48 ({time.time() - t0:.0f} s)', flush=True)
    T = np.nanmedian(np.where(np.isnan(T), 96.0, T), axis=2); np.fill_diagonal(T, 0)
    T = np.minimum(T, T.T)   # undirected for the spanning tree
    np.save(cache, T); return T


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


def build(R, F, state_stops, end, D, rng, topk, beam=30, label='', dist=None, near=2, oracle=None, dump=None, root=None, quiet=False):
    """Beam search backwards (C reverse scan). A node: states picked (end first), states left, the latest time at
    each stop of the last state, and its through vehicles (staying aboard needs no transfer). Each step every node
    scans back once; its top-k unvisited states by latest time plus the `near` closest ones become children; the
    beam keeps the children with the best score = latest time minus the leftover-work estimate (strand_cost).
    Returns (order start..end, states nothing could reach)."""
    NEG = -np.inf; st_arr = {x: np.array(state_stops[x], dtype=np.int64) for x in state_stops}
    def sparse(ns):
        idx = np.nonzero(ns[0] >= 0)[0]; return idx, ns[0][idx], ns[1][idx]
    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep
    nodes = [root] if root is not None else [dict(picked=[end], left=set(range(N_STATES)) - {end}, cur={int(s): D for s in state_stops[end]}, ns=None,
                  pin=[state_stops[end][0]])]
    step = 0
    def expand(nd, only=None):
        """Children of a node: (candidates sorted by latest time, picked children). only=x: just that state."""
        hi = max(nd['cur'].values()); cands = []
        for W in WINDOWS:
            L, ok, k0, k1 = F.layer(nd['cur'], True, hi - W * 3600, dense(nd['ns']))
            mask = np.zeros(R.N, bool)
            for x in nd['left']: mask[st_arr[x]] = True
            eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
            for x in nd['left']:
                v = vals[st_arr[x]]; i = int(np.argmax(v))
                if v[i] > NEG: cands.append((float(v[i]), x, int(st_arr[x][i])))
            if cands: break
        cands.sort(reverse=True)
        if only is not None: pick = [c for c in cands if c[1] == only]
        else:
            pick = cands[:topk]; here = nd['picked'][-1]
            for c in sorted(cands, key=lambda c: dist[here][c[1]])[:near]:   # 'grab Maine while you're here'
                if c not in pick: pick.append(c)
        kids = []
        for v, x, s_best in pick:
            xm = np.zeros(R.N, bool); xm[st_arr[x]] = True
            eff_x, ns_x = F.through(ok, k0, k1, xm)
            cur = {int(s): float(max(L[s], eff_x[s])) for s in st_arr[x] if max(L[s], eff_x[s]) > NEG}
            kid = dict(picked=nd['picked'] + [x], left=nd['left'] - {x}, cur=cur, ns=sparse(ns_x), pin=nd['pin'] + [s_best])
            kid['score'] = max(cur.values()) - strand_cost(kid['left'], x, dist); kids.append(kid)
        return cands, kids

    onode = nodes[0] if oracle else None
    while nodes[0]['left']:
        step += 1; t_step = time.time(); children = []
        for nd in nodes:
            cands, kids = expand(nd); children += kids
        if oracle and onode is not None and step < len(oracle):
            xo = oracle[step]
            ocands, okids = expand(onode, xo)
            rank = next((i + 1 for i, c in enumerate(ocands) if c[1] == xo), None)
            here = onode['picked'][-1]
            near_set = {c[1] for c in sorted(ocands, key=lambda c: dist[here][c[1]])[:near]}
            would_pick = rank is not None and (rank <= topk or xo in near_set)
            if okids:
                onode = okids[0]
                opending = (onode, rank, would_pick, xo)
            else:
                print(f'    ORACLE step {step}: {ABBR[R.state_names[xo]]} unreachable backwards from the oracle chain', flush=True); onode = None; opending = None
        else: opending = None
        if not children: break
        seen = set(); nodes = []
        for c in sorted(children, key=lambda c: -c['score']):
            key = (frozenset(c['left']), c['picked'][-1])
            if key in seen: continue
            seen.add(key); nodes.append(c)
            if len(nodes) >= beam: break
        if opending:
            on, rank, would_pick, xo = opending
            cut = nodes[-1]['score']; pos = 1 + sum(1 for c in nodes if c['score'] > on['score'])
            in_beam = any(set(c['picked']) == set(on['picked']) and c['picked'][-1] == on['picked'][-1] for c in nodes)   # same states placed, same current state
            print(f'    ORACLE step {step}: {ABBR[R.state_names[xo]]} time-rank {rank} {"considered" if would_pick else "NOT CONSIDERED"}, '
                  f'score {(on["score"] - cut) / 3600:+.1f} h vs beam cut (would rank {pos}/{len(nodes)}) -> {"in beam" if in_beam else "PRUNED"}', flush=True)
        if dump and step == dump[0]:   # diagnostics: save this step's beam and the reference chain, stop
            pickle.dump(dict(D=D, step=step, nodes=nodes[:20], oracle_node=onode, oracle=oracle), open(dump[1], 'wb'))
            print(f'    dumped step {step} to {dump[1]}'); raise SystemExit
        b0 = nodes[0]; t_b = max(b0['cur'].values()); s_b = b0['pin'][-1]
        tail = ' < '.join(ABBR[R.state_names[x]] for x in b0['picked'][-4:])
        msg = (f'{label} step {step}: ...{tail} | at {R.stop_name[s_b][:24]} {R.fmt_time(t_b, s_b)} '
               f'({(D - t_b) / 3600:.1f} h back, leftover est {strand_cost(b0["left"], b0["picked"][-1], dist) / 3600:.0f} h, '
               f'{len(b0["left"])} left, {len(nodes)} in beam, {time.time() - t_step:.1f} s)')
        if quiet: continue
        print('   ', msg, flush=True)
        live_write(R, f'build back: {label}', 'building', [n['pin'] for n in nodes[:2]], msg, round((D - t_b) / 3600, 1))
    nd = nodes[0]
    return nd['picked'][::-1], sorted(nd['left']), max(nd['cur'].values())


def visit_sequence(R, S, legs, start_stop):
    """States in the order a route first collects them (start state, then along every ride and walk-in)."""
    seq = []
    def add(x):
        if x >= 0 and x not in seq: seq.append(int(x))
    if start_stop is not None and start_stop >= 0: add(int(R.state[start_stop]))
    for l in legs:
        if l[0] == 'walk' and l[2] >= R.first_virtual: add(int(R.state[l[2]]))
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        fi, tid, _ = trip; f = R.feeds[fi]; t = f.trips[tid]
        ids = [R.idx[f.stops[x[1]][0]] for x in t['stops']]
        if bs in ids and al in ids:
            for k in ids[ids.index(bs):ids.index(al) + 1]: add(int(R.state[k]))
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--end', required=True, help='end state abbreviation, e.g. CA')
    ap.add_argument('--from', dest='frm', required=True, help='first deadline to try (ISO, --tz); deadlines run for 7 days from it')
    ap.add_argument('--tz', default='America/New_York'); ap.add_argument('--step', type=float, default=6, help='hours between deadlines')
    ap.add_argument('--tries', type=int, default=1, help='builds per deadline: 1 greedy + randomized top-3')
    ap.add_argument('--strand-kmh', type=float, default=70, help='speed for the leftover-work estimate (lower = weigh stranding more)')
    ap.add_argument('--beam', type=int, default=30, help='partial chains kept per step')
    ap.add_argument('--topk', type=int, default=3, help='states per node taken as children by latest time. The 237 '
                    'route needs its 6th-ranked state at one step (CO out of Kansas) and its 5th at another (WI '
                    'out of Wyoming), so 3 cannot rebuild it however wide the beam is.')
    ap.add_argument('--km-estimate', action='store_true', help='old leftover estimate: straight-line km at --strand-kmh')
    ap.add_argument('--strand-w', type=float, default=1.0, help='weight on the timetable leftover estimate')
    ap.add_argument('--dump-step', type=int, help='save the beam and the tracked chain at this step, then stop')
    ap.add_argument('--track', help='reference route pickle (e.g. the 237 result): report where the beam loses it')
    ap.add_argument('--keep', type=int, default=3, help='save this many best builds as seeds')
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True, help='prefix for the seed pickles')
    a = ap.parse_args()
    globals()['STRAND_KMH'] = a.strand_kmh; globals()['STRAND_W'] = a.strand_w
    inv = {v: k for k, v in ABBR.items()}
    D0 = datetime.fromisoformat(a.frm).replace(tzinfo=ZoneInfo(a.tz))
    # the router's calendar must cover ~11 days before the earliest deadline through the last one
    R = TimeRouter(load_feeds(), (D0 - timedelta(days=12)).date(), a.days)
    end = R.state_names.index(inv[a.end])
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    F = B.RevFast(R)
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    dist['M'] = np.array([[dist[x][y] for y in range(N_STATES)] for x in range(N_STATES)])
    if not a.km_estimate: dist['T'] = state_times(R, F, state_stops, D0.timestamp() - 7 * 86400, '../out/state_times_real.npy')
    rng = random.Random(48); results = []; t_run = time.time(); oracle = None
    if a.track:
        d = pickle.load(open(a.track, 'rb')); st0 = R.stop_name.index(d['start'])
        S0 = Search(R, st0, d['t0'], [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0, d['t0'], S0, None, None
        f0, l0 = S0.evaluate(d['order'])
        seq = visit_sequence(R, S0, l0, st0); oracle = seq[::-1]
        print('reference first visits:', ' > '.join(ABBR[R.state_names[x]] for x in seq), f'({len(seq)} states, finish {R.fmt_time(f0, st0)})')
        if oracle[0] != end: print('  reference does not end in', a.end); oracle = None
    n_dl = int(7 * 24 / a.step)
    for di in range(n_dl):
        D = (D0 + timedelta(hours=di * a.step)).timestamp()
        for tri in range(a.tries):
            order, left, _ = build(R, F, state_stops, end, D, rng, a.topk, a.beam, f'{a.end} deadline {di + 1}/{n_dl}', dist, oracle=oracle, dump=(a.dump_step, f'{a.out}_dump{a.dump_step}.pkl') if a.dump_step else None)
            print('    checking forward: insert leftovers, drop passing states, pick the start day and clock', flush=True)
            # forward: free start in the order's first state, end fixed; insert leftovers at their cheapest
            # spot, drop states covered in passing, then pick the start day and latest clock
            S = Search(R, FREE, D - 12 * 86400, [], 1, end=end)
            ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, FREE, S.t0, S, None, end
            S.sticky = {end, order[0]}   # free start lives in order[0]: pruning it would move the start and drop that state
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
