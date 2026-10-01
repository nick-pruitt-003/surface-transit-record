---
name: use-homebrew-python
description: Run bus48 scripts with /opt/homebrew/bin/python3; bare python3 can resolve to system python without numpy
metadata:
  node_type: memory
  type: reference
  originSessionId: abd82cc4-031f-4ccb-ae83-0926900c1607
  modified: 2026-09-22T17:57:50.810Z
---

bus48 scripts need numpy, which is installed for Homebrew Python 3.14 at `/opt/homebrew/bin/python3`. In some sessions `PATH` resolves `python3` to `/usr/bin/python3` (no numpy), and every script dies at `import numpy` in under a second, which looks like a search failure in the logs.

Use the absolute interpreter path in queue scripts (`out/longruns.sh`, `out/rank_matrix.sh`) and any nohup'd run. Related: [[stay-responsive-during-runs]]
