"""Local search over the state order using real timetables as the objective.

usage: python3 time_search.py --start Missoula --at 2026-09-21T07:00 --tz America/Denver \
         --seed ../out/start_newton.pkl [--prefix "Idaho,Washington"] --budget 900 --workers 8 --out ../out/time_best.pkl
"""
import argparse, json, os, pickle, random, time, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES

_R = None; _START = None; _T0 = None; _BASE = None; _SELF = None


TIE_W = 0.02   # weight of the mean per-state arrival: breaks ties between equal finishes so partial savings
               # (reaching a once-daily departure with more slack) count and the search can climb toward it

def _finish(order):
    f, m = _R.finish(_START, _T0, order, _BASE, profile=True)
    return f + TIE_W * (m - _T0) if f is not None else float('inf')

def _drop_eval(order):
    """Worker side of prune: finish time and whether the route still covers every state."""
    f, legs = _SELF.evaluate(order)
    return f, (f != float('inf') and _SELF.all_states(legs))


class Search:
    def __init__(self, R, start, t0, prefix, workers, done=(), start_opts=()):
        self.R = R; self.start = start; self.t0 = t0; self.workers = workers
        self.start_opts = [start] + [x for x in start_opts if x != start]   # stops the start may move to
        self.day0 = t0   # start windows are [day0 + k days, +24 h)
        self.patience = 0   # seconds without a new best before stopping early (0 = use the whole budget)
        self.done = set(done)   # states already collected before the start
        self.prefix = []
        for p in prefix:
            self.prefix.append(p if p.startswith('@') else R.state_names.index(p))
        self.P = len(self.prefix)
        self.sticky = set()        # pins from the seed; gateway pins the search adds may be dropped again
        self.gateways = self.build_gateways()

    # ---- live progress for out/live/index.html (never allowed to break the search) ----
    LIVE_PATH = os.environ.get('BUS48_LIVE', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'out', 'live', 'live.json'))

    def legs_json(self, legs):
        R = self.R; out = []
        for l in legs:
            if l[0] not in ('ride', 'walk'): continue
            if l[0] == 'ride': _, trip, a, t0, b, t1 = l; ag, rt, hs = R.trip_info[(trip[0], trip[1])]; how = f'{ag}: {rt or hs}'
            else: _, a, b, t0, t1 = l; how = 'walk / local'
            out.append(dict(kind=l[0], a=[*map(float, R.stop_xy[a]), R.stop_name[a]], b=[*map(float, R.stop_xy[b]), R.stop_name[b]],
                            dep=R.fmt_time(t0, a), arr=R.fmt_time(t1, b) if t1 else '', how=how[:70]))
        return out

    def live(self, force=False, note=None, **kw):
        try:
            L = self.__dict__.setdefault('_live', dict(started=time.time(), evals=0, kick=0, history=[], log=[], best_h=None, current_h=None))
            L.update(kw)
            if note: L['log'] = (L['log'] + [[round(time.time() - L['started']), note]])[-14:]
            if not force and time.time() - self.__dict__.get('_live_t', 0) < 2: return
            self._live_t = time.time(); L['now'] = time.time()
            os.makedirs(os.path.dirname(self.LIVE_PATH), exist_ok=True)
            tmp = self.LIVE_PATH + '.tmp'; json.dump(L, open(tmp, 'w')); os.replace(tmp, self.LIVE_PATH)
        except Exception as e:
            print('live view error (ignored):', e, flush=True)

    def live_point(self, current_h=None, best_h=None):
        L = self.__dict__.get('_live')
        if L is None: return
        if current_h is not None: L['current_h'] = current_h
        if best_h is not None: L['best_h'] = best_h
        L['history'] = (L['history'] + [[round(time.time() - L['started'], 1), L.get('best_h'), L.get('current_h')]])[-3000:]

    def build_gateways(self, per_state=5, sep_km=60, radius_km=6):
        """Busiest stop clusters per state, as '@~lon,lat,km' targets. Replacing a state with one of its
        gateways lets the search collect the state somewhere other than the earliest stop it can reach
        (Mobile instead of Tuscaloosa, the Memphis walk-in instead of Jackson at 3 AM)."""
        R = self.R; xy = np.asarray(R.stop_xy, dtype=float)
        deps = np.bincount(R.cfrom, minlength=R.N)
        out = {}; busiest = [i for i in np.argsort(-deps) if deps[i] > 0]
        for s in range(N_STATES):
            idx = [i for i in busiest if R.state[i] == s]
            picks = []
            for i in idx:
                lon, lat = xy[i]
                if all(np.hypot((lon - a) * 111.3 * np.cos(np.radians(lat)), (lat - b) * 111.3) > sep_km for a, b in picks):
                    picks.append((lon, lat))
                if len(picks) >= per_state: break
            out[s] = [f'@~{a:.4f},{b:.4f},{radius_km}' for a, b in picks]
        return out

    def covered(self, legs):
        """States with an alighting-capable stop anywhere along the ridden trips."""
        seen = set()
        for l in legs:
            if l[0] == 'walk' and l[2] >= self.R.first_virtual: seen.add(int(self.R.state[l[2]]))   # border walk-in
            if l[0] != 'ride': continue
            _, trip, bs, bt, al, at = l
            fi, tid, _ = trip; f = self.R.feeds[fi]; t = f.trips[tid]
            ids = [self.R.idx[f.stops[s[1]][0]] for s in t['stops']]
            if bs in ids and al in ids:
                i, j = ids.index(bs), ids.index(al)
                for k in ids[min(i, j):max(i, j) + 1]:
                    if self.R.state[k] >= 0: seen.add(int(self.R.state[k]))
        return seen

    def evaluate(self, order):
        f, legs = self.R.route(self.start, self.t0, order)
        if f is None: return float('inf'), [l for l in legs if l[0] != 'unreachable']
        return f, legs

    def prune(self, order, pool=None):
        """Drop states the route covers in passing. All single drops are tried at once (in the pool when
        there is one) and the best harmless one is taken, instead of re-routing them one by one."""
        f, legs = self.evaluate(order)
        if f == float('inf'): return order, f, legs
        while len(order) > self.P:
            cands = [order[:j] + order[j + 1:] for j in range(self.P, len(order))]
            res = pool.map(_drop_eval, cands) if pool else [_drop_eval(o) for o in cands]
            ok = [(r[0], k) for k, r in enumerate(res) if r[1] and r[0] <= f and order[self.P + k] not in self.sticky]   # seed pins stay
            if not ok: break
            f2, k = min(ok)
            x = order[self.P + k]
            print('  drop', x if isinstance(x, str) else self.R.state_names[x], '->', round((f2 - self.t0) / 3600, 1), 'h')
            order = cands[k]; f = f2
        f, legs = self.evaluate(order)
        return order, f, legs

    def _base_cov(self, legs):
        s = int(self.R.state[self.start])   # -1 when the start stop lies outside every state
        return self.covered(legs) | self.done | ({s} if s >= 0 else set())

    def all_states(self, legs):
        return len(self._base_cov(legs)) >= N_STATES

    def missing(self, legs):
        cov = self._base_cov(legs)
        return [s for s in range(N_STATES) if s not in cov]

    def repair(self, order, pool):
        """Insert each missing state at the position that finishes earliest."""
        f, legs = self.evaluate(order)
        for m in self.missing(legs):
            cands = [order[:j] + [m] + order[j:] for j in range(self.P, len(order) + 1)]
            fs = pool.map(_finish, cands) if pool else [_finish(o) for o in cands]
            j = int(np.argmin(fs)); order = cands[j]
        f, legs = self.evaluate(order)
        return order, f, legs

    def moves(self, order):
        n = len(order); P = self.P; out = []
        for i in range(P, n):
            seg = order[i:i + 1]; rest = order[:i] + order[i + 1:]
            for j in range(P, n):                            # relocate anywhere (whole-route moves like GA from Savannah to Atlanta)
                if j != i: out.append(rest[:j] + seg + rest[j:])
        for i in range(P, n - 1):
            for j in range(i + 2, min(n, i + 6) + 1):        # reverse segments of up to 6
                out.append(order[:i] + order[i:j][::-1] + order[j:])
        for i in range(P, n):                                # collect a state at one of its gateways instead
            x = order[i]
            gws = self.gateways.get(x, []) if not isinstance(x, str) else \
                  next((g for g in self.gateways.values() if x in g), [])
            for g in gws:
                if g != x: out.append(order[:i] + [g] + order[i + 1:])
        return out

    def pool_for(self, order, pool):
        """Cache the incumbent's layer labels and fork a fresh pool so workers inherit them."""
        global _BASE
        self.R.route(self.start, self.t0, order); _BASE = (list(order), self.R.last_outs)
        if self.workers <= 1: return None
        if pool: pool.close(); pool.join()
        import multiprocessing as mp
        return mp.get_context('fork').Pool(self.workers)

    def descend(self, order, f, legs, deadline, pool):
        """First-improvement local search from (order, f, legs) until no move helps or time is up.
        Moves are compared on the tie-broken score (_finish), so equal finishes with earlier states still count."""
        improved = True; it = 0; sc = _finish(order)
        while improved and time.time() < deadline:
            improved = False
            cands = self.moves(order); random.shuffle(cands)
            batch = max(1, self.workers * 2)
            for i in range(0, len(cands), batch):
                if time.time() > deadline: break
                chunk = cands[i:i + batch]
                fs = pool.map(_finish, chunk) if pool else [_finish(o) for o in chunk]
                it += len(chunk); j = int(np.argmin(fs))
                self.live(evals=self.__dict__.get('_live', {}).get('evals', 0) + len(chunk), phase='descending')
                if fs[j] < sc - 60:
                    o2, f2, l2 = self.repair(chunk[j], pool)
                    s2 = _finish(o2)
                    if s2 < sc - 60 and f2 <= f + 60 and self.all_states(l2):
                        order, f, legs, sc = o2, f2, l2, s2; improved = True
                        print('  improve', round((f - self.t0) / 3600, 1), 'h after', it, 'evals', flush=True)
                        self.live_point(current_h=round((f - self.t0) / 3600, 2))
                        self.live(force=True, current=self.legs_json(legs), note=f'improve: {(f - self.t0) / 3600:.1f} h (from window start)'); break
            if improved:
                order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool); sc = _finish(order)
        return order, f, legs, pool

    def latest_start(self, start, t_lo, order, span=24 * 3600, step=600):
        """Latest clock in [t_lo, t_lo + span) that still finishes as early as leaving at t_lo. Finish is
        non-decreasing in the start clock (timetables are FIFO), so a binary search over 10-min steps works."""
        f0 = self.R.finish(start, t_lo, order)
        if f0 is None: return None
        lo, hi = 0, int(span // step) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            f = self.R.finish(start, t_lo + mid * step, order)
            if f is not None and f <= f0 + 60: lo = mid
            else: hi = mid - 1
        return t_lo + lo * step

    def settle(self, order):
        """Best start for this order over start stops x 7 start days, each at its latest clock.
        Scored on hours from the first bus boarded to the finish. Returns (elapsed, stop, window start, finish, legs):
        the search keeps running from the window start so later moves may still use an earlier first bus."""
        R = self.R; best = None
        for st in self.start_opts:
            for k in range(7):
                t_lo = self.day0 + k * 86400
                t = self.latest_start(st, t_lo, order)
                if t is None: continue
                f, legs = R.route(st, t, order)
                if f is None: continue
                s0 = int(R.state[st])
                if len(self.covered(legs) | self.done | ({s0} if s0 >= 0 else set())) < N_STATES: continue
                first = next((l[3] for l in legs if l[0] == 'ride'), t)
                if best is None or f - first < best[0] - 60: best = (f - first, st, t_lo, f, legs)
        return best

    def set_start(self, st, t, order, pool):
        global _START, _T0
        self.start, self.t0 = st, t; _START, _T0 = st, t
        return self.pool_for(order, pool)

    def adopt(self, order, pool):
        """Move the search to the best start for this order. Returns (elapsed, finish, legs, pool)."""
        b = self.settle(order)
        if b is None:
            f, legs = self.evaluate(order); return float('inf'), f, legs, pool
        el, st, t, f, legs = b
        if (st, t) != (self.start, self.t0):
            first = next((l[3] for l in legs if l[0] == 'ride'), t)
            print(f'  start -> {self.R.stop_name[st]}, first bus {self.R.fmt_time(first, st)}: {el / 3600:.1f} h', flush=True)
            self.live(note=f'start moved: {self.R.stop_name[st]}, first bus {self.R.fmt_time(first, st)}')
            pool = self.set_start(st, t, order, pool)
        return el, f, legs, pool

    def perturb(self, order, k=3):
        """Relocate k random states (after the prefix) to random positions."""
        o = list(order)
        for _ in range(k):
            i = random.randrange(self.P, len(o)); x = o.pop(i)
            o.insert(random.randrange(self.P, len(o) + 1), x)
        return o

    def run(self, order, budget):
        global _R, _START, _T0, _SELF
        _R, _START, _T0, _SELF = self.R, self.start, self.t0, self
        order = self.prefix + [x for x in order if x not in self.prefix]
        self.sticky = {x for x in order if isinstance(x, str)}
        pool = self.pool_for(order, None)
        f, legs = self.evaluate(order)
        if not self.all_states(legs):
            print('seed misses', [self.R.state_names[s] for s in self.missing(legs)]); order, f, legs = self.repair(order, pool)
            pool = self.pool_for(order, pool)
        order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool)   # drop states the seed already covers in passing
        print('start', round((f - self.t0) / 3600, 1), 'h, order', len(order), flush=True)
        self.live_point(current_h=round((f - self.t0) / 3600, 2))
        self.live(force=True, budget=budget, phase='starting', current=self.legs_json(legs), note=f'seed: {(f - self.t0) / 3600:.1f} h')
        deadline = time.time() + budget
        order, f, legs, pool = self.descend(order, f, legs, deadline, pool)
        el, f, legs, pool = self.adopt(order, pool)
        print('settled', round(el / 3600, 1), 'h from first bus', flush=True)
        self.live_point(best_h=round(el / 3600, 2))
        self.live(force=True, best=self.legs_json(legs), start=self.R.stop_name[self.start], note=f'first best: {el / 3600:.1f} h from first bus')
        best = (order, f, legs, el, self.start, self.t0); kick = 0; last_gain = time.time()
        while time.time() < deadline:      # iterated local search: kick the incumbent, descend, keep if better
            if self.patience and time.time() - last_gain > self.patience:
                print(f'converged: no new best for {self.patience:.0f} s, stopping early', flush=True)
                self.live(note='converged, stopping early'); break
            kick += 1
            if (self.start, self.t0) != best[4:6]: pool = self.set_start(best[4], best[5], best[0], pool)
            o2 = self.perturb(best[0], 2 + kick % 3)
            o2, f2, l2 = self.repair(o2, pool)
            if not self.all_states(l2): continue
            pool = self.pool_for(o2, pool)
            print('kick', kick, 'from', round((f2 - self.t0) / 3600, 1), 'h', flush=True)
            self.live_point(current_h=round((f2 - self.t0) / 3600, 2))
            self.live(force=True, kick=kick, phase='kicked', current=self.legs_json(l2), note=f'kick {kick}: shake up, restart at {(f2 - self.t0) / 3600:.1f} h')
            o2, f2, l2, pool = self.descend(o2, f2, l2, deadline, pool)
            e2, f2, l2, pool = self.adopt(o2, pool)
            if e2 < best[3] - 60 or (e2 <= best[3] + 60 and f2 <= best[1] + 60 and _finish(o2) < _finish(best[0]) - 60):
                best = (o2, f2, l2, e2, self.start, self.t0); last_gain = time.time()
                print('  new best', round(e2 / 3600, 1), 'h from first bus', flush=True)
                self.live_point(best_h=round(e2 / 3600, 2))
                self.live(force=True, best=self.legs_json(l2), start=self.R.stop_name[self.start], note=f'NEW BEST {e2 / 3600:.1f} h')
        if pool: pool.close()
        self.live(force=True, phase='done', note=f'done: best {best[3] / 3600:.1f} h')
        self.start, self.t0 = best[4], best[5]
        self.best_elapsed = best[3]
        return best[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True); ap.add_argument('--at', required=True); ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--seed', help='result pickle'); ap.add_argument('--seed-states', help='comma list of state abbreviations (or @stop pins) in visiting order'); ap.add_argument('--prefix', default='')
    ap.add_argument('--budget', type=float, default=900); ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True)
    ap.add_argument('--done', default='', help='comma list of state abbreviations already collected before --start')
    ap.add_argument('--seed-pins', action='store_true', help='keep the seed pickle\'s @stop pins (by default only states are kept)')
    ap.add_argument('--patience', type=float, default=0, help='stop early after this many seconds without a new best')
    ap.add_argument('--start-alt', default='', help='semicolon list of other stops the start may move to (each tried on 7 days, latest clock)')
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), t0.date(), a.days)
    start = R.stops_matching(a.start)[0]
    from common import ABBR
    inv = {v: k for k, v in ABBR.items()}
    done = [R.state_names.index(inv[x.strip()]) for x in a.done.split(',') if x.strip()]
    if a.seed_states:
        # '@stop' items are pins (e.g. '@Las Vegas Amtrak Station' to leave the Chief for the Denver bus)
        seed = [x.strip() if x.strip().startswith('@') else R.state_names.index(inv[x.strip()]) for x in a.seed_states.split(',')]
    else:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order']
                if (isinstance(x, (int, np.integer)) and x < N_STATES) or (a.seed_pins and isinstance(x, str) and x.startswith('@'))]
    seed = [x for x in seed if x not in done]
    alts = [R.stops_matching(q.strip())[0] for q in a.start_alt.split(';') if q.strip()]
    S = Search(R, start, t0.timestamp(), [x.strip() for x in a.prefix.split(',') if x.strip()], a.workers, done, alts)
    S.patience = a.patience
    S.live(force=True, name=os.path.basename(a.out).replace('.pkl', ''), phase='loading')
    order, f, legs = S.run(seed, a.budget)
    if f == float('inf'): print('FINAL unreachable'); return
    # FINAL is hours from the first bus boarded to the finish (the start clock is chosen by the search)
    print('FINAL', round(S.best_elapsed / 3600, 1), 'h', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]))
    first = next(l for l in legs if l[0] == 'ride')
    print('START', R.stop_name[S.start], 'first bus', R.fmt_time(first[3], first[2]))
    print(' > '.join(R.state_names[x] if isinstance(x, int) else x for x in order))
    print(R.describe(legs))
    pickle.dump(dict(order=order, finish=f, legs=legs, start=R.stop_name[S.start], t0=S.t0, elapsed=S.best_elapsed), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
