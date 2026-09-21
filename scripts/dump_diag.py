"""Read a --dump-step dump and say why the tracked chain lost the beam at that step.

  python3 dump_diag.py ../out/bbd_dump19.pkl

Prints, for the tracked ("oracle") node and the top beam nodes: the current state, how late the node
still is, the leftover estimate, the score, and the set of states still unplaced. The question it
exists to answer is whether the beam leader has the SAME states left as the tracked chain. If it
does, no estimate that looks only at the set of remaining states can ever separate the two, however
it is weighted, and the only lever left is where the chain is and what time it is there.
"""
import pickle, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import build_backward as BB
from common import ABBR

ET = ZoneInfo('America/New_York')


def main(path):
    d = pickle.load(open(path, 'rb'))
    D, step, nodes, onode, oracle = d['D'], d['step'], d['nodes'], d.get('oracle_node'), d.get('oracle')
    print(f'dump of step {step}, deadline {datetime.fromtimestamp(D, ET):%a %Y-%m-%d %H:%M}, '
          f'{len(nodes)} beam nodes saved', flush=True)
    R = TimeRouter(load_feeds(), (datetime.fromtimestamp(D, ET) - __import__('datetime').timedelta(days=12)).date(), 20)
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    dist['M'] = np.array([[dist[x][y] for y in range(N_STATES)] for x in range(N_STATES)])
    import os
    for c in ('../out/state_times_real.npy', '../out/state_times.npy'):
        if os.path.exists(c): dist['T'] = np.load(c); break
    ab = lambda x: ABBR[R.state_names[x]]

    def line(tag, nd):
        t = max(nd['cur'].values()); lo = BB.strand_cost(nd['left'], nd['picked'][-1], dist)
        print(f'{tag:10s} at {ab(nd["picked"][-1]):3s} {datetime.fromtimestamp(t, ET):%a %H:%M} '
              f'({(D - t) / 3600:6.1f} h back)  leftover est {lo / 3600:5.1f} h  score {nd["score"] / 3600:8.1f} h  '
              f'{len(nd["left"]):2d} left', flush=True)
        return frozenset(nd['left'])

    oleft = line('TRACKED', onode) if onode is not None else None
    print()
    same = 0
    for i, nd in enumerate(nodes[:8]):
        l = line(f'beam #{i + 1}', nd)
        if oleft is not None and l == oleft: same += 1
    if oleft is not None:
        allsame = sum(1 for nd in nodes if frozenset(nd['left']) == oleft)
        print(f'\n{allsame}/{len(nodes)} beam nodes have EXACTLY the states left that the tracked chain has '
              f'({same}/8 of the top 8).', flush=True)
        if allsame:
            print('  -> for those nodes strand_cost() differs only through `here`, so re-weighting or '
                  'rescaling a set-of-states estimate cannot reorder them. Only a time-aware estimate can.')
        lead = nodes[0]
        print(f'  tracked left:  {" ".join(sorted(ab(x) for x in onode["left"]))}')
        print(f'  leader  left:  {" ".join(sorted(ab(x) for x in lead["left"]))}')
        d1 = sorted(ab(x) for x in (onode['left'] - lead['left']))
        d2 = sorted(ab(x) for x in (lead['left'] - onode['left']))
        print(f'  only tracked still needs: {" ".join(d1) or "(none)"}')
        print(f'  only leader  still needs: {" ".join(d2) or "(none)"}')
        if oracle:
            rem = [ab(x) for x in oracle[step:]]
            print(f'\n  the tracked chain picks these next, in this order: {" > ".join(rem)}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '../out/bbd_dump19.pkl')
