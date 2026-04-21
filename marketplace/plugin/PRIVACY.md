# Privacy — What Sutra Plugin Collects (and What It Doesn't)

*Version: plugin v1.3.1 · Updated: 2026-04-21 · License: MIT*

## Default behavior

**By default, Sutra collects nothing that leaves your machine.**

The plugin ships with `telemetry_optin = false` in `.claude/sutra-project.json` when you run `/sutra:onboard`. In that state:

- No network calls
- No git pushes
- All metrics queued locally to `~/.sutra/metrics-queue.jsonl` and never transmitted

## If you opt in (via `/sutra:go` or manual edit)

`telemetry_optin = true` enables transmission. On every Claude Code session `Stop` event, the plugin fire-and-forgets a push to `sankalpasawa/sutra-data` (a private GitHub repo). Push fails silently if you don't have SSH write access to that repo — your session never blocks.

### What data is in the push

Machine-validated against `.claude-plugin/SCHEMA.md` before it leaves your machine:

| Field | Example | Why |
|---|---|---|
| `install_id` | `9cee17981d3fbe86` | SHA-256 of `HOME + sutra_version`, first 16 chars. Stable per user+version; changes on version bump. |
| `project_id` | `6342ecbf23f85e` | SHA-256 of normalized git remote URL (or cwd+USER fallback), first 12 chars. Stable per repo. |
| `sutra_version` | `1.3.1` | For cohorting by plugin version. |
| `tier` | `0` | Operator tier (0 = unknown for external users). |
| `dept` | `os_health` | Enum: os_health, estimation, velocity, cost, quality, portfolio, knowledge, governance, sessions. |
| `metric` | `queue_depth_at_stop` | Snake-case machine-validated identifier. |
| `value` | `42` | Number only. Strings in value field are rejected (exit 4). |
| `unit` | `count` | Enum: count, pct, tokens, ratio, ms, bytes, number. |
| `window` | `lifetime` | Enum: instant, 24h, 7d, lifetime. |
| `ts` | `1776782035` | Unix seconds. |

### What data is NEVER transmitted

Regex-rejected at the emit layer:

- File paths (absolute or relative)
- Prompt content (anything a user typed)
- Task slugs if they contain project-specific words
- Email addresses
- GitHub handles
- Anything containing `/Users/`, `/home/`, or `C:\`
- Company names in free-text fields

Any string field that fails the PII check causes `emit-metric.sh` to exit 4 and skip the row.

## Layer A estimation events (not transmitted in v1)

The estimation log at `.claude/sutra-estimation.log` stays local. It may contain task slugs you wrote. v1 does not transmit these. v2 (Supabase transport) will add an opt-in for aggregated Layer A → Layer B rollup so you can see charter compliance stats without raw event content leaving your machine.

## Third-party destinations

None. The plugin does not talk to analytics vendors, error reporters, or third-party APIs. The only outbound destination is the private GitHub repo you've explicitly opted into.

## Rotation / retention

- Local queue rotates at 10k lines to `~/.sutra/metrics-queue.*.bak`.
- Pushed files in `sutra-data` are immutable per-push JSONL files; never rewritten. Retention is controlled by the data store operator (not the plugin).

## Disabling or uninstalling

- **Disable telemetry**: edit `.claude/sutra-project.json` → `"telemetry_optin": false`. Effect is immediate.
- **Clear local queue**: `rm ~/.sutra/metrics-queue.jsonl`
- **Full factory reset** (if shell helpers are installed): `sutra-reset`
- **Plugin uninstall**: `claude plugin uninstall sutra@sutra` — removes the plugin; `~/.sutra/` is preserved unless you also run `rm -rf ~/.sutra`.

## Roadmap (what this may change in v2)

- **Supabase transport**: enables external users (without GitHub write access) to push telemetry via anonymous RLS-gated write. Opt-in will remain default-off.
- **Install funnel event**: a single anonymous "install_completed" ping on first onboard — currently NOT shipped; local-only.
- **Consent UI**: explicit in-session prompt before first transmission with link to this document.

## Questions

- Open an issue: <https://github.com/sankalpasawa/sutra/issues>
- Code paths: `hooks/emit-metric.sh` (emit layer), `scripts/push.sh` (transport), `ARCHITECTURE.yaml` § privacy (machine spec)
