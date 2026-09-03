---
type: recipe
reusable: yes
reads: design/GAME-PLAN-agents.md · PUBLISH-CHECK.md · seo_agent/README.md · seo_agent/HISTORY.md
produces: one new agent, running inside the Sutra panel, shipped through a DMG release
last_updated: 2026-09-03
---

# Building another agent inside Sutra

The engineering recipe. Every path is relative to `marketplace/plugin/sutra-ui/`
unless it starts with `/`. The plain-English twin is `NEW-AGENT-plain.md`; it has
the same eleven sections in the same order, so a line here has a line there.

The only agent that exists today is the SEO Writer (`seo_agent/`, shipped in
2.239.0). Every rule below was extracted from it by reading the code, not from
memory. Where the shell still hardcodes that one agent, this file says so and
names the exact lines that have to become a list.

---

## What this does

Takes a job a person would otherwise do by hand over an hour, and turns it into
an agent that does the work in front of them: named steps, a run log, and checkpoints
where the person edits or redirects before the next step runs.

An agent is four things, in this order of importance:

1. **A loop that enforces the rules in code.** Not a prompt that asks nicely.
2. **A registry of tools** whose descriptions carry the RULE for when each runs, and
   whose plain-English rows are what the Tools screen shows.
3. **A run folder on disk** that is the whole truth about what happened.
4. **A screen** that projects that folder, and never holds state of its own.

---

## The one rule that governs everything

**A rule the model is asked to follow is a suggestion. A rule the loop enforces
is a rule.**

That sentence is the docstring of `seo_agent/loop.py` and it decides every design
question below. The model is never told what a step costs, never told which
tools are gated, and never given a chance to skip a checkpoint. `registry.for_model()`
strips `gate`, `cost_credits` and `module` before the model sees a tool, and
`test_endtoend.py` asserts it:

```python
all("gate" not in t and "cost_credits" not in t and "module" not in t
    for t in registry.for_model())
```

The corollary, from the same docstring: **when it needs the user, the process
does not sleep. It writes its files and returns.** There is no blocked thread
holding a checkpoint open. `_wait()` writes `status="waiting"` plus a
`waiting_on` dict, emits a `waiting` event, and returns. The HTTP layer sees a
waiting run. When the answer arrives, `resume()` picks the run back up from disk.

---

## Branch table: which shape are you building

One spine, two entry shapes. Pick before you write anything.

| | **B1. A second agent** | **B2. A new destination** |
|---|---|---|
| When | The job is agent-shaped: steps, checkpoints, artifacts | The surface is not a chat with a review panel at all |
| Enters at | Step 1 | Step 1 |
| Skips | Step 9b (rail registration) | nothing |
| Extra work | Step 9a: turn the hardcoded agent into a list | Step 9b: eight registration points, `test_nav.js` count pins |
| Exits at | Step 15 | Step 15 |
| Precedent | none yet, you are first | `seo_agent` + `17-agents.js`, 2.239.0 |

B1 is the intended path. `app.py:126-128` states it: *"Its routes live under
`/api/agents/<agent>/` so a second agent is another prefix, not another top-level
shape."* The cost is that `17-agents.js` currently hardcodes one agent, so B1
pays a one-time refactor (Step 9a) that B2 does not.

---

## What you produce

Named output per step, up front, so nothing later is invented.

| Step | Output |
|---|---|
| 1 | `design/GAME-PLAN-<agent>.md` — the brief, layout, checkpoints, verification lanes |
| 2 | `<agent>/` — engine package skeleton with `store.py`, `registry.py`, `loop.py`, `llm.py` |
| 3 | `<agent>/registry.py` — every tool declared with gate and cost |
| 4 | `<agent>/tools/*.py` — one module per tool, each `run(ctx, **kw) -> dict` |
| 5 | `<agent>/prompts/*.md` — one file per model call |
| 6 | `<agent>/tests/run_all.sh` + suites — green before anything else starts |
| 7 | `agents_api_<agent>.py` — routes under `/api/agents/<agent>` |
| 8 | `test_<agent>_api.py` — routes, guards, secrets, error codes |
| 9 | `static/js/18-<agent>.js` + `static/<agent>.css` — the screen |
| 10 | `tests/fixtures/<agent>-events.json` — captured from a real run |
| 11 | `test_<agent>.js` — L1 projections + L2 rendered DOM |
| 12 | edits to `app.py`, `panel.html`, `requirements.txt`, `bundle-runtime.sh`, `conftest.py`, `PUBLISH-CHECK.md` |
| 13 | a green gate, recorded |
| 14 | screenshots and a real run, with what they found written down |
| 15 | version bump, changelog, commit, tag, DMG |

---

## Inputs

- The job, described the way the person describes it, not the way a system would.
- The four to six moments where a human must see the work before it continues.
- Every step that costs money or more than a minute, with its number.
- Any credentials the job needs. They go in `connections.json`, chmod `0600`,
  and they are never echoed back to the screen.
- A real example of the finished output, made by hand, to judge quality against.

---

## The steps

### Step 1. Write the brief before the code

**Does:** fixes the shape so the build is assembly, not discovery.
**Follows:** `design/GAME-PLAN-agents.md` as the template.
**Output:** `design/GAME-PLAN-<agent>.md`.

Copy the section list from the SEO Writer's plan: What ships · Where it lives ·
The shell contract · The layout (an ASCII sketch) · The run log table · The
checkpoints table · Settings views · Binding constraints · Verification lanes.

The two tables that matter most are the run log (one row per event kind, saying
what glyph and what text it draws) and the checkpoints (one row per review view,
saying what it shows and what its footer buttons do). Write both before any code.
The SEO Writer has five: the brand pack after setup, then per article the topics, the
research brief, the plan and the draft.

**Gotcha:** if you cannot fill the checkpoint table, the job is not agent-shaped
yet. Stop and re-describe the job.

### Step 2. Create the engine package, standalone

**Does:** gives the agent a home that imports nothing from the app.
**Follows:** `seo_agent/` as the reference implementation.
**Output:** `<agent>/` with `__init__.py`, `store.py`, `registry.py`, `loop.py`,
`llm.py`, `tools/`, `prompts/`, `checks/`, `tests/`, `README.md`, `HISTORY.md`, and one
sub-package per long pipeline (`brand/`, `research/`, `write/`), one module per step,
each `run(<inputs>) -> dict`, with the tool in `tools/` sequencing them. The build
contract the sub-packages follow is `CONTRACTS.md`, and it is the file to hand a
builder before they write a line.

The standalone rule is load-bearing and asserted by the module docstrings: the
engine never imports anything from `sutra-ui`. The entire coupling in the other
direction is one environment variable (`<AGENT>_CLAUDE_BIN`, Step 7). That is
what lets you develop the engine outside the app and drop it in.

**`store.py`, copied whole.** The convention, quoted from its docstring:
*"Nothing lives in memory. A run is a folder; its state file says where we are and
its event log says how it got there."*

The on-disk layout:

```
<data_dir()>/
  chats/
    c-<8 hex>/                       chat.json, messages.json
      runs/
        r-HHMMSS-<slug>/             state.json, events.jsonl, artifacts/
  knowledge/                         whatever your agent learns once and reuses
  library/                           finished output, one folder per item
  memory.jsonl
  connections.json                   chmod 0600
```

Three details a new agent must copy exactly.

*Messages are per chat, not per run.* `chats/<id>/messages.json` holds the whole
conversation while state and events live per run. That is what lets one chat hold
several runs against a shared history.

*The data dir resolves on every call, never at import:*

```python
def data_dir():
    if _DATA_DIR: return _DATA_DIR
    env = os.environ.get("<AGENT>_DATA", "").strip()
    return os.path.abspath(os.path.expanduser(env or DEFAULT_DATA_DIR))
```

Precedence is `set_data_dir()` then the env var then
`~/.sutra-ui/agents/<agent>`. Resolving at import freezes the path and breaks
both tests and the read-only bundle. `DEFAULT_DATA_DIR` must be under the home
directory: the `.app` is read-only once signed.

*Writes are atomic.* Temp file in the same directory, chmod `0o644`, then
`os.replace`. Cross-directory moves are not atomic. `append_jsonl` is a plain
append and deliberately is not atomic.

```python
def write_json(path, data, indent=2):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try: os.remove(tmp)
        except OSError: pass
        raise
```

The credentials file gets `0o600` after every save, wrapped in `try/except OSError`.

**The event record.** Every event is exactly this, and nothing more:

```python
def emit(chat_id, run_id, type, **fields):
    ev = {"t": now(), "type": type}
    ev.update(fields)
    append_jsonl(events_path(chat_id, run_id), ev)
    return ev
```

No id, no sequence number. Ordering is line order in `events.jsonl`, and readers
page with `get_events(chat, run, since=N)` where `since` is a **line index**, not
a timestamp. The screen's cursor arithmetic depends on that.

**The run state.** Written whole by `new_run()`:

```python
{"run_id": run_id, "chat_id": chat_id, "topic": topic,
 "status": "running", "stage": "topic", "current_step": None,
 "waiting_on": None, "credits_spent": 0,
 "started_at": now(), "updated_at": now()}
```

`STATES = ("running", "waiting", "done", "stopped", "failed")`. `patch_state()`
reads, updates, saves with a fresh `updated_at`, and returns the merged state.
The screen reads `status`, `waiting_on` (and inside it `kind`, `call_id`, `tool`,
`cost_credits`, `question`, `view`), `stage` and `credits_spent`.

**`llm.py`. The CLI comes first, always.**

```python
def call(system, messages, tools=None, model=None, on_retry=None):
    binary = cli_bin()
    if binary:
        return _claude_cli(system, messages, tools, binary,
                           model or os.environ.get("<AGENT>_MODEL", "").strip() or None,
                           on_retry=on_retry)
    a, o = _keys()
    if a: return _anthropic(...)
    if o: return _openai(...)
    raise NoKey("No model available. Install the Claude CLI or add a key in Connections.")
```

Provider order is `claude-cli → anthropic → openai → NoKey`. The CLI wins whenever
it is present, and that is what keeps billing on the user's subscription instead
of per token. All three providers normalise to
`{"text": str, "tool_calls": [{"id", "name", "input"}], "raw": ...}`.

The CLI argv, exactly:

```python
cmd = [binary, "-p", "--output-format", "json", "--no-session-persistence",
       "--tools", "", "--setting-sources", "", "--strict-mcp-config",
       "--disable-slash-commands",
       "--system-prompt", _cli_system(system, tools),
       "--json-schema", _compact(CLI_TOOL_SCHEMA if tools else CLI_TEXT_SCHEMA)]
if model: cmd += ["--model", model]
```

The prompt goes on **stdin**, never in argv. `--bare` is never passed: it breaks
login. The four slimming flags cut a call to roughly 850 input tokens.

Because the CLI has no tool-calling API, tools are described in the system prompt
and the reply comes back through a JSON schema. This intro is hard-won and must
be copied close to verbatim, or the model emits a native `tool_use` that fails:

> IMPORTANT: none of the tools below exist in this session. Emitting a tool_use
> for any of them fails with "No such tool available". The only tool you have is
> StructuredOutput, which delivers your reply. To call one of the tools below,
> put `{"name", "input"}` into the tool_calls array of that structured reply and
> stop; the host runs it and the result comes back in the next turn as
> "Result of &lt;id&gt;".

Strip the parent session out of the child environment, or a nested Claude Code
session makes the CLI treat your call as its child:

```python
CLI_STRIP_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID",
                 "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_PID",
                 "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                 "ANTHROPIC_API_KEY")
```

`ANTHROPIC_API_KEY` goes too, so the CLI can never bill the API.

Transient failures are weather, not faults. `CLI_RETRY_SLEEPS = (5, 15, 40)` with
`_TRANSIENT = ("529", "overloaded", "rate limit", "429", "went to sleep", "503",
"502", ...)`, and `on_retry(message)` is called before each retry so the run log
says what happened. Keep `NoKey` and `ModelError` as separate exception classes:
telling someone to sign in when Anthropic was overloaded is a real bug that
shipped once.

**`loop.py`, the control flow.** Entry points are `start()`, `step()`,
`resume()`, `stop()`. There is no `run()`.

`step()` is one `while True` whose body is: autonomy check, model call, then for
each returned tool call either pause, or run it. In order:

```
a. moves >= AUTONOMY_LIMIT   -> _wait("question", None, {...}); return
b. reply = llm.call(system, messages, registry.for_model(), on_retry=...)
c. emit "model_turn" with ms, tool_calls, provider
d. NoKey / Exception          -> emit step_failed; status="failed"; return
e. no tool calls              -> emit "message"; status="done"; emit "run_finished"; return
f. record the assistant turn (text block + one tool_use block per call) BEFORE running anything
g. per call:
     ask_user      -> _wait("question", call_id, {...});  return
     show_artifact -> _wait("artifact", call_id, {...});  return
     log_step      -> emit "note"; tool_result {"ok": True}; continue
     save_memory   -> store.add_memory; emit "memory_saved"; continue
     money gate    -> _wait("approval", call_id, {...});  return
     otherwise     -> emit step_started, run it, emit step_finished/step_failed, moves += 1
h. messages.append({"role": "user", "content": results}); save; loop
```

Four things to copy exactly.

*`moves += 1` only for real work.* `log_step` and `save_memory` are free and never
count toward the cap, so an agent that narrates well is not punished for it.

*The money gate re-reads state from disk* at the moment of the check, and reads
the gate from the registry, never from the model's reply:

```python
state = store.get_state(chat_id, run_id)
approved = set(state.get("approved_tools", []))
if registry.gate(name) in ("ask_before", "always_approve") and name not in approved:
```

`approved_tools` makes approval sticky per tool name for the whole run, so a
second call of the same paid tool does not re-ask.

*The autonomy cap does not kill the run.* `AUTONOMY_LIMIT = 25` converts into a
`question` wait with `call_id=None` and two options. The user decides.

*Credits are charged after the tool returns without raising*, never before.

The tool contract in full:

```python
def _run_tool(chat_id, run_id, name, args, step_id=None):
    spec = registry.get(name)
    mod = importlib.import_module("." + spec["module"], package=__package__)
    ctx = {"chat_id": chat_id, "run_id": run_id, "step_id": step_id,
           "emit": lambda **kw: store.emit(chat_id, run_id, **kw)}
    return mod.run(ctx, **(args or {}))
```

`ctx` carries exactly four keys. The import is relative, so a tool's name never
depends on `sys.path`. A tool returns a dict; the loop reads only `summary` from
it and hands the whole dict back as the tool result. A raising tool does not kill
the run:

```python
results.append({"type": "tool_result", "tool_use_id": call_id,
                "content": {"error": str(e)[:600],
                            "hint": "Tell the user what failed and what you will try instead."}})
```

with `recovering=True` on the `step_failed` event. `recovering=True` draws amber,
`False` draws red. The screen depends on that distinction.

`_wait()` writes state first, then emits, and the `call_id` rides on both:

```python
def _wait(chat_id, run_id, kind, call_id, payload, stage=None):
    fields = {"status": "waiting", "waiting_on": dict(payload, kind=kind, call_id=call_id)}
    if stage: fields["stage"] = stage
    store.patch_state(chat_id, run_id, **fields)
    store.emit(chat_id, run_id, "waiting", kind=kind, call_id=call_id, **payload)
```

The screen pairs a later `resumed` with the exact question it answered by
`call_id`, instead of guessing by order.

`resume(chat_id, run_id, answer)` refuses unless `status == "waiting"`, coerces a
non-dict answer to `{"text": str(answer)}`, then splits:

*Approval, declined.* The tool is never run. The tool result is
`{"declined": True, "hint": "The user said not now. Do not retry it. Offer a
cheaper path or ask what they would prefer instead."}` plus `user_said` when they
typed something.

*Approval, granted.* Add the tool to `approved_tools` and **run the approved call
inline**, from the `args` stored in `waiting_on`. The docstring says why, and it
is worth copying as rationale: *"The user approved THIS call, so the honest thing
is to run it now and hand back the real result. Bouncing back to the model and
hoping it asks again wastes a turn and, worse, lets it change its mind about a
step the user just paid for."* `approval` is the only wait kind that stores `args`.

*Everything else.* Emit `resumed` with a one-line human summary, and for an
artifact wait re-read the artifact **from disk**, not from what the model wrote,
truncating at 24000 chars with an explicit note that the file on disk is complete.

Both branches end the same way: save messages, `status="running"`,
`waiting_on=None`, `return step(...)`.

The full event vocabulary the screen understands. Emit these names and nothing else:

| Event | Fields | Emitted by |
|---|---|---|
| `model_turn` | `ms`, `tool_calls`, `provider` | after each model call |
| `note` | `label` | `log_step`, and the retry callback |
| `message` | `text` | model prose |
| `step_started` | `id`, `label`, `tool` | before a tool |
| `substep_finished` | `parent`, `label`, `note` | tools, via the shared reporter |
| `step_finished` | `id`, `label`, `ms`, `summary` | after a tool |
| `step_failed` | `id`, `label`, `ms`, `reason`, `detail`, `recovering` | tool or model failure |
| `waiting` | `kind`, `call_id`, plus the payload | `_wait` |
| `resumed` | `by`, `answer`, and `approved`/`note` | `resume` |
| `memory_saved` | `text`, `id` | `save_memory` |
| `saved_to_library` | `item_id`, `title` | the host app, not the loop |
| `run_finished` | none | on `status="done"` |
| `stopped` | `by` | `stop` |

`substep_finished` must carry `parent`, because the screen groups sub-rows under
the step whose `id` matches.

**The system prompt carries memory.** `_system_prompt()` reads `prompts/system.md`
and substitutes three tokens, each collapsing to `""` when empty:
`{{COMPANY}}`, `{{VOICE}}`, `{{MEMORY}}`. The last one is
`store.memory_rules()` rendered as a bulleted list under *"Follow these unless
they say otherwise in this conversation"*. That is how standing rules reach the
conversation. They also reach the WORK: `sh.memory_block()` is passed as `{{MEMORY}}`
to every prompt that shapes or writes prose (the plan, the headings, each section, the
edits, the intro and the close) and to the research prompts that decide topic and
angle. A rule the user states once holds everywhere, or it is not a rule.

### Step 3. Declare the tools, with the costs the model never sees

**Does:** puts every cost and gate in one file, out of the model's reach.
**Follows:** `registry.py`.
**Output:** a `WORK_TOOLS` list and a `label()` dict.

The docstring is the spec: *"Costs and gates live HERE, not in the model's head.
The description on each tool is what the model reads to pick it, so each one
carries a RULE, not just a definition. That is the only lever that makes it
choose correctly."*

A work tool entry:

```python
{
    "name": "run_research",
    "description": "...",            # states the RULE: when to run it, what must come first
    "gate": "ask_before",            # auto | ask_before | always_approve
    "cost_credits": 8,
    "est_minutes": 12,
    "module": "tools.run_research",  # dotted path RELATIVE to the package
    "input_schema": {"type": "object", "properties": {...}, "required": [...]},
    "locked": [],
}
```

Gate semantics:

| Gate | Meaning |
|---|---|
| `auto` | just run it. Every work tool in the SEO Writer is `auto` since 2.240.0: the user asked for no credit stops. Paid steps do their own balance pre-flight and say when they skipped. |
| `ask_before` | the loop still supports it: stop and ask before the tool runs |
| `always_approve` | stop every time, for an irreversible step |

UI tools (`ask_user`, `show_artifact`) carry `"pauses": True` instead of `module`.

**The trap:** `registry.pauses()` exists and `loop.py` never calls it. The pause
is hardwired by name (`if name == "ask_user"`). A new pausing tool needs a branch
in `step()`, not just a flag. Either add the branch or make `step()` consult
`registry.pauses()` and delete the dead accessor.

What the model sees is three keys only:

```python
def for_model():
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in ALL]
```

`label(name)` returns the human line the run log shows when the model did not
call `log_step` first. Add a row per tool.

Adding one tool means six edits: the module, the registry entry, the `label()`
row, a `STAGE_FOR` entry if it drives the stage bar, a prompt file if it calls
the model, and a block in `tests/test_tools.py`.

### Step 4. Write the tools

**Does:** the actual work.
**Output:** `<agent>/tools/<name>.py`, each exposing `run(ctx, **declared_args) -> dict`.

Return at minimum `{"summary": "..."}`. Add `"artifact": "<filename>"` when the
tool writes one, and `"error": "..."` for a soft failure the model should react to
rather than crash on.

`tools/_shared.py` is not a tool (the leading underscore says so, and the registry
never points at it). It holds three kinds of helper, and a new agent wants all
three: tolerant readers for the knowledge files, `load_prompt(name)` so no prompt
is ever built inline in code, and `substep(ctx, label, note)` for progress.

Emit substeps. A tool that takes minutes and says nothing looks like a hang.

Network tools: present as a browser, not as a crawler. A User-Agent reading
`(compatible; <agent>/1.0)` earned a 429 on the very first request from a real
site. And write the fallback path before you need it: the SEO Writer indexes from
search data when a site refuses the crawl outright.

### Step 5. Write the prompts as files

**Does:** keeps prompts diffable and single-sourced.
**Output:** `<agent>/prompts/<call>.md`, one per model call, plus `system.md`.

Never build a prompt inline in a `.py`. Load with `sh.load_prompt("<name>")` and
fill `{{TOKEN}}` placeholders with `sh.fill(tpl, **tokens)`.

`_writing_rules.md` is the pattern for a shared fragment several prompts include.
One concept, one wording, referenced everywhere.

### Step 6. Make the engine green before touching the app

**Does:** proves the engine without the panel, the CLI or the network.
**Output:** `<agent>/tests/run_all.sh` printing `ALL SUITES PASS`.

The suites are plain scripts that print PASS/FAIL and call `sys.exit`, not pytest
tests. `run_all.sh` runs each with `python -m <agent>.tests.<name>` inside a
throwaway data dir:

```bash
if [ -z "$<AGENT>_DATA" ]; then
  <AGENT>_DATA="$(mktemp -d -t <agent>-tests)"; made_tmp=1
fi
export <AGENT>_DATA
export <AGENT>_NO_CLI=1        # the model is stubbed; never shell out to claude here
```

Six suites is the shape that worked: `test_loop` (control flow), `test_tools`
(each tool against stubbed model and network), `test_endtoend` (a whole run with a
scripted model), `test_behaviour` (the gates: autonomy cap, money gate, decline
path, recovering flags), `test_checks_editing`, `test_llm_cli` (the CLI argv, the
env strip, the retry ladder).

`test_behaviour.py` is the one that earns its keep. It asserts exactly
`AUTONOMY_LIMIT` tool executions then a stop, that a declined tool never runs,
and that `recovering` is `True` for tool failures and `False` for model failures.

**Gotcha:** the engine's script-style tests must be excluded from the app's pytest
run or the whole session dies. See Step 12.

### Step 7. Add the routes

**Does:** exposes the run folder over HTTP without putting any logic in the route.
**Follows:** `agents_api.py`.
**Output:** `agents_api_<agent>.py` with `router = APIRouter(prefix="/api/agents/<agent>")`.

Every route is thin: read a file, or kick the loop. Copy these verbatim.

```python
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
def _ok_id(*ids):
    return all(isinstance(i, str) and _ID.match(i) and ".." not in i for i in ids)

def _bad(msg, code=400):
    return JSONResponse({"detail": msg}, status_code=code)
```

Leading alphanumeric, then up to 79 of `[A-Za-z0-9._-]`. That forbids `/`, forbids
a leading dot, and the `".."` check is belt and braces. Apply it to every path id
**and** to any artifact name that arrives in a body. Every error is
`{"detail": "<msg>"}`, which is the shape the front end's failure handler reads.

Background work goes on a daemon thread, one per run, keyed by `chat_id + run_id`:

```python
def _spawn(key, fn):
    with _lock:
        t = _workers.get(key)
        if t and t.is_alive(): return False
        th = threading.Thread(target=fn, daemon=True, name="<agent>:" + key)
        _workers[key] = th; th.start()
        return True

def _guarded(chat_id, run_id, fn):
    """A crash inside the loop lands in the run's own log, never silently in a thread."""
    def wrapped():
        try: fn()
        except Exception as e:
            store.emit(chat_id, run_id, "step_failed", label="Run",
                       reason=str(e)[:400], detail=traceback.format_exc()[-1500:],
                       recovering=False)
            store.patch_state(chat_id, run_id, status="failed", error=str(e)[:400])
    return wrapped
```

Refusals come from checking run status, not from `_spawn`'s return value. A send
to a running run is `409 "The agent is still working. Stop it first, or wait."`
An answer to a run that is not waiting is `409`.

The binary handshake is one function and one env var:

```python
def _sync_claude_bin():
    """Hand the agent the same `claude` the chat drives. providers.py owns detection."""
    try: path = providers.provider_bin("claude")
    except Exception: path = None
    if path: os.environ["<AGENT>_CLAUDE_BIN"] = path
    return path
```

Call it at import and before every route that may reach the model. `providers.py`
owns detection (login-shell PATH, settings override, env override). Do not
reimplement it.

**Secrets.** Two mechanisms, both mandatory.

`GET /connections` returns booleans, never values:

```python
return {k: bool((c.get(k) or "").strip()) for k in _CONN_KEYS}
```

`POST /connections` copies only allowlisted keys, and deletes any API key on
every save, whether or not the request mentioned it:

```python
for k in ("anthropic_key", "openai_key"):
    c.pop(k, None)
```

That retro-cleans a store written by an older build. `test_agents_api.py`'s
`test_20_connections_never_echo_secrets_and_refuse_api_keys` enforces it.

`GET /tools` projects an explicit field allowlist out of the registry rather than
returning entries, so module paths never reach the browser.

`GET /health` returns six keys: `ok`, `model_provider`, `claude_bin`, your
integration booleans, `chats`, `data_dir`.

**What is generic** and copies straight across: `_bad`, `_ok_id`, `_spawn`,
`_guarded`, `_live_status`, `_sync_claude_bin`, the chats routes, the run read
routes, the generic artifact get and save, `answer`, `stop`, memory, the
connections shape, the `/tools` projection and the `/health` shape.

**What is yours:** the prefix, the engine import, the env var name, the thread
name, your `waiting_on.kind` vocabulary, your artifact kinds and their checks,
your knowledge routes, your library routes, `_CONN_KEYS`, and the editing imports.

One route runs a model call inline on the request thread: `/edit`. It is a single
block rewrite and it is fast enough. Everything else spawns.

### Step 8. Test the routes

**Does:** pins the guards, the codes and the secrets.
**Output:** `test_<agent>_api.py`, a `unittest.TestCase` pytest collects.

Two setup lines carry all the pain:

```python
# loopback base_url: TrustedHostMiddleware refuses "testserver" with a 400
cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")
HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
```

Point `<AGENT>_DATA` at a temp dir in `setUpClass`. Stub the model with a scripted
object whose `call(system, messages, tools=None, **kw)` returns the shapes you
want, and poll for settle rather than sleeping a fixed time.

Cover at minimum: the id guard rejecting `bad%20id` and `.hidden`, the 409s, the
404s, secrets never echoed, API keys refused, `/tools` carrying no module paths,
and the data dir resolving under home.

### Step 9. Build the screen

**Does:** projects the run folder. Holds no state of its own.
**Follows:** `static/js/17-agents.js` and `static/agents.css`.
**Output:** `static/js/18-<agent>.js`, `static/<agent>.css`.

**The shell contract, and why it is shaped this way.** `render()` rewrites
`#panes` wholesale and `#scBody` whenever the screen's HTML string changes:

```js
const html = SCREENS[S.screen]();
if (scBody.__lastScreenHtml !== html){ ... scBody.innerHTML = html; }
```

So the screen function returns a **constant** string and mounts into it:

```js
if (typeof SCREENS !== "undefined") SCREENS.agents = () => `<div class="ag" id="agRoot" data-ag-shell></div>`;
if (typeof TITLES  !== "undefined") TITLES.agents  = ["Agents", "agents that work in front of you · SEO Writer"];
```

Both entries are mandatory. `render()` destructures `TITLES[S.screen]`, so a
missing row is a TypeError that aborts render before the pane is touched, leaving
the previous screen up as though the click did nothing.

A `MutationObserver` on `#panes` notices an unmounted shell and builds the three
columns. The guard is a dataset flag so a repaint that preserved the node does not
remount:

```js
if (!root.dataset.agLive){
  root.dataset.agLive = "1";
  root.innerHTML = `<aside class="ag-side" id="agSide"></aside>...`;
  agDraw(true); agStartPoll(); agBootLoad();
}
```

Every piece of state lives in `S.ag`, created lazily and never torn down, so a
remount costs nothing: the transcript scroll offset and the composer draft come
back exactly as they were. Writes go through a diff guard:

```js
function agSetHtml(id, html){
  const el = document.getElementById(id); if (!el) return false;
  if (el.__agHtml === html) return false;
  el.__agHtml = html; el.innerHTML = html; return true;
}
```

**Polling, not a socket.** One second while a run is live, four when idle, and the
fetch is skipped while `document.hidden`. A separate one-second interval repaints
so the elapsed clock ticks without a fetch. Events page with a per-run cursor;
the chat list refreshes every fourth tick and health every eighth.

**Every string through one escaper.** `agEsc` escapes five characters including
the single quote, which makes it safe in a quoted attribute as well as a text
node. The shell's own `esc()` covers four and must be paired with `escAttr()` for
attributes. Pick one and hold it.

**Guard every DOM touch with `typeof`.** The file must parse and run to completion
with no DOM at all, because the test harness loads it under `vm` with no
`document`. One unguarded `document.` at top level and the whole suite cannot load
the file.

**Pure renderers as top-level functions.** Every projection and every renderer is
a top-level `ag*` function so the tests can extract the real shipped function
rather than a copy.

**The checkpoint gate is worth copying literally.** A footer with approve buttons
renders only when this artifact is the one the live run is actually waiting on:

```js
const atCheckpoint = live && live.status === "waiting" && live.waiting_on
                  && live.waiting_on.kind === "artifact"
                  && live.run_id === p.run_id && live.waiting_on.artifact === p.name;
```

A reopened past artifact shows no approve button. A library item opens read-only.

**Never invent a number.** No percentage, no ETA. Elapsed is measured between the
first and last event, or to now while live. `agDur` returns `<1s`, `8s`,
`1m 12s`, `1h 1m` and nothing more precise than that.

**A step still running in a run that is no longer alive was interrupted.** Sweep
at the end of the projection and mark it, or the screen spins forever on a dead run.

**CSS.** Every colour, radius and font comes from `panel.css` tokens, so light,
dark and the accent picker are inherited for free. There is not one media query
for colour in `agents.css`, and exactly one literal colour in 299 lines (white on
the danger red, where a token would flip in dark mode). Scope everything under
your root class. Borrow `.runstrip`, `.trow`, `.pill`, `.btn`, `.pc`, `.send`,
`.dot`, `.md-p` from `panel.css` rather than redefining them, and override only to
rescale.

If your screen needs the full row, pin the pane the way the Shadow home does:

```js
const agw = S.screen === "agents" && !bCol;
bp.classList.toggle("agwide", agw);
if (agw && bp.style) bp.style.flex = "1 1 100%";
```

The inline flex is needed because the pane carries a saved inline flex-basis that
beats any class. Measured at 385px beside an open chat before this fix.

#### Step 9a. B1 only: turn the hardcoded agent into a list

`17-agents.js` currently assumes one agent. Six places have to become data before
a second one fits:

| Place | Today | Needs to be |
|---|---|---|
| `AG_API` (line 19) | one constant | per-agent, from the selected agent |
| `AG_STAGES` (20) | the SEO pipeline | per-agent stage list |
| `AG_VIEW_TITLE` (21) | four SEO views | per-agent view titles |
| `agHeroHtml` (390) | three SEO plays, DataForSEO note | per-agent hero copy |
| `agSideHtml` (413) | "SEO Writer", `dataforseo` health | a list of agents, the selected one marked |
| `agPanelHtml` dispatcher (568) | four SEO views | per-agent view renderers |
| `TITLES.agents` subtitle | names the SEO Writer | names the destination only |

Everything else in the file is already generic: the projection from events, the
run log, the question and approval cards, the composer, polling, mount, and about
two thirds of the action dispatcher.

The clean split is a small per-agent descriptor object (api prefix, stages, view
titles, hero, panel renderers) registered by each agent's module into a shared
`AGENTS` map, with `17-agents.js` becoming the shell. Do that refactor as its own
commit, with the existing 24 tests still green, before adding the second agent.

#### Step 9b. B2 only: register a new destination

Eight edits, in this order:

| File | Line | Edit |
|---|---|---|
| `01-state.js` | 117 | add the id to `DESTS`, in the founder's order, not appended |
| `01-state.js` | ~132 | `DEST_PLANES.<id>: []` (an empty array is what makes it full-bleed) |
| `01-state.js` | 173 | `DEST_DEFAULT_SCREEN.<id>: "<screen>"` |
| `02-helpers.js` | 728 | `DEST_LABEL.<id>` |
| `02-helpers.js` | 730 | `DEST_ICON.<id>` (a key into `ICON`, not markup) |
| `02-helpers.js` | ~546 | the `ICON.<id>` glyph paths, no `<svg>` wrapper |
| your module | — | `SCREENS.<id>` and `TITLES.<id>` |
| `panel.html` | 6, 185 | one `<link>`, one `<script>`, both `?v=__ASSETVER__`, script before `09-tail.js` |

Then update the three count pins in `test_nav.js`: the ordered-list test at 97,
the rail paint count at 172, and the count re-asserted inside the Org accordion
test at 550, whose assertion **message** also says the number. Leave a dated
comment saying why the destination was added and where it sits. That is the file's
convention.

Copy the `routines` nav test at `test_nav.js:105-112` as the template for a
per-destination test. The Agents work skipped that and should not have.

### Step 10. Capture fixtures from a real run

**Does:** makes the screen tests test reality.
**Output:** `tests/fixtures/<agent>-events.json`.

Run the agent for real once. Save the run's events and final state, with a `note`
key recording when, against what model, and how the run ended:

```json
{"note": "captured from a real standalone run on 2026-09-03 (stub model, demo keyword data); the run ended with a model failure",
 "state": {...}, "events": [...]}
```

The house rule from `PUBLISH-CHECK.md`: **fixtures are captured, never invented.**
Hand-typed event objects are acceptable only for small targeted edge cases, where
the point is the edge and not the wire shape.

If your agent has block-addressed edits, dump the **server** splitter's output for
the same text into a second fixture and assert the JavaScript splitter agrees byte
for byte. The screen addresses an edit by block id, so a splitter that disagreed
by one would rewrite the wrong paragraph.

### Step 11. Test the screen at L1 and L2

**Does:** the double-test floor.
**Output:** `test_<agent>.js`.

Load the real file under `vm` with the smallest stub set, and take the functions
out of the context so you are testing what ships:

```js
const ctx = { SCREENS:{}, TITLES:{}, S:{}, console,
  apiGet: async()=>({}), apiPost: async()=>({}),
  setTimeout, clearTimeout, setInterval, clearInterval, Date, JSON, Math,
  Number, String, Array, Object, RegExp, encodeURIComponent, isNaN };
vm.createContext(ctx);
vm.runInContext(SRC, ctx, { filename: "18-<agent>.js" });
```

Compare arrays with `JSON.stringify`: arrays born inside the vm context have
another `Array` prototype, so `deepStrictEqual` fails on identical data.

L1 asserts the projections against the captured fixture. L2 asserts rendered HTML.
The cases that caught real bugs in the SEO Writer, worth reproducing:

- the screen shell string is identical across two calls
- a hostile label reaches the DOM escaped, from a run whose request is `<img src=x onerror=alert(1)>`
- an answered approval shows its decision and offers no buttons
- a step still running in a failed run is marked interrupted, never left spinning
- the checkpoint footer stays disabled until a choice is made
- connections renders `placeholder="•••••• (set)"` with `value=""`

### Step 12. Wire it into the app and the bundle

**Does:** makes it load, ship and stay tested.
**Output:** edits to six files, all small.

| File | Edit | If you skip it |
|---|---|---|
| `app.py` router block (113-130) | `import <mod>; app.include_router(<mod>.router)` | routes 404 |
| `app.py:502` `_asset_version()` | add your CSS to the list | a CSS-only change serves stale from cache |
| `panel.html` | the `<link>` and the `<script>` before `09-tail.js` | nothing loads |
| `requirements.txt` | `==` pins, pure-Python wheels only | the cross-arch DMG leg fails |
| `bundle-runtime.sh:145` | add the **import** name to the tuple | the dep ships unverified |
| `conftest.py` | add your package to `collect_ignore` | pytest aborts the whole session |
| `PUBLISH-CHECK.md:22-40` | add your JS suite and your `run_all.sh` | your checks are not in the gate |

The dependency constraint is strict and its failure mode is asymmetric. The
cross-arch leg runs `pip install --target ... --only-binary=:all: --platform
macosx_11_0_<arch> --python-version 3.12`. With `--platform` set, pip cannot build
anything, so every dependency and every transitive dependency must publish a
matching wheel. A wheel tagged `macosx_12_0_arm64` does not match. An Apple
Silicon dev box takes the native branch and never sees the problem; it surfaces on
the Intel CI leg after about forty minutes of runner time. Test with
`./bundle-runtime.sh --arch x86_64` before you pin.

`conftest.py` exists because pytest imports modules at collection, and the
engine's script-style tests call `sys.exit` at module level, which aborts the
whole session with an INTERNALERROR after about 28 unrelated tests.

### Step 13. Run the gate

**Does:** the only definition of done that counts.
**Follows:** `PUBLISH-CHECK.md`.

```
1.  node test_panel.js
2.  node test_governance.js
3.  node test_charter_filter.js
3b. node test_agents.js          # and yours
4.  .venv/bin/python -m pytest -q # collect ALL test_*.py, never a hand-typed list
4b. bash seo_agent/tests/run_all.sh   # and yours
5.  QA_BACKEND=repo bash qa-shell/run.sh
6.  PANEL_URL=http://127.0.0.1:7011/ qa/run.sh
```

Steps 1 to 4 are code truth. Step 5 is production truth. Step 6 is design truth.
A feature is publishable when all three agree.

Compare the pytest failure **names** against a baseline you captured before your
work, not the count. Same names in and out means you added no failures.

**CI runs neither pytest nor the agent JS suite.** The release workflow runs
`test_provision.js`, `test_panel.js`, `test_nav.js`, `test_charter_filter.js` and
the importer tests. Your route tests are enforced by this gate and by nothing else.

### Step 14. Run it for real and look at it

**Does:** finds what reading cannot.
**Output:** screenshots in light and dark, a real run, and a written record of
what running it changed.

The SEO Writer's list of things found only by running it is the argument for this
step: a class name colliding with a shell style, a pane measured at 385px, a
crawler User-Agent earning a 429, a 529 reported to the user as "not signed in", a
pytest collection abort, and a Playwright `networkidle` wait that never fires
because the panel holds an SSE stream open.

Record what you proved and what you did not. The GAME-PLAN's closing table has
three sections: what shipped and how it was verified, what running it found, and
what is left for a later release. Write all three honestly.

### Step 15. Release

**Does:** puts it in the user's app.

The installed app runs the panel from `Sutra.app/Contents/Resources/payload/plugin/sutra-ui`,
its own bundled copy. Editing the checkout changes nothing for an installed build,
and neither does restaging. Only a new DMG moves it.

1. Bump `marketplace/plugin/.claude-plugin/plugin.json` `.version` and the `core`
   entry in `/.claude-plugin/marketplace.json` to the **same** value. The release
   guard compares both against the tag and fails in seconds if they disagree.
2. Add a `## <version> (<date>)` entry to `marketplace/plugin/CHANGELOG.md`, no
   `v` prefix. Bold lead sentence per bullet in plain user language, then two to
   five lines of prose. The last bullet is the engineering line, naming the engine
   package and its check count, the routes module and prefix, the front-end module
   and stylesheet, and any new dependency with the reason it is acceptable.
3. Add a `## v<version> (<date>, HEAD)` entry to `/CURRENT-VERSION.md`, with a `v`
   prefix, one tight paragraph, and move `HEAD` off the old entry. Update both
   `**updated**` dates.
4. Commit, push to `main`.
5. Tag `v<version>-desktop` and push the tag. That is what triggers the DMG build.
   Roughly seven minutes, two architectures, and the release publishes both DMGs
   with per-asset checksums.
6. Confirm the release exists and carries both assets before telling anyone it
   shipped.

The plugin and the desktop app update on different tracks. The plugin pulls from
the repository and moves on the next session. The app only moves when a DMG is
published. A user seeing the new plugin version and the old app version is the
expected state between step 4 and step 5.

---

## Mapping: every step to the code it is grounded in

| Step | Grounded in |
|---|---|
| 1 | `design/GAME-PLAN-agents.md` |
| 2 | `seo_agent/store.py`, `loop.py`, `llm.py` docstrings |
| 3 | `seo_agent/registry.py`; `tests/test_endtoend.py` (the model never sees costs) |
| 4 | `seo_agent/tools/*.py`, `tools/_shared.py` |
| 5 | `seo_agent/prompts/`, `_shared.load_prompt` |
| 6 | `seo_agent/tests/run_all.sh`, `test_behaviour.py` |
| 7 | `agents_api.py`; `app.py:77-100` origin guard; `providers.provider_bin` |
| 8 | `test_agents_api.py:22, 58-59` |
| 9 | `static/js/17-agents.js`; `06-render.js:910-914`, `951-957`; `05-chat.js` TITLES note |
| 9b | `01-state.js:117,132,173`; `02-helpers.js:546,728,730`; `test_nav.js:97,172,550` |
| 10 | `tests/fixtures/agents-events.json`; `PUBLISH-CHECK.md:112-114` |
| 11 | `test_agents.js:22-40` |
| 12 | `app.py:129-130, 502`; `panel.html:6,185`; `bundle-runtime.sh:128-148`; `conftest.py` |
| 13 | `PUBLISH-CHECK.md:22-42` |
| 14 | `design/GAME-PLAN-agents.md`, closing section |
| 15 | `.github/workflows/release-dmg.yml` guard job; `electron/provision.js:83-114` |

---

## Rules shelf

- `PUBLISH-CHECK.md` — the gate, the four authoring levels, the rules of the road.
- `design/GAME-PLAN-agents.md` — the layout, the run log table, the checkpoints.
- `seo_agent/README.md` — the engine's own contract for an outside caller.
- `seo_agent/HISTORY.md` — what was tried, what broke, what was decided.
- `FLAG.md` — if your agent needs a flag, the rollback rules live there.
- `~/.claude/conventions/building-workflows.md` — the recipe shape this file uses.

---

## Gotchas

1. **`SCREENS.<id>` and `TITLES.<id>` are assignments.** Two modules claiming the
   same id, and the second wins silently.
2. **A missing `TITLES` row is a TypeError, not a blank header.** It aborts
   `render()` and the click looks ignored.
3. **`registry.pauses()` is dead code.** The pause is hardwired by tool name in
   `step()`. Add the branch.
4. **The cross-arch pip failure only happens on the Intel CI leg.** Never on an
   Apple Silicon dev box.
5. **CI runs neither pytest nor `test_agents.js`.** The gate is the only enforcement.
6. **`TrustedHostMiddleware` rejects `testserver`.** Every `TestClient` needs
   `base_url="http://127.0.0.1"` or everything is a 400.
7. **The origin guard only fires when an `Origin` header is present.** Curl passes
   free; the Electron window does not. Route every browser call through
   `apiGet`/`apiPost` or mutations 403.
8. **Adding a stylesheet without adding it to `_asset_version()`** serves a stale
   file from cache after a CSS-only edit.
9. **Engine tests that `sys.exit` at import** abort the entire pytest session, and
   the traceback points nowhere near your agent.
10. **`substep_finished` without a `parent`** floats loose instead of nesting.
11. **`recovering=True` versus `False`** is the difference between amber and red.
    Get it backwards and every recoverable hiccup looks fatal.
12. **The bundled payload always wins over the staged copy.** Testing repo code in
    the real shell needs `QA_BACKEND=repo`.
13. **Never `browser.close()` on a `connectOverCDP` session**, and never leave the
    app in debug mode.
14. **Playwright's `networkidle` never fires** against the panel: it holds an SSE
    stream open. Wait on a selector.

---

## Build checklist

- [ ] Brief written: layout, run log table, checkpoints table, verification lanes
- [ ] `<agent>/` package created, importing nothing from sutra-ui
- [ ] `store.py`: run folder layout, atomic writes, `0600` on credentials, data dir resolved per call
- [ ] `loop.py`: money gate re-reads state, autonomy cap asks rather than kills, approved call runs inline
- [ ] `llm.py`: CLI first, prompt on stdin, no `--bare`, parent session env stripped, transient retries visible
- [ ] `registry.py`: every tool has a gate and a cost; `for_model()` strips both
- [ ] Tools written, each `run(ctx, **kw) -> dict`, emitting substeps
- [ ] Prompts in files, none inline
- [ ] `tests/run_all.sh` green in a throwaway data dir, with the CLI disabled
- [ ] Routes added; ids validated; secrets returned as booleans; API keys dropped
- [ ] `test_<agent>_api.py` green, loopback base_url, panel token header
- [ ] Screen: constant shell, observer mount, all state in `S.ag`, every string escaped
- [ ] Every DOM touch guarded by `typeof`, so the file loads under `vm`
- [ ] CSS from tokens only; no invented colours; no colour media query
- [ ] Fixtures captured from a real run, with a provenance note
- [ ] `test_<agent>.js` green: L1 projections and L2 rendered DOM
- [ ] `app.py` mount, `_asset_version()`, `panel.html`, `requirements.txt`, `bundle-runtime.sh`, `conftest.py`
- [ ] `PUBLISH-CHECK.md` lists the new gate steps
- [ ] Full gate run; pytest failure names compared against a baseline
- [ ] Run for real; screenshots light and dark; findings written into the plan
- [ ] Version bumped in both manifests to the same value
- [ ] CHANGELOG and CURRENT-VERSION entries written
- [ ] Committed, pushed, tagged `v<version>-desktop`
- [ ] Release confirmed with both DMG assets attached
