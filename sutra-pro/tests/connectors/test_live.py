"""Live checks against the REAL claude and codex CLIs on the owner's own logins (CN-9, connectors design 7 and 9).

They run only with SUTRA_LIVE=1 (`tests/conftest.py` skips `live`): `SUTRA_LIVE=1 scripts/py -m pytest tests/connectors/test_live.py -q -m live`.
A CLI that is not installed or not signed in skips its tests. Each CLI gets THREE tiny calls (the list below needs three, not two):

    1. one-shot native schema      round trip, native schema accepted (for Codex: the strict-schema form), `how == "native"`
    2. chat turn 1 with the sutra tools   a real MCP tool call by the model (`sutra_models_list` needs no database)
    3. chat turn 2                 resume keeps the provider session, and the usage of the turn (a delta) is not negative

These close the UNVERIFIED items of connectors.md section 9 that a model has to answer: the Codex strict schema against the real
API, the MCP tool call on each CLI, and the usage delta on resume. Nothing here asserts on a model's wording, only on shape.
"""
from __future__ import annotations

import json
import shutil

import pytest

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import ConnectorError
from sutra_app.connectors.models import ConnectorConfig, Message, SessionSpec

pytestmark = pytest.mark.live

CALL_TIMEOUT_S = 240.0
SCHEMA = {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"], "additionalProperties": False}


@pytest.fixture(scope="module", params=["claude", "codex"])
def live(request, tmp_path_factory):
    name = request.param
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")
    root = tmp_path_factory.mktemp(f"live-{name}")
    cfg = ConnectorConfig(data_dir=root / "data", work_root=root / "work")
    connector = ClaudeConnector(cfg) if name == "claude" else CodexConnector(cfg)
    try:
        auth = connector.probe_auth()
    except ConnectorError as err:
        pytest.skip(f"{name} status could not be read: {err.user_message()}")
    if auth.signed_in is not True or auth.billing == "api_key":
        pytest.skip(f"{name} is not signed in with a subscription login")
    yield connector
    connector.runner.stop_all()


def test_native_schema_round_trip(live):
    result = live.call_json_result('Reply with JSON {"word": "ok"} and nothing else.', schema=SCHEMA, timeout=CALL_TIMEOUT_S, effort="low")
    assert result.how == "native"
    assert isinstance(result.value, dict) and isinstance(result.value.get("word"), str) and result.value["word"]
    assert result.turn.provider == live.name and result.turn.model
    assert result.turn.usage.total >= 0 and result.calls_made == 1


def test_chat_turn_calls_an_mcp_tool_and_resume_reports_a_usage_delta(live):
    state = live.start(SessionSpec(session_id=f"live_{live.name}", provider=live.name, tool_profile="sutra"))
    seen = []
    first = live.send(state, Message(role="user", text="Call the tool sutra_models_list exactly once, then reply with the word done."),
                      timeout_s=CALL_TIMEOUT_S, on_event=seen.append)
    try:
        calls = [e for e in seen if e.kind == "tool_call"]
        assert calls, "the model made no tool call"
        named = [e for e in calls if "name" in e.data]
        assert all("sutra_models_list" in json.dumps(e.data) for e in named), [e.data for e in calls]    # Codex names no tool (observed)
        assert first.text.strip()
        assert state.provider_session_id and state.turns == 1
        session_id = state.provider_session_id

        second = live.send(state, Message(role="user", text="Reply with the single word ok."), timeout_s=CALL_TIMEOUT_S)
        assert state.provider_session_id == session_id and state.turns == 2          # the turn was a resume, not a new session
        for turn in (first, second):
            assert all(getattr(turn.usage, field) >= 0 for field in type(turn.usage).model_fields)
        assert second.usage.total >= 0
    finally:
        live.forget(state)
