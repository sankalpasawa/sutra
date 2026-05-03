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
| Scale: <files>, <time>, <cost>                                 |
| Stops if: <abort condition>                                    |
| Switch: ON | OFF (override: BLUEPRINT_ACK=1 reason)            |
+----------------------------------------------------------------+
```

ASCII-only per CLAUDE.md (D-UX-1 codex 2026-05-04: "ASCII everywhere; unicode buys nothing here and violates the written rule plus terminal/log portability"). Native renderer at sutra/marketplace/native/src/renderers/terminal-events.ts is the canonical reference (line 6: "no unicode box-drawing — readable in any terminal + log file").

Five fields, all required:

- **Doing** — one plain-English sentence. No jargon. No protocol IDs. No filenames unless central.
- **Steps** — numbered, max 6. If more, group. Use `→` for sequence inside a step if needed.
- **Scale** — files touched, time estimate, cost (~$X)
- **Stops if** — what condition aborts the plan and triggers re-blueprint
- **Switch** — `ON` normally; `OFF` if any kill-switch level is active

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
- Scale has all three: files / time / cost
- Stops if is concrete (not "if something fails")
- Switch matches reality (kill-switch state actually checked)

If any check fails, redraft.

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
