"""CN-1: the shared connector models (connectors design 3.1)."""
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from sutra_app.connectors import models as m
from sutra_app.engine import port


def usage(i=0, c=0, w=0, o=0, r=0):
    return m.Usage(input_tokens=i, cached_input_tokens=c, cache_write_tokens=w, output_tokens=o, reasoning_tokens=r)


# ---- Usage -----------------------------------------------------------------------------------------------------------

def test_usage_input_total_and_total():
    u = usage(2, 1079, 2276, 53, 10)
    assert u.input_total == 3357            # the captured Claude fixture: 2 + 1079 + 2276
    assert u.total == 3410


def test_usage_subtraction_clamps_each_part_at_zero():
    assert usage(10, 5, 3, 7, 2) - usage(4, 9, 3, 1, 5) == usage(6, 0, 0, 6, 0)


def test_usage_addition_sums_each_part_and_does_not_mutate():
    a, b = usage(1, 2, 3, 4, 1), usage(10, 20, 30, 40, 2)
    assert a + b == usage(11, 22, 33, 44, 3)
    assert a == usage(1, 2, 3, 4, 1)


def test_usage_arithmetic_with_a_non_usage_is_a_type_error():
    with pytest.raises(TypeError):
        usage(1) + 1
    with pytest.raises(TypeError):
        usage(1) - 1


def test_usage_refuses_negative_parts():
    with pytest.raises(ValidationError):
        usage(i=-1)


# ---- closed models ---------------------------------------------------------------------------------------------------

MINIMAL = {
    m.Usage: {}, m.Quota: {}, m.Message: {"role": "user", "text": "hi"}, m.RouteContext: {}, m.AskRequest: {"user": "q"},
    m.JsonRequest: {"user": "q"}, m.AuthStatus: {"provider": "claude", "installed": True, "checked_at": 1.0},
    m.ModelInfo: {"slug": "s", "label": "S", "efforts": ["low"], "context_window": None, "images": False, "listed": True},
    m.Capabilities: {"native_schema": True, "resume": True, "images": False, "partials": True, "mcp": False},
    m.SessionSpec: {"session_id": "cs_1"}, m.ConnectorEvent: {"kind": "text"}, m.ConnectorConfig: {"data_dir": "/tmp/d"},
}


@pytest.mark.parametrize("cls", sorted(MINIMAL, key=lambda c: c.__name__))
def test_every_model_forbids_extra_keys(cls):
    cls(**MINIMAL[cls])
    with pytest.raises(ValidationError, match="Extra inputs"):
        cls(**MINIMAL[cls], surprise=1)


def turn(**kw):
    base = dict(text="ok", provider="claude", model="sonnet", provider_session_id=None, usage=usage(1, o=2), usd=0.5,
                usd_basis="reported", duration_ms=10)
    return m.TurnResult(**{**base, **kw})


def test_turn_result_and_session_state_forbid_extra_keys_too():
    with pytest.raises(ValidationError, match="Extra inputs"):
        turn(surprise=1)
    with pytest.raises(ValidationError, match="Extra inputs"):
        m.SessionState(session_id="a", provider="claude", provider_session_id=None, model="s", effort="low", workdir="/w",
                       created_at=1.0, surprise=1)


def test_turn_result_requires_the_fields_the_design_lists_without_defaults():
    with pytest.raises(ValidationError):
        m.TurnResult(text="x", provider="claude")
    t = turn()
    assert (t.structured, t.quota, t.subtype) == (None, None, None)


def test_provider_and_effort_are_closed_vocabularies():
    with pytest.raises(ValidationError):
        turn(provider="gemini")
    with pytest.raises(ValidationError):
        m.SessionSpec(session_id="a", effort="extreme")
    for ok in ("low", "medium", "high", "xhigh", "max"):
        assert m.SessionSpec(session_id="a", effort=ok).effort == ok


# ---- Allowance is the engine's class ---------------------------------------------------------------------------------

def test_allowance_is_the_engine_class_object():
    assert m.Allowance is port.Allowance
    assert m.CallTag is port.CallTag


def test_allowance_bounds_are_the_engines():
    with pytest.raises(ValidationError):
        m.Allowance(max_calls=-1)
    with pytest.raises(ValidationError):
        m.Allowance(max_usd=-0.01)
    with pytest.raises(ValidationError):
        m.Allowance(max_usd=float("nan"))
    assert m.Allowance(max_calls=0).max_calls == 0


def test_route_context_defaults_are_independent_per_instance():
    a, b = m.RouteContext(), m.RouteContext()
    assert a.allowance == m.Allowance() and a.tag == port.CallTag() and a.avoid == []
    assert a.allowance is not b.allowance and a.avoid is not b.avoid


def test_route_context_takes_a_tag_an_allowance_and_avoid():
    ctx = m.RouteContext(tag=port.CallTag(function="audit", purpose="review"), allowance=m.Allowance(max_calls=3, envelope_id="a-1"),
                         avoid=["claude"], session_id="cs_x", node_id="sales.audit")
    assert ctx.tag.function == "audit" and ctx.allowance.max_calls == 3 and ctx.avoid == ["claude"]
    with pytest.raises(ValidationError):
        m.RouteContext(avoid=["gemini"])


# ---- requests --------------------------------------------------------------------------------------------------------

def test_ask_request_defaults_and_the_schema_field_name():
    r = m.AskRequest(user="hello", schema={"type": "object"}, tools=["sutra_read"])
    assert (r.system, r.kind, r.effort, r.images, r.timeout_s, r.partials) == ("", "text", None, [], None, False)
    assert r.schema == {"type": "object"} and r.tools == ("sutra_read",)
    assert "schema" in m.AskRequest.model_fields and "schema" in m.JsonRequest.model_fields


def test_ask_request_timeout_must_be_positive_and_finite():
    for bad in (0, -1, float("inf")):
        with pytest.raises(ValidationError):
            m.AskRequest(user="x", timeout_s=bad)


def test_ask_request_scripted_callable_is_kept_but_never_dumped():
    r = m.AskRequest(user="x", scripted=lambda: "mock reply")
    assert r.scripted() == "mock reply"
    assert "scripted" not in r.model_dump()


def test_json_request_is_json_kind_and_accepts_a_class_or_a_dict():
    class Reply(BaseModel):
        a: int

    assert m.JsonRequest(user="x").kind == "json"
    assert m.JsonRequest(user="x", schema=Reply).schema is Reply
    assert m.JsonRequest(user="x", schema={"type": "object"}).schema == {"type": "object"}
    with pytest.raises(ValidationError):
        m.JsonRequest(user="x", kind="text")


# ---- results ---------------------------------------------------------------------------------------------------------

def test_json_result_as_tuple_is_object_usd_how():
    r = m.JsonResult(value={"a": 1}, usd=None, how="native", turn=turn(), calls_made=1, usd_spent=0.0)
    assert r.as_tuple() == ({"a": 1}, None, "native")
    with pytest.raises(ValidationError):
        m.JsonResult(value=1, usd=0.0, how="chat", turn=turn(), calls_made=1, usd_spent=0.0)
    with pytest.raises(ValidationError):
        m.JsonResult(value=1, usd=0.0, how="native", turn=turn(), calls_made=-1, usd_spent=0.0)


def test_auth_status_account_is_not_in_the_repr():
    s = m.AuthStatus(provider="claude", installed=True, signed_in=True, account="me@example.com", checked_at=1.0)
    assert "me@example.com" not in repr(s)
    assert s.account == "me@example.com"
    assert (s.billing, s.signed_in, m.AuthStatus(provider="codex", installed=False, checked_at=1.0).signed_in) == ("unknown", True, None)


# ---- sessions --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("good", ["cs_5e0a77b19c3d", "A-b_9", "x" * 64])
def test_session_id_accepts_directory_safe_names(good):
    assert m.SessionSpec(session_id=good).session_id == good


@pytest.mark.parametrize("bad", ["", "x" * 65, "../etc", "a/b", "a b", "a.b", "é", "a\n"])
def test_session_id_pattern_refuses_anything_that_could_leave_the_work_root(bad):
    with pytest.raises(ValidationError, match="session_id"):
        m.SessionSpec(session_id=bad)


def test_session_state_checks_the_id_too_and_has_the_design_defaults():
    kw = dict(provider="claude", provider_session_id=None, model="sonnet", effort="low", workdir="/w", created_at=1.0)
    s = m.SessionState(session_id="cs_1", **kw)
    assert (s.tool_profile, s.turns, s.switches, s.pinned, s.cum_usd, s.cum_usage) == ("none", 0, 0, None, 0.0, usage())
    with pytest.raises(ValidationError, match="session_id"):
        m.SessionState(session_id="../x", **kw)
    with pytest.raises(ValidationError):
        m.SessionState(session_id="cs_1", **{**kw, "turns": -1})


def test_session_state_round_trips_the_design_example():
    example = {"session_id": "cs_5e0a77b19c3d", "provider": "claude", "provider_session_id": "092c7b68-7118-42da-ba0a-57fa2e5ef699",
               "model": "sonnet", "effort": "low", "tool_profile": "none", "workdir": "/private/var/folders/x/sutra-app-501/work/cs_5e0a77b19c3d",
               "turns": 2, "switches": 0, "pinned": None, "cum_usd": 0.0190348,
               "cum_usage": {"input_tokens": 6, "cached_input_tokens": 1728, "cache_write_tokens": 4570, "output_tokens": 57, "reasoning_tokens": 0},
               "created_at": 1793748000.0}
    assert m.SessionState.model_validate(example).model_dump() == example


def test_connector_event_kinds_are_the_eight_of_the_design():
    for kind in ("started", "text_delta", "text", "tool_call", "tool_result", "quota", "notice", "turn_done"):
        assert m.ConnectorEvent(kind=kind).data == {}
    with pytest.raises(ValidationError):
        m.ConnectorEvent(kind="other")


# ---- ConnectorConfig -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "GITHUB_TOKEN", "MY_SECRET", "db_password", "ApiKey"])
def test_extra_env_refuses_secret_looking_names(name):
    with pytest.raises(ValidationError, match="credentials"):
        m.ConnectorConfig(data_dir="/d", extra_env={name: "x"})


def test_extra_env_accepts_gateway_and_fake_names():
    cfg = m.ConnectorConfig(data_dir="/d", extra_env={"ANTHROPIC_BASE_URL": "http://gw", "FAKE_PYTHON": "/usr/bin/python3"})
    assert cfg.extra_env["ANTHROPIC_BASE_URL"] == "http://gw"


def test_config_defaults():
    cfg = m.ConnectorConfig(data_dir="/d")
    assert (cfg.claude_exe, cfg.codex_exe, cfg.gh_exe, cfg.python, cfg.work_root, cfg.extra_env) == ("claude", "codex", "gh", sys.executable, None, {})
    assert isinstance(cfg.data_dir, Path)


def test_work_root_default_is_under_the_temp_root_by_uid_and_is_a_realpath(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setattr(tempfile, "tempdir", str(link))
    got = m.ConnectorConfig(data_dir="/d").resolved_work_root()
    assert got.parent == real / f"sutra-app-{os.getuid()}" and re.fullmatch(r"work-[0-9a-f]{12}", got.name)
    explicit = m.ConnectorConfig(data_dir="/d", work_root=link / "w").resolved_work_root()
    assert explicit == real / "w"


def test_two_data_folders_never_share_a_default_work_root(tmp_path, monkeypatch):
    """QA firstrun-settings: the default root was `<tempdir>/sutra-app-<uid>/work` for EVERY data folder of one user, so a second
    app (or a brand-new data folder) read the first one's session.json: its pinned model, its provider conversation id."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    a = m.ConnectorConfig(data_dir=tmp_path / "data-a").resolved_work_root()
    b = m.ConnectorConfig(data_dir=tmp_path / "data-b").resolved_work_root()
    assert a != b and a.parent == b.parent
    assert m.ConnectorConfig(data_dir=tmp_path / "data-a").resolved_work_root() == a            # the same folder always gets the same root
    assert m.ConnectorConfig(data_dir=tmp_path / "x" / ".." / "data-a").resolved_work_root() == a      # however the path is spelled


def test_a_data_folder_reached_through_a_link_keeps_its_work_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    real = tmp_path / "real-data"
    real.mkdir()
    link = tmp_path / "link-data"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system cannot make a link here")
    assert m.ConnectorConfig(data_dir=link).resolved_work_root() == m.ConnectorConfig(data_dir=real).resolved_work_root()


def test_an_explicit_work_root_is_used_as_given_for_every_data_folder(tmp_path):
    one = m.ConnectorConfig(data_dir=tmp_path / "a", work_root=tmp_path / "w").resolved_work_root()
    two = m.ConnectorConfig(data_dir=tmp_path / "b", work_root=tmp_path / "w").resolved_work_root()
    assert one == two == Path(os.path.realpath(tmp_path / "w"))
