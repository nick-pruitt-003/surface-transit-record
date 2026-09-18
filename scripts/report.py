# Relabel the node path with the fewest bus legs (switch only at stop cells), then emit txt/csv/geojson
import pickle, json, math, sys, csv
from collections import defaultdict
gfile=sys.argv[3] if len(sys.argv)>3 else 'graph2.pkl'
G=pickle.load(open(gfile,'rb')); CE=pickle.load(open(gfile.replace('graph','cgraph'),'rb')); R=pickle.load(open(sys.argv[1],'rb'))
keys=G['keys']; xy=G['node_xy']; state=G['state']; names=G['names']; routes=G['routes']; stops=G['stops']
abbr={'Alabama':'AL','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT','Delaware':'DE','Florida':'FL','Georgia':'GA','Idaho':'ID','Illinois':'IL','Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD','Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT','Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY','North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY'}
GRID=0.01
def hav(a,b):
    lon1,lat1=a; lon2,lat2=b; p=math.pi/180
    x=(math.sin((lat2-lat1)*p/2)**2+math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2*6371*math.asin(math.sqrt(x))
cp=R['path']; full=[cp[0]]
for a,b in zip(cp,cp[1:]):
    k=(a,b) if a<b else (b,a); w,p=CE[k]
    if p[0]!=a: p=p[::-1]
    full+=p[1:]
# cell -> routes, cell -> stops
import re
def canon(ri):
    car,short,long_=routes[ri]; nm=(long_ or short or '')
    parts=[p.strip() for p in re.split(r'\s*(?:->|<->|–|-)\s*',nm) if p.strip()]
    return (car,' | '.join(sorted(parts)) if len(parts)>1 else nm)
groups={}; gid_of={}
for ri in range(len(routes)):
    g=canon(ri); gid_of[ri]=groups.setdefault(g,len(groups))
grep_=None
cell_routes=defaultdict(set); cell_stops=defaultdict(set)
for i,k in enumerate(keys):
    if k[0]=='r':
        cx,cy=k[2]
        for dx in (-1,0,1):
            for dy in (-1,0,1): cell_routes[(cx+dx,cy+dy)].add(gid_of[k[1]])
gname={v:k for k,v in groups.items()}
rep={}
for ri in range(len(routes)): rep.setdefault(gid_of[ri],ri)
for si,(sn,st,car,lon,lat) in enumerate(stops):
    cx,cy=round(lon/GRID),round(lat/GRID)
    for dx in (-1,0,1):
        for dy in (-1,0,1): cell_stops[(cx+dx,cy+dy)].add(si)
# cell sequence (dedupe consecutive), with the state of each cell
seq=[]
for v in full:
    k=keys[v]
    if k[0]!='r': continue
    ce=k[2]
    if not seq or seq[-1][0]!=ce: seq.append((ce,state[v],gid_of[k[1]]))
# DP: fewest legs; switch only at stop cells (or where the original path switched at a stop hub)
INF=10**9
best=[{} for _ in seq]; back=[{} for _ in seq]
for r in cell_routes[seq[0][0]]: best[0][r]=1; back[0][r]=None
for i in range(1,len(seq)):
    ce=seq[i][0]; prev=best[i-1]; isstop=bool(cell_stops.get(ce)) or bool(cell_stops.get(seq[i-1][0]))
    pmin=min(prev.values()); pr=min(prev,key=prev.get)
    for r in cell_routes[ce]:
        stay=prev.get(r,INF)
        sw=pmin+1 if isstop else INF
        if stay<=sw: best[i][r]=stay; back[i][r]=r
        else: best[i][r]=sw; back[i][r]=pr
    if not best[i]:  # no route at this cell?? fall back to original label
        r=seq[i][2]; best[i][r]=pmin+1; back[i][r]=pr
# backtrack
r=min(best[-1],key=best[-1].get); lab=[None]*len(seq)
for i in range(len(seq)-1,-1,-1):
    lab[i]=r; r=back[i][r]
# legs
legs=[]
for i,(ce,st,_) in enumerate(seq):
    if legs and legs[-1]['route']==lab[i] and ce in legs[-1]['cellset'] and len(legs[-1]['cells'])>3:
        legs[-1]['turnaround']=True
        legs.append(dict(route=lab[i],cells=[legs[-1]['cells'][-1],ce],cellset={ce},states=[st] if st>=0 else [],km=hav((legs[-1]['cells'][-1][0]*GRID,legs[-1]['cells'][-1][1]*GRID),(ce[0]*GRID,ce[1]*GRID))))
        continue
    if not legs or legs[-1]['route']!=lab[i]:
        if legs:
            # the move from the previous leg's last cell to this one is real travel:
            # keep it on the previous bus if that bus serves this cell (an out-and-back
            # whose return is a single hop), otherwise it opens the new leg
            pl=legs[-1]; pc=pl['cells'][-1]; gap=hav((pc[0]*GRID,pc[1]*GRID),(ce[0]*GRID,ce[1]*GRID))
            if pl['route'] in cell_routes.get(ce,()) and ce in pl['cellset']:
                pl['km']+=gap; pl['cells'].append(ce); pl['turnaround']=True
                if st>=0 and (not pl['states'] or pl['states'][-1]!=st): pl['states'].append(st)
                legs.append(dict(route=lab[i],cells=[ce],cellset={ce},states=[st] if st>=0 else [],km=0.0))
            else:
                legs.append(dict(route=lab[i],cells=[pc,ce],cellset={ce},states=[st] if st>=0 else [],km=gap))
        else:
            legs.append(dict(route=lab[i],cells=[ce],cellset={ce},states=[st] if st>=0 else [],km=0.0))
    else:
        l=legs[-1]; l['km']+=hav((l['cells'][-1][0]*GRID,l['cells'][-1][1]*GRID),(ce[0]*GRID,ce[1]*GRID)); l['cells'].append(ce); l['cellset'].add(ce)
        if st>=0 and (not l['states'] or l['states'][-1]!=st): l['states'].append(st)
def stop_at(cell):
    ss=cell_stops.get(cell)
    if not ss: return ''
    lon,lat=cell[0]*GRID,cell[1]*GRID
    si=min(ss,key=lambda s:hav((stops[s][3],stops[s][4]),(lon,lat)))
    name,st_=stops[si][:2]
    return f"{name}, {st_}" if st_ else name
seen=[]; lines=[]; rows=[]; km=0
for n,l in enumerate(legs,1):
    car,long_=gname[l['route']]; short=long_; km+=l['km']
    sts=[abbr[names[s]] for s in l['states']]
    fresh=[]
    # states with a stop on this leg, in order; record the first stop cell per state
    stopstate={}
    for ce in l['cells']:
        if cell_stops.get(ce):
            nm=stop_at(ce); stabbr=nm.rsplit(', ',1)[-1]
            stopstate.setdefault(stabbr,nm)
    for stabbr,nm in stopstate.items():
        if stabbr in abbr.values() and stabbr not in seen: seen.append(stabbr); fresh.append(f"{stabbr} @ {nm.rsplit(', ',1)[0]}")
    def first_stop(cells):
        for c in cells:
            nm=stop_at(c)
            if nm: return nm
        return ''
    board=first_stop(l['cells'][:3]) or (first_stop(legs[n-2]['cells'][-3:][::-1]) if n>1 else '')
    alight=first_stop(l['cells'][-3:][::-1])
    local=car.startswith('LOCAL'); speed=25 if local else 90
    note='out-and-back, return on same corridor' if l.get('turnaround') else ''
    lines.append(f"{n:2d}. {car} — {long_ or short}  [{l['km']:.0f} km]  {board} -> {alight}  states: {'>'.join(sts)}"+(f"  NEW: {','.join(fresh)}" if fresh else ""))
    rows.append([n,'','','',board,alight,car,long_ or short,round(l['km']),round(l['km']*0.621),round(l['km']/speed,1),'>'.join(sts),','.join(fresh),'',note])
hdr=f"Total {km:.0f} km ({km*0.621:.0f} mi), {len(legs)} bus legs, {len(seen)} states with a stop\nState order: {' > '.join(seen)}\n"
out=sys.argv[2]; open(out,'w').write(hdr+"\n".join(lines)); print(hdr)
with open(out.replace('.txt','.csv'),'w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['Leg','Day','Depart','Arrive','Board at','Alight at','Carrier','Route','km','mi','Est hours','States on this leg','New states','Price','Notes']); w.writerows(rows)
feats=[dict(type='Feature',properties=dict(leg=n,carrier=gname[l['route']][0],route=gname[l['route']][1],km=round(l['km'])),geometry=dict(type='LineString',coordinates=[[c[0]*GRID,c[1]*GRID] for c in l['cells']])) for n,l in enumerate(legs,1)]
json.dump(dict(type='FeatureCollection',features=feats),open(out.replace('.txt','.geojson'),'w'))
