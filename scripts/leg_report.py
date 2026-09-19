"""Leg report for a finished search log (out/res_<name>.log): waits, long rides, U-turns.

Reads the leg lines printed after FINAL, so it needs no router and is safe to run
alongside a search.

  python3 leg_report.py ../out/res_denverV7.log [--wait 2]

U-turn: a leg that ends at a place the route already left within the last 30 h
(same city name), i.e. riding back over the same ground.
"""
import re, sys

LEG = re.compile(r'^d(\d+) (\w{3}) (\d\d):(\d\d)\s+(.*?)\s+->\s+d(\d+) (\w{3}) (\d\d):(\d\d)\s+(.*?)\s+\[(.*)\]$')


def city(s):
    s = re.sub(r'\(.*?\)', '', s).split(',')[0]
    return re.split(r'\s+(Bus|Amtrak|Intermodal|Union|Station|Downtown|Transit|Greyhound|Travel|Airport|Shop)\b', s)[0].strip().lower()


def main():
    path = sys.argv[1]; wmin = float(sys.argv[sys.argv.index('--wait') + 1]) if '--wait' in sys.argv else 2.0
    lines = open(path).read().split('\n')
    k = max(i for i, l in enumerate(lines) if l.startswith('FINAL'))
    print(lines[k]); legs = []
    for l in lines[k + 1:]:
        m = LEG.match(l.strip())
        if not m: continue
        d1, _, h1, m1, a, d2, _, h2, m2, b, how = m.groups()
        t1 = int(d1) * 24 + int(h1) + int(m1) / 60; t2 = int(d2) * 24 + int(h2) + int(m2) / 60
        legs.append((t1, t2, a, b, how))
    ride = sum(t2 - t1 for t1, t2, *_ in legs); total = legs[-1][1] - legs[0][0]
    print(f'{len(legs)} legs, {total:.1f} h first boarding to last arrival, riding {ride:.1f} h, waiting/walking {total - ride:.1f} h\n')
    left = []   # (time left, city)
    for i, (t1, t2, a, b, how) in enumerate(legs):
        flags = []
        if i:
            w = t1 - legs[i - 1][1]
            if w >= wmin: flags.append(f'WAIT {w:.1f} h before')
        if t2 - t1 >= 12: flags.append(f'LONG RIDE {t2 - t1:.1f} h')
        back = [c for (tl, c) in left if c == city(b) and t2 - tl <= 30]
        if back: flags.append('U-TURN back to ' + city(b))
        left.append((t1, city(a)))
        day = lambda t: f'd{int(t // 24)} {int(t % 24):02d}:{int(round(t % 1 * 60)):02d}'
        print(f'{day(t1)} {a[:34]:34s} -> {day(t2)} {b[:34]:34s} {how[:40]:40s} ' + ('  <<< ' + '; '.join(flags) if flags else ''))


if __name__ == '__main__':
    main()
