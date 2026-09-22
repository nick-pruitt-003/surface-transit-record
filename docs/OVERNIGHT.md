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
| `c_fwd48_states` | 26 min | deepest 25/48 | 8419 nodes in 1500 s (6/s) | 0 | none |  | rc=0 |

## The wall, found: positioning moves are sorted to the back and then cut off

`c_fwd48_states` stopped at 25/48 like everything else, five runs for five walls, so the ranking mattered
less than any of the knobs suggested. The `--track` replay says why, and it is not a knob at all.

Ranking the control's forty legs by where the search puts them:

| leg | destination | rank | collects |
|---|---|---|---|
| 21 | Saint George | 486385 / 1156415 | nothing |
| 6 | Holmes at Elvis Presley | 16727 / 375718 | nothing |
| 10 | Des Moines | 6524 / 199476 | IA |
| 7 | Airways Transit Center | 1293 / 25989 | nothing |
| 31 | Houston 808 Jefferson St | 129 / **129** | nothing |
| 23 | Bonneville Transit Center | 98 / 331320 | nothing |

Median rank is 4, so most of the route is ranked fine. What is not fine is every leg that collects no new
state, and leg 31 is ranked last out of its own list of 129. All three orderings share a first sort key:

```python
if   a.order == 'rate':   opts.sort(key=lambda o: (n_new(o) == 0, (o[1] - t) / max(1, n_new(o))))
elif a.order == 'states': opts.sort(key=lambda o: (n_new(o) == 0, -n_new(o), -o[1]))
else:                     opts.sort(key=lambda o: (n_new(o) == 0, -o[1]))
```

`n_new(o) == 0` is False before True, so every repositioning ride sorts behind every state-collecting ride,
and then `opts[:a.width]` cuts. While any option collects a state, the search cannot reposition. The
control needs to reposition at least five times, one of them the Memphis hop to Holmes that CLAUDE.md
records as load-bearing for Mississippi five days later.

This explains the whole night at once. Ordering did not move the wall because all three orderings carry
the same key. Width cannot move it either, so `c_fwd48_w24` and `c_fwd48_w36` are already answered: no
width reaches rank 486385. The states ladder did not bend because the requirement was never what bound.
And 24 or 25 states is simply where the route first needs a move the search is forbidden to consider.

It is also the same failure the file already lists four times: a reasonable-sounding rule, here "prefer
moves that make progress", quietly deleting the sparse link the route depends on. A ride that collects
nothing is not a wasted ride; it is how you stand in the right place at the right time.

### The reserve did not clear the wall, and the test that says so is weak

One full search with the positioning reserve: 17477 nodes in 1503 s, deepest 25/48. Reverted, per the
condition stated when it went in.

Two honest caveats on that.

It did change the trajectory. It reached 25 states at 203 s, twenty-one rides deep at Detroit Bus Station,
101.1 h spent, where every earlier run reached 24 or 25 inside ten seconds at eleven rides. Twenty-one
rides and 101 h is much closer to the shape of the control than eleven rides into the Northeast. So the
reserve does something; it just does not get past 25.

And the criterion was poor. `deepest` is printed when a node is popped, before pruning, so it counts how
far a doomed chain got, which this very file argued three sections ago. Judging a fix by it is judging by
the wrong number. The revert is the disciplined call given the stated condition, but it rests on a weak
test rather than a clean refutation, and the fix may deserve a second look under a better one.

A better test exists and should be built before touching the ranking again: instrument `--track` to report,
per leg, whether the control's ride is in the shortlist the search would actually expand, rather than its
rank in the full sorted list. That answers the question directly. Rank is not the quantity of interest;
membership in the expanded set is.

### What to do next, and why it is not a scalar

The diagnosis stands and is the most solid result of the night: positioning rides sort behind every
state-collecting ride, and among themselves they are ranked by how little time they burn, which is
meaningless for them. That is why a five minute local hop outranks Saint George by half a million places.

The exact quantity is already in the deadline tables. For an option arriving at `to` at `at`,

```
slack = min over owed y of ( L[y][to] - at )
```

is how close that move leaves the chain to losing the state it can least afford. It is a numpy min over the
owed rows at one column, the same shape as the existing `ceiling(collected)`, so it is affordable per
candidate, and it is read off the tables rather than estimated. Ranking positioning rides by slack prefers
a long repositioning ride that keeps the West reachable over a local hop that burns five minutes and
achieves nothing, which is exactly the distinction duration cannot draw.

Falsification, before building: if slack ranking is right, the instrumented `--track` should show the
control's positioning legs inside the expanded set, and a run should reach states it has never reached. If
the legs are still outside, the ranking is not the binding constraint and the pruning is the next suspect.

## The measurement that settles it: rank within the leg's own group

`--track` now reports, per leg, where the control's ride sits among its own kind as well as overall, which
is the number that decides what to do. All twelve legs outside `--width 12`:

| leg | destination | group rank | collects |
|---|---|---|---|
| 36 | Washington Union | 13/13 collecting | GA SC NC VA |
| 25 | Las Vegas Amtrak | 13/14 collecting | NM |
| 2 | Detroit | 25/152 collecting | MI |
| 10 | Des Moines | 6524/57235 collecting | IA |
| 30 | AKARD STATION | 16/190 positioning | - |
| 19 | Pasco Bus Stop | 10/66 positioning | - |
| 35 | Amtrak Station | 29/41 positioning | - |
| 23 | Bonneville Transit Center | 87/331309 positioning | - |
| 31 | Houston 808 Jefferson St | 129/129 positioning | - |
| 7 | Airways Transit Center | 1233/25929 positioning | - |
| 6 | Holmes at Elvis Presley | 6794/365785 positioning | - |
| 21 | Saint George | 486373/1156403 positioning | - |

Two things follow, and the first corrects what this file claimed two sections ago.

**The `n_new == 0` key is not the explanation.** Four of the twelve are collecting legs, so they never met
that key at all, and leg 36 is the worst case of the lot: it collects four states, Georgia, South Carolina,
North Carolina and Virginia, and ranks dead last among its thirteen collecting peers. The earlier claim that
the demotion of positioning rides explained the whole night was an overclaim on partial evidence.

**What is actually wrong is ranking by hours per new state.** It is a local measure and this route's value
is not local. Leg 36 is the Silver Meteor, about fourteen hours for four states, 3.5 h each, and every
short hop that grabs one state quickly beats it on that ratio. The same logic buries Saint George: judged
on how little time it burns, a five minute local hop wins and a long repositioning ride that is the only
way south does not. Collecting or positioning, the ranking prefers what looks efficient in the next hour
over what makes the rest of the route possible, which is the fourth entry in the CLAUDE.md table wearing
different clothes.

**And the menu is not what `branching.py` measured.** At leg 21 the node offers 1156415 options, of which
1156403 collect nothing. A "median of 2 useful services" counted services along the reference route; these
are alighting points, every stop of every boardable trip inside `--horizon` at every footpath neighbour. A
million alighting points is not a choice set anyone can rank usefully, and it is the same explosion the
profile found in `rides_into`. Reducing options to the ones that can matter, per boardable trip rather than
per stop along it, is a separate problem from ranking and probably has to come first.

Falsification for the ranking work, stated before building: rank by the slack the deadline tables already
hold, `min over owed y of (L[y][to] - at)`, and the control's twelve outside legs should move up their
groups. If leg 36 and leg 21 stay buried, slack is not the missing signal either and the option set, not
the ranking, is the thing to fix.
