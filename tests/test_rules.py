"""The posture rules, checked against a Monday that opens at 08:00 and closes at 16:30."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from closure_call.facility import Period
from closure_call.nws import Alert
from closure_call.rules import (
    DELAYED_ARRIVAL,
    EARLY_DISMISSAL,
    FULL_CLOSURE,
    NORMAL,
    UNSCHEDULED_LEAVE,
    RoadSummary,
    recommend,
)

TZ = ZoneInfo("America/Chicago")


def at(hour, minute=0, day=12):
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


PERIOD = Period(opens=at(8), closes=at(16, 30))
NOW = at(5)  # the manager decides at 5:00 am
ROADS_OPEN = RoadSummary(closures=0, major_delays=0)


def alert(event="Flood Warning", severity="Severe", certainty="Likely", starts=at(2), ends=at(9, day=13)):
    return Alert(
        id="test",
        event=event,
        severity=severity,
        certainty=certainty,
        urgency="Expected",
        starts=starts,
        ends=ends,
        headline="",
        area="",
        source="test",
        fetched_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc),
    )


def posture(alerts, roads=ROADS_OPEN, now=NOW):
    return recommend(alerts, roads, PERIOD, now).posture


# The learner's rules


def test_warning_during_work_hours_with_roads_open_gives_unscheduled_leave():
    assert posture([alert()]) == UNSCHEDULED_LEAVE


def test_full_road_closure_raises_it_to_full_closure():
    assert posture([alert()], RoadSummary(closures=1, major_delays=0)) == FULL_CLOSURE


def test_major_delays_alone_do_not_raise_a_warning_to_closure():
    assert posture([alert()], RoadSummary(closures=0, major_delays=6)) == UNSCHEDULED_LEAVE


def test_warning_that_ends_early_gives_delayed_arrival():
    assert posture([alert(ends=at(9))]) == DELAYED_ARRIVAL


def test_delayed_arrival_cutoff_is_two_hours_after_opening():
    assert posture([alert(ends=at(10))]) == DELAYED_ARRIVAL
    assert posture([alert(ends=at(10, 1))]) == UNSCHEDULED_LEAVE


# The confirmed additions


def test_warning_that_starts_during_the_workday_gives_early_dismissal():
    assert posture([alert(starts=at(13))]) == EARLY_DISMISSAL


def test_extreme_warning_gives_full_closure():
    assert posture([alert(severity="Extreme")]) == FULL_CLOSURE


def test_watch_stays_normal():
    assert posture([alert(event="Winter Storm Watch")]) == NORMAL


def test_advisory_alone_stays_normal():
    assert posture([alert(event="Wind Advisory", severity="Moderate")]) == NORMAL


def test_advisory_with_a_road_closure_or_major_delay_gives_unscheduled_leave():
    advisory = alert(event="Winter Weather Advisory", severity="Moderate")
    assert posture([advisory], RoadSummary(closures=1, major_delays=0)) == UNSCHEDULED_LEAVE
    assert posture([advisory], RoadSummary(closures=0, major_delays=1)) == UNSCHEDULED_LEAVE


def test_advisory_with_no_road_data_stays_normal():
    assert posture([alert(event="Wind Advisory", severity="Moderate")], roads=None) == NORMAL


# Timing


def test_alert_that_ends_before_opening_does_not_count():
    assert posture([alert(ends=at(7))]) == NORMAL


def test_alert_that_starts_after_closing_does_not_count():
    assert posture([alert(starts=at(18))]) == NORMAL


def test_alert_that_already_ended_today_does_not_count():
    assert posture([alert(ends=at(11))], now=at(12)) == NORMAL


def test_warning_with_no_end_time_is_treated_as_lasting_all_day():
    assert posture([alert(ends=None)]) == UNSCHEDULED_LEAVE


# Several alerts, and alerts outside the three hazards


def test_no_alerts_gives_normal_with_high_confidence():
    result = recommend([], ROADS_OPEN, PERIOD, NOW)
    assert result.posture == NORMAL
    assert result.alert is None
    assert result.confidence == "high"


def test_strongest_posture_wins():
    watch = alert(event="High Wind Watch")
    warning = alert(event="Winter Storm Warning")
    result = recommend([watch, warning], ROADS_OPEN, PERIOD, NOW)
    assert result.posture == UNSCHEDULED_LEAVE
    assert result.alert is warning
    assert result.other_alerts == (watch,)


def test_out_of_scope_alert_is_listed_but_never_evaluated():
    tornado = alert(event="Tornado Warning", severity="Extreme")
    result = recommend([tornado], ROADS_OPEN, PERIOD, NOW)
    assert result.posture == NORMAL
    assert result.out_of_scope == (tornado,)


# Confidence and the "by how much" record


def test_confidence_follows_the_alert_certainty():
    assert recommend([alert(certainty="Observed")], ROADS_OPEN, PERIOD, NOW).confidence == "high"
    assert recommend([alert(certainty="Possible")], ROADS_OPEN, PERIOD, NOW).confidence == "medium"
    assert recommend([alert(certainty="Unlikely")], ROADS_OPEN, PERIOD, NOW).confidence == "low"


def test_missing_road_data_lowers_confidence_one_step():
    assert recommend([alert(certainty="Likely")], None, PERIOD, NOW).confidence == "medium"
    assert recommend([alert(certainty="Possible")], None, PERIOD, NOW).confidence == "low"
    assert recommend([alert(certainty="Unlikely")], None, PERIOD, NOW).confidence == "low"


def test_recommendation_says_which_cutoff_was_crossed_and_by_how_much():
    result = recommend([alert(ends=at(12))], ROADS_OPEN, PERIOD, NOW)
    timing = result.crossings[2]
    assert timing.threshold == "Hazard ends by Mon 10:00, 2 h after opening"
    assert timing.observed == "ends Mon 12:00"
    assert timing.margin == "2.0 h past the cutoff"
    assert "A full road closure in the county would raise this to Full closure." in result.would_change
