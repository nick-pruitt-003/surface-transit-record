"""Re-time the best routes on any date window and say which leg broke (Oct 27 2026).

Timetables change before any real travel date (the City of New Orleans moved two hours, the Fargo -> Sioux Falls
Jefferson went from a daily 15:50 to 14:30 Thu-Mon, and RX fell from 235.6 h to unusable without anyone touching
it). This answers "do our routes still work for this window, and if not, where did each one break" in one command.

  python3 retime_routes.py --save                      record docs/route_baselines.json from the result pickles in
                                                       ROUTES (each on its own reference window). Tracked in git, so
                                                       the baselines travel with the repo; out/ does not.
  python3 retime_routes.py --at 2026-11-09 [--days 22] [--routes X,Control] [--out ../docs/retime_2026-11-09.md]
                                                       re-time every baseline on that window, from the current feeds

For each route and each of the 7 start days from --at it settles two orders and keeps the better: the baseline's
alighting stops pinned in sequence, with each state target placed where the baseline collected it (finds a break
exactly: a pin that can no longer be reached in time shows up as a missed departure), and the route's own state order
(catches a different connection that works as well). Hours count
from the first move: an opening walk before the first bus (Moorhead -> Fargo) is included at its walking time.

The report per route: hours against the baseline, start day, states missing, then the legs that differ from the
baseline: departures that moved, rides that disappeared or appeared, and every new wait of 20 h or more (a missed
once-a-day departure, which is how a route usually breaks).

Leaf script: nothing imports it. Routes are evaluated, not searched; follow a broken one up with time_search or
ride_search (docs/sweep.md has the recipes).
"""
import argparse, json, os, pickle, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from time_router import cached_router, N_STATES
import time_search as ts
from common import ABBR

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, '..', 'out')
BASE = os.path.join(HERE, '..', 'docs', 'route_baselines.json')
ROUTES = [  # name, result pickle under out/, reference window (start date, days), note
    ('X', 'res_x.pkl', (date(2026, 11, 9), 22), 'Sheridan WY -> Moorhead MN, the best route (CLAUDE.md)'),
    ('Moorhead AR', 'sweep10/f_moorhead.pkl', (date(2026, 11, 9), 22), 'Fargo (walk from Moorhead) -> Big River Crossing AR line, sweep 10'),
    ('Control', 'control_nov/eval_stl.pkl', (date(2026, 11, 4), 27), 'Huntington WV -> Vermont line'),
    ('Record', 'wide/rec_true.pkl', (date(2026, 11, 19), 20), 'White River Junction -> Huntington, the record shape'),
    ('Wheeling', 'retime/fwh.pkl', (date(2026, 11, 9), 22), 'Wheeling, Kentucky moved next to Ohio (Oct 25)'),
    ('Tornado Greeley', 'sweep9/run_33.pkl', (date(2026, 11, 9), 22), 'sweep 9 run 33: Tornado Houston -> Biloxi -> Live Oak -> Meteor'),
    ('Fulton Meteor', 'sweep9/focus/frun_05.pkl', (date(2026, 11, 9), 22), 'sweep 9 run 05 focused: Tornado + Live Oak -> Silver Meteor'),
]
WEEK = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def start_stop(R, name):
    m = R.stops_matching(name)
    return next((i for i in m if R.stop_name[i] == name), m[0] if m else None)


def first_move(legs):
    """Clock start: the first bus, less the walking time of any walk before it (timed to arrive as it leaves)."""
    walk = 0
    for l in legs:
        if l[0] == 'ride': return l[3] - walk
        walk += l[4] - l[3]
    return legs[0][3]


def summarise(R, legs, t_first):
    rides = []
    for l in legs:
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        ag, rt, hs = R.trip_info[(trip[0], trip[1])]
        rides.append(dict(frm=R.stop_name[bs], to=R.stop_name[al], agency=ag, route=rt or hs or '',
                          dep=R.fmt_time(bt, bs).split(' ', 1)[1], arr=R.fmt_time(at, al).split(' ', 1)[1],
                          dep_h=round((bt - t_first) / 3600, 2), arr_h=round((at - t_first) / 3600, 2)))
    return rides


def save():
    out, routers = [], {}
    for name, rel, win, note in ROUTES:
        p = os.path.join(OUT_DIR, rel)
        if not os.path.exists(p): print(f'skip {name}: no {p}'); continue
        if win not in routers: routers[win] = cached_router(*win, verbose=False)
        R = routers[win]; d = pickle.load(open(p, 'rb'))
        st = start_stop(R, d['start'])
        # the stored clock first (a route that opens with a walk needs it), then the clock just before the first bus
        # that eval_pickles uses, then the best start day of the reference window
        cands = [d['t0']] + ([d['finish'] - d['elapsed'] - 600] if 'finish' in d and 'elapsed' in d else [])
        f = legs = None
        for t0 in cands:
            S = ts.Search(R, st, t0, [], 1); ts.bind(R, st, t0, S)
            f, legs = S.evaluate(d['order'])
            if f < 1e18 and legs and S.all_states(legs): break
        else:
            day0 = datetime(win[0].year, win[0].month, win[0].day, tzinfo=ZoneInfo('America/New_York')).timestamp()
            S = ts.Search(R, st, day0, [], 1); ts.bind(R, st, day0, S); b = S.settle(d['order'])
            if b is None: print(f'skip {name}: does not evaluate on its reference window'); continue
            f, legs = b[3], b[4]
        t1 = first_move(legs)
        order = [x if isinstance(x, str) else ABBR[R.state_names[x]] for x in d['order']]
        # the pinned sequence: every alighting stop in turn, each state target of the order placed just before the stop
        # of the leg that first collected it (a state is often collected on the way: the City of New Orleans takes
        # Kentucky at Fulton before Memphis, so KY after @Memphis would send the router on looking for it); walk-ins
        # such as the Mississippi line are not pins, so they stay targets
        targets = [x for x in d['order'] if not isinstance(x, str)]
        seq, owed = [], set(S.missing([]))
        for i, l in enumerate(legs):
            stop = l[4] if l[0] == 'ride' else l[2]
            now = set(S.missing(legs[:i + 1]))
            seq += [ABBR[R.state_names[x]] for x in targets if x in owed - now]
            owed = now
            if l[0] == 'ride' and (not seq or seq[-1] != '@' + R.stop_name[stop]): seq.append('@' + R.stop_name[stop])
        if legs[-1][0] == 'walk': seq.append('@' + R.stop_name[legs[-1][2]])   # a walk-in finish (Moorhead, the VT line)
        first_dt = datetime.fromtimestamp(t1, ZoneInfo('UTC'))
        out.append(dict(name=name, note=note, source=rel, start=d['start'], window=[win[0].isoformat(), win[1]],
                        hours=round((f - t1) / 3600, 2), first_move_utc=first_dt.isoformat(),
                        start_weekday=R.fmt_time(t1, st).split(' ')[1], order=order, pinned=seq,
                        rides=summarise(R, legs, t1)))
        print(f'{name}: {out[-1]["hours"]:.2f} h, {len(seq)} pinned targets, {len(out[-1]["rides"])} rides')
    json.dump(dict(saved=date.today().isoformat(), routes=out), open(BASE, 'w', encoding='utf-8'), indent=1)
    print(f'wrote {os.path.normpath(BASE)}')


def settle(S, order):
    b = S.settle(order)   # best of 7 start days, each at its latest clock; legs are timed at that clock
    return None if b is None or not b[4] else (b[3], b[4])


def diff(base, rides):
    """Legs that differ from the baseline, matched by (from, to, carrier)."""
    key = lambda r: (r['frm'], r['to'], r['agency'])
    old = {key(r): r for r in base}; new = {key(r): r for r in rides}
    lines = []
    for r in base:
        n = new.get(key(r))
        if n is None: lines.append(f"- gone: {r['agency']} {r['frm']} {r['dep']} -> {r['to']} {r['arr']}")
        elif n['dep'][-5:] != r['dep'][-5:] or n['arr'][-5:] != r['arr'][-5:]:
            lines.append(f"- moved: {r['agency']} {r['frm']} -> {r['to']}: was {r['dep']} -> {r['arr']}, now {n['dep']} -> {n['arr']}")
    for r in rides:
        if key(r) not in old: lines.append(f"- new: {r['agency']} {r['frm']} {r['dep']} -> {r['to']} {r['arr']}")
    prev = None
    for r in rides:   # waits of 20 h or more: a missed once-a-day departure
        if prev is not None and r['dep_h'] - prev >= 20:
            lines.append(f"- **{r['dep_h'] - prev:.1f} h wait** before {r['agency']} {r['frm']} {r['dep']} (missed a daily departure?)")
        prev = r['arr_h']
    return lines


def retime(at, days, names, out_path):
    base = json.load(open(BASE, encoding='utf-8'))
    R = cached_router(at, days, verbose=False)
    tz = ZoneInfo('America/New_York')
    rep = [f'# Re-timed routes: window {at.isoformat()} + {days} days', '',
           f'Feeds as of {datetime.now(tz).strftime("%Y-%m-%d %H:%M")}; baselines saved {base["saved"]}. '
           'Hours from the first move (an opening walk counts). Start day: the best of the 7 from the window start.', '',
           'A route that starts on or reaches the Northeast Corridor before Mon Nov 16 2026 meets the Portal Bridge gap '
           '(no early Washington -> Boston Acelas), so "no complete route" for the Record in an earlier window is that, '
           'not a timetable change.', '',
           '| route | baseline h | now h | change | start | missing |', '|---|---|---|---|---|---|']
    detail = []
    inv = {v: k for k, v in ABBR.items()}
    tok = lambda x: x if x.startswith('@') else R.state_names.index(inv[x])
    for b in base['routes']:
        if names and b['name'] not in names: continue
        st = start_stop(R, b['start'])
        if st is None:
            rep.append(f"| {b['name']} | {b['hours']:.1f} | start stop gone | | | |"); continue
        day0 = datetime(at.year, at.month, at.day, tzinfo=tz).timestamp()
        S = ts.Search(R, st, day0, [], 1); ts.bind(R, st, day0, S)
        tries = []
        for label, order in (('pinned', [tok(x) for x in b['pinned']]), ('own order', [tok(x) for x in b['order']])):
            try: r = settle(S, order)
            except Exception as e: print(f"{b['name']} {label}: {e}", file=sys.stderr); r = None
            if r: tries.append((r[0] - first_move(r[1]), label, r))
        if not tries:
            rep.append(f"| {b['name']} | {b['hours']:.1f} | no complete route | | | |")
            detail += [f"## {b['name']}: no complete route in this window", '', b['note'], '']; continue
        h, label, (f, legs) = min(tries, key=lambda x: x[0])
        h /= 3600; t1 = first_move(legs)
        miss = [ABBR[R.state_names[s]] for s in S.missing(legs)]
        rides = summarise(R, legs, t1)
        ch = h - b['hours']
        rep.append(f"| {b['name']} | {b['hours']:.1f} | {h:.1f} | {'+' if ch >= 0 else ''}{ch:.1f} | {R.fmt_time(t1, st)} | {', '.join(miss) or 'none'} |")
        d = diff(b['rides'], rides)
        detail += [f"## {b['name']}: {h:.2f} h ({label}; baseline {b['hours']:.2f} h)", '', b['note'], '']
        if d and abs(ch) < 0.05 and not any('wait**' in x for x in d):
            d = ['- same finish; these legs differ only as equal-time alternatives on this start day:'] + ['  ' + x for x in d]
        detail += (d or ['- every leg as in the baseline']) + ['']
        print(f"{b['name']}: {h:.2f} h (baseline {b['hours']:.2f}), {len(d)} differences", flush=True)
    text = '\n'.join(rep + [''] + detail)
    if out_path: open(out_path, 'w', encoding='utf-8').write(text); print(f'wrote {out_path}')
    print(text)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--save', action='store_true'); ap.add_argument('--at'); ap.add_argument('--days', type=int, default=22)
    ap.add_argument('--routes', help='comma list of route names (default all)'); ap.add_argument('--out')
    a = ap.parse_args()
    if a.save: save()
    elif a.at: retime(date.fromisoformat(a.at), a.days, set(a.routes.split(',')) if a.routes else None, a.out)
    else: ap.error('--save or --at')
