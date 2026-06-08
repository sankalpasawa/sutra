---
issue: 47
title: "[v2.9.0] # Reposition Sutra Core as the brain layer of the Sutra family (Path A)"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T12:54:54Z
updated: 2026-04-30T12:54:54Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/47
comments: []
---

# #47 [v2.9.0] # Reposition Sutra Core as the brain layer of the Sutra family (Path A)

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T12:54:54Z  |  **Updated:** 2026-04-30T12:54:54Z
**URL:** https://github.com/sankalpasawa/sutra/issues/47

---

# Reposition Sutra Core as the brain layer of the Sutra family (Path A)

## Context

Sutra has been migrating from a heavy plugin model (the `sutra/core` plugin in `~/.claude/plugins/cache/`) to a thin-plugin + npm-installer + project-local-hooks model (`sutra-os` + `sutra-plugin`). The new project-native architecture is Sutra Native. The question this brief answers: **what should happen to Sutra Core?**

After several rounds of analysis — including an adversarial review that surfaced six load-bearing flaws in an earlier "fork and rebrand" recommendation — the proposal that survives scrutiny is **Path A**: Core stays inside the Sutra family, sharpens its job, and becomes the **brain layer** that complements Native's runtime.

This is filed as a public issue at the user's direction. If any part of this should be private, please feel free to redact.

## The pitch in one paragraph

Sutra Core does not fork, rebrand, or leave the Sutra family. It sharpens its role. **Native is the runtime that fires hooks inside each project; Core is the brain that turns those fires into self-calibrating intelligence.** Same family, complementary surfaces, no audience overlap, no feature collision. Core's flagship becomes the OS engines (Coverage / Estimation / Adaptive Protocol) running as actual runtime — not docs. Codex-sutra ships as a high-end opt-in module, not the headline. The story to engineers becomes: *"Native gives you discipline. Core tells you whether the discipline is working."*

```
Native = runtime hooks (project)         Core = analytics (cross-project)
Native = founder-facing                  Core = engineer-facing
Native = free                            Core = free + Pro tier
Native = the discipline                  Core = the calibration
```

## The 3-step instruction manual

Written in second person, addressed to Sutra Core itself. The technical execution is left to the team — these are directives, not a sprint plan.

### Step 1 — Take your real position.

You are not a product that competes with Sutra Native. You are the **brain layer**. Native is the runtime — it fires hooks inside the project. You are the engine room — you read those fires and turn them into intelligence. Native is for the founder running their day. You are for the engineer running deep work. Stop describing yourself as "an operating system for building with AI." You are the **analytics and calibration layer** of the Sutra family. Update your front door — readme, marketplace listing, `/core:start` banner, every place a new user lands — so this position is the first thing they see.

### Step 2 — Promote your OS engines from documents to running code.

Coverage, Estimation, and Adaptive Protocol have been markdown specs since v1.0. They are your flagship. Make them real.

- **Coverage** — score how much of the Sutra process actually fired per task.
- **Estimation** — predict before, capture after, recalibrate continuously.
- **Adaptive Protocol** — pick the right depth automatically and learn from overrides.

Ship Coverage first. It is the smallest engine and proves the path for the other two. If you cannot ship Coverage as runtime, the rest of this plan is wrong — abort and rethink rather than push through.

### Step 3 — Build the pipe that feeds the engines.

You need data, and Native already produces it. Build a consent-gated pipe that pulls Native's per-project hook-fire logs into your cross-project aggregator. Required properties, non-negotiable:

- Opt-in per project; default off.
- Scrubbed locally before storage.
- Stored locally. No central push, ever.
- Reversible — any project can withdraw and have its data forgotten on command.

Without this pipe, your engines starve. With it, the engines become a moat that takes months of real session data to replicate.

## Why this position survives adversarial review

| Concern raised | How this position handles it |
|---|---|
| Codex-sutra moat is thin (CodeRabbit, Copilot Code Review will commoditize) | Codex-sutra is a feature inside Core, not the product. If the AI-reviews-AI category collapses into a free PR-tab feature, Core is unhurt. |
| OS engines need longitudinal telemetry to be defensible | That's exactly the moat. Telemetry compounds — a competitor needs 6+ months of real session data to leapfrog. Core owns the aggregation rail; Native ships the per-project log that feeds it. |
| Single maintainer can't ship two new things | This is one continuous product family with two surfaces. Native already exists; Core already exists. The work is finishing engines that have been docs for too long, not building from scratch. |
| Audience-shift assumption (founders → EMs) is fatal | We don't ship one. Core stays inside Sutra's existing audience. Pro-tier users self-select — engineers running deep workflows. No GTM pivot required. |
| GitHub ships free multi-model review by Q1 2027 | Doesn't touch Core's flagship. Coverage / Estimation / Adaptive Protocol live in a different category — process telemetry, not code review. |
| Naming a standalone product around "codex" collides with OpenAI Codex | Not relevant here — Core stays branded as Sutra Core. No rename needed. |

## Footnotes — not steps

- **Codex-sutra continues to exist.** It is a feature inside Core now, not the headline. Ship it opt-in.
- **Path B (standalone product, rebrand)** is filed for later. Reconsider only after the engines have run for ~90 days and produced honest data on whether the brain-layer position is working. Naming research, audience analysis, and standalone positioning are documented separately.
- **The companion architecture for `/core:resume` + `/core:bookmark`** (filed as a separate issue) is the first concrete feature where users feel the brain-layer story — same data plumbing the OS engines will need.

## Open questions for the team

These are decisions Sankalp owns, not directives:

1. **Pricing model** — is a paid Pro tier on Core the right revenue path, or is Core free indefinitely?
2. **Telemetry contract** — Native side commits to schema stability for `hook-fires.jsonl`?
3. **Engineering capacity** — what's the realistic timeline for one maintainer to ship Coverage + Estimation + Adaptive Protocol as runtime?
4. **Path B re-eval criteria** — what telemetry signals would trigger reconsidering the standalone-fork question? (Default suggestion: Pro-tier conversion <2% of free users → reconsider.)
5. **Codex-sutra default state** — stays opt-in forever, or earn its way back to default-on with telemetry of false-positive rates?
6. **Deprecation path** — when should Core's duplicate skills (input-routing, depth-estimation, readability-gate, output-trace) be suppressed when Native is detected? 2.9.0 (suppression-on-detection) → 3.0.0 (removal)?

## Provenance

This brief originated in a Claude Code session brainstorm on 2026-04-30. Three rounds of analysis: an initial "preserve optionality" hedge → a "fork and rebrand" overcorrection → a stress-test via independent adversarial review that returned this position. The session adopted Sutra's own framework (input-routing, depth-estimation, readability-gate, output-trace) plus an Estimation Engine table and a Coverage retrospective on the prior recommendation. Six of six adversarial-review challenges shaped the final shape of the brief.

Posting publicly at the user's direction — happy to move to a private channel if you'd prefer for future strategic notes.
