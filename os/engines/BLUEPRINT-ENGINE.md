# Sutra — Blueprint Engine

ENFORCEMENT: SOFT (V1 — skill-only, self-emitted) → HARD (V2+ — hook-enforced)
STATUS: V1 SHIPPED 2026-04-27
DRI: CEO of Asawa (founder direction); engine-of-record for all BLUEPRINT improvements.

---

## Purpose

The Blueprint Engine generates a per-task plan-preview block that prints BEFORE Claude takes any tool action. The founder gains a pre-spend intervention point — sees the planned steps, scale (files / time / cost), stops-if conditions, and kill-switch state in one founder-readable block.

The engine is the durable home for this primitive. The current skill (`core:blueprint`) is V1's raw form. As localized memory accrues — per-task patterns, founder-revised formats, depth-aware variants — the engine grows beyond what a stateless skill can hold.

---

## Doctrine — Engine vs Skill (founder, 2026-04-27 refined)

| Term | What it is | Analog |
|------|------------|--------|
| **Skill** | Raw form of intelligence — stateless rule, same in every invocation | Knowledge |
| **Engine** | A **bound** (container) for skills + **project-level** memory/time/context | Wisdom |

A **skill** is a stateless rule. Same instruction, same output, every time.

An **engine** is the **bound** that wraps a set of skills AND binds them to the **project's** evolving state. The PROJECT is the meta-layer. The founder is one actor in the project — not the center. Other actors: the codebase, milestones, partners, regulatory state, supply chain, fleet, time itself.

The three powers an engine has that a skill alone does not are all **project-level**:

| Power | Project-level meaning |
|-------|----------------------|
| **Memory** | How the project's history has shaped what works — architectures tried, patterns retired, decisions made, paths abandoned |
| **Time** | How the project has evolved — phase changes, milestone shifts, doctrine generations, priority resets |
| **Context** | What surrounds the project right now — other companies, dependencies, partners, fleet state, current focus |

**Engine = nothing by default.** An engine ships as an **empty bound** — a slot with a doorplate, no skills inside, no project state loaded. As skills get added and project state accumulates, the engine fills.

**Engines update over time.** Right now updates are **manual**; stringent update protocols (when to update, by whom, with what acceptance criteria) are deferred until the pattern stabilizes.

**V1 of any new primitive = a skill inside an empty engine bound.** V2+ fills the bound — skills accumulate, project memory/time/context become legible, and the engine begins applying skills with awareness of project state.

---

## The Block (V1 format)

Generated once per founder turn, after INPUT ROUTING + DEPTH blocks, before any Edit/Write/Bash/Agent tool call.

```
┌─ BLUEPRINT ─────────────────────────────────────────────────┐
│ Doing: <plain-English task statement>                        │
│ Steps: 1) <step> 2) <step> 3) <step> ...                     │
│ Scale: <files>, <time>, <cost>                               │
│ Stops if: <abort condition>                                  │
│ Switch: ON | OFF (override: BLUEPRINT_ACK=1 reason)          │
└──────────────────────────────────────────────────────────────┘
```

Five fields, all required: **Doing / Steps / Scale / Stops if / Switch**.

For Depth ≥ 4 or branching tasks, the block may extend to a heavy-ASCII multi-step diagram with arrows and decision branches. For Depth 1-2 trivial work, the compact form above is sufficient. Founder-readability is the gate.

---

## When It Fires

- Every founder turn that will result in any Edit / Write / Bash / Agent tool call
- After: INPUT ROUTING block, DEPTH + ESTIMATION block
- Before: any tool call

NOT fired for: pure-question turns Claude answers from context with no tool calls.

---

## Kill-Switch (3 levels — D32 pattern)

| Level | Mechanism | Scope |
|-------|-----------|-------|
| Per-turn | `BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <command>` | Single tool call |
| Per-machine | `touch ~/.blueprint-disabled` | All sessions on this machine |
| Fleet | `BLUEPRINT_BLOCK: false` in `sutra/os/SUTRA-CONFIG.md` | All clients |

When kill-switch is active → block omitted, single line emitted: `BLUEPRINT skipped (kill-switch: <level>)`. Ledger row written to `.enforcement/blueprint-ledger.jsonl` (V2 — V1 has no ledger).

---

## V1 Scope (skill-only, self-emitted)

V1 ships:
- Skill at `sutra/marketplace/plugin/skills/blueprint/SKILL.md`
- This engine charter (declares intent + future)
- CLAUDE.md mandatory-blocks update
- Memory routing entry (`project_blueprint_engine.md`)
- H-AI charter P11 implementation entry: V1 SHIPPED

V1 does NOT ship:
- Hook enforcement (deferred to V2 if drift observed)
- 4-fixture test (deferred to V2)
- `.enforcement/blueprint-ledger.jsonl` (deferred to V2)
- Operationalization 6-section block (deferred — V1 is skill, not L0/L1 protocol)

---

## V2+ Roadmap

When localized memory becomes valuable:

| Version | Adds |
|---------|------|
| V2 | PreToolUse hook `blueprint-check.sh` blocks Edit/Write/Bash if marker missing. 4-fixture test. Ledger. |
| V3 | Format adaptation. Engine remembers founder's preferred format per task type (compact vs heavy, depth-gated). |
| V4 | Multi-block. Branching tasks get multi-block blueprints with explicit decision points. |
| V5 | Cross-session continuity. Engine recognizes recurring task shapes and pre-populates blueprints. |

---

## Operationalization (V1 stub — full 6-section in V2)

V1 is skill-only. Full operationalization (per D30a 6-section template) ships when V2 promotes to plugin-shipped enforcement. V1 is exempt because it does not change runtime behavior — Claude self-emits the block per skill instruction; no hook, no enforcement, no per-fleet wiring.

When V2 ships, this section gets the standard 6 subsections: Measurement / Adoption / Monitoring / Iteration / DRI / Decommission.

---

## Improvement Routing

**Future founder direction containing the words: "blueprint", "task preview", "plan block", "pre-task", "before doing" → improvements route to this engine.**

This is the durable home for all BLUEPRINT-related improvements. Memory entry `project_blueprint_engine.md` carries the routing rule so it surfaces in future conversations. Do NOT spawn parallel doctrine for blueprint variants — extend this engine.

---

## Related

- Skill: `sutra/marketplace/plugin/skills/blueprint/SKILL.md`
- H-AI charter P11 (Implementations registry): `holding/HUMAN-AI-INTERACTION.md`
- Mandatory-block declaration: `CLAUDE.md` § Mandatory Blocks
- Backlog tracker: `holding/TODO.md` (cascade entry 2026-04-27)
- D-direction: TBD (D36 already taken by PROTO-024 + LLM-agnostic federation; D37+ when ratified)
- Codex review (PROTO-019): pending on V1 diff
