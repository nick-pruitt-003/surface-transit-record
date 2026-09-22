"""Gate for the route X cloud job: X's own order from Sheridan 22:20 must evaluate at 239.50 h on this router. Leaf script."""
from datetime import date
from time_router import cached_router
from pick import gate
R = cached_router(date(2026, 9, 24), 20)
names = ['Wyoming', 'Montana', 'Arizona', '@Albuquerque Bus Station', 'Louisiana', 'Florida', 'Maine', 'Vermont',
         'West Virginia', 'Kentucky', 'Michigan', 'North Dakota', 'Nebraska', 'Arkansas', 'Mississippi']
order = [n if n.startswith('@') else R.state_names.index(n) for n in names]
she = [i for i, n in enumerate(R.stop_name) if n == 'Sheridan WY Taco Bell 1655 Coffeen Ave (Jefferson)']
t = 1790445600.0  # Sat Sep 26 22:20 MDT, X's first bus
gate('route X from Sheridan 22:20 on this router', lambda: min((R.finish(s, t, order) - t) / 3600 for s in she), 239.50, 0.01)
