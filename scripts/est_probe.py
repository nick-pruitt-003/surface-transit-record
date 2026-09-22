"""Score candidate leftover-work estimates against a --dump-step dump.

  python3 est_probe.py ../out/bbd_dump19.pkl

The beam drops the tracked chain when (latest time - estimate) ranks it below the cut, so what matters
is not how close an estimate is to the true remainder but whether it separates the tracked node from
the beam leader by more than their gap in latest time. This prints that separation for each estimate,
and the per-state marginal costs the current matrix assigns, without building a router.
"""
import json, os, pickle, sys
import numpy as np
from common import ABBR, DATA_DIR, SKIP_STATES

N = 48
# the router numbers states by the order of the borders file it loads (states_500k when present, as in
# time_router), not alphabetically; read the same file rather than build a router just for the labels
_hi = os.path.join(DATA_DIR, 'states_500k.geojson')
AB = [ABBR[f['properties']['name']] for f in
      json.load(open(_hi if os.path.exists(_hi) else os.path.join(DATA_DIR, 'states.geojson')))['features']
      if f['properties']['name'] not in SKIP_STATES]


def mst(nodes, M):
    if len(nodes) < 2: return 0.0
    m = M[np.ix_(nodes, nodes)]
    inside = np.zeros(len(nodes), bool); inside[0] = True; best = m[0].copy(); tot = 0.0
    for _ in range(len(nodes) - 1):
        best[inside] = np.inf; j = int(np.argmin(best)); tot += best[j]; inside[j] = True
        best = np.minimum(best, m[j])
    return tot


def enter(nodes, M):
    """Each state after the first must be entered once: sum of each one's cheapest incoming edge from
    anywhere else still on the route. A path visits them in some order, so every one of them pays at
    least its cheapest entry; unlike a spanning tree this does not let a whole cluster hang off one
    cheap edge."""
    if len(nodes) < 2: return 0.0
    m = M[np.ix_(nodes, nodes)].copy(); np.fill_diagonal(m, np.inf)
    return float(m.min(axis=0)[1:].sum())


def main(path):
    d = pickle.load(open(path, 'rb'))
    D, step, nodes, on = d['D'], d['step'], d['nodes'], d['oracle_node']
    mats = [m for m in (sys.argv[2] if len(sys.argv) > 2 else '').split(',') if m] or ['../out/state_times_real.npy']
    lead = nodes[0]
    t_on, t_ld = max(on['cur'].values()), max(lead['cur'].values())
    gap = (t_ld - t_on) / 3600
    print(f'step {step}: tracked is {gap:.1f} h further back than the beam leader, so an estimate only '
          f'keeps it alive if it charges the leader MORE than the tracked node by over {gap:.1f} h.\n')

    T = np.load(mats[0])
    here_on, here_ld = on['picked'][-1], lead['picked'][-1]
    only_on = sorted(on['left'] - lead['left']); only_ld = sorted(lead['left'] - on['left'])
    print('the two differ by one state each:')
    for x in only_on: print(f'  only the tracked node still needs {AB[x]}: cheapest hop to it {T[x][list(on["left"])].min():.1f} h')
    for x in only_ld: print(f'  only the leader  still needs {AB[x]}: cheapest hop to it {T[x][list(lead["left"])].min():.1f} h')

    print('\nmatrix                            tracked   leader   leader-tracked   keeps tracked?')
    for m in mats:
        M = np.load(m)
        a = mst([here_on] + sorted(on['left']), M); b = mst([here_ld] + sorted(lead['left']), M)
        sep = b - a
        print(f'{os.path.basename(m)[:33]:33s} {a:6.1f} h {b:6.1f} h   {sep:+8.1f} h        {"YES" if sep > gap else "no"}')

    print('\nper-state marginal cost the current matrix implies (cheapest hop to each state still left, '
          'tracked node):')
    row = sorted(((float(T[x][sorted(on['left'] - {x})].min()), AB[x]) for x in on['left']), reverse=True)
    print('  dearest: ' + ', '.join(f'{a} {v:.1f}h' for v, a in row[:6]))
    print('  cheapest: ' + ', '.join(f'{a} {v:.1f}h' for v, a in row[-6:]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '../out/bbd_dump19.pkl')
