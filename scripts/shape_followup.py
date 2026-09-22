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
import argparse, pickle, re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from time_router import cached_router
from common import ABBR
import time_search as ts
from time_search import Search
from pick import choose

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
    a = ap.parse_args()
    tz = ZoneInfo(a.tz)
    text = open(a.log).read().splitlines()
    ctl = next((l for l in text if l.startswith('control order')), None)
    if ctl is None: raise SystemExit(f'{a.log} has no control order line; did forward_shapes finish?')
    full_ab = ctl.split(',', 1)[1].split()
    rows = []
    for l in text:
        m = ROW.match(l)
        if m: rows.append((float(m.group(4)), int(m.group(1)), m.group(5), m.group(6).strip()))
    if not rows: raise SystemExit(f'{a.log} has no result rows')
    rows.sort()
    picks = [r for r in rows if r[1] != 0][:a.top]
    print(f'{len(rows)} rotations in the log; following up {len(picks)}: '
          + ', '.join(f'rot {k} {el:.2f} h' for el, k, _, _ in picks), flush=True)

    R = cached_router(date(2026, 9, 24), 20)
    inv = {v: k for k, v in ABBR.items()}
    full = [R.state_names.index(inv[x]) for x in full_ab]
    for el, k, when, name in picks:
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


if __name__ == '__main__':
    main()
