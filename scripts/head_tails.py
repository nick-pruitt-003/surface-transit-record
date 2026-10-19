"""Good heads, new tails (Nick, Oct 5 2026): old routes whose front half was strong but whose Plains tail died on
the stale Jefferson data. For each, re-time the old order on today's data, cut it at its last pass through Chicago or
Indianapolis that still owes two or more Plains states, and write a tail-search job that fixes the head (the states it
collected, in order, then a pin on that stop) and searches the rest freely.

Leaf script: nothing imports it.   python3 head_tails.py > ../out/tails/jobs.txt   (from scripts/)
Each output line: name|start stop|tz|prefix|seed states|head hours|states owed
"""
import pickle, re, sys
import time_search as ts
from route_report import R
from common import ABBR

CANDIDATES = [   # (name, pickle) for distinct families at or under ~244 h before the Jefferson fixes
    ('ht', '../out/focus4/ht.pkl'), ('huntington', '../out/sweep4/huntington.pkl'), ('control', '../out/ht2/hun.pkl'),
    ('rx', '../out/shapes/rx_long.pkl'), ('newbuffalo', '../out/focus3b/run_22_fixed.pkl'),
    ('portland_ar', '../out/focus2/portland_ar.pkl'), ('hanover_ms', '../out/focus2/hanover_ms.pkl'),
    ('portland_me', '../out/sweep2/run_13.pkl'), ('saint_george', '../out/sweep2/run_16.pkl'),
    ('menomonie', '../out/sweep3/run_08.pkl'), ('hanover', '../out/sweep2/run_07.pkl'), ('fulton', '../out/sweep4/run_15.pkl'),
    ('nola', '../out/sweep2/run_22.pkl'), ('rjc', '../out/sweep3/run_05.pkl'), ('brooke', '../out/focus3/run_22.pkl'),
]
HUB = re.compile(r'^(Chicago|Indianapolis|Museum Campus|Millennium Station)')
PLAINS = {R.state_names.index(n) for n in ('North Dakota', 'South Dakota', 'Nebraska', 'Iowa', 'Minnesota')}


def main():
    for name, p in CANDIDATES:
        try: d = pickle.load(open(p, 'rb'))
        except Exception as e: print(f'# {name}: {e}', file=sys.stderr); continue
        m = [s for s in R.stops_matching(d['start']) if R.stop_name[s] == d['start']] or R.stops_matching(d['start'])
        if not m: print(f'# {name}: no stop {d["start"]}', file=sys.stderr); continue
        st, t0 = m[0], d['t0']
        S = ts.Search(R, st, t0, [], 1); ts.bind(R, st, t0, S)
        f, legs = S.evaluate(d['order'])
        if not legs: print(f'# {name}: does not evaluate', file=sys.stderr); continue
        got, seq, cut = {int(R.state[st])}, [int(R.state[st])], None
        first = next((l[3] for l in legs if l[0] == 'ride'), t0)
        for l in legs:
            if l[0] == 'ride':
                new = S.covered([l]) - got; dest = l[4]; t = l[5]
            else:
                new = ({int(R.state[l[2]])} if R.walk_collects(l[2]) else set()) - got; dest = l[2]; t = l[4]
            seq += sorted(new); got |= new
            if HUB.match(R.stop_name[dest]) and len(PLAINS - got) >= 2:
                cut = (list(seq), R.stop_name[dest], t)
        if not cut: print(f'# {name}: no Chicago/Indianapolis cut with the Plains still owed', file=sys.stderr); continue
        seq_, hub, t = cut
        # The head is the route's OWN pruned order up to the cut, not every state it collected: forcing each collected
        # state in turn sends the router a different way (Oct 6: HT's head then reached Chicago on Tuesday, not Saturday).
        have = set(seq_)
        prefix = [R.state_names[s] for s in d['order'] if isinstance(s, int) and s in have] + ['@' + hub]
        # the fixed head must reproduce: evaluated alone it reaches the hub no later than the old route did
        S2 = ts.Search(R, st, t0, [], 1); ts.rebind(S2)
        fh, lh = S2.evaluate([x if x.startswith('@') else R.state_names.index(x) for x in prefix])
        ts.rebind(S)
        if not lh or fh > t + 60:
            print(f'# {name}: SKIP, the fixed head reaches {hub} at {R.fmt_time(fh, st) if fh < 1e18 else "never"}, '
                  f'the old route at {R.fmt_time(t, st)}', file=sys.stderr); continue
        seed = [ABBR[R.state_names[s]] for s in d['order'] if isinstance(s, int)]
        owed = sorted(ABBR[R.state_names[s]] for s in range(len(R.state_names)) if s not in set(seq_))
        tz = str(R.stop_zone(st))
        print('|'.join([name, R.stop_name[st], tz, ','.join(prefix), ','.join(seed), f'{(t - first) / 3600:.1f}', ' '.join(owed)]))
        print(f'# {name}: head {(t - first) / 3600:.1f} h to {hub} ({R.fmt_time(t, st)}), '
              f'owes {len(owed)}: {" ".join(owed)}; old route now {("%.1f h" % ((f - first) / 3600)) if f < 1e18 and S.all_states(legs) else "BROKEN, misses " + " ".join(sorted(ABBR[R.state_names[s]] for s in S.missing(legs)))}', file=sys.stderr)


if __name__ == '__main__':
    main()
