---
name: beat-237-needs-new-shape
description: "Nick's direction on bus48 — no tweak of the 237.3 route beats it; only radically different routes (new ends, orders built from scratch) are worth compute"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 384ff0cf-9d75-4ef3-83dd-102fefea50d2
  modified: 2026-09-22T19:29:18.628Z
---

Nick (2026-09-22): "there is no tinkering to 237.3 that will make it faster, any changes that get us below will look radically different." He called a run of rotations of the control's state order (forward_shapes + time_search follow-ups) "pointless", and it was cancelled along with its cloud routine.

**Why:** a rotation or local edit keeps the control's order, which was built for a WV start / VT end; a route with other ends (e.g. NM→CA) has a completely different order. Same idea as CLAUDE.md's "never seed new end points from old routes".

**How to apply:** don't propose runs that start from or perturb the 237.3 order to find something faster. To look for a faster route, build orders from scratch per start/end pair using the router itself, and gate the builder by checking it rediscovers ~237 on Huntington→VT. Checks that 237.3 is *valid* (e.g. the proxy-free search) are a separate question and still worth running.
