---
name: flow
preamble-tier: 2
version: 1.1.0
description: |
  Orchestrator skill that walks the end-to-end work-resolution spine on one
  unit of work: classify the input TYPE, resolve a matching workflow type
  (follow its steps) or construct steps, run the inner engine (factors + lens
  + Cynefin) on EVERY step, run each step as a Work-Atom, then close
  (measure + learn). The recursive successor to core:workflow — workflow
  walks the per-turn governance sequence; flow walks the full resolution
  spine and recurses into sub-steps. Use when a unit of work is substantive
  enough to need explicit resolution (multi-step, ambiguous shape, or
  "how do I even do this"). FIRES on EVERY input — but as an INLINE FLOW block
  (literal text, the way Input Routing fires), not a Skill call. The full
  recursive Skill spine is the DEEP mode, invoked only for substantive /
  multi-step / ambiguous work (founder D61, 2026-06-14; firing-mechanism
  amended 2026-06-15: inline block, not skill-invocation-every-turn — a hook
  cannot force a Skill, but inline literal text reaches Input-Routing reliability).
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

**Fires on EVERY input via the INLINE FLOW block (D61, 2026-06-14; firing-mechanism amended 2026-06-15)**:
Flow FIRES on every input the way Input Routing fires — by emitting an INLINE
FLOW block as literal text (see "The resolved-path FLOW block" below), NOT by
invoking the Skill tool. This is the firing, and it is what makes Flow as
reliable as Input Routing: a hook can inject a nudge and floor a miss, but no
hook can force a Skill invocation on the first pass — so the per-turn artifact
must be literal text the model emits, not a tool it must choose to call. Every
input — a one-line answer, a single read, a yes/no, chitchat — emits the inline
block (its honest resolved spine) and writes the flow markers (sandbox-safe; see
the callout under "The spine").

The FULL recursive Skill spine (`Skill(core:flow)` + the six stages + recursion
into sub-steps) is the DEEP mode — invoke it only for substantive / multi-step /
ambiguous / unknown-how work, not on every trivial turn. Inline block = the
per-turn floor (always); the Skill = the deep mode (when the work warrants it).

**HONESTY BAR (the anti-theater rule)**: the inline block states what ACTUALLY
resolved for this unit. On a trivial turn that is genuinely TYPE + a CONSTRUCT/
FOLLOW decision + one ATOM step + an honest inner read + close — do NOT claim a
recursive walk, a cynefin domain, or factor counts you did not actually run. An
honest 1-step ATOM block is correct; a block that fakes the full spine is the
theater D61 forbids.

**Why amended (2026-06-15)**: the v2.39.14 contract was "invoke the Skill every
turn in full." A hook cannot force a Skill, so on no-tool turns the model skipped
it. The only true "fires every time by construction" is the spine running as CODE
outside the model (the Native engine) — the long game. Until then, inline literal
text + the two floors (flow-gate, flow-stop-check) is the most reliable in-session
firing. (Per-turn governance — Input Routing, Depth, H-Sutra header — still also
applies; that is the `core:workflow` block stack, layered on top of, not replaced
by, `flow`.)

## The spine

A numbered procedure. Walk it top to bottom for the unit of work. Each stage
delegates judgment to an existing skill and writes a marker the hook reads.
Markers are SESSION-SCOPED: they live under
`$CLAUDE_PROJECT_DIR/.claude/sessions/<session-id>/` (session-id =
`CLAUDE_CODE_SESSION_ID` env; `<sdir>` below abbreviates that directory).
Every marker carries a `SESSION=<session-id>` field. The legacy shared
globals directly under `.claude/` are maintained by marker-lib dual-write —
the model NEVER writes them directly. Primary write path is the
`sutra-marker set <name> <content>` CLI (plugin `bin/`; resolves the same
session dir as the hooks); the printf forms below are the manual fallback.

**Marker writes MUST persist to the real filesystem (read before writing any marker)**:
the `<sdir>/flow-*` markers are read by hooks that run OUTSIDE the assistant tool
sandbox — `flow-gate.sh` (PreToolUse) and `flow-stop-check.sh` (Stop). A sandboxed
`printf > <sdir>/flow-*` is ROLLED BACK when the Bash call ends: the same call sees
the file, the next call and every hook do not. If a marker does not persist, the
hooks read stale state and either block a mutation that WAS classified (flow-gate)
or force a spurious redo on a turn where Flow DID fire (flow-stop-check). Therefore
EVERY marker write below MUST bypass the sandbox so it lands on the real FS the
hooks read: in Claude Code, run the Bash tool with `dangerouslyDisableSandbox: true`
for each marker write, then confirm it persisted in a SEPARATE call. (On a host
without a write sandbox this is a no-op — the write already persists.)

```
input
  |
  v
[1] CLASSIFY TYPE ------------------> writes <sdir>/flow-classified
  |   (core:input-routing + core:human-sutra)
  v
[2] RESOLVE A WORKFLOW TYPE --------> writes <sdir>/flow-type-resolved
  |   (core:workflow-type-resolve)
  |   child scope FIRST, then platform
  v
[3] FOLLOW the matched type   OR   CONSTRUCT the steps
  |   (matched -> mandatory skeleton)  (none -> build the step_graph)
  v
[4] for EVERY step: INNER ENGINE ---> writes <sdir>/flow-inner
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
[6] CLOSE --------------------------> writes <sdir>/flow-closed
      measure (did it meet the GOAL?) + learn (note for next time)
```

### Stage 1 — CLASSIFY TYPE

Classify the input before doing anything. Delegate to `core:input-routing`
for the TYPE (direction | task | feedback | new concept | question) and to
`core:human-sutra` for the 9-cell header tag. Classification labels the input;
it does NOT decide whether the spine runs — under D61 the full spine runs on
every input regardless of TYPE. A pure question still walks all six stages
(resolve -> inner -> atom -> close), it does not short-circuit to an answer.

Write the marker (primary: `sutra-marker set flow-classified "TYPE=<type> CELL=<cell> SESSION=$CLAUDE_CODE_SESSION_ID TS=$(date +%s)"`; manual fallback):

```bash
sdir="${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?set by harness}"
mkdir -p "$sdir"
printf 'TYPE=%s CELL=%s SESSION=%s TS=%s\n' \
  "$TYPE" "$CELL" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
  > "$sdir/flow-classified"
```

Replace `$TYPE` with the routing type and `$CELL` with the H-Sutra 9-cell
header value for this turn (for example `INBOUND-DIRECT`). Do NOT write the
legacy shared `.claude/flow-classified` — that global twin is maintained by
marker-lib dual-write, not by the model.

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

Write the marker (primary: `sutra-marker set flow-type-resolved ...`; manual fallback):

```bash
printf 'RESOLUTION=%s SCOPE=%s SESSION=%s TS=%s\n' \
  "$RESOLUTION" "$SCOPE" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?}/flow-type-resolved"
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
printf 'LENS=%s CYNEFIN=%s FACTORS=%s SESSION=%s TS=%s\n' \
  "$LENS_AXES" "$CYNEFIN_DOMAIN" "$FACTOR_COUNT" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?}/flow-inner"
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

Write the marker (primary: `sutra-marker set flow-closed ...`; manual fallback):

```bash
printf 'MEASURED=%s LEARNED=%s SESSION=%s TS=%s\n' \
  "$MEASURED_CHECK" "$LEARNED_NOTE" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?}/flow-closed"
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
| [1] Classify TYPE | `core:input-routing` + `core:human-sutra` | `<sdir>/flow-classified` |
| [2] Resolve a workflow type | `core:workflow-type-resolve` | `<sdir>/flow-type-resolved` |
| [3] Follow / Construct | this skill (`core:flow`) | (uses [2]'s marker) |
| [4] Inner engine | `core:depth-estimation` + `core:lens` + `core:cynefin` | `<sdir>/flow-inner` |
| [5] Work-Atom run + verify | `core:blueprint` (pre/post) | (verified in-line) |
| [6] Close | this skill (`core:flow`) | `<sdir>/flow-closed` |
| predecessor | `core:workflow` (per-turn governance sequence) | — |

## Enforcement — two floors (NOT the firing)

The markers are not decorative. Two hooks read them and floor a miss. Neither
is the firing mechanism (the inline FLOW block is — see above); they are
backstops that catch a turn that skipped it.

- **`flow-gate.sh` — mutation floor (PreToolUse, HARD fleet-wide, v2.39.12)**:
  an Edit/Write to a non-whitelisted path, or a Task/Agent dispatch, that
  skipped classify+resolve exits 2 (blocks) and logs `.enforcement/flow-gate.jsonl`.
  Catches construct/dispatch mutations only — a pure no-tool turn calls no tool,
  so it cannot reach there.
- **`flow-stop-check.sh` — no-tool floor (Stop, HARD fleet-wide, v2.39.15)**:
  at turn-end, if this session's `flow-classified` marker is absent, it returns
  `{"decision":"block"}` and forces exactly one redo. This floors the pure
  no-tool turns flow-gate cannot — a one-line answer, yes/no, chitchat.
  Loop-safe via `stop_hook_active` (the re-invoked turn passes; never traps).

**Both floors depend on the markers PERSISTING** — see the sandbox callout under
"The spine". A marker written via sandboxed Bash is rolled back, so flow-gate
would block a mutation that was actually classified, and flow-stop-check would
force a spurious redo on a turn where Flow fired. Write markers via the Write
tool (or `dangerouslyDisableSandbox`), then they land on the real FS the hooks read.

Kill-switches (disable both hooks): env `FLOW_DISABLED=1` or file
`$HOME/.flow-disabled`. Override for one call: `FLOW_ACK=1 FLOW_ACK_REASON='<why>'`
(audit-logged). Skills explain; hooks enforce — this skill writes the markers,
the hooks read them.

## Orchestrator mode (D62 / ADR-029)

Flag-gated multi-worker mode for the spine. Canon: `sutra/os/decisions/ADR-029-flow-orchestrator-mode.md` (D62 bootstrap). OFF by default — check before activating any of the machinery below:

```bash
jq -r '.feature_flags.flow_orchestrator_mode // "off"' \
  "$(dirname "$0")/../../sutra-defaults.json"   # plugin root sutra-defaults.json
```

When the flag is `off` (the shipped default) there is ZERO behavior change: this skill runs exactly as documented above, single-lane, and nothing in this section applies. `experimental` = orchestrator dispatch active only where the operating repo has opted in (currently asawa-holding); operators elsewhere treat it as `off` unless they opt in. When `on`:

**Boundary**: one orchestrator per unit, N worker Work-Atoms. The orchestrator owns classify / resolve / dispatch / validate / failure disposition / CLOSE. Each worker owns exactly one atom and never dispatches sub-workers; recursion routes back through the orchestrator.

**Return contract**: every worker returns ONE JSON object per
`references/return-contract.schema.json`, validated by
`bin/validate-return-contract.sh` (VALID exit 0 / INVALID exit 1; stdin or file arg):

- required: `atom_id`, `status` (`done`/`failed`/`blocked`/`partial`), `result` (<= 4000 chars — bounded summary, never a transcript), `verify` (runnable check, string or `{check, result: PASS/FAIL/WAIVED}`), `confidence` (`high`/`moderate`/`low`), `trace_id`
- optional: `evidence` (<= 2000 chars), `files_touched`, `risks` (<= 10), `followups`, `note` (<= 500 chars)

An invalid return is a worker failure, not a formatting nit.

**Failure policy**: a worker gets max 3 attempts at its atom (initial + 2 retries, each retry states what changed), then STOPS and returns. The orchestrator then picks exactly one of the ADR-011 closed five-set: `rollback` / `escalate` / `pause` / `abort` / `continue`. No improvised sixth path.

**Factors**: `bin/flow-factors.sh "<unit>"` emits the deterministic mechanical factors (`unit_factors.steps_est` etc.) feeding stage [4]; byte-identical on repeat runs by contract.

**Ledger (sole writer)**: the orchestrator — never a worker — appends one row per unit at CLOSE via `bin/flow-ledger-append.sh` (caps 2048 chars/string, 8192 bytes/row; 6-pattern secret redaction). Close checklist + row schema: `references/flow-ledger.md`.

Acceptance suite: `tests/flow-orchestrator/run.sh` (fixtures f1..f8; 8/8 required).

## Self-check

Before claiming the unit is resolved, verify:

- [ ] `<sdir>/flow-classified` written with a real TYPE + cell + `SESSION=`.
- [ ] `<sdir>/flow-type-resolved` written — either `FOLLOW:<skill>` with a
      scope, or `CONSTRUCT`.
- [ ] The inner engine ran on EVERY step (not just the first) — a FOLLOWed
      skeleton did not switch it off. `<sdir>/flow-inner` written.
- [ ] Every step bottomed out at an ATOM or was explicitly escalated. No open
      recursion.
- [ ] `<sdir>/flow-closed` written with a runnable measure + a learn note.
- [ ] The resolved-path FLOW block was emitted for this unit.

If a check fails, do not claim resolution — finish the missing stage first.
