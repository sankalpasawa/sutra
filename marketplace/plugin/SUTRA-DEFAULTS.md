# Sutra Defaults — Plugin Convention Pack

**Source-of-truth**: this file (human-readable) + `sutra-defaults.json` (machine-readable; consumed by hooks/skills).

**Audience**: Sutra plugin clients. These are the conventions Sutra recommends every session emit by default. They're how Asawa (the holding company that builds Sutra) operates day-to-day, now shipped as plugin defaults so every client gets the same discipline.

**Authority**: Founder direction D40 (2026-04-30) — *"Every governance discipline Asawa uses must be available to every Sutra plugin client by default."*

**Status**: HARD for Asawa-owned (T1/T2 per D34); RECOMMENDED for T3/T4 with override path documented below.

**Core principle**: skills + docs EXPLAIN; hooks ENFORCE. There is **one** canonical policy substrate — `sutra-defaults.json` — consumed by all hooks/skills/commands. No duplication.

---

## The Five Per-Turn Blocks

Every turn — **including pure-question turns**, not just Edit/Write turns — emits these blocks before responding to the user.

### 1. Input Routing

```
INPUT: [what the user said]
TYPE: direction | task | feedback | new concept | question
EXISTING HOME: [where this already lives, or "none"]
ROUTE: [which protocol/file/skill handles this]
FIT CHECK: [what changes in existing architecture]
ACTION: [proposed action]
```

Skill: `core:input-routing`. Soft hint: `per-turn-discipline-prompt.sh` reminds you on every turn.

### 2. Depth + Estimation

Before the work:

```
TASK: "[what you're about to do]"
DEPTH: X/5 (surface | considered | thorough | rigorous | exhaustive)
EFFORT: [time, files]
COST: ~$X
IMPACT: [what changes for whom]
```

After completion:

```
TRIAGE: depth_selected=X, depth_correct=X, class=[correct|over|under]
ESTIMATE: tokens_est=N, files_est=M, time_min_est=T
ACTUAL: tokens=<observed>, files=<touched>, time_min=<measured>
```

Skill: `core:depth-estimation`. Auto-captured by `estimation-collector.sh`.

### 3. BLUEPRINT (when tool calls planned)

```
+- BLUEPRINT --------------------------------------------------+
| Doing: <plain-English task statement>                         |
| Steps: 1) <step> 2) <step> 3) <step>                          |
| Scale: <files>, <time>, <cost>                                |
| Stops if: <abort condition>                                   |
| Switch: ON | OFF                                              |
+--------------------------------------------------------------+
```

Skill: `core:blueprint`. Hook: `blueprint-check.sh`. Skip on pure-question turns.

### 4. Build-Layer (when path is governed by D38)

```
BUILD-LAYER: L0 | L1 | L2
ACTIVATION-SCOPE: fleet | cohort:<name> | single-instance:<name>
TARGET-PATH: <abs path>
```

L0 = plugin-shipped (fleet); L1 = staging with promotion deadline; L2 = instance-only forever. Hook: `build-layer-check.sh`.

### 5. Output Trace (one line per response, end of turn)

```
> route: <skill> > <domain> > <nodes> > <terminal>
```

Skill: `core:output-trace`. Default verbosity L1.

---

## Consult-Before-Edit Policy

**At Depth >= 3 with Edit/Write/MultiEdit planned**, consult codex (or another second opinion) **before** the first Edit/Write call.

**Mechanism**: invoke `core:codex-sutra` skill (consult mode) with a tight <500-word prompt summarizing the proposed change + 3-5 questions. Keep codex calls under 5 minutes (chunk if needed).

**Convergence pattern**: if codex agrees, execute end-to-end without per-step approval. If codex diverges, surface to user and re-decide.

Per `consult_policy` in `sutra-defaults.json`.

---

## Skill Explanation Cards (4-line)

Before invoking any Skill, emit a 4-line card so the user can predict the experience:

```
SKILL:  <name>
WHAT:   <what it does in one sentence>
WHY:    <why it applies to this task>
EXPECT: <what you'll see — interactions, files written, time>
ASKS:   <what input the skill will request from the user>
```

Skill: `core:skill-explain`. **Convention only** — Claude Code lacks a PreSkillUse hook so no enforcement is possible. Hooks ENFORCE; this convention EXPLAINS.

---

## Subagent Dispatch Contract

Every Agent/Task tool dispatch prompt opens with:

```
§Sutra discipline (mandatory)
1. Input Routing block
2. Depth + Estimation block
3. Build-Layer marker (if D38 path)
4. Operationalization 6-section ops block (per artifact)
5. Codex review per layer (xhigh / high / medium)
```

And ends with a 4-line footer:

```
TRIAGE: <values>
ESTIMATE: <values>
ACTUAL: <values>
OS TRACE: <one line>
```

Hook: `subagent-dispatch-brief.sh` (soft hint on PreToolUse Task).

---

## Output Discipline

- **Tables > prose** when comparing options
- **Numbers > adjectives** when describing scale ("200 LOC" not "small")
- **ASCII boxes** for decisions (no unicode box-drawing chars)
- **Progress bars** for scores (`#####.....` 5/10)
- **Decisions boxed** so user can't miss them

Skill: `core:readability-gate`. Applied at output time.

---

## Override Path

**Per-installation override**: edit `~/.sutra/overrides.json` (created on first override) to disable specific defaults.

**Per-command override**: `BLUEPRINT_ACK=1 BLUEPRINT_ACK_REASON='<why>' <tool>` for one-off overrides (audit-logged).

**Kill-switches** (full disable):
- `touch ~/.sutra-defaults-disabled` — disables all defaults (escape hatch)
- `BLUEPRINT_BLOCK: false` in `sutra/os/SUTRA-CONFIG.md` — blueprint specifically

---

## Why These Defaults

These conventions emerged from Asawa's day-to-day operation as the holding company that builds Sutra. They're not theoretical — they're the actual discipline that makes a multi-company AI-augmented operation work without dropping balls.

Per D40: every Sutra plugin client inherits these defaults so the discipline ships, not just the skills. Per Codex's caveat: hooks injecting prompt text are **soft guidance only** — fragility includes prompt dilution, prompt collision, token bloat, cosmetic emission, and subagent drift. Where deterministic checks exist, they back the soft hints.

**Source-of-truth chain**: D40 (`holding/FOUNDER-DIRECTIONS.md`) → this file (human-readable) → `sutra-defaults.json` (machine-readable) → hooks/skills consume json.

## Flow activation (v2.39.16) — INLINE block every turn, Skill for substantive work

`core:flow` FIRES on EVERY input — the way Input Routing fires — by emitting an INLINE FLOW block (literal text the model emits), NOT by invoking the Skill tool. A hook cannot force a Skill on the first pass, so the per-turn artifact is literal text (D61, amended 2026-06-15). The full `core:flow` Skill (deep recursive spine) is reserved for substantive / multi-step / ambiguous / unknown-how work.

| Turn | What fires |
|---|---|
| every input (task / direction / new_concept / question / feedback / chitchat) | INLINE FLOW block (literal text) + write flow markers via the Write tool |
| substantive / multi-step / ambiguous / unknown-how | additionally invoke the full `core:flow` Skill (deep recursive spine) |

The block reports the honest resolved spine for the unit: [1] TYPE/cell → [2] FOLLOW a workflow type (child→platform) or CONSTRUCT → [3] steps → [4] inner engine (factors + lens + Cynefin) → [5] mode per step → [6] close. **Honesty bar**: state what ACTUALLY resolved — an honest 1-step ATOM block on a trivial turn is correct; faking the full spine is theater.

**Enforcement**: HARD, fleet-wide, via two FLOORS (not the firing). `flow-gate.sh` (PreToolUse) blocks an Edit/Write/Task that skipped classify+resolve. `flow-stop-check.sh` (Stop) forces one redo when Flow didn't fire on a no-tool turn (loop-safe via `stop_hook_active`). Both depend on markers persisting — write them via the Write tool (Claude Code rolls back sandboxed Bash writes to `.claude/`). Kill-switches: `FLOW_DISABLED=1` / `~/.flow-disabled` / `FLOW_ACK=1`.
