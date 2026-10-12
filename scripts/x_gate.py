"""Gate for the route X cloud job: X's own order from Sheridan 22:20 must evaluate at 239.50 h on this router. Leaf script."""
from datetime import date
from time_router import cached_router
from pick import gate
R = cached_router(date(2026, 11, 5), 20)
names = ['Wyoming', 'Montana', 'Arizona', '@Albuquerque Bus Station', 'Louisiana', 'Florida', 'Maine', 'Vermont',
         'West Virginia', 'Kentucky', 'Michigan', 'North Dakota', 'Nebraska', 'Arkansas', 'Mississippi']
order = [n if n.startswith('@') else R.state_names.index(n) for n in names]
she = [i for i, n in enumerate(R.stop_name) if n == 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)']
from datetime import datetime
from zoneinfo import ZoneInfo
# Sat Nov 7 12:00 MST, the Sep 26 clock moved +42 days with the window (the epoch constant was missed, review Oct 11).
# The 239.50 h figure is September's; Acela 2152 is off the Nov 7-13 timetable, so expect this gate to need re-measuring.
t = datetime(2026, 11, 7, 12, 0, tzinfo=ZoneInfo('America/Denver')).timestamp()
bus = t + 10 * 3600 + 20 * 60  # the 22:20 Sheridan departure; X's 239.50 h is measured from here
gate('route X from Sheridan 22:20 on this router', lambda: min((R.finish(s, t, order) - bus) / 3600 for s in she), 239.50, 0.01)
