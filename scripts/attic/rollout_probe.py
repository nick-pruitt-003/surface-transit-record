"""Score the nodes in a --dump-step dump by playing each one out, and see where the tracked chain lands.

  python3 rollout_probe.py ../out/bbm_dump19.pkl [--beam 5] [--topk 6] [--depth 0]

The leftover estimates all fail at the step where the beam loses the 237 route for the same reason: what
Oklahoma costs there is not the cost of reaching Oklahoma, which is small, but the cost of taking it and
then still having to cross the West. That is a property of the sequence, so the way to price it is to
play the sequence. Each node is run on to the start and ranked by the start time it reaches, which is
the quantity the whole search is trying to make as late as possible.

--depth n stops each rollout after n more states instead of running to the start, to see how much
lookahead is needed: the search can afford a short one per node per step, not a full one.

An earlier run of this ranked the reference last of 21. That was with topk 3, which cannot generate the
6th-ranked state the reference needs out of Kansas, and with the state matrix that counted border
walk-in points and so made neighbouring states free. Both are fixed, so it is worth redoing.
"""
import argparse, pickle, time
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
    ap.add_argument('--beam', default='5', help='comma list to sweep'); ap.add_argument('--topk', type=int, default=6)
    ap.add_argument('--tracked-only', action='store_true', help='only play the tracked node, at each --beam')
    ap.add_argument('--depth', type=int, default=0, help='stop each rollout after this many more states (0 = to the start)')
    a = ap.parse_args()
    d = pickle.load(open(a.dump, 'rb'))
    D, step, nodes, on = d['D'], d['step'], d['nodes'], d['oracle_node']
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
    import random
    rng = random.Random(48)

    bw = None

    def play(nd):
        """Run this node on and return (start time it reaches, states it could not place)."""
        root = dict(picked=list(nd['picked']), left=set(nd['left']), cur=dict(nd['cur']), ns=nd['ns'],
                    pin=list(nd['pin']))
        if a.depth:   # stop early: keep only the states a short lookahead would place
            root['_stop'] = len(root['picked']) + a.depth
        order, left, t = BB.build(R, F, state_stops, nd['picked'][0], D, rng, a.topk, bw,
                                  '', dist, oracle=None, root=root, quiet=True, stop_at=root.get('_stop'))
        return t, left

    beams = [int(x) for x in str(a.beam).split(',')]
    t0 = time.time()
    if a.tracked_only:
        # From this node a 237.3 h completion is known to exist, so whatever the sweep converges to is
        # how much of the gap is beam width and how much is the score being wrong about the tail.
        print(f'playing only the tracked node (at {ab(on["picked"][-1])}, {len(on["left"])} states left), '
              f'topk {a.topk}. A perfect completion from here is 237.3 h.\n')
        for bw in beams:
            t, left = play(on)
            print(f'  beam {bw:4d} -> {(D - t) / 3600:6.1f} h'
                  + (f'  (could not place {",".join(ab(x) for x in left)})' if left else '')
                  + f'   ({time.time() - t0:.0f} s)', flush=True)
        return
    bw = beams[0]
    rows = []
    for i, nd in enumerate(nodes):
        t, left = play(nd)
        rows.append((t, f'beam #{i + 1}', ab(nd['picked'][-1]), left))
        print(f'  beam #{i + 1:2d} at {ab(nd["picked"][-1]):3s} -> start '
              f'{datetime.fromtimestamp(t, ET):%a %H:%M} ({(D - t) / 3600:6.1f} h) '
              f'{"missing " + ",".join(ab(x) for x in left) if left else ""} ({time.time() - t0:.0f} s)', flush=True)
    t, left = play(on)
    rows.append((t, 'TRACKED', ab(on['picked'][-1]), left))
    print(f'  TRACKED   at {ab(on["picked"][-1]):3s} -> start {datetime.fromtimestamp(t, ET):%a %H:%M} '
          f'({(D - t) / 3600:6.1f} h) {"missing " + ",".join(ab(x) for x in left) if left else ""}', flush=True)

    rows.sort(key=lambda r: -r[0])
    pos = next(i + 1 for i, r in enumerate(rows) if r[1] == 'TRACKED')
    print(f'\nranked by the start each one reaches (later is better):')
    for i, (t, tag, here, left) in enumerate(rows[:6]):
        print(f'  {i + 1:2d}. {tag:9s} at {here:3s}  {(D - t) / 3600:6.1f} h'
              + (f'  (could not place {",".join(ab(x) for x in left)})' if left else ''))
    print(f'\nTRACKED ranks {pos}/{len(rows)}'
          f'   [the reference route is 237.3 h end to end]')
    print('the fix holds if that is in the top few; bottom half and playing the sequence is not the answer either.')


if __name__ == '__main__':
    main()
