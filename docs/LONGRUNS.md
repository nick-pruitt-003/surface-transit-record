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

## Addendum: full pair tables, and where the chain actually died

`scripts/pair_tables.py` builds every pair table once (48 x 47 scans, 427 s on 6 workers, 174 MB cached in
`out/pairs_<key>.npy`, keyed on every array the scans read plus the deadline and span) and answers a node in
one 9 KB read: `PairTables(R, D, span, L_end, L).dead(stop, t, owed)`. Running it validates itself:

- The 237 control, every node from leg 1 (63 nodes): **0 killed**, tightest AL & FL at Oklahoma City, +0.11 h.
- The run-1 chain dies at **ride 10, Springfield MA, holding 23 states** (CA & WA miss by 5.8 h), not at
  Denver. It was alive at New York (+2.2 h) and the Northeast leg from there lost it. Every node from ride
  10 to the 31-state Salt Lake City one, and the 83000 nodes explored below them, were already dead.

Not yet wired into `ride_search.py`; that edit belongs with whoever holds the file.

Two reading hazards fixed in both probes, from review: a pickle's stop indices are router-local, so
`check_path` verifies every leg against this router by trip key (boarding at `frm` or anywhere walkable
from it, alighting at `to` at the recorded time) and refuses the pickle otherwise; and 2955 stop names map to
more than one stop (Huntington Bus Stop is 755 and 3322), so names resolve to all exact matches and the
control is evaluated from each (both finish at 237.74 h). `check_path` was only exercised on a pickle that
fits; its refusal path was last seen firing on a false positive, since fixed, not on a true mismatch.

## The prune in the search (e19c68d), 200 s each, run-1 settings

| | `--pairs push` | `--pairs pop` |
|---|---|---|
| nodes expanded | 5632 (28/s) | 7150 (36/s) |
| killed by the pair test | 8310 | 1496 |
| `deepest` printed | 27 | 29, Truckee Amtrak, 132.7 h |
| deepest bucket still queued at exit | 1 node at 26, survives the pair test | 11 nodes at 28, **0** survive (Truckee: ND & LA miss by 26.1 h) |
| FOUND | none | none |

Pop prints `deepest` before its pair test runs, so its 29 is a dead chain, and its deep bucket was all
zombies. Push tests before a node is queued, so everything it holds is live under the pair test and its
honest frontier after 200 s is 26 states. Pop still opened with the Northeast dive (Springfield at 1 s);
push never queues it. The control loses 0 of 63 nodes under the same tables. The frontier sweep never ran
(queue far below 200 k), so its `0 jointly dead` invariant was not exercised.

The brief's four runs are re-running on e19c68d with `--pairs push` on the three forward runs; backward has
no pair check and runs as before.

## The full-depth census: the unpruned baseline's honest depth was 21, not 30

The push-vs-pop entry above was read with the census as it then was, which examined only `top = max(hist)`
and told you nothing about the buckets below it. Widened to every bucket, the same 200 s baseline
(`--pairs report`, prune switched off, run-1 settings) says something much stronger:

```
queue at exit:      879 nodes, depth 31:2 30:28 29:12 28:24 27:31 26:94 25:80 24:84 23:37 22:61 21:277 20:16
pair-live by depth:            31:0/2 30:0/28 29:0/12 28:0/24 27:0/31 26:0/94 25:0/80 24:0/84 23:0/37 22:0/61 21:12/277 20:6/16
deepest node the per-state test keeps: 31; deepest that survives the pair test: 21.
```

Every node from 22 states to 31 was jointly dead. All 458 of them. The run printed `deepest 30/48` and its
honest depth was **21**, a nine-state gap between what the search believed and what was true.

| | reported deepest | honest deepest |
|---|---|---|
| no prune (`--pairs report`) | 30 | **21** |
| `--pairs push` | 27 | **26** |

So the prune does not merely tidy up after the search, it moves the real frontier from 21 to 26. The budget
that went into 458 doomed nodes goes into chains that can still finish.

The twelve survivors at 21 states are Indianapolis, Ligonier, Effingham, Fort Wayne and Goshen, all in
Indiana and Illinois, all owing the same eighteen states, and that set is the entire West plus the far
Northeast. **The live frontier is exactly the chains that have not yet committed East.** Every chain that
went East first is in the dead 458, which is the corridor argument arriving from a third instrument that was
not built to produce it.

### Pair-margin ranking: measured, and it is not the answer

`--rerank N` re-orders the top N options by the pair margin before `--width` cuts. Replays against the
control at N=24 and N=60 are **identical on every leg**, and both report 31/40 against slack's 30/40.

The +1 is Fargo moving 13/36 to 11/36, across the width line. It is real, and it is incidental:

| leg | slack | rerank |
|---|---|---|
| 13 Fargo +ND | 13/36 | 11/36 |
| 14 Minneapolis +MN | 2/154 | 1/154 |
| 17 Billings +WY MT | 2/150 | 1/150 |
| **19 Pasco** | **4/53** | **11/53** |
| 20 Salt Lake City +UT OR | 1/20 | 3/20 |
| 21 Saint George | 21586/21638 | 21586/21638 |

It **demotes the Pasco leg**, the corridor `CORRIDORS.md` measures as forced in all 36 start cases, and
leaves Saint George exactly where it was. The reason is in CORRIDORS.md already: the control's Pasco leg
sits at +1.9 h with the whole East still owed, so it is one of the *tightest* moves on the route, and a
ranker preferring margin walks away from it. Forcedness and comfort are not the same quantity, and the pair
margin measures comfort.

There is also no N that would help. Legs with few options have all their action inside the top 24, and the
legs that need help have thousands, so no head small enough to price in an inner loop reaches them.

Two notes on method, both of which nearly cost a wrong conclusion:

- 31/40 is the exact number that rose spuriously once before, on a refactor that was meant to change
  nothing. Reporting the tally without diffing which leg moved would have sold a reshuffle as progress.
- The falsification was stated before the run ("it should promote Spokane to Pasco and Saint George") and
  the run falsified it. The caveat that killed it was in CORRIDORS.md, written down, and read, one turn
  before the prediction was made anyway.
