---
part-id: P15
bucket: pillars
template: L1-pov
parity-source: sutra-defaults.json .right_effort (cap-108, v2.15.0) + CLAUDE.md §Right-Effort Discipline
parity-source-sha256: 62788aaf975fc7f54b412d8d1d77a64c26eee2b8d34b89a748a9cfc8157119cc
status: DRAFT v1
authored: 2026-06-12
---

# P15: Right-Effort discipline

## Pillar statement

> Before any state mutation (Edit/Write), four rules apply, verbatim from the fleet policy schema: **think_first** — "state assumptions; if multiple interpretations exist, ask. No silent guesses." **simpler_alt** — "if 200 lines could be 50, rewrite. No speculative abstractions." **surgical_scope** — "only changed lines that trace to the request. No drive-by refactors." **verify_loop** — "task = success criteria + verification. 'Make X work' → 'test passes'." The 4 principle strings are the IP; the plumbing around them is replaceable.

## What this rules in

- The 4 rules as a pre-mutation gate on every Edit/Write (`applies_before: [Edit, Write]` in the schema), fleet-shipped since v2.15.0.
- Schema-as-single-source: the runtime emitter (`per-turn-discipline-prompt.sh`, UserPromptSubmit) jq-reads `.right_effort.principles_short` at fire time — policy text is never hardcoded in the emitter.
- Dual kill-switch semantics: env (`RIGHT_EFFORT_DISABLED=1`) + file (`~/.right-effort-disabled`), both honored.
- Native evolution path: the 4 principles become the default typed `factors[]` on the Task lifecycle between SHAPE and PLAN, each weighted per the Sutra weight-distribution core IP — discipline becomes structural rather than a prompt nudge. Spec lives in `../blocks/B8-task-framework-factors.md` (which names Right-Effort its conceptual root 3x); B8 content is NOT duplicated here.
- Enforcement as convention (soft stderr nudge) backed by the deterministic Edit/Write hook stack elsewhere — the nudge reminds; the markers/hooks block.

## What this rules out

- Silent interpretation guesses when a request is ambiguous (think_first violation).
- Speculative abstractions and 200-line solutions to 50-line problems (simpler_alt violation).
- Drive-by refactors — changed lines that do not trace to the request (surgical_scope violation).
- Task definitions without success criteria + a runnable verification (verify_loop violation).
- Hardcoding the principle text into emitters/hooks instead of reading the policy schema at runtime.

## Falsification test

**If an Edit/Write fires in an activated project with kill-switches off and no Right-Effort surface (nudge or typed B8 factors) was applied to it → P15 broken; the discipline has regressed from policy to folklore.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P15 is a post-cutover gap-fill.)

## Doctrine inheritance (from L0)

P15 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Inheritance is via L0 generally — Customer Focus First (`./P0-customer-focus-first.md`) applies as parent: right-effort exists so the reader gets exactly the change they asked for, verified, and nothing else. Alignment with the Simple test is direct (simpler_alt IS the Simple test at edit granularity).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- sutra/marketplace/plugin/sutra-defaults.json `.right_effort` — canonical policy schema: principles, principles_short, applies_before, soft_hint_hook, kill_switch (production evidence).
- sutra/marketplace/plugin/hooks/per-turn-discipline-prompt.sh — runtime emitter; jq-reads of `.right_effort`; kill-switches; fresh-install gate (production evidence).
- sutra/marketplace/plugin/hooks/hooks.json — UserPromptSubmit registration (production evidence).
- /Users/asawa/Claude/asawa-holding/CLAUDE.md §Right-Effort Discipline — Asawa-side mirror with promotion note (production evidence).
- holding/CAPABILITY-MAP.md — cap-108 shipping row, audit-confirmed.
- `../blocks/B8-task-framework-factors.md` — factors[] spec; Right-Effort as conceptual root (cross-bucket; spec NOT duplicated here).
- `./P0-customer-focus-first.md` — doctrine parent.
- Source: github.com/forrestchang/andrej-karpathy-skills (try-before-buy, 2026-04-27).
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production policy schema per MIGRATION-PLAN §9 limitation #2.
