"""Who gets notified, using the synthetic roster.

The letters A to E are the five example employees the rules were designed around:
A = Riley Brooks (E02), B = Devon Grant (E06), C = Morgan Ellis (E04),
D = Jordan Avery (E01), E = Skyler James (E09).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from closure_call.facility import Period, load_facility
from closure_call.nws import Alert, PointInfo
from closure_call.notify import build_package, rationale
from closure_call.roads import RoadContext
from closure_call.rules import DELAYED_ARRIVAL, FULL_CLOSURE, NORMAL, UNSCHEDULED_LEAVE, RoadSummary, recommend

TZ = ZoneInfo("America/Chicago")
FACILITY = load_facility()
PLACE = PointInfo(timezone="America/Chicago", city="Elba", state="AL", county="Coffee")
PERIOD = Period(opens=datetime(2026, 10, 12, 8, tzinfo=TZ), closes=datetime(2026, 10, 12, 16, 30, tzinfo=TZ))
NOW = datetime(2026, 10, 12, 5, tzinfo=TZ)
ALERT = Alert(
    id="test",
    event="Flood Warning",
    severity="Severe",
    certainty="Likely",
    urgency="Expected",
    starts=datetime(2026, 10, 12, 2, tzinfo=TZ),
    ends=datetime(2026, 10, 13, 9, tzinfo=TZ),
    headline="",
    area="",
    source="test",
    fetched_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc),
)


def package(posture=UNSCHEDULED_LEAVE):
    return {notice.employee_id: notice for notice in build_package(posture, FACILITY, PERIOD, ALERT)}


def test_a_assigned_here_and_due_in_gets_the_posture_message_by_text_and_email():
    notice = package()["E02"]
    assert notice.included
    assert notice.channels == ("text", "email")
    assert "This applies to you" in notice.message
    assert "you may take unscheduled leave or telework" in notice.message


def test_b_on_detail_elsewhere_gets_nothing_and_the_reason_is_recorded():
    notice = package()["E06"]
    assert not notice.included
    assert notice.channels == ()
    assert notice.message == ""
    assert notice.reason == "Assigned here but on detail at another site today."


def test_c_already_teleworking_gets_an_email_only():
    notice = package()["E04"]
    assert notice.included
    assert notice.channels == ("email",)
    assert "no action is needed" in notice.message


def test_d_essential_personnel_are_told_to_report_as_scheduled():
    for posture in (UNSCHEDULED_LEAVE, FULL_CLOSURE):
        notice = package(posture)["E01"]
        assert notice.included
        assert "Report as scheduled" in notice.message
        assert "Do not report" not in notice.message


def test_e_detailed_here_gets_the_same_message_as_a():
    notices = package()
    assert notices["E09"].message == notices["E02"].message
    assert notices["E09"].channels == notices["E02"].channels
    assert notices["E09"].reason == "Expected at this building today (detailed here from usda-sc-dale-al)."


def test_accessibility_flag_switches_the_text_to_a_voice_call():
    assert package()["E03"].channels == ("voice call", "email")


def test_normal_operations_notifies_nobody():
    assert not any(notice.included for notice in package(NORMAL).values())


def test_full_closure_tells_other_staff_not_to_report():
    assert "Do not report to the building" in package(FULL_CLOSURE)["E02"].message


def test_delayed_arrival_message_gives_the_new_reporting_time():
    assert "Report by 10:00 instead of 08:00" in package(DELAYED_ARRIVAL)["E02"].message


def test_message_says_what_is_happening_and_until_when():
    message = package()["E02"].message
    assert FACILITY.name in message
    assert "Unscheduled leave or telework on Monday October 12" in message
    assert "a Flood Warning in effect until Tue 09:00" in message


def test_everyone_on_the_roster_appears_exactly_once_with_a_reason():
    notices = build_package(UNSCHEDULED_LEAVE, FACILITY, PERIOD, ALERT)
    assert [notice.employee_id for notice in notices] == [person.id for person in FACILITY.employees]
    assert all(notice.reason for notice in notices)


def test_manager_can_set_a_posture_when_no_alert_is_active():
    notices = build_package(FULL_CLOSURE, FACILITY, PERIOD, None)
    assert "Full closure on Monday October 12." in notices[1].message


def test_rationale_names_the_posture_the_alert_and_the_missing_road_data():
    result = recommend([ALERT], None, PERIOD, NOW)
    text = rationale(result, FACILITY, PLACE, None, NOW)
    assert "is Unscheduled leave or telework for the operating day of Monday October 12" in text
    assert "a Flood Warning in effect" in text
    assert "rated Severe in severity and Likely in certainty" in text
    assert "State road data was not available" in text
    assert "Confidence is medium. It was lowered one step because road data is missing." in text
    assert "\n" not in text


def test_rationale_reports_road_counts_and_keeps_confidence_when_road_data_exists():
    roads = RoadSummary(closures=0, major_delays=1)
    text = rationale(recommend([ALERT], roads, PERIOD, NOW), FACILITY, PLACE, roads, NOW)
    assert "State road data for the county shows 0 full road closure(s) and 1 major delay(s)." in text
    assert "Confidence is high." in text
    assert "lowered one step" not in text


def test_rationale_says_tomtom_closures_were_shown_but_not_counted():
    context = RoadContext(closed_segments=56, on_numbered_roads=0, source="test", fetched_at=NOW)
    without = recommend([ALERT], None, PERIOD, NOW)
    text = rationale(without, FACILITY, PLACE, None, NOW, context)
    assert "TomTom lists 56 closed road segments in the county, 0 of them on numbered roads." in text
    assert "were not counted" in text
    assert "Confidence is medium. It was lowered one step because road data is missing." in text


def test_rationale_with_no_alert_says_so():
    result = recommend([], None, PERIOD, NOW)
    text = rationale(result, FACILITY, PLACE, None, NOW)
    assert "is Normal operations" in text
    assert "no flood, wind or winter alert covering this location" in text
