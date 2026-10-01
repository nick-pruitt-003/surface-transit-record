---
name: stay-responsive-during-runs
description: Never block the conversation waiting on long searches/builds; background them and keep working or answering
metadata: 
  node_type: memory
  type: feedback
  originSessionId: abd82cc4-031f-4ccb-ae83-0926900c1607
  modified: 2026-09-22T16:25:06.628Z
---

Long bus48 runs (searches, table builds, profiles) must go to the background (run_in_background, Monitor, or a subagent watching them). Do not issue foreground `until ...; do sleep` waits that make me unreachable.

**Why:** Nick is fine with long tests but not with me going silent during them; subagents and background tasks exist so iteration continues while runs finish.

**How to apply:** launch run in background → give status → keep doing useful work (read logs so far, prep next step, answer questions). Use completion notifications, not blocking waits. Related: [[use-typesafe-skill]]
