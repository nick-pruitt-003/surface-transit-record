"""Test time-aware leftover estimates on a --dump-step dump.

  python3 reach_probe.py ../out/bbd_dump19.pkl [window_hours]

The set of states still to place is nearly identical for the tracked chain and the beam leader, so no
estimate built from that set can tell them apart. This measures the one thing that does differ: from
each node, at its own clock, one reverse scan gives the latest time you could still be in each state
it has not placed.

It also shows why summing the dearest few of those is not an estimate at all. Each one is the node's
own time minus a latest time, so summing n of them counts that time n times over, and a score that
subtracts the sum from that same time ends up paying a chain n-1 times just for being further back.
Run it on the step 19 dump and 'strand + reach dearest 5' looks decisive; run it on the step 11 dump,
where the reference chain is ahead rather than behind, and the same estimate is the worst of the lot.
Only the single furthest value is safe to use.
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
    D, step, nodes, on = d['D'], d['step'], d['nodes'], d['oracle_node']
    R = TimeRouter(load_feeds(), (datetime.fromtimestamp(D, ET) - timedelta(days=12)).date(), 20)
    F = B.RevFast(R)
    ab = lambda x: ABBR[R.state_names[x]]
    st_arr = {x: np.array([i for i in range(R.N) if R.state[i] == x], dtype=np.int64) for x in range(N_STATES)}

    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep

    def reach(nd):
        """{state: hours back from this node at which you can still be in it}, over the states left."""
        t = max(nd['cur'].values())
        L, ok, k0, k1 = F.layer(nd['cur'], True, t - W * 3600, dense(nd['ns']))
        mask = np.zeros(R.N, bool)
        for x in nd['left']: mask[st_arr[x]] = True
        eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
        out = {}
        for x in nd['left']:
            v = float(vals[st_arr[x]].max())
            out[x] = (t - v) / 3600 if v > -np.inf else float('inf')
        return t, out

    t_on, h_on = reach(on)
    t_ld, h_ld = reach(nodes[0])
    gap = (t_ld - t_on) / 3600
    print(f'\nstep {step}, {W} h window. The tracked chain is {gap:.1f} h further back than the leader, '
          f'so an estimate saves it only if it charges the leader over {gap:.1f} h more.\n')

    def show(tag, nd, h):
        far = [ab(x) for x, v in h.items() if v == float('inf')]
        top = sorted(((v, ab(x)) for x, v in h.items() if v < float('inf')), reverse=True)[:6]
        print(f'{tag}: at {ab(nd["picked"][-1])}, dearest states still to place: '
              + ', '.join(f'{a} {v:.1f}h' for v, a in top) + (f'  | beyond the window: {" ".join(far)}' if far else ''))
    show('TRACKED', on, h_on); show('LEADER ', nodes[0], h_ld)

    CAP = W * 1.5
    import os
    T = np.load('../out/state_times_real.npy' if os.path.exists('../out/state_times_real.npy') else '../out/state_times.npy')
    dist = {'T': T}
    def vals(h): return sorted((min(v, CAP) for v in h.values()), reverse=True)
    def strand(nd): return BB.strand_cost(nd['left'], nd['picked'][-1], dist) / 3600
    ests = (('strand_cost alone (current)', lambda nd, h: strand(nd)),
            ('reach, dearest 3', lambda nd, h: sum(vals(h)[:3])),
            ('reach, dearest 5', lambda nd, h: sum(vals(h)[:5])),
            ('strand + reach dearest 3', lambda nd, h: strand(nd) + sum(vals(h)[:3])),
            ('strand + reach dearest 5', lambda nd, h: strand(nd) + sum(vals(h)[:5])),
            ('strand + reach dearest 8', lambda nd, h: strand(nd) + sum(vals(h)[:8])))
    print('\nestimate                     tracked   leader   leader-tracked   keeps tracked?')
    for name, fn in ests:
        a, b = fn(on, h_on), fn(nodes[0], h_ld)
        print(f'{name:28s} {a:6.1f} h {b:6.1f} h   {b - a:+8.1f} h        {"YES" if b - a > gap else "no"}')

    # the same estimates across the whole saved beam: how far down would the tracked node rank?
    scans = [reach(nd) for nd in nodes]
    print('\nrank the tracked node would hold in the saved beam (lower is better, 1 = best):')
    for name, fn in ests:
        sc_on = t_on - fn(on, h_on) * 3600
        worse = sum(1 for nd, (t, h) in zip(nodes, scans) if t - fn(nd, h) * 3600 > sc_on)
        print(f'  {name:28s} {worse + 1}/{len(nodes) + 1}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '../out/bbd_dump19.pkl',
         float(sys.argv[2]) if len(sys.argv) > 2 else 110.0)
