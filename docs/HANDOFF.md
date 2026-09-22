# bus48 handoff (Sep 18, 2026)

Goal: visit all 48 contiguous states by scheduled surface transport (intercity bus, Amtrak, local transit for connections) faster than the known timetabled record of **238.83 h** (White River Junction → Huntington, Guinness 13d 21h 34m).

**Current best: 237.5 h, verified end to end in the router.** Result pickle: `out/hun_ms_meteor.pkl`. Leg sheet: `~/Downloads/48states_Huntington_237h.xlsx`. The sheet's day numbers are one too high, and it uses the feed's 1:00 AM Barons time; the real departure is 12:45 AM.

## 1. Rules (Nick's)

1. You must be able to get off at a stop in each state.
2. No U-turns on long-distance buses. Allowed exception: the Boston–Portland ME round trip.
3. Amtrak and local transit are allowed.
4. Border walk-ins count if the walk is short. Nick accepted 1.3 km jogs (17–18 min walking, 12–13 min jogging).
5. The start day is free. The Cincinnati Kentucky trick counts but is risky. Barstow is the minimum California point coming from Las Vegas.

## 2. The 237.5 h route

Starts Huntington WV, Thu Sep 24, 12:45 AM ET. Ends at the Vermont line in Hanover, Sat Oct 3, 10:14 PM ET.

- Barons BSB 33 Huntington 12:45 AM → Columbus 4:30. Kentucky comes from the Ashland stop, and again from Fulton on the train.
- BSB 33A Columbus 6:50 → Detroit 11:30 → 1:50 PM Greyhound → Indianapolis → Effingham 9:15 PM
- City of New Orleans 10:01 PM → Memphis 4:42 AM → walk to Bellevue at Carr → MATA 42 5:32 → Holmes at Elvis Presley 6:07 → 1.3 km walk to the Mississippi line and back → 7:07 bus → Airways Transit Center 7:38
- Jefferson Lines 8:30 (via Conway AR) → Kansas City 7:25 PM → 1:30 AM Sioux Falls → Fargo 2:35 PM → 3:55 PM Minneapolis → Eau Claire WI out and back
- 6:45 AM Billings bus (via Gillette WY) → Spokane 1:30 AM → NWL 710 to Pasco → 1:25 PM Greyhound → Salt Lake City 2:30 AM → Salt Lake Express 6:30 → St George → Las Vegas → FlixBus → Barstow 5:55 PM
- Southwest Chief 8:47 PM → Newton 1:47 AM → BeeLine 3:00 → OKC bus station 6:43 (one ticket) → 6:55 Greyhound → Dallas 11:10 → 11:30 FlixBus (or 1:00 PM) → Houston
- 6:35 PM Greyhound → Tallahassee 11:00 → Jacksonville 2:50 PM → JTA route 4, 3:00/3:01 PM → Amtrak station 3:29 → Silver Meteor 4:11 PM
- Washington 6:25 AM → 6:40 AM Acela (Saturday) → Boston 1:46 PM → Concord Coach Portland ME round trip, 2:15/4:45 → 7:30 PM Dartmouth Coach → Hanover 10:00 → walk to the VT line, 10:14 PM

### Risks

| Connection | Buffer | If missed |
|---|---|---|
| Silver Meteor → Acela, Washington | 15 min | +3.8 h → 241.0 h (loses the record) |
| BeeLine → Greyhound, OKC | 12 min | one ticket, so protected |
| Greyhound → JTA 4, Jacksonville | 10 min | weekday backup bus at 3:31 PM |
| FlixBus → Greyhound, Houston | 40 min | — |
| Sioux Falls → Fargo bus | — | doesn't run Tue/Wed, so the route can't start Sun or Mon |

The record route has 8 tight connections, and missing most of them costs +24 h.

## 3. Why the route has this shape

Six once-daily "anchors" fix the timing:

1. Effingham → Memphis train, Thu 10:01 PM ET
2. KC → Sioux Falls, Sat 1:30 AM
3. Minneapolis → Billings, Sun 6:45 AM
4. Southwest Chief at Barstow, Tue 8:47 PM
5. Houston → Jacksonville Greyhound, Thu 6:35 PM
6. Silver Meteor, Fri 4:11 PM

Time only comes off by trimming the two ends, or by reaching an anchor 24 h earlier. New England has to be one end. The northern tier only works via Jefferson Lines. The Michigan + West Virginia cluster has to be the other end.

## 4. Tested and ruled out (don't rerun)

| Start / idea | Result |
|---|---|
| Huntington Thu (search) | 237.7 (= 237.5 with real Barons times) |
| Fargo shortcut seed | 237.7, back to the same route |
| Fargo start | 246.5 |
| Wheeling | 258.4 (Michigan costs 31.7 h; 226.7 for 47 states) |
| Omaha | 252.7, invalid (used bogus river walk-ins) |
| Bluefield | 279.0 |
| Milwaukee / Tornado | 288.9 |
| Pasco / Jacksonville / Barstow | 257.0 / 255.2 / 281.4 |

These don't help either:
- Parkersburg, CVG, Morgantown, Weirton starts
- TARTA, South Bend Transpo, Dubuque, Kimball/Cheyenne, Pierre–Bismarck
- Tufesa (Vegas → Boise leaves Fri 10 PM, arrives 2 PM, runs weekly)
- Kansas via KCATA; the Huntington / Lawrence County bridge feeds
- Fargo 3:15 PM northern Billings bus: saves 24 h but loses MN, WI and WY, and Wyoming eats the 24 h
- The 4:47 AM DC train skips Delaware. First DE option: 3:30 Greyhound DC → Wilmington 5:55 → 6:07 Acela (Sat)

## 5. Still open (only these are worth running)

The queue `out/run_safe_queue.sh` (copy in `scripts/`) runs these three, one at a time:

1. **kcdirect.** Huntington 12:45 AM → Columbus 4:15 → 4:40 AM Greyhound → St. Louis 3:10 PM → 5:15 PM → Kansas City 9:45 PM Thu. That catches the Fri 1:30 AM Sioux Falls bus, 24 h earlier. Cost: Michigan, TN, MS and AR have to go somewhere else. By hand it ties, with Michigan unplaced. Dallas 7:00 PM → Memphis 3:45 AM Greyhound is confirmed. Nick found nothing that reaches KC in time with Detroit kept.
2. **record2.** Re-search the 238.8 h record shape (`out/time_238.pkl`) with the new feeds and code.
3. **reverseA.** The 237.5 h shape run backwards, starting from White River Junction.

Also open:
- 152 feed trips with placeholder times are invisible to the router: Omnibus Express to El Paso, Tornado routes 7/8/9, RedCoach Dallas↔OKC, Limousine Express LA↔El Paso, Miami↔Houston. Real times could open new shapes.
- An ending that avoids the 15 min Meteor → Acela connection.

Results get appended to `out/resume_summary.txt` as `name: FINAL ...`. Logs are in `out/res_<name>.log`.

## 6. How to run (IMPORTANT: this machine crashed once)

The Mac has 8 cores (4 performance + 4 efficiency) and 8 GB of RAM. One router uses about 550 MB. Two searches at once (8 + 4 workers) plus ad-hoc router tests crashed it.

1. Run **one search at a time**, with `--workers 4` and `nice -n 10`. `run_safe_queue.sh` has a lock file (`out/.search.lock`) and refuses to start while another queue is running.
2. Don't start ad-hoc router tests while a search is running. Wait, or `pkill -f run_safe_queue; pkill -f time_search` first.
3. Always use `/opt/homebrew/bin/python3`. Plain `python3` is /usr/bin/python3, which has no numpy.
4. Env: `BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4`. 1.4 is needed for the Memphis → MS walk-in; the record route used 0.5.
5. Launch detached (`nohup ... &`), with one notifier per result. Never block on a search.

Example:

```bash
cd ~/Downloads/bus48/scripts && BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 nice -n 10 /opt/homebrew/bin/python3 -u time_search.py --start "Huntington Bus Stop" --at 2026-09-24T00:30 --tz America/New_York --seed ../out/hun_ms_meteor.pkl --budget 900 --workers 4 --days 16 --out ../out/res_x.pkl > ../out/res_x.log 2>&1 &
```

Search notes:
- Targets are state indices or `@stop substring` pins. Each target is greedy earliest-arrival, so an unpinned order can drift from the chain you meant. Pin stops, or seed with the full state sequence, to reproduce a specific route.
- Seeds without pins can start at ~340 h. That's normal, and prune/relocate brings them down.
- The scan is in C (`scripts/csa.c` via ctypes): about 6 ms per `finish()`.

## 7. Changes in commit 4dc5bbf+ (branch `pipeline`, not pushed)

- `scripts/time_router.py`:
  - `keep_routes` per-feed route filter
  - loads the previous service day (needed for the 12:45 AM Barons trip, which originates Wed in Charlotte)
  - `RIVER_BORDERS` walk-in block, with `RIVER_OK` exceptions for Hanover and Fargo/Moorhead
  - `data/walk_links.csv` loader (`extra:` end points are reachable only by their measured link)
  - ExtraFeed max speed 160
- `scripts/time_search.py`: parallel `prune` via `_drop_eval` in the worker pool
- `data/extra_trips.csv`:
  - Barons real times
  - Tornado Route 3 Milwaukee → Dallas, *daily assumed*, with an *approximate* Effingham stop
  - two on-foot border stops
- `data/walk_links.csv`: Dubuque ↔ WI line 88 min; Memphis Amtrak ↔ AR line via the Big River Crossing, 33 min
- `data/more_gtfs/*.zip` + `keep_routes.json`: mata, jta, gobus, svrta, mlta, tarta, transpo, metra, kimball, jule, fourcounty, dart, lake_erie. Calendars were extended to 2026-12-31 for svrta, metra and kimball. Metra headers were cleaned.

Assumptions to verify before a real attempt:
- Barons intermediate stop times
- Tornado runs daily
- the Fargo/Moorhead bridge walk
- every calendar extended past its published end

## 8. Sep 18 evening: search fixes and results

Search fixes (all on by default except the scan window, which the run scripts set):
- `BUS48_SCAN_SLACK_H=24`: a state can be collected at any of its stops reached within a day of the first, not just 10 h (Mobile over Tuscaloosa, etc.).
- Gateway moves: each state's 5 busiest stop clusters become `@~lon,lat,km` targets the search can swap in.
- Tie-break (`TIE_W`): equal finishes prefer earlier per-state arrivals, so partial savings toward a once-daily departure count.
- Relocate a state anywhere in the order (was within 8 places); `--seed-states` accepts `@stop` pins; seed pins are never pruned.
- `scripts/leg_report.py <log>`: waits, long rides, U-turns for a finished run. U-turns are allowed when timetabled (Nick).
- `scripts/hub_table.py`: schedule-free riding-time floor between 53 hubs (`out/hub_table.csv`); the Sioux Falls hub point needs fixing.

New data: Las Vegas NM Amtrak 3:05 PM → Denver 8:15 PM daily bus (off the Chief); Groome DEN airport ↔ Cheyenne shuttle + A Line link; Wandacoach Florence SC → Jacksonville (never wins); Lawrence County Transit (Ashland ↔ Coal Grove OH, Huntington ↔ South Point OH, weekdays daytime).

Results with the fixes (h): Huntington 237.5 (unchanged, local optimum), record 238.8 (unchanged), fixFargoDenver 244.4, Fargo 246.5, denverV7c/v7cAtlanta 247.2, fixDenverN1 248.6, Omaha 255.6, zephyrSouth 259.2, twopass 277.0.

fixFargoDenver by hand is ~239.9 h: Hanover VT-line walk 6:05 AM → 6:40 Dartmouth Coach → Portland round trip → 3:10 PM Acela → Baltimore → 12:35 AM Greyhound → Pittsburgh 7:35 AM (then unchanged to Jacksonville Fri 2:50 PM) → Savannah → Charlotte → Columbus → Effingham → City of New Orleans → Memphis → Big River Crossing to AR, Sun ~6:15 AM ET. Opening cutoff: at Boston South Station by 3:00 PM (3:15 PM NER); a 4:00 PM Boston bus + 9:00 PM FlixBus NYC → Baltimore 12:05 AM would add ~1 h if Delaware can be collected. The 237.5 route's New England ending was tested in every order: ending anywhere but the Hanover VT line costs ~9 h.

Checked Sep 18 late: AE bus Las Vegas NV Tue 6:00 PM → Kingman → Phoenix → Tucson → El Paso 6:29 AM (in extra_trips, no NM stop). Every El Paso → Houston/East Texas bus (Greyhound, Omnibus, Tornado, El Expreso) leaves at night, so Houston a day early (Wed 6:35 PM Jacksonville bus) is out of reach this way. Dead end.
Big River Crossing (Memphis → AR walk link) opens 6 AM (Nick); the router does not enforce hours. fixFargoDenver's Sun 4:42 AM Memphis arrival therefore reaches AR ~6:33 AM → ~241.2 h (the only earlier AR is a taxi across I-40, not allowed).
COAST (Portsmouth NH) feed added: route 44 Portsmouth ↔ Kittery (PNSY Gate 1) is weekdays only and the Pease Shuttle has no trips. Maine via Kittery never beats the Portland round trip: Acela reaches Boston 1:46 PM, C&J runs every 2 h from 9 AM (Nick), so the earliest return misses the 5:30 PM Dartmouth Coach. The New England ending finishes 22:14 from DC 6:25 AM on every weekday. Meteor lateness: 10 min to 4.5 h late all give 241.2 h (Sun 2:00 AM, via Portsmouth walk-in + WRJ Greyhound).
Upper Midwest (Sep 18): in the 237.5 route, Sioux Falls Sat 10:05 → Fargo → Minneapolis → Eau Claire overnight round trip → Minneapolis 6:45 AM → Sioux Falls again Sun 12:40 → Billings is a 26.5 h loop that collects ND, MN and WI. Only one Sioux Falls → Billings bus runs a day (12:40), and nothing gets ND, MN and WI back to Sioux Falls by 12:40 the same day, so the loop costs exactly one day. Montana costs nothing because Billings is on the only bus west. Local transit can't help: the Sioux Falls → Fargo (I-29) bus has no North Dakota stop south of Fargo, Moorhead is no earlier, and Metro Transit 294 to Stillwater runs once a day on weekdays. In the fixHun variant, dropping ND alone or MT alone leaves Pasco at Mon 13:10; dropping ND+NE+IA gives Sun 13:10.
Standing Rock + Bis-Man (Sep 19): Standing Rock Public Transit routes 1/2/4/5/9/12 were added to extra_trips and data/more_gtfs/bisman.zip was added. The Minneapolis → Fargo → Bismarck → McLaughlin/Mobridge SD → Billings path never wins. Leaving KC at 1:00 AM on any weekday and taking the best order of NE/IA/MN/WI/ND/SD/MT(+WY), Pasco is +62.2 h at best, the same as the 237.5 route (Sat → Mon 13:10), with or without Wyoming. The same-day SD loop fails because Standing Rock route 4 reaches Mandan at 6:15 PM, but the Bis-Man Purple bus to Bismarck leaves at 7:25 PM (arr. 7:55 PM), after the 6:30 PM Jefferson bus to Billings.

Sep 19 afternoon:
- Tools: scripts/blocker_finder.py (joint drop tests + near-miss departures), joint_move.py (pull a set of states out and re-insert them jointly), latest_start.py (latest start per stop that keeps a route's finish), retime.py.
- Blockers: denverV7c's full days (AL+FL+MS, WY+MT+ND) come from the route's shape (Pasco-south start). No carrier fixes them, and Missoula start is +6.9 h. fixDenverN1: WA+OR one day. fixFargoDenver: only the tail (WV+KY ~9 h).
- New carriers: StarLine (NYC <-> JAX/Orlando/Tampa, Savannah 8 PM northbound), Savannah CAT, Vonlane + RedCoach Dallas->Houston, Jaguar (Columbus 22:30 -> Wheeling 00:35 -> NYC 07:30), Wonder Bus (Knoxville 18:00 -> Winchester 01:00 -> Martinsburg -> Hagerstown -> Chambersburg 02:20 -> NYC 07:00), Weirton Transit + PRT 29 (one trip each). None moved a sub-250 route.
- 237.5 start: the latest_start sweep over WV stops gives 237.2 h real via the 1:00 AM Barons at Huntington (Charlotte -> Columbus trip) -> Columbus 4:50 -> the same 6:50 Detroit bus. Fixed departure: Columbus 6:50 Barons (and the City of New Orleans at Effingham, Thu 10:01 PM).
- Near misses: a Wheeling ~3 AM westbound to Columbus would give 235.2 h, but Wheeling looks drop-off only westbound. Weirton 6:10 -> Pittsburgh 8:50 Greyhound -> Toledo 2:05 PM fails because Michigan can't be collected by the 3:05 PM bus (TARTA to the MI line is >= 1h10). The latest Pittsburgh departure that works is 1:25 AM.

## 9. Sep 21: rebuilding out/, and why build_backward loses the 237 route

`out/` is gitignored, so a fresh clone has no result pickles at all and nothing can be tracked or
regression-checked. `scripts/rebuild_237.py` rebuilds both from the route written out in section 2:
237.74 h from the 12:30 AM clock and 237.34 h from 12:54 AM, finishing Sat Oct 3 10:14 PM either way,
all 48 states. Run it before `regress.py` on a new machine. Two details it has to get right:

- The router's own visit order is `... UT > AZ > NV > CA > NM ...`, not `UT > NV > CA > AZ`. Arizona is
  collected on the St George -> Las Vegas leg through the Virgin River Gorge, before Nevada.
- `res_starttest.pkl` came out of a search, so its order is pruned and West Virginia is not in it: the
  start stop is in WV and the first bus collects the state on the way out. This is not cosmetic. With WV
  first the start stop is itself in layer 0 and the backward pass reads the latest start straight off
  that layer; without it the start has to reach layer 0 by boarding, which costs one MIN_TRANSFER. That
  is the whole difference between 00:59:20 and the 00:54 `regress.py` records.

### Where the beam loses the route

Test: `build_backward.py --end VT --from 2026-10-03T22:14 --tz America/New_York --step 168 --track
../out/res_starttest.pkl`. The chain is dropped at step 19 (OK), 19.2 h below the beam cut. At that step
the reference stands at OK on Wed 17:20 and the beam leader at TX on Thu 12:25: same number of states
placed, and the sets differ by exactly one each, the reference still needing MS and the leader OK.

Two defects found, both fixed:

1. **The state-to-state matrix was measuring adjacency, not travel.** `state_times` scanned from every
   stop of a state including its border walk-in points, and those come in pairs either side of a state
   line, so neighbouring states came out 0.0 h apart. A spanning tree over 28 remaining states cost 45 h.
   It now skips walk-in points (cache `out/state_times_real.npy`); the same tree costs 70 h and the step
   19 gap narrows to 16.8 h.
2. **Candidate generation was too narrow.** `--topk` was fixed at 3. Walking the reference's own
   remaining picks (`scripts/tail_diag.py`) shows all of them rank 1 or 2 except Colorado out of Kansas
   at rank 6 and Wisconsin out of Wyoming at rank 5, so no beam width could rebuild it. With `--topk 6`
   step 21 goes from NOT CONSIDERED to considered.

### What is still open, and what not to retry

The selection gap at step 19 is not closed. The reference is 19.1 h further back than the leader there,
and nothing tried charges the leader enough more to make up for it. Ruled out, with numbers:

| Tried | Result |
|---|---|
| Beam 150 (and 100 earlier) | still ranks 151/150 at step 19 |
| Doubling strand_cost | -12.9 h, worse: scaling amplifies the wrong sign |
| Cheapest-entry sum over the matrix | -0.9 h, still the wrong sign |
| At most 2 chains per current state | evicts the reference's own TX node at step 18 |
| Sum of the dearest few reach values | not an estimate: see below |

The last one is worth recording because it looked convincing. From one reverse scan a node knows the
latest time it could still be in each state it has not placed; summing the furthest few of those and
subtracting from the node's own time separated step 19 cleanly (rank 21/21 -> 4/21). It is arithmetic,
not signal: each value is the node's own time minus a latest time, so summing n of them counts that time
n times and the score pays a chain n-1 times over simply for being further back. At step 11, where the
reference is ahead rather than behind, the same estimate is the worst of the six tested. Only the single
furthest value is safe, and alone it is worth 9.5 h against the 19.1 h needed.

Where the remaining signal has to come from: from Texas, Oklahoma on its own is cheap, and the reference
pays 19 h there for the once-a-day chain out (Newton, the Southwest Chief, the morning OKC bus). The cost
is in doing Oklahoma *and then* continuing west, so it is a property of the sequence, not of the state,
and no per-state estimate off a single scan can see it. `tail_diag.py` puts the whole tail at 49 h of
myopic loss over 28 steps, 24.6 h of it in those two steps alone.

Diagnostics added: `dump_diag.py` (what the beam holds at a `--dump-step` dump and how it differs from
the tracked chain), `est_probe.py` (candidate estimates against a dump, no router needed),
`reach_probe.py` (scan-based estimates, and the bias above), `tail_diag.py` (the tracked chain's
remaining picks, their rank, and what each costs).

### Sep 21 late: the backward builder's score has a ceiling at 267.7 h

Root the search at the reference's own step 19 node, in Oklahoma, with 28 states left, from which a
237.3 h completion is known to exist (`scripts/tail_track.py`, `scripts/rollout_probe.py`). It reaches:

| beam | topk | lineage survival | reaches |
|---|---|---|---|
| 5 | 6 | - | 289.0 h |
| 15 | 6 | - | 279.1 h |
| 30 | 6 | - | 267.7 h |
| 60 | 6 | - | 267.7 h |
| 120 | 6 | - | 267.7 h |
| 60 | 12 | - | 267.7 h |
| 60 | 6 | 40 places | 267.7 h |

Byte-identical past beam 30. Neither beam width, nor candidate width, nor reserving places for chains
that would otherwise die moves it. **267.7 h is the scoring function's own optimum, and search effort is
irrelevant to it.** Do not spend more on the search side.

`tail_track` says why. From Oklahoma the reference's next two picks hold (Colorado at rank 6 survives, so
`--topk 6` is doing its job), and it is lost four steps later at California, which backwards is boarding
the Southwest Chief at Barstow. That costs 11.8 h against the myopic alternative. It then sits 5 to 25 h
under the cut for fifteen consecutive steps and only collects its advantage at the very end, where it
leads the beam by 30 to 47 h (OH +31.6, KY +47.3, WV +38.9).

So the route needs the search to take a child 9 to 12 h worse than its best sibling, fifteen times
running. Lineage survival does not give that: the reference's parent survives happily via a different
child, and what has to survive is the losing sibling. Nothing short of exhaustive search picks a losing
sibling fifteen times, so the fix has to be in the score, not in what survives it.

What the score has to start doing: credit those fifteen choices. Two families are already ruled out by
measurement, both because the two chains' remaining states differ by only one at the point of the cut:
anything computed from the set of states left (spanning tree, cheapest-entry sum, any weighting of
either), and anything computed per state from one reverse scan (the furthest-back state is worth 9.5 h
against the 19.1 h needed). What is left is knowledge the route already has and the score does not:
section 3's six once-daily anchors. A chain that has committed to one has locked in progress its clock
does not show, and that is the quantity to put in the estimate.

Worth considering: the forward search does reach 237 and the backward builder tops out at 267.7, so the
builder's value may be as a seed generator for the forward search rather than as a route finder. "It does
not count until it can rebuild 237" may be the wrong bar for this tool.

`half_probe.py` is unsound as written and its verdict should be ignored: it ranks by pure lateness with no
leftover estimate, which is weaker than the builder, and it cannot even reproduce the eastern half that
the real builder tracks to within an hour. Fix it to score the way `build` does before believing it.

## 10. Sep 22: the four local hops, and what the route stands on

The 237 route has four legs whose access is a *modelled* link rather than a service: `LOCAL_MAX_KM` builds a
proxy for any 1.5 to 10 km gap at a flat 30 min plus 15 km/h. Each was checked against the real feeds.

| leg | hop | verdict |
|---|---|---|
| 6 | 3.5 km Memphis Amtrak -> Bellevue at Carr | **weakest.** No MATA route reaches the Bellevue/Carr stops from downtown. Route 34 (05:20 from 2nd St at Beale, 993 m from the Amtrak door) reaches Lamar Ave at Minna Pl at 05:29, 370 m short, 3 min before the CROSSTOWN. Otherwise it is a 3.5 km walk in the 50 min the timetable allows. |
| 19 | 9.9 km SLC Intermodal -> Salt Lake Express shop | **fictional, and fixable.** The shop is out by the airport; the nearest UTA stop is 350 m from it. FrontRunner leaves Salt Lake Central, 50 m from where the Greyhound drops you, every 30 min, and the same 06:30 Salt Lake Express calls at Provo/Orem (Exit 263) at 07:50, 110 m from Provo Central Station. 06:06 -> 07:11 leaves 39 min; 06:36 -> 07:41 leaves 9. Same bus, same St George 12:20: no time saved, and about 4 h of slack gained on an overnight Greyhound. |
| 21 | 8.7 km Las Vegas Airport -> Downtown (1st St) | **real.** RTC RED LINE 14:06 from Harry Reid Zero Level (83 m from the stop) reaches Bonneville Transit Center 14:50, 126 m from the FlixBus stop, 15 min before it leaves. Route 108 is a second option. |
| 22 | 2.8 km Barstow Station -> Barstow Amtrak | **real.** VVTA route 1 at 18:18 (80 m from the FlixBus drop) reaches Hutchinson St at N 1st Ave 18:29, 420 m from the depot, over 2 h before the Chief. The 19:28 is a backup, and 2.8 km in 2 h 52 min is a walk anyway. Note route 1's last Barstow Station trip is 17:10 on a Sunday, before the 17:55 arrival, so a Sunday Barstow is walk-only. The Chief calls only at the depot; "Barstow Amtrak Bus Stop", 70 m from the FlixBus stop, is a thruway bus stop and a decoy. |

Memphis has slack that has not been used. The CROSSTOWN runs Bellevue/Carr at 04:32, 05:32, 06:32, 07:02,
07:32, and back from Holmes at 07:07, 07:37, 08:07. The 07:37 back reaches Airways at 08:08, still 22 min
before the 08:30 Jefferson Lines. So either keep the 05:32 out and take the 07:37 back, which turns 60 min at
the Mississippi line into 90, or take the 06:32 out and the 07:37 back, which gives 1 h 50 min to cover the
3.5 km into Bellevue/Carr and leaves 30 min for the 1.3 km walk each way.

### The proxies are load-bearing

`BUS48_LOCAL_MAX_KM=0` drops every proxy and keeps only real timetables and walks. The same 48-state order
then still collects every state, but takes **285.7 h instead of 237.7 h**. Without them the router does find
real access everywhere it needs it (TRAX to the Salt Lake Express airport stop, RTC to the Las Vegas
terminal, MATA through Mississippi Blvd), but the timings cascade and the route loses the Southwest Chief at
Barstow, going via Raton and Trinidad instead.

That 48 h is the greedy cost of the *same state order*, not proof that no proxy-free route is quick. But it
does mean the 237 h figure currently rests on links nobody runs, so before an attempt the open question is
whether a search with `BUS48_LOCAL_MAX_KM=0` finds something near 240. That has not been run.

## 11. Sep 22: the static-matrix family is dead, and what replaces it

The last idea for the leftover estimate was to make the state-to-state matrix frequency-aware: a high
percentile over the sampled deadlines instead of the median, symmetrised by the dearer direction instead
of the cheaper, so that a once-a-day corridor costs more than a dense one. The chains the beam cannot tell
apart differ by exactly one state, and that state is always a rare-corridor one (Oklahoma at step 19,
California at tail step 4) against a dense one (Mississippi), so the prediction was that the leader would
finally be charged more. Both matrices are built (`--times-pct`, `--times-sym`, cached as
`state_times_real_p{pct}{sym}.npy`).

It is wrong, and it fails in the informative direction. At step 19, needing +19.1 h:

| matrix | tracked | leader | separation |
|---|---|---|---|
| median, min-symmetrised (current) | 70.5 h | 63.6 h | -6.9 h |
| 75th percentile, max-symmetrised | 136.9 h | 124.9 h | -12.0 h |
| 90th percentile, max-symmetrised | 189.0 h | 172.1 h | -16.8 h |

The estimates get much closer to the true remainder of about 160 h, and the separation gets steadily
**worse**. The reason is structural: a spanning tree is a *minimum*, so it attaches every state by its
cheapest remaining neighbour. Oklahoma is interior, ringed by states still unplaced, so it attaches cheaply
however the matrix is scaled, and scaling only amplifies the sign that was already wrong.

**So every estimate of the form f(states left, static matrix) is ruled out by measurement**: plain, doubled,
cheapest-entry sum, and both frequency-aware matrices. Together with the earlier results (no set-based
estimate can separate chains whose remaining states differ by one; per-state reach from one scan is worth
9.5 h against the 19.1 needed; summing reach values is arithmetically biased), there is no estimate left to
try in this shape. Stop writing them.

### What the route actually needs, and where to build next

`scripts/anchors.py` derives from the feeds alone the services that are both long and rare: 4 or more states
in one ride, at most twice a day. It reproduces section 3's anchors without being told them (the Southwest
Chief and the Silver Meteor both come out near the top), which is the check that the concept is real and not
fitted to the known route.

Committing to one of these is precisely what the score cannot price. The chain that boards the Chief at
Barstow is 11.8 h worse immediately, because committing means being somewhere at a fixed hour, and stays
worse for fifteen steps. A score cannot see that far, and a beam cannot hold it. So **branch on the
commitment instead of pricing it**: for each anchor, run a build that is forced to use it, and compare the
finished routes. That is a few dozen constrained runs rather than one search, and none of them needs a
better heuristic.

The list also turned up a lead that is in neither section 3 nor section 4:

```
 8 states  0.43/day   Empire Builder   OR > WA > ID > MT > ND > MN > WI > IL
                      Portland -> Chicago Union Station
```

Eight states in one ride, covering the northern tier the 237 route currently spends legs 15 to 18 and about
two days crossing by Jefferson Lines via Billings, Spokane and Pasco. It does not collect SD, WY, NE or IA,
which the Jefferson runs do, so it is not a drop-in. It has not been tested.

## 12. Sep 22: depth-first with backtracking, and the number that decides it

Nick's shape: the timetables are a menu, the search works against a time limit, and when the options taken
get it too far it backs up a step and tries the next one, then a step further back. That is branch and
bound (`scripts/dfs_backward.py`), and it fixes the exact flaw that defeated every estimate.

A beam prunes **relatively**: it keeps whichever chains look best against each other now, which is why it
throws away a route that is behind for fifteen steps and only wins at the end. Backtracking prunes
**absolutely**: a branch dies only when what it has spent plus a floor on what is left would pass the limit.
Being behind some other chain is not a reason, so the 237 route is never discarded. It also changes what is
needed from the estimate, from one that ranks correctly, which five attempts failed at, to one that merely
never sits above the truth. That is a far easier target, and the reach floor that was useless for ranking is
a perfectly good bound.

First run, end VT, limit 238 h, topk 6: **6163 nodes in 903 s (7/s), 5112 branches cut, nothing found.**

### The bound is 35% of the truth, and it needs about 85%

`scripts/bound_probe.py` walks the reference chain and compares each candidate floor with the remaining time
along that same chain. (Measure the remainder against this chain's own end, not the forward route's clock: a
strict sequential backward chain is a stronger requirement than the route, which collects states in passing,
so its latest times run earlier and `total - spent` goes negative near the start. An earlier version of the
probe did that and reported false inadmissibility.)

| step | at | true left | tree | reach | hybrid | best/true |
|---|---|---|---|---|---|---|
| 1 | VT | 259.9 | 90.2 | 73.6 | 88.5 | 35% |
| 9 | PA | 244.2 | 83.2 | 67.6 | 83.0 | 34% |
| 17 | AL | 211.6 | 70.9 | 66.8 | 73.7 | 35% |
| 25 | NV | 136.2 | 58.7 | 54.9 | 60.9 | 45% |
| 33 | WI | 75.2 | 36.6 | 21.8 | 42.0 | 56% |
| 41 | MS | 30.0 | 15.5 | 20.8 | 11.4 | 69% |

The arithmetic that matters: with a limit of 238 h and a floor of 90 h, nothing is cut until 148 h have been
spent, which is around step 21. The top twenty levels are unprunable, and 6^20 is 3.6e15. At a 60% bound
pruning would start near step 17, still 1.7e13. At **85%** it starts around step 6, and 6^7 is 280000, which
is searchable. So the bound has to roughly triple. That is the whole problem, stated as a number.

Two smaller results: `win`, counting a state the scan could not reach as at least a window away, is worth
nothing, because from anywhere in the country every state is reachable inside 110 h, so it equals `reach`
everywhere. And `hybrid`, the spanning tree with the current state's edges replaced by measured ones, is not
better than the plain tree (88.5 against 90.2 at the root).

### Where a tighter bound would come from

Not from another matrix: section 11 ruled that family out. The standard answer to this is abstraction.
Partition the 48 states into about eight regions, precompute the true minimum time to traverse each region
and to move between them by time of day, and bound by the cheapest region ordering (8! = 40320, trivial to
enumerate). Because regions partition the states the bound stays admissible, and because it uses real
traversal costs rather than best-case pairwise hops it should be far tighter than 35%. That is a
substantial build and it has not been started.

The cheaper use of the same idea, which is worth doing first: **bounded backtracking over a window.** Do not
search 48 levels from scratch. Hold the 237 route fixed except for k consecutive states and search that
window exhaustively with the limit set to the current best. At k of 6 to 8 that is a few thousand nodes per
window and it is exact within the window, which is a strictly stronger version of what the forward search's
relocate move does by sampling.

### Empire Builder: tested and ruled out (Sep 22)

`anchors.py` put the Empire Builder at the top of the western anchors, 8 states in one ride, and it was in
neither section 3 nor section 4. Nick's framing was right and is what made it testable: it is not a redesign,
it is a leg swap, on at Minneapolis or Fargo and off at Spokane or Pasco, replacing legs 15 to 18.

Minneapolis is the only boarding that works at all. The westbound passes Fargo at 05:13 CT, nine hours before
the route reaches Fargo at 14:35.

| | |
|---|---|
| MSP dep 24:13 ET (23:13 CT) -> Spokane 55:49 -> Pasco arr 58:40 ET (07:40 PT) | 34.5 h riding |
| the current Minneapolis -> Pasco chain | 32.4 h, so the train is slower |
| arrival at Pasco | 07:40 against 13:10, 5.5 h earlier |
| what leaves Pasco southbound | 13:25 and 14:25 PT only (flix feed, stored UTC as 20:25 and 21:25) |

So the 5.5 h is spent waiting: the next bus to Salt Lake City is 13:25 either way. Against that the swap costs
**Wyoming** (Gillette, on the Minneapolis -> Billings bus) and **Wisconsin** (the Eau Claire round trip leaves
Minneapolis 00:15, and the Builder leaves 23:13 the evening before, so the two cannot both be done). Montana,
Idaho and Washington are collected either way, at Havre, Sandpoint and Spokane. Section 8 already prices
Wyoming alone at 24 h. Strictly worse on every axis; do not rerun.

The wider lesson for the search: no window reordering could ever have found or refuted this, because using the
Builder needs IL, WI, MN, ND, MT, ID, WA and OR contiguous, and they sit ten places apart in the route. Leg
swaps around a named service have to be tested directly.

### Memphis: the slack is fixed, you only choose where it sits (Sep 22)

Both links out are once a day with no alternative: Memphis -> Conway 08:30 -> 11:10, and Conway -> Kansas
City 11:20 -> 19:25 on a ten minute connection. So the 6.1 h wait at Kansas City is slack that can only be
spent in Kansas City. The 08:30 is hard, the 04:42 Amtrak arrival is hard, and the CROSSTOWN's 60 min
headway means the spare hour lands in one lump in one of two places.

Nothing but route 34 reaches the Bellevue/Carr stops from downtown, and it lands 370 m away at 05:29
against a 05:32 departure, so the choice is forced:

| | getting to Bellevue/Carr | at Holmes for the 1.3 km each way |
|---|---|---|
| rt 34 at 05:20, then the 06:32 CROSSTOWN | relaxed, about 57 min sitting | **30 min**, so a jog |
| walk the 3.5 km from the Amtrak door, 05:32 CROSSTOWN | 50 min for about 4 km, brisk, no margin | **90 min**, a walk |

Nick's call is the first: push it a headway and get breakfast near the transfer, since 2.6 km in 30 min is
inside the 1.3 km in 12 to 13 he has already accepted. Worth recording that this is the third time the
route's spare time ends up on the Mississippi walk, which makes that walk the thing to verify on the ground.

The 3 min 370 m dash off route 34 onto the 05:32 should not be planned around either way: it depends on
route 34 being exactly on time and leaves no margin at all.

### The alight rule: Barstow and Conway are the tests (Sep 22)

`ride_search.py` had to decide where a ride may be got off, and the first version used a guess: any stop in a
state not yet collected, or any stop with at least six departing services. Nick named the two stops that test
it, and the rule fails both.

| stop the route must use | distinct services | old rule |
|---|---|---|
| Barstow Station (where FlixBus drops) | 8 | passes, but the Chief does not leave from here |
| **Barstow Amtrak depot** | **2** | **fails**, and California is already collected by then, so the new-state clause does not save it either |
| **Conway, AR** | **5** | **fails**, and survives only because Arkansas happens to be new there |

So the search could never have boarded the Southwest Chief, and Conway is one reordering away from being
invisible too. A busyness count is exactly the kind of aggregation that ruined every earlier estimate: the
two stops a 48-state route cannot do without are a desert depot and a small Arkansas town.

The rule is now exact and has no knob. Getting off at a stop is allowed when every state still owed remains
collectible from there at that time, and the end remains reachable, both read straight off the deadline
tables. Barstow and Conway both pass, because from either one everything still owed is still collectible.
`--hub` survives only as the fallback for runs given no deadline.

## 13. Where backward's second actually goes

Backward runs at about one node a second, against 274 for forward. Two guesses at the cause were wrong and
both were measured before shipping, which is the only reason they did not end up in the tree:

| tried | result |
|---|---|
| cache the per-node reverse scan on (stop, clock rounded up to the half hour) | 43 nodes at 62 s either way, identical at every heartbeat. Not shipped. |
| `conn_pos`: index each connection's position in its trip instead of walking the trip list to find it | 56 nodes in 93 s against 57 in 92 s. Shipped as a simplification, not as a fix. |

The scan cache deserves one caveat rather than a verdict: a 90 s backward run sees about 46 nodes, no stop
repeats in 46 nodes, so the cache could not hit even once. It was measured on a sample too small to say
anything. If backward ever runs fast enough to revisit a stop, try it again.

A profile of a 90 s backward run (`cProfile`, sorted by internal time) says where the second goes. Search
phase only, 96 s for 46 nodes:

| where | calls | tottime | per call | share |
|---|---|---|---|---|
| `ride_search.py:rides_into` | 42 | 44.1 s | 1.05 s | ~46% |
| `backward.py:through`, from `still_collectable` | ~42 of 91 | ~24 s | 0.57 s | ~25% |

Building the menu costs twice what the feasibility scan does, and the scan was what both guesses attacked.
`rides_into` is a triple loop: footpath neighbours of the stop, times every arrival inside `--horizon`
hours at each, times every upstream stop of each trip found. At a hub that is on the order of a hundred
thousand emitted options, each carrying a freshly built `frozenset(got)`, which are then sorted so that
`--width` of them survive.

The next thing to try, exact and behaviour-identical: `got` grows monotonically as the loop walks upstream
and most upstream stops add no new state, so the frozenset only has to be rebuilt when a state is actually
added and can be shared by reference in between. That replaces one allocation per upstream stop with one
per new state. The forward side has the same shape and the same fix. Measure it the same way before
believing it, and note that the honest test needs a run long enough to see more than 46 nodes.

## 14. Repair: what the dead time could collect

Nick's question, and the answer is yes. A constructive search cannot rank its way to the Memphis move: the
ride to Holmes is one of 834 survivors at that node, collects nothing on arrival, and pays off five days
later in Florida. As a repair it is trivial, because the chain already exists and the hole is visible.

For a gap between where one ride drops you, at that time, and where the next picks you up, at that time:

```
one forward scan from (A, t_in)    earliest you can be at every stop
one reverse scan from (B, t_out)   latest you can leave every stop and still make B
state y fits  <=>  some stop of y has earliest <= latest
```

Two scans per gap, 0.0 s each, 37 gaps on the control. Nothing estimated, no threshold invented.

`repair_probe.py --route ../out/res_starttest.pkl --drop 6-7` removes the Memphis excursion and asks what
the reopened window offers:

```
 5  Memphis -> Memphis (MA   3.8 h   AR MS
```

Mississippi and Arkansas, which is what the control collects there, recovered from the timetable on a route
that no longer contained the move. Nick described the gap as four hours; it measures 3.8.

Every other window on the control reports nothing, including Omaha at 4.8 h, Salt Lake City at 4.0 h,
Minneapolis at 3.9 h and Barstow at 2.9 h. On an optimal route that is the right answer, and it says the
probe is not simply spraying candidates. It also measures something about 237 that had only been asserted:
all of its dead time except Memphis holds no state it lacks.

### The modelling error worth remembering

The first version required the next ride to board where the last one alighted, dismissing anything else as
"not a clean layover". That excluded precisely the move it was written for, since the Memphis excursion
lands at Holmes and boards the Jefferson bus at Airways Transit Center. Run on the intact control it printed
`HOLMES 1.0 h TN MS` and looked correct, while being structurally unable to find the move on a route that
did not already contain it. Only dropping the excursion separated the two.

That is the fifth time a same-shaped assumption has hidden the thing the route depends on, and the first
four are in CLAUDE.md. The gap's two ends are data; requiring them to be equal was a guess.

### When it is free, and when it is not

The first version of this section claimed a detour "leaves every later leg bit-identical, so nothing
downstream can break". That is only true when the chain was **alighting at X anyway**. If it was going to
stay aboard through X, an insertion forces getting off and reboarding, which costs at least MIN_TRANSFER
and may miss the vehicle entirely, and the later legs are then not identical at all.

Memphis happens to alight, so the probe result there does not demonstrate the general claim, and the claim
was doing real work: it was going to be the foundation of a spine-plus-repair design where repair is always
free. It is not. A repair pass has to check whether the window it is filling sits inside a stay-aboard, and
price it when it does.

What survives is the weaker and still useful statement: where the chain already alights and the detour
returns before the same departure, elapsed time is unchanged by construction. What changes is the owed set,
and that is where the gain lives. Collecting MS at Memphis is what frees the Houston to Tallahassee bus that skips
Mississippi, which arrives early enough for the Silver Meteor and the accelerated finish. The operator is
not a tidy-up pass, it is an enabler.

Next: run it on what the search produces rather than on the control. A chain that stalls at 28 states owes
20, and the question is how many of those its own dead time already holds.

## 15. Sep 22: the pair prune, and what the deep bucket was really holding

The search kept a node while every state it still owed was individually collectable, `L[y][stop] >= t`.
That test is exact and it is not enough. The deepest chain of the long runs passed it at every leg and was
already dead: from ride 10 at Springfield Union Station, holding 23 states, it owed California and
Washington, each reachable on its own and neither reachable after the other. It then spent 2600 s and
83000 nodes below that position and reported 31 states. The 31 was not progress, it was bookkeeping.

`pair_tables.py` answers the question the per-state table cannot, with the same scans and no new machinery.
`L[z]` is one reverse scan seeded from z's stops with `L_end`. Seed a scan from y's stops with `L[z]`
instead and you get `L[y->z][s]`, the latest you can be at s and still collect y, then z, then finish.
`P[stop, y, z]` is the better of the two orders. A node owing y and z is dead when its clock is past it.
Nothing is estimated, which is the only reason it is allowed anywhere near this route.

`--pairs {report,pop,push}` wires it into `ride_search.py`. `report` builds the table and prunes nothing,
which is the arm the other two are read against; without it the baseline and the pruned runs are measured
with different instruments and the comparison says nothing.

### What it validated before it pruned anything

| | |
|---|---|
| table | 805 s on 2 workers of a 4-core box, 182 MB, keyed on the scan inputs so a changed router rebuilds |
| control, via `pair_tables.py` | 48/48 states, 69 nodes, 0 killed |
| control, via `ride_search.py --track --pairs push` | 0 of 40 ride nodes killed |
| tightest control margin, both | **+0.03 h at Trinidad CO, on AL & FL** |
| the deep chain | dead from ride 10, Springfield MA, CA & WA by 5.8 h |

The two control validations derive the owed set differently: `pair_tables` reads it off the route's legs
through `leg_states`, the replay accumulates what the menu actually returned. They agree on the same
tightest node and the same margin, which is a cross-check rather than one code path run twice.

**+0.03 h is 108 seconds, and that is the number to watch.** The table is a relaxation, so the true margin
can only be looser and the prune is sound as built. But it also means the prune is within two minutes of
killing the 237 route at Trinidad, and the last time a one-minute difference in how a walk was modelled got
in front of this route it compounded backwards into four hours by Houston. Anything that makes `P` stricter
has to be measured against that leg specifically, not against the replay's pass/fail.

### Where the check goes, and why there are two sites

`pop` tests a node as it comes off the frontier, `push` before it goes on. They are not interchangeable and
the difference is not throughput. `deepest` is raised at pop, before the death tests, and the exit census
reads whatever is sitting in the queue. So only `push` keeps a jointly dead chain from being counted as
depth and from filling the census. Which is cheaper is a measurement; which is honest is not.

The frontier sweep uses the test too, and prints what it dropped. Under `--pairs push` that has to read 0.
If it does not, a node reached the frontier untested, and the sweep is reporting the bug rather than doing
useful work.

### The gate the prune needed, and the one the writer never had

The search's pair sites live in `best_first`, which `--track` never reaches, so the prune would have shipped
with no gate inside the search at all. `--track` now tests the control's own nodes and exits non-zero on a
kill: a rule that kills a node of the 237 route is not a prune.

The same pass closed an older hole. `be64aa9` added a field to the legs the search pushes and not to the
ones it writes, so every `--out` raised `ValueError` with `regress.py` green and `--track` green, because
nothing routine exercises `route_record`. The replay is already walking real legs through the real menu, so
it now builds the same leg tuples `best_first` pushes, hands them to `route_record`, and asserts the derived
state order equals what the chain was credited with and that the result pickles. Doing that surfaced a live
`UnboundLocalError`: `route_record` was defined at line 960 and the `--track` block runs inline at 691.

The lesson is the one in CLAUDE.md's tier table, stated again because it keeps costing: a green oracle suite
and a green replay say nothing about a path neither of them executes. Ask which lines a gate actually runs.
