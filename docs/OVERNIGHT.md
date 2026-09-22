# Overnight runs

Appended by `scripts/overnight.sh`. One search at a time.

## Overnight queue, started 2026-09-22 05:17 UTC

Head: bb2d7d0. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|

## Overnight queue, started 2026-09-22 05:48 UTC

Head: 1e63717. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|

### Restarted 05:48 UTC, forward first

The 05:17 queue was stopped four minutes in. Its first run, `a_back48`, was doing 0.46 nodes a second
(160 nodes in 344 s), so the five backward runs in the original order would each have seen a few hundred
nodes and said nothing about breadth. Restarted at head 1e63717 with all six forward runs first and
backward last, and with two of the backward slots spent on forward knobs instead.

Two throughput fixes were tried and measured before the restart. A reverse-scan cache changed nothing (43
nodes at 62 s either way) and is not in the tree; `conn_pos` is, as a simplification rather than a fix. A
profile then put 46% of the search in `rides_into` and 25% in the scan both had attacked. See HANDOFF §13.

Gates before the restart: `regress.py` 6/6, and the control replays with no leg missing from the menu
(28/40 inside `--width 12`, 47/48 states, exit 0).
