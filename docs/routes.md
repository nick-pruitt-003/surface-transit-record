# Every route at or under the record

Record: **238.83 h** (White River Junction → Huntington). Six of our routes beat it, all re-evaluated on the
corrected data of Oct 1 2026 (repaired trips, per-stop time zones, the TOML manual trips, new feeds). The full
leg tables, waits and connection lists are generated into [`routes_data.md`](routes_data.md) by
`scripts/route_report.py`; rerun it whenever the data changes.

| route | hours | start | finish | family |
|---|---|---|---|---|
| **HT** | **230.02** (230.2 from the 06:10 walk) | Hanover NH (Ledyard Lot), Thu 06:23; Vermont on foot first | Tallahassee FL, Sat 20:25 | NH → FL; HMS without its forced Mississippi finish |
| **Wheeling** | **234.24** | Wheeling WV, Ohio Coach 04:00 (03:00 verified: 235.24) | VT line from Hanover, Sat 22:14 | WV → VT |
| **RX** | **234.75** | Primm NV, Thu 10:50 (702 Shuttles; Las Vegas 10:00 Greyhound: 235.58) | Sheridan WY (JL 702 from Billings), Sun 06:35 | X with the West at the end; found by the unguided sweep |
| **Control** | **237.24** | Huntington WV, Thu 01:00 | VT line from Hanover, Sat 22:14 | WV → VT |
| **MEX** | **237.75** | Huntington WV, Tue 01:00 | Portland ME, Thu 22:45 | WV → ME |
| **NBA** | **237.52** | New Buffalo MI (Amtrak), Wed 21:47 | Arkansas line on the Big River Crossing, Sat 18:18 | MI → AR; sweep 3, focused |
| **HAR** | **237.69** (237.9 from the 06:10 walk) | Hanover NH (Ledyard Lot), Thu 06:23; Vermont on foot first | Forrest City AR, Sun 03:05 | NH → AR; found by sweep 2, focused |
| **X_TOL** | **237.91** | Sheridan WY, Thu 22:20 | VT line from Hanover, Sun 22:14 | WY → VT |
| **X** | **238.11** | Sheridan WY, Sat 22:20 | MS line at Southaven, Tue 21:26 | WY → MS |
| **HMS** | **238.19** (238.4 from the walk) | Hanover NH (Ledyard Lot), Thu 06:23 | Biloxi MS, Sun 03:35 | NH → MS; sweep 2, focused |

## How to read the analysis

For every ride the report gives its **miss penalty**: how much later you would reach the same stop on the next
departure that gets there at all. **+24 h is a once-daily anchor.** A wait in front of an anchor is slack you can
only spend by reaching that anchor a whole day earlier, so it is not really available. Waits in front of
frequent services (a few hours of miss penalty) are the only soft spots. The **marginal cost** of a state is how
much earlier the route finishes if that state is dropped and the same order re-timed.

## Have the shapes been squeezed dry?

Mostly yes, and the numbers say why.

- **Every long wait in the WV → VT family sits in front of a once-daily anchor.** Omaha 4.8 h (Jefferson to Sioux
  Falls), Salt Lake 2.5 h (Salt Lake Express), Detroit 2.3 h (Greyhound Detroit → Indianapolis), Newton 1.2 h
  (BeeLine), Las Vegas 1.2 h (702 Shuttles), Billings 1.1 h (Jefferson to Spokane), Lake Charles 1.0 h (Houston →
  Orlando): all +24 h. None of it is spendable without moving something upstream by a full day.
- **The one soft spot was at the very start**, the control's 2.0 h in Columbus, and the Wheeling start already
  harvested it (237.24 → 234.24). That is why the Wheeling route is the same as the control from Columbus on, to
  the minute.
- **Marginal costs:** in the control family only the two ends cost anything (ME 5.0 h, VT 4.3 h) plus FL 1.5 h.
  In X and X_TOL no single state costs even a minute: anchors absorb every saving.
- **X is pinned at both ends of its middle.** The head must catch the Silver Meteor at Jacksonville Thu 16:11,
  which fixes Hanover Friday 22:00; the tail is already the fastest possible (Sat 03:00 out of Hanover, 91.4 h,
  checked over a whole week). Its 4.5 h at Hanover is the gap between them; the Dartmouth Coach is frequent
  (+1.7 h) but leaving later only waits elsewhere, because the tail's own anchors (Harrisburg 14:50, the Barons
  out of Indianapolis, Jefferson) are daily.

Where some slack is still not proven useless:

1. **X_TOL's interior** has the most waits in front of non-daily-anchor services: Columbus 4.1 h for the Barons
   to Chicago (next option +16 h), Kansas City 4.1 h (+13.9 h), Pittsburgh 2.4 h (+12.7 h), Nashville 1.8 h
   (+17.9 h), Memphis 1.2 h (+11.5 h). Each is a place where arriving later, or taking a different service, might
   save time without a day's shift. A search seeded from X_TOL's own order (same endpoints) is the way to test it.
2. **The Wisconsin block** in the WV → VT family: Minneapolis 3.9 h (next option +7.7 h) and Eau Claire 2.4 h
   (+3.1 h) are the only multi-hour waits in front of frequent services. They are absorbed downstream today
   (dropping WI saves nothing, because the Jefferson Minneapolis → Billings it returns for is daily), so a gain
   there needs a different way west, not a faster Wisconsin.
3. **New shapes rather than tweaks:** the north-entry X head (Nashville → NYC overnight, skipping the Meteor
   anchor), and a Cody ending built like X (fix Fargo 15:15 → Billings → Cody, solve the tail into Fargo, then the
   head). Both are in HANDOFF 28 as open.

## The routes

### Wheeling, 234.24 h (WV → VT)

The control with a different first hour: start at the Wheeling Jaguar stop and take the Ohio Coach to Columbus,
arriving for the same 06:50 Barons to Detroit the control sits two hours waiting for. Identical to the control from
Columbus on, finishing Sat 22:14. The 04:00 passage rests on transposed running times; the 03:00 is verified and
gives 235.24 h. Tight points: Columbus (6 min), Indianapolis (10 min), the Bellevue at Carr hop in Memphis (7 min),
Conway AR (10 min), Spokane and Pasco (15 min each).

### Control, 237.24 h (WV → VT)

Huntington 01:00 → Columbus → Detroit → Indianapolis → Effingham → City of New Orleans → Memphis (MS on foot at
Holmes) → Conway AR → Kansas City → Des Moines → Omaha → Sioux Falls → Fargo → Minneapolis → Eau Claire WI and
back → Jefferson to Billings → Spokane → Pasco → Salt Lake →
St George → Las Vegas → 702 to Victorville → Southwest Chief → Las Vegas NM → AE bus → Trinidad → Chief →
Newton → BeeLine → Oklahoma City → Dallas → RedCoach → Houston → Flix to Lake Charles → Tallahassee → Jacksonville →
Silver Meteor → Acela → Portland ME and back → Dartmouth Coach → Hanover → VT line. Ends: ME 5.0 h, VT 4.3 h.

### MEX, 237.75 h (WV → ME)

The control's body with the ending swapped: Hanover, Advance Transit to White River Junction for Vermont, the
17:55 Greyhound to Boston, Concord Coach to Portland. Half an hour slower than the control because the Vermont
round trip is longer than the Maine one (Nick's point). It needs a **weekday** in New England: on a Saturday
Advance Transit runs a reduced schedule without the 17:10 that makes the 17:55, and the route falls to 245.3 h.

### X_TOL, 237.91 h (WY → VT)

Sheridan Thu 22:20 → Billings → Spokane → Pasco → Salt Lake → Las Vegas → Barstow → Chief → Albuquerque → Newton
→ BeeLine → Heartland Flyer → Fort Worth → Texas Eagle → Longview → Shreveport → Texarkana → Nashville → Detroit
→ Pittsburgh (WV) → Columbus → Barons to Chicago → Minneapolis → Fargo → Sioux Falls → Kansas City →
Fayetteville → Memphis → Atlanta → Jacksonville → Meteor → Acela → Portland → Hanover → VT line, Sun 22:14. The loosest interior of
the five (see above).

### X, 238.11 h (WY → MS)

Sheridan Sat 22:20, the same West as the control (Salt Lake → St George → Las Vegas → 702 → Victorville → Chief),
Texas and the Gulf to the Meteor, Acela, Portland, Hanover Fri 22:00, then the tail: Dartmouth Coach 03:00 →
Boston → Regional → Harrisburg 14:50 Greyhound via Wheeling → Indianapolis → Louisville and back → Detroit →
Chicago → Minneapolis → Fargo → Sioux Falls → Kansas City → Fayetteville → Memphis → walk to the MS line, Tue 21:26.
Built today as the fastest 22-state head joined to the fastest tail (HANDOFF 28), and still the only record route
with a real tail out of Vermont.

### RX, 234.75 h (NV → WY), found Oct 2 by the unguided sweep

Not designed by anyone: the overnight sweep (`docs/sweep.md`) found its family from a mechanical seed at 240.0 h, and
a focused search moved the start to Las Vegas (235.58 h). The 702 Shuttles 10:50 from Primm NV (screenshot Oct 2) to
Barstow, walking to Barstow Station for the 12:55 Greyhound, reaches the same San Bernardino 15:10 anchor and starts
50 min later for the same finish: 234.75 h. It is **X with the West moved to the end**:

- **South first:** Primm Thu 10:50 → Barstow → San Bernardino → Greyhound across Arizona and New Mexico to Oklahoma City
  (Fri 21:15) → Memphis → Delta Bus Lines to Baton Rouge → (23:55) Tallahassee → Jacksonville → **Silver Meteor** → Acela → Boston.
- **New England:** Dartmouth Coach to Hanover → Advance Transit to White River Junction (VT) → Greyhound to Boston →
  Concord Coach to Portland ME → overnight back through Boston to New York.
- **X's tail, mostly:** Greyhound New York → Indianapolis (PA, WV, OH) → Louisville and back → South Bend (Michigan
  via a Transpo bus near the line) → Chicago → Minneapolis → Fargo → Sioux Falls → Kansas City.
- **The West last:** Kansas City → Denver → Greyhound over I-70 and through Salt Lake and Boise to Pasco → Spokane →
  Billings → **JL 702 into Sheridan** for Wyoming, Sun 06:35.

The Gulf leg as booked (Nick, Oct 2): Memphis Sat 10:00 Delta Bus Lines to Baton Rouge 18:30 (Mississippi on the way),
then Greyhound 23:55 from Baton Rouge straight through Mobile, Pensacola and Panama City Beach to Tallahassee 11:00,
and the 11:25 to Jacksonville 14:50: one Greyhound itinerary, no backtrack. `route_report.py` pins Baton Rouge, but
the router breaks the exact tie by hopping to Lafayette at 20:10 to board the same Orlando bus there at 22:35, so
`routes_data.md` and `route_legs.xlsx` show that loop; it changes nothing after Tallahassee. Other equal-time Gulf
options: Greyhound Memphis -> New Orleans, the 20:50 via Biloxi to Mobile, then the same bus at 03:45.

Risks: two hand-entered legs (Dartmouth Coach 14:30, JL 702), several 8–10 minute connections, and the Advance
Transit link at Hanover only runs on weekdays (it falls on a Monday here). Wyoming is only reached by the final
Billings → Sheridan run, since the Denver → Pasco Greyhound takes I-70, not Wyoming; a West taken the other way round
(Denver → Cheyenne → Billings → Spokane → Salt Lake) is being searched.

**Optional South Bend variant (same 234.75 h, more time in Chicago).** The router waits 1.5 h at Adams & Dylan
for the 17:52 Blackthorn back, then takes the 18:55 Greyhound to Chicago (20:05) and waits for the 22:00 to
Minneapolis. Instead: off the 15:52 Blackthorn at Adams & Dylan, about a mile on Mayflower to the Michigan line
(around 16:06), then about 6.5 miles to South Bend Airport for the **South Shore Line 16:52** (Chicago Millennium
17:55 CT, Illinois at Hegewisch). That is 7.5 miles in 60 minutes, about 7.5 mph or an 8:00 mile, and nearer
8.2 mph with five minutes to board; a ride-hail does it easily. No bus fills the gap: the Transpo stops nearest the line are all on
routes 5 and 16 (Adams & Dylan 0.90 km; FedEx Ground on Dylan 1.63 km; Auten & Oakland, Hammerschmidt and SR 933
about 1.66 km), all every two hours. Route 5's 14:33 from South Street would make it easy but leaves seven minutes
before the Miller arrives, and route 2 leaves Everwise (on Portage) at 15:57 and 16:57, either side of the window.
Miss the train and the router's plan is intact: 17:52 Blackthorn, 18:55 Greyhound. Not a time saving (the 22:00
anchor absorbs it); about 4 h in Chicago instead of 1.5 h on a rural corner.

### HAR, 237.69 h (NH → AR) and HMS, 238.19 h (NH → MS), found Oct 2 by sweep 2

Two finishes on one spine, both found by the second unguided sweep (runs 13 and 07, 239.8 and 242.1 h) and moved
under the record by focused searches, which both moved the start to Ledyard Lot in Hanover. Hours count from the
first bus (Advance Transit 06:23); the route begins with a 06:10 walk over the Vermont line and back (add 0.2 h).
Neither uses Ohio Coach.

- **New England first:** Ledyard Lot, Vermont on foot, Advance Transit → Dartmouth Coach 06:40 → Boston → Portland ME
  and back → Amtrak to Baltimore → Flix to Augusta GA → Camden SC → Charlotte → Barons to Columbus → Michigan City.
- **Michigan on foot:** Michigan City Transit, then the measured Michiana run (4.5 km out, 6.9 km back to Carroll Ave
  at Nick's running pace) → South Shore to Chicago.
- **Plains:** Chicago → Minneapolis → Fargo → Sioux Falls; Nebraska rides out to Maryville and back in the dead time
  before the once-daily 12:40 I-90 bus (measured: costs nothing), which then takes SD, WY and MT to Billings.
- **West:** Billings → Spokane → Pasco → Salt Lake → St George → Las Vegas → San Bernardino → **Southwest Chief** to
  Newton KS → BeeLine to Oklahoma City → Dallas → Houston → Tallahassee.
- **HAR finish:** Tallahassee → Birmingham → Memphis → Greyhound 02:10 to Forrest City AR, Sun 03:05.
- **HMS finish:** Memphis, the Big River Crossing walk at 06:30 (bridge hours kept) → Birmingham → Tallahassee →
  Mobile → Biloxi MS, Sun 03:35.

Risks: the Michiana run is the longest measured run in any record route; the HAR finish is a 02:10 departure.

### HT, 230.02 h (NH → FL): the fastest route we have, found Oct 2

HMS with one change. HMS's focused search had been told to finish in Mississippi, copied from where its sweep run
happened to end, so it spent its last seven hours on Tallahassee → Mobile → Biloxi. But the 09:00 Memphis →
Birmingham Greyhound stops at **Tupelo MS (10:40)**, so Mississippi comes free on a bus the route already rides, and
the route ends at Tallahassee on Saturday 20:25: **230.02 h** from the first bus (230.2 from the 06:10 walk), 4.2 h
under Wheeling, 8.8 under the record, no Ohio Coach. Everything up to Newton is HAR/HMS; from there:

- Newton → BeeLine to Oklahoma City → Heartland Flyer to Fort Worth → Texas Eagle to Longview → Amtrak bus to
  Shreveport (LA) → Greyhound to Texarkana → overnight to Memphis (03:45, Tennessee).
- **Big River Crossing walk 05:45-07:03** for Arkansas (the first walk of the day; the bridge opens at 06:00).
- Memphis 09:00 → Tupelo MS → Birmingham AL 13:25 → Tallahassee FL 20:25.

Boston → DC: stay on the 15:10 Acela to Washington Union Station (22:22) and board the same Flix there at 00:30, a
same-station connection, instead of Baltimore Penn → Baltimore downtown bus station (Nick); same 230.02 h.

Risks: the Michiana run; the 05:45 bridge walk is the first one possible and 12-minute turnarounds follow; the
Longview → Shreveport link is an Amtrak bus timed to the Texas Eagle, which waits for the train (Nick), so its
12-minute connection is not a risk.

The lesson, again: a fixed finish copied from a sweep run is a guess, not a constraint. HMS's finish cost 8.2 h.

### NBA, 237.52 h (MI → AR), found Oct 3 by sweep 3

Sweep 3 run 22 (240.5 h), focused from its real start stop with the fixed search (d90d8f0). The Hanover-spine
pieces in another order: New Buffalo → Chicago → St Paul → Minneapolis → Fargo → Sioux Falls (Nebraska in the
Maryville dead time) → I-90 bus → Billings → Spokane → Pasco → Salt Lake → Las Vegas → San Bernardino → Southwest Chief
→ BeeLine → Dallas → Houston → Tallahassee → Jacksonville → Silver Meteor → Boston → Portland ME → Hanover overnight →
Philadelphia → Harrisburg → Indianapolis → Nashville → Memphis, then the Holmes walk for Mississippi and the Big River
Crossing walk to the Arkansas line (17:45-18:18, inside the bridge hours). No Ohio Coach.

Lead: the report's marginal costs put Arkansas at 2.4 h and Mississippi at 1.7 h, both bought by the final Memphis
walks. That is the shape that turned HMS (238.19) into HT (230.02); worth a "state given free" pass.
