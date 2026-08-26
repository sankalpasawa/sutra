---
name: updating-canon
description: Decision tree for editing a canon layer (engine charters + ADRs). Route any new architectural fact to exactly one home — charter section, new ADR, both, archive, or reject — instead of scattering it across research/plan files. Generalized 2026-08-26 from the Asawa Native-canon discipline (D54).
---

> Fleet note: path examples below are from the originating repo (Asawa). Map them to YOUR canon: engines of record at `os/engines/` (or the plugin mirrors at `plugin/os/engines/`), decisions at `os/decisions/`, archives at your repo's archive dir. The five-step routing logic is the skill; the paths are examples.

---
name: updating-native-canon
description: Decision tree for adding new Native information after Phase 1.5 lock-in. Routes every new fact to charter-edit OR new ADR; blocks scattered writes.
type: write-routing-rule
---

# Updating Native Canon (post-D54)

## Trigger
Any session where new information about Native (primitives, decisions, behavior, integration, ops) needs to land in the repo.

## Decision tree

1. Is the new info a **runtime contract change** (primitive added, invariant changed, integration boundary moved)?
   - YES → **edit `sutra/os/engines/NATIVE-ENGINE.md`** §matching-section AND open a new ADR explaining WHY
   - NO → continue to step 2

2. Is the new info a **decision rationale** (we chose X over Y because Z)?
   - YES → **create new `sutra/os/decisions/ADR-NNN-<slug>.md`** (next sequence number); follow `writing-adr` standard
   - NO → continue to step 3

3. Is the new info **operational findings / observability data / runtime telemetry insight**?
   - YES → if it changes the charter's Operations section → edit charter; otherwise → ADR if it justifies a new decision; otherwise → likely ephemeral, do NOT persist as Native canon
   - NO → continue to step 4

4. Is the new info **purely historical (post-mortem of a past wave)**?
   - YES → does NOT belong in canon. Either: (a) skip if redundant with existing archive, or (b) add a row to `_archive/native-v1.x/INDEX.md` if it's a new archive entry
   - NO → continue to step 5

5. **Default reject**: if none of 1–4 fit, the info is probably scattered-doc territory. Do NOT write to `holding/research/*native*` or `holding/plans/native-*`. Surface to founder; ask if it warrants a new ADR or charter edit.

## Hard rules (post-D54)
- NEVER write a new file at `holding/research/*native*.md` or `holding/plans/native-*.md`
- NEVER edit `holding/RESUME-NATIVE-CHARTER.md` (archived; superseded by NATIVE-ENGINE.md)
- NEVER duplicate charter content in an ADR (link instead)
- ALWAYS: if both charter-edit AND new ADR fit, do BOTH (charter says WHAT; ADR says WHY)
- ALWAYS: any change to charter contract triggers a new ADR explaining why

## Discoverability
This skill content is also referenced from `CLAUDE.md` "Native Canon" section and from D54 in `FOUNDER-DIRECTIONS.md`. Future Claude sessions reading either inherit this routing.

## Verification (per-edit)
- Before commit: `git diff --name-only` shows ONLY paths in the allowed set (charter, ADRs, INDEX, archive, governance lock files)
- If diff includes `holding/research/*native*` or `holding/plans/native-*`: ABORT, route via this skill
