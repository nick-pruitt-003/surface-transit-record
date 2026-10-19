#!/bin/bash
# Cloud job: X_TOL (X with the interior entered at Toledo) then the joint audit. Results pushed to docs/.
cd "$(dirname "$0")"
push () { git add ../docs/cloud_tol.txt ../docs/joint_audit.txt 2>/dev/null; git commit -qm "cloud result: $1" || true; for i in 1 2 3; do git pull -q --rebase && git push -q && return 0; sleep 5; done; echo "PUSH FAILED $1" >&2; return 1; }
mkdir -p ../out; R=../docs/cloud_tol.txt; touch $R
# A search that exits nonzero is recorded as FAILED, which the skip check does not match, published, and the job
# stops there: a rerun retries it rather than taking its partial output as a result.
fail () { echo "FAILED $1 rc=$2" | tee -a $R; tail -20 "$3" >> $R; push "$1-failed"; exit 3; }
python3 -u x_gate.py || { echo "GATE FAILED (X did not reproduce 239.50)" | tee -a $R; push gate; exit 2; }
BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 -u time_search.py \
  --start "Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)" --at 2026-11-05T12:00 --tz America/Denver \
  --seed-states "WY,MT,AZ,@Albuquerque Bus Station,LA,FL,ME,VT,@Toledo Bus Stop,MI,WV,KY,ND,NE,AR,MS" \
  --budget 1800 --workers ${W:-2} --days 20 --out ../out/fam_XTOL.pkl > ../out/fam_XTOL.log 2>&1
rc=$?; [ $rc -eq 0 ] || fail X_TOL $rc ../out/fam_XTOL.log
echo "X_TOL rc=0 $(grep -E '^FINAL|^START|^END' ../out/fam_XTOL.log | tr '\n' ' ')" | tee -a $R
sed -n '/^FINAL/,$p' ../out/fam_XTOL.log | head -90 >> $R; push X_TOL || exit 4
python3 -u joint_audit.py > ../docs/joint_audit.txt 2>&1; rc=$?; echo "audit rc=$rc" >> $R
if [ $rc -ne 0 ]; then push audit-failed; exit $rc; fi
push audit || exit 4
echo "ALL DONE"
