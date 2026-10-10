"""Which operating day a decision applies to, and how live alerts are read."""

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from closure_call.facility import load_facility, operating_period, placed
from closure_call.nws import parse_alert

TZ = "America/Chicago"
FACILITY = load_facility()


def local(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo(TZ))


def test_before_opening_the_decision_is_for_today():
    period = operating_period(FACILITY, TZ, local(11, 5))
    assert (period.opens, period.closes) == (local(11, 8), local(11, 16, 30))


def test_during_the_workday_the_decision_is_for_today():
    assert operating_period(FACILITY, TZ, local(11, 12)).opens == local(11, 8)


def test_after_closing_the_decision_is_for_the_next_open_day():
    assert operating_period(FACILITY, TZ, local(11, 17)).opens == local(12, 8)


def test_closed_days_are_skipped():
    weekdays_only = replace(FACILITY, open_days=(0, 1, 2, 3, 4))
    # 2026-10-10 is a Saturday, so the next open day is Monday the 12th.
    assert operating_period(weekdays_only, TZ, local(10, 5)).opens == local(12, 8)


def test_period_uses_the_facility_time_zone_not_the_callers():
    now_utc = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)  # 05:00 in Alabama
    assert operating_period(FACILITY, TZ, now_utc).opens == local(11, 8)


def test_moving_the_facility_keeps_its_profile_and_names_it_after_the_county():
    moved = placed(FACILITY, 45.0194, -109.9335, "Park")
    assert moved.name == "Park County USDA Service Center (synthetic)"
    assert (moved.latitude, moved.longitude) == (45.0194, -109.9335)
    assert (moved.opens, moved.closes, moved.employees) == (FACILITY.opens, FACILITY.closes, FACILITY.employees)


def feature(**overrides):
    properties = {
        "id": "urn:test",
        "@id": "https://api.weather.gov/alerts/urn:test",
        "event": "Flood Warning",
        "severity": "Severe",
        "certainty": "Likely",
        "urgency": "Expected",
        "onset": "2026-10-11T00:00:00-04:00",
        "ends": "2026-10-11T21:00:00-04:00",
        "effective": "2026-10-10T02:54:00-04:00",
        "expires": "2026-10-10T15:00:00-04:00",
        "headline": "Flood Warning issued",
        "areaDesc": "Coffee, AL",
    }
    return {"properties": {**properties, **overrides}}


FETCHED = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)


def test_alert_times_describe_the_hazard_not_the_message():
    alert = parse_alert(feature(), FETCHED)
    assert alert.starts == datetime.fromisoformat("2026-10-11T00:00:00-04:00")
    assert alert.ends == datetime.fromisoformat("2026-10-11T21:00:00-04:00")
    assert alert.source == "https://api.weather.gov/alerts/urn:test"
    assert alert.fetched_at == FETCHED


def test_alert_with_no_end_time_keeps_none_instead_of_the_message_expiry():
    assert parse_alert(feature(ends=None), FETCHED).ends is None


def test_alert_with_no_onset_starts_when_the_message_took_effect():
    alert = parse_alert(feature(onset=None), FETCHED)
    assert alert.starts == datetime.fromisoformat("2026-10-10T02:54:00-04:00")
