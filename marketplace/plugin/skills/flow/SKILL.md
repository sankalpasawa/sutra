---
name: flow
preamble-tier: 2
version: 1.0.0
description: |
  Orchestrator skill that walks the end-to-end work-resolution spine on one
  unit of work: classify the input TYPE, resolve a matching workflow type
  (follow its steps) or construct steps, run the inner engine (factors + lens
  + Cynefin) on EVERY step, run each step as a Work-Atom, then close
  (measure + learn). The recursive successor to core:workflow — workflow
  walks the per-turn governance sequence; flow walks the full resolution
  spine and recurses into sub-steps. Use when a unit of work is substantive
  enough to need explicit resolution (multi-step, ambiguous shape, or
  "how do I even do this"). Runs on EVERY input in FULL, by default — the
  complete six-stage spine walks on every turn regardless of TYPE, the way
  Input Routing does. No fast-path, no skip (founder D61, 2026-06-14: Flow
  universal + full-manner like Input Routing). Cost optimization deferred.
allowed-tools: ["Bash"]
---

# The Flow — end-to-end work-resolution spine

`core:flow` is the orchestrator. It takes one unit of work and walks it
from raw input to a closed, measured result. It is the next evolution of
`core:workflow`: where `workflow` walks the per-turn governance *sequence*
(Input Routing -> Depth -> BLUEPRINT -> Execute -> Trace), `flow` walks the
work-*resolution* spine and recurses into every sub-step. `workflow` is a
checklist for one turn; `flow` is a resolver for one problem of any size.

In current Sutra there is no engine process. Claude is the runtime. This
skill is a discipline Claude reads and follows; the steps below are walked
by Claude, marker files are written along the way, and the `flow-gate` hook
reads those markers to enforce that the spine was actually walked.

Canon: ADR-026 (workflow-type guidance-first resolution) + ADR-027
(value<->axis single primitive). Rendered in `flow.html` sections 0 / G / H.

## What it does / when to use / when to skip

**What**: resolves a unit of work end to end — classify -> resolve a
workflow type or construct steps -> shape every step with the inner engine
-> run each step as a Work-Atom -> close. Recurses: any step that is itself
a problem is run through the same spine.

**When to use**:

- A multi-step task where the shape is not obvious up front.
- A task where you suspect a reusable workflow/skill/playbook already exists
  and you want to find and follow it instead of reinventing.
- A task you do not yet know how to do — flow's Mode 3 designs the method.
- Onboarding, audit, or pedagogy: showing the full resolution spine on a
  real unit of work.

**Full-manner on EVERY input (D61, 2026-06-14) — supersedes the v2.39.11 fast-path**:
Flow runs the COMPLETE six-stage spine on every input, regardless of TYPE —
the way Input Routing fires on every turn. There is no fast-path collapse and
no "trivial turn skips to an answer" exit: a one-line answer, a single read, a
yes/no, chitchat all walk classify -> resolve -> inner -> work-atom -> close in
full, with all four markers written. The founder chose universal + full-manner
over cost-proportional explicitly; **cost optimization (a cheaper head for
trivial turns) is DEFERRED, not designed-in**. Until that optimization ships,
pay the full spine every turn. (Per-turn governance — Input Routing, Depth,
H-Sutra header — still also applies; that is the `core:workflow` block stack,
layered on top of, not replaced by, `flow`.)

## The spine

A numbered procedure. Walk it top to bottom for the unit of work. Each stage
delegates judgment to an existing skill and writes a marker the hook reads.
Markers live under `$CLAUDE_PROJECT_DIR/.claude/`.

```
input
  |
  v
[1] CLASSIFY TYPE ------------------> writes .claude/flow-classified
  |   (core:input-routing + core:human-sutra)
  v
[2] RESOLVE A WORKFLOW TYPE --------> writes .claude/flow-type-resolved
  |   (core:workflow-type-resolve)
  |   child scope FIRST, then platform
  v
[3] FOLLOW the matched type   OR   CONSTRUCT the steps
  |   (matched -> mandatory skeleton)  (none -> build the step_graph)
  v
[4] for EVERY step: INNER ENGINE ---> writes .claude/flow-inner
  |   (core:depth-estimation factors + core:lens + core:cynefin)
  |   a workflow type constrains the OUTER steps; it NEVER turns
  |   the inner engine off (ADR-026 D4)
  v
[5] RUN the step as a WORK-ATOM
  |   construct GOAL / CONSTRAINTS / CONTEXT
  |   dispatch one LLM call OR one skill
  |   verify pre/post (core:blueprint)
  |   (a step that is itself a problem -> recurse: section "The recursion")
  v
[6] CLOSE --------------------------> writes .claude/flow-closed
      measure (did it meet the GOAL?) + learn (note for next time)
```

### Stage 1 — CLASSIFY TYPE

Classify the input before doing anything. Delegate to `core:input-routing`
for the TYPE (direction | task | feedback | new concept | question) and to
`core:human-sutra` for the 9-cell header tag. Classification labels the input;
it does NOT decide whether the spine runs — under D61 the full spine runs on
every input regardless of TYPE. A pure question still walks all six stages
(resolve -> inner -> atom -> close), it does not short-circuit to an answer.

Write the marker:

```bash
mkdir -p "${CLAUDE_PROJECT_DIR:-.}/.claude"
printf 'TYPE=%s CELL=%s TS=%s\n' "$TYPE" "$CELL" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/flow-classified"
```

Replace `$TYPE` with the routing type and `$CELL` with the H-Sutra 9-cell
header value for this turn (for example `INBOUND-DIRECT`).

### Stage 2 — RESOLVE A WORKFLOW TYPE

A workflow type is a reusable workflow / skill / playbook whose steps you can
FOLLOW. Look one up before constructing anything. Check scopes in this order
(ADR-026 — more-specific scope wins):

1. **CHILD** scope first — company-local skills and playbooks
   (`custody_owner = <tenant>`). These override platform defaults.
2. **PLATFORM** scope next — plugin skills shipped to the whole fleet
   (`custody_owner = null`).

Delegate the lookup to `core:workflow-type-resolve`. Outcomes:

- A type matches -> `RESOLUTION=FOLLOW:<skill>` and `SCOPE=child|platform`.
- Nothing matches -> `RESOLUTION=CONSTRUCT` and `SCOPE=none`.

Write the marker:

```bash
printf 'RESOLUTION=%s SCOPE=%s TS=%s\n' "$RESOLUTION" "$SCOPE" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/flow-type-resolved"
```

`$RESOLUTION` is `FOLLOW:<skill-name>` or `CONSTRUCT`. `$SCOPE` is `child`,
`platform`, or `none`.

### Stage 3 — FOLLOW or CONSTRUCT (outer steps)

- **FOLLOW**: the matched workflow type supplies a mandatory skeleton. Its
  steps are not optional — follow them in order. The skeleton fixes the
  OUTER shape (which steps, in what order).
- **CONSTRUCT**: no type matched. Build the step_graph yourself from the
  factors. The construct branch produces the same kind of OUTER shape, just
  authored on the spot instead of looked up.

Either way, the result is a list of steps. The next stage runs on every step
of that list regardless of which branch produced it.

### Stage 4 — INNER ENGINE (runs on EVERY step, ALWAYS)

This is the load-bearing rule from ADR-026 D4: a workflow type constrains the
outer steps; it NEVER switches the inner engine off. Whether the step came
from a FOLLOWed skeleton or a CONSTRUCTed graph, shape it with the inner
engine before running it:

- **factors** — `core:depth-estimation` sets the depth (how exhaustive) and
  the task factors for this step.
- **lens** — `core:lens` reframes the step across the axes that matter
  (the ACROSS direction of the one primitive; keep an axis only if it
  changes what-you-build or who-reads).
- **Cynefin** — `core:cynefin` places the step in a domain (clear /
  complicated / complex / chaotic) and picks the response posture.

The inner engine is generic (ADR-027): the only hard-coded primitive is
`value <-> axis`. Axes are minted per step (interrogative x mechanism),
never enumerated. The "cross" is a runtime product over the axes you pick —
do not hard-code axis names or a fixed grid. Realization (DOWN / decompose),
Reflection (UP / generalize), and the lens family (ACROSS / reframe) are the
three directions of that one move, and they are data, not schema.

Write the marker (once per step, or once for the unit if steps share a lens):

```bash
printf 'LENS=%s CYNEFIN=%s FACTORS=%s TS=%s\n' \
  "$LENS_AXES" "$CYNEFIN_DOMAIN" "$FACTOR_COUNT" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/flow-inner"
```

`$LENS_AXES` is a short comma-separated list of the axes you picked,
`$CYNEFIN_DOMAIN` is the placed domain, `$FACTOR_COUNT` is how many task
factors applied.

### Stage 5 — RUN the step as a Work-Atom

A Work-Atom is the smallest runnable unit. For each step:

1. **Construct** the atom: `GOAL` (what done looks like), `CONSTRAINTS`
   (what must hold), `CONTEXT` (what the call needs to see).
2. **Dispatch**: either one LLM call (the work itself) OR one skill (a
   reusable discipline). One atom = one dispatch.
3. **Verify** pre/post with `core:blueprint`: the pre-check confirms the atom
   is ready to run; the post-check confirms the GOAL was met. A failed
   post-check triggers blueprint's fix-loop before the next step.

If a step is itself a problem (one dispatch will not hold it), do not force
it into one atom — recurse. See the next section.

### Stage 6 — CLOSE

After the last step:

- **Measure**: did the unit of work meet its GOAL? State the runnable check.
- **Learn**: one note for next time — what to reuse, what to change, whether
  a CONSTRUCTed shape should be promoted into a reusable workflow type.

Write the marker:

```bash
printf 'MEASURED=%s LEARNED=%s TS=%s\n' \
  "$MEASURED_CHECK" "$LEARNED_NOTE" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/flow-closed"
```

## The recursion

A step is a smaller problem. Run the SAME spine on it. There are exactly
three resolution modes, and the unification with the generic engine (ADR-027)
is noted on each:

| Mode | Name | When | Engine direction | Stop |
|---|---|---|---|---|
| 1 | ATOM | one-shot dispatch will hold the step | terminal (base case) | — |
| 2 | SUB-WORKFLOW | you know the how, but one shot will not hold it | DOWN — decompose into a step_graph; each sub-step recurses | atomicity |
| 3 | HOW-OF-HOW | you do NOT know the how | UP — run a workflow that DESIGNS the workflow; its output IS a workflow, then run that | reflexivity |

- **Mode 1 (ATOM)** is the base case: construct GOAL/CONSTRAINTS/CONTEXT,
  dispatch once, verify. Terminal.
- **Mode 2 (SUB-WORKFLOW)** decomposes a step into a step_graph and runs the
  whole spine on each sub-step. This is the DOWN direction of `value <-> axis`
  (a value opens into an axis of sub-values).
- **Mode 3 (HOW-OF-HOW)** runs a workflow whose *output is itself a
  workflow* — you design the method, then execute the method it produced.
  This is the UP direction (climb a level to generalize the approach).

### Halting rule

Every recursion MUST bottom out at an ATOM (Mode 1) or ESCALATE TO A HUMAN.
There is no third exit. A branch that keeps decomposing without reaching an
atom and cannot be designed by Mode 3 is an escalation, not a loop.

The meta-climb (Mode 3 stacking on Mode 3) maps to the HOW section 3
Reflection rungs M0..M6 and stops by reflexivity — the rung that describes
itself is the top; do not climb past it. If you reach the reflexive rung and
still have no method, escalate to a human.

## The resolved-path FLOW block

Emit this ASCII block once for the unit of work, filled with what actually
resolved for THIS unit (not the generic template). It makes the spine
visible: which branch, which mode, which inner-engine picks.

```
+-- FLOW ----------------------------------------------------------+
| Unit:       <one-line statement of the work>                     |
| [1] TYPE:   <type> / cell <9cell>                                |
| [2] RESOLVE: FOLLOW <skill> (scope <child|platform>)  | CONSTRUCT|
| [3] STEPS:  <n> steps  ->  s1 ... s2 ... s3 ...                  |
| [4] INNER:  lens=<axes>  cynefin=<domain>  factors=<n>           |
| [5] MODE:   per step -> s1:ATOM  s2:SUB-WORKFLOW  s3:ATOM        |
| [6] CLOSE:  measure=<runnable check>  learn=<one note>           |
| Halting:    all steps bottom out at ATOM | escalate: <none|why>  |
+------------------------------------------------------------------+
```

ASCII only (no unicode box-drawing). Use `+`, `|`, `-`, and `->`.

## Reuse map — which existing skill runs each stage

`flow` orchestrates; it does not re-implement. Each stage delegates to a
skill that already owns that judgment.

| Stage | Owns the judgment | Marker written |
|---|---|---|
| [1] Classify TYPE | `core:input-routing` + `core:human-sutra` | `.claude/flow-classified` |
| [2] Resolve a workflow type | `core:workflow-type-resolve` | `.claude/flow-type-resolved` |
| [3] Follow / Construct | this skill (`core:flow`) | (uses [2]'s marker) |
| [4] Inner engine | `core:depth-estimation` + `core:lens` + `core:cynefin` | `.claude/flow-inner` |
| [5] Work-Atom run + verify | `core:blueprint` (pre/post) | (verified in-line) |
| [6] Close | this skill (`core:flow`) | `.claude/flow-closed` |
| predecessor | `core:workflow` (per-turn governance sequence) | — |

## Enforcement — the flow-gate hook

The four markers are not decorative. The `flow-gate` hook reads them on
`PreToolUse` and checks the spine was walked before a mutation lands.

- **Today (SOFT)**: the hook is advisory. Missing markers produce a stderr
  nudge and a JSONL row in `.enforcement/flow-gate.jsonl`. It never blocks —
  every fleet client keeps working.
- **Company profile (HARD, future)**: when a client's userConfig sets
  `profile=company`, the same hook promotes to a hard gate (exit 2) on
  missing markers. That promotion is described in the hook and NOT active in
  v1.

Kill-switches (both disable the hook entirely): env `FLOW_DISABLED=1` or the
file `$HOME/.flow-disabled`. Override for a single mutation: `FLOW_ACK=1`
(audit-logged to `.enforcement/flow-gate-ledger.jsonl`). Skills explain;
hooks enforce — this skill writes the markers, the hook reads them.

## Self-check

Before claiming the unit is resolved, verify:

- [ ] `.claude/flow-classified` written with a real TYPE + cell.
- [ ] `.claude/flow-type-resolved` written — either `FOLLOW:<skill>` with a
      scope, or `CONSTRUCT`.
- [ ] The inner engine ran on EVERY step (not just the first) — a FOLLOWed
      skeleton did not switch it off. `.claude/flow-inner` written.
- [ ] Every step bottomed out at an ATOM or was explicitly escalated. No open
      recursion.
- [ ] `.claude/flow-closed` written with a runnable measure + a learn note.
- [ ] The resolved-path FLOW block was emitted for this unit.

If a check fails, do not claim resolution — finish the missing stage first.
