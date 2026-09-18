import pickle, numpy as np, random, time, sys
PREFIX=[x.strip() for x in sys.argv[3].split(',')] if len(sys.argv)>3 else []
P=len(PREFIX)
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
G=pickle.load(open('graph4.pkl','rb')); S=G; CE=pickle.load(open('cgraph4.pkl','rb'))
names=S['names']; state0=S['state']
nodes=sorted({k for e in CE for k in e}); idx={v:i for i,v in enumerate(nodes)}; N=len(nodes)
state=state0[nodes]
ek=list(CE.keys()); a=np.array([idx[e[0]] for e in ek]); b=np.array([idx[e[1]] for e in ek]); w=np.array([max(CE[e][0],1e-6) for e in ek])
V=N
def ms(labels_idx,labels_val,pred=False):
    ai=np.r_[a,b,np.full(len(labels_idx),V)]; bi=np.r_[b,a,labels_idx]; wi=np.r_[w,w,np.maximum(labels_val,1e-9)]
    M=coo_matrix((wi,(ai,bi)),shape=(N+1,N+1)).tocsr()
    return dijkstra(M,directed=True,indices=V,return_predecessors=pred)
isstop=np.array([G['keys'][v][0]=='s' for v in nodes])
nearstop=isstop.copy()
for (u,v) in CE:
    if G['keys'][u][0]=='s': nearstop[idx[v]]=True
    if G['keys'][v][0]=='s': nearstop[idx[u]]=True
snodes=[np.where((state==s)&nearstop)[0] for s in range(48)]
print('stop nodes per state min',min(len(x) for x in snodes))
# hubs
t0=time.time()
DS=np.array([ms(snodes[s],np.zeros(len(snodes[s]))) [:N] for s in range(48)])
tot=DS.sum(0)
hub=[snodes[s][np.argmin(tot[snodes[s]])] for s in range(48)]
Dh=np.array([ms([hub[s]],[0])[:N][hub] for s in range(48)])
print('hubs done',round(time.time()-t0,1),'s')
pass
def cost_h(o): return sum(Dh[o[i],o[i+1]] for i in range(len(o)-1))
def two_opt(order,D):
    def cost(o): return sum(D[o[i],o[i+1]] for i in range(len(o)-1))
    best=cost(order); improved=True
    while improved:
        improved=False; n=len(order)
        for i in range(0,n-1):
            for j in range(i+2,n+1):
                new=order[:i]+order[i:j][::-1]+order[j:]; c=cost(new)
                if c<best-1e-9: order,best,improved=new,c,True
        for L in (1,2,3):
            for i in range(0,n-L+1):
                seg=order[i:i+L]; rest=order[:i]+order[i+L:]
                for j in range(0,len(rest)+1):
                    for sg in (seg,seg[::-1]):
                        new=rest[:j]+sg+rest[j:]; c=cost(new)
                        if c<best-1e-9: order,best,improved=new,c,True
    return order,best
def nn(start,D):
    order=[start]; left=set(range(48))-{start}
    while left:
        cur=order[-1]; nxt=min(left,key=lambda t:D[cur,t]); order.append(nxt); left.remove(nxt)
    return order
best=None
for st in range(48):
    o,c=two_opt(nn(st,Dh),Dh)
    if best is None or c<best[1]: best=(o,c)
random.seed(2)
for k in range(40):
    o=best[0][:]; i,j=sorted(random.sample(range(48),2)); o=o[:i]+o[i:j][::-1]+o[j:]
    o,c=two_opt(o,Dh)
    if c<best[1]: best=(o,c)
print('hub TSP',round(best[1]),'km:',' > '.join(names[x] for x in best[0]))
# exact layered eval with prefix cache
cache={}
def exact(order,want_path=False):
    order=tuple(order)
    # find longest cached prefix
    k=len(order)
    while k>1 and order[:k] not in cache: k-=1
    if k==1 or order[:1] not in cache:
        lab=np.zeros(len(snodes[order[0]])); cache[order[:1]]=lab; k=1
    lab=cache[order[:k]]
    preds=[]
    for j in range(k,len(order)):
        s_prev,s=order[j-1],order[j]
        if want_path:
            d,p=ms(snodes[s_prev],lab,True); preds.append(p)
        else: d=ms(snodes[s_prev],lab)
        lab=d[:N][snodes[s]]; cache[order[:j+1]]=lab
    if want_path: return lab.min(),preds
    return lab.min()
def exact_full(order):
    # recompute all layers with preds, return cost and node path (contracted ids)
    o=list(order); lab=np.zeros(len(snodes[o[0]])); preds=[]; labs=[lab]
    for j in range(1,len(o)):
        d,p=ms(snodes[o[j-1]],lab,True); preds.append(p); lab=d[:N][snodes[o[j]]]; labs.append(lab)
    end=snodes[o[-1]][np.argmin(lab)]; total=lab.min()
    path=[]
    for j in range(len(o)-1,0,-1):
        p=preds[j-1]; seg=[end]
        while p[seg[-1]]!=V: seg.append(p[seg[-1]])
        path=seg[::-1]+path[1:] if path else seg[::-1]
        end=seg[-1]
    return total,path
t0=time.time(); c0=exact(best[0]); print('exact cost of hub order',round(c0),'km in',round(time.time()-t0,1),'s')
def covered_states(path):
    p=np.array(path); return set(state[p[nearstop[p]]].tolist())-{-1}
def prune(order):
    nodrop=set()
    while True:
        c,path=exact_full(order)
        # position in path where each state first touched
        first={}
        for i,v in enumerate(path):
            s=state[v]
            if s not in first: first[s]=i
        # slot boundaries: find index of path where layer of each required state begins -> approximate by first touch order
        # required state s at slot j is droppable if some earlier-slot state's first touch index > first[s]  (i.e. s touched before order reaches it)
        drop=None
        for j in range(1,len(order)):
            s=order[j]
            if s in nodrop or j<P: continue
            if first[s] < first[order[j-1]]: drop=s; break
        if drop is None: return order,c,path
        o2=[x for x in order if x!=drop]
        c2,p2=exact_full(o2)
        if len(covered_states(p2))<48 or c2>c: nodrop.add(drop); continue
        order=o2
        print('  drop',names[drop])
if len(sys.argv)>2:
    seed=pickle.load(open(sys.argv[2],'rb'))['order']; print('seeded from',sys.argv[2],len(seed))
    _c,_p=exact_full(seed); miss=[x for x in range(48) if x not in covered_states(_p)]
    for m in miss:
        bo=None
        for j in range(len(seed)+1):
            o2=seed[:j]+[m]+seed[j:]; c2=exact(o2)
            if bo is None or c2<bo[1]: bo=(o2,c2)
        seed=bo[0]; print('  inserted',names[m],round(bo[1]))
    if PREFIX:
        pre=[names.index(x) for x in PREFIX]; seed=pre+[x for x in seed if x not in pre]
    best=(seed,0)
order,c,path=prune(best[0]); print('after prune',len(order),'required,',round(c),'km, covered',len(covered_states(path)))
# local search on exact cost with proxy pruning
budget=float(sys.argv[1]) if len(sys.argv)>1 else 900
t0=time.time(); improved=True; it=0
def moves(order):
    n=len(order); ms_=[]
    for i in range(P,n):
        seg=order[i:i+1]; rest=order[:i]+order[i+1:]
        for j in range(n):
            if j==i or j<P: continue
            ms_.append(rest[:j]+seg+rest[j:])
    for i in range(P,n-1):
        for j in range(i+2,n+1):
            ms_.append(order[:i]+order[i:j][::-1]+order[j:])
    return ms_
while improved and time.time()-t0<budget:
    improved=False
    cand=moves(order)
    cand.sort(key=cost_h)
    base=cost_h(order)
    for o in cand:
        if time.time()-t0>budget: break
        if cost_h(o)-base>800: break
        cc=exact(o); it+=1
        if cc<c-1:
            c=cc; order=o; improved=True; print('  improve',round(c),'km after',it,'evals',round(time.time()-t0),'s'); break
    if improved:
        order,c,path=prune(order)
        # re-add check: all 48 covered?
        cov=covered_states(path)
        if len(cov)<48:
            miss=[s for s in range(48) if s not in cov]; print('  MISSING',[names[s] for s in miss])
            for m in miss:
                bo=None
                for j in range(len(order)+1):
                    o2=order[:j]+[m]+order[j:]; c2=exact(o2)
                    if bo is None or c2<bo[1]: bo=(o2,c2)
                order,c=bo
            c,path=exact_full(order); print('  reinserted ->',round(c),'covered',len(covered_states(path)))
c,path=exact_full(order)
print('FINAL',round(c),'km required',len(order),'covered',len(covered_states(path)))
print(' > '.join(names[x] for x in order))
pickle.dump(dict(order=order,cost=c,path=[nodes[v] for v in path]),open('result6.pkl','wb'))
