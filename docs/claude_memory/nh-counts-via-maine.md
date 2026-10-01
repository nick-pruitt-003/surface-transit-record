---
name: nh-counts-via-maine
description: "Nick's rule (Oct 1 2026): any route into or out of Maine counts New Hampshire, even on a bus that doesn't stop there"
metadata:
  node_type: memory
  type: project
  originSessionId: 1387d40c-fb7a-47b1-b50d-e5afcc5f69f7
  modified: 2026-10-01T20:22:36.258Z
---

Nick ruled on Oct 1 2026 that a bus between Boston and Portland ME (Concord Coach on I-95) counts as collecting New Hampshire, even though it doesn't stop there. Every land route to Maine crosses NH. A Kittery stop with a walk over to Portsmouth would also do.

**Why:** without this rule, a Maine-start route paid for a Boston → Londonderry NH → Boston detour at the end (MEW, 276.9 h).

**How to apply:** for runs that start or end in Portland ME, pass `--done NH` to `time_search.py` (start) or treat NH as covered (end). Don't apply it to routes that never go to Maine. Related: [[beat-237-needs-new-shape]].
