"""Who is told what once a posture is decided, and the plain-language rationale for it.

The system drafts and routes messages. Nothing is actually sent.
"""

from dataclasses import dataclass
from datetime import timedelta

from closure_call.rules import (
    DELAYED_ARRIVAL,
    EARLY_DISMISSAL,
    FULL_CLOSURE,
    NORMAL,
    POSTURES,
    THRESHOLDS,
    UNSCHEDULED_LEAVE,
)


@dataclass(frozen=True)
class Notice:
    """One person on the roster: whether they are told, why, how, and what."""

    employee_id: str
    name: str
    included: bool
    reason: str
    channels: tuple[str, ...] = ()
    message: str = ""


INSTRUCTIONS = {
    DELAYED_ARRIVAL: (
        "Report by {late} instead of {opens}. If your route is unsafe, ask your supervisor "
        "about unscheduled leave or telework."
    ),
    EARLY_DISMISSAL: "Report as usual and plan to leave early. Your supervisor will confirm the departure time.",
    UNSCHEDULED_LEAVE: (
        "The office is open, but you may take unscheduled leave or telework. "
        "Tell your supervisor which you choose before {opens}."
    ),
    FULL_CLOSURE: (
        "Do not report to the building. Telework if you are able to, and contact your supervisor with questions."
    ),
}


def _a(word):
    return f"an {word}" if word[0] in "AEIOU" else f"a {word}"


def _headline(posture, facility, period, alert):
    """What is happening: the same first sentences for everyone."""
    headline = f"{facility.name}: {POSTURES[posture]} on {period.opens:%A %B %d}."
    if alert is None:
        return headline
    tz = period.opens.tzinfo
    until = f" until {alert.ends.astimezone(tz):%a %H:%M}" if alert.ends else ""
    return f"{headline} The National Weather Service has {_a(alert.event)} in effect{until}."


def build_package(posture, facility, period, alert):
    """One Notice for every person on the roster, for the posture the manager decided.

    Who is expected at the building today decides the list, not who is assigned to it.
    """
    headline = _headline(posture, facility, period, alert)
    late = period.opens + timedelta(hours=THRESHOLDS["delayed_arrival_hours"].value)
    notices = []
    for person in facility.employees:
        if posture == NORMAL:
            notice = Notice(person.id, person.name, False, "Normal operations: no notification needed.")
        elif person.status_today == "detail_elsewhere":
            notice = Notice(person.id, person.name, False, "Assigned here but on detail at another site today.")
        elif person.status_today == "telework":
            notice = Notice(
                person.id,
                person.name,
                True,
                "Already teleworking today: information only, no early text.",
                ("email",),
                f"{headline} You are scheduled to telework today, so no action is needed.",
            )
        else:
            # Action is needed before the commute, so this goes by text (or voice call) as well as email.
            channels = ("voice call" if person.prefers_voice_call else "text", "email")
            if person.essential:
                reason = "Essential personnel expected at this building today."
                message = (
                    f"{headline} You are essential personnel, so your reporting requirement does not change. "
                    "Report as scheduled. If you cannot travel safely, call your supervisor."
                )
            else:
                assigned_here = person.home_office == facility.id
                where = "assigned here" if assigned_here else f"detailed here from {person.home_office}"
                reason = f"Expected at this building today ({where})."
                instruction = INSTRUCTIONS[posture].format(late=f"{late:%H:%M}", opens=f"{period.opens:%H:%M}")
                message = (
                    f"{headline} This applies to you: you are expected at this building today. {instruction}"
                )
            notice = Notice(person.id, person.name, True, reason, channels, message)
        notices.append(notice)
    return notices


def rationale(result, facility, place, roads, now, context=None):
    """One plain-language paragraph a manager could paste into an email."""
    period = result.period
    tz = period.opens.tzinfo
    sentences = [
        f"As of {now.astimezone(tz):%A %B %d at %H:%M %Z}, the recommended posture for {facility.name} "
        f"near {place.city}, {place.state} is {POSTURES[result.posture]} for the operating day of "
        f"{period.opens:%A %B %d} ({period.opens:%H:%M} to {period.closes:%H:%M})."
    ]
    alert = result.alert
    if alert:
        ends = f"to {alert.ends.astimezone(tz):%A %H:%M}" if alert.ends else "with no stated end time"
        sentences.append(
            f"The National Weather Service has {_a(alert.event)} in effect for this location from "
            f"{alert.starts.astimezone(tz):%A %H:%M} {ends}, rated {alert.severity} in severity and "
            f"{alert.certainty} in certainty."
        )
    else:
        sentences.append("The National Weather Service has no flood, wind or winter alert covering this location.")
    if roads is None:
        sentences.append("State road data was not available for this location.")
        if context:
            sentences.append(
                f"TomTom lists {context.closed_segments} closed road segments in the county, "
                f"{context.on_numbered_roads} of them on numbered roads. These are shown for context only and "
                "were not counted, because TomTom gives no cause for a closure."
            )
    else:
        sentences.append(
            f"State road data for the county shows {roads.closures} full road closure(s) and "
            f"{roads.major_delays} major delay(s)."
        )
    sentences.append(f"The rule applied: {result.rule}")
    lowered = " It was lowered one step because road data is missing." if roads is None else ""
    sentences.append(f"Confidence is {result.confidence}.{lowered}")
    if result.would_change:
        sentences.append("What would change this: " + " ".join(result.would_change))
    if result.out_of_scope:
        names = ", ".join(sorted({other.event for other in result.out_of_scope}))
        sentences.append(f"Also active here but outside what this system evaluates (flood, wind, winter): {names}.")
    return " ".join(sentences)
