/* tail_mip.py's city-hop scan (Nov 18 2026). From one origin (a stop, a clock), every (arrival, states touched)
   that city transit and footpaths can reach, Pareto in (earlier, more states), at the stops the caller marks as
   outputs (intercity stops and end-state stops). Exact under the router's rules, nothing stricter:
     - the origin can walk on arrival (one footpath, or one to a walk-in point plus one onward), then board after
       `off` (MIN_TRANSFER after alighting, 0 at the search's start);
     - an arrival by ride can walk the same way; boarding after any arrival waits MIN_TRANSFER;
     - a trip once boarded is ridden on (staying aboard needs no transfer);
     - every stop a ride or walk touches adds its owed-state bit.
   No horizon, no round cap, no first-departure rule: the scan runs to the deadline. Labels are (time, mask); one
   is dropped only when another at the same stop and of the same kind is no later and holds every one of its bits.
   tail_mip.py's Python scan_py is the reference for this, line for line (tail_mip.py --selftest checks both). */
#include <stdlib.h>
#include <string.h>

typedef long long M64;
typedef struct { double t; M64 m; } Lab;
typedef struct { Lab *v; int n, cap; } LV;
typedef struct { M64 *v; int n, cap; } IV;

static int N_ = 0, NT_ = 0;
static LV *AL, *WL, *BL;          /* per stop: arrivals by ride (may walk on), arrivals on foot, board-ready */
static IV *TM;                    /* per trip: masks of everyone aboard */
static int *tS, ntS, *tT, ntT;
static unsigned char *mS, *mT;

int hs_init(int N, int NT) {
    N_ = N; NT_ = NT;
    AL = calloc(N, sizeof(LV)); WL = calloc(N, sizeof(LV)); BL = calloc(N, sizeof(LV));
    TM = calloc(NT > 0 ? NT : 1, sizeof(IV));
    tS = malloc(sizeof(int) * N); tT = malloc(sizeof(int) * (NT > 0 ? NT : 1));
    mS = calloc(N, 1); mT = calloc(NT > 0 ? NT : 1, 1);
    ntS = ntT = 0;
    return (AL && WL && BL && TM && tS && tT && mS && mT) ? 0 : -1;
}

static void touchS(int s) { if (!mS[s]) { mS[s] = 1; tS[ntS++] = s; } }
static void touchT(int t) { if (!mT[t]) { mT[t] = 1; tT[ntT++] = t; } }

static int lv_add(LV *L, double t, M64 m) {
    for (int i = 0; i < L->n; i++) if (L->v[i].t <= t && (m & ~L->v[i].m) == 0) return 0;
    int k = 0;
    for (int i = 0; i < L->n; i++) if (!(t <= L->v[i].t && (L->v[i].m & ~m) == 0)) L->v[k++] = L->v[i];
    L->n = k;
    if (L->n == L->cap) { L->cap = L->cap ? 2 * L->cap : 4; L->v = realloc(L->v, sizeof(Lab) * L->cap); }
    L->v[L->n].t = t; L->v[L->n].m = m; L->n++;
    return 1;
}

static int iv_add(IV *L, M64 m) {
    for (int i = 0; i < L->n; i++) if ((m & ~L->v[i]) == 0) return 0;
    int k = 0;
    for (int i = 0; i < L->n; i++) if ((L->v[i] & ~m) != 0) L->v[k++] = L->v[i];
    L->n = k;
    if (L->n == L->cap) { L->cap = L->cap ? 2 * L->cap : 4; L->v = realloc(L->v, sizeof(M64) * L->cap); }
    L->v[L->n++] = m;
    return 1;
}

/* scan-wide inputs */
static const M64 *sbit; static const int *fptr, *fto; static const double *fw;
static const unsigned char *outp, *virt;
static double MT, OFF; static int B;
static int cap_, nout_, over_; static int *os_; static double *ot_; static M64 *om_; static int *ok_;

static void out(int s, double t, M64 m, int kind) {
    if (nout_ >= cap_) { over_ = 1; return; }
    os_[nout_] = s; ot_[nout_] = t; om_[nout_] = m; ok_[nout_] = kind; nout_++;
}

static void walk_arr(int j, double t, M64 m, double rdy, int kind) {
    if (!lv_add(&WL[j], t, m)) return;
    touchS(j);
    if (outp[j]) out(j, t, m, kind);
    lv_add(&BL[j], t + rdy, m);
}

static void ride_arr(int u, double t, M64 m, int origin) {
    if (!lv_add(&AL[u], t, m)) return;
    touchS(u);
    if (outp[u]) out(u, t, m, origin ? 2 : 0);
    lv_add(&BL[u], t + (origin ? OFF : MT), m);
    for (int f = fptr[u]; f < fptr[u + 1]; f++) {
        int j = fto[f]; double w = fw[f]; M64 mm = m | sbit[j];
        double rdy = origin ? OFF : MT; int kd = origin ? 3 : 1;
        walk_arr(j, t + w, mm, rdy, kd);
        if (virt[j])
            for (int f2 = fptr[j]; f2 < fptr[j + 1]; f2++) {
                int j2 = fto[f2]; if (j2 == j) continue;
                walk_arr(j2, t + w + fw[f2], mm | sbit[j2], rdy, kd);
            }
    }
}

/* kind per output: 0 arrived by ride, 1 on foot, 2 the origin itself, 3 on foot from the origin (2 and 3 are ready
   after `off`, the rest after MIN_TRANSFER) */
int hs_scan(int nsrc, const int *srcs, double t, double off, double D, double mt,
            int nc, const double *dep, const double *arr, const int *cf, const int *ct, const int *trip,
            const M64 *sbit_, const unsigned char *outp_, const unsigned char *virt_,
            const int *fptr_, const int *fto_, const double *fw_,
            int cap, int *os, double *ot, M64 *om, int *ok) {
    sbit = sbit_; outp = outp_; virt = virt_; fptr = fptr_; fto = fto_; fw = fw_;
    MT = mt; OFF = off; B = nsrc ? srcs[0] : -1;
    cap_ = cap; nout_ = 0; over_ = 0; os_ = os; ot_ = ot; om_ = om; ok_ = ok;
    for (int i = 0; i < nsrc; i++) ride_arr(srcs[i], t, sbit[srcs[i]], 1);   /* several origins at once: free start */
    int lo = 0, hi = nc;
    while (lo < hi) { int md = (lo + hi) / 2; if (dep[md] < t) lo = md + 1; else hi = md; }
    M64 tmp[256];
    for (int k = lo; k < nc; k++) {
        if (dep[k] > D) break;
        int u = cf[k], tr = trip[k];
        LV *bl = &BL[u];
        for (int i = 0; i < bl->n; i++)
            if (bl->v[i].t <= dep[k]) { if (iv_add(&TM[tr], bl->v[i].m)) touchT(tr); }
        IV *tm = &TM[tr];
        if (tm->n == 0) continue;
        int v = ct[k];
        for (int i = 0; i < tm->n; i++) tm->v[i] |= sbit[v];
        if (arr[k] > D) continue;
        int n = tm->n < 256 ? tm->n : 256;
        memcpy(tmp, tm->v, sizeof(M64) * n);
        for (int i = 0; i < n; i++) ride_arr(v, arr[k], tmp[i], 0);
    }
    for (int i = 0; i < ntS; i++) { int s = tS[i]; AL[s].n = WL[s].n = BL[s].n = 0; mS[s] = 0; }
    for (int i = 0; i < ntT; i++) { int x = tT[i]; TM[x].n = 0; mT[x] = 0; }
    ntS = ntT = 0;
    return over_ ? -1 : nout_;
}
