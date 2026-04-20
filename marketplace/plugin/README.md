# Sutra

Operating system for building with AI. Governance + observability for Claude Code sessions.

## What you get

- **Input routing** — every user message classified (direction / task / feedback / question) before any tool use
- **Depth + estimation** — every task rated 1-5 with cost/effort estimate before work begins
- **Readability gate** — outputs formatted as tables/boxes/metrics, not prose
- **Output trace** — every response ends with a one-line OS trace
- **Auto-emission observability** — every session-stop emits 3 metrics, auto-pushed to your Sutra data store
- **Shell helpers** — one-word commands (`sutra-go`, `sutra-reset`) from any terminal

## Install (new users, zero state)

```bash
# 1. Register the marketplace
claude plugin marketplace add sankalpasawa/sutra

# 2. Install the plugin
claude plugin install sutra@sutra

# 3. Install shell helpers (one-time, appends to ~/.zshrc or ~/.bashrc)
bash ~/.claude/plugins/cache/sutra/sutra/*/scripts/install-shell-helpers.sh
source ~/.zshrc   # or ~/.bashrc

# Done. Now anywhere:
sutra-go
```

`sutra-go` creates a fresh temp project, deploys Sutra with telemetry ON, and opens Claude. One word.

## Usage inside Claude

```
/sutra:sutra-go         — onboard current dir + enable telemetry (one-shot)
/sutra:sutra-onboard    — onboard only (telemetry default off)
/sutra:sutra-status     — show install_id / project_id / queue depth / last flush
/sutra:sutra-push       — manual push (normally unnecessary — auto-push runs on Stop)
/sutra:depth-check      — check depth marker
/sutra:sutra            — session activation banner
```

## Shell commands (after running `install-shell-helpers.sh`)

| Command | Purpose |
|---|---|
| `sutra-go` | Fresh dir + deploy + telemetry ON + open Claude |
| `sutra-uninstall` | Remove plugin + marketplace (keep data) |
| `sutra-reset` | Full factory reset — plugin + data + cache |
| `sutra-status-global` | Check install + queue state from any terminal |

## Telemetry + privacy

- Default when onboarding via `/sutra:sutra-onboard`: **opt-in FALSE** (privacy default)
- Default when onboarding via `/sutra:sutra-go` or `sutra-go`: **opt-in TRUE** (observability default)
- Auto-push on Stop (v1.1.3+): if opt-in is true, queue ships to your data store asynchronously on every session end
- Data store: `sankalpasawa/sutra-data` (PRIVATE) — you're the only one with write access unless you distribute tokens
- Schema: `.claude-plugin/SCHEMA.md` in the data repo — PII-rejected at the emit layer + validated in CI on every push

## Architecture

Source of truth: `ARCHITECTURE.yaml` — structured YAML with components, flows, identities, privacy matrix. Any LLM can render visuals on demand from it (never persist ASCII art — it goes stale).

## License

MIT.

## Status

v1.1.4 — auto-emission + auto-push + shell installer. Production-ready for portfolio use. External distribution needs Supabase transport (v2).
