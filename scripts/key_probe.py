"""Score candidate frontier keys on a saved --xprobe frontier (../out/xprobe_last.pkl), offline.

For every layer X's reference passes through, rank X's node against the queued nodes in that layer under
several keys built from the exact pair table, and print how many sit ahead of X under each. Lower key pops
first, as in ride_search's pri(). Leaf script; nothing imports it.

  py key_probe.py --at 2026-11-12T22:10 --by 2026-11-22T15:10 --tz America/Denver [--days 20]
"""
import argparse, glob, os, pickle
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from pair_tables import resolve_stop
from common import ABBR

ap = argparse.ArgumentParser()
ap.add_argument('--at', required=True); ap.add_argument('--by', required=True)
ap.add_argument('--tz', required=True); ap.add_argument('--days', type=int, default=20)
ap.add_argument('--pairs', help='pairs_*.npy (default: newest in ../out)')
ap.add_argument('--probe', default='../out/xprobe_last.pkl')
ap.add_argument('--k', type=int, default=10)
a = ap.parse_args()
when = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
D = datetime.fromisoformat(a.by).replace(tzinfo=ZoneInfo(a.tz)).timestamp()
R = cached_router(when.date(), a.days, verbose=False)
P = np.load(a.pairs or max(glob.glob('../out/pairs_*.npy'), key=os.path.getmtime), mmap_mode='r')
idx = {ABBR[n]: i for i, n in enumerate(R.state_names)}
d = pickle.load(open(a.probe, 'rb'))
T0 = when.timestamp()                       # spent is relative to the run's --at
_ids = {}


def margins(stopname, t, have):
    """sorted margins (h) of every unordered owed pair, at the stop of that name that leaves the most room"""
    owed = np.array(sorted(set(range(len(R.state_names))) - {idx[s] for s in have}), dtype=np.int64)
    if stopname not in _ids: _ids[stopname] = resolve_stop(R, stopname) or []
    best = None
    for s in _ids[stopname]:
        sub = np.asarray(P[s])[np.ix_(owed, owed)] - np.float32(t - D)
        m = np.sort(sub[np.triu_indices(len(owed), 1)]) / 3600.0
        if best is None or m[0] > best[0]: best = m
    return best


K = a.k
KEYS = {
    'current  spent-3*min': lambda sp, m: sp - 3 * m[0],
    'min margin only':      lambda sp, m: -m[0],
    f'mean {K} tightest':   lambda sp, m: -m[:K].mean(),
    f'spent-3*mean{K}':     lambda sp, m: sp - 3 * m[:K].mean(),
    'pairs under 24 h':     lambda sp, m: (m < 24).sum() - m[0] / 1e4,
    'mean all pairs':       lambda sp, m: -m.mean(),
}
print(f'{"layer":>5} {"X at":<26}' + ''.join(f'{k:>22}' for k in KEYS))
for row in d['x']:
    nleg, n, spx, sx, name, st, px, pm = row
    its = d['items'].get(n)
    if not its: continue
    mx = margins(name, T0 + spx, st)
    if mx is None: continue
    keysx = {k: f(spx / 3600, mx) for k, f in KEYS.items()}
    ahead = {k: 0 for k in KEYS}
    for it in its:
        m = margins(it[2], it[3], it[4])
        if m is None: continue
        for k, f in KEYS.items():
            if f(it[1] / 3600, m) < keysx[k]: ahead[k] += 1
    print(f'{n:>5} {name[:26]:<26}' + ''.join(f'{f"{ahead[k]}/{len(its)}":>22}' for k in KEYS), flush=True)
