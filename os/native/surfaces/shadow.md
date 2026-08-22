---
part-id: SHADOW
bucket: surfaces
template: L9-surface-spec
parity-source: founder direction 2026-08-22 (no engine canon section yet; product surface pointer)
parity-source-sha256: none
status: DRAFT v0
authored: 2026-08-22
---

# Surface: SHADOW

Companion overlay on Sutra Desktop; the product lives at `holding/plans/shadow/INDEX.md`. This part-file exists so the Native canon knows the surface exists and what it may call.

| field | value |
|---|---|
| **status** | DRAFT v0 — pointer only; promote to full L9 spec when Shadow calls Native surfaces (M2) |
| **updated** | 2026-08-22 |

## Purpose

Shadow sees the app, prompts the founder minimally, records instructions, and — from M2 — acts through Native surfaces rather than around them.

## Interface (operator-facing)

| Shadow does | via Native surface | from |
|---|---|---|
| records an instruction + founder confirmation | AUDIT (EngineEvent + DecisionProvenance) | MVP |
| replays a standing instruction | ROUTE -> RUN under GATE | M2 |
| files a fix for Sutra itself | RUN (Teamsutra workflow) | M3 |

## Invariants (must always hold)

| invariant | source |
|---|---|
| every Shadow action emits exactly one EngineEvent with instruction provenance | AUDIT row 5 |
| Shadow never bypasses GATE for non-idempotent actions | DESIGN.md §5 hard floor |
| nothing leaves the machine | CONTEXT-MODEL §2 |

## Open questions

| # | question |
|---|---|
| 1 | does Shadow's instruction ledger become a Native primitive (Instruction) or stay product-local |

---

provenance: {author: claude (session a1834e18), date: 2026-08-22, inputs: [holding/plans/shadow/*, surfaces/audit.md shape], review: dual-lane (via product docs), supersedes: none, confidence: low, gaps: [no parity-source canon section; D54 routing says product facts stay in product docs — this file is a pointer by founder request]}
