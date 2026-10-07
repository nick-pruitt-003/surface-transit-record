"""Improve a route by searching every ordering of a sliding window of states, on the real timetables.

  python3 window_search.py --route ../out/res_starttest.pkl --k 6

No estimate, no matrix, no aggregation. Hold the route fixed except for k consecutive states, try every
ordering of those k, and evaluate each one the way the router actually evaluates a route. Slide the window
along and repeat. Whatever the timetables say, that is the answer.

This exists because every attempt to score a partial route failed, and they failed for one reason: they all
summarised ten million real connections into a 48x48 table of typical hours. The minimum over stop pairs
turns the table into a map of which states touch, the median erases the once-a-day services the route is
actually built around, and a spanning tree then chains those minimums together, which is why Oklahoma reads
as cheap when it is the whole difficulty. Within a window there is nothing to summarise: k! orderings is a
few hundred, and each one gets a real finish time.

Exact inside the window, so an improvement is real and a failure to improve means no reordering of those k
states helps, which the forward search's relocate move can only sample.
"""
import argparse, itertools, pickle, time
from datetime import datetime
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds
import time_search as ts
from time_search import Search
from common import ABBR

ET = ZoneInfo('America/New_York')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--route', default='../out/res_starttest.pkl')
    ap.add_argument('--k', type=int, default=6, help='states in the window (k! orderings each)')
    ap.add_argument('--first', type=int, default=1, help='first position to slide over; 0 would move the start state')
    ap.add_argument('--days', type=int, default=18)
    ap.add_argument('--passes', type=int, default=2, help='sweeps over the route; a second sweep can compound gains')
    ap.add_argument('--out', help='pickle to write if anything beats the input')
    a = ap.parse_args()

    d = pickle.load(open(a.route, 'rb'))
    order, t0, start_name = list(d['order']), d['t0'], d['start']
    R = TimeRouter(load_feeds(), datetime.fromtimestamp(t0, ET).date(), a.days)
    start = R.stop_name.index(start_name)
    S = Search(R, start, t0, [], 1)
    ts.bind(R, start, t0, S)
    ab = lambda x: ABBR[R.state_names[x]]

    def elapsed(o):
        f, legs = S.evaluate(o)
        if f == float('inf') or not S.all_states(legs): return None
        return (f - t0) / 3600

    base = elapsed(order)
    if base is None: print('the input route does not evaluate'); return
    print(f'input {base:.2f} h, {len(order)} states, window {a.k} ({len(list(itertools.permutations(range(a.k))))} '
          f'orderings per position)\n', flush=True)
    best, best_h = list(order), base
    t_start = time.time(); tried = 0
    for p in range(a.passes):
        improved = False
        for i in range(a.first, len(best) - a.k + 1):
            head, win, tail = best[:i], best[i:i + a.k], best[i + a.k:]
            local, local_h = None, best_h
            for perm in itertools.permutations(win):
                if list(perm) == win: continue
                tried += 1
                h = elapsed(head + list(perm) + tail)
                if h is not None and h < local_h - 1e-9: local, local_h = list(perm), h
            if local is not None:
                print(f'  [{time.time() - t_start:5.0f}s] pos {i:2d}: {best_h:.2f} -> {local_h:.2f} h  '
                      f'({" ".join(ab(x) for x in win)}  ->  {" ".join(ab(x) for x in local)})', flush=True)
                best = head + local + tail; best_h = local_h; improved = True
        print(f'  pass {p + 1}: {best_h:.2f} h after {tried} orderings, {time.time() - t_start:.0f} s', flush=True)
        if not improved: break

    print(f'\ninput {base:.2f} h -> best {best_h:.2f} h  ({best_h - base:+.2f} h) after {tried} orderings')
    if best_h < base - 1e-9:
        print('  ' + ' > '.join(ab(x) for x in best))
        if a.out:
            f, _ = S.evaluate(best)
            pickle.dump(dict(order=best, t0=t0, start=start_name, elapsed=f - t0, finish=f), open(a.out, 'wb'))
            print('  wrote', a.out)
    else:
        print('  no reordering of any window of this size beats the input, which the relocate move could only sample')


if __name__ == '__main__':
    main()
