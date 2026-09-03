"""tests/test_llm_cli.py — the claude-cli provider, with the subprocess stubbed.

Proves the provider order, the exact command shape, that the conversation is flattened
into one stdin prompt the model can follow, that tool calls come back with local ids in
the same shape the API providers return, and that a logged-out CLI raises NoKey with a
message a person can act on. No real claude process is ever started here.
"""
import json
import os
import re
import subprocess
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))

SAVED_ENV = {k: os.environ.get(k) for k in
             ("SEO_AGENT_NO_CLI", "SEO_AGENT_CLAUDE_BIN", "SEO_AGENT_MODEL", "CLAUDECODE",
              "ANTHROPIC_API_KEY", "CLAUDE_CODE_SESSION_ID")}
REAL_RUN = subprocess.run

def env(**kw):
    for k in SAVED_ENV:
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = v

# --- a canned CLI -----------------------------------------------------------------------
CAPTURED = {}
def canned(reply):
    """subprocess.run that records what it was asked and answers with `reply` as JSON."""
    def run(cmd, **kw):
        CAPTURED.clear()
        CAPTURED.update(cmd=cmd, input=kw.get("input"), env=kw.get("env"), timeout=kw.get("timeout"))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(reply), stderr="")
    return run


print("\nprovider order")
store.save_connections({})
env(SEO_AGENT_NO_CLI="1")
ok("no CLI and no keys gives None", llm.provider() is None, llm.provider())
store.save_connections({"anthropic_key": "sk-a"})
ok("no CLI, anthropic key gives anthropic", llm.provider() == "anthropic")
store.save_connections({"openai_key": "sk-o"})
ok("no CLI, openai key gives openai", llm.provider() == "openai")
env(SEO_AGENT_CLAUDE_BIN=sys.executable)          # any real executable stands in for claude
store.save_connections({"anthropic_key": "sk-a"})
ok("the CLI beats a saved key", llm.provider() == "claude-cli", llm.provider())
env(SEO_AGENT_CLAUDE_BIN="/nonexistent/claude")
ok("a missing binary falls through to the key", llm.provider() == "anthropic", llm.provider())
store.save_connections({})

print("\na tool-calling turn through the CLI")
env(SEO_AGENT_CLAUDE_BIN=sys.executable, CLAUDECODE="1", ANTHROPIC_API_KEY="sk-should-not-leak",
    CLAUDE_CODE_SESSION_ID="abc")
llm.subprocess.run = canned({
    "is_error": False, "result": "ignored when structured_output is present",
    "structured_output": {"text": "Reading the site.",
                          "tool_calls": [{"name": "log_step", "input": {"message": "Reading"}},
                                         {"name": "fake_tool", "input": {"a": 1}}]}})
TOOLS = [{"name": "log_step", "description": "Say one line.",
          "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}}},
         {"name": "fake_tool", "description": "Does the thing.",
          "input_schema": {"type": "object", "properties": {"a": {"type": "integer"}}}}]
MESSAGES = [
    {"role": "user", "content": "write me an article"},
    {"role": "assistant", "content": [
        {"type": "text", "text": "On it."},
        {"type": "tool_use", "id": "t2", "name": "fake_tool", "input": {"a": 1}}]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t2",
         "content": {"summary": "fake tool ran", "rows": "42 rows of keyword data"}}]},
]
reply = llm.call("You are the agent.", MESSAGES, TOOLS)
cmd = CAPTURED["cmd"]
ok("ran the configured binary", cmd[0] == sys.executable, cmd[0])
ok("print mode, json output, no session", all(f in cmd for f in
   ("-p", "--output-format", "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands")))
ok("built-in tools and settings switched off",
   cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--setting-sources") + 1] == "")
ok("never passes --bare", "--bare" not in cmd)
ok("no --model unless SEO_AGENT_MODEL is set", "--model" not in cmd)
ok("timeout is 300s", CAPTURED["timeout"] == 300)
system = cmd[cmd.index("--system-prompt") + 1]
ok("system prompt carries the tools section", "## Tools you can call" in system)
ok("each tool is named with its schema",
   "fake_tool: Does the thing." in system and '"a":{"type":"integer"}' in system)
ok("the reply rule is stated", "return an empty tool_calls list" in system)
schema = json.loads(cmd[cmd.index("--json-schema") + 1])
ok("the tool schema is used", schema["required"] == ["text", "tool_calls"])
prompt = CAPTURED["input"]
ok("prompt went in on stdin, not argv", isinstance(prompt, str) and "write me an article" not in " ".join(cmd))
ok("user text is flattened", "User: write me an article" in prompt)
ok("assistant text is flattened", "Assistant: On it." in prompt)
ok("the tool call is flattened", 'Assistant called fake_tool (t2) with {"a":1}' in prompt)
ok("the tool result is in the prompt", "Result of t2:" in prompt and "42 rows of keyword data" in prompt)
ok("the prompt ends on the model's turn", prompt.rstrip().endswith("Assistant:"))
sub_env = CAPTURED["env"]
ok("nested Claude Code variables are stripped",
   "CLAUDECODE" not in sub_env and "CLAUDE_CODE_SESSION_ID" not in sub_env)
ok("the API key is stripped so nothing bills the API", "ANTHROPIC_API_KEY" not in sub_env)
ok("PATH survives", "PATH" in sub_env)
ok("text comes back", reply["text"] == "Reading the site.")
ok("two tool calls come back", [c["name"] for c in reply["tool_calls"]] == ["log_step", "fake_tool"])
ok("every call carries a local id", all(re.match(r"^call-[0-9a-f]{8}$", c["id"]) for c in reply["tool_calls"]),
   [c.get("id") for c in reply["tool_calls"]])
ok("ids are distinct", len({c["id"] for c in reply["tool_calls"]}) == 2)
ok("inputs are carried", reply["tool_calls"][1]["input"] == {"a": 1})
ok("the shape matches the API providers", set(reply) == {"text", "tool_calls", "raw"})

print("\na long tool result is capped")
big = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t9",
                                     "content": {"blob": "x" * 50000}}]}]
llm.call("s", big, TOOLS)
ok("capped near 20000 chars", 20000 <= len(CAPTURED["input"]) < 21000, len(CAPTURED["input"]))

print("\ntext() and json_call() through the CLI")
llm.subprocess.run = canned({"is_error": False, "result": "", "structured_output": {"text": "pong"}})
ok("text() reads the text field", llm.text("Say pong") == "pong")
schema = json.loads(CAPTURED["cmd"][CAPTURED["cmd"].index("--json-schema") + 1])
ok("a text-only call uses the text-only schema", list(schema["properties"]) == ["text"])
ok("no tools section without tools", "## Tools you can call" not in CAPTURED["cmd"][CAPTURED["cmd"].index("--system-prompt") + 1])
llm.subprocess.run = canned({"is_error": False, "result": "",
                             "structured_output": {"text": "```json\n{\"topics\": [1, 2]}\n```"}})
ok("json_call() tolerates fences", llm.json_call("give me json") == {"topics": [1, 2]})

print("\n--model only when asked")
env(SEO_AGENT_CLAUDE_BIN=sys.executable, SEO_AGENT_MODEL="claude-haiku-5")
llm.text("hi")
c = CAPTURED["cmd"]
ok("--model is passed from SEO_AGENT_MODEL", "--model" in c and c[c.index("--model") + 1] == "claude-haiku-5")
env(SEO_AGENT_CLAUDE_BIN=sys.executable)

print("\nnot logged in")
llm.subprocess.run = canned({"is_error": True, "result": "Not logged in · Please run /login"})
try:
    llm.call("s", [{"role": "user", "content": "hi"}])
    ok("raises NoKey", False, "no raise")
except llm.NoKey as e:
    ok("raises NoKey", True)
    ok("says how to fix it", "sign in" in str(e) and "claude" in str(e), str(e))
llm.CLI_RETRY_SLEEPS = ()   # a transient error would otherwise sleep 60s here; one attempt is the test
llm.subprocess.run = canned({"is_error": True, "result": "Rate limit reached"})
try:
    llm.call("s", [{"role": "user", "content": "hi"}])
    ok("other CLI errors surface as ModelError, never as a sign-in problem", False, "no raise")
except llm.NoKey as e:
    ok("other CLI errors surface as ModelError, never as a sign-in problem", False, "raised NoKey: " + str(e))
except llm.ModelError as e:
    ok("other CLI errors surface as ModelError, never as a sign-in problem", True)
    ok("and keep the CLI's own reason", "Rate limit" in str(e), str(e))

print("\ntransient errors are retried")
_calls = {"n": 0}
_real_canned = canned({"is_error": False, "result": "", "structured_output": {"text": "pong"}})
_bad = canned({"is_error": True, "result": "API Error: 529 Overloaded. Try again in a moment."})
def _flaky(*a, **kw):
    _calls["n"] += 1
    return (_bad if _calls["n"] == 1 else _real_canned)(*a, **kw)
llm.CLI_RETRY_SLEEPS = (0,)
llm.subprocess.run = _flaky
r = llm.call("s", [{"role": "user", "content": "hi"}])
ok("a 529 on the first try is retried once and the answer comes back", r["text"] == "pong" and _calls["n"] == 2,
   "text=%r calls=%d" % (r["text"], _calls["n"]))
_calls["n"] = 0
llm.CLI_RETRY_SLEEPS = ()
llm.subprocess.run = _flaky
try:
    llm.call("s", [{"role": "user", "content": "hi"}])
    ok("with no retries left the 529 is raised as ModelError", False, "no raise")
except llm.ModelError as e:
    ok("with no retries left the 529 is raised as ModelError", "529" in str(e) and _calls["n"] == 1, str(e))
_perm = canned({"is_error": True, "result": "Invalid request: schema too deep"})
llm.CLI_RETRY_SLEEPS = (0, 0)
_calls["n"] = 0
def _perm_count(*a, **kw):
    _calls["n"] += 1
    return _perm(*a, **kw)
llm.subprocess.run = _perm_count
try:
    llm.call("s", [{"role": "user", "content": "hi"}])
except llm.ModelError:
    pass
ok("a non-transient error is NOT retried", _calls["n"] == 1, "calls=%d" % _calls["n"])

print("\nno structured output")
llm.subprocess.run = canned({"is_error": False, "result": "plain words"})
r = llm.call("s", [{"role": "user", "content": "hi"}])
ok("falls back to the plain result", r["text"] == "plain words" and r["tool_calls"] == [])

# --- restore -----------------------------------------------------------------------------
llm.subprocess.run = REAL_RUN
for k, v in SAVED_ENV.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v
store.save_connections({})

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all CLI provider checks passed")
