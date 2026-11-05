#!/usr/bin/env python3
"""Fake `claude`, `codex` and `gh` for the connector tests (work package CN-2, connectors.md section 7).

    fake_cli.py <claude|codex|gh> ARGS...      (the sh wrappers next to this file call it; stdlib only, Python 3.9+)
    fake_cli.py --scenarios <claude|codex>     list the scenario names

It replays the streams captured from the real CLIs in tests/fixtures/connectors/ (MANIFEST.json says what was captured, what is
derived and what is handwritten), so no test needs a real model. It never touches ~/.claude, ~/.codex or the network.

ENVIRONMENT (no name contains KEY, TOKEN, SECRET or PASSWORD, so a connector's extra_env accepts them)
  FAKE_CLI_STATE         a directory: the sequence counter, sessions.json, calls.jsonl, exits.jsonl, auth.json. Without it the
                         fake is stateless: every call is the first, nothing is logged, sessions never accumulate.
  FAKE_CLI_SEQUENCE      comma list of scenarios, one per MODEL CALL (claude -p, codex exec, codex exec resume) of any CLI; the
                         last one repeats; `name*3` repeats a name. Status, help and version commands do not consume it.
  FAKE_CLAUDE_SEQUENCE / FAKE_CODEX_SEQUENCE   the same for one CLI (own counter); wins over FAKE_CLI_SEQUENCE.
                         Default scenario: `ok` (ok_structured when a schema was sent, else ok_plain); `ok` becomes
                         not_logged_in / not_signed_in while that CLI is signed out.
  FAKE_CLAUDE_AUTH / FAKE_CODEX_AUTH / FAKE_GH_AUTH   signed_in (default) | signed_out | api_key (claude, codex) | console
                         (claude) | error (claude, codex). auth.json in the state directory (written by a finished
                         `codex login --device-auth`) wins over the variable. FAKE_AUTH_FROM_CONFIG=1: claude and codex are
                         signed in only while $CLAUDE_CONFIG_DIR (or $CODEX_HOME) holds a file named fake-login (how a
                         signed-out probe with an empty config directory behaves).
  FAKE_REPLY_JSON        JSON that replaces the reply (structured_output, the StructuredOutput tool input, result, the text
  FAKE_REPLY_TEXT        blocks, agent_message.text) of the scenarios that carry an `ok` reply; TEXT wins for text fields and
                         JSON for structured fields. Error scenarios keep their own text.
  FAKE_COST_USD          this call's cost in usd (Claude); FAKE_USAGE: JSON, this call's token amounts under the CLI's own key
                         names (a key not listed counts 0). The fake adds them to the session total, because both CLIs report
                         cumulative counters on a resumed session (connectors.md 1.2 row 6).
  FAKE_PATCH             JSON list of edit ops applied last to the scenario's lines: {"match": {"type": "result"},
                         "set": {"is_error": true, "usage.output_tokens": 3}, "delete": ["a.b"], "drop": false}
  FAKE_LINE_DELAY        seconds between output lines (the `slow` scenario: 0.3)
  FAKE_EXIT_CODE         exit code instead of the one the stream implies
  FAKE_BAD_FLAG          the flag the `bad_flag` scenario complains about (default: the first long option of the call)
  FAKE_IGNORE_SIGINT / FAKE_IGNORE_SIGTERM    1: the process ignores that signal (cancel ladder tests)
  FAKE_MAX_SECONDS       hang, slow and device-auth give up after this long (default 60), so a forgotten fake cannot live on
  FAKE_STDIN_TIMEOUT     seconds to wait for the prompt on stdin (default 5); the call log says stdin_complete false if it
                         never reached EOF
  FAKE_LOG_ENV           comma list of variable names whose VALUES go into the call log as env_values
  FAKE_CLAUDE_VERSION / FAKE_CODEX_VERSION    version string reported by --version (and by Claude's init event)
  FAKE_HELP_MISSING      comma list of flags removed from the --help text (feature detection tests)
  FAKE_CLAUDE_MCP        present (default) | local | empty : what `claude mcp list` prints
  FAKE_DEVICE_AUTH_SECONDS   `codex login --device-auth` completes by itself after this many seconds; otherwise it waits for
                         the file <state>/device_auth_approve (or for a signal)
  FAKE_CODEX_ROLLOUT     on (default) | off | bad : write, skip or corrupt the rollout file with the token_count events (it goes
                         to $CODEX_HOME, else to <state>/codex_home, and never into your real ~/.codex)
  FAKE_GH_REPOS          comma list of owner/repo that exist (default octo-org/hello-world)
  FAKE_GH_FAIL           not_found | rate_limit | unauthorized | server_error | network : every `gh api` call fails that way
  FAKE_GH_BIG_BYTES      size of the generated file big.txt (default 60000)
  FAKE_PYTHON / SUTRA_FAKE_PYTHON   the interpreter the wrappers use (SUTRA_ wins; a connector drops SUTRA_* from the child
                         environment, so pass FAKE_PYTHON through extra_env)

SCENARIOS: see scenario_names(cli). A scenario is a fixture name (ok_structured, ok_plain, not_logged_in, quota, overloaded, ...),
a row id of the error tables in connectors.md (C4, X6, ...), `file:<absolute path>` (replay any JSONL file), or one of hang,
hang_silent, slow, slow401, crash, noise, bad_flag and the other presets.

CALL LOG: every invocation appends one record to calls.jsonl at its start: n, cli, kind (call | probe), op, argv (without the
program name), cwd, cwd_entries, stdin, stdin_complete, env_keys (names only; PWD, SHLVL, _ and the other names a shell, macOS or
Python add on their own are left out), env_values, files (path, exists, mode, size and content of file-valued flags such as
--output-schema, --system-prompt-file and --mcp-config, read while the call runs, because the connector deletes them afterwards),
scenario, session_id, pid, t_start. exits.jsonl gets {n, cli, exit, t_end, signal} when the process ends.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import datetime
import fcntl
import hashlib
import json
import os
import re
import select
import signal
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures" / "connectors"

CLIS = ("claude", "codex", "gh")
EXIT_CRASH = 137                 # what a killed child shows (128 + SIGKILL)
EXIT_SETUP = 64                  # the test set the fake up wrongly
EXIT_SIGPIPE = 141
EXIT_TIMEOUT = 124
DEFAULT_MAX_SECONDS = 60.0
# names a shell, macOS or Python put into a child's environment by themselves; they are not what the caller passed
SHELL_ARTEFACTS = frozenset({"PWD", "OLDPWD", "SHLVL", "_", "__CF_USER_TEXT_ENCODING", "CPATH", "LIBRARY_PATH", "MANPATH", "SDKROOT"})
MODEL_ALIASES = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}      # observed: the alias sonnet ran as claude-sonnet-5-5
CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
CODEX_SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")           # Claude result.usage
MODEL_USAGE_KEYS = {"input_tokens": "inputTokens", "cache_creation_input_tokens": "cacheCreationInputTokens",
                    "cache_read_input_tokens": "cacheReadInputTokens", "output_tokens": "outputTokens"}          # ... and in modelUsage
CODEX_USAGE_KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
NOISE_LINES = ("Warning: something printed to stdout that is not an event", "")
AUTH_MODES = {"claude": ("signed_in", "signed_out", "api_key", "console", "error"), "codex": ("signed_in", "signed_out", "api_key", "error"),
              "gh": ("signed_in", "signed_out")}


class FakeError(Exception):
    """The test set the fake up wrongly (unknown scenario, bad variable): reported on stderr, exit 64."""


class Stop(BaseException):
    """Raised by a signal handler to end the run with an exit code."""

    def __init__(self, code, sig=None):
        BaseException.__init__(self, code)
        self.code, self.sig = code, sig


# ------------------------------------------------------------------------------------------------ fixtures and JSON helpers
_MISSING = object()


def fixture_text(rel):
    return (FIXTURES / rel).read_text(encoding="utf-8")


def fixture_json(rel):
    return json.loads(fixture_text(rel))


def parse_lines(text):
    """JSONL text -> list of dicts; a line that is not a JSON object (noise, a blank line) stays a string."""
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    out = []
    for raw in parts:
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = None
        out.append(obj if isinstance(obj, dict) else raw)
    return out


def load_lines(rel):
    return parse_lines(fixture_text(rel))


def dump_line(item):
    return item if isinstance(item, str) else json.dumps(item, separators=(",", ":"), ensure_ascii=False)


def compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _parts(path):
    return [int(p) if p.isdigit() else p for p in path.split(".")]


def get_path(obj, path, default=_MISSING):
    cur = obj
    for part in _parts(path):
        try:
            cur = cur[part]
        except (KeyError, IndexError, TypeError):
            return default
    return cur


def set_path(obj, path, value):
    parts = _parts(path)
    cur = obj
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def del_path(obj, path):
    parts = _parts(path)
    cur = obj
    for part in parts[:-1]:
        try:
            cur = cur[part]
        except (KeyError, IndexError, TypeError):
            return
    try:
        del cur[parts[-1]]
    except (KeyError, IndexError, TypeError):
        pass


def apply_patch(lines, ops, where):
    """Edit parsed lines. Op: {"match": {path: value, ...}, "set": {path: value}, "delete": [path], "drop": bool}.
    An op that matches no line is an error, so a preset cannot silently stop doing its job when a fixture changes."""
    out = list(lines)
    for op in ops:
        match = op.get("match", {})
        hit = False
        kept = []
        for item in out:
            if isinstance(item, dict) and all(get_path(item, k) == v for k, v in match.items()):
                hit = True
                if op.get("drop"):
                    continue
                for path in op.get("delete", ()):
                    del_path(item, path)
                for path, value in op.get("set", {}).items():
                    try:
                        set_path(item, path, copy.deepcopy(value))
                    except (KeyError, IndexError, TypeError):
                        raise FakeError("%s: cannot set %s (a part of the path is missing)" % (where, path))
            kept.append(item)
        if not hit:
            raise FakeError("%s: the edit %s matched no line" % (where, compact(match)))
        out = kept
    return out


def split_even(text, parts):
    """Cut text into at most `parts` non-empty pieces of nearly equal length."""
    if not text:
        return []
    parts = max(1, min(parts, len(text)))
    size, extra = divmod(len(text), parts)
    out, pos = [], 0
    for i in range(parts):
        step = size + (1 if i < extra else 0)
        out.append(text[pos:pos + step])
        pos += step
    return out


def truthy(value):
    return value is not None and str(value).strip().lower() not in ("", "0", "false", "no", "off")


def manifest_index():
    return {e["path"]: e for e in fixture_json("MANIFEST.json")["files"]}


def recorded_after(rel):
    """The fixture whose session `rel` continues (MANIFEST recorded_after, inherited through `base`), or None."""
    index = manifest_index()
    seen = set()
    while rel in index and rel not in seen:
        seen.add(rel)
        entry = index[rel]
        if entry.get("recorded_after"):
            return entry["recorded_after"]
        rel = entry.get("base")
    return None


# ------------------------------------------------------------------------------------------------ scenarios
class Scn:
    """A scenario: a fixture file (or a base scenario) plus edits. An attribute left None is inherited from the base."""

    FIELDS = ("file", "probe", "replyable", "exit", "delay", "free", "hang_after", "noise", "interrupt", "external")

    def __init__(self, file=None, base=None, patch=(), probe=None, replyable=None, exit=None, delay=None,
                 free=None, hang_after=None, noise=None, interrupt=None, external=None):
        self.file, self.base, self.patch, self.probe = file, base, list(patch), probe
        self.replyable, self.exit, self.delay = replyable, exit, delay
        self.free, self.hang_after, self.noise, self.interrupt, self.external = free, hang_after, noise, interrupt, external

    def over(self, parent):
        """A copy of this scenario laid over its resolved base (a base-less scenario passes an empty Scn)."""
        merged = Scn(patch=parent.patch + self.patch)
        for name in self.FIELDS:
            mine = getattr(self, name)
            setattr(merged, name, mine if mine is not None else getattr(parent, name))
        return merged


def _error_edits(error, text, status):
    """Edits that turn an API-error stream (an assistant line plus a result line) into another error."""
    return [{"match": {"type": "assistant"}, "set": {"error": error, "message.content.0.text": text}},
            {"match": {"type": "result"}, "set": {"result": text, "api_error_status": status}}]


def _result_only_error(status, text=None):
    """C19: the result line fails with a status or a text but the assistant line carries no `error` enum."""
    result = {"api_error_status": status}
    if text is not None:
        result["result"] = text
    return [{"match": {"type": "assistant"}, "delete": ["error", "is_api_error_message"]}, {"match": {"type": "result"}, "set": result}]


def _claude_table():
    S = Scn
    return {
        "ok_structured": S("claude/stream_structured_ok.jsonl", replyable=True),
        "ok_plain": S("claude/stream_resume_plain_ok.jsonl", replyable=True),
        "not_logged_in": S("claude/stream_not_logged_in.jsonl"),
        "mcp_connected": S("claude/stream_mcp_server_connected.jsonl"),
        "tool_profile": S("claude/stream_tool_profile_init.jsonl"),
        "session_lost": S("claude/stream_resume_unknown_session.jsonl", probe="claude_resume_unknown_session"),
        "control_interrupt": S("claude/control_interrupt_response.jsonl", exit=0, interrupt=True),
        "quota": S("derived/claude_quota_rejected.jsonl"),
        "billing_error": S("derived/claude_billing_error.jsonl"),
        "overloaded": S("derived/claude_overloaded.jsonl"),
        "server_error": S("derived/claude_server_error.jsonl"),
        "invalid_request": S("derived/claude_invalid_request.jsonl"),
        "model_not_found": S("derived/claude_model_not_found.jsonl"),
        "login_expired": S("derived/claude_login_expired.jsonl"),
        "structured_failed": S("derived/claude_structured_failed.jsonl"),
        "error_during_execution": S("derived/claude_error_during_execution.jsonl"),
        "truncated_no_result": S("derived/claude_truncated_no_result.jsonl"),
        "plain_not_json": S("derived/claude_plain_not_json.jsonl"),
        "plain_json_in_fence": S("derived/claude_plain_json_in_fence.jsonl"),
        "plain_json_wrong_shape": S("derived/claude_plain_json_wrong_shape.jsonl"),
        "noise_lines": S("derived/claude_noise_lines.jsonl", replyable=True),
        # command-line failures that print no stream (cli_errors.json)
        "bad_flag": S(probe="claude_unknown_option"),
        "invalid_json_schema": S(probe="claude_invalid_json_schema"),
        "system_prompt_file_missing": S(probe="claude_system_prompt_file_missing"),
        # presets: a fixture with edits (the codes are the CLI's own enum, the wording of the edited texts is invented)
        "oauth_org_not_allowed": S(base="not_logged_in", patch=_error_edits("oauth_org_not_allowed", "Your organization does not allow this login", 403)),
        "account_on_hold": S(base="not_logged_in", patch=_error_edits("account_on_hold", "Your account is on hold", 403)),
        "verification_required": S(base="not_logged_in", patch=_error_edits("verification_required", "Verification is required to continue", 403)),
        "rate_limited": S(base="quota", patch=[{"match": {"type": "rate_limit_event"}, "drop": True}]
                          + _error_edits("rate_limit", "API Error: rate limited, retry later", 429)),
        "max_output_tokens": S(base="overloaded", patch=_error_edits("max_output_tokens", '{"answer": "partial reply cut by the output limit', None)),
        "max_budget": S(base="error_during_execution", patch=[{"match": {"type": "result"}, "set": {"subtype": "error_max_budget_usd"}}]),
        "result_error_401": S(base="not_logged_in", patch=_result_only_error(401, "Invalid authentication credentials")),
        "result_error_403": S(base="not_logged_in", patch=_result_only_error(403, "Forbidden")),
        "result_error_not_logged_in": S(base="not_logged_in", patch=_result_only_error(None)),
        "result_error_429": S(base="not_logged_in", patch=_result_only_error(429, "Too many requests")),
        "result_error_503": S(base="not_logged_in", patch=_result_only_error(503, "Service unavailable")),
        "empty_reply": S(base="ok_plain", replyable=False, patch=[{"match": {"type": "assistant"}, "set": {"message.content.0.text": ""}},
                                                                  {"match": {"type": "result"}, "set": {"result": ""}}]),
        # behaviours
        "truncated_exit0": S(base="truncated_no_result", exit=0),
        "crash": S(base="truncated_no_result"),
        "hang": S(base="ok", hang_after=1),
        "hang_silent": S(base="ok", hang_after=0),
        "slow": S(base="ok", delay=0.3, free=1),
        "noise": S(base="ok", noise=True),
    }


def _codex_table():
    S = Scn
    return {
        "ok_structured": S("codex/exec_structured_ok.jsonl", replyable=True),
        "ok_plain": S("codex/exec_resume_plain_ok.jsonl", replyable=True),
        "not_signed_in": S("codex/exec_not_signed_in.jsonl"),
        "usage_limit": S("derived/codex_usage_limit.jsonl"),
        "rate_limited_429": S("derived/codex_rate_limited_429.jsonl"),
        "server_error_500": S("derived/codex_server_error_500.jsonl"),
        "schema_rejected_400": S("derived/codex_schema_rejected_400.jsonl"),
        "model_unsupported_400": S("derived/codex_model_unsupported_400.jsonl"),
        "reply_not_json": S("derived/codex_reply_not_json.jsonl"),
        "reply_wrong_shape": S("derived/codex_reply_wrong_shape.jsonl"),
        "reply_in_fence": S("derived/codex_reply_in_fence.jsonl"),
        "truncated_no_turn_end": S("derived/codex_truncated_no_turn_end.jsonl"),
        "empty_reply": S("derived/codex_empty_reply.jsonl"),
        "unknown_item_type": S("derived/codex_unknown_item_type.jsonl", replyable=True),
        "bad_flag": S(probe="codex_unknown_argument"),
        "output_schema_file_invalid": S(probe="codex_output_schema_file_invalid"),
        "output_schema_file_missing": S(probe="codex_output_schema_file_missing"),
        "missing_working_directory": S(probe="codex_missing_working_directory"),
        "session_lost": S(probe="codex_resume_unknown_thread"),
        "provider_error": S(base="usage_limit", patch=[{"match": {"type": "turn.failed"}, "set": {"error.message": "unexpected status 418 I'm a teapot"}}]),
        "usage_limit_try_again": S(base="usage_limit", patch=[{"match": {"type": "turn.failed"}, "set": {
            "error.message": "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Nov 5th, 2026 4:30 PM."}}]),
        "turn_failed_401": S(base="not_signed_in", patch=[{"match": {"type": "error"}, "drop": True}, {"match": {"item.type": "error"}, "drop": True}]),
        "slow401": S(base="not_signed_in", delay=0.5, free=3),
        "truncated_exit0": S(base="truncated_no_turn_end", exit=0),
        "crash": S(base="truncated_no_turn_end"),
        "hang": S(base="ok", hang_after=2),
        "hang_silent": S(base="ok", hang_after=0),
        "slow": S(base="ok", delay=0.3, free=2),
        "noise": S(base="ok", noise=True),
    }


# names the other CLI's table uses for the same thing, so one shared FAKE_CLI_SEQUENCE works whichever CLI answers first
_ALIASES = {
    "claude": {"not_signed_in": "not_logged_in", "usage_limit": "quota", "rate_limited_429": "result_error_429", "server_error_500": "server_error",
               "resume_unknown_session": "session_lost", "unknown_option": "bad_flag", "interrupt": "control_interrupt"},
    "codex": {"not_logged_in": "not_signed_in", "quota": "usage_limit", "overloaded": "server_error_500", "server_error": "server_error_500",
              "rate_limited": "rate_limited_429", "billing_error": "usage_limit", "resume_unknown_thread": "session_lost", "unknown_argument": "bad_flag",
              "schema_rejected": "schema_rejected_400", "model_unsupported": "model_unsupported_400", "model_not_found": "model_unsupported_400"},
}

# the rows of connectors.md 3.4 (C) and 3.5 (X) that a scenario can reproduce; C1, X1 (PATH emptied) and X4 (signed out before the call) need none
ROWS = {
    "claude": {"C2": "bad_flag", "C3a": "invalid_json_schema", "C3b": "system_prompt_file_missing", "C4": "not_logged_in", "C5": "login_expired",
               "C6a": "oauth_org_not_allowed", "C6b": "account_on_hold", "C6c": "verification_required", "C7": "quota", "C8": "rate_limited",
               "C9": "billing_error", "C10": "overloaded", "C11": "server_error", "C12": "invalid_request", "C13": "model_not_found",
               "C14": "max_output_tokens", "C15": "structured_failed", "C16": "session_lost", "C17": "error_during_execution", "C18": "max_budget",
               "C19a": "result_error_401", "C19b": "result_error_403", "C19c": "result_error_not_logged_in", "C19d": "result_error_429",
               "C19e": "result_error_503", "C20": "crash", "C21": "truncated_exit0", "C22": "hang", "C23": "slow", "C24": "empty_reply",
               "C25": "noise_lines"},
    "codex": {"X2": "bad_flag", "X3a": "output_schema_file_invalid", "X3b": "output_schema_file_missing", "X3c": "missing_working_directory",
              "X5": "not_signed_in", "X5b": "slow401", "X5c": "turn_failed_401", "X6": "usage_limit", "X7": "rate_limited_429",
              "X8": "server_error_500", "X9": "schema_rejected_400", "X10": "model_unsupported_400", "X11": "provider_error", "X12": "session_lost",
              "X13": "crash", "X14": "truncated_exit0", "X15": "hang", "X16": "slow", "X17": "empty_reply", "X18": "unknown_item_type"},
}
ROWS_WITHOUT_SCENARIO = {"claude": ("C1",), "codex": ("X1", "X4")}

_TABLES = {}


def table(cli):
    if cli not in _TABLES:
        _TABLES[cli] = _claude_table() if cli == "claude" else _codex_table()
    return _TABLES[cli]


def scenario_names(cli):
    """Every name FAKE_CLI_SEQUENCE accepts for `cli` (the file:<path> form aside)."""
    return sorted(set(table(cli)) | {"ok"} | set(ROWS.get(cli, {})) | set(_ALIASES.get(cli, {})))


def canonical(cli, name):
    """A scenario name as typed -> its key in the table (or "ok"). The fixture's file stem, with or without the cli prefix, also works."""
    tbl = table(cli)
    if name == "ok" or name in tbl:
        return name
    if name in ROWS.get(cli, {}):
        return ROWS[cli][name]
    if name in _ALIASES.get(cli, {}):
        return _ALIASES[cli][name]
    for key, scn in tbl.items():
        if scn.file:
            stem = Path(scn.file).stem
            if name in (stem, stem[len(cli) + 1:] if stem.startswith(cli + "_") else stem):
                return key
    raise FakeError("unknown scenario %r; known: %s" % (name, ", ".join(scenario_names(cli))))


def resolve(cli, name, has_schema):
    """-> a fresh Scn with its base chain applied."""
    key = canonical(cli, name)
    if key == "ok":
        key = "ok_structured" if has_schema else "ok_plain"
    scn = table(cli)[key]
    return scn.over(resolve(cli, scn.base, has_schema) if scn.base else Scn())


def parse_sequence(spec):
    out = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, star, count = part.rpartition("*")
        if star and count.isdigit() and name:
            out.extend([name] * int(count))
        else:
            out.append(part)
    return out


# ------------------------------------------------------------------------------------------------ state and the call log
class State:
    """The FAKE_CLI_STATE directory. Every read-modify-write happens inside locked()."""

    def __init__(self, path):
        self.dir = Path(path) if path else None
        if self.dir is not None:
            self.dir.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def locked(self):
        if self.dir is None:
            yield
            return
        fd = os.open(str(self.dir / "lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)                              # closing releases the lock

    def read(self, name, default):
        if self.dir is None:
            return default
        try:
            return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def write(self, name, data):
        if self.dir is None:
            return
        tmp = self.dir / ("%s.%d.tmp" % (name, os.getpid()))
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(self.dir / name))

    def bump(self, key):
        """Add one to a counter and return the new value (1 on the first call). Stateless: always 0."""
        if self.dir is None:
            return 0
        counters = self.read("counters.json", {})
        counters[key] = counters.get(key, 0) + 1
        self.write("counters.json", counters)
        return counters[key]

    def append(self, name, rec):
        if self.dir is None:
            return
        with open(str(self.dir / name), "a", encoding="utf-8", errors="surrogateescape") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------------------------------------ argument parsing
CLAUDE_SHORT = {"-p": "--print", "-r": "--resume", "-v": "--version", "-h": "--help", "-n": "--name", "-c": "--continue", "-d": "--debug", "-w": "--worktree",
                "--allowed-tools": "--allowedTools", "--disallowed-tools": "--disallowedTools"}
CLAUDE_VALUE = {"--model", "--effort", "--output-format", "--input-format", "--system-prompt", "--system-prompt-file", "--append-system-prompt",
                "--append-system-prompt-file", "--session-id", "--json-schema", "--max-budget-usd", "--permission-mode", "--permission-prompts",
                "--setting-sources", "--settings", "--fallback-model", "--agent", "--agents", "--name", "--plugin-dir", "--plugin-url",
                "--debug-file", "--autocompact"}
CLAUDE_VARIADIC = {"--tools", "--allowedTools", "--disallowedTools", "--mcp-config", "--add-dir", "--betas", "--file"}
CLAUDE_OPTIONAL = {"--resume", "--debug", "--from-pr", "--worktree", "--prompt-suggestions", "--cloud", "--remote-control", "--teleport"}
CODEX_SHORT = {"-c": "--config", "-i": "--image", "-m": "--model", "-s": "--sandbox", "-C": "--cd", "-o": "--output-last-message", "-p": "--profile",
               "-h": "--help", "-V": "--version"}
CODEX_VALUE = {"--config", "--image", "--model", "--sandbox", "--cd", "--output-last-message", "--profile", "--output-schema", "--color",
               "--add-dir", "--local-provider", "--enable", "--disable"}
GH_SHORT = {"-X": "--method", "-H": "--header", "-f": "--raw-field", "-F": "--field", "-q": "--jq", "-t": "--template", "-p": "--preview", "-i": "--include"}
GH_VALUE = {"--method", "--header", "--raw-field", "--field", "--jq", "--template", "--hostname", "--input", "--cache", "--preview"}
FILE_FLAGS = ("--system-prompt-file", "--append-system-prompt-file", "--output-schema", "--settings", "--mcp-config", "--image", "--output-last-message")


def parse_argv(argv, short, value, variadic=(), optional=()):
    """-> (opts, positionals). opts maps a long option name to the list of its values; a flag holds [True]."""
    opts, pos = {}, []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            pos.extend(argv[i + 1:])
            break
        if tok.startswith("--") and "=" in tok:
            name, _, val = tok.partition("=")
            opts.setdefault(short.get(name, name), []).append(val)
            i += 1
        elif tok.startswith("-") and tok != "-":
            name = short.get(tok, tok)
            if name in value:
                opts.setdefault(name, []).append(argv[i + 1] if i + 1 < len(argv) else "")
                i += 2
            elif name in variadic:
                vals, j = [], i + 1
                while j < len(argv) and not (argv[j].startswith("-") and argv[j] != "-"):
                    vals.append(argv[j])
                    j += 1
                opts.setdefault(name, []).extend(vals or [""])
                i = j
            elif name in optional:
                if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    opts.setdefault(name, []).append(argv[i + 1])
                    i += 2
                else:
                    opts.setdefault(name, []).append("")
                    i += 1
            else:
                opts.setdefault(name, []).append(True)
                i += 1
        else:
            pos.append(tok)
            i += 1
    return opts, pos


def last(opts, name, default=None):
    vals = opts.get(name)
    return vals[-1] if vals else default


# ------------------------------------------------------------------------------------------------ one invocation
class Stream:
    def __init__(self, lines, exit_code, stderr="", delay=0.0, free=0, hang_after=None):
        self.lines, self.exit, self.stderr = lines, exit_code, stderr
        self.delay, self.free, self.hang_after = delay, free, hang_after


class Run:
    """One invocation of the fake. Everything is injected, so a test can run it in-process; signal handlers are installed only
    with handle_signals (the command line entry point does that)."""

    def __init__(self, cli, argv, env=None, stdin=None, stdout=None, stderr=None, cwd=None, handle_signals=False):
        self.cli, self.argv = cli, list(argv)
        self.env = dict(os.environ if env is None else env)
        self._stdin = stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr
        self.cwd = cwd if cwd is not None else os.getcwd()
        self.handle_signals = handle_signals
        self.state = State(self.env.get("FAKE_CLI_STATE"))
        self.opts, self.pos = {}, []
        self.rec = None
        self.stdin_bytes = b""
        self.t_start = time.time()
        self._exit_logged = False

    # ---- plumbing
    def getenv(self, name, default=None):
        return self.env.get(name, default)

    def out(self, text):
        self.stdout.write(text)
        self.stdout.flush()

    def err(self, text):
        self.stderr.write(text)
        self.stderr.flush()

    def number(self, name, default):
        raw = self.getenv(name)
        if raw in (None, ""):
            return default
        try:
            return float(raw)
        except ValueError:
            raise FakeError("%s=%r is not a number" % (name, raw))

    def json_env(self, name, expect=None):
        """The JSON value of a variable (None when unset); `expect` is the type it must have."""
        raw = self.getenv(name)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError as e:
            raise FakeError("%s is not valid JSON: %s" % (name, e))
        if expect is not None and not isinstance(value, expect):
            raise FakeError("%s must be a JSON %s" % (name, "object" if expect is dict else "list"))
        return value

    def run(self):
        code, sig = None, None
        try:
            if self.handle_signals:
                self._install_signals()
            code = self._dispatch()
        except Stop as stop:
            code, sig = stop.code, stop.sig
        except BrokenPipeError:
            code = EXIT_SIGPIPE
        except FakeError as e:
            with contextlib.suppress(BrokenPipeError):
                self.err("fake %s: %s\n" % (self.cli, e))
            code = EXIT_SETUP
        finally:
            self._log_exit(code, sig)
        return code

    def _install_signals(self):
        def on_int(signum, frame):
            raise Stop(0 if self.cli == "claude" else 130, "SIGINT")       # claude answered SIGINT with exit 0 (cli_errors.json)

        def on_term(signum, frame):
            if self.cli == "claude":
                raise Stop(143, "SIGTERM")                         # claude answered SIGTERM with exit 143; codex was simply killed (-15)
            self._log_exit(-signal.SIGTERM, "SIGTERM")
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGINT, signal.SIG_IGN if truthy(self.getenv("FAKE_IGNORE_SIGINT")) else on_int)
        signal.signal(signal.SIGTERM, signal.SIG_IGN if truthy(self.getenv("FAKE_IGNORE_SIGTERM")) else on_term)

    def _log_exit(self, code, sig=None):
        if self.rec is None or code is None or self._exit_logged:
            return
        self._exit_logged = True
        with self.state.locked():
            self.state.append("exits.jsonl", {"n": self.rec["n"], "cli": self.cli, "exit": code, "t_end": time.time(), "signal": sig})

    # ---- the call log
    def _env_keys(self):
        keys = set(self.env) - SHELL_ARTEFACTS
        if "LANG" not in self.env and "LC_ALL" not in self.env:
            keys.discard("LC_CTYPE")                             # Python sets it itself in the C locale
        return sorted(keys)

    def _file_records(self):
        out = {}
        for flag in FILE_FLAGS:
            for value in self.opts.get(flag, ()):
                if value is True or value == "":
                    continue
                if flag == "--mcp-config" and value.lstrip().startswith(("{", "[")):
                    out.setdefault(flag, []).append({"inline": True, "content": value})
                    continue
                rec = {"path": value, "exists": os.path.exists(value)}
                if rec["exists"]:
                    st = os.stat(value)
                    rec["mode"] = "%04o" % (st.st_mode & 0o7777)
                    rec["size"] = st.st_size
                    if flag != "--image" and st.st_size <= 1000000:
                        try:
                            with open(value, encoding="utf-8") as f:
                                rec["content"] = f.read()
                        except (OSError, UnicodeDecodeError):
                            pass
                out.setdefault(flag, []).append(rec)
        return out

    def _cwd_entries(self):
        try:
            return sorted(os.listdir(self.cwd))[:50]
        except OSError:
            return None

    def _record(self, kind, op, stdin_text=None, stdin_complete=None, **extra):
        rec = {"n": 0, "cli": self.cli, "kind": kind, "op": op, "argv": list(self.argv), "cwd": self.cwd, "cwd_entries": self._cwd_entries(),
               "stdin": stdin_text, "stdin_complete": stdin_complete, "env_keys": self._env_keys(), "scenario": None, "session_id": None,
               "pid": os.getpid(), "t_start": self.t_start}
        rec.update(extra)
        wanted = self.getenv("FAKE_LOG_ENV")
        if wanted:
            rec["env_values"] = {k: self.env[k] for k in wanted.split(",") if k in self.env}
        files = self._file_records()
        if files:
            rec["files"] = files
        return rec

    def _probe(self, op, **extra):
        """Log a status, help or version command: it does not consume the sequence."""
        self.rec = self._record("probe", op, **extra)
        with self.state.locked():
            self.rec["n"] = self.state.bump("n")
            self.state.append("calls.jsonl", self.rec)

    # ---- input
    def read_stdin(self):
        """-> (bytes, reached EOF). Waits at most FAKE_STDIN_TIMEOUT, so a caller that forgets to close stdin cannot hang a suite."""
        if self._stdin is not None:
            return self._stdin, True
        timeout = self.number("FAKE_STDIN_TIMEOUT", 5.0)
        try:
            fd = sys.stdin.fileno()
            if os.isatty(fd):
                return b"", True
        except (OSError, ValueError, AttributeError):
            return b"", True
        chunks, deadline = [], time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return b"".join(chunks), False
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                return b"".join(chunks), False
            try:
                data = os.read(fd, 1 << 20)
            except OSError:
                return b"".join(chunks), True
            if not data:
                return b"".join(chunks), True
            chunks.append(data)

    # ---- shared helpers
    def _dispatch(self):
        return {"claude": self._claude, "codex": self._codex, "gh": self._gh}[self.cli]()

    def auth_mode(self, cli):
        saved = self.state.read("auth.json", {})
        if cli in saved:
            return saved[cli]
        if truthy(self.getenv("FAKE_AUTH_FROM_CONFIG")) and cli in ("claude", "codex"):
            home = self.getenv("CLAUDE_CONFIG_DIR" if cli == "claude" else "CODEX_HOME")
            return "signed_in" if home and (Path(home) / "fake-login").exists() else "signed_out"
        mode = self.getenv("FAKE_%s_AUTH" % cli.upper(), "signed_in")
        if mode not in AUTH_MODES[cli]:
            raise FakeError("FAKE_%s_AUTH=%r; use one of %s" % (cli.upper(), mode, ", ".join(AUTH_MODES[cli])))
        return mode

    def help_text(self, text):
        for flag in filter(None, (f.strip() for f in (self.getenv("FAKE_HELP_MISSING") or "").split(","))):
            text = drop_help_option(text, flag)
        return text

    # ------------------------------------------------------------------------------------------ claude
    def _claude(self):
        self.opts, self.pos = parse_argv(self.argv, CLAUDE_SHORT, CLAUDE_VALUE, CLAUDE_VARIADIC, CLAUDE_OPTIONAL)
        if "--version" in self.opts:
            self._probe("version")
            version = self.getenv("FAKE_CLAUDE_VERSION")
            self.out(("%s (Claude Code)\n" % version) if version else fixture_text("handwritten/claude_version.txt"))
            return 0
        if "--help" in self.opts or not self.argv:
            self._probe("help")
            self.out(self.help_text(fixture_text("claude/help.txt")))
            return 0
        if "--print" in self.opts:
            return self._claude_print()
        pos = self.pos
        if pos[:2] == ["auth", "status"]:
            self._probe("auth_status")
            return self._claude_auth_status()
        if pos[:2] == ["mcp", "list"]:
            self._probe("mcp_list")
            names = {"present": "claude_mcp_list", "local": "claude_mcp_list_local", "empty": "claude_mcp_list_empty"}
            kind = self.getenv("FAKE_CLAUDE_MCP", "present")
            if kind not in names:
                raise FakeError("FAKE_CLAUDE_MCP=%r; use present, local or empty" % kind)
            self.out(fixture_text("handwritten/%s.txt" % names[kind]))
            return 0
        if pos[:1] == ["purge"]:
            self._probe("purge")
            return 0
        self._probe("other")
        self.err("fake claude: unsupported command %s (the fake serves -p, auth status, mcp list, purge, --help, --version)\n" % " ".join(self.argv))
        return 2

    def _claude_auth_status(self):
        mode = self.auth_mode("claude")
        if mode == "signed_out":
            self.out(fixture_text("claude/auth_status_signed_out.json"))
            return 1
        if mode == "error":
            self.err("Error: could not read the credentials\n")
            return 2
        if mode in ("api_key", "console"):
            doc = fixture_json("claude/auth_status_signed_in.json")
            doc["authMethod"] = mode
            for key in ("email", "orgId", "orgName", "subscriptionType"):
                doc.pop(key, None)
            self.out(json.dumps(doc, indent=2) + "\n")
        else:
            self.out(fixture_text("claude/auth_status_signed_in.json"))
        return 0

    def _claude_print(self):
        opts = self.opts
        out_format = last(opts, "--output-format", "text")
        if out_format not in ("text", "json", "stream-json"):
            self._probe("print")
            self.err("error: option '--output-format <format>' argument '%s' is invalid. Allowed choices are text, json, stream-json.\n" % out_format)
            return 1
        stdin, complete = self.read_stdin()
        self.stdin_bytes = stdin
        self.rec = self._record("call", "print", stdin.decode("utf-8", "replace"), complete)
        problem = None
        schema = last(opts, "--json-schema")
        if out_format == "stream-json" and "--verbose" not in opts:
            problem = "Error: When using --print, --output-format=stream-json requires --verbose\n"       # UNVERIFIED wording, real rule
        elif schema is not None:
            try:
                json.loads(schema)
            except ValueError as e:
                problem = "Error: --json-schema is not valid JSON: JSON Parse error: %s\n" % e
        spf = last(opts, "--system-prompt-file")
        if problem is None and spf is not None and not os.path.isfile(spf):
            problem = "Error: System prompt file not found: %s\n" % spf
        effort = last(opts, "--effort")
        if problem is None and isinstance(effort, str) and effort not in CLAUDE_EFFORTS:
            self.err("Warning: Unknown --effort value '%s' — ignoring it and using the default effort. Valid values: low, medium, high, xhigh, max.\n" % effort)
        sid = last(opts, "--session-id") or last(opts, "--resume") or None
        stream = self._planned(problem, 1, schema is not None, sid)
        return self._emit_claude(stream, out_format)

    def _planned(self, problem, problem_exit, has_schema, sid):
        """Under the state lock: number the call, pick and build the scenario, write the call record."""
        with self.state.locked():
            self.rec["n"] = self.state.bump("n")
            try:
                if problem:
                    self.rec["scenario"] = "(argument error)"
                    return Stream([], problem_exit, problem)
                return self._plan_stream(has_schema, sid)
            except FakeError as e:
                self.rec["error"] = str(e)
                raise
            finally:
                self.state.append("calls.jsonl", self.rec)

    def _plan_stream(self, has_schema, sid):
        name = self._next_scenario() or "ok"
        if name == "ok" and self.auth_mode(self.cli) == "signed_out":
            name = "not_logged_in" if self.cli == "claude" else "not_signed_in"
        self.rec["scenario"] = name
        if name.startswith("file:"):
            path = name[5:]
            if not os.path.isabs(path):
                raise FakeError("file: scenarios need an absolute path, got %r" % path)
            scn = Scn(file=path, external=True, replyable=False)
        else:
            scn = resolve(self.cli, name, has_schema)
        return self._build_claude(scn, sid) if self.cli == "claude" else self._build_codex(scn, sid)

    def _next_scenario(self):
        per_cli = self.getenv("FAKE_%s_SEQUENCE" % self.cli.upper())
        spec, key = (per_cli, "seq:" + self.cli) if per_cli else (self.getenv("FAKE_CLI_SEQUENCE"), "seq:shared")
        seq = parse_sequence(spec)
        if not seq:
            return None
        if len(seq) > 1 and self.state.dir is None:
            raise FakeError("a sequence of several scenarios needs FAKE_CLI_STATE to count the calls")
        index = max(0, self.state.bump(key) - 1)
        return seq[min(index, len(seq) - 1)]

    # ---- building a stream
    def _scenario_lines(self, scn):
        """-> (lines, stderr template, exit code of the probe or None): the scenario's lines before any per-call rewriting."""
        lines = parse_lines(Path(scn.file).read_text(encoding="utf-8")) if scn.external else load_lines(scn.file) if scn.file else []
        stderr, probe_exit = "", None
        if scn.probe:
            probe = next(p for p in fixture_json("cli_errors.json")["probes"] if p["id"] == scn.probe)
            stderr, probe_exit = probe.get("stderr", ""), probe.get("exit")
            if not scn.file and probe.get("stdout"):
                lines = parse_lines(probe["stdout"])
        lines = apply_patch(lines, scn.patch, "scenario")
        if scn.noise:
            lines = lines[:1] + list(NOISE_LINES) + lines[1:]
        return lines, stderr, probe_exit

    def _stderr_text(self, template, new_id):
        flag = self.getenv("FAKE_BAD_FLAG") or next((o for o in self.opts if o.startswith("--") and o not in ("--print", "--verbose")), None) or "--no-such-flag"
        path = (self.opts.get("--output-schema") or self.opts.get("--system-prompt-file") or ["<file>"])[0]
        return template.replace("--no-such-flag", flag).replace("<file>", str(path)).replace("<path>", str(path)).replace("<id>", str(new_id or "<id>"))

    def _reply_values(self):
        obj = self.json_env("FAKE_REPLY_JSON")
        text = self.getenv("FAKE_REPLY_TEXT")
        if text is None and obj is not None:
            text = compact(obj)
        return text, obj

    def _implied_exit(self, lines):
        dicts = [l for l in lines if isinstance(l, dict)]
        if self.cli == "claude":
            results = [l for l in dicts if l.get("type") == "result"]
            return (1 if results[-1].get("is_error") else 0) if results else EXIT_CRASH
        types = [l.get("type") for l in dicts]
        return 1 if "turn.failed" in types else 0 if "turn.completed" in types else EXIT_CRASH

    def _finish(self, lines, scn, stderr, probe_exit, new_id):
        patch = self.json_env("FAKE_PATCH", list)
        if patch:
            lines = apply_patch(lines, patch, "FAKE_PATCH")
        forced = self.number("FAKE_EXIT_CODE", None)
        if forced is not None:
            code = int(forced)
        elif scn.exit is not None:
            code = int(scn.exit)
        elif probe_exit is not None:
            code = int(probe_exit)
        else:
            code = self._implied_exit(lines)
        delay = self.number("FAKE_LINE_DELAY", scn.delay or 0.0)
        return Stream(lines, code, self._stderr_text(stderr, new_id), delay, scn.free or 0, scn.hang_after)

    def _session(self, new_id):
        sessions = self.state.read("sessions.json", {})
        return sessions, sessions.get("%s:%s" % (self.cli, new_id), {})

    def _build_claude(self, scn, sid):
        lines, stderr, probe_exit = self._scenario_lines(scn)
        new_id = sid or "00000000-0000-4000-8000-%012d" % self.rec["n"]
        self.rec["session_id"] = new_id
        lines = rewrite_ids(lines, "session_id", new_id)
        version = self.getenv("FAKE_CLAUDE_VERSION")
        if version:
            lines = [dict(l, claude_code_version=version) if isinstance(l, dict) and l.get("subtype") == "init" else l for l in lines]
        model = last(self.opts, "--model")
        full = MODEL_ALIASES.get(model) or (model if isinstance(model, str) and model.startswith("claude-") else None)
        if full:
            rename_model(lines, full)
        if scn.replyable:
            text, obj = self._reply_values()
            replace_claude_reply(lines, text, obj)
        sessions, prior = self._session(new_id)
        follows = None if scn.external else recorded_after(scn.file) if scn.file else None
        sessions["claude:%s" % new_id] = account_claude(lines, prior, follows, self.number("FAKE_COST_USD", None), self.json_env("FAKE_USAGE", dict))
        self.state.write("sessions.json", sessions)
        if scn.interrupt:
            answer_interrupt(lines, self.stdin_bytes)
        lines = adjust_partials(lines, "--include-partial-messages" in self.opts, new_id)
        return self._finish(lines, scn, stderr, probe_exit, new_id)

    def _build_codex(self, scn, sid):
        lines, stderr, probe_exit = self._scenario_lines(scn)
        new_id = sid or "00000000-0000-7000-8000-%012d" % self.rec["n"]
        self.rec["session_id"] = new_id
        lines = rewrite_ids(lines, "thread_id", new_id)
        if scn.replyable:
            text, _ = self._reply_values()
            if text is not None:
                replace_codex_reply(lines, text)
        sessions, prior = self._session(new_id)
        follows = None if scn.external else recorded_after(scn.file) if scn.file else None
        state, turn = account_codex(lines, prior, follows, self.json_env("FAKE_USAGE", dict))
        sessions["codex:%s" % new_id] = state
        self.state.write("sessions.json", sessions)
        if turn is not None and "--ephemeral" not in self.opts:
            self.rec["rollout"] = self._write_rollout(new_id, state["usage"], turn)
        return self._finish(lines, scn, stderr, probe_exit, new_id)

    def _emit_claude(self, stream, out_format):
        if out_format == "stream-json" or not stream.lines:
            return self._emit(stream)
        results = [l for l in stream.lines if isinstance(l, dict) and l.get("type") == "result"]
        if results:
            self.out((compact(results[-1]) if out_format == "json" else str(results[-1].get("result", ""))) + "\n")
        if stream.stderr:
            self.err(stream.stderr)
        return stream.exit

    def _emit(self, stream):
        deadline = time.time() + self.number("FAKE_MAX_SECONDS", DEFAULT_MAX_SECONDS)
        for i, item in enumerate(stream.lines):
            if stream.hang_after is not None and i >= stream.hang_after:
                break
            if stream.delay and i >= stream.free:
                time.sleep(stream.delay)
            self.out(dump_line(item) + "\n")
            if time.time() > deadline:
                return EXIT_TIMEOUT
        if stream.hang_after is not None and stream.hang_after < len(stream.lines):
            while time.time() < deadline:
                time.sleep(0.05)
            return EXIT_TIMEOUT
        if stream.stderr:
            self.err(stream.stderr)
        return stream.exit

    # ------------------------------------------------------------------------------------------ codex
    def _codex(self):
        self.opts, self.pos = parse_argv(self.argv, CODEX_SHORT, CODEX_VALUE)
        opts, pos = self.opts, self.pos
        if "--version" in opts and not pos:
            self._probe("version")
            version = self.getenv("FAKE_CODEX_VERSION")
            self.out(("codex-cli %s\n" % version) if version else fixture_text("handwritten/codex_version.txt"))
            return 0
        if "--help" in opts or pos[:1] == ["help"] or not self.argv:
            self._probe("help")
            rel = ("codex/exec_resume_help.txt" if pos[:2] == ["exec", "resume"] else "codex/exec_help.txt" if pos[:1] == ["exec"]
                   else "handwritten/codex_help.txt")
            self.out(self.help_text(fixture_text(rel)))
            return 0
        if pos[:2] == ["login", "status"]:
            self._probe("login_status")
            return self._codex_login_status()
        if pos[:1] == ["login"] and "--device-auth" in opts:
            self._probe("device_auth")
            return self._codex_device_auth()
        if pos[:2] == ["debug", "models"]:
            self._probe("models")
            self.out(fixture_text("codex/models_excerpt.json"))
            return 0
        if pos[:2] == ["mcp", "list"]:
            self._probe("mcp_list")
            self.out("[]\n" if "--json" in opts else "No MCP servers configured yet. Try `codex mcp add my-tool -- my-command`.\n")
            return 0
        if pos[:1] == ["delete"]:
            self._probe("delete")
            return 0
        if pos[:1] == ["exec"]:
            return self._codex_exec(resume=pos[1:2] == ["resume"])
        self._probe("other")
        self.err("fake codex: unsupported command %s (the fake serves exec, exec resume, login status, login --device-auth, debug models, "
                 "mcp list, delete, --help, --version)\n" % " ".join(self.argv))
        return 2

    def _codex_login_status(self):
        mode = self.auth_mode("codex")
        if mode == "signed_out":
            self.err("Not logged in\n")
            return 1
        if mode == "error":
            self.err("Error: could not read auth.json\n")
            return 2
        self.err("Logged in using ChatGPT\n" if mode == "signed_in" else "Logged in using an API key - sk-proj-***FAKE\n")   # api_key wording UNVERIFIED
        return 0

    def _codex_device_auth(self):
        self.out(fixture_text("codex/login_device_auth.txt"))
        started = time.time()
        auto = self.number("FAKE_DEVICE_AUTH_SECONDS", None)
        limit = self.number("FAKE_MAX_SECONDS", DEFAULT_MAX_SECONDS)
        approve = (self.state.dir / "device_auth_approve") if self.state.dir else None
        while time.time() - started < limit:
            if (approve is not None and approve.exists()) or (auto is not None and time.time() - started >= auto):
                with self.state.locked():
                    saved = self.state.read("auth.json", {})
                    saved["codex"] = "signed_in"
                    self.state.write("auth.json", saved)
                self.out("Successfully logged in\n")
                return 0
            time.sleep(0.05)
        return EXIT_TIMEOUT

    def _codex_exec(self, resume):
        opts, pos = self.opts, self.pos
        bad, bad_exit = None, 1
        if resume:                                                  # `exec resume` takes no -s and no -C (cli_errors.json verified_flags)
            for flag, shown in (("--sandbox", "-s"), ("--cd", "-C")):
                if flag in opts:
                    bad, bad_exit = "error: unexpected argument '%s' found\n\nUsage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]\n\nFor more information, try '--help'.\n" % shown, 2
                    break
        sandbox = last(opts, "--sandbox")
        if bad is None and isinstance(sandbox, str) and sandbox not in CODEX_SANDBOXES:
            bad, bad_exit = "error: invalid value '%s' for '--sandbox <SANDBOX_MODE>'\n" % sandbox, 2
        schema = last(opts, "--output-schema")
        if bad is None and schema is not None:
            try:
                with open(schema, encoding="utf-8") as f:
                    json.loads(f.read())
            except FileNotFoundError:
                bad = "Reading additional input from stdin...\nFailed to read output schema file %s: No such file or directory (os error 2)\n" % schema
            except ValueError as e:
                bad = "Reading additional input from stdin...\nOutput schema file %s is not valid JSON: %s\n" % (schema, e)
        cd = last(opts, "--cd")
        if bad is None and isinstance(cd, str) and not os.path.isdir(cd):
            bad = "Error: No such file or directory (os error 2)\n"
        stdin, complete = self.read_stdin()
        self.stdin_bytes = stdin
        self.rec = self._record("call", "exec_resume" if resume else "exec", stdin.decode("utf-8", "replace"), complete)
        rest = [p for p in pos[2:] if p != "-"] if resume else []
        stream = self._planned(bad, bad_exit, schema is not None, rest[0] if rest else None)
        return self._emit(stream)

    def _write_rollout(self, thread_id, total, turn):
        """The token_count line Codex adds to the thread's rollout file after a turn (the connector reads the quota from it)."""
        mode = self.getenv("FAKE_CODEX_ROLLOUT", "on")
        if mode == "off":
            return "off"
        root = self.getenv("CODEX_HOME") or (str(self.state.dir / "codex_home") if self.state.dir else None)
        if root is None:
            return "skipped: no CODEX_HOME and no state directory"
        if os.path.realpath(root) == os.path.realpath(os.path.expanduser("~/.codex")):
            return "skipped: CODEX_HOME is the real ~/.codex"      # a test must never add files to the owner's Codex history
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)
        existing = sorted(Path(root).glob("sessions/*/*/*/rollout-*-%s.jsonl" % thread_id))
        path = existing[0] if existing else Path(root) / "sessions" / now.strftime("%Y/%m/%d") / ("rollout-%s-%s.jsonl" % (now.strftime("%Y-%m-%dT%H-%M-%S"), thread_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if not existing:                                                    # a rollout file holds more than token counts: a reader must pick them out
            lines.append({"timestamp": stamp, "type": "session_meta", "payload": {"id": thread_id, "originator": "codex_exec", "cli_version": "0.146.0"}})
        if mode == "bad":
            lines = ["this is not json"]
        else:
            lines.append({"timestamp": stamp, "type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}})
            sample = parse_lines(fixture_text("codex/rollout_token_count.jsonl"))[0]
            info = sample["payload"]["info"]
            info["total_token_usage"] = dict(total, total_tokens=total["input_tokens"] + total["output_tokens"])
            info["last_token_usage"] = dict(turn, total_tokens=turn["input_tokens"] + turn["output_tokens"])
            sample["timestamp"] = stamp
            lines.append(sample)
        with open(str(path), "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(dump_line(line) + "\n")
        return str(path)

    # ------------------------------------------------------------------------------------------ gh
    def _gh(self):
        opts, pos = parse_argv(self.argv, GH_SHORT, GH_VALUE)
        self.opts, self.pos = opts, pos
        if "--version" in opts:
            self._probe("version")
            self.out(fixture_text("handwritten/gh/version.txt"))
            return 0
        if pos[:2] == ["auth", "status"]:
            self._probe("auth_status")
            if self.auth_mode("gh") == "signed_out":
                self.err(fixture_text("handwritten/gh/auth_status_signed_out.txt"))
                return 1
            self.out(fixture_text("handwritten/gh/auth_status_signed_in.txt"))
            return 0
        if pos[:2] == ["auth", "token"]:
            self._probe("auth_token")
            self.out("gho_FAKE_TOKEN_DO_NOT_USE_0000000000000000\n")            # a recognisable value: tests assert it never leaks
            return 0
        if pos[:1] == ["api"]:
            return self._gh_api()
        self._probe("other")
        self.err("fake gh: unsupported command %s (the fake serves api, auth status, auth token, --version)\n" % " ".join(self.argv))
        return 2

    def _gh_api(self):
        opts, pos = self.opts, self.pos
        endpoint = pos[1] if len(pos) > 1 else ""
        fields = opts.get("--raw-field", []) + opts.get("--field", [])
        method = (last(opts, "--method") or ("POST" if fields else "GET")).upper()      # gh turns -f/-F fields into a POST unless -X says GET
        self._probe("api", method=method, endpoint=endpoint)
        for name in ("--jq", "--template", "--input"):
            if name in opts:
                self.err("fake gh: %s is not supported by the fake\n" % name)
                return 2
        if method != "GET":
            self.err("fake gh: only GET is served (read-only); got %s\n" % method)
            return 1
        if self.auth_mode("gh") == "signed_out":
            self.err(fixture_text("handwritten/gh/auth_required.txt"))
            return 4
        failures = fixture_json("handwritten/gh/errors.json")
        fail = self.getenv("FAKE_GH_FAIL")
        if fail:
            if fail not in failures:
                raise FakeError("FAKE_GH_FAIL=%r; use one of %s" % (fail, ", ".join(sorted(failures))))
            return self._gh_fail(failures[fail])
        split = urlsplit("/" + endpoint.lstrip("/"))
        query = dict(parse_qsl(split.query))
        for field in fields:
            key, _, val = field.partition("=")
            query[key] = val
        repos = [r.strip() for r in (self.getenv("FAKE_GH_REPOS") or "octo-org/hello-world").split(",") if r.strip()]
        raw = "raw" in " ".join(opts.get("--header", [])).lower()
        status, body = gh_route(unquote(split.path.strip("/")), query, raw, repos, int(self.number("FAKE_GH_BIG_BYTES", 60000)))
        if status != 200:
            return self._gh_fail(failures["not_found"])
        self.out(body if isinstance(body, str) else compact(body) + "\n")
        return 0

    def _gh_fail(self, failure):
        if failure["body"] is not None:
            self.out(compact(failure["body"]) + "\n")
        self.err(failure["stderr"])
        return 1


# ------------------------------------------------------------------------------------------------ stream rewriting
def rewrite_ids(lines, key, new_id):
    """Every `key` value (session_id, thread_id) becomes new_id; the old ids inside other strings follow."""
    old = set()

    def collect(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key and isinstance(v, str):
                    if v:
                        old.add(v)
                else:
                    collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)

    for line in lines:
        collect(line)

    def fix(obj):
        if isinstance(obj, dict):
            return {k: (new_id if k == key and isinstance(v, str) else fix(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fix(v) for v in obj]
        if isinstance(obj, str):
            for o in old:
                obj = obj.replace(o, new_id)
        return obj

    return [fix(l) if isinstance(l, dict) else l for l in lines]


def rename_model(lines, full):
    for line in lines:
        if not isinstance(line, dict):
            continue
        if line.get("subtype") == "init" and "model" in line:
            line["model"] = full
        msg = line.get("message")
        if isinstance(msg, dict) and msg.get("model") not in (None, "<synthetic>"):
            msg["model"] = full
        usage = line.get("modelUsage")
        if isinstance(usage, dict) and usage:
            first = next(iter(usage))
            if first != full:
                line["modelUsage"] = {(full if k == first else k): v for k, v in usage.items()}


def replace_claude_reply(lines, text, obj):
    """FAKE_REPLY_*: `text` fills the text fields, `obj` the structured ones."""
    if text is None and obj is None:
        return
    deltas = []
    for item in lines:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "assistant":
            for block in (item.get("message") or {}).get("content", []):
                if block.get("type") == "text" and text is not None:
                    block["text"] = text
                elif block.get("type") == "tool_use" and block.get("name") == "StructuredOutput" and obj is not None:
                    block["input"] = copy.deepcopy(obj)
            if isinstance(item.get("wire_tool_inputs"), dict) and obj is not None:
                item["wire_tool_inputs"] = {k: copy.deepcopy(obj) for k in item["wire_tool_inputs"]}
        elif kind == "stream_event":
            delta = (item.get("event") or {}).get("delta") or {}
            if delta.get("type") == "input_json_delta":
                deltas.append(delta)
        elif kind == "result":
            if "result" in item and text is not None:
                item["result"] = text
            if "structured_output" in item and obj is not None:
                item["structured_output"] = copy.deepcopy(obj)
    if deltas and obj is not None:
        if len(deltas) == 1:
            deltas[0]["partial_json"] = compact(obj)
        else:                                                       # the captured stream opens with an empty delta, then the JSON in pieces
            pieces = split_even(compact(obj), len(deltas) - 1)
            for i, delta in enumerate(deltas):
                delta["partial_json"] = pieces[i - 1] if 0 < i <= len(pieces) else ""


def replace_codex_reply(lines, text):
    target = None
    for item in lines:
        if isinstance(item, dict) and item.get("type") == "item.completed" and (item.get("item") or {}).get("type") == "agent_message":
            target = item
    if target is not None:
        target["item"]["text"] = text


def _tokens(obj, keys):
    return {k: int((obj or {}).get(k, 0) or 0) for k in keys}


def _first_of_type(rel, kind):
    for item in load_lines(rel):
        if isinstance(item, dict) and item.get("type") == kind:
            return item
    return {}


def account_claude(lines, prior, follows, env_cost, env_usage):
    """Make the result line cumulative for the session. `prior` is the session's state before this call; returns the state after."""
    results = [l for l in lines if isinstance(l, dict) and l.get("type") == "result"]
    if not results:
        return prior
    res = results[-1]
    recorded = float(res.get("total_cost_usd") or 0.0)
    base = float(_first_of_type(follows, "result").get("total_cost_usd") or 0.0) if follows else 0.0
    turn_cost = env_cost if env_cost is not None else max(0.0, recorded - base)
    cost = round(float(prior.get("cost", 0.0)) + turn_cost, 12)
    usage = res.setdefault("usage", {})
    if env_usage is not None:
        for key in USAGE_KEYS:
            usage[key] = int(env_usage.get(key, 0))
        for iteration in usage.get("iterations") or ():
            for key in USAGE_KEYS:
                iteration[key] = usage[key]
        for item in lines:
            msg = item.get("message") if isinstance(item, dict) else None
            if isinstance(msg, dict) and isinstance(msg.get("usage"), dict) and msg.get("model") != "<synthetic>":
                for key in USAGE_KEYS:
                    msg["usage"][key] = usage[key]
    turn = _tokens(usage, USAGE_KEYS)
    tokens = {k: int((prior.get("tokens") or {}).get(k, 0)) + turn[k] for k in USAGE_KEYS}
    res["total_cost_usd"] = cost
    for entry in (res.get("modelUsage") or {}).values():
        for key in USAGE_KEYS:
            entry[MODEL_USAGE_KEYS[key]] = tokens[key]
        entry["costUSD"] = cost
    return {"turns": int(prior.get("turns", 0)) + 1, "cost": cost, "tokens": tokens}


def account_codex(lines, prior, follows, env_usage):
    """Make turn.completed.usage cumulative for the thread. -> (state after, this turn's usage, or None when the turn did not complete)."""
    done = [l for l in lines if isinstance(l, dict) and l.get("type") == "turn.completed"]
    if not done:
        return prior, None
    event = done[-1]
    recorded = _tokens(event.get("usage"), CODEX_USAGE_KEYS)
    if env_usage is not None:
        turn = _tokens(env_usage, CODEX_USAGE_KEYS)
    elif follows:
        base = _tokens(_first_of_type(follows, "turn.completed").get("usage"), CODEX_USAGE_KEYS)
        turn = {k: max(0, recorded[k] - base[k]) for k in CODEX_USAGE_KEYS}
    else:
        turn = recorded
    before = _tokens(prior.get("usage"), CODEX_USAGE_KEYS)
    total = {k: before[k] + turn[k] for k in CODEX_USAGE_KEYS}
    event["usage"] = dict(total)
    return {"turns": int(prior.get("turns", 0)) + 1, "usage": total}, turn


def answer_interrupt(lines, stdin):
    """The control_response echoes the request_id of the control_request on stdin."""
    rid = None
    for raw in stdin.decode("utf-8", "replace").splitlines():
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        if isinstance(msg, dict) and msg.get("type") == "control_request":
            rid = msg.get("request_id")
    if rid is not None:
        for item in lines:
            if isinstance(item, dict) and item.get("type") == "control_response":
                item["response"]["request_id"] = rid


def adjust_partials(lines, partials, sid):
    """Without --include-partial-messages the CLI prints no stream_event lines. With it, a plain reply gets the kind of events the
    captured structured stream has (synthesised: only the structured stream was captured)."""
    if not partials:
        return [l for l in lines if not (isinstance(l, dict) and l.get("type") == "stream_event")]
    if any(isinstance(l, dict) and l.get("type") == "stream_event" for l in lines):
        return lines
    for i, item in enumerate(lines):
        if not (isinstance(item, dict) and item.get("type") == "assistant"):
            continue
        msg = item.get("message") or {}
        blocks = [b for b in msg.get("content", []) if b.get("type") == "text"]
        if msg.get("model") == "<synthetic>" or not blocks:
            continue

        def event(kind, n, **fields):
            seed = ("%s/%s/%d" % (sid, kind, n)).encode()
            return {"type": "stream_event", "event": dict({"type": kind}, **fields), "session_id": sid, "parent_tool_use_id": None,
                    "uuid": str(uuid.UUID(bytes=hashlib.md5(seed).digest())), "api_message_id": msg.get("id")}

        head = [event("message_start", 0, message={"model": msg.get("model"), "id": msg.get("id"), "type": "message", "role": "assistant",
                                                    "content": [], "stop_reason": None, "usage": msg.get("usage", {})}),
                event("content_block_start", 0, index=0, content_block={"type": "text", "text": ""})]
        head += [event("content_block_delta", n + 1, index=0, delta={"type": "text_delta", "text": piece}) for n, piece in enumerate(split_even(blocks[0].get("text", ""), 3))]
        tail = [event("content_block_stop", 0, index=0),
                event("message_delta", 0, delta={"stop_reason": "end_turn", "stop_sequence": None}, usage={"output_tokens": (msg.get("usage") or {}).get("output_tokens", 0)}),
                event("message_stop", 0)]
        return lines[:i] + head + [item] + tail + lines[i + 1:]
    return lines


def drop_help_option(text, flag):
    """Remove the option block that starts with `flag` from a --help text: its line, its deeper-indented lines and the blank lines after."""
    pattern = re.compile(r"^(\s*)(-\w, )?(--[\w-]+, )*%s(?![\w-])" % re.escape(flag))
    out, skipping, indent = [], False, 0
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        depth = len(line) - len(stripped)
        if skipping:
            if stripped == "" or depth > indent:
                continue
            skipping = False
        m = pattern.match(line)
        if m:
            skipping, indent = True, len(m.group(1))
            continue
        out.append(line)
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ gh routes
def _wrap60(data):
    text = base64.b64encode(data).decode("ascii")
    return "\n".join(text[i:i + 60] for i in range(0, len(text), 60)) + "\n"      # GitHub breaks the base64 content every 60 characters


def gh_route(path, query, raw, repos, big_bytes):
    """-> (http status, body). The body is a JSON-able object, or text for a raw file."""
    parts = path.split("/")
    if len(parts) < 3 or parts[0] != "repos":
        return 404, None
    owner, repo, rest = parts[1], parts[2], parts[3:]
    if ("%s/%s" % (owner, repo)).lower() not in [r.lower() for r in repos]:
        return 404, None

    def fill(obj):
        return json.loads(json.dumps(obj).replace("__OWNER__", owner).replace("__REPO__", repo))

    if not rest:
        return 200, fill(fixture_json("handwritten/gh/repo.json"))
    if rest[0] in ("pulls", "issues") and len(rest) == 1:
        state = query.get("state", "open")
        items = [i for i in fill(fixture_json("handwritten/gh/%s.json" % rest[0])) if state == "all" or i["state"] == state]
        per_page, page = int(query.get("per_page", 30)), int(query.get("page", 1))
        return 200, items[(page - 1) * per_page:page * per_page]
    if rest[0] in ("pulls", "issues") and len(rest) == 2 and rest[1].isdigit():
        found = [i for i in fill(fixture_json("handwritten/gh/%s.json" % rest[0])) if i["number"] == int(rest[1])]
        return (200, found[0]) if found else (404, None)
    if rest[0] == "contents":
        return _gh_contents("/".join(rest[1:]), query.get("ref", "main"), raw, owner, repo, big_bytes, fill)
    return 404, None


def _gh_contents(path, ref, raw, owner, repo, big_bytes, fill):
    files = fill(fixture_json("handwritten/gh/files.json"))
    files["big.txt"] = "".join("line %06d of the big fixture file\n" % i for i in range(big_bytes // 36 + 1))[:big_bytes]
    if path in files:
        if raw:
            return 200, files[path]
        data = files[path].encode("utf-8")
        base = "https://api.github.com/repos/%s/%s/contents/%s" % (owner, repo, path)
        return 200, {"type": "file", "encoding": "base64", "size": len(data), "name": path.rsplit("/", 1)[-1], "path": path,
                     "content": _wrap60(data), "sha": hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), "url": base + "?ref=" + ref,
                     "html_url": "https://github.com/%s/%s/blob/%s/%s" % (owner, repo, ref, path),
                     "download_url": "https://raw.githubusercontent.com/%s/%s/%s/%s" % (owner, repo, ref, path)}
    prefix = path.strip("/") + "/" if path.strip("/") else ""
    names = {}
    for name in files:
        if name.startswith(prefix):
            head, sep, _ = name[len(prefix):].partition("/")
            names[head] = "dir" if sep else "file"
    if not names:
        return 404, None
    return 200, [{"type": kind, "name": n, "path": prefix + n, "size": len(files.get(prefix + n, ""))} for n, kind in sorted(names.items())]


# ------------------------------------------------------------------------------------------------ entry point
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--scenarios" and argv[1] in ("claude", "codex"):
        sys.stdout.write("\n".join(scenario_names(argv[1])) + "\n")
        return 0
    if not argv or argv[0] not in CLIS:
        sys.stderr.write("usage: fake_cli.py claude|codex|gh [ARGS...]   or   fake_cli.py --scenarios claude|codex\n")
        return 2
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="surrogateescape")
    code = Run(argv[0], argv[1:], handle_signals=True).run()
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return code


if __name__ == "__main__":
    sys.exit(main())
