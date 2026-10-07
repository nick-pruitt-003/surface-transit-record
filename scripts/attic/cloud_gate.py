"""Gate for a cloud container: the control must evaluate at 237.34 h on the router this container builds. Leaf script."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from time_router import cached_router
from common import ABBR
from pick import gate
R = cached_router(date(2026, 9, 24), 20)
inv = {v: k for k, v in ABBR.items()}
ab = 'WV KY OH MI IN IL TN MS AR MO IA NE SD ND MN WI WY MT ID WA OR UT AZ NV CA NM CO KS OK TX LA AL FL GA SC NC VA MD DE PA NJ NY CT RI MA ME NH VT'.split()
full = [R.state_names.index(inv[x]) for x in ab]
hun = [i for i, n in enumerate(R.stop_name) if n == 'Huntington Bus Stop']
t = datetime(2026, 9, 24, 0, 54, tzinfo=ZoneInfo('America/New_York')).timestamp()
gate('control from Huntington 00:54 on this router', lambda: min((R.finish(h, t, full) - t) / 3600 for h in hun), 237.34, 0.01)
