"""Regression checks: facts we already verified, re-checked on the current code and data (~2 min, one router).

  python3 regress.py            # prints PASS/FAIL per check, exits 1 on any failure

Run it before committing router, search or data changes. Add a check whenever a bug is fixed or a fact verified.
"""
import pickle, sys, time, traceback
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import time_router as tr
from time_router import TimeRouter, load_feeds, N_STATES
import time_search as ts
from time_search import Search
import backward as B

OUT = '../out/'
ET, CT = ZoneInfo('America/New_York'), ZoneInfo('America/Chicago')
results = []


def check(name):
    def deco(fn):
        t = time.time()
        try: fn(); results.append((name, True, f'{time.time() - t:.0f}s'))
        except Exception as e: results.append((name, False, f'{type(e).__name__}: {e}')); traceback.print_exc()
        return fn
    return deco


def search_for(R, start, t0):
    S = Search(R, start, t0, [], 1)
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, start, t0, S, None, None
    return S


print('settings: MIN_TRANSFER', tr.MIN_TRANSFER // 60, 'min, WALKIN_KM', tr.WALKIN_KM, ', SCAN_SLACK', tr.SCAN_SLACK / 3600, 'h')
R = TimeRouter(load_feeds(), datetime(2026, 9, 23).date(), 18)
t237 = datetime(2026, 9, 24, 0, 30, tzinfo=ET).timestamp()
hun = R.stops_matching('Huntington Bus Stop')[0]


@check('defaults match the search settings (5 min transfers, 1.4 km walk-ins, 24 h slack)')
def _():
    assert (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK) == (300, 1.4, 86400), (tr.MIN_TRANSFER, tr.WALKIN_KM, tr.SCAN_SLACK)


@check('Amtrak times are agency (Eastern) time: CONO Effingham 10:01 PM, Memphis 4:42 AM Central')
def _():
    efg = R.stops_matching('Effingham Amtrak Station')[0]; mem = R.idx['amtrak:MEM']
    day = datetime(2026, 9, 24, tzinfo=CT).timestamp()
    ks = [k for k in range(len(R.dep)) if R.cfrom[k] == efg and day < R.dep[k] < day + 86400
          and R.trip_info[(R.ctrip[k][0], R.ctrip[k][1])][1] == 'City of New Orleans']
    deps = {datetime.fromtimestamp(R.dep[k], CT).strftime('%H:%M') for k in ks}
    assert '22:01' in deps, deps
    k = ks[[datetime.fromtimestamp(R.dep[j], CT).strftime('%H:%M') for j in ks].index('22:01')]
    key = R.ctrip[k]; arr = [R.arr[j] for j in range(k, min(k + 400000, len(R.dep))) if R.ctrip[j] == key and R.cto[j] == mem]
    assert arr and datetime.fromtimestamp(arr[0], CT).strftime('%H:%M') == '04:42', arr


@check('237 route (hun_ms_meteor) is valid: all 48 states, finish <= 238.0 h from the 12:30 AM clock')
def _():
    S = search_for(R, hun, t237)
    f, legs = S.evaluate(pickle.load(open(OUT + 'hun_ms_meteor.pkl', 'rb'))['order'])
    assert S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]
    assert (f - t237) / 3600 <= 238.0, (f - t237) / 3600


@check('router and coverage agree: every state target is collected by a ride or border walk-in (Sunland seed)')
def _():
    st = R.stops_matching('McNutt & Calle Morocco')[0]; t0 = datetime(2026, 9, 23, tzinfo=ZoneInfo('America/Denver')).timestamp()
    S = search_for(R, st, t0)
    inv = {v: k for k, v in ts.ABBR.items()}
    order = [R.state_names.index(inv[x]) for x in 'TX,LA,MS,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,WV,KY,TN,AR,MO,IL,IN,MI,WI,MN,IA,NE,KS,OK,CO,WY,SD,ND,MT,ID,WA,OR,UT,AZ,NV,CA'.split(',')]
    f, legs = S.evaluate(order)
    assert f < float('inf') and S.all_states(legs), [R.state_names[s] for s in S.missing(legs)]


@check('backward report on the 237 result: every layer feasible, slack >= 0, latest start = 12:59 AM Thu')
def _():
    d = pickle.load(open(OUT + 'res_starttest.pkl', 'rb')); order = d['order']; t0 = d['t0']
    start = R.stop_name.index(d['start'])
    fw, bad = B.forward(R, start, t0, order); assert bad is None, bad
    rev = [[] for _ in range(R.N)]
    for i in range(R.N):
        for j, w in R.foot.get(i, ()): rev[j].append((i, w))
    D = min(fw[-1].values()); lat = {s: D for s in fw[-1]}; stays = {}
    for k in range(len(order) - 2, -2, -1):
        want = [start] if k < 0 else fw[k]
        latest, stay = B.backward_layer(R, rev, lat, not isinstance(order[k + 1], str), t0 if k < 0 else min(fw[k].values()), stays, want)
        if k < 0: ls = max([latest[start]] + [t - tr.MIN_TRANSFER for t in stay.get(start, {}).values()]) + tr.MIN_TRANSFER; break
        lat = {s: max([latest[s]] + list(stay.get(s, {}).values())) for s in fw[k]}
        lat = {s: v for s, v in lat.items() if v > float('-inf')}; stays = stay
        assert lat, f'layer {k} ({order[k]}) empty'
        assert max(v - fw[k][s] for s, v in lat.items()) >= -60, f'layer {k} negative slack'
    assert datetime.fromtimestamp(ls, ET).strftime('%a %H:%M') == 'Thu 00:59', datetime.fromtimestamp(ls, ET)


@check('move labels read correctly')
def _():
    S = Search.__new__(Search); S.R = R; n = lambda a: R.state_names.index(a)
    o = [n('Ohio'), n('Michigan'), n('Indiana'), n('Illinois')]
    assert S.move_label(o, [o[0], o[2], o[3], o[1]]) == 'move MI after IL', S.move_label(o, [o[0], o[2], o[3], o[1]])
    assert S.move_label(o, [o[0], o[2], o[1], o[3]]).startswith('reverse'), S.move_label(o, [o[0], o[2], o[1], o[3]])


print()
for name, ok, info in results: print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else '\n     ' + info))
print(f'\n{sum(ok for _, ok, _ in results)}/{len(results)} passed')
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
