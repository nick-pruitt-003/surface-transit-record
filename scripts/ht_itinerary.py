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
    ws2.append(['Start day', 'Total', 'Memphis falls on', 'Memphis on real MATA'])
    for r in (('Mon / Tue / Wed', '230.10 h', 'Wed / Thu / Fri', 'yes: Walker 04:30 reaches the bridge for the 05:45 walk'),
              ('Thu', '230.10 h', 'Sat', 'no: first useful MATA is 07:00; needs a taxi from the terminal'),
              ('Fri', '230.10 h', 'Sun', 'not checked'),
              ('Sat / Sun', 'chain breaks', '', 'a non-daily service in the chain')):
        ws2.append(list(r))
    for col, w in zip('ABCD', (16, 12, 18, 60)): ws2.column_dimensions[col].width = w
    wb.save('../docs/ht_itinerary.xlsx')
    print('wrote ../docs/ht_itinerary.xlsx:', n, 'legs,', round((f - t0) / 3600, 2), 'h')


if __name__ == '__main__':
    main()
