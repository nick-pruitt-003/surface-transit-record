"""Chain every order of the six blocks from blocks.pkl and rank them. Leaf script, no router, about 2 min.

A candidate is an order of the six blocks, a variant and direction for each, and a start slot. Its time is
block, joint, block, ... looked up in the tables. A departure is floored to its 15-minute slot, so a candidate can
only look better than it is, never worse: the ranking may keep a dead one for block_verify.py to kill, but it
cannot drop a live one for rounding.

Calibration gates the ranking: the control's and X's own block sequences are priced against their real totals.
Each must come within CAL_TOL_H and rank inside the published top. If either misses, the blocks are drawn wrong,
so the ranking is not printed and no assemble.pkl is written for block_verify.py; the script exits 1.

Lookups never wrap: a transition past the end of the tables is infinite, not read off an earlier week. Starts are
the first week's slots; the tables (blocks.py) run long enough past that for a whole route.

Output: ../out/assemble.txt and ../out/assemble.pkl (top candidates, for block_verify.py)
"""
import argparse, itertools, os, pickle, sys
import numpy as np

CAL_TOL_H = 2.0   # hours either way; the floor to 15-minute slots can only flatter a sequence

KNOWN = {  # name: ([(block, entry, exit)], real hours)
    'control': ([('GL', 'Huntington', 'Chicago'), ('PL', 'Memphis', 'Minneapolis'), ('NW', 'Sheridan', 'LasVegasAirport'),
                 ('SW', 'LasVegasAirport', 'Dallas'), ('GS', 'Dallas', 'WashingtonDC'), ('NE', 'WashingtonDC', 'Hanover')], 237.34),
    'X': ([('NW', 'Sheridan', 'LasVegasAirport'), ('SW', 'LasVegasAirport', 'Dallas'), ('GS', 'Dallas', 'WashingtonDC'),
           ('NE', 'WashingtonDC', 'Hanover'), ('GL', 'Huntington', 'Chicago'), ('PL', 'Chicago', 'Memphis')], 238.32),   # X with the router's own Holmes ending
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tables', default='../out/blocks.pkl')
    ap.add_argument('--top', type=int, default=50)
    a = ap.parse_args()
    # written only on a calibrated success, so any exit before that leaves no ranking for block_verify.py to read
    if os.path.exists('../out/assemble.pkl'): os.remove('../out/assemble.pkl')
    D = pickle.load(open(a.tables, 'rb')); S, n = D['slot'], D['n']
    week = D.get('week', n)
    if n <= week: sys.exit(f'{a.tables} holds {n} slots, one week or less: every transition past it would have to wrap. '
                           f'Rebuild it with blocks.py, whose default runs past the first week.')
    blocks = sorted({k[0] for k in D['variants']})
    var = {b: [k for k in D['variants'] if k[0] == b] for b in blocks}
    starts = np.arange(week, dtype=np.float64) * S   # start in the first week; the rest of the table is horizon

    def step(t, d):
        s = np.floor(t / S); ok = s < n
        out = np.full_like(t, np.inf)
        out[ok] = np.maximum(t[ok], s[ok] * S + d[s[ok].astype(np.int64)])
        return out

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
    lines = [f'{len(res)} block sequences priced over {week} start slots of {S // 60} min', '',
             f'calibration (each within {CAL_TOL_H} h of real and inside the top {a.top}, or nothing below is published):']
    ok = True
    for name, (seq, real) in KNOWN.items():
        h = price(tuple(seq)); j = int(np.argmin(h)); r = rank.get(tuple(seq), -1) + 1
        good = np.isfinite(h[j]) and abs(h[j] - real) <= CAL_TOL_H and 0 < r <= a.top; ok &= good
        lines.append(f'  {name:8s} tables {h[j]:6.1f} h vs real {real:6.2f} h ({h[j] - real:+.1f}), rank {r} of {len(res)}  {"ok" if good else "FAILED"}')
    if not ok:
        lines += ['', 'CALIBRATION FAILED: the blocks do not reproduce the known routes, so no ranking is published and no '
                  'assemble.pkl is written for block_verify.py.']
        open('../out/assemble.txt', 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines), flush=True)
        sys.exit(1)
    lines += ['', f'top {a.top}:']
    for i, (h, j, seq) in enumerate(res[:a.top]):
        lines.append(f'{i + 1:3d} {h:6.1f} h  start slot {j:3d} (+{j * S / 3600:5.2f} h from Thu 00:00 CT)  {fmt(seq)}')
    open('../out/assemble.txt', 'w').write('\n'.join(lines) + '\n'); print('\n'.join(lines), flush=True)
    pickle.dump(dict(res=res[:max(a.top, 200)], S=S, t0=D['t0'], variants=D['variants'], portals=D['portals']), open('../out/assemble.pkl', 'wb'))


if __name__ == '__main__':
    main()
