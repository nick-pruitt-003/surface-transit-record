#!/bin/bash
# Cloud job, two long searches, one after the other. Results in docs/cloud_wy_sun.txt.
# WY_LONG: X_TOL's front half (Sheridan -> Jacksonville Amtrak for the Meteor), seeded with X_TOL's own order, 60 min.
#   --at is noon ET so the first Sheridan bus is the Thursday 22:20 X_TOL rides; from 00:00 it took Wednesday's and lost a day.
#   The seed alone reaches Jacksonville in about 205.3 h, so a FINAL above 205.5 h means the seed did not reproduce
#   and the run is void. Below the control's front half (206.5 h from its first bus) it beats the control.
# SUN: a whole route from Sunland Park NM, east along the Gulf first and the Northwest spine westbound last, ending in CA
#   (unforced, the first run turned west and rode the spine eastbound), 90 min.
cd "$(dirname "$0")"
R=../docs/cloud_wy_sun.txt; : > $R
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1"; }
mkdir -p ../out
if [ -n "$RUN_WY" ]; then   # off: with the Meteor fixed, Sheridan 22:20 and the Meteor 16:11 pin X_TOL at 237.9 h
BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)" \
  --end "~-81.724,30.366,0.3" --end-by 2026-10-03T16:05 --at 2026-09-24T12:00 --tz America/New_York \
  --done "GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT" \
  --seed-states "WY,MT,ID,WA,OR,UT,NV,CA,@Albuquerque Bus Station,AZ,NM,CO,KS,OK,TX,LA,AR,TN,KY,IN,@Toledo Bus Stop,OH,MI,WV,IL,WI,MN,ND,SD,IA,NE,MO,MS,AL,FL" \
  --budget 3600 --workers ${W:-2} --days 20 --out ../out/wy_long.pkl > ../out/wy_long.log 2>&1
echo "WY_LONG rc=$? $(grep -E '^FINAL|^START|^END' ../out/wy_long.log | tr '\n' ' ')" | tee -a $R
sed -n '/^FINAL/,$p' ../out/wy_long.log | grep -E '^d|^FINAL|^START|^  (walk|local)' | head -50 >> $R; push WY_LONG
fi
BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "Sunland Park Casino" \
  --start-alt "Sunland Park & Doniphan" --end CA --at 2026-09-24T00:00 --tz America/Denver \
  --seed-states "NM,TX,LA,MS,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,WV,OH,MI,IN,KY,TN,AR,OK,KS,MO,IL,IA,NE,CO,SD,ND,WI,MN,WY,MT,ID,WA,OR,UT,NV,CA,AZ" \
  --budget 5400 --workers ${W:-2} --days 20 --out ../out/sun.pkl > ../out/sun.log 2>&1
echo "SUN rc=$? $(grep -E '^FINAL|^START|^END' ../out/sun.log | tr '\n' ' ')" | tee -a $R
sed -n '/^FINAL/,$p' ../out/sun.log | grep -E '^d|^FINAL|^START|^  (walk|local)' | head -80 >> $R; push SUN
echo "ALL DONE"
