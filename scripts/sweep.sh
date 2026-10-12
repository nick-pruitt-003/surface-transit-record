#!/bin/bash
# Unguided sweep with early abort on known families. One search at a time; resumable (a run whose log has FINAL or
# ABORTED is skipped on restart). Seeds: one comma list per line in DIR/seeds.txt (random_seeds.py N SEED).
#   bash sweep.sh ../out/sweep3 [budget=780] [patience=240] [grace=300]
# A run whose best route settles into a family in known_families.json after `grace` seconds is stopped and logged
# ABORTED, and the queue moves on. Families stay covered by the focused searches.
cd "$(dirname "$0")" || exit 1
O=$1; BUDGET=${2:-780}; PATIENCE=${3:-240}; GRACE=${4:-300}
export BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 BUS48_WORKERS=${BUS48_WORKERS:-16} PYTHONUNBUFFERED=1
PY=${PY:-py}
i=0
while IFS= read -r seed; do
  i=$((i + 1)); n=$(printf '%02d' $i); log=$O/run_$n.log; live=$O/run_$n.live.json
  grep -qE '^(FINAL|ABORTED)' $log 2>/dev/null && continue
  rm -f $live
  BUS48_LIVE=$live $PY -X utf8 time_search.py --start free:${seed%%,*} --at 2026-11-05T00:00 \
    --seed-states $seed --budget $BUDGET --patience $PATIENCE --out $O/run_$n.pkl > $log 2>&1 &
  pid=$!
  # poll until the search ends or its best settles into a known family after the grace period
  while kill -0 $pid 2>/dev/null; do
    v=$($PY -X utf8 family_watch.py $live --check 2>/dev/null)
    age=$($PY -c "import json,time;L=json.load(open('$live'));print(int(L['now']-L['started']))" 2>/dev/null || echo 0)
    if [[ $v == ABORT* && $age -ge $GRACE ]]; then
      winpid=$(cat /proc/$pid/winpid 2>/dev/null)
      if [ -n "$winpid" ]; then taskkill //F //T //PID $winpid > /dev/null 2>&1; else kill $pid 2>/dev/null; fi
      wait $pid 2>/dev/null
      echo "ABORTED $v" >> $log; echo "run $n aborted $(date): $v" >> $O/progress.txt
      break
    fi
    sleep 20
  done
  wait $pid 2>/dev/null
  grep -q '^FINAL' $log && echo "run $n done $(date): $(grep '^FINAL' $log)" >> $O/progress.txt
done < $O/seeds.txt
$PY -X utf8 - "$O" > $O/summary.md <<'PY'
import glob, re, sys
O = sys.argv[1]; rows = []; ab = []
for p in sorted(glob.glob(f'{O}/run_*.log')):
    t = open(p, encoding='utf-8', errors='replace').read(); run = re.search(r'run_\d+', p).group(0)
    m = re.search(r'^FINAL ([\d.]+) h (.*)$', t, re.M); s = re.search(r'^START (.*) first bus (.*)$', t, re.M)
    a = re.search(r'^ABORTED (.*)$', t, re.M)
    if a: ab.append((run, a.group(1)))
    elif m and s: rows.append((float(m.group(1)), run, s.group(1), s.group(2), m.group(2)))
rows.sort()
print(f'# Sweep results ({O})\n\nRecord 238.83 h. Known families stopped early: {len(ab)}.\n')
print('| rank | hours | run | start | first bus | finish |\n|---|---|---|---|---|---|')
for k, r in enumerate(rows, 1): print(f'| {k} | {r[0]:.1f} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |')
if ab: print('\n## Stopped early (known family)\n'); [print(f'- {r}: {v}') for r, v in ab]
PY
echo "SWEEP DONE $(date)" >> $O/progress.txt
