"""Print a live recommendation for the facility.

Usage: python -m closure_call [--lat LATITUDE --lon LONGITUDE]
"""

import argparse
import textwrap
from datetime import datetime, timezone

from closure_call import nws
from closure_call.facility import load_facility, operating_period, placed
from closure_call.notify import build_package, rationale
from closure_call.roads import get_road_context, get_road_summary
from closure_call.rules import POSTURES, recommend


def _describe(alert, tz):
    ends = alert.ends.astimezone(tz).strftime("%a %H:%M") if alert.ends else "no end time"
    return (
        f"{alert.event} | {alert.severity}, {alert.certainty}, {alert.urgency} | "
        f"{alert.starts.astimezone(tz):%a %H:%M} to {ends} | "
        f"fetched {alert.fetched_at:%Y-%m-%d %H:%M:%S} UTC\n      {alert.source}"
    )


def main():
    parser = argparse.ArgumentParser(description="Print a live closure recommendation for the facility.")
    parser.add_argument("--lat", type=float, help="move the facility to this latitude")
    parser.add_argument("--lon", type=float, help="move the facility to this longitude")
    args = parser.parse_args()
    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon must be given together")

    facility = load_facility()
    latitude = facility.latitude if args.lat is None else args.lat
    longitude = facility.longitude if args.lon is None else args.lon

    now = datetime.now(timezone.utc)
    place = nws.get_point_info(latitude, longitude)
    facility = placed(facility, latitude, longitude, place.county)
    alerts = nws.get_active_alerts(facility.latitude, facility.longitude)
    period = operating_period(facility, place.timezone, now)
    roads = get_road_summary(place)
    context = get_road_context(place)
    result = recommend(alerts, roads=roads, period=period, now=now)
    tz = period.opens.tzinfo

    print(facility.name)
    print(f"Location: near {place.city}, {place.state} ({facility.latitude}, {facility.longitude})")
    print(f"Decision time: {now.astimezone(tz):%a %Y-%m-%d %H:%M %Z}")
    print(f"Operating period: {period.opens:%a %H:%M} to {period.closes:%H:%M}")
    print()
    print(f"RECOMMENDATION: {result.posture} - {POSTURES[result.posture]}")
    print(f"Rule: {result.rule}")
    print(f"Confidence: {result.confidence}")
    print()
    print("Thresholds checked:")
    for crossing in result.crossings:
        print(f"  - {crossing.threshold} | observed: {crossing.observed} | {crossing.margin}")
    print("What would change it:")
    for change in result.would_change:
        print(f"  - {change}")
    print("Inputs:")
    if result.alert:
        print(f"  - DECIDING: {_describe(result.alert, tz)}")
    for alert in result.other_alerts:
        print(f"  - {_describe(alert, tz)}")
    if roads is None:
        print(f"  - State road data: unavailable (no road feed for {place.state})")
        if context:
            print(
                f"  - TomTom context, not counted: {context.closed_segments} closed road segments in "
                f"{place.county} County, {context.on_numbered_roads} on numbered roads | "
                f"fetched {context.fetched_at:%Y-%m-%d %H:%M:%S} UTC\n      {context.source}"
            )
    else:
        print(
            f"  - Road data, {place.county} County: full closures {roads.closures}, major delays {roads.major_delays}, "
            f"counted events {len(roads.events)} | fetched {roads.fetched_at:%Y-%m-%d %H:%M:%S} UTC\n"
            f"      {roads.source}"
        )
    if result.out_of_scope:
        print("Active but not evaluated (outside flood, wind and winter):")
        for alert in result.out_of_scope:
            print(f"  - {_describe(alert, tz)}")
    print()
    print("Rationale (ready to paste into an email):")
    print(textwrap.fill(rationale(result, facility, place, roads, now, context), width=100))
    print()
    print("Notification package if the manager accepts this recommendation (nothing is sent):")
    messages = {}
    for notice in build_package(result.posture, facility, period, result.alert):
        how = " + ".join(notice.channels) if notice.included else "not notified"
        print(f"  - {notice.name:14} {how:18} {notice.reason}")
        if notice.included:
            messages.setdefault(notice.message, []).append(notice.name)
    for message, names in messages.items():
        print(f"\n  Message to {', '.join(names)}:")
        print(textwrap.indent(textwrap.fill(message, width=96), "    "))


if __name__ == "__main__":
    main()
