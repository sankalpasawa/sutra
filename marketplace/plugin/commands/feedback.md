---
name: feedback
description: Capture feedback about Sutra. Local by default; `--public` opts into a confirmed GitHub issue post via gh CLI.
disable-model-invocation: false
---

# /core:feedback — Feedback channel

**Default (local)** — writes your thoughts to `~/.sutra/feedback/manual/<timestamp>.md`. Nothing transmitted. Granting this also enables local consent so auto-capture signals (overrides, corrections, abandonment) persist to disk — see `~/.sutra/PRIVACY.md`.

**Opt-in transmit** — add `--public` to post the scrubbed body as a GitHub issue at `sankalpasawa/sutra` via the `gh` CLI. Requires `gh` installed + authenticated. Asks for a `yes` confirmation before posting (issue is PUBLIC + permanent). Falls back to local-only capture if `gh` is missing, not authed, or you cancel.

```
/core:feedback "short thought — stays local"
/core:feedback --public "bigger report — opens GitHub issue after I confirm"
```

Run this command via the Bash tool:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra feedback "$ARGUMENTS"
```
