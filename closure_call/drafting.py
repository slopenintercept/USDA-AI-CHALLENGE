"""Optional AI wording: Claude rewords the rationale and the message drafts.

The rules decide the posture and the templates state the facts. Claude only improves
the wording. Every rewrite is checked against the template it came from, and the
template is kept whenever a check fails or the API is unavailable.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL = "claude-opus-5-5"

SYSTEM = """You improve the wording of official weather closure notices for a federal office.

Each piece of text you receive was assembled from fixed templates and verified facts. Rewrite each \
piece so it reads naturally and is easy to act on at 5 in the morning.

Rules:
- Do not add, remove or change any fact, time, date, number, name, place or instruction.
- Keep every clock time exactly as written, for example 08:00.
- Keep every phrase listed under keep_exactly exactly as written.
- Do not add advice, apologies, greetings or sign-offs.
- The piece with id "rationale" stays one paragraph. Every other piece is a message to employees \
and stays short enough to read as a text message.
- Return every piece you were given, with the same id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "pieces": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pieces"],
    "additionalProperties": False,
}

NUMBER = re.compile(r"\d+(?:[:.]\d+)*")
CLOCK_TIME = re.compile(r"\d{1,2}:\d{2}")


class DraftingError(Exception):
    """Claude's wording could not be produced, so the templates stay in use."""


@dataclass(frozen=True)
class Draft:
    rationale: str  # the wording to use: Claude's, or the template where a check failed
    messages: dict  # template message -> the wording to use for it
    model: str  # the model that wrote the wording
    rejected: tuple[str, ...]  # pieces that kept their template wording, and why


def problems(original, rewrite, keep):
    """Reasons a rewrite cannot be used. An empty list means it passed every check."""
    found = []
    known = set(NUMBER.findall(original))
    added = sorted({number for number in NUMBER.findall(rewrite) if number not in known})
    if added:
        found.append(f"adds numbers that are not in the facts ({', '.join(added)})")
    dropped_times = sorted(time for time in set(CLOCK_TIME.findall(original)) if time not in rewrite)
    if dropped_times:
        found.append(f"drops a time ({', '.join(dropped_times)})")
    dropped = [phrase for phrase in keep if phrase.lower() in original.lower() and phrase.lower() not in rewrite.lower()]
    if dropped:
        found.append(f"drops a required name ({', '.join(dropped)})")
    return found


def draft(rationale, messages, keep, client=None):
    """Ask Claude to reword the rationale and each message, then check every rewrite.

    `keep` lists phrases that must survive, such as the status and alert names. A piece that
    fails a check keeps its template wording. Raises DraftingError when no draft comes back.
    """
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise DraftingError("No Anthropic API key is set.")
        client = anthropic.Anthropic(timeout=90.0, max_retries=1)

    pieces = {"rationale": rationale, **{f"message-{number}": text for number, text in enumerate(messages, start=1)}}
    request = {"keep_exactly": keep, "pieces": [{"id": name, "text": text} for name, text in pieces.items()]}
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(request, indent=1)}],
            # Rewording is a simple task, and low effort keeps the screen responsive.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            # If a safety classifier declines the request, the API retries it on its recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as error:
        raise DraftingError("The Anthropic API key was rejected.") from error
    except anthropic.RateLimitError as error:
        raise DraftingError("The Anthropic API rate limit was reached.") from error
    except anthropic.APIStatusError as error:
        raise DraftingError(f"The Anthropic API returned an error ({error.status_code}).") from error
    except anthropic.APIConnectionError as error:
        raise DraftingError("The Anthropic API could not be reached.") from error
    if response.stop_reason != "end_turn":
        raise DraftingError(f"Claude did not finish a draft (stop reason: {response.stop_reason}).")

    text = next(block.text for block in response.content if block.type == "text")
    rewritten = {piece["id"]: piece["text"] for piece in json.loads(text)["pieces"]}

    final, rejected = {}, []
    for name, original in pieces.items():
        rewrite = rewritten.get(name)
        issues = ["was not returned"] if rewrite is None else problems(original, rewrite, keep)
        final[name] = original if issues else rewrite
        rejected.extend(f"{name} {issue}" for issue in issues)
    return Draft(
        rationale=final["rationale"],
        messages={text: final[f"message-{number}"] for number, text in enumerate(messages, start=1)},
        model=response.model,
        rejected=tuple(rejected),
    )
