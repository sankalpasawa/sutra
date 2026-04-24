# Sutra — Privacy

*Version: plugin v2.0.0 · Updated: 2026-04-24 · License: MIT*

Sutra helps you build. To do that well, it learns from how you work — locally, on your machine, with strict limits.

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

This stores your message at `~/.sutra/feedback/manual/<timestamp>.md` and grants consent for future auto-capture to persist. The plugin does not send this anywhere — there is no `--send` command in v2.0. If you want Sutra team visibility, file an issue in the public source repo.

## What we don't promise

- We don't promise OS-level backups will exclude `~/.sutra/`. They might include it. That's outside Sutra's control.
- We don't promise Spotlight won't index the files. To exclude, create `~/.sutra/.noindex` or run `xattr -w com.apple.metadata:com_apple_backup_excludeItem true ~/.sutra/`.
- We don't promise regex scrubbing catches every secret pattern ever invented. It's a secondary guardrail. The primary defense is that Sutra derives signals from hook metadata, not from scanning your text for secrets. If you find a secret type we miss, tell us via `/sutra feedback`.

## Tier-specific defaults

If you're running Sutra inside an Asawa-owned setup (T1 internal / T2 owned portfolio), auto-capture persists by default and fan-in to the Sutra team is implicit — your operator has already consented on your behalf. T3 client-owned projects and T4 external fleet installs follow the strictest model described above.

## Questions or problems

- `/sutra feedback "your message"` — stays local, no account needed
- Audit the code if you want: the plugin source lives in the Sutra repository and every file in `sutra/marketplace/plugin/` is the actual code that runs

---

## Changelog

### v2.0.0 (2026-04-24) — privacy model replaced

What changed from v1.9.0:

- **Signals, not content**: new capture derives counters from hook metadata; does not scan prompt or file content as the primary mechanism.
- **In-memory-until-consent** for external installs: new `~/.sutra/feedback/auto/` path is not written until first `/sutra feedback` grants consent.
- **Legacy telemetry DEPRECATED**: the previous model (`telemetry_optin = true` in `.claude/sutra-project.json`, identity stamping into `manifest.json`, push to `sankalpasawa/sutra-data` on every Stop event) is superseded. It remains available gated behind `SUTRA_LEGACY_TELEMETRY=1` for compatibility with existing T1/T2 workflows; new installs get the v2 model.
- **New hardening**: `0700`/`0600` permissions, atomic writes, append-locked JSONL, symlink-refusal for `~/.sutra/`.
- **Scope reduction**: no outbound transmission in v2 default mode. No GitHub push, no transport layer. Sutra's improvement loop runs through manual `/sutra feedback` only until a consent-gated fan-in design ships in a future version.

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
