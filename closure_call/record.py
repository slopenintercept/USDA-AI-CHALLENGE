"""The decision record: one JSON line per decision, and lines are only ever added.

Every record carries its own SHA-256 fingerprint and the fingerprint of the record
before it. Changing or removing an earlier record breaks that chain, and `verify`
reports it. This makes edits evident; it cannot stop someone who rebuilds the whole file.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, time, timezone
from pathlib import Path

from closure_call.rules import POSTURES

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "records" / "decisions.jsonl"
FIRST_RECORD = "0" * 64  # stands in for "the record before" on the first line


def _plain(value):
    """JSON form of the date and time values inside the saved dataclasses."""
    if isinstance(value, (datetime, time)):
        return value.isoformat()
    raise TypeError(f"Cannot save a {type(value).__name__}.")


def _fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def make_decision(recommended, decided, decided_by, reason, decided_at):
    """The human decision. A written reason is required when it differs from the recommendation."""
    if not decided_by.strip():
        raise ValueError("The record needs the name of the person who decided.")
    if decided != recommended and not reason.strip():
        raise ValueError("A written reason is required when the decision differs from the recommendation.")
    return {
        "posture": decided,
        "posture_name": POSTURES[decided],
        "decided_by": decided_by.strip(),
        "decided_at": decided_at,
        "reason": reason.strip(),
        "differs_from_recommendation": decided != recommended,
    }


def build_entry(
    facility, place, roads, recommendation, rationale, decision, notices, corrects=None, road_context=None
):
    """Everything known at decision time, in the shape that gets saved.

    `corrects` is the sequence number of an earlier record this one corrects.
    """
    return {
        "facility": asdict(facility),
        "place": asdict(place),
        "roads": asdict(roads) if roads else None,
        "road_context": asdict(road_context) if road_context else None,  # shown to the manager, never counted
        # Includes every alert as received, with its source URL and fetch time.
        "recommendation": {**asdict(recommendation), "posture_name": POSTURES[recommendation.posture]},
        "rationale": rationale,
        "decision": decision,
        "notifications": [asdict(notice) for notice in notices],
        "corrects": corrects,
    }


def read_all(path=DEFAULT_PATH):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def append(entry, path=DEFAULT_PATH):
    """Add one record to the end of the file and return it as saved."""
    path = Path(path)
    records = read_all(path)
    corrects = entry.get("corrects")
    if corrects is not None and not any(record["sequence"] == corrects for record in records):
        raise ValueError(f"Record {corrects} does not exist, so it cannot be corrected.")

    record = json.loads(json.dumps(entry, default=_plain))
    record["sequence"] = len(records) + 1
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    record["previous_fingerprint"] = records[-1]["fingerprint"] if records else FIRST_RECORD
    record["fingerprint"] = _fingerprint(record)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def verify(path=DEFAULT_PATH):
    """Problems found in the chain. An empty list means no saved record was changed or removed."""
    path = Path(path)
    problems = []
    previous = FIRST_RECORD
    lines = path.read_text().splitlines() if path.exists() else []
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"Line {number}: is not a readable record.")
            previous = None
            continue
        saved = record.pop("fingerprint", None)
        if record.get("sequence") != number:
            problems.append(f"Line {number}: expected record {number}, found record {record.get('sequence')}.")
        if record.get("previous_fingerprint") != previous:
            problems.append(f"Line {number}: does not follow the record before it.")
        if saved != _fingerprint(record):
            problems.append(f"Line {number}: contents do not match its fingerprint.")
        previous = saved
    return problems
