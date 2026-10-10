"""Which road events count toward the thresholds."""

from datetime import datetime, timezone

import requests

from closure_call import roads
from closure_call.nws import PointInfo
from closure_call.roads import ALABAMA_EVENTS, get_road_context, get_road_summary, summarize_alabama, summarize_tomtom

FETCHED = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)


def event(kind, severity, county="Coffee", end_county=None):
    return {
        "type": kind,
        "severity": severity,
        "startLocation": {"county": county},
        "endLocation": {"county": end_county} if end_county else None,
    }


def summary(*events):
    return summarize_alabama(list(events), "Coffee", FETCHED)


def test_road_condition_and_incident_closures_count():
    result = summary(event("RoadCondition", "Closed"), event("Incident", "Closed"))
    assert result.closures == 2


def test_facility_and_roadwork_closures_do_not_count():
    result = summary(event("Facility", "Closed"), event("Roadwork", "Closed"))
    assert result.closures == 0
    assert result.events == ()


def test_major_delays_are_counted_separately_from_closures():
    result = summary(
        event("RoadCondition", "MajorDelay"),
        event("RoadCondition", "ModerateDelay"),
        event("Incident", "MajorDelay"),
        event("Roadwork", "MajorDelay"),
    )
    assert (result.closures, result.major_delays) == (0, 2)


def test_only_the_facility_county_counts():
    assert summary(event("RoadCondition", "Closed", county="Dale")).closures == 0


def test_an_event_that_ends_in_the_county_counts():
    assert summary(event("RoadCondition", "Closed", county="Dale", end_county="Coffee")).closures == 1


def test_summary_keeps_the_source_the_fetch_time_and_the_counted_events():
    debris = event("RoadCondition", "ModerateDelay")
    result = summary(debris, event("Roadwork", "Closed"))
    assert result.source == ALABAMA_EVENTS
    assert result.fetched_at == FETCHED
    assert result.events == (debris,)


def test_a_state_with_no_feed_reports_road_data_as_unavailable():
    montana = PointInfo(timezone="America/Denver", city="Cooke City", state="MT", county="Park")
    assert get_road_summary(montana) is None


# TomTom context: shown to the manager, never counted by the rules

COUNTY = (((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),)  # a square county one degree wide
ROAD_CLOSED, ROADWORKS = 8, 9


def incident(category, start, end=None, road_numbers=()):
    return {
        "geometry": {"type": "LineString", "coordinates": [list(start), list(end or start)]},
        "properties": {"id": f"{category}-{start}-{end}", "iconCategory": category, "roadNumbers": list(road_numbers)},
    }


def context(*incidents):
    return summarize_tomtom(list(incidents), COUNTY, FETCHED)


def test_closed_segments_inside_the_county_are_listed():
    result = context(incident(ROAD_CLOSED, (0.5, 0.5)), incident(ROAD_CLOSED, (0.2, 0.9), road_numbers=["US-212"]))
    assert (result.closed_segments, result.on_numbered_roads) == (2, 1)
    assert result.source == roads.TOMTOM_INCIDENTS
    assert result.fetched_at == FETCHED


def test_segments_outside_the_county_and_other_categories_are_left_out():
    result = context(incident(ROAD_CLOSED, (1.5, 0.5)), incident(ROADWORKS, (0.5, 0.5)))
    assert result.closed_segments == 0


def test_a_segment_that_only_ends_in_the_county_is_listed():
    assert context(incident(ROAD_CLOSED, (1.5, 0.5), end=(0.9, 0.5))).closed_segments == 1


def test_a_single_point_incident_is_handled():
    point = {"geometry": {"type": "Point", "coordinates": [0.5, 0.5]}, "properties": {"id": "p", "iconCategory": 8}}
    assert context(point).closed_segments == 1


def test_saved_incidents_keep_their_details_and_end_points_but_not_the_full_line():
    (saved,) = context(incident(ROAD_CLOSED, (0.5, 0.5), end=(0.6, 0.5))).incidents
    assert saved == {
        "properties": {"id": "8-(0.5, 0.5)-(0.6, 0.5)", "iconCategory": 8, "roadNumbers": []},
        "start": [0.5, 0.5],
        "end": [0.6, 0.5],
    }


def test_a_small_county_needs_one_request_and_a_large_one_is_split():
    small = (((0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)),)  # about 55 km on each side
    assert len(roads._boxes(small)) == 1
    large = (((-111.0, 44.0), (-109.0, 44.0), (-109.0, 46.0), (-111.0, 46.0)),)
    boxes = roads._boxes(large)
    assert len(boxes) == 6  # about 157 km wide and 221 km tall
    assert min(box[0] for box in boxes) == -111.0 and max(box[2] for box in boxes) == -109.0
    assert min(box[1] for box in boxes) == 44.0 and max(box[3] for box in boxes) == 46.0


def place(state):
    return PointInfo(timezone="America/Denver", city="Cooke City", state=state, county="Park", county_rings=COUNTY)


def refuse_requests(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request should be made")

    monkeypatch.setattr(roads.requests, "get", fail)


def test_no_context_is_fetched_for_alabama_because_state_data_is_counted_there(monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", "test-key")
    refuse_requests(monkeypatch)
    assert get_road_context(place("AL")) is None


def test_no_context_without_a_key(monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    refuse_requests(monkeypatch)
    assert get_road_context(place("MT")) is None


def test_a_failed_request_gives_no_context_instead_of_an_error(monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", "test-key")

    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(roads.requests, "get", fail)
    assert get_road_context(place("MT")) is None
