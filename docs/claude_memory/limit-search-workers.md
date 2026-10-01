---
name: limit-search-workers
description: "bus48 searches must run with few workers (default 1) so they don't eat the Mac's memory"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 384ff0cf-9d75-4ef3-83dd-102fefea50d2
  modified: 2026-09-23T13:06:29.849Z
---

Run bus48 searches (time_search.py, forward_shapes.py, anything spawning workers) with `--workers 1` by default, never 3, and never load a second router while one is running unless swap has plenty free.

**Why:** Nick uses the Mac while searches run; 3 workers plus an extra router load pushed free swap under 1 GB and stalled other work. He stopped a launch on Sep 23 2026 to say "don't use all my memory, limit the workers".

**How to apply:** default `--workers 1`; go to 2 only if Nick says the machine is free. Check `sysctl vm.swapusage` before launching, and keep one search at a time. Related: [[stay-responsive-during-runs]].

Sep 23 2026: even one worker plus Teams froze the Mac, and Nick had me kill everything. During calls or heavy use, run nothing locally; offer the cloud instead.
