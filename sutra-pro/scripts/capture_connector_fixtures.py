#!/usr/bin/env python3
"""Refresh tests/fixtures/connectors from the real `claude` and `codex`. A human runs this; no test and no gate ever does.

    SUTRA_LIVE=1 .venv/bin/python scripts/capture_connector_fixtures.py [--only claude|codex] [--skip STEP,...] [--out DIR]
    .venv/bin/python scripts/capture_connector_fixtures.py --plan        # print every step and what it writes; run nothing

It repeats the probe session behind connectors.md section 1.2: AT MOST TWO calls per CLI reach a model (a fresh call with a
JSON schema, then a resume of that session); everything else needs no model: status commands, --help, signed-out runs against an
EMPTY config directory, flag errors, an unknown session id. Each of those steps checks its own result, and the script stops
that step when one looks as if it reached a model. Calls use the connectors' flags and environment allowlist, run in a scratch
directory under the temp dir, and the sessions they leave behind are removed with `claude purge` / `codex delete` (best effort).

Written files are scrubbed (your e-mail, organisation, home directory, scratch paths, the device sign-in code) and the Claude init
event is trimmed to the keys a connector reads. `derived/` and `handwritten/` fixtures are NOT regenerated: the script says so at the
end, so you re-check their wording against the new captures. It also updates the CLI versions in MANIFEST.json.

--claude / --codex name the executables (default: claude and codex on PATH); --pass-env NAME,... forwards more variables to them (the
tests use it to drive the fakes in tests/fakes). Exit 0 when every step wrote its files, 1 when a step failed, 2 for a refusal.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "connectors"
MAX_MODEL_CALLS = 2
# the connectors' child environment (connectors.md section 4); copied so that the script runs without the package
ENV_ALLOW = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY",
             "NO_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "no_proxy", "all_proxy", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
             "XDG_STATE_HOME", "CLAUDE_CONFIG_DIR", "CODEX_HOME")
CLAUDE_INIT_KEYS = ("type", "subtype", "cwd", "session_id", "tools", "mcp_servers", "model", "permissionMode", "apiKeySource", "claude_code_version",
                    "output_style", "capabilities", "uuid")
CODEX_MODEL_KEYS = ("slug", "display_name", "description", "visibility", "default_reasoning_level", "supported_reasoning_levels", "context_window",
                    "max_context_window", "input_modalities", "supported_in_api", "priority")
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}
PROMPT_FRESH = "Reply with the single word ok in the answer field."
PROMPT_RESUME = "Reply with the single word ok."
UNKNOWN_SESSION = "00000000-0000-4000-8000-0000000000ff"
STATUS_TIMEOUT = 60
CALL_TIMEOUT = 180
SIGNED_OUT_TIMEOUT = 120          # a signed-out codex retries its 401s for 18-20 s
# the stdio MCP server the CLIs are pointed at: it logs every request it receives and answers initialize and tools/list
PROBE_SERVER = '''import json, sys
log = open(sys.argv[1], "a")
for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    log.write(raw + "\\n")
    log.flush()
    try:
        msg = json.loads(raw)
    except ValueError:
        continue
    mid, method = msg.get("id"), msg.get("method")
    if method == "initialize":
        result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "probe", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "ping", "description": "ping", "inputSchema": {"type": "object", "properties": {}}}]}
    elif mid is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}) + "\\n")
        sys.stdout.flush()
        continue
    else:
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\\n")
    sys.stdout.flush()
'''


class CaptureError(Exception):
    """A step cannot go on (or one of its safety checks failed)."""


class Result:
    def __init__(self, code, stdout, stderr, seconds, timed_out=False):
        self.code, self.stdout, self.stderr, self.seconds, self.timed_out = code, stdout, stderr, seconds, timed_out


def run_cmd(argv, env, stdin_text=None, cwd=None, timeout=CALL_TIMEOUT):
    """Run to the end in its own process group; kill the whole group after `timeout` seconds."""
    started = time.time()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=cwd, env=env, text=True, start_new_session=True)
    timed_out = False
    try:
        out, err = proc.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    return Result(proc.returncode, out, err, round(time.time() - started, 1), timed_out)


def run_until(argv, env, pattern, cwd=None, timeout=30):
    """Start a process, read its combined output until `pattern` matches, then stop it -> (output, seconds). For the device sign-in."""
    started = time.time()
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, env=env, start_new_session=True)
    buf = b""
    try:
        while time.time() - started < timeout:
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if not ready:
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            if re.search(pattern, buf.decode("utf-8", "replace")):
                break
    finally:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    return buf.decode("utf-8", "replace"), round(time.time() - started, 1)


# ------------------------------------------------------------------------------------------------ scrubbing and trimming
class Scrubber:
    """Replace what identifies the owner or the machine with the placeholders the fixtures already use."""

    def __init__(self, home=None):
        self.pairs = []
        self.add(home if home is not None else str(Path.home()), "/Users/me")

    def add(self, secret, replacement):
        if secret and len(secret) > 1 and secret != replacement and (secret, replacement) not in self.pairs:
            self.pairs.append((secret, replacement))
            self.pairs.sort(key=lambda p: -len(p[0]))             # the longest first: a scratch directory inside the home directory wins

    def learn_identity(self, doc):
        """From the signed-in `auth status` JSON: the e-mail, organisation id and name."""
        self.add(doc.get("email"), "user@example.com")
        self.add(doc.get("orgId"), "00000000-0000-0000-0000-000000000000")
        self.add(doc.get("orgName"), "user@example.com's Organization")

    def text(self, value):
        for secret, replacement in self.pairs:
            value = value.replace(secret, replacement)
        return value

    def obj(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.obj(v) for v in value]
        if isinstance(value, dict):
            return {k: self.obj(v) for k, v in value.items()}
        return value


def trim_claude_init(event):
    """Keep only the keys of the system/init event that a connector reads."""
    return {k: v for k, v in event.items() if k in CLAUDE_INIT_KEYS}


def scrub_stream(text, scrubber, fixed_cwd=False):
    """A stream-json or JSONL capture -> the fixture text: init trimmed (its cwd becomes /work with fixed_cwd), strings scrubbed, one
    compact JSON object per line. Lines that are not JSON are kept (scrubbed); blank lines are dropped."""
    out = []
    for raw in text.split("\n"):
        if raw.strip() == "":
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            out.append(scrubber.text(raw))
            continue
        if isinstance(obj, dict) and obj.get("type") == "system" and obj.get("subtype") == "init":
            obj = trim_claude_init(obj)
            if fixed_cwd:
                obj["cwd"] = "/work"
        out.append(json.dumps(scrubber.obj(obj), separators=(",", ":"), ensure_ascii=False))
    return "\n".join(out) + "\n"


def scrub_device_code(text):
    # no \b: the code sits right behind the colour escape "...94m", where a word boundary does not exist
    return re.sub(r"(?<![A-Z0-9])[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])", "ABCD-EFGHJ", text)


def strip_models(doc):
    """`codex debug models` without its instruction texts."""
    return {"models": [{k: m[k] for k in CODEX_MODEL_KEYS if k in m} for m in doc.get("models", [])]}


def parse_jsonl(text):
    out = []
    for raw in text.split("\n"):
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def stream_result(text):
    """The `result` line of a Claude stream, or {}."""
    found = [o for o in parse_jsonl(text) if o.get("type") == "result"]
    return found[-1] if found else {}


def probe_doc(res, **extra):
    """The cli_errors.json shape of one probe: exit, stdout, stderr, seconds."""
    doc = {"exit": res.code, "stdout": res.stdout, "stderr": res.stderr, "seconds": res.seconds}
    doc.update(extra)
    return doc


# ------------------------------------------------------------------------------------------------ the steps
STEPS = {
    "claude": ["claude_help", "claude_auth_status", "claude_fresh", "claude_resume", "claude_signed_out", "claude_resume_unknown", "claude_mcp",
               "claude_tool_profile", "claude_interrupt", "claude_errors"],
    "codex": ["codex_help", "codex_login_status", "codex_fresh", "codex_resume", "codex_rollout", "codex_signed_out", "codex_device_auth",
              "codex_models", "codex_mcp", "codex_errors"],
}
PLAN = {   # step -> (what it runs, what it writes, model calls)
    "claude_help": ("claude --version, claude --help", "claude/help.txt", 0),
    "claude_auth_status": ("claude auth status (signed in; signed out with an empty CLAUDE_CONFIG_DIR)",
                           "claude/auth_status_signed_in.json, claude/auth_status_signed_out.json", 0),
    "claude_fresh": ("claude -p ... --json-schema ... --include-partial-messages --session-id <uuid>", "claude/stream_structured_ok.jsonl", 1),
    "claude_resume": ("claude -p ... --resume <uuid>", "claude/stream_resume_plain_ok.jsonl", 1),
    "claude_signed_out": ("claude -p ... with an empty CLAUDE_CONFIG_DIR", "claude/stream_not_logged_in.jsonl", 0),
    "claude_resume_unknown": ("claude -p ... --resume <unknown uuid>", "claude/stream_resume_unknown_session.jsonl", 0),
    "claude_mcp": ("claude -p ... --mcp-config <probe MCP server> (empty config)", "claude/stream_mcp_server_connected.jsonl, mcp/claude_client_requests.jsonl", 0),
    "claude_tool_profile": ("claude -p ... with the tool profile flags (empty config)", "claude/stream_tool_profile_init.jsonl", 0),
    "claude_interrupt": ("claude -p --input-format stream-json with a control_request interrupt on stdin", "claude/control_interrupt_response.jsonl", 0),
    "claude_errors": ("claude with a bad flag, a bad schema, a missing system prompt file", "cli_errors.json", 0),
    "codex_help": ("codex --version, codex exec --help, codex exec resume --help", "codex/exec_help.txt, codex/exec_resume_help.txt", 0),
    "codex_login_status": ("codex login status (signed in; signed out with an empty CODEX_HOME)", "cli_errors.json", 0),
    "codex_fresh": ("codex exec --json ... --output-schema <file> -", "codex/exec_structured_ok.jsonl", 1),
    "codex_resume": ("codex exec resume --json ... <thread id> -", "codex/exec_resume_plain_ok.jsonl", 1),
    "codex_rollout": ("read the token_count lines of that thread's rollout file", "codex/rollout_token_count.jsonl", 0),
    "codex_signed_out": ("codex exec ... with an empty CODEX_HOME (about 20 s of 401 retries)", "codex/exec_not_signed_in.jsonl", 0),
    "codex_device_auth": ("codex login --device-auth with an empty CODEX_HOME, stopped once the code is printed", "codex/login_device_auth.txt", 0),
    "codex_models": ("codex debug models", "codex/models_excerpt.json", 0),
    "codex_mcp": ("codex exec ... -c mcp_servers.sutra.* <probe MCP server> (empty CODEX_HOME)", "mcp/codex_client_requests.jsonl", 0),
    "codex_errors": ("codex with a bad flag, a bad schema file, a missing directory, an unknown thread", "cli_errors.json", 0),
}


class Capture:
    def __init__(self, out, claude="claude", codex="codex", only=None, skip=(), pass_env=(), say=print, environ=None):
        self.out, self.exe = Path(out), {"claude": claude, "codex": codex}
        self.only, self.skip, self.pass_env, self.say = only, set(skip), tuple(pass_env), say
        self.environ = dict(os.environ if environ is None else environ)
        self.scratch = Path(tempfile.mkdtemp(prefix="sutra-capture-"))
        self.scrub = Scrubber(self.environ.get("HOME"))
        for form in (str(self.scratch), str(self.scratch.resolve())):
            self.scrub.add(form, "/scratch/probe")
        self.model_calls = {"claude": 0, "codex": 0}
        self.written, self.failed, self.warnings = [], [], []
        self.versions, self.probes, self.session = {}, {}, {}

    # ---- plumbing
    def env(self, cli, empty_config=False):
        """The connectors' environment allowlist (plus --pass-env). empty_config points the CLI at an empty config directory: no login."""
        env = {k: self.environ[k] for k in ENV_ALLOW + self.pass_env if k in self.environ}
        if empty_config:
            home = self.scratch / ("%s-empty-config" % cli)
            home.mkdir(exist_ok=True)
            env["CLAUDE_CONFIG_DIR" if cli == "claude" else "CODEX_HOME"] = str(home)
        return env

    def workdir(self, name):
        path = self.scratch / name
        path.mkdir(exist_ok=True)
        return str(path)

    def write(self, rel, text):
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
        if rel not in self.written:
            self.written.append(rel)
        self.say("  wrote %s" % rel)

    def call(self, cli, argv, *, reaches_model, env, stdin=None, cwd=None, timeout=CALL_TIMEOUT):
        """The one way to start a command that could reach a model: counts those that do and refuses a third."""
        if reaches_model:
            if self.model_calls[cli] >= MAX_MODEL_CALLS:
                raise CaptureError("refusing call %d that reaches a %s model (the limit is %d)" % (self.model_calls[cli] + 1, cli, MAX_MODEL_CALLS))
            self.model_calls[cli] += 1
        return run_cmd(argv, env, stdin, cwd, timeout)

    def run(self):
        for cli in ("claude", "codex"):
            if self.only and cli != self.only:
                continue
            self.say("== %s" % cli)
            for name in STEPS[cli]:
                if name in self.skip or name.split("_", 1)[1] in self.skip:
                    self.say("- %s: skipped" % name)
                    continue
                self.say("- %s: %s" % (name, PLAN[name][0]))
                try:
                    getattr(self, name)()
                except CaptureError as e:
                    self.failed.append((name, str(e)))
                    self.say("  FAILED: %s" % e)
                except Exception as e:                      # one broken step must not hide the others
                    self.failed.append((name, "%s: %s" % (type(e).__name__, e)))
                    self.say("  FAILED: %s: %s" % (type(e).__name__, e))
            self.cleanup(cli)
        self.write_cli_errors()
        self.update_manifest()
        return 1 if self.failed else 0

    def cleanup(self, cli):
        """Best effort: remove the sessions the model calls left in the CLI's own folders."""
        try:
            if cli == "claude" and self.session.get("claude_dir"):
                run_cmd([self.exe["claude"], "purge", "-y", self.session["claude_dir"]], self.env("claude"), timeout=STATUS_TIMEOUT)
            if cli == "codex" and self.session.get("codex_thread"):
                run_cmd([self.exe["codex"], "delete", self.session["codex_thread"]], self.env("codex"), timeout=STATUS_TIMEOUT)
        except Exception as e:
            self.warnings.append("removing the %s session failed (%s); remove it by hand" % (cli, e))

    def probe_server(self, name):
        """-> (script, log): a probe MCP server that appends every request it receives to `log`."""
        script = self.scratch / "probe_mcp_server.py"
        script.write_text(PROBE_SERVER)
        log = self.scratch / ("%s_requests.jsonl" % name)
        log.write_text("")
        return script, log

    def save_mcp_requests(self, rel, log):
        requests = parse_jsonl(log.read_text())
        if not requests:
            self.warnings.append("%s: the CLI never contacted the probe MCP server, so the file was left as it was" % rel)
            return
        for req in requests:
            if req.get("method") == "server/discover":
                req["params"] = "(trimmed)"
        self.write(rel, "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in requests))

    # ---- claude
    def claude_argv(self, *, schema=None, partials=False, session=None, resume=None, extra=()):
        argv = [self.exe["claude"], "-p", "--output-format", "stream-json", "--verbose"]
        if partials:
            argv.append("--include-partial-messages")
        if schema:
            argv += ["--json-schema", json.dumps(schema, separators=(",", ":"))]
        argv += ["--tools", "", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "", "--model", "sonnet", "--effort", "low"]
        if session:
            argv += ["--session-id", session]
        if resume:
            argv += ["--resume", resume]
        return argv + list(extra)

    def claude_help(self):
        env = self.env("claude")
        found = re.search(r"\d+\.\d+\.\d+", run_cmd([self.exe["claude"], "--version"], env, timeout=STATUS_TIMEOUT).stdout)
        self.versions["claude"] = found.group(0) if found else None
        helped = run_cmd([self.exe["claude"], "--help"], env, timeout=STATUS_TIMEOUT)
        if helped.code != 0 or "Usage" not in helped.stdout:
            raise CaptureError("claude --help gave exit %s and no usage text" % helped.code)
        self.write("claude/help.txt", self.scrub.text(helped.stdout))

    def claude_auth_status(self):
        signed_in = run_cmd([self.exe["claude"], "auth", "status"], self.env("claude"), timeout=STATUS_TIMEOUT)
        try:
            doc = json.loads(signed_in.stdout)
        except ValueError:
            raise CaptureError("claude auth status printed no JSON (exit %s)" % signed_in.code)
        if not doc.get("loggedIn"):
            raise CaptureError("claude is not signed in here: sign in with `claude auth login`, then run this again")
        self.scrub.learn_identity(doc)
        self.write("claude/auth_status_signed_in.json", json.dumps(self.scrub.obj(doc), indent=2, ensure_ascii=False) + "\n")
        self.probes["claude_auth_status_signed_in"] = {"argv": ["claude", "auth", "status"], "exit": signed_in.code, "stream": "stdout",
                                                      "body": "claude/auth_status_signed_in.json", "seconds": signed_in.seconds}
        signed_out = run_cmd([self.exe["claude"], "auth", "status"], self.env("claude", empty_config=True), timeout=STATUS_TIMEOUT)
        doc = json.loads(signed_out.stdout)
        if doc.get("loggedIn"):
            raise CaptureError("an empty CLAUDE_CONFIG_DIR still shows a login: the signed-out captures would reach a model, stopping")
        self.write("claude/auth_status_signed_out.json", json.dumps(self.scrub.obj(doc), indent=2, ensure_ascii=False) + "\n")
        self.probes["claude_auth_status_signed_out"] = {"argv": ["claude", "auth", "status"], "env": "empty CLAUDE_CONFIG_DIR", "exit": signed_out.code,
                                                       "stream": "stdout", "body": "claude/auth_status_signed_out.json"}

    def claude_fresh(self):
        work, session = self.workdir("claude-work"), str(uuid.uuid4())
        res = self.call("claude", self.claude_argv(schema=SCHEMA, partials=True, session=session), reaches_model=True,
                        env=self.env("claude"), stdin=PROMPT_FRESH, cwd=work)
        result = stream_result(res.stdout)
        if res.code != 0 or result.get("is_error") or "structured_output" not in result:
            raise CaptureError("the fresh call did not succeed (exit %s, %s)" % (res.code, (result.get("result") or res.stderr)[:120]))
        self.session["claude_id"], self.session["claude_dir"] = session, work
        self.write("claude/stream_structured_ok.jsonl", scrub_stream(res.stdout, self.scrub, fixed_cwd=True))

    def claude_resume(self):
        if "claude_id" not in self.session:
            raise CaptureError("there is no fresh session to resume (claude_fresh did not run or failed)")
        res = self.call("claude", self.claude_argv(resume=self.session["claude_id"]), reaches_model=True, env=self.env("claude"),
                        stdin=PROMPT_RESUME, cwd=self.session["claude_dir"])
        result = stream_result(res.stdout)
        if res.code != 0 or result.get("is_error"):
            raise CaptureError("the resumed call did not succeed (exit %s, %s)" % (res.code, (result.get("result") or res.stderr)[:120]))
        self.write("claude/stream_resume_plain_ok.jsonl", scrub_stream(res.stdout, self.scrub, fixed_cwd=True))

    def claude_without_login(self, what, resume=None, extra=()):
        """A call that must not reach a model: the config directory is empty, so there is no login and nothing is billed."""
        res = self.call("claude", self.claude_argv(resume=resume, extra=extra), reaches_model=False, env=self.env("claude", empty_config=True),
                        stdin=PROMPT_RESUME, cwd=self.workdir("claude-nologin"), timeout=STATUS_TIMEOUT)
        result = stream_result(res.stdout)
        if (result.get("total_cost_usd") or 0) > 0:
            raise CaptureError("the %s call cost money: it reached a model, stopping" % what)
        return res, result

    def claude_signed_out(self):
        res, result = self.claude_without_login("signed-out")
        if not result.get("is_error"):
            raise CaptureError("the signed-out call did not fail: stopping, it may have reached a model")
        self.write("claude/stream_not_logged_in.jsonl", scrub_stream(res.stdout, self.scrub, fixed_cwd=True))

    def claude_resume_unknown(self):
        res, result = self.claude_without_login("unknown-session", resume=UNKNOWN_SESSION)
        if result.get("num_turns") != 0:
            raise CaptureError("the unknown-session call did not fail while loading the session (num_turns %r)" % result.get("num_turns"))
        self.write("claude/stream_resume_unknown_session.jsonl", scrub_stream(res.stdout, self.scrub))
        self.probes["claude_resume_unknown_session"] = probe_doc(res, stdout=None, stdout_fixture="claude/stream_resume_unknown_session.jsonl",
                                                                 stderr=res.stderr.replace(UNKNOWN_SESSION, "<id>"))

    def claude_mcp(self):
        script, log = self.probe_server("claude_mcp")
        config = json.dumps({"mcpServers": {"sutra": {"command": sys.executable, "args": [str(script), str(log)]}}})
        res, _ = self.claude_without_login("mcp", extra=["--mcp-config", config])
        self.write("claude/stream_mcp_server_connected.jsonl", scrub_stream(res.stdout, self.scrub, fixed_cwd=True))
        self.save_mcp_requests("mcp/claude_client_requests.jsonl", log)

    def claude_tool_profile(self):
        script, log = self.probe_server("claude_tool_profile")
        config = self.scratch / "tool_profile_mcp.json"
        config.write_text(json.dumps({"mcpServers": {"sutra": {"command": sys.executable, "args": [str(script), str(log)]}}}))
        config.chmod(0o600)
        res, _ = self.claude_without_login("tool-profile", extra=["--mcp-config", str(config), "--restricted", "--allowedTools", "mcp__sutra__*",
                                                                  "--permission-mode", "dontAsk", "--permission-prompts", "none"])
        self.write("claude/stream_tool_profile_init.jsonl", scrub_stream(res.stdout, self.scrub, fixed_cwd=True))

    def claude_interrupt(self):
        request = json.dumps({"type": "control_request", "request_id": "req_1", "request": {"subtype": "interrupt"}}) + "\n"
        argv = [self.exe["claude"], "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--tools", "",
                "--no-session-persistence", "--model", "sonnet", "--effort", "low"]
        res = self.call("claude", argv, reaches_model=False, env=self.env("claude", empty_config=True), stdin=request,
                        cwd=self.workdir("claude-nologin"), timeout=STATUS_TIMEOUT)
        replies = [o for o in parse_jsonl(res.stdout) if o.get("type") == "control_response"]
        if not replies:
            raise CaptureError("claude answered no control_request (exit %s)" % res.code)
        self.write("claude/control_interrupt_response.jsonl", json.dumps(self.scrub.obj(replies[0]), separators=(",", ":")) + "\n")

    def error_probes(self, cli, cases):
        """cases: id -> (argv, {real value: label in argv}, {real value: label in stderr}). Every command must fail, which also shows
        that it reached no model."""
        env, work = self.env(cli, empty_config=True), self.workdir("%s-nologin" % cli)
        for pid, (argv, in_argv, in_stderr) in cases.items():
            res = self.call(cli, argv, reaches_model=False, env=env, stdin="", cwd=work, timeout=STATUS_TIMEOUT)
            if res.code == 0:
                raise CaptureError("%s: the command succeeded, so it may have reached a model" % pid)
            stderr = res.stderr
            for real, label in in_stderr.items():
                stderr = stderr.replace(real, label)
            self.probes[pid] = probe_doc(res, stderr=stderr, argv=[cli] + [in_argv.get(a, a) for a in argv[1:]])

    def claude_errors(self):
        exe, missing = self.exe["claude"], str(self.scratch / "no-such-system-prompt.txt")
        self.error_probes("claude", {
            "claude_unknown_option": ([exe, "-p", "hi", "--no-such-flag"], {}, {}),
            "claude_invalid_json_schema": ([exe, "-p", "hi", "--output-format", "stream-json", "--verbose", "--json-schema", "{not json"], {}, {}),
            "claude_system_prompt_file_missing": ([exe, "-p", "hi", "--output-format", "json", "--tools", "", "--no-session-persistence",
                                                   "--system-prompt-file", missing], {missing: "<missing file>"}, {missing: "<path>"}),
        })

    # ---- codex
    def codex_argv(self, *, workdir, schema_file=None, resume=None, extra=()):
        argv = [self.exe["codex"], "exec"] + (["resume"] if resume else []) + ["--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"]
        if not resume:
            argv += ["-s", "read-only", "-C", workdir]
        argv += ["-m", "gpt-5.6-luna", "-c", 'model_reasoning_effort="low"']
        if resume:
            argv += ["-c", 'sandbox_mode="read-only"']
        if schema_file:
            argv += ["--output-schema", schema_file]
        return argv + list(extra) + ([resume] if resume else []) + ["-"]

    def codex_help(self):
        env = self.env("codex")
        found = re.search(r"\d+\.\d+\.\d+", run_cmd([self.exe["codex"], "--version"], env, timeout=STATUS_TIMEOUT).stdout)
        self.versions["codex"] = found.group(0) if found else None
        for argv, rel in (([self.exe["codex"], "exec", "--help"], "codex/exec_help.txt"), ([self.exe["codex"], "exec", "resume", "--help"], "codex/exec_resume_help.txt")):
            res = run_cmd(argv, env, timeout=STATUS_TIMEOUT)
            if res.code != 0 or "Usage" not in res.stdout:
                raise CaptureError("%s gave exit %s and no usage text" % (" ".join(argv[1:]), res.code))
            self.write(rel, self.scrub.text(res.stdout))

    def codex_login_status(self):
        for pid, empty in (("codex_login_status_signed_in", False), ("codex_login_status_signed_out", True)):
            res = run_cmd([self.exe["codex"], "login", "status"], self.env("codex", empty_config=empty), timeout=STATUS_TIMEOUT)
            if empty and res.code == 0:
                raise CaptureError("an empty CODEX_HOME still shows a login: the signed-out captures would reach a model, stopping")
            if not empty and res.code != 0:
                raise CaptureError("codex is not signed in here: use `codex login`, then run this again")
            doc = {"id": pid, "argv": ["codex", "login", "status"], "exit": res.code, "stream": "stderr" if res.stderr.strip() else "stdout",
                   "stdout": res.stdout.strip(), "stderr": res.stderr.strip(), "seconds": res.seconds}
            if empty:
                doc["env"] = "empty CODEX_HOME"
            self.probes[pid] = doc

    def codex_fresh(self):
        work = self.workdir("codex-work")
        schema = self.scratch / "schema.json"
        schema.write_text(json.dumps(SCHEMA))
        schema.chmod(0o600)
        res = self.call("codex", self.codex_argv(workdir=work, schema_file=str(schema)), reaches_model=True, env=self.env("codex"), stdin=PROMPT_FRESH, cwd=work)
        events = parse_jsonl(res.stdout)
        thread = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), None)
        if res.code != 0 or not thread or not any(e.get("type") == "turn.completed" for e in events):
            raise CaptureError("the fresh call did not complete (exit %s): %s" % (res.code, res.stderr[:120]))
        self.session["codex_thread"], self.session["codex_dir"] = thread, work
        self.write("codex/exec_structured_ok.jsonl", scrub_stream(res.stdout, self.scrub))

    def codex_resume(self):
        if "codex_thread" not in self.session:
            raise CaptureError("there is no fresh thread to resume (codex_fresh did not run or failed)")
        res = self.call("codex", self.codex_argv(workdir=self.session["codex_dir"], resume=self.session["codex_thread"]), reaches_model=True,
                        env=self.env("codex"), stdin=PROMPT_RESUME, cwd=self.session["codex_dir"])
        if res.code != 0 or not any(e.get("type") == "turn.completed" for e in parse_jsonl(res.stdout)):
            raise CaptureError("the resumed call did not complete (exit %s): %s" % (res.code, res.stderr[:120]))
        self.write("codex/exec_resume_plain_ok.jsonl", scrub_stream(res.stdout, self.scrub))

    def codex_rollout(self):
        thread = self.session.get("codex_thread")
        if not thread:
            raise CaptureError("there is no thread whose rollout file could be read")
        home = Path(self.environ.get("CODEX_HOME") or Path(self.environ.get("HOME") or Path.home()) / ".codex")
        files = sorted(home.glob("sessions/*/*/*/rollout-*-%s.jsonl" % thread))
        if not files:
            raise CaptureError("no rollout file for thread %s under %s" % (thread, home))
        counts = [o for o in parse_jsonl(files[0].read_text()) if (o.get("payload") or {}).get("type") == "token_count"]
        if not counts:
            raise CaptureError("the rollout file holds no token_count line")
        self.write("codex/rollout_token_count.jsonl", "".join(json.dumps(self.scrub.obj({"timestamp": c.get("timestamp"), "payload": c["payload"]}),
                                                                         separators=(",", ":")) + "\n" for c in counts))

    def codex_without_login(self, what, extra=()):
        """A call that must not reach a model: the CODEX_HOME is empty, so every request is answered 401."""
        work = self.workdir("codex-nologin")
        res = self.call("codex", self.codex_argv(workdir=work, extra=extra), reaches_model=False, env=self.env("codex", empty_config=True),
                        stdin=PROMPT_RESUME, cwd=work, timeout=SIGNED_OUT_TIMEOUT)
        events = parse_jsonl(res.stdout)
        if not any(e.get("type") == "turn.failed" for e in events) or any(e.get("type") == "turn.completed" for e in events):
            raise CaptureError("the %s call did not fail with turn.failed: stopping, it may have reached a model" % what)
        return res

    def codex_signed_out(self):
        res = self.codex_without_login("signed-out")
        self.write("codex/exec_not_signed_in.jsonl", scrub_stream(res.stdout, self.scrub))

    def codex_device_auth(self):
        out, _ = run_until([self.exe["codex"], "login", "--device-auth"], self.env("codex", empty_config=True), r"[A-Z0-9]{4}-[A-Z0-9]{5}", timeout=30)
        if not re.search(r"https://\S+", out):
            raise CaptureError("the device sign-in printed no link")
        self.write("codex/login_device_auth.txt", scrub_device_code(self.scrub.text(out)))

    def codex_models(self):
        res = run_cmd([self.exe["codex"], "debug", "models"], self.env("codex"), timeout=STATUS_TIMEOUT)
        try:
            doc = json.loads(res.stdout)
        except ValueError:
            raise CaptureError("codex debug models printed no JSON (exit %s)" % res.code)
        self.write("codex/models_excerpt.json", json.dumps(strip_models(doc), indent=1, ensure_ascii=False) + "\n")

    def codex_mcp(self):
        script, log = self.probe_server("codex_mcp")
        self.codex_without_login("mcp", extra=["-c", "mcp_servers.sutra.command=%s" % json.dumps(sys.executable),
                                               "-c", "mcp_servers.sutra.args=%s" % json.dumps([str(script), str(log)])])
        self.save_mcp_requests("mcp/codex_client_requests.jsonl", log)

    def codex_errors(self):
        exe = self.exe["codex"]
        bad_json, absent, absent_dir = (str(self.scratch / n) for n in ("bad-schema.json", "no-such-schema.json", "no-such-dir"))
        Path(bad_json).write_text("{not json")
        self.error_probes("codex", {
            "codex_unknown_argument": ([exe, "exec", "--no-such-flag", "hi"], {}, {}),
            "codex_output_schema_file_invalid": ([exe, "exec", "--output-schema", bad_json, "hi"], {bad_json: "<file with {not json>"}, {bad_json: "<file>"}),
            "codex_output_schema_file_missing": ([exe, "exec", "--output-schema", absent, "hi"], {absent: "<missing file>"}, {absent: "<file>"}),
            "codex_missing_working_directory": ([exe, "exec", "-C", absent_dir, "hi"], {absent_dir: "<missing dir>"}, {}),
            "codex_resume_unknown_thread": ([exe, "exec", "resume", "--json", UNKNOWN_SESSION, "-"], {UNKNOWN_SESSION: "<unknown uuid>"}, {UNKNOWN_SESSION: "<id>"}),
        })

    # ---- the bookkeeping files
    def write_cli_errors(self):
        """Merge the probes into cli_errors.json by id; the entries and sections this run did not reproduce stay as they are."""
        if not self.probes:
            return
        path = self.out / "cli_errors.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"captured_with": [], "date": "", "probes": [], "signals": [], "verified_flags": {}}
        by_id = {p["id"]: p for p in doc.get("probes", [])}
        for pid, fresh in self.probes.items():
            merged = dict(by_id.get(pid, {"id": pid}))
            merged.update(self.scrub.obj(fresh))
            merged = {k: v for k, v in merged.items() if v is not None}
            by_id[pid] = merged
        doc["probes"] = list(by_id.values())
        doc["date"] = time.strftime("%Y-%m-%d")
        seen = [("claude %s" % self.versions["claude"]) if self.versions.get("claude") else None,
                ("codex-cli %s" % self.versions["codex"]) if self.versions.get("codex") else None]
        if any(seen):
            doc["captured_with"] = [v for v in seen if v]
        self.write("cli_errors.json", json.dumps(doc, indent=1, ensure_ascii=False) + "\n")

    def update_manifest(self):
        path = self.out / "MANIFEST.json"
        if not path.exists() or not any(self.versions.values()):
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = {"claude": "claude ", "codex": "codex-cli "}
        for entry in data["files"]:
            if entry.get("origin") == "captured":
                for cli, label in labels.items():
                    if self.versions.get(cli):
                        entry["cli"] = re.sub(re.escape(label) + r"\d+\.\d+\.\d+", label + self.versions[cli], entry.get("cli", ""))
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        self.say("updated the CLI versions in MANIFEST.json")

    def report(self):
        self.say("")
        self.say("wrote %d files; model calls: %s" % (len(self.written), ", ".join("%s %d" % kv for kv in sorted(self.model_calls.items()))))
        for line in self.warnings:
            self.say("warning: %s" % line)
        for name, why in self.failed:
            self.say("FAILED %s: %s" % (name, why))
        self.say("not regenerated (derived and handwritten fixtures): re-check their wording against the new captures; MANIFEST.json lists them")

    def close(self):
        shutil.rmtree(str(self.scratch), ignore_errors=True)


def plan_text():
    lines = ["Steps (at most %d calls per CLI reach a model):" % MAX_MODEL_CALLS]
    for cli in ("claude", "codex"):
        for name in STEPS[cli]:
            what, writes, calls = PLAN[name]
            lines.append("  %-22s %s -> %s%s" % (name, what, writes, "   [%d model call]" % calls if calls else ""))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Refresh tests/fixtures/connectors from the real CLIs (needs SUTRA_LIVE=1).")
    ap.add_argument("--only", choices=("claude", "codex"))
    ap.add_argument("--skip", default="", help="comma list of step names (claude_mcp) or step suffixes (mcp) to skip")
    ap.add_argument("--out", default=str(FIXTURES))
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--codex", default="codex")
    ap.add_argument("--pass-env", default="", help="more environment variable names to forward to the CLIs (the tests use it for the fakes)")
    ap.add_argument("--keep-scratch", action="store_true", help="keep the scratch directory (it is removed when every step succeeded)")
    ap.add_argument("--plan", action="store_true", help="print the steps and exit")
    args = ap.parse_args(argv)
    if args.plan:
        print(plan_text())
        return 0
    if os.environ.get("SUTRA_LIVE") != "1":
        print("This runs the real claude and codex on your logins (at most %d model calls each). Set SUTRA_LIVE=1 to go ahead, "
              "or use --plan to see what it would do." % MAX_MODEL_CALLS, file=sys.stderr)
        return 2
    cap = Capture(args.out, args.claude, args.codex, args.only, [s for s in args.skip.split(",") if s], [s for s in args.pass_env.split(",") if s])
    code = cap.run()
    cap.report()
    if code == 0 and not args.keep_scratch:
        cap.close()
    else:
        print("scratch directory kept at %s" % cap.scratch)
    return code


if __name__ == "__main__":
    sys.exit(main())
