#!/bin/bash
# Cloud job for route X (239.50 h; 238.08 h with the MATA 30/42 Holmes ending by hand). Gate first, then two
# tuning runs, one at a time; each result is committed and pushed to docs/cloud_results_x.txt, and a run
# already in that file is skipped, so a restart resumes.
cd "$(dirname "$0")"
R=../docs/cloud_results_x.txt; touch $R
W=${W:-3}
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1"; }
run () {  # run <tag> <seed order>
  grep -q "^$1 " $R && { echo "skip $1"; return; }
  echo "$(date -u +%H:%M) start $1"
  BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start free:WY --at 2026-09-25T12:00 --tz America/Denver \
    --seed-states "$2" --budget 1500 --workers $W --days 20 --out ../out/cx_$1.pkl > ../out/cx_$1.log 2>&1
  echo "$1 rc=$? $(grep -E '^FINAL|^START|^END' ../out/cx_$1.log | tr '\n' ' ')" | tee -a $R
  sed -n '/^FINAL/,$p' ../out/cx_$1.log | head -80 > ../docs/cloud_x_$1_legs.txt; git add ../docs/cloud_x_$1_legs.txt; push $1
}
mkdir -p ../out
python3 -u x_gate.py || { echo "GATE FAILED" | tee -a $R; push gate; exit 2; }
# X1: tune from X's own order. X2: the same with Kentucky unpinned, to go after the 5 h Louisville round trip.
run X1_tune "WY,MT,AZ,@Albuquerque Bus Station,LA,FL,ME,VT,WV,KY,MI,ND,NE,AR,MS"
run X2_noKY "WY,MT,AZ,@Albuquerque Bus Station,LA,FL,ME,VT,WV,MI,ND,NE,AR,MS"
echo "ALL X RUNS DONE"
