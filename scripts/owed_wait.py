"""Expected wait to get INTO each state, from the router's own connections (ride_search --owed-cost).

For each state y, the arrival times of every connection that crosses into y from another state (flights and
drives alike) over one week. A chain that turns up at a uniformly random time waits on average sum(gap^2) /
(2 * week) for the next way in, so a country with one flight a week costs ~84 h and one with a flight every
hour ~0.5 h. Exact from the timetable, no thresholds; it is a ranking term only and never prunes.
Units: hours, one per state index."""
import numpy as np

WEEK = 7 * 86400


def owed_wait(R, n_states, week0=None):
    if week0 is None:                               # the second week of the router's window, in its epoch seconds
        import calendar
        week0 = calendar.timegm(R.d0.timetuple()) + 7 * 86400
    st = np.asarray(R.state)
    sf, stt = st[np.asarray(R.cfrom)], st[np.asarray(R.cto)]
    arr = np.asarray(R.arr)
    m = (stt >= 0) & (stt != sf) & (arr >= week0) & (arr < week0 + WEEK)
    W = np.full(n_states, WEEK / 2 / 3600.0)          # no way in at all that week: half a week, the worst case
    ys, ts = stt[m], arr[m] - week0
    order = np.lexsort((ts, ys)); ys, ts = ys[order], ts[order]
    cut = np.flatnonzero(np.diff(ys)) + 1
    for g in np.split(np.arange(len(ys)), cut):
        if not len(g): continue
        t = np.unique(ts[g]).astype(float)
        gaps = np.diff(np.concatenate([t, [t[0] + WEEK]]))     # wraps the week round
        W[ys[g[0]]] = (gaps ** 2).sum() / (2 * WEEK) / 3600.0
    return W
