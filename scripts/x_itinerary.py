"""X as an itinerary to ride (docs/x_itinerary.xlsx): Sheridan WY Thursday 22:20 to Moorhead MN on foot the second
Sunday, 232.1 h. Same sheets as attic/ht_itinerary.py; the ending is pinned to Nick's measured 83 min walk from the Fargo
Jefferson station to Moorhead, not the router's Fargo local-transit proxy (MATBUS has no Sunday service).

Leaf script: nothing imports it.   python3 x_itinerary.py   (from scripts/)
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import time_search as ts
from route_report import R, st
from common import ABBR

ET = ZoneInfo('America/New_York'); MT = ZoneInfo('America/Denver')
START = datetime(2026, 11, 5, 22, 10, tzinfo=MT)         # Thursday in the timetable window; 10 min before the 22:20 Jefferson (5 min rule)
TRIP = datetime(2026, 10, 15).date()   # a Thursday that finishes Sun Oct 25, before the Nov 1 clock change; Book ahead shows these dates
ORDER = 'OR,AZ,OK,FL,@Hanover (Hanover Inn),ME,WV,MS,MO,WI,MI,ND,@Moorhead MN 13th Ave N,MN'

# notes keyed by a substring of the leg's from/to stop names (first match wins)
NOTES = [
    ('Sheridan WY Taco Bell', 'START (Wyoming). Jefferson JL 701 boards at the Taco Bell, 1655 Coffeen Ave; stop point approximate, confirm on the ticket. Be there by 22:10.'),
    ('Salt Lake City (Airport)', 'Arrive SLC Intermodal 02:30; the Salt Lake Express leaves from the airport at 04:45. No TRAX that early and no taxis (rules): walk 6.8 km (~90 min), on foot by ~04:05.'),
    ('Las Vegas Bus Terminal', 'Airport to the downtown Greyhound terminal: RTC bus (4 km), 2.3 h to spare before the 14:00.'),
    ('Newton', 'Southwest Chief overnight; BeeLine Newton -> Oklahoma City at 03:00 (once a day) for Oklahoma.'),
    ('Houston Bus Station', 'METRORail Green Line from Central Station Rusk to Magnolia Park, short walk to the Greyhound station.'),
    ('White River Junction', 'Advance Transit Yellow (free) from Main at Allen to Sykes Ave; Vermont counts at White River Junction.'),
    ('Portland, ME', 'Overnight in Portland: 22:45 in, 03:15 out (Concord Coach both ways); the one allowed Boston-Portland round trip.'),
    ('HOLMES at ELVIS PRESLEY', 'Mississippi on foot: 1.3 km from Holmes at Elvis Presley to the state line and back (about 19 min each way), between MATA Crosstown buses.'),
    ('Kenosha', 'Wisconsin by Metra UP-N out and back (Saturday schedule).'),
    ('Four Winds', 'Four Winds Casino shuttle from Chinatown (35th & State / Wentworth): Michigan at New Buffalo. 21+ with photo ID. Return arrival in Chicago is assumed; Saturday service to confirm.'),
    ('Davenport', 'Iowa: get off at Davenport (00:05, bus leaves 00:30) and back on.'),
    ('Moorhead MN 13th Ave N', 'FINISH (Minnesota). Walk 3.7 mi from the Fargo Jefferson station via 12th Ave N to 508 13th Ave N Moorhead (83 min). MATBUS has no Sunday service.'),
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
    fp = R.stops_matching('Sheridan WY Taco Bell')[0]; t0 = START.timestamp()
    S = ts.Search(R, fp, t0, [], 1); ts.bind(R, fp, t0, S)
    f, legs = S.evaluate(order)
    assert S.all_states(legs), [ABBR[R.state_names[s]] for s in S.missing(legs)]
    wb = Workbook(); ws = wb.active; ws.title = 'X itinerary'
    ws.append([f'X: {(f - t0) / 3600:.2f} h from 22:10 (first bus 22:20 MT). Start Thursday at Sheridan WY; '
               f'finish {R.fmt_time(f, legs[-1][2] if legs[-1][0] == "walk" else legs[-1][4])} at Moorhead MN. Times are local at each stop; d-numbers count days from Thu Sep 24.'])
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
    ws2.append(['Start day', 'Total', 'Finish', 'Notes'])
    for k in range(7):
        t0k = (START + timedelta(days=k)).timestamp()
        Sk = ts.Search(R, fp, t0k, [], 1); ts._SELF, ts._START, ts._T0 = Sk, fp, t0k
        fk, lk = Sk.evaluate(order)
        okk = fk < 1e18 and Sk.all_states(lk)
        ws2.append([(START + timedelta(days=k)).strftime('%A'), f'{(fk - t0k) / 3600:.2f} h' if okk else 'breaks',
                    R.fmt_time(fk, lk[-1][2] if lk[-1][0] == 'walk' else lk[-1][4]) if okk else '',
                    'same order from Sheridan 22:10 that weekday; totals count from 22:10'])
    ts._SELF, ts._START, ts._T0 = S, fp, t0
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
        fin = R.fmt_time(f2, legs[-1][2] if legs[-1][0] == "walk" else legs[-1][4]) if ok and waited else (R.fmt_time(f2, l2[-1][4] if l2[-1][0] == 'ride' else l2[-1][2]) if ok else 'not recoverable in the window')
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
                  ('Four Winds shuttle (Michigan)', 'return arrival times in Chicago are not published (assumed); 21+ with photo ID; confirm Saturday service', 'fourwindscasinoshuttle.com'),
                  ('Fargo finish', 'the 83 min walk to Moorhead is from a Google walking screenshot (Nick); MATBUS has no Sunday service', 'walk_links.csv'),):
        m += 1; ws4.append([m, *extra])
    for col, w in zip('ABCD', (4, 60, 70, 110)): ws4.column_dimensions[col].width = w

    # ---- Book ahead: every reservable intercity leg with its date, for pricing ----
    ws5 = wb.create_sheet('Book ahead')
    ws5.append(['day', f'date (start Thu {TRIP:%b %d})', 'depart', 'from', 'arrive', 'to', 'carrier', 'service', 'book', 'price', 'segment booked'])
    for c in ws5[1]: c.font = Font(bold=True)
    LOCAL = ('MATA', 'Michian City', 'Metropolitan Transit Authority of Harris', 'Jacksonville Transportation', 'Transpo', 'On foot',
             'Northern Indiana Commuter', 'Advance Transit', 'Metra', 'Chicago Transit', 'Regional Transportation Commission', 'Utah Transit', 'DALLAS AREA')
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
        dn = (d0.date() - START.date()).days
        ws5.append([f'day {dn + 1}', (TRIP + timedelta(days=dn)).strftime('%a %b %d'), d0.strftime('%H:%M'), R.stop_name[bs],
                    datetime.fromtimestamp(at, tz_of(al)).strftime('%a %H:%M'), R.stop_name[al], ag, rt or hs, book, None, None])
        ws5.cell(ws5.max_row, 10).number_format = '$#,##0.00'
    last = ws5.max_row
    ws5.append(['', '', '', '', '', '', '', '', 'TOTAL', f'=SUM(J2:J{last})', f'=COUNTA(K2:K{last})&" of {last - 1} booked"'])
    ws5.cell(ws5.max_row, 10).number_format = '$#,##0.00'
    for c in ws5[ws5.max_row]: c.font = Font(bold=True)
    ws5.append([]); ws5.append(['', 'Walk-up / local (no reservation): UTA, RTC Las Vegas, Houston METRO, JTA, Advance Transit (free), MATA, Metra (ticket at station or Ventra app), CTA'])
    ws5.append(['', f'No clock change: a Thu {TRIP:%b %d} start finishes Sun {TRIP + timedelta(days=10):%b %d}, before Nov 1. A Thu Oct 22 start would cross it on the Chicago -> Omaha overnight.'])
    ws5.append(['', f'Dates are trips from the timetable window (Sep 24 start) relabelled to a Thu {TRIP:%b %d} start: confirm each leg runs on its date when pricing.'])
    ws5.freeze_panes = 'A2'
    for col, w in zip('ABCDEFGHIJK', (7, 16, 7, 34, 11, 34, 26, 40, 26, 10, 16)): ws5.column_dimensions[col].width = w
    wb.save('../docs/x_itinerary.xlsx')
    print('wrote ../docs/x_itinerary.xlsx:', n, 'legs,', round((f - t0) / 3600, 2), 'h')


if __name__ == '__main__':
    main()
