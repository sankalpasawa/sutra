"""Egress scrub and audit row (work package ABS-2; the old test_switch_egress cases re-expressed)."""
from __future__ import annotations

import json
import stat
import sys
import time

import pytest

from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.egress import SHAPES, Egress, scan
from sutra_app.connectors.models import AskRequest, JsonRequest, Message
from sutra_app.connectors.engine_port import make_port  # noqa: F401  (the engine seam exists)
from test_chat_port import make

SAMPLES = {
    "openai-key": "sk-abcdefgh12345678", "github-token": "ghp_" + "a" * 24, "github-pat": "github_pat_" + "b" * 24,
    "slack-token": "xoxb-1234567890-abc", "aws-key-id": "AKIA" + "A" * 16, "bearer": "Bearer " + "c" * 20,
    "jwt": "eyJabcdefgh.eyJabcdefgh.abcdefgh", "stripe-key": "sk_live_" + "d" * 16,
    "pem-private-key": "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
    "slack-webhook": "https://hooks.slack.com/services/T000/B000/XXXXXXXXXX",
    "discord-webhook": "https://discord.com/api/webhooks/123456/abcdefghijk",
}


@pytest.mark.parametrize("name,sample", sorted(SAMPLES.items()))
def test_each_shape_is_replaced_and_counted(name, sample):
    out, counts = scan(f"before {sample} after", replace=True)
    assert sample not in out and f"[redacted:{name}]" in out and counts.get(name) == 1


def test_prefix_keeping_shapes_keep_the_prefix_only():
    out, counts = scan("DATABASE_URL=postgres://user:hunter2hunter2@host/db password = abcdefghijkl1234", replace=True)
    assert "hunter2" not in out and "abcdefghijkl1234" not in out and "postgres://[redacted:db-uri-credentials]host/db" in out
    assert counts == {"db-uri-credentials": 1, "private-key-env": 1}


def test_every_shape_has_a_sample():
    assert {n for n, _, k in SHAPES if not k} == set(SAMPLES)


def test_observe_mode_returns_identical_text_and_writes_the_row(tmp_path):
    e = Egress(tmp_path / "c" / "egress.jsonl")
    text = f"key {SAMPLES['openai-key']} and {SAMPLES['jwt']}"
    assert e.check(text, session="s1", provider="claude", replace=False) is text
    row, = e.rows()
    assert row["mode"] == "observe" and row["shapes"] == {"jwt": 1, "openai-key": 1} and row["session"] == "s1"


def test_the_row_holds_no_match_and_the_file_is_private(tmp_path):
    e = Egress(tmp_path / "egress.jsonl")
    e.check(f"x {SAMPLES['github-token']}", session=None, provider="codex", replace=True)
    raw = (tmp_path / "egress.jsonl").read_text()
    assert SAMPLES["github-token"] not in raw and "ghp_" not in raw
    if sys.platform != "win32":
        assert stat.S_IMODE((tmp_path / "egress.jsonl").stat().st_mode) == 0o600


def test_known_secret_values_are_scrubbed(tmp_path):
    class R:
        def secrets(self):
            return ["topsecretvalue"]
    e = Egress(tmp_path / "e.jsonl", redactor=R())
    assert e.check("a topsecretvalue b", session="s", provider="claude", replace=True) == "a [redacted:secret-value] b"
    assert e.rows()[0]["shapes"] == {"secret-value": 1}


def test_a_long_text_is_scanned_in_bounded_time():
    text = ("-----BEGIN PRIVATE KEY-----\n" * 5000) + "a" * 200_000
    t = time.perf_counter()
    scan(text, replace=True)
    assert time.perf_counter() - t < 5


def test_an_unwritable_log_never_stops_the_call(tmp_path):
    (tmp_path / "blocker").write_text("x")
    e = Egress(tmp_path / "blocker" / "egress.jsonl")
    assert e.check("hello", session="s", provider="claude", replace=True) == "hello"


def test_a_chat_prompt_is_scrubbed_before_it_reaches_the_provider(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    router.egress = Egress(tmp_path / "egress.jsonl")
    port.send("cs_e1", ChatTurnIn(text=f"use {SAMPLES['openai-key']} please"))
    assert SAMPLES["openai-key"] not in claude.calls[0].prompt and "[redacted:openai-key]" in claude.calls[0].prompt
    assert router.egress.rows()[0]["shapes"] == {"openai-key": 1}


def test_the_carry_over_is_scrubbed_too(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    router.egress = Egress(tmp_path / "egress.jsonl")
    history.messages_list = [Message(role="user", text=f"old {SAMPLES['jwt']}"), Message(role="user", text="now")]
    port.send("cs_e2", ChatTurnIn(text="now"))
    assert SAMPLES["jwt"] not in claude.calls[0].prompt and "[redacted:jwt]" in claude.calls[0].prompt


def test_the_engine_path_is_observe_only_and_byte_identical(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    router.egress = Egress(tmp_path / "egress.jsonl")
    from sutra_app.connectors.models import RouteContext
    from sutra_app.engine.port import CompletionRequest
    secret = SAMPLES["openai-key"]
    router.complete(CompletionRequest(system="s", user=f"prompt {secret}"))
    assert claude.calls[0].prompt.count(secret) == 1
    assert router.egress.rows()[0]["mode"] == "observe" and router.egress.rows()[0]["shapes"] == {"openai-key": 1}


def test_orchestrator_json_calls_are_scrubbed(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    router.egress = Egress(tmp_path / "egress.jsonl")
    try:
        router.call_json(JsonRequest(user=f"x {SAMPLES['github-token']}", schema={"type": "object"}))
    except Exception:
        pass                                            # the stub's reply need not be JSON; the prompt is what is checked
    assert all(SAMPLES["github-token"] not in c.prompt for c in claude.calls)
    assert router.egress.rows()[0]["mode"] == "replace"


@pytest.mark.parametrize("uri,leak", [
    ("postgres://user:p@ss:word123@host/db", "word123"),
    ("postgres://u:pa/ss1234@h/x", "ss1234"),
    ("redis://:onlypass99@cache:6379/0", "onlypass99"),
])
def test_db_uri_credentials_with_at_colon_or_slash_in_the_password_are_fully_replaced(uri, leak):
    out, counts = scan(f"a {uri} and then more", replace=True)
    assert leak not in out and counts == {"db-uri-credentials": 1} and out.startswith("a ") and out.endswith(" and then more")
    assert "[redacted:db-uri-credentials]" in out


def test_a_uri_without_credentials_is_left_alone():
    assert scan("see postgres://host:5432/db and me@x.org", replace=True)[0] == "see postgres://host:5432/db and me@x.org"
