---
part-id: P18
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md §D18 + EXTERNAL-CLIENT-INSTALL.md 2-command contract + scripts/go.sh
parity-source-sha256: 68b58e7217e9ed1de1ee87b701c1abfef49cb2e70ec5f31054a55c4146136800
status: DRAFT v1
authored: 2026-06-12
---

# P18: Packaging before launch

## Pillar statement

> Packaging IS the product, and packaging work precedes launch work on every roadmap. Per FOUNDER-DIRECTIONS.md D18 (founder verbatim): *"People won't use it if it's not packaged."* Install friction gates all adoption; until a stranger can reach a governed working session in a bounded number of steps, there is nothing to launch. This pillar is the doctrine statement only — packaging/channel/onboarding mechanics live in Native §6 (Distribution) and are not duplicated here.

## What this rules in

- Roadmap ordering: packaging and install UX are scheduled BEFORE launch activities ("Week 1-2, not Week 3-4" in the original direction), and dogfooded before public launch — production sequence: built + dogfooded (CM9, DayFlow) before launch per the D29 cascade.
- A hard install ceiling as the product contract — production shape: 2 commands plus one activation step (EXTERNAL-CLIENT-INSTALL.md: `/plugin marketplace add` + `/plugin install`, then one-shot `go.sh` onboard+telemetry+banner).
- Host-quirk hardening as part of packaging, not an afterthought — production lesson: jq replacing python3 for EDR-killed hosts (v2.18.0); fail-open install paths.
- Channel-change hygiene: when the distribution channel changes (npx → marketplace plugin), the enforcement-registry row is rewritten, not left FUTURE — production's DIRECTION-ENFORCEMENT row D18 still reads FUTURE against the dead npx framing; port the lesson, not the staleness.

## What this rules out

- Launching anything whose install path has not been packaged and dogfooded.
- Treating install UX as post-launch polish — friction at minute zero is a product defect, not an ops issue.
- Speculative channel mechanics in doctrine: the channel is replaceable (npm shipped, was retired to `sutra/archive/package-v1.2.1-retired/`; the plugin channel replaced it); the principle is not.
- Duplicating §6 Distribution mechanics into this pillar.

## Falsification test

**If a Native launch activity (announcement, cohort onboard, public listing) is scheduled before its install path meets the packaged contract (bounded-command install + one-shot activation, dogfooded) → P18 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P18 is a post-cutover gap-fill.)

## Doctrine inheritance (from L0)

P18 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Inheritance via L0 directly — Customer Focus First (`./P0-customer-focus-first.md`): the install path is the customer's FIRST output to read; if they need explanation to get running, fix the packaging. Alignment with the Scalable test is direct (adoption scales only through the packaged channel).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md §D18 — doctrine + founder verbatim (production evidence).
- holding/DIRECTION-ENFORCEMENT.md row D18 — honest-but-stale FUTURE row under dead npx framing (production evidence; the staleness is itself a ported lesson).
- sutra/marketplace/plugin/EXTERNAL-CLIENT-INSTALL.md — 2-command install contract (production evidence).
- sutra/marketplace/plugin/scripts/go.sh — one-shot onboard+telemetry+announce (production evidence).
- sutra/marketplace/plugin/scripts/start.sh + scripts/onboard.sh — activation surfaces (production evidence).
- Native §6 (Distribution) — packaging/channel/onboarding mechanics; this pillar states only the doctrine.
- `./P0-customer-focus-first.md` — doctrine parent.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production source docs per MIGRATION-PLAN §9 limitation #2.
