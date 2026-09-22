"""What could be collected in the dead time a route already has?

Nick's Memphis move, asked as a question the timetable can answer. The 237 route collects Mississippi on
foot at Holmes because there is a four hour gap between the City of New Orleans arriving at Memphis and the
Jefferson bus leaving, with no productive move in it. The state costs nothing, because the time was already
spent. And it is not merely free: collecting MS there frees the Houston to Tallahassee bus that skips
Mississippi, which arrives early enough for the Silver Meteor and the accelerated finish.

A constructive search cannot find that move by ranking. At Memphis the ride to Holmes is one of 834
surviving options and collects nothing on arrival, so no local score puts it near the top, and its payoff is
five days and two thousand miles away. As a repair it is trivial: the chain already exists, the hole is
visible, and the only question is what fits inside it.

The question is exact and cheap. For a layover at stop X from t_in to t_out:

  one forward scan from (X, t_in)   gives the earliest you can be at every stop
  one reverse scan from (X, t_out)  gives the latest you can leave every stop and still be back

and a state is insertable when it owns a stop where the first is not after the second. Two scans per
layover, about eighty for a whole route, against the millions of option-scorings the constructive search
pays. Nothing is estimated and no threshold is invented: a window either fits a detour or it does not.

The insertion is also provably free of side effects. A detour that returns to X before the same departure
leaves every later leg of the route bit-identical, so nothing downstream can break. What it does change is
the set of states still owed, and that is where the real gain lives, because a state no longer owed can
release a faster ride later.

Run it against the control and it should rediscover Memphis:

  python3 repair_probe.py --route ../out/res_starttest.pkl
"""
import argparse, pickle, time
from zoneinfo import ZoneInfo
import numpy as np
from time_router import TimeRouter, load_feeds, cached_router, MIN_TRANSFER, N_STATES
import backward as B
import time_search as ts
from time_search import Search
from common import ABBR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', default='../out/res_starttest.pkl')
    ap.add_argument('--min-window', type=float, default=30, help='minutes; shorter layovers are reported '
                    'but not scanned, since nothing fits')
    ap.add_argument('--drop', default=None, help='N or N-M: pretend the route never took these rides, so '
                    'layover around it reopens. The honest test of the operator: drop the Memphis detour '
                    'and it should offer Mississippi back.')
    ap.add_argument('--days', type=int, default=20)
    a = ap.parse_args()

    d = pickle.load(open(a.route, 'rb'))
    # The service date the router was built for, not whatever date this machine's clock calls that
    # instant. The route starts at 00:54 Eastern, so a container running in UTC happens to agree and one
    # running west of Eastern would silently build a router for the previous day. New pickles carry the
    # date; older ones are read in Eastern, which is the clock the route is written in.
    sdate = d.get('service_date')
    sdate = (__import__('datetime').date.fromisoformat(sdate) if sdate else
             __import__('datetime').datetime.fromtimestamp(d['t0'], ZoneInfo('America/New_York')).date())
    R = cached_router(sdate, a.days)
    ab = lambda x: ABBR[R.state_names[x]] if x >= 0 else '--'
    st0 = R.stop_name.index(d['start'])
    S = Search(R, st0, d['t0'], [], 1)
    ts._R, ts._START, ts._T0, ts._SELF, ts._BASE, ts._END = R, st0, d['t0'], S, None, None
    _, legs = S.evaluate(d['order'])
    rides = [l for l in legs if l[0] == 'ride']
    if a.drop:
        lo_, _, hi_ = a.drop.partition('-')
        lo_ = int(lo_); hi_ = int(hi_ or lo_)
        if 1 <= lo_ <= hi_ <= len(rides):
            for g_ in rides[lo_ - 1:hi_]:
                print(f'pretending the route never took {R.stop_name[g_[2]][:24]} -> '
                      f'{R.stop_name[g_[4]][:24]}', flush=True)
            rides = rides[:lo_ - 1] + rides[hi_:]
    print(f'{len(rides)} rides over {len(d["order"])} states\n', flush=True)

    # Where the route stands still. A layover is arriving somewhere and leaving it later, and the gap is
    # time already spent whatever happens in it.
    stops_by_state = {}
    for s in range(R.N):
        y = int(R.state[s])
        if y >= 0: stops_by_state.setdefault(y, []).append(s)
    st_arr = {y: np.array(v, dtype=np.int64) for y, v in stops_by_state.items()}

    rev = B.RevFast(R)
    holes = []
    for i in range(len(rides) - 1):
        _, _trip, _bs, _bt, al, at = rides[i]
        _, _t2, bs2, bt2, _al2, _at2 = rides[i + 1]
        # The window runs from where one ride drops you to where the next one picks you up, and those need
        # not be the same stop. Requiring them to match is what made the first version of this probe miss
        # the move it was written for: the Memphis excursion lands at Holmes and boards the Jefferson bus at
        # Airways Transit Center, so a same-stop test threw it away. The two scans do not care, they just
        # need the two ends.
        gap = bt2 - at
        if gap > 0: holes.append((i + 1, al, at, bs2, bt2, gap))

    # What the route already holds by the time it reaches each layover. Without this the table is mostly
    # tautology: standing in Wisconsin, Wisconsin is collectable. The question worth asking is what a
    # window could add that the route does not have yet.
    have = [None] * (len(rides) + 1)
    seen = set()
    if R.state[st0] >= 0: seen.add(int(R.state[st0]))
    for _l in legs:
        if _l[0] == 'walk' and _l[2] >= R.first_virtual and R.state[_l[2]] >= 0: seen.add(int(R.state[_l[2]]))
    running = set()
    if R.state[st0] >= 0: running.add(int(R.state[st0]))
    for i, (_, _t, bs_, _bt, al_, _at) in enumerate(rides):
        for s_ in (bs_, al_):
            if R.state[s_] >= 0: running.add(int(R.state[s_]))
        have[i + 1] = set(running)

    print(f'{len(holes)} layovers where the route waits at the stop it arrived at\n', flush=True)
    print(f'{"after leg":>9}  {"stop":28s} {"window":>8}  states it could add that the route lacks there', flush=True)

    total_free = set()
    for n, X, t_in, Y, t_out, gap in sorted(holes, key=lambda h: -h[5]):
        if gap < a.min_window * 60:
            continue
        t0_ = time.time()
        # out: earliest you can be anywhere, leaving X at t_in
        stops = np.array([X]); times = np.array([float(t_in)]); trips = np.array([-1], dtype=np.int32)
        _h, _t, _l, pred = R._scan_fast(stops, times, trips, 'VT', want_pred=True)
        best = pred['best']
        # back: latest you can leave anywhere and still stand at X by t_out
        latest, ok, k0, k1 = rev.layer({int(Y): float(t_out)}, False, float(t_in), None)
        eff, _ = rev.through(ok, k0, k1, np.ones(R.N, bool))
        back = np.maximum(latest, eff)

        already = have[n] if have[n] is not None else set()
        fits = []
        for y in range(N_STATES):
            sa = st_arr.get(y)
            if sa is None or y in already: continue      # standing in it is not a discovery
            if np.any(np.isfinite(best[sa]) & (best[sa] <= back[sa])):
                fits.append(y)
        total_free |= set(fits)
        where = R.stop_name[X][:26] if X == Y else f'{R.stop_name[X][:12]} -> {R.stop_name[Y][:11]}'
        print(f'{n:9d}  {where:28s} {gap / 3600:6.1f} h  '
              f'{" ".join(ab(y) for y in fits) if fits else "nothing"}'
              f'   [{time.time() - t0_:.1f}s]', flush=True)

    print(f'\n{len(total_free)} distinct states are reachable inside dead time somewhere on this route: '
          f'{" ".join(ab(y) for y in sorted(total_free))}', flush=True)
    print('\nA state here is one the route could collect without spending a minute it was not already '
          'spending. That is the move the constructive search cannot rank its way to, and the reason the '
          'control takes Mississippi at Memphis.', flush=True)


if __name__ == '__main__':
    main()
