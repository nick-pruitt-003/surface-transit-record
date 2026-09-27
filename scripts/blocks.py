"""Block and joint tables for the six-block assembler. Leaf script; runs in the cloud (about 40 min, one process).

The three routes under the record are one loop of blocks cut open at different joints. This prices the pieces
exactly so assemble.py can chain every order of them without a router:

  block table: for each block variant (entry portal, exit portal, fixed state order) and its reverse, the time from
               leaving the entry portal to reaching the exit portal having collected the block's states, for every
               15-minute departure slot of a week.
  joint table: portal to portal, same slots, no states.

Slots run over the whole departure horizon, not one week wrapped: a start in the first week plus a route of up to
eleven days, so assemble.py never reads a later day's timetable off the first week's (holidays and calendar ends
differ by date). The router is built for 20 days, which covers it.

A portal is a point: you leave from the stops within 0.3 km of it and have reached it at a stop within the SAME
0.3 km. It used to be 1 km on arrival, which let a block end up to 1.3 km from where the next one left and charged
nothing for the gap; assemble.py also skips the joint when an exit portal is the next entry, so that walk was free
twice. Now the only uncharged hop is inside one 0.3 km cluster of stops, a few minutes at most.
The six blocks partition the 48 states; that is asserted below, so a state cannot silently go missing.

Output: ../out/blocks.pkl  {'slot': s, 't0': epoch, 'n': slots, 'portals', 'variants': {key: (entry, exit, states)},
                            'block': {key: durations}, 'joint': {(a, b): durations}}   durations in seconds, inf = never
"""
import argparse, math, pickle, time
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np
from time_router import cached_router
from common import ABBR

SLOT, WEEK, HORIZON_DAYS = 900, 7 * 86400, 18   # first-week starts + routes up to 11 days
PORTALS = {
    'Sheridan': (-106.945, 44.774), 'LasVegasAirport': (-115.148, 36.086), 'Dallas': (-96.804, 32.779),
    'WashingtonDC': (-77.006, 38.898), 'Hanover': (-72.288, 43.702), 'Huntington': (-82.438, 38.422),
    'Toledo': (-83.542, 41.638), 'Chicago': (-87.644, 41.875), 'Memphis': (-89.993, 35.062),
    'Minneapolis': (-93.276, 44.981),
}
BLOCKS = {  # block: [(entry, exit, states in travel order)]; every variant is also run reversed
    'NW': [('Sheridan', 'LasVegasAirport', 'WY MT ID WA OR UT NV')],
    'SW': [('LasVegasAirport', 'Dallas', 'CA AZ NM CO KS OK TX')],
    'GS': [('Dallas', 'WashingtonDC', 'LA MS AL FL GA SC NC VA')],
    'NE': [('WashingtonDC', 'Hanover', 'MD DE PA NJ NY CT RI MA ME NH VT')],
    'GL': [('Huntington', 'Chicago', 'WV KY OH MI IN IL'), ('Toledo', 'Chicago', 'OH MI WV KY IN IL')],
    'PL': [('Chicago', 'Memphis', 'WI MN ND SD IA NE MO AR TN'), ('Memphis', 'Minneapolis', 'TN AR MO IA NE SD ND MN WI')],
}


def variants():
    out = {}
    for b, vs in BLOCKS.items():
        for e, x, st in vs:
            s = st.split()
            out[(b, e, x)] = (e, x, s)
            out[(b, x, e)] = (x, e, s[::-1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='../out/blocks')
    ap.add_argument('--slots', type=int, default=HORIZON_DAYS * 86400 // SLOT)
    a = ap.parse_args()
    allst = [s for vs in BLOCKS.values() for s in vs[0][2].split()]
    assert len(allst) == 48 and len(set(allst)) == 48, f'blocks must partition the 48 states, got {len(set(allst))}'
    for b, vs in BLOCKS.items():
        for v in vs: assert set(v[2].split()) == set(vs[0][2].split()), f'{b} variants cover different states'
    R = cached_router(date(2026, 9, 24), 20)
    inv = {v: k for k, v in ABBR.items()}
    xy = np.asarray(R.stop_xy[:R.first_virtual], dtype=float)
    orig, tgt = {}, {}
    for n, (lon, lat) in PORTALS.items():
        d = np.hypot((xy[:, 0] - lon) * 111.3 * math.cos(math.radians(lat)), (xy[:, 1] - lat) * 111.3)
        orig[n] = np.nonzero(d <= 0.3)[0].astype(np.int64); tgt[n] = f'@~{lon},{lat},0.3'   # same stops out as in
        if len(orig[n]) == 0: raise SystemExit(f'portal {n} has no stop within 0.3 km')
        print(f'{n:16s} {len(orig[n])} stops: {sorted({R.stop_name[i] for i in orig[n]})[:3]}', flush=True)
    t0 = datetime(2026, 9, 24, 0, 0, tzinfo=ZoneInfo('America/Chicago')).timestamp()
    deps = t0 + SLOT * np.arange(a.slots)
    V = variants(); block, joint = {}, {}; T = time.time()
    save = lambda: pickle.dump(dict(slot=SLOT, t0=t0, n=a.slots, week=WEEK // SLOT, portals=PORTALS, variants=V, block=block, joint=joint), open(a.out + '.pkl', 'wb'))
    for k, (e, x, st) in V.items():
        order = [R.state_names.index(inv[s]) for s in st] + [tgt[x]]
        d = np.full(a.slots, np.inf)
        for i, t in enumerate(deps):
            f = R.finish(orig[e], float(t), order)
            if f is not None: d[i] = f - t
        block[k] = d; save()
        print(f'block {k}: best {np.nanmin(d) / 3600:.1f} h, median {np.median(d[np.isfinite(d)]) / 3600 if np.isfinite(d).any() else float("inf"):.1f} h  ({time.time() - T:.0f} s)', flush=True)
    for A in PORTALS:
        for B in PORTALS:
            if A == B: continue
            d = np.full(a.slots, np.inf)
            for i, t in enumerate(deps):
                _, tm, _ = R._scan_fast(orig[A], np.full(len(orig[A]), float(t)), np.full(len(orig[A]), -1, dtype=np.int32), tgt[B])
                if len(tm): d[i] = float(tm.min()) - t
            joint[(A, B)] = d
        save(); print(f'joints from {A} done ({time.time() - T:.0f} s)', flush=True)
    print('wrote', a.out + '.pkl', flush=True)


if __name__ == '__main__':
    main()
