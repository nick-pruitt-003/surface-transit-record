"""Reverse a report CSV so the route runs end-to-start (distance model is symmetric).

usage: python3 reverse_csv.py in.csv out.csv
Blank board/alight cells are filled from the neighbouring leg before reversing; new states are recomputed.
"""
import csv, sys

with open(sys.argv[1], newline='') as fh: rows = list(csv.DictReader(fh))
if not rows: raise SystemExit('input report contains no data rows')
for i, r in enumerate(rows):          # fill gaps by chaining legs
    if not r['Alight at'] and i + 1 < len(rows): r['Alight at'] = rows[i + 1]['Board at']
    if not r['Board at'] and i: r['Board at'] = rows[i - 1]['Alight at']
seen = set(); out = []
for n, r in enumerate(reversed(rows), 1):
    states = [s for s in (r['States on this leg'] or '').split('>') if s][::-1]
    new = [s for s in states if s not in seen]; seen.update(new)
    q = dict(r); q['Leg'] = n; q['Board at'], q['Alight at'] = r['Alight at'], r['Board at']
    q['States on this leg'] = '>'.join(states)
    q['New states'] = ','.join(new)   # forward report's step-off stops don't carry over; pick them while testing
    if ' | ' in (r['Route'] or ''): q['Route'] = ' | '.join(r['Route'].split(' | ')[::-1])
    out.append(q)
with open(sys.argv[2], 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(out)
print(len(out), 'legs,', len(seen), 'states, starts at', out[0]['Board at'], '-> ends at', out[-1]['Alight at'])
