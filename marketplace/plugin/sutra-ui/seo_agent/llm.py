"""llm.py — the one place a model gets called.

Everything else in the app talks to this file, so swapping provider is a change
here and nowhere else. The person picks a provider and model (store.model_choice),
the same three the Sutra chat offers:

    claude-cli   the `claude` binary on this machine, billed to the user's Claude
                 subscription. The default, and the fallback whenever the chosen
                 provider cannot run. SEO_AGENT_NO_CLI=1 switches it off.
    codex-cli    the `codex` binary, signed in to the person's OpenAI account.
    deepseek     DeepSeek's API, with the key the person saved for DeepSeek chat.

and two legacy API providers, used only when no CLI is there:

    anthropic    the API, when an anthropic_key is saved in Connections.
    openai       the API, when an openai_key is saved in Connections.

Tool calling is normalised: whatever the provider returns comes back as a plain
list of {id, name, input}, and tool results go back as a plain list. Nothing
above this file knows which provider answered.
"""
import json
import os
import shutil
import signal
import subprocess
import time
import uuid

import httpx

from . import store

ANTHROPIC_MODEL = "claude-sonnet-5"
OPENAI_MODEL = "gpt-4o"
TIMEOUT = 180.0
CLI_TIMEOUT = 300.0          # one CLI call is a whole model turn; a long section needs room
RESULT_CAP = 20000           # chars of one tool result the flattened CLI prompt keeps


class NoKey(Exception):
    pass


def _keys():
    c = store.connections()
    return (c.get("anthropic_key", "").strip(), c.get("openai_key", "").strip())


def cli_bin():
    """Path to the claude binary, or None when there is none or it is switched off.

    SEO_AGENT_CLAUDE_BIN names the binary explicitly; otherwise it is whatever `claude`
    resolves to on PATH. SEO_AGENT_NO_CLI=1 disables it regardless.
    """
    if os.environ.get("SEO_AGENT_NO_CLI", "").strip() == "1":
        return None
    override = os.environ.get("SEO_AGENT_CLAUDE_BIN", "").strip()
    return shutil.which(override or "claude")


CHOICES = ("claude", "codex", "deepseek")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"     # what the DeepSeek CLI runs when no model is picked

# The panel (agents_api.py) knows how the Sutra chat finds a DeepSeek key and which provider the
# chat defaults to. This package imports nothing from the panel, so the panel hands those two
# answers in here as functions. Unset, DeepSeek has no key and the default is Claude.
_HOOKS = {"deepseek_key": None, "default_choice": None}


def set_hooks(deepseek_key=None, default_choice=None):
    _HOOKS["deepseek_key"] = deepseek_key
    _HOOKS["default_choice"] = default_choice


def codex_bin():
    if os.environ.get("SEO_AGENT_NO_CLI", "").strip() == "1":
        return None
    override = os.environ.get("SEO_AGENT_CODEX_BIN", "").strip()
    return shutil.which(override or "codex")


def _deepseek_key():
    fn = _HOOKS["deepseek_key"]
    try:
        return (fn() or "").strip() if fn else ""
    except Exception:  # noqa: BLE001 -- a keychain hiccup means "no key", never a crash
        return ""


def chosen():
    """(provider, model) the person picked, else the Sutra chat's default, else Claude."""
    c = store.model_choice()
    pid, model = c["provider"], c["model"]
    if pid not in CHOICES and _HOOKS["default_choice"]:
        try:
            pid, model = _HOOKS["default_choice"]()
        except Exception:  # noqa: BLE001
            pid, model = "", ""
    if pid not in CHOICES:
        return "claude", ""
    return pid, (model or "")


def provider():
    """What will actually answer: "codex-cli" | "deepseek" | "claude-cli" | "anthropic" |
    "openai" | None. The chosen provider when it can run, otherwise Claude, so a Codex that got
    signed out never leaves the agent dead while Claude is right there."""
    pid, _ = chosen()
    if pid == "codex" and codex_bin():
        return "codex-cli"
    if pid == "deepseek" and _deepseek_key():
        return "deepseek"
    if cli_bin():
        return "claude-cli"
    a, o = _keys()
    if a:
        return "anthropic"
    if o:
        return "openai"
    return None


def available():
    return provider() is not None


# ---- claude cli ------------------------------------------------------------------------
# The CLI has no tool-calling API, so tools are described in the system prompt and the
# reply is forced into a JSON shape with --json-schema. The conversation, which loop.py
# stores in the Anthropic content-block format, is flattened into one prompt on stdin.

CLI_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "input": {"type": "object"}},
                "required": ["name", "input"],
            },
        },
    },
    "required": ["text", "tool_calls"],
}

CLI_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

# The CLI runs the turn with one real tool, StructuredOutput, which delivers the JSON
# reply. Shown a list headed "tools", the model emits a native tool_use for one of them,
# gets "No such tool available" and answers around it. Seen in a live run; this intro is
# what stops it, so keep it blunt and keep the mechanism named.
CLI_TOOL_INTRO = ("IMPORTANT: none of the tools below exist in this session. Emitting a "
                  "tool_use for any of them fails with \"No such tool available\". The only "
                  "tool you have is StructuredOutput, which delivers your reply. To call one "
                  "of the tools below, put {\"name\", \"input\"} into the tool_calls array "
                  "of that structured reply and stop; the host runs it and the result comes "
                  "back in the next turn as \"Result of <id>\".")
# THE ONE-SENTENCE CAP, AND THE EXEMPTION IT NEEDED. Capping the text on a tool-calling turn
# keeps a run readable: nobody wants a paragraph of preamble in front of every step. But it was
# fighting two rules in the brief at once (found 2026-09-10, by running it).
#
# The FIRST turn of a conversation is the exception, and it is not a small one. The brief says
# context comes before any question -- a person who typed "hi" is owed what this is and what it
# is about to offer, not a bare question. With the cap applying there, that was roughly a coin
# flip: on a state with plenty to report the model overrode the cap and gave proper context; on a
# tidy one it obeyed and opened with "Here's the top idea on the sheet." and a question. Same cap
# also produced whole turns that were nothing but a third-person status line.
#
# So the cap now says what it always meant: keep the RUNNING COMMENTARY short. It was never
# meant to govern the sentence that introduces the agent to somebody.
CLI_TOOL_RULE = ("Reply with text and zero or more tool_calls. When you call tools, keep text to "
                 "one short sentence -- EXCEPT on the first turn of a conversation, where a short "
                 "paragraph of context before the question is expected and wanted. Never make the "
                 "whole reply a status line about yourself: write to the person, not about "
                 "yourself. When you have nothing more to do, return an empty tool_calls list.")

# A nested Claude Code session leaves these in the environment and the CLI would treat
# our call as a child of it. ANTHROPIC_API_KEY goes too, so the CLI never bills the API.
CLI_STRIP_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID",
                 "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID", "CLAUDE_CODE_MESSAGING_SOCKET",
                 "CLAUDE_CODE_MESSAGING_TOKEN", "ANTHROPIC_API_KEY")

NOT_LOGGED_IN = "Claude CLI is not logged in. Run `claude` once in a terminal and sign in."


def _compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _cli_env():
    env = dict(os.environ)
    for k in CLI_STRIP_ENV:
        env.pop(k, None)
    return env


def _cli_system(system, tools):
    """The system prompt, plus a tools section when there are tools to call."""
    if not tools:
        return system
    lines = [system.rstrip(), "", "## Tools you can call", "", CLI_TOOL_INTRO, ""]
    for t in tools:
        lines.append("- %s: %s" % (t["name"], t["description"]))
        lines.append("  input_schema: " + _compact(t["input_schema"]))
    lines += ["", CLI_TOOL_RULE]
    return "\n".join(lines)


def _cli_prompt(messages):
    """Flatten the stored conversation into one transcript, ending on the model's turn."""
    parts = []
    for m in messages:
        speaker = "User: " if m.get("role") == "user" else "Assistant: "
        content = m.get("content")
        if isinstance(content, str):
            parts.append(speaker + content)
            continue
        for block in content or []:
            kind = block.get("type")
            if kind == "text":
                parts.append(speaker + (block.get("text") or ""))
            elif kind == "tool_use":
                parts.append("Assistant called %s (%s) with %s"
                             % (block.get("name"), block.get("id"),
                                _compact(block.get("input") or {})))
            elif kind == "tool_result":
                body = json.dumps(block.get("content"), ensure_ascii=False)
                if len(body) > RESULT_CAP:
                    body = body[:RESULT_CAP] + "..."
                parts.append("Result of %s:\n%s" % (block.get("tool_use_id"), body))
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _cli_command(binary, system, tools, model, web=False):
    """The CLI call. `--tools ""` is the default and it matters: the model answers from the prompt
    and nothing else, so a step cannot quietly reach the internet and nobody notices.

    `web=True` is the ONE exception, and only two callers may set it: the enrichment search and the
    replacement-source hunt. Both exist to go and find pages, both are the port of a step the
    original runs as `claude -p --allowedTools WebSearch`, and without it they can only ask the
    model for URLs it believes exist. A believed URL fails to load and is discarded, so nothing
    invented survives either way, but guess-and-check finds less than a search does. (2026-09-09.)
    """
    cmd = [binary, "-p", "--output-format", "json", "--no-session-persistence",
           "--tools", "WebSearch" if web else "", "--setting-sources", "", "--strict-mcp-config",
           "--disable-slash-commands",
           "--system-prompt", _cli_system(system, tools),
           "--json-schema", _compact(CLI_TOOL_SCHEMA if tools else CLI_TEXT_SCHEMA)]
    if model:
        cmd += ["--model", model]
    return cmd


class ModelError(RuntimeError):
    """The CLI answered, but with an error that is not about being signed in. Kept apart
    from NoKey so the screen never tells someone to sign in when the real problem was
    Anthropic being overloaded for a minute."""


# Seconds to wait before each retry of a TRANSIENT failure. The first live run died on
# "API Error: 529 Overloaded" after a single try; that is weather, not a fault, and the
# right answer is to wait and try again, up to three more times. Tests set this to ().
CLI_RETRY_SLEEPS = (5, 15, 40)
_TRANSIENT = ("529", "overloaded", "rate limit", "429", "went to sleep", "503", "502",
              "timed out", "timeout", "econnreset", "socket hang up", "temporarily")


def _transient(text):
    t = (text or "").lower()
    return any(k in t for k in _TRANSIENT)


def _claude_cli(system, messages, tools, binary, model, on_retry=None, timeout=None, web=False):
    cmd = _cli_command(binary, system, tools, model, web=web)
    prompt = _cli_prompt(messages)
    return _retrying(lambda: _claude_cli_once(cmd, prompt, binary, timeout), on_retry)


def _cli_result(out):
    """The CLI's result object out of whatever it printed, or None.

    Normally stdout is exactly one JSON object. On 2026-09-14 a Mac got "did not return JSON
    (exit 0)" with a perfectly good result object in the text, so something else was printed
    alongside it (a notice line, or more than one JSON line). Take the whole thing when it
    parses, else the last line that is a result object, else the first object found in the text.
    """
    if not out:
        return None
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            return data
        if isinstance(data, list):          # some builds print the whole event list
            found = [d for d in data if isinstance(d, dict) and d.get("type") == "result"]
            return found[-1] if found else None
    except ValueError:
        pass
    fallback = None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            if d.get("type") == "result" or "structured_output" in d:
                return d
            fallback = fallback or d
    if fallback is not None:
        return fallback
    dec = json.JSONDecoder()
    i = out.find("{")
    while i != -1:
        try:
            d, _ = dec.raw_decode(out, i)
            if isinstance(d, dict) and ("result" in d or "structured_output" in d):
                return d
        except ValueError:
            pass
        i = out.find("{", i + 1)
    return None


# ---- codex cli -------------------------------------------------------------------------
# `codex exec` runs one turn and writes its last message to a file. --output-schema forces the
# reply shape, and OpenAI's strict schemas allow no free-form objects, so a tool's input travels
# as a JSON string and is parsed back below. It runs read-only in an empty folder: it answers
# from the prompt, the same as the Claude call with --tools "".

CODEX_TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["text", "tool_calls"],
    "properties": {
        "text": {"type": "string"},
        "tool_calls": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "input"],
            "properties": {"name": {"type": "string"},
                           "input": {"type": "string",
                                     "description": "the tool's input object, JSON-encoded"}}}},
    },
}
CODEX_TEXT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
                     "properties": {"text": {"type": "string"}}}
CODEX_TOOL_INTRO = ("IMPORTANT: you are the brain of a host program. Do not run shell commands, "
                    "read files or browse; everything you need is in this prompt. The tools below "
                    "are run by the host: to call one, put {\"name\", \"input\"} into the "
                    "tool_calls array of your reply, with input being the tool's arguments as a "
                    "JSON object encoded into a string, and stop. The result comes back in the "
                    "next turn as \"Result of <id>\".")
NOT_SIGNED_IN_CODEX = "Codex is not signed in. Sign in from Sutra's chat settings, or pick another model."


def _codex_prompt(system, messages, tools):
    head = system.rstrip()
    if tools:
        lines = [head, "", "## Tools you can call", "", CODEX_TOOL_INTRO, ""]
        for t in tools:
            lines.append("- %s: %s" % (t["name"], t["description"]))
            lines.append("  input_schema: " + _compact(t["input_schema"]))
        lines += ["", CLI_TOOL_RULE]
        head = "\n".join(lines)
    return head + "\n\n---\n\n" + _cli_prompt(messages)


def _kill_group(p):
    """End one CLI process and everything it started. The process was given its own session
    (start_new_session in _run_process), so one signal to the group reaches its children too,
    and no `claude` or `codex` helper is left running with nobody to answer to."""
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.kill()
        except OSError:
            pass


def _run_process(cmd, prompt, limit):
    """Start one CLI process, feed it the prompt on stdin, wait for it. Returns
    (returncode, stdout, stderr).

    THE PROCESS IS WATCHED BY THE RUN THIS THREAD WORKS FOR, so stop_run() can kill it while the
    model is still answering. Until 2026-09-16 a model call was subprocess.run with nothing
    holding the handle: Stop wrote "stopped" to disk and the call ran on to its end, a minute or
    more, and only then did anything look at the state. Raises Stopped when the run was stopped
    before or during the call, subprocess.TimeoutExpired when it outlived `limit`.
    """
    run = _GATE.current()
    if run and run.is_stopped():
        raise Stopped(STOPPED_BEFORE)
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, env=_cli_env(), start_new_session=True)
    if run:
        run.watch(p)            # kills at once if the Stop landed between the check and here
    try:
        try:
            out, err = p.communicate(prompt, timeout=limit)
        except subprocess.TimeoutExpired:
            _kill_group(p)
            p.communicate()
            raise
    finally:
        if run:
            run.unwatch(p)
    if run and run.is_stopped():
        raise Stopped(STOPPED_DURING)
    return p.returncode, out or "", err or ""


def _codex_cli_once(binary, system, messages, tools, model, timeout=None):
    import tempfile
    limit = float(timeout or CLI_TIMEOUT)
    with tempfile.TemporaryDirectory(prefix="seo-codex-") as d:
        schema_path = os.path.join(d, "schema.json")
        out_path = os.path.join(d, "last.json")
        with open(schema_path, "w", encoding="utf-8") as fh:
            json.dump(CODEX_TOOL_SCHEMA if tools else CODEX_TEXT_SCHEMA, fh)
        cmd = [binary, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
               "--color", "never", "-C", d, "--output-schema", schema_path, "-o", out_path]
        if model:
            cmd += ["-m", model]
        cmd.append("-")
        try:
            _rc, p_out, p_err = _run_process(cmd, _codex_prompt(system, messages, tools), limit)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Codex timed out: no answer within %d seconds." % int(limit))
        except OSError as e:
            raise RuntimeError("Could not start Codex at %s: %s" % (binary, e))
        try:
            with open(out_path, encoding="utf-8") as fh:
                raw = fh.read().strip()
        except OSError:
            raw = ""
    if not raw:
        # codex echoes the whole prompt to stderr, so the last 400 characters are mostly our own
        # prompt. Its real complaint is on the lines that start with ERROR.
        both = p_err + "\n" + p_out
        errors = [ln.strip()[6:].strip() for ln in both.splitlines() if ln.strip().startswith("ERROR:")]
        why = errors[-1] if errors else both.strip()[-300:]
        low = why.lower()
        if "not logged in" in low or "log in" in low or "login" in low or "not signed in" in low \
                or "unauthorized" in low:
            raise NoKey(NOT_SIGNED_IN_CODEX)
        raise ModelError("Codex could not answer: %s" % why[:300])
    data = _cli_result(raw)
    if not isinstance(data, dict):
        return {"text": raw, "tool_calls": [], "raw": None}
    calls = []
    for c in data.get("tool_calls") or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        inp = c.get("input")
        if isinstance(inp, str):
            try:
                inp = json.loads(inp) if inp.strip() else {}
            except ValueError:
                inp = {}
        calls.append({"id": "call-" + uuid.uuid4().hex[:8], "name": c["name"],
                      "input": inp if isinstance(inp, dict) else {}})
    text = data.get("text")
    return {"text": (text if isinstance(text, str) else "").strip(), "tool_calls": calls, "raw": None}


def _claude_cli_once(cmd, prompt, binary, timeout=None):
    limit = float(timeout or CLI_TIMEOUT)
    try:
        rc, p_out, p_err = _run_process(cmd, prompt, limit)
    except subprocess.TimeoutExpired:
        # The wording carries the retry: _transient() reads the message, and "timed out" is one of
        # the keys it looks for. Reword this and the retry above silently stops happening.
        raise RuntimeError("The Claude CLI timed out: no answer within %d seconds." % int(limit))
    except OSError as e:
        raise RuntimeError("Could not start the Claude CLI at %s: %s" % (binary, e))

    out = p_out.strip()
    data = _cli_result(out)
    if not isinstance(data, dict):
        tail = (p_err.strip() or out)[-400:]
        if "not logged in" in tail.lower() or "log in" in tail.lower():
            raise NoKey(NOT_LOGGED_IN)
        raise RuntimeError("Claude CLI did not return JSON (exit %s): %s" % (rc, tail))

    result = data.get("result")
    result_text = result if isinstance(result, str) else json.dumps(result or "")
    if data.get("is_error") or "Not logged in" in result_text:
        if "logged in" in result_text.lower() or "log in" in result_text.lower():
            raise NoKey(NOT_LOGGED_IN)
        raise ModelError("Claude CLI returned an error: " + result_text[:400])

    structured = data.get("structured_output")
    if not isinstance(structured, dict):
        # No structured answer came back. The plain result is the best we have.
        return {"text": result_text.strip(), "tool_calls": [], "raw": None}

    text = structured.get("text")
    calls = []
    for c in structured.get("tool_calls") or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        inp = c.get("input")
        if isinstance(inp, str):
            try:
                inp = json.loads(inp)
            except ValueError:
                inp = {}
        calls.append({"id": "call-" + uuid.uuid4().hex[:8], "name": c["name"],
                      "input": inp if isinstance(inp, dict) else {}})
    return {"text": (text if isinstance(text, str) else "").strip(),
            "tool_calls": calls, "raw": None}


# ---- anthropic -------------------------------------------------------------------------

def _anthropic(system, messages, tools, key, model):
    payload = {
        "model": model, "max_tokens": 8000,
        "system": system, "messages": messages,
    }
    if tools:
        payload["tools"] = [
            {"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in tools
        ]
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=payload, timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    text, calls = "", []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
        elif block.get("type") == "tool_use":
            calls.append({"id": block["id"], "name": block["name"],
                          "input": block.get("input", {})})
    return {"text": text.strip(), "tool_calls": calls, "raw": data.get("content", [])}


# ---- openai ----------------------------------------------------------------------------

def _openai(system, messages, tools, key, model):
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m.get("content"), str):
            msgs.append(m)
            continue
        for block in m["content"]:
            if block.get("type") == "tool_result":
                msgs.append({"role": "tool", "tool_call_id": block["tool_use_id"],
                             "content": json.dumps(block.get("content"))[:20000]})
            elif block.get("type") == "tool_use":
                msgs.append({"role": "assistant", "tool_calls": [{
                    "id": block["id"], "type": "function",
                    "function": {"name": block["name"],
                                 "arguments": json.dumps(block.get("input", {}))}}]})
            elif block.get("type") == "text":
                msgs.append({"role": m["role"], "content": block["text"]})
    payload = {"model": model, "messages": msgs, "max_tokens": 8000}
    if tools:
        payload["tools"] = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}} for t in tools]
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": "Bearer " + key, "content-type": "application/json"},
        json=payload, timeout=TIMEOUT,
    )
    r.raise_for_status()
    choice = r.json()["choices"][0]["message"]
    calls = [{"id": c["id"], "name": c["function"]["name"],
              "input": json.loads(c["function"]["arguments"] or "{}")}
             for c in (choice.get("tool_calls") or [])]
    return {"text": (choice.get("content") or "").strip(), "tool_calls": calls, "raw": None}


# ---- the gate: how many model calls run at once ----------------------------------------
#
# Every model call passes _GATE. It used to be one fixed semaphore of PARALLEL shared by the
# whole app, so three articles running at once each got a third of one article's speed. Now
# each RUN that registers (run_slot) has its own budget of PARALLEL slots, the whole app is
# capped at PARALLEL_MAX, and calls that belong to no run (a one-off tool, a script, a test)
# share one fallback budget of PARALLEL. With one run the behaviour is exactly the old one.
#
# Measured on an M4 with 16 GB (2026-09-16): 12 tiny `claude -p` calls at once took 3.7 s
# against 3.0 s for one, about 230 MB each, and none was rate-limited. The CPU is not the
# limit; the account's usage limit is, and that is what the pause below is for.

import re as _re
import threading as _threading
from concurrent.futures import ThreadPoolExecutor as _Pool
from contextlib import contextmanager as _contextmanager
from datetime import datetime as _dt, timedelta as _td

PARALLEL = int(os.environ.get("SEO_AGENT_PARALLEL", "3"))          # slots PER RUN, and the fallback
PARALLEL_MAX = int(os.environ.get("SEO_AGENT_PARALLEL_MAX", "9"))  # the ceiling for the whole app

_local = _threading.local()      # .run = the key of the run this thread works for, or None


class Stopped(RuntimeError):
    """The run was stopped by the person.

    Raised by check_stop() at the start of any NEW piece of work (a model call, a paid search, a
    page read, a research or write step), out of a model call whose CLI process stop_run() killed,
    out of a wait for a slot, and out of a usage-limit pause. A RuntimeError, so a tool's own
    catch-all sees it; the next boundary raises it again, so a tool that swallows one still ends
    at its next step and never starts more work.
    """


STOPPED_BEFORE = "Stopped by the user before this started."
STOPPED_DURING = "Stopped by the user while the model was answering."
STOP_POLL = 1.0              # how often a thread waiting for a slot looks for a Stop


class _Run:
    def __init__(self, key, on_note=None, should_stop=None):
        self.key = key
        self.on_note = on_note          # on_note(text): one status row in that run's chat
        self.should_stop = should_stop  # should_stop() -> True once the person pressed Stop
        self.in_use = 0
        self._stop = _threading.Event()  # set by stop_run(), or once should_stop() first says so
        self._procs = set()              # the CLI processes answering for this run right now
        self._plock = _threading.Lock()

    def is_stopped(self):
        """Has this run been stopped? The in-memory flag first (stop_run sets it), then the
        caller's own test (the run's state on disk). A disk-side stop sets the flag too, so the
        processes are killed and every later check is a memory read."""
        if self._stop.is_set():
            return True
        try:
            if self.should_stop and self.should_stop():
                self.stop()
                return True
        except Exception:  # noqa: BLE001 -- an unreadable state file is not a Stop
            pass
        return False

    def stop(self):
        """Flag the run stopped and kill every CLI process it has in flight."""
        self._stop.set()
        with self._plock:
            procs = list(self._procs)
        for p in procs:
            _kill_group(p)

    def watch(self, proc):
        """Hold a process so stop() can reach it. A process handed in after the Stop landed is
        killed here and now, so the two can never miss each other."""
        with self._plock:
            self._procs.add(proc)
            stopped = self._stop.is_set()
        if stopped:
            _kill_group(proc)

    def unwatch(self, proc):
        with self._plock:
            self._procs.discard(proc)


class _Gate:
    def __init__(self, per_run=None, cap=None):
        self._cond = _threading.Condition()
        self._runs = {}                 # key -> _Run, while the run is alive
        self._total = 0
        self._loose = 0                 # calls in flight that belong to no run
        self._per_run = per_run         # None = follow the module's PARALLEL
        self._cap = cap                 # None = follow the module's PARALLEL_MAX

    def configure(self, per_run=None, cap=None):
        """Set the two numbers at runtime (the Sutra setting). None puts one back on the env."""
        with self._cond:
            self._per_run = int(per_run) if per_run else None
            self._cap = int(cap) if cap else None
            self._cond.notify_all()

    def limits(self):
        per = self._per_run or PARALLEL
        cap = self._cap or PARALLEL_MAX
        return max(1, per), max(1, per, cap)

    def _can(self, run):
        per, cap = self.limits()
        if self._total >= cap:
            return False
        return (run.in_use if run else self._loose) < per

    def acquire(self):
        run = self._runs.get(getattr(_local, "run", None))
        with self._cond:
            while not self._can(run):
                # A call queued behind the run's own slots must not start once the run is
                # stopped: stop_run() wakes every waiter, and the poll covers a disk-side stop.
                if run and run.is_stopped():
                    raise Stopped(STOPPED_BEFORE)
                self._cond.wait(STOP_POLL)
            self._total += 1
            if run:
                run.in_use += 1
            else:
                self._loose += 1
        return run

    def release(self, run):
        with self._cond:
            self._total -= 1
            if run:
                run.in_use -= 1
            else:
                self._loose -= 1
            self._cond.notify_all()

    def register(self, run):
        with self._cond:
            self._runs[run.key] = run
            self._cond.notify_all()

    def unregister(self, run):
        with self._cond:
            self._runs.pop(run.key, None)
            self._cond.notify_all()

    def runs(self):
        with self._cond:
            return list(self._runs.values())

    def current(self):
        return self._runs.get(getattr(_local, "run", None))

    def find(self, key):
        with self._cond:
            return self._runs.get(key)

    def wake(self):
        with self._cond:
            self._cond.notify_all()

    def in_flight(self):
        with self._cond:
            return {"total": self._total, "loose": self._loose,
                    "runs": {k: r.in_use for k, r in self._runs.items()}}


_GATE = _Gate()


def _bind(key):
    prev = getattr(_local, "run", None)
    _local.run = key
    return prev


@_contextmanager
def run_slot(chat_id=None, run_id=None, on_note=None, should_stop=None):
    """`with llm.run_slot(chat, run, on_note, should_stop):` around one run's whole life.

    Registers the run with the gate (its own PARALLEL slots) and binds this thread to it, so
    every call made on this thread, and on any pool made with llm.pool(), counts against the
    run's budget. The run is unregistered when the block ends, however it ends; a pool thread
    still finishing a call afterwards simply releases into the counters it took from.
    """
    key = "%s/%s" % (chat_id or "", run_id or uuid.uuid4().hex[:8])
    run = _Run(key, on_note, should_stop)
    _GATE.register(run)
    prev = _bind(key)
    try:
        yield key
    finally:
        _bind(prev)
        _GATE.unregister(run)


def check_stop():
    """Raise Stopped if the run this thread works for has been stopped. Nothing happens outside
    a run.

    THE ONE BOUNDARY EVERY PIECE OF WORK CROSSES FIRST. call() runs it before a model call,
    dfs._send before a paid DataForSEO call, web.fetch before a page read, research's cached()
    and write_article's step() before a step. So a Stop is noticed at the next natural boundary
    of whatever is running, and nothing new is started past it: what is already on disk stays
    for the continue to reuse.
    """
    run = _GATE.current()
    if run and run.is_stopped():
        raise Stopped(STOPPED_BEFORE)


def stop_run(chat_id, run_id):
    """Reach the work a run has in flight: kill its CLI processes, wake its threads waiting for
    a slot, and flag it so every check_stop() from here raises. True when the run was live in
    this process. The caller (loop.stop) has already written the state to disk."""
    run = _GATE.find("%s/%s" % (chat_id, run_id))
    if not run:
        return False
    run.stop()
    _GATE.wake()
    return True


def pool(max_workers=None):
    """A ThreadPoolExecutor whose workers belong to the same run as the thread that made it.

    Use this, not a bare ThreadPoolExecutor, wherever a tool fans model calls out: a plain pool's
    threads know no run, so their calls would fall into the shared fallback budget and the run
    would not get its own speed. Defaults to one worker per slot the run has.
    """
    key = getattr(_local, "run", None)
    return _Pool(max_workers=max_workers or _GATE.limits()[0], initializer=_bind, initargs=(key,))


def slot_settings():
    """The two numbers in force and where each came from: {per_run, max, source}."""
    per, cap = _GATE.limits()
    saved = store.slot_settings()
    source = "setting" if (saved.get("per_run") or saved.get("max")) else (
        "env" if (os.environ.get("SEO_AGENT_PARALLEL") or os.environ.get("SEO_AGENT_PARALLEL_MAX")) else "default")
    return {"per_run": per, "max": cap, "source": source}


def load_slot_settings():
    """Apply the saved Sutra setting (store.slot_settings) on top of the env. Called at start-up
    and after every save. A missing file leaves the env and the defaults in charge."""
    saved = store.slot_settings()
    _GATE.configure(saved.get("per_run"), saved.get("max"))
    return slot_settings()


# ---- the pause: a usage limit waits instead of failing ---------------------------------
#
# On 2026-09-15 three runs died at once on "You've hit your session limit · resets 1am
# (Asia/Calcutta)". That is not a fault in the run; it is the account's clock. So a call that
# fails with a usage-limit message reads the reset time out of it, tells each running chat once
# ("Paused: Claude usage limit reached. Carrying on at 1:02 am."), waits until then plus a
# margin, and tries the same call again. Every other call arriving meanwhile waits at the door
# (call() checks the pause before it takes a slot), so nothing burns attempts against a limit
# that is known to be shut. A Stop from the person ends the wait with Stopped.

LIMIT_MARGIN = 120           # seconds past the stated reset before trying again
LIMIT_BLIND_WAIT = 900       # when the message names no time: try again after this long
LIMIT_MAX_WAIT = 6 * 3600    # give up with a clear message once one call has waited this long
LIMIT_POLL = 2.0             # how often a waiting call looks for a Stop

_LIMIT_KEYS = ("session limit", "usage limit", "hit your limit", "out of extra usage",
               "quota exceeded", "quota has been exhausted")

# Swappable clock, so a test can run a six-hour pause in milliseconds.
_now = time.time
_sleep = time.sleep

_PROVIDER_LABEL = {"claude-cli": "Claude", "codex-cli": "Codex", "deepseek": "DeepSeek",
                   "anthropic": "Anthropic", "openai": "OpenAI"}

_ISO = _re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}:?\d{2})?")
_CLOCK = _re.compile(r"(?:resets?|resetting|try again|available again|available|back)\s+"
                     r"(?:at\s+|around\s+|by\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?![\d:])",
                     _re.I)
# A bare "at 9am" / "at 13:00" with no reset word in front, as in "try again on 3 Jan at 9am".
# Needs the am/pm or the colon, so "at 5 pages" is never read as five o'clock.
_AT_CLOCK = _re.compile(r"\bat\s+(\d{1,2})(?:(?::(\d{2}))\s*(am|pm|a\.m\.|p\.m\.)?|()\s*(am|pm|a\.m\.|p\.m\.))(?![\d:])", _re.I)
_RELATIVE = _re.compile(r"\b(?:in|after)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b", _re.I)
_ZONE = _re.compile(r"\b([A-Z][A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?|UTC|GMT)\b")
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t|tember)?"
        r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?")
_DATE_MD = _re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(\d{4}))?", _re.I)   # Sep 26th, 2026
_DATE_DM = _re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r"\b(?:,?\s*(\d{4}))?", _re.I)   # 26 Sep 2026


def _usage_limited(text):
    """True for an error that says the account is out of usage until some reset. A bare
    "rate limit" stays a transient retry unless it names a reset time."""
    t = (text or "").lower()
    if any(k in t for k in _LIMIT_KEYS):
        return True
    return "rate limit" in t and parse_reset(text) is not None


def _zone_of(text):
    m = _ZONE.search(text or "")
    if not m:
        return None
    name = m.group(1)
    if name in ("UTC", "GMT"):
        from datetime import timezone
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 -- an unknown zone name means "read it as local time"
        return None


def parse_reset(text, now=None):
    """The reset moment named in an error message, as a Unix time. None when it names none.

    Reads "resets 1am (Asia/Calcutta)", "resets 8pm (...)", "resets at 13:00", "try again at
    3:45 PM UTC", an ISO time, "try again at Sep 26th" (Codex's weekly limit), and "try again
    in 15 minutes". A clock time is the NEXT occurrence in the named zone (today if still
    ahead, else tomorrow); a date is the next such date, at the clock time if one is given.
    """
    text = text or ""
    now = _now() if now is None else now
    m = _ISO.search(text)
    if m:
        raw = m.group(0).replace(" ", "T", 1).replace(" ", "")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            d = _dt.fromisoformat(raw)
            if d.tzinfo is None:
                d = d.replace(tzinfo=_zone_of(text) or _dt.fromtimestamp(now).astimezone().tzinfo)
            return d.timestamp()
        except ValueError:
            pass
    tz = _zone_of(text) or _dt.fromtimestamp(now).astimezone().tzinfo
    base = _dt.fromtimestamp(now, tz)

    hour = minute = None
    m = _CLOCK.search(text)
    parts = (m.group(1), m.group(2), m.group(3)) if m else None
    if not parts:
        m = _AT_CLOCK.search(text)
        if m:
            parts = (m.group(1), m.group(2), m.group(3) or m.group(5))
    if parts:
        hour, minute, ampm = int(parts[0]), int(parts[1] or 0), (parts[2] or "").replace(".", "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            hour = minute = None

    m = _DATE_MD.search(text)
    mon, day, year = (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)
    if not m:
        m = _DATE_DM.search(text)
        if m:
            day, mon, year = m.group(1), m.group(2), m.group(3)
    if mon:
        try:
            when = base.replace(month=_MONTHS.index(mon.lower()[:3]) + 1, day=int(day),
                                hour=hour or 0, minute=minute or 0, second=0, microsecond=0)
            if year:
                when = when.replace(year=int(year))
            elif when <= base:
                when = when.replace(year=when.year + 1)
            return when.timestamp()
        except ValueError:
            pass

    if hour is not None:
        when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if when <= base:
            when += _td(days=1)
        return when.timestamp()
    m = _RELATIVE.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        return now + n * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1)
    return None


def _clock_words(when, now):
    """"1:02 am", "1:02 am tomorrow", or "1:02 am on Thu 18 Sep", in the Mac's own time."""
    w = _dt.fromtimestamp(when).astimezone()
    n = _dt.fromtimestamp(now).astimezone()
    words = w.strftime("%I:%M %p").lstrip("0").lower()
    days = (w.date() - n.date()).days
    if days == 1:
        words += " tomorrow"
    elif days > 1:
        words += w.strftime(" on %a %d %b")
    return words


class _Pause:
    """The one account-wide pause. `until` is a Unix time; a value in the past is no pause."""

    def __init__(self):
        self._lock = _threading.Lock()
        self.until = 0.0
        self.message = ""
        self.seq = 0            # bumps each time a new, later pause begins
        self._noted = set()     # (run key, seq) pairs already told about this pause

    def begin(self, until, message):
        with self._lock:
            if until <= self.until and self.until > _now():
                return False           # somebody is already waiting for the same or a later reset
            self.until = until
            if message != self.message:
                # A new message is a new row in each chat. The same message again (a blind
                # 15-minute retry that found the limit still shut) is not: one row, not one every
                # quarter hour for six hours.
                self.seq += 1
                self._noted = set()
            self.message = message
            seq = self.seq
        for run in _GATE.runs():
            self._tell(run, seq, message)
        return True

    def _tell(self, run, seq, message):
        mark = (run.key, seq)
        with self._lock:
            if mark in self._noted:
                return
            self._noted.add(mark)
        if run.on_note:
            try:
                run.on_note(message)
            except Exception:  # noqa: BLE001 -- a chat we cannot write to must not break the wait
                pass

    def active(self):
        return self.until > _now()

    def wait(self, on_retry=None):
        """Block until the pause is over. Raises Stopped when this thread's run was stopped."""
        told_loose = False
        while True:
            with self._lock:
                until, seq, message = self.until, self.seq, self.message
            now = _now()
            if now >= until:
                return
            run = _GATE.current()
            if run:
                self._tell(run, seq, message)       # a run that began during the pause hears about it
                if run.is_stopped():
                    raise Stopped("Stopped while waiting for the usage limit to reset.")
            elif on_retry and not told_loose:
                told_loose = True
                try:
                    on_retry(message)
                except Exception:  # noqa: BLE001
                    pass
            _sleep(max(0.0, min(LIMIT_POLL, until - now)))

    def clear(self):
        with self._lock:
            self.until = 0.0
            self._noted = set()


_PAUSE = _Pause()


def _pause_for(error_text, waited, on_retry=None):
    """Begin (or join) the pause the error asks for and wait it out. Returns the seconds this
    call has now waited in total. Raises ModelError when that would pass LIMIT_MAX_WAIT."""
    now = _now()
    label = _PROVIDER_LABEL.get(provider() or "", "The model's")
    reset = parse_reset(error_text, now)
    if reset is not None and reset + LIMIT_MARGIN <= now:
        reset = None                  # a reset already behind us, yet the limit still bites: go blind
    if reset is None:
        until = now + LIMIT_BLIND_WAIT
        words = ("Paused: %s usage limit reached. It did not say when it resets, so trying again "
                 "every %d minutes." % (label, LIMIT_BLIND_WAIT // 60))
    else:
        until = reset + LIMIT_MARGIN
        words = "Paused: %s usage limit reached. Carrying on at %s." % (label, _clock_words(until, now))
    if waited + (until - now) > LIMIT_MAX_WAIT:
        hours = LIMIT_MAX_WAIT // 3600
        if reset is not None and until - now > LIMIT_MAX_WAIT:
            raise ModelError("%s usage limit reached, and it does not reset until %s, more than %d hours "
                             "away. Stopping here. Send a message to carry on once it has reset."
                             % (label, _clock_words(until, now), hours))
        raise ModelError("%s usage limit is still in force after %d hours of waiting. Stopping here. "
                         "Send a message to carry on once it has reset." % (label, hours))
    _PAUSE.begin(until, words)
    _PAUSE.wait(on_retry)
    return waited + (until - now)


# ---- the call --------------------------------------------------------------------------

LONG_TIMEOUT = 1200.0        # a whole document in one call (a brand file, a full-article edit)


def call(system, messages, tools=None, model=None, on_retry=None, timeout=None, web=False):
    """timeout: seconds for this one call. Whole-document calls pass LONG_TIMEOUT; the
    default CLI_TIMEOUT is for a turn or a section. Per call, never a global swap."""
    check_stop()                 # a stopped run starts no new model call, whatever the caller
    if _PAUSE.active():
        _PAUSE.wait(on_retry)
    run = _GATE.acquire()
    try:
        return _call(system, messages, tools, model, on_retry, timeout, web)
    finally:
        _GATE.release(run)


def _retrying(once, on_retry=None):
    """Run once(). A usage-limit error pauses (see _Pause) and tries the SAME call again; a
    TRANSIENT error is retried after each of CLI_RETRY_SLEEPS; anything else is raised.

    RuntimeError, not just ModelError (2026-09-10). _TRANSIENT has listed "timed out" and
    "timeout" since the day it was written, but a timeout does not come back as a ModelError:
    _claude_cli_once turns subprocess.TimeoutExpired into a plain RuntimeError, which the old
    clause never caught. NoKey is not a RuntimeError, so a sign-in problem still surfaces at once.
    """
    attempts = 1 + len(CLI_RETRY_SLEEPS)
    attempt = 0
    waited = 0.0
    while True:
        try:
            return once()
        except Stopped:
            raise                # a Stop is not weather: never waited out, never tried again
        except RuntimeError as e:
            why = str(e).replace("Claude CLI returned an error: ", "")
            if _usage_limited(why):
                waited = _pause_for(why, waited, on_retry)    # a pause does not spend an attempt
                continue
            if attempt + 1 < attempts and _transient(why):
                wait = CLI_RETRY_SLEEPS[attempt]
                if on_retry:
                    # A silent minute looks like a hang. Say what is happening, in the log.
                    try:
                        on_retry("The model was unavailable (%s). Waiting %ds and trying again, "
                                 "attempt %d of %d." % (why[:90], wait, attempt + 2, attempts))
                    except Exception:
                        pass
                time.sleep(wait)
                attempt += 1
                continue
            raise


def _deepseek(system, messages, tools, key, model, timeout=None):
    """DeepSeek's OpenAI-compatible API, with native tool calling. The same key and the same
    account the DeepSeek CLI in Sutra's chat uses."""
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            msgs.append({"role": m.get("role"), "content": content})
            continue
        texts, calls, results = [], [], []
        for block in content or []:
            kind = block.get("type")
            if kind == "text":
                texts.append(block.get("text") or "")
            elif kind == "tool_use":
                calls.append({"id": block["id"], "type": "function",
                              "function": {"name": block["name"],
                                           "arguments": json.dumps(block.get("input") or {})}})
            elif kind == "tool_result":
                body = json.dumps(block.get("content"), ensure_ascii=False)
                results.append({"role": "tool", "tool_call_id": block["tool_use_id"],
                                "content": body[:RESULT_CAP]})
        if m.get("role") == "assistant":
            out = {"role": "assistant", "content": "\n".join(texts)}
            if calls:
                out["tool_calls"] = calls
            msgs.append(out)
        else:
            msgs.extend(results)
            if texts:
                msgs.append({"role": "user", "content": "\n".join(texts)})
    payload = {"model": model or DEEPSEEK_MODEL, "messages": msgs, "max_tokens": 8000}
    if tools:
        payload["tools"] = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}} for t in tools]
    try:
        r = httpx.post(DEEPSEEK_URL, json=payload, timeout=float(timeout or CLI_TIMEOUT),
                       headers={"Authorization": "Bearer " + key, "content-type": "application/json"})
    except httpx.TimeoutException:
        raise RuntimeError("DeepSeek timed out.")
    except httpx.HTTPError as e:
        raise RuntimeError("Could not reach DeepSeek (temporarily): %s" % e)
    if r.status_code == 401:
        raise NoKey("DeepSeek refused the saved key. Sign in to DeepSeek again in Sutra's chat settings.")
    if r.status_code == 402:
        raise ModelError("DeepSeek says the balance is empty. Top it up, or pick another model.")
    if r.status_code >= 400:
        raise ModelError("DeepSeek returned an error %s: %s" % (r.status_code, r.text[:300]))
    choice = (r.json().get("choices") or [{}])[0].get("message") or {}
    calls = []
    for c in choice.get("tool_calls") or []:
        fn = c.get("function") or {}
        try:
            inp = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            inp = {}
        calls.append({"id": c.get("id") or "call-" + uuid.uuid4().hex[:8], "name": fn.get("name"),
                      "input": inp if isinstance(inp, dict) else {}})
    return {"text": (choice.get("content") or "").strip(), "tool_calls": calls, "raw": None}


def _call(system, messages, tools=None, model=None, on_retry=None, timeout=None, web=False):
    """on_retry(message) is called before each retry of a transient CLI error, so the
    caller can put a line in the run log instead of leaving the user staring at a spinner."""
    running = provider()
    pid, picked = chosen()
    # A web search is a Claude CLI feature. Those two calls stay on Claude when it is here.
    if running in ("codex-cli", "deepseek") and not (web and cli_bin()):
        use = model or picked or None
        if running == "codex-cli":
            b = codex_bin()
            return _retrying(lambda: _codex_cli_once(b, system, messages, tools, use, timeout), on_retry)
        key = _deepseek_key()
        return _retrying(lambda: _deepseek(system, messages, tools, key, use, timeout), on_retry)
    binary = cli_bin()
    if binary:
        if not model and pid == "claude":
            model = picked or None
        return _claude_cli(system, messages, tools, binary,
                           model or os.environ.get("SEO_AGENT_MODEL", "").strip() or None,
                           on_retry=on_retry, timeout=timeout, web=web)
    a, o = _keys()
    if a:
        return _anthropic(system, messages, tools, a, model or ANTHROPIC_MODEL)
    if o:
        return _openai(system, messages, tools, o, model or OPENAI_MODEL)
    raise NoKey("No model available. Install the Claude CLI or add a key in Connections.")


def text(prompt, system="You are a precise assistant. Answer with only what was asked.", timeout=None,
         web=False):
    """One-shot text. Used inside tools, where no tool-calling is needed.

    `web=True` lets this ONE call search the internet. Only the enrichment search and the
    replacement-source hunt may pass it: both exist to go and find pages, and both are ports of a
    step the original runs with WebSearch enabled. Everything else answers from its prompt.
    """
    return call(system, [{"role": "user", "content": prompt}], timeout=timeout, web=web)["text"]


def json_call(prompt, system="Reply with valid JSON only. No prose, no code fences.", retries=1,
              timeout=None, web=False):
    """One-shot JSON, with a tolerant extractor and one retry on a parse failure."""
    for attempt in range(retries + 1):
        raw = text(prompt, system, timeout=timeout, web=web)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1), default=-1)
            end = max(cleaned.rfind("}"), cleaned.rfind("]"))
            if start != -1 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    pass
            if attempt == retries:
                raise ValueError("Model did not return valid JSON:\n" + raw[:500])
    return None
