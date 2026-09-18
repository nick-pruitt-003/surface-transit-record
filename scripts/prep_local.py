import sqlite3, json, pickle, numpy as np, shapely, struct
from collections import defaultdict
from shapely.strtree import STRtree
from shapely.geometry import shape
GRID=0.01
def cell(lon,lat): return (round(lon/GRID),round(lat/GRID))
stops=json.load(open('/Users/nick_pruitt/Downloads/NTAD_Intercity_Bus_Atlas_Stops_-6979428015416139090.geojson'))['features']
cell_stops=defaultdict(set)
for si,s in enumerate(stops):
    lon,lat=s['geometry']['coordinates']; cx,cy=cell(lon,lat)
    for dx in (-1,0,1):
        for dy in (-1,0,1): cell_stops[(cx+dx,cy+dy)].add(si)
sj=json.load(open('states.geojson')); skip={'Alaska','Hawaii','Puerto Rico','District of Columbia'}
polys=[shape(f['geometry']) for f in sj['features'] if f['properties']['name'] not in skip]
names=[f['properties']['name'] for f in sj['features'] if f['properties']['name'] not in skip]
tree=STRtree(polys)
c=sqlite3.connect('/Users/nick_pruitt/Downloads/NTAD_National_Transit_Map_Routes_-3744149803598222330.gpkg')
def gpkb(b):
    flags=b[3]; env=(flags>>1)&7; hl=8+{0:0,1:32,2:48,3:48,4:64}[env]
    return shapely.from_wkb(b[hl:])
kept=[]; n=0; nb=0
for row in c.execute('select OBJECTID,SHAPE,ntd_id,agency_id,route_short_name,route_long_name,route_type from National_Transit_Map_Routes where route_type=\'3\''):
    n+=1
    try: g=gpkb(row[1])
    except Exception as e: nb+=1; continue
    g=shapely.simplify(g,0.002)
    coords=shapely.get_coordinates(g)
    if len(coords)<2: continue
    cells=set(cell(x,y) for x,y in coords)
    near=set()
    for ce in cells: near|=cell_stops.get(ce,set())
    # states touched: sample coords
    samp=coords[::max(1,len(coords)//20)]
    st=set(tree.query(shapely.points(samp[:,0],samp[:,1]),predicate='within')[1].tolist())
    if len(near)>=2 or len(st)>=2:
        kept.append(dict(oid=row[0],agency=row[3],short=row[4],long=row[5],ntd=row[2],geom=g,near=near,states=st))
    if n%5000==0: print(n,len(kept),flush=True)
print('bus routes',n,'bad',nb,'kept',len(kept))
pickle.dump(kept,open('local_kept.pkl','wb'))
