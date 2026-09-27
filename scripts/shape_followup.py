"""Take the best rotations forward_shapes found and let time_search improve each one. Leaf script.

forward_shapes measures a rotation of the control's order as it stands. A different shape carries the
control's ordering inside it, which was optimised for Huntington, so its measured time is an upper bound on
what that shape can do. time_search is the tool that turned an ordering into the 237 route in the first
place: relocate, reverse, prune, re-time. This hands it each promising rotation as a seed.

Start stops are resolved exactly, not by `stops_matching(x)[0]` as time_search's --start does: the log
truncates names to 38 characters, so the stop must match that prefix AND lie in the rotation's first state,
and when several do the pick is reported against its runner-up.

    python3 shape_followup.py --log ../out/fs_full.log --top 3 --budget 900 --workers 2
"""
import argparse, hashlib, os, pickle, re, time
from datetime import datetime, date
from zoneinfo import ZoneInfo
from time_router import cached_router
from common import ABBR
import time_search as ts
from time_search import Search
import numpy as np
from pick import choose, gate

ROW = re.compile(r'^\s+(\d+) (\w\w)\s+(\w\w)\s+([\d.]+) h\s+(\w{3} \d\d \w{3} \d\d:\d\d)\s+(.*?)(\s+BEATS THE CONTROL)?$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default='../out/fs_full.log')
    ap.add_argument('--top', type=int, default=3, help='rotations to follow up, best first, rotation 0 excluded')
    ap.add_argument('--budget', type=float, default=900)
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--tz', default='America/New_York')
    ap.add_argument('--year', type=int, default=2026)
    ap.add_argument('--tag', default='fwd', help='names the output pickles, so forward and reversed runs do not overwrite each other')
    ap.add_argument('--results', default=None, help='TSV to append one line per finished rotation to, and to read '
                    'on start so rotations already in it are skipped: the resume mechanism for runs that cannot '
                    'survive the night in one process')
    ap.add_argument('--stop-after-min', type=float, default=0, help='start no new rotation after this many '
                    'minutes, so a session ends cleanly inside its container\'s lifetime (0 = no limit)')
    ap.add_argument('--push', action='store_true', help='git commit and push --results after every rotation, so '
                    'a reclaimed container loses at most the rotation in flight')
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    text = open(a.log).read().splitlines()
    ctl = next((l for l in text if l.startswith('control order')), None)
    if ctl is None: raise SystemExit(f'{a.log} has no control order line; did forward_shapes finish?')
    full_ab = ctl.split(',', 1)[1].split()   # as printed: forward_shapes reverses BEFORE printing, so with --reverse this
    # is already the reversed cycle, and full[k:] + full[:k] below is its own rotation k (the gate undoes it, not this)
    rows = []
    for l in text:
        m = ROW.match(l)
        if m: rows.append((float(m.group(4)), int(m.group(1)), m.group(5), m.group(6).strip()))
    if not rows: raise SystemExit(f'{a.log} has no result rows')
    rows.sort()
    # Which run a result belongs to: the cycle the rotations are cut from AND the candidates the log ranked (each
    # rotation's time, departure and start stop), so two logs of one cycle with different sweeps do not share an id.
    # Sorted rows, so the id does not depend on line order. Resume skips only a row with this id.
    run_id = hashlib.sha1((ctl.strip() + '\n' + '\n'.join(f'{k} {el:.2f} {when} {name}' for el, k, when, name in rows)).encode()).hexdigest()[:12]
    reversed_ = '(REVERSED)' in ctl
    # rotation 0 of the forward cycle IS the control; rotation 0 of the reversed cycle is a new shape
    picks = [r for r in rows if reversed_ or r[1] != 0]
    if a.top: picks = picks[:a.top]
    done = set()
    if a.results and os.path.exists(a.results):
        for l in open(a.results):
            p = l.rstrip('\n').split('\t')
            # rows written before the id column existed carry none, so they never match and are redone: safe direction
            if len(p) > 7 and p[0] == a.tag and p[1].isdigit() and p[7] == run_id: done.add(int(p[1]))
        if done: print(f'{len(done)} {a.tag} rotations of run {run_id} already in {a.results}; skipping them', flush=True)
    picks = [r for r in picks if r[1] not in done]
    print(f'{len(rows)} rotations in the log; following up {len(picks)}: '
          + ', '.join(f'rot {k} {el:.2f} h' for el, k, _, _ in picks), flush=True)

    R = cached_router(date(2026, 9, 24), 20)
    inv = {v: k for k, v in ABBR.items()}
    full = [R.state_names.index(inv[x]) for x in full_ab]
    # The control through THIS router before any rotation counts. A cloud container builds its own router
    # from data/, so a different feed, date window or code version must show up here and not as a
    # plausible number in the results.
    control = full[::-1] if reversed_ else full
    hun = [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']
    t_ctl = datetime(2026, 9, 24, 0, 54, tzinfo=ZoneInfo('America/New_York')).timestamp()
    gate('control from Huntington 00:54 on this router',
         lambda: min((R.finish(h, t_ctl, control) - t_ctl) / 3600 for h in hun), 237.34, 0.01)
    t_start = time.time()
    os.makedirs('../out', exist_ok=True)
    for el, k, when, name in picks:
        if a.stop_after_min and time.time() - t_start > a.stop_after_min * 60:
            print(f'\nstop-after-min {a.stop_after_min:g} reached; {len(picks)} rotations were queued, '
                  f'the rest resume next session', flush=True); break
        order = full[k:] + full[:k]
        hits = [i for i, s in enumerate(R.stop_name) if s[:38] == name and R.state[i] == order[0]]
        if not hits:
            print(f'\nrot {k}: no stop in {full_ab[k]} named {name!r}; skipped', flush=True); continue
        st = choose(hits, key=lambda i: i, label=f'rot {k} start stop', show=lambda i: f'{i} {R.stop_name[i]}')
        t0 = datetime.strptime(f'{a.year} {when}', '%Y %a %d %b %H:%M').replace(tzinfo=tz).timestamp()
        print(f'\n=== rot {k}: {full_ab[k]} .. {full_ab[k - 1]}, forward_shapes {el:.2f} h from '
              f'{R.stop_name[st]} {when}; time_search {a.budget:.0f} s ===', flush=True)
        S = Search(R, st, t0, [], a.workers)
        order_, f, legs = S.run(order, a.budget)
        if f == float('inf'):
            print(f'rot {k}: FINAL unreachable', flush=True); continue
        h = S.best_elapsed / 3600
        print(f'rot {k}: FINAL {h:.2f} h from first bus'
              + ('   BEATS THE CONTROL' if h < 237.34 else f'   (+{h - 237.34:.2f} h on the control)'), flush=True)
        print(R.describe(legs), flush=True)
        pickle.dump(dict(order=order_, finish=f, legs=legs, start=S.start_name(legs), t0=S.t0,
                         elapsed=S.best_elapsed, rotation=k), open(f'../out/followup_{a.tag}_rot{k}.pkl', 'wb'))
        if a.results:
            ab_ = lambda x: ABBR[R.state_names[x]] if isinstance(x, (int, np.integer)) else str(x)
            first = next((l for l in legs if l[0] == 'ride'), None)
            with open(a.results, 'a') as fh:
                fh.write('\t'.join([a.tag, str(k), f'{el:.2f}', f'{h:.2f}', S.start_name(legs),
                                     R.fmt_time(first[3], first[2]) if first else '', ' '.join(ab_(x) for x in order_), run_id])
                         + '\n')
            if a.push:
                import subprocess
                subprocess.run(['git', 'add', a.results], check=False)
                subprocess.run(['git', 'commit', '-q', '-m', f'followup {a.tag} rot {k}: {h:.2f} h'], check=False)
                r_ = subprocess.run(['git', 'push', '-q'], check=False)
                print(f'pushed rot {k}' if r_.returncode == 0 else f'PUSH FAILED rot {k} rc={r_.returncode}', flush=True)


if __name__ == '__main__':
    main()
