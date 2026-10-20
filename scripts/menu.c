/* ride_search's menu, in C: generate a node's candidate rides and return only the best `width` of them.

   The Python version built every candidate as an Opt (namedtuple + frozenset) and sorted the lot, then used the
   first --width. Profiled on the Sheridan run (Oct 12) a node offered about 59000 candidates for 12 used, and
   building and sorting them was ~85% of the search. Same loops, same tests, same key, same tie order (generation
   order, which is what Python's stable sort keeps), but nothing outside the top `width` is ever materialised.

   Mirrors ride_search.rides_from (the `cap is not None` branch: deadline tables present, no Menu/dedupe) and
   ride_search.sort_opts with order='slack' and no pair re-rank. Key, ascending: (0 if (trip, to) is a goal ride
   else 1 [only when goals are given], 1 if the option collects nothing new else 0 [only with split on], -slack).
   City-transit trips may only be left at `useful` stops or in another state than the boarding stop
   (ride_search --city-stops). States are bits of a uint64 (48 states). Build: cc -O3 -shared -fPIC menu.c -o menu.so */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

typedef struct { double k3; int k1, k2; long long gen; int to; double at; int trip; uint64_t got; int walk, k, kk; } Cand;

static inline int cand_less(const Cand *a, const Cand *b) {   /* strict: a ranks before b */
    if (a->k1 != b->k1) return a->k1 < b->k1;
    if (a->k2 != b->k2) return a->k2 < b->k2;
    if (a->k3 != b->k3) return a->k3 < b->k3;
    return a->gen < b->gen;
}

/* keep the best `w` seen so far, sorted ascending; returns the new count */
static inline int keep_top(Cand *top, int n, int w, const Cand *c) {
    if (n == w && !cand_less(c, &top[n - 1])) return n;
    int i = (n < w) ? n : w - 1;
    while (i > 0 && cand_less(c, &top[i - 1])) { top[i] = top[i - 1]; i--; }
    top[i] = *c;
    return n < w ? n + 1 : n;
}

static inline double slack_of(int to, double at, uint64_t owed_after, uint64_t new_bits,
                              const double *cap, const double *L, const double *L_end, int n_stops, int n_states) {
    if (!new_bits) return cap[to] - at;                       /* owed unchanged: the node's own ceiling */
    if (!owed_after) return L_end[to] - at;
    double m = L_end[to];
    for (int y = 0; y < n_states; y++)
        if (owed_after >> y & 1ULL) { double v = L[(size_t)y * n_stops + to]; if (v < m) m = v; }
    return m - at;
}

int menu_top(int s, double t, int aboard, uint64_t collected,
             int n_stops, int n_states, int n_trips,
             const int *bptr, const int *bconn, const double *bdep,          /* departures per stop, by time */
             const int *tptr, const int *tconn, const int *conn_pos,         /* connections per trip, in order */
             const int *ctrip, const int *cto, const double *arr, const double *dep, const int *state,
             const unsigned char *city_trip, const unsigned char *useful,  /* --city-stops: per trip, per stop */
             int skip_city,                                                 /* --city-hop: city trips come whole, from Python */
             const int *fptr, const int *fto, const double *fw,              /* footpaths (R.foot order) */
             const int *wptr, const int *wy, const double *ww,               /* walk-ins per stop */
             const double *L, const double *L_end, const double *cap,
             double horizon, double min_transfer, int split,
             int n_goal, const int *goal_trip, const int *goal_stop,
             int width, int *seen_stamp, int stamp,
             int *o_to, double *o_at, int *o_trip, uint64_t *o_got, int *o_walk, int *o_k, int *o_kk, long long *o_total)
{
    Cand *top = (Cand *)malloc(sizeof(Cand) * (size_t)(width > 0 ? width : 1));
    if (!top) return -1;
    int n = 0; long long gen = 0;
    uint64_t all = (n_states >= 64) ? ~0ULL : ((1ULL << n_states) - 1);
    uint64_t owed0 = all & ~collected;
    /* the stop itself first, then its footpath neighbours, as in [(s, 0)] + list(R.foot.get(s, ())) */
    int nfoot = fptr[s + 1] - fptr[s];
    for (int e = -1; e < nfoot; e++) {
        int j = (e < 0) ? s : fto[fptr[s] + e];
        double w = (e < 0) ? 0.0 : fw[fptr[s] + e];
        double t_ok = t + w;
        int lo = bptr[j], hi = bptr[j + 1];
        if (lo == hi) continue;
        int a = lo, b = hi;                                           /* bisect_left(bdep, t_ok) */
        while (a < b) { int m = (a + b) >> 1; if (bdep[m] < t_ok) a = m + 1; else b = m; }
        stamp++;                                                      /* fresh `seen` per neighbour */
        for (int i = a; i < hi && bdep[i] <= t_ok + horizon; i++) {
            int k = bconn[i]; int key = ctrip[k];
            if (seen_stamp[key] == stamp) continue;
            if (skip_city && city_trip[key]) continue;
            if (!(key == aboard && j == s) && dep[k] < t_ok + min_transfer) continue;
            seen_stamp[key] = stamp;
            uint64_t got = 0; int fresh = 0;
            for (int q = tptr[key] + conn_pos[k]; q < tptr[key + 1]; q++) {
                int kk = tconn[q]; int to = cto[kk]; int st = state[to];
                if (st >= 0) { got |= 1ULL << st; if (!(collected >> st & 1ULL)) fresh = 1; }
                double at = arr[kk];
                uint64_t owed_after = owed0 & ~got;
                if (!fresh) {
                    if (at > cap[to]) continue;
                } else {
                    if (at > cap[to]) {
                        int bad = 0;
                        for (int y = 0; y < n_states; y++)
                            if ((owed_after >> y & 1ULL) && at > L[(size_t)y * n_stops + to]) { bad = 1; break; }
                        if (bad) continue;
                    }
                    if (at > L_end[to]) continue;
                }
                /* --city-stops useful: ride through city-transit stops where getting off cannot matter */
                if (!useful[to] && city_trip[key] && state[to] == state[j]) continue;
                {   Cand c; c.to = to; c.at = at; c.trip = key; c.got = got; c.walk = -1; c.k = k; c.kk = kk; c.gen = gen++;
                    uint64_t nb = got & ~collected;
                    c.k1 = 1;
                    if (n_goal) { c.k1 = 1; for (int g = 0; g < n_goal; g++) if (goal_trip[g] == key && goal_stop[g] == to) { c.k1 = 0; break; } }
                    else c.k1 = 0;
                    c.k2 = split ? (nb == 0) : 0;
                    c.k3 = -slack_of(to, at, owed_after, nb, cap, L, L_end, n_stops, n_states);
                    n = keep_top(top, n, width, &c); }
                for (int e2 = wptr[to]; e2 < wptr[to + 1]; e2++) {
                    int y = wy[e2]; double ww_ = ww[e2];
                    if ((got >> y & 1ULL) || (collected >> y & 1ULL)) continue;
                    double at2 = at + 2 * ww_;
                    if (at2 > L_end[to] || at > L[(size_t)y * n_stops + to]) continue;
                    if (at2 > cap[to]) {
                        int bad = 0;
                        for (int z = 0; z < n_states; z++)
                            if (z != y && (owed_after >> z & 1ULL) && at2 > L[(size_t)z * n_stops + to]) { bad = 1; break; }
                        if (bad) continue;
                    }
                    Cand c; c.to = to; c.at = at2; c.trip = key; c.got = got | (1ULL << y); c.walk = y; c.k = k; c.kk = kk; c.gen = gen++;
                    uint64_t nb = c.got & ~collected;
                    if (n_goal) { c.k1 = 1; for (int g = 0; g < n_goal; g++) if (goal_trip[g] == key && goal_stop[g] == to) { c.k1 = 0; break; } }
                    else c.k1 = 0;
                    c.k2 = split ? (nb == 0) : 0;
                    c.k3 = -slack_of(to, at2, owed_after & ~(1ULL << y), nb, cap, L, L_end, n_stops, n_states);
                    n = keep_top(top, n, width, &c);
                }
            }
        }
    }
    for (int i = 0; i < n; i++) {
        o_to[i] = top[i].to; o_at[i] = top[i].at; o_trip[i] = top[i].trip; o_got[i] = top[i].got;
        o_walk[i] = top[i].walk; o_k[i] = top[i].k; o_kk[i] = top[i].kk;
    }
    *o_total = gen;
    free(top);
    return n;
}

/* --city-hop's scan, in C: ride_search.city_scan line for line. Earliest arrival over city transit only from
   (s, t), within H and `rounds` rides, RAPTOR-style rounds. Profiled Oct 19 the Python version cost ~1 s a node
   (92 calls, 90 s of a 90 s budget), which is what made --city-hop unusable. Outputs: best/pred per stop, valid
   where bstamp[v] == gen; `touched` lists stops in the order Python's dict would have inserted them. The seen
   set per (u, j) is keyed (route id, next stop), as Python's (feed, route, cto). Returns the touched count. */
#define CS_HBITS 15
int city_scan(int s, double t, int aboard, double H, double min_transfer, int rounds,
              const int *bptr, const int *bconn, const double *bdep,
              const int *tptr, const int *tconn, const int *conn_pos,
              const int *ctrip, const int *cto, const double *arr, const double *dep,
              const unsigned char *city_trip, const int *rid,
              const int *fptr, const int *fto, const double *fw,
              int gen, int *bstamp, double *best, int *pk, int *pkk, int *pu,
              int *touched, int *marked, int *nxt, int *mstamp,
              int *hr, int *hc, int *hstamp, int *hgen,
              const unsigned char *hop_target, const int *cfrom, const int *state, int *ends, int *n_ends)
{
    int nt = 0, nm = 1, hg = *hgen;
    bstamp[s] = gen; best[s] = t; pk[s] = pkk[s] = pu[s] = -1; touched[nt++] = s; marked[0] = s;
    for (int rnd = 0; rnd < rounds; rnd++) {
        int nn = 0; int mg = ++hg;                  /* per-round stamp for the first-occurrence dedupe */
        for (int mi = 0; mi < nm; mi++) {
            int u = marked[mi]; double tu = best[u];
            int nfoot = fptr[u + 1] - fptr[u];
            for (int e = -1; e < nfoot; e++) {
                int j = (e < 0) ? u : fto[fptr[u] + e];
                double t_ok = tu + ((e < 0) ? 0.0 : fw[fptr[u] + e]);
                int lo = bptr[j], hi = bptr[j + 1];
                if (lo == hi) continue;
                int a = lo, b = hi;
                while (a < b) { int m = (a + b) >> 1; if (bdep[m] < t_ok) a = m + 1; else b = m; }
                hg++;                                               /* fresh seen_r per (u, j) */
                for (int i = a; i < hi && bdep[i] <= H; i++) {
                    int k = bconn[i]; int key = ctrip[k];
                    if (!city_trip[key]) continue;
                    if (!(rnd == 0 && key == aboard && j == s) && dep[k] < t_ok + min_transfer) continue;
                    int r_ = rid[key], c_ = cto[k];
                    unsigned h = ((unsigned)r_ * 2654435761u ^ (unsigned)c_ * 40503u) & ((1u << CS_HBITS) - 1);
                    int dup = 0;
                    while (hstamp[h] == hg) { if (hr[h] == r_ && hc[h] == c_) { dup = 1; break; } h = (h + 1) & ((1u << CS_HBITS) - 1); }
                    if (dup) continue;
                    hstamp[h] = hg; hr[h] = r_; hc[h] = c_;
                    for (int q = tptr[key] + conn_pos[k]; q < tptr[key + 1]; q++) {
                        int kk = tconn[q]; double at = arr[kk];
                        if (at > H) break;
                        int to = cto[kk];
                        if (bstamp[to] != gen) { bstamp[to] = gen; best[to] = INFINITY; touched[nt++] = to; }
                        if (at < best[to]) {
                            best[to] = at; pk[to] = k; pkk[to] = kk; pu[to] = u;
                            if (mstamp[to] != mg) { mstamp[to] = mg; nxt[nn++] = to; }
                        }
                    }
                }
            }
        }
        if (!nn) break;
        memcpy(marked, nxt, sizeof(int) * (size_t)nn); nm = nn;
    }
    *hgen = hg;
    /* the useful ends, in touched order: an intercity stop / walk-in (hop_target) or the first stop in a new state */
    int ne = 0;
    for (int i = 1; i < nt; i++) {
        int v = touched[i];
        int cross = state[v] >= 0 && state[v] != state[s] && state[cfrom[pkk[v]]] != state[v];
        if (hop_target[v] || cross) ends[ne++] = v;
    }
    *n_ends = ne;
    return nt;
}
