---
name: human-sutra
description: Use on every user message AFTER input-routing. Classifies the turn into 9-cell × 3-tag schema (CQRS-extended), appends a JSONL log row, and emits the visible header tag for the response.
allowed-tools: Bash, Read
---

# Human-Sutra Interaction Layer skill

V1.0 runtime for the H↔Sutra Interaction Layer. Wraps `scripts/classify.sh` and turns its JSON into (a) a single-line header tag at the top of the response and (b) a JSONL row in `holding/state/interaction/log.jsonl`. Charter: `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (commit f65725a). Locked decisions: `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md` (commit b88b7cc). v1.0 instruments only — visibility before influence (D42).

## Skill card (per [Explain skills on first use] memory)

- **WHAT**: classifies every founder ↔ Sutra ↔ Sutra interaction into the 9-cell × 3-tag taxonomy (DIRECTION × VERB plus TIMING / CHANNEL / REV / RISK).
- **WHY**: visibility-before-influence (D42); founder needs flow visibility to write evolution rules in ADR-002+.
- **EXPECT**: a single bracketed header tag at the very top of the response, plus one JSONL row appended to `holding/state/interaction/log.jsonl`.
- **ASKS**: nothing — autonomous; never blocks the founder.

## When this skill fires

- Every founder turn at `UserPromptSubmit`.
- **Skill execution order** (when this skill RUNS): AFTER `input-routing` (consumes its `TYPE` via translation table), BEFORE `blueprint` (which reads h-sutra's classification for the per-task BLUEPRINT block). Explicit ordering is registered in `sutra/marketplace/plugin/hooks.json` (top-level) under `ordering.UserPromptSubmit.human-sutra`.
- **Header position in response** (where the OUTPUT lands): the header tag is the FIRST text in the response, ABOVE the existing Input Routing block. It is a SEPARATE single line prepended above Input Routing — it NEVER replaces the Input Routing block.
- These are two independent properties: execution order governs WHEN the skill runs in the per-turn skill chain; header position governs WHERE its output appears in the rendered response.

Per-turn block stack (response output order, top to bottom):

```
1. [HUMAN-SUTRA HEADER TAG]     (skill: human-sutra)            <- FIRST text in response
2. INPUT ROUTING block          (skill: core:input-routing)
3. DEPTH + ESTIMATION block     (skill: core:depth-estimation)
4. BLUEPRINT block              (skill: core:blueprint)
5. BUILD-LAYER block            (when editing protected paths)
6. ... tool calls ...
7. OUTPUT TRACE one-liner       (skill: core:output-trace)
```

Skill execution order on `UserPromptSubmit` (when each skill runs, independent of output position):

```
input-routing  →  human-sutra  →  blueprint
                   (consumes TYPE,  (reads h-sutra
                    emits header)    classification)
```

## Classification procedure

Step-by-step inside the skill runtime:

1. **Read the Input Routing TYPE.** Either parse it from the prior `input-routing` skill block in this turn OR set the `IR_TYPE` env var when invoking `classify.sh` directly. Accepted values: `direction | task | feedback | new-concept | question`.
2. **Invoke the classifier.** Pass the founder's raw input on `stdin` (or as `$1`) and the routing type via env:
   ```bash
   IR_TYPE="$input_routing_type" \
     bash sutra/marketplace/plugin/skills/human-sutra/scripts/classify.sh "$INPUT"
   ```
3. **Capture stdout JSON** and parse with `jq`. Required fields: `turn_id`, `direction`, `verb`, `principal_act`, `mixed_acts`, `tense`, `timing`, `channel`, `reversibility`, `decision_risk`, `stage_1_pass`, `stage_3_emission_type`, `input_routing_type`.
4. **Check the classifier exit code.**
   - Exit `0` and parseable JSON → proceed to Header emission + Logging.
   - Non-zero exit OR `jq` parse failure OR `jq` missing → **fail-CLOSED for the log row** (skip the append; emit a single-line stderr warning) and **fail-OPEN for downstream** (do not block input-routing, blueprint, or any other skill).

## Header emission

The header is the FIRST text in the response — a SEPARATE single line prepended ABOVE the existing Input Routing block. It NEVER replaces the Input Routing block — that backward-compat invariant is non-negotiable. (Note: this is the response-output position, distinct from skill-execution-order — see "When this skill fires" above.)

Format:

```
[<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]
```

When `mixed_acts` is non-empty, render as `<VERB>(<MIXED1>[,<MIXED2>])`. When `tense` is non-null, prepend ` · TENSE:<tense>` between VERB and TIMING. On `stage_1_pass=false` with `retry_saturated=false`, emit the Stage-1 fail tag instead.

| # | Scenario | Header |
|---|----------|--------|
| 1 | Direct task, reversible, medium risk | `[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:medium]` |
| 2 | Direct task, irreversible, high risk | `[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:irreversible · RISK:high]` |
| 3 | Past-tense query | `[INBOUND·QUERY · TENSE:past · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]` |
| 4 | Compound DIRECT + ASSERT | `[INBOUND·DIRECT(ASSERT) · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]` |
| 5 | Stage-1 fail (vague pronoun) | `[STAGE-1-FAIL · CLARIFY · attempt:1/1]` |

Header rules:

- Exactly one line. No leading or trailing whitespace. No markdown.
- Bracketed: a single `[` at start, a single `]` at end.
- Field separator is ` · ` (space, middle dot, space). No commas.
- Keys are uppercase (`TIMING`, `CHANNEL`, `REV`, `RISK`, `TENSE`); values lowercase except for the verb tokens.

## Logging procedure

Append-only JSONL at `holding/state/interaction/log.jsonl`. Whitelist path — no cascade hook, no build-layer marker required. Skill `mkdir -p`s the directory on first append.

Schema (one row per turn):

| Field | Type | Notes |
|-------|------|-------|
| `ts` | string | ISO-8601 UTC, second precision |
| `turn_id` | string | correlation key for retry / re-entrancy dedup |
| `direction` | string | always `INBOUND` in v1.0 |
| `verb` | string | `DIRECT` / `QUERY` / `ASSERT` / `STAGE-1-FAIL` |
| `principal_act` | string | same as verb (mirrors classifier output) |
| `mixed_acts` | array | `[]` or e.g. `["QUERY","ASSERT"]` |
| `tense` | string \| null | `past` / `present` / `future` / `null` |
| `timing` | string | `now` / `later` |
| `channel` | string | `in-band` / `out-of-band` |
| `reversibility` | string | `reversible` / `irreversible` |
| `decision_risk` | string | `low` / `medium` / `high` |
| `stage_1_pass` | bool | `true` when Stage-1 confidence gate passes; mirrors `classifier.stage_1_pass` |
| `stage_3_emission_type` | string | `OUT-ASSERT` / `OUT-QUERY` |
| `input_routing_type` | string | from `IR_TYPE` |

Append rules:

- Atomic POSIX append via `>>` for entries < 4096 bytes (the v1.0 schema fits comfortably under that bound).
- One JSON object per line, no trailing commas, no pretty-printing.
- **Dedup rule**: if a row with matching `turn_id` already exists in the last 10 rows of the file, SKIP the append (`tail -n 10 ... | grep -F "$turn_id"`). Prevents duplicate logs on retries / subagent re-entry.

Reference append (illustrative — actual implementation lives in the skill runtime, not in this doc):

```bash
log=holding/state/interaction/log.jsonl
mkdir -p "$(dirname "$log")"
if ! tail -n 10 "$log" 2>/dev/null | grep -qF "\"turn_id\":\"$TURN_ID\""; then
  printf '%s\n' "$ROW_JSON" >> "$log"
fi
```

## Failure policy

Codex P2.5 fold. Two independent posture choices:

| Failure | Posture | Behavior |
|---------|---------|----------|
| Classifier non-zero exit / malformed JSON / `jq` missing | **fail-CLOSED for log row** | SKIP the JSONL append. Don't write malformed entries. Emit a single-line stderr warning: `h-sutra: classifier failed for turn $TURN_ID`. |
| Same as above | **fail-OPEN for downstream** | NEVER block input-routing, blueprint, depth-estimation, build-layer, or any other governance skill from running. The skill's exit status is always `0` because the skill is informational, not gating. |

Header tag policy on classifier failure: emit `[H-SUTRA-FAIL · classifier]` so the founder sees the failure inline, then continue with the rest of the response stack.

## Stage-3 OUT-DIRECT discipline (ADR-002)

Before emitting any draft `REQUEST·HUMAN-EXEC` (Sutra asking the founder to run a terminal command), apply the **OUT-DIRECT 3-check**. If NONE hit → demote to internal action (Sutra runs via own Bash) + emit OUT-ASSERT (INFORM). If ANY hit → surface REQUEST·HUMAN-EXEC.

| # | Check | Hits when |
|---|---|---|
| 1 | `cant-self-exec` | command needs interactive TTY (`gcloud auth login`), GUI not in headless, requires founder OAuth, or no Bash path exists |
| 2 | `denylist-hit` | falls in the 6-domain irreversible denylist defined in ADR-001 §4 Rule 4 verbatim — (a) destructive file ops · (b) external sends · (c) founder-reputation outputs · (d) money movement · (e) legal/compliance · (f) irreversible publication |
| 3 | `opt-out` | command class explicitly marked "always founder-runs" |

These 3 checks are exhaustive. No 4th gate.

### Demotion telemetry

When the 3-check demotes, log the demotion on the **existing turn row** in `holding/state/interaction/log.jsonl` (one-row-per-turn invariant preserved). Add three optional fields:

```json
{
  "out_direct_3check_hits": [],
  "out_direct_demoted": true,
  "original_out_form": "REQUEST·HUMAN-EXEC"
}
```

When surfaced (≥1 check hits), `out_direct_3check_hits` is non-empty (e.g. `["denylist-hit"]`), `out_direct_demoted` is `false`, `original_out_form` is `REQUEST·HUMAN-EXEC`.

When no OUT-DIRECT was drafted this turn (most turns), all three fields are absent OR `out_direct_demoted=false` + `original_out_form=null`.

### Parallel-but-different to OUT-QUERY 3-check

Both gates share the same shape (3 boolean checks gating Stage-3 emission) but address different failure modes: OUT-QUERY 3-check kills over-asking; OUT-DIRECT 3-check kills over-handoff. Same shape, different semantic content. **Parallel, NOT symmetric.**

### Discipline mode

This is a **model-side self-check at emission time**. NOT classifier-side — `classify.sh` stays INBOUND-only (ADR-001 invariant preserved). Audit-only post-surface scan deferred to v1.1+ (ADR-N).

## v1.0 limits

Instrumentation + safety guardrails ONLY. Per D42: visibility before influence.

| In v1.0 | Not in v1.0 (backlog → ADR-002+) |
|---------|----------------------------------|
| Classification (9-cell × 3-tag) | Behavior-optimization rules (over-asking fix beyond bounded retry) |
| Header tag emission | `AUDIENCE` tag |
| JSONL log row append | `CONTINUITY` tags (`CONTINUE` / `RESUME` / `REFINE`) |
| Bounded retry safety (1 attempt then proceed-or-refuse) | `SEVERITY` tag |
| Irreversible-domain denylist | Cross-turn behavior shaping |

## Evolution

Every change to this skill ships as a numbered ADR plus a regression test, per Charter §Evolution discipline. ADR-001 (commit b88b7cc) is the baseline. New tags, new fail postures, or new header fields must land as ADR-002 / ADR-003 / etc. with an update to `tests/h-sutra/` covering the new behavior.

## Self-check

Before producing the header tag, the skill MUST verify:

- [ ] Input Routing block already present in the response, OR `IR_TYPE` env var supplied to the classifier.
- [ ] Classifier exit code captured (and JSON parse attempted).
- [ ] Header format matches exactly: one line, bracketed, ` · ` separators, uppercase keys, no extra whitespace, no missing required fields.
- [ ] Log row append committed (or deliberately skipped per Failure policy with a stderr warning).
- [ ] Header tag is the FIRST text in the response, prepended ABOVE Input Routing as a SEPARATE single line — never below, never replacing it. (Charter §Stage 3 invariant.)

If any check fails, do not emit a malformed header. Emit `[H-SUTRA-FAIL · self-check]` and continue with the rest of the per-turn block stack.
