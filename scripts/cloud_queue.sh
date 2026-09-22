#!/bin/bash
# Cloud half of the Sep 22 route-family queue. One search at a time; each result is committed and pushed
# to docs/cloud_results.txt as it lands, and runs already in that file are skipped, so a restart resumes.
cd "$(dirname "$0")"
R=../docs/cloud_results.txt; touch $R
W=${W:-3}
push () { git add $R; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1"; }
done_ () { grep -q "^$1 " $R; }
run () {  # run <tag> <start> <end> <tz> <at> <order>
  local tag=$1 st=$2 e=$3 tz=$4 at=$5 o=$6
  done_ $tag && { echo "skip $tag (already in results)"; return; }
  echo "$(date -u +%H:%M) start $tag: $st -> $e"
  BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start "$st" --end $e --at $at --tz $tz \
    --seed-states "$o" --budget 1200 --workers $W --days 20 --out ../out/fam_$tag.pkl > ../out/fam_$tag.log 2>&1
  echo "$tag rc=$? $(grep -E '^FINAL|^START|^END' ../out/fam_$tag.log | tr '\n' ' ')" | tee -a $R; push $tag
}
front () {  # front <tag> <free:XX> <order>: latest start collecting the 20 front states that makes Pasco by Mon 13:20 PT
  local tag=$1
  done_ $tag && { echo "skip $tag (already in results)"; return; }
  echo "$(date -u +%H:%M) start $tag"
  BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py --start $2 --end "Pasco Bus Stop" \
    --end-by 2026-09-28T13:20 --at 2026-09-24T00:00 --tz America/Los_Angeles \
    --done "OR,UT,AZ,NV,CA,NM,CO,KS,OK,TX,LA,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT" --seed-states "$3" \
    --budget 1200 --workers $W --days 20 --out ../out/front_$tag.pkl > ../out/front_$tag.log 2>&1
  echo "$tag rc=$? $(grep -E '^FINAL|^START|^END' ../out/front_$tag.log | tr '\n' ' ')" | tee -a $R; push $tag
}
mkdir -p ../out
python3 -u cloud_gate.py || { echo "GATE FAILED"; exit 2; }
run M_SPF_WV Spearfish WV America/Denver 2026-09-24T19:00 "SD,WY,MT,ID,WA,OR,UT,NV,CA,AZ,NM,CO,KS,OK,TX,LA,AR,MO,NE,IA,MN,ND,WI,IL,IN,KY,TN,MS,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,MI,OH,WV"
front K1_control free:WV "WV,KY,OH,MI,IN,IL,TN,MS,AR,MO,IA,NE,SD,ND,MN,WI,WY,MT,ID,WA"
front K2_mi free:MI "MI,OH,WV,KY,IN,IL,TN,MS,AR,MO,IA,NE,WI,MN,SD,WY,ND,MT,ID,WA"
front K3_ms free:MS "MS,TN,AR,MO,KY,WV,OH,MI,IN,IL,WI,MN,IA,NE,SD,WY,ND,MT,ID,WA"
run N_DIC_MI Dickinson MI America/Denver 2026-09-24T19:00 "ND,MT,ID,WA,OR,UT,NV,CA,AZ,NM,CO,WY,NE,SD,MN,WI,IL,IA,MO,KS,OK,TX,AR,LA,MS,TN,KY,IN,AL,FL,GA,SC,NC,VA,WV,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,MI"
run O_DIC_WV Dickinson WV America/Denver 2026-09-24T19:00 "ND,MT,ID,WA,OR,UT,NV,CA,AZ,NM,CO,WY,NE,SD,MN,WI,IL,IA,MO,KS,OK,TX,AR,LA,MS,TN,KY,IN,AL,FL,GA,SC,NC,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,MI,OH,WV"
run F_DIC_SD Dickinson SD America/Denver 2026-09-24T19:00 "ND,MT,ID,WA,OR,CA,NV,AZ,UT,WY,CO,NM,TX,OK,KS,MO,AR,LA,MS,AL,FL,GA,SC,NC,TN,KY,WV,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,MI,IN,IL,WI,MN,IA,NE,SD"
run G_DIC_MN Dickinson MN America/Denver 2026-09-24T19:00 "ND,MT,ID,WA,OR,CA,NV,AZ,UT,WY,CO,NM,TX,OK,KS,MO,AR,LA,MS,AL,FL,GA,SC,NC,TN,KY,WV,VA,MD,DE,PA,NJ,NY,CT,RI,MA,ME,NH,VT,OH,MI,IN,IL,WI,IA,NE,SD,MN"
echo "ALL CLOUD RUNS DONE"
