<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-021-sutra-plugin-host-residency.md. -->
# ADR-021: Sutra Plugin Host Residency

**Status**: Accepted (founder-delegated 2026-06-12; parity project T5; deepseek-reviewed same run, codex retro-review queued on auth restore)
**Date**: 2026-06-12
**Context anchor**: closes Host block open gap #4 ("where does the Sutra plugin live in the block diagram") — `holding/website/native/index.html#so-host` + `#section-4-12-parity` §4.12.4.

## Context

The Native first-layer schema (§1.0, LOCKED) has 8 blocks: UI · Host (Claude CLI) · Orchestration · System of Process · System of Record · Authority+Tenancy · Compute · External World. The Sutra plugin — 76 hooks, 21 skills, 6 per-turn governance blocks, sutra-defaults.json — ships to every fleet install but had no declared home in the block diagram. The Host block's second-order draft carried this as open gap #4. The Sutra→Native parity ledger (148 concepts, 2026-06-12) needed the placement settled to anchor ~30 plugin-implemented concepts.

## Decision

**The Sutra plugin is HOST-RESIDENT.** It is the governance layer the Host (Claude CLI) loads per-session:

- hooks = Host lifecycle interceptors (PreToolUse/PostToolUse/Stop/SessionStart/UserPromptSubmit)
- skills = Host-invokable bundles (slash-command surface)
- per-turn blocks = Host-emitted discipline (header, routing, depth, blueprint, build-layer, trace)
- sutra-defaults.json = policy payload the Host-resident layer carries

Daemon-side analogs (workflow registry, EngineEvents, schedules) live in Orchestration / System of Process — they are Native-daemon machinery, not plugin residency. Upstream governance CONTENT the plugin transports (defaults, founder directions) is Authority+Tenancy material; the plugin is its transport, not its home. No new block is added to §1.0.

## Consequences

- Parity ledger rows for plugin-implemented concepts anchor to Host (+ projection to their content's altitude).
- Future plugin capabilities declare Host-residency by default; daemon-side counterparts require an explicit Orchestration/SoP design.
- §1.0 stays locked — this ADR documents placement inside the existing schema.
- The 17 shipped-but-unwired hooks (parity T1 finding) are Host-resident dormant mechanisms; wire-or-retire review is an ops follow-up, not a placement question.
