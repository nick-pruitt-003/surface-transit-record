# Cloud sweep sketch (not wired up)

A sweep is 24 independent `time_search` runs that share nothing, so it fits a CI matrix: 24 parallel jobs turn the
local 5 hours into about 20 minutes of wall clock. Focused searches and data work stay on the Windows box, where
the router is cached and the loop with Nick (screenshot, data change, re-time) is minutes, not a CI round trip.

This is a sketch for review. Nothing here is committed under `.github/`, so nothing runs.

## Shape

1. **prepare** (one job): checkout, build `csa.so`, build the router once and cache its pickle keyed on `data/` and
   the router sources, generate seeds (`random_seeds.py 24 <seed>`), emit them as the matrix.
2. **run** (24 jobs, one per seed): restore the router cache (2 s instead of ~1-3.5 min), run `time_search` with
   the sweep settings and the same early abort as `sweep.sh` (`family_watch.py` against `known_families.json`),
   upload log, pickle and live file as an artifact.
3. **collect** (one job): download every artifact, write the ranked `summary.md` (same table as `sweep.sh`),
   flag Ohio Coach, upload it.

## Workflow sketch

```yaml
name: sweep
on:
  workflow_dispatch:
    inputs:
      seed:   {description: 'random_seeds.py seed', default: '3001'}
      n:      {description: 'number of runs', default: '24'}
      budget: {description: 'seconds per run', default: '780'}

jobs:
  prepare:
    runs-on: ubuntu-latest   # GitHub-hosted, works on a personal account (Blacksmith needs an org)
    outputs: {seeds: ${{ steps.seeds.outputs.json }}}
    steps:
      - uses: actions/checkout@v4
        with: {lfs: false}
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install numpy scipy shapely timezonefinder openpyxl
      - run: cd scripts && cc -O3 -shared -fPIC csa.c -o csa.so
      - uses: actions/cache@v4
        with:
          path: out/router_*.pkl
          key: router-${{ hashFiles('data/**', 'scripts/time_router.py', 'scripts/common.py', 'scripts/csa.c') }}
      - id: seeds
        run: |
          cd scripts
          python3 random_seeds.py ${{ inputs.n }} ${{ inputs.seed }} > ../seeds.txt
          python3 -c "import json;print('json='+json.dumps([l.strip() for l in open('../seeds.txt') if l.strip()]))" >> $GITHUB_OUTPUT

  run:
    needs: prepare
    runs-on: ubuntu-latest
    timeout-minutes: 40
    strategy:
      fail-fast: false
      matrix: {seed: '${{ fromJson(needs.prepare.outputs.seeds) }}'}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install numpy scipy shapely timezonefinder
      - run: cd scripts && cc -O3 -shared -fPIC csa.c -o csa.so
      - uses: actions/cache/restore@v4
        with:
          path: out/router_*.pkl
          key: router-${{ hashFiles('data/**', 'scripts/time_router.py', 'scripts/common.py', 'scripts/csa.c') }}
      - name: search (stopped early if it settles into a known family)
        env: {BUS48_WORKERS: '4', BUS48_LIVE: '../run/live.json', PYTHONUNBUFFERED: '1'}
        run: |
          mkdir -p run && cd scripts
          seed='${{ matrix.seed }}'
          setsid python3 time_search.py --start free:${seed%%,*} --at 2026-09-24T00:00 --seed-states "$seed" \
            --budget ${{ inputs.budget }} --patience 240 --out ../run/run.pkl > ../run/run.log 2>&1 &
          pid=$!
          if python3 family_watch.py ../run/live.json --grace 300 --every 20 > ../run/abort.txt; then
            kill -- -$pid; echo "ABORTED $(cat ../run/abort.txt)" >> ../run/run.log
          fi
          wait $pid || true
      - uses: actions/upload-artifact@v4
        with: {name: 'run-${{ strategy.job-index }}', path: run/}

  collect:
    needs: run
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {path: runs}
      - run: |
          # same table as scripts/sweep.sh, over runs/run-*/run.log, plus an Ohio Coach column
          python3 scripts/sweep_summary.py runs > summary.md    # to write: factor the table out of sweep.sh
      - uses: actions/upload-artifact@v4
        with: {name: summary, path: summary.md}
```

## Open points before it is real

- **Runners and cost.** Nick's GitHub is a personal account, so Blacksmith (org only) and GitHub's larger runners
  (paid org plans) are out. Standard `ubuntu-latest` runners have 4 vCPU (`BUS48_WORKERS=4`, so each run searches
  about a quarter as much as the 16-worker local box per minute; give runs a longer budget). Free plan: 2000
  minutes a month for private repos, unlimited for public; a 24-run sweep at ~20 min a job is ~480 minutes.
- **Router build in CI.** Measured 63 s here; on a runner, likely 1-3.5 min once per data change (then cached).
  `cached_router` keys on `data/` and the router sources but not `csa.c` (bootstrap.sh's warning), so the cache
  key above adds `csa.c` itself.
- **Reproducibility is better than local.** Every job sees the commit it started from; the local sweep 2 had data
  land mid-run.
- **Results do not land in the repo.** They come back as artifacts; someone (or a session) downloads and writes
  them into `docs/sweep.md`, as now.
- **Repo size.** The checkout carries ~121 MB of GTFS per job; fine for 24 jobs, worth a shallow clone.
- `sweep_summary.py` does not exist yet: the table is inline in `sweep.sh` and would be factored out.
