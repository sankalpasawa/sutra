---
name: native-author-part
description: Authors a single Native canon part-file under sutra/os/native/<bucket>/<part-id>.md per the bucket-specific industry-anchored template. One of 11 bucket templates (blocks/pillars/events/primitives/hardstops/decisions/open-questions/doc-layers/surfaces/impl-phases/metrics) is applied. Captures parity-source SHA256 from NATIVE-ENGINE.md anchor section and writes it into the file header. Fires when invoked explicitly during Native canon migration (sutra/os/native/MIGRATION-PLAN.md Phase 1-11). Skip when authoring net-new architecture (use core:architect), when reviewing existing part-files (use core:codex-sutra review), when planning the migration itself (use core:incremental-architect), or when bulk-extracting (use parallel subagent dispatch). Output is a single canonical markdown file plus an audit log entry; this skill writes ONE file at a time. Captures founder-domain-language in the part-file body but applies the industry-anchored template (Google PRD/Sinek WHY/Nygard ADR/Sean Ellis Amplitude/Lenny Rachitsky/CloudEvents/Stripe RFC/Keep-a-Changelog/Linear cycle/Domain-Driven Design) for shape consistency. Founder-restricted via build-layer marker (L0 plugin).
allowed-tools: Read, Write, Bash, Grep
---

# Native Author Part — single per-part canon authoring

This skill writes ONE canon part-file at a time under `sutra/os/native/<bucket>/<part-id>.md`. It is the canonical authoring primitive for the Native canon decomposition (see `sutra/os/native/MIGRATION-PLAN.md` v1.1+). Each invocation reads the source anchor in `sutra/os/engines/NATIVE-ENGINE.md`, applies the bucket-specific template, writes the file, and emits a parity-audit log row.

## Skill card

- **WHAT**: write one part-file at `sutra/os/native/<bucket>/<part-id>.md` per the bucket's industry-anchored template.
- **WHY**: 127-part decomposition of Native canon requires consistent shape per category; ad-hoc authoring breaks parity audits and template guarantees.
- **EXPECT**: one new markdown file (~40-100 lines depending on template); one JSONL row appended to `.enforcement/native-migration-semantic-audit.jsonl`; one SHA256 captured at `.enforcement/native-migration-source-checksums.jsonl`.
- **ASKS**: 0 if `part-id` + `bucket` are passed; 1-2 if ambiguous (which template variant for blocks).

`allowed-tools` rationale: `Read` for source anchor + template, `Write` for new part-file + audit log, `Bash` narrowly for SHA256 + audit append, `Grep` for source-anchor location.

## Inputs

| Input | Required? | Default | Notes |
|---|---|---|---|
| `part-id` | yes | — | e.g., `B9`, `P14`, `HS-3`, `ExecutionStarted`, `route`, `phase-A`, `Q4`, `L1`, `Workflow`, `north-star-ohs` |
| `bucket` | yes | derived from part-id pattern | one of: blocks, pillars, events, primitives, hardstops, open-questions, doc-layers, surfaces, impl-phases, metrics. (decisions = LINK only, no file authored.) |
| `source-anchor` | optional | derived | `§N.M` reference within `NATIVE-ENGINE.md`. If omitted, skill greps for canonical anchor pattern. |
| `force` | optional | false | overwrite existing file if true; reject otherwise. |

## 11 Bucket templates

### Template 1: blocks (B1-B18 + 7a-7e + F1) — L8 Feature Spec (Google PRD + Lenny Rachitsky)

```markdown
---
part-id: <e.g., B9>
bucket: blocks
template: L8-feature-spec
parity-source: §<canonical-anchor>
parity-source-sha256: <captured-on-author>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <Part-id>: <Block Name>

## 1-line summary
<One sentence. Active voice. Founder-comprehensible.>

## Scope (in / out)
- **In scope**: <bullet list>
- **Out of scope**: <bullet list — explicit NGs>

## User outcome (the operator gets ___)
<Sinek WHY layer compressed to one paragraph: WHAT the operator gets in their life.>

## UX flow (narrative, not screens)
<Step-by-step user-side flow. No UI — Native is terminal+log.>

## Acceptance criteria (Given/When/Then)
| # | Given | When | Then |
|---|---|---|---|

## Data model
<Typed primitives consumed/produced. References to sutra/os/native/primitives/*.md.>

## Edge cases
<Failure modes, surprising inputs, race conditions.>

## Telemetry
<Events emitted; metrics affected. References to sutra/os/native/events/*.md and metrics/north-star-ohs.md.>

## Dependencies
- Primitives: <list>
- Events: <list>
- Surfaces: <list>
- Hardstops that fire here: <list>

## References
- NATIVE-ENGINE.md §<anchor>
- Cross-links to other part-files
```

### Template 2: pillars (P1-P14) — L1 POV (Sinek Golden Circle)

```markdown
---
part-id: <e.g., P14>
bucket: pillars
template: L1-pov
parity-source: §10.2 + §10.3
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <P-id>: <Pillar Name>

## Pillar statement (one paragraph)
<The WHY. What we believe. Sinek-style.>

## What this rules in
<Behaviors / decisions consistent with this pillar.>

## What this rules out
<Behaviors / decisions inconsistent with this pillar.>

## Falsification test
<When this pillar is broken — observable failure mode. From §10.3.>

## Doctrine inheritance (from L0)
<Which Founding Doctrine principle this pillar derives from. Resolution of any tension.>

## References
- NATIVE-ENGINE.md §10.2 row for <P-id>
- Founding Doctrine link
```

### Template 3: events (26 types) — L9 Tech Spec (CloudEvents-style + Twelve-Factor)

```markdown
---
part-id: <e.g., ExecutionStarted>
bucket: events
template: L9-event-spec
parity-source: §3.2
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <Event Type>

## Purpose
<What this event signals.>

## Schema (CloudEvents 1.0 form)
```json
{
  "specversion": "1.0",
  "type": "<event-type>",
  "source": "/<source>",
  "id": "<uuid>",
  "time": "<rfc3339>",
  "data": { /* typed payload */ }
}
```

## Emitter(s)
<Which surface(s) or block(s) emit this event.>

## Consumer(s)
<Which surface(s) / block(s) / hooks consume.>

## Ordering invariants
<Causal ordering rules; sequence guarantees.>

## Replayability
<Idempotent on replay? Side-effects? Audit-only?>

## References
- NATIVE-ENGINE.md §3.2 row for <event-type>
- Cross-links to emitter/consumer part-files
```

### Template 4: primitives (10) — L9 Tech Spec (DDD type signature)

```markdown
---
part-id: <e.g., Workflow>
bucket: primitives
template: L9-primitive-spec
parity-source: §2.<sub-section>
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <Primitive Name>

## Purpose
<What this typed contract represents.>

## Type signature (TypeScript-style)
```typescript
type <Name> = {
  // fields w/ types
}
```

## Invariants (must hold)
<Bullet list of properties that MUST hold across all instances.>

## Lifecycle (created → terminal states)
<State diagram in prose: how instances come into existence, transitions, terminal states.>

## Serialization (JSONL row shape)
<Persistence form — exact JSONL row schema.>

## Cross-primitive references
<Which other primitives this references (parent_id / tenant_id / etc).>

## References
- NATIVE-ENGINE.md §2.<sub-section>
```

### Template 5: hardstops (HS-1..HS-8) — ADR-style (Nygard) + STRIDE

```markdown
---
part-id: <e.g., HS-1>
bucket: hardstops
template: ADR-style-invariant
parity-source: §6.9.<sub-section>
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <HS-id>: <Hardstop Name>

## Status
ACTIVE

## Context (when this fires)
<Trigger condition; observable state that activates the hardstop.>

## Decision (fail-mode)
<What Native does when triggered. Fail-closed semantics.>

## Recovery path
<How operator gets unstuck. Manual override conditions.>

## Downstream effects
<What stops working when this fires; what alerts emit.>

## STRIDE relevance
<Spoofing/Tampering/Repudiation/Info-disclosure/DoS/Elevation — which threat this guards against.>

## References
- NATIVE-ENGINE.md §6.9 row for <HS-id>
```

### Template 6: open-questions (Q1-Q11) — Research-log (Stripe RFC)

```markdown
---
part-id: <e.g., Q4>
bucket: open-questions
template: research-log
parity-source: §14.10 + §12.4
parity-source-sha256: <captured>
status: ANSWERED | OPEN
answered: <YYYY-MM-DD or null>
authored: <YYYY-MM-DD>
---

# Q<id>: <Question summary>

## Question
<Verbatim question from §14.10 or §12.4.>

## Why it matters
<Product-shape consequence of the answer.>

## Default if unanswered
<Pre-answer default per §14.10 / §12.4 table.>

## Answer (if ANSWERED)
<Founder-ratified answer. Trace to in-session decision OR ADR-NNN.>

## Sources informing the answer
<Founder voice / memory / canon / agent research / codex consult.>

## References
- NATIVE-ENGINE.md §14.10 or §12.4 row for <Q-id>
```

### Template 7: doc-layers (8 layers) — L13 Release Note style (Keep-a-Changelog)

```markdown
---
part-id: <e.g., L1>
bucket: doc-layers
template: L13-release-note-style
parity-source: §10/§11/§12/§13/§14 preambles
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# <Layer-id>: <Doc Layer Name>

## Purpose (what this layer answers)
<One sentence — e.g., L1 = WHY we exist.>

## Producer (who authors)
<Role responsible. Usually founder for L1-L4/L6/L11/L14.>

## Consumer (who reads)
<Audience — founder / claude / codex / T4 fleet operators.>

## Cadence (how often refreshed)
<Per quarter / per release / per direction-change.>

## Ratification rules
<What it takes to flip DRAFT → RATIFIED.>

## Native instance (where this layer lives in canon)
<File path for the Native realization of this layer.>

## References
- holding/PRODUCT-DOC-STANDARD.md (L0-L14 spec)
- NATIVE-ENGINE.md anchor for Native instance
```

### Template 8: surfaces (6 surfaces) — L9 Tech Spec + C4

```markdown
---
part-id: <e.g., ROUTE>
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# Surface: <Surface Name>

## Purpose
<One sentence — what this surface does for the operator.>

## Interface (operator-facing)
<How the operator interacts. Inputs accepted.>

## Invariants (must always hold)
<Properties of the surface that never break.>

## Integration points
- Primitives consumed: <list>
- Events emitted: <list>
- Events consumed: <list>
- Surfaces upstream/downstream: <list>

## C4 context
<Where this surface sits in the C4 container view.>

## References
- NATIVE-ENGINE.md §14.7 + §<runtime-section>
```

### Template 9: impl-phases (5 phases) — L12 Roadmap (Linear cycle)

```markdown
---
part-id: <e.g., phase-A>
bucket: impl-phases
template: L12-roadmap-entry
parity-source: §14.15.1
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# Phase <id>: <Phase Name>

## Gate (entry criteria)
<What must be true to start.>

## Scope (what gets done)
<Bullet list of deliverables.>

## Duration (target wall-clock)
<Estimate.>

## DRI
<Responsible identity.>

## Acceptance (exit criteria)
<What proves the phase complete.>

## Dependencies (on other phases / blocks)
<List.>

## Rollback
<How to revert if phase needs undo.>

## References
- NATIVE-ENGINE.md §14.15.1 row for <phase>
```

### Template 10: metrics (1 file — N*) — L11 OKR (Sean Ellis Amplitude + Google OKR)

```markdown
---
part-id: north-star-ohs-per-week
bucket: metrics
template: L11-okr
parity-source: §11.2
parity-source-sha256: <captured>
status: DRAFT v1
authored: <YYYY-MM-DD>
---

# Operator-Hours-Saved per Week (OHS/wk)

## Definition
<Precise definition. What "operator hour saved" means.>

## Measurement
<How it's computed. Data sources. Cadence.>

## Targets
| Horizon | Target | Rationale |
|---|---|---|
| v1 baseline | 0 | pre-Native |
| v1 14d post-install | ≥3 OHS/wk | early adoption signal |
| v3 mature | ≥20 OHS/wk | sustained value |

## Leading inputs
<List of leading indicators that move N*.>

## What "winning" looks like
<Qualitative description — what 5-year success looks like.>

## References
- NATIVE-ENGINE.md §11.2
```

### Template 11: decisions (link only — no file authored)

```
Note: bucket "decisions" does NOT author new files via this skill.
ADRs already canonical at sutra/os/decisions/ADR-004*..017*.md.
Skill emits a manifest update only: append link to sutra/os/native/decisions/INDEX.md.
```

## Process (every invocation)

1. **Resolve bucket from part-id** (derive if not passed):
   - `B*` or `7[a-e]` or `F1` → blocks
   - `P*` → pillars
   - Mixed-case CamelCase (e.g., `ExecutionStarted`) → events OR primitives (disambiguate via grep on NATIVE-ENGINE.md §3.2 vs §2)
   - `HS-*` → hardstops
   - `Q*` → open-questions
   - `L*` → doc-layers
   - lowercase surface name → surfaces
   - `phase-*` → impl-phases
   - `north-star-*` → metrics
   - `ADR-*` → decisions (link only, no file authored — return INDEX-update directive)

2. **Locate source anchor in NATIVE-ENGINE.md** (`grep` for canonical anchor pattern).

3. **Capture SHA256** of the anchor section content: `sha256sum < (extract section)`. Append to `.enforcement/native-migration-source-checksums.jsonl` as `{anchor, sha256, ts, source_lines}`.

4. **Apply bucket template** (the 11 above) filling in:
   - Header frontmatter (part-id, bucket, parity-source, parity-source-sha256, status=DRAFT v1, authored=today)
   - Body — extracted from NATIVE-ENGINE.md anchor section, reformatted into template shape, no content loss

5. **Write file** at `sutra/os/native/<bucket>/<part-id>.md`. Reject (exit 2) if file exists AND `force=false`.

6. **Emit semantic-audit row** at `.enforcement/native-migration-semantic-audit.jsonl`: `{part_id, bucket, sha256, verdict=DRAFT, ts, source_anchor, output_path}`.

7. **Return** the path + the SHA256. Caller (claude orchestrator) is responsible for invoking codex review on the new file (per MIGRATION-PLAN.md §5 observability rule 7).

## When to use

| Trigger | Use this skill? |
|---|---|
| "Author B9 part-file" | Yes |
| "Decompose pillars bucket" | Yes (call 14 times, once per P-id) |
| "Bulk-author 24 block files" | Yes (parallel subagent dispatch; 4 concurrent per MQ2) |
| "Review B9 part-file after authoring" | No — use `core:codex-sutra` review |
| "Plan the next bucket migration phase" | No — see `sutra/os/native/MIGRATION-PLAN.md` |
| "Author a brand-new Native concept not yet in canon" | No — first add to NATIVE-ENGINE.md OR new ADR, then call this skill to extract |
| "Decommission engine doc post-migration" | No — see MIGRATION-PLAN.md Phase 13 |

## Failure modes to watch

- Source anchor not found → exit 2 with reason `anchor_not_found`; surface to caller.
- SHA256 capture fails (engine doc mid-edit) → exit 2 with reason `source_unstable`; retry after engine doc commit.
- Bucket cannot be derived from part-id → exit 2 with reason `ambiguous_bucket`; require explicit `bucket` arg.
- File exists + `force=false` → exit 2 with reason `file_exists`; require explicit force.

## Build-Layer

L0 (PLUGIN-RUNTIME, fleet). Ships with Sutra plugin v2.36+ to T4 fleet via marketplace.

## Composition with other Sutra + ecosystem skills

| When you need... | Use... |
|---|---|
| Plan the migration | `core:incremental-architect` (already done — MIGRATION-PLAN.md v1.1) |
| Author one part-file | this skill |
| Review one part-file | `core:codex-sutra` review or design-review |
| Bulk-author multiple files in parallel | claude orchestrator dispatches subagents, each calling this skill |
| Verify parity post-bucket | `holding/scripts/native-parity-audit-structural.sh` + `native-parity-audit-semantic.sh` (Phase 0c) |
| Decommission engine doc | MIGRATION-PLAN.md Phase 12 + decommission-gate hook (Phase 0d) |

## Eval pack

Three evals shipped in `evals/` next to this SKILL.md:
1. Author B9 part-file from §14.7 + §14.15.2 anchors → verify schema + SHA256 + audit row.
2. Reject duplicate-author of B9 with `force=false` → verify exit 2 + reason.
3. Derive bucket for ambiguous part-id `Workflow` (could be primitive OR block) → verify disambiguation.

## Self-score (optional telemetry, never a side effect)

If `holding/research/skill-adoption-log.jsonl` is writable AND telemetry not opted out — one row may be appended per invocation:

```json
{"date": "YYYY-MM-DD", "skill": "native-author-part", "career_track": 5, "mode": "Generative", "subject": "<part-id>", "bucket": "<bucket>", "template": "<template-id>", "wall_seconds": N, "sha256_ok": true}
```

If sink unwritable or opted out — silently skip.

## Upstream rules this skill embeds

- D54 (2026-05-07 + amendment 2026-05-09): forbidden paths under `holding/**` for native scatter; canonical paths under `sutra/os/native/**`.
- D38 plugin-first: this skill ships in plugin (L0), not in `holding/`.
- D52 autonomous push: skill's audit-log append is autonomous; founder confirms only on novel structural changes.
- D55 Structure-First: each part-file uses bucket-specific template; no ad-hoc shapes.
- MIGRATION-PLAN.md v1.1 §5 observability: parity-source SHA256 + semantic-audit row mandatory.
