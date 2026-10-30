# Proving X is the floor: what was tried, Oct 30 2026

Question: is X (232.30 h, Sheridan WY Thu Nov 12 22:10 to Moorhead MN) the fastest route, or does
something exist near 228 h? Finding a faster route is what searches already do. This was the other half:
can `ride_search` **prove** that nothing faster exists?

The idea: with the menu cap removed (`--width 100000`), the feasibility tables (deadline, pair, triple)
are exact and permissive (guard=False), so a search that empties its queue below X's time has shown no
route beats X from that start. Short answer: **not at this scale**. Details below.

## Riding-time floor (`scripts/min_ride.py`, `53f29bf`)

Riding time alone, every connection instant, beam 300 plus a drop/move cleanup pass: **157.8 h** to touch
all 48. An upper bound on the true floor (the beam is not exhaustive). So X is roughly 158 h riding and
74 h of waiting the timetables force. The cleanup's one improvement was dropping a West Wendover detour:
Nevada comes free on Beaver Dam to Primm.

## Calibration from X's start (Oct 29-30)

Same flags as the X reproduction, menu uncapped:

| run | deadline | result |
|---|---|---|
| proofA | 14:40, X fits | **found X, 232.30 h**, after 75 min of search |
| proofB | 14:27, one minute under X | **did not finish**: stopped at 8.2 h search |

proofB's queue never turned down:

| search time | nodes expanded | queue | deepest |
|---|---|---|---|
| 1 h | 235k | 467k | 36/48 |
| 4 h | 2.0M | 1.49M | 36/48 |
| 8.2 h | 4.87M | 2.69M | 36/48 |

About 40 GB of memory per run. The deepest chain sat at 36/48 (Florida, Kentucky) for 7 of the 8 hours,
so the branching is not only in the West: the East is explored exhaustively too.

## The "never rides Greyhound US0550" slice (Oct 30)

Nick's rule: every fast route rides some part of US0550 (Seattle - Pasco - Boise - SLC - Denver, once a
day each way); any alternative is ~28 h slower, or near time-neutral via Salt Lake Express/Northwestern
Stage but never faster. The plan was to prove that slice empty first, then search only 550 slices by
direction and day.

Run with `BUS48_DROP_EXTRA=out/no_us0550.csv` (`ba23c37`; drops US0550 both ways all days, including the
hand-entered SLC-Provo row), proofB's deadline. **It did not die fast**: stopped at 4.9 h search, 2.74M
nodes, queue 2.01M and growing, deepest 36/48. At equal search time it carried more open branches than
proofB. Removing the corridor does not shrink the problem, because the explosion is in the East.

The Northwest crossing list (`docs/region_NW.md`, `access_diff.py --region`) is still the right way to
slice the West; it just isn't enough on its own.

## Why the bound is too weak (`scripts/bound_gap.py`)

On proofB's 34 deepest logged branches, time left before the deadline against riding-only figures for the
owed states:

| figure | branches it would kill |
|---|---|
| single-state lower bound (worst owed state's detour to the end) | **0** of 34: 30-75 h against 60-230 h left |
| beam tour over all owed states (estimate, not a bound) | **28** of 34 |

Example: 23/48 at Newark, 99.5 h left, ~103.7 h of riding alone for its 25 owed states. Hopeless, kept alive
for hours, because pairs and triples never see a whole-tour shortfall. Margins are thin (4-10 h on a 100 h
remainder), so a valid bound must be within a few percent of the riding floor. Spanning-tree style bounds
are typically 10-20% low, and a state-to-state matrix makes neighbours 0 h apart (CLAUDE.md's first
lesson). An exact per-owed-set tour solve is a TSP over stop groups per node: a research project, not
attempted.

## Using the tour estimate to rank instead (`--tour`, opt-in)

`scripts/tour_est.py`: the beam from `min_ride`, with cached shortest-path trees and each state's nearest
stop per tree precomputed. Beam width matters: widths 1 and 3 are 15 h off width 20 on average (up to
50 h either way), so width 20, ~0.36 s first call, cached by (stop, owed set).

`ride_search --tour 1` scores branches by it. On the X reproduction (today's data, `--target 233`, 1 h
budget):

| | found X at | nodes/s | deepest waiting at exit |
|---|---|---|---|
| default | **1040 s** | 53 | 34/48 |
| `--tour 1` | 2475 s | 21 | 39/48 |

The ranking is better (the open frontier sits deeper) but the per-node cost is not paid back. It stays
opt-in; it may earn its keep on a new shape where the pair key ranks worse than it does on X.

## Where this leaves the proof

On hold. Needed before trying again: a valid whole-tour bound within a few percent of the riding floor at
under ~10 ms a node. Until then, "nothing beats X" is a finding of the searches, not a proof.
