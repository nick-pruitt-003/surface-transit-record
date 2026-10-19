"""Write-ups of every route at or under the record, re-evaluated on the current data (docs/routes.md).

For each route: the leg table, and the facts that say where time could still come from, all read off the
timetable rather than estimated:

  miss penalty  for every ride, how much later you reach its alighting stop on the next departure from the same
                stop that gets there at all. About 24 h is a once-daily anchor; an hour or so is a frequent service.
  waits         every gap over an hour before a ride, and what the ride is (an anchor wait is slack that cannot
                be spent unless something upstream moves by a whole service interval).
  tight         every connection under 20 minutes.
  marginal      how much earlier the route finishes when one state is dropped and the same order re-timed.

Leaf script: nothing imports it.  python3 route_report.py > ../docs/routes_data.md   (from scripts/)
"""
import pickle, sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
import time_search as ts
from common import ABBR

R = cached_router(date(2026, 11, 5), 20, verbose=False)
inv = {v: k for k, v in ABBR.items()}
st = lambda a: R.state_names.index(inv[a])
DEP, CFROM, CTO = np.asarray(R.dep), np.asarray(R.cfrom), np.asarray(R.cto)
tid = {}; CT = np.array([tid.setdefault(k[:2] + (k[2],), len(tid)) for k in R.ctrip], dtype=np.int64)


def miss_penalty(bs, bt, al, at):
    """Arrival at `al` on the next departure from `bs` after `bt` that reaches it, minus `at` (hours)."""
    k0, k1 = np.searchsorted(DEP, bt + 1), np.searchsorted(DEP, bt + 72 * 3600)
    best = None
    for k in k0 + np.nonzero(CFROM[k0:k1] == bs)[0]:
        if best is not None and DEP[k] > best: break
        k2 = np.searchsorted(DEP, DEP[k] + 60 * 3600)
        hit = np.nonzero((CT[k:k2] == CT[k]) & (CTO[k:k2] == al))[0]
        if len(hit):
            a = R.arr[k + hit[0]]
            best = a if best is None else min(best, a)
    return None if best is None else (best - at) / 3600


def report(name, start, t0, order, end=None, fixed=True, note=''):
    S = ts.Search(R, start, t0, [], 1, end=end)
    ts.bind(R, start, t0, S, end=end)
    if not fixed:   # best start day over the week, at that day's latest clock
        b = S.settle(order); start = b[1]; t0 = S.latest_start(start, b[2], order)
        S = ts.Search(R, start, t0, [], 1, end=end); ts._START, ts._T0, ts._SELF = start, t0, S
    f, legs = S.evaluate(order)
    rides = [l for l in legs if l[0] == 'ride']
    first = rides[0][3]
    assert S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]
    print(f'\n## {name}: {(f - first) / 3600:.2f} h\n')
    if note: print(note + '\n')
    print(f'First bus {R.fmt_time(first, rides[0][2])} from {R.stop_name[rides[0][2]]}; finish {R.fmt_time(f, rides[-1][4])} '
          f'at {R.stop_name[legs[-1][2] if legs[-1][0] == "walk" else legs[-1][4]]}.\n')
    print('| # | depart | from | arrive | to | service | wait before | miss penalty |')
    print('|---|---|---|---|---|---|---|---|')
    prev = None; waits = []; tight = []; n = 0
    for l in legs:
        if l[0] == 'walk':
            prev = l[4]; continue
        _, trip, bs, bt, al, at = l; n += 1
        ag, rt, hs = R.trip_info[(trip[0], trip[1])]
        w = (bt - prev) / 3600 if prev is not None else None
        mp = miss_penalty(bs, bt, al, at)
        svc = f'{ag}: {rt or hs}'.replace('|', '/')[:60]
        print(f'| {n} | {R.fmt_time(bt, bs)} | {R.stop_name[bs][:34]} | {R.fmt_time(at, al)} | {R.stop_name[al][:34]} | {svc} | '
              f'{"" if w is None else f"{w:.2f} h"} | {"none in 72 h" if mp is None else f"+{mp:.1f} h"} |')
        if w is not None and w >= 1: waits.append((w, n, R.stop_name[bs], svc, mp))
        if w is not None and w < 20 / 60: tight.append((w * 60, n, R.stop_name[bs], svc))
        prev = at
    print('\n**Waits over an hour** (slack; spendable only if the ride after it is not an anchor):\n')
    for w, n, s, svc, mp in sorted(waits, reverse=True):
        print(f'- {w:.1f} h at {s} before leg {n} ({svc}); miss penalty {"none" if mp is None else f"+{mp:.1f} h"}')
    print('\n**Connections under 20 minutes:** ' + ('; '.join(f'leg {n} at {s} ({m:.0f} min)' for m, n, s, _ in tight) or 'none'))
    res = []
    for s in range(N_STATES):
        if s == end: continue
        S2 = ts.Search(R, start, t0, [], 1, done=[s], end=end); ts._SELF = S2
        f2, l2 = S2.evaluate([x for x in order if x != s])
        if f2 != float('inf') and S2.all_states(l2) and f - f2 > 60: res.append(((f - f2) / 3600, ABBR[R.state_names[s]]))
    ts._SELF = S
    print('\n**Marginal state cost** (finish earlier when that state is dropped, same order): '
          + (', '.join(f'{a} {h:.1f} h' for h, a in sorted(res, reverse=True)) or 'none over a minute; anchors absorb every single-state saving'))
    return (f - first) / 3600


if __name__ == '__main__':
    out = {}
    w = pickle.load(open('../out/res_wheeling.pkl', 'rb'))
    out['Wheeling'] = report('Wheeling (Ohio Coach 04:00 passage, transposed)', R.stop_name.index(w['start']), w['t0'], w['order'],
                             note='HANDOFF 20. The 03:00 passage (verified) is one hour longer; the 04:00 rests on transposed running times.')
    c = pickle.load(open('../out/res_starttest.pkl', 'rb'))
    out['control'] = report('Control (Huntington -> Vermont line)', R.stop_name.index(c['start']), c['t0'], c['order'])
    # MEX: the control's order with Vermont moved ahead of Maine and the finish in Portland ME (HANDOFF 23)
    mex = [x for x in c['order'] if x not in (st('VT'), st('ME'))] + ['@Hanover (Hanover Inn)', '@White River Junction Bus Station', '@Boston South Station', st('ME')]   # WRJ is in VT
    out['MEX'] = report('MEX (control start, Vermont mid-route, finish Portland ME)', R.stop_name.index(c['start']), c['t0'], mex,
                        end=st('ME'), fixed=False, note='HANDOFF 23, rebuilt here from its description: the control order, then Hanover, Advance Transit to White River Junction (VT), Greyhound to Boston, Portland ME. Start day re-chosen: on the control route day this part falls on a Saturday, when Advance Transit runs a reduced schedule without the 17:10 that makes the 17:55 Greyhound.')
    sher = R.stops_matching('Sheridan WY Taco Bell')[0]
    # X_TOL's logged order is pruned, and pruning depends on the exact path, so on today's data it drops states.
    # Rebuild the route by pinning every stop the logged run alighted at, in order, then the Vermont line.
    import re
    xtol = []
    for line in open('../docs/cloud_tol.txt', encoding='utf-8'):
        m = re.search(r'->  d\d+ \w+ \d\d:\d\d  (.*), (?:[A-Z]{2}|None)   \[', line)
        if m and re.match(r'^d\d+ ', line) and (not xtol or xtol[-1] != '@' + m.group(1)): xtol.append('@' + m.group(1))
    xtol.append(st('VT'))
    out['X_TOL'] = report('X_TOL (Sheridan -> Vermont line via Toledo)', sher, datetime(2026, 11, 5, tzinfo=ZoneInfo('America/Denver')).timestamp(),
                          xtol, end=st('VT'), fixed=False, note='HANDOFF 22 / docs/cloud_tol.txt order, start day re-chosen on today\'s data.')
    j = pickle.load(open('../out/shapes/join.pkl', 'rb'))
    out['X'] = report('X (Sheridan -> Mississippi line at Southaven)', R.stop_name.index(j['start']), j['t0'], j['order'], end=st('MS'),
                      note='HANDOFF 28: route X rebuilt as the fastest head (22 states, to Hanover) joined to the fastest tail.')
    # RX: found by the unguided sweep (run 01, 240.0) and a focused search (Oct 2 2026): X with the West at the end.
    lv = R.stops_matching('Primm Bus Stop (702 Shuttles)')[0]   # 702 Shuttles 10:50 (Oct 2 screenshot): 50 min better than the Las Vegas 10:00 Greyhound
    # pin Baton Rouge: Delta Bus Lines from Memphis (MS on the way), then the 23:55 Orlando bus straight to Tallahassee and Jacksonville (Nick, Oct 2). Ties the Lafayette backtrack, and is bookable
    rx = [st(a) if len(a) == 2 else a for a in 'NV,CA,AR,TN,@Baton Rouge Bus Station,LA,FL,VT,ME,KY,MI,ND,SD,OR,WY'.split(',')]
    out['RX'] = report('RX (Primm NV -> Sheridan WY)', lv, datetime(2026, 11, 4, 23, 0, tzinfo=ZoneInfo('America/Los_Angeles')).timestamp(),
                       rx, end=st('WY'), fixed=False, note='docs/sweep.md: the unguided sweep found its family (240.0); a focused search moved the start to Las Vegas; the 702 Shuttles 10:50 from Primm (Oct 2) starts it 50 min later for the same finish.')
    # The Hanover spine (sweep 2 runs 13 and 07, focused Oct 2): Ledyard Lot start (Vermont on foot at 06:10), New
    # England, Southeast, Michiana, Fargo, the I-90 bus, the West, Southwest Chief, BeeLine, Houston; two finishes.
    led = R.stops_matching('Ledyard Lot')[0]; t_led = datetime(2026, 11, 5, 6, 0, tzinfo=ZoneInfo('America/New_York')).timestamp()
    hx = lambda o: [a if a.startswith('@') else st(a) for a in o.split(',')]   # '@stop' items are pins
    out['HAR'] = report('HAR (Hanover -> Forrest City AR)', led, t_led, hx('NH,VT,ME,GA,WV,MI,ND,NE,MT,OR,CA,OK,FL,AR'),
                        note='docs/sweep.md: sweep 2 run 13 (239.8, from Portland ME), focused: start moved to Ledyard Lot. Hours count from the first bus (06:23); from the 06:10 walk add 0.2 h.')
    out['HMS'] = report('HMS (Hanover -> Biloxi MS)', led, t_led, hx('NH,VT,ME,GA,WV,MI,ND,NE,WY,OR,AZ,KS,LA,AR,FL,MS'),
                        note='docs/sweep.md: sweep 2 run 07 (242.1), focused. Hours count from the first bus (06:23); from the 06:10 walk add 0.2 h.')
    # HT: HMS without its forced Mississippi finish. Mississippi comes at Tupelo on the Memphis -> Birmingham bus, so
    # the route ends at Tallahassee (Oct 2: HMS's focused search had been given --end MS from its sweep run).
    # HT starts at Foley Park (Vermont end of the Ledyard Bridge) and walks 16 min to the Hanover Inn for the 06:40
    # Dartmouth Coach (Nick, Oct 3); 06:19 is the latest start under the 5-minute rule. New Hampshire comes on the coach.
    fp = R.stops_matching('Foley Park at the Vermont end')[0]; t_fp = datetime(2026, 11, 5, 6, 19, tzinfo=ZoneInfo('America/New_York')).timestamp()
    out['HT'] = report('HT (Foley Park VT -> Tallahassee FL)', fp, t_fp, hx('ME,@Washington Union Station,GA,WV,MI,ND,NE,WY,OR,AZ,KS,LA,AR,MS,FL'),
                       note='Mississippi at Tupelo on the 09:00 Memphis -> Birmingham Greyhound; starts on foot at Foley Park 06:19 (latest that keeps the chain), so 230.10 h from the first step. Hours below count from the first bus, the 06:40 Dartmouth Coach.')
    # NBA: sweep 3 run 22 (240.5), focused with the fixed search (d90d8f0): New Buffalo MI -> Big River Crossing AR line.
    nba = R.stops_matching('New Buffalo Amtrak')[0]; t_nba = datetime(2026, 11, 11, 21, 37, tzinfo=ZoneInfo('America/New_York')).timestamp()
    out['NBA'] = report('NBA (New Buffalo MI -> Arkansas line, Big River Crossing)', nba, t_nba, hx('ND,MO,WA,AZ,OK,LA,FL,ME,VT,WV,MS,AR'),
                        note='Sweep 3 run 22 (240.5 h), focused from its real start stop with the fixed search. Ends on foot at the Arkansas line mid-bridge, inside the bridge hours.')
    print('\n## Summary\n')
    for k, v in out.items(): print(f'- {k}: {v:.2f} h')
