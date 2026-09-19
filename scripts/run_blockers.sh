#!/bin/zsh
# Blocker finder on the less-optimised sub-250 routes, one at a time.
cd /Users/nick_pruitt/Downloads/bus48/scripts
export BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 BUS48_SCAN_SLACK_H=24
PY=/opt/homebrew/bin/python3
for n in fixFargoDenver fixDenverN1; do
  nice -n 10 $PY -u blocker_finder.py --route ../out/res_$n.pkl --start "White River Junction" --at 2026-09-24T04:20 --tz America/New_York > ../out/blk_$n.log 2>&1
done
nice -n 10 $PY -u blocker_finder.py --route ../out/res_denverV7c.pkl --start "Pasco" --at 2026-09-24T12:00 --tz America/Los_Angeles > ../out/blk_denverV7c.log 2>&1
