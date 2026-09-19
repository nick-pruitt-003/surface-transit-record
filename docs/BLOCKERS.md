# Main blockers (Sep 19 2026)

Generated from the loaded timetables by `scripts/frequency_report.py` (full output: `out/frequency_report.txt`).
"/day" = direct departures per day averaged over two weeks; below 1.0 means the service skips days.

## The 237 route's chain of sparse links (in route order)

Every link here runs at most about twice a day. Missing one costs a day unless a later one also works.

| # | Link | Departs | Per day | Note |
|---|------|---------|---------|------|
| 1 | Barons Columbus → Detroit | Thu 6:50 AM | 2 | first fixed departure; Huntington 1:00 AM Barons feeds it (237.2 h) |
| 2 | Greyhound Detroit → Indianapolis | Thu 1:50 PM | 2 | |
| 3 | Greyhound Indianapolis → Effingham | Thu 7:35 PM | 2 | |
| 4 | City of New Orleans Effingham → Memphis | Thu 10:01 PM | 1 | |
| 5 | Jefferson Memphis → Conway → Kansas City | Fri 8:30 AM | **0.6** | **Wed–Sat only** |
| 6 | Jefferson Kansas City → Sioux Falls | Sat 1:30 AM | 1 | |
| 7 | Jefferson Sioux Falls → Fargo | Sat 10:30 AM | **0.7** | **Mon, Thu–Sun only** |
| 8 | Jefferson Fargo → Minneapolis | Sat 3:55 PM | 2 | then the Eau Claire overnight loop (5/day, free) |
| 9 | Jefferson Minneapolis → Sioux Falls → Billings | Sun 6:45 AM | 1 via Sioux Falls | ND+MN+WI loop costs this day (see HANDOFF) |
| 10 | Jefferson Billings → Spokane | Mon 1:30 AM | 1 | |
| 11 | Greyhound Pasco → Salt Lake City | Mon 1:25 PM | 1 | |
| 12 | Southwest Chief Barstow → Newton | Tue 8:47 PM | 1 | Vegas → Barstow is slack before it |
| 13 | BeeLine Newton → Oklahoma City | Thu 3:00 AM | 1 | tied to the Chief |
| 14 | AE Houston → Tallahassee (or Greyhound 6:35 PM) | Thu 7:30 PM | 1 each | eastbound Houston departure is the Gulf anchor |
| 15 | Silver Meteor Jacksonville → DC | Fri 4:11 PM | 2 | DC 6:25 AM → 6:40 Acela is the tightest connection |

Frequent (not blockers): OKC → Dallas (5/day), Dallas → Houston (5+/day), Vegas → Barstow (5/day), St George → Vegas (11/day), everything in the Northeast (Acela 19/day, Concord Coach 16/day, Dartmouth Coach 14/day).

## Once-a-day corridors across the network (direct service)

| Corridor | Per day | Carrier |
|----------|---------|---------|
| Cheyenne ↔ Billings | 0.1 (weekly) | Express Arrow |
| Sioux Falls ↔ Fargo | 0.7 | Jefferson |
| Dallas ↔ Shreveport / New Orleans | 0.7 | Greyhound |
| Houston ↔ Dallas ↔ OKC (FlixBus through service) | 0.7 | FlixBus |
| Sioux Falls ↔ Omaha ↔ Kansas City | 1 | Jefferson |
| Sioux Falls ↔ Rapid City ↔ Billings | 1 | Jefferson |
| Fargo ↔ Billings (I-94) | 1 | Jefferson |
| Spokane ↔ Billings | 1 | Jefferson |
| Pasco ↔ Boise ↔ Salt Lake City | 1 | Greyhound |
| Salt Lake City ↔ Cheyenne | 1 | Greyhound |
| Tallahassee ↔ Birmingham ↔ Nashville | 1 | Greyhound |
| Las Vegas NV → Phoenix → El Paso | 1 | AE |
| Southwest Chief, City of New Orleans, Empire Builder, Texas Eagle | 1 each | Amtrak |
| Cardinal | 0.4 (3/week) | Amtrak |
| Denver ↔ Cheyenne | 3 (per Nick; Groome DEN airport ↔ Cheyenne 8/day is also loaded) | |

## Takeaways

1. The 237 route is a chain of about ten once-a-day links from Effingham to Oklahoma City. A gain has to move the whole chain a day earlier, or shorten the ends (start before Columbus 6:50 AM, end after the Meteor).
2. Two links in the chain are **not daily**: Jefferson Memphis → Kansas City runs Wed–Sat, and Sioux Falls → Fargo runs Mon and Thu–Sun (GTFS calendars). With Memphis on day 2 and Sioux Falls on day 3, only Tue, Wed, Thu or Fri starts satisfy both; the Thursday start does. Other day limits (Big River Crossing hours, weekday-only local transit) still apply on top.
3. The northern Plains are the thinnest part of the map: every link from Sioux Falls, Fargo, Billings and Spokane is once a day.
