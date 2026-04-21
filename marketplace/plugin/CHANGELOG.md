# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [1.3.0] — 2026-04-21

Permission-prompt reduction + command namespace cleanup.

### Added

- `bin/sutra` unified dispatcher — single executable replacing six script invocations. Claude Code auto-adds plugin `bin/` to PATH, so `sutra onboard`, `sutra push`, etc. run as bare commands (no Bash permission prompts per distinct script path).

### Changed

- **Command rename (BREAKING)** — `/sutra:sutra-onboard` → `/sutra:onboard`, `/sutra:sutra-push` → `/sutra:push`, `/sutra:sutra-status` → `/sutra:status`, `/sutra:sutra-go` → `/sutra:go`. Drops redundant `sutra-` prefix now that Claude Code namespaces commands as `plugin:command`.
- All command files now invoke `!sutra <sub>` instead of `!bash ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.sh`. Single permission scope.

### Migration

- Auto-update will pull new command files. Old slash commands (`/sutra:sutra-onboard` etc.) stop working; use the new names.
- First use of `sutra` bare command may surface one permission prompt per session depending on Claude Code version — one allow covers all subcommands.

## [1.2.1] — 2026-04-21

Brand-leak scrub before external launch.

### Fixed

- `plugin.json` description: removed an internal brand reference; now reads "local metric telemetry".
- `ARCHITECTURE.yaml`: internal operator paths replaced with abstract `<operator>/` placeholders.

### Added

- `marketplace/design/2026-04-21-first-run-walkthrough.md` — T+0 → T+60s scripted experience (CM3).
- Plugin leak audit now PASSES; official `claude plugin validate` PASSES.

## [1.2.0] — 2026-04-20

Per-session tool telemetry.

### Added

- `hooks/posttool-counter.sh` — PostToolUse hook tracks which tools ran per session, writes to `$SUTRA_HOME/sessions/<session_id>.counters`.
- Stop hook extended — `flush-telemetry.sh` reads session counters, emits `tool_uses_session`, `skill_uses_session`, `write_uses_session`, and related metrics; cleans up counter file after emit.
- `ARCHITECTURE.yaml` as structured source of truth (v1.0.0) — components, flows, identities, privacy matrix.

## [1.1.4] — 2026-04-20

Shell-helper installer.

### Added

- `scripts/install-shell-helpers.sh` — appends `sutra-go` / `sutra-uninstall` / `sutra-reset` / `sutra-status-global` one-word commands to user's `~/.zshrc` or `~/.bashrc`. Idempotent.
- README install flow updated for new-laptop users.

## [1.1.3] — 2026-04-19

Auto-push on Stop.

### Added

- `hooks/flush-telemetry.sh` — fire-and-forget async push on Stop event if `telemetry_optin=true`. Never blocks session teardown.

### Changed

- Per codex review: Stop hook stays light — local file writes only, no synchronous network or git.

## [1.1.2] — 2026-04-19

### Added

- `/sutra:sutra-go` — one-shot onboard + telemetry ON command.

## [1.1.1] — 2026-04-19

Plugin observability auto-emission.

### Added

- `flush-telemetry.sh` auto-emits three metrics on Stop: `sessions.session_stops_total`, `os_health.queue_depth_at_stop`, `os_health.depth_marker_present`.
- Analytics collector (operator-side) reads plugin telemetry rows and rolls up per-metric count + median.

## [1.1.0] — 2026-04-18

Layer-B metric telemetry.

### Added

- `lib/project-id.sh` — deterministic install_id (sha256 HOME+version) + project_id (sha256 git remote).
- `lib/queue.sh` — local metric queue at `~/.sutra/metrics-queue.jsonl`; rotates at 10k lines.
- `hooks/emit-metric.sh` — Layer B writer: validates numeric values, rejects PII in string fields, appends to queue.
- `commands/sutra-onboard.md` — first-time project setup writing `.claude/sutra-project.json`.
- `commands/sutra-push.md` — manual push to `sankalpasawa/sutra-data` (opt-in gated).
- `commands/sutra-status.md` — local state inspector.

## [1.0.0] — 2026-04-18

First production release. Outcome-tested.

### Added

- Outcome test suite at `tests/outcome/` — install, activation, enforcement, commands, update, logging, leak-audit as black-box scripts.
- Hooks shift from warn-only to structured: `depth-marker-pretool.sh` logs violations; `estimation-stop.sh` writes session log.

## [0.2.0] — 2026-04-19

Unified deploy.

### Changed

- Plugin strips shadow skills (they duplicated dispatcher logic) and becomes a thin bridge that invokes `npx github:sankalpasawa/sutra-os init` on first `/sutra`.

## [0.1.0] — 2026-04-18

First release. Minimum viable plugin for functional validation.

### Added

- Skills: `input-routing`, `depth-estimation`, `readability-gate`, `output-trace`
- Commands: `/sutra`, `/depth-check`
- Hooks: `depth-marker-pretool` (warn-only, PreToolUse Edit|Write), `estimation-stop` (Stop event logger)
- Audit script: `scripts/leak-audit.sh` (brand-leak mechanism)
- MIT license

### Known limitations

- Hooks warn rather than block. Hard enforcement deferred to v0.2.
- No per-profile defaults yet (individual / project / company).
- Estimation log is session-local, not cross-session.
