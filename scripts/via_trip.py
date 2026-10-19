"""Force a specific scheduled trip, then optionally continue a 48-state search.

Finds the earliest way from --start to board a trip matching --via (agency/route
substring), rides it to --alight (default: last stop of that trip), and reports
covered states. With --budget, runs time_search from the alight for whatever
states are still missing.

usage:
  python3 via_trip.py --start "Dallas I-30" --at 2026-11-06T18:00 --tz America/Chicago \
      --via "Dallas I-30 -> Gastonia" --alight Charlotte
  python3 via_trip.py --start "Huntington Bus Stop" --at 2026-11-05T00:30 --tz America/New_York \
      --via "Dallas I-30 -> Gastonia" --alight Charlotte --seed ../out/hun_ms_meteor.pkl \
      --budget 300 --workers 4 --out ../out/via_expreso.pkl
"""
import argparse, pickle, sys
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES, MIN_TRANSFER, ABBR
from time_search import Search


def find_trips(R, via):
    """(fi, tid, trip_dict) whose agency/route contain --via (case-insensitive)."""
    q = via.lower(); out = []
    for fi, f in enumerate(R.feeds):
        for tid, t in f.trips.items():
            blob = f"{t.get('agency', '')} {t.get('route', '')} {t.get('headsign', '')}".lower()
            if q in blob: out.append((fi, tid, t))
    return out


def trip_stop_indices(R, fi, tid):
    f = R.feeds[fi]; t = f.trips[tid]
    return [R.idx[f.stops[s[1]][0]] for s in t['stops'] if f.stops[s[1]][0] in R.idx]


def earliest_board(R, start, t0, matches):
    """Earliest (board_stop, board_dep, trip_key, alightable_stops) onto any matching trip instance."""
    boardable = set()
    for fi, tid, t in matches:
        boardable.update(trip_stop_indices(R, fi, tid))
    if not boardable:
        return None
    # one CSA to every stop that appears on a matching trip
    out, pred, best = R.scan({start: (t0, None)}, boardable)
    if not out:
        return None
    best_opt = None
    # connections of matching trips, keyed by trip_key
    want = {(fi, tid) for fi, tid, _ in matches}
    for k, key in enumerate(R.ctrip):
        fi, tid, di = key
        if (fi, tid) not in want: continue
        a = int(R.cfrom[k]); dep = float(R.dep[k])
        if a not in out: continue
        arr, ltrip = out[a]
        need = 0 if ltrip == key else MIN_TRANSFER
        if arr + need > dep: continue
        # alight: every later stop on this trip instance (connections share trip_key)
        alights = []
        for k2 in range(k, len(R.ctrip)):
            if R.ctrip[k2] != key: continue
            alights.append((int(R.cto[k2]), float(R.arr[k2])))
        if not alights: continue
        opt = (dep, arr, a, key, alights)
        if best_opt is None or opt[0] < best_opt[0] or (opt[0] == best_opt[0] and opt[1] < best_opt[1]):
            best_opt = opt
    return best_opt


def pick_alight(R, alights, alight_q):
    """Choose alight stop from (stop, arr_time) list. Prefer name match; else last."""
    if not alight_q:
        return alights[-1]
    q = alight_q.lower()
    hits = [(s, t) for s, t in alights if q in R.stop_name[s].lower()]
    return hits[-1] if hits else alights[-1]


def ride_states(R, key, board, alight):
    """States touched while riding trip_key from board stop to alight stop."""
    fi, tid, _ = key; f = R.feeds[fi]; t = f.trips[tid]
    ids = [R.idx[f.stops[s[1]][0]] for s in t['stops'] if f.stops[s[1]][0] in R.idx]
    if board not in ids or alight not in ids: return set()
    i, j = ids.index(board), ids.index(alight)
    seen = set()
    for k in ids[min(i, j):max(i, j) + 1]:
        if R.state[k] >= 0: seen.add(int(R.state[k]))
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--start', required=True)
    ap.add_argument('--at', required=True)
    ap.add_argument('--tz', default='America/Chicago')
    ap.add_argument('--via', required=True, help='substring matched against agency + route + headsign')
    ap.add_argument('--alight', default='', help='alight stop name substring (default: last stop of the trip)')
    ap.add_argument('--days', type=int, default=16)
    ap.add_argument('--seed', help='seed pickle for the post-via search')
    ap.add_argument('--seed-states', help='comma state/@stop order for the post-via search')
    ap.add_argument('--budget', type=int, default=0, help='seconds of time_search after the forced ride (0 = report only)')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    t0 = datetime.fromisoformat(a.at).replace(tzinfo=ZoneInfo(a.tz))
    print('loading feeds…', flush=True)
    R = TimeRouter(load_feeds(), t0.date(), a.days)
    cands = R.stops_matching(a.start)
    if not cands: sys.exit(f'no start matching {a.start!r}')
    start = cands[0]
    print('start', R.stop_name[start], R.abbr[start])

    matches = find_trips(R, a.via)
    if not matches: sys.exit(f'no trip matching --via {a.via!r}')
    print(f'matched {len(matches)} trip template(s):')
    for fi, tid, t in matches[:8]:
        print(f'  [{R.feeds[fi].name}] {t["agency"]}: {t["route"][:70]}')

    caught = earliest_board(R, start, t0.timestamp(), matches)
    if caught is None: sys.exit('cannot reach any boarding stop of a matching trip in time')
    dep, arrive_board, board, key, alights = caught
    alight, at = pick_alight(R, alights, a.alight)
    fi, tid, di = key
    tinfo = R.feeds[fi].trips[tid]
    print('\nFORCED RIDE')
    print(f'  board  {R.fmt_time(dep, board)}  {R.stop_name[board]}, {R.abbr[board]}')
    print(f'         (arrived {R.fmt_time(arrive_board, board)}, wait {int((dep - arrive_board) / 60)} min)')
    print(f'  alight {R.fmt_time(at, alight)}  {R.stop_name[alight]}, {R.abbr[alight]}')
    print(f'  trip   {tinfo["agency"]}: {tinfo["route"][:80]}')
    print(f'  elapsed to alight {round((at - t0.timestamp()) / 3600, 1)} h')

    via_states = ride_states(R, key, board, alight)
    start_st = int(R.state[start])
    done = via_states | ({start_st} if start_st >= 0 else set())
    # also count states reached on the way to the board stop
    to_board, legs_to_board = R.route(start, t0.timestamp(), [f'@#{board}'])
    if to_board is not None:
        # rough: states on rides to board
        for l in legs_to_board:
            if l[0] != 'ride': continue
            _, trip, bs, bt, al, att = l
            done |= ride_states(R, trip, bs, al)
    print('states on via ride:', sorted(ABBR[R.state_names[s]] for s in via_states))
    print('states done (via + approach):', len(done), sorted(ABBR[R.state_names[s]] for s in done))
    missing = [s for s in range(N_STATES) if s not in done]
    print('still missing:', len(missing), sorted(ABBR[R.state_names[s]] for s in missing))

    if a.budget <= 0:
        if a.out:
            pickle.dump(dict(via=dict(key=key, board=board, dep=dep, alight=alight, at=at),
                             done=done, missing=missing), open(a.out, 'wb'))
        return

    # continue search from alight for remaining states
    inv = {ABBR[n]: n for n in R.state_names}
    if a.seed_states:
        seed = [x.strip() if x.strip().startswith('@') else R.state_names.index(inv[x.strip()])
                for x in a.seed_states.split(',')]
    elif a.seed:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order']
                if isinstance(x, (int, np.integer)) and x < N_STATES]
    else:
        seed = list(missing)
    seed = [x for x in seed if (isinstance(x, str) or x in missing)]
    print(f'\nsearching {len(missing)} remaining states from alight, budget {a.budget}s…', flush=True)
    S = Search(R, alight, at, [], a.workers, done=done, fixed_start=True)
    order, f, legs = S.run(seed, a.budget)
    print('FINAL', round((f - t0.timestamp()) / 3600, 1), 'h (from original start)')
    print(R.describe(legs[:12]), '\n…' if len(legs) > 12 else '')
    if a.out:
        pickle.dump(dict(finish=f, legs=legs, order=order, via=dict(key=key, board=board, alight=alight),
                         t0=t0.timestamp(), start=start), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
