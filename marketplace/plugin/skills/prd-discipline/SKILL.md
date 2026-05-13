---
name: prd-discipline
description: Use when authoring, editing, or extending any product-shaped artifact (PRDs, design docs, product specs, module specs, platform docs). Triggers on new product PRD start, section addition or rewrite, ask to "make this section better", peer-review verdict requiring fix, section bulking past readability threshold, or any time content is being added to a structured product document.
---

# PRD Discipline

## Overview

A product document is an operating contract between founder, builders, and operators. Discipline = the artifact stays readable, structurally honest, and gap-aware as it grows. Five invariants keep it that way.

## When to use

Any turn that writes to:

- A `product-prd-*.html` / `*-prd.md` / similar product spec
- A design doc that defines product shape
- A module/feature spec authored before code lands
- A charter or platform doc with operator-facing surface

## When NOT to use

- Engineering implementation notes (use code reviews + ADRs)
- Throwaway research drafts (use `holding/research/` patterns)
- One-line memos, chat replies, governance log entries

## The 5 Invariants

### 1. STRUCTURED

Section shape is declared BEFORE any content lands. No ad-hoc prose appended at the bottom.

- Default to numbered hierarchy: §0 → §1 → §1.1 → §1.1.1
- Every fact has exactly one home — the home is its anchor ID
- New facts join an existing section OR explicitly declare a new sub-section
- Reject "wherever it fits" content additions

**Namespace-collision check** (v2 — from baseline test 2026-05-13): before naming a new series identifier (Pillar `P-N`, Block `B-N`, Hardstop `HS-N`, ADR `ADR-N`, Open Question `Q-N`, Direction `D-N`, EngineEvent name), grep canon for existing reservations:

```bash
grep -rE "^P[0-9]+|HS-[0-9]+|ADR-[0-9]+|Q[0-9]+" sutra/os/native/ sutra/os/decisions/
```

Do NOT reuse a series prefix that canon already owns. If you must extend a canon series, declare the next free number; if the new thing is a different concept, pick a new prefix.

**Naming with alternatives** (v2): when introducing a new name (product, pillar, primitive, module), capture 2-3 alternatives + reasoning in `§Open questions`. Names are reversible at v1; far easier to refactor with the alternatives recorded than to rediscover them later.

**Why**: orphan facts decay. Operators cannot find or audit what has no home. Namespace collisions surface late and force expensive rename ripples.

### 2. VISUAL FIRST

If you compare ≥3 items → TABLE. If you describe a flow → DIAGRAM. If a decision must be impossible to miss → BOX IT.

| Element | When |
|---|---|
| `<table>` | ≥3 comparable items (features, options, tiers, gaps) |
| ASCII box `+----+` | Decisions, recommendations, status callouts (no Unicode per D-UX-1) |
| `<pre>` ASCII diagram | Flows, hierarchies, state machines |
| `<details>` collapsible | Reference inventories >10 items (drilldowns) |
| `<ul>` | 3-7 short items; longer → table or collapsible |

Prose is the fallback for nuance + judgment. Default visual; reach for prose only when the content is genuinely prose-shaped.

### 3. RESTRUCTURE-ON-BULK

When a section has accreted past readability, run D55 4-step **before** adding more:

1. **Survey** existing structure that the new content touches
2. **Reorganize** new + existing into one coherent shape
3. **Simplify** (dedupe, merge, delete redundancy)
4. **Surface** what was added, restructured, simplified, deleted

Triggers:

- Section feels like a pile rather than an outline
- Same fact appears 2+ times under different sub-headings
- Reader cannot scan-jump to the answer they need
- TOC entries point at parent anchors instead of specific sub-anchors
- Sub-section >1500 words OR `<h4>` block >500 words

Do NOT keep adding to a bulk section. Restructure FIRST, then add.

**Scale-undershoot rule** (v2 — from baseline test 2026-05-13): if the authored content falls SIGNIFICANTLY short of the declared scale (e.g., 770 lines vs 1500-2500 target), do NOT silently compress and ship. Surface a META-TODO in your **response** (not silently in the doc): "Content short of declared scale — sections X / Y / Z are thin; founder should ratify the trim OR I should extend." Silent compression hides the gap; explicit surface lets founder choose.

### 4. CONNECTED

Every section cross-references the sections it depends on or extends. No orphans.

- Cite anchor IDs, never prose ("see §4.5", not "see the test-before-conclude section")
- New fact → must link to the section it composes with
- Removed section → must redirect or migrate all inbound references
- Cross-cutting concerns appear in a single overlay section + are cited from each affected section

Audit check: every `href="#X"` must match an `id="X"` in the same doc. Zero misses.

**Canon-typed-entity rule** (v2 — from baseline test 2026-05-13): when referencing a canon-typed entity (EngineEvent name, HS-N hardstop, primitive name, ADR number, Pillar P-N, Surface name, Doc-layer L-N, Open-question Q-N), resolve the identifier to a canon path BEFORE writing. No invented EngineEvent names. No invented HS codes. No invented ADR numbers. If the entity does not yet exist in canon, mark `TODO(canon): <entity-kind> for <purpose>` and stop — do not invent the name.

### 5. GAP-SURFACING (not gap-filling)

When content is missing or unknown, MARK IT. Never fabricate to close the gap.

| Marker | When |
|---|---|
| `TODO(<owner>): <what>` | Known-required fact, founder/owner needs to fill |
| `Q-<NNN>: <question>` | Open question requiring decision |
| `Forward-looking: <fact>` + link | Known deferral with activation path |

Forbidden:

- Pulling content from training data to "look complete"
- Inventing example numbers, names, behaviors not in source material
- Padding a section with restatements of adjacent content
- Inferring founder intent from convention when the source is silent
- "Reasonable example" placeholders that read as real content

**TODO is not an alibi** (v2 — from baseline test 2026-05-13): writing `TODO: confirm X = <invented-Y>` where `<invented-Y>` is a plausible value you made up is STILL fabrication. The TODO marker does NOT license filling in a guess next to the question. The form is `TODO(<owner>): <question>` and the answer field STAYS EMPTY. If you find yourself drafting the answer "to help the founder", stop. The placeholder anchors thinking; an empty marker preserves the choice.

If the gap is large, surface it to the founder in the response — NOT in the artifact body.

## Section-authoring workflow

Run these 8 steps per section:

```
1. Declare section ID + parent
2. Identify the FACTS the section must carry (founder words + source paths)
3. Pick visual structure (table / diagram / callout / collapsible / list / prose)
4. Author content using ONLY facts from step 2
5. Mark gaps (TODO/Q/Forward-looking) for anything missing
6. Add cross-refs to sections this depends on / extends
7. If parent section is at bulk threshold → run 4-step restructure FIRST
8. Verify: anchor↔href closure + visual element present + zero fabricated content
```

## Composition with ADR-020

ADR-020 (Layer-B Product Authoring Template) defines WHAT sections a product PRD must contain. This skill defines HOW each section is written, restructured, and connected over time.

| Layer | Owner | Carries |
|---|---|---|
| WHAT | `sutra/os/decisions/ADR-020-*.md` | Section list (12 required), required canon files, pattern boundaries |
| HOW | This skill (`prd-discipline`) | Visual shape, restructure protocol, gap rules, anchor discipline |

Both compose. Either alone is insufficient.

## Red flags — STOP and restructure

| Symptom | Restart action |
|---|---|
| Pasting content "at the bottom" because "it fits there" | Survey first; assign a proper home OR declare a new sub-section |
| Section title doesn't accurately describe content | Rename OR split |
| Same concept defined in 2+ places | Pick one home; the others reference |
| Adding without removing — file size only grows | Force simplification step |
| TOC entry points at parent-§ anchor | Add the missing sub-section anchor + repoint |
| "I'll fill the gap with a reasonable example" | STOP. Mark as TODO. Surface to founder. |
| `<ul>` has grown to 12+ items | Convert to table or `<details>` collapsible |
| Section composes 3+ concerns without cross-refs | Author the overlay + cite from each affected section |

## Common rationalizations

| Excuse | Reality |
|---|---|
| "It's just one paragraph, doesn't need a table" | If you're comparing things, table beats prose every time |
| "I'll restructure later when I have more content" | Bulky sections never get restructured later |
| "The founder will know what I meant by this example" | Founder asked for no fabrication; mark as TODO |
| "Cross-ref is obvious from context" | Future reader is not in this conversation; cite anchor |
| "This section is short enough to skip the 4-step" | The 4-step is action-time default, not a section-size gate |
| "Adding one section won't trigger bulk" | The trigger is content scan-ability, not size; check ALL signals |
| "Mark as TODO loses momentum" | Fabricated content costs more momentum when peer review catches it |
| "TODO with a guess is better than empty" | The guess anchors founder thinking. Empty placeholder is the honest form. Strip the guess. |
| "I'll use a placeholder name and refactor later" | Names propagate fast through cross-refs. Name with alternatives recorded OR mark TODO(name). |
| "Scale undershoot is fine, the content is dense" | If you fell short of declared scale, surface that in your response — let founder decide trim vs extend. |
| "EngineEvent / HS code name is obvious from context" | Resolve to canon path BEFORE writing. Invented identifier names propagate as if real. |

## Verification checklist (per section)

- [ ] Section has stable anchor ID
- [ ] Section title accurately describes content (no marketing slop)
- [ ] At least one visual element present (table / diagram / callout / collapsible / list)
- [ ] All factual claims trace to founder words OR named source path
- [ ] All gaps marked (TODO/Q/Forward-looking); none fabricated
- [ ] Cross-refs cite anchor IDs (not prose)
- [ ] Section appears in TOC at correct level
- [ ] No duplicate content with adjacent sections
- [ ] If parent section was bulky → 4-step restructure performed first

## Anti-patterns

- **Narrative dumping** — paragraphs describing the history of how a design was reached. History belongs in ADRs or research, not PRDs.
- **Comprehensive bullet lists** — when a list grows to 12+ items, it's a table or a collapsible drilldown.
- **Inline schema dumps** — code, schemas, exhaustive enums belong in canon files. PRD body cites them, doesn't duplicate.
- **Founder-voice fabrication** — never author operator-voice content (pillar quotes, persona statements, vision claims) without founder fill. Mark + surface.
- **TOC collapse** — TOC entries all pointing to parent-§ anchors because sub-section anchors weren't authored. Always author the sub-section anchor first, then the TOC entry.
- **Section title drift** — title says X but body talks about Y. Rename or split.
- **Append-only authoring** — adding without restructuring grows toward unreadability.

## Iron law

**No new content into a bulk section. Restructure first.** No fabricated facts. No orphan facts. No prose where a table belongs. No silent gaps.

## Testing this skill

**v1 (2026-05-13)** — authored from R1-R11 PRD-review evidence (Native PRD codex+deepseek verdicts).

**v2 (2026-05-13)** — refactored from formal TDD baseline subagent test at `.enforcement/skill-tests/2026-05-13-prd-discipline-baseline.md`. Subagent wrote a Senior Expert Layer-B PRD WITHOUT loading this skill and captured 5 named rationalizations:

| # | Rationalization observed | Plugged in v2 |
|---|---|---|
| 1 | Scale undershoot silently absorbed (770 vs 1500-2500 lines) | §3 Scale-undershoot rule |
| 2 | Pillar namespace collision (P1-P5 vs canonical P1-P14) | §1 Namespace-collision check |
| 3 | Fabrication-as-completion (TODO + invented answer) | §5 TODO-is-not-an-alibi rule |
| 4 | EngineEvent names invented without canon check | §4 Canon-typed-entity rule |
| 5 | Product name "Senior Expert" never interrogated; alternatives unrecorded | §1 Naming-with-alternatives rule |

v3 follow-up: re-run baseline subagent test WITH v2 skill loaded; capture any new rationalizations the v2 rules don't yet address; plug those.
