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

## Overnight queue, started 2026-09-22 06:18 UTC

Head: 1ad47cf. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|
| `a_fwd48` | 0 min | no depth line | n/a | 0 | none |  | rc=143 |

## Overnight queue, started 2026-09-22 06:19 UTC

Head: 1ad47cf. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|

## Overnight queue, started 2026-09-22 07:18 UTC

Head: 1ad47cf. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|

### Why the first three queues died, and what the first full forward run showed

Three queues died young: 05:17 (stopped by hand), 05:48 (dead at 226 s of search) and 06:19 (dead at
414 s). Not OOM: the memory cgroup has no limit, `failcnt` 0, peak 423 MB against 16 GB. The 06:19 one
survived nine minutes, ending about eight minutes after the last tool call of the session. The container is
reclaimed when the session goes quiet, and no amount of `nohup`, `setsid` or cgroup reparenting beats that.
So the queue now resumes instead of restarting, and the hourly check-in supervises it while awake.

The 06:19 run did get far enough to say something about forward, which no run had before:

```
[   10s] 24/48 states,  80.7 h spent, at White River Junction, 11 rides, 37 nodes
[   42s] still 24/48,  8996 nodes (216/s), 1917 in frontier, 2017 kept
[  414s] still 24/48, 10372 nodes ( 25/s), 1703 in frontier, 2617 kept
```

Forward reaches 24/48 in ten seconds and then stops, and the interesting part is the rate: 216 nodes a
second falling to 25 while the frontier stays flat near 1700 and the kept set creeps up. It is not running
out of frontier, it is spending ever more per node, and the plateau is at 24 rather than the 25 recorded
earlier. Worth pointing the profiler at a forward run too, since the assumption that forward is fast holds
only for its first minute.
