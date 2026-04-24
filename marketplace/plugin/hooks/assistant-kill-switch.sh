#!/usr/bin/env bash
#
# BUILD-LAYER: L1 (single-instance:asawa-holding)
#   Promotion target: sutra/marketplace/plugin/hooks/assistant-kill-switch.sh
#   Promotion by: 2026-05-24 (30d L1 stability window)
#   Acceptance: 3 off-path zero-cost tests green + end-to-end dogfood on Billu post-P2
#   Stale disposition: delete holding copy 30d after plugin-side promotion
#
# Direction: D29 (speed is core), D31/D32 (Sutra owns authority, default-off), founder requirement 2026-04-24 (zero tokens when disabled)
# Spec: holding/research/2026-04-24-assistant-layer-design.md §5
#
# PURPOSE
# Zero-cost kill-switch shim for the Sutra Assistant observer hook.
# When the Assistant is disabled at L2 (user runtime) or L1 (Sutra authority
# via hook-registry default-off), this shim exits before any Sutra logic
# loads. No config parse, no yaml read, no language runtime. 3 syscalls max.
#
# DISABLED WHEN (any of):
#   1. $SUTRA_ASSISTANT_DISABLED is set (non-empty)
#   2. ~/.sutra-assistant-disabled file exists
#   3. ~/.sutra-disabled file exists (global Sutra kill)
#
# When disabled: exit 0 silently (observer never called).
# When enabled: exec's assistant-observer.sh with the same args + stdin.

[ -n "${SUTRA_ASSISTANT_DISABLED:-}" ] && exit 0
[ -f "$HOME/.sutra-assistant-disabled" ] && exit 0
[ -f "$HOME/.sutra-disabled" ] && exit 0

# Pass through to real observer. exec replaces this process — no wrapper overhead.
exec "$(dirname "$0")/assistant-observer.sh" "$@"

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (D30a / PROTO-000 6-part rule)
#
# ### 1. Measurement mechanism
# Invariant metric: `events.jsonl` lines written during a session with any L2
# kill-switch flag active = 0. Verified by `test-assistant-kill-switch.sh`.
# Latency metric: wall-time of shim fast-path (off-path) < 5ms p99; measured via
# hook-log timings when the wrapper runs without exec'ing observer.
#
# ### 2. Adoption mechanism
# L1 copy active in asawa-holding only during P1. Promotion to
# sutra/marketplace/plugin/hooks/ at P5 means every plugin client receives it
# on `/plugin install sutra@marketplace` or plugin auto-update.
#
# ### 3. Monitoring / escalation
# Asawa Analytics dept scans hook-log.jsonl for unexpected observer writes
# while disabled flags were active. Breach = any row with assistant-observer
# fire AND L2 flag present. Surfaced at 24h cadence.
#
# ### 4. Iteration trigger
# - Any zero-cost invariant breach in production → patch + postmortem per D11
# - Any added kill-switch path (e.g., per-tool-type) → revise this file
# - Plugin schema change that shifts hook-dispatcher semantics → revise and re-test
#
# ### 5. DRI
# Sutra-OS owner (founder during P1-P6; rotates when CoS product ships externally).
#
# ### 6. Decommission criteria
# 2026-05-24 — delete this holding L1 copy after 30d plugin-stability review
# at sutra/marketplace/plugin/hooks/. Plugin copy becomes canonical thereafter.
# ═══════════════════════════════════════════════════════════════════════════
