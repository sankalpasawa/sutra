"""fanout.py -- one job, many independent sub-tasks, several providers, one answer.

    /fanout Research these 15 competitors and compare pricing and weaknesses.
        -> planner (the PARENT provider) decomposes into sub-tasks
        -> each sub-task goes to a SUITABLE runnable provider, least loaded
           first, so independent work spreads instead of stacking on one
        -> at most MAX_CONCURRENT_WORKERS run at once, one process each
        -> results are merged IN TASK ORDER
        -> the parent provider synthesises one ordinary reply

THE TRIGGER IS NOT THE ARCHITECTURE. Exactly one function in this file knows
the string "/fanout": should_orchestrate(). Everything below it takes a `job`
string and never learns how that job was recognised. Replacing the trigger with
automatic detection is then a change to one predicate, not to the engine --
which is the whole reason it is factored this way rather than inlined into
ws_chat where the switch detector lives.

WHAT THIS DELIBERATELY DOES NOT TOUCH, and each omission is load-bearing:

  chat_store        Workers write NOTHING. Not a turn, not a segment, not an
                    index row. The parent's own turn is recorded exactly as it
                    always was, through app.py's existing append_turn of
                    `operator_msg`. Fifteen concurrent writers on one record
                    would be a lost-update race (chat_store.load/save is a
                    read-modify-write with no lock); the fix is to have no
                    concurrent writers rather than to add one.
  provider_history  No segments. active_segment is hist[-1] and
                    segment_of_turn assumes a monotonic from_turn -- both
                    assert ONE provider owns the next turn, which is exactly
                    what a fan-out is not. Sub-tasks are not part of the
                    conversation's provider timeline; they are inputs to a turn
                    that happens on the parent's provider.
  switch.*          Not called, not extended. switch.plan's first guards are
                    "already running on target" and "no session yet", both of
                    which are sentences about a chat MOVING. Nothing moves here.
  settings.json     Never written. providers.save_settings() has exactly one
                    caller (org_api.py:833, POST /providers/active) and this is
                    not it. A sub-task on DeepSeek does not make DeepSeek the
                    global default, or the chat's default, or anything at all
                    after it exits.

COST IS THE BILLING MODEL, NOT A PRICE LIST, AND THE DIRECTION IS THE OPPOSITE
OF THE OBVIOUS ONE.

Nothing in this codebase knows what a token costs, and nothing here invents a
figure. What the codebase DOES declare, per provider, is HOW EACH ONE BILLS --
and on this product that decides which turns cost the operator cash:

  claude    usage_kind "window-percent" = "a share of a rate-limit window"
            (providers.usage_kind_for). ws_chat REFUSES a turn when
            ANTHROPIC_API_KEY is set, specifically so it "bills the Max plan,
            not the API". => FLAT SUBSCRIPTION. A turn spends allowance, not
            money.
  codex     BIMODAL, and the panel already resolves which
            (providers.codex_auth). CODEX_BILLING_DETAIL, verbatim:
              chatgpt  "covered by your ChatGPT plan ... Nothing here is
                        billed per token."      => FLAT SUBSCRIPTION
              api_key  "billed to your OpenAI API account ... at OpenAI's API
                        pricing"                => METERED
  deepseek  usage_kind "balance" = "money left in a pay-as-you-go account";
            deepseek_usage.py's own header: "pay-as-you-go credit remaining".
            => USER-PAID CREDITS. Every turn spends real money.

So on the shipped configuration DeepSeek is the ONLY provider that always draws
cash per turn. The tier below is derived from the declarations above instead of
asserted, so it follows the operator's actual credentials: sign codex out of
ChatGPT and into an API key and its tier moves on the next fan-out.

COST IS A TIE-BREAK, NOT A GATE (2026-09-10, founder direction). Leading the
routing key with cost made one provider structurally unreachable rather than
merely unpreferred -- see choose_provider for the measurement. Sub-task
assignment now leads with LOAD, and cost decides between providers that are
equally suitable and equally idle.

THE COUNTERARGUMENT, WHICH IS REAL AND IS WHY THE OVERRIDE STAYS.
Subscription capacity is not free, it is just not cash. Fifteen sub-tasks on a
Max plan spend a five-hour window the operator also needs for interactive work,
and a $0.002 DeepSeek turn that preserves it may be the better trade. This
module cannot settle that: the marginal cost of allowance depends on how close
to the limit you are and what else you need it for, and neither fact is
available here. So the default minimises CASH -- which is what "cheapest"
ordinarily means -- and SUTRA_UI_FANOUT_COST is the lever for an operator who
would rather spend credit than window.

Reads:  providers (readiness, ids, usage_kind, codex credential)
Writes: nothing.
"""
import asyncio
import json
import os
import re

import providers

# ─────────────────────────────────────────────────────── the trigger ──────
# THE ONLY PLACE IN SUTRA THAT KNOWS THIS STRING. See the module header.

TRIGGER = "/fanout"

#: THE CLIENT DOES NOT SEND WHAT THE OPERATOR TYPED, and this feature is the
#: first thing in Sutra that had to care.
#:
#: askClaude builds `turn.sent = groundingPrefix(turn) + turn.text`
#: (02-helpers.js) and puts THAT on the wire. groundingPrefix (01-state.js)
#: never returns empty -- every message, in every pane, arrives at ws_chat
#: behind a block like:
#:
#:     PLACEMENT: unresolved -- no department could be resolved for this turn.
#:     (confidence 0.00, mode none)
#:     Do not invent an address. Proceed, and name the gap if it matters.
#:
#:     /fanout Research these six competitors...
#:
#: So a startswith() test on the raw frame is False for every real `/fanout`
#: an operator can type, and the feature silently did nothing in the actual UI
#: while every server-side test passed -- because those tests write the socket
#: directly and never grow the prefix.
#:
#: STRIPPED HERE RATHER THAN CHANGED IN THE CLIENT. The prefix is deliberate:
#: it is the ADR-028 placement grounding the model is supposed to see, and it
#: must keep reaching the provider. What has to be recovered is only the
#: question "what did the operator actually ask for", which is a trigger
#: concern and belongs in this section with the rest of the trigger.
_GROUNDING_HEAD = "PLACEMENT:"
_GROUNDING_SPLIT = "\n\n"


def operator_text(message):
    """(prefix, text) -- Sutra's grounding block split from what was typed.

    ("", message) when there is no grounding block, so a message that reached
    the socket by any other route is untouched.

    THE BLOCK'S SHAPE IS EXACT, not guessed: groundingPrefix joins its lines
    with "\\n" and appends "\\n\\n", and none of the lines it can emit is
    blank -- so the FIRST blank line is always the boundary, and the block
    always opens with "PLACEMENT:".
    """
    if not isinstance(message, str):
        return "", message
    if not message.lstrip().startswith(_GROUNDING_HEAD):
        return "", message
    lead = message[:len(message) - len(message.lstrip())]
    body = message.lstrip()
    at = body.find(_GROUNDING_SPLIT)
    if at == -1:
        # A grounding block and nothing after it. There is no operator text to
        # recover, so nothing is stripped.
        return "", message
    return lead + body[:at + len(_GROUNDING_SPLIT)], body[at + len(_GROUNDING_SPLIT):]

#: How many sub-tasks a plan may contain. A planner that returns 400 rows is
#: not a plan, it is a runaway -- and 400 one-shot CLI spawns on a laptop is a
#: denial of service the operator did not ask for. Rows past the cap are
#: dropped and the drop is SAID, not silently applied.
MAX_TASKS = 24

#: Below this there is nothing to fan out. One sub-task is just the original
#: job with two extra process spawns and a synthesis round-trip, so it falls
#: back to an ordinary turn and says why.
MIN_TASKS = 2

#: THE V1 CONCURRENCY CEILING. Five workers may be mid-turn at once; a sixth
#: sub-task waits for a slot and starts the moment one frees. Bounded, never
#: unbounded -- each worker is a real CLI process with an 8 MiB stream buffer,
#: and "run all fifteen" is a laptop the operator cannot use.
#:
#: Raised from 3 (2026-09-10, founder direction). Three matched
#: seo_agent/llm.py:343 PARALLEL, which throttles in-process API calls; this
#: throttles process spawns, and the measured shape of a fan-out -- mostly
#: waiting on provider I/O, not on local CPU -- carries five comfortably.
MAX_CONCURRENT_WORKERS = 5

#: Back-compat alias. Kept because Orchestration(limit=...) and the tests name
#: one of the two, and a second constant is cheaper than a rename that touches
#: call sites for no behavioural reason.
DEFAULT_LIMIT = MAX_CONCURRENT_WORKERS


def should_orchestrate(message):
    """True when this message should go to the orchestration engine.

    V1: the operator typed the command. This predicate is the ENTIRE product
    trigger -- a future automatic version replaces its body and nothing else in
    this module, or in app.py, has to change.
    """
    if not isinstance(message, str):
        return False
    return _is_command(message) or _is_command(operator_text(message)[1])


def _is_command(text):
    """The literal test, on one candidate string.

    TRIED TWICE by the caller -- on the raw frame and on the text behind a
    grounding block -- and the order matters: an unprefixed message is never
    altered, and a strip can only take effect when what it uncovers IS the
    command. So a message that merely happens to open with "PLACEMENT:" and
    contains a blank line cannot have its first paragraph eaten.
    """
    if not isinstance(text, str):
        return False
    head = text.strip()
    if not head.lower().startswith(TRIGGER):
        return False
    # "/fanoutx ..." is not the command. The character after it must be absent
    # or whitespace, or a longer command starting with the same letters would
    # be swallowed the day one exists.
    rest = head[len(TRIGGER):]
    return rest == "" or rest[0].isspace()


def parse_request(message):
    """{"ok", "job", "prefix", "error"} for a message should_orchestrate() took.

    `prefix` is Sutra's grounding block, or "". It is handed back rather than
    discarded because the block is the placement context the model is meant to
    receive: the caller rebuilds `prefix + job` so a fan-out turn keeps exactly
    the grounding an ordinary turn would have had, minus the command word.

    Kept next to the trigger and nowhere near the engine: the engine takes a
    job string. Deliberately not a command framework -- one command does not
    justify a parser, and a parser is what would have to be maintained the day
    a second one is added for a different reason.
    """
    if not should_orchestrate(message):
        return {"ok": False, "job": "", "prefix": "",
                "error": "not a %s request" % TRIGGER}
    prefix, text = ("", message) if _is_command(message) else operator_text(message)
    job = text.strip()[len(TRIGGER):].strip()
    if not job:
        return {"ok": False, "job": "", "prefix": prefix, "error":
                "%s needs a job to work on. Try: %s <describe the work, e.g. "
                "\"research these 6 competitors and compare pricing\">"
                % (TRIGGER, TRIGGER)}
    return {"ok": True, "job": job, "prefix": prefix, "error": None}


# ────────────────────────────────────────────── cost and capability ───────

#: Cheapest first. See the module header for why this is declared rather than
#: measured, and why it is overridable.
COST_ORDER = ("low", "medium", "high")

#: Least capable first. A provider may take any task at or below its own level.
CAPABILITY_ORDER = ("light", "standard", "deep")

#: Billing model -> cost tier. The ONE judgement in this file, and it is a
#: judgement about CASH: a turn that spends plan allowance is cheaper than one
#: that spends credit, because only the second leaves the operator's balance
#: lower. "unknown" sits with metered on purpose -- routing must never PREFER
#: a provider whose billing it could not determine.
BILLING_COST = {
    "subscription": "low",
    "metered": "high",
    "unknown": "high",
}

#: The HARDEST class of sub-task each provider is trusted with.
#:
#: GROUNDED IN WHAT THE PANEL ALREADY MEASURED about each provider's
#: steerability, which is the only capability evidence this codebase actually
#: holds. No benchmark is run and none is implied.
#:
#:   deepseek  "light".  Declares ZERO per-turn controls, and providers.py
#:             documents each absence on the wire: no reasoning-effort that
#:             reaches the request body, no budget cap, no system-prompt
#:             append, no usable tool allow-list. It is the cheapest and the
#:             least steerable, which is precisely the profile for bounded,
#:             self-contained work.
#:   codex     "standard".  Three turn options, including model_reasoning_effort
#:             (low..ultra) enforced by codex itself, and a real sandbox model.
#:   claude    "deep".  Five turn options including effort and max_budget_usd,
#:             the full permission-mode set, and the only provider this panel
#:             drives with its own MCP tools.
#:
#: A provider with no entry is treated as "light" -- the cautious direction,
#: since the consequence is that it only receives the simplest work rather than
#: being handed something it may not manage.
PROVIDER_CAPABILITY = {
    "deepseek": "light",
    "codex": "standard",
    "claude": "deep",
}

#: What a sub-task gets when the planner does not say, or says something
#: unrecognised. "standard" rather than "light": guessing too low routes real
#: analysis to the least steerable provider, and the failure is a bad answer
#: that reads like a real one. Guessing too high costs money and produces a
#: correct answer, which is the better way to be wrong.
DEFAULT_CAPABILITY = "standard"

#: Operator override, e.g. SUTRA_UI_FANOUT_COST="claude=low,deepseek=high".
#: Exists because "cheapest" is genuinely ambiguous between a flat-rate
#: subscription and a metered balance -- see the module header.
COST_ENV = "SUTRA_UI_FANOUT_COST"


def billing_model(pid):
    """"subscription" | "metered" | "unknown" -- how `pid` bills THIS operator.

    DERIVED FROM WHAT THE PANEL ALREADY DECLARES, never from a price list. See
    the module header for the declaration behind each arm.

    Codex is the one that must be ASKED rather than looked up, because its
    answer depends on which credential is on the machine and the two bill
    differently. providers.codex_auth() is the panel's own resolver for that,
    it never raises, and it answers "unknown" rather than guessing a mode --
    which is exactly the value this function should pass through.
    """
    kind = providers.usage_kind_for(pid)
    if kind == "window-percent":
        return "subscription"
    if kind == "balance":
        return "metered"
    if pid == "codex":
        try:
            state = (providers.codex_auth() or {}).get("state")
        except Exception:      # noqa: BLE001 -- a probe must not fail a job
            return "unknown"
        return {"chatgpt": "subscription", "api_key": "metered"}.get(
            state, "unknown")
    return "unknown"


def provider_cost(pid, models=None):
    """Cost tier for `pid`, honouring the operator override.

    `models` is an optional {pid: billing_model} computed once per fan-out --
    billing_model("codex") shells out to `codex login status`, and doing that
    per sub-task would add a subprocess and up to CODEX_STATUS_TIMEOUT seconds
    to every routing decision. Omitted, it is resolved per call, which is what
    keeps this usable from a test or a one-off.
    """
    raw = os.environ.get(COST_ENV) or ""
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        name, _, tier = pair.partition("=")
        if name.strip() == pid and tier.strip() in COST_ORDER:
            return tier.strip()
    model = (models or {}).get(pid) or billing_model(pid)
    return BILLING_COST.get(model, "high")


def cost_map(pids):
    """{pid: billing_model} for a whole fan-out, resolved once. See
    provider_cost for why once matters."""
    return {pid: billing_model(pid) for pid in pids}


def provider_capability(pid):
    return PROVIDER_CAPABILITY.get(pid, "light")


def clean_capability(value):
    v = (value or "").strip().lower() if isinstance(value, str) else ""
    return v if v in CAPABILITY_ORDER else DEFAULT_CAPABILITY


def eligible_providers():
    """Runnable providers this build can drive headlessly, in catalogue order.

    READINESS IS providers.runnable_providers() AND NOTHING ELSE. That flag is
    already `installed AND configured AND adapter` (providers.py:1884), so a
    signed-out Codex, an unkeyed DeepSeek and Gemini (no adapter) are all
    excluded here without this module holding a second opinion about any of
    them -- which is what would drift.
    """
    import worker
    return [p["id"] for p in providers.runnable_providers()
            if p["id"] in worker.DRIVABLE]


def suitable_providers(required, eligible):
    """(providers that can do `required`, note) -- capability gate only.

    Split out of choose_provider so "which providers COULD do this" is one
    answer with one definition, and the pick among them is a separate
    decision. Nothing about the capability check changed when the tie-break
    did.

    When nothing is capable enough, the MOST capable runnable provider is
    returned with the shortfall as a note: refusing the sub-task outright
    would drop work the operator asked for over a routing table's opinion.
    """
    if not eligible:
        return [], "no runnable provider"
    want = CAPABILITY_ORDER.index(clean_capability(required))
    capable = [p for p in eligible
               if CAPABILITY_ORDER.index(provider_capability(p)) >= want]
    if capable:
        return capable, None
    return (sorted(eligible,
                   key=lambda p: -CAPABILITY_ORDER.index(provider_capability(p)))[:1],
            "no runnable provider is rated %s; used the most capable one "
            "available" % clean_capability(required))


def choose_provider(required, eligible, models=None, load=None):
    """(provider_id, note) -- a suitable runnable provider, least loaded first.

    THE RULE, in one line: among runnable providers whose capability is at
    least what the task needs, take the one carrying the FEWEST sub-tasks so
    far; break ties by cost tier, then by catalogue order.

    WHY LOAD LEADS, AND WHAT IT REPLACED (2026-09-10, founder direction).
    The previous key led with cost, and on the shipped configuration that made
    one provider structurally unreachable rather than merely unpreferred:
    Claude and a ChatGPT-authed Codex both bill as "subscription" -> "low",
    DeepSeek bills as pay-as-you-go -> "high", and Claude is capability-
    suitable for EVERY task. So DeepSeek could only win when no subscription
    provider was suitable, which never happens -- it lost even a `light`
    sub-task it was the exact match for. Measured on this machine: light and
    standard both routed to codex, deep to claude, deepseek to nothing.

    Load-first spreads independent sub-tasks across every provider that can
    actually do them, which is the point of a fan-out. It does NOT weaken the
    capability gate -- `capable` above is unchanged, so an unsuitable provider
    is still never offered the work, and a `deep` task with only Claude rated
    for it still goes to Claude every time.

    COST IS STILL CONSULTED, at equal load, so the cheaper of two equally
    idle and equally suitable providers wins and SUTRA_UI_FANOUT_COST still
    steers. It is a tie-break now rather than a gate; that is the whole change.

    DETERMINISTIC. Same plan, same eligible set -> same assignment twice,
    because `load` is threaded through route() in task order and the final key
    is catalogue position. No randomness, no round-robin cursor to persist.

    `load` is {provider_id: tasks_already_assigned}; omitted, every provider
    reads as idle and this behaves exactly as a single-task decision should.
    """
    capable, note = suitable_providers(required, eligible)
    if not capable:
        return None, note
    load = load or {}
    best = min(capable,
               key=lambda p: (load.get(p, 0),
                              COST_ORDER.index(provider_cost(p, models)),
                              eligible.index(p)))
    return best, note


def route(tasks, eligible, models=None):
    """Assign a provider to every task; returns a new list.

    A `provider` field on a planned task is IGNORED, deliberately. The planner
    prompt asks for capability and never for a vendor, and honouring a named
    one would hand the model the cost decision this function exists to make --
    including the ability to spread work across vendors for no reason, which
    is the exact behaviour the routing requirement rules out. Which provider
    runs a sub-task is decided here, from capability and billing, or nowhere.
    """
    out = []
    #: Sub-tasks assigned so far, per provider. Counted ACROSS the whole plan
    #: rather than per capability level, so a job of three light and three
    #: standard sub-tasks spreads over the providers that can take them
    #: instead of stacking each level onto its own single best match.
    load = {}
    for t in tasks:
        cap = clean_capability(t.get("capability"))
        pid, note = choose_provider(cap, eligible, models, load)
        if pid:
            load[pid] = load.get(pid, 0) + 1
        row = dict(t)
        # ROUTE GUARANTEES THE ID, rather than trusting parse_plan to have set
        # it. Everything downstream keys the progress frame on task["id"], and
        # when that key was merely *usually* present the failure was silent and
        # total: _emit_tool raised KeyError inside the gather, every task came
        # back "failed", and not one progress frame reached the client. Caught
        # by test_progress_rides_existing_tool_frames_only calling route()
        # directly, which is exactly what a future second planner would do.
        row["id"] = str(t.get("id") or "t%d" % (len(out) + 1))
        row["capability"] = cap
        row["provider"] = pid
        row["route_note"] = note
        row["status"] = "pending"
        row["result"] = None
        row["error"] = None
        out.append(row)
    return out


# ──────────────────────────────────────────────────────── planning ────────

def planner_prompt(job):
    """The one prompt the parent provider answers before any worker runs.

    It asks for CAPABILITY, not for a provider, and it is not told which
    providers exist. Which provider runs a sub-task is a billing decision this
    module owns (choose_provider); naming vendors here would invite the planner
    to spread work across them, which is the behaviour the routing rule exists
    to prevent.
    """
    return "\n".join([
        "You are planning how to execute one job by splitting it into "
        "INDEPENDENT sub-tasks that can run in parallel with no knowledge of "
        "each other.",
        "",
        "THE JOB:",
        job,
        "",
        "Reply with ONLY a JSON array. No prose, no markdown fences, no "
        "explanation. Each element:",
        '  {"instruction": "<a complete, self-contained instruction>",',
        '   "capability": "light" | "standard" | "deep"}',
        "",
        "Rules:",
        "- Each instruction must stand alone. A worker sees ONLY its own "
        "instruction and nothing about the job or the other sub-tasks, so "
        "restate whatever context it needs.",
        "- Sub-tasks must be independent. If one needs another's output, they "
        "are one sub-task.",
        "- capability describes how hard THIS ONE sub-task is, on its own, "
        "with the job already broken up:",
        "    light     lookup, extraction, summarising one source, describing "
        "one thing, pulling out stated facts",
        "    standard  comparing a few things, analysis, multi-step reasoning "
        "over material you were given",
        "    deep      genuine judgement, architecture, weighing subtle "
        "trade-offs, or a call someone would defend in a review",
        "- RATE HONESTLY AND DO NOT ROUND UP. Decomposition is what makes a "
        "sub-task easy: once a job is split, most pieces are light or "
        "standard even when the whole job was hard. Marking everything "
        "\"deep\" is not caution, it is a wrong answer -- it routes trivial "
        "work to the heaviest assistant and wastes the operator's capacity. "
        "Reserve \"deep\" for the pieces that genuinely need judgement; "
        "there are usually few, and often none.",
        "- Do NOT include the final synthesis step. That happens afterwards.",
        "- At most %d sub-tasks." % MAX_TASKS,
        "- If the job genuinely cannot be split into %d or more independent "
        "sub-tasks, reply with exactly []." % MIN_TASKS,
    ])


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_plan(text):
    """(tasks, error). Tolerant, and deliberately small.

    Same posture as seo_agent/llm.py:378 json_call -- strip a fence, find the
    array, parse, and give up with a sentence rather than a traceback. No
    schema framework: the shape is two keys, and a validator large enough to
    need a library would be larger than the thing it validates.
    """
    if not isinstance(text, str) or not text.strip():
        return [], "the planner returned nothing"
    body = _FENCE.sub("", text.strip()).strip()
    data = None
    try:
        data = json.loads(body)
    except ValueError:
        # A model that ignored "no prose" usually wraps the array in a
        # sentence. Take the outermost bracket pair and try once more.
        start, end = body.find("["), body.rfind("]")
        if start != -1 and end > start:
            try:
                data = json.loads(body[start:end + 1])
            except ValueError:
                data = None
    if data is None:
        return [], "the planner did not return valid JSON"
    if isinstance(data, dict):
        # Some models wrap the array in {"tasks": [...]} despite the
        # instruction. Accept the one obvious shape rather than failing a whole
        # job over a container.
        for key in ("tasks", "subtasks", "sub_tasks", "plan", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return [], "the planner returned %s, not a list of sub-tasks" % type(data).__name__

    tasks, dropped = [], 0
    for item in data:
        if len(tasks) >= MAX_TASKS:
            dropped += 1
            continue
        if isinstance(item, str):
            instruction = item.strip()
            row = {"instruction": instruction, "capability": DEFAULT_CAPABILITY}
        elif isinstance(item, dict):
            instruction = str(item.get("instruction")
                              or item.get("task") or "").strip()
            # `provider`, if the model emitted one, is dropped here
            # rather than carried and ignored downstream -- see route().
            row = {"instruction": instruction,
                   "capability": clean_capability(item.get("capability"))}
        else:
            continue
        if not instruction:
            continue
        row["id"] = "t%d" % (len(tasks) + 1)
        tasks.append(row)
    err = None
    if dropped:
        err = "the planner returned more than %d sub-tasks; the extra %d were "\
              "not run" % (MAX_TASKS, dropped)
    return tasks, err


# ─────────────────────────────────────────────────────── execution ────────

class Orchestration:
    """The live state of ONE fan-out, and the handle that cancels it.

    EXISTS BECAUSE ws_chat's STOP CANNOT SEE A WORKER. Its reader task calls
    rt.stop() on the PANE's runtime (app.py's `_reader`), and during a fan-out
    the pane's runtime has not been spawned yet -- the live children are
    locals inside worker.run_one. Without something to hold them, a Stop would
    signal nothing and a disconnect would leave up to three CLI processes
    running against the operator's account.

    Deliberately NOT session_runtime.RUNTIMES: that map is the address Shadow's
    say-chain resolves, and a throwaway worker must not be a legal target for
    an injected turn. This is a private set owned by one request.
    """

    def __init__(self, limit=DEFAULT_LIMIT):
        self.limit = max(1, int(limit or DEFAULT_LIMIT))
        self.live = set()
        self.tasks = []
        self.cancelled = False

    def add(self, rt):
        self.live.add(rt)
        if self.cancelled:
            # Raced with a cancel that has already swept. Kill it now, or this
            # one child outlives the stop that was meant to take it.
            self._kill(rt)

    def done(self, rt):
        self.live.discard(rt)

    @staticmethod
    def _kill(rt):
        try:
            rt.kill_group()
        except Exception:
            pass

    def cancel(self):
        """Idempotent, synchronous, and safe to call from anywhere.

        Sync on purpose: the two callers are ws_chat's `stop` handler and its
        `finally`, neither of which can await. kill_group() signals the process
        GROUP, so a CLI's helpers go with it.
        """
        self.cancelled = True
        for rt in list(self.live):
            self._kill(rt)
        self.live.clear()
        for t in list(self.tasks):
            if not t.done():
                t.cancel()


def _label(pid):
    p = providers.provider_by_id(pid)
    return (p or {}).get("name") or pid


def _summary(task, n):
    text = (task.get("instruction") or "").strip().replace("\n", " ")
    if len(text) > 90:
        text = text[:89] + "…"
    return "Sub-task %d/%d — %s" % (task["index"] + 1, n, text)


async def _emit_tool(emit, phase, task, n, **extra):
    """Progress rides the EXISTING `tool` frame -- no new protocol.

    That frame is Sutra's own vocabulary, not a provider passthrough: both
    session_runtime and acp_runtime COMPOSE it from native events, so a third
    composer is in keeping rather than a hack. The client already stores it
    with a full lifecycle (toolRuns keyed by id) and renders a running/ok/failed
    row with an expandable output, which is the whole progress UI for free.
    """
    if emit is None:
        return
    # THE WHOLE BODY IS GUARDED, not just the send. Building the frame reads
    # task fields and calls providers.provider_by_id for the label, and when
    # only `await emit(...)` was wrapped, a KeyError while composing escaped
    # into the gather and turned a working sub-task into a failed one.
    # Progress must never be able to cost a result.
    try:
        frame = {"type": "tool", "phase": phase,
                 "id": "fanout-%s" % task.get("id", "?")}
        if phase == "start":
            frame.update({"name": _label(task.get("provider")),
                          "summary": _summary(task, n), "command": "",
                          "caller": None})
        frame.update(extra)
        await emit(frame)
    except Exception:
        # A dead socket is handled by the turn loop; it must not surface here
        # as a failed sub-task.
        pass


async def execute(tasks, runner, workdir, perm_mode, emit=None, orch=None):
    """Run every task, at most `orch.limit` at once, and return them in ORDER.

    Ordering is by task index, never by completion -- the same discipline
    seo_agent/write/write_body.py:195 uses (index-keyed dict, rebuilt in range
    order), because a comparison table whose rows arrive in whatever order the
    providers happened to finish is not the table anyone asked for.

    return_exceptions=True is load-bearing: without it the first worker to
    raise cancels the gather and takes the other fourteen with it, which is the
    exact opposite of the isolation requirement.
    """
    orch = orch or Orchestration()
    sem = asyncio.Semaphore(orch.limit)
    n = len(tasks)

    async def one(task):
        async with sem:
            if orch.cancelled:
                # A REASON, not just a status. A cancelled row with no error
                # renders as a sub-task that simply produced nothing, which is
                # indistinguishable from a provider that answered with silence.
                task["status"] = "cancelled"
                task["error"] = task["error"] or "stopped before it started"
                return task
            await _emit_tool(emit, "start", task, n)
            task["status"] = "running"
            res = await runner(task["provider"], task["instruction"],
                               workdir, perm_mode, orch)
            if res.get("ok"):
                task["status"] = "done"
                task["result"] = res.get("text") or ""
            else:
                task["status"] = "failed"
                task["error"] = res.get("error") or "unknown failure"
                # A failed worker may still have produced partial text; keep it
                # so the synthesis can use what there is.
                task["result"] = res.get("text") or None
            await _emit_tool(
                emit, "end", task, n, ok=task["status"] == "done",
                output=(task["result"] or task["error"] or "")[:4000])
            return task

    for i, t in enumerate(tasks):
        t["index"] = i
    coros = [one(t) for t in tasks]
    running = [asyncio.ensure_future(c) for c in coros]
    orch.tasks = running
    try:
        await asyncio.gather(*running, return_exceptions=True)
    finally:
        orch.tasks = []
    for t in tasks:
        if t["status"] in ("pending", "running"):
            # gather returned but this one never resolved: cancelled, or its
            # future raised. Either way it has no result and must not be
            # presented as though it might.
            t["status"] = "cancelled" if orch.cancelled else "failed"
            t["error"] = t["error"] or ("stopped before it finished"
                                        if orch.cancelled else "did not complete")
    return sorted(tasks, key=lambda t: t["index"])


# ─────────────────────────────────────────────────────── synthesis ────────

def results_block(job, tasks):
    """The sub-task results, as text for the parent provider to synthesise.

    Failures are STATED, not hidden. A synthesis that silently omits four of
    fifteen competitors reads as complete and is not, and the operator has no
    way to tell. Naming them is what lets the final answer say "I could not
    reach these four".
    """
    ok = [t for t in tasks if t["status"] == "done"]
    bad = [t for t in tasks if t["status"] != "done"]
    lines = [
        "[SUTRA FAN-OUT RESULTS]",
        "",
        "The job below was split into %d independent sub-tasks and run across "
        "several AI providers. %d succeeded, %d did not."
        % (len(tasks), len(ok), len(bad)),
        "",
        "ORIGINAL JOB:",
        job,
        "",
    ]
    for t in tasks:
        head = "--- sub-task %d/%d (%s, %s) ---" % (
            t["index"] + 1, len(tasks), _label(t["provider"]), t["status"])
        lines += [head, "INSTRUCTION: " + (t.get("instruction") or "")]
        if t["status"] == "done":
            lines += ["RESULT:", t["result"] or ""]
        else:
            lines += ["NOT COMPLETED: " + (t.get("error") or "unknown")]
            if t.get("result"):
                lines += ["PARTIAL OUTPUT BEFORE IT FAILED:", t["result"]]
        lines.append("")
    lines += [
        "[END OF FAN-OUT RESULTS]",
        "",
        "Write ONE coherent answer to the original job using the results "
        "above. Do not describe the sub-tasks, the providers, or this process "
        "-- the operator asked for the answer, not the method. Where a "
        "sub-task did not complete, say plainly what is missing rather than "
        "inventing it. Do not repeat any work the results already contain.",
    ]
    return "\n".join(lines)


def compose(base_msg, job, tasks):
    """The parent provider's prompt: whatever it was already being sent, plus
    the results.

    APPENDED rather than replacing, so this composes with the provider-switch
    carry-over without either feature knowing about the other: if switch.plan
    already rewrote the turn into a transcript replay, that replay is still
    there and the results follow it.
    """
    return (base_msg or job) + "\n\n" + results_block(job, tasks)


# ─────────────────────────────────────────────────────── top level ────────

async def run(job, parent_pid, workdir, perm_mode, runner=None, emit=None,
              orch=None, limit=DEFAULT_LIMIT):
    """Plan, route, execute, and return {"ok", "tasks", "detail", "reason"}.

    ok=False means the caller should run the turn UNCHANGED with the operator's
    original message -- planning failed, or the job does not decompose. That is
    a fallback, never a fabrication: the operator still gets a real answer from
    the parent provider, just without the fan-out.
    """
    orch = orch or Orchestration(limit)
    runner = runner or _default_runner

    eligible = eligible_providers()
    if not eligible:
        return {"ok": False, "reason": "no-providers", "tasks": [],
                "detail": "no provider on this machine can run a sub-task"}

    # THE PLANNER RUNS ON THE PARENT PROVIDER, headless, exactly like a worker.
    # Not on the pane's own runtime: that process has not been spawned yet at
    # this point in the turn, and spawning it early to ask a planning question
    # would put a turn the operator never sent into their session transcript.
    plan_res = await runner(parent_pid, planner_prompt(job),
                            workdir, perm_mode, orch)
    if orch.cancelled:
        return {"ok": False, "reason": "cancelled", "tasks": [],
                "detail": "stopped before planning finished"}
    if not plan_res.get("ok"):
        return {"ok": False, "reason": "planner-failed", "tasks": [],
                "detail": "the planner could not run (%s)"
                          % (plan_res.get("error") or "no detail")}

    tasks, warn = parse_plan(plan_res.get("text") or "")
    if not tasks:
        return {"ok": False, "reason": "no-tasks", "tasks": [],
                "detail": warn or "this job was not split into independent "
                                  "sub-tasks"}
    if len(tasks) < MIN_TASKS:
        return {"ok": False, "reason": "not-worth-it", "tasks": [],
                "detail": "this job came back as %d sub-task(s); running it "
                          "directly instead" % len(tasks)}

    tasks = route(tasks, eligible, cost_map(eligible))
    tasks = await execute(tasks, runner, workdir, perm_mode, emit=emit, orch=orch)

    if orch.cancelled:
        return {"ok": False, "reason": "cancelled", "tasks": tasks,
                "detail": "stopped before the sub-tasks finished"}
    if not any(t["status"] == "done" for t in tasks):
        # EVERY worker failed. Fabricating a synthesis from nothing is the one
        # outcome that must not happen, so this reports the failure and lets
        # the caller run the original message normally.
        return {"ok": False, "reason": "all-failed", "tasks": tasks,
                "detail": "all %d sub-tasks failed" % len(tasks)}

    return {"ok": True, "reason": None, "tasks": tasks, "detail": warn,
            "counts": counts(tasks)}


async def _default_runner(pid, prompt, workdir, perm_mode, orch):
    """The real one. Injectable in run() so every test above this line can run
    without a provider binary."""
    import worker
    return await worker.run_one(pid, prompt, workdir, perm_mode,
                                on_spawn=orch.add, on_done=orch.done)


def counts(tasks):
    """{provider: n} over the tasks, for the one-line summary the caller logs."""
    out = {}
    for t in tasks:
        out[t["provider"]] = out.get(t["provider"], 0) + 1
    return out
