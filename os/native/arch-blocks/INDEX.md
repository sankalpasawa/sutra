---
part-id: arch-blocks-INDEX
bucket: arch-blocks
template: bucket-index
parity-source: master/index.html §1.0 + §1.0.1 second-order block diagrams
status: DRAFT v1
authored: 2026-06-13
governed-by: ADR-024 (Option A — canonize the 8 §1.0 architecture blocks)
---

# Architecture Blocks (§1.0) — canon bucket

The 8 blocks of the locked §1.0 runtime schema. Created per ADR-024 (Option A) to close the gap where the architecture blocks had no canon home (only product feature blocks B* did). Source = the §1.0.1 second-order diagrams in the frozen monolith, which are founder-UNLOCKED working drafts — so all entries are DRAFT, each carrying a `parity-source-sha256` drift sentinel; promote to authoritative as the founder locks each §1.0.1 block.

| Block | File | Status | §1.0.1 source anchor |
|---|---|---|---|
| UI (Consumer Product) | [ui.md](ui.md) | **DRAFT v1 — authored** | #so-ui + §2.F |
| Host (Claude CLI) | host.md | SEED — pending | #so-host |
| Orchestration | orchestration.md | SEED — pending | #so-orchestration |
| System of Process | system-of-process.md | SEED — pending | #so-system-of-process |
| System of Record | system-of-record.md | SEED — pending | #so-system-of-record |
| Authority + Tenancy | authority-tenancy.md | SEED — pending | #so-authority-tenancy |
| Compute | compute.md | SEED — pending | #so-compute |
| External World | external-world.md | SEED — pending | #so-external-world |

**Authoring queue**: UI done (it is the critical path — unblocks components C1/C3 per ADR-023). The other 7 are SEED-pending: author on founder lock of their §1.0.1 second-order + coordination with the IA-migration session (Session A builds the website renders of these same blocks). Authoring one block = extract its #so-* second-order into a part-file mirroring ui.md's shape (role · parts · invariants · prohibitions · open gaps · downstream consumers), capture source SHA.
