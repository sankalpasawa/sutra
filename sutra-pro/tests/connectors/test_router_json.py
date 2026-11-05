"""Router JSON strategy: native, prompted, repair, `native_blocked`, `complete()` with a schema (connectors design 3.6, D33,
S2-models-04, work package CN-7). The real ClaudeConnector and CodexConnector run against the fake CLIs; the stub covers `how`."""
from __future__ import annotations

import json
import pytest
from pydantic import BaseModel

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import InvalidJsonError
from sutra_app.connectors.models import ConnectorConfig, JsonRequest
from sutra_app.connectors.policy import parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.schema import schema_sha, to_json_schema
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink
from sutra_app.engine.port import CallTag, CompletionRequest

SCHEMA_DICT = {"type": "object", "properties": {"answer": {"type": "string"}, "extra": {"type": "string"}}, "required": ["answer"]}


class Out(BaseModel):
    answer: str


class Other(BaseModel):
    verdict: str


def policy(**defaults):
    base = {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
            "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": False,
            "tool_profile": "none", "idle_timeout_s": 120}
    base.update(defaults)
    return parse_policy({"version": 1, "providers": {"claude": {"model": "sonnet", "max_concurrency": 4},
                                                     "codex": {"model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": "read-only"}},
                         "defaults": base, "rules": [], "rates": {}})


@pytest.fixture
def rig(fake, tmp_path):
    class Rig:
        def __init__(self):
            self.fake = fake
            self.sink = MemoryUsageSink()
            self.sleeps = []

        def router(self, *names, pol=None, **kw):
            cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
            connectors = {n: (ClaudeConnector if n == "claude" else CodexConnector)(cfg) for n in names}
            return Router(connectors, pol or policy(), usage_sink=self.sink, sleep=self.sleeps.append, rng=lambda: 0.0, **kw)

        def json(self, router, schema=Out, text="hello"):
            return router.call_json(JsonRequest(user=text, schema=schema))

        def argvs(self, cli="claude"):
            return [c["argv"] for c in fake.model_calls(cli)]
    return Rig()


def block(router, provider, schema):
    """Mark a schema's native path as known-bad, so the first spawn is prompted."""
    connector = router.connectors[provider]
    router.native_blocked.add((provider, schema_sha(connector.transport_schema(to_json_schema(schema)))))


def test_native_structured_reply_is_the_pydantic_instance(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "hi"})
    result = rig.json(rig.router("claude"))
    assert result.value == Out(answer="hi") and result.how == "native" and result.calls_made == 1
    assert "--json-schema" in rig.argvs()[0]
    assert rig.sink.rows[0].how == "native" and rig.sink.rows[0].ok


def test_json_requests_use_the_low_effort_of_the_policy(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "hi"})
    rig.json(rig.router("claude"))
    argv = rig.argvs()[0]
    assert argv[argv.index("--effort") + 1] == "low"


def test_a_structured_error_switches_to_the_prompted_path_once(rig):
    rig.fake.sequence("structured_failed", "ok_plain").reply(text='{"answer": "via prompt"}')
    router = rig.router("claude")
    result = rig.json(router)
    assert result.value == Out(answer="via prompt") and result.how == "prompted" and result.calls_made == 2
    first, second = rig.argvs()
    assert "--json-schema" in first and "--json-schema" not in second
    assert [a["code"] for a in rig.sink.rows[0].detail["attempts"]] == ["structured", "ok"]
    assert rig.sink.rows[0].how == "prompted"


def test_native_blocklist_a_schema_that_failed_natively_starts_prompted_next_time(rig):
    rig.fake.sequence("structured_failed", "ok_plain").reply(text='{"answer": "x"}')
    router = rig.router("claude")
    rig.json(router)
    assert len(router.native_blocked) == 1 and next(iter(router.native_blocked))[0] == "claude"
    again = rig.json(router)
    assert again.how == "prompted" and again.calls_made == 1                 # one failed call per process, not one per request
    assert len(rig.argvs()) == 3 and "--json-schema" not in rig.argvs()[2]


def test_native_blocklist_is_per_schema(rig):
    rig.fake.sequence("structured_failed", "ok_plain", "ok_structured").reply(text='{"answer": "x"}', json={"verdict": "v"})
    router = rig.router("claude")
    rig.json(router)
    result = rig.json(router, schema=Other)
    assert "--json-schema" in rig.argvs()[2] and result.value == Other(verdict="v") and result.how == "native"


def test_native_blocklist_is_per_provider(rig):
    router = rig.router("claude", "codex")
    block(router, "claude", Out)
    assert not router._is_blocked("codex", router.connectors["codex"], to_json_schema(Out))
    assert router._is_blocked("claude", router.connectors["claude"], to_json_schema(Out))


def test_not_json_is_repaired_with_the_rejected_reply_quoted(rig):
    rig.fake.sequence("plain_not_json", "ok_plain").reply(text='{"answer": "fixed"}')
    router = rig.router("claude")
    block(router, "claude", Out)
    result = rig.json(router)
    assert result.value == Out(answer="fixed") and result.how == "repaired" and result.calls_made == 2
    repair_stdin = rig.fake.model_calls("claude")[1]["stdin"]
    assert "YOUR LAST REPLY WAS REJECTED" in repair_stdin and "Reply again with one JSON object only" in repair_stdin
    assert rig.sink.rows[0].how == "repaired" and len(rig.sink.rows) == 1


def test_a_reply_that_is_never_valid_raises_invalid_json_after_two_repairs(rig):
    rig.fake.sequence("plain_not_json")
    router = rig.router("claude")
    block(router, "claude", Out)
    with pytest.raises(InvalidJsonError) as e:
        rig.json(router)
    assert len(rig.argvs()) == 3 and e.value.detail["rounds"] == 2 and e.value.detail["calls"] == 3
    row, = rig.sink.rows
    assert row.ok is False and row.how == "prompted" and len(row.detail["attempts"]) == 3


def test_repair_rounds_come_from_the_policy(rig):
    rig.fake.sequence("plain_not_json")
    router = rig.router("claude", pol=policy(repair_rounds=0))
    block(router, "claude", Out)
    with pytest.raises(InvalidJsonError):
        rig.json(router)
    assert len(rig.argvs()) == 1


def test_a_reply_of_the_wrong_shape_names_the_field(rig):
    rig.fake.sequence("plain_json_wrong_shape")
    router = rig.router("claude", pol=policy(repair_rounds=0))
    block(router, "claude", Out)
    with pytest.raises(InvalidJsonError, match="answer"):
        rig.json(router)


def test_a_cut_off_reply_is_closed_and_read(rig):
    rig.fake.sequence("ok_plain").reply(text='{"answer": "cut off here')
    router = rig.router("claude")
    block(router, "claude", Out)
    assert rig.json(router).value == Out(answer="cut off here")


def test_a_dict_schema_returns_the_checked_dict(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "d"})
    result = rig.router("claude").call_json(JsonRequest(user="hi", schema=SCHEMA_DICT))
    assert result.value == {"answer": "d"} and result.as_tuple() == ({"answer": "d"}, result.usd, "native")


def test_a_dict_schema_rejects_a_missing_required_key(rig):
    rig.fake.sequence("ok_plain").reply(text='{"extra": "x"}')
    router = rig.router("claude", pol=policy(repair_rounds=0))
    block(router, "claude", SCHEMA_DICT)
    with pytest.raises(InvalidJsonError, match="answer"):
        router.call_json(JsonRequest(user="hi", schema=SCHEMA_DICT))


def test_no_schema_parses_one_json_object_on_the_prompted_path(rig):
    rig.fake.sequence("ok_plain").reply(text='Sure:\n```json\n{"x": 1}\n```')
    result = rig.router("claude").call_json(JsonRequest(user="hi"))
    assert result.value == {"x": 1} and result.how == "prompted"
    assert "--json-schema" not in rig.argvs()[0] and '{"type":"object"}' in rig.fake.model_calls("claude")[0]["stdin"]


def test_codex_gets_the_strict_schema_in_a_file_and_prunes_the_nulls(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "c", "extra": None})
    router = rig.router("codex")
    result = router.call_json(JsonRequest(user="hi", schema=SCHEMA_DICT))
    assert result.value == {"answer": "c"} and result.how == "native" and result.usd is None
    sent = json.loads(rig.fake.model_calls("codex")[0]["files"]["--output-schema"][0]["content"])
    assert sent["additionalProperties"] is False and sent["required"] == ["answer", "extra"]
    assert rig.sink.rows[0].usd is None and rig.sink.rows[0].tokens_in


def test_invalid_json_does_not_fall_back_by_default(rig):
    rig.fake.sequence("plain_not_json", cli="claude")
    rig.fake.sequence("ok_structured", cli="codex").reply(json={"answer": "codex"})
    router = rig.router("claude", "codex")
    block(router, "claude", Out)
    with pytest.raises(InvalidJsonError):
        rig.json(router)
    assert rig.fake.model_calls("codex") == []


def test_invalid_json_falls_back_when_the_policy_says_so(rig):
    rig.fake.sequence("plain_not_json", cli="claude")
    rig.fake.sequence("ok_structured", cli="codex").reply(json={"answer": "codex"})
    router = rig.router("claude", "codex", pol=policy(fallback_on_invalid_json=True))
    block(router, "claude", Out)
    result = rig.json(router)
    assert result.value == Out(answer="codex") and result.calls_made == 4
    assert rig.sink.rows[0].provider == "codex" and rig.sink.rows[0].detail["note"] == "claude gave invalid JSON, answered by codex"


def test_an_unauthenticated_reply_at_spawn_time_falls_back_with_a_note(rig):
    rig.fake.sequence("not_logged_in", cli="claude")
    rig.fake.sequence("ok_structured", cli="codex").reply(json={"answer": "codex"})
    router = rig.router("claude", "codex")
    result = rig.json(router)
    assert result.value == Out(answer="codex") and rig.sleeps == []
    assert rig.sink.rows[0].detail["note"] == "claude not signed in, answered by codex"
    assert router.health.peek_auth("claude") is None            # a not_signed_in error drops the cached sign-in


def test_the_stub_answers_a_schema_with_its_example_and_how_stub(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy(), connector="stub")
    result = router.call_json(JsonRequest(user="hi", schema=Out))
    assert result.value == Out(answer="stub") and result.how == "stub"


def test_a_scripted_reply_reaches_the_stub_in_a_json_request(tmp_path):
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    router = Router({"stub": StubConnector(cfg)}, policy(), connector="stub")
    result = router.call_json(JsonRequest(user="hi", schema=Out, scripted=lambda: '{"answer": "scripted"}'))
    assert result.value == Out(answer="scripted")


# ---- complete() with a json_schema: the native step only, no repair --------------------------------------------------------------

def complete(router, schema=SCHEMA_DICT, **kw):
    return router.complete(CompletionRequest(system="sys", user="hello", json_mode=True, json_schema=schema, tag=CallTag(function="identity"), **kw))


def test_complete_with_a_schema_returns_the_native_reply_text(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "n"})
    out = complete(rig.router("claude"))
    assert json.loads(out.text) == {"answer": "n"}
    assert out.structured == {"provider": "claude", "subtype": "success", "present": True}
    assert "--json-schema" in rig.argvs()[0]


def test_complete_never_repairs_and_hands_a_bad_reply_to_the_engine(rig):
    rig.fake.sequence("ok_plain").reply(text="not json at all")
    router = rig.router("claude")
    out = complete(router)
    assert out.text == "not json at all" and out.structured["present"] is False
    assert len(rig.argvs()) == 2 and len(router.native_blocked) == 1          # the native try, then ONE prompted retry, no repair round
    assert "--json-schema" not in rig.argvs()[1]
    assert len(rig.sink.rows) == 1 and rig.sink.rows[0].how == "prompted"


def test_complete_starts_prompted_for_a_blocked_schema(rig):
    rig.fake.sequence("ok_plain").reply(text="{}")
    router = rig.router("claude")
    block(router, "claude", SCHEMA_DICT)
    complete(router)
    assert len(rig.argvs()) == 1 and "--json-schema" not in rig.argvs()[0]
    assert "Answer with ONE JSON object only" in rig.fake.model_calls("claude")[0]["stdin"]


def test_complete_prunes_the_nulls_the_codex_strict_schema_forced_in(rig):
    rig.fake.sequence("ok_structured").reply(json={"answer": "c", "extra": None})
    out = complete(rig.router("codex"))
    assert json.loads(out.text) == {"answer": "c"}
    assert out.usd is None and out.input_tokens and out.provider == "codex"


def test_complete_leaves_an_unreadable_codex_reply_alone(rig):
    rig.fake.sequence("ok_structured").reply(text="plain words, no JSON")
    out = complete(rig.router("codex"))
    assert out.text == "plain words, no JSON"


def test_complete_json_mode_without_a_schema_is_a_plain_call_with_the_requests_effort(rig):
    rig.fake.sequence("ok_plain").reply(text="  {}  ")
    router = rig.router("claude")
    out = router.complete(CompletionRequest(system="s", user="u", json_mode=True, effort="low"))
    router.complete(CompletionRequest(system="s", user="u", json_mode=True))
    first, second = rig.argvs()
    assert out.text == "{}" and out.structured is None and "--json-schema" not in first
    assert first[first.index("--effort") + 1] == "low" and second[second.index("--effort") + 1] == "high"     # the engine's own choice stands
