# Where every cutoff comes from

This is the "show your work" document for Closure Call. Every rule the system applies is
listed here with its source. The rules themselves live in two tables at the top of
[`closure_call/rules.py`](../closure_call/rules.py), `LADDER` and `THRESHOLDS`, so the code
and this document can be checked against each other.

Each cutoff is one of three kinds, and the kind is stated every time:

- **Official definition**: taken from the National Weather Service (NWS) or the Office of
  Personnel Management (OPM).
- **Team decision**: a choice we made, with the evidence we looked at.
- **Starting value**: a number we needed but could not calibrate in a hackathon. These are
  the first things an agency should review.

All live numbers below were measured on 2026-10-10.

## 1. The five postures are OPM's operating statuses

The system recommends one of five postures. Each is one of the standard operating status
announcements in OPM's *Governmentwide Dismissal and Closure Procedures* (December 2025,
section IV.B).

| Our posture | OPM status | OPM's wording |
| --- | --- | --- |
| 1. Normal operations | 1. Open | "Employees are expected to begin the workday on time." |
| 2. Delayed arrival | 3. Delayed Arrival | "Employees should plan to arrive for work no more than X hour(s) later than they would normally be expected to arrive." |
| 3. Early dismissal | 4. Early Departure | "agencies may need to allow employees to depart work before the end of the workday" |
| 4. Unscheduled leave or telework | 2. Open with Option for Unscheduled Leave or Unscheduled Telework | "Employees must notify the supervisor of their intent to use unscheduled leave or unscheduled telework" |
| 5. Full closure | 5. Office Closure | "The office is closed for weather/safety reasons and maximum telework is in effect." |

OPM's sixth status, Shelter-In-Place, is not modeled.

**Who decides.** OPM issues these announcements only for the Washington, DC area. Elsewhere,
section I.B says employees "must follow the operating status announcements issued by their
agency" and that "Federal field office heads generally make workforce status decisions".
That field decision is the one this system supports. It recommends a posture and never
issues one: a named person records the decision, and a written reason is required whenever
it differs from the recommendation.

## 2. Which alerts count: the Watch, Advisory, Warning ladder

Kind: **official definition** for the ladder, **team decision** for what each rung does.

The NWS issues three levels of alert for most hazards. Its glossary defines them this way:

- **Watch**: the risk "has increased significantly, but its occurrence, location, and/or
  timing is still uncertain".
- **Advisory**: conditions "less serious than a warning" that "may cause significant
  inconvenience".
- **Warning**: the event "is occurring, is imminent, or has a very high probability of
  occurring" and poses "a threat to life or property".

The system handles three hazards, chosen because all three had live alerts during the demo
window. These twelve NWS alert names are in scope:

| Hazard | Watch | Advisory | Warning |
| --- | --- | --- | --- |
| Flood | Flood Watch | Flood Advisory | Flood Warning, Flash Flood Warning |
| Wind | High Wind Watch | Wind Advisory | High Wind Warning |
| Winter | Winter Storm Watch | Winter Weather Advisory | Winter Storm Warning, Blizzard Warning, Ice Storm Warning |

What each rung does:

| Rung | Recommendation | Why |
| --- | --- | --- |
| Watch | 1, with a note to monitor | The hazard is only possible. |
| Advisory | 1, or 4 if county roads are closed or badly delayed | An advisory alone rarely closes an office. Roads are what stop people getting in. |
| Warning | 4 by default. Timing and roads can change it (sections 3 and 4). | A Warning means a threat to life or property. |

Any other active alert, such as a Tornado Warning, is shown to the manager under "not
evaluated" and never changes the posture. The system does not claim to judge hazards it has
no rules for.

## 3. The four numbers

| Cutoff | Value | Kind |
| --- | --- | --- |
| Severity that gives full closure | Extreme | Official definition |
| Hours after opening for delayed arrival | 2 | Starting value |
| Full road closures that raise 4 to 5 | 1 | Team decision |
| Major road delays that raise an Advisory to 4 | 1 | Starting value |

**Severity: Extreme gives full closure.** NWS alerts carry a severity field defined by the
Common Alerting Protocol (CAP) standard. Extreme is its top level, "extraordinary threat to
life or property". Severe, one level down, is "significant threat to life or property", and
it is what the Flood Warnings and Winter Storm Warnings we saw were rated. A Warning rated
Extreme goes straight to posture 5.

**Delayed arrival: the hazard ends within 2 hours after opening.** A Warning that ends early
in the workday gives posture 2. One that lasts longer stays at 4. OPM defines the status as
"Open - X Hour(s) Delayed Arrival" and leaves X to the decision-maker. Its own worked example
uses a 2-hour delayed arrival, so 2 is our starting value. We did not calibrate it.

**Road closures: one full closure in the county raises 4 to 5.** The team rule is that a
single full road closure means some staff cannot reach the building. Two details matter:

- *Only the facility's county counts.* County is the unit that both NWS alerts and USDA
  Service Centers use, so there is no radius to defend.
- *Only weather and incident closures count.* Alabama's state feed labels each event with a
  type. On 2026-10-10 it marked 22 events statewide as Closed:

  | Event type | Marked Closed | Counted? |
  | --- | --- | --- |
  | Facility (rest areas and similar) | 12 | No |
  | Roadwork | 4 | No |
  | Incident | 4 | Yes |
  | RoadCondition (weather and debris) | 2 | Yes |

  Counting all 22 would have let a closed rest area close an office.

A closure raises posture 4 to 5 only. It does not change delayed arrival or early dismissal.

**Major delays: one is enough under an Advisory.** An Advisory with a full closure, or with
one RoadCondition or Incident event that the state marks MajorDelay, gives posture 4. This
uses the state's own category so we do not invent a measure of "bad". The count of one is a
starting value.

## 4. Timing

Kind: **team decision**.

- A decision applies to one operating day: today if the office has not closed yet,
  otherwise the next open day.
- An alert counts only if it overlaps the rest of that day. One that ends before opening or
  starts after closing gives posture 1.
- A Warning that starts after opening, during the workday, gives posture 3, early dismissal.
- Alert times are the hazard's own times (`onset` and `ends`), not the message's
  (`effective` and `expires`). The NWS reissues messages, so `expires` is not when the
  hazard ends. When the NWS gives no end time, the hazard is treated as lasting all day.

## 5. Confidence

Kind: **official definition** for the mapping, **team decision** for the road step.

Confidence comes from the alert's CAP certainty field, then drops one step when state road
data is missing.

| NWS certainty | CAP meaning | Confidence |
| --- | --- | --- |
| Observed | Determined to have occurred or to be ongoing | High |
| Likely | More than about 50% likely | High |
| Possible | About 50% or less | Medium |
| Unlikely, Unknown | Not expected, or not stated | Low |

Example: the same Winter Storm Warning rated Likely gives High confidence where state road
data exists and Medium where it does not.

## 6. Road data: what is counted and what is only shown

**Counted: Alabama's state DOT feed.** It is open, needs no key, and labels each event with
a type and a severity, which is what makes the rule in section 3 possible.

**Unavailable: every other state.** There is no national feed for weather road closures.
Each state publishes its own. Where we have no state feed, the system says "state road data
unavailable", lowers its confidence one step, and lists road data under what would change
the recommendation.

**Shown but never counted: TomTom.** Outside Alabama the system fetches TomTom's closed road
segments for the county and shows them to the manager. They never change the posture. This
was a team decision made after looking at live data:

| County | Weather on 2026-10-10 | Closed segments in the county |
| --- | --- | --- |
| Jackson, Missouri (Kansas City) | Calm, no alerts | 134 |
| Clark, Nevada (Las Vegas) | Calm | 56 |
| Coffee, Alabama | Flood Warning | 124 |
| Park, Montana | Winter storm starting that evening | 3 |

Two things rule out counting them:

1. Calm places list many closures. With a cutoff of one, Kansas City would be recommended
   for full closure under any Warning.
2. TomTom gives no cause. Every closure reads only "Closed", so weather closures cannot be
   separated from construction, which is exactly what the Alabama rule depends on.

One thing we did not resolve: on the same morning Alabama's feed listed no counted closures
in Coffee County, while TomTom listed 124 closed segments there. The two sources measure
different things, and we did not reconcile them.

## 7. Who gets notified

Kind: **team decision**, anchored to OPM where OPM speaks to it.

The rule is that who is expected at the building today decides the list, not who is
assigned to it. The building roster and the assignment roster are different lists.

| Person | What they get | Anchor |
| --- | --- | --- |
| Expected at the building today, assigned here or detailed here | The posture message, by text and email | Action is needed before the commute. |
| Essential personnel expected at the building | A separate message: report as scheduled | OPM: "Emergency employees are expected to report to or remain at their worksite unless otherwise directed by their agencies." |
| Already teleworking today | An email for information, with no early text | OPM: employees "regularly scheduled to telework that day are expected to begin work on time". |
| Assigned here but on detail elsewhere | Nothing | They are not affected. |

Every person on the roster appears in the package with the reason they were included or
left out. An accessibility flag switches the text to a voice call. The system drafts and
routes messages. It does not send them.

## 8. AI wording: what Claude may and may not do

Kind: **team decision**.

No model decides anything. The posture, the thresholds, the confidence and the recipient
list all come from the rules above. Claude (`claude-opus-5-5`) is used for one optional step:
rewording the rationale and the message drafts.

| Guardrail | How it is enforced |
| --- | --- |
| Claude sees only verified text | The request contains the template text and the names to keep, nothing else. |
| No invented numbers | Every number or time in a rewrite must already appear in its template. |
| No dropped times | Every clock time in the template must appear in the rewrite. |
| Names kept | The status name, alert name and facility name must appear in the rewrite. |
| Fail safe | A piece that fails a check keeps its template wording, and the screen lists why. With no key, or if the API fails or declines, the templates are used. |
| Accountable | The manager reads the wording before recording, and the record states whether Claude or the template wrote the rationale and the messages. |

The checks are in [`closure_call/drafting.py`](../closure_call/drafting.py) and are tested
without calling the API. On 2026-10-10 a live call reworded one rationale and three messages
in about 9 seconds, and all four passed.

## 9. Known limits

- The 2-hour delayed arrival window and the single major delay are starting values.
- The synthetic facility is open seven days a week so that a weekend demo evaluates the
  current day. Real Service Centers open Monday to Friday. Federal holidays are not modeled.
- Alerts are matched to the facility's exact coordinates. A river Flood Warning covers the
  river's reach, not the whole county, so a facility elsewhere in the county is not under it.
- Hazards outside flood, wind and winter are displayed and not evaluated.
- State road data exists for Alabama only.
- The decision record makes edits evident. It cannot stop someone who rebuilds the whole
  file, and removing the newest records leaves a valid shorter chain. A real deployment
  would anchor the fingerprints somewhere the record keeper cannot write.
- The roster is synthetic, and each person's status for the day is a fixed field.
- The wording checks catch new numbers, dropped times and dropped names. They cannot catch a
  change of meaning that uses none of those. A person reading the draft is the last check.

## Sources

- OPM, *Governmentwide Dismissal and Closure Procedures*, December 2025:
  <https://www.opm.gov/policy-data-oversight/pay-leave/reference-materials/handbooks/dcdismissal.pdf>
- NWS glossary, Watch, Advisory and Warning:
  <https://forecast.weather.gov/glossary.php?word=warning>
- NWS, "Watch Warning Advisory Explained":
  <https://www.weather.gov/sjt/WatchWarningAdvisoryExplained>
- NWS API documentation: <https://www.weather.gov/documentation/services-web-api>
- OASIS, Common Alerting Protocol version 1.2, severity and certainty fields:
  <http://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html>
- Alabama DOT traffic events feed: <https://api.algotraffic.com/v4.0/TrafficEvents>
- Anthropic, Claude API documentation: <https://platform.claude.com/docs>
- TomTom Traffic API, Incident Details:
  <https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/traffic-incidents/incident-details>
