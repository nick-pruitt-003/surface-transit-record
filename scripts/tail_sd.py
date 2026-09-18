import pickle, numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
G=pickle.load(open('graph2.pkl','rb')); CE=pickle.load(open('cgraph2.pkl','rb')); R=pickle.load(open('result2.pkl','rb'))
nodes=sorted({k for e in CE for k in e}); idx={v:i for i,v in enumerate(nodes)}; N=len(nodes)
ek=list(CE.keys()); a=np.array([idx[e[0]] for e in ek]); b=np.array([idx[e[1]] for e in ek]); w=np.array([max(CE[e][0],1e-6) for e in ek])
A=coo_matrix((np.r_[w,w],(np.r_[a,b],np.r_[b,a])),shape=(N,N)).tocsr()
targets=[i for i,k in enumerate(G['keys']) if k[0]=='s' and 'Watertown' in G['stops'][k[1]][0] and G['stops'][k[1]][1]=='SD']
print([G['stops'][G['keys'][t][1]] for t in targets])
end=R['path'][-1]; d,p=dijkstra(A,indices=idx[end],return_predecessors=True)
t=min(targets,key=lambda v:d[idx[v]]); print('tail km',round(d[idx[t]]))
seg=[idx[t]]
while p[seg[-1]]!=-9999 and seg[-1]!=idx[end]: seg.append(p[seg[-1]])
seg=[nodes[v] for v in seg[::-1]]
R2=dict(order=R['order']+[G['names'].index('South Dakota')],cost=R['cost']+d[idx[t]],path=R['path']+seg[1:])
pickle.dump(R2,open('result2_sd.pkl','wb')); print('ok',len(R2['path']))
