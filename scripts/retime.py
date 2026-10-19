"""Re-time saved routes on the current data (e.g. after adding a carrier), expanded to every state as a target.

  python3 retime.py NAME:START:AT:TZ [...]     e.g. denverV7c:Pasco:2026-11-05T12:00:America/Los_Angeles
"""
import pickle, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from time_router import TimeRouter, load_feeds
from time_search import Search
from blocker_finder import expand

feeds = load_feeds()
for arg in sys.argv[1:]:
    name, rest = arg.split(':', 1); start, rest = rest.split(':', 1); at, tz = rest[:16], rest[17:]
    t0 = datetime.fromisoformat(at).replace(tzinfo=ZoneInfo(tz)).timestamp()
    R = TimeRouter(feeds, datetime.fromisoformat(at).date(), 16); st = R.stops_matching(start)[0]; S = Search(R, st, t0, [], 1)
    saved = pickle.load(open(f'../out/res_{name}.pkl', 'rb'))
    f, legs = S.evaluate(saved['order'])
    if S.all_states(legs):
        order = expand(R, S, saved['order'], legs); f2, legs2 = S.evaluate(order)
    else: f2, legs2 = f, legs
    print(f'{name}: saved {(saved["finish"] - t0) / 3600:.1f} h -> now {(f - t0) / 3600:.1f} h (expanded {(f2 - t0) / 3600:.1f} h), all states {S.all_states(legs)}', flush=True)
    print(R.describe(legs2 if f2 <= f else legs))
