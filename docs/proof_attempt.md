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

## Meet in the middle: the forward half (Oct 30-31)

`ride_search --split-at TIME` stops each node at TIME and saves it as a label (stop, arrival, states held);
a complete harvest (queue emptied) plus a backward half and a join would make a proof. Forward half from
X's start, proofB's deadline, uncapped, split at Tue Nov 17 18:00 MT (X's midpoint).

Run 1 (pair key, `--goal`, 3 h): queue 353k at 1 h, 765k at 2.8 h, growth falling (+81, +50, +7 per s),
13221 labels when the budget ran out.

Run 2, overnight (ranking-only options dropped: no `--goal`, `--pair-k 1`, no depth bias; frontier ordered
earliest-first so dominance prunes more): ~360 nodes/s throughout, 4-5x run 1.

| search time | queue | labels |
|---|---|---|
| 3.4 h | 2.42M | 214k |
| 5.9 h | 2.88M | 334k |
| 7.4 h | 3.56M (peak) | 400k |
| 9.0 h | 3.51M | 475k |

It peaked and turned, but shrank ~10 a second: ~100 h more to empty, with the deepest node still at 19/48.
Stopped at 9 h. Halving the depth does not make the space finishable; the branching is in which states a
route holds by mid-week, and pairs and triples cannot cut it. Meet in the middle needs the stronger bound
below as much as the full search does.

Skeleton-pinned proofs (fix the Chief day, the Northwest crossing, the Fargo finish) were set aside: they
would finish, but only prove X is the best of its own shape, which the searches already show.

## A riding-only bound cannot prove these branches dead (Oct 31)

`scripts/tour_bound.py` pins the true riding floor of each proofB branch between a feasible tour and valid lower
bounds. The floor is a generalised TSP path over "entry stops" (the 3363 heads of edges crossing into a state):
any sequence of one entry stop per owed state, joined by shortest paths, collects them all, and no route rides
less. The feasible tour (`ub`) fixes the entry stops optimally for an order (a min-plus pass) and improves the
order by moves and reversals.

| branch | owed | hours left | lb (single state) | lb (state matrix) | ub (feasible) | 20-wide beam |
|---|---|---|---|---|---|---|
| 19/48 Washington | 28 | 142.8 | 71.2 | 71.2 | 133.4 | 171.6 |
| 23/48 Newark | 24 | 99.5 | 37.2 | 37.2 | **79.5** | 103.6 |
| 28/48 Boston | 19 | 92.3 | 41.8 | 41.8 | 75.8 | 100.8 |
| 32/48 Savannah | 15 | 79.6 | 29.2 | 29.2 | 66.8 | 84.1 |
| 34/48 Jacksonville | 13 | 76.9 | 29.5 | 29.5 | 55.5 | 59.9 |

Two results, both decisive:

1. **The beam's "kills" were the beam overshooting.** On every branch with 30 or fewer owed states the feasible
   tour comes in 4-38 h under the beam, and under the hours left. Newark (the example above) needs at most 79.5 h
   of riding against 99.5 h left. So the true riding floor is below the time left on all of them, and **no
   riding-only bound, however exact, kills any of them.** What makes them hopeless is waiting, not riding. The
   earlier "28 of 34" in this file is withdrawn.
2. **The state-matrix bound equals the single-state bound** on almost every row, as CLAUDE.md's first lesson
   predicts: a matrix of minimum distances between states lets the tour cross a state for free.

## Where this leaves the proof

Option 1 as posed (a whole-tour riding bound) is closed: the gap between these branches and death is timetable
waiting, which a clock-free bound cannot see. The bounds that do see it are the time-dependent ones the search
already has (deadline, pairs, triples), and they are exact only for small sets. A proof needs a time-dependent
bound over larger sets: either wider tables (quadruples cost about 48/4 times the triples, ~10 GB and a day) or a
cheap timetable-aware relaxation, e.g. charging each owed state its earliest reachable arrival from the branch's
clock rather than its riding distance. Until then, "nothing beats X" is a finding of the searches, not a proof.

## Quadruples kill proofB's branches (Oct 31)

proofB built triples lazily and tried 3 per node. With the full triple table (`build_triples.py`, 158 min on Windows)
and quads built on top of it (`scripts/quad_probe.py`: the 4 tightest owed triples at a branch, each extended by every
other owed state, four reverse scans per quad), on proofB's logged branches:

| from | branches | dead by pair | by full triples | by tested quads | median quad margin |
|---|---|---|---|---|---|
| 19/48 down | 16 | 0 | 10 | **16** | -19.6 h |
| 5/48 down | 31 | 1 | 19 | **29** | -23.9 h |

The chain is dead by quads from 7/48 (Grand Junction, -11.9 h): heading east from Colorado without Washington leaves
Nevada/New Mexico + Florida + Maine + Washington uncollectable. Only Elko (+17.4 h) and Truckee (+4.6 h) survive.
proofB's branches are on the pre-refresh router and the tables on current feeds, but margins this wide hold.

So the bound the proof needs is time-dependent quads, not a riding bound. The full quad table is 194580 rows (~46 GB,
~37 h), but owed sets overlap so much that most branches needed no new scans. `QuadTables` (`pair_tables.py`,
`ride_search --quads push`) builds them lazily off the hot path: a node tests the candidate quads already built,
queues the missing ones on a worker pool and moves on. Each quad is its own file, so a killed run loses nothing.

**Gate deadline.** The replay at 14:27 (one minute under X's 14:28) failed, correctly: pair, triple and quad all put
Memphis at -23.8 h. A margin is how late a node is against the latest departure that still finishes, and on a timetable
a one minute miss is a whole service interval (the next day's connection). So the tables are built at **14:30**, where X
fits and the replay must show no kill at all, and the proof runs with `--by 2026-11-22T14:30 --target 326.45` (finish by
14:27). Tables three minutes looser only prune less.

## The proof from X's start finished (Nov 1)

**No route that leaves Sheridan WY at Thu Nov 12 22:10 reaches Minnesota by Sun Nov 22 14:27; X arrives 14:28.** On the
current feeds (`6ea9328`, data `496b0bf`), under the model's rules (5 min transfers, 1.4 km walk-ins, the feed set), the
search queue emptied with nothing under the target.

Run (`proofR`, WSL, `--jobs 16`): `--start "Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)" --at 2026-11-09T00:00
--resume-at 2026-11-12T22:10 --end MN --days 22 --by 2026-11-22T14:30 --target 326.45 --key pair --pairs push --triples
push --quads push --frontier depth --slack-weight 3 --depth-bias 8 --city-hop --hop-slots 4 --width 100000`, with the
full triple table built at the 14:30 deadline (119 min, 20 forked workers). No `--goal`, `--pair-k 1`: ranking-only
options cost per node and change no prune.

| | |
|---|---|
| gate first | X replay at 14:30: 0 of 48 killed by pair, triple or quad; tightest margins +0.25 / +0.25 / +0.37 h |
| search | **4.0 h** (12:45-16:49), 6.21M nodes at 430/s, within the 12 h budget |
| queue | ~610k peak at 1.5 h, 469k at 2.9 h, 179k at 3.7 h, empty at 4.0 h |
| killed at push | 87.1M by pairs, 83.0M by triples, 70.6M by quads (15062 new quads, 60312 scans) |
| deepest | 47/48 at Fargo, X's west and a Louisville - Nashville - Chicago - Omaha middle, which cannot make the Moorhead walk in time |

What made it finish where proofB (8.2 h, queue still growing) did not: full triples tested at every node instead of 3
lazy ones, quads, and ~13x the node rate (step 1: drop the ranking scan and the uncapped sort, ~2.2x; step 2: forked
expansion, `--jobs 16`, ~6x on top; 20 min benchmark on the old data: 39 -> 64 -> 521 nodes/s).

**Scope.** This proves X is the fastest route **from its own start** (stop, departure, Minnesota end). It says nothing
about other start stops, other days, or other end states.

**Open caveat: node dominance and staying aboard.** `dominated()` drops a node when another at the same stop holds a
superset of its states and arrived no later. The key ignores `aboard`, so a node that could stay on its bus can be
dropped for one that arrived up to MIN_TRANSFER earlier and cannot board that bus fresh (the same seam as `--dedupe`,
CLAUDE.md). Closing it: require `sp + MIN_TRANSFER <= spent` unless the aboard trips match, and rerun (~4 h).
**Closed in `a4db915` (Nov 1 18:39)**, and hand-applied to the WSL copy at 18:34, so every proof below ran with it.
This X proof did not; it was not rerun (Nick, Nov 5: beating X from its own start needs ~24 h of savings, because
the Sioux Falls - Fargo bus runs once a day), and the reverse search below covers X's finish with the fix.

**Where to point it next.** Not X's other start days: X does not run every day, and its finish hangs on a once-a-day
Fargo departure, so a variant of X beats it only by saving ~24 h. The productive use is the near-miss shapes whose
finish has frequent options (a state-line walk, a corridor with several departures), where an hour saved early can
actually land at the end: pin each one's start, build its end's tables at X's time, and either find a route under X
or prove none exists from there.

## Proofs from the near-miss starts (Nov 1-6)

Each pins a near-miss route's own start (stop and time) and asks whether **anything** reaches its end state within X's
232.13 h from there. Queue empty means no: not that route, nor any other order from that start. Same machinery as
the X proof (`--key pair --pairs push --triples push --quads push`, full triple table built at the deadline), all on
WSL at code `6ea9328` plus the dominance fix (identical to `a4db915`, applied by hand Nov 1 18:34), data `496b0bf`,
under the model's rules (5 min transfers, 1.4 km walk-ins, the feed set).

| start (pinned) | end | deadline | result | search | nodes | killed: pairs / triples / quads | deepest |
|---|---|---|---|---|---|---|---|
| Fargo, Mon Nov 9 11:34 (the Moorhead AR route, 235.73 h) | AR | Thu Nov 19 03:55 | **queue empty, nothing** | 71 min, 8 jobs | 1.37M | 3.6M / 25.7M / 19.1M | 24/48 |
| Huntington, Thu Nov 12 00:34 (the Control, 237.5 h) | VT | Sat Nov 21 16:55 | **queue empty, nothing** | 10.4 h (9.0 h at 8 jobs, then 1.4 h at 16) | 10.0M | 10.8M / 15.4M / 26.2M | 21/48 at 187 h |
| Wheeling, Wed Nov 11 20:54 (241.17 h) | VT | Sat Nov 21 13:15 | **queue empty, nothing** | 4.3 h (4.0 h, a WSL crash, then 15 min resumed) | 6.10M | 2.0M / 5.6M / 6.7M (resumed part) | 19/48 |
| Fulton Amtrak, Mon Nov 9 03:45 (Fulton Meteor, 241.61 h) | MI | Wed Nov 18 20:05 | **queue empty, nothing** | 4.7 h, 16 jobs | 4.83M | 4.7M / 68.7M / 107.6M | 21/48 |

Notes:

- **Restarts lose almost nothing.** `--save-queue` writes the queue hourly; the Control was resumed at 16 jobs from its 8
  job save, and Wheeling from its 15:45 save after WSL went down at 15:52 (Windows stayed up). The resumed Wheeling ran
  at ~6600 nodes/s against 354/s before, because its quads were already on disk.
- **Pace depends on the quads already built**, not the start: a proof is slow (150-350 nodes/s) while it builds the
  quads it needs and fast once they exist. The queue rises, holds flat for an hour or more, then falls.
- **Scope**, as for X: each is a statement about its pinned start and end state, under this feed set. Tornado Greeley
  (239.88 h) was not run (Nick: its question is the start time, not the middle). The Record shape (238.83 h) has no
  proof of its own.

## The reverse search from X's finish (queued Nov 6)

The forward proofs pin a start; X's question is the other way round, because its end is fixed by a once-a-day bus
(Sioux Falls 10:00 - Fargo 14:05, Thu-Mon) and its start is free. `--dir backward` stands at Fargo at a day's 14:05 with
MN held as collected (`--skip MN`: the 83 min walk over the Red River) and asks whether any start no earlier than the
deadline minus the target reaches it holding the other 47. Mirror tables (`rev_tables.py`, `build_triples.py --back`)
prune it the way the forward tables prune forward.

First launch (Nov 6 02:48) did not search: the chain script omitted `--key pair`, which `--triples` requires, and its
`search()` returned `tail`'s exit code, so the refusal was logged as "gate exited 0, found nothing". Both fixed; gate
relaunched Nov 6 08:40. (`--key` does not order the backward search; the flag only satisfies the check.)

`~/bus48/out/reverseX.sh` (WSL, unattended, resumable) runs after Fulton: update the WSL copy to `pipeline`, then a
**gate** on Sun Nov 22 at 230.80 h to Fargo, which X fits (230.75 h), and which must find something or the chain
stops; then one **proof** per finish day at 230.74 h, just under X: Nov 22, 21, 23, 20, 19. Finish days before Nov 22
start before Nov 12 and cross the Northeast Corridor before the Portal Bridge cutover ends (Nov 16), so those proofs
hold for that broken week only.
