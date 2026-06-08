---
issue: 48
title: "[v2.8.11] # Feature proposal: `sutra schedule` \u2014 local-first cron with target failover"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T16:44:33Z
updated: 2026-04-30T16:44:33Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/48
comments: []
---

# #48 [v2.8.11] # Feature proposal: `sutra schedule` — local-first cron with target failover

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T16:44:33Z  |  **Updated:** 2026-04-30T16:44:33Z
**URL:** https://github.com/sankalpasawa/sutra/issues/48

---

# Feature proposal: `sutra schedule` — local-first cron with target failover

## Problem

The built-in `/schedule` slash command (Anthropic routines) **silently fails to execute** on accounts where the routines feature isn't enabled at the org level. The RemoteTrigger API accepts create/update/run/list operations and returns 200, but the execution engine never spawns sessions. No error surfaces anywhere CLI-accessible.

Today (2026-04-30) I lost ~5 hours diagnosing this. Reproduction:

1. Create routine via `/schedule` with `run_once_at` 2 minutes in future, prompt = 25-line Python that just calls `chat.postMessage` with one hardcoded text
2. Wait 6+ minutes
3. `RemoteTrigger get` returns `ended_reason: ""` (per docs, should be `"run_once_fired"` after a one-shot fires)
4. `next_run_at` unchanged at the past timestamp
5. No Slack post, no error, no log

Same gate as the routines UI returning `?reason=no_org_access`. Cannot be fixed from prompt-side; needs Anthropic to enable routines for the org.

## Proposal — `sutra schedule`

Sutra-native scheduler with pluggable backends, addressing the silent-no-op failure mode head-on.

**CLI:**
```
sutra schedule create <yaml>
sutra schedule list
sutra schedule logs <id> [--tail]
sutra schedule run <id>             # fire now
sutra schedule pause/resume <id>
sutra schedule diagnose <id>        # probe target health
sutra schedule remove <id>
sutra schedule migrate <id> --to <target>
```

**Backends (pluggable):**
- `launchd` — local macOS (works regardless of cloud feature flags)
- `github-actions` — cloud, free, debuggable, repo-based
- `cloudflare-workers` — edge cron
- `anthropic-routines` — drops in when org gets execution enabled

## Hard design constraints (lessons from today's incident)

1. **Smoke-test on create is non-negotiable.** Refuse to mark a schedule "active" until first execution is proven. Today's silent no-op was the root cause of a 5-hour debugging session.
2. **Liveness ≠ execution-success.** Track `last_executed_at` separately from `last_api_call_at`. Cron `next_run_at` advancing is *not* proof execution happened.
3. **Logs must be surfaceable** via `sutra schedule logs <id>` from day 1. If we can't read what a run did, the schedule isn't really active.
4. **Failover should be first-class.** Primary + backup target with automatic fallthrough on missed runs.
5. **Fail loudly, not silently.** Any execution that doesn't post the expected output should alert.

## YAML config sketch

```yaml
id: founder-digest-daily
name: "Sutra Founder Digest · Daily"

schedule:
  cron: "30 5 * * 1-5"           # 5-field UTC
  timezone_hint: "Asia/Calcutta"  # display-only
  human_readable: "Mon-Fri 11:00 IST"

target:
  primary: launchd
  backup: github-actions

job:
  type: claude-prompt              # claude-prompt | python-script | shell-script
  prompt: |
    [self-contained]
  # OR script_path: ./scripts/run.py

runtime:
  timeout_seconds: 900
  max_retries: 1

credentials:
  - env_var: SLACK_BOT_TOKEN
    keychain_service: testlify-digest-bot-token
    keychain_account: vinit

observability:
  log_path: ~/.sutra/schedules/{id}/logs/
  heartbeat_url: optional
  alert_on_failure:
    - slack_channel: "#alerts"

sutra:
  apply_governance: true           # each run gets input-routing/depth/readability
  telemetry: true
  depth_marker: 5
```

## Build phases

| Phase | Capability | Backends | Effort |
|---|---|---|---|
| **v0.1** | YAML + smoke-test + log surface | launchd | ~2 days |
| **v0.2** | + GitHub Actions backend | + gh-actions | ~3 days |
| **v0.3** | + Cloudflare Workers Cron | + cf-workers | ~3 days |
| **v0.4** | + Anthropic routines backend | + anthropic-routines | ~2 days |
| **v0.5** | Multi-target failover | primary + backup | ~3 days |
| **v0.6** | Sutra-governance integration | depth/routing/readability per run | ~2 days |
| **v0.7** | Observability dashboard | `sutra schedule status` | ~3 days |

**MVP (v0.1):** ~2 days, unblocks ~90% of single-developer cases (local launchd is enough when the user's machine is roughly always on).

**Production-ready (v0.5):** ~13 cumulative days.

## Why this isn't covered by existing tools

| Tool | Gap |
|---|---|
| `/schedule` (Anthropic routines) | Cloud-only · org-gated · opaque · no logs |
| macOS launchd | Too low-level · no Slack/Anthropic integration · no smoke-test |
| GitHub Actions | Requires separate repo + YAML language · not Sutra-native · no Keychain |
| Zapier / Make.com | Paid · AI synthesis is awkward · not Sutra-governance integrated |
| cron-job.org | Just hits URLs · needs separate endpoint to host · not credential-aware |

`sutra schedule` would fill the gap of *"I want a recurring Claude-powered job that posts to Slack, with logs I can actually read, that doesn't silently fail, and that integrates with the rest of my Sutra setup."*

## Open design decisions

1. **Prompt execution model** — Claude session per run, or shell script, or both?
2. **Cron syntax** — strict 5-field UTC, or natural language ("every weekday 11 AM IST")?
3. **Credential scope** — macOS Keychain only? Linux fallback (env vars)? 1Password CLI?
4. **Failover policy** — same-minute retry on primary failure, or next-minute, or manual?
5. **Governance coupling** — every scheduled run automatically gets input-routing/depth/readability? Opt-in? Never?
6. **State durability** — flat JSON in `~/.sutra/schedules/state.json` (git-friendly), SQLite (concurrent-safe), or file-system markers?

## Adjacent issue (likely separate ticket needed)

The underlying Anthropic routines silent-no-op behavior is probably worth its own report to Anthropic support — at minimum the API should surface `org_not_enabled` or similar when execution is gated, rather than returning 200 and silently dropping the schedule.

---

*Reported by: Vinit Asawa (Founder's Office, Testlify)*
*Filed via Sutra-governed Claude session, 2026-04-30*
