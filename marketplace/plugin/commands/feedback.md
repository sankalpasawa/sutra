---
name: feedback
description: Capture feedback about Sutra — stays local on your machine, never transmitted.
disable-model-invocation: false
---

# /core:feedback — Manual feedback channel

Writes your thoughts to `~/.sutra/feedback/manual/<timestamp>.md`. Nothing is sent anywhere. Running this also grants local consent so auto-capture signals (overrides, corrections, abandonment) start persisting to disk — see `~/.sutra/PRIVACY.md`.

No `--send` in v2. To share feedback with the Sutra team, copy the file manually.

!${CLAUDE_PLUGIN_ROOT}/bin/sutra feedback "$ARGUMENTS"
