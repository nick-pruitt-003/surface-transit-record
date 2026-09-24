"""Chain every order of the six blocks from blocks.pkl and rank them. Leaf script, no router, about 2 min.

A candidate is an order of the six blocks, a variant and direction for each, and a start slot. Its time is
block, joint, block, ... looked up in the tables. A departure is floored to its 15-minute slot, so a candidate can
only look better than it is, never worse: the ranking may keep a dead one for block_verify.py to kill, but it
cannot drop a live one for rounding.

Calibration before the ranking prints: the control's and X's own block sequences are priced and shown next to
their real totals, and where they rank. If they are far off or rank low, the blocks are drawn wrong and the
ranking below them means nothing.

Output: ../out/assemble.txt and ../out/assemble.pkl (top candidates, for block_verify.py)
"""
import argparse, itertools, pickle
import numpy as np

KNOWN = {  # name: ([(block, entry, exit)], real hours)
    'control': ([('GL', 'Huntington', 'Chicago'), ('PL', 'Memphis', 'Minneapolis'), ('NW', 'Sheridan', 'LasVegasAirport'),
                 ('SW', 'LasVegasAirport', 'Dallas'), ('GS', 'Dallas', 'WashingtonDC'), ('NE', 'WashingtonDC', 'Hanover')], 237.34),
    'X': ([('NW', 'Sheridan', 'LasVegasAirport'), ('SW', 'LasVegasAirport', 'Dallas'), ('GS', 'Dallas', 'WashingtonDC'),
           ('NE', 'WashingtonDC', 'Hanover'), ('GL', 'Huntington', 'Chicago'), ('PL', 'Chicago', 'Memphis')], 239.50),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tables', default='../out/blocks.pkl')
    ap.add_argument('--top', type=int, default=50)
    a = ap.parse_args()
    D = pickle.load(open(a.tables, 'rb')); S, n = D['slot'], D['n']
    blocks = sorted({k[0] for k in D['variants']})
    var = {b: [k for k in D['variants'] if k[0] == b] for b in blocks}
    starts = np.arange(n, dtype=np.float64) * S

    def step(t, d):
        s = np.floor(t / S)
        return np.maximum(t, s * S + d[(s % n).astype(np.int64)])

    def price(seq):
        t = starts.copy()
        for i, k in enumerate(seq):
            if i and seq[i - 1][2] != k[1]: t = step(t, D['joint'][(seq[i - 1][2], k[1])])
            t = step(t, D['block'][k])
        return (t - starts) / 3600

    res = []   # (best hours, start slot, seq)
    for perm in itertools.permutations(blocks):
        for seq in itertools.product(*(var[b] for b in perm)):
            h = price(seq); j = int(np.argmin(h))
            if np.isfinite(h[j]): res.append((float(h[j]), j, seq))
    res.sort(key=lambda r: r[0])
    rank = {r[2]: i for i, r in enumerate(res)}
    fmt = lambda seq: ' | '.join(f'{b} {e}>{x}' for b, e, x in seq)
    lines = [f'{len(res)} block sequences priced over {n} start slots of {S // 60} min', '', 'calibration (must be close and rank high):']
    for name, (seq, real) in KNOWN.items():
        h = price(tuple(seq)); j = int(np.argmin(h))
        lines.append(f'  {name:8s} tables {h[j]:6.1f} h vs real {real:6.2f} h ({h[j] - real:+.1f}), rank {rank.get(tuple(seq), -1) + 1} of {len(res)}')
    lines += ['', f'top {a.top}:']
    for i, (h, j, seq) in enumerate(res[:a.top]):
        lines.append(f'{i + 1:3d} {h:6.1f} h  start slot {j:3d} (+{j * S / 3600:5.2f} h from Thu 00:00 CT)  {fmt(seq)}')
    open('../out/assemble.txt', 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines), flush=True)
    pickle.dump(dict(res=res[:max(a.top, 200)], S=S, t0=D['t0'], variants=D['variants'], portals=D['portals']), open('../out/assemble.pkl', 'wb'))


if __name__ == '__main__':
    main()
