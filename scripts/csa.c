/* Connection Scan inner loop for time_router.TimeRouter.finish().
   Mirrors TimeRouter.scan(): one-hop footpaths, MIN_TRANSFER between vehicles (0 to stay on a trip),
   stop scanning SCAN_SLACK after the first target is reached. Build: cc -O3 -shared -fPIC csa.c -o csa.so */
#include <stdlib.h>
#include <string.h>
#include <math.h>

int csa_scan(int n_conn, const double *dep, const double *arr, const int *cfrom, const int *cto, const int *ctrip,
             int start_k, int n_stops, int n_trips,
             const int *foot_ptr, const int *foot_to, const double *foot_w,
             double *best, int *ltrip, const unsigned char *is_target,
             double min_transfer, double slack,
             int *pconn, int *pwalk, double *pwalk_t, int *trip_bstop, double *trip_bdep)   /* may all be NULL */
{
    unsigned char *reached = (unsigned char *)calloc((size_t)n_trips, 1);
    double *init = (double *)malloc(sizeof(double) * (size_t)n_stops);
    if (!reached || !init) { free(reached); free(init); return -1; }
    memcpy(init, best, sizeof(double) * (size_t)n_stops);
    for (int s = 0; s < n_stops; s++) {            /* one walking hop from the starting labels */
        if (isinf(init[s])) continue;
        for (int e = foot_ptr[s]; e < foot_ptr[s + 1]; e++) {
            int j = foot_to[e]; double t = init[s] + foot_w[e];
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
        if (at < best[b]) {
            best[b] = at; ltrip[b] = trip;
            if (pconn) { pconn[b] = k; pwalk[b] = -1; }
            if (is_target[b] && at < target_best) target_best = at;
            for (int e = foot_ptr[b]; e < foot_ptr[b + 1]; e++) {
                int j = foot_to[e]; double t = at + foot_w[e];
                if (t < best[j]) { best[j] = t; ltrip[j] = -1; if (pconn) { pconn[j] = -1; pwalk[j] = b; pwalk_t[j] = at; } }
            }
        }
    }
    free(reached); free(init);
    return 0;
}
