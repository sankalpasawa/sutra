---
part-id: P0
bucket: pillars
template: L1-pov
parity-source: FOUNDING-DOCTRINE.md Principle 0 + sutra-defaults.json .customer_focus_first (cap-112) + CLAUDE.md Core Behaviors mirror
parity-source-sha256: 2a8b9a1a07a5056f15e367599a972ac0cca21b39ea0ab7b5bc73093ed8c980fb
status: DRAFT v1
authored: 2026-06-12
---

# P0: Customer Focus First

## Pillar statement

> Every output serves the person reading it. If the customer needs explanation to understand, fix it. Supersedes all other principles. Per FOUNDING-DOCTRINE.md Principle 0 (verbatim): "Every output serves the person reading it. If the customer needs explanation to understand, fix it. Supersedes all other principles."

P0 is not a peer of P1-P21 — it is the doctrine parent that every pillar inherits from. The §10.4 doctrine-tension table already resolves pillar conflicts AGAINST doctrine (P11 vs Customer Focus is recorded there); this file makes the parent itself a first-class part-file so the supersession rule is canon, not folklore.

## What this rules in

- **Supersession**: when any pillar, tone register, brevity default, or governance format conflicts with the reader's ability to understand customer-facing output, the conflict resolves to P0. Precedence is the load-bearing clause, not just the rule text.
- Downstream tone/format policies MUST declare their P0 scope boundary explicitly — production precedent: Anti-Glaze tone scopes itself to founder-facing only because customer-facing output routes through P0 (CLAUDE.md Core Behaviors).
- Fleet distribution as policy schema: `sutra-defaults.json` `.customer_focus_first` (v2.26.0) carries rule + precedence + `source_doctrine` pointer + kill-switch `{CUSTOMER_FOCUS_DISABLED=1, ~/.customer-focus-disabled}`.
- Enforcement `convention_only` with coverage note "policy-visible, not behavior-verified" — production deliberately chose this as TERMINAL status after the 2026-05-15 codex/deepseek triage convergence (a hard hook here was judged theater). CSM row cap-112 = shipping (policy-visible).

## What this rules out

- Any pillar or policy claiming exemption from P0 — there is no output surface outside its scope (`applies_to: all_responses`).
- Tone/format policies shipped WITHOUT a declared P0 scope boundary.
- A behavior-verification hook for P0 — explicitly rejected as terminal-status decision; re-opening requires founder + dual-AI re-review, not an implementation PR.
- Treating the doctrine as Asawa-local memory: it is fleet policy (sutra-defaults.json), doctrine file, and CLAUDE.md mirror simultaneously; the schema is the shipped form.

## Falsification test

**If any Native output ships that its reader cannot understand without explanation, and the conflicting policy (tone, brevity, governance format) is upheld over the reader → P0 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists for P0; P0 predates the pillar table as L0 doctrine.)

## Doctrine inheritance (from L0)

P0 IS the L0 doctrine entering the pillar bucket — it does not inherit; it is inherited FROM. Per §10.4, Customer Focus First is named parent-of-all-pillars and is the arbiter in the recorded P11-vs-Customer-Focus tension. The 5 Doctrine tests (Dynamic · Flexible · Scalable · Simple · Nuanced) sit beside P0 at Hierarchy Level 0; P0 carries the explicit supersession clause among them.

(FOUNDING-DOCTRINE.md is a 2026-06-12 reconstruction; P0's operative text survives verbatim via cap-112/CLAUDE.md cross-references. The 5-Tests per-test elaboration prose is recorded LOST — a gap to surface via founder re-authoring, not invent inline.)

## References

- /Users/asawa/Claude/root-os/FOUNDING-DOCTRINE.md — Principle 0 operative text + Hierarchy Level 0 standing (production evidence).
- sutra/marketplace/plugin/sutra-defaults.json `.customer_focus_first` — fleet-shipped policy schema: rule, precedence, source_doctrine, kill_switch (production evidence).
- /Users/asawa/Claude/asawa-holding/CLAUDE.md Core Behaviors — instruction mirror + Anti-Glaze P0 scope boundary (production evidence).
- holding/CAPABILITY-MAP.md — cap-112 row; policy-visible-is-terminal status discipline (production evidence).
- holding/PRODUCT-DOC-STANDARD.md — L0 PRINCIPLES layer citing FOUNDING-DOCTRINE.md as source-of-truth.
- NATIVE-ENGINE.md §10.4 — doctrine-tension table (P0 as arbiter in P11 tension).
- `./P14-outcomes-drive-design.md` — P14 already quotes P0 verbatim as its parent; P0 file is the canonical home.
- Parity-source deviation: this part fills a canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production source docs per MIGRATION-PLAN §9 limitation #2.
