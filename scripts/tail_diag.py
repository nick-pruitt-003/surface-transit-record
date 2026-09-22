"""From a --dump-step dump, walk the tracked chain's remaining picks and say what each one costs.

  python3 tail_diag.py ../out/bbd_dump19.pkl

At every step it prints the candidates the builder would rank first, where the reference route's own next state
sits among them, and what taking the reference's state costs against taking the best-ranked one. A step where
the reference pays a lot and the builder cannot see why is a step where no node-scoring heuristic will save it:
the cost is in the sequence, not in the node.
"""
import pickle, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import backward as B
import build_backward as BB
from common import ABBR

ET = ZoneInfo('America/New_York')


def main(path, W):
    d = pickle.load(open(path, 'rb'))
    D, step0, on, oracle = d['D'], d['step'], d['oracle_node'], d['oracle']
    R = TimeRouter(load_feeds(), (datetime.fromtimestamp(D, ET) - timedelta(days=12)).date(), 20)
    F = B.RevFast(R)
    ab = lambda x: ABBR[R.state_names[x]]
    st_arr = {x: np.array([i for i in range(R.N) if R.state[i] == x], dtype=np.int64) for x in range(N_STATES)}

    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep

    def sparse(ns):
        idx = np.nonzero(ns[0] >= 0)[0]; return idx, ns[0][idx], ns[1][idx]

    def step(nd, want):
        """(candidates by latest time, the child that takes `want`)."""
        hi = max(nd['cur'].values())
        L, ok, k0, k1 = F.layer(nd['cur'], True, hi - W * 3600, dense(nd['ns']))
        mask = np.zeros(R.N, bool)
        for x in nd['left']: mask[st_arr[x]] = True
        eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
        cands = []
        for x in nd['left']:
            v = vals[st_arr[x]]; i = int(np.argmax(v))
            if v[i] > -np.inf: cands.append((float(v[i]), x, int(st_arr[x][i])))
        cands.sort(reverse=True)
        kid = None
        if want in nd['left']:
            xm = np.zeros(R.N, bool); xm[st_arr[want]] = True
            eff_x, ns_x = F.through(ok, k0, k1, xm)
            cur = {int(s): float(max(L[s], eff_x[s])) for s in st_arr[want] if max(L[s], eff_x[s]) > -np.inf}
            if cur:
                best_s = max(cur, key=cur.get)
                kid = dict(picked=nd['picked'] + [want], left=nd['left'] - {want}, cur=cur,
                           ns=sparse(ns_x), pin=nd['pin'] + [best_s])
        return cands, kid

    nd = on; total = 0.0
    print(f'\nwalking the reference chain on from step {step0} (at {ab(nd["picked"][-1])}), {W} h window.')
    print('the cost column is how much later the best-ranked state would have left you, had you taken it '
          'instead.\n')
    print('step  take  rank  cost vs best   best-ranked few')
    for i in range(step0 + 1, len(oracle)):
        want = oracle[i]
        cands, kid = step(nd, want)
        if kid is None:
            print(f'{i:4d}  {ab(want):4s}  -- unreachable from here'); break
        rank = next((j + 1 for j, c in enumerate(cands) if c[1] == want), None)
        best = cands[0][0]; got = max(kid['cur'].values())
        cost = (best - got) / 3600; total += max(cost, 0.0)
        head = ' '.join(f'{ab(c[1])}{(cands[0][0] - c[0]) / 3600:+.0f}' for c in cands[:4])
        flag = '  <<<' if cost > 8 else ''
        print(f'{i:4d}  {ab(want):4s}  {rank if rank else "-":>4}  {cost:11.1f} h   {head}{flag}')
        nd = kid
    print(f'\ntotal paid against always taking the best-ranked state: {total:.1f} h over '
          f'{len(oracle) - step0 - 1} steps')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '../out/bbd_dump19.pkl',
         float(sys.argv[2]) if len(sys.argv) > 2 else 110.0)
