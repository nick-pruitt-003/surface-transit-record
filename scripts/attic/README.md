# attic

Scripts for designs that are ruled out or retired. Nothing outside this folder imports them. They are kept so
the experiments in `docs/HANDOFF.md` can be re-run.

- **Ordering search** (searches orderings of the 48 states, superseded by `ride_search.py`; see CLAUDE.md):
  `build_backward`, `dfs_backward` and the diagnostics `bound_probe`, `dump_diag`, `tail_diag`, `tail_track`,
  `half_probe`, `reach_probe`, `rollout_probe`, `est_probe`.
- **Distance pipeline** (the first pass, before the timetable router): `prep_amtrak_speeds`, `prep_local`,
  `build_graph`, `solve`, `report`, `xlsx`.
- **HT itinerary** (`ht_itinerary`): HT re-searches to 244.2 h on the Oct 5-6 data.
- **Cloud queues** (`cloud_*.sh`, `cloud_gate.py`): for the reclaimed cloud container.

They import the live modules (`common`, `time_router`, `backward`, `pick`) and use paths relative to `scripts/`,
so run them from there with the live folder on the path:

    cd scripts && PYTHONPATH=. python3 attic/<script>.py ...
