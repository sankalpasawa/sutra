# Windows Support — Research & Decision Doc

*Author: CEO of Asawa · 2026-04-22 · Status: research-only, no implementation*

## Problem

Sutra plugin v1.5.1 ships skills + commands that work anywhere Claude Code runs, but enforcement hooks + the bin/sutra dispatcher are **bash-only**. Windows users get ~50% of plugin value today: model-side governance (input routing, depth estimation, readability gate, output trace, session retrieve) works because it's markdown guidance. Bash-hook enforcement (depth marker gate, estimation log, auto-push telemetry) is dark.

## Paths — three explicit options

### A. WSL2 requirement (ship today)

Document that Windows users install WSL2 and run Claude Code from inside it. Bash hooks then work identically.

- **Cost**: 0 engineering. One-line website + README section. Already shipped in v1.5.1 README.
- **Benefit**: Full plugin parity for WSL2-capable users.
- **Excludes**: Corporate Windows users without admin / WSL2 policy. Estimate: ~20-30% of Windows Claude Code users in enterprise environments.
- **Maintenance**: 0. Status: **ACTIVE (shipped v1.5.1)**.

### B. Dual bash / PowerShell implementations

Every `.sh` hook gets a `.ps1` sibling. Plugin detects OS, picks the right invocation in `hooks.json` via conditional entries.

- **Cost**: ~12 hours initial (6 hooks × 2 hours each including test) + ongoing maintenance 2× forever.
- **Benefit**: Native Windows, no WSL2 dependency.
- **Risk**: Dual implementations DRIFT. Tested by codex in prior small-team projects — failure rate >30% within 6 months. Hard requirement: CI that runs both variants on every change. That's a GitHub Actions matrix we don't have today.
- **Recommendation**: **SKIP** unless WSL2 adoption fails measurably (>50% of Windows users won't install WSL2 after 2-week data window).

### C. Node rewrite of hooks + dispatcher

Rewrite the 8 bash scripts (`bin/sutra` + 7 hooks) in Node/TypeScript. Ship `.js` files. Claude Code has Node on every platform. Single codebase.

- **Cost**: ~2-3 focused days initial. One-time pain. Single maintenance surface thereafter.
- **Benefit**: True cross-platform. Also: better testing (real test framework vs bash's fragile assertions), better error handling, easier to extend.
- **Risk**: Throws away ~500 lines of bash idioms we've accumulated + proven. Regression surface is real until outcome test suite catches up.
- **Dependencies**: Node >=18 on user machine. Claude Code already bundles Node runtime, so this is effectively zero additional user burden.
- **Recommendation**: **QUEUE for v2.0.0** alongside Supabase transport (already v2 roadmap). Bundle breaking changes into one major.

## Decision matrix

| Path | Ship time | User friction | Maintenance | Keep? |
|---|---|---|---|---|
| A (WSL2 docs) | DONE v1.5.1 | High for non-WSL2 users | Zero | ✅ retain as near-term |
| B (dual .ps1) | 12h | Low | 2× forever | ❌ skip |
| C (Node rewrite) | 2-3 days | Low | 1× | ⏳ v2.0.0 candidate |

## Telemetry target (before committing to C)

Before spending 2-3 days on Node rewrite, collect these for 2 weeks:

1. **Windows install attempts** — `install_id` grouped by OS (requires adding an OS field to install.mjs — out of scope today, v1.6+).
2. **WSL2 adoption rate** — what fraction of Windows install attempts followed the README WSL2 path. Proxy: GitHub Issues with `platform:windows` label mentioning WSL2.
3. **Churn** — installs that never ran `/core:start` (no telemetry push appears in sutra-data). Proxy for "bounced because it didn't work."

If Windows installs <5% of total after 2 weeks → keep A, skip C.
If Windows installs 5-20% + WSL2 adoption looks workable → keep A, plan C for v2.
If Windows installs >20% + WSL2 friction visible in issues → expedite C.

## What's shipped today (v1.5.1)

- [x] README platform compatibility matrix
- [x] WSL2 install path (Path A)
- [x] Website platform matrix
- [x] This research doc

## What's NOT shipped (deferred to v2+)

- [ ] Path C — Node rewrite of hooks + dispatcher
- [ ] OS field in install telemetry
- [ ] Windows-specific issue label on GitHub
- [ ] WSL2 adoption funnel

## Cross-references

- Plugin v1.5.1 README — platform matrix section
- Website `#get-started` platform compatibility callout
- VERSIONING.md — v2.0.0 line items
- PRIVACY.md — "v2 Supabase transport" roadmap (same release as Node rewrite)

## Operationalization

### 1. Measurement mechanism
Metric: windows_plugin_install_rate = Windows installs / total installs over rolling 14 days. Data source: sutra-data install telemetry once OS field exists (v1.6+). Null handling: report N/A until OS field ships.

### 2. Adoption mechanism
This doc is research-only; adoption is via future release decisions (v2.0.0 planning).

### 3. Monitoring / escalation
Who: CEO of Asawa. Cadence: monthly until Windows data exists; then quarterly. Warn threshold: >5% Windows installs without a chosen path forward. Breach: >15% Windows installs for 30 days with no path = unblock C immediately.

### 4. Iteration trigger
Revise when: (a) OS field ships in telemetry, (b) first 10 Windows installs observed, (c) a Windows user files a GitHub issue blocking on bash, (d) Claude Code hooks gain native PowerShell support.

### 5. DRI
Role: CEO of Asawa. Durable until v2.0.0 release planning hands off to implementation owner.

### 6. Decommission criteria
Retire this doc when: v2.0.0 ships Node rewrite (Path C) OR measurement confirms Windows demand stays <5% for 6 months (Path A is permanent).
