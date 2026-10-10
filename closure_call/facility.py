"""The synthetic facility: one county USDA Service Center profile that can be placed anywhere."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "facility.json"


@dataclass(frozen=True)
class Employee:
    id: str
    name: str
    role: str
    home_office: str  # id of the facility this person is assigned to
    status_today: str  # "in_office" (at this building), "telework" or "detail_elsewhere"
    essential: bool
    prefers_voice_call: bool  # accessibility: a voice call in place of a text
    email: str
    phone: str


@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    latitude: float
    longitude: float
    opens: time
    closes: time
    open_days: tuple[int, ...]  # 0 = Monday ... 6 = Sunday
    employees: tuple[Employee, ...]


@dataclass(frozen=True)
class Period:
    """One operating day at the facility, in the facility's own time zone."""

    opens: datetime
    closes: datetime


def load_facility(path=DEFAULT_PATH):
    raw = json.loads(Path(path).read_text())
    hours = raw["hours"]
    return Facility(
        id=raw["id"],
        name=raw["name"],
        latitude=raw["latitude"],
        longitude=raw["longitude"],
        opens=time.fromisoformat(hours["opens"]),
        closes=time.fromisoformat(hours["closes"]),
        open_days=tuple(hours["open_days"]),
        employees=tuple(Employee(**person) for person in raw["employees"]),
    )


def placed(facility, latitude, longitude, county):
    """The same facility profile at another location, named after the county it sits in."""
    return replace(facility, latitude=latitude, longitude=longitude, name=f"{county} County {facility.name}")


def operating_period(facility, timezone_name, now):
    """The operating day a decision made at `now` applies to.

    That is today if the office has not closed yet, otherwise the next open day.
    """
    local_now = now.astimezone(ZoneInfo(timezone_name))
    for days_ahead in range(8):
        day = local_now.date() + timedelta(days=days_ahead)
        closes = datetime.combine(day, facility.closes, local_now.tzinfo)
        if day.weekday() in facility.open_days and closes > local_now:
            return Period(opens=datetime.combine(day, facility.opens, local_now.tzinfo), closes=closes)
    raise ValueError("The facility has no open days.")
