/* Connection Scan inner loop for time_router.TimeRouter.finish().
   Mirrors TimeRouter.scan(): one-hop footpaths, MIN_TRANSFER between vehicles (0 to stay on a trip),
   footpaths relaxed when a RIDE improves a stop (see `ride[]` below, not when it improves best[]),
   stop scanning SCAN_SLACK after the first target is reached. is_target 2 = a state target's stop: a footpath that
   crosses a state line (foot_x) can't land on it, so a state is collected by a ride (or a border walk-in stop, 1). Build: cc -O3 -shared -fPIC csa.c -o csa.so */
#include <stdlib.h>
#include <string.h>
#include <math.h>

int csa_scan(int n_conn, const double *dep, const double *arr, const int *cfrom, const int *cto, const int *ctrip,
             int start_k, int n_stops, int n_trips,
             const int *foot_ptr, const int *foot_to, const double *foot_w, const unsigned char *foot_x,
             double *best, int *ltrip, const unsigned char *is_target,
             double min_transfer, double slack,
             int *pconn, int *pwalk, double *pwalk_t, int *trip_bstop, double *trip_bdep)   /* may all be NULL */
{
    unsigned char *reached = (unsigned char *)calloc((size_t)n_trips, 1);
    double *init = (double *)malloc(sizeof(double) * (size_t)n_stops);
    double *ride = (double *)malloc(sizeof(double) * (size_t)n_stops);   /* earliest arrival BY A RIDE */
    if (!reached || !init || !ride) { free(reached); free(init); free(ride); return -1; }
    memcpy(init, best, sizeof(double) * (size_t)n_stops);
    for (int s = 0; s < n_stops; s++) ride[s] = INFINITY;
    for (int s = 0; s < n_stops; s++) {            /* one walking hop from the starting labels */
        if (isinf(init[s])) continue;
        for (int e = foot_ptr[s]; e < foot_ptr[s + 1]; e++) {
            int j = foot_to[e]; double t = init[s] + foot_w[e];
            if (foot_x[e] && is_target[j] == 2) continue;
            if (t < best[j]) { best[j] = t; ltrip[j] = -1; if (pconn) { pconn[j] = -1; pwalk[j] = s; pwalk_t[j] = init[s]; } }
        }
    }
    double target_best = INFINITY;
    for (int k = start_k; k < n_conn; k++) {
        double dt = dep[k];
        if (dt > target_best + slack) break;
        int trip = ctrip[k], a = cfrom[k];
        if (!reached[trip]) {
            double ba = best[a];
            if (isinf(ba)) continue;
            double need = (ltrip[a] == trip) ? 0.0 : min_transfer;
            if (ba + need <= dt) { reached[trip] = 1; if (pconn) { trip_bstop[trip] = a; trip_bdep[trip] = dt; } } else continue;
        }
        int b = cto[k]; double at = arr[k];
        /* Footpaths are relaxed when a RIDE newly improves this stop, not when it improves best[].
           Walks do not chain (one hop), so a walk-derived label at b must not suppress the onward walk
           that a ride arriving at b would license. Memphis, Tue 6 Oct: a 57 min proxy link puts Holmes at
           21:02:13 while the MATA bus arrives 21:07:26, so `at < best[b]` failed, this whole block was
           skipped, and the 1142 s walk over the Mississippi line was never relaxed. The state went
           uncollectable because a faster arrival shadowed a slower one. best[b] <= ride[b] always, so
           every case that relaxed before still relaxes: this only adds the shadowed ones. */
        int fresh_ride = at < ride[b];
        if (fresh_ride) ride[b] = at;
        if (at < best[b]) {
            best[b] = at; ltrip[b] = trip;
            if (pconn) { pconn[b] = k; pwalk[b] = -1; }
            if (is_target[b] && at < target_best) target_best = at;
        }
        if (fresh_ride) {
            for (int e = foot_ptr[b]; e < foot_ptr[b + 1]; e++) {
                int j = foot_to[e]; double t = at + foot_w[e];
                if (foot_x[e] && is_target[j] == 2) continue;
                if (t < best[j]) { best[j] = t; ltrip[j] = -1; if (pconn) { pconn[j] = -1; pwalk[j] = b; pwalk_t[j] = at; } }
            }
        }
    }
    free(reached); free(init); free(ride);
    return 0;
}

/* Reverse Connection Scan for backward.py / build_backward.py (mirrors backward.backward_layer).
   latest[] comes in holding the next layer's latest times (-INF elsewhere) and goes out holding the latest time
   at every stop from which the next layer is still reached. Walks: one hop onto a boarding or off a ride, over
   the reversed footpaths (rev_*); rev_x marks a walk that crosses a state line, refused onto the next layer's
   stops when guard is set. ns_stop/ns_dep: per trip, a next-layer stop where staying aboard needs no transfer.
   ok_dep (out, -INF = never usable): per trip, the latest departure at which it still gets there in time. */
int csa_rev(const double *dep, const double *arr, const int *cfrom, const int *cto, const int *ctrip, int k0, int k1,
            int n_stops, const int *rev_ptr, const int *rev_from, const double *rev_w, const unsigned char *rev_x,
            double *latest, int guard, const int *ns_stop, const double *ns_dep, double min_transfer, double *ok_dep)
{
    double *init = (double *)malloc(sizeof(double) * (size_t)n_stops), *board = (double *)malloc(sizeof(double) * (size_t)n_stops);
    if (!init || !board) { free(init); free(board); return -1; }
    memcpy(init, latest, sizeof(double) * (size_t)n_stops);
    for (int s = 0; s < n_stops; s++) {
        board[s] = -INFINITY;
        if (isinf(init[s])) continue;
        for (int e = rev_ptr[s]; e < rev_ptr[s + 1]; e++) {
            if (guard && rev_x[e]) continue;
            int j = rev_from[e]; double t = init[s] - rev_w[e];
            if (t > latest[j]) latest[j] = t;
        }
    }
    for (int k = k1; k >= k0; k--) {
        int tr = ctrip[k];
        if (isinf(ok_dep[tr])) {
            int b = cto[k];
            if (arr[k] <= latest[b] || (ns_stop[tr] == b && arr[k] <= ns_dep[tr])) ok_dep[tr] = dep[k]; else continue;
        }
        int a = cfrom[k]; double t = dep[k] - min_transfer;
        if (t > board[a]) {
            board[a] = t;
            if (t > latest[a]) latest[a] = t;
            for (int e = rev_ptr[a]; e < rev_ptr[a + 1]; e++) {
                int j = rev_from[e]; double u = t - rev_w[e];
                if (u > latest[j]) latest[j] = u;
            }
        }
    }
    free(init); free(board);
    return 0;
}
