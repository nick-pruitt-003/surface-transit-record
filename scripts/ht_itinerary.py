"""HT as an itinerary to ride: every leg with its local times, how to make each connection, and the quality-of-life
choices and risks found by hand (docs/ht_itinerary.xlsx).

Start day Monday: the chain is daily, so Mon/Tue/Wed starts all give 230.10 h, and a Monday start puts Memphis on a
Wednesday, when MATA's 04:30 Walker bus reaches the Big River Crossing before the 05:45 walk (Saturday it does not).

Leaf script: nothing imports it.   python3 ht_itinerary.py   (from scripts/)
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import time_search as ts
from route_report import R, st
from common import ABBR

ET = ZoneInfo('America/New_York')
START = datetime(2026, 9, 28, 6, 19, tzinfo=ET)          # Monday; 06:19 is the latest start that keeps the chain
ORDER = 'ME,@Washington Union Station,GA,WV,MI,ND,NE,WY,OR,AZ,KS,LA,AR,MS,FL'

# notes keyed by a substring of the leg's from/to stop names (first match wins)
NOTES = [
    ('Foley Park', 'START. Stand at Foley Park (Vermont end of the Ledyard Bridge); Vermont counts here. Walk 0.6 mi via W Wheelock St (16 min). Leave by 06:19 (06:24 with no margin); 06:20 by the 5-minute rule loses the coach and a day.'),
    ('Hanover (Hanover Inn)', 'Dartmouth Coach 06:40, once a day. New Hampshire counts on board.'),
    ('Washington Union Station', 'QoL: stay on the Acela to DC instead of Baltimore; board the Flix at Union Station itself (same station, 2 h wait). Once a day.'),
    ('Michigan line at Michiana', 'Measured run: 4.5 km out (51 min) and 6.9 km back to Carroll Ave (85 min) at Nick\'s 4.1 mph pace. The longest run in any record route.'),
    ('Museum Campus', 'South Shore into Chicago. To the Chicago bus station: walk or CTA (2 km), 4.7 h to spare before the 22:00.'),
    ('Maryville', 'Dead time: the next useful bus is the once-daily 12:40 I-90 bus from Sioux Falls. This loop collects Nebraska, Iowa, Missouri at no cost. Alternative: off at Sioux City, walk the Veterans Bridge into Nebraska (30 min).'),
    ('Salt Lake City (Airport)', 'Arrive SLC Intermodal 02:30; the Salt Lake Express leaves from the airport at 04:45. No transit at that hour: taxi, or walk 6.8 km (~90 min).'),
    ('Las Vegas Bus Terminal', 'Airport to downtown terminal: RTC bus (4 km), 2.3 h to spare before the 14:00.'),
    ('Newton', 'Southwest Chief overnight; BeeLine Newton -> Oklahoma City at 03:00 (once a day) for Oklahoma.'),
    ('Longview', 'Amtrak Thruway bus timed to the Texas Eagle; it waits for the train.'),
    ('Arkansas line on Big River', 'Big River Crossing walk, Arkansas at mid-bridge. Bridge open 06:00-22:00. Weekday MATA from the Greyhound terminal: Walker 04:30 -> Vance & 3rd 05:21, walk 13 min to Central Station. Back: walk to 2nd & Vance, Mallory 07:21 -> Airways 08:03. Weekday backup: route 12 Airways 05:14 -> Florida & Georgia 05:51, walk 19 min to the bridge.'),
    ('Memphis Bus Station', 'Greyhound terminal = Airways Transit Center (3033 Airways Blvd), ~10 km from downtown.'),
    ('Tupelo', 'Mississippi counts at Tupelo on this bus.'),
    ('Tallahassee (CK Steele', 'FINISH (Florida).'),
]


def note_for(a, b):
    if 'Memphis Bus Station' in a and b == 'Memphis':
        return ('Real weekday MATA (the router shows a local-transit proxy here): Walker 04:30 Airways Transit Center -> '
                'Vance & 3rd 05:21, walk 13 min to Central Station for the 05:45 bridge walk. Backup: route 12 Airways 05:14 '
                '-> Florida & Georgia 05:51, walk 19 min to the bridge. Saturday has no service this early.')
    for k, v in NOTES:
        if k in a or k in b: return v
    return ''


def same_trip_exists(leg, N):
    """Does the same service (carrier and route) run from the same stop to the same stop N days later, same times?"""
    import numpy as np
    _, trip, bs, bt, al, at = leg
    key = R.trip_info[(trip[0], trip[1])][:2]
    dep = R._dep_np if hasattr(R, '_dep_np') else np.asarray(R.dep)
    R._dep_np = dep
    t = bt + N * 86400
    for k in range(int(np.searchsorted(dep, t - 60)), int(np.searchsorted(dep, t + 61))):
        if R.cfrom[k] != bs or R.trip_info[R.ctrip[k][:2]][:2] != key: continue
        tr = R.ctrip[k]
        for j in range(k, int(np.searchsorted(dep, at + N * 86400 + 1))):
            if R.ctrip[j] == tr and R.cto[j] == al and abs(R.arr[j] - (at + N * 86400)) <= 60: return True
    return False


def main():
    order = [x if x.startswith('@') else st(x) for x in ORDER.split(',')]
    fp = R.stops_matching('Foley Park at the Vermont end')[0]; t0 = START.timestamp()
    S = ts.Search(R, fp, t0, [], 1); ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, fp, t0, S, None, None
    f, legs = S.evaluate(order)
    assert S.all_states(legs), [ABBR[R.state_names[s]] for s in S.missing(legs)]
    wb = Workbook(); ws = wb.active; ws.title = 'HT itinerary'
    ws.append([f'HT: {(f - t0) / 3600:.2f} h from the first step. Start Monday {START:%b %d} 06:19 at Foley Park VT; '
               f'finish {R.fmt_time(f, legs[-1][4])} at Tallahassee. Times are each stop\'s local time; d-numbers count days from Thu Sep 24 (d5 = Mon Sep 28).'])
    ws['A1'].font = Font(bold=True, size=12)
    hdr = ['#', 'depart', 'from', 'st', 'arrive', 'to', 'st', 'how', 'ride h', 'wait before h', 'new states', 'states', 'notes']
    ws.append(hdr)
    for c in ws[2]: c.font = Font(bold=True)
    seen = {int(R.state[fp])}; prev = None; n = 0; blue = PatternFill('solid', fgColor='D6E4F0'); amber = PatternFill('solid', fgColor='FFF3CD')
    for l in legs:
        if l[0] == 'walk':
            _, a, b, s0, s1 = l
            if s1 - s0 < 300 and not R.walk_collects(b): prev = s1; continue    # skip trivial platform walks
            new = ({int(R.state[b])} - seen) if R.walk_collects(b) else set(); seen |= new
            n += 1
            ws.append([n, R.fmt_time(s0, a), R.stop_name[a], R.abbr[a] or '', R.fmt_time(s1, b), R.stop_name[b], R.abbr[b] or '',
                       'on foot' if (s1 - s0) < 3 * 3600 and (R.walk_collects(b) or b in getattr(R, 'link_ends', ()) or a in getattr(R, 'link_ends', ())) else 'local transit / walk',
                       round((s1 - s0) / 3600, 2), '', ' '.join(sorted(ABBR[R.state_names[x]] for x in new)), len(seen), note_for(R.stop_name[a], R.stop_name[b])])
            ws.cell(ws.max_row, 13).fill = amber if ws.cell(ws.max_row, 13).value else PatternFill()
            prev = s1; continue
        _, trip, bs, bt, al, at = l
        cov = S.covered([l]); new = cov - seen; seen |= cov; n += 1
        ag, rt, hs = R.trip_info[(trip[0], trip[1])]
        ws.append([n, R.fmt_time(bt, bs), R.stop_name[bs], R.abbr[bs] or '', R.fmt_time(at, al), R.stop_name[al], R.abbr[al] or '',
                   f'{ag}: {rt or hs}', round((at - bt) / 3600, 2), '' if prev is None else round((bt - prev) / 3600, 2),
                   ' '.join(sorted(ABBR[R.state_names[x]] for x in new)), len(seen), note_for(R.stop_name[bs], R.stop_name[al])])
        if R.feeds[trip[0]].name == 'extra': ws.cell(ws.max_row, 8).fill = blue
        if ws.cell(ws.max_row, 13).value: ws.cell(ws.max_row, 13).fill = amber
        prev = at
    for col, w in zip('ABCDEFGHIJKLM', (4, 14, 30, 4, 14, 30, 4, 40, 7, 9, 12, 7, 90)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=3):
        row[12].alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'A3'
    ws2 = wb.create_sheet('Start day')
    ws2.append(['Start day', 'Total', 'Memphis falls on', 'Notes'])
    for r in (('Monday (recommended)', '230.10 h', 'Wednesday', 'Memphis on weekday MATA (Walker 04:30 to the bridge); Chicago on a Wednesday, when the extra Four Winds shuttles run (from Oct 28)'),
              ('Tuesday / Wednesday', '230.10 h', 'Thursday / Friday', 'same chain, weekday Memphis'),
              ('Thursday', '230.10 h', 'Saturday', 'no MATA early enough on Saturday: taxi from the Greyhound terminal to the bridge'),
              ('Friday', '230.10 h', 'Sunday', 'Sunday MATA not checked'),
              ('Saturday / Sunday', 'misses Missouri', '', 'the Sioux Falls dead-time ride does not reach Missouri on those days; a detour would be needed')):
        ws2.append(list(r))
    for col, w in zip('ABCD', (22, 16, 18, 110)): ws2.column_dimensions[col].width = w

    # ---- If you miss a leg: replay from the boarding stop one minute after the bus left, same remaining order ----
    ws3 = wb.create_sheet('If you miss a leg')
    ws3.append(['#', 'missed', 'from', 'to', 'next best finish', 'cost h', 'recovery starts with'])
    for c in ws3[1]: c.font = Font(bold=True)
    rides = [(i, l) for i, l in enumerate(legs) if l[0] == 'ride']
    base_f = f
    # the full visiting order (every state, in the order HT first collects it): the pruned ORDER only works on HT's
    # exact path, and a replay from a missed connection takes a different one
    full = []; seen_ = {int(R.state[fp])}
    for x in legs:
        new_ = (S.covered([x]) if x[0] == 'ride' else ({int(R.state[x[2]])} if R.walk_collects(x[2]) else set())) - seen_
        for s_ in sorted(new_, key=lambda z: R.state_names[z]): full.append(s_)
        seen_ |= new_
    for k, (i, l) in enumerate(rides, 1):
        _, trip, bs, bt, al, at = l
        before = legs[:i]; got = S.covered([x for x in before if x[0] == 'ride']) | {int(R.state[fp])}
        for x in before:
            if x[0] == 'walk' and R.walk_collects(x[2]): got.add(int(R.state[x[2]]))
        dc_done = any(x[0] == 'ride' and 'Washington Union Station' in R.stop_name[x[4]] for x in before)
        # Recovery A, go now: HT's remaining path as targets, each leg's new states before its alighting stop, so a
        # later bus to the same stop cannot skip a state the original collected on the way.
        rem = []; seen2 = set(got)
        for x in legs[i:]:
            if x[0] == 'ride': nw = S.covered([x]) - seen2
            else: nw = ({int(R.state[x[2]])} if R.walk_collects(x[2]) else set()) - seen2
            seen2 |= nw
            rem += sorted(nw, key=lambda z: R.state_names[z])
            pin = f'@#{x[4] if x[0] == "ride" else x[2]}'
            if not rem or rem[-1] != pin: rem.append(pin)
        pins = []
        for x in legs[i:]:
            pin = f'@#{x[4] if x[0] == "ride" else x[2]}'
            if not pins or pins[-1] != pin: pins.append(pin)
        best_ = None
        for tgt in (pins, rem):   # pins alone (freest), then pins with each leg's states (cannot skip one)
            S2 = ts.Search(R, bs, bt + 60, [], 1, done=sorted(got)); ts._SELF, ts._START, ts._T0 = S2, bs, bt + 60
            f_, l_ = S2.evaluate(tgt)
            if f_ < 1e18 and S2.all_states(l_) and (best_ is None or f_ < best_[0]): best_ = (f_, l_, 0)
        # Recovery B, wait: the same chain N days later, checked trip by trip (same carrier and route, same times)
        for N in (1, 2, 3):
            if best_ is not None and best_[0] <= base_f + N * 86400: break
            if all(same_trip_exists(x, N) for x in legs[i:] if x[0] == 'ride'):
                best_ = (base_f + N * 86400, [], N); break
        ok = best_ is not None
        f2, l2, waited = best_ if ok else (float('inf'), [], 0)
        ag = R.trip_info[(trip[0], trip[1])][0]
        first = next((x for x in l2 if x[0] == 'ride'), None)
        how = (f'wait {waited} day(s): the same buses run, everything shifts {waited * 24} h' if waited else
               f'{R.fmt_time(first[3], first[2])} {R.trip_info[(first[1][0], first[1][1])][0]}: {R.stop_name[first[2]]} -> {R.stop_name[first[4]]}' if first else '')
        fin = R.fmt_time(f2, legs[-1][4]) if ok and waited else (R.fmt_time(f2, l2[-1][4] if l2[-1][0] == 'ride' else l2[-1][2]) if ok else 'not recoverable in the window')
        ws3.append([k, f'{R.fmt_time(bt, bs)} {ag}', R.stop_name[bs], R.stop_name[al], fin, round((f2 - base_f) / 3600, 1) if ok else '', how])
        c = ws3.cell(ws3.max_row, 6)
        if ok and c.value is not None: c.fill = PatternFill('solid', fgColor='F8D7DA' if c.value >= 20 else 'FFF3CD' if c.value >= 3 else 'D4EDDA')
        ts._SELF, ts._START, ts._T0 = S, fp, t0
    for col, w in zip('ABCDEFG', (4, 34, 30, 30, 18, 7, 90)): ws3.column_dimensions[col].width = w
    ws3.freeze_panes = 'A2'

    # ---- Verify before going: anything not straight from a GTFS feed, and every proxy hop ----
    ws4 = wb.create_sheet('Verify')
    ws4.append(['#', 'leg', 'why it needs checking', 'source / assumption'])
    for c in ws4[1]: c.font = Font(bold=True)
    m = 0
    for l in legs:
        if l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            ag, rt, _ = R.trip_info[(trip[0], trip[1])]
            if R.feeds[trip[0]].name == 'extra':
                m += 1; ws4.append([m, f'{R.fmt_time(bt, bs)} {R.stop_name[bs]} -> {R.stop_name[al]}', f'hand-entered ({ag}): confirm times and days on the carrier site', rt])
        elif l[0] == 'walk' and (l[4] - l[3]) > 20 * 60 and not (R.walk_collects(l[2]) or l[2] in getattr(R, 'link_ends', ()) or l[1] in getattr(R, 'link_ends', ())):
            m += 1; ws4.append([m, f'{R.fmt_time(l[3], l[1])} {R.stop_name[l[1]]} -> {R.stop_name[l[2]]}', 'router local-transit proxy: plan the real bus, walk or taxi', note_for(R.stop_name[l[1]], R.stop_name[l[2]]) or 'see itinerary notes'])
    for extra in (('All GTFS legs', 'feeds are a snapshot (Sep-Oct 2026): re-check every once-daily leg on the carrier site before booking', 'Greyhound, Flix, Jefferson, Barons, Amtrak'),
                  ('Four Winds shuttle (alternative to the Michiana run)', 'return arrival times in Chicago are not published (assumed 1 h 40 min); 21+ with photo ID', 'fourwindscasinoshuttle.com'),):
        m += 1; ws4.append([m, *extra])
    for col, w in zip('ABCD', (4, 60, 70, 110)): ws4.column_dimensions[col].width = w

    # ---- Book ahead: every reservable intercity leg with its date, for pricing ----
    ws5 = wb.create_sheet('Book ahead')
    ws5.append(['day', 'date (Monday start)', 'depart', 'from', 'arrive', 'to', 'carrier', 'service', 'book'])
    for c in ws5[1]: c.font = Font(bold=True)
    LOCAL = ('MATA', 'Michian City', 'Metropolitan Transit Authority of Harris', 'Jacksonville Transportation', 'Transpo', 'On foot',
             'Northern Indiana Commuter', 'Advance Transit', 'Regional Transportation Commission', 'Utah Transit', 'DALLAS AREA')
    tz_of = lambda stop: R.stop_zone(stop)
    for l in legs:
        if l[0] != 'ride': continue
        _, trip, bs, bt, al, at = l
        ag, rt, hs = R.trip_info[(trip[0], trip[1])]
        if any(ag.startswith(x) for x in LOCAL): continue
        d0 = datetime.fromtimestamp(bt, tz_of(bs))
        book = 'Amtrak (reserved)' if ag.startswith('Amtrak') else 'carrier site / app'
        if 'Dartmouth' in ag: book = 'dartmouthcoach.com (reserve)'
        if 'Salt Lake Express' in ag: book = 'saltlakeexpress.com (reserve)'
        if 'BeeLine' in ag: book = 'BeeLine (phone/site)'
        ws5.append([f'day {(d0.date() - START.date()).days + 1}', d0.strftime('%a %b %d'), d0.strftime('%H:%M'), R.stop_name[bs],
                    datetime.fromtimestamp(at, tz_of(al)).strftime('%a %H:%M'), R.stop_name[al], ag, rt or hs, book])
    ws5.append([]); ws5.append(['', 'Walk-up / local (no reservation): Advance Transit, MATA, Michigan City Transit, South Shore Line (ticket at station or app), Houston METRO, JTA, RTC Las Vegas, UTA'])
    for col, w in zip('ABCDEFGHI', (7, 16, 7, 34, 11, 34, 26, 40, 26)): ws5.column_dimensions[col].width = w
    wb.save('../docs/ht_itinerary.xlsx')
    print('wrote ../docs/ht_itinerary.xlsx:', n, 'legs,', round((f - t0) / 3600, 2), 'h')


if __name__ == '__main__':
    main()
