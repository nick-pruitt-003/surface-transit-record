#!/bin/bash
# Cloud job: SUN2, a whole route from Sunland Park NM ending in CA, 90 min. Results in docs/cloud_sun2.txt.
# SUN (254.6 h) had a fast Gulf front (Meteor at Jacksonville 61 h after the start) and a westbound spine finish,
# but spent three days zigzagging the plains: KC -> Topeka -> Denver -> Cheyenne -> back to Denver -> Omaha -> Fargo ->
# Billings. SUN2 pins Buffalo WY before Billings, so CO, WY and MT come on the way into the spine
# (Denver -> Cheyenne -> Buffalo 21:25 -> JL 701 -> Billings 00:25 -> the 01:30 to Spokane), and the plains run one way.
cd "$(dirname "$0")/.."   # run from scripts/: the live modules and ../out are relative to it
R=../docs/cloud_sun2.txt; : > $R
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1" >&2; return 1; }
# A search that exits nonzero is recorded as FAILED, which the skip check does not match, published, and the job
# stops there: a rerun retries it rather than taking its partial output as a result.
fail () { echo "FAILED $1 rc=$2" | tee -a $R; tail -20 "$3" >> $R; push "$1-failed"; exit 3; }
mkdir -p ../out
python3 -u rebuild_237.py > ../out/rebuild.log 2>&1 && python3 -u regress.py > ../out/regress.log 2>&1 || { echo "REGRESS FAILED" | tee -a $R; tail -25 ../out/regress.log ../out/rebuild.log >> $R; push regress; exit 2; }
echo "regress ok: $(tail -1 ../out/regress.log)" | tee -a $R
BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "Sunland Park Casino" \
  --start-alt "Sunland Park & Doniphan" --end CA --at 2026-11-05T00:00 --tz America/Denver \
  --seed-states "NM,TX,OK,AR,TN,MS,LA,AL,FL,GA,SC,NC,VA,MD,DE,NJ,NY,CT,VT,NH,MA,RI,ME,PA,WV,OH,IN,KY,MI,IL,WI,MN,ND,SD,IA,NE,MO,KS,CO,@~-106.690,44.355,1.0,WY,MT,ID,WA,OR,UT,AZ,NV,CA" \
  --budget 5400 --workers ${W:-2} --days 20 --out ../out/sun2.pkl > ../out/sun2.log 2>&1
rc=$?; [ $rc -eq 0 ] || fail SUN2 $rc ../out/sun2.log
echo "SUN2 rc=0 $(grep -E '^FINAL|^START|^END' ../out/sun2.log | tr '\n' ' ')" | tee -a $R
sed -n '/^FINAL/,$p' ../out/sun2.log | grep -E '^d|^FINAL|^START|^  (walk|local)' | head -90 >> $R; push SUN2 || exit 4
echo "ALL DONE"
