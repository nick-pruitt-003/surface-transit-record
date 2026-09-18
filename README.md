# bus48 — shortest scheduled-surface route through the 48 contiguous states

Distance-based first pass, "perfect connections" assumption. Produces a leg-by-leg
itinerary (txt / csv / xlsx / geojson) that you then check against real timetables.

## Rules encoded
- A state counts only where you can **get off at a listed stop** (bus atlas stop or
  Amtrak station). Riding through does not count.
- Transfers, and reversing direction, only at a stop. Each transfer costs 10 km-equivalent.
- Bus legs are weighted by road km. Amtrak legs are weighted by road-equivalent km using
  each train's measured average speed from the GTFS (`data/route_speeds.json`).
- Local transit (optional layer) is weighted 4x.

## Inputs (put in `data/`, or edit the absolute paths at the top of the build scripts)
- `NTAD_Intercity_Bus_Atlas_Routes_*.geojson` and `NTAD_Intercity_Bus_Atlas_Stops_*.geojson`
  from data.bts.gov (NTAD Intercity Bus Atlas).
- `NTAD_National_Transit_Map_Routes_*.gpkg` (optional, local transit layer).
- `amtrak_gtfs.zip` from https://content.amtrak.com/content/gtfs/GTFS.zip (included).
- `states.geojson` (included).

## Pipeline
```
pip install shapely networkx scipy numpy openpyxl
cd scripts
python3 build2.py                 # intercity bus graph  -> graph2.pkl / cgraph2.pkl
python3 prep_local.py && python3 build3.py   # + local transit -> graph3 (optional)
unzip -d amtrak ../data/amtrak_gtfs.zip && python3 build4.py   # + Amtrak -> graph4
python3 solve3.py 1200 [seed.pkl]                 # bus only        -> result2.pkl
python3 solve4.py 2400 result2.pkl                # bus + local     -> result3.pkl
python3 solve5.py 2400 result2.pkl                # bus + Amtrak    -> result4.pkl
python3 solve6.py 1500 result2.pkl "Montana,Washington,Oregon,Utah,Nevada,Arizona,New Mexico,Texas"
                                                   # bus + Amtrak with a locked state prefix -> result6.pkl
python3 report2.py result4.pkl out.txt graph4.pkl  # itinerary txt/csv/geojson
python3 xlsx.py out.csv out.xlsx "title"           # spreadsheet template
```
First arg to the solvers is the local-search budget in seconds.

## How the solver works
1. Snap every route shape to a 0.01° grid; nodes are (route, cell); edges follow the shape.
2. Stops become hub nodes; a route cell within ~1.5 km of a stop links to it (transfer point).
3. Contract degree-2 chains so shortest paths are fast.
4. State order = open-path TSP over per-state hub distances, then exact evaluation by
   layered Dijkstra (each layer must reach a stop-adjacent node in the next state).
5. Local search (or-opt + 2-opt on the state order) on the exact cost, dropping states
   that get covered incidentally, re-inserting any that get lost.
6. `report2.py` relabels the node path into the fewest bus legs, splitting at turnarounds.

## Known gaps
- Carriers not in the NTAD atlas (Tufesa, Turimex, El Expreso, Omnibus…) are invisible.
- No timetables yet; Amtrak GTFS `stop_times.txt` is in the zip for a later time-aware pass.
- Route names are grouped by carrier + sorted endpoint names, so "A -> B" and "B -> A" merge.
