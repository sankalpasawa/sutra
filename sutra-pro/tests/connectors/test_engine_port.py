"""make_port and RouterPort: the engine's model seam (connectors design 3.10, S1-contracts-02, work package CN-7).

Three groups: the signature and the imports the contract fixes; one assertion set run against J2's `ScriptedPort` and the stub-only
port of `make_port` (they are twins); and the real connectors against the fake CLIs (mapping, describe, preflight, close)."""
from __future__ import annotations

import inspect
import threading
import time
from pathlib import Path

import pytest

import sutra_app.connectors as connectors_package
from sutra_app.connectors import engine_port
from sutra_app.connectors.engine_port import RouterPort, build_connectors, make_port, port_from_config
from sutra_app.connectors.errors import CallCancelledError, InvalidRequestError
from sutra_app.connectors.health import API_KEY_REFUSED
from sutra_app.connectors.models import ConnectorConfig
from sutra_app.connectors.policy import load_default_policy, parse_policy
from sutra_app.connectors.router import Router
from sutra_app.connectors.stub import StubConnector
from sutra_app.connectors.usage import MemoryUsageSink, UsageSink
from sutra_app.engine import port as engine_port_module
from sutra_app.engine.llm import ScriptedPort
from sutra_app.engine.port import (
    Allowance, CallTag, CompletionRequest, CompletionResult, ModelError, ModelPort, NoModelAvailable, PortInfo, PortSpec,
    PreflightResult, QuotaExhausted,
)

TAG = CallTag(run_id="j2-20261104-000000-ab12", dept_id="web", task_id="tsk_aaaaaaaaaaaa", function="audit", role="judge", stage="website",
              step=7, call_no=12, atom="a-1234567890-01", purpose="review")


def spec(tmp_path, **kw):
    fields = dict(mock=True, run_id="j2-20261104-000000-ab12", dept_id="web", task_id="tsk_aaaaaaaaaaaa", data_dir=str(tmp_path / "data"))
    fields.update(kw)
    return PortSpec(**fields)


# ---- the contract ---------------------------------------------------------------------------------------------------------------

def test_the_signature_of_make_port_is_fixed():
    sig = inspect.signature(make_port)
    assert list(sig.parameters) == ["spec", "usage_sink"]
    spec_param, sink_param = sig.parameters.values()
    assert spec_param.annotation is PortSpec and spec_param.default is inspect.Parameter.empty
    assert sink_param.kind is inspect.Parameter.KEYWORD_ONLY and sink_param.default is None
    assert sink_param.annotation == (UsageSink | None) and sig.return_annotation is ModelPort


def test_portspec_and_allowance_come_from_the_engine_module():
    assert engine_port.PortSpec is engine_port_module.PortSpec
    from sutra_app.connectors.models import Allowance as ConnectorAllowance
    assert ConnectorAllowance is engine_port_module.Allowance


def test_make_port_exists_only_in_engine_port_and_is_reachable_from_the_package():
    assert connectors_package.make_port is make_port
    defining = [p.name for p in Path(connectors_package.__file__).parent.glob("*.py") if "def make_port" in p.read_text(encoding="utf-8")]
    assert defining == ["engine_port.py"]


def test_runspec_never_appears_in_the_connector_package():
    names = [p.name for p in Path(connectors_package.__file__).parent.rglob("*.py") if "RunSpec" in p.read_text(encoding="utf-8")]
    assert names == []


def test_make_port_builds_a_stub_only_router_for_mock_or_the_stub_connector(tmp_path):
    for kw in (dict(mock=True), dict(mock=False, connector="stub")):
        port = make_port(spec(tmp_path, **kw))
        assert isinstance(port, RouterPort) and isinstance(port, ModelPort)
        assert list(port.router.connectors) == ["stub"] and port.router.mode == "offline"
        assert port.describe() == PortInfo(provider="stub", model="scripted", mock=True)
        assert port.preflight().ok


def test_make_port_reads_the_policy_file_under_data_dir(tmp_path):
    data = tmp_path / "data"
    (data / "connectors").mkdir(parents=True)
    good = load_default_policy().model_dump(mode="json")
    good["providers"]["codex"]["enabled"] = False
    (data / "connectors" / "policy.json").write_text(__import__("json").dumps(good))
    port = make_port(spec(tmp_path, mock=False, connector="claude"))
    assert port.router.policy_source == "file" and port.router.policy_error is None and list(port.router.connectors) == ["claude"]
    (data / "connectors" / "policy.json").write_text("{not json")
    broken = make_port(spec(tmp_path, mock=False, connector="auto"))
    assert broken.router.policy_source == "default" and "not valid JSON" in broken.router.policy_error
    assert list(broken.router.connectors) == ["claude", "codex"]


def test_build_connectors_follows_the_policy():
    cfg = ConnectorConfig(data_dir="/tmp/x")
    pol = load_default_policy()
    assert list(build_connectors(cfg, pol)) == ["claude", "codex"]
    assert list(build_connectors(cfg, pol, only="codex")) == ["codex"]
    only_claude = parse_policy({**pol.model_dump(mode="json"), "providers": {"claude": {"model": "sonnet"}},
                                "defaults": {**pol.model_dump(mode="json")["defaults"], "order": ["claude"]}, "rules": [], "rates": {}})
    assert list(build_connectors(cfg, only_claude)) == ["claude"]
    codex = build_connectors(cfg, pol)["codex"]
    assert codex.sandbox == "read-only" and set(codex.rates) == {"gpt-5.6-luna"}


# ---- the twins: one assertion set against ScriptedPort and the stub-only port -----------------------------------------------------

@pytest.fixture(params=["scripted_port", "stub_router_port"])
def twin(request, tmp_path):
    sink = MemoryUsageSink()
    port = ScriptedPort(sink) if request.param == "scripted_port" else make_port(spec(tmp_path), usage_sink=sink)
    yield port, sink
    port.close()


def request_with(**kw):
    return CompletionRequest(system="You are a judge.", user="Judge the page.", tag=TAG, **kw)


def test_twin_scripted_reply_is_returned_as_it_is(twin):
    port, _ = twin
    out = port.complete(request_with(scripted=lambda: "  canned reply \n"))
    assert out.text == "  canned reply \n" and (out.provider, out.model, out.usd) == ("stub", "scripted", 0.0)
    assert (out.input_tokens, out.output_tokens) == (len("You are a judge.Judge the page.") // 4, len("  canned reply \n") // 4)
    assert isinstance(out, CompletionResult) and out.duration_ms is not None


def test_twin_the_tag_reaches_the_usage_row(twin):
    port, sink = twin
    port.complete(request_with(scripted=lambda: "x" * 40))
    row = sink.rows[0]
    row = row if isinstance(row, dict) else row.model_dump()
    expected = {"provider": "stub", "model": "scripted", "purpose": "review", "task_id": "tsk_aaaaaaaaaaaa", "dept_id": "web", "fn": "audit",
                "step": "J2.g", "atom_id": "a-1234567890-01", "tokens_out": 10, "usd": 0.0, "ok": True, "how": "stub",
                "call_ref": "j2-20261104-000000-ab12:12"}
    assert {k: row[k] for k in expected} == expected


def test_twin_each_request_hands_one_row_to_the_sink_failures_included(twin):
    port, sink = twin
    port.complete(request_with(scripted=lambda: "ok"))
    with pytest.raises(TypeError):
        port.complete(request_with(scripted=lambda: 5))
    rows = [r if isinstance(r, dict) else r.model_dump() for r in sink.rows]
    assert [r["ok"] for r in rows] == [True, False] and len(rows) == 2


def test_twin_a_call_without_a_call_number_gets_a_request_ref(twin):
    port, sink = twin
    port.complete(CompletionRequest(system="s", user="u", scripted=lambda: "x"))
    row = sink.rows[0]
    row = row if isinstance(row, dict) else row.model_dump()
    assert row["call_ref"].startswith("r:") and row["atom_id"] is None


def test_twin_the_builtin_reply_without_a_script(twin):
    port, _ = twin
    out = port.complete(CompletionRequest(system="s", user="u" * 100))
    assert out.text == "[stub] " + "u" * 60


def test_twin_progress_events_are_chars_and_text(twin):
    port, _ = twin
    seen = []
    port.complete(request_with(scripted=lambda: "abcdef"), seen.append)
    assert seen and seen[-1] == {"chars": 6, "text": "abcdef"}


def test_twin_a_closed_port_raises_a_model_error(twin):
    port, sink = twin
    port.close()
    with pytest.raises(ModelError):
        port.complete(request_with(scripted=lambda: "x"))


def test_twin_the_engine_sends_no_allowance(twin):
    port, _ = twin
    req = request_with(scripted=lambda: "x")
    assert req.allowance is None
    assert port.complete(req).text == "x"


# ---- the stub-only port, in detail ------------------------------------------------------------------------------------------------

def test_errors_the_engine_sees_are_its_own_classes(tmp_path):
    sink = MemoryUsageSink()
    port = make_port(spec(tmp_path), usage_sink=sink)
    port.router.connectors["stub"].fail_next("quota")
    with pytest.raises(QuotaExhausted) as e:
        port.complete(request_with())
    assert isinstance(e.value, ModelError) and isinstance(e.value, RuntimeError)
    assert sink.rows[0].ok is False
    port.router._restrict = "codex"
    with pytest.raises(NoModelAvailable):
        port.complete(request_with())


def test_allowance_none_becomes_the_empty_allowance_and_a_given_one_is_kept(tmp_path):
    seen = []

    class Spy(StubConnector):
        def call_text(self, prompt, **kw):
            seen.append(kw["ctx"])
            return super().call_text(prompt, **kw)
    cfg = ConnectorConfig(data_dir=tmp_path / "data", work_root=tmp_path / "work")
    port = RouterPort(Router({"stub": Spy(cfg)}, load_default_policy(), connector="stub"), mock=True)
    port.complete(request_with())
    port.complete(request_with(allowance=Allowance(max_calls=3, envelope_id="atom-1")))
    assert seen[0].allowance == Allowance() and seen[0].tag == TAG
    assert seen[1].allowance == Allowance(max_calls=3, envelope_id="atom-1")
    assert seen[0].session_id is None


def test_a_missing_image_is_an_invalid_request_before_any_call(tmp_path):
    sink = MemoryUsageSink()
    port = make_port(spec(tmp_path), usage_sink=sink)
    with pytest.raises(InvalidRequestError, match="image not found"):
        port.complete(request_with(images=[str(tmp_path / "gone.png")]))
    assert port.router.connectors["stub"].calls == [] and len(sink.rows) == 1


def test_an_image_that_exists_reaches_the_stub(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG")
    port = make_port(spec(tmp_path))
    assert port.complete(request_with(images=[str(img)])).text.startswith("[stub]")


def test_a_json_schema_request_gets_the_stub_example_and_structured_info(tmp_path):
    port = make_port(spec(tmp_path))
    out = port.complete(request_with(json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}))
    assert __import__("json").loads(out.text) == {"ok": False}
    assert out.structured == {"provider": "stub", "subtype": None, "present": False}


def test_a_book_reply_by_function_and_stage_answers_the_engines_call(tmp_path):
    port = make_port(spec(tmp_path))
    port.router.connectors["stub"].book.set("audit", "website", '{"verdict": "pass"}')
    assert port.complete(request_with()).text == '{"verdict": "pass"}'


def test_make_port_without_a_sink_works(tmp_path):
    assert make_port(spec(tmp_path)).complete(request_with(scripted=lambda: "x")).text == "x"


# ---- the real connectors against the fake CLIs ---------------------------------------------------------------------------------------

def real_port(fake, tmp_path, connector="auto", sink=None, **spec_kw):
    return port_from_config(spec(tmp_path, mock=False, connector=connector, **spec_kw), ConnectorConfig(**fake.config_kwargs(tmp_path)),
                            usage_sink=sink, sleep=lambda s: None)


def test_complete_maps_the_result_field_by_field(fake, tmp_path):
    fake.sequence("ok_plain").reply(text="  pong \n").cost(0.01).usage(input_tokens=10, cache_read_input_tokens=5,
                                                                        cache_creation_input_tokens=3, output_tokens=7)
    sink = MemoryUsageSink()
    out = real_port(fake, tmp_path, "claude", sink).complete(request_with())
    assert out.text == "pong" and out.provider == "claude" and out.model
    assert (out.input_tokens, out.output_tokens) == (18, 7) and out.usd == pytest.approx(0.01)
    assert isinstance(out.duration_ms, int) and isinstance(out.session_id, str) and out.structured is None and out.note is None
    row, = sink.rows
    assert out.detail == row.detail and out.detail["attempts"][0]["code"] == "ok" and row.tokens_in == 18 and row.atom_id == "a-1234567890-01"


def test_effort_and_the_tag_reach_the_cli(fake, tmp_path):
    fake.sequence("ok_plain")
    port = real_port(fake, tmp_path, "claude")
    port.complete(request_with(effort="low"))
    port.complete(request_with(effort="high"))
    first, second = [c["argv"] for c in fake.model_calls("claude")]
    assert first[first.index("--effort") + 1] == "low" and second[second.index("--effort") + 1] == "high"
    assert first[first.index("--model") + 1] == "sonnet"


def test_a_fallback_note_is_in_the_result_and_in_progress(fake, tmp_path):
    fake.sequence("quota", cli="claude")
    fake.sequence("ok_plain", cli="codex").reply(text="from codex")
    seen = []
    out = real_port(fake, tmp_path).complete(request_with(), seen.append)
    assert out.text == "from codex" and out.provider == "codex" and out.note == "claude out of quota, answered by codex"
    assert {"note": out.note} in seen and out.usd is None


def test_describe_and_preflight_with_both_clis_ready(fake, tmp_path):
    port = real_port(fake, tmp_path)
    assert port.describe() == PortInfo(provider="claude", model="sonnet", mock=False)
    result = port.preflight()
    assert isinstance(result, PreflightResult) and result.ok and result.message == "claude is ready (sonnet)"
    assert [(p["name"], p["installed"], p["signed_in"]) for p in result.providers] == [("claude", True, True), ("codex", True, True)]
    assert fake.model_calls() == []                                         # no model call


def test_preflight_uses_the_other_provider_when_one_is_signed_out(fake, tmp_path):
    fake.auth(claude="signed_out")
    port = real_port(fake, tmp_path)
    assert port.describe().provider == "codex"
    result = port.preflight()
    assert result.ok and result.message.startswith("codex is ready")
    assert {p["name"]: p["signed_in"] for p in result.providers} == {"claude": False, "codex": True}


def test_preflight_says_why_nothing_is_usable(fake, tmp_path):
    fake.auth(claude="signed_out", codex="signed_out")
    port = real_port(fake, tmp_path)
    result = port.preflight()
    assert result.ok is False and result.message == ("No model is available: Claude: not signed in: run `claude auth login`; "
                                                      "Codex: not signed in: use Sign in or run `codex login`")
    assert port.describe() == PortInfo(provider=None, model=None, mock=False)


def test_preflight_names_a_missing_cli_with_the_install_hint(fake, tmp_path):
    kw = fake.config_kwargs(tmp_path)
    kw["claude_exe"] = str(tmp_path / "no-such-claude")
    port = port_from_config(spec(tmp_path, mock=False, connector="claude"), ConnectorConfig(**kw))
    result = port.preflight()
    assert result.ok is False and "Claude: CLI not found on PATH (install it and run `claude` once)" in result.message
    assert result.providers == [{"name": "claude", "installed": False, "signed_in": None, "detail": "CLI not found on PATH"}]


def test_preflight_refuses_an_api_key_login(fake, tmp_path):
    fake.auth(codex="api_key")
    port = real_port(fake, tmp_path, "codex")
    result = port.preflight()
    assert result.ok is False and API_KEY_REFUSED in result.message


def test_a_live_engine_port_writes_an_observe_row_and_the_prompt_stays_byte_identical(fake, tmp_path):
    """QA dept-run P1: the engine's port never had `router.egress`, so a key in a brief left no audit row at all (D109: J2's agents are
    observed, never edited)."""
    from sutra_app.connectors.egress import Egress
    fake.sequence("ok_plain")
    key = "sk-" + "A1b2C3d4" * 4
    token = "ghp_" + "Z9y8X7w6V5" * 3
    real_port(fake, tmp_path, "claude").complete(CompletionRequest(
        system="You are a judge.", user=f"Our analytics key is {key} and our deploy token is {token}.", tag=TAG))
    sent = fake.model_calls("claude")[0]["stdin"]
    assert key in sent and token in sent and "[redacted" not in sent                    # observe only: J2's prompt is not edited
    rows = Egress(tmp_path / "data" / "connectors" / "egress.jsonl").rows()
    assert len(rows) == 1 and rows[0]["mode"] == "observe" and rows[0]["provider"] == "claude"
    assert rows[0]["shapes"] == {"openai-key": 1, "github-token": 1}
    assert key not in (tmp_path / "data" / "connectors" / "egress.jsonl").read_text()    # a row never holds a match


def test_a_stub_only_engine_port_writes_no_egress_file(tmp_path):
    make_port(spec(tmp_path)).complete(request_with(scripted=lambda: "x"))
    assert not (tmp_path / "data" / "connectors" / "egress.jsonl").exists()


def test_connector_claude_builds_only_claude(fake, tmp_path):
    port = real_port(fake, tmp_path, "claude")
    assert list(port.router.connectors) == ["claude"]
    fake.auth(claude="signed_out")
    port2 = real_port(fake, tmp_path / "again", "claude")
    assert port2.preflight().ok is False                                    # codex is not a fallback when claude was asked for


def test_close_stops_a_running_child(fake, tmp_path):
    fake.sequence("hang")
    port = real_port(fake, tmp_path, "claude")
    box = {}

    def run():
        try:
            port.complete(request_with())
        except Exception as e:
            box["error"] = e
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    fake.wait_for(1, "claude")
    started = time.time()
    port.close()
    worker.join(20)
    assert isinstance(box["error"], CallCancelledError) and time.time() - started < 15 and not worker.is_alive()
    with pytest.raises(CallCancelledError):
        port.complete(request_with())
