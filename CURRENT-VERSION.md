# Sutra — Current Version

## v2.39.3 (2026-05-13, HEAD)

**Add `prd-discipline` skill** — product-document writing discipline.

- New skill at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- 5 invariants: STRUCTURED · VISUAL FIRST · RESTRUCTURE-ON-BULK · CONNECTED · GAP-SURFACING.
- Composes with ADR-020 Layer-B Product Authoring Template.
- Run `/reload-plugins` to activate in-session.

## v2.39.2 (2026-05-13)

**Remove 15-min hard cap on `codex-sutra` + `deepseek` skills** (founder D2026-05-13).

- 900-s wrapper kill removed from both skills; replaced with SIGINT trap (founder Ctrl-C → SIGTERM/SIGKILL on the whole process group).
- Heartbeat warnings now fire every 10 min during long-running calls (was one-shot at 10 min). Stall warn at 5 min no-progress unchanged.
- `deepseek`: `curl --max-time 900` flag removed — DeepSeek API server-side timeout is the only network bound.
- `sutra-defaults.json`: `deepseek.limits.wall_seconds_hard_cap` is now `null`.
- Fail-closed: `Hard-cap timeout / reason=timeout / exit 124` → `Founder interrupt (Ctrl-C) / reason=interrupted / exit 130`.
- Native canon: `phase-D-codex-review.md` + `HS-7-codex-queue-stale.md` updated with amendment line. HS-7 itself unchanged (watches review-backlog health, not per-call duration).

Rationale: long-reasoning runs were being killed before completion. Founder Ctrl-C is the only interrupt path now; stall + heartbeat keep silent hangs observable.

For prior release history, see `marketplace/plugin/CHANGELOG.md`.
