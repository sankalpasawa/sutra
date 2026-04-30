---
name: start
description: The one command. Onboards this project, asks about telemetry (default OFF — explicit opt-in only), activates governance skills, writes a depth marker, prints what's active. Run this first.
disable-model-invocation: false
---

# /core:start — Activate Sutra here

One command. Everything.

## Telemetry preflight (interactive — first install only)

**Before running the bash command below, ASK THE USER:**

> "Do you want to enable Sutra telemetry to help improve the plugin? (default: no)
>  • YES → outbound metrics push enabled (see PRIVACY.md for what's collected)
>  • NO → local-only, no transmission (recommended default)"

**Skip the question** if `.claude/sutra-project.json` already exists (idempotent re-run — preserve existing setting).

**Then run** the bash command with the appropriate `--telemetry` flag:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra start --telemetry off    # default; user said no
${CLAUDE_PLUGIN_ROOT}/bin/sutra start --telemetry on     # user explicitly said yes
```

If user gives no clear answer or default, use `--telemetry off`. The flag precedence is:
**CLI flag > existing `.claude/sutra-project.json` > default OFF**.

## What happens

1. **Identity** — writes `.claude/sutra-project.json` with deterministic `install_id` + `project_id` (stable per user+version, per repo)
2. **Telemetry** — opt-in only; default OFF. You'll be asked at first install (this command). Edit the JSON file or re-run with `--telemetry on|off` to change later. See PRIVACY.md for what's collected.
3. **Skills** — governance skills auto-apply to every turn (per D40 v2.9.0 — see SUTRA-DEFAULTS.md)
4. **Depth marker** — a sensible default so the first Edit/Write doesn't trip the PreToolUse warn
5. **Queue** — local metrics queue initialized at `~/.sutra/metrics-queue.jsonl` (used only if telemetry opt-in)

Idempotent — re-running is safe (preserves existing telemetry setting).

## What you can use after `/core:start`

### Skills (8) — invoke any time

| Skill | What it does |
|---|---|
| `core:input-routing` | Classify user input (TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION) |
| `core:depth-estimation` | Emit `DEPTH X/5` block before any task; auto-estimation on completion |
| `core:blueprint` | Emit BLUEPRINT before tool calls (Doing / Steps / Scale / Stops if / Switch) |
| `core:output-trace` | One-line route trace at end of response |
| `core:readability-gate` | Format output (tables, ASCII boxes, numbers > adjectives) |
| `core:codex-sutra` | Codex CLI wrapper — review / challenge / consult modes (D40 default policy: consult before Edit/Write at Depth ≥ 3) |
| `core:skill-explain` | 4-line skill card (SKILL / WHAT / WHY / EXPECT / ASKS) before any skill invocation |
| `core:workflow` | Pedagogical wrapper — runs the full canonical Sutra sequence on one task |

### Commands (10) — slash invocations

| Command | Use |
|---|---|
| `/core:start` | (this) onboard / activate |
| `/core:status` | inspect install / queue / telemetry state |
| `/core:update` | pull the latest plugin version |
| `/core:permissions` | paste-ready settings.local.json snippet (reduce permission prompts) |
| `/core:depth-check` | manual Depth + Estimation block emit |
| `/core:learn` | interactive Sutra tutor — depth, routing, charters, hooks, build-layer |
| `/core:feedback` | capture feedback (local by default; `--public` opens GitHub issue) |
| `/core:sbom` | software bill of materials — SHA256 per shipped file |
| `/core:workflow` | pedagogical Sutra-discipline wrapper — runs the full canonical sequence on one task |
| `/core:uninstall` | remove the plugin |

### Auto-governance (51 hooks across 6 events)

The plugin installs hooks that fire deterministically on every session — you don't invoke them, they just run:

- **SessionStart** (×7): banners, telemetry init, codex-directive sweep, inbox display, log rotation
- **PreToolUse** (×16): depth-marker check, blueprint check, build-layer check, RTK auto-rewrite, codex-directive gate, structural-move check, boundaries enforcement, key/env-var detection
- **PostToolUse** (×10): cascade-check (D13), estimation enforcement, artifact check, MCP compress, agent completion check, narration vs artifact check
- **PermissionRequest** (×1): meta-permission gate
- **UserPromptSubmit** (×4): codex-directive detect, feedback routing, **per-turn discipline reminder (D40 G1)**
- **Stop** (×13): telemetry flush, log triage, compliance tracker, context budget check, kill-switch state

## Quick start — try this

After `/core:start`, ask Claude something concrete to see the discipline in action:

```
Plan a small refactor of one file in this repo.
```

You should see:
- Input Routing block (TYPE: task / ROUTE: ...)
- Depth + Estimation block (DEPTH 2/5 or 3/5)
- BLUEPRINT (if tool calls planned)
- If Depth ≥ 3: a codex consult invocation
- Output Trace one-liner at the end

Or invoke the pedagogical wrapper to see ALL 8 steps explicitly:

```
/core:workflow Plan a small refactor of one file
```

## Full convention pack

See `SUTRA-DEFAULTS.md` (this plugin root) for the complete canon — every per-turn block, every kill-switch, every override path. The machine-readable schema is at `sutra-defaults.json` (consumed by hooks at runtime per D40 G6).

## Related

- `/core:status` — inspect install / queue / telemetry state
- `/core:update` — pull the latest plugin version
- `/core:uninstall` — remove Sutra
- `/core:depth-check` — manual depth marker before a big task
- `/core:learn` — interactive lessons on each Sutra primitive
- `/core:workflow` — see the full Sutra discipline applied to one task
