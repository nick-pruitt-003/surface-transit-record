# Every route at or under the record

Record: **238.83 h** (White River Junction → Huntington). Six of our routes beat it, all re-evaluated on the
corrected data of Oct 1 2026 (repaired trips, per-stop time zones, the TOML manual trips, new feeds). The full
leg tables, waits and connection lists are generated into [`routes_data.md`](routes_data.md) by
`scripts/route_report.py`; rerun it whenever the data changes.

| route | hours | start | finish | family |
|---|---|---|---|---|
| **Wheeling** | **234.24** | Wheeling WV, Ohio Coach 04:00 (03:00 verified: 235.24) | VT line from Hanover, Sat 22:14 | WV → VT |
| **RX** | **234.75** | Primm NV, Thu 10:50 (702 Shuttles; Las Vegas 10:00 Greyhound: 235.58) | Sheridan WY (JL 702 from Billings), Sun 06:35 | X with the West at the end; found by the unguided sweep |
| **Control** | **237.24** | Huntington WV, Thu 01:00 | VT line from Hanover, Sat 22:14 | WV → VT |
| **MEX** | **237.75** | Huntington WV, Tue 01:00 | Portland ME, Thu 22:45 | WV → ME |
| **X_TOL** | **237.91** | Sheridan WY, Thu 22:20 | VT line from Hanover, Sun 22:14 | WY → VT |
| **X** | **238.11** | Sheridan WY, Sat 22:20 | MS line at Southaven, Tue 21:26 | WY → MS |

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
