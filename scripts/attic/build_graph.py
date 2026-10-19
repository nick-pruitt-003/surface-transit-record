"""Build the routing graph from one or more layers.

usage: python3 build_graph.py --out graph2 --layers intercity
       python3 build_graph.py --out graph4 --layers intercity,amtrak
       python3 build_graph.py --out graph3 --layers intercity,local
"""
import argparse, csv, io, json, zipfile
from collections import defaultdict
import shapely
from common import (GraphBuilder, StateIndex, contract, data_path, save_graph, DATA_DIR)

LOCAL_WEIGHT = 4.0          # local buses are ~4x slower per km than intercity
BUS_GC_SPEED = 75.0         # great-circle km/h a coach achieves; rail weights scale against it


def layer_intercity(gb):
    stops = json.load(open(data_path('NTAD_Intercity_Bus_Atlas_Stops_*.geojson')))['features']
    for s in stops:
        lon, lat = s['geometry']['coordinates']; p = s['properties']
        gb.add_stop(p['stop_name'], p['state_usps'], p['carrier_name'], lon, lat)
    routes = json.load(open(data_path('NTAD_Intercity_Bus_Atlas_Routes_*.geojson')))['features']
    for f in routes:
        p = f['properties']
        ri = gb.add_route(p['carrier_name'], p['route_short_name'], p['route_long_name'])
        g = f['geometry']
        lines = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
        for line in lines:
            gb.add_shape(ri, ((c[0], c[1]) for c in line))


def layer_amtrak(gb, states):
    """Amtrak rail from the GTFS zip. Each train is weighted by 75 km/h over its
    measured great-circle average speed (see prep_amtrak_speeds.py)."""
    z = zipfile.ZipFile(data_path('amtrak_gtfs.zip'))
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))
    for st in rd('stops.txt'):
        lon, lat = float(st['stop_lon']), float(st['stop_lat'])
        gb.add_stop(st['stop_name'], states.abbr_of_point(lon, lat), 'Amtrak', lon, lat)
    speeds = json.load(open(data_path('route_speeds.json')))
    rt = {r['route_id']: r for r in rd('routes.txt')}
    shape_route = {}
    for t in rd('trips.txt'):
        if rt[t['route_id']]['route_type'] == '2':
            shape_route.setdefault(t['shape_id'], t['route_id'])
    shp = defaultdict(list)
    for r in rd('shapes.txt'):
        if r['shape_id'] in shape_route:
            shp[r['shape_id']].append((int(r['shape_pt_sequence']), float(r['shape_pt_lon']), float(r['shape_pt_lat'])))
    for sid, pts in shp.items():
        pts.sort()
        name = rt[shape_route[sid]]['route_long_name']
        w = min(1.6, max(0.7, BUS_GC_SPEED / speeds.get(name, 65.0)))
        ri = gb.add_route('Amtrak', '', name)
        gb.add_shape(ri, ((lon, lat) for _, lon, lat in pts), weight=w)


def layer_local(gb):
    """Local transit routes selected by prep_local.py (local_kept.pkl)."""
    import os, pickle
    with open(os.path.join(DATA_DIR, 'local_kept.pkl'), 'rb') as f:
        kept = pickle.load(f)
    for k in kept:
        ri = gb.add_route('LOCAL ' + str(k['agency']), k['short'], k['long'])
        g = k['geom']
        parts = [g] if g.geom_type == 'LineString' else list(g.geoms)
        for part in parts:
            gb.add_shape(ri, part.coords, weight=LOCAL_WEIGHT, cell_hubs=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True, help='basename, writes <out>.pkl and c<out>.pkl')
    ap.add_argument('--layers', default='intercity', help='comma list of intercity,amtrak,local')
    a = ap.parse_args()
    layers = [x.strip() for x in a.layers.split(',') if x.strip()]
    bad = set(layers) - {'intercity', 'amtrak', 'local'}
    if bad:
        ap.error(f'unknown layer(s): {", ".join(sorted(bad))}')
    states = StateIndex(); gb = GraphBuilder()
    if 'intercity' in layers:
        layer_intercity(gb)
    if 'amtrak' in layers:
        layer_amtrak(gb, states)
    if 'local' in layers:
        layer_local(gb)
    print('walk links', gb.link_nearby_stops())
    graph = gb.finish(states)
    print('nodes', len(graph['node_xy']), 'edges', len(graph['edges']), 'routes', len(graph['routes']), 'stops', len(graph['stops']))
    cedges = contract(graph)
    print('contracted edges', len(cedges))
    save_graph(graph, cedges, a.out)


if __name__ == '__main__':
    main()
