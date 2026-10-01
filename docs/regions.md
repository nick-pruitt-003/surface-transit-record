# Region tests (Oct 1 2026)

For each region: the fastest way to collect exactly those states, any order, starting anywhere in the region
and finishing anywhere. Run as

    BUS48_MIN_TRANSFER=5 BUS48_WALKIN_KM=1.4 python3 time_search.py --start free:<first state of seed> \
      --at 2026-09-24T00:00 --seed-states <seed> --done <every other state> --budget 900 --patience 300 --workers 4

with no `--end`, three seeds per region: forward, reversed, and rotated to start mid-region. Day d1 is Thu
Sep 24. Hours run from the first bus boarded to the finish, the same clock as the 237.3 h control.

## Results

| region | states | hours | start stop | first bus | finish stop | finish | seeds fwd / rev / mid |
|---|---|---|---|---|---|---|---|
| W7 | WA ID OR CA NV UT AZ | **26.6** | Pasco Bus Stop, WA | Thu 13:25 | CA state line, walk from Primm NV | Fri 15:59 | 35.7* / 26.6 / 26.6 |
| NE | ME NH VT MA RI CT NY | **12.0** | Hanover (Hanover Inn), NH | Thu 04:50 | NY Moynihan Train Hall | Thu 16:50 | 12.0 / 12.0 / 12.0 |
| COAST | NJ PA DE MD VA NC SC GA FL | **20.8** | Philadelphia, PA | Thu 09:45 | Jacksonville, FL | Fri 06:32 | 20.8 / 20.8 / 20.8 |
| SOUTH | TN MS AR LA AL TX OK | **24.8** | Marshall (Pony Express Travel Ctr), TX | Thu 07:50 | Sallisaw Best Mart, OK | Fri 08:40 | 24.8 / 24.8 / 24.8 |
| PLAINS | MN WI ND SD NE IA KS MO | **21.1** | Menomonie, WI | Thu 07:45 | Kansas City 47th St Transit Center, KS | Fri 04:50 | 21.1 / 21.1 / 21.1 |
| LAKES | IL IN MI OH KY WV | **16.1** | Huntington Bus Stop, WV | Thu 10:15 | Benton Harbor Bus Stop, MI | Fri 02:20 | 16.1 / 16.1 / 16.1 |

\* W7's forward seed stalled at 35.7 h under the old search, which kicked between the same three or four
orders until `--patience` ran out. With the memoised, exhaustive search (`edbba0a`) the same seed finds 26.6 h
in 3 min. Every other region agrees across all three seeds.

All times are local at the stop. Clocks are the latest start that makes the same finish, so on most of these
the first bus could be any of several days; the table shows the one the search settled on.

## Against the control

`scripts/region_control.py` splits the control (Huntington Thu 01:00, 237.24 h first bus to finish on
the current data) by the moment it first touches each state. Two measures bracket what a region costs it:

- **in-region**: only the gaps between two first touches that are *both* in the region. No entry cost, so it
  is the fair comparison with a region test, which starts inside the region for free. The floor.
- **attributed**: every gap charged to the state collected at its end, so a region also pays for the trip
  into it (MT to ID is charged to W7, CO to KS to PLAINS). The 48 states partition the route this way, with
  38.8 h left over for CO, NM, MT and WY, which no region holds. The ceiling.

| region | region test | control in-region | control attributed | control loses (floor - ceiling) | control's span |
|---|---|---|---|---|---|
| W7 | 26.6 | 39.6 | 49.0 | **13.0 - 22.4** | 106.8 h -> 146.4 h |
| NE | 12.0 | 12.6 | 12.9 | 0.6 - 0.9 | 224.6 h -> 237.2 h |
| COAST | 20.8 | 27.5 | 29.2 | 6.7 - 8.4 | 196.8 h -> 224.3 h |
| SOUTH | 24.8 | 29.0 | 42.7 | 4.2 - 17.9 | interleaved, 26.6 h -> 195.1 h |
| PLAINS | 21.1 | 35.6 | 43.3 | **14.5 - 22.2** | interleaved, 38.5 h -> 166.3 h |
| LAKES | 16.1 | 21.2 | 21.3 | 5.1 - 5.2 | 0.0 h -> 21.2 h |

**The control loses the most time in the West and the Plains, and they are close to a tie.** W7 loses
22.4 h on the attributed measure and PLAINS 22.2; on the in-region floor PLAINS loses 14.5 and W7 13.0.
W7 is one contiguous block (Idaho at 106.8 h to Arizona at 146.4 h), so its in-region figure is clean: the
control spends 39.6 h on states a standalone route does in 26.6. PLAINS is split across the route (MO IA NE
SD ND MN WI by 74.1 h, Kansas at 166.3 h), and the single biggest piece is Wisconsin: 9.9 h from the control's first touch of Minnesota to
its first touch of Wisconsin, against a region route that simply starts at Menomonie.

NE is where the control is already near the regional optimum (0.6 - 0.9 h), which matches HANDOFF: the
Meteor, Acela, Portland and Dartmouth Coach tail has survived every attempt to beat it.

What this does **not** say is that 237.3 h can lose 13 to 22 hours in either region. A region test is free
to start at whatever clock suits it and to end anywhere; the control has to arrive from the previous region
and leave toward the next one, and a once-daily anchor on either side absorbs most local savings (HANDOFF
22, finding 3). The region bests add to 121.4 h against the control's 198.4 h attributed to the same 44
states (237.2 h less 38.8 h for CO NM MT WY), and much of that difference is joins.

## Caveats

- **NE starts with a walk before its first bus.** Vermont is collected by walking from the Hanover Inn to
  the VT line and back, 04:10 to 04:38, before the 04:50 Greyhound. Hours count from the first bus, so that
  walk is free here; from the first step it is 12.7 h.
- **LAKES misses Nick's chain because the data does.** HANDOFF 23 records Huntington 10:15 -> Toledo 16:30,
  TARTA to the Michigan line, Barons BSB 25 18:20 -> Chicago 22:55, WV KY OH MI IN IL in 12 h 40. No Barons
  trip in the feeds runs Toledo 18:20 -> Chicago. The nearest are Cleveland -> Chicago (Toledo 16:35 ->
  Chicago 22:10, which does not enter Michigan) and Detroit -> Cincinnati (Toledo 18:20). Evaluating that
  order on the current data gives 21.9 h via Detroit. If BSB 25 is real it needs an `extra_trips.csv` row
  from its timetable, and LAKES drops to about 12.7 h.
- **South Hammond IN prints in Eastern time.** Lake County, Indiana keeps Central, so a NICTD leg showed
  South Hammond 08:00 -> Hegewisch 07:10. The absolute times are right (it only showed up in the LAKES chain
  evaluation, not in any result above), but `fmt_time` uses the wrong zone for that stop.
- Data: W7 ran on `ac44fcc`; NE onward also had the Greyhound Max Meadows -> Toledo row (`3a2463a`, 63
  more connections). No result above rides it.
- How the states are collected matters for the rule that a bus must stop: Arizona is Beaver Dam on the Salt
  Lake Express (St George -> Las Vegas), Iowa and Nebraska are Sioux City and Omaha on the Jefferson Sioux
  Falls -> Kansas City, Delaware and Maryland are Wilmington and Baltimore on the Northeast Regional, and
  Kentucky is the Ashland stop.

## Leg lists

### W7, 26.6 h

Washington > Arizona > California (Oregon, Idaho, Utah and Nevada in passing)

```
d1 Thu 13:25  Pasco Bus Stop, WA  ->  d2 Fri 02:30  Salt Lake City Intermodal Trans Ctr, UT   [Greyhound: Seattle-Boise-SLC-Denver; La Grande OR, Boise ID]
  local Salt Lake City Intermodal Trans Ctr -> Salt Lake City (Airport)  (6.8 km, from d2 Fri 02:30)
d2 Fri 06:00  Salt Lake City (Airport), UT  ->  d2 Fri 11:30  Saint George (Bluff St Office), UT   [Salt Lake Express: SLC Airport -> St George -> Las Vegas]
d2 Fri 12:40  Saint George (Bluff St Office), UT  ->  d2 Fri 13:50  Las Vegas (Airport), NV   [Salt Lake Express: St George -> Las Vegas; Beaver Dam AZ]
  local Las Vegas (Airport) -> Las Vegas Dean Martin Blue Diamond (702 Shuttles)  (6.0 km, from d2 Fri 13:50)
d2 Fri 15:15  Las Vegas Dean Martin Blue Diamond (702 Shuttles), NV  ->  d2 Fri 15:50  Primm Bus Stop (702 Shuttles), NV   [702 Shuttles: Las Vegas -> Los Angeles]
  walk  Primm Bus Stop (702 Shuttles) -> CA state line  (0.6 km, from d2 Fri 15:50)
```

### NE, 12.0 h

New Hampshire > Vermont > Maine > Rhode Island > New York (Massachusetts and Connecticut in passing)

```
  walk  Hanover (Hanover Inn) -> VT state line  (0.9 km, from d1 Thu 04:10)
  walk  VT state line -> Hanover (Hanover Inn)  (0.9 km, from d1 Thu 04:24)
d1 Thu 04:50  Hanover (Hanover Inn), NH  ->  d1 Thu 07:35  Boston (South Station), MA   [Greyhound: Boston - Burlington - Montreal]
  walk  Boston (South Station) -> Boston South Station  (0.1 km, from d1 Thu 07:35)
d1 Thu 08:00  Boston South Station, MA  ->  d1 Thu 09:55  Portland, ME   [Concord Coach Lines]
d1 Thu 10:30  Portland, ME  ->  d1 Thu 12:25  Boston South Station, MA   [Concord Coach Lines]
  walk  Boston South Station -> Boston  (0.3 km, from d1 Thu 12:25)
d1 Thu 13:00  Boston, MA  ->  d1 Thu 16:50  NY Moynihan Train Hall at Penn Station, NY   [Amtrak: Acela; Providence RI, New Haven CT]
```

### COAST, 20.8 h

Pennsylvania > New Jersey > Florida (DE MD VA NC SC GA in passing)

```
d1 Thu 09:45  Philadelphia, PA  ->  d1 Thu 10:11  Trenton, NJ   [Amtrak: Keystone Service]
d1 Thu 10:22  Trenton, NJ  ->  d1 Thu 12:58  Washington Union Station, DC   [Amtrak: Northeast Regional; Wilmington DE, Baltimore MD]
d1 Thu 13:48  Washington Union Station, DC  ->  d2 Fri 06:32  Jacksonville, FL   [Amtrak: Floridian; Alexandria VA, Raleigh NC, Columbia SC, Savannah GA]
```

### SOUTH, 24.8 h

Texas > Alabama > Oklahoma (LA MS TN AR in passing)

```
d1 Thu 07:50  Marshall (Pony Express Travel Ctr), TX  ->  d1 Thu 18:50  Birmingham Intermodal Facility, AL   [Greyhound: Atlanta - Birmingham - Dallas; Shreveport LA, Jackson MS]
d1 Thu 19:00  Birmingham Intermodal Facility, AL  ->  d1 Thu 23:35  Memphis Bus Station, TN   [Greyhound: Atlanta - Memphis]
d2 Fri 02:10  Memphis Bus Station, TN  ->  d2 Fri 08:40  Sallisaw Best Mart, OK   [Greyhound: Oklahoma City - Memphis; Forrest City AR, Little Rock AR]
```

### PLAINS, 21.1 h

Wisconsin > North Dakota > Kansas (MN SD IA NE MO in passing)

```
d1 Thu 07:45  Menomonie, WI  ->  d1 Thu 08:45  Saint Paul Union Depot, MN   [Greyhound: Chicago - Milwaukee - Minneapolis]
  walk  Saint Paul Union Depot -> St. Paul (Union Depot)  (0.0 km, from d1 Thu 08:45)
d1 Thu 09:00  St. Paul (Union Depot), MN  ->  d1 Thu 09:25  Minneapolis, MN   [Jefferson Lines: Kansas City -> Minneapolis]
d1 Thu 10:35  Minneapolis, MN  ->  d1 Thu 14:55  Fargo, ND   [Jefferson Lines: Minneapolis -> Billings]
d1 Thu 15:50  Fargo, ND  ->  d1 Thu 19:50  Sioux Falls, SD   [Jefferson Lines: Fargo -> Sioux Falls]
d1 Thu 20:05  Sioux Falls, SD  ->  d2 Fri 04:15  Kansas City, MO   [Jefferson Lines: Sioux Falls -> Kansas City; Sioux City IA, Omaha NE]
  walk  Kansas City -> Kansas City Bus Station  (0.0 km, from d2 Fri 04:15)
d2 Fri 04:35  Kansas City Bus Station, MO  ->  d2 Fri 04:50  Kansas City 47th St Transit Center, KS   [Greyhound: St Louis - Denver]
```

### LAKES, 16.1 h

West Virginia > Kentucky > Illinois > Michigan (OH IN in passing)

```
d1 Thu 10:15  Huntington Bus Stop, WV  ->  d1 Thu 12:55  Columbus (E Mound St), OH   [Greyhound: Detroit - Columbus - Charlotte; Ashland KY]
d1 Thu 14:55  Columbus (E Mound St), OH  ->  d1 Thu 21:35  Chicago, IL   [Barons: Columbus -> Chicago; Fort Wayne IN, South Bend IN]
  walk  Chicago -> Chicago Bus Station  (0.0 km, from d1 Thu 21:35)
d1 Thu 23:35  Chicago Bus Station, IL  ->  d2 Fri 02:20  Benton Harbor Bus Stop, MI   [Greyhound: Chicago - Kalamazoo - Detroit]
```

## Run time

W7, NE, COAST and SOUTH ran on the old search: each seed used its full 900 s budget or stopped on
`--patience`, about 15 min a region. W7 also rebuilt the router from GTFS in every run; from `ee2a07f` (NE
on) runs load the cached router in about 2 s. PLAINS and LAKES ran on `edbba0a`
(cached router, memoised scoring, idle-kick stop, exhaustive enumeration up to 7 states): PLAINS took about
1 min for all three seeds, stopping on exhaustion after 840 to 947 distinct orders; LAKES enumerated all 720
orders in 31 s and then ran to `--patience` on gateway moves that never improved. Logs and pickles are in
`out/regions/` (gitignored).

## Follow-ups (Oct 1 evening)

**Barons BSB 25 added** (`extra_trips.csv`, from Nick's screenshot): Toledo (Amtrak) 18:20 -> Angola, Lagrange,
Shipshewana, Elkhart, South Bend -> Merrillville, Gary -> Chicago 22:55 Central. LAKES rerun: still **16.1 h**,
same route. The 12 h 40 chain fails at TARTA, not Barons: route 26 (Miracle Mile via Lewis) leaves downtown
at 16:30, the minute the Greyhound arrives, and the 17:30 reaches Alexis & Lewis at 17:54; the next run back
reaches downtown 19:15. Even the 16:30 would not do it: Alexis & Lewis 16:54, about 2.5 km to the Michigan
line and back, and the return passes at 17:19. It misses by about five minutes before any transfer slack.

**Four Corners.** Nick's friend proposed collecting AZ UT CO NM around the Four Corners using the
Albuquerque - Durango Greyhound and Navajo Transit (`data/more_gtfs/navajo.zip`, NTS GTFS feed_version
20260313). Region test on the four states, all 24 orders enumerated:

| | hours | route |
|---|---|---|
| without NTS | **22.8** | St George -> Las Vegas -> Flagstaff -> Albuquerque -> Trinidad CO |
| with NTS | **22.8** | identical; NTS is never used |
| forced: Durango bus, then NTS Gallup -> Window Rock | 44.7 | |
| forced: Durango bus, then NTS via Shiprock | 68.7 | |
| forced: Trinidad, Albuquerque, NTS Window Rock, Chief, Las Vegas, St George | 33.8 | |

Why it cannot work on this network: no scheduled service reaches the monument (NTS's nearest stops are
Shiprock, 30 km, and Round Rock), NTS never enters Utah or Colorado, its Route 18 (Shiprock - Farmington,
the only link to the Durango bus) has a calendar that ended 2026-03-12, and every route is weekday-only.

Utah via Page (Express brochure, Route F to Wahweap Housing on Stateline Dr.) needs NTS Route 1 Tuba City -
Ft. Defiance (PDF revised 08/27/2026, Monday - Thursday, one round trip, not in the GTFS) and Express Route B
Page - Tuba City (Tuba City -> Page only at 7:00 AM). Window Rock 15:15 -> Tuba City 19:04, overnight, Page
8:27, Wahweap 13:33 and back, Route B 15:27 to Tuba City, overnight, Route 1 6:00 -> Window Rock 9:37: about
42 h for Utah alone, against 22.8 h for all four states via St George. Not entered as data, since the
arithmetic is exact and the stops would need coordinates nobody has checked.

Still open: **Bustang Outrider Grand Junction - Durango**, which with the Durango - Farmington - Albuquerque
Greyhound would link the Zephyr / Bustang West at Grand Junction to New Mexico without Denver. Needs its
timetable.

Display bugs seen (absolute times correct, only `fmt_time` shows the wrong zone): South Hammond IN prints
Eastern (Lake County is Central); Navajo Nation stops in Arizona print Arizona time (the Nation keeps
Mountain daylight time).
