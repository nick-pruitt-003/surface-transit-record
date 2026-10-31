"""Would quadruple tables kill the branches proofB kept alive? (Oct 31 2026, option 1 of docs/proof_attempt.md.)

The full quad table is C(48,4) = 194580 rows, ~46 GB and about a day to build. Before paying that, test it where it
has to work: on proofB's logged branches (deep chains the search kept for hours), compute exact quad margins for
the quads most likely to bind, lazily, and see whether any goes negative where every triple is still positive.

Built the way the triples are built from the pairs. T[x, y, z][s] (the full triple table) is the latest you can be
at s and still collect x, y, z in the best order and finish. One reverse scan seeded from w's stops with T[x, y, z]
gives the latest anywhere to collect w first, then the triple; the max over which of the four goes first is the
quad table Q[w, x, y, z][stop]. A node past it is dead, exactly, like every other table here (guard=False).

Per branch: every triple of its owed states is a lookup, so the triple margin is exact over all of them. The quads
tested are the K tightest triples, each extended by every other owed state. A negative quad margin is a proof the
branch is dead; a positive one says only that these quads do not kill it.

The branch clock is the log's "h spent", printed to 0.1 h, so it is taken 0.05 h early (more permissive). Several
stops can share a printed name: the most permissive of them is used. Leaf script: nothing imports it.

usage (from scripts/, after build_triples.py for the same deadline):
  python3 quad_probe.py ../out/proofB.log --at 2026-11-09T00:00 --by 2026-11-22T14:27 --tz America/Denver \
      --end MN --days 22 --limit 326.45 --min-depth 19
"""
import argparse, os, re, time
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR
import backward as B
from pair_tables import PairTables, _latest_from, triple_index, full_paths

_W = {}


def _init(router_args, D, span, tri_path, st_stops):
    R = cached_router(*router_args, verbose=False)
    _, idx3 = triple_index()
    _W.update(F=B.RevFast(R), D=D, span=span, T=np.load(tri_path, mmap_mode='r'), idx3=idx3, st_stops=st_stops,
              N=R.N)


def _first_then(item):
    """w first, then the triple (a, b, c): latest at every stop, relative to D"""
    w, (a, b, c) = item
    F, D, span, T, st_stops = _W['F'], _W['D'], _W['span'], _W['T'], _W['st_stops']
    row = T[int(_W['idx3'][a, b, c])]
    nxt = {s: D + float(row[s]) for s in st_stops[w] if np.isfinite(row[s])}
    if not nxt: return item, np.full(_W['N'], -np.inf, dtype=np.float32)
    return item, (_latest_from(F, D, span, nxt) - D).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--at', required=True); ap.add_argument('--by', required=True)
    ap.add_argument('--tz', required=True); ap.add_argument('--end', required=True)
    ap.add_argument('--days', type=int, default=20); ap.add_argument('--span', type=float, default=260)
    ap.add_argument('--limit', type=float, required=True, help="the run's limit, hours from --at (the log's 'limit')")
    ap.add_argument('--min-depth', type=int, default=19)
    ap.add_argument('--k', type=int, default=4, help='tightest triples extended to quads per branch')
    ap.add_argument('--workers', type=int, default=12)
    a = ap.parse_args()
    import multiprocessing as mp
    tz = ZoneInfo(a.tz)
    when = datetime.fromisoformat(a.at).replace(tzinfo=tz)
    D = datetime.fromisoformat(a.by).replace(tzinfo=tz).timestamp()
    router_args = (when.date(), a.days)
    R = cached_router(*router_args)
    code = {ABBR[R.state_names[y]]: y for y in range(N_STATES)}
    end_st = code[a.end]
    F = B.RevFast(R)
    st_stops = {x: [i for i in range(R.N) if R.state[i] == x] for x in range(N_STATES)}
    L_end = _latest_from(F, D, a.span, {int(s): D for s in st_stops[end_st]})
    L = np.full((N_STATES, R.N), -np.inf)
    for y in range(N_STATES):
        nxt = {int(s): float(L_end[s]) for s in st_stops[y] if L_end[s] > -np.inf}
        if nxt: L[y] = _latest_from(F, D, a.span, nxt)
    PT = PairTables(R, D, a.span, L_end=L_end, L=L, router_args=router_args)
    tri_path, done_path = full_paths(PT.cache_dir, PT.key)
    if not (os.path.exists(done_path) and np.load(done_path).all()):
        raise SystemExit(f'full triple table incomplete for pair key {PT.key}: run build_triples.py first')
    T = np.load(tri_path, mmap_mode='r'); _, idx3 = triple_index()
    from itertools import combinations
    pool = mp.get_context('spawn').Pool(a.workers, initializer=_init,
                                        initargs=(router_args, D, a.span, tri_path, PT.st_stops))
    cache = {}
    t_start = when.timestamp()
    pat = re.compile(r'\[\s*(\d+)s\]\s+(\d+)/48 states,\s+([\d.]+) h spent, at (.+?), \d+ rides.*owes ([A-Z,]+)')
    rows = []
    for line in open(a.log, encoding='utf-8', errors='replace'):
        m = pat.search(line)
        if not m or int(m[2]) < a.min_depth: continue
        n, spent, stop, owes = int(m[2]), float(m[3]), m[4].strip(), m[5].split(',')
        cands = [i for i in range(R.N) if R.stop_name[i] == stop] or \
                [i for i in range(R.N) if R.stop_name[i].startswith(stop)]
        owed = sorted(code[c] for c in owes if c in code and code[c] != end_st)
        if not cands or len(owed) < 4: continue
        rel = t_start + (spent - 0.05) * 3600 - D            # node clock relative to D, taken early
        t0 = time.time()
        pair = min(float(np.max([PT.P[s, y, z] for s in cands])) for y, z in combinations(owed, 2)) - rel
        tri = {}
        for k in combinations(owed, 3):
            tri[k] = float(np.max(T[int(idx3[k])][cands])) - rel
        tight = sorted(tri, key=tri.get)[:a.k]
        quads = {tuple(sorted(t + (w,))) for t in tight for w in owed if w not in t}
        need = {(w, tuple(sorted(set(q) - {w}))) for q in quads for w in q} - set(cache)
        for item, row in pool.imap_unordered(_first_then, sorted(need), chunksize=2):
            cache[item] = row[cands].copy()
        qm = {q: float(np.max(np.maximum.reduce([cache[(w, tuple(sorted(set(q) - {w})))] for w in q]))) - rel
              for q in quads}
        qmin = min(qm, key=qm.get)
        name = lambda ks: '+'.join(ABBR[R.state_names[x]] for x in ks)
        rows.append((n, pair / 3600, tri[tight[0]] / 3600, qm[qmin] / 3600))
        print(f'{n:2d}/48 {stop[:24]:24s} owes {len(owed):2d}  pair {pair / 3600:+6.1f}  '
              f'triple {tri[tight[0]] / 3600:+6.1f} ({name(tight[0])})  quad {qm[qmin] / 3600:+6.1f} ({name(qmin)})  '
              f'{len(quads)} quads, {len(need)} scans, {time.time() - t0:.0f} s', flush=True)
    pool.close(); pool.join()
    r = np.array([x[1:] for x in rows])
    print(f'\n{len(rows)} branches: dead by pair {int((r[:, 0] < 0).sum())}, by triple {int((r[:, 1] < 0).sum())}, '
          f'by tested quads {int((r[:, 2] < 0).sum())}; median margin pair {np.median(r[:, 0]):.1f} h, '
          f'triple {np.median(r[:, 1]):.1f} h, quad {np.median(r[:, 2]):.1f} h', flush=True)


if __name__ == '__main__':
    main()
