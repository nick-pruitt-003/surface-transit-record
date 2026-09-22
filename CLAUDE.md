# bus48

Find a scheduled surface route through all 48 contiguous states faster than the timetabled record of
238.83 h. Best verified: **237.3 h** (Huntington WV to the Vermont line at Hanover). `docs/HANDOFF.md` has
the route, the rules, and everything tested and ruled out. Read it before proposing anything.

## Working rules

- **One search at a time.** Not three in parallel to compare them.
- **Run `scripts/regress.py` (6 checks) before committing** anything touching the router, the search or the
  data. A new leaf script that nothing imports is the one exception, and say so when you skip it.
- Defaults are 5 min transfers, 1.4 km walk-ins, 24 h slack.
- Never seed new end points from old routes.
- `out/` is gitignored, so a fresh checkout has no result pickles. `scripts/rebuild_237.py` rebuilds them.
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

## Diagnostics worth reusing

Instrumenting against the known answer worked every time; running searches blind and reading the result did
not. `ride_search.py --track` replays the control leg by leg and says which are missing and why.
`branching.py` measures the real menu size. `bound_probe.py` scores a bound against the true remainder.
`tail_diag.py`, `dump_diag.py` and `reach_probe.py` do the same for the ordering searches.

State a falsification condition before building, and validate on at least two cases that disagree. A
reach-based estimate once looked decisive on one dump and was arithmetically broken: it summed n copies of
the node's own clock, so it paid a chain for being further back. It only showed up on a second dump where
the reference was ahead rather than behind.
