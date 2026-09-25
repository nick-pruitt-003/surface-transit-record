"""Price a hand-drawn route shape exactly, with no search. Leaf script, about a minute.

A search is free to reorder states, and near a strong shape (X_TOL) it slides back into it and drags any pins
along as a dead-end tail: SHE_BEN and SHE_MD both did. This evaluates the order exactly as written, pins and all,
from Sheridan's 22:20 bus on each of seven start days, and prints the best day's legs. The number is what the
shape costs as drawn; a search seeded from it can only improve on it.

Gated first on X_TOL's own order reproducing 237.9 h from its Thursday bus. A day whose route misses a state
counts as infinite: following turning points alone gave 236.4 h on a Tuesday that skipped SD, SC, DE and NE.
"""
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from time_router import cached_router
from common import ABBR
from pick import gate
from time_search import Search

R = cached_router(date(2026, 9, 24), 20)
inv = {v: k for k, v in ABBR.items()}
DN = ZoneInfo('America/Denver')
SHE = [i for i, n in enumerate(R.stop_name) if n == 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)']
SYR = '@~-76.1693,43.0766,0.5'
DET = '@~-83.0580,42.3280,0.5'
parse = lambda s: [x if x.startswith('@') else R.state_names.index(inv[x]) for x in s]

SHAPES = {
    # X_TOL's order as the search left it, the gate
    'X_TOL': 'NV @Albuquerque_Bus_Station LA @Toledo_Bus_Stop WV ND AR FL ME VT',   # the search's own turning points
    # Nick: the Interior ends at Detroit 23:00, then Cleveland -> Syracuse -> Albany 14:40 -> Bennington (evening)
    # -> Albany -> Boston -> Portland -> Boston -> Acela south to DC
    'MD_acela_south': 'WY MT ID WA OR UT NV CA AZ @Albuquerque_Bus_Station NM CO KS OK TX LA MS AL FL GA SC NC VA WV KY TN AR MO IA NE SD ND MN WI IL IN MI DET OH SYR NY @Bennington_VT_Transit_Center VT MA NH ME RI CT NJ PA DE MD',
    # X with New England in the middle through Bennington, then Albany 16:05 -> Cleveland -> Toledo and the Interior
    'BW_westbound': 'WY MT ID WA OR UT NV CA AZ @Albuquerque_Bus_Station NM CO KS OK TX LA MS AL FL GA SC NC VA MD DE PA NJ NY CT RI MA NH ME @Bennington_VT_Transit_Center VT @Toledo_Bus_Stop MI OH WV KY IN IL WI MN ND SD IA NE MO AR TN',
}


CHECK = Search(R, SHE[0], datetime(2026, 9, 24, 12, 0, tzinfo=DN).timestamp(), [], 1)   # for its 48-state coverage test


def order_of(spec):
    out = []
    for x in spec.split():
        if x == 'DET': out.append(DET)
        elif x == 'SYR': out.append(SYR)
        elif x.startswith('@'): out.append('@' + x[1:].replace('_', ' '))
        else: out.append(R.state_names.index(inv[x]))
    return out


def best(order):
    res = []
    for d in range(7):
        t = datetime(2026, 9, 24, 12, 0, tzinfo=DN).timestamp() + d * 86400
        f, legs = R.route(SHE, t, order)
        if f is None: res.append((float('inf'), d, None)); continue
        if CHECK.missing(legs): res.append((float('inf'), d, None)); continue   # misses a state: not a route
        first = next(l[3] for l in legs if l[0] == 'ride')
        res.append(((f - first) / 3600, d, legs))
    return min(res, key=lambda r: r[0]), res


(h, d, _), _ = best(order_of(SHAPES['X_TOL']))
gate('X_TOL order from Sheridan, best of 7 start days', lambda: h, 237.9, 0.1)
for name in sys.argv[1:] or [k for k in SHAPES if k != 'X_TOL']:
    (h, d, legs), allres = best(order_of(SHAPES[name]))
    days = '  '.join(f"{(datetime(2026, 9, 24, tzinfo=DN) + timedelta(days=dd)):%a} {hh:.1f}" for hh, dd, _ in allres)
    print(f'\n== {name}: best {h:.1f} h (start day offset {d})   by start day: {days}')
    if legs: print(R.describe(legs))
