"""Find the services a 48-state route has to be planned around, from the feeds rather than from a known route.

  python3 anchors.py [--min-states 4] [--max-per-day 2]

An anchor is a service that is both long and rare: it collects several states in one ride, and it runs once
or twice a day, so a route either makes it or loses most of a day. Every attempt at scoring partial backward
chains has failed on exactly these: the chain that commits to one looks worse for the next fifteen steps,
because committing means being somewhere at a fixed hour, and only pays at the end.

This lists them by states spanned and departures per day so the next thing built can branch on the
commitment itself instead of trying to price it.
"""
import argparse, collections, os, sys
from datetime import datetime
import numpy as np
from time_router import TimeRouter, load_feeds, N_STATES
from common import ABBR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-states', type=int, default=4, help='states a ride must collect to count as long')
    ap.add_argument('--max-per-day', type=float, default=2.0, help='departures per day for it to count as rare')
    ap.add_argument('--day', default='2026-11-04'); ap.add_argument('--days', type=int, default=14)
    a = ap.parse_args()
    R = TimeRouter(load_feeds(), datetime.fromisoformat(a.day).date(), a.days)
    ab = lambda x: ABBR[R.state_names[x]] if x >= 0 else '--'

    # one entry per trip pattern: the states it runs through, and how many times it departs over the window
    pat = collections.defaultdict(lambda: [0, None, None])
    # Count the departures actually in the calendar, not the trip entities in the feed. R.trip_info holds one
    # entry per feed trip however many days it runs, so dividing by the window understated everything: the
    # Empire Builder, which runs daily, came out at 0.43 a day.
    # A connection's trip key is (feed, trip id, day index), and there is one connection per consecutive
    # stop pair, so a forty-stop train contributes thirty-nine entries a day. Counting whole keys and then
    # looking one up by (feed, trip id) matched nothing and gave zero; counting raw entries counted
    # connections and pushed every long train past the rarity filter. Dedupe the dated keys first, then
    # count how many days each feed trip actually runs.
    dated = collections.Counter((fi_, tid_) for fi_, tid_, _day in set(R.ctrip))
    for (fi, tid), info in R.trip_info.items():
        f = R.feeds[fi]; t = f.trips.get(tid)
        if t is None: continue
        ids = [R.idx.get(f.stops[x[1]][0]) for x in t['stops']]
        ids = [i for i in ids if i is not None]
        sts = []
        for i in ids:
            s = int(R.state[i])
            if s >= 0 and (not sts or sts[-1] != s): sts.append(s)
        uniq = list(dict.fromkeys(sts))
        if len(uniq) < a.min_states: continue
        key = (info[1] or '', tuple(uniq))
        pat[key][0] += dated.get((fi, tid), 0)
        pat[key][1] = info[0] if pat[key][1] is None else pat[key][1]
        pat[key][2] = (R.stop_name[ids[0]], R.stop_name[ids[-1]])
    rows = []
    for (name, uniq), (n, agency, ends) in pat.items():
        per_day = n / a.days
        if per_day <= a.max_per_day: rows.append((len(uniq), -per_day, name, agency, uniq, per_day, ends))
    rows.sort(reverse=True)
    print(f'\nservices collecting {a.min_states}+ states at no more than {a.max_per_day} departures a day '
          f'({len(rows)} of them)\n')
    print(f'{"states":6s} {"per day":7s}  service')
    for nst, _, name, agency, uniq, per_day, ends in rows[:30]:
        print(f'{nst:6d} {per_day:7.2f}  {(name or agency)[:38]:38s} {" > ".join(ab(x) for x in uniq)}')
        print(f'{"":15s}{ends[0][:34]} -> {ends[1][:34]}')
    print(f'\n{len(rows)} anchors. A route has to make these or lose most of a day, and they are what the '
          f'leftover estimates cannot price.')


if __name__ == '__main__':
    main()
