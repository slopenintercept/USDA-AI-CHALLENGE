"""Road conditions in the facility's county.

Alabama publishes an open state DOT feed, and its closures and major delays are
counted by the rules. For other states the rules treat road data as unavailable.
TomTom's closed roads are fetched there as context for the manager only.
"""

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from closure_call.rules import RoadSummary

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ALABAMA_EVENTS = "https://api.algotraffic.com/v4.0/TrafficEvents"
HEADERS = {"User-Agent": "closure-call (USDA AI Challenge hackathon project)"}
TIMEOUT_SECONDS = 20

# Team decision: only these kinds of event count toward the road thresholds.
# Facility events (rest areas and similar) and Roadwork do not.
COUNTED_TYPES = {"RoadCondition", "Incident"}

TOMTOM_INCIDENTS = "https://api.tomtom.com/traffic/services/5/incidentDetails"
TOMTOM_FIELDS = "{incidents{geometry{type,coordinates},properties{id,iconCategory,events{description},from,to,roadNumbers}}}"
TOMTOM_ROAD_CLOSED = 8  # TomTom's category number for a closed road
TOMTOM_BOX_KM = 95  # one request may cover at most 10,000 square km


@dataclass(frozen=True)
class RoadContext:
    """Closed roads in the county according to TomTom.

    Team decision: this is shown to the manager and never counted by the rules. TomTom gives
    no cause for a closure, and calm places list many of them (134 in Jackson County,
    Missouri on 2026-10-10 with no weather alert active).
    """

    closed_segments: int
    on_numbered_roads: int
    source: str
    fetched_at: datetime
    incidents: tuple = field(default=(), compare=False, repr=False)


def summarize_alabama(events, county, fetched_at):
    """Count closures and major delays among the events that start or end in this county."""

    def in_county(event):
        places = (event["startLocation"], event.get("endLocation") or {})
        return any(place.get("county") == county for place in places)

    counted = [event for event in events if event["type"] in COUNTED_TYPES and in_county(event)]
    return RoadSummary(
        closures=sum(event["severity"] == "Closed" for event in counted),
        major_delays=sum(event["severity"] == "MajorDelay" for event in counted),
        source=ALABAMA_EVENTS,
        fetched_at=fetched_at,
        events=tuple(counted),
    )


def get_road_summary(place):
    """Live state DOT road conditions for the facility's county, or None when no feed covers its state."""
    if place.state != "AL":
        return None
    response = requests.get(ALABAMA_EVENTS, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return summarize_alabama(response.json(), place.county, datetime.now(timezone.utc))


def _inside(ring, longitude, latitude):
    """Whether a point lies inside a closed ring of (longitude, latitude) points."""
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _boxes(rings):
    """Boxes small enough for one TomTom request each that together cover the county."""
    longitudes = [longitude for ring in rings for longitude, _ in ring]
    latitudes = [latitude for ring in rings for _, latitude in ring]
    west, east, south, north = min(longitudes), max(longitudes), min(latitudes), max(latitudes)
    km_per_degree_east = 111.32 * math.cos(math.radians((south + north) / 2))
    columns = math.ceil((east - west) * km_per_degree_east / TOMTOM_BOX_KM)
    rows = math.ceil((north - south) * 110.57 / TOMTOM_BOX_KM)
    width, height = (east - west) / columns, (north - south) / rows
    return [
        (west + column * width, south + row * height, west + (column + 1) * width, south + (row + 1) * height)
        for column in range(columns)
        for row in range(rows)
    ]


def summarize_tomtom(incidents, rings, fetched_at):
    """Closed road segments that start or end inside the county outline."""
    closed = []
    for incident in incidents:
        shape = incident["geometry"]
        points = [shape["coordinates"]] if shape["type"] == "Point" else shape["coordinates"]
        start, end = points[0], points[-1]
        in_county = any(_inside(ring, longitude, latitude) for ring in rings for longitude, latitude in (start, end))
        if incident["properties"]["iconCategory"] == TOMTOM_ROAD_CLOSED and in_county:
            closed.append({"properties": incident["properties"], "start": start, "end": end})
    return RoadContext(
        closed_segments=len(closed),
        on_numbered_roads=sum(bool(incident["properties"].get("roadNumbers")) for incident in closed),
        source=TOMTOM_INCIDENTS,
        fetched_at=fetched_at,
        incidents=tuple(closed),
    )


def get_road_context(place):
    """TomTom's closed roads for the county, in states with no DOT feed here.

    Returns None in Alabama, without a key, or when the request fails: this is context
    only, so a TomTom outage must not block the recommendation.
    """
    key = os.environ.get("TOMTOM_API_KEY")
    if place.state == "AL" or not key:
        return None
    found = {}
    try:
        for box in _boxes(place.county_rings):
            response = requests.get(
                TOMTOM_INCIDENTS,
                timeout=TIMEOUT_SECONDS,
                params={
                    "key": key,
                    "bbox": ",".join(f"{value:.5f}" for value in box),
                    "fields": TOMTOM_FIELDS,
                    "language": "en-US",
                    "timeValidityFilter": "present",
                },
            )
            response.raise_for_status()
            for incident in response.json()["incidents"]:
                found[incident["properties"]["id"]] = incident
    except requests.RequestException:
        return None
    return summarize_tomtom(found.values(), place.county_rings, datetime.now(timezone.utc))
