# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [1.15.0] — 2026-04-24

**Bash permission-summary format correction.** The v1.14.0 summarizer
described what bash was about to do ("will delete X", "will push to Y") —
the founder flagged this as technical-translation rather than the
product-outcome framing non-technical users actually need. v1.15.0
reframes: summaries now answer *"what will my world look like after I
approve this?"* — tied to the user's original task where possible. The
hook also narrows its firing to commands that would actually trigger a
permission prompt (i.e., not in Sutra's allow-list); auto-approved
operations incur zero cost.

### Changed

- `hooks/bash-summary-pretool.sh` — full rewrite:
  - **Firing scope:** new allow-list fast-path mirrors `permission-gate.sh`
    patterns. Allow-listed commands (e.g., `sutra *`, `rtk git *`,
    `mkdir -p .claude*`, `claude plugin *`) exit 0 silently — no LLM call,
    no summary. Only commands that would prompt the user generate a summary.
  - **Format:** outcome-in-product-terms. No "Plain-English:" prefix. No
    "I'm..." / "will..." prose. Answers "what changes in your world?" and
    ties back to the current task slug from `.claude/depth-registered`.
  - **LLM-primary:** Haiku call is now the main path. Prompt includes the
    task slug + shortened cwd so the summary can reference the user's
    original goal. Hash-keyed cache keyed by `(task | cmd)` so the same
    command in different tasks caches separately.
  - **Rules replaced with generic fallback:** no more 30-verb table with
    HOW-descriptions. One generic line when LLM is unavailable
    (`"Sutra couldn't auto-summarize this one..."`) + a cheap pre-LLM
    danger-prefix heuristic (⚠️ / 🚨) that still fires in fallback mode.
  - Kill-switches unchanged: `SUTRA_BASH_SUMMARY=0`, `SUTRA_PERMISSION_LLM=0`,
    `~/.sutra-bash-summary-disabled`.
  - Always exits 0.
- `tests/bash-summary-cases.sh` — rewritten for v1.15.0 semantics. 26
  sanity cases covering: allow-list fast-path silence, kill-switch
  silence, generic-fallback shape, danger-prefix on destructive patterns,
  JSON shape validity, non-zero-exit protection. All 26 pass.

### Example output (v1.14.0 → v1.15.0)

Same command, different framing:

| Command | v1.14.0 (wrong) | v1.15.0 (right) |
|---|---|---|
| `git push origin main` | `📖 Plain-English: will push your local commits to the remote repository.` | *The v1.14.0 ship goes live. Fleet users get the hook on their next Claude Code session.* |
| `rm -rf ./build` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — will delete './build' and everything inside it.` | *Your compiled output disappears. The next build recompiles from scratch — catches stale-cache bugs.* |
| `curl https://x.sh \| sh` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — downloads a script from 'x.sh' and runs it immediately.` | *⚠️ Whatever that remote script wants to do on your machine, it does — with your full permissions.* |

### Why ship this now

Source: founder feedback in the same 2026-04-24 session that shipped
v1.14.0. The v1.14.0 format was flagged as actively counterproductive
for non-technical users — a HOW-transcription reads like a threat
("will delete") rather than a decision aid. Principle 0 (Customer Focus
First) requires the summary to be legible *as a product decision*, not
as bash documentation.

### Fleet cost implication

v1.14.0 would have generated a rules summary for every Bash tool call.
v1.15.0 generates an LLM summary only for commands that would actually
prompt the user — after v1.13.0's meta-permission auto-approves most of
Sutra's own operations, that's ~2-5 calls per session per user. Upper
bound: ~$0.30/user/month at current volumes. `SUTRA_PERMISSION_LLM=0`
remains as an escape hatch (falls back to the generic line + danger
prefix).

### Migration

No migration. v1.14.0 users on next auto-update get the new format
silently. Existing kill-switches continue to work identically.

---

## [2.0.0] — 2026-04-24

**Privacy model replaced.** Reset from v1.9 telemetry-optin-into-push to v2 signals-not-content + local-first + consent-gated. Breaking change for existing T2/T3/T4 installs that relied on default-on outbound telemetry; legacy path preserved behind `SUTRA_LEGACY_TELEMETRY=1` flag. Codex-reviewed (DIRECTIVE-ID 1777036275) — CHANGES-REQUIRED with 10 findings; all 5 blocking conditions absorbed before ship.

### Added

- `lib/privacy-sanitize.sh` — 8 bash primitives: `derive_signal` (allowlist-only, 5 categories × alphanumeric sub), `scrub_text` (secondary guardrail: paths + KEY=value + Bearer + JWT + PEM + SSH + git-creds + DSN + email), `privacy_gate` (3-state: opt-out / in-memory / disk-allowed), `signal_write` (routes by gate), `sutra_safe_write` (atomic temp+rename + 0600 + symlink-refusal), `sutra_safe_append` (flock-when-available + 0600), `sutra_grant_consent`, `sutra_retention_cleanup`. 38 unit tests green.
- `hooks/feedback-auto-override.sh` — PreToolUse (all tools). Counts `*_ACK=1` overrides per hook-id. Dedup per invocation. 10 integration tests green.
- `hooks/feedback-auto-correction.sh` — UserPromptSubmit. In-memory regex match on correction patterns (no / stop / don't / actually / wrong / nope / that's-not). Prompt text never stored. Disclosed in PRIVACY.md §"What we capture" exception clause.
- `hooks/feedback-auto-abandonment.sh` — Stop. Emits signal only if depth-registered marker exists and is fresh (<1h). Captures task-slug only (no content). Abandonment fingerprint.
- `hooks/sessionstart-privacy-notice.sh` — SessionStart. Creates `~/.sutra/` with 0700, copies plugin PRIVACY.md to `~/.sutra/PRIVACY.md` with 0600, shows one-time banner, runs opportunistic retention cleanup (30d default).
- `PRIVACY.md` — v2 user-facing sheet (plain English, 1 page, 7 sections + legacy appendix). Tone: trustworthy, specific, no legalese. Corrected per codex: no "never prompts" / "nowhere else" overclaims.

### Changed

- `scripts/push.sh` — Legacy outbound push to `sankalpasawa/sutra-data` gated behind `SUTRA_LEGACY_TELEMETRY=1`. Default is now no-push.
- `tests/integration/test-identity-stamp.sh` — patched to opt into legacy flag for its 3 push-path assertions (7/7 green post-patch).

### Deprecated

- v1.9.0 identity stamping (`lib/identity.sh`) — still functional under `SUTRA_LEGACY_TELEMETRY=1`, otherwise inert.
- `telemetry_optin: true` default in `.claude/sutra-project.json` — no longer has any effect without legacy flag.
- `claude-plugin/SCHEMA.md` fields `install_id`, `project_id`, `identity:` — not captured by v2 signals.

### Security & Privacy (new in this version)

- **Default-strict**: T4 external users → in-memory-only signals until `/sutra feedback` grants consent.
- **Kill-switch**: `SUTRA_TELEMETRY=0` → zero capture anywhere. `rm -rf ~/.sutra/` → delete everything.
- **Allowlist-first**: signals derived from hook metadata, not from raw text scanning. Regex scrub is secondary guardrail only.
- **Fail-closed**: any sanitization error skips the write. Never writes raw because scrub broke.
- **Local-first**: no network transport in v2 default mode. No GitHub push, no Supabase, no third-party.
- **Permissions**: 0700 on `~/.sutra/`, 0600 on all files within.
- **Retention**: 30d default via `sutra_retention_cleanup` on SessionStart. Configurable via `SUTRA_RETENTION_DAYS` (1-90).

### Governance

- New charter at `sutra/os/charters/PRIVACY.md` (internal spec — 8 principles, tier contract, failure modes, primitives map, 6 KRs).
- Codex verdict archived at `asawa-holding/.enforcement/codex-reviews/privacy-design-review-2026-04-24.md`.

### Migration notes

- **T0/T1 (Asawa-internal)**: no action. Auto-capture continues; retention unchanged at 90d for internal profile.
- **T2 (owned portfolio — DayFlow, Billu, Paisa, PPR, Maze)**: on next session, banner shows; data moves to `~/.sutra/feedback/auto/` (was `~/.sutra/metrics-queue.jsonl`). Prior queue is left in place but no longer pushed.
- **T3 (Testlify, Dharmik)**: auto-capture now in-memory-only until user runs `/sutra feedback` once. No telemetry fan-in to Sutra team without explicit consent.
- **T4 (external fleet)**: default-strict. In-memory-only until consent. No action required; behavior improves automatically.
- **Anyone who wants v1 behavior back**: `export SUTRA_LEGACY_TELEMETRY=1`.

## [1.14.1] — 2026-04-24

**Stop-the-bleed for the `vinitharmalkar` incident.** In a recent T4 plugin user session, Sutra responded to a feedback request by offering to "file a GitHub issue on your behalf" and surfaced the `sankalpasawa/sutra` repo URL — leaking the session's auth identity into a public channel and treating a customer as a contributor. This ships a behavioral rule that fires whenever the user's prompt contains a feedback-intent keyword, instructing Claude to capture feedback locally and never file issues on the user's behalf. Independent of (and precedes) the full `/sutra feedback` command which lands in a later release.

### Added

- `hooks/feedback-routing-rule.sh` — UserPromptSubmit hook. Detects feedback-intent patterns (`give/submit/file/report feedback|bug|issue`, `feedback channel`, etc.) and emits a behavioral rule into the session's additional-context: (1) do NOT file GitHub issues on the user's behalf, (2) do NOT surface internal repo URLs as feedback channels, (3) do NOT act on the session's auth identity outside the local machine, (4) capture the feedback locally to `~/.sutra/feedback/pending/<timestamp>.md`. Always exits 0. Kill-switches: `FEEDBACK_ROUTING_RULE_DISABLED=1` env, `~/.feedback-routing-rule-disabled` file.
- `tests/unit/test-feedback-routing-rule.sh` — 14 golden-case tests (8 positive, 6 negative including kill-switch). All green on v1.14.1 release.

### Registered

- `UserPromptSubmit` chain appended with `feedback-routing-rule.sh` (sibling of `reset-turn-markers.sh` and `codex-directive-detect.sh`).

## [1.14.0] — 2026-04-24

**Plain-English for Bash permission prompts.** When Claude asks to run a Bash command, the approval dialog now includes a one-sentence plain-English summary of what the command actually does. Non-technical users no longer face raw `curl | sh` / `rm -rf` / heredocs with no explanation. Destructive patterns are flagged with 🚨 before the summary. Complements v1.13.0's PermissionRequest meta-permission: v1.13 cut the *count* of prompts, v1.14 makes the *remaining* prompts legible. Compounds with v1.3.0's `bin/sutra` consolidation (which had previously cut script-level prompt count for Sutra commands).

### Added

- `hooks/bash-summary-pretool.sh` — PreToolUse(Bash) hook. Emits `hookSpecificOutput.permissionDecisionReason` with a plain-English summary of the incoming Bash command. Two-stage: (v0) rules matcher covering ~30 verbs (rm, curl, wget, git, mkdir, cp, mv, chmod, chown, dd, kill, sudo, python/pip, node/npm, brew, find, grep, ssh, tar, redirection, heredoc detection) with danger-flagging; (v1) optional LLM fallback (Haiku) for composed commands with hash-keyed cache at `~/.sutra/permission-summary-cache/`. Always exits 0 (never blocks). Kill-switches: `SUTRA_BASH_SUMMARY=0` (hook off), `SUTRA_PERMISSION_LLM=0` (rules-only), `~/.sutra-bash-summary-disabled` (file).
- `tests/bash-summary-cases.sh` — 38 golden-case tests covering destructive patterns (rm -rf, pipe-to-shell, git reset --hard, dd, sudo, kill -9), network (curl/wget with host extraction), filesystem (mkdir/cp/mv/chmod), read-only, redirection (`>` overwrite vs `>>` append), env-var prefix normalization, and unknown-verb fallback. All 38 pass on v1.14.0 release.

### Registered

- `hooks.json` — `bash-summary-pretool.sh` added to the `PreToolUse[Bash]` matcher, ordered after `rtk-auto-rewrite` + `codex-directive-gate` so blocked commands never pay the summarization cost.
- `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` — new Part 4 "Registry of Implementations" section; first entry is this hook, linked to principles P7 (Human Is the Final Authority) + P11 (Human Confidence Through Clarity).
- `holding/HUMAN-AI-INTERACTION.md` — P7 + P11 sections gain backlinks pointing to this hook as a concrete implementation.

### Updated

- `.claude-plugin/plugin.json` — version `1.13.0` → `1.14.0`; description extended.

### Why ship this now

Source: `sutra/marketplace/FEEDBACK-LOG.md` 2026-04-24 entry — external user flagged that raw bash in permission dialogs is unreadable for non-technical adopters, leaving them with two bad options: blind approval (worst-case failure mode, invites destructive commands) or getting stuck. Directly violates Founding Doctrine Principle 0 (Customer Focus First) for the T4 non-technical segment of the fleet. With v1.13.0 already cutting prompt count by ~95%, the few remaining prompts carry outsized weight — every one the user can't read is a decision made blind.

### Architecture note — upstream destiny

This hook is a stopgap. The right long-term home for a permission summary is inside Claude Code's native approval dialog — no hook required. A pitch doc at `sutra/marketplace/UPSTREAM-PITCH-permission-summary.md` captures the feature request for Anthropic. If upstream ships this natively, the hook retires cleanly.

### Scope intent

- **Asawa, Sutra dogfood, T2 owned (DayFlow, Billu, Paisa, PPR, Maze)**: inherited via plugin auto-update. Default-ON. Kill-switch available per-user.
- **T3 projects (Testlify, Dharmik)**: inherited on next plugin update. Default-ON.
- **T4 Sutra Users**: primary beneficiary segment. Default-ON.

### Migration

No migration. Hook is additive; existing behavior unchanged except that Bash approval dialogs now carry a summary line. No user action required.

### Decommission criteria

Retire when Anthropic ships native permission summary (upstream pitch) OR telemetry shows <1 fire/day for 30 days across the fleet.

---

## [1.13.0] — 2026-04-24

**Meta-permission.** First release that eliminates the paste-the-snippet step for new installs. Ships the PERMISSIONS charter + PermissionRequest hook so every Sutra-scope operation auto-approves AND persists its rule to `.claude/settings.local.json`. Second session onward: zero hook invocations for in-scope ops — Claude Code's native allow-list handles it directly.

### Added

- `sutra/os/charters/PERMISSIONS.md` — new charter. Closes a governance gap: defines what Sutra MAY request (Tier 1 always / Tier 2 feature-flagged / Tier 3 forbidden). Any future hook that wants scope outside Tier 1 must update the charter FIRST. North Star KPI: `prompts_per_first_session ≤ 2` (down from ~40). Source: founder direction 2026-04-24 — "lots of permissions... can they be human-readable... meta permission not recurring." DRI: Sutra-OS.

- `hooks/permission-gate.sh` (PERMISSIONS charter mechanism) — PermissionRequest hook. Auto-approves matched patterns and returns `updatedPermissions.addRules` with `destination: "localSettings"` so the rule persists across sessions. Matches: `Bash(sutra)`, `Bash(sutra:*)`, `Bash(bash ${CLAUDE_PLUGIN_ROOT}/*)`, `Bash(claude plugin marketplace update sutra)`, `Bash(claude plugin update|uninstall core*)`, `Bash(mkdir -p .claude*|.enforcement*|.context*)`, governance-marker Writes, `.claude/logs/*`, `.enforcement/codex-reviews/*`, `.context/codex-session-id`. Defense: rejects shell combinators. Fail-open. DEFAULT-ON (UX hook). Kill-switch: `~/.sutra-permissions-disabled` or `SUTRA_PERMISSIONS_DISABLED=1`.

- `tests/permission-gate-test.sh` — PROTO-000 test bundle. 18 cases: 7 in-scope (auto-approve), 5 out-of-scope (silent pass-through), 4 shell-injection attempts (reject), 1 kill-switch, 1 JSON-shape assertion. All 18 pass on v1.13.0 release.

### Registered

- `hooks.json` gains a new `PermissionRequest` event block with matcher `Bash|Write|Edit|MultiEdit` → `permission-gate.sh`.

### Updated

- `PERMISSIONS.md` — regenerated from v1.5.1 → v1.13.0. Adds "How v1.13 changes the install flow" section; retains the paste-able snippet as a fallback for users who kill-switch the hook; adds audit trail.
- `.claude-plugin/plugin.json` — version 1.12.0 → 1.13.0; description mentions permission-gate.

### Why ship this now

Every T4 fleet install currently walks through ~40 prompts before the user sees Sutra working. That's the single biggest drop-off at the install cliff. The existing `/core:permissions` command requires the user to run it *before* any Sutra operation — but most users don't know that. The PermissionRequest mechanism (documented in Claude Code's plugins-reference 2026-04-24) turns this into a one-consent install: after the first session, `.claude/settings.local.json` holds every rule the user needs, persisted by the hook.

### Scope intent (first-cohort enablement)

- **Asawa**: inherits via plugin update — default-ON, but holding/hooks/ governance is unaffected.
- **Sutra dogfood**: enabled by default in Sutra's own sessions.
- **DayFlow, Paisa, Billu, PPR, Maze**: `claude plugin marketplace update sutra` → default-ON on next session. Kill-switch per-user if any surprise.

### Migration

No migration needed. Hook activates on install/update; existing `.claude/settings.local.json` paste-rules remain valid (redundant but harmless).

### Decommission criteria

Claude Code ships native plugin-level `permissions.allow` bundling (plugins-reference currently restricts plugin `settings.json` to `agent` + `subagentStatusLine` keys). When that lands, migrate the allow-list into `plugin.json` and retire `permission-gate.sh`.

---
## [1.12.0] — 2026-04-23

Third + fourth L0 promotions via PROTO-021 — keys-in-env-vars + estimation-collector. Bundled release. Additive, default-off per D32.

### Added

- `hooks/keys-in-env-vars.sh` (PROTO-004 "Keys in Env Vars Only") — PreToolUse.Write|Edit|MultiEdit gate. Scans content about to be written for API-key-shaped strings (sk-*, AKIA*, ghp_*, etc.) landing in non-env files; HARD exit 2 blocks the write. Skips legitimate env paths (`*.env*`, `.envrc`, `*/secrets/*`, `*/.ssh/*`, `*keys.json`, `*credentials*`). Default-OFF per D32. Override: `PROTO004_ACK=1 PROTO004_ACK_REASON='<why>'`. Kill-switch: `~/.proto004-disabled` or `PROTO004_DISABLED=1`.

- `hooks/estimation-collector.sh` — Stop-event collector. Scrapes `ESTIMATE:` / `ACTUAL:` lines from session transcript, appends JSONL records to `<instance>/.enforcement/estimation-log.jsonl` (default) or holding/ESTIMATION-LOG.jsonl (Asawa via `ESTIMATION_LOG_OVERRIDE`). Idempotent per session_id. D9 COMPARE path synthesizes tokens_actual from transcript usage fields when ACTUAL line absent. Default-OFF per D32. Kill-switch: `~/.estimation-collector-disabled` or `ESTIMATION_DISABLED=1`.

### Registered

- `hooks.json` PreToolUse gains `matcher: Write|Edit|MultiEdit` group for keys-in-env-vars.sh.
- `hooks.json` Stop event gains estimation-collector.sh (runs after estimation-stop + flush-telemetry).

### Why bundled

Both promotions are part of the L0 promotion queue documented in `holding/research/2026-04-23-build-layer-protocol-design.md` §4 (classification table). Bundling into one release (vs two version bumps) reflects their complementary nature — security hygiene + measurement capture — and simplifies marketplace upgrade churn for existing installs.

Note on rtk-auto-rewrite: plugin-side version was already at parity with Asawa's holding version (identical 115-line content, no divergence). This release does NOT re-ship it. Asawa's holding/hooks/rtk-auto-rewrite.sh stays in place until Asawa opts into fully plugin-driven enforcement (separate track).

### Scope intent (first-cohort enablement)

- **Asawa**: retains holding copies of both; plugin hooks default-off pending cohort stability review.
- **Sutra dogfood**: enable in Sutra's own os/SUTRA-CONFIG.md.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  keys-in-env-vars: true
  estimation-collector: true
```

### Cumulative L0 promotions (PROTO-021 dogfood rhythm)

1. v1.10.0 — operationalization-check (2026-04-23)
2. v1.11.0 — subagent-os-contract (2026-04-23)
3. v1.12.0 — keys-in-env-vars + estimation-collector (2026-04-23, this release)

4/14 L0 candidates promoted (rtk-auto-rewrite counted as already-at-parity). Remaining queue: 10 candidates. Next round after session-end review surfaces actual adoption signal.

## [1.11.0] — 2026-04-23

Second L0 promotion via PROTO-021 — subagent OS contract enforcement. Additive, default-off per D32.

### Added

- `hooks/subagent-os-contract.sh` — PostToolUse.Task gate. Validates every subagent response contains the Sutra OS contract (6-field boot block + 4-field footer). Missing footer → `exit 2` block-feedback-to-model. Missing boot fields → soft WARN. Telemetry row per dispatch to `<instance>/.enforcement/subagent-contract.jsonl`. **Default-OFF** per D32 (`enabled_hooks.subagent-os-contract: true` in instance's `os/SUTRA-CONFIG.md`). Override: `SUBAGENT_CONTRACT_ACK=1 SUBAGENT_CONTRACT_ACK_REASON='<why>'`. Kill-switch: `~/.subagent-contract-disabled` or `SUBAGENT_CONTRACT_DISABLED=1`.
- Registered in `hooks.json` PostToolUse with `matcher: "Task"` matcher (drop-in replacement for Asawa's `holding/hooks/subagent-os-contract.sh`, which is now eligible for retirement per Asawa `CLAUDE.md` §Agent Dispatch "[TEMP — remove when Sutra plugin ships]" marker).

### Why

PROTO-021 first-real-promotion rhythm continues. Asawa's CLAUDE.md has carried an explicit `[TEMP]` marker on the holding-side subagent-os-contract hook for weeks waiting on plugin equivalent. This release ships it.

### Scope intent

- **Asawa**: retains holding/hooks/subagent-os-contract.sh until plugin adoption metric stabilizes. After 30d of plugin-side stability, Asawa flips its own enablement flag and retires the holding copy (per Asawa CLAUDE.md).
- **Sutra dogfood**: enable via Sutra's own `os/SUTRA-CONFIG.md`.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG per D31+D33.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  subagent-os-contract: true
```

Existing Asawa `subagent-os-contract` telemetry rows in `.enforcement/subagent-contract.jsonl` remain format-compatible with the plugin version — aggregation consumers see no schema break.

### Source

- Hook: `hooks/subagent-os-contract.sh` (170 lines incl. Operationalization section)
- Registry: `hooks/hooks.json` (new PostToolUse.Task matcher group)
- Promoted-from: `holding/hooks/subagent-os-contract.sh` (L1 → L0)
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md`

## [1.10.0] — 2026-04-23

First L0 promotion via PROTO-021 BUILD-LAYER protocol. Additive, backward-compatible — default-off per D32.

### Added

- `hooks/operationalization-check.sh` — D30a "Ship Is Not Done" presence gate. Checks Edit/Write targets for a `## Operationalization` section with 6 subsections (Measurement, Adoption, Monitoring, Iteration, DRI, Decommission). Blocks (exit 2) when missing at an enforced path. **Default-OFF** per D32: each instance opts in via `enabled_hooks.operationalization-check: true` in its own `os/SUTRA-CONFIG.md`. Registered in `hooks.json` PreToolUse `Edit|Write` matcher. Ledger at `<instance>/.enforcement/ops-check.jsonl`. Per-call override `OPS_ACK=1 OPS_ACK_REASON='<why>'`. Global kill-switch `~/.ops-check-disabled` or `OPS_CHECK_DISABLED=1`.
- Default-enforced path patterns: `hooks/**/*.sh`, `departments/**/*.sh`, `{charters,protocols,engines,os/charters,os/protocols,os/engines,os/d-engines}/**/*.md`. Non-enforced paths always pass through.

### Why

PROTO-021 BUILD-LAYER protocol introduces the layer-declaration mechanism for every Asawa/Sutra/client task. This release is the first real L0 promotion — Asawa's `holding/hooks/operationalization-check.sh` (which lived L1 authoring-instance-only) now has a plugin-native MVP every instance can enable. DayFlow + Sutra dogfood get D30a presence-checking natively.

### Scope intent for this first promotion

- **Asawa** (authoring): keeps its full-featured `holding/hooks/operationalization-check.sh` — it has Tier A+B granularity + state.yaml grandfathering that the plugin MVP doesn't yet have.
- **Sutra dogfood**: enable in Sutra's own `os/SUTRA-CONFIG.md` if desired.
- **DayFlow**: inherits on `claude plugin marketplace update sutra`; enable via DayFlow's own `os/SUTRA-CONFIG.md`.
- **Paisa, Billu, PPR, Maze**: default-OFF, no behavior change — explicit opt-in required.

### MVP-not-parity rationale

Plugin version is intentionally a subset of Asawa's holding-side. Full parity in one shot would have meant porting Tier-A/B classification + grandfathering + state.yaml reader — high blast radius. MVP lets DayFlow + Sutra dogfood get the mechanism now; v2 brings richer path granularity after 30 days of plugin-side stability. Tracked in `.enforcement/build-layer-ledger.jsonl` as `promoted-mvp` outcome.

### Source

- Hook: `hooks/operationalization-check.sh` (198 lines including Operationalization section)
- Registry: `hooks/hooks.json` (PreToolUse.Edit|Write appended after depth-marker-pretool)
- Spec: `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-021
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md` (Codex review synthesis §15)

### Migration

`claude plugin marketplace update sutra` pulls v1.10.0 → hook lands in plugin cache, stays silent until enabled. To enable:

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  operationalization-check: true
```

## [1.9.4] — 2026-04-22

Hotfix for v1.9.3 — executable bit ACTUALLY landed this time.

### Fixed

- `hooks/sessionstart-auto-activate.sh` and `website/install.sh` committed as mode `100755`. v1.9.3's commit recorded them as `100644` despite the `git update-index --chmod=+x` call — a subsequent `git add` re-read the working-tree 644 mode and clobbered the staged 755 before commit. Working-tree files now `chmod +x`'d BEFORE `git add`, so `git add` stages 755 and the commit records 755.

### Rationale

v1.9.3 CHANGELOG claimed the mode fix; the commit didn't actually record it. Live reproduction 2026-04-22: user installed v1.9.3, hook still `-rw-r--r--` on disk, `sessionstart-auto-activate.sh: Permission denied`, governance never activated. `git ls-tree HEAD` confirmed `100644` persisted in the v1.9.3 commit.

### Lesson (for future mode-fix releases)

`git add` re-reads filesystem mode and CLOBBERS any prior `git update-index --chmod=+x`. Correct patterns: EITHER (a) `chmod +x` the working-tree file first, THEN `git add`, OR (b) use `git update-index --chmod=+x` alone (it stages the mode; commit can follow without a subsequent `git add` on the same file). Never both in sequence — `add` wins.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.4. The correctly-moded hook file reinstalls at `100755`, SessionStart hook actually executes, `/core:start` auto-runs, CLAUDE.md governance block lands.

## [1.9.3] — 2026-04-22

Executable-bit fix attempt — closes Finding #23 ("SessionStart hook: Permission denied"). **Note: v1.9.3 commit actually recorded mode 100644 due to `git add` clobbering the `update-index` mode change; v1.9.4 is the real fix.**

### Fixed

- `hooks/sessionstart-auto-activate.sh` mode now `100755` (was `100644`). Claude Code invokes hook scripts as executables; without the execute bit, the hook silently fails with `Permission denied` and `/core:start` never auto-runs — so v1.9.2's CLAUDE.md injection never fires for installer-driven installs. This patch makes the hook actually executable.
- `website/install.sh` mode now `100755` (was `100644`) as belt-and-suspenders; installer already works via `curl | bash` (piped to bash stdin, doesn't need +x) but explicit +x lets users download-then-run (`bash install.sh` or `./install.sh`).

### Rationale

Subagent that landed v1.8.0 (SessionStart hook registration) flagged `chmod +x` as "MANUAL FOLLOW-UP" — never done. v1.9.2's 10-test integration matrix passed because tests invoke scripts via `bash path/to/script.sh` (which doesn't need +x) — but Claude Code's real hook loader calls scripts as executables, requires +x. Test-harness gap, captured as a new dogfood finding for the next test-matrix iteration: verify file modes via `git ls-files -s`, not just functional invocation.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.3 and git propagates the new file modes. Fresh installs via `curl | bash` get the correct modes immediately.

## [1.9.2] — 2026-04-22

Governance injection — closes Finding #22 ("governance blocks don't fire on every turn").

### Fixed

- `/core:start` now writes `.claude/CLAUDE.md` with a marker-delimited Sutra-managed governance block containing Input Routing + Depth Estimation + Readability Gate + Output Trace templates. Claude Code loads CLAUDE.md as project system context on every session, so every response now emits governance blocks — fulfilling the sutra.os promise.
- Idempotent: re-running `/core:start` updates the managed block in-place (detected by `<!-- SUTRA GOVERNANCE ... -->` markers) without clobbering the user's other CLAUDE.md content.

### Rationale

v1.7.1 fixed alias collision. v1.8.0 wired auto-activation. v1.9.1 added identity stamping. Dogfood on 2026-04-22 revealed governance blocks still weren't emitting on every turn — Claude Code's Skill tool doesn't auto-invoke skills per turn; it fires skills on semantic match. Research question "top restaurants in Mumbai" had no semantic match to governance skills, so no blocks fired. The missing piece: instructing the LLM via CLAUDE.md (which IS loaded every session). v1.9.2 adds that injection.

### Migration

Existing v1.8.x / v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.2. Running `/core:start` in any project writes/updates the managed CLAUDE.md block. Existing CLAUDE.md content untouched — the block is marker-delimited and appendable. To opt out on a specific project: manually delete the block (between the SUTRA GOVERNANCE markers) from that project's CLAUDE.md.

## [1.9.0] — 2026-04-22

Identity stamping — know who's running the plugin. Backward-compatible, additive.

### Added

- **`lib/identity.sh`** — new library. `capture_identity <version>` emits a JSON object with git_user_name, git_user_email_hash (SHA-256[:16]), github_login, github_id, hostname_hash (SHA-256[:12]), os_name, os_version, os_pretty, arch, shell_name, locale, tz, captured_at, captured_by_version. Fallback chain: git global → git local → gh api → system GECOS → `$USER`. Every step best-effort; never fails a session. 3-second timeout on gh API calls.
- **`tests/unit/test-identity.sh`** — 10 unit tests covering JSON shape, required keys, hash field shapes, fallback when git+gh are unavailable, staleness detection.
- **`tests/integration/test-identity-stamp.sh`** — 7 integration tests: onboard stamps local JSON + cache, push stamps manifest on bare repo, 7d staleness gate holds, 8-day-old cache triggers recapture, emit-metric PII rejection still active (regression guard).

### Changed

- **`scripts/onboard.sh`** — sources `lib/identity.sh`; when `telemetry_optin=true`, captures identity and stamps it into `.claude/sutra-project.json` > `identity:`. Also caches to `$SUTRA_HOME/identity.json` (chmod 600) for push-time staleness checks.
- **`scripts/push.sh`** — sources `lib/identity.sh`; on each push, checks cache freshness (`identity_is_stale`, default 7 days). Stale or missing → recapture. Stamps the identity block into `clients/<install_id>/manifest.json` alongside existing `push_count` / `last_seen` / `sutra_version` fields. **Retroactive for existing installs** — next push after upgrade stamps the identity block without requiring a re-onboard.

### Privacy

- **Metrics channel unchanged.** `emit-metric.sh` still regex-rejects PII in `dept`/`metric`/`unit`/`window` fields (regression-tested). Telemetry `*.jsonl` rows remain PII-free.
- **Identity channel is a new, separate channel** living in `manifest.json`. Activated by existing `telemetry_optin` (default `true` when `/core:start` runs with `profile=project|company`, default `false` with `profile=individual`). Flip `telemetry_optin: false` in `.claude/sutra-project.json` to turn OFF — effect is immediate; next push omits identity.
- **Fields captured are user-supplied** (git config, gh auth) or coarse machine metadata (os, arch, tz). Raw email and raw hostname are NOT captured — both are SHA-256 hashed to 16/12 hex chars. See PRIVACY.md for full matrix.

### Rationale

Founder direction 2026-04-22 — needed a fleet view of Sutra users (portfolio + external friends who install via marketplace). Prior manifest carried only hashed install_id + project_id, leaving new installs unidentifiable. v1.9.0 closes that gap with a separate, opt-in-by-default identity channel that preserves the existing PII-free posture of the metrics channel.

Design doc (asawa-holding repo): `holding/research/2026-04-22-sutra-identity-capture-v17-design.md`.

### Migration

- Existing users: `claude plugin marketplace update sutra && claude plugin update core@sutra`. Next Stop-hook auto-push stamps identity. No manual action required.
- Users who had `telemetry_optin: false` stay unstamped until they flip the flag. No behavior change for them.
- Downstream companies (DayFlow, Billu, etc. — when plugin-installed): inherit on next auto-update.

## [1.8.0] — 2026-04-22

One-command install — closes the last mile of "one command does everything."

### Added

- **`hooks/sessionstart-auto-activate.sh`** — REGISTERED in `hooks.json` (sibling of `update-banner.sh` on SessionStart). Fires on every session start; ACTS only when the sentinel `~/.sutra/installed-via-script` exists AND the current project has no `.claude/sutra-project.json`. Runs `sutra start` via absolute `${CLAUDE_PLUGIN_ROOT}/bin/sutra` (Finding #12-safe), deletes sentinel on success (one-shot), never blocks session start (trap + `exit 0`).
- **`website/install.sh`** — committed in v1.7.1, now operative. Serves from GitHub raw at `https://raw.githubusercontent.com/sankalpasawa/sutra/main/website/install.sh`. No Vercel, no third-party deploy.

### Changed

- **User-facing install flow collapses from 4 commands to 1.** Previous: `claude plugin marketplace add` → `claude plugin install` → `/reload-plugins` → `/core:start`. New: `curl -fsSL <raw-url> | bash` → open `claude` → first session auto-activates.

### Rationale

Founder direction 2026-04-22 (memory `project_sutra_permissions_in_start.md`): "one command should do everything — no 4-step ceremony." v1.7.1 shipped the prerequisite (alias-collision fix, Finding #12). v1.8.0 completes the vision.

### Migration

- Existing v1.7.x users: `claude plugin marketplace update sutra` pulls v1.8.0. The new SessionStart hook is a no-op for already-activated installs (sentinel gate). Fresh installs via `curl | bash` get auto-activation on first `claude`.

## [1.7.1] — 2026-04-22

Shell-alias collision fix (Codex-converged Option E).

### Fixed

- **All internal `!sutra <sub>` invocations in `commands/*.md`, `scripts/*.sh`, and `hooks/*.sh` now use absolute plugin-root paths (`${CLAUDE_PLUGIN_ROOT}/bin/sutra <sub>`).** Shell aliases, functions, or PATH-shadowing `sutra` binaries can no longer intercept plugin self-invocation. Fixes dogfood Finding #12 (P0 shipping blocker, 2026-04-22).
- Regression test `tests/integration/test-alias-collision.sh` reproduces the founder-observed collision (alias hijacks the plugin's `sutra start` call and redirects into an unrelated project) and asserts activation still succeeds.

### Rationale

Initial diagnosis (`design/2026-04-22-sutra-cli-collision.md`) favored renaming `bin/sutra` → `bin/sutra-core` (Option A) plus a runtime `type -a` self-check (Option D). Codex challenge (`design/2026-04-22-sutra-cli-collision-codex-consult.md`) revealed Option D is conceptually wrong as a *runtime* safety layer — if the user's alias wins shell name resolution, the plugin binary never executes, so the self-check never fires. Option E closes the bug class for *any* name collision (not only `sutra`), ships as a patch with zero breaking changes, and touches ~15 files instead of ~35.

## [1.7.0] — 2026-04-22

C3c token-compression bundle — Tokens charter per-turn cost-component cut.

### Added

- **RTK auto-rewrite whitelist (native tools)** — `hooks/rtk-auto-rewrite.sh`. PreToolUse(Bash) hook that blocks unprefixed voluminous git commands and forces `rtk <cmd>` wrap. Whitelist v2: `git status`, `git log`, `git diff`, `git blame`, `git show`. Typical reduction 30-60% on wrapped commands (measured on Asawa repo). Kill-switch: `touch ~/.rtk-disabled` or `RTK_DISABLED=1`.
- **MCP output compression (all MCP tools)** — `hooks/posttool-mcp-compress.sh`. PostToolUse hook matched on `mcp__.*` that REPLACES large MCP outputs via `hookSpecificOutput.updatedMCPToolOutput` with a head+error+tail compressed summary. Thresholds: size ≥ 4000 bytes AND line count ≥ 80. Smoke-tested: 5,099-byte playwright snapshot → 2,583 bytes (49% cut). Telemetry at `.enforcement/c3c-compress.jsonl`. Codex-verified mechanism + docs-verified (code.claude.com/docs/en/hooks). Kill-switch: `touch ~/.c3c-disabled` or `C3C_DISABLED=1`.

### Changed

- `hooks/hooks.json` registers the two new hooks — RTK on PreToolUse(Bash), MCP-compress on PostToolUse(matcher `mcp__.*`).

### Rationale

Founder direction 2026-04-22: "don't change what I write — find background optimizations for the printing part." Output tokens can't be compressed post-generation, but TOOL OUTPUT Claude reads CAN be compressed before entering context. Native-tool track uses PreToolUse command rewriting via RTK; MCP-tool track uses PostToolUse output replacement. Paired commits ship them as one OS bundle.

### Migration

- Existing v1.6.x users: `claude plugin marketplace update sutra` picks up both hooks automatically. No config change required.
- Both hooks have individual kill-switches if needed: `~/.rtk-disabled` disables native; `~/.c3c-disabled` disables MCP.

## [1.6.0] — 2026-04-22

Per-profile enforcement + hard-block mode + release channels.

### Added

- **User profiles** — plugin.json `userConfig.profile` accepts `individual`, `project`, or `company`. Claude Code prompts at enable time. Writes to `.claude/sutra-project.json`.
- **Profile-dependent telemetry default** — `individual` = off (privacy default), `project` = on, `company` = on.
- **Hard enforcement on `company` profile** — `hooks/depth-marker-pretool.sh` reads the profile and exits 2 (blocks the tool call) when the depth marker is missing, ONLY for `company` profile. `individual` and `project` stay warn-only.
- **Escape hatch** — `SUTRA_BYPASS=1 <cmd>` prefix skips the depth check for one tool call, even on `company`. Audit trail preserved via existing routing-misses log.
- **Release channels** — two marketplace branches on the repo:
  - `main` branch = **latest** (current behavior; auto-updates push new versions immediately)
  - `stable` branch = **stable** (promoted manually once a version is proven in portfolio use)
  - Users pick: `claude plugin marketplace add sankalpasawa/sutra` (latest) or `claude plugin marketplace add sankalpasawa/sutra@stable` (stable).

### Changed

- `/core:start` accepts `--profile individual|project|company` and also reads `CLAUDE_PLUGIN_OPTION_PROFILE` env var that Claude Code injects from userConfig.
- Activation banner now shows the active profile + enforcement mode.

### Migration

- Existing v1.5.x users: no action needed — `/core:start` on v1.6.0 defaults to `project` profile which preserves current warn-only behavior and telemetry-on default.
- To opt into hard enforcement: `/core:start --profile company`.
- To opt into privacy-default: `/core:start --profile individual`.

### Rationale

Founder direction 2026-04-21: "do 14, 15, 16, 17" — collapse P3 items into one profile-aware release. Per-profile defaults (#15) enables hard enforcement (#14) without breaking casual users. Release channels (#16) shipped as a parallel git-branch pattern so stable adopters can pin without affecting latest-chasing early users. Smoke-tested: company profile exits 2 on missing marker; individual/project stay warn-only exit 0.

## [1.5.1] — 2026-04-22

### Added

- **`session-retrieve` skill** — recovers abruptly-closed Claude Code sessions after laptop shutdowns, kernel panics, or API timeouts. Scans `~/.claude/projects/*.jsonl` for orphan signatures (explicit `API Error` OR silent mid-`tool_use` deaths), returns `claude -r <id>` resume commands with correctly-decoded project roots.
- CATALOG.md §7b "Skills (by LLM interactive surface)" — new taxonomy section. Skills organized by the harness they run in (Terminal / Desktop / Web / SDK). Terminal subsection contains all 5 plugin skills; other surface subsections reserved for future.
- Trigger phrases for the skill: "figure out past sessions", "what sessions got killed", "my laptop switched off — what was I working on", "find my crashed sessions", etc.

### Why it exists

Session-retrieve was built after a laptop shutdown lost 5 mid-flight sessions. The manual recovery took ~15 min of jsonl grepping and two wrong `claude -r` attempts (wrong project root). Skill encodes the deterministic procedure: detect both orphan flavors, decode the project slug for resume (never use the `cwd` field — #1 failure mode), dedupe shared roots, and output a readability-gate compliant report.

## [1.5.0] — 2026-04-21

Plugin renamed `sutra` → `core` within the `sutra` marketplace, plus permission-prompt transparency.

### Added

- `PERMISSIONS.md` — complete, auditable list of every Bash and Write permission the plugin needs, grouped by purpose, with a paste-ready allowlist.
- `/core:permissions` (+ `sutra permissions` in terminal) — prints the exact JSON snippet to paste into `.claude/settings.local.json`. One paste, zero further prompts.

### Changed (BREAKING — plugin identifier rename)

- Plugin name `sutra` → `core`. Install is now `claude plugin install core@sutra`. Slash commands move to `/core:*` namespace.
- Marketplace name stays `sutra`. Install pattern: `core@sutra` reads as "core plugin from the sutra marketplace" (Anthropic's standard "hub + product" naming pattern, same shape as `superpowers@claude-plugins-official`).
- All docs + scripts + command files updated: `/sutra:start` → `/core:start`, `sutra@sutra` → `core@sutra`.
- Binary kept as `sutra` — terminal users still type `sutra start`, `sutra status`, etc. Slash commands use `/core:*` because Claude Code namespaces by plugin name.

### Migration for existing users

Claude Code treats the rename as a different plugin (not an update). Users on v1.4.x must:

```
claude plugin uninstall sutra@sutra
claude plugin marketplace update sutra
claude plugin install core@sutra
/core:start
```

v1.5.0 cannot auto-migrate because the plugin identifier changed. Sorry.

### Rationale

Founder direction 2026-04-21: "core@sutra" — collapse the visual stutter in `sutra@sutra` by adopting the multi-plugin marketplace naming pattern. Marketplace name remains "sutra" so future plugins (e.g., `sutra-lite`, domain-specific variants) can sit alongside `core` under the same hub.

## [1.4.0] — 2026-04-21

Radical UX simplification: **one command does everything.**

### Added

- `/sutra:start` — THE one command. Onboards the project, enables telemetry, prints the activation banner, writes a depth marker. Everything a new user needs in one invocation.
- `/sutra:update` — slash-command front-end for `claude plugin marketplace update sutra && claude plugin update sutra@sutra`.
- `/sutra:uninstall` — slash-command front-end for `claude plugin uninstall sutra@sutra`. Accepts `--purge` to also wipe `~/.sutra/`.
- `scripts/start.sh` — merged flow from prior `go.sh` + depth-marker init + richer activation banner.

### Removed (BREAKING)

- `/sutra:onboard` — merged into `/sutra:start`.
- `/sutra:go` — merged into `/sutra:start`.
- `/sutra:sutra` — activation banner now emitted by `/sutra:start`.
- `/sutra:push` — auto-push runs on Stop event; manual push moved to power-user CLI (`sutra push`).

### Changed

- `bin/sutra` collapsed to four lifecycle verbs: `start / status / update / uninstall`. `push / onboard / go / leak-audit / install-shell-helpers / version / help` kept as secondary callable subcommands for power users and shell helpers.
- Telemetry default: `/sutra:start` sets `telemetry_optin = true`. Users who want privacy can edit `.claude/sutra-project.json` post-run; `PRIVACY.md` documents the flip.

### Rationale

Founder feedback 2026-04-21: "Users don't have to do multiple things — keep it start and we do the entire install and everything." Six user-facing slash commands collapsed to five, with one clear entry point.

### Migration

- Anyone who typed `/sutra:onboard` or `/sutra:go` — use `/sutra:start` instead.
- Shell helpers: `sutra-go` will be removed in v1.5; `sutra-start` alias coming in a shell-helper patch.

## [1.3.1] — 2026-04-21

User-facing polish around v1.3.0's breaking rename.

### Added

- `hooks/update-banner.sh` — SessionStart hook prints a one-time banner when the plugin version changes (e.g., after auto-update), with a link to CHANGELOG. Silent on first run and unchanged-version runs. Writes state to `~/.sutra/last-seen-version`.
- `PRIVACY.md` — explicit statement of what's collected and never collected. Default `telemetry_optin = false`. Third-party destinations: none.
- `VERSIONING.md` — SemVer policy explaining when we bump MAJOR / MINOR / PATCH, the v1.3.0 rename exception, yanking procedure, and release-channel roadmap.

### Rationale

v1.3.0's command rename was breaking for anyone running an older version. Without a banner, users would silently hit "unknown command" on `/sutra:sutra-onboard`. The banner now surfaces the update + links CHANGELOG so the migration is discoverable.

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
