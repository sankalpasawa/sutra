# Sutra — the operating system for AI-native companies

Claude Code gives you a brilliant agent. Sutra makes it a **Chief of Staff**: governance,
memory, per-turn discipline, and a fleet feedback loop — so one founder can run many
companies through the same operating system, and every company running it makes the
canon better for all of them.

## Get started (60 seconds)

```bash
curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash
```

Then in any project: `cd your/project && claude` → `/core:start`.
The story, pillars, and hardstops: **[sutra-os website](https://sutra-os.vercel.app)**.

## Desktop app (optional)

Sutra also ships a macOS desktop app — the placement registry (departments, charters,
placements) with a Claude chat panel, terminal, git diff and file editor beside it. It
drives your local `claude` CLI, so it **bills as your existing subscription, never the
API**.

```bash
cd marketplace/plugin/sutra-ui && ./install.sh
```

```bash
open -a Sutra
```

The installer builds a real Electron app at `/Applications/Sutra.app` (it runs
`npm install` for you on first run) and a `sutra-ui` CLI that serves on a free port.
Re-run `./install.sh` to update; `./install.sh --uninstall` removes both.

macOS only today, and it needs the `claude` CLI already logged in. Full details —
permission modes, the workdir picker, the gated editor, what each pane reads —
are in **[`marketplace/plugin/sutra-ui/README.md`](marketplace/plugin/sutra-ui/README.md)**.

## What is Native?

Native is Sutra rebuilt as a **real engine** — deterministic workflows and the Work-Atom
primitive — instead of prompt discipline inside Claude Code. It is the productization of
everything the plugin has proven in production.

> **Canon note:** Native runtime details are canonical in
> [`os/engines/NATIVE-ENGINE.md`](os/engines/NATIVE-ENGINE.md) and the ADRs in
> [`os/decisions/`](os/decisions/). If anything in this README conflicts with those, the
> canon docs win. Orientation index: [`os/native/README.md`](os/native/README.md).

## What is Sankalp actually doing?

The question everyone asks — answered by behavior, not title.

- **Daily loop**: discover what Claude Code can newly do → understand it → fold it into
  Sutra (plugin + canon) → keep Sutra a 1:1 map on top of Claude Code as it evolves.
- **Proof**: every capability is dogfooded across his own portfolio — six owned products,
  two client projects, one holding company — before it ships to the fleet.
- **Goal**: make running a company with AI an *installable discipline* — one command gives
  a founder the governance, memory, and operating loop that today exist only as practice.
- **Short term**: ship Native v1 while the plugin keeps proving the canon in production.
- **Deliberately not done yet**: pricing, self-serve onboarding, revenue from the OS itself.

The full question-by-question ledger — strategic, commercial, tactical, and the honest
OPEN items — lives in **[CLARITY.md](CLARITY.md)**.

## Map of this repo

| Path | What it is |
|---|---|
| `marketplace/plugin/` | The shipping Sutra plugin (skills, hooks, governance) |
| `marketplace/plugin/sutra-ui/` | The macOS desktop app — registry, chat, terminal, git, editor |
| `os/engines/NATIVE-ENGINE.md` | Native's canonical charter (source of truth) |
| `os/decisions/` | ADRs — decision rationale of record |
| `os/native/` | Native canon, one part-file per concern ([index](os/native/README.md)) |
| `os/charters/` | Cross-cutting charters (tokens, speed, permissions) |
| `website/` | The sutra-os story page |
| `CLARITY.md` | Pitch ledger: every "what are you doing?" question, answered or OPEN |
| `CATALOG.md` · `VISION.md` · `PRODUCT-VISION.md` | Product vision + typed catalog |
