"""Local search over the state order using real timetables as the objective.

usage: python3 time_search.py --start Missoula --at 2026-09-21T07:00 --tz America/Denver \
         --seed ../out/start_newton.pkl [--prefix "Idaho,Washington"] --budget 900 --workers 8 --out ../out/time_best.pkl
"""
import argparse, pickle, random, time, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES

_R = None; _START = None; _T0 = None


def _finish(order):
    f, legs = _R.route(_START, _T0, order)
    return f if f is not None else float('inf')


class Search:
    def __init__(self, R, start, t0, prefix, workers):
        self.R = R; self.start = start; self.t0 = t0; self.workers = workers
        self.prefix = []
        for p in prefix:
            self.prefix.append(p if p.startswith('@') else R.state_names.index(p))
        self.P = len(self.prefix)

    def covered(self, legs):
        """States with an alighting-capable stop anywhere along the ridden trips."""
        seen = set()
        for l in legs:
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

    def prune(self, order):
        f, legs = self.evaluate(order)
        if f == float('inf'): return order, f, legs
        changed = True
        while changed:
            changed = False
            for j in range(self.P, len(order)):
                o2 = order[:j] + order[j + 1:]
                f2, l2 = self.evaluate(o2)
                if f2 <= f and self.all_states(l2):
                    print('  drop', self.R.state_names[order[j]], '->', round((f2 - self.t0) / 3600, 1), 'h')
                    order, f, legs = o2, f2, l2; changed = True; break
        return order, f, legs

    def all_states(self, legs):
        return len(self.covered(legs) | {int(self.R.state[self.start])}) >= N_STATES

    def missing(self, legs):
        cov = self.covered(legs) | {int(self.R.state[self.start])}
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
            for j in range(P, n):
                if j != i: out.append(rest[:j] + seg + rest[j:])
        for i in range(P, n - 1):
            for j in range(i + 2, min(n, i + 12) + 1):
                out.append(order[:i] + order[i:j][::-1] + order[j:])
        return out

    def run(self, order, budget):
        global _R, _START, _T0
        _R, _START, _T0 = self.R, self.start, self.t0
        pool = None
        if self.workers > 1:
            import multiprocessing as mp
            pool = mp.get_context('fork').Pool(self.workers)
        order = self.prefix + [x for x in order if x not in self.prefix]
        f, legs = self.evaluate(order)
        if not self.all_states(legs):
            print('seed misses', [self.R.state_names[s] for s in self.missing(legs)]); order, f, legs = self.repair(order, pool)
        print('start', round((f - self.t0) / 3600, 1), 'h, order', len(order))
        t_start = time.time(); improved = True; it = 0
        while improved and time.time() - t_start < budget:
            improved = False
            cands = self.moves(order); random.shuffle(cands)
            batch = max(1, self.workers * 2)
            for i in range(0, len(cands), batch):
                if time.time() - t_start > budget: break
                chunk = cands[i:i + batch]
                fs = pool.map(_finish, chunk) if pool else [_finish(o) for o in chunk]
                it += len(chunk); j = int(np.argmin(fs))
                if fs[j] < f - 60:
                    o2, f2, l2 = self.repair(chunk[j], pool)
                    if f2 < f - 60 and self.all_states(l2):
                        order, f, legs = o2, f2, l2; improved = True
                        print('  improve', round((f - self.t0) / 3600, 1), 'h after', it, 'evals', round(time.time() - t_start), 's', flush=True); break
            if improved:
                order, f, legs = self.prune(order)
        if pool: pool.close()
        return order, f, legs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True); ap.add_argument('--at', required=True); ap.add_argument('--tz', default='America/Denver')
    ap.add_argument('--seed', help='result pickle'); ap.add_argument('--seed-states', help='comma list of state abbreviations in visiting order'); ap.add_argument('--prefix', default='')
    ap.add_argument('--budget', type=float, default=900); ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    R = TimeRouter(load_feeds(), t0.date(), a.days)
    start = R.stops_matching(a.start)[0]
    if a.seed_states:
        from common import ABBR
        inv = {v: k for k, v in ABBR.items()}
        seed = [R.state_names.index(inv[x.strip()]) for x in a.seed_states.split(',')]
    else:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order'] if isinstance(x, (int, np.integer)) and x < N_STATES]
    S = Search(R, start, t0.timestamp(), [x.strip() for x in a.prefix.split(',') if x.strip()], a.workers)
    order, f, legs = S.run(seed, a.budget)
    if f == float('inf'): print('FINAL unreachable'); return
    print('FINAL', round((f - t0.timestamp()) / 3600, 1), 'h', R.fmt_time(f, [l for l in legs if l[0] == 'ride'][-1][4]))
    print(' > '.join(R.state_names[x] if isinstance(x, int) else x for x in order))
    print(R.describe(legs))
    pickle.dump(dict(order=order, finish=f, legs=legs), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
