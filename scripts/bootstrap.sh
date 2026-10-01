#!/usr/bin/env bash
# Bring a fresh checkout up to a state where a search can run, and prove it.
#
# Everything the router needs is committed, including all 42 GTFS files, so a clone carries the whole
# world (about 121 MB packed). Three things are NOT in git and have to be regenerated here:
#
#   scripts/csa.so            build artifact. cached_router does NOT hash csa.c, so a stale .so is not
#                             merely old, it is WRONG: the signature gained two parameters in c478bf1.
#   out/res_starttest.pkl     the 237 control, rebuilt by rebuild_237.py. Without it nothing can be
#   out/hun_ms_meteor.pkl     gated or tracked, and every "gate" silently measures nothing.
#   out/res_wheeling.pkl      the 234 h Wheeling route, for --track. Written by wheeling_start.py.
#
# Run it from inside scripts/, like regress.py, because paths resolve against ../out relatively.
#
#     cd scripts && ./bootstrap.sh
#
# It is idempotent and safe to re-run. It exits non-zero the moment anything fails to reproduce, because
# a bootstrap that reports success on a broken checkout is worse than no bootstrap.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== 1. toolchain ==="
python3 -VV
cc --version | head -1
python3 - <<'PY'
import sys
missing = []
for m in ('numpy', 'scipy', 'shapely', 'timezonefinder'):
    try: __import__(m)
    except ImportError: missing.append(m)
if missing:
    sys.exit(f'missing Python packages: {" ".join(missing)}\n  pip install {" ".join(missing)}')
print('numpy, scipy, shapely, timezonefinder present')
PY

echo
echo "=== 2. csa.so ==="
# Unconditional. cached_router keys on data/, time_router.py and common.py but NOT on csa.c, so there is
# no mechanism that would notice a stale object; rebuilding costs a second and removes the whole class.
cc -O3 -shared -fPIC csa.c -o csa.so
echo "built $(ls -la csa.so | awk '{print $5}') bytes from csa.c"

echo
echo "=== 3. result pickles (first router build is ~75 s, then cached at ~2 s) ==="
mkdir -p ../out
python3 rebuild_237.py
python3 wheeling_start.py --write ../out/res_wheeling.pkl

echo
echo "=== 4. gates ==="
python3 regress.py

echo
echo "=== ready ==="
cat <<'EOF'
The search that the measurements point at, --goal rather than the default slack key
(replay: 38/40 legs inside --width 12 against 31/40, Saint George rank 3 against 509160):

  python3 ride_search.py --start "Wheeling 949 Main St (Jaguar)" \
    --at 2026-09-24T03:55 --tz America/New_York \
    --end VT --by 2026-10-04T01:55 --target 238 \
    --goal --pairs push --budget 7200 --out ../out/wheeling_goal.pkl

Budget notes, measured rather than guessed:
  * --pairs push spends about 1060 s building pair tables BEFORE it searches. --budget covers the
    search loop only, so wall-clock is roughly budget + 20 min.
  * --goal costs about 30 ms a node against a per-node budget of about 40, which is exactly why it
    lost a depth race (23 against 26) while winning the replay. Give it hours, not minutes.
  * On 4 cores the slack run managed 2 nodes/s and reached an honest 26/48, budget-bound rather than
    stuck: every depth bucket in its exit frontier was pair-live N/N.

And the trap that has cost three wrong measurements in one session: never set a start clock to a
service's own departure minute. Boarding needs best[a] + MIN_TRANSFER <= dep, so the bus you meant to
catch is exactly MIN_TRANSFER out of reach and the scan silently takes the next one, one whole service
interval later. That is why --at above is 03:55 and not 04:00.
EOF
