#!/bin/bash
# Cloud job: front halves for the Cleveland tail. Results in docs/cloud_cle.txt.
# Tail (priced exactly, Sep 25): Greyhound Cleveland (Brook Park) 04:30 -> Albany 14:40 -> Yankee Trails 17:15 ->
# Bennington -> Albany 21:05 -> NYC -> 01:00 bus -> Boston 05:30 -> Providence -> Boston -> Concord Coach -> Portland
# 11:55 next day: 31.4 h boarding Mon-Thu, 32.2 h Fri, a day more on weekends (Bennington runs weekdays only).
# It collects NY VT MA NH ME RI CT, so those are --done here. Each run reaches Cleveland with the other 41 states;
# total = first bus -> next weekday 04:30 at Cleveland + the tail. Beats the control if the front is under 205.9 h.
cd "$(dirname "$0")/.."   # run from scripts/: the live modules and ../out are relative to it
R=../docs/cloud_cle.txt; : > $R
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1" >&2; return 1; }
# A search that exits nonzero is recorded as FAILED, which the skip check does not match, published, and the job
# stops there: a rerun retries it rather than taking its partial output as a result.
fail () { echo "FAILED $1 rc=$2" | tee -a $R; tail -20 "$3" >> $R; push "$1-failed"; exit 3; }
mkdir -p ../out
run () { # name start seed
  BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "$2" --at 2026-11-05T12:00 --tz America/Denver \
    --end "Cleveland Bus Station (Brook Park)" --end-by 2026-11-16T02:25 \
    --done "NY,VT,MA,NH,ME,RI,CT" --seed-states "$3" \
    --budget 3600 --workers ${W:-2} --days 20 --out ../out/cle_$1.pkl > ../out/cle_$1.log 2>&1
  local rc=$?; [ $rc -eq 0 ] || fail $1 $rc ../out/cle_$1.log
  echo "$1 rc=0 $(grep -E '^FINAL|^START|^END' ../out/cle_$1.log | tr '\n' ' ')" | tee -a $R
  sed -n '/^FINAL/,$p' ../out/cle_$1.log | grep -E '^d|^  (walk|local)' | head -70 >> $R; push $1 || exit 4
}
run SHE "Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)" "WY,MT,ID,WA,OR,UT,NV,CA,AZ,@Albuquerque Bus Station,NM,CO,KS,OK,TX,LA,MS,AL,FL,GA,SC,NC,VA,MD,DE,NJ,PA,WV,KY,TN,AR,MO,IA,NE,SD,ND,MN,WI,IL,IN,MI,OH"
run FLA free:FL "FL,GA,SC,NC,VA,MD,DE,NJ,PA,WV,KY,TN,MS,AL,LA,TX,NM,AZ,CA,NV,UT,OR,WA,ID,MT,WY,CO,KS,OK,AR,MO,IA,NE,SD,ND,MN,WI,IL,IN,MI,OH"
echo "ALL DONE"
