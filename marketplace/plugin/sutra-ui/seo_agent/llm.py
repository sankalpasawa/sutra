"""llm.py — the one place a model gets called.

Everything else in the app talks to this file, so swapping provider is a change
here and nowhere else. Three providers, tried in a fixed order:

    claude-cli   the `claude` binary on this machine, billed to the user's Claude
                 subscription. Chosen first whenever it is installed, unless
                 SEO_AGENT_NO_CLI=1 switches it off.
    anthropic    the API, when an anthropic_key is saved in Connections.
    openai       the API, when an openai_key is saved in Connections.

Tool calling is normalised: whatever the provider returns comes back as a plain
list of {id, name, input}, and tool results go back as a plain list. Nothing
above this file knows which provider answered.
"""
import json
import os
import shutil
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


def provider():
    """"claude-cli" | "anthropic" | "openai" | None, in that order of preference."""
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
CLI_TOOL_RULE = ("Reply with text and zero or more tool_calls. When you call tools, keep "
                 "text to one short sentence. When you have nothing more to do, return an "
                 "empty tool_calls list.")

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


def _cli_command(binary, system, tools, model):
    cmd = [binary, "-p", "--output-format", "json", "--no-session-persistence",
           "--tools", "", "--setting-sources", "", "--strict-mcp-config",
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


def _claude_cli(system, messages, tools, binary, model, on_retry=None):
    cmd = _cli_command(binary, system, tools, model)
    prompt = _cli_prompt(messages)
    attempts = 1 + len(CLI_RETRY_SLEEPS)
    for attempt in range(attempts):
        try:
            return _claude_cli_once(cmd, prompt, binary)
        except ModelError as e:
            if attempt + 1 < attempts and _transient(str(e)):
                wait = CLI_RETRY_SLEEPS[attempt]
                if on_retry:
                    # A silent minute looks like a hang. Say what is happening, in the log.
                    try:
                        on_retry("The model was unavailable (%s). Waiting %ds and trying again, "
                                 "attempt %d of %d." % (str(e).replace("Claude CLI returned an error: ", "")[:90],
                                                        wait, attempt + 2, attempts))
                    except Exception:
                        pass
                time.sleep(wait)
                continue
            raise


def _claude_cli_once(cmd, prompt, binary):
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           timeout=CLI_TIMEOUT, env=_cli_env())
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI gave no answer within %d seconds." % int(CLI_TIMEOUT))
    except OSError as e:
        raise RuntimeError("Could not start the Claude CLI at %s: %s" % (binary, e))

    out = (p.stdout or "").strip()
    try:
        data = json.loads(out) if out else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        tail = ((p.stderr or "").strip() or out)[-400:]
        if "not logged in" in tail.lower() or "log in" in tail.lower():
            raise NoKey(NOT_LOGGED_IN)
        raise RuntimeError("Claude CLI did not return JSON (exit %s): %s" % (p.returncode, tail))

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


# ---- the call --------------------------------------------------------------------------

def call(system, messages, tools=None, model=None, on_retry=None):
    """on_retry(message) is called before each retry of a transient CLI error, so the
    caller can put a line in the run log instead of leaving the user staring at a spinner."""
    binary = cli_bin()
    if binary:
        return _claude_cli(system, messages, tools, binary,
                           model or os.environ.get("SEO_AGENT_MODEL", "").strip() or None,
                           on_retry=on_retry)
    a, o = _keys()
    if a:
        return _anthropic(system, messages, tools, a, model or ANTHROPIC_MODEL)
    if o:
        return _openai(system, messages, tools, o, model or OPENAI_MODEL)
    raise NoKey("No model available. Install the Claude CLI or add a key in Connections.")


def text(prompt, system="You are a precise assistant. Answer with only what was asked."):
    """One-shot text. Used inside tools, where no tool-calling is needed."""
    return call(system, [{"role": "user", "content": prompt}])["text"]


def json_call(prompt, system="Reply with valid JSON only. No prose, no code fences.", retries=1):
    """One-shot JSON, with a tolerant extractor and one retry on a parse failure."""
    for attempt in range(retries + 1):
        raw = text(prompt, system)
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
