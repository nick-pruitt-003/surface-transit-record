#!/bin/bash
# Cloud job: latest start that still makes the Silver Meteor at Jacksonville Amtrak (16:11) with the other 33 states
# done, so the shared tail (Meteor, Acela, Portland loop, Dartmouth Coach 19:30, VT line 22:14) finishes the route.
# Deadline Sat Oct 3 16:05 ET. The control's front half starts Fri Sep 25 00:54 ET for that Meteor, X_TOL's Thu Sep 24
# 22:20 MT. A start later than the control's beats it by the difference. Results in docs/cloud_latest.txt.
cd "$(dirname "$0")/.."   # run from scripts/: the live modules and ../out are relative to it
R=../docs/cloud_latest.txt; touch $R
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1" >&2; return 1; }
# A search that exits nonzero is recorded as FAILED, which the skip check does not match, published, and the job
# stops there: a rerun retries it rather than taking its partial output as a result.
fail () { echo "FAILED $1 rc=$2" | tee -a $R; tail -20 "$3" >> $R; push "$1-failed"; exit 3; }
mkdir -p ../out
python3 -u rebuild_237.py > ../out/rebuild.log 2>&1 || { echo "REBUILD FAILED" | tee -a $R; tail -20 ../out/rebuild.log >> $R; push rebuild; exit 2; }
python3 -u regress.py > ../out/regress.log 2>&1 || { echo "REGRESS FAILED" | tee -a $R; tail -20 ../out/regress.log >> $R; push regress; exit 2; }
echo "regress ok: $(tail -1 ../out/regress.log)" | tee -a $R
TAIL="GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT"
run () { # name start seed
  BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "$2" \
    --end "~-81.724,30.366,0.3" --end-by 2026-11-14T16:05 --at 2026-11-05T00:00 --tz America/New_York \
    --done "$TAIL" --seed-states "$3" --budget 1500 --workers ${W:-2} --days 20 --out ../out/lat_$1.pkl > ../out/lat_$1.log 2>&1
  local rc=$?; [ $rc -eq 0 ] || fail $1 $rc ../out/lat_$1.log
  echo "$1 rc=0 $(grep -E '^FINAL|^START|^END|latest' ../out/lat_$1.log | tr '\n' ' ')" | tee -a $R
  sed -n '/^FINAL/,$p' ../out/lat_$1.log | grep -E '^d|^FINAL|^START' | head -40 >> $R; push $1 || exit 4
}
run WV free:WV "WV,KY,OH,MI,IN,IL,TN,MS,AR,MO,IA,NE,SD,ND,MN,WI,WY,MT,ID,WA,OR,UT,AZ,NV,CA,NM,CO,KS,OK,TX,LA,AL,FL"
run WY free:WY "WY,MT,ID,WA,OR,UT,NV,CA,AZ,NM,CO,KS,OK,TX,LA,AR,TN,KY,IN,OH,MI,WV,IL,WI,MN,ND,SD,IA,NE,MO,MS,AL,FL"
run MI free:MI "MI,OH,WV,KY,IN,IL,WI,MN,ND,SD,IA,NE,MO,KS,CO,WY,MT,ID,WA,OR,UT,NV,CA,AZ,NM,OK,TX,AR,TN,MS,LA,AL,FL"
echo "ALL DONE"
