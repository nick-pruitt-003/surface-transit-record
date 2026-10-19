"""Which ways into Florida leave a chain alive? Leaf script: nothing imports it.

Nick's rule: no successful Florida route avoids Jacksonville, Lake City or Tallahassee; the panhandle loop
(Mobile - Pensacola - Mobile) does not connect. A claim about joint feasibility, so the pair tables answer it.

From the control's node before Florida (re-evaluated through the router) and at every 2 h across that day
with the same held set, route to Florida forced through each gateway area, credit every state the route
passes, and run the pair test where it collects Florida. Alive means some order of everything still owed
can still finish by the deadline, two states at a time; dead means it provably cannot.

    nice -n 19 python3 florida_probe.py
"""
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router, N_STATES
from common import ABBR
import time_search as ts_
from time_search import Search
from pair_tables import PairTables, leg_states

TZ = ZoneInfo('America/New_York')
MOBILE = (30.6954, -88.0399)
GATES = {'Pensacola': (30.4213, -87.2169), 'Pensacola loop': (30.4213, -87.2169), 'Tallahassee': (30.4383, -84.2807),
         'Lake City': (30.1897, -82.6393), 'Jacksonville': (30.3322, -81.6557)}


def main():
    R = cached_router(datetime(2026, 11, 5).date(), 20, verbose=False)
    ab = lambda x: ABBR[R.state_names[x]]
    inv = {v: k for k, v in ABBR.items()}
    FL = R.state_names.index(inv['FL'])
    D = datetime(2026, 11, 14, 22, 54, tzinfo=TZ).timestamp()
    PT = PairTables(R, D, 260, verbose=False)
    tcn = defaultdict(list)
    for k in range(len(R.dep)): tcn[R.ctrip[k]].append(k)

    tc = datetime(2026, 11, 5, 0, 30, tzinfo=TZ).timestamp()
    best_ = None
    for h in [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']:
        S = Search(R, h, tc, [], 1)
        ts_.bind(R, h, tc, S)
        f, legs = S.evaluate(pickle.load(open('../out/hun_ms_meteor.pkl', 'rb'))['order'])
        if best_ is None or f < best_[0]: best_ = (f, legs, h)
    _, legs, hun = best_
    have = {int(R.state[hun])}
    node = None
    for l in legs:
        if l[0] == 'ride':
            _, trip, bs, bt, al, at = l
            nxt = have | leg_states(R, (trip, bs, al, bt, at), tcn)
            if FL in nxt: break                             # stop at the control's last node before Florida
            have = nxt; node = (al, at, frozenset(have))
        elif l[0] == 'walk':
            if R.state[l[2]] >= 0: have.add(int(R.state[l[2]]))
    stop0, t0c, held = node
    print(f'control node before Florida: {R.stop_name[stop0]} at {datetime.fromtimestamp(t0c, TZ):%a %H:%M}, '
          f'{(t0c - tc) / 3600:.1f} h, {len(held)} held, owes {" ".join(ab(y) for y in range(N_STATES) if y not in held)}\n')

    day = datetime.fromtimestamp(t0c, TZ).replace(hour=0, minute=0)
    times = [t0c] + [(day + timedelta(hours=h)).timestamp() for h in range(0, 24, 2)]
    print(f'{"leave":17s}' + ''.join(f'{g:>20s}' for g in GATES))
    for t0 in times:
        row = []
        for g, (la, lo) in GATES.items():
            try:
                # the loop: into Florida at Pensacola and back out west to Mobile, which is Nick's claim; plain
                # 'Pensacola' also counts the eastbound I-10 bus that merely passes it on the way to Tallahassee
                tg = [f'@~{lo},{la},15', FL] + ([f'@~{MOBILE[1]},{MOBILE[0]},10'] if g == 'Pensacola loop' else [])
                te, lg = R._route_fast(np.array([stop0]), float(t0), tg)
            except Exception:
                te, lg = None, []
            if te is None or not np.isfinite(te):
                row.append('unreachable'); continue
            got = set(); last = stop0
            for l in lg:
                if l[0] == 'ride':
                    _, trip, bs, bt, al, at = l
                    got |= leg_states(R, (trip, bs, al, bt, at), tcn); last = al
                elif l[0] == 'walk':
                    if R.state[l[2]] >= 0: got.add(int(R.state[l[2]]))
                    last = l[1] if l[2] >= R.first_virtual else l[2]
            owed = [y for y in range(N_STATES) if y not in held and y not in got]
            m, y, z = PT.worst(last, float(te), owed)
            row.append(f'{"alive" if m >= 0 else "DEAD"} {m / 3600:+.1f}h @{(te - t0) / 3600:.0f}h')
        tag = ' (ctrl)' if t0 == t0c else ''
        print(f'{datetime.fromtimestamp(t0, TZ):%a %H:%M}{tag:8s}' + ''.join(f'{c:>20s}' for c in row), flush=True)
    print('\ncell: pair verdict where Florida is collected, tightest margin, hours from leaving to collecting FL')


if __name__ == '__main__':
    main()
