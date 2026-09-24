#!/bin/bash
# Cloud job: X_TOL (X with the interior entered at Toledo) then the joint audit. Results pushed to docs/.
cd "$(dirname "$0")"
push () { git add ../docs/cloud_tol.txt ../docs/joint_audit.txt 2>/dev/null; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1"; }
mkdir -p ../out; R=../docs/cloud_tol.txt; touch $R
python3 -u x_gate.py || { echo "GATE FAILED (X did not reproduce 239.50)" | tee -a $R; push gate; exit 2; }
BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py \
  --start "Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)" --at 2026-09-24T12:00 --tz America/Denver \
  --seed-states "WY,MT,AZ,@Albuquerque Bus Station,LA,FL,ME,VT,@Toledo Bus Stop,MI,WV,KY,ND,NE,AR,MS" \
  --budget 1800 --workers ${W:-2} --days 20 --out ../out/fam_XTOL.pkl > ../out/fam_XTOL.log 2>&1
echo "X_TOL rc=$? $(grep -E '^FINAL|^START|^END' ../out/fam_XTOL.log | tr '\n' ' ')" | tee -a $R
sed -n '/^FINAL/,$p' ../out/fam_XTOL.log | head -90 >> $R; push X_TOL
python3 -u joint_audit.py > ../docs/joint_audit.txt 2>&1; echo "audit rc=$?" >> $R; push audit
echo "ALL DONE"
