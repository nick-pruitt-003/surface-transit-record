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
| `a_fwd48` | 27 min | deepest 25/48 | 13248 nodes in 1502 s (9/s) | 0 | none |  | rc=0 |
| `b_fwd30` | 17 min | deepest 24/30 | 11530 nodes in 900 s (13/s) | 0 | none |  | rc=0 |

### The states ladder answers a different question than it asked

`b_fwd30` was meant to find where the wall bends when fewer states are required. It does not bend:

| run | required | deepest | when | where | budget spent after |
|---|---|---|---|---|---|
| `a_fwd48` | 48 | 25 | ~10 s | White River Junction, 80.7 h, 11 rides | 13248 nodes, nothing better |
| `b_fwd30` | 30 | 24 | 9 s | White River Junction, 80.7 h, 11 rides | 11530 nodes, nothing better |

Same stop, same depth, same clock, same ride count. `b_fwd30` needed six more states and could not find them
in fifteen minutes. Lowering the requirement changes nothing, so the requirement is not what binds.

What binds is the opening dive. `--order rate` sorts candidates by time per new state, and the cheapest
states per hour are the small ones stacked along the Northeast corridor, so the search takes them first and
arrives beside the finish at 80 h holding 24 states. From there the remaining half of the country cannot be
collected and returned from inside the limit, so every continuation dies on the deadline tables. The 237
control does the Northeast **last**, for exactly this reason.

Two consequences. First, `deepest` is not a progress measure: it is printed when a node is popped, before
pruning, so it reports how far one doomed chain got. A run that says 25/48 may never have had a live chain
past 12. Second, the ladder runs still queued (`b_fwd36`, `b_fwd42`, `b_fwd45`) will almost certainly repeat
the same 24 at the same stop, and the runs that matter are the ordering ones, `c_fwd48_early` and
`c_fwd48_states`, which change the dive itself.
| `b_fwd36` | 16 min | deepest 24/36 | 11512 nodes in 901 s (13/s) | 0 | none |  | rc=0 |

## Overnight queue, started 2026-09-22 08:19 UTC

Head: 9445381. One search at a time. 237.3 h is the control: the test is
that a run reproduces it, not that it beats it.

| run | wall | deepest | nodes | FOUND | best | independent check | rc |
|---|---|---|---|---|---|---|---|

### Queue re-pointed at the ordering runs, 08:19 UTC

`b_fwd36` made it three for three: 11512 nodes in 901 s, deepest 24/36, same stop and clock as the other
two. `b_fwd42` and `b_fwd45` are dropped rather than run, because forty minutes spent confirming a wall
seen three times buys nothing, and the night has room for about two runs an hour.

What replaces them is the pair that tests the diagnosis instead of the symptom. `--order early` and
`--order states` change the opening dive; `--width` only widens a dive that is going the wrong way, so it
now sits behind them. If the diagnosis is right, an ordering that does not front-load the Northeast should
get past 25 states, and if neither does, the dive is not the whole story and the next thing to look at is
why the frontier never recovers once the greedy chain has poisoned it.
| `c_fwd48_early` | 26 min | deepest 25/48 | 14684 nodes in 1500 s (10/s) | 0 | none |  | rc=0 |

### Ordering does not move the wall, so the diagnosis was wrong

`c_fwd48_early` ran the full 1500 s and stopped at 25/48, the same place `--order rate` stops. It got there
by a different road, Hanover at 68.1 h and Wilmington at 78.8 h, nineteen rides deep against rate's eleven
to White River Junction, so the knob does change the dive. It just does not change where the dive ends.

That kills the explanation offered two sections up. Front-loading the Northeast is real, but the candidate
ordering is not what causes it, because every ordering does it.

What does cause it is one line up from the ordering, in the priority function:

```
pri = spent - credit * 3600 * n_states          # --credit defaults to 5.0 h
```

237 h over 48 states is 4.94 h per state, so the default prices every state at the average and the priority
is "hours behind the ideal pace". Now price the wall with it. A chain holding 24 states at 80 h is running
at 3.3 h per state, comfortably ahead, and the queue rewards it accordingly. But it is ahead only because
the states it took are the cheap dense ones in the Northeast; the 24 it still owes are spread across the
West and need 157 h, or 6.5 h each. A flat per-state credit cannot see the difference, so it promotes every
chain that spent the cheap half and starves the ones that did the West first, which is what the control
does. Changing `--order` cannot fix that, because `--order` only picks among the children of a node the
priority function already chose.

The obvious next move is a `--credit` sweep, and it is worth one run, but a scalar is the wrong shape and
this project has been here before: a flat price per state is exactly the kind of summary statistic that has
broken four times already. The exact quantity is on hand instead. `L[y][stop]` is the latest you can be at
a stop and still collect y and finish, so for a node standing at `stop` at `t` the slack

```
min over owed y of ( L[y][stop] - t )
```

is how close the chain is to losing the state it can least afford to lose, read straight off the deadline
tables rather than estimated. Ranking by slack prefers chains that are still comfortable everywhere over
chains that are far ahead on average and already out of time somewhere, which is the distinction a flat
credit cannot draw.

Falsification, stated before building it: if slack ranking is right, a run should pass 25 states and the
chains it expands late should be ones with the West already collected. If it stalls at 25 like everything
else, then the wall is not in the ranking at all and the next suspect is the pruning, not the priority.
