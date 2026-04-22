---
name: sutra-help
description: Show Sutra commands, the current install state, and how to get help. Use when the user says "help", "what can Sutra do", "sutra help", or types /sutra-help.
disable-model-invocation: true
---

# /sutra-help

Pull current state:

```!
echo "Sutra version: $(cat .claude/sutra-version 2>/dev/null | head -1 || echo 'not installed')"
echo "Hooks active: $(ls .claude/hooks/sutra/*.sh 2>/dev/null | wc -l | tr -d ' ')"
echo "OS docs installed: $(ls .claude/os/ 2>/dev/null | wc -l | tr -d ' ')"
echo "Recent hook fires: $(wc -l < .claude/logs/hook-fires.jsonl 2>/dev/null || echo 0)"
```

Render the help panel:

```
🧭 Sutra — help

Commands:
  /sutra           CEO day dashboard (activates Sutra mode)
  /sutra-onboard   Onboard a new company from scratch (guided)
  /sutra-update    Update Sutra OS to the latest version
  /sutra-help      This help
  /company         Open a company-scoped session

What Sutra does automatically:
  • Every message → input routing classification
  • Every task → depth + estimation block (1-5 scale)
  • Every Edit/Write → depth-marker enforcement
  • Every response → readability gate + OS trace
  • Every session → logged to .claude/logs/hook-fires.jsonl

Where to look:
  CLAUDE.md                       project identity + rules
  TODO.md                         priority stack
  os/STATUS.md                    where the project is
  os/METRICS.md                   KPIs
  os/OKRs.md                      goals + progress
  SUTRA-CONFIG.md                 tier, enforcement, depth defaults
  .claude/logs/hook-fires.jsonl   per-turn telemetry

Get help:
  Issues  https://github.com/sankalpasawa/sutra-os/issues
  Docs    https://github.com/sankalpasawa/sutra-os#readme
```
