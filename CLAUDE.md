# bus48

Find a scheduled surface route through all 48 contiguous states faster than the timetabled record of
238.83 h. Best verified: **237.3 h** (Huntington WV to the Vermont line at Hanover). `docs/HANDOFF.md` has
the route, the rules, and everything tested and ruled out. Read it before proposing anything.

## Working rules

- **One search at a time.** Not three in parallel to compare them.
- **Run `scripts/regress.py` before committing** anything touching the router, the search or the
  data. A new leaf script that nothing imports is the one exception, and say so when you skip it.
- Defaults are 5 min transfers, 1.4 km walk-ins, 24 h slack.
- Never seed new end points from old routes.
- `out/` is gitignored, so a fresh checkout has no result pickles. `scripts/rebuild_237.py` rebuilds them.
- **Long runs do not survive the session going quiet.** This container is reclaimed after a period of
  inactivity, so a queue launched with `nohup` and left alone dies: measured at about eight minutes after
  the last tool call, three times. `setsid` does not help and neither does moving the process out of the
  Bash call's cgroup, though that is worth doing anyway (a process started from a tool call lives in that
  call's cgroup, and the cgroup is torn down when the call's container is recycled). What works is an
  hourly check-in that restarts the queue and then actively supervises it, plus a queue that **resumes**:
  `overnight.sh` skips any run whose log already holds a summary line, so a restart continues instead of
  redoing the first run for ever. Budget accordingly, and remember every run pays about 3.5 min of GTFS
  loading before it searches.
- Don't write `pkill -f <script>` in a command whose own text contains that script name. It matches the
  shell running it and kills the command before it runs. Use `pgrep -f "ride_sea[r]ch"` instead. Cost me
  three commands before I noticed.

## 237 is a control, not a target

It is already optimised for its shape and is not expected to be beaten on it. The test of a new search is
that it **reproduces** it, and the bar is convergence within about ten minutes over repeated runs, not
finding it first try. A leg ranked below the width cap is fine, backtracking reaches it; a leg missing from
the menu entirely is a bug. Count those separately.

## The one lesson that keeps repeating

**Every time a summary statistic went where the timetable could answer exactly, it broke on the sparse rural
link the route actually depends on.** Four times in one session:

| what I put in the way | what it silently hid |
|---|---|
| `state_times`: min over stop pairs, median over deadlines, spanning tree over the result | made neighbouring states 0.0 h apart, so the estimate measured which states touch, not travel |
| alight rule "stop has >= 6 services" | the Barstow Amtrak depot has 2, and the Southwest Chief leaves from nowhere else |
| footpath filter `w <= WALK_MAX_KM * 1000 / 1.25` (a made-up 1200 against a value in seconds) | every local-transit hop over 20 min: Memphis to Bellevue at Carr, SLC to the Salt Lake Express shop, Barstow Station to the depot |
| collecting states only where a ride stops | Mississippi, which the route takes on foot from Holmes at Elvis Presley |
| ranking candidate rides by hours per new state | the Silver Meteor, 14 h for GA SC NC VA, ranked last of 13 collecting options; and Saint George, 486373rd of 1156403 positioning ones |

The fifth entry is the one that cost a whole night, so state it on its own: **hours per new state is a
local measure and this route's value is not local.** A long-haul ride that collects four states in fourteen
hours loses on that ratio to any short hop that grabs one state in twenty minutes, and a repositioning ride
that is the only way south loses to a five minute local hop that achieves nothing. Measured against the
control, the ranking disagrees at twelve of its forty legs. Rank by what the deadline tables already know,
`min over owed y of (L[y][to] - at)`, which is how close a move leaves the chain to losing the state it can
least afford, not by how efficient the next hour looks.

The stops a 48-state route cannot do without are a two-service desert depot, a five-service town in Arkansas,
and a 1.3 km walk to a state line. Nothing built on busyness, averages or radii will keep them. Ask the
timetable; it answers exactly and it is already loaded.

Mississippi shows how far this reaches. Taking it on foot at Memphis costs nothing, because there is a four
hour gap between the City of New Orleans arriving and the Jefferson bus leaving with no productive move in
it. That frees the Houston to Tallahassee bus that *skips* Mississippi, which arrives early enough for the
Silver Meteor and the fast finish. Collect MS the modal way on the Gulf corridor and the ending is gone. A
border walk-in in Tennessee is load-bearing for a connection in Florida five days later.

## Give the deadline its slack

`--by` is the latest acceptable finish, which is **start + target**, not the reference route's own finish
time. Passing the reference's finish (22:14) gives a zero-slack deadline, and then a one minute difference
in how a walk is modelled is fatal: the Hanover to Vermont line link came out 15 min against the route's
14, so L_end[Hanover] sat one minute before the route's own arrival, the Dartmouth Coach was excluded, and
that compounded backwards into four hours by Houston, where Maine then looked uncollectable from Texas
onward. With the correct deadline (00:54 + 238 h = 22:54) all 40 rides of the control are on the menu.

Feasibility tables are built with guard=False on purpose. The guard blocks a walk crossing a state line
into the target's stop, which is a rule about how a search layer may collect a state, not about what is
physically possible. A bound that is too permissive only lets a dead branch live a little longer; one that
is too strict prunes the answer.

## Search designs, and why the earlier ones failed

Searching **orderings of the 48 states** (`build_backward.py`, `dfs_backward.py`) is the wrong space. Its
branching is the topk of 6 and its leftover estimate has to price a set of states with no idea where or when
you are. Every form of that estimate failed, measured: plain, doubled, cheapest-entry, and two
frequency-aware matrices which got *closer to the true remainder* while ranking *worse*. A spanning tree is
a minimum, so an interior state attaches by its cheapest unplaced neighbour however the matrix is scaled.
The beam tops out at 267.7 h regardless of beam width, candidate width or survival rules. Don't write
another estimate in that shape.

Searching **the rides themselves** (`ride_search.py`) is the right space, and is Nick's original design. A
node is a stop, a time and what has been collected; the menu is what actually departs. Measured branching is
a median of 2 useful services, and ten of the reference route's thirty-nine points have none at all, where
the next move is forced. Houston offers 2164 departures over 28 services and not one is useful.

It needs no leftover estimate. Both clocks live on the node: elapsed, and time to the deadline. One reverse
scan per state gives `L[y][stop]`, the latest you can be there and still collect y and finish, so a branch
dies on a fact rather than an estimate, and `alight_ok` decides where to get off the same way.

## Two gates, because one technique found every real bug and the others found none

Every serious defect was found by replaying the control through the search. Running searches blind and
reading the output found nothing, for hours. So:

1. **`python3 ride_search.py ... --track ../out/res_starttest.pkl` after any change to the search.** It
   exits non-zero when a leg of the control is not on the menu at all. A leg ranked below `--width` is
   fine, backtracking reaches it. A leg missing is a bug, not a note.
2. **The search never reports its own result.** `confirm()` rebuilds the state order from the path and
   hands it to `Search.evaluate`, and the run prints whether the router agrees. Two bugs in one night
   produced routes that do not exist: states credited at every stop a ride passed, with nobody getting off
   and no time charged, and a chain accepted for collecting all 48 while parked somewhere that was not the
   end. Neither survives an independent evaluation. The search proposes, the router disposes.

And the rule those bugs came from, stated as a test to apply before writing a line: **if the timetable can
answer this exactly, do not put a number in front of it.** Every magic threshold this session hid the
sparse rural link the route depends on. When a threshold seems unavoidable, make it permissive rather than
strict, so it can only let a dead branch live a little longer and never prune a live one: that is why the
deadline tables use guard=False and why the scan cache rounds its clock up.

## The live instances, not just the history

The table above lists bugs that were fixed. Nick's audit found the same shape still sitting in the default
path, which matters more, and the reply to it is that prose does not fail a build. `regress.py` now asserts
the geography instead: the Barstow depot, Conway, Holmes and the Bellevue at Carr hop exist, Holmes still
steps over the Mississippi line on foot, and nothing on the ride-search path picks stops by how busy they
are. That last one fails if `build_gateways` is ever wired into `ride_search.py`, because it ranks by raw
departure count and contains none of the three stops the control cannot do without.

Still live and not yet addressed, in the order they are being worked:

| what | where | what it can erase |
|---|---|---|
| ranking by hours per new state | `--order rate`, no longer the default since slack measured 25 vs 28 vs 31, and no longer hardcoded in `overnight.sh` | the Silver Meteor, 14 h for four states, last of thirteen |
| positioning rides sorted behind collecting ones | `sort_opts`, first key in every mode including slack | Spokane to Pasco, Saint George, Memphis to Holmes |
| a flat 5 h credit per state on the frontier | `--credit` | a west-first chain loses to a cheap north-east one that looks ahead of pace |
| the `--hub 6` alight fallback | `alight_ok` when no `--end`/`--by` is given | the Barstow depot has 2, Conway has 5 |
| walk-only cap in the branching diagnostic | `branching.py` | local-proxy hops, which taints the "median 2 useful services" figure quoted above |
| hand allowlist of routes per feed | `data/more_gtfs/keep_routes.json` | `lake_erie` entirely; `mata` is trimmed to routes 42 and 30, and Memphis is where the route walks to Mississippi |

When adding a check here, make it able to fail. A first version of the gateway check asserted that a list
was non-empty, which reads like a test and tests nothing.

## What --dedupe costs, and why it stays opt-in

Option dominance drops an option when another at the same stop holds at least its states and arrives at
least MIN_TRANSFER earlier. The slack is what makes it safe: the survivor is ready to board by the time the
discarded option arrived, so it can take whatever that option would have taken next.

The seam, found by adversarial review rather than by a run: dominance keys on (stop, states, time) and not
on the trip. If the useful continuation is *being already aboard* some trip T, and T cannot be boarded
fresh at that stop, the survivor does not preserve it. Rare in this data and not something `--track` can
catch, because the replay only ever exercises the control's own trips, and a non-control casualty is
silent.

That is why `--dedupe` is opt-in rather than the default, and the mitigation is the reason, not a verdict.
Turning it on by default needs either a proof that the case cannot arise in this feed set or a check that
would notice it.

## Where a check belongs, now that the world is cached

A built router is pickled by `cached_router` and reloads in 2 s against 63 s to build, keyed on every file
under `data/`, the dates, and the source of `time_router.py`. That changes where checks can live: geography
assertions used to be exiled to the slow suite because they needed a router, and now they do not.

| tier | cost | what belongs |
|---|---|---|
| A0 | milliseconds, no router | `Menu`, dominance, slack arithmetic, leg tuple layouts, `got` emptiness. Synthetic fixtures of a few connections, not Amtrak. |
| A1 | seconds, warm router | Holmes stepping over the Mississippi line, the Bellevue hop costing over twenty minutes, sparse stops surviving the filters. |
| B, `regress.py` | ~15 s warm | Oracles and wiring: the 237 route evaluates, calendars and agency time, busyness stays off the search path. |
| C, `--track` | minutes | The control replay. The gate for any change to the search. |
| D | hours | Full searches. Never the inner loop. |

Two rules the day produced.

**Put a fixed bug in the cheapest tier that can see it.** Both of today's escapes were A0 shapes. `if not
got` never fired because `got` holds every state a ride passes through, and a three-stop synthetic trip
would have caught it in milliseconds; instead it cost a profile, a push and a restart on another machine.
The ride-versus-walk tuple index is the same: `('ride', trip, board, dep, alight, arr)` against
`('walk', from, to, t0, t1)`, so the destination is index 4 on one and index 2 on the other.

**A green `regress.py` does not mean the new loops are safe.** It passed 8/8 on a version where every
candidate died on a `None` subscript, because it never exercises generation. Only the control replay caught
that. B is an oracle suite, not a generation gate, and reading it as one is how a broken build looks fine.

## On a change that claims to change nothing, a number going up is a failure signal

Making walk-ins their own move type was meant to be behaviour-neutral, and the control replay came back at
31/40 instead of 30/40. The extra leg was not progress. Walk-in options now carry the real trip key rather
than none, and the replay matched a control leg by stop and trip alone, so a plain ride in the control
started matching the ride-plus-detour variant of the same trip to the same stop. A different move, counted
as the same one, in the gate that exists to catch exactly that.

Nothing announced it. The only reason it surfaced is that the tally moved when it should not have, so treat
that as the signal: when a refactor says it changes nothing, any number that improves is unexplained until
proven otherwise, and unexplained improvements in a gate usually mean the gate got easier.

## Diagnostics worth reusing

Instrumenting against the known answer worked every time; running searches blind and reading the result did
not. `ride_search.py --track` replays the control leg by leg and says which are missing and why.
`branching.py` measures the real menu size. `bound_probe.py` scores a bound against the true remainder.
`tail_diag.py`, `dump_diag.py` and `reach_probe.py` do the same for the ordering searches.

State a falsification condition before building, and validate on at least two cases that disagree. A
reach-based estimate once looked decisive on one dump and was arithmetically broken: it summed n copies of
the node's own clock, so it paid a chain for being further back. It only showed up on a second dump where
the reference was ahead rather than behind.
