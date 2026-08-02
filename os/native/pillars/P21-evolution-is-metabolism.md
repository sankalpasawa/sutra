---
part-id: P21
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md D37 index row + PROTOCOLS.md §PROTO-025 + plugin hook structural-move-check.sh
parity-source-sha256: 48efa56c17a27312f80331e4306c33349a9d07defe942c6f564498d526944659  # whole-file digest of FOUNDER-DIRECTIONS.md; intentionally identical to P20 (both sources are sections of that single file)
status: DRAFT v1
authored: 2026-06-12
---

# P21: Evolution is the metabolism

## Pillar statement

> Evolution is not a folder, not a side-project, not an abstraction layer — it is the meta-process by which the company-system evolves as a whole. Six activities are its scope, verbatim from D37: **structural moves** (mv/rm/archive), **charter changes**, **protocol additions/retirements**, **fleet propagation**, **feedback absorption**, and **abstraction-ladder analysis** (concrete feature → primitive → customization surface → meta-self-creation). A system that cannot name its own metabolism restructures itself silently.

## What this rules in

- Evolution as a NAMED meta-process with an enforcement spine: any structural operation on a governance-HARD path requires current-turn authorization (build-layer marker), is blocked exit-2 without it, and is ledgered (PROTO-025; plugin hook `structural-move-check.sh`, PreToolUse:Bash).
- The same-marker-two-trigger-surfaces design: Edit/Write guarded by build-layer-check, Bash mv/rm/git-mv guarded by structural-move-check — one authorization, every mutation channel.
- Override only with explicit ACK env + reason, always audit-logged (honor-system at env level, evidence-system at ledger level).
- The founding incident, as the source states it: D37's own text names "Trigger: 2026-04-06 unauthorized archive of `holding/evolution/` — restored in `87fb3ca`" and names PROTO-025 as the enforcement spine in the same row (sourced verbatim from FOUNDER-DIRECTIONS.md D37; not an inferred causality) — evolution artifacts can never again be silently restructured.

## What this rules out

- Treating evolution as a backlog item or department rather than the system's own change-metabolism.
- Structural moves on governance paths without a declared, ledgered authorization in the same turn.
- Fleet changes (protocol add/retire, charter change) that propagate without the meta-process naming them.

## Falsification test

**If a structural operation (move/delete/rename) lands on a governance-HARD path with no authorization marker in that turn and no ledger row — and nothing blocked it → P21 broken.** (Production contract: exit 2 + JSONL ledger row; port verbatim.)

## Doctrine inheritance (from L0)

P21 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill). Customer Focus First (`./P0-customer-focus-first.md`) applies as parent: the metabolism exists so change never silently degrades what the operator depends on. Alignment with the Dynamic test is direct (the system is built to evolve — but only legibly).

(If a tension exists in practice but is not in §10.4, surface it via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md D37 index row — full doctrine text incl. the six activities (production evidence; index-only by renumber history, see D57 note).
- sutra/layer2-operating-system/PROTOCOLS.md §PROTO-025 Structural-Move Authorization — ACTIVE, HARD-ON-CODE (production evidence).
- sutra/marketplace/plugin/hooks/structural-move-check.sh — the enforcement hook, fleet L0 (production evidence).
- holding/hooks/structural-move-check.test.sh — shipped test per PROTO-000 (production evidence).
- holding/evolution/ — the protected artifact family; 2026-04-06 incident is the founding case.
- `../blocks/B13-multi-runtime-concurrency.md` + `../blocks/7e-mid-exec-mutation.md` — execution-time parallelism, explicitly NOT this pillar's scope (evolve-while-in-use is a different axis, see `./P19-parallel-evolution-own-project.md`).
- `./P0-customer-focus-first.md` — doctrine parent.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production governing text + enforcement per MIGRATION-PLAN §9 limitation #2.
