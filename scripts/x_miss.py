"""If you miss a leg, for route X as booked (docs/x_itinerary_nov12.xlsx). Leaf script: nothing imports it;
run from scripts/: python3 x_miss.py

Route X (the sheet's own legs, not the router's choice between them).

For every ride in the X itinerary tab: start at its boarding stop one minute after it leaves, owe the states the
sheet has not collected yet in X's order, and route. Cost is against catching it (same stop, ten minutes before),
so the router's shorter Moorhead walk cancels out.
"""
import os, re, sys, openpyxl
from datetime import datetime, timedelta
os.chdir(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, '.')
from time_router import cached_router
from common import ABBR

SHEET = '../docs/x_itinerary_nov12.xlsx'
R = cached_router(datetime.fromisoformat('2026-11-05T00:54').date(), 20)
inv = {v: k for k, v in ABBR.items()}
X = ('MT ID WA OR UT AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA NH VT ME WV OH IN KY TN MS '
     'AR MO IL WI MI IA NE SD ND MN').split()
ALIAS = {'Provo Central Station/Intermodal Hub': 'Provo/Orem (Exit 263)', 'Barstow (Amtrak)': 'Barstow',
         'Chicago (95th - Dan Ryan)': 'Chicago (95th - Dan Ryan)'}
D0 = datetime(2026, 11, 5)


def stop(name):
    name = ALIAS.get(name, name)
    hit = [i for i, s in enumerate(R.stop_name) if s == name]
    if hit: return hit
    # a prefix is only trusted when it names one place: 'Kansas City' prefixes several stations, and routing from all
    # of them at once (and timing the clock in the first one's zone) understates the cost of a miss
    pre = [i for i, s in enumerate(R.stop_name) if s.startswith(name)]
    if len({R.stop_name[i] for i in pre}) > 1: print('ambiguous stop name, add an ALIAS:', name, sorted({R.stop_name[i] for i in pre})[:5]); return []
    return pre


def clock(cell, s):
    m = re.match(r'(?:by )?d(\d+) \w{3} ~?(\d\d):(\d\d)( ET)?', cell)
    d, h, mi, et = int(m[1]), int(m[2]), int(m[3]), m[4]
    z = R.stop_zone(s)
    if et: from zoneinfo import ZoneInfo; z = ZoneInfo('America/New_York')
    return (D0 + timedelta(days=d - 1, hours=h, minutes=mi)).replace(tzinfo=z).timestamp()


def when(t, s):
    d = datetime.fromtimestamp(t, R.stop_zone(s))
    return f'd{(d.date() - D0.date()).days + 1} {d:%a %H:%M}'


wb = openpyxl.load_workbook(SHEET); ws = wb['X itinerary']
got = {'WY'}; rows = []
for r in range(3, ws.max_row + 1):
    v = [ws.cell(r, c).value for c in range(1, 14)]
    if not isinstance(v[0], int): continue
    n, dep, frm, arr, to, how, new = v[0], v[1], v[2], v[4], v[5], v[7], v[10]
    ride = not how.startswith(('local', 'on foot'))
    if ride:
        ss = stop(frm)
        if not ss: print('no stop', frm); got |= set((new or '').split()); continue
        t = clock(dep, ss[0])
        owe = [R.state_names.index(inv[x]) for x in X if x not in got]
        g, rl = R.route(ss, t + 60, owe)
        c, _ = R.route(ss, t - 600, owe)
        first = next((x for x in rl if x[0] == 'ride'), None) if g else None
        rec = ''
        if first:
            _, tr, b, d2, a, _ = first; ag, rt, hs = R.trip_info[(tr[0], tr[1])]
            rec = f'{when(d2, b)} {ag}: {R.stop_name[b]} -> {R.stop_name[a]}'
        cost = round((g - c) / 3600) if g and c else None
        fin = 'no finish in the window' if not g else f'+{cost} h' if cost else 'no loss'
        rows.append((n, f'{dep} {how.split(":")[0]}', frm, to, fin, cost, rec))
        print(rows[-1], flush=True)
    got |= set((new or '').split())

ms = wb['If you miss a leg']
ms.delete_rows(1, ms.max_row)
ms.append(['#', 'missed', 'from', 'to', 'next best', 'cost h', 'recovery starts with'])
for x in rows: ms.append(list(x))
ms.append([])
ms.append([None, 'Recovery keeps the remaining states in route X\'s order, from the missed ride\'s boarding stop one minute after '
           'it leaves; cost is against catching it. Built on the repo data as of Oct 5 2026 (timetable window from Sep 24).'])
wb.save(SHEET)
print('written', len(rows))
