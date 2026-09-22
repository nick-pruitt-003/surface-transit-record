#!/bin/bash
# One search at a time, in order of how much each would tell us, with a one-line summary appended to a
# tracked file after every run so the results survive even if the container does not.
#
# Order matters. A first asks whether the superset dominance committed at bb2d7d0 breaks the plateau at
# all, since that is untested at scale. B is the most diagnostic: a ladder over --states turns "it stops
# at 25/48" into a curve, and where the curve bends is the thing to attack. C only then asks which knob
# moves it, tested at the wall rather than blind.
set -u
cd "$(dirname "$0")"
OUT=../out
NOTES=../docs/OVERNIGHT.md
COMMON="--end VT --by 2026-10-03T22:54 --tz America/New_York --target 238 --order rate"
FWD="--start \"Huntington Bus Stop\" --at 2026-09-24T00:54"

note () { echo "$1" >> "$NOTES"; }

# A process started from a Claude Bash call lives in that call's cgroup, and the cgroup is torn down when
# the call's container is recycled, taking every process in it. That is what killed two queues five minutes
# after launch, with no OOM and no signal in any log: the first died at 344 s, the second at 226 s, and the
# memory cgroup showed no limit and failcnt 0. nohup does not help, because this is not SIGHUP. setsid on
# the queue itself is not enough either, because each run spawns a fresh python that inherits the cgroup it
# was spawned from. So every run moves itself and its children to the root cgroup before waiting on them.
detach () {
  local p c
  for p in "$@" $(pgrep -P "$1" 2>/dev/null); do
    for c in /sys/fs/cgroup/*/tasks; do [ -w "$c" ] && echo "$p" > "$c" 2>/dev/null; done
  done
}

run () {              # run <name> <budget_s> <extra args...>
  local name=$1 budget=$2; shift 2
  local log=$OUT/on_$name.log
  # Resume rather than restart. The container is reclaimed when the session goes quiet, so the queue does
  # not survive the night on its own: it is restarted by an hourly check-in, and without this every restart
  # would redo the first run for ever and never reach the rest. A log with a summary line in it is a run
  # that finished, so skip it.
  if [ -f "$log" ] && grep -q "nodes in .* s" "$log"; then
    echo "=== $name already done, skipping ===" >&2; return
  fi
  local t0=$(date -u +%s)
  echo "=== $name starting $(date -u +%H:%M:%S) ===" >&2
  timeout $((budget + 600)) python3 -u ride_search.py $COMMON --budget "$budget" "$@" > "$log" 2>&1 &
  local pid=$!
  sleep 1; detach $pid            # the python under timeout is a child, so detach picks it up too
  wait $pid
  local rc=$? t1=$(date -u +%s)
  local deep=$(grep -oE 'deepest [0-9]+/[0-9]+' "$log" | tail -1)
  local nodes=$(grep -oE '^[0-9]+ nodes in [0-9]+ s \([0-9]+/s\)' "$log" | tail -1)
  local found=$(grep -c 'FOUND' "$log")
  local best=$(grep -E '^best ' "$log" | tail -1)
  local chk=$(grep -E 'independent check' "$log" | tail -1)
  note "| \`$name\` | $(( (t1 - t0) / 60 )) min | ${deep:-no depth line} | ${nodes:-n/a} | $found | ${best:-none} | ${chk:-} | rc=$rc |"
}

mkdir -p $OUT
note ""
note "## Overnight queue, started $(date -u '+%Y-%m-%d %H:%M UTC')"
note ""
note "Head: $(git -C .. rev-parse --short HEAD). One search at a time. 237.3 h is the control: the test is"
note "that a run reproduces it, not that it beats it."
note ""
note "| run | wall | deepest | nodes | FOUND | best | independent check | rc |"
note "|---|---|---|---|---|---|---|---|"

# Forward first, and all of it, before any backward run. Backward moves at about one node a second here
# (56 nodes in 93 s, measured twice), so a 25 minute backward run sees a few hundred nodes and cannot say
# anything about breadth; forward does 274 a second and every question below is answerable there. Spending
# the night the other way round would have bought five starved runs. Backward stays in the queue, at the
# end, because "it is still slow at 25 minutes" is itself worth recording.

# A: does superset dominance break the plateau at all
eval run a_fwd48  1500 $FWD --states 48

# B: where is the wall. It does not bend. a_fwd48, b_fwd30 and b_fwd36 all stop at 24 or 25 states, all at
# White River Junction, all 80.7 h and eleven rides in, all reached inside ten seconds. b_fwd30 needed six
# more states and did not find one in 11530 nodes. The requirement is not what binds, so b_fwd42 and
# b_fwd45 are dropped: they would spend forty minutes confirming a wall now seen three times.
eval run b_fwd30  900  $FWD --states 30
eval run b_fwd36  900  $FWD --states 36

# C: which knob moves it. These are now the runs that matter. What binds is the opening dive: ordering by
# time per new state takes the cheap Northeast states first and strands the chain beside the finish at 80 h
# with half the country uncollected. --order early and --order states change that dive; --width does not,
# so it goes last.
eval run c_fwd48_early 1500 $FWD --states 48 --order early
eval run c_fwd48_states 1500 $FWD --states 48 --order states
eval run c_fwd48_w24   1500 $FWD --states 48 --width 24
eval run c_fwd48_w36   1500 $FWD --states 48 --width 36

# D: backward, last, for the record
eval run d_back48 1500 --dir backward --states 48
eval run d_back48_w24 1200 --dir backward --states 48 --width 24

note ""
note "Queue finished $(date -u '+%Y-%m-%d %H:%M UTC')."
echo "ALL DONE" >&2
