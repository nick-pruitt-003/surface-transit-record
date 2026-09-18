"""Find a short walk through the graph that reaches a stop in all 48 states.

usage: python3 solve.py --graph graph2 --budget 1200 --out result2.pkl
       python3 solve.py --graph graph4 --seed result2.pkl --prefix "Montana,Washington,@Tucson,New Mexico" ...

--prefix locks the first states of the order. An entry "@Name" is a named stop
target (any stop whose name contains Name) instead of a state.
"""
import argparse, pickle, random, time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from common import load_graph

N_STATES = 48


class Solver:
    def __init__(self, graph, cedges, prefix):
        self.G = graph; self.names = list(graph['names'])
        keys = graph['keys']
        self.nodes = sorted({k for e in cedges for k in e})
        self.idx = {v: i for i, v in enumerate(self.nodes)}; self.N = len(self.nodes)
        self.state = graph['state'][self.nodes]
        ek = list(cedges.keys())
        self.a = np.array([self.idx[e[0]] for e in ek]); self.b = np.array([self.idx[e[1]] for e in ek])
        self.w = np.array([max(cedges[e][0], 1e-6) for e in ek])
        # edges touching a stop hub carry the transfer cost; overridable at solve time
        self.hub_edge = np.array([keys[e[0]][0] == 's' or keys[e[1]][0] == 's' for e in ek])
        # a node "counts" for a state if it is a stop hub or a route cell adjacent to one
        isstop = np.array([keys[v][0] == 's' for v in self.nodes])
        self.nearstop = isstop.copy()
        for (u, v) in cedges:
            if keys[u][0] == 's': self.nearstop[self.idx[v]] = True
            if keys[v][0] == 's': self.nearstop[self.idx[u]] = True
        self.targets = [np.where((self.state == s) & self.nearstop)[0] for s in range(N_STATES)]
        # named stop targets from the prefix
        self.prefix = []
        for p in prefix:
            if p.startswith('@'):
                q = p[1:].lower()
                stopidx = {i for i, st in enumerate(graph['stops']) if q in str(st[0]).lower()}
                sel = set()
                for (u, v) in cedges:
                    for x, y in ((u, v), (v, u)):
                        if keys[x][0] == 's' and keys[x][1] in stopidx:
                            sel.add(self.idx[x]); sel.add(self.idx[y])
                self.names.append(p); self.targets.append(np.array(sorted(sel)))
                self.prefix.append(len(self.targets) - 1)
                print('target', p, len(sel), 'nodes')
            else:
                self.prefix.append(self.names.index(p))
        self.P = len(self.prefix)
        self.cache = {}
        # for turnaround detection: cell of each contracted node, and how many
        # distinct route groups (carrier + sorted endpoints) serve each cell
        import re
        from collections import defaultdict
        def canon(ri):
            car, short, long_ = graph['routes'][ri]; nm = (long_ or short or '')
            parts = [p.strip() for p in re.split(r'\s*(?:->|<->|–|-)\s*', nm) if p.strip()]
            return (car, ' | '.join(sorted(parts)) if len(parts) > 1 else nm)
        gid = {}
        for ri in range(len(graph['routes'])):
            gid[ri] = gid.get(ri) or canon(ri)
        self.node_cell = [keys[v][2] if keys[v][0] == 'r' else None for v in self.nodes]
        groups = defaultdict(set)
        for k in keys:
            if k[0] == 'r': groups[k[2]].add(gid[k[1]])
        self.cell_groups = {c: len(g) for c, g in groups.items()}
        self.turn_penalty = 0.0; self.frequent = 4

    # --- shortest paths -------------------------------------------------
    def multi_source(self, src_idx, src_val, pred=False):
        V = self.N
        ai = np.r_[self.a, self.b, np.full(len(src_idx), V)]
        bi = np.r_[self.b, self.a, src_idx]
        wi = np.r_[self.w, self.w, np.maximum(src_val, 1e-9)]
        M = coo_matrix((wi, (ai, bi)), shape=(V + 1, V + 1)).tocsr()
        return dijkstra(M, directed=True, indices=V, return_predecessors=pred)

    def exact(self, order):
        """Cost of the best walk visiting targets in this order (prefix-cached)."""
        order = tuple(order); k = len(order)
        while k > 1 and order[:k] not in self.cache:
            k -= 1
        if k == 1 and order[:1] not in self.cache:
            self.cache[order[:1]] = np.zeros(len(self.targets[order[0]]))
        lab = self.cache[order[:k]]
        for j in range(k, len(order)):
            d = self.multi_source(self.targets[order[j - 1]], lab)
            lab = d[:self.N][self.targets[order[j]]]; self.cache[order[:j + 1]] = lab
        return lab.min()

    def exact_full(self, order):
        """Recompute with predecessors; returns (cost, node path in contracted ids)."""
        o = list(order); lab = np.zeros(len(self.targets[o[0]])); preds = []
        for j in range(1, len(o)):
            d, p = self.multi_source(self.targets[o[j - 1]], lab, True)
            preds.append(p); lab = d[:self.N][self.targets[o[j]]]
        end = self.targets[o[-1]][np.argmin(lab)]; total = lab.min(); path = []
        for j in range(len(o) - 1, 0, -1):
            p = preds[j - 1]; seg = [end]
            while p[seg[-1]] != self.N:
                seg.append(p[seg[-1]])
            path = seg[::-1] + path[1:] if path else seg[::-1]
            end = seg[-1]
        return total, path

    def turnarounds(self, path):
        """Apexes where the walk retraces its last 3 cells, on corridors with
        fewer than self.frequent parallel route groups."""
        cells = [c for c in (self.node_cell[v] for v in path) if c is not None]
        cells = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
        n = 0
        for i in range(3, len(cells) - 3):
            if cells[i - 1] == cells[i + 1] and cells[i - 2] == cells[i + 2] and cells[i - 3] == cells[i + 3]:
                if self.cell_groups.get(cells[i], 0) < self.frequent: n += 1
        return n

    def penalised(self, order):
        c, path = self.exact_full(order)
        return c + self.turn_penalty * self.turnarounds(path), path

    def covered(self, path):
        p = np.array(path)
        return set(self.state[p[self.nearstop[p]]].tolist()) - {-1}

    # --- ordering heuristics -------------------------------------------
    def hub_matrix(self):
        DS = np.array([self.multi_source(t, np.zeros(len(t)))[:self.N] for t in self.targets[:N_STATES]])
        tot = DS.sum(0)
        hub = [t[np.argmin(tot[t])] for t in self.targets[:N_STATES]]
        return np.array([self.multi_source([h], [0])[:self.N][hub] for h in hub])

    @staticmethod
    def order_cost(o, D):
        return sum(D[o[i], o[i + 1]] for i in range(len(o) - 1))

    def two_opt(self, order, D):
        best = self.order_cost(order, D); improved = True
        while improved:
            improved = False; n = len(order)
            for i in range(n - 1):
                for j in range(i + 2, n + 1):
                    new = order[:i] + order[i:j][::-1] + order[j:]; c = self.order_cost(new, D)
                    if c < best - 1e-9: order, best, improved = new, c, True
            for L in (1, 2, 3):
                for i in range(n - L + 1):
                    seg = order[i:i + L]; rest = order[:i] + order[i + L:]
                    for j in range(len(rest) + 1):
                        for sg in (seg, seg[::-1]):
                            new = rest[:j] + sg + rest[j:]; c = self.order_cost(new, D)
                            if c < best - 1e-9: order, best, improved = new, c, True
        return order, best

    def initial_order(self):
        D = self.hub_matrix(); best = None
        for st in range(N_STATES):
            order = [st]; left = set(range(N_STATES)) - {st}
            while left:
                cur = order[-1]; nxt = min(left, key=lambda t: D[cur, t]); order.append(nxt); left.remove(nxt)
            o, c = self.two_opt(order, D)
            if best is None or c < best[1]: best = (o, c)
        random.seed(2)
        for _ in range(40):
            o = best[0][:]; i, j = sorted(random.sample(range(N_STATES), 2)); o = o[:i] + o[i:j][::-1] + o[j:]
            o, c = self.two_opt(o, D)
            if c < best[1]: best = (o, c)
        self.D = D
        return best[0]

    def apply_prefix(self, order):
        pre = self.prefix
        return pre + [x for x in order if x not in pre]

    def best_insert(self, order, m):
        bo = None
        for j in range(self.P, len(order) + 1):
            o2 = order[:j] + [m] + order[j:]; c2 = self.exact(o2)
            if bo is None or c2 < bo[1]: bo = (o2, c2)
        return bo

    def ensure_covered(self, order):
        c, path = self.exact_full(order)
        for m in [s for s in range(N_STATES) if s not in self.covered(path)]:
            order, c = self.best_insert(order, m); print('  inserted', self.names[m], round(c))
        return order

    def prune(self, order):
        """Drop states that the walk reaches before their slot, if that never
        loses coverage or raises cost."""
        nodrop = set()
        while True:
            c, path = self.exact_full(order)
            first = {}
            for i, v in enumerate(path):
                s = self.state[v]
                if s not in first: first[s] = i
            drop = None
            for j in range(1, len(order)):
                s = order[j]
                if s in nodrop or j < self.P or s >= N_STATES: continue
                if first.get(s, 10**9) < first.get(order[j - 1], 10**9): drop = s; break
            if drop is None:
                return order, c, path
            o2 = [x for x in order if x != drop]; c2, p2 = self.exact_full(o2)
            if len(self.covered(p2)) < N_STATES or c2 > c:
                nodrop.add(drop); continue
            order = o2; print('  drop', self.names[drop])

    def moves(self, order):
        n = len(order); P = self.P; out = []
        for i in range(P, n):
            seg = order[i:i + 1]; rest = order[:i] + order[i + 1:]
            for j in range(P, n):
                if j != i: out.append(rest[:j] + seg + rest[j:])
        for i in range(P, n - 1):
            for j in range(i + 2, n + 1):
                out.append(order[:i] + order[i:j][::-1] + order[j:])
        return out

    def local_search(self, order, budget):
        order, c, path = self.prune(order)
        if self.turn_penalty > 0: c, path = self.penalised(order)
        print('start', round(c), 'km,', len(order), 'required, turnarounds', self.turnarounds(path))
        t0 = time.time(); improved = True; it = 0
        proxy = lambda o: sum(self.D[o[i], o[i + 1]] for i in range(len(o) - 1) if o[i] < N_STATES and o[i + 1] < N_STATES)
        while improved and time.time() - t0 < budget:
            improved = False; base = proxy(order)
            for o in sorted(self.moves(order), key=proxy):
                if time.time() - t0 > budget or proxy(o) - base > 800: break
                if self.turn_penalty > 0:
                    cc, _ = self.penalised(o)
                else:
                    cc = self.exact(o)
                it += 1
                if cc < c - 1:
                    c = cc; order = o; improved = True
                    print('  improve', round(c), 'km after', it, 'evals', round(time.time() - t0), 's'); break
            if improved:
                self.cache.clear()   # bound memory; prefixes are recomputed on demand
                order, c, path = self.prune(order)
                if self.turn_penalty > 0: c, path = self.penalised(order)
                if len(self.covered(path)) < N_STATES:
                    order = self.ensure_covered(order); c, path = self.exact_full(order)
        return order, c, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--graph', required=True); ap.add_argument('--budget', type=float, default=1200)
    ap.add_argument('--seed', help='result pickle whose state order seeds the search')
    ap.add_argument('--prefix', default='', help='comma list of states / @stop names locked at the front')
    ap.add_argument('--turn-penalty', type=float, default=0.0, help='km-equivalent charged per reversal on a corridor with < 4 parallel services')
    ap.add_argument('--transfer-penalty', type=float, default=None, help='km-equivalent per transfer (graph default is 10)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    graph, cedges = load_graph(a.graph)
    S = Solver(graph, cedges, [x.strip() for x in a.prefix.split(',') if x.strip()])
    S.turn_penalty = a.turn_penalty
    if a.transfer_penalty is not None:
        S.w[S.hub_edge] = max(a.transfer_penalty / 2.0, 1e-6)   # two hub edges per transfer
    order = S.initial_order()
    if a.seed:
        seed = [x for x in pickle.load(open(a.seed, 'rb'))['order'] if x < N_STATES]
        order = S.apply_prefix(seed)   # a seed is trusted over the hub ordering
    order = S.apply_prefix(order)
    order = S.ensure_covered(order)
    order, c, path = S.local_search(order, a.budget)
    c, path = S.exact_full(order)
    print('FINAL', round(c), 'km required', len(order), 'covered', len(S.covered(path)), 'turnarounds', S.turnarounds(path))
    print(' > '.join(S.names[x] for x in order))
    pickle.dump(dict(order=order, cost=c, path=[S.nodes[v] for v in path], graph=a.graph), open(a.out, 'wb'))


if __name__ == '__main__':
    main()
