---
name: use-typesafe-skill
description: Nick wants the TypeSafe (typesafe-ai) skill used when working on bus48
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1ec36f0c-034c-42ee-976d-fea64a8b64d4
  modified: 2026-09-21T21:02:26.503Z
---

On the bus48 project, load the `typesafe:typesafe-ai` skill (plugin `typesafe@typesafe-ai`, installed 2026-09-21) whenever a task needs semantic judgment rather than exact computation.

**Why:** Nick asked for it explicitly on 2026-09-21, right after installing the fast-jev-compaction plugin (which also uses TypeSafe's Jev model).

**How to apply:** the router and search (time_router.py, time_search.py, csa.c) are exact timetable math and stay plain code. Candidate TypeSafe uses are fuzzy matching of stop names across feeds, reading carrier timetable pages or screenshots into extra_trips.csv rows, and triaging which placeholder-time trips could matter to the route. Calls need TYPESAFE_API_KEY, which Nick sets himself; never ask for the key in chat.
