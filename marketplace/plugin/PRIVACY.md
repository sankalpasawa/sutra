# Sutra — Privacy

*Version: plugin v2.18.0 · Updated: 2026-05-03 · License: MIT*

Sutra helps you build. To do that well, it learns from how you work — locally, on your machine, with strict limits.

## v2.18.0 amendment — opt-in transport restored (2026-05-03)

**TL;DR**: default is **OFF**. Nothing leaves your machine without explicit opt-in. If you opt in via `--telemetry on`, signals push to a Sutra-team GitHub repo on every Stop event. `SUTRA_TELEMETRY=0` is the single kill-switch and disables both local capture AND outbound push uniformly.

**What changed from v2.0**: v2.0 framed itself as "no outbound transmission in default mode" and treated push as deprecated infrastructure. That was incomplete — the `--telemetry on` flag (added v2.9.1) persisted opt-in but never actually transmitted because a hard gate in `scripts/push.sh` blocked all pushes regardless of consent. v2.18.0 honors the opt-in.

**On the opt-in path** (when you ran `/core:start --telemetry on` or `/sutra-go`):

| Aspect | Detail |
|---|---|
| **WHAT pushed** | Local metric queue (`~/.sutra/metrics-queue.jsonl`, schema-validated rows: `install_id`, `project_id`, `ts`, `sutra_version`, `tier`, `dept`, `metric`, `value`, `unit`, `window`) PLUS a small manifest file with `install_id`, `project_id`, `project_name_optional`, `sutra_version`, `push_count`, `first_seen`, `last_seen` |
| **CADENCE** | Automatic on every Stop event when opted in. Async, fire-and-forget. Failed pushes preserve the queue for next attempt. |
| **DESTINATION** | `sankalpasawa/sutra-data` — **PRIVATE on GitHub but COLLABORATOR-VISIBLE** (same disclosure as PROTO-024 V1 §"Say something directly" below). Every install that has push access can read every other install's `clients/<install_id>/` directory. |
| **NOT pushed** | Identity stamping (removed v2.2.0 — no `github_login`, `git_user_name`, `git_user_email`, hostname, etc. crosses the wire on this rail). Source code, prompts, file content — all stay local per the v2.0 "signals not content" capture model. |
| **KILL-SWITCH** | `SUTRA_TELEMETRY=0` (env var) disables both **capture** (no rows enter the queue) AND **push** (push.sh / flush-telemetry.sh / posttool-counter.sh / emit-metric.sh all early-exit on this). Setting this AFTER opting in stops further transmission immediately even if `telemetry_optin=true` remains in `.claude/sutra-project.json`. |

**To opt out completely** after opting in:
```
SUTRA_TELEMETRY=0     # env (single session) OR put in your shell profile
rm -rf ~/.sutra/      # delete everything Sutra has written locally
```
The `telemetry_optin=true` flag in `.claude/sutra-project.json` becomes inert under `SUTRA_TELEMETRY=0`.

**Codex review**: 5-round consult chain converged at PASS — see `.enforcement/codex-reviews/2026-05-03-v2.18.0-opt-in-push.md` for the verdict trail.

---

## What we capture

**Signals, not content.** Sutra counts things like:

- How often a governance hook blocks an action
- How often you override a hook (and which one)
- How often a tool fails (by tool name and error class)
- Whether tasks finish or get abandoned

We derive these from metadata Sutra already sees during normal operation: tool names, hook IDs, exit codes, environment variable **names** (not values). We do not store your prompts, code, diffs, or files.

**One exception, disclosed precisely**: to count "correction" signals — when you say *no*, *stop*, *don't*, *actually* to Sutra — the plugin reads your prompt text **in memory only** during the hook run. Nothing from the prompt is written to disk or transmitted. Only a counter increments.

## What we never touch

- Source code, file contents, git diffs
- Session transcripts
- API keys, tokens, secrets (auto-scrubbed as a secondary guard)
- Real user names or full filesystem paths (sanitized to `<HOME>`)

## Where it lives

On your machine, in `~/.sutra/`. Sutra itself does not transmit this data off your machine by default.

**Your default is off-disk.** On first install (external users), signals are counted **in memory only** for the current session. Nothing is written to `~/.sutra/feedback/auto/` until you explicitly consent:

- Run `/sutra feedback "anything"` once → consent granted for this install, future signals persist locally
- Or set `SUTRA_FEEDBACK_CONSENT=granted` in your shell

Without consent, counters exist only in the current session and vanish when the session ends. Sutra keeps working — you just don't accumulate cross-session feedback insights.

**What we can't control**: your OS may replicate `~/.sutra/` via Time Machine, iCloud Drive, or enterprise endpoint agents. Sutra sets permissions to `0700` on directories and `0600` on files, but cannot override OS-level backup or sync. Document your own backup hygiene.

**Inspect what's stored right now**:

```
ls ~/.sutra/feedback/auto/        # list signal files
ls ~/.sutra/feedback/manual/      # list things you typed via /sutra feedback
```

Files are JSONL — one signal per line, each with category + counter. Human-readable.

## How long we keep it

- 30 days by default. Older data auto-deleted on next hook fire.
- `SUTRA_RETENTION_DAYS=N` (1-90) to change.

## Turn it off completely

```
SUTRA_TELEMETRY=0            # zero auto-capture, not even in memory
rm -rf ~/.sutra/             # delete everything Sutra has written
```

Sutra keeps working at full functionality with zero data captured.

## Say something directly

```
/sutra feedback "your thoughts here"
```

This stores your message at `~/.sutra/feedback/manual/<timestamp>.md` and grants consent for future auto-capture to persist.

**v2.6.0+ — feedback is also pushed to the Sutra team's private GitHub repo (PROTO-024 V1).**

What that means precisely:
- Your message is **scrubbed** locally (paths, secrets, JWTs, GitHub/OpenAI/AWS/Slack/Stripe tokens, signed URLs, DSNs, webhooks, emails, phone numbers, plus a 40+ character high-entropy fallback for anything regex misses).
- The scrubbed copy is committed and pushed to `sankalpasawa/sutra-data` under `clients/<install_id>/feedback/<timestamp>.md`.
- This repo is **PRIVATE on GitHub**, but it is **collaborator-visible** — every install that has push access to write telemetry to this repo also has read access to all other installs' feedback files.
- For V1, this is **not a private team-only channel** — it is a **collaborator-visible inbox**. V2 (planned) adds client-side encryption (RSA-4096 + AES-256-CBC hybrid via `openssl`) so other collaborators see only opaque ciphertext.
- If you want zero outbound transmission, disable with any of:
  - `--no-fanout` flag on the call (`/sutra feedback --no-fanout "..."`)
  - `SUTRA_FEEDBACK_FANOUT=0` env var
  - `touch ~/.sutra-feedback-fanout-disabled` file
- If you want world-visible (rather than collaborator-visible), use `/sutra feedback --public "..."` which posts a GitHub issue at `sankalpasawa/sutra` with explicit confirmation.

**Full V1 residual-risk set (deferred to V2)** — mirrors PROTOCOLS.md PROTO-024:
- **H1/H10** Cross-tenant content readability — V2 closes via client-side encryption to a Sutra team public key shipped with the plugin.
- **H3** install_id is currently deterministic `sha256(HOME:version)[:16]` — linkable across repos for the same machine. V2 replaces with random 128-bit hex per install, stored in `~/.sutra/identity.json`.
- **H5** Git history retains scrubbed payload after reap. "User-deletable" applies to local file and remote tip; history persists. V2 ciphertext-in-history is opaque without the private key.
- **H8** Identity join is server-side / founder-manual in V1. V2 keeps identity in encrypted payload, joined only after decryption.
- **Filenames** in V1 are `<timestamp>.md` under `clients/<install_id>/feedback/`. V2 uses random UUIDs in a flat path so install↔file linkage is broken for collaborator-readers.
- **Key rotation** — V2 ships with a documented yearly key rotation policy.

**Why this is honest, not hidden**: the codex review on 2026-04-25 (`.enforcement/codex-reviews/2026-04-25-proto-024-feedback-fanin-and-reset-hook-fix.md`) flagged that calling V1 "private" would be inaccurate. PROTO-024 V1 ships with HONEST wording: collaborator-visible inbox, not a private channel.

### Close-Loop Layer (v2.8.0, 2026-04-28)

When you file a public issue at `sankalpasawa/sutra` (via `/sutra feedback --public` or directly on github.com), and we later ship a fix, we want to tell you in a way you'll actually see — not bury the announcement in a github email you might miss. Two things happen:

1. **Mapping recorded.** When `/sutra feedback --public` succeeds, the plugin writes `{install_id, issue_number, title, ts}` to two places:
   - Local: `~/.sutra/feedback/manual/sent.jsonl` (your machine only)
   - Server-pushed: `clients/<install_id>/feedback-mapping.jsonl` in `sankalpasawa/sutra-data` (collaborator-visible like the rest of that repo — same disclosure as PROTO-024 V1 above)

   This is needed so the close-out can reach the right plugin install. The mapping does NOT include the body of your feedback — that's already in the public gh issue.

2. **Inbox display on session start.** A new `inbox-display.sh` hook runs on every Sutra session start. It does two things:
   - Reads `clients/<install_id>/inbox/` from `sankalpasawa/sutra-data` for any close-out messages addressed to your install. Verifies the message's `gh_author` field matches your `gh api user --jq .login` BEFORE displaying (privacy two-factor — fence against wrong-user delivery if mapping has a bug).
   - If `gh auth` is set up on your machine, also queries the gh API for issues authored by you that closed since last-seen, displays close-out comments. This covers feedback filed via gh-UI directly (no plugin involvement, no mapping).

**Disclosure same as PROTO-024 V1:** the inbox files at `clients/<install_id>/inbox/<ts>-<#>.md` are collaborator-visible to anyone with push access to `sankalpasawa/sutra-data`. They contain the close-out comment text (which is also publicly visible on the gh issue) plus your `gh_author` username. V2 will encrypt.

**Kill-switches:**
- `SUTRA_INBOX_DISABLED=1` — env var, single-session
- `~/.sutra-inbox-disabled` — file presence, persistent

If you don't want close-out messages displayed, set either kill-switch. The hook soft-fails (exit 0) regardless of any error path, so it never blocks session start.

## What we don't promise

- We don't promise OS-level backups will exclude `~/.sutra/`. They might include it. That's outside Sutra's control.
- We don't promise Spotlight won't index the files. To exclude, create `~/.sutra/.noindex` or run `xattr -w com.apple.metadata:com_apple_backup_excludeItem true ~/.sutra/`.
- We don't promise regex scrubbing catches every secret pattern ever invented. It's a secondary guardrail. The primary defense is that Sutra derives signals from hook metadata, not from scanning your text for secrets. If you find a secret type we miss, tell us via `/sutra feedback`.

## Tier-specific defaults

> **[SUPERSEDED in v2.18.0 — 2026-05-03]** The paragraph below was written when telemetry coupled to the install profile (T1/T2 auto-consent / T3-T4 strict). v2.9.1 decoupled the two — telemetry is now controlled by an explicit `--telemetry on|off` flag, default OFF for ALL tiers. v2.18.0 honors that opt-in by actually transmitting (see top-of-doc amendment). The original tier-default text is preserved below for historical accuracy only; it no longer reflects current behavior.

~~If you're running Sutra inside an Asawa-owned setup (T1 internal / T2 owned portfolio), auto-capture persists by default and fan-in to the Sutra team is implicit — your operator has already consented on your behalf. T3 client-owned projects and T4 external fleet installs follow the strictest model described above.~~

## Questions or problems

- `/sutra feedback "your message"` — stays local, no account needed
- Audit the code if you want: the plugin source lives in the Sutra repository and every file in `sutra/marketplace/plugin/` is the actual code that runs

---

## Changelog

### v2.2.0 (2026-04-25) — PROTO-024 V1 feedback fanout (collaborator-visible inbox)

What changed from v2.1.0:

- **`/sutra feedback` now pushes to Sutra team's private GitHub repo** (PROTO-024 V1). Scrubbed content lands at `sankalpasawa/sutra-data` under `clients/<install_id>/feedback/<ts>.md`. **This is a collaborator-visible inbox, not a private team-only channel** — every install with push access can read all feedback. V2 (planned) closes this with client-side encryption.
- **Strengthened scrub** in `lib/privacy-sanitize.sh`: added detectors for GitHub `ghp_*`, OpenAI `sk-*`, AWS `AKIA*`, Slack `xoxb-*`, Stripe `sk_live_*`, JWTs, signed URLs (S3/GCS/Azure), DSNs, webhook URLs, emails, E.164 phone, plus a 40+ character high-entropy fallback for anything regex misses.
- **`manifest.identity` no longer written on push** (closes the v1.9.0 PII leak that stamped `github_login`/`github_id`/`git_user_name` into the remote manifest on every telemetry push). Pre-v2.2.0 manifests on the remote are left intact (no retroactive scrub in this ship; planned for V2 transport).
- **`/sutra feedback` decoupled from `SUTRA_TELEMETRY=0`**: turning telemetry off no longer disables manual feedback. The two opt-outs are now independent — `SUTRA_FEEDBACK_FANOUT=0` (or `~/.sutra-feedback-fanout-disabled`, or the `--no-fanout` flag) is the manual-feedback fanout kill-switch.
- **`reset-turn-markers.sh` moved from `UserPromptSubmit` to `Stop` event**: closes a spoof vulnerability where a real user prompt containing a sentinel string could suppress per-turn governance reset. The hook now fires only at assistant turn end, where there is no synthetic-turn ambiguity.

What did NOT change:

- Local capture path (`~/.sutra/feedback/manual/<ts>.md`) is unchanged.
- Auto-capture signals (override / correction / abandonment) stay LOCAL — fanout NOT in V2.2.0.
- Permissions (`0700`/`0600`) unchanged.
- Retention default (30d) unchanged.

### v2.0.0 (2026-04-24) — privacy model replaced

What changed from v1.9.0:

- **Signals, not content**: new capture derives counters from hook metadata; does not scan prompt or file content as the primary mechanism.
- **In-memory-until-consent** for external installs: new `~/.sutra/feedback/auto/` path is not written until first `/sutra feedback` grants consent.
- **Legacy telemetry DEPRECATED**: the previous model (`telemetry_optin = true` in `.claude/sutra-project.json`, identity stamping into `manifest.json`, push to `sankalpasawa/sutra-data` on every Stop event) is superseded. It remains available gated behind `SUTRA_LEGACY_TELEMETRY=1` for compatibility with existing T1/T2 workflows; new installs get the v2 model.
- **New hardening**: `0700`/`0600` permissions, atomic writes, append-locked JSONL, symlink-refusal for `~/.sutra/`.
- **Scope reduction**: ~~no outbound transmission in v2 default mode. No GitHub push, no transport layer.~~ **[SUPERSEDED in v2.18.0 — 2026-05-03]** This was true at v2.0 and remained accidentally true through v2.17 because a hard gate in `scripts/push.sh` blocked all pushes regardless of consent. v2.9.1 added the `--telemetry on|off` opt-in flag but did not lift the v2.0 transport block — net effect was opt-in theater. v2.18.0 lifts the block and honors the opt-in: when you explicitly run `--telemetry on`, push to `sankalpasawa/sutra-data` resumes on every Stop event. **Default OFF posture is unchanged.** See top-of-doc v2.18.0 amendment for the full opt-in disclosure (what's pushed, cadence, destination, kill-switch).

---

## Legacy model (v1.9.0, deprecated — gated behind `SUTRA_LEGACY_TELEMETRY=1`)

The following was the prior privacy contract. It is no longer the default. New installs should not see it apply unless `SUTRA_LEGACY_TELEMETRY=1` is explicitly set.

### v1.9.0 identity stamping (deprecated)

When `telemetry_optin = true` under the legacy flag, the plugin stamped a structured `identity:` block into `manifest.json` in `sankalpasawa/sutra-data`:

| Field | What | Raw or hashed? |
|---|---|---|
| `git_user_name` | `git config user.name` | raw |
| `git_user_email_hash` | `sha256(git_user_email)[:16]` | hashed |
| `github_login` | `gh api user` .login | raw |
| `github_id` | `gh api user` .id | raw |
| `hostname_hash` | `sha256(hostname)[:12]` | hashed |
| `os_name`, `os_version`, `arch` | `uname`, `sw_vers` | raw |
| `shell_name`, `locale`, `tz` | `$SHELL`, `$LANG`, `date +%Z` | raw |

### v1.4.0 default behavior (deprecated)

Previously, running `/core:start` enabled telemetry by default (`telemetry_optin = true`). In v2.0 this no longer activates anything. The onboarding flow no longer auto-opts you into transmission.

### v1 push contract (deprecated)

On every `Stop` event, the legacy path pushed schema-validated JSONL rows to a private GitHub repo (`sankalpasawa/sutra-data`). Validated fields: `install_id`, `project_id`, `sutra_version`, `tier`, `dept`, `metric`, `value`, `unit`, `window`, `ts`. Regex-rejected fields: file paths, prompt content, emails, GitHub handles, company names, anything containing `/Users/`, `/home/`, or `C:\`.

### v1 legacy opt-out (still works)

- Edit `.claude/sutra-project.json` → `"telemetry_optin": false` (legacy flag, effect immediate on next Stop)
- OR unset `SUTRA_LEGACY_TELEMETRY` to switch fully to v2 model

---

*The legacy section is retained for transparency about what the plugin used to do and for sites running legacy-gated installs. New users should read only the top of this document.*
