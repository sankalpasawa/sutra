# Sutra OS

Operating system for building with AI. One npx command deploys 30 governance hooks, 22 OS docs, and project templates into any Claude Code project folder.

## Install

```bash
npx -y github:sankalpasawa/sutra-os init
```

Run that inside any project folder. It creates `CLAUDE.md`, `TODO.md`, `os/`, and `.claude/hooks/sutra/`. After install, open Claude Code in the folder — every session is governed by Sutra automatically.

## What gets installed

```
your-project/
├── CLAUDE.md                    governance identity
├── TODO.md                      priority stack
├── SUTRA-CONFIG.md              tier, enforcement, depth defaults
├── os/
│   ├── STATUS.md, METRICS.md, OKRs.md
│   └── (governance artifacts)
├── .claude/
│   ├── settings.json            hook wiring
│   ├── hooks/sutra/             30 governance hooks
│   ├── os/                      22 governance docs
│   ├── commands/                /sutra, /sutra-onboard, /sutra-update, /sutra-help, /company
│   ├── logs/                    hook-fires.jsonl (per-turn telemetry)
│   └── sutra-version            pin
└── .enforcement/                block + override logs
```

## Update

Inside Claude Code: `/sutra-update`

Or manually:

```bash
npx -y github:sankalpasawa/sutra-os init
```

Re-running the installer preserves your content and refreshes Sutra-managed files only.

## Uninstall

```bash
npx -y github:sankalpasawa/sutra-os --uninstall
```

Removes Sutra's hooks, commands, settings-wiring, and OS docs. Leaves your own files + gstack + GSD untouched.

## Tiers

Default tier is `2` (product — full OS, 30 hooks, all governance docs). Lighter tier for governance-only installs:

```bash
npx -y github:sankalpasawa/sutra-os init --tier=1
```

| Tier | Name | What ships |
|---|---|---|
| 1 | governance | Boundary enforcement + SUTRA-CONFIG + feedback dirs only (minimal) |
| 2 | product (default) | Full OS: all hooks, all OS docs, all templates |
| 3 | platform | Same as 2 today; reserved for future protocol harvester |

## Common commands (after install + restart)

| Command | Purpose |
|---|---|
| `/sutra` | CEO day dashboard — activates Sutra mode, shows priorities/OKRs/status |
| `/sutra-onboard` | Guided onboarding for a new company |
| `/sutra-update` | Pull the latest Sutra OS |
| `/sutra-help` | Show all commands + current state |
| `/company NAME` | Open a company-scoped session |

## Update notifications

On SessionStart, Sutra checks for a newer version (rate-limited to once per 6 hours). If one exists, you'll see:

```
🧭 Sutra update available: v0.2.1 → v0.3.0
   To update: /sutra-update
```

No prompt if you're current. No prompt if offline.

## License

MIT.

## Status

v0.2.2 — deploy pipeline + enforcement + update-check. External install tested end-to-end.

## Issues

https://github.com/sankalpasawa/sutra-os/issues
