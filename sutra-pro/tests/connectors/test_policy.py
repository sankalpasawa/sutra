"""The routing policy (CN-6, connectors 3.6): default, rules, validation, user file, S1-contracts-17."""
from __future__ import annotations

import copy
import json
import os
import stat

import pytest

from sutra_app.connectors.errors import PolicyInvalidError
from sutra_app.connectors.models import AskRequest, RouteContext
from sutra_app.connectors.policy import (
    DEFAULT_POLICY_PATH, RoutingPolicy, load_default_policy, load_policy, parse_policy, user_policy_path, write_policy,
)
from sutra_app.engine.port import CallTag


@pytest.fixture
def raw():
    return json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def _policy(raw, **changes):
    data = copy.deepcopy(raw)
    data.update(changes)
    return parse_policy(data)


def _req(**tag):
    kind = tag.pop("kind", "text")
    images = tag.pop("images", [])
    tools = tag.pop("tools", ())
    effort = tag.pop("effort", None)
    timeout = tag.pop("timeout_s", None)
    return AskRequest(user="hi", kind=kind, images=images, tools=tools, effort=effort, timeout_s=timeout,
                      ctx=RouteContext(tag=CallTag(**tag)))


# ---- the shipped default -----------------------------------------------------------------------------------------------
def test_default_loads_and_reproduces_j2():
    policy = load_default_policy()
    assert policy.version == 1
    assert policy.defaults.order == ["claude", "codex"]                    # Claude first, Codex only as the fallback
    assert (policy.model_for("claude"), policy.model_for("codex")) == ("sonnet", "gpt-5.6-luna")
    assert (policy.max_concurrency("claude"), policy.max_concurrency("codex")) == (4, 2)
    assert policy.providers["codex"].sandbox == "read-only"
    d = policy.defaults
    assert (d.timeout_s, d.max_attempts, d.retry_delays_s, d.repair_rounds, d.max_calls_per_request) == (900, 2, [2, 5], 2, 6)
    assert (d.fallback_on_invalid_json, d.tool_profile, d.idle_timeout_s) == (False, "none", 120)


def test_default_file_has_no_allow_api_key_billing(raw):
    assert "allow_api_key_billing" not in DEFAULT_POLICY_PATH.read_text(encoding="utf-8")
    assert "allow_api_key_billing" not in json.dumps(load_default_policy().model_dump())


def test_default_rates_are_null_so_codex_cost_is_unknown():
    rate = load_default_policy().rate("codex", "gpt-5.6-luna")
    assert rate is not None
    assert (rate.in_per_mtok, rate.cached_in_per_mtok, rate.out_per_mtok) == (None, None, None)
    assert load_default_policy().rate("claude", "sonnet") is None


def test_j2_effort_defaults_low_for_json_high_for_text():
    policy = load_default_policy()
    assert policy.resolve(_req(function="identity", kind="json")).effort == "low"
    assert policy.resolve(_req(function="identity", kind="text")).effort == "high"


# ---- resolve: rules ----------------------------------------------------------------------------------------------------
def test_defaults_only_when_no_rule_matches():
    got = load_default_policy().resolve(_req(function="identity"))
    assert got.rule_index is None
    assert got.order == ("claude", "codex")
    assert (got.timeout_s, got.max_attempts, got.repair_rounds, got.max_calls_per_request) == (900, 2, 2, 6)
    assert [got.retry_delay(0), got.retry_delay(1), got.retry_delay(5)] == [2, 5, 5]     # the last delay repeats


def test_default_rules_chat_agent_timeout_and_summary_effort():
    policy = load_default_policy()
    chat = policy.resolve(_req(function="chat_agent", purpose="chat_plan", kind="json"))
    assert (chat.rule_index, chat.timeout_s) == (0, 120)
    summary = policy.resolve(_req(function="audit", purpose="summary"))
    assert (summary.rule_index, summary.effort, summary.timeout_s) == (1, "low", 300)


def test_first_matching_rule_wins(raw):
    raw["rules"] = [{"match": {"function": "audit"}, "timeout_s": 11}, {"match": {"function": "audit"}, "timeout_s": 22},
                    {"match": {}, "timeout_s": 33}]
    policy = parse_policy(raw)
    assert policy.resolve(_req(function="audit")).timeout_s == 11
    assert policy.resolve(_req(function="identity")).timeout_s == 33            # an empty match is a catch-all


def test_fnmatch_on_function_stage_and_role(raw):
    raw["rules"] = [{"match": {"function": "W-*", "stage": "p?d", "role": "[pj]*"}, "repair_rounds": 0}]
    policy = parse_policy(raw)
    assert policy.resolve(_req(function="W-12", stage="prd", role="planner")).repair_rounds == 0
    assert policy.resolve(_req(function="W-12", stage="prd", role="judge")).repair_rounds == 0
    assert policy.resolve(_req(function="W-12", stage="prd", role="builder")).repair_rounds == 2      # role mismatch
    assert policy.resolve(_req(function="W-12", stage="prds", role="planner")).repair_rounds == 2     # "?" is one character
    assert policy.resolve(_req(function="audit", stage="prd", role="planner")).repair_rounds == 2
    assert policy.resolve(_req(function="W-12", role="planner")).repair_rounds == 2                   # no stage never matches "p?d"


def test_fnmatch_is_case_sensitive(raw):
    raw["rules"] = [{"match": {"function": "Audit"}, "timeout_s": 5}]
    assert parse_policy(raw).resolve(_req(function="audit")).rule_index is None


def test_purpose_kind_has_images_and_tools_match_exactly(raw):
    raw["rules"] = [
        {"match": {"purpose": "summ"}, "timeout_s": 1},
        {"match": {"kind": "json", "has_images": True}, "timeout_s": 2},
        {"match": {"tools": ["sutra", "github"]}, "timeout_s": 3},
    ]
    policy = parse_policy(raw)
    assert policy.resolve(_req(purpose="summary")).rule_index is None            # purpose is exact, not a prefix or a glob
    assert policy.resolve(_req(purpose="summ")).timeout_s == 1
    assert policy.resolve(_req(kind="json", images=["a.png"])).timeout_s == 2
    assert policy.resolve(_req(kind="text", images=["a.png"])).rule_index is None
    assert policy.resolve(_req(kind="json")).rule_index is None
    assert policy.resolve(_req(tools=("github", "sutra"))).timeout_s == 3        # same names, any order
    assert policy.resolve(_req(tools=("sutra",))).rule_index is None


def test_rule_overrides_every_field_it_sets(raw):
    raw["rules"] = [{"match": {"function": "audit"}, "order": ["codex"], "effort": "max", "timeout_s": 5, "idle_timeout_s": 6,
                     "max_attempts": 3, "retry_delays_s": [0.5], "repair_rounds": 0, "max_calls_per_request": 2,
                     "fallback_on_invalid_json": True, "tool_profile": "sutra"}]
    got = parse_policy(raw).resolve(_req(function="audit"))
    assert (got.order, got.effort, got.timeout_s, got.idle_timeout_s) == (("codex",), "max", 5, 6)
    assert (got.max_attempts, got.retry_delays_s, got.repair_rounds, got.max_calls_per_request) == (3, (0.5,), 0, 2)
    assert (got.fallback_on_invalid_json, got.tool_profile) == (True, "sutra")


def test_rule_beats_request_which_beats_defaults_for_effort_and_timeout():
    policy = load_default_policy()
    # no rule: the request's own value, else the default
    assert policy.resolve(_req(function="x", kind="json", effort="max", timeout_s=7)).effort == "max"
    assert policy.resolve(_req(function="x", kind="json", effort="max", timeout_s=7)).timeout_s == 7
    # a matching rule sets them: the rule wins over what the caller sent
    got = policy.resolve(_req(function="audit", purpose="summary", effort="max", timeout_s=7))
    assert (got.effort, got.timeout_s) == ("low", 300)


def test_empty_retry_delays_mean_no_wait(raw):
    raw["defaults"]["retry_delays_s"] = []
    assert parse_policy(raw).resolve(_req()).retry_delay(0) == 0.0


# ---- validation ---------------------------------------------------------------------------------------------------------
def test_allow_api_key_billing_fails_validation_with_its_own_message(raw):
    for place in (raw, raw["defaults"], raw["providers"]["codex"]):
        data = copy.deepcopy(raw)
        target = data if place is raw else data["defaults"] if place is raw["defaults"] else data["providers"]["codex"]
        target["allow_api_key_billing"] = True
        with pytest.raises(PolicyInvalidError) as err:
            parse_policy(data)
        assert "allow_api_key_billing" in err.value.user_message()
        assert "S1-contracts-17" in err.value.detail["errors"][0]


def test_bad_provider_name_raises_policy_invalid(raw):
    raw["providers"]["gemini"] = {"model": "x"}
    with pytest.raises(PolicyInvalidError) as err:
        parse_policy(raw)
    assert err.value.code == "policy_invalid"
    assert any("providers.gemini" in line for line in err.value.detail["errors"])


def test_order_must_name_configured_providers(raw):
    del raw["providers"]["codex"]
    raw["rules"] = []
    with pytest.raises(PolicyInvalidError, match="not in providers"):
        parse_policy(raw)                                                       # defaults.order still lists codex
    raw["defaults"]["order"] = ["claude", "stub"]
    assert parse_policy(raw).defaults.order == ["claude", "stub"]               # the stub is always allowed
    raw["rules"] = [{"match": {}, "order": ["codex"]}]
    with pytest.raises(PolicyInvalidError, match=r"rules\[0\]\.order"):
        parse_policy(raw)


@pytest.mark.parametrize("change", [
    lambda r: r.update(version=2),
    lambda r: r.pop("defaults"),
    lambda r: r["defaults"].update(order=[]),
    lambda r: r["defaults"].update(order=["claude", "claude"]),
    lambda r: r["defaults"].update(timeout_s=0),
    lambda r: r["defaults"].update(max_attempts=0),
    lambda r: r["defaults"].update(retry_delays_s=[-1]),
    lambda r: r["defaults"].update(effort_json="ultra"),
    lambda r: r["defaults"].update(tool_profile="shell"),
    lambda r: r["defaults"].update(surprise=1),
    lambda r: r["providers"]["claude"].update(model=""),
    lambda r: r["providers"]["claude"].update(max_concurrency=0),
    lambda r: r["providers"]["claude"].update(sandbox="read-only"),
    lambda r: r["providers"]["codex"].update(sandbox="danger-full-access"),
    lambda r: r["rules"].append({"match": {}, "order": ["claude", "claude"]}),
    lambda r: r["rules"].append({"match": {"colour": "red"}}),
    lambda r: r["rules"].append({"match": {}, "effort": "ultra"}),
    lambda r: r["rates"]["codex"]["gpt-5.6-luna"].update(out_per_mtok=-1),
])
def test_invalid_policies_are_refused(raw, change):
    change(raw)
    with pytest.raises(PolicyInvalidError) as err:
        parse_policy(raw)
    assert err.value.detail["errors"]


def test_not_json_and_not_an_object():
    with pytest.raises(PolicyInvalidError, match="not valid JSON"):
        parse_policy("{nope")
    with pytest.raises(PolicyInvalidError, match="JSON object"):
        parse_policy("[1, 2]")


def test_policy_is_closed_at_the_top_level(raw):
    raw["note"] = "hi"
    with pytest.raises(PolicyInvalidError):
        parse_policy(raw)
    assert RoutingPolicy.model_config["extra"] == "forbid"


# ---- the user file -------------------------------------------------------------------------------------------------------
def test_no_data_dir_or_no_file_gives_the_default(tmp_path):
    assert load_policy().source == "default"
    got = load_policy(tmp_path)
    assert (got.source, got.error, got.errors) == ("default", None, [])


def test_valid_user_file_replaces_the_default(tmp_path, raw):
    raw["providers"]["claude"]["model"] = "opus"
    path = user_policy_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    got = load_policy(tmp_path)
    assert got.source == "file" and got.error is None
    assert got.policy.model_for("claude") == "opus"


def test_invalid_user_file_gives_default_plus_policy_error(tmp_path, raw):
    raw["defaults"]["allow_api_key_billing"] = True
    path = user_policy_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(raw), encoding="utf-8")
    got = load_policy(tmp_path)
    assert got.source == "default"
    assert got.policy == load_default_policy()
    assert "allow_api_key_billing" in got.error and got.errors


def test_unparsable_and_unreadable_user_files_fall_back(tmp_path):
    path = user_policy_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    assert load_policy(tmp_path).error
    path.write_bytes(b"\xff\xfe\x00bad")
    got = load_policy(tmp_path)
    assert got.source == "default" and got.error
    path.unlink()
    path.mkdir()                                                                # a folder where the file should be
    got = load_policy(tmp_path)
    assert got.source == "default" and "cannot be read" in got.error


def test_write_policy_validates_then_stores_atomically(tmp_path, raw):
    raw["providers"]["claude"]["model"] = "opus"
    stored = write_policy(tmp_path, raw)
    assert stored.model_for("claude") == "opus"
    path = user_policy_path(tmp_path)
    assert load_policy(tmp_path).policy == stored
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in path.parent.iterdir()] == ["policy.json"]           # no temp file left
    bad = copy.deepcopy(raw)
    bad["defaults"]["order"] = []
    with pytest.raises(PolicyInvalidError):
        write_policy(tmp_path, bad)
    assert load_policy(tmp_path).policy == stored                               # a refused body wrote nothing
