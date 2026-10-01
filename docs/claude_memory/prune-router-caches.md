---
name: prune-router-caches
description: "bus48 router caches (~650 MB each) filled the disk twice; keep at most 2, check disk before launching"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1387d40c-fb7a-47b1-b50d-e5afcc5f69f7
  modified: 2026-09-28T18:17:38.922Z
---

Keep at most 2 `out/router_*.pkl` caches. `cached_router` now prunes to `BUS48_ROUTER_CACHES` (default 2) by last use before writing a new one (committed after LX2's regress, Sep 28 2026).

**Why:** every edit to `data/`, `time_router.py` or `common.py`, and every new date window, writes a fresh ~650 MB cache and the old ones are never valid again. They filled the disk on Sep 27 and Sep 28; the Mac slowed down and swap had nowhere to go, since macOS keeps swap on the same disk.

**How to apply:** before launching any local run, check `df -h /System/Volumes/Data` and `sysctl vm.swapusage`. Under ~5 GB disk free, delete all but the newest cache first. Don't rely on the pruning alone when running one-off router loads. Related: [[limit-search-workers]].
