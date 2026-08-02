---
name: cynefin
preamble-tier: 2
version: 1.0.0
description: |
  Certainty-gate for the current step of the Flow. Classifies the step into one
  of four Cynefin domains (Clear / Complicated / Complex / Chaotic) and emits the
  workflow SHAPE that domain implies — sequence vs parallel vs choice, the
  stringency to apply, and whether a human gate is mandatory. Use this as the
  inner-engine certainty pass on EVERY step before you commit to a how: it tells
  you whether to code a fixed sequence, ask an expert LLM, run parallel probes,
  or act-to-stabilize then escalate. Skip only on a pure-question turn with no
  step to execute, or once the domain is already pinned in the session's
  flow-inner marker for this step. Writes CYNEFIN=<domain> to
  .claude/sessions/<session-id>/flow-inner.
allowed-tools: ["Bash"]
---

# Cynefin — Certainty Gate

A step in the Flow is a problem. Before you pick HOW to solve it, decide how
much you can KNOW about it. Cynefin sorts the step by the relationship between
cause and effect, and each sort implies a different workflow shape. This is the
certainty axis of the inner engine: it never picks the answer, it picks the
SHAPE of the search for the answer.

The inner engine always runs. Resolving a workflow type (via
`core:workflow-type-resolve`) constrains the OUTER steps; this gate shapes how
you execute each step regardless. Run it per step.

Certainty is one axis the inner engine reads — it sits alongside the lens pass
(`core:lens`) and the factors pass. Per the generic engine (ADR-027), certainty
is a minted axis instance, not a privileged hard-coded schema: Cynefin gives you
four well-worn values on that one axis, but the axis itself is the same
`value/axis` primitive every other lens uses. Use it because it is battle-tested
for the certainty question, not because it is special.

## The four domains

```
                  ORDERED                  UNORDERED
            +-------------------+    +-------------------+
  KNOWN     |     CLEAR         |    |    COMPLEX        |
  cause     | sense-categorize- |    | probe-sense-      |
  ->effect  |        respond    |    |        respond    |
            | fixed sequence    |    | parallel probes   |
            +-------------------+    +-------------------+
  UNKNOWN   |   COMPLICATED     |    |    CHAOTIC        |
  cause     | sense-analyze-    |    | act-sense-        |
  ->effect  |        respond    |    |        respond    |
            | expert sequence   |    | stabilize+escalate|
            +-------------------+    +-------------------+
```

The split that matters: in ORDERED domains (Clear, Complicated) the right
answer EXISTS and can be found before acting. In UNORDERED domains (Complex,
Chaotic) the right answer EMERGES — you must act to learn, and acting changes
the system. Do not run an ordered workflow on an unordered step; you will commit
to a plan that the system will not honor.

## How to classify

Ask, in order, about the current step:

```
1) Is the cause->effect path knowable in advance?      no -> go to 3
2) Is it obvious to a non-expert (one right way)?      yes -> CLEAR
   else (needs expertise / analysis)                        -> COMPLICATED
3) Is the situation actively breaking right now?       yes -> CHAOTIC
   else (cause emerges only by probing)                     -> COMPLEX
```

When the step sits on a boundary, pick the LESS certain domain. Treating a
Complex step as Complicated is the common failure — it forces a confident plan
onto an emergent problem. Erring toward less certainty costs a probe; erring
toward more certainty costs a wrong commitment.

## CLEAR — sense, categorize, respond

Best practice exists. Cause and effect are obvious to anyone. The step has one
right way and it is already written down somewhere.

```
+--- CLEAR ------------------------------------------------------+
| Recognize : obvious, repeatable, non-expert can verify;        |
|             a checklist or existing skill already covers it.   |
| Pattern   : SEQUENCE (fixed). sense -> categorize -> respond.  |
| Execute as: codeable / hand to an existing skill. Low LLM --   |
|             do not spend judgment where a rule suffices.       |
| Stringency: PROCESS (binding). Follow the steps exactly.       |
| Human gate: NO.                                                |
+----------------------------------------------------------------+
```

If you find yourself debating a Clear step, you have mis-sorted it — it is
probably Complicated.

## COMPLICATED — sense, analyze, respond

Good practice exists, but it takes expertise to find. There may be several valid
answers; an expert (or an expert-mode LLM call) analyzes and chooses.

```
+--- COMPLICATED ------------------------------------------------+
| Recognize : knowable-but-not-obvious; needs analysis, a domain |
|             expert, or a reasoned LLM pass; "it depends".      |
| Pattern   : SEQUENCE (expert). sense -> analyze -> respond,    |
|             with real judgment at the analyze node.            |
| Execute as: one LLM call per step carrying judgment; or a      |
|             sub-workflow of analyzed steps. Mid-to-high LLM.   |
| Stringency: DIRECTIVE (strong default, expert may deviate with |
|             a stated reason).                                  |
| Human gate: NO (unless the analysis surfaces a high-stakes     |
|             irreversible call -- then gate that node).         |
+----------------------------------------------------------------+
```

Most non-trivial knowledge work is Complicated. The how is known to someone; the
job is to apply it correctly.

## COMPLEX — probe, sense, respond

No right answer is knowable in advance. Cause and effect are only clear in
hindsight. You cannot analyze your way to the answer — you must run safe-to-fail
probes, read what emerges, and amplify what works.

```
+--- COMPLEX ----------------------------------------------------+
| Recognize : novel, ambiguous, no precedent; reasonable experts |
|             disagree; the answer depends on how the system     |
|             reacts to your move.                               |
| Pattern   : PARALLEL probes. Run several small safe-to-fail    |
|             attempts at once, then GATE before committing to   |
|             the one that worked. probe -> sense -> respond.    |
| Execute as: declarative -- state the goal and constraints, fan |
|             out probes, let the result select the path. Do NOT |
|             pre-pick a single plan.                            |
| Stringency: PRINCIPLE (goal + guardrails; method is open).    |
| Human gate: GATE before commit -- confirm a probe succeeded    |
|             and is safe to scale before you amplify it. (A     |
|             reviewer gate, not necessarily a human, but human  |
|             if stakes are high.)                               |
+----------------------------------------------------------------+
```

The trap is dressing a Complex step as Complicated to feel decisive. If you
cannot name the analysis that would yield the answer, it is Complex — probe.

## CHAOTIC — act, sense, respond

No discernible cause and effect; the situation is actively breaking. There is no
time to probe. Act first to stabilize, then re-sort the now-calmer situation —
and escalate to a human, because chaotic steps are where judgment, authority,
and accountability matter most.

```
+--- CHAOTIC ----------------------------------------------------+
| Recognize : active failure / breakage / urgent harm; no        |
|             pattern; every second of deliberation costs.       |
| Pattern   : ACT to stabilize, then sense. act -> sense ->      |
|             respond. Take a decisive containing action first.  |
| Execute as: minimal decisive move to stop the bleeding, then   |
|             STOP automated execution.                          |
| Stringency: DIRECTIVE under duress -- do the safe containing   |
|             thing, do not improvise scope.                     |
| Human gate: YES, REQUIRED. After stabilizing, escalate to a    |
|             human. Do not let the Flow auto-resolve a chaotic  |
|             step -- this is a hard halt.                       |
+----------------------------------------------------------------+
```

Chaotic is the one domain where a human gate is non-negotiable. Stabilize, then
hand off. Once stabilized, the step usually re-sorts into Complex or
Complicated, and the Flow resumes from there. This is the same halting rule the
spine enforces everywhere: a step bottoms out at a one-shot atom or escalates to
a human — Chaotic forces the escalation arm.

## Domain -> shape, at a glance

```
DOMAIN        SEQUENCE  PATTERN          STRINGENCY  LLM   HUMAN GATE
Clear         yes       fixed sequence   process     low   no
Complicated   yes       expert sequence  directive   high  no*
Complex       no        parallel probes  principle   mixed gate-before-commit
Chaotic       no        act-then-sense   directive   low   YES (required)
```
\* gate only a high-stakes irreversible node inside an otherwise un-gated
Complicated step.

## Write the marker

After you classify, record the domain so the inner-engine pass is visible to the
flow-gate hook. The marker file is SESSION-SCOPED:
`.claude/sessions/$CLAUDE_CODE_SESSION_ID/flow-inner` (the legacy shared
`.claude/flow-inner` twin is maintained by marker-lib dual-write — never write it
directly). Its canonical shape is a SINGLE line carrying every inner-engine field
for this step:

```
LENS=<axes> CYNEFIN=<domain> FACTORS=<n> SESSION=<session-id> TS=<unix>
```

The lens pass (`core:lens`) and the factors pass write their own fields onto
that one line. Do not clobber their fields and do not split the marker across
multiple lines — keep one authoritative line per step. Use exactly one of these
domain values: `clear` `complicated` `complex` `chaotic`.

Case A — the line already exists this turn (lens or factors ran first). Set or
replace the `CYNEFIN=` field in place; leave the other fields untouched:

```bash
DOM="<domain>"     # one of: clear complicated complex chaotic
SDIR="${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?}"
F="$SDIR/flow-inner"
mkdir -p "$SDIR"
if [ -s "$F" ] && grep -q 'CYNEFIN=' "$F"; then
  # replace the existing CYNEFIN= token, preserve LENS=/FACTORS=/SESSION=/TS=
  sed -i.bak "s/CYNEFIN=[^ ]*/CYNEFIN=$DOM/" "$F" && rm -f "$F.bak"
elif [ -s "$F" ]; then
  # line exists but has no CYNEFIN field yet: append the token to that line
  sed -i.bak "1s/[[:space:]]*$/ CYNEFIN=$DOM/" "$F" && rm -f "$F.bak"
else
  # Case B -- nothing written yet: create the line with just your field
  printf 'CYNEFIN=%s SESSION=%s TS=%s\n' "$DOM" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" > "$F"
fi
```

The hook reads the value of `CYNEFIN=` from this session's `flow-inner`; a single
coherent line is what it expects. If you only have the domain to record (no lens
or factors pass yet), Case B's one-line `CYNEFIN=<domain> TS=<unix>` is correct
on its own — the other passes will add their fields to the same line.

## How this composes with the rest of the Flow

- The certainty domain SHAPES the step; it never replaces the workflow type you
  resolved via `core:workflow-type-resolve`. A Complicated step inside a
  `FOLLOW:<skill>` workflow still follows that skill's skeleton — Cynefin tells
  you how much judgment each node carries.
- Domain drives recursion mode in the spine (`core:flow`). Clear -> usually a
  Mode 1 atom (one-shot holds). Complicated -> often Mode 2 sub-workflow
  (decompose into analyzed steps). Complex -> Mode 2 with parallel probes, or
  Mode 3 if you must design the probe workflow first. Chaotic -> stabilize, then
  escalate (human is the halt).
- Pair this with the lens pass (`core:lens` — which axes change what-you-build or
  who-reads) and the factors pass. Together they are the inner engine that runs
  on every step, always.
- This gate composes with the standing Sutra discipline (`core:input-routing`,
  `core:depth-estimation`, `core:blueprint`); it does not replace any of them. It
  runs INSIDE a step, after those per-turn blocks have classified and scoped the
  work — it adds the certainty read, it does not duplicate routing or depth.