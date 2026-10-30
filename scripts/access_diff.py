"""New-access diff: every timetabled way into and out of the hard states, old data against new (Oct 29 2026).

Step 2 of the after-refresh workflow (memory: targeted-over-sweeps). After a data change, the question is not "is the
best route faster" (retime_routes.py answers that) but "what can a route now do that it could not before", and the
place that matters is the hard states, where a route depends on one or two services. So this lists, exactly, per
state:

  visits   every run of consecutive stops one trip makes inside the state: the stop before it outside the state and
           its departure, the first and last stop inside with their times, the stop after it outside and its arrival,
           and the weekdays it runs. A trip that starts or ends inside the state shows '-' for that side: it gets you
           in or out, not both. A trip that starts and ends inside (city buses) is left out: it is not access.
  walks    every walk into the state: automatic border walk-ins (from which stop, how long) and the end points of
           hand-measured walk links (data/walk_links.csv).

and then diffs two listings: visits that are new, gone, or run on different days, and for each new visit the visit
it replaces between the same outside stops, if any, with both in-state spans, so "faster" is a pair of exact times
rather than a summary number. Nothing is ranked or estimated; a visit is a fact from the timetable.

The week listed is Mon Nov 16 - Sun Nov 22 2026 (after the Portal Bridge gap), from the same router window
retime_routes.py uses (--at 2026-11-09 --days 22), so the cache is shared. Times are each stop's local clock.

usage (from scripts/):
  python3 access_diff.py --rev 40c35ab                diff the data at that commit against the working tree
  python3 access_diff.py --rev 40c35ab --states SD,ND  only these states
  python3 access_diff.py --list out.json [--code DIR] the listing alone (--code: import the router from DIR)

--rev checks the revision out once as a git worktree under out/access_wt/<rev> (data/ is tracked, so it is the
whole old world) and builds its router there, in its own out/ so it cannot prune this checkout's caches. The report
goes to docs/access_<rev>.md. Leaf script: nothing imports it.
"""
import argparse, json, os, subprocess, sys
from collections import defaultdict
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HARD = 'SD,ND,MT,WY,ME,VT,NH,WA,ID,NM,OK,AR,MS,WV'
AT, DAYS = date(2026, 11, 9), 22
WEEK = (date(2026, 11, 16), date(2026, 11, 22))
DOW = 'MTWTFSS'


def listing(states, code_dir, region=None):
    """region: a name for `states` taken as one block (--region), so a trip running from one of them to another
    stays inside and only crossings of the block's outer edge are visits."""
    sys.path.insert(0, code_dir)
    import numpy as np
    from time_router import cached_router
    R = cached_router(AT, DAYS)
    name = lambda i: f'{R.stop_name[i]}, {R.abbr[i] or "?"}'
    if region:
        want = {region}; ab = [region if x in set(states) else x for x in R.abbr]
    else:
        want = set(states); ab = R.abbr
    clock = lambda ts, i: datetime.fromtimestamp(ts, R.stop_zone(i))

    # trips that touch a wanted state, then every connection of those trips, in order
    st = np.array([1 if a in want else 0 for a in ab], dtype=np.int8)
    hit = np.where((st[R.cfrom] == 1) | (st[R.cto] == 1))[0]
    keys = {R.ctrip[k] for k in hit.tolist()}
    conns = defaultdict(list)
    for k, key in enumerate(R.ctrip):
        if key in keys: conns[key].append(k)
    visits = defaultdict(set)   # (state, agency, route, before, dep, first, arr, last, dep, after, arr) -> weekdays
    for key, ks in conns.items():
        ks.sort(key=lambda k: R.dep[k])
        seq = [(int(R.cfrom[ks[0]]), None, float(R.dep[ks[0]]))]   # (stop, arrival, departure)
        for n, k in enumerate(ks):
            nxt = float(R.dep[ks[n + 1]]) if n + 1 < len(ks) else None
            seq.append((int(R.cto[k]), float(R.arr[k]), nxt))
        ag, rt, hs = R.trip_info[(key[0], key[1])]
        i = 0
        while i < len(seq):
            s = ab[seq[i][0]]
            if s not in want: i += 1; continue
            j = i
            while j + 1 < len(seq) and ab[seq[j + 1][0]] == s: j += 1
            first, last = seq[i], seq[j]
            t_in = first[1] if first[1] is not None else first[2]
            day = clock(t_in, first[0]).date()
            # a trip that starts and ends inside the state (city buses, in-state intercity) moves you around in it
            # but is not a way in or out; those were 2014 of Oklahoma's 2055 visits (EMBARK, Tulsa), burying the rest
            if WEEK[0] <= day <= WEEK[1] and (i > 0 or j + 1 < len(seq)):
                hm = lambda ts, stop: clock(ts, stop).strftime('%H:%M') if ts is not None else '-'
                b = seq[i - 1] if i > 0 else None; a = seq[j + 1] if j + 1 < len(seq) else None
                rec = (s, ag or '', rt or hs or '',
                       name(b[0]) if b else '-', hm(b[2], b[0]) if b else '-',
                       name(first[0]), hm(t_in, first[0]), name(last[0]), hm(last[2] if last[2] is not None else last[1], last[0]),
                       name(a[0]) if a else '-', hm(a[1], a[0]) if a else '-')
                visits[rec].add(day.weekday())
            i = j + 1

    # walks into a wanted state: border walk-ins and measured walk-link ends
    walks = set()
    first_virtual = getattr(R, 'first_virtual', R.N); ends = getattr(R, 'link_ends', set())
    for v in range(R.N):
        if ab[v] not in want or not (v >= first_virtual or v in ends): continue
        # a walk-in point is also chained to every stop its base stop walks to (CHAIN_WALKIN), 2997 edges in Maine;
        # list only the walk from the stop the point was built from ('walkin:<base uid>:<ST>')
        sid = R.stop_ids[v]; base = R.idx.get(sid.split(':', 1)[1].rsplit(':', 1)[0]) if sid.startswith('walkin:') else None
        for i, w in R.foot.get(v, ()):
            if ab[i] != ab[v] and (base is None or i == base):
                kind = 'walk-in' if v >= first_virtual else 'walk link'
                walks.add((ab[v], kind, name(i), R.stop_name[v], round(w / 60)))
    return {'visits': [list(k) + [''.join(DOW[d] if d in v else '-' for d in range(7))] for k, v in sorted(visits.items())],
            'walks': sorted(map(list, walks))}


def diff(old, new, states, rev):
    out = [f'# New-access diff: data at {rev} against the working tree', '',
           f'Week Mon {WEEK[0]} - Sun {WEEK[1]}; states {", ".join(states)}. Generated by scripts/access_diff.py. A visit is '
           'one trip\'s run of stops inside the state: outside stop before -> first stop in (arrival) ... last stop in '
           '(departure) -> outside stop after. "-" = the trip starts or ends inside the state.', '']
    fmt = lambda v: (f'{v[3]} {v[4]} -> **{v[5]} {v[6]}** ... **{v[7]} {v[8]}** -> {v[9]} {v[10]}  '
                     f'[{v[1]}: {v[2]}] `{v[11]}`')
    # a visit is its carrier, stops and times; the route text is display only (a reworded note is not a new bus)
    key = lambda v: (v[0], v[1]) + tuple(v[3:11])
    def merged(visits, s):
        # rows that are the same bus (Wonder Bus has a Nashville and a Knoxville row) share a key: union their days
        out = {}
        for v in visits:
            if v[0] != s: continue
            k = key(v)
            if k in out: out[k] = out[k][:11] + [''.join(a if a != '-' else b for a, b in zip(out[k][11], v[11]))]
            else: out[k] = list(v)
        return out
    for s in states:
        ov = merged(old['visits'], s); nv = merged(new['visits'], s)
        ow = {tuple(w) for w in old['walks'] if w[0] == s}; nw = {tuple(w) for w in new['walks'] if w[0] == s}
        added = [nv[k] for k in nv if k not in ov]; gone = [ov[k] for k in ov if k not in nv]
        days = [(ov[k], nv[k]) for k in nv if k in ov and ov[k][11] != nv[k][11]]
        wa = sorted(nw - ow); wg = sorted(ow - nw)
        head = f'## {s}: {len(nv)} visits, {len(nw)} walks'
        if not (added or gone or days or wa or wg):
            out += [head + ' (unchanged)', '']; continue
        out += [head, '']
        if added:
            out.append('New visits:')
            for v in sorted(added, key=lambda v: (v[5], v[6])):
                out.append(f'- {fmt(v)}')
                # the same pass between the same outside stops in the old data, for a faster/slower comparison
                same = [o for o in ov.values() if o[3] == v[3] and o[9] == v[9] and key(o) not in nv]
                for o in same[:3]: out.append(f'  - replaces? {fmt(o)}')
            out.append('')
        if gone:
            out.append('Gone:'); out += [f'- {fmt(v)}' for v in sorted(gone, key=lambda v: (v[5], v[6]))]; out.append('')
        if days:
            out.append('Days changed:'); out += [f'- {fmt(n)} (was `{o[11]}`)' for o, n in days]; out.append('')
        if wa or wg:
            out.append('Walks:'); out += [f'- new {w[1]}: {w[2]} -> {w[3]}, {w[4]} min' for w in wa]
            out += [f'- gone {w[1]}: {w[2]} -> {w[3]}, {w[4]} min' for w in wg]; out.append('')
    return '\n'.join(out) + '\n'


def region_report(states, region, data):
    """Every way across the block's edge, grouped by the states either side, so a set of search slices can be
    checked for completeness against it: a route that passes through the block crosses its edge on one of these."""
    st = lambda nm: nm.rsplit(', ', 1)[-1] if nm != '-' else '-'
    groups = defaultdict(list)
    for v in data['visits']:
        groups[(st(v[3]), st(v[9]))].append(v)
    out = [f'# Every timetabled way into and out of {region} ({", ".join(states)}), Mon {WEEK[0]} - Sun {WEEK[1]}', '',
           'Generated by `scripts/access_diff.py --region`. The states are one block: a trip moving between them stays '
           'inside, and a visit is one trip\'s run of stops inside the block, from the outside stop before it to the '
           'outside stop after. "-" = the trip starts or ends inside the block, so it only gets you in, or only out. '
           'Trips that start and end inside are not listed (not a crossing). Times are each stop\'s local clock; days '
           'are Mon-Sun.', '',
           '## Corridors (states either side of the block)', '',
           '| from | to | services | carriers |', '|---|---|---|---|']
    for (fb, ta), vs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        out.append(f'| {fb} | {ta} | {len(vs)} | {", ".join(sorted({v[1] for v in vs}))} |')
    out += ['', f'Walks over the edge into the block: {len(data["walks"])}', '']
    for w in data['walks']: out.append(f'- {w[1]}: {w[2]} -> {w[3]}, {w[4]} min')
    for (fb, ta), vs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        out += ['', f'## {fb} -> {region} -> {ta}', '']
        for v in sorted(vs, key=lambda v: (v[3], v[4], v[5])):
            out.append(f'- {v[3]} {v[4]} -> **{v[5]} {v[6]}** ... **{v[7]} {v[8]}** -> {v[9]} {v[10]}  '
                       f'[{v[1]}: {v[2]}] `{v[11]}`')
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rev'); ap.add_argument('--list'); ap.add_argument('--code', default=HERE)
    ap.add_argument('--states', default=HARD)
    ap.add_argument('--region', help='a name for --states taken as one block: list every way across its edge '
                    'to docs/region_<name>.md (no diff)')
    a = ap.parse_args()
    states = [s.strip().upper() for s in a.states.split(',') if s.strip()]
    if a.region:
        data = listing(states, a.code, region=a.region)
        rep = os.path.join(ROOT, 'docs', f'region_{a.region}.md')
        open(rep, 'w', encoding='utf-8').write(region_report(states, a.region, data))
        print('report:', rep, f'({len(data["visits"])} crossings, {len(data["walks"])} walks)')
        return
    if a.list:
        json.dump(listing(states, a.code), open(a.list, 'w', encoding='utf-8'), indent=0)
        return
    if not a.rev: ap.error('--rev or --list')
    sha = subprocess.check_output(['git', 'rev-parse', '--short', a.rev], cwd=ROOT, text=True).strip()
    wt = os.path.join(ROOT, 'out', 'access_wt', sha)
    if not os.path.isdir(wt):
        subprocess.check_call(['git', 'worktree', 'add', '--detach', wt, sha], cwd=ROOT)
    tmp = os.path.join(ROOT, 'out', 'access_wt')
    old_json, new_json = os.path.join(tmp, f'{sha}.json'), os.path.join(tmp, 'working.json')
    me = os.path.abspath(__file__)
    for path, code in ((old_json, os.path.join(wt, 'scripts')), (new_json, HERE)):
        print(f'listing {code} ...', flush=True)
        subprocess.check_call([sys.executable, me, '--list', path, '--code', code, '--states', ','.join(states)], cwd=code)
    old = json.load(open(old_json, encoding='utf-8')); new = json.load(open(new_json, encoding='utf-8'))
    rep = os.path.join(ROOT, 'docs', f'access_{sha}.md')
    open(rep, 'w', encoding='utf-8').write(diff(old, new, states, sha))
    print('report:', rep)


if __name__ == '__main__':
    main()
