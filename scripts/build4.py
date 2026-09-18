import json, numpy as np, pickle, math, shapely
from collections import defaultdict
from shapely.strtree import STRtree
from shapely.geometry import shape
GRID=0.01
src='/Users/nick_pruitt/Downloads/NTAD_Intercity_Bus_Atlas_Routes_3794487008466975906.geojson'
stops=json.load(open('/Users/nick_pruitt/Downloads/NTAD_Intercity_Bus_Atlas_Stops_-6979428015416139090.geojson'))['features']
d=json.load(open(src))
def cell(lon,lat): return (round(lon/GRID),round(lat/GRID))
def hav(a,b):
    lon1,lat1=a; lon2,lat2=b; p=math.pi/180
    x=(math.sin((lat2-lat1)*p/2)**2+math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2*6371*math.asin(math.sqrt(x))
# stop cells -> stop ids (3x3 patch)
import csv
sj0=json.load(open('states.geojson')); skip0={'Alaska','Hawaii','Puerto Rico','District of Columbia'}
ab={'Alabama':'AL','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT','Delaware':'DE','Florida':'FL','Georgia':'GA','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT','Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY'}
polys0=[shape(f['geometry']) for f in sj0['features'] if f['properties']['name'] not in skip0]
names0=[f['properties']['name'] for f in sj0['features'] if f['properties']['name'] not in skip0]
tree0=STRtree(polys0)
amk_stops=list(csv.DictReader(open('amtrak/stops.txt')))
for st in amk_stops:
    lon,lat=float(st['stop_lon']),float(st['stop_lat'])
    q=tree0.query(shapely.points([lon],[lat]),predicate='within')
    sname=ab[names0[q[1][0]]] if len(q[1]) else None
    stops.append({'geometry':{'coordinates':[lon,lat]},'properties':{'stop_name':st['stop_name'],'state_usps':sname,'carrier_name':'Amtrak'}})
cell_stops=defaultdict(set); stop_info=[]
for si,s in enumerate(stops):
    lon,lat=s['geometry']['coordinates']; p=s['properties']
    stop_info.append((p['stop_name'],p['state_usps'],p['carrier_name'],lon,lat))
    cx,cy=cell(lon,lat)
    for dx in (-1,0,1):
        for dy in (-1,0,1): cell_stops[(cx+dx,cy+dy)].add(si)
# nodes
node_key={}; node_xy=[]; node_kind=[]  # kind: ('r',route,cell) or ('s',stop)
def nid(key,xy):
    i=node_key.get(key)
    if i is None:
        i=len(node_xy); node_key[key]=i; node_xy.append(xy)
    return i
edges={}; routes=[]
def add(a,b,w,ri):
    if a==b: return
    k=(a,b) if a<b else (b,a)
    e=edges.get(k)
    if e is None: edges[k]=[w,{ri}]
    else: e[1].add(ri); e[0]=min(e[0],w)
for si,(n,st,c,lon,lat) in enumerate(stop_info): nid(('s',si),(lon,lat))
for ri,f in enumerate(d['features']):
    p=f['properties']; routes.append((p['carrier_name'],p['route_short_name'],p['route_long_name']))
    g=f['geometry']; lines=[g['coordinates']] if g['type']=='LineString' else g['coordinates']
    for line in lines:
        prev=None; lastst=set()
        for c in line:
            ce=cell(c[0],c[1]); i=nid(('r',ri,ce),(ce[0]*GRID,ce[1]*GRID))
            if prev is not None and prev!=i: add(prev,i,hav(node_xy[prev],node_xy[i]),ri)
            if prev!=i:
                cur=cell_stops.get(ce,set())
                for si in cur-lastst: add(i,node_key[('s',si)],5.0,-1)
                lastst=cur
            prev=i

spd=json.load(open('amtrak/route_speeds.json'))
def railw(name): return min(1.6,max(0.7,75.0/spd.get(name,65.0)))
rt={r['route_id']:r for r in csv.DictReader(open('amtrak/routes.txt'))}
shape_route={}
for t in csv.DictReader(open('amtrak/trips.txt')):
    if rt[t['route_id']]['route_type']=='2': shape_route.setdefault(t['shape_id'],t['route_id'])
shp=defaultdict(list)
for r in csv.DictReader(open('amtrak/shapes.txt')):
    if r['shape_id'] in shape_route: shp[r['shape_id']].append((int(r['shape_pt_sequence']),float(r['shape_pt_lon']),float(r['shape_pt_lat'])))
for sid,pts in shp.items():
    pts.sort(); ri=len(routes); rname=rt[shape_route[sid]]['route_long_name']; routes.append(('Amtrak','',rname)); RAILW=railw(rname)
    prev=None; lastst=set()
    for _,lon,lat in pts:
        ce=cell(lon,lat); i=nid(('r',ri,ce),(ce[0]*GRID,ce[1]*GRID))
        if prev is not None and prev!=i: add(prev,i,RAILW*hav(node_xy[prev],node_xy[i]),ri)
        if prev!=i:
            cur=cell_stops.get(ce,set())
            for si in cur-lastst: add(i,node_key[('s',si)],5.0,-1)
            lastst=cur
        prev=i
print('amtrak shapes',len(shp))
print('nodes',len(node_xy),'edges',len(edges))
# states
sj=json.load(open('states.geojson')); skip={'Alaska','Hawaii','Puerto Rico','District of Columbia'}
polys=[];names=[]
for f in sj['features']:
    if f['properties']['name'] in skip: continue
    polys.append(shape(f['geometry'])); names.append(f['properties']['name'])
xy=np.array(node_xy); pts=shapely.points(xy[:,0],xy[:,1]); tree=STRtree(polys)
state=np.full(len(xy),-1,dtype=np.int32); q=tree.query(pts,predicate='within'); state[q[0]]=q[1]
keys=[None]*len(node_xy)
for k,i in node_key.items(): keys[i]=k
pickle.dump(dict(node_xy=node_xy,keys=keys,edges=edges,routes=routes,stops=stop_info,names=names,state=state),open('graph4.pkl','wb'))
# contract
adj=defaultdict(dict)
for (a,b),(w,rs) in edges.items(): adj[a][b]=w; adj[b][a]=w
N=len(node_xy); keep=np.zeros(N,bool)
for v in range(N):
    nb=adj[v]
    if len(nb)!=2 or keys[v][0]=='s' or any(state[u]!=state[v] for u in nb): keep[v]=True
print('kept',keep.sum())
cedges={}; seen=set()
for v in np.where(keep)[0]:
    for u in adj[v]:
        if (v,u) in seen: continue
        path=[v,u]; w=adj[v][u]; prev,cur=v,u; seen.add((v,u))
        while not keep[cur]:
            nxt=[x for x in adj[cur] if x!=prev][0]; w+=adj[cur][nxt]; path.append(nxt); prev,cur=cur,nxt
        seen.add((cur,prev))
        if cur==v: continue
        key=(v,cur) if v<cur else (cur,v); p=path if v<cur else path[::-1]
        if key not in cedges or cedges[key][0]>w: cedges[key]=(w,p)
print('contracted edges',len(cedges))
pickle.dump(cedges,open('cgraph4.pkl','wb'))
