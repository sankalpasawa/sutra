# Sutra — Blueprint Engine

ENFORCEMENT: V1 SOFT (skill-only) → V2 HARD (hook-enforced; marker-flag gate D48)
STATUS: V2 SHIPPED 2026-05-05 (Wave 1 — foundational paths only; Wave 2 broadens 2026-05-19)
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

## The Block (V2 format — D48 2026-05-05)

Generated once per founder turn, after INPUT ROUTING + DEPTH blocks, before any Edit/Write/Bash/Agent tool call. ASCII only (D-UX-1).

```
+-- BLUEPRINT --------------------------------------------------+
| Doing: <plain-English task statement>                         |
| Steps: 1) <step> 2) <step> 3) <step>                          |
| Output looks like: <concrete observable target>               |
| Verified by: <runnable check - cmd, grep, file, screenshot>   |
| Scale: <files>, <time>, <cost>                                |
| Stops if: <abort condition>                                   |
| Switch: ON | OFF (override: BLUEPRINT_ACK=1 reason)           |
+---------------------------------------------------------------+
```

Seven fields, all required: **Doing / Steps / Output looks like / Verified by / Scale / Stops if / Switch**. Output + Verified added per D48 — task-type work pre-declares target + runnable check. Trivial verification rejected: "works", "passes", "done", "no errors", "it runs", "looks good", "tested", "verified".

For Depth ≥ 4 or branching tasks, the block may extend to a heavy-ASCII multi-step diagram. For Depth 1-2 trivial work, the compact form above is sufficient. Founder-readability is the gate.

## Marker schema (V2)

After emitting the block, write `.claude/blueprint-registered`:
```
HAS_OUTPUT=1
HAS_VERIFY=1
TASK=<task-slug>
TS=<unix-timestamp>
```

Hook `blueprint-check.sh` reads marker; HARD-blocks foundational-path edits when `HAS_OUTPUT=0` or `HAS_VERIFY=0`. SOFT advisory elsewhere (Wave 1). Wave 2 (2026-05-19) broadens HARD to all Edit/Write if override rate clean.

## State-mismatch flow (V2 — D48)

When the `Verified by` cmd returns fail:
1. File problem record at `holding/state/problems/<ts>-<slug>.json` (audit trail).
2. In-session LLM (Claude) reads failure output, diagnoses root cause, picks fix.
3. Apply fix via Edit/Write/Bash.
4. Re-run `Verified by` cmd.
5. Pass → attest, close problem, done. Fail → goto 1, iteration += 1.
6. Hard cap = 3 iterations → STOP, surface boxed blocker to founder.

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
