---
part-id: P20
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md §D25 + DIRECTION-ENFORCEMENT.md row D25
parity-source-sha256: 48efa56c17a27312f80331e4306c33349a9d07defe942c6f564498d526944659  # whole-file digest of FOUNDER-DIRECTIONS.md; intentionally identical to P21 (both sources are sections of that single file)
status: DRAFT v1
authored: 2026-06-12
---

# P20: Technical and scientific rigor

## Pillar statement

> Use proper technical terminology, verbatim from D25: formal methods (invariants, safety/liveness), distributed systems (consensus, Byzantine fault tolerance), military doctrine (Standing Orders, ROE), software patterns (sealed classes, policy engines). **No plain-language approximations where precise terms exist.** The system must be legible to engineers, architects, and domain experts.

## What this rules in

- The four named vocabularies as the default naming sources when designing architecture, protocols, or documentation, or when naming concepts (D25 trigger conditions, DIRECTION-ENFORCEMENT row D25, SOFT, ACTIVE).
- Terminology check at authoring time: applied through Native's industry-anchored doc templates (`core:native-author-part`) as part of the template review step — the discipline lives in the authoring path, not a runtime hook.
- Rigor-as-practice already visible across canon: typed events, invariants, hardstops, sealed primitive sets — P20 names the doctrine those practices follow.

## What this rules out

- Plain-language approximations where a precise domain term exists ("rule that always applies" where "invariant" is meant; "wait for everyone" where "completion barrier" is meant).
- Inventing project-local vocabulary for concepts the four named fields already name.
- Runtime enforcement machinery for this pillar — production never needed a hook for it (doc-only by design), and Native does not add one.

## Falsification test

**If a newly authored canon part merges without a terminology-check line in its review record (the `core:native-author-part` template review step), or a merged part names a concept with a plain-language approximation for which one of the four vocabularies has the precise term (checkable by grep against the part's nouns) → P20 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P20 is a post-cutover gap-fill. deepseek MODIFY absorbed 2026-06-12: test made mechanical — record-presence + grep, not reviewer judgment.)

## Doctrine inheritance (from L0)

P20 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Customer Focus First (`./P0-customer-focus-first.md`) applies as parent with a real boundary: precision serves the expert reader; operator-facing surfaces (UI, §2.F) still translate to operator language — P20 governs system-internal naming and engineering documents, not the consumer voice. Alignment with the Nuanced test is direct.

(If a tension exists in practice but is not in §10.4, surface it via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md §D25 — operative rule, quoted verbatim above (production evidence).
- holding/DIRECTION-ENFORCEMENT.md row D25 — TRIGGER/ENFORCEMENT/STATUS (production evidence).
- sutra/layer2-operating-system/PARALLELIZATION-ARCHITECTURE.md — example of the discipline practiced (consensus/barrier vocabulary in use).
- `./P12-deterministic-surface-stochastic-core.md`, `./P14-outcomes-drive-design.md` — frame rigor-as-infrastructure; P20 states the terminology doctrine they assume.
- `./P0-customer-focus-first.md` — doctrine parent; operator-voice boundary.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production governing text per MIGRATION-PLAN §9 limitation #2.
