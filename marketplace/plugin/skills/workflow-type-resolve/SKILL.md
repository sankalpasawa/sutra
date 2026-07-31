---
name: workflow-type-resolve
preamble-tier: 2
version: 1.0.0
description: |
  Given a classified intent, decide whether to FOLLOW an existing reusable
  workflow type (a skill / command / playbook whose purpose fits this work)
  or CONSTRUCT the steps from scratch via the inner engine. Searches CHILD
  scope (company-local skills + commands + playbooks) before PLATFORM scope
  (the plugin skill catalog), and child-custody wins. Use right after the
  intent is classified (core:input-routing + core:human-sutra) and before you
  start building steps. Skip when you are already mid-step inside a resolved
  workflow, or for a pure read-only question with no work to shape.
allowed-tools: ["Bash"]
---

# Workflow-type resolve (the RESOLVER step of the Flow)

This is the SECOND station on the Flow spine. The first station classified
the input (TYPE + 9-cell, via `core:input-routing` and `core:human-sutra`).
This station answers one question:

```
+-- THE RESOLVER QUESTION ------------------------------------------+
|                                                                   |
|   Does a reusable WORKFLOW TYPE already exist for this work?      |
|                                                                   |
|     YES  -> FOLLOW it     (its steps are the mandatory skeleton)  |
|     NO   -> CONSTRUCT     (build the steps via the inner engine)  |
|                                                                   |
+-------------------------------------------------------------------+
```

A "workflow type" is high-level guidance on HOW a piece of work should be
shaped: a reusable workflow, a skill, a command, or a playbook. In current
Sutra these live as markdown skills (`skills/<name>/SKILL.md`), slash
commands (`commands/<name>.md`), and company-local playbooks. The resolver
looks one up by purpose.

Canon: **ADR-026** (guidance-first resolution; child-custody-wins; inner
engine always runs). Spine render: `platform/flow.html` sections 0 / G / H.

## The one rule you must not break

A workflow type constrains the OUTER steps. It NEVER switches the inner
engine off. Whether you FOLLOW or CONSTRUCT, inside EVERY step you still run
the inner engine: factors + lens + Cynefin (+ dials). FOLLOW gives you the
skeleton; the inner engine gives each bone its shape. This is the founder
correction baked into ADR-026: "when you have high-level guidance, within
that you also have to run factors, lenses, Cynefin dials ... but you have
to ensure you follow those steps of the guidance as well."

## Scope: CHILD first, then PLATFORM

Workflow types live at two custody levels. Search the more specific one
first.

```
+-- SCOPE 1: CHILD  (search FIRST) ---------------------------------+
| custody     = this instance / this company (custody_owner=tenant) |
| where       = company-local skills, commands, playbooks           |
|               e.g. .claude/skills/**, commands/**, project docs    |
| why first   = more specific beats more general; a company's own   |
|               playbook overrides the fleet default                 |
+-------------------------------------------------------------------+
              | (no child match)
              v
+-- SCOPE 2: PLATFORM  (search SECOND) -----------------------------+
| custody     = fleet default (custody_owner = null), shipped L0     |
| where       = the plugin skill catalog (core:* skills + commands)  |
| why second  = the shared baseline every Sutra client inherits      |
+-------------------------------------------------------------------+
              | (no platform match)
              v
        CONSTRUCT  (no reusable type -> build it)
```

Child-custody wins: if BOTH a child playbook and a platform skill fit, you
FOLLOW the CHILD one (it is the more-specific, locally-owned shape).

## Procedure

### Step 1 — Enumerate candidate workflow types

List what could shape this work, child scope first.

- **CHILD candidates**: company-local skills (`.claude/skills/**`), local
  commands (`commands/**` owned by this instance), and any project playbook
  or runbook documents. These have `custody = this instance`.
- **PLATFORM candidates**: the plugin skill catalog (the `core:*` skills
  and slash commands shipped in this plugin). These have `custody = fleet`.

You do not need an exhaustive index — surface the few candidates whose
stated purpose plausibly touches THIS work.

### Step 2 — Semantic match (purpose fit, most-specific wins)

For each candidate, read its purpose (skill `description`, command summary,
or playbook header) and ask: does this exist to do work like THIS one?

- Match on PURPOSE, not on keyword overlap. "Onboard a company" matches a
  company-onboarding playbook even if neither says the word "onboard".
- Prefer the MOST SPECIFIC fit. A dedicated `onboard-company` workflow
  beats a generic `do-a-project` workflow.
- Prefer CHILD over PLATFORM when both fit equally (child-custody-wins).
- A candidate "matches" only if following its steps would genuinely shape
  this work. A loose thematic association is NOT a match — when in doubt,
  treat it as no-match and CONSTRUCT.

### Step 3a — If a candidate matches -> FOLLOW

1. Name the winning workflow type and its scope.
2. Treat its steps as the MANDATORY outer skeleton — do not skip or reorder
   them. If the workflow is a skill, invoke / follow that skill.
3. Inside EACH of its steps, still run the inner engine (factors + lens +
   Cynefin + dials). The skeleton is fixed; the per-step shaping is live.
4. Write the resolution marker (Step 4) — required on this branch.

### Step 3b — If NO candidate matches -> CONSTRUCT

1. There is no reusable type — you will build the steps yourself.
2. Decompose the work via the inner engine: mint the axes this idea needs
   (interrogative x mechanism), run factors + lens + Cynefin, and shape a
   step graph.
3. HALTING / escalation: every step must bottom out at an ATOM (one-shot
   works) or escalate to a human. If you do NOT even know the HOW, do not
   guess — escalate to Mode 3 (how-of-how) per `core:flow`: run a workflow
   that DESIGNS the workflow, then run its output.
4. Write the resolution marker (Step 4) — required on this branch too.

### Step 4 — Emit the block and write the marker

Emit this block verbatim into your response (ASCII only):

```
+-- WORKFLOW-TYPE RESOLVE ------------------------------------------+
| Intent      : <one-line restatement of the classified work>       |
| Candidates  : <child: ...> | <platform: ...> | <none>             |
| Match       : <winning workflow-type name, or "none">             |
| Resolution  : FOLLOW:<skill-name>  |  CONSTRUCT                    |
| Scope       : child | platform | none                             |
| Inner engine: ALWAYS — factors + lens + Cynefin run inside steps  |
| Next        : <invoke the skill / decompose / escalate Mode 3>    |
+-------------------------------------------------------------------+
```

Then write the marker so the Flow hook can confirm this station was walked.
Writing the marker is MANDATORY on BOTH branches — the `flow-gate` hook
reads this session's `flow-type-resolved` marker to verify the resolver ran.
Markers are SESSION-SCOPED: they live at
`.claude/sessions/$CLAUDE_CODE_SESSION_ID/<name>` and carry a `SESSION=` field.
The legacy shared `.claude/flow-type-resolved` twin is maintained by marker-lib
dual-write — never write it directly. Primary path is
`sutra-marker set flow-type-resolved "<content>"`; manual fallback below. Run
exactly ONE of the two commands:

```bash
sdir="${CLAUDE_PROJECT_DIR:-.}/.claude/sessions/${CLAUDE_CODE_SESSION_ID:?}"
mkdir -p "$sdir"

# --- FOLLOW branch (replace name + scope with what you resolved) ---
printf 'RESOLUTION=FOLLOW:%s SCOPE=%s SESSION=%s TS=%s\n' \
  "core:sutra-onboard" "platform" "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
  > "$sdir/flow-type-resolved"

# --- CONSTRUCT branch (use INSTEAD OF the FOLLOW line above) ---
# printf 'RESOLUTION=CONSTRUCT SCOPE=none SESSION=%s TS=%s\n' \
#   "$CLAUDE_CODE_SESSION_ID" "$(date +%s)" \
#   > "$sdir/flow-type-resolved"
```

Marker contract (write EXACTLY one of these forms — note the SINGLE-SPACE
field separators, no commas):

```
.claude/sessions/<session-id>/flow-type-resolved
  FOLLOW    : RESOLUTION=FOLLOW:<skill> SCOPE=child|platform SESSION=<session-id> TS=<unix>
  CONSTRUCT : RESOLUTION=CONSTRUCT SCOPE=none SESSION=<session-id> TS=<unix>
```

Replace `core:sutra-onboard` / `platform` with the workflow type and scope
you actually resolved. On CONSTRUCT, scope is always `none`.

## Worked examples

```
INTENT:  "onboard a new company end to end"
  child candidates    : none
  platform candidates : core:sutra-onboard (8-phase intake->activate)
  match               : core:sutra-onboard  (purpose fits exactly)
  -> RESOLUTION=FOLLOW:core:sutra-onboard SCOPE=platform
  -> follow its 8 phases as the skeleton; run the inner engine in each phase

INTENT:  "decide whether to build or buy a billing system"
  child candidates    : none
  platform candidates : none fit (no build-vs-buy workflow type ships)
  match               : none
  -> RESOLUTION=CONSTRUCT SCOPE=none
  -> decompose via inner engine; HOW is known (a decision), so Mode 2
     sub-workflow, no escalation needed

INTENT:  "run our company's release checklist"
  child candidates    : .claude/skills/release-checklist (local playbook)
  platform candidates : core:workflow (generic discipline wrapper)
  match               : release-checklist  (child beats platform)
  -> RESOLUTION=FOLLOW:release-checklist SCOPE=child
  -> child-custody-wins: the company playbook overrides the fleet default
```

## Where this sits on the spine

```
input
  -> CLASSIFY            (input-routing + human-sutra)   [done before here]
  -> RESOLVE  <-- THIS SKILL: FOLLOW vs CONSTRUCT
  -> FOLLOW steps | CONSTRUCT steps
       -> inner engine shapes EVERY step (always)
       -> run each step as a Work-Atom (recurse if not atomic)
  -> CLOSE               (measure -> learn)
```

The full spine and the recursion / halting rules live in `core:flow`. This
skill owns ONE station: the FOLLOW-vs-CONSTRUCT decision and its marker.

## Notes

- This skill EXPLAINS the resolution discipline; the `flow-gate` hook
  ENFORCES that the marker was written (soft-first: nudge + log in v1).
- Skills supply judgment; hooks supply non-skippable enforcement. The
  resolver is judgment — getting the FOLLOW/CONSTRUCT call right is the
  point; the marker just lets the hook confirm the station was visited.
- This skill composes with `core:input-routing`, `core:human-sutra`,
  `core:depth-estimation`, and `core:blueprint` — it does not replace or
  duplicate them. Classification happens upstream; depth + blueprint still
  fire on the actual mutating steps once they are shaped.

## Deterministic matcher v0 (ADR-026 matching function)

`bin/workflow-type-match.sh` is the deterministic FLOOR under Step 2. It
scans the same two scopes this skill describes — CHILD first
(`.claude/skills/*/SKILL.md`, `skills/*.md`, `holding/skills/*.md`,
`.claude/commands/*.md`, `commands/*.md` under `$CLAUDE_PROJECT_DIR`), then
PLATFORM (`$CLAUDE_PLUGIN_ROOT/skills/*/SKILL.md`, falling back to
`sutra/marketplace/plugin/skills/*/SKILL.md`) — extracts each candidate's
name + front-matter description (or first paragraph), and scores by token
overlap: intent is lowercase-tokenized, tokens <= 3 chars dropped, then
`score = 3 * (intent tokens in name) + 1 * (intent tokens in description)`.
Score >= 2 is a match; highest score wins; ties go to child scope, then
LC_ALL=C alphabetical. Fully deterministic: no network, no date, sorted
iteration, LC_ALL=C.

Invocation (intent as plain args):

```bash
"${CLAUDE_PLUGIN_ROOT:-sutra/marketplace/plugin}/bin/workflow-type-match.sh" onboard a new company
```

Output is EXACTLY ONE line, in the same shape as the resolution marker:

```
RESOLUTION=FOLLOW:<name> SCOPE=<child|platform> SCORE=<n>
RESOLUTION=CONSTRUCT SCOPE=none SCORE=0
```

Two boundaries to respect:

- **Floor, not ceiling.** Skill judgment may OVERRIDE the matcher's answer
  in either direction — accept a below-threshold candidate or reject an
  above-threshold one — but only with a stated reason in the
  WORKFLOW-TYPE RESOLVE block (e.g. "matcher scored 4 on keyword overlap,
  but the candidate's purpose does not fit — CONSTRUCT"). Step 2's rule
  stands: match on PURPOSE; the matcher only measures token overlap.
- **v0 is token-overlap only.** It cannot see synonyms or purpose ("onboard
  a company" will not match a candidate that never says "onboard").
  Semantic matching is the recorded v2 path; until then the matcher is a
  cheap, reproducible first pass — never the final judge.
