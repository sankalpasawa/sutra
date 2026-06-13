# ADR-024: §1.0 Architecture-Block Canon Migration (FORK — founder decision)

**Status**: PROPOSED (founder-gated; surfaced 2026-06-13; dual-lane codex+deepseek both recommend this fork)
**Date**: 2026-06-13
**Context anchor**: surfaced while grounding ADR-023 / components bucket; dual-lane verdict file `.enforcement/codex-reviews/2026-06-13-govui-directive-1781320510.md` (DIRECTIVE-ID 1781320510, CHANGES-REQUIRED).

## Context

Grounding for the governance-UI work revealed a structural gap: **none of the 8 §1.0 architecture blocks (UI · Host · Orchestration · System of Process · System of Record · Authority+Tenancy · Compute · External World) exist as canon part-files.** Only the B-numbered *product feature* blocks do. The architecture blocks' behavior — including the UI block's F.x trust gates, G.x error surfaces, M1-M6 modalities that components C1/C3 cite — lives ONLY in the frozen, founder-UNLOCKED monolith `holding/website/native/master/index.html` §1.0.1 / §2.F.

Consequence: components citing architecture-block behavior have no canonical anchor; their provenance points at an unlocked website doc, not canon.

## Decision needed (the fork — NOT yet decided)

How do the 8 §1.0 architecture blocks become canon?

| Option | Shape | Cost | Risk |
|---|---|---|---|
| A | New canon bucket `arch-blocks/` — 8 part-files, one per §1.0 block, extracted from §1.0.1 | M-L | overlaps the parallel IA migration (Session A is homing these in the website); must coordinate |
| B | Fold architecture-block contracts into existing buckets (e.g. surfaces/ + primitives/) | M | conceptual mismatch — arch blocks aren't surfaces or primitives |
| C | Architecture blocks stay website-only (PRD layer); canon never holds them; components cite the website via a blessed citation form | S | violates D54 spirit (normative behavior outside canon); provenance stays soft |

## Why deferred (both reviewers CONFIRMED)

1. **Source is founder-unlocked** — §1.0.1 second-order is "WORKING DRAFT, founder review pending." Canonizing now would lock draft content.
2. **It is a whole layer (8 blocks), not the UI block alone** — a UI-only promotion creates asymmetric canon.
3. **Overlaps Session A's active IA migration** — which is extracting these same block sections into website pages. Unilateral canon promotion risks collision + duplication.

## Recommendation (for founder)

Option A (new `arch-blocks/` bucket), sequenced AFTER: (a) founder locks the §1.0.1 second-order block diagrams, and (b) coordination with the IA-migration session on canon-vs-website ownership. Until then, components C1/C2/C3 remain DRAFT and cite §1.0.1 via ADR-023 Context with an explicit OPEN provenance note.

## Consequences

- Until resolved: governance-UI LLD (C1/C2/C3) cannot be normatively locked; the exposure matrix in components/INDEX.md stays PROVISIONAL.
- This ADR is the tracking home for the decision; it does not itself migrate anything.
