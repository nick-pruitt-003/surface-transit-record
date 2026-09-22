# Long-budget runs, and why they were stopped

Run locally on a MacBook (8 cores, 8 GB), 2026-09-22, not in the cloud container, so the idle reclaim did not
apply. The brief was four runs, one at a time, 1 h / 4 h / 1 h / 1 h, to find out whether time moves the
wall at 28/48. What actually happened is that the code moved three times under the queue, run 1 was
re-run on each version, and runs 2 to 4 were held on instruction pending the queue census. The question
got answered anyway, by a different instrument: see "The wall is joint infeasibility" below.

Common arguments throughout:

```
--end VT --by 2026-10-03T22:54 --tz America/New_York --target 238 --states 48
--start "Huntington Bus Stop" --at 2026-09-24T00:54 --order slack --dedupe
```

## Runs

| run | code | wall | deepest states | nodes | nodes/s | FOUND | best | independent check |
|---|---|---|---|---|---|---|---|---|
| slack 1h | 984d773 (pre-6a4bd70) | 1208 s, killed | 27/48 | 3767 | 3 | none | - | - |
| slack 1h | 023b4a2 | 91 s, killed (hold) | 27/48 | 2494 | 27 | none | - | - |
| slack 1h | **18861ed** | 2769 s, killed (hold) | **31/48** | 90777 | 33 (42 steady to 20 min) | none | - | - |
| deep31 re-run | 18861ed | 200 s budget | 31/48 | 10660 | 53 | none | - | - |
| slack 4h | - | not run | | | | | | |
| rate 1h (old default) | - | not run | | | | | | |
| backward 1h | - | not run | | | | | | |

No run found a route, so no independent check ever executed and there is nothing to flag there.

Deepest lines in full, 18861ed:

```
[    7s] 27/48 states,  105.8 h spent, at Ann Arbor, 17 rides, 1695 nodes, 522 in frontier
[   85s] 28/48 states,  116.7 h spent, at Winona, 17 rides, 4231 nodes, 767 in frontier
[   85s] 29/48 states,  121.7 h spent, at Clear Lake Jct., 18 rides, 4336 nodes, 787 in frontier
[  143s] 30/48 states,  133.0 h spent, at Cheyenne (Sinclair), 17 rides, 6641 nodes, 862 in frontier
[  163s] 31/48 states,  141.3 h spent, at Salt Lake City Intermodal Tr, 17 rides, 7414 nodes, 1060 in frontier
[ 2769s] still 31/48, 90777 nodes (33/s), 19761 in frontier, 39384 kept
```

Nothing new after 163 s, across 83000 further nodes. Peak memory 3.1 GB (`/usr/bin/time -l`), so memory
did not bind. The frontier grew about 8 nodes/s the whole time: it was not close to exhausting anything.

The search is deterministic. The 200 s re-run reached 31/48 at the same node, 7414, and the same stop and
clock, so the saved `out/deep31.pkl` is the run-1 chain. Its westward leg is Chicago, California Zephyr
(train 5, trip 296927) to Denver, then an intercity bus toward Reno, reaching Salt Lake City at 141.3 h.

The pre-6a4bd70 row is not comparable on rate: the machine was at load 12-16 with the search at 30-75% of
one core and swapping. Every later row ran at load 5-7.

## Throughput by commit, and where the time goes

cProfile, search phase only, same arguments:

| code | nodes/s under profiler | `rides_from` share | top cost inside it |
|---|---|---|---|
| 023b4a2 | 14 | 177.5 s of 180 s | `any(at > L[y][to] ...)` at the alight test: 331M generator calls, 65 s |
| 3dc91dd | 18 | 118 s of 120 s | the same generator, 215M calls, 43 s: the shortcut gated on `not got`, which is almost never true because `got` holds every state passed, not only new ones |
| 18861ed | 26 | 113 s of 120 s | generator gone; the loop itself, and `Menu.add` 23M calls 13 s |

Generation is still the whole of the per-node cost. The next lever, if one is wanted, is the Python loop
over downstream stops, not anything after it.

## The wall is joint infeasibility, not time

`deepest` is printed at pop, so the census work asked whether the deep bucket was dead. It is not dead by
the per-state test: that test runs at **push**, inside `rides_from` (`at <= cap[to]`, and the owed-after
test when a ride collects something new), against tables that never change during a run. A queued node
therefore cannot fail it at pop, and the cloud census confirmed `0 pops were already dead`.

But the per-state test only asks whether each owed state is reachable on its own. `scripts/pair_probe.py`
asks it two at a time, exactly, with the same scans. Seeding the reverse scan from y's stops with `L[z]`
instead of `L_end` gives `L[y->z]`, the latest you can be anywhere and still collect y, then z, then
finish. A node is dead if some owed pair fails in both orders.

Falsification first. Every node of the 237 control from 28 states onward (legs 37 to 60, re-evaluated
through the router) has **0 jointly impossible pairs**, tightest margins +0.1 to +1.8 h. The method does not
kill a route that finishes.

The run-1 chain:

| node | spent | left | owes | impossible pairs | tightest |
|---|---|---|---|---|---|
| ride 16, Denver | 129.0 h | 109.0 h | 19 | 21 of 171 | CA & WA: WA then CA misses by 15.5 h |
| ride 17, Salt Lake City | 141.3 h | 96.7 h | 17 | 42 of 136 | NM & WA: WA then NM misses by 16.5 h |

The chain was already provably dead at Denver, twelve hours of route before its deepest node. Washington
and Oregon are the recurring culprits: anything that has to happen after the Pacific Northwest costs a
full day more than the deadline allows, and the repeated -15.5 h at Denver is +8.5 h (Washington alone)
less 24 h, the signature of a once-daily service.

So the answer to the brief's question is that more time does not move the wall, because the wall is not a
shortage of nodes. From 163 s to 2769 s the search explored descendants of chains the per-state tables
cannot see are dead. A four-hour run would have done more of the same.

Three consequences, for whoever picks this up:

1. **A pair test is a legitimate prune.** It is exact, it uses nothing but the deadline tables, and on the
   control it kills nothing. All 48x47 pair tables would cost about 2256 scans, roughly 26 minutes at the
   measured 0.7 s each; computing them lazily for owed pairs costs 342 scans for the two nodes above.
2. **The `--order` comparisons (25 vs 28 vs 31) are not zombie comparisons** in the per-state sense, since
   no node in the queue ever failed that test. They may still be comparisons of how fast each ordering
   reaches a jointly dead position, which the pair probe can now measure per run.
3. **Runs 2 to 4 are worth running only after something changes what the search prunes or prefers.**
   Same commands and budgets as the brief.

## Other notes

- `regress.py` uses paths relative to the working directory (`'../out/'`, `open('ride_search.py')`). Run
  from the repo root it reports 5/8 with three spurious failures. Always run it from `scripts/`.
- The Borealis (Amtrak route 42991, trains 1333/1340, Chicago to St. Paul) is in the feed and runs daily
  both ways for the whole window, at Winona 17:45 ET. Run 1's 28th state was at Winona, but on a sibling
  chain the pickle does not keep, so whether that was the Borealis or the Empire Builder is unresolved.
- The deep bucket in the census is one Salt Lake City position repeated across walk-connected stops.
  Dominance keys on the exact stop, so those copies coexist. That is throughput, not correctness, and
  extending dominance across a walk would need the same slack treatment as `MIN_TRANSFER`. Noted, not built.
- `--dedupe` dominance does not key on the boarded trip (CLAUDE.md), so it can drop a continuation that
  depends on being already aboard. It stays opt-in; run 3 in the brief is the no-dedupe comparison.

Logs are in `out/` (gitignored): `long_slack_1h_precommit6a4bd70.log`, `long_slack_1h_at023b4a2_partial.log`,
`long_slack_1h_18861ed_stopped2650s.log`, `deep31.log`, `prof_*.log`, `pair_probe2.log`, and the chain
`deep31.pkl`.
