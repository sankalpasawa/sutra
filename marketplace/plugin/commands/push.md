---
name: push
description: Push queued telemetry metrics to sankalpasawa/sutra-data. Manual, user-initiated. Respects telemetry_optin flag.
disable-model-invocation: true
---

# /sutra:push — Manual telemetry push

Transmits the Layer B queue (`~/.sutra/metrics-queue.jsonl`) to the central store.
Skips if `telemetry_optin` is `false` in `.claude/sutra-project.json`.

!sutra push

## Failure behavior

- Network / auth error → queue preserved, retry on next `/sutra:push`.
- Empty queue → no-op.
- Opt-in false → no-op with reminder.
