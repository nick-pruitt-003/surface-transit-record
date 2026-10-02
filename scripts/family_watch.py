"""Early abort for sweeps: is a running time_search converging on a family we already have?

A sweep run spends its whole budget wherever its seed lands, and two sweeps found the same basins (St George ->
Sheridan, New Orleans) from unrelated seeds. Those basins are kept by the focused searches, so a sweep run that
settles into one is better stopped and its time given to the next seed.

A family is a start pattern and a finish pattern (substrings of the first boarding stop and the last stop of the
run's current best route, read from its live progress file). An empty pattern list matches anything. The check
only fires after a grace period, so a run passing through a known shape on its way elsewhere is not cut.

Leaf script: nothing imports it.
  python3 family_watch.py LIVE.json [--grace 300] [--every 30]   waits; prints 'ABORT <family>' and exits 0 when the
                                                                  run's best is a known family, exits 1 when the run ends
  python3 family_watch.py LIVE.json --check                       one look at a (finished) live file, no waiting
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def signature(L):
    best = L.get('best') or []
    if not best: return None
    rides = [l for l in best if l.get('kind') == 'ride'] or best
    return rides[0]['a'][2], best[-1]['b'][2], L.get('best_h')


def match(sig, families):
    s, f, _ = sig
    hit = lambda pats, x: not pats or any(p.lower() in x.lower() for p in pats)
    for fam in families:
        if hit(fam['start'], s) and hit(fam['finish'], f): return fam['name']
    return None


def main():
    a = sys.argv[1:]; path = a[0]
    grace = float(a[a.index('--grace') + 1]) if '--grace' in a else 300
    every = float(a[a.index('--every') + 1]) if '--every' in a else 30
    fams = json.load(open(os.path.join(HERE, 'known_families.json'), encoding='utf-8'))
    while True:
        try: L = json.load(open(path, encoding='utf-8'))
        except (OSError, ValueError): L = None
        if L:
            sig = signature(L)
            age = L.get('now', time.time()) - L.get('started', time.time())
            if sig and ('--check' in a or age >= grace):
                fam = match(sig, fams)
                if fam: print(f'ABORT {fam}: best {sig[2]} h, {sig[0]} -> {sig[1]}', flush=True); return 0
            if '--check' in a: print(f'new: {sig}' if sig else 'no best yet'); return 1
            if L.get('phase') == 'done': return 1
        elif '--check' in a: print('unreadable'); return 1
        time.sleep(every)


if __name__ == '__main__':
    sys.exit(main())
