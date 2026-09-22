# Forced corridors: where geography makes one decision out of several legs

Nick's hand-routing claims, tested against the router rather than built in. Measured 2026-09-22 on the
run-1 settings' router (cached, 2026-09-24, 20 days).

## Pacific Northwest: Spokane - Pasco - Hermiston/La Grande - Salt Lake City, either direction

Claim: the only efficient way to collect WA, OR and ID, at least five hours faster than any alternative.

`scripts/corridor_probe.py`: from Spokane, Salt Lake City and Boise, every 2 h across day 5, route every
order of WA OR ID plus the same orders forced through Portland or Seattle; class each route by whether it
touches a stop within 15 km of Pasco, Hermiston or La Grande (including rides passing through).

- The corridor is the fastest way in **all 36** start (area, time) cases.
- Gap to the best route avoiding it: +20.8 h from Spokane at most times, +7 to +31 h from Salt Lake City and
  Boise, and at several start times no avoiding route exists at all.
- Under five hours in 4 of 36: +4.6 h (Spokane, noon to 16:00) and +4.3 h (Boise 10:00). All four are start
  times that just miss the corridor's own daily service, so the corridor itself takes 25-28 h there.
- Best orders: WA OR ID from Spokane, ID OR WA from Salt Lake City and Boise. Every non-corridor route that
  finished went via Seattle; forcing Portland never won.
- Caveat: "avoiding" covers the router's earliest route per order plus forced Portland/Seattle detours, not
  every conceivable route.

Why it matters for ride_search: the corridor is one decision worth three states, but the menu offers it a leg
at a time, and Spokane to Pasco on its own collects one state in a few hours. That is the leg CLAUDE.md lists
as buried by the old ranking. The 237 control takes it north to south: Spokane 109.0 h, Pasco 111.7 h (pair
margin +1.9 h, 20 states held, the whole East still owed), Salt Lake City 124.0 h, Saint George 133.8 h.

Suggestion, for whoever holds ride_search.py: offer the corridor as a composite move (Spokane to Salt Lake
City, or the reverse, as one option collecting WA OR ID) so slack ranking scores its value the way it scores
the Silver Meteor's four states. Gate it with the control replay; it must not remove any leg.

## Salt Lake City exits (exit_probe.py)

From a node at Salt Lake City, the earliest route to each of Pocatello, Boise, Pasco, Saint George, Las
Vegas, West Wendover, Cheyenne and Denver, crediting states passed, then the pair test. On the live
`--pairs push` chain (Salt Lake City 117.3 h, 27 held, arrived from Cheyenne adding CO IA NE, pair margin
+6.4 h standing there) **every exit is dead** on its earliest route (-11.9 to -24.8 h; West Wendover -17.8 h
despite being 2.8 h away). A chain reaching Salt Lake City at 117 h owing LA TX FL ME NH and the Dakotas is
already lost in every direction: the problem is upstream of the exit, and the control reaches the region a
different way, from the north with the East still unowed.

Nick's rule (arriving from Idaho: Cheyenne, Denver or Las Vegas; from Wyoming or Colorado: Pasco or Las
Vegas; never West Wendover) is consistent with this but not yet tested on a node where some exit survives.

## Northern New England: Boston - Portland - Boston - Upper Valley, or the reverse

Claim: Boston, Portland, Boston, Upper Valley (or its reverse) always beats Boston, Upper Valley, Boston,
Portland.

Measured from South Station on d10 (Sat), every 2 h: Portland first (ending in VT) against Upper Valley first
(ending in ME). Portland first wins or ties at 11 of 12 start times (by 0 to +8.9 h, largest at 14:00-16:00),
but **not always**: leaving at 18:00 Upper Valley first is 2.4 h faster. A strong tendency, not a law. With
`--end VT` it is forced anyway, since only Portland-first ends in Vermont, which is what the control does.
