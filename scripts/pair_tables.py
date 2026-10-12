"""Pair deadline tables: can a node still collect two owed states, in some order, and finish?

ride_search keeps a node while every owed state is collectable on its own, L[y][stop] >= t. The run-1 chain
passed that at every step and was still dead from Denver onward: 21 owed pairs at Denver and 42 at Salt Lake
City could not be collected in either order (pair_probe.py, docs/LONGRUNS.md). The per-state test cannot see
it, so the search spent 2600 s and 83000 nodes below a chain that had already lost.

The pair test is exact and uses nothing but the scans the search already trusts. L[y] is one reverse scan
seeded from y's stops with L_end. Seed it from y's stops with L[z] instead:

    L[y->z][s] = latest you can be at s and still collect y, then z, then finish

A node at (stop, t) owing y and z is dead if t > max(L[y->z][stop], L[z->y][stop]). Nothing is estimated.

Stored as P[stop, y, z] = max of the two orders, as float32 seconds relative to the deadline D (a float32
epoch would round to two minutes; relative to D it is exact to a tenth of a second over the whole span).
The diagonal is +inf so a state is never paired with itself. 48 x 47 scans, run in parallel and cached on
disk under a key of every array the scans read, so a changed router or deadline rebuilds rather than hits.

    python3 pair_tables.py            build or load, then validate: the 237 control must lose nothing and
                                      the run-1 chain must die where pair_probe said it did
"""
import hashlib, os, time
import numpy as np
from time_router import N_STATES
import backward as B

HERE = os.path.dirname(os.path.abspath(__file__))

BUILD_VERSION = 'pairs-v1'
_W = {}      # worker state, inherited by fork


def _latest_from(F, D, span, nxt):
    lat, ok, k0, k1 = F.layer(nxt, False, D - span * 3600, None)
    eff, _ = F.through(ok, k0, k1, np.ones(F.R.N, bool))
    return np.maximum(lat, eff)


def _row(y):
    """every L[y->z] for one y, relative to D, float32"""
    F, D, span, L, st_stops = _W['F'], _W['D'], _W['span'], _W['L'], _W['st_stops']
    out = np.full((N_STATES, F.R.N), -np.inf, dtype=np.float32)
    for z in range(N_STATES):
        if z == y: continue
        nxt = {s: float(L[z][s]) for s in st_stops[y] if L[z][s] > -np.inf}
        if nxt: out[z] = (_latest_from(F, D, span, nxt) - D).astype(np.float32)
    return y, out


def fingerprint(R, F, D, span, L_end, L):
    h = hashlib.sha1()
    fa = R._fa
    for arr in (fa['dep'], fa['arr'], fa['cfrom'], fa['cto'], fa['ctrip'], np.asarray(R.state), F.ptr, F.frm, F.w, F.x):
        h.update(np.ascontiguousarray(arr).tobytes())
    # L_end and L are the seeds of every _row scan, so hashing them closes a whole class of key gap at once
    # instead of enumerating config and hoping the list is complete. Two gaps it closes, found by review:
    #
    #   --end. END_ST appeared nowhere in the key, so `--end ME` with the same dates produced the same key
    #   and loaded the Vermont table. Every P value then reads "collect y, then z, then reach Vermont" while
    #   pruning a search that has to reach Maine, and the cache hit returns before L_end is even looked at.
    #
    #   BUS48_MIN_TRANSFER. It is applied inside csa_rev at scan time rather than baked into dep/arr/F.w, so
    #   a router rebuilt at a different transfer time yields byte-identical arrays and the old key. A table
    #   built at 5 min and served to a search running at 3 is up to 120 s STRICTER per seam, and the
    #   control's tightest margin is 108 s at Trinidad CO. That run prunes the 237 route and nothing about
    #   the invocation looks like a table change, so no gate re-runs.
    #
    # Both are cheap to hash because both callers already hold L: it is the same tables the search prunes
    # with. Anything that moves a scan (the end state, the transfer time, the span, the deadline, the walk
    # speed, the feed set) moves L, and therefore moves the key.
    for arr in (L_end, L):
        h.update(np.ascontiguousarray(np.asarray(arr, dtype=np.float64)).tobytes())
    h.update(repr((float(D), float(span), N_STATES, BUILD_VERSION)).encode())
    # backward.py and csa.c are the scan; this file's source is not hashed, so a fix to the validation below
    # does not throw away ten minutes of tables. Bump BUILD_VERSION when _row or the P layout changes.
    for src in ('backward.py', 'csa.c'):
        p = os.path.join(HERE, src)
        if os.path.isfile(p): h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


class PairTables:
    def __init__(self, R, D, span=260, L_end=None, L=None, cache_dir=None, workers=None, verbose=True):
        self.R, self.D = R, float(D)
        F = B.RevFast(R)
        st_stops = [[] for _ in range(N_STATES)]
        for s in range(R.N):
            if R.state[s] >= 0: st_stops[int(R.state[s])].append(s)
        cache_dir = cache_dir or os.path.join(HERE, '..', 'out')
        # Required, not optional, because they are now part of the key. Building them here instead would
        # mean paying for them before every cache hit, which is most of what the cache saves, and both
        # callers already have them in hand: they are the tables the search prunes with.
        if L is None or L_end is None:
            raise ValueError('pass L_end and L. They are what the cache key is built from, because they '
                             'are what encodes the end state, the transfer time, the span and the '
                             'deadline. Without them the key cannot tell a Vermont table from a Maine one.')
        key = fingerprint(R, F, D, span, L_end, L)
        path = os.path.join(cache_dir, f'pairs_{key}.npy')
        if os.path.exists(path):
            self.P = np.load(path, mmap_mode='r')
            if verbose: print(f'pair tables from cache ({os.path.basename(path)})', flush=True)
            return
        t0 = time.time()
        _W.update(F=F, D=float(D), span=span, L=L, st_stops=st_stops)
        yz = np.full((N_STATES, N_STATES, R.N), -np.inf, dtype=np.float32)
        import multiprocessing as mp
        n = workers or max(1, (os.cpu_count() or 2) - 2)
        with mp.get_context('fork').Pool(n) as pool:
            for k, (y, row) in enumerate(pool.imap_unordered(_row, range(N_STATES)), 1):
                yz[y] = row
                if verbose and k % 8 == 0:
                    print(f'  pair tables: {k}/{N_STATES} rows in {time.time() - t0:.0f} s', flush=True)
        P = np.maximum(yz, yz.transpose(1, 0, 2))            # best order, [y, z, stop]
        del yz
        idx = np.arange(N_STATES); P[idx, idx, :] = np.inf
        P = np.ascontiguousarray(P.transpose(2, 0, 1))        # [stop, y, z]: one node reads one 9 KB block
        tmp = path + f'.{os.getpid()}.tmp.npy'
        np.save(tmp, P); os.replace(tmp, path)
        self.P = np.load(path, mmap_mode='r')
        if verbose: print(f'pair tables built in {time.time() - t0:.0f} s with {n} workers, cached as '
                          f'{os.path.basename(path)}', flush=True)

    def worst(self, stop, t, owed):
        """(margin seconds, y, z) of the tightest owed pair at this node; margin < 0 means dead"""
        o = np.asarray(owed, dtype=np.int64)
        if len(o) < 2: return np.inf, -1, -1
        sub = np.asarray(self.P[stop])[np.ix_(o, o)] - np.float32(t - self.D)
        i = int(np.argmin(sub)); a, b = divmod(i, len(o))
        return float(sub.flat[i]), int(o[a]), int(o[b])

    def dead(self, stop, t, owed):
        return self.worst(stop, t, owed)[0] < 0


def resolve_stop(R, name):
    """Exact-name matches for a stop, all of them. 2955 names in the router map to more than one stop
    (Huntington Bus Stop is 755 and 3322, one per feed), so `stop_name.index` and `stops_matching()[0]`
    silently pick one. Callers get the list and must decide, out loud."""
    ex = [i for i, n in enumerate(R.stop_name) if n == name]
    if not ex: raise ValueError(f'no stop named exactly {name!r}')
    return ex


def check_path(R, path, start=None):
    """Refuse a pickle whose stop indices belong to a different router.

    Stop indices are router-local. A pickle written by one build and read by another lands every leg on some
    other stop without an error: the first control test in pair_probe read Houston as the final leg and
    Hanover as Detroit, and called every node dead. Trip keys are feed identifiers and survive a rebuild, so
    each ride is checked against this router: its trip must depart `frm` and arrive at `to` at the recorded
    time. A walk must be a footpath this router has. Returns a list of problems, empty when the path fits."""
    from collections import defaultdict
    bad = []
    if start is not None and path and R.stop_name[path[0][1]] != start:
        bad.append(f'first stop is {R.stop_name[path[0][1]]!r}, pickle says {start!r}')
    by_trip = defaultdict(list)
    need = {leg[0] for leg in path if leg[0] is not None}
    for k in range(len(R.dep)):
        if R.ctrip[k] in need: by_trip[R.ctrip[k]].append(k)
    for i, leg in enumerate(path, 1):
        trip, frm, to, bt, at = leg[:5]
        if not (0 <= frm < R.N and 0 <= to < R.N):
            bad.append(f'leg {i}: stop index out of range'); continue
        if trip is None:
            if frm != to and not any(j == to for j, _w in R.foot.get(frm, ())) \
                    and not any(j == frm for j, _w in R.foot.get(to, ())):
                bad.append(f'leg {i}: no footpath {R.stop_name[frm][:24]} -> {R.stop_name[to][:24]}')
            continue
        cs = by_trip.get(trip)
        if not cs: bad.append(f'leg {i}: trip {trip} not in this router'); continue
        seg = leg[6] if len(leg) > 6 else None
        if seg:
            # connection indices are router-local as well: both must be in range and on this trip
            if not all(0 <= int(k) < len(R.dep) and R.ctrip[int(k)] == trip for k in seg):
                bad.append(f'leg {i}: its connections {tuple(seg)} are not trip {trip} in this router')
                continue
        # frm is where the node stood; ride_search boards at it or at any stop a footpath reaches from it
        # (leg 1 of the run-1 chain stands at Huntington 755 and boards at Huntington 3322)
        near = {frm} | {j for j, _w in R.foot.get(frm, ())}
        if not any(int(R.cfrom[k]) in near for k in cs):
            bad.append(f'leg {i}: trip {trip} never leaves {R.stop_name[frm][:24]} or anywhere walkable from it')
        walked = len(leg) > 5 and leg[5] is not None and leg[5] >= 0     # a walk-in's clock includes the walk
        if not any(int(R.cto[k]) == to and (walked or abs(float(R.arr[k]) - at) < 1) for k in cs):
            bad.append(f'leg {i}: trip {trip} does not reach {R.stop_name[to][:24]} at the recorded time')
    return bad


def leg_states(R, leg, trip_conns):
    """Every state a leg is in. From 9081646 a leg carries seg = (board connection, alight connection) and
    that stretch is exact, loops included; older legs fall back to the trip's connections by time."""
    trip, frm, to, bt, at = leg[:5]
    walk = leg[5] if len(leg) > 5 else None
    seg = leg[6] if len(leg) > 6 else None
    out = set()
    if trip is not None:
        if seg:
            lo_, hi_ = sorted((float(R.dep[seg[0]]), float(R.dep[seg[1]])))
            ks = [k for k in trip_conns.get(trip, ()) if lo_ <= R.dep[k] <= hi_]
        else:
            ks = [k for k in trip_conns.get(trip, ()) if bt <= R.dep[k] and R.arr[k] <= at]
        for k in ks:
            for s_ in (int(R.cfrom[k]), int(R.cto[k])):
                if R.state[s_] >= 0: out.add(int(R.state[s_]))
    if R.state[to] >= 0: out.add(int(R.state[to]))
    if walk is not None and walk >= 0: out.add(int(walk))
    return out


def main():
    import argparse, pickle
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from time_router import cached_router
    from common import ABBR
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default='2026-11-05T00:54')
    ap.add_argument('--by', default='2026-11-14T22:54')
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--end', default='VT')
    ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--days', type=int, default=20)
    ap.add_argument('--control', default='../out/hun_ms_meteor.pkl')
    ap.add_argument('--control-at', default='2026-11-05T00:30')
    ap.add_argument('--control-start', default='Huntington Bus Stop')
    ap.add_argument('--route', default='../out/deep31.pkl')
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    R = cached_router(datetime.fromisoformat(a.at).date(), a.days)
    ab = lambda x: ABBR[R.state_names[x]]
    inv = {v: k for k, v in ABBR.items()}
    end_st = R.state_names.index(inv[a.end])
    F = B.RevFast(R)
    st_stops = [[s for s in range(R.N) if R.state[s] == y] for y in range(N_STATES)]
    L_end = _latest_from(F, D, a.span, {s: D for s in st_stops[end_st]})
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        nxt = {s: float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
        if nxt: L[y] = _latest_from(F, D, a.span, nxt)
    PT = PairTables(R, D, a.span, L_end=L_end, L=L)

    # Falsification: every node of the control, from its first leg, must survive. It finishes inside D.
    import time_search as ts_
    from time_search import Search
    tc = datetime.fromisoformat(a.control_at).replace(tzinfo=tz).timestamp()
    order = pickle.load(open(a.control, 'rb'))['order']
    tried = []
    for hun_ in resolve_stop(R, a.control_start):      # every exact match, not the first; keep the fastest
        S = Search(R, hun_, tc, [], 1)
        ts_._R, ts_._START, ts_._T0, ts_._SELF, ts_._BASE, ts_._END = R, hun_, tc, S, None, None
        fin_, legs_ = S.evaluate(order)
        tried.append((fin_, hun_, legs_))
    fin, hun, legs = min(tried, key=lambda x: x[0])
    print(f'control start {a.control_start!r}: stops ' + ', '.join(f'{h} finishes {(f - tc) / 3600:.2f} h'
          for f, h, _ in tried) + f'; using {hun}', flush=True)
    from collections import defaultdict
    trip_conns = defaultdict(list)
    for k in range(len(R.dep)): trip_conns[R.ctrip[k]].append(k)
    have = {int(R.state[hun])} if R.state[hun] >= 0 else set()
    tight = (np.inf, None)
    n_nodes = killed = 0
    for i, l in enumerate(legs, 1):
        if l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            have |= {int(R.state[R.cto[k]]) for k in trip_conns.get(trip, ()) if bt <= R.dep[k] and R.arr[k] <= at
                     and R.state[R.cto[k]] >= 0}
            for s_ in (bs, al):
                if R.state[s_] >= 0: have.add(int(R.state[s_]))
            stop, t = al, at
        elif l[0] == 'walk':
            _, frm, to, t0w, t1w = l[:5]
            if R.state[to] >= 0: have.add(int(R.state[to]))
            stop, t = (frm if to >= R.first_virtual else to), t1w
        else:
            continue
        owed = [y for y in range(N_STATES) if y not in have]
        m, y, z = PT.worst(stop, t, owed)
        n_nodes += 1
        if m < tight[0]: tight = (m, f'leg {i} {R.stop_name[stop][:24]} {ab(y)}&{ab(z)}' if y >= 0 else '')
        if m < 0:
            killed += 1
            print(f'  CONTROL KILLED at leg {i}: {R.stop_name[stop][:28]}, {ab(y)} & {ab(z)} miss by {-m / 3600:.1f} h')
    print(f'control: {len(have)}/{N_STATES} states, {n_nodes} nodes, {killed} killed; tightest pair margin '
          f'{tight[0] / 3600:+.2f} h ({tight[1]})', flush=True)

    # The run-1 chain must die, and where pair_probe said: Denver, CA & WA by 15.5 h.
    if a.route and os.path.exists(a.route):
        d = pickle.load(open(a.route, 'rb'))
        bad = check_path(R, d['path'], d.get('start'))
        if bad:
            print(f'REFUSED {a.route}: its stop indices do not fit this router ({len(bad)} problems)')
            for b in bad[:5]: print('   ', b)
            return
        have = set()
        for i, leg in enumerate(d['path'], 1):
            trip, frm, to, bt, at = leg[:5]
            if not have and R.state[frm] >= 0: have.add(int(R.state[frm]))
            have |= leg_states(R, leg, trip_conns)
            col = set(d['collected']) if i == len(d['path']) else have
            owed = [y for y in range(N_STATES) if y not in col]
            m, y, z = PT.worst(to, at, owed)
            print(f'  chain ride {i:2d} {R.stop_name[to][:26]:26s} {len(col):2d} held  tightest '
                  + (f'{ab(y)}&{ab(z)} {m / 3600:+.1f} h' if y >= 0 else '-') + ('   DEAD' if m < 0 else ''))


if __name__ == '__main__':
    main()
