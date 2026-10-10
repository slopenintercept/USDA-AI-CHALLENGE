"""List places with a live flood, wind or winter alert, for placing the facility on demo morning.

Usage: python -m closure_call.find [--hazard flood|wind|winter] [--limit N]

Each row is checked: the coordinates printed are confirmed to be covered by that alert.
"""

import argparse
from datetime import datetime

from closure_call import nws
from closure_call.geo import point_inside
from closure_call.rules import LADDER

RUNG_ORDER = {"warning": 0, "advisory": 1, "watch": 2}


def candidates(features, hazard=None):
    """Alerts for the hazards in scope: Warnings first, and within a level the longest-lasting first."""

    def order(feature):
        properties = feature["properties"]
        ends = properties.get("ends")
        lasts_until = datetime.fromisoformat(ends).timestamp() if ends else float("inf")
        return RUNG_ORDER[LADDER[properties["event"]][1]], -lasts_until

    in_scope = [
        feature
        for feature in features
        if feature["properties"]["event"] in LADDER
        and (hazard is None or LADDER[feature["properties"]["event"]][0] == hazard)
    ]
    return sorted(in_scope, key=order)


def location(feature):
    """A (latitude, longitude) inside the alert's area: its own outline, or its first zone when it has none."""
    shape = feature["geometry"] or nws.get_shape(feature["properties"]["affectedZones"][0])
    ring = shape["coordinates"][0] if shape["type"] == "Polygon" else shape["coordinates"][0][0]
    longitude, latitude = point_inside([tuple(point) for point in ring])
    return round(latitude, 4), round(longitude, 4)


def main():
    parser = argparse.ArgumentParser(description="List places with a live flood, wind or winter alert.")
    parser.add_argument("--hazard", choices=["flood", "wind", "winter"], help="show only this hazard")
    parser.add_argument("--limit", type=int, default=8, help="how many places to list (default 8)")
    args = parser.parse_args()

    listed = 0
    for feature in candidates(nws.get_all_active_features(), args.hazard):
        if listed == args.limit:
            break
        properties = feature["properties"]
        latitude, longitude = location(feature)
        # Confirm the point really is covered, so the coordinates work when pasted in.
        if not any(alert.id == properties["id"] for alert in nws.get_active_alerts(latitude, longitude)):
            continue
        listed += 1
        ends = properties.get("ends")
        until = f"until {datetime.fromisoformat(ends):%a %H:%M} local" if ends else "no end time given"
        print(f"{properties['event']} | {properties['severity']} | {until} | {properties['areaDesc'][:70]}")
        print(f"    latitude {latitude}, longitude {longitude}")
        print(f"    .venv/bin/python -m closure_call --lat {latitude} --lon {longitude}")
    if not listed:
        print("No live flood, wind or winter alerts found.")


if __name__ == "__main__":
    main()
