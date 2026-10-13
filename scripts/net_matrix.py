"""Timetable-free network matrix for the State Line Driver page (Nick, Oct 13 2026).

The graph is the router's own: an edge for every pair of consecutive stops on any trip in the window, weighted by the
shortest scheduled ride between them, plus every footpath (walk-ins, measured walks, local hops). No waiting, no
boarding time, no days: a lower bound that only goes where buses and trains actually run, so Yellowstone stops being
a shortcut. Candidate points per state: the intercity stops on the most distinct links (hubs) plus the stops nearest
each other state, so border collections (West Memphis, Primm, Moorhead, walk-ins) survive.

Leaf script: nothing imports it.   py net_matrix.py ../out/net_router/net.json   (from scripts/)
"""
import base64, json, sys
from datetime import date
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from time_router import cached_router, INTERCITY_MORE
from common import ABBR

R = cached_router(date(2026, 11, 12), 20, verbose=False)
N = len(R.stop_ids)
INTER = {'flix', 'amtrak', 'ibus', 'extra', 'walkin'} | set(INTERCITY_MORE)

# ride edges: shortest arr - dep per (from, to)
src = np.asarray(R.cfrom, dtype=np.int64); dst = np.asarray(R.cto, dtype=np.int64)
w = (np.asarray(R.arr) - np.asarray(R.dep)).astype(np.float64)
ok = (w > 0) & (src != dst)
key = src[ok] * N + dst[ok]; w = w[ok]
order = np.lexsort((w, key)); key = key[order]; w = w[order]
first = np.ones(len(key), bool); first[1:] = key[1:] != key[:-1]
key = key[first]; w = w[first]
rs, rd = key // N, key % N
# footpaths
fs, fd, fw = [], [], []
for i, lst in R.foot.items():
    for j, s in lst:
        if i != j: fs.append(i); fd.append(j); fw.append(float(max(s, 1)))
S = np.concatenate([rs, np.array(fs, np.int64)]); D = np.concatenate([rd, np.array(fd, np.int64)])
W = np.concatenate([w, np.array(fw)])
G = csr_matrix((W, (S, D)), shape=(N, N))
print(f'graph: {N} stops, {len(rs)} ride edges, {len(fs)} footpaths', file=sys.stderr)

# candidates: per state, the 3 busiest intercity stops, then farthest-point picks so every corner of the state has one
# (Oct 13: busiest-plus-near-a-border missed Sheridan WY), then up to 3 walk-in border points spread the same way
st = np.asarray(R.state)
inter = np.array([R.stop_ids[i].split(':')[0] in INTER for i in range(N)])
deg = np.bincount(rs, minlength=N) + np.bincount(rd, minlength=N)
xy = np.array(R.stop_xy)   # (lon, lat)
def spread(pool, have, k):
    pick = list(have)
    while len(pick) < k and len(pool) > len(set(pick) & set(pool)):
        rest = [i for i in pool if i not in pick]
        if not pick: pick.append(rest[0]); continue
        P = xy[pick]; Q = xy[rest]
        d = np.min(((Q[:, None, 0] - P[None, :, 0]) * 0.8) ** 2 + (Q[:, None, 1] - P[None, :, 1]) ** 2, axis=1)
        if d.max() < 0.15 ** 2: break   # nothing left more than ~15 km from a pick
        pick.append(rest[int(np.argmax(d))])
    return pick
cands = []
for s in range(len(R.state_names)):
    real = [int(i) for i in np.where((st == s) & inter & (deg > 0))[0] if not R.stop_ids[i].startswith('walkin:')]
    if not real: real = [int(i) for i in np.where((st == s) & (deg > 0))[0] if not R.stop_ids[i].startswith('walkin:')]
    real.sort(key=lambda i: -deg[i])
    pick = spread(real, real[:3], 9)
    walk = [int(i) for i in np.where(st == s)[0] if R.stop_ids[i].startswith('walkin:') or (R.walk_collects(i) and not R.stop_ids[i].startswith('walkin:'))]
    pick += [i for i in spread(walk, [], 3) if i not in pick]
    cands += pick
cands = list(dict.fromkeys(cands))
print(f'{len(cands)} candidate points before the reachability filter', file=sys.stderr)

dist, pred = dijkstra(G, directed=True, indices=cands, return_predecessors=True)
dist = dist[:, cands]   # seconds
# drop dead ends: a candidate that cannot reach, or be reached from, most of the others breaks whole routes
fin = np.isfinite(dist)
keep = [k for k in range(len(cands)) if fin[k].mean() > 0.8 and fin[:, k].mean() > 0.8]
cands = [cands[k] for k in keep]; dist = dist[np.ix_(keep, keep)]
pred = pred[keep]
# states each fastest path passes through at a real stop (Nick, Oct 13: Milwaukee -> Fargo goes through Minneapolis, so
# Minnesota should not need a stop of its own). 48 bits per pair, as two 32-bit words.
real_stop = np.array([not R.stop_ids[i].startswith('walkin:') for i in range(N)])
lo_w = np.zeros((len(cands), len(cands)), '<u4'); hi_w = np.zeros((len(cands), len(cands)), '<u4')
for a in range(len(cands)):
    pr = pred[a]
    for b in range(len(cands)):
        if a == b or not np.isfinite(dist[a, b]): continue
        m = 0; j = pr[cands[b]]
        while j >= 0 and j != cands[a]:
            if real_stop[j] and st[j] >= 0: m |= 1 << int(st[j])
            j = pr[j]
        lo_w[a, b] = m & 0xFFFFFFFF; hi_w[a, b] = m >> 32
mins = np.where(np.isfinite(dist), np.minimum(np.round(dist / 60), 65534), 65535).astype('<u2')
pts = [[ABBR[R.state_names[st[i]]], R.stop_name[i][:48], round(float(xy[i][1]), 4), round(float(xy[i][0]), 4)] for i in cands]
out = {'points': pts, 'minutes_b64': base64.b64encode(mins.tobytes()).decode(), 'n': len(cands),
       'state_order': [ABBR[x] for x in R.state_names],
       'pass_lo_b64': base64.b64encode(lo_w.tobytes()).decode(), 'pass_hi_b64': base64.b64encode(hi_w.tobytes()).decode(),
       'note': 'shortest scheduled ride + walk time over the Nov 12-Dec 1 2026 network; no waiting or boarding time'}
json.dump(out, open(sys.argv[1], 'w'), separators=(',', ':'))
print(f'wrote {sys.argv[1]}: {len(cands)}^2 matrix, unreachable pairs {int((mins == 65535).sum())}', file=sys.stderr)
