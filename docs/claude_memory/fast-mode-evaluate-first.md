---
name: fast-mode-evaluate-first
description: "Nick wants \"does this chain work\" answered by evaluating a fixed order (seconds), not a 25-min search; real searches get --patience"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1387d40c-fb7a-47b1-b50d-e5afcc5f69f7
  modified: 2026-10-01T21:23:52.916Z
---

When Nick asks whether a specific chain or ordering works, or what it does to the total, run `time_search.py ... --budget 0` with that order as `--seed-states` (plus pins and `--fixed-start` where needed). That only evaluates, repairs and prunes the seed, so it takes seconds on a warm router. Use a full search only for "find the best route of this shape", and always pass `--patience 240`–`300` so it stops once it plateaus.

**Why:** on Oct 1 2026 he was frustrated that testing three routes took over an hour. Most of that was fixed 25-min budgets on questions that needed one evaluation.

**How to apply:** default to evaluation, and still keep one search at a time. Related: [[stay-responsive-during-runs]], [[limit-search-workers]].
