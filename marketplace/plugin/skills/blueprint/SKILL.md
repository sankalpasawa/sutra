---
name: blueprint
description: Use before tool calls that MUTATE state (Edit/Write/MultiEdit), branch (Agent), or run multi-step plans. Skip for read-only single-call turns and pure questions. Emits BLUEPRINT block (Doing / Steps / Scale / Stops-if / Switch) so the founder sees the plan before Claude takes action. Honors 3-level kill-switch (env / fs / SUTRA-CONFIG). Task-shape gate per D-UX-2 codex ADVISORY 2026-05-04 (was "any tool call"; revised to mutation/branching/multi-step). Engine of record at sutra/os/engines/BLUEPRINT-ENGINE.md.
---

# BLUEPRINT — Pre-task Plan Preview

Every founder turn that will result in any tool call gets a BLUEPRINT block. Emit it AFTER the INPUT ROUTING + DEPTH blocks, BEFORE any Edit / Write / Bash / Agent tool call.

## The block

```
+--- BLUEPRINT --------------------------------------------------+
| Doing: <plain-English task statement>                          |
| Steps: 1) <step> 2) <step> 3) <step>                           |
| Output looks like: <concrete observable target>                |
| Verified by: <runnable check - cmd, grep, file, screenshot>    |
| Scale: <files>, <time>, <cost>                                 |
| Stops if: <abort condition>                                    |
| Switch: ON | OFF (override: BLUEPRINT_ACK=1 reason)            |
+----------------------------------------------------------------+
```

ASCII-only per CLAUDE.md (D-UX-1 codex 2026-05-04). Native renderer at sutra/marketplace/native/src/renderers/terminal-events.ts is the canonical reference.

Seven fields, all required (Output + Verified added per D48, 2026-05-05):

- **Doing** — one plain-English sentence. No jargon. No protocol IDs. No filenames unless central.
- **Steps** — numbered, max 6. If more, group. Use `→` for sequence inside a step if needed.
- **Output looks like** *(D48)* — concrete observable target. Specific (file path + content sketch / exit code / screenshot criteria). NOT "it works" or "done".
- **Verified by** *(D48)* — a runnable check that returns pass/fail. Examples: `bash test-foo.sh` (exit 0), `grep -q "X" file`, `curl -fsS URL`, `test -x path`, multimodal screenshot + attestation. Trivial values ("works", "passes", "done", "no errors", "it runs", "looks good", "tested", "verified") are rejected.
- **Scale** — files touched, time estimate, cost (~$X)
- **Stops if** — what condition aborts the plan and triggers re-blueprint
- **Switch** — `ON` normally; `OFF` if any kill-switch level is active

## Marker write (after emitting the block)

Write `.claude/blueprint-registered` with:
```
HAS_OUTPUT=1
HAS_VERIFY=1
TASK=<task-slug>
TS=<unix-timestamp>
```

`HAS_OUTPUT=1` and `HAS_VERIFY=1` are honor-system flags — set them only when the BLUEPRINT actually contains both new lines with non-trivial values. Hook `blueprint-check.sh` reads the marker and rejects edits to foundational paths (charters, protocols, FOUNDER-DIRECTIONS, sutra/os/engines, design plans) when either flag is missing.

## Verification kinds (pick one for `Verified by`)

| Kind | Example |
|---|---|
| Shell test | `bash sutra/marketplace/plugin/tests/unit/test-foo.sh` |
| Typecheck / lint | `npx tsc --noEmit` |
| Grep contract | `grep -q "<expected>" <file>` |
| File existence | `test -x <path>` |
| HTTP / deploy | `curl -fsS <url> \| grep -q '<title>'` |
| Hook re-run + diff | `bash holding/scripts/capability-audit.sh` |
| Multimodal / visual | Playwright screenshot to `/tmp/<slug>.png` + Claude reads + attests visual criteria |
| LLM eval (codex) | `bash holding/scripts/codex-review.sh <diff>` |
| Bundle (multi-step) | `bash scripts/verify-<task>.sh` (wraps several checks) |

## On verification FAIL (state mismatch)

1. File problem record at `holding/state/problems/<ts>-<slug>.json` (audit trail).
2. In-session LLM (Claude itself) reads failure output, diagnoses root cause, picks fix.
3. Apply fix via Edit/Write/Bash.
4. Re-run `Verified by` cmd.
5. Pass → attest, close problem, done. Fail → goto 1, iteration += 1.
6. Hard cap: iteration = 3 → STOP, surface boxed blocker to founder.

## Format escalation (depth-aware)

| Depth | Default format |
|-------|----------------|
| 1-2 (trivial) | Compact box (above) |
| 3 (multi-file) | Compact box; may use `→ → →` arrows in Steps for clarity |
| 4-5 (significant / exhaustive) | Heavy-ASCII multi-step diagram OK if branching adds clarity |

When in doubt: compact box. Founder-readability is the gate.

## Kill-switch (3 levels)

Skip the block AND emit a single explanatory line if any of these are active:

| Level | Mechanism | Detect via |
|-------|-----------|------------|
| Per-turn | `BLUEPRINT_ACK=1` env var | `${BLUEPRINT_ACK:-}` non-empty |
| Per-machine | `~/.blueprint-disabled` file | `[ -f ~/.blueprint-disabled ]` |
| Fleet | `BLUEPRINT_BLOCK: false` in `sutra/os/SUTRA-CONFIG.md` | grep config key |

When skipped, emit one line: `BLUEPRINT skipped (kill-switch: <level>)` — nothing else.

## When NOT to fire

- Pure-question turns (no tool calls planned)
- Read-only single-Read responses (block is fine, but Steps may be just `1) Read X`)
- After kill-switch active

## Self-check before emission

After drafting, verify:
- Doing is one sentence
- Steps ≤ 6
- **Output looks like** is concrete (file path / exit code / observable criteria) — not "works" or "done"
- **Verified by** is runnable (shell cmd, grep, curl, test, multimodal recipe) — not in trivial blocklist
- Scale has all three: files / time / cost
- Stops if is concrete (not "if something fails")
- Switch matches reality (kill-switch state actually checked)

If any check fails, redraft. After emitting, write the marker with `HAS_OUTPUT=1 HAS_VERIFY=1` only if both new fields are non-trivial.

## Engine of record

Durable home: `sutra/os/engines/BLUEPRINT-ENGINE.md`. Future founder feedback on BLUEPRINT format, scope, or behavior routes to that engine — not to new doctrine. This skill is V1's raw form; the engine will accumulate memory and supersede the skill in V2+.

## Order in the per-turn block stack

```
1. INPUT ROUTING block          (skill: core:input-routing)
2. DEPTH + ESTIMATION block     (skill: core:depth-estimation)
3. BLUEPRINT block              (skill: core:blueprint) ← THIS ONE
4. BUILD-LAYER block            (only when editing protected paths)
5. ... tool calls ...
6. OUTPUT TRACE one-liner       (skill: core:output-trace)
```
