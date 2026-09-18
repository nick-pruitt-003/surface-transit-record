"""Local search over the state order using real timetables as the objective.

usage: python3 time_search.py --start Missoula --at 2026-09-21T07:00 --tz America/Denver \
         --seed ../out/start_newton.pkl [--prefix "Idaho,Washington"] --budget 900 --workers 8 --out ../out/time_best.pkl
"""
import argparse, pickle, random, time, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES

_R = None; _START = None; _T0 = None; _BASE = None; _SELF = None


def _finish(order):
    f = _R.finish(_START, _T0, order, _BASE)
    return f if f is not None else float('inf')

def _drop_eval(order):
    """Worker side of prune: finish time and whether the route still covers every state."""
    f, legs = _SELF.evaluate(order)
    return f, (f != float('inf') and _SELF.all_states(legs))


class Search:
    def __init__(self, R, start, t0, prefix, workers, done=()):
        self.R = R; self.start = start; self.t0 = t0; self.workers = workers
        self.done = set(done)   # states already collected before the start
        self.prefix = []
        for p in prefix:
            self.prefix.append(p if p.startswith('@') else R.state_names.index(p))
        self.P = len(self.prefix)

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
            ok = [(r[0], k) for k, r in enumerate(res) if r[1] and r[0] <= f]
            if not ok: break
            f2, k = min(ok)
            print('  drop', self.R.state_names[order[self.P + k]], '->', round((f2 - self.t0) / 3600, 1), 'h')
            order = cands[k]; f = f2
        f, legs = self.evaluate(order)
        return order, f, legs

    def all_states(self, legs):
        return len(self.covered(legs) | {int(self.R.state[self.start])} | self.done) >= N_STATES

    def missing(self, legs):
        cov = self.covered(legs) | {int(self.R.state[self.start])} | self.done
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
            for j in range(max(P, i - 8), min(n, i + 9)):   # relocate within 8 positions
                if j != i: out.append(rest[:j] + seg + rest[j:])
        for i in range(P, n - 1):
            for j in range(i + 2, min(n, i + 6) + 1):        # reverse segments of up to 6
                out.append(order[:i] + order[i:j][::-1] + order[j:])
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
        """First-improvement local search from (order, f, legs) until no move helps or time is up."""
        improved = True; it = 0
        while improved and time.time() < deadline:
            improved = False
            cands = self.moves(order); random.shuffle(cands)
            batch = max(1, self.workers * 2)
            for i in range(0, len(cands), batch):
                if time.time() > deadline: break
                chunk = cands[i:i + batch]
                fs = pool.map(_finish, chunk) if pool else [_finish(o) for o in chunk]
                it += len(chunk); j = int(np.argmin(fs))
                if fs[j] < f - 60:
                    o2, f2, l2 = self.repair(chunk[j], pool)
                    if f2 < f - 60 and self.all_states(l2):
                        order, f, legs = o2, f2, l2; improved = True
                        print('  improve', round((f - self.t0) / 3600, 1), 'h after', it, 'evals', flush=True); break
            if improved:
                order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool)
        return order, f, legs, pool

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
        pool = self.pool_for(order, None)
        f, legs = self.evaluate(order)
        if not self.all_states(legs):
            print('seed misses', [self.R.state_names[s] for s in self.missing(legs)]); order, f, legs = self.repair(order, pool)
            pool = self.pool_for(order, pool)
        order, f, legs = self.prune(order, pool); pool = self.pool_for(order, pool)   # drop states the seed already covers in passing
        print('start', round((f - self.t0) / 3600, 1), 'h, order', len(order), flush=True)
        deadline = time.time() + budget
        order, f, legs, pool = self.descend(order, f, legs, deadline, pool)
        best = (order, f, legs); kick = 0
        while time.time() < deadline:      # iterated local search: kick the incumbent, descend, keep if better
            kick += 1
            o2 = self.perturb(best[0], 2 + kick % 3)
            o2, f2, l2 = self.repair(o2, pool)
            if not self.all_states(l2): continue
            pool = self.pool_for(o2, pool)
            print('kick', kick, 'from', round((f2 - self.t0) / 3600, 1), 'h', flush=True)
            o2, f2, l2, pool = self.descend(o2, f2, l2, deadline, pool)
            if f2 < best[1] - 60:
                best = (o2, f2, l2); print('  new best', round((f2 - self.t0) / 3600, 1), 'h', flush=True)
        if pool: pool.close()
        return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True); ap.add_argument('--at', required=True); ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--seed', help='result pickle'); ap.add_argument('--seed-states', help='comma list of state abbreviations in visiting order'); ap.add_argument('--prefix', default='')
    ap.add_argument('--budget', type=float, default=900); ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True)
    ap.add_argument('--done', default='', help='comma list of state abbreviations already collected before --start')
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), t0.date(), a.days)
    start = R.stops_matching(a.start)[0]
    from common import ABBR
    inv = {v: k for k, v in ABBR.items()}
    done = [R.state_names.index(inv[x.strip()]) for x in a.done.split(',') if x.strip()]
    if a.seed_states:
        seed = [R.state_names.index(inv[x.strip()]) for x in a.seed_states.split(',')]
    else:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order'] if isinstance(x, (int, np.integer)) and x < N_STATES]
    seed = [x for x in seed if x not in done]
    S = Search(R, start, t0.timestamp(), [x.strip() for x in a.prefix.split(',') if x.strip()], a.workers, done)
    order, f, legs = S.run(seed, a.budget)
    if f == float('inf'): print('FINAL unreachable'); return
    print('FINAL', round((f - t0.timestamp()) / 3600, 1), 'h', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]))
    print(' > '.join(R.state_names[x] if isinstance(x, int) else x for x in order))
    print(R.describe(legs))
    pickle.dump(dict(order=order, finish=f, legs=legs), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
