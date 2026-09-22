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
