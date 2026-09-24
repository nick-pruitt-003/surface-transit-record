"""Re-cost the assembler's top candidates exactly with the router. Leaf script; cloud, about 10 min.

The assembler floors every departure to its slot, so its hours are optimistic. This is the check that removes that:
each candidate's full state order (its blocks' states, with each block's exit portal pinned so the router follows
the same shape) is evaluated from its entry portal at every departure in a two-hour window around its best slot,
and again with the pins dropped so the router may take any path through the same state order. The better of the
two is reported. Gated first on the control reproducing 237.34 h, so nothing prints from a router that disagrees.

Output: ../out/block_verify.txt
"""
import argparse, math, pickle
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR
from pick import gate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=30)
    a = ap.parse_args()
    A = pickle.load(open('../out/assemble.pkl', 'rb'))
    R = cached_router(date(2026, 9, 24), 20)
    inv = {v: k for k, v in ABBR.items()}
    idx = lambda s: R.state_names.index(inv[s])
    ctl = [idx(x) for x in 'WV KY OH MI IN IL TN MS AR MO IA NE SD ND MN WI WY MT ID WA OR UT AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH VT'.split()]
    hun = [i for i, nm in enumerate(R.stop_name) if nm == 'Huntington Bus Stop']
    t_ctl = datetime(2026, 9, 24, 0, 54, tzinfo=ZoneInfo('America/New_York')).timestamp()
    gate('control total from Huntington 00:54', lambda: (R.finish(hun, t_ctl, ctl) - t_ctl) / 3600, 237.34, 0.02)

    xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float)
    def portal_stops(name):
        lon, lat = A['portals'][name]
        d = np.hypot((xy[:, 0] - lon) * 111.3 * math.cos(math.radians(lat)), (xy[:, 1] - lat) * 111.3)
        return np.nonzero(d <= 0.3)[0].astype(np.int64)
    pin = lambda name: '@~{},{},1.0'.format(*A['portals'][name])

    S, t0 = A['S'], A['t0']; ct = ZoneInfo('America/Chicago'); lines = []
    for i, (h_tab, j, seq) in enumerate(A['res'][:a.top]):
        pinned, plain = [], []
        for k in seq:
            st = [idx(s) for s in A['variants'][k][2]]
            pinned += st + [pin(k[2])]; plain += st
        start = portal_stops(seq[0][1]); best = (float('inf'), None, '')
        for dt in range(-4, 5):   # the slot +/- one hour, in 15 min steps
            t = t0 + (j + dt) * S
            for label, order in (('pinned', pinned), ('free', plain)):
                f = R.finish(start, t, order)
                if f is None: continue
                # elapsed from the first bus, not the clock: route() tells us when that is
                legs = R.route(start, t, order)[1]
                first = next((l[3] for l in legs if l[0] == 'ride'), t)
                h = (f - first) / 3600
                if h < best[0]: best = (h, first, label)
        h, first, label = best
        when = datetime.fromtimestamp(first, ct).strftime('%a %H:%M CT') if first else '-'
        flag = '  BEATS THE CONTROL' if h < 237.34 else ('  beats the record' if h < 238.83 else '')
        lines.append(f'{i + 1:3d} tables {h_tab:6.1f}  router {h:6.1f} h ({label}, first bus {when}){flag}  '
                     + ' | '.join(f'{b} {e}>{x}' for b, e, x in seq))
        print(lines[-1], flush=True)
    open('../out/block_verify.txt', 'w').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
