"""Closure Call demo screen.

Run with: .venv/bin/streamlit run app.py

The page fetches live data once per refresh and keeps that snapshot, so the
decision record saves exactly what was on screen when the manager decided.
"""

import json
from datetime import datetime, timezone

import requests
import streamlit as st

from closure_call import nws, record
from closure_call.facility import load_facility, operating_period, placed
from closure_call.notify import build_package, rationale
from closure_call.roads import get_road_context, get_road_summary
from closure_call.rules import POSTURES, THRESHOLDS, recommend

# Where the synthetic facility can be placed. On demo morning, pick a place with a live alert.
PLACES = {
    "Elba, Alabama": (31.4146, -86.0677),
    "Cooke City, Montana": (45.0194, -109.9335),
    "Las Vegas, Nevada": (36.1716, -115.1391),
    "Kansas City, Missouri": (39.0997, -94.5786),
}
OTHER = "Other coordinates"


def fetch_snapshot(latitude, longitude):
    """Everything the manager sees, fetched once so the screen and the record agree."""
    now = datetime.now(timezone.utc)
    place = nws.get_point_info(latitude, longitude)
    facility = placed(load_facility(), latitude, longitude, place.county)
    alerts = nws.get_active_alerts(latitude, longitude)
    roads = get_road_summary(place)
    context = get_road_context(place)
    result = recommend(alerts, roads, operating_period(facility, place.timezone, now), now)
    return {
        "facility": facility,
        "place": place,
        "roads": roads,
        "context": context,
        "result": result,
        "now": now,
        "rationale": rationale(result, facility, place, roads, now, context),
    }


st.set_page_config(page_title="Closure Call", layout="wide")

with st.sidebar:
    st.header("Facility location")
    choice = st.selectbox("Place the facility", [*PLACES, OTHER])
    if choice == OTHER:
        latitude = st.number_input("Latitude", value=31.4146, format="%.4f")
        longitude = st.number_input("Longitude", value=-86.0677, format="%.4f")
    else:
        latitude, longitude = PLACES[choice]
    refresh = st.button("Refresh live data")

if refresh or st.session_state.get("location") != (latitude, longitude):
    try:
        st.session_state.snapshot = fetch_snapshot(latitude, longitude)
    except requests.RequestException as error:
        st.error(f"Could not fetch live data: {error}")
        st.stop()
    st.session_state.location = (latitude, longitude)

snapshot = st.session_state.snapshot
facility, place, roads, result, now = (snapshot[key] for key in ("facility", "place", "roads", "result", "now"))
context = snapshot["context"]
period = result.period
tz = period.opens.tzinfo


def clock(when):
    return when.astimezone(tz).strftime("%a %H:%M") if when else "no end time"


st.title("Closure Call")
st.caption("The system recommends. A person decides.")
st.subheader(facility.name)
st.write(
    f"Near {place.city}, {place.state} ({facility.latitude}, {facility.longitude}). "
    f"Live data fetched {now.astimezone(tz):%A %B %d at %H:%M %Z}."
)

# 1. Recommendation ---------------------------------------------------------------------------

st.header("1. Recommendation")
st.markdown(f"## {result.posture} · {POSTURES[result.posture]}")
left, right = st.columns(2)
left.metric("Confidence", result.confidence.capitalize())
right.metric("Operating period", f"{period.opens:%a %H:%M} to {period.closes:%H:%M}")
st.write(f"**Rule that fired:** {result.rule}")

if result.crossings:
    st.subheader("Thresholds checked")
    st.dataframe(
        [{"Cutoff": c.threshold, "Observed": c.observed, "By how much": c.margin} for c in result.crossings],
        hide_index=True,
        width="stretch",
    )
st.subheader("What would change it")
st.markdown("\n".join(f"- {change}" for change in result.would_change))

st.subheader("Inputs")
alert_rows = [
    {
        "Role": role,
        "Alert": alert.event,
        "Severity": alert.severity,
        "Certainty": alert.certainty,
        "Urgency": alert.urgency,
        "Starts": clock(alert.starts),
        "Ends": clock(alert.ends),
        "Fetched (UTC)": f"{alert.fetched_at:%Y-%m-%d %H:%M:%S}",
        "Source": alert.source,
    }
    for role, alerts in (
        ("Set the posture", [result.alert] if result.alert else []),
        ("Also considered", result.other_alerts),
        ("Not evaluated: outside flood, wind and winter", result.out_of_scope),
    )
    for alert in alerts
]
if alert_rows:
    st.dataframe(
        alert_rows,
        hide_index=True,
        width="stretch",
        column_config={"Source": st.column_config.LinkColumn("Source", display_text="NWS alert")},
    )
else:
    st.write("The National Weather Service has no active alert covering this location.")

if roads is None:
    st.warning(
        f"State road data unavailable: there is no road feed for {place.state}. Confidence was lowered one step."
    )
    if context:
        closed, numbered = st.columns(2)
        closed.metric(f"Closed road segments, {place.county} County (TomTom)", context.closed_segments)
        numbered.metric("Of those, on numbered roads", context.on_numbered_roads)
        st.caption(
            "Context for the manager only. These are not counted by the rules, because TomTom gives no cause "
            f"for a closure and calm places list many. Fetched {context.fetched_at:%Y-%m-%d %H:%M:%S} UTC "
            f"from {context.source}"
        )
        if context.incidents:
            with st.expander("Closed road segments listed by TomTom"):
                st.dataframe(
                    [
                        {
                            "Road numbers": ", ".join(incident["properties"].get("roadNumbers") or []),
                            "From": incident["properties"].get("from"),
                            "To": incident["properties"].get("to"),
                        }
                        for incident in context.incidents
                    ],
                    hide_index=True,
                    width="stretch",
                )
else:
    closures, delays, counted = st.columns(3)
    closures.metric(f"Full road closures, {place.county} County", roads.closures)
    delays.metric("Major delays", roads.major_delays)
    counted.metric("Road events counted", len(roads.events))
    st.caption(f"Road data fetched {roads.fetched_at:%Y-%m-%d %H:%M:%S} UTC from {roads.source}")
    if roads.events:
        with st.expander("Road events counted"):
            st.dataframe(
                [
                    {
                        "Type": event.get("type"),
                        "Severity": event.get("severity"),
                        "What": event.get("title"),
                        "Detail": event.get("description"),
                        "Updated": event.get("lastUpdatedAt"),
                    }
                    for event in roads.events
                ],
                hide_index=True,
                width="stretch",
            )

st.subheader("Rationale, ready to paste into an email")
st.code(snapshot["rationale"], language=None, wrap_lines=True)

with st.expander("Where each cutoff comes from"):
    st.dataframe(
        [
            {"Cutoff": name, "Value": str(t.value), "Meaning": t.meaning, "Source": t.source}
            for name, t in THRESHOLDS.items()
        ],
        hide_index=True,
        width="stretch",
    )

# 2. Decision ---------------------------------------------------------------------------------

st.header("2. Decision")
decided = st.selectbox(
    "Posture you are deciding",
    list(POSTURES),
    index=list(POSTURES).index(result.posture),
    format_func=lambda posture: f"{posture} · {POSTURES[posture]}",
    key=f"decided-{now.isoformat()}",  # a new snapshot starts again from the recommendation
)
if decided != result.posture:
    st.info("This differs from the recommendation, so a written reason is required.")
notices = build_package(decided, facility, period, result.alert)

with st.form("decision"):
    decided_by = st.text_input("Your name")
    reason = st.text_area("Reason", help="Required when your decision differs from the recommendation.")
    if st.form_submit_button("Record decision", type="primary"):
        try:
            decision = record.make_decision(result.posture, decided, decided_by, reason, datetime.now(timezone.utc))
        except ValueError as error:
            st.error(str(error))
        else:
            saved = record.append(
                record.build_entry(
                    facility, place, roads, result, snapshot["rationale"], decision, notices, road_context=context
                )
            )
            st.success(f"Saved as record {saved['sequence']}, fingerprint {saved['fingerprint'][:16]}...")

# 3. Notification package ---------------------------------------------------------------------

st.header("3. Notification package")
st.caption("Drafted for the posture selected above. Nothing is sent.")
st.dataframe(
    [
        {
            "Name": notice.name,
            "Notified": "Yes" if notice.included else "No",
            "Channels": " + ".join(notice.channels),
            "Why": notice.reason,
        }
        for notice in notices
    ],
    hide_index=True,
    width="stretch",
)
messages = {}
for notice in notices:
    if notice.included:
        messages.setdefault(notice.message, []).append(notice.name)
for message, names in messages.items():
    with st.expander(f"Message to {len(names)} people: {', '.join(names)}"):
        st.code(message, language=None, wrap_lines=True)

# 4. Decision record --------------------------------------------------------------------------

st.header("4. Decision record")
problems = record.verify()
try:
    records = record.read_all()
except json.JSONDecodeError:
    records = []
if problems:
    st.error("The record file has been changed. " + " ".join(problems))
else:
    st.success(f"{len(records)} records saved. The chain of fingerprints is unbroken.")
if records:
    st.dataframe(
        [
            {
                "Record": saved["sequence"],
                "Recorded (UTC)": saved["recorded_at"][:19].replace("T", " "),
                "Facility": saved["facility"]["name"],
                "Recommended": saved["recommendation"]["posture_name"],
                "Decided": saved["decision"]["posture_name"],
                "By": saved["decision"]["decided_by"],
                "Reason": saved["decision"]["reason"],
            }
            for saved in reversed(records)
        ],
        hide_index=True,
        width="stretch",
    )
    with st.expander("Open a full record"):
        chosen = st.selectbox("Record number", [saved["sequence"] for saved in reversed(records)])
        st.json(records[chosen - 1], expanded=1)
