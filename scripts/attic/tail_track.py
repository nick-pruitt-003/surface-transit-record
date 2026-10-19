"""Track the reference chain through its own tail, rooted at the node a --dump-step dump saved.

  python3 tail_track.py ../out/bbm_dump19.pkl [--beam 30] [--topk 6]

Rolling out from the reference's own node saturates at 267.7 h for any beam of 30 or more, when 237.3 h
from that node is known to exist. So neither the leftover estimate nor the beam width is what loses the
route, and the question is which of the 28 remaining steps drops it and why: a state never generated, a
state generated and out-scored, or a node thrown away by the duplicate key.

Same --track report as build_backward, but starting from the dumped node rather than the end state, so
every line is about the tail alone.
"""
import argparse, pickle, random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import backward as B
import build_backward as BB
from common import ABBR

ET = ZoneInfo('America/New_York')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dump', nargs='?', default='../out/bbm_dump19.pkl')
    ap.add_argument('--beam', type=int, default=30); ap.add_argument('--topk', type=int, default=6)
    ap.add_argument('--near', type=int, default=2)
    a = ap.parse_args()
    d = pickle.load(open(a.dump, 'rb'))
    D, step, on, oracle = d['D'], d['step'], d['oracle_node'], d['oracle']
    R = TimeRouter(load_feeds(), (datetime.fromtimestamp(D, ET) - timedelta(days=12)).date(), 20)
    F = B.RevFast(R)
    ab = lambda x: ABBR[R.state_names[x]]
    state_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    cen = {x: np.mean([R.stop_xy[i] for i in state_stops[x] if i < R.first_virtual], axis=0) for x in range(N_STATES)}
    km = lambda p, q: float(np.hypot((p[0] - q[0]) * 111.3 * np.cos(np.radians((p[1] + q[1]) / 2)), (p[1] - q[1]) * 111.3))
    dist = {x: {y: km(cen[x], cen[y]) for y in range(N_STATES)} for x in range(N_STATES)}
    dist['M'] = np.array([[dist[x][y] for y in range(N_STATES)] for x in range(N_STATES)])
    for c in ('../out/state_times_real.npy', '../out/state_times.npy'):
        if os.path.exists(c): dist['T'] = np.load(c); break

    # build() reads oracle[step] with step counting from this root, so line it up with the root's own state
    tail = oracle[step:]
    assert tail[0] == on['picked'][-1], (ab(tail[0]), ab(on['picked'][-1]))
    root = dict(picked=list(on['picked']), left=set(on['left']), cur=dict(on['cur']), ns=on['ns'], pin=list(on['pin']))
    print(f'rooted at {ab(root["picked"][-1])} with {len(root["left"])} states left, beam {a.beam}, '
          f'topk {a.topk}. The reference finishes 237.3 h from here.\n')
    order, left, t = BB.build(R, F, state_stops, root['picked'][0], D, rng=random.Random(48), topk=a.topk,
                              beam=a.beam, label='tail', dist=dist, near=a.near, oracle=tail, root=root)
    print(f'\nbeam reached {(D - t) / 3600:.1f} h' + (f', could not place {",".join(ab(x) for x in left)}' if left else ''))


if __name__ == '__main__':
    main()
