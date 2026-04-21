---
name: onboard
description: First-time setup for Sutra in this project. Generates install_id + project_id, writes .claude/sutra-project.json, initializes local telemetry queue. Idempotent.
disable-model-invocation: true
---

# /sutra:onboard — Project onboarding

Writes `.claude/sutra-project.json` with deterministic install_id + project_id.

!sutra onboard

## What this does

- `install_id = sha256(HOME + sutra_version)[:16]` — stable per user+version
- `project_id = sha256(normalized_git_remote_url)[:12]` — stable per repo (cwd fallback)
- `telemetry_optin` defaults to `false` (preserved across re-runs)
- Queue initialized at `~/.sutra/metrics-queue.jsonl`

## Next steps

- `/sutra:status` to inspect state
- Edit `.claude/sutra-project.json` → `"telemetry_optin": true` to enable push
- `/sutra:push` to deliver queue to `sankalpasawa/sutra-data`
