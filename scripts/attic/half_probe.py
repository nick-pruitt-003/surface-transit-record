"""Is the beam leader doing the eastern half faster, or just doing less of it?

  python3 half_probe.py [--beam 300] [--topk 8]

At the step where the beam drops the 237 route, the reference stands in Oklahoma 19 h further back than
the leader, with the same number of states placed. Two readings: either the search has found a genuinely
quicker way to run Oklahoma -> Vermont, and the reference's eastern half is the weak part, or the leader
is simply carrying fewer of the awkward states and has not paid for Oklahoma yet.

This decides it. Take exactly the states the reference has placed at that step, search their orderings
from Vermont at the deadline, and report the latest you can be in Oklahoma having covered all of them.
Later than the reference's own Wed 17:20 means its eastern half is beatable by that much and is worth
attacking. No later means the 19 h is not a slower first half, it is the bill for Oklahoma.
"""
import argparse, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
import backward as B
import build_backward as BB
from common import ABBR

ET = ZoneInfo('America/New_York')
DEADLINE = datetime(2026, 11, 14, 22, 14, tzinfo=ET)
# what the reference has placed at step 19, backwards from Vermont, with Oklahoma held back to the end
EAST = 'NH ME MA RI CT NY NJ PA DE MD VA NC SC GA FL AL LA TX'.split()
LAST = 'OK'
REF = datetime(2026, 11, 11, 17, 20, tzinfo=ET)   # the reference's own latest time in Oklahoma


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--beam', type=int, default=300); ap.add_argument('--topk', type=int, default=8)
    a = ap.parse_args()
    D = DEADLINE.timestamp()
    R = TimeRouter(load_feeds(), (DEADLINE - timedelta(days=12)).date(), 20)
    F = B.RevFast(R)
    inv = {v: k for k, v in ABBR.items()}
    sid = lambda ab: R.state_names.index(inv[ab])
    ab = lambda x: ABBR[R.state_names[x]]
    st_arr = {x: np.array([i for i in range(R.N) if R.state[i] == x], dtype=np.int64) for x in range(N_STATES)}
    vt, last = sid('VT'), sid(LAST)
    east = {sid(x) for x in EAST}

    def dense(sp):
        ns_stop = np.full(F.nt, -1, dtype=np.int32); ns_dep = np.full(F.nt, -np.inf)
        if sp is not None: ns_stop[sp[0]] = sp[1]; ns_dep[sp[0]] = sp[2]
        return ns_stop, ns_dep

    def sparse(ns):
        idx = np.nonzero(ns[0] >= 0)[0]; return idx, ns[0][idx], ns[1][idx]

    def kids_of(nd, want=None, k=1):
        """Children of a node: the k states it can still be in latest, or just `want`."""
        hi = max(nd['cur'].values())
        L, ok, k0, k1 = F.layer(nd['cur'], True, hi - 140 * 3600, dense(nd['ns']))
        mask = np.zeros(R.N, bool)
        for x in nd['left']: mask[st_arr[x]] = True
        if want is not None: mask[:] = False; mask[st_arr[want]] = True
        eff, _ = F.through(ok, k0, k1, mask); vals = np.maximum(L, eff)
        pool = [want] if want is not None else list(nd['left'])
        cands = sorted(((float(vals[st_arr[x]].max()), x) for x in pool), reverse=True)
        out = []
        for _, x in cands[:k]:
            xm = np.zeros(R.N, bool); xm[st_arr[x]] = True
            eff_x, ns_x = F.through(ok, k0, k1, xm)
            cur = {int(s): float(max(L[s], eff_x[s])) for s in st_arr[x] if max(L[s], eff_x[s]) > -np.inf}
            if cur: out.append(dict(picked=nd['picked'] + [x], left=nd['left'] - {x}, cur=cur, ns=sparse(ns_x)))
        return out

    nodes = [dict(picked=[vt], left=set(east), cur={int(s): D for s in st_arr[vt]}, ns=None)]
    t0 = time.time()
    while nodes[0]['left']:
        children = []
        for nd in nodes: children += kids_of(nd, k=a.topk)
        if not children: break
        seen = set(); kept = []
        for c in sorted(children, key=lambda c: -max(c['cur'].values())):
            key = (frozenset(c['left']), c['picked'][-1])
            if key in seen: continue
            seen.add(key); kept.append(c)
            if len(kept) >= a.beam: break
        nodes = kept
        b = nodes[0]
        print(f'  {len(b["picked"]) - 1}/{len(EAST)} placed, best at {ab(b["picked"][-1])} '
              f'{datetime.fromtimestamp(max(b["cur"].values()), ET):%a %H:%M} '
              f'({len(nodes)} in beam, {time.time() - t0:.0f} s)', flush=True)

    best = None
    for nd in nodes:
        for k in kids_of(nd, want=last):
            t = max(k['cur'].values())
            if best is None or t > best[0]: best = (t, k['picked'])
    print()
    if best is None:
        print(f'no ordering of those {len(EAST)} states reaches {LAST} at all'); return
    t, picked = best
    d = (t - REF.timestamp()) / 3600
    print(f'reference is in {LAST} at {REF:%a %H:%M} ({(D - REF.timestamp()) / 3600:.1f} h back)')
    print(f'best found     {LAST} at {datetime.fromtimestamp(t, ET):%a %H:%M} ({(D - t) / 3600:.1f} h back)  '
          f'-> {d:+.1f} h')
    print('  ' + ' < '.join(ab(x) for x in picked))
    print(f'\n{"the eastern half IS beatable by that much" if d > 0.5 else "the eastern half is not the problem: the 19 h is what Oklahoma costs"}')


if __name__ == '__main__':
    main()
