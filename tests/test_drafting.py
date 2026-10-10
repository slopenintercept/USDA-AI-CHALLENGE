"""The checks that keep Claude's wording faithful to the facts. No test calls the real API."""

import json
from types import SimpleNamespace

import pytest

from closure_call import drafting

RATIONALE = (
    "As of Monday October 12 at 05:00 CDT, the recommended posture is Unscheduled leave or telework. "
    "The National Weather Service has a Flood Warning in effect until Tuesday 09:00."
)
MESSAGE = "Delayed arrival on Monday October 12. A Flood Warning is in effect. Report by 10:00 instead of 08:00."
KEEP = ["Unscheduled leave or telework", "Delayed arrival", "Flood Warning"]


def test_a_faithful_rewrite_passes():
    rewrite = "Delayed arrival, Monday October 12: a Flood Warning is in effect. Please report by 10:00, not 08:00."
    assert drafting.problems(MESSAGE, rewrite, KEEP) == []


def test_a_new_number_is_caught():
    rewrite = MESSAGE + " Expect about 3 inches of water."
    assert drafting.problems(MESSAGE, rewrite, KEEP) == ["adds numbers that are not in the facts (3)"]


def test_a_changed_time_is_caught_as_both_added_and_dropped():
    rewrite = MESSAGE.replace("10:00", "10:30")
    assert drafting.problems(MESSAGE, rewrite, KEEP) == [
        "adds numbers that are not in the facts (10:30)",
        "drops a time (10:00)",
    ]


def test_a_dropped_alert_name_is_caught_whatever_its_capitals():
    assert drafting.problems(MESSAGE, MESSAGE.replace("Flood Warning", "flood warning"), KEEP) == []
    rewrite = MESSAGE.replace("A Flood Warning is in effect.", "There is flooding.")
    assert drafting.problems(MESSAGE, rewrite, KEEP) == ["drops a required name (Flood Warning)"]


def test_a_phrase_that_was_never_in_the_template_is_not_required():
    assert drafting.problems(RATIONALE, RATIONALE, KEEP) == []  # "Delayed arrival" is not in the rationale


class FakeClient:
    """Stands in for the Anthropic client and returns whatever pieces it is given."""

    def __init__(self, pieces, stop_reason="end_turn"):
        self.pieces, self.stop_reason, self.request = pieces, stop_reason, None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.request = request
        text = json.dumps({"pieces": [{"id": name, "text": value} for name, value in self.pieces.items()]})
        return SimpleNamespace(
            stop_reason=self.stop_reason, model="claude-opus-5-5", content=[SimpleNamespace(type="text", text=text)]
        )


def test_claude_wording_is_used_when_it_passes_the_checks():
    better_rationale = RATIONALE.replace("the recommended posture is", "we recommend")
    better_message = MESSAGE.replace("Report by 10:00 instead of 08:00.", "Please report by 10:00, not 08:00.")
    client = FakeClient({"rationale": better_rationale, "message-1": better_message})
    result = drafting.draft(RATIONALE, [MESSAGE], KEEP, client)
    assert result.rationale == better_rationale
    assert result.messages == {MESSAGE: better_message}
    assert result.model == "claude-opus-5-5"
    assert result.rejected == ()


def test_the_request_sends_only_the_template_text_and_the_names_to_keep():
    client = FakeClient({"rationale": RATIONALE, "message-1": MESSAGE})
    drafting.draft(RATIONALE, [MESSAGE], KEEP, client)
    sent = json.loads(client.request["messages"][0]["content"])
    assert sent == {
        "keep_exactly": KEEP,
        "pieces": [{"id": "rationale", "text": RATIONALE}, {"id": "message-1", "text": MESSAGE}],
    }
    assert client.request["model"] == "claude-opus-5-5"


def test_a_rewrite_that_fails_a_check_falls_back_to_its_template_only():
    better_rationale = RATIONALE.replace("the recommended posture is", "we recommend")
    client = FakeClient({"rationale": better_rationale, "message-1": MESSAGE.replace("10:00", "11:00")})
    result = drafting.draft(RATIONALE, [MESSAGE], KEEP, client)
    assert result.rationale == better_rationale
    assert result.messages == {MESSAGE: MESSAGE}
    assert result.rejected == (
        "message-1 adds numbers that are not in the facts (11:00)",
        "message-1 drops a time (10:00)",
    )


def test_a_piece_claude_leaves_out_keeps_its_template():
    result = drafting.draft(RATIONALE, [MESSAGE], KEEP, FakeClient({"rationale": RATIONALE}))
    assert result.messages == {MESSAGE: MESSAGE}
    assert result.rejected == ("message-1 was not returned",)


def test_a_declined_or_cut_off_response_is_an_error_not_a_draft():
    with pytest.raises(drafting.DraftingError, match="stop reason: refusal"):
        drafting.draft(RATIONALE, [MESSAGE], KEEP, FakeClient({}, stop_reason="refusal"))


def test_without_a_key_no_request_is_attempted(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(drafting.DraftingError, match="No Anthropic API key"):
        drafting.draft(RATIONALE, [MESSAGE], KEEP)
