# bus48 supplement: hand-collected schedules for a 48-state bus route

This is the schedule data I collected by hand while planning a scheduled-surface route through all 48 contiguous
US states (the timetabled record is 238.83 h). The public GTFS feeds don't have all of it: some carriers publish
no feed at all, some feeds disagree with the carrier's own booking site, and some feeds put stops in the wrong place.
It's published so anyone can check the routes, and so the next person attempting this doesn't have to collect it again.

It **supplements** the public feeds; it doesn't replace them. Load it next to Amtrak's GTFS, the FlixBus/Greyhound
feed, the intercity feed (`intercity_merged_gtfs.zip`), and the city transit feeds listed in `city_routes.csv`.

Timetables are for **November 2026**. Bus schedules change, so check any leg you depend on against the carrier's
booking page before you travel. The carrier's site is treated as ground truth throughout.

## What's here

| file | what it is |
|---|---|
| `gtfs/` (also `../bus48_supplement_gtfs.zip`) | A GTFS feed of every hand-entered trip: Tornado Bus (rebuilt from its booking API: departure plus cumulative drive and dwell times), Jefferson Lines corrections, Vonlane, RedCoach, Salt Lake Express, Omnibus Express, the Four Winds casino shuttle, TCATA and ETrax (built from PDF timetables), and others. |
| `walks.csv` | Measured walks between stops: Google walking time and distance, usually confirmed against the map. Most join a carrier's stop to a nearby station or city bus, or cross a state line on foot (Dubuque to the Wisconsin line, Fargo to Moorhead, Sioux City to the South Dakota line on the Military Rd bridge). |
| `timed_walks.csv` | Walks over paths that have opening hours, so they're modelled as timed departures: the Big River Crossing between Memphis and Arkansas (open 06:00 to 22:00), and the timed Ledyard Bridge run in Hanover. |
| `corrections/drop_trips.csv` | Public-feed trips that the carrier's own site contradicts, why, and the hand-entered trip that replaces each one. |
| `corrections/stop_points.csv` | Public-feed stops placed in the wrong spot, with the measured point and its source. |
| `city_routes.csv` | The city transit feeds used, and which routes of each, chosen to link intercity stops to each other. |

## Reading the GTFS

- `trips.txt` has two extra columns. `source_file` is the file in the bus48 repo the trip came from (`data/manual/*.toml`),
  and `source_note` says where the trip came from: carrier site, screenshot, booking API, PDF timetable, and the date it was checked.
- A stop that also exists in a public feed keeps that feed's ID: `ibus:` (intercity_merged_gtfs), `flix:`, `amtrak:`,
  or `<city feed>:`. That way the trips connect to the public feeds without guessing. A stop that exists only here
  has an ID starting `extra:`, followed by its name.
- `stops.txt` adds a `location_note` column wherever a public feed's point was corrected.
- Times are written in each trip's agency time zone. Where a carrier runs in more than one zone, its agency is split
  by zone (for example "Tornado Bus (America/Chicago)").
- `transfers.txt` holds the measured walks as minimum transfer times (`transfer_type` 2).
- The calendar is each trip's weekday pattern, valid November 1 to December 31, 2026.

## Rules the routes were planned under

Scheduled public services only: no taxis, rideshare or private cars. Walking is allowed, including across state
lines. Transfers need at least 5 minutes. A state counts once the route is in it, by ride or on foot.

## Caveats

- Days marked "daily assumed" in a `source_note` weren't confirmed for every weekday.
- A few services can't be timetabled exactly and are entered as they run: ETrax in Effingham IL is a deviated
  route, and UCAP in Rock County MN is booked dial-a-ride.
- Tornado Bus's own site shows some times in the wrong time zone. The trips here were rebuilt from the booking API's
  drive times, and the stop points were checked against addresses and maps.

Built by `scripts/export_gtfs.py` in the bus48 repo, from the router's own loader, so these are exactly the times
the route search used.
