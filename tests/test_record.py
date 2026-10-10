"""The decision record: only ever added to, with edits and removals detectable."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from closure_call import record
from closure_call.facility import Period, load_facility
from closure_call.notify import build_package, rationale
from closure_call.nws import Alert, PointInfo
from closure_call.rules import NORMAL, UNSCHEDULED_LEAVE, recommend

DECIDED_AT = datetime(2026, 10, 12, 10, 5, tzinfo=timezone.utc)


def entry(note="first", corrects=None):
    return {"decision": {"reason": note}, "corrects": corrects}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "records" / "decisions.jsonl"


def test_records_are_numbered_and_chained(path):
    first = record.append(entry("first"), path)
    second = record.append(entry("second"), path)
    assert (first["sequence"], second["sequence"]) == (1, 2)
    assert first["previous_fingerprint"] == record.FIRST_RECORD
    assert second["previous_fingerprint"] == first["fingerprint"]
    assert record.read_all(path) == [first, second]
    assert record.verify(path) == []


def test_appending_never_changes_earlier_lines(path):
    record.append(entry("first"), path)
    before = path.read_text()
    record.append(entry("second"), path)
    assert path.read_text().startswith(before)


def test_editing_an_old_record_is_detected(path):
    record.append(entry("kept the office open"), path)
    record.append(entry("second"), path)
    path.write_text(path.read_text().replace("kept the office open", "closed the office"))
    assert record.verify(path) == ["Line 1: contents do not match its fingerprint."]


def test_editing_the_latest_record_is_detected(path):
    record.append(entry("first"), path)
    record.append(entry("second"), path)
    path.write_text(path.read_text().replace("second", "changed"))
    assert record.verify(path) == ["Line 2: contents do not match its fingerprint."]


def test_removing_a_record_is_detected(path):
    for note in ("first", "second", "third"):
        record.append(entry(note), path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert record.verify(path) == [
        "Line 2: expected record 2, found record 3.",
        "Line 2: does not follow the record before it.",
    ]


def test_unreadable_line_is_reported(path):
    record.append(entry("first"), path)
    path.write_text("not a record\n")
    assert record.verify(path) == ["Line 1: is not a readable record."]


def test_missing_file_has_no_records_and_no_problems(path):
    assert record.read_all(path) == []
    assert record.verify(path) == []


def test_agreeing_with_the_recommendation_needs_no_reason():
    decision = record.make_decision(UNSCHEDULED_LEAVE, UNSCHEDULED_LEAVE, "Jordan Avery", "", DECIDED_AT)
    assert decision["differs_from_recommendation"] is False
    assert decision["decided_by"] == "Jordan Avery"
    assert decision["posture_name"] == "Unscheduled leave or telework"


def test_overriding_the_recommendation_requires_a_written_reason():
    with pytest.raises(ValueError, match="written reason is required"):
        record.make_decision(UNSCHEDULED_LEAVE, NORMAL, "Jordan Avery", "  ", DECIDED_AT)
    decision = record.make_decision(
        UNSCHEDULED_LEAVE, NORMAL, "Jordan Avery", "River crested below the forecast.", DECIDED_AT
    )
    assert decision["differs_from_recommendation"] is True
    assert decision["reason"] == "River crested below the forecast."


def test_a_decision_needs_the_name_of_who_decided():
    with pytest.raises(ValueError, match="name of the person who decided"):
        record.make_decision(NORMAL, NORMAL, " ", "", DECIDED_AT)


def test_a_correction_is_a_new_record_that_points_to_the_old_one(path):
    record.append(entry("first"), path)
    correction = record.append(entry("fixed a typo in the reason", corrects=1), path)
    assert correction["sequence"] == 2
    assert correction["corrects"] == 1
    assert record.read_all(path)[0]["decision"]["reason"] == "first"
    assert record.verify(path) == []


def test_a_correction_must_point_to_a_record_that_exists(path):
    record.append(entry("first"), path)
    with pytest.raises(ValueError, match="Record 7 does not exist"):
        record.append(entry("oops", corrects=7), path)
    assert len(record.read_all(path)) == 1


def test_a_full_decision_is_saved_with_every_input_and_can_be_read_back(path):
    tz = ZoneInfo("America/Chicago")
    facility = load_facility()
    place = PointInfo(timezone="America/Chicago", city="Elba", state="AL", county="Coffee")
    period = Period(opens=datetime(2026, 10, 12, 8, tzinfo=tz), closes=datetime(2026, 10, 12, 16, 30, tzinfo=tz))
    now = datetime(2026, 10, 12, 5, tzinfo=tz)
    alert = Alert(
        id="urn:test",
        event="Flood Warning",
        severity="Severe",
        certainty="Likely",
        urgency="Expected",
        starts=datetime(2026, 10, 12, 2, tzinfo=tz),
        ends=datetime(2026, 10, 13, 9, tzinfo=tz),
        headline="Flood Warning issued",
        area="Coffee, AL",
        source="https://api.weather.gov/alerts/urn:test",
        fetched_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc),
        raw={"event": "Flood Warning", "description": "The Pea River at Elba is forecast to flood."},
    )
    result = recommend([alert], None, period, now)
    decision = record.make_decision(result.posture, NORMAL, "Jordan Avery", "Roads confirmed clear.", DECIDED_AT)
    notices = build_package(NORMAL, facility, period, alert)
    saved = record.append(
        record.build_entry(
            facility, place, None, result, rationale(result, facility, place, None, now), decision, notices
        ),
        path,
    )

    (loaded,) = record.read_all(path)
    assert loaded == saved
    assert loaded["recommendation"]["posture_name"] == "Unscheduled leave or telework"
    assert loaded["recommendation"]["rule"].startswith("Warning during work hours")
    assert loaded["recommendation"]["alert"]["source"] == "https://api.weather.gov/alerts/urn:test"
    assert loaded["recommendation"]["alert"]["fetched_at"] == "2026-10-12T10:00:00+00:00"
    assert loaded["recommendation"]["alert"]["raw"]["description"].startswith("The Pea River")
    assert loaded["roads"] is None
    assert loaded["decision"]["decided_by"] == "Jordan Avery"
    assert loaded["decision"]["decided_at"] == "2026-10-12T10:05:00+00:00"
    assert loaded["decision"]["differs_from_recommendation"] is True
    assert len(loaded["notifications"]) == len(facility.employees)
    assert record.verify(path) == []
