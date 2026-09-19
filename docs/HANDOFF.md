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
