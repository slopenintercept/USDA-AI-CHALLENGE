# Closure Call

When severe weather threatens a federal facility, someone has to decide whether to close
it, and then tell the right employees. Closure Call puts everything that person needs in
one place: live National Weather Service alerts, state road conditions, a recommended
posture with its reasoning, a drafted notification package, and a record of what was known
and what was decided.

**The system recommends. A person decides.**

Built for the USDA AI Challenge. The facility and its employees are synthetic. The weather
and road data are live.

## How it works

```text
NWS alerts for the facility's coordinates ─┐
                                           ├─> rules ─> recommended posture
State road data for the facility's county ─┘            + thresholds checked
                                                        + confidence
                                                        + what would change it
                                                        + plain-language rationale
                                                              │
                                             the manager decides (name, reason)
                                                              │
                                   notification package ──────┴────── decision record
                                   (who, why, channel, message)      (add-only, fingerprinted)
```

The five postures are normal operations, delayed arrival, early dismissal, unscheduled
leave or telework, and full closure. Three hazards are in scope: flood, wind and winter
storm.

## The five deliverables

| Deliverable | Where it is |
| --- | --- |
| 1. Working system on live NWS data | [`app.py`](app.py), [`closure_call/nws.py`](closure_call/nws.py) |
| 2. Recommendation with reasoning | [`closure_call/rules.py`](closure_call/rules.py), section 1 of the screen |
| 3. Notification package | [`closure_call/notify.py`](closure_call/notify.py), section 3 of the screen |
| 4. Decision record | [`closure_call/record.py`](closure_call/record.py), section 4 of the screen |
| 5. Threshold defensibility | [`docs/thresholds.md`](docs/thresholds.md), and the tables at the top of `rules.py` |

## Run it

Python 3.10 or newer is needed.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start the screen:

```bash
.venv/bin/streamlit run app.py --server.address localhost
```

Or print a recommendation in the terminal:

```bash
.venv/bin/python -m closure_call
```

Run the tests:

```bash
.venv/bin/python -m pytest
```

The NWS and Alabama feeds need no key. TomTom road context is optional: create a file named
`.env` containing `TOMTOM_API_KEY=` followed by your key. Without it the system still runs
and simply shows no TomTom context.

## Demo script

1. Find live alerts. This lists places under a flood, wind or winter alert right now, with
   coordinates that have been checked:

   ```bash
   .venv/bin/python -m closure_call.find
   ```

2. Start the screen and pick **Elba, Alabama**. If its Flood Warning has ended, choose
   **Other coordinates** and paste a flood location from step 1.
3. Read section 1 aloud: the posture, the rule that fired, each threshold with how far it
   was from the cutoff, and what would change the recommendation.
4. Open **Where each cutoff comes from**. Every number has a source.
5. In section 2, record a decision that agrees with the recommendation. Then choose a
   different posture and try to record it with no reason. The screen refuses.
6. In section 3, show who is notified, who is left out, and why.
7. Move the facility to a winter or wind location from step 1. Outside Alabama the screen
   says state road data is unavailable, lowers its confidence, and shows TomTom's closures
   as context that was not counted.
8. Pick **Kansas City, Missouri**. With no alert, the system says normal operations.
9. In section 4, open a full record. It holds every input as received, with its source and
   the time it was fetched.

## Data sources

| Source | Used for | Key |
| --- | --- | --- |
| [NWS API](https://www.weather.gov/documentation/services-web-api) | Active alerts, time zone and county for a location | None |
| [Alabama DOT traffic events](https://api.algotraffic.com/v4.0/TrafficEvents) | Road closures and major delays, counted by the rules | None |
| [TomTom Incident Details](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/traffic-incidents/incident-details) | Closed roads outside Alabama, shown as context only | Free key |

## Decisions worth knowing about

- **Rules decide the posture.** Every cutoff is in one table with its source, so a
  recommendation can be explained and defended line by line.
- **The facility can move.** It is one Service Center profile placed by coordinates. Its
  time zone and county come from the NWS, so the same rules work in any state.
- **Only some road events count.** In Alabama's feed, weather and incident closures count.
  Rest areas and roadwork do not.
- **TomTom is shown, not counted.** Calm counties list more than a hundred closed road
  segments and TomTom gives no cause, so its numbers never change the posture.
- **Missing data is stated.** Where there is no state road feed, the system says so and
  lowers its confidence instead of guessing.
- **The record is only ever added to.** Each record carries a fingerprint of the one before
  it. A correction is a new record that points to the old one.

The evidence behind each of these is in [`docs/thresholds.md`](docs/thresholds.md).

## Limits

- The facility and roster are synthetic. The office is set to open seven days a week so a
  weekend demo evaluates the current day, and federal holidays are not modeled.
- State road data covers Alabama only.
- Hazards other than flood, wind and winter storm are displayed and not evaluated.
- Messages are drafted from fixed templates and routed to a channel. Nothing is sent.
- The record's fingerprint chain shows edits. It cannot stop someone who rebuilds the file.

## Layout

```text
app.py                  the demo screen
closure_call/
  nws.py                live alerts and location lookup
  facility.py           the synthetic facility and its operating day
  rules.py              alert ladder, thresholds, posture rules
  roads.py              Alabama road data (counted) and TomTom context (shown)
  notify.py             notification package and rationale
  record.py             the add-only decision record
  find.py               lists places with a live alert
  geo.py                point-in-outline helpers
data/facility.json      the facility profile and roster
docs/thresholds.md      where every cutoff comes from
tests/                  82 tests
```
