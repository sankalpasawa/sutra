"""LLM wrapper: Claude or Gemini, with an offline mock mode (STUDIO_MOCK=1 or no API key).

Provider pick: STUDIO_PROVIDER=claude-cli uses the local `claude -p` on the Claude subscription (as the Sutra
repo does: ANTHROPIC_API_KEY is removed from its environment so it never bills the API). Otherwise
ANTHROPIC_API_KEY wins if set, else GEMINI_API_KEY, else mock.
Replies are streamed so the UI can show progress; pass on_progress(event) to receive:
  {"chars": int, "text": str}                      as text arrives
  {"note": str}                                    retries and model switches
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time



def _load_env_file():
    """Read KEY=value lines from .env next to this file. Variables already set in the shell win."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if value and not os.getenv(key):
                os.environ[key] = value


_load_env_file()

if os.getenv("STUDIO_PROVIDER") == "claude-cli":
    PROVIDER = "claude-cli"
    MODEL = os.getenv("CLAUDE_CLI_MODEL", "sonnet")   # alias; the CLI resolves it to the current Sonnet
elif os.getenv("ANTHROPIC_API_KEY"):
    PROVIDER = "anthropic"
    MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
elif os.getenv("GEMINI_API_KEY"):
    PROVIDER = "gemini"
    # Comma-separated fallback list: if one model is busy or out of quota, the next is tried.
    MODELS = [m.strip() for m in os.getenv("GEMINI_MODEL", "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite").split(",")
              if m.strip()]
    MODEL = MODELS[0]
else:
    PROVIDER, MODEL = None, None
MOCK = os.getenv("STUDIO_MOCK") == "1" or PROVIDER is None
MOCK_DELAY = float(os.getenv("STUDIO_MOCK_DELAY", "0"))  # seconds per mock reply, to try the progress UI
# Optional Gemini thinking cap for short JSON replies (routing, spec, review). Off by default: a 512 cap
# coincided with replies cut off mid-JSON on 2026-09-29. Set GEMINI_LOW_THINKING=512 to try it again.
LOW_THINKING_BUDGET = int(os.getenv("GEMINI_LOW_THINKING", "0")) or None
LAST_META = {}  # model, finish reason and token counts of the latest Gemini reply, saved with failed replies
_client = None
# Whether a provider's model can open files (the run folder) during a call. None can: claude-cli runs with --tools ""
# in the temp folder, the Anthropic and Gemini calls send no tools. Set one True only when it gets a file-read tool.
READS_FILES = {"claude-cli": False, "anthropic": False, "gemini": False}


def can_read_files():
    """True when the current provider can read a file a prompt points to (a cut input's full text)."""
    return not MOCK and READS_FILES.get(PROVIDER, False)


# Whether a provider can give one call tools that work in a folder (ask(tools=...), J2_AGENT_TOOLS). Only claude-cli:
# the Anthropic and Gemini calls would need their own tool loop. Which tools, and the permission rules, come only from
# the caller (a form's data in artifacts/types.json); nothing here names a tool.
TOOLS = {"claude-cli": True, "anthropic": False, "gemini": False}
TOOL_KEYS = ("tools", "allow", "cwd", "root", "usd", "log_chars")
# The CLI's own sandbox for every command a tool runs: writes only in the builder's folder, reads fenced to that folder
# and the system paths outside the home folder (the repo's .env, ~/.ssh and every other run are under it), no way out.
# The network is whatever the caller's permission rules open (types.json "builder_tools": a WebFetch domain rule also
# opens the sandbox's host list). Measured 2026-11-12 (tools/agent_tools_smoke.py): writes outside the folder are
# refused; a folder under the CLI's own temp folder (/private/tmp/claude-<uid>) is not protected, so a builder folder
# must resolve inside the run folder ("root"), checked before every call.
# SECURITY: the sandbox is what confines the command tool. The allow-list is not a security boundary: a rule for a
# runner lets that runner run any code. Never run a tools call without cli_settings, and never run a builder's code
# anywhere else (J2 reads the test result from the CLI's record).
CLI_SANDBOX = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False}}


def cli_settings(tools):
    """The --settings of one tools call: CLI_SANDBOX with reads fenced (home folder denied, the builder's folder and
    any extra folder allowed back), writes only in the folder (and the extra one), the caller's rules as allow rules,
    and the file tools refused outside the working folders."""
    folders = [os.path.realpath(tools["cwd"])] + [os.path.realpath(x) for x in tools.get("extra") or []]
    sb = {**CLI_SANDBOX["sandbox"], "filesystem": {"denyRead": ["~/"], "allowRead": folders, "allowWrite": folders}}
    return {"sandbox": sb, "permissions": {"allow": list(tools["allow"]), "additionalDirectories": folders[1:],
                                           "blockReadsOutsideWorkingDirectories": True}}


def tools_on():
    """Builders get tools unless J2_AGENT_TOOLS=0; offline (mock) only when J2_AGENT_TOOLS=1."""
    return (os.getenv("J2_AGENT_TOOLS") or ("0" if MOCK else "1")) == "1"


def can_use_tools():
    """True when the current provider can run a call with tools in a folder."""
    return not MOCK and TOOLS.get(PROVIDER, False)


def inside(path, root):
    """True when path resolves (symlinks followed) to a folder strictly inside root."""
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p != r and p.startswith(r.rstrip(os.sep) + os.sep)


def _tool_problems(tools):
    """Why a tools request can't be run ([] when it can): every key given, the lists not empty, the folder there and
    inside the run folder (root) once symlinks are resolved."""
    out = [f"tools needs {k}" for k in TOOL_KEYS if tools.get(k) in (None, "", [])]
    if not out and not os.path.isdir(tools["cwd"]):
        out.append(f"tools cwd {tools['cwd']} is not a folder")
    elif not out and not inside(tools["cwd"], tools["root"]):
        out.append(f"tools cwd {tools['cwd']} does not resolve inside the run folder {tools['root']}")
    return out


class CallTimeout(RuntimeError):
    """A call ran past its time limit and was stopped: its reply, if one ever comes, is never returned."""


def ask(system, user, mock, max_tokens=1500, effort="high", on_progress=None, json_mode=False, images=None,
        schema=None, timeout=None, tools=None):
    """effort="low" caps Gemini thinking; use it for short structured replies.
    json_mode=True makes Gemini return a JSON object only (Claude follows the prompt's format).
    images: PNG paths sent with the prompt (Audit's screenshots); every provider takes them, mock ignores them.
    schema: a JSON Schema the reply must follow (J2_ARTIFACT_SCHEMA=1). claude-cli sends it with --json-schema and
    reads structured_output; the Anthropic API uses output_config's json_format; Gemini gets response_schema when
    the schema is simple enough, else the schema in the prompt and code validates it. The reply is still returned as
    the JSON text, so nothing downstream changes. LAST_META["structured"] records what the provider did.
    timeout: seconds; past it the call is stopped (claude-cli: the process is killed; the streaming APIs: the request
    times out or the stream is closed) and CallTimeout is raised. Mock ignores it.
    tools: None (every call today: no tools) or {"tools": [names], "allow": [permission rules], "cwd": folder,
    "root": the run folder cwd must resolve inside, "usd": cost limit, "log_chars": longest string kept in the tool
    log}, all from the caller's data and settings. Other keys are ignored.
    The call then runs in that folder with those tools only; LAST_META gets "tool_calls" (name, input, ok), "usd"
    and "stop". Mock ignores it; a provider without tools (TOOLS) raises RuntimeError."""
    images = [p for p in images or [] if p and os.path.exists(p)]
    progress = on_progress or (lambda e: None)
    LAST_META.clear()   # each provider fills in what it reports (tokens included); mock reports nothing
    if tools is not None and (bad := _tool_problems(tools)):
        raise ValueError("; ".join(bad))
    if MOCK:
        return _stream_mock(mock(), progress)
    if tools is not None and not TOOLS.get(PROVIDER, False):
        raise RuntimeError(f"{PROVIDER} can't run a call with tools (llm.TOOLS)")
    if not timeout:
        return _ask(system, user, max_tokens, effort, progress, json_mode, images, schema, None, tools)
    deadline = time.time() + timeout
    try:
        return _ask(system, user, max_tokens, effort, progress, json_mode, images, schema, deadline, tools)
    except CallTimeout:
        raise
    except Exception as e:      # an SDK's own timeout error, or anything else that ends past the deadline
        if time.time() >= deadline:
            raise CallTimeout(f"stopped after {timeout:g}s ({type(e).__name__})") from e
        raise


def _check_deadline(deadline):
    if deadline and time.time() >= deadline:
        raise CallTimeout("time limit reached while streaming")


def _ask(system, user, max_tokens, effort, progress, json_mode, images, schema, deadline, tools=None):
    if PROVIDER == "gemini":
        return _ask_gemini(system, user, max_tokens, effort, progress, json_mode, images, schema, deadline)
    if PROVIDER == "claude-cli":
        return _ask_claude_cli(system, user, effort, progress, images, schema, deadline, tools)
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    text = ""
    extra = {"output_config": {"format": {"type": "json_schema", "schema": schema}}} if schema else {}
    if deadline:
        extra["timeout"] = max(0.1, deadline - time.time())
    with _client.messages.stream(model=MODEL, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": _blocks(user, images)}], **extra) as stream:
        for piece in stream.text_stream:
            _check_deadline(deadline)
            text += piece
            progress({"chars": len(text), "text": text})
        usage = stream.get_final_message().usage
    LAST_META.update(model=MODEL, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)
    if schema:
        LAST_META["structured"] = {"provider": "anthropic", "subtype": "success", "present": bool(text.strip())}
    return text.strip()


def _blocks(user, images):
    """Anthropic message content: the images first, then the prompt text."""
    if not images:
        return user
    out = []
    for path in images:
        with open(path, "rb") as f:
            out.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(f.read()).decode()}})
    return out + [{"type": "text", "text": user}]


def _ask_claude_cli(system, user, effort, progress, images=None, schema=None, deadline=None, tools=None):
    """One non-interactive `claude -p` call with no tools, MCP, skills or settings: a plain completion.
    The CLI has no max-tokens flag, so the reply format in the prompt is what keeps replies short.
    With images the prompt goes in as one stream-json user message (image blocks + text) and the result line is read
    from the stream-json output.
    With tools (ask's tools): only the caller's tools and permission rules, run in its folder: --restricted keeps the
    file tools in the folder and loads no user or project settings, --safe-mode loads no CLAUDE.md, hooks or plugins,
    dontAsk refuses anything the rules don't allow, the sandbox (cli_settings) keeps commands' writes in the folder and
    their reads out of the home folder, the network is what the rules open, --max-budget-usd stops the call past the cost limit (checked after each turn, so one turn may
    go over). The output is stream-json, so every tool call is read back."""
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}
    io = ((["--input-format", "stream-json"] if images else [])
          + (["--output-format", "stream-json", "--verbose"] if images or tools else ["--output-format", "json"]))
    tool_args = ["--tools", ""] if tools is None else [
        "--tools", ",".join(tools["tools"]), "--allowedTools", " ".join(tools["allow"]), "--restricted", "--safe-mode",
        "--permission-mode", "dontAsk", "--permission-prompts", "none", "--settings", json.dumps(cli_settings(tools)),
        "--max-budget-usd", f"{float(tools['usd']):g}"]
    # A long system prompt goes in a temporary file: Windows refuses a command line over 32,767 characters (WinError 206)
    sysfile = None
    if len(system) > 20000:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(system)
            sysfile = f.name
    cmd = ["claude", "-p", *io, *(["--system-prompt-file", sysfile] if sysfile else ["--system-prompt", system]),
           *tool_args, "--model", MODEL,
           "--effort", "low" if effort == "low" else "high", "--no-session-persistence", "--strict-mcp-config",
           "--disable-slash-commands", "--setting-sources", ""]
    if schema:      # structured output: Claude Code validates the schema, then returns the object in structured_output
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    try:
        return _run_claude_cli(cmd, images, user, env, progress, schema, deadline, tools)
    finally:
        if sysfile:
            try:
                os.remove(sysfile)
            except OSError:
                pass


def _cli_meta(d):
    """What `claude -p` reports about one call, kept with it (the structured-output verdict is added by the caller)."""
    keep = {k: LAST_META[k] for k in ("structured", "tool_calls", "usd", "denied", "stop") if k in LAST_META}
    LAST_META.clear()
    u = d.get("usage") or {}
    LAST_META.update(model=next(iter(d.get("modelUsage") or {}), MODEL), duration_ms=d.get("duration_ms"),
                     input_tokens=(u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                     + (u.get("cache_creation_input_tokens") or 0) if u else None,
                     output_tokens=u.get("output_tokens"), usd=d.get("total_cost_usd"))
    LAST_META.update(keep)


def _short(v, limit):
    """v for the tool log: a string longer than limit becomes its length and sha256 (a file's whole text stays in
    the file), dicts and lists item by item."""
    if isinstance(v, str) and len(v) > limit:
        return {"chars": len(v), "sha256": hashlib.sha256(v.encode("utf-8")).hexdigest()}
    if isinstance(v, dict):
        return {k: _short(x, limit) for k, x in v.items()}
    if isinstance(v, list):
        return [_short(x, limit) for x in v]
    return v


def _stream_lines(text):
    out = []
    for x in (text or "").splitlines():
        if x.strip().startswith("{"):
            try:
                out.append(json.loads(x))
            except ValueError:
                pass
    return out


def _tool_meta(lines, tools, d, stop=None):
    """LAST_META's tool record of one call: every tool call as the CLI reported it (name, input, ok), in order, the
    cost the CLI reports, how many calls its rules refused, and why it stopped (done, budget, timeout, or the CLI's
    own subtype)."""
    calls, by_id = [], {}
    for x in lines:
        m = x.get("message")      # a system event's message is a string
        content = m.get("content") if isinstance(m, dict) else None
        for c in content if isinstance(content, list) else []:
            if not isinstance(c, dict):
                continue
            if x.get("type") == "assistant" and c.get("type") == "tool_use":
                by_id[c.get("id")] = {"n": len(calls) + 1, "name": c.get("name"),
                                      "input": _short(c.get("input"), int(tools["log_chars"])), "ok": None}
                calls.append(by_id[c.get("id")])
            elif x.get("type") == "user" and c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                by_id[c["tool_use_id"]]["ok"] = not c.get("is_error")
    sub = d.get("subtype")
    LAST_META.update(tool_calls=calls, usd=d.get("total_cost_usd"), denied=len(d.get("permission_denials") or []),
                     stop=stop or ("done" if sub == "success" else "budget" if sub == "error_max_budget_usd"
                                   else sub or "no result"))


def _run_claude_cli(cmd, images, user, env, progress, schema=None, deadline=None, tools=None):
    stdin = (json.dumps({"type": "user", "message": {"role": "user", "content": _blocks(user, images)}}) + "\n"
             if images else user)
    last = None
    # a call with tools is run once: a retry would start over on the files the first one wrote (the caller decides)
    for attempt in range(1 if tools else 2):
        if deadline and time.time() >= deadline:
            raise CallTimeout("time limit reached before the CLI retry")
        try:
            # subprocess.run kills the process on timeout, so a stopped call can never reply later
            p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env,
                               timeout=max(0.1, deadline - time.time()) if deadline else 900,
                               cwd=tools["cwd"] if tools else tempfile.gettempdir())
            lines = []
            if images or tools:   # stream-json: one JSON event per line; the reply is the "result" event
                lines = _stream_lines(p.stdout)
                d = next((x for x in reversed(lines) if x.get("type") == "result"), {})
            else:
                d = json.loads(p.stdout or "{}")
            if tools:
                _tool_meta(lines, tools, d)
            sub = d.get("subtype")
            if schema:
                so = d.get("structured_output")
                ok = p.returncode == 0 and sub == "success" and not d.get("is_error") and so is not None
                err = (p.stderr or "").strip()[:300]
                LAST_META["structured"] = {"provider": "claude-cli", "subtype": sub, "present": so is not None,
                                           "exit": p.returncode, **({"stderr": err} if err else {})}
                if not ok:
                    # The whole verdict, so a CLI that never called the model (a refused --json-schema: exit 1, no
                    # stdout, the reason on stderr) is never reported as a bare "subtype None"
                    why = (f"exit {p.returncode}, "
                           + ("no stdout" if not (p.stdout or "").strip() else
                              f"subtype {sub!r}" if sub != "success" else "no structured_output in the reply")
                           + (f", stderr: {err}" if err else ""))
                    last = RuntimeError(f"claude -p structured output failed: {why}")
                    progress({"note": f"{last}; retrying" if attempt == 0 else str(last)})
                    continue
                text = json.dumps(so, ensure_ascii=False)
                _cli_meta(d)
                progress({"chars": len(text), "text": text})
                return text
            if p.returncode == 0 and not d.get("is_error") and (d.get("result") or "").strip():
                text = d["result"].strip()
                _cli_meta(d)
                progress({"chars": len(text), "text": text})
                return text
            last = RuntimeError(f"claude -p failed (exit {p.returncode}): {(d.get('result') or p.stderr)[:300]}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            if tools and isinstance(e, subprocess.TimeoutExpired):      # the tool calls made before the kill
                out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else e.stdout
                _tool_meta(_stream_lines(out), tools, {}, stop="timeout")
            if deadline and isinstance(e, subprocess.TimeoutExpired):
                raise CallTimeout("claude -p killed at the time limit") from e
            last = RuntimeError(f"claude -p failed: {type(e).__name__}")
        progress({"note": f"{last}; retrying" if attempt == 0 else str(last)})
    raise last


def _stream_mock(text, progress):
    steps = 30 if MOCK_DELAY else 1
    for i in range(1, steps + 1):
        part = text[:len(text) * i // steps]
        progress({"chars": len(part), "text": part})
        if MOCK_DELAY:
            time.sleep(MOCK_DELAY / steps)
    return text


def _simple_schema(schema):
    """True when a schema has no $ref, no definitions and no type lists: Gemini's response_schema takes those only."""
    t = json.dumps(schema or {})
    return "$ref" not in t and "definitions" not in t and '"type": [' not in t


def _ask_gemini(system, user, max_tokens, effort, progress, json_mode=False, images=None, schema=None, deadline=None):
    global _client
    from google import genai
    from google.genai import errors, types
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY
    # Gemini's thinking tokens count against max_output_tokens, so the config adds headroom below.
    thinking = (types.ThinkingConfig(thinking_budget=LOW_THINKING_BUDGET)
                if effort == "low" and LOW_THINKING_BUDGET else None)
    last = None
    # Busy (503) or out of quota (429): switch to the next model at once instead of waiting on the same one.
    # One short pause between rounds; two rounds at most.
    for rnd in range(2):
        for model in MODELS:
            _check_deadline(deadline)
            config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens + 8192,
                                                 thinking_config=thinking,
                                                 http_options=types.HttpOptions(timeout=max(1000, int(
                                                     (deadline - time.time()) * 1000))) if deadline else None,
                                                 response_mime_type="application/json" if json_mode else None)
            try:
                text, finish, usage = "", None, None
                contents = user
                if images:
                    contents = [types.Part.from_bytes(data=open(p, "rb").read(), mime_type="image/png") for p in images] \
                        + [user]
                for chunk in _client.models.generate_content_stream(model=model, contents=contents, config=config):
                    _check_deadline(deadline)
                    text += chunk.text or ""
                    if chunk.candidates and chunk.candidates[0].finish_reason:
                        finish = chunk.candidates[0].finish_reason
                    usage = chunk.usage_metadata or usage
                    progress({"chars": len(text), "text": text})
                finish = getattr(finish, "name", finish)
                LAST_META.clear()
                LAST_META.update(model=model, finish=finish, thinking_budget=LOW_THINKING_BUDGET if thinking else None,
                                 json_mode=json_mode, max_output_tokens=config.max_output_tokens,
                                 input_tokens=getattr(usage, "prompt_token_count", None),
                                 output_tokens=getattr(usage, "candidates_token_count", None),
                                 thinking_tokens=getattr(usage, "thoughts_token_count", None))
                if finish not in (None, "STOP"):  # cut off (MAX_TOKENS), blocked (SAFETY), etc.
                    progress({"note": f"{model} stopped early: {finish}"})
                if not text.strip():
                    raise EmptyReply(f"{model} returned no text (finish reason: {finish})")
                return text.strip()
            except errors.APIError as e:
                if e.code == 400 and thinking is not None and "thinking" in str(e).lower():
                    # This model does not accept a thinking budget; retry without one.
                    progress({"note": f"{model} rejected the thinking budget, retrying without it"})
                    return _ask_gemini(system, user, max_tokens, "high", progress, json_mode, images, schema,
                                       deadline)
                if e.code not in (404, 429, 500, 503):
                    raise
                last = e
                reason = {404: "not available", 429: "out of quota"}.get(e.code, "busy")
                progress({"note": f"{model} is {reason} ({e.code}), trying the next option"})
        if rnd == 0:
            progress({"note": "All models busy, retrying in 4s"})
            time.sleep(4)
    raise last


class EmptyReply(RuntimeError):
    pass


def extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise ValueError("no JSON object in reply")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        # A reply cut short or missing its last brace (runs/j2-20261013-185235: the whole proposal became a 400-char
        # "say"): close the open string and brackets and try once more; still bad -> the caller's fallback.
        return json.loads(close_json(text[start:]))


def close_json(s):
    """s with its unclosed string and brackets closed, in order."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            esc, in_str = (not esc and ch == "\\"), in_str and not (ch == '"' and not esc)
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    return s.rstrip().rstrip(",") + ('"' if in_str else "") + "".join(reversed(stack))


def extract_html(text):
    m = re.search(r"```html\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    i = text.lower().find("<!doctype")
    if i == -1:
        i = text.lower().find("<html")
    if i == -1:
        raise ValueError("no HTML in reply")
    return text[i:].strip()


def partial_html(text):
    """HTML written so far in a streaming reply (for the live preview), or '' if none yet."""
    low = text.lower()
    i = low.find("<!doctype")
    if i == -1:
        i = low.find("<html")
    if i == -1:
        return ""
    html = text[i:]
    end = html.find("```")
    return html[:end] if end != -1 else html
