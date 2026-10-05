# Jefferson Lines legs to confirm on jeffersonlines.com

The Jefferson GTFS behind our intercity feed is the June 2024 - June 2025 export (Saucon, version 31660), and four of its
trips have been 20-80 min off the current site. Every leg below marked **check** still comes from that export; legs marked
**confirmed** were entered from Nick's booking screenshots (Oct 2026). Times are local; weekday as in each route's plan.

## Control (237.24, valid)

| leg | depart | from | arrive | to | status |
|---|---|---|---|---|---|
| 1 | d2 Fri 08:30 | Memphis (MATA Airways Transit Center) | d2 Fri 11:10 | Conway | **check** (Memphis -> Tulsa) |
| 2 | d2 Fri 11:20 | Conway | d2 Fri 19:25 | Kansas City | **check** (Pine Bluff -> Kansas City) |
| 3 | d2 Fri 19:45 | Kansas City | d2 Fri 22:45 | Des Moines | **check** (Tulsa -> Minneapolis) |
| 4 | d3 Sat 06:15 | Omaha | d3 Sat 09:45 | Sioux Falls | confirmed (JL Omaha 06:15 -> Sioux City -> Vermilli) |
| 5 | d3 Sat 10:00 | Sioux Falls | d3 Sat 14:05 | Fargo | confirmed (JL Sioux Falls 10:00 -> Brookings -> Wat) |
| 6 | d3 Sat 15:55 | Fargo | d3 Sat 20:20 | Minneapolis | **check** (Billings -> Minneapolis) |
| 7 | d4 Sun 06:45 | Minneapolis | d5 Mon 00:25 | Billings | **check** (Minneapolis -> Billings) |
| 8 | d5 Mon 01:30 | Billings | d5 Mon 10:30 | Spokane | **check** (Billings -> Spokane) |

## Wheeling (234.24, valid, Ohio Coach)

| leg | depart | from | arrive | to | status |
|---|---|---|---|---|---|
| 1 | d2 Fri 08:30 | Memphis (MATA Airways Transit Center) | d2 Fri 11:10 | Conway | **check** (Memphis -> Tulsa) |
| 2 | d2 Fri 11:20 | Conway | d2 Fri 19:25 | Kansas City | **check** (Pine Bluff -> Kansas City) |
| 3 | d2 Fri 19:45 | Kansas City | d2 Fri 22:45 | Des Moines | **check** (Tulsa -> Minneapolis) |
| 4 | d3 Sat 06:15 | Omaha | d3 Sat 09:45 | Sioux Falls | confirmed (JL Omaha 06:15 -> Sioux City -> Vermilli) |
| 5 | d3 Sat 10:00 | Sioux Falls | d3 Sat 14:05 | Fargo | confirmed (JL Sioux Falls 10:00 -> Brookings -> Wat) |
| 6 | d3 Sat 15:55 | Fargo | d3 Sat 20:20 | Minneapolis | **check** (Billings -> Minneapolis) |
| 7 | d4 Sun 06:45 | Minneapolis | d5 Mon 00:25 | Billings | **check** (Minneapolis -> Billings) |
| 8 | d5 Mon 01:30 | Billings | d5 Mon 10:30 | Spokane | **check** (Billings -> Spokane) |

## HT plan (Plains block pending re-search)

| leg | depart | from | arrive | to | status |
|---|---|---|---|---|---|
| 1 | d9 Fri 06:15 | Omaha | d9 Fri 09:45 | Sioux Falls | confirmed (JL Omaha 06:15 -> Sioux City -> Vermilli) |
| 2 | d9 Fri 10:00 | Sioux Falls | d9 Fri 14:05 | Fargo | confirmed (JL Sioux Falls 10:00 -> Brookings -> Wat) |
| 3 | d9 Fri 14:30 | Fargo | d9 Fri 18:25 | Sioux Falls | confirmed (JL Fargo 14:30 -> Sisseton Jct -> Summit) |
| 4 | d9 Fri 20:05 | Sioux Falls | d10 Sat 02:15 | Maryville | **check** (Sioux Falls -> Kansas City) |
| 5 | d10 Sat 03:25 | Maryville | d10 Sat 05:40 | Omaha | **check** (Kansas City -> Sioux Falls) |
| 6 | d10 Sat 06:15 | Omaha | d10 Sat 09:45 | Sioux Falls | confirmed (JL Omaha 06:15 -> Sioux City -> Vermilli) |
| 7 | d10 Sat 10:25 | Sioux Falls | d10 Sat 10:55 | Luverne | confirmed (JL Sioux Falls 10:25 -> Luverne MN 10:55) |
| 8 | d10 Sat 11:05 | Luverne | d10 Sat 14:20 | Willmar | **check** (Sioux Falls -> Minneapolis-St Paul (Airp) |
| 9 | d10 Sat 15:10 | Willmar | d10 Sat 19:00 | Sioux Falls | **check** (Minneapolis-St Paul (Airport - MSP) -> S) |
| 10 | d10 Sat 19:10 | Sioux Falls | d11 Sun 00:00 | Minneapolis | **check** (Billings -> Minneapolis) |
| 11 | d11 Sun 06:45 | Minneapolis | d12 Mon 00:25 | Billings | **check** (Minneapolis -> Billings) |
| 12 | d12 Mon 01:30 | Billings | d12 Mon 10:30 | Spokane | **check** (Billings -> Spokane) |

## Already corrected from the site (in data/manual/jefferson_lines.toml)

Fargo -> Sioux Falls 14:30 (feed 15:50, dropped); Sioux Falls -> Fargo 10:00 (feed 10:30, dropped); Maryville ->
Sioux Falls 09:45 and Omaha -> Sioux Falls 09:45 (feed 10:05); Sioux Falls -> Luverne 10:25 (feed 10:30); Chicago
21:15 -> Omaha (missing from the feed); JL 938 Bismarck 13:05 -> Minneapolis 21:10 and JL 805 Minneapolis 21:45 ->
Des Moines -> Kansas City; Des Moines -> Omaha 03:45 (inferred); Vivian -> Pierre 15:40.
