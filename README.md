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
pip install shapely scipy numpy openpyxl
cd scripts
python3 prep_amtrak_speeds.py                       # -> data/route_speeds.json (from the GTFS timetable)
python3 build_graph.py --out graph2 --layers intercity
python3 build_graph.py --out graph4 --layers intercity,amtrak
python3 prep_local.py && python3 build_graph.py --out graph3 --layers intercity,local   # optional
python3 solve.py --graph graph2 --budget 1200 --out result2.pkl
python3 solve.py --graph graph4 --budget 2400 --seed result2.pkl --out result4.pkl
python3 solve.py --graph graph4 --budget 1500 --seed result2.pkl --out result7.pkl \
    --prefix "Montana,Washington,Oregon,Utah,Nevada,California,@Tucson,New Mexico,@El Paso,Texas"
python3 report.py result4.pkl out.txt graph4.pkl   # itinerary txt/csv/geojson
python3 xlsx.py out.csv out.xlsx "title"           # spreadsheet template
```
`--prefix` locks the first entries of the state order; `@Name` is a named stop target.
Data files are found by glob in `data/` (override with `BUS48_DATA=/path`).

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
