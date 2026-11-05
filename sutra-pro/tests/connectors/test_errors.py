"""CN-1: the connector error tree (connectors design 3.2)."""
import importlib.util
from datetime import timezone

import pytest

import sutra_app.connectors as connectors
from sutra_app.connectors import errors as E
from sutra_app.engine import port

# code -> (class, kind, retryable, fallback_ok): the table of design 3.2, one row per code
TABLE = {
    "no_model": (E.NoProviderError, "unavailable", False, False),
    "cli_missing": (E.CliMissingError, "unavailable", False, True),
    "cli_flag_unsupported": (E.FlagUnsupportedError, "unavailable", False, True),
    "not_signed_in": (E.NotSignedInError, "auth", False, True),
    "account_blocked": (E.AccountBlockedError, "auth", False, True),
    "quota": (E.QuotaError, "quota", False, True),
    "rate_limited": (E.RateLimitedError, "quota", True, True),
    "overloaded": (E.OverloadedError, "unavailable", True, True),
    "server_error": (E.ServerError, "unavailable", True, True),
    "timeout": (E.CallTimeoutError, "timeout", True, True),
    "crashed": (E.CrashedError, "unavailable", True, True),
    "protocol_error": (E.ProtocolError, "unavailable", False, True),
    "provider_error": (E.ProviderError, "unavailable", True, True),
    "model_not_found": (E.ModelNotFoundError, "unavailable", False, True),
    "session_lost": (E.SessionLostError, "unavailable", False, False),
    "empty_reply": (E.EmptyReplyError, "bad_output", True, True),
    "structured": (E.StructuredError, "bad_output", False, False),
    "invalid_json": (E.InvalidJsonError, "bad_output", False, False),
    "reply_truncated": (E.ReplyTruncatedError, "bad_output", False, False),
    "invalid_request": (E.InvalidRequestError, "bad_output", False, False),
    "envelope_exceeded": (E.EnvelopeExceededError, "quota", False, False),
    "cancelled": (E.CallCancelledError, "unavailable", False, False),
    "policy_invalid": (E.PolicyInvalidError, "unavailable", False, False),
}
# the six codes the engine names: the class is also the engine's class
ENGINE = {"no_model": port.NoModelAvailable, "cli_missing": port.CliMissing, "not_signed_in": port.NotSignedIn,
          "quota": port.QuotaExhausted, "timeout": port.ModelTimeout, "structured": port.StructuredOutputFailed}


def test_registry_holds_exactly_the_codes_of_the_table():
    assert set(E.ERROR_CLASSES) == set(TABLE)
    assert all(cls.code == code for code, cls in E.ERROR_CLASSES.items())


@pytest.mark.parametrize("code", sorted(TABLE))
def test_each_code_has_the_flags_of_the_table(code):
    cls, kind, retryable, fallback = TABLE[code]
    e = cls("x", provider="claude")
    assert E.ERROR_CLASSES[code] is cls
    assert (e.code, e.kind, e.retryable, e.fallback_ok) == (code, kind, retryable, fallback)
    assert e.kind in E.KINDS
    assert isinstance(e, RuntimeError) and isinstance(e, port.ModelError) and isinstance(e, E.ConnectorError)


@pytest.mark.parametrize("code,engine_cls", sorted(ENGINE.items()))
def test_engine_classes_are_also_bases_of_the_six_named_codes(code, engine_cls):
    assert isinstance(E.ERROR_CLASSES[code]("x"), engine_cls)


def test_other_codes_are_not_engine_subclasses_of_the_named_six():
    e = E.RateLimitedError("x")
    assert not isinstance(e, (port.NotSignedIn, port.QuotaExhausted, port.ModelTimeout))
    assert not isinstance(E.QuotaError("x"), port.NotSignedIn)


def test_instances_keep_the_engine_flags_that_the_table_overrides_nothing_of():
    # ModelTimeout is retryable in the engine and in the table; QuotaExhausted is not in either
    assert E.CallTimeoutError().retryable is port.ModelTimeout.retryable is True
    assert E.QuotaError().retryable is port.QuotaExhausted.retryable is False


# ---- user_message: the wording of the table --------------------------------------------------------------------------

MESSAGES = [
    (E.CliMissingError("", provider="claude"), "Claude CLI not found on PATH: install it and run `claude` once"),
    (E.CliMissingError("", provider="codex"), "Codex CLI not found on PATH: install it and run `codex login`"),
    (E.FlagUnsupportedError("", provider="claude", detail={"cli": "claude", "version": "2.1.308", "flag": "--json-schema"}),
     "claude 2.1.308 does not accept `--json-schema`: update the CLI"),
    (E.NotSignedInError("", provider="claude"), "Claude is not signed in: run `claude auth login`"),
    (E.NotSignedInError("", provider="codex"), "Codex is not signed in: use Sign in or run `codex login`"),
    (E.AccountBlockedError("", provider="codex"), "Your Codex account needs attention (organisation, hold or verification)"),
    (E.RateLimitedError("", provider="claude"), "Claude is rate limiting; retrying"),
    (E.OverloadedError("", provider="codex"), "Codex is busy"),
    (E.ServerError("", provider="claude"), "Claude had a server error"),
    (E.CallTimeoutError("", provider="claude", detail={"seconds": 900}), "Claude did not answer within 900 s"),
    (E.CrashedError("", provider="codex", detail={"cli": "codex", "exit": 137}), "codex stopped unexpectedly (exit 137)"),
    (E.ProtocolError("", provider="claude", detail={"cli": "claude"}), "claude gave output this app cannot read"),
    (E.ProviderError("rate card missing", provider="claude"), "rate card missing"),
    (E.ModelNotFoundError("", provider="codex", detail={"model": "gpt-9"}), "model gpt-9 is not available"),
    (E.EmptyReplyError("", provider="codex"), "Codex returned nothing"),
    (E.StructuredError(""), "the structured reply could not be produced"),
    (E.ReplyTruncatedError(""), "reply was cut off (partial text in detail)"),
    (E.InvalidRequestError("image /x.png does not exist"), "image /x.png does not exist"),
    (E.EnvelopeExceededError(""), "the envelope allows no more calls, money or time"),
    (E.CallCancelledError(""), "stopped"),
    (E.PolicyInvalidError("policy.json: rules.0.match: unknown key"), "policy.json: rules.0.match: unknown key"),
]


@pytest.mark.parametrize("err,text", MESSAGES, ids=[m[0].code + "-" + str(m[0].provider) for m in MESSAGES])
def test_user_message_matches_the_table(err, text):
    assert err.user_message() == text
    assert str(err) == text or err.message == str(err)


def test_str_of_an_error_built_without_message_is_the_user_message():
    assert str(E.NotSignedInError(provider="claude")) == "Claude is not signed in: run `claude auth login`"


def test_quota_message_names_provider_and_reset_time():
    e = E.QuotaError("", provider="claude", resets_at=1793748000.0)
    assert e.resets_at == 1793748000.0
    assert e.user_message(tz=timezone.utc) == "Claude usage limit reached; resets 2026-11-03 23:20 UTC"
    assert E.QuotaError("", provider="codex").user_message() == "Codex usage limit reached; try again later"


def test_no_provider_message_lists_why_each_provider_was_skipped():
    e = E.NoProviderError(skipped=[("claude", "not signed in"), ("codex", "API-key login refused (D7)")])
    assert e.user_message() == "No model is available: Claude: not signed in; Codex: API-key login refused (D7)"
    assert e.detail["skipped"] == [{"provider": "claude", "reason": "not signed in"},
                                   {"provider": "codex", "reason": "API-key login refused (D7)"}]
    assert "no provider is configured" in E.NoProviderError().user_message()


def test_invalid_json_message_is_cut_at_500_characters():
    assert len(E.InvalidJsonError("x" * 900).user_message()) == 500
    assert "JSON" in E.InvalidJsonError().user_message()


def test_session_lost_is_internal_but_still_says_something_plain():
    assert "session was lost" in E.SessionLostError().user_message()


# ---- as_dict ---------------------------------------------------------------------------------------------------------

def test_as_dict_holds_no_prompt_text_and_no_secrets():
    e = E.CrashedError("", provider="claude", detail={
        "exit": 1, "prompt": "SECRET PROMPT TEXT", "system": "sys text", "stdin": "typed", "env": {"PATH": "/bin"},
        "api_key": "sk-abc", "GITHUB_TOKEN": "ghp_x", "attempts": [{"code": "ok", "prompt": "nested prompt"}],
        "nested": {"password": "p", "keep": 1}})
    d = e.as_dict()
    assert "SECRET PROMPT" not in repr(d) and "sk-abc" not in repr(d) and "ghp_x" not in repr(d) and "nested prompt" not in repr(d)
    assert d["detail"]["exit"] == 1 and d["detail"]["nested"] == {"keep": 1}
    assert d["detail"]["attempts"] == [{"code": "ok"}]
    assert e.detail["prompt"] == "SECRET PROMPT TEXT"      # the error object itself is untouched


def test_as_dict_shape_and_caps():
    e = E.QuotaError("", provider="claude", resets_at=5.0, detail={"big": "y" * 5000, "many": list(range(500)), "obj": object()})
    d = e.as_dict()
    assert set(d) == {"code", "kind", "retryable", "fallback_ok", "provider", "message", "detail", "resets_at"}
    assert (d["code"], d["kind"], d["retryable"], d["fallback_ok"], d["provider"], d["resets_at"]) == ("quota", "quota", False, True, "claude", 5.0)
    assert len(d["detail"]["big"]) == E.MAX_DETAIL_STRING + 3
    assert len(d["detail"]["many"]) == E.MAX_DETAIL_ITEMS
    assert isinstance(d["detail"]["obj"], str)
    assert d["message"].startswith("Claude usage limit reached")


# ---- error_for_code and the package ---------------------------------------------------------------------------------

def test_error_for_code_builds_the_class_and_passes_keywords():
    e = E.error_for_code("rate_limited", "slow down", provider="codex")
    assert type(e) is E.RateLimitedError and e.provider == "codex" and e.message == "slow down"


def test_error_for_code_with_an_unknown_code_is_a_provider_error_that_remembers_it():
    e = E.error_for_code("brand_new", "odd", detail={"a": 1})
    assert type(e) is E.ProviderError and e.detail == {"a": 1, "code": "brand_new"}


def test_package_exports_every_error_class():
    for name in [c.__name__ for c in E.ERROR_CLASSES.values()] + ["ConnectorError", "ERROR_CLASSES", "error_for_code"]:
        assert getattr(connectors, name) is getattr(E, name)
        assert name in connectors.__all__


def test_package_resolves_later_names_only_when_their_module_exists():
    for name, module in {"Router": "router", "build_router": "factory", "make_port": "engine_port"}.items():
        exists = importlib.util.find_spec(f"sutra_app.connectors.{module}") is not None
        assert (name in connectors.__all__) is exists
        if not exists:
            with pytest.raises(AttributeError, match="not part of this build yet"):
                getattr(connectors, name)
    with pytest.raises(AttributeError):
        connectors.NoSuchThing
