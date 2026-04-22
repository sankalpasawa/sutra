# Sutra Core

Operating system for building with AI. Governance + observability for Claude Code sessions.

**v1.7.1** — MIT license · `core@sutra` in the Claude Code marketplace

## What you get

- **Input routing** — every user message classified (direction / task / feedback / question) before any tool use
- **Depth + estimation** — every task rated 1-5 with cost/effort estimate before work begins
- **Readability gate** — outputs formatted as tables/boxes/metrics, not prose
- **Output trace** — every response ends with a one-line OS trace
- **Session retrieve** — recover abruptly-closed sessions after a laptop crash
- **RTK auto-rewrite** — PreToolUse hook forces `rtk` wrap on voluminous bash (`git status`/`log`/`diff`/`blame`/`show`) for 30-60% tool-output reduction
- **MCP output compression** — PostToolUse hook replaces large MCP tool outputs (≥4KB, ≥80 lines) with head+error+tail summaries (~50% cut)
- **Per-profile enforcement** — `individual` / `project` / `company` profiles via `/core:start --profile` (v1.6.0+); `company` hard-blocks on missing depth markers
- **Local telemetry** — `~/.sutra/metrics-queue.jsonl`; opt-in push to a data store

## Install (60 seconds)

```bash
# 1. Register the marketplace
claude plugin marketplace add sankalpasawa/sutra

# 2. Install the plugin
claude plugin install core@sutra
```

Then in any Claude Code session:

```
/core:start
```

That's it. One command activates everything.

## Every command

Inside Claude Code (slash commands):

| Command | Purpose |
|---|---|
| `/core:start` | The one command. Onboard + activate + depth marker. Accepts `--profile individual\|project\|company` (v1.6.0+). |
| `/core:status` | Install ID, project ID, queue depth, telemetry flag, active profile. |
| `/core:update` | Pull the latest plugin version. |
| `/core:uninstall` | Remove the plugin. `--purge` also wipes `~/.sutra/`. |
| `/core:permissions` | Print a paste-ready allowlist for `.claude/settings.local.json`. |
| `/core:depth-check` | Manual depth marker for the next task. |

From your terminal (bare command, no prefix):

```
sutra help
sutra start
sutra status
sutra update
sutra uninstall
```

## Platform support

| Platform | Skills + Commands | Hooks (bash) | Telemetry |
|---|---|---|---|
| macOS terminal | ✅ Full | ✅ Full | ✅ Full |
| macOS desktop app | ✅ Full | ✅ Full | ✅ Full |
| Linux terminal | ✅ Full | ✅ Full | ✅ Full |
| VS Code / JetBrains (Mac/Linux) | ✅ Full | ✅ Full | ✅ Full |
| Windows (native) | ✅ Full | ❌ no-op | ❌ no-op |
| Windows via **WSL2** | ✅ Full | ✅ Full | ✅ Full |
| Claude Code web app | ✅ Full | ⚠ sandboxed | ⚠ sandboxed |

### Windows users — use WSL2

The plugin's enforcement hooks are bash scripts. On Windows, run Claude Code from inside WSL2 and everything works identically to macOS/Linux.

```powershell
# 1. Install WSL2 (one-time, run in PowerShell as Administrator)
wsl --install

# 2. After WSL2 installs + reboots, open an Ubuntu terminal and:
curl -fsSL https://claude.ai/install.sh | bash
claude plugin marketplace add sankalpasawa/sutra
claude plugin install core@sutra
claude
# Inside Claude Code:
/core:start
```

Without WSL2, the skills and slash commands still work — you just lose the automatic governance hooks and telemetry. Acceptable for a trial; recommend WSL2 for real use.

A Node-based rewrite of the hooks (removing the bash dependency) is on the roadmap.

## Privacy

See [PRIVACY.md](PRIVACY.md). Short version: plugin install collects nothing. `/core:start` enables telemetry by default; flip `"telemetry_optin": false` in `.claude/sutra-project.json` to disable.

## Permissions

See [PERMISSIONS.md](PERMISSIONS.md). Run `/core:permissions` inside Claude Code for the paste-ready allowlist.

## Versioning

See [VERSIONING.md](VERSIONING.md). SemVer. Plugin auto-updates on session start for public marketplaces like ours.

## Architecture

See [ARCHITECTURE.yaml](ARCHITECTURE.yaml) — structured YAML with components, flows, identities, privacy matrix. Any LLM can render visuals on demand from it (never persist ASCII art — it goes stale).

## License

MIT.

## Issues / feedback

<https://github.com/sankalpasawa/sutra/issues>
