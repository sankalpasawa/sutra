# Shadow — Current State

> Source of truth for what Shadow actually does today.
> This document should be based on code inspection, not product aspirations.

---

## Status: NOT YET POPULATED

**This document is a placeholder. It should be populated after the Shadow
implementation audit** (run `prompts/audit.md` against the codebase).

Until that audit runs, every section below is empty on purpose. An empty
section here means "not yet inspected" — it does not mean "not implemented."

### Rules for populating this document

| Rule | Detail |
|------|--------|
| Evidence required | Every claim cites a file path, and a line or symbol where useful |
| Classify everything | `IMPLEMENTED` / `PARTIAL` / `UI-ONLY` / `MOCK` / `UNCLEAR` / `NOT IMPLEMENTED` |
| No aspiration | If `shadow_context.md` describes it but the code does not do it, that belongs in **Known Limitations**, not in the section body |
| No silent promotion | Never convert `INFERENCE → FACT` or `UI concept → implemented behavior` (see `shadow_context.md` §36, Source Discipline) |
| Date the inspection | Note the commit or date the audit was run against; code moves, this document does not update itself |

### Relationship to the other documents

| Document | Answers |
|----------|---------|
| `shadow_context.md` | What we believe Shadow is *supposed* to be |
| `current_state.md` (this file) | What the code *actually does* |
| `decisions.md` | What we have *explicitly decided* |
| `experiments.md` | What we *learned* from using Shadow |
| `prompts/` | Reusable instructions for Claude Code |

Do not merge these. A gap between `shadow_context.md` and this file is a
finding, not an inconsistency to be tidied away.

---

## Runtime Architecture

## Delegation / Mission Flow

## Worker Relationship

## Supervision Loop

## Intervention

## Completion / Verification

## Mission States

## Autonomy

## Safety / Authority

## Memory

## Persistence

## Watch

## Attention

## Presence

## Human Escalation

## Tests

## Known Limitations

## Open Implementation Questions

---

## Pre-existing Shadow documentation (needs future reconciliation)

Two Shadow-related documents already exist elsewhere in this repository. They
predate this workspace, they have **not** been read, verified, or reconciled
against `shadow_context.md`, and neither has been modified.

| File | Size | Last modified | Status |
|------|------|---------------|--------|
| `marketplace/plugin/sutra-ui/SHADOW.md` | 7.6 KB | 2026-09-13 | Unreviewed — needs investigation |
| `os/native/surfaces/shadow.md` | 1.9 KB | 2026-09-07 | Unreviewed — needs investigation |

Open questions for the reconciliation pass:

1. Does either document describe implemented behavior, or intended behavior?
2. Where either contradicts `shadow_context.md`, which is authoritative?
3. Should either be superseded by this workspace, kept as a surface-specific
   spec, or folded into `current_state.md` as evidence?

Do not reconcile these until the implementation audit has run — otherwise the
reconciliation is a comparison of two aspirational documents with no ground
truth between them.
