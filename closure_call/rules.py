"""Turn live inputs into one of five closure postures.

Every cutoff the rules use is in the tables below, next to where it came from.
The system recommends; a person decides.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from closure_call.facility import Period
from closure_call.nws import Alert

NORMAL, DELAYED_ARRIVAL, EARLY_DISMISSAL, UNSCHEDULED_LEAVE, FULL_CLOSURE = 1, 2, 3, 4, 5

POSTURES = {
    NORMAL: "Normal operations",
    DELAYED_ARRIVAL: "Delayed arrival",
    EARLY_DISMISSAL: "Early dismissal",
    UNSCHEDULED_LEAVE: "Unscheduled leave or telework",
    FULL_CLOSURE: "Full closure",
}

# NWS alert names for the three hazards in scope, placed on the Watch / Advisory / Warning ladder.
# Source: NWS definitions. A Watch means the hazard is possible. An Advisory means it is
# occurring or imminent but less serious. A Warning means it threatens life or property.
LADDER = {
    "Flood Watch": ("flood", "watch"),
    "Flood Advisory": ("flood", "advisory"),
    "Flood Warning": ("flood", "warning"),
    "Flash Flood Warning": ("flood", "warning"),
    "High Wind Watch": ("wind", "watch"),
    "Wind Advisory": ("wind", "advisory"),
    "High Wind Warning": ("wind", "warning"),
    "Winter Storm Watch": ("winter", "watch"),
    "Winter Weather Advisory": ("winter", "advisory"),
    "Winter Storm Warning": ("winter", "warning"),
    "Blizzard Warning": ("winter", "warning"),
    "Ice Storm Warning": ("winter", "warning"),
}


@dataclass(frozen=True)
class Threshold:
    value: object
    meaning: str
    source: str


THRESHOLDS = {
    "delayed_arrival_hours": Threshold(
        2,
        "A Warning that ends within this many hours after opening gives delayed arrival.",
        "Starting value. OPM's Governmentwide Dismissal and Closure Procedures (December 2025, section IV.B.3) "
        "define 'Open - X Hour(s) Delayed Arrival' and leave X to the decision-maker. "
        "Its worked example uses a 2-hour delayed arrival.",
    ),
    "closure_severity": Threshold(
        "Extreme",
        "A Warning the NWS rates at this severity gives full closure.",
        "NWS alert severity field (CAP standard). Extreme is the highest level: "
        "an extraordinary threat to life or property.",
    ),
    "road_closures_for_closure": Threshold(
        1,
        "This many full road closures in the facility's county raise unscheduled leave to full closure.",
        "Team decision: any full closure means some staff cannot reach the building.",
    ),
    "major_delays_for_advisory": Threshold(
        1,
        "Under an Advisory, this many major road delays in the county give unscheduled leave. "
        "So does any full closure.",
        "Starting value. Uses the state DOT's own 'MajorDelay' category for weather and incident events.",
    ),
}

# Confidence starts from the alert's own certainty field (CAP standard) and drops one step
# when road data is missing.
CONFIDENCE_STEPS = ["low", "medium", "high"]
CONFIDENCE_BY_CERTAINTY = {
    "Observed": "high",
    "Likely": "high",
    "Possible": "medium",
    "Unlikely": "low",
    "Unknown": "low",
}


@dataclass(frozen=True)
class RoadSummary:
    """Road conditions in the facility's county, counted by closure_call.roads."""

    closures: int
    major_delays: int
    source: str = ""  # the feed's address
    fetched_at: datetime | None = None
    events: tuple = field(default=(), compare=False, repr=False)  # the counted events as received


@dataclass(frozen=True)
class Crossing:
    """One threshold check: the cutoff, what was observed, and by how much."""

    threshold: str
    observed: str
    margin: str


@dataclass(frozen=True)
class Finding:
    """What one alert means for the posture."""

    posture: int
    rule: str
    crossings: tuple[Crossing, ...] = ()
    would_change: tuple[str, ...] = ()


@dataclass(frozen=True)
class Recommendation:
    posture: int
    rule: str
    crossings: tuple[Crossing, ...]
    would_change: tuple[str, ...]
    confidence: str
    period: Period
    alert: Alert | None  # the alert that set the posture
    other_alerts: tuple[Alert, ...]  # in scope, but did not set the posture
    out_of_scope: tuple[Alert, ...]  # not flood, wind or winter: shown to the manager, never evaluated


def _clock(when, period):
    return when.astimezone(period.opens.tzinfo).strftime("%a %H:%M")


def _hours(delta):
    return f"{abs(delta.total_seconds()) / 3600:.1f} h"


def _assess(alert, rung, roads, period, now):
    """Posture for one in-scope alert, with the rule that fired and the thresholds it was checked against."""
    if (alert.ends and alert.ends <= max(period.opens, now)) or alert.starts >= period.closes:
        return Finding(NORMAL, f"{alert.event} does not overlap the operating period.")

    level = Crossing(
        "Alert level: Warning", rung.capitalize(), "at the cutoff" if rung == "warning" else "below the cutoff"
    )
    closures_needed = THRESHOLDS["road_closures_for_closure"].value
    road = Crossing(
        f"Full road closures in the county: {closures_needed}",
        "road data unavailable" if roads is None else str(roads.closures),
        "not checked" if roads is None else f"{roads.closures - closures_needed:+d} against the cutoff",
    )

    if rung == "watch":
        return Finding(
            NORMAL,
            "Watch: the hazard is possible, so stay at normal operations and monitor.",
            (level,),
            ("An upgrade of this Watch to a Warning would change the posture.",),
        )

    if rung == "advisory":
        delays_needed = THRESHOLDS["major_delays_for_advisory"].value
        if roads is not None and (roads.closures >= closures_needed or roads.major_delays >= delays_needed):
            delays = Crossing(
                f"Major road delays in the county: {delays_needed}",
                str(roads.major_delays),
                f"{roads.major_delays - delays_needed:+d} against the cutoff",
            )
            return Finding(
                UNSCHEDULED_LEAVE,
                "Advisory with county roads closed or badly delayed.",
                (level, road, delays),
                ("Roads reopening and delays clearing would return this to Normal operations.",),
            )
        return Finding(
            NORMAL,
            "Advisory alone: normal operations.",
            (level, road),
            (
                "A full road closure or a major delay in the county would raise this to "
                "Unscheduled leave or telework.",
                "An upgrade of this Advisory to a Warning would change the posture.",
            ),
        )

    severity_cutoff = THRESHOLDS["closure_severity"].value
    if alert.severity == severity_cutoff:
        return Finding(
            FULL_CLOSURE,
            f"Warning rated {severity_cutoff} by the NWS.",
            (level, Crossing(f"Severity for full closure: {severity_cutoff}", alert.severity, "at the cutoff")),
            (f"A downgrade below {severity_cutoff} severity would lower this.",),
        )
    severity = Crossing(f"Severity for full closure: {severity_cutoff}", alert.severity, "below the cutoff")

    delay_hours = THRESHOLDS["delayed_arrival_hours"].value
    cutoff = period.opens + timedelta(hours=delay_hours)
    cutoff_text = f"Hazard ends by {_clock(cutoff, period)}, {delay_hours} h after opening"
    if alert.ends and alert.ends <= cutoff:
        timing = Crossing(
            cutoff_text, f"ends {_clock(alert.ends, period)}", f"{_hours(cutoff - alert.ends)} before the cutoff"
        )
        return Finding(
            DELAYED_ARRIVAL,
            "Warning that ends early in the workday.",
            (level, severity, timing),
            (f"An extension past {_clock(cutoff, period)} would raise this to Unscheduled leave or telework.",),
        )
    if alert.starts > period.opens:
        timing = Crossing(
            f"Hazard starts after opening at {_clock(period.opens, period)}",
            f"starts {_clock(alert.starts, period)}",
            f"{_hours(alert.starts - period.opens)} after opening",
        )
        return Finding(
            EARLY_DISMISSAL,
            "Warning that starts during the workday.",
            (level, severity, timing),
            ("A start at or before opening would raise this to Unscheduled leave or telework.",),
        )

    timing = Crossing(
        cutoff_text,
        f"ends {_clock(alert.ends, period)}" if alert.ends else "no end time given",
        f"{_hours(alert.ends - cutoff)} past the cutoff" if alert.ends else "treated as lasting all day",
    )
    if roads is not None and roads.closures >= closures_needed:
        return Finding(
            FULL_CLOSURE,
            "Warning during work hours with a full road closure in the county.",
            (level, severity, timing, road),
            ("The road reopening would lower this to Unscheduled leave or telework.",),
        )
    return Finding(
        UNSCHEDULED_LEAVE,
        "Warning during work hours with no full road closure known in the county.",
        (level, severity, timing, road),
        (
            "A full road closure in the county would raise this to Full closure.",
            f"An NWS upgrade to {severity_cutoff} severity would raise this to Full closure.",
            f"An end time at or before {_clock(cutoff, period)} would lower this to Delayed arrival.",
            "Cancellation of the warning would return this to Normal operations.",
        ),
    )


def recommend(alerts, roads, period, now):
    """Recommend a posture for one operating period. `roads` is None when no road data is available."""
    in_scope = [alert for alert in alerts if alert.event in LADDER]
    findings = [(_assess(alert, LADDER[alert.event][1], roads, period, now), alert) for alert in in_scope]
    if findings:
        # The strongest posture wins.
        finding, deciding = max(findings, key=lambda pair: pair[0].posture)
        confidence = CONFIDENCE_BY_CERTAINTY[deciding.certainty]
    else:
        finding = Finding(
            NORMAL,
            "No flood, wind or winter alert covers the facility.",
            would_change=("Any flood, wind or winter Watch, Advisory or Warning covering the facility.",),
        )
        deciding = None
        confidence = "high"
    if roads is None:
        confidence = CONFIDENCE_STEPS[max(CONFIDENCE_STEPS.index(confidence) - 1, 0)]

    return Recommendation(
        posture=finding.posture,
        rule=finding.rule,
        crossings=finding.crossings,
        would_change=finding.would_change,
        confidence=confidence,
        period=period,
        alert=deciding,
        other_alerts=tuple(alert for alert in in_scope if alert is not deciding),
        out_of_scope=tuple(alert for alert in alerts if alert.event not in LADDER),
    )
