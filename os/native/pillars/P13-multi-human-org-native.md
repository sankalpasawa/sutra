---
part-id: P13
bucket: pillars
template: L1-pov
parity-source: §10.2 row P13 + §10.3 row P13 + §10.4 row P13
parity-source-sha256: 9ab85e4f4db19497a8eb586c11140d4aa6cf1df56b79af19edcb907927f0615b
status: DRAFT v1
authored: 2026-05-09
---

# P13: Multi-human-org-Native architecture

## Pillar statement

> Each human has their own Native instance; Natives interact at the organizational level; org-shared artifacts are addressable. Per §10.2 row P13: "each human has own Native; Natives interact; org-shared artifacts." Native's organizational model is one-Native-per-human (not one-Native-per-org), with cross-Native addressing for shared artifacts. v1 ships single-human Native; the org-tenant primitive is wired into v1 schema with logic deferred to v2+ (per codex consult round-3 2026-05-09).

## What this rules in

- One Native instance per human operator (not one per organization).
- Cross-Native addressing for org-shared artifacts.
- v1 ships single-human Native; org-tenant primitive present in v1 schema (per §10.4 resolution).
- v2+ ships the org-level interaction logic.

## What this rules out

- Two operators in the same org sharing one Native instance (per §10.3 P13 falsification, post-v2 form).
- Natives that cannot address each other for org-shared artifacts (per §10.3 P13 falsification, post-v2 form).
- Org-as-primary-unit-of-Native architecture (the human is primary; the org is composed).

## Falsification test

**v1 = single-human-Native (org mode = v2+ scope per codex consult round-3 2026-05-09). Post-v2: if two operators in same org share one Native instance OR Natives cannot address each other for org-shared artifacts → P13 broken.** (Exact text from §10.3 row P13.)

## Doctrine inheritance (from L0)

§10.4 lists a direct tension: **P13 (multi-human-org) vs Doctrine "Scalable" (1 → 100 companies)**. Resolution per §10.4: "org-tenant primitive built into v1 schema (deferred logic)." The Scalable test is satisfied at v1 by carrying the org-tenant primitive in the schema even though logic is deferred — the architecture does not need a v2 rewrite to scale to multi-human-org; only logic activation. This preserves the scalability test without forcing P13's full logic into v1.

## References

- NATIVE-ENGINE.md §10.2 row P13 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P13 — falsification test (v1 vs post-v2 phasing).
- NATIVE-ENGINE.md §10.4 row P13 — doctrine tension + resolution.
- `../primitives/tenant.md` — org-tenant primitive (Phase 5; v1 schema slot, v2+ logic).
- Codex consult round-3 (2026-05-09) — phased v1/v2+ falsification ratified.
