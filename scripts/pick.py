"""Two helpers for the two mistake shapes HANDOFF 16 counts six of eight errors in.

choose()  never pick one element of a set silently. It returns the winner and prints the runner-up and the
          gap, so "chose Marks 06:25, runner-up MS line at Holmes 06:26, gap 60 s" is on screen the first
          time it happens instead of three turns later. `cands[0]`, argmin over a state's stops, sorted() of a
          covered-set and `stops_matching(x)[0]` were all this.

gate()    never print a verdict before the known answer reproduces. A probe calls it on the control first and
          exits if the control does not come back as expected, so nothing it prints afterwards can be a fact
          about a broken harness. Four IMPOSSIBLE verdicts went out before anything checked the control.

Leaf module, no router import: the A0 tests exercise it in milliseconds.
"""


def choose(items, key, label, show=str, out=print, quiet=False):
    """The item with the smallest key, reported against the runner-up. Raises on an empty set rather than
    returning None, because an empty candidate set reaching a pick is itself the bug worth seeing."""
    items = list(items)
    if not items:
        raise ValueError(f'{label}: nothing to choose from')
    ranked = sorted(items, key=key)
    best = ranked[0]
    if not quiet:
        if len(ranked) == 1:
            out(f'{label}: {show(best)} (only candidate)')
        else:
            k0, k1 = key(best), key(ranked[1])
            tie = '  TIE' if k0 == k1 else ''
            out(f'{label}: chose {show(best)}, runner-up {show(ranked[1])}, gap {_gap(k0, k1)}{tie}')
    return best


def _gap(a, b):
    try:
        return f'{b - a:.4g}'
    except TypeError:          # tuple keys: report the first element that differs
        for x, y in zip(a, b):
            if x != y:
                try: return f'{y - x:.4g}'
                except TypeError: return f'{x!r} -> {y!r}'
        return '0'


def gate(name, fn, expected, tol, out=print):
    """Run fn(), require it within tol of expected, and stop the program otherwise. Returns the value."""
    got = fn()
    if got is None or abs(got - expected) > tol:
        raise SystemExit(f'GATE FAILED {name}: expected {expected} +/- {tol}, got {got}. '
                         f'Nothing after this line would be a fact about the timetable.')
    out(f'gate {name}: {got:.4g} (expected {expected} +/- {tol})')
    return got
