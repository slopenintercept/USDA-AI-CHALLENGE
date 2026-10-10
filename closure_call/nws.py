"""Live National Weather Service data for one facility location.

API documentation: https://www.weather.gov/documentation/services-web-api
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

API = "https://api.weather.gov"
# The NWS API needs no key, but asks every client to identify itself.
HEADERS = {
    "User-Agent": "closure-call (USDA AI Challenge hackathon project)",
    "Accept": "application/geo+json",
}
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class Alert:
    id: str
    event: str  # for example "Flood Warning"
    severity: str  # Extreme, Severe, Moderate, Minor or Unknown
    certainty: str  # Observed, Likely, Possible, Unlikely or Unknown
    urgency: str  # Immediate, Expected, Future, Past or Unknown
    starts: datetime
    ends: datetime | None  # None means the NWS gave no end time
    headline: str
    area: str
    source: str  # this alert's own URL
    fetched_at: datetime
    raw: dict = field(default_factory=dict, compare=False, repr=False)  # the alert as received


@dataclass(frozen=True)
class PointInfo:
    timezone: str  # IANA name, for example "America/Chicago"
    city: str
    state: str
    county: str  # name only, for example "Coffee"
    # The county outline as rings of (longitude, latitude) points.
    county_rings: tuple = field(default=(), compare=False, repr=False)


def _get(url, params=None):
    response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def parse_alert(feature, fetched_at):
    p = feature["properties"]
    return Alert(
        id=p["id"],
        event=p["event"],
        severity=p["severity"],
        certainty=p["certainty"],
        urgency=p["urgency"],
        # "onset" and "ends" describe the hazard itself. "effective" and "expires" describe
        # the message, which the NWS reissues, so "expires" is not when the hazard ends.
        starts=datetime.fromisoformat(p.get("onset") or p["effective"]),
        ends=datetime.fromisoformat(p["ends"]) if p.get("ends") else None,
        headline=p.get("headline") or "",
        area=p.get("areaDesc") or "",
        source=p["@id"],
        fetched_at=fetched_at,
        raw=p,
    )


def get_active_alerts(latitude, longitude):
    """Alerts in effect right now whose area covers this exact point."""
    data = _get(f"{API}/alerts/active", {"point": f"{latitude:.4f},{longitude:.4f}"})
    fetched_at = datetime.now(timezone.utc)
    return [parse_alert(feature, fetched_at) for feature in data["features"]]


def get_point_info(latitude, longitude):
    """Time zone, nearest place and county for a location, so the facility can be moved by coordinates alone."""
    p = _get(f"{API}/points/{latitude:.4f},{longitude:.4f}")["properties"]
    place = p["relativeLocation"]["properties"]
    county = _get(p["county"])
    shape = county["geometry"]
    polygons = [shape["coordinates"]] if shape["type"] == "Polygon" else shape["coordinates"]
    return PointInfo(
        timezone=p["timeZone"],
        city=place["city"],
        state=place["state"],
        county=county["properties"]["name"],
        county_rings=tuple(tuple(map(tuple, polygon[0])) for polygon in polygons),
    )
