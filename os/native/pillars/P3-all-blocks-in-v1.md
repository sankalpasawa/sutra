---
part-id: P3
bucket: pillars
template: L1-pov
parity-source: §10.2 row P3 + §10.3 row P3 + §10.4 row P3
parity-source-sha256: 9bf17ed156dc4462df05c98a8ebccf0511b679485323d0db094d321709e87cba
status: DRAFT v1
authored: 2026-05-09
---

# P3: All blocks in v1

## Pillar statement

> Completeness beats depth-of-one-block. v1 ships every Native block as a stub at minimum, rather than shipping a few blocks deeply and the rest as TODO. Per §10.2 row P3: "completeness > depth-of-one-block; v1 ships every block as a stub minimum." The operator must see the full shape of Native at v1 — partial-shape Native is worse than full-shape stubs.

## What this rules in

- Every B-block (B1-B18 + 7a-7e + F1) ships in v1, even if logic is a stub (per §10.3 P3 falsification).
- Outcome-first ordering within the "all blocks" set — the top-5 v1 outcome blocks (per §14.15.2) get full logic first; remaining blocks ship as functional stubs.
- Founder-visible shape: at v1, the operator can navigate every block, even if some return "stub" responses.

## What this rules out

- Shipping v1 with any of B1-B18 + 7a-7e missing entirely (per §10.3 P3 falsification).
- "Deep on B9, nothing on B5/B18/etc." — partial-shape Native that hides the full architecture from the operator.
- Treating stubs as failure — stubs are a deliberate v1 completeness mechanism.

## Falsification test

**If v1 ships missing any of B1-B18 + 7a-7e → P3 broken; not feature-complete.** (Exact text from §10.3 row P3.)

## Doctrine inheritance (from L0)

§10.4 lists a direct tension: **P3 (all blocks v1) vs Doctrine "Simple" (10-min understandable)**. Resolution per §10.4: "v1 stubs are simple by design; logic added incrementally." Stubs satisfy "Simple" because each stub block has a minimal, understandable surface even when logic is incomplete. Completeness of the architecture (P3) and simplicity of any one block (Doctrine) are reconciled by deliberate stubbing rather than omission.

## References

- NATIVE-ENGINE.md §10.2 row P3 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P3 — falsification test.
- NATIVE-ENGINE.md §10.4 row P3 — doctrine tension + resolution.
- NATIVE-ENGINE.md §14.15.2 — outcome-first v1 ordering within all-blocks-shipped commitment.
- `./P14-outcomes-drive-design.md` — companion pillar: outcome-ordering within P3's completeness floor.
