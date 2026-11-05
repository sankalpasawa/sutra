# Sutra Pro

A new app (no relation to the old sutra-ui; the design is the J2 prototype's). You chat with Sutra; one global org chart of
departments and divisions grows and reshapes with each request. Every department runs the five J2 functions (Identity,
Adaptation, Priority, Coordination, Audit) as agentic graph nodes that work in atoms: a goal, constraints, context, one unit of
work and a verify step that has the teeth. Model calls go through a connector layer with a Claude connector and a Codex
connector (CLI first, your own logins, never an API key). Everything runs on your computer and listens on 127.0.0.1 only.

This folder lives in the Sutra repository ([sankalpasawa/sutra](https://github.com/sankalpasawa/sutra)) beside the older Sutra product, which it does
not touch (D98). Its workflows are the `.github/workflows/sutra-pro-*.yml` files at the root of the repository.

- Architecture diagram (published, version 8): https://claude.ai/artifact/HweydYv8jVVoZBA9SkuxVB
- Design in one page: [docs/DESIGN.md](docs/DESIGN.md); the five sections are in [docs/design/](docs/design/)
- Every decision with its why and what was rejected: [docs/DECISIONS.md](docs/DECISIONS.md)
- Rule, step, endpoint and decision to module and test: [docs/TRACEABILITY.md](docs/TRACEABILITY.md)

## Download the app

Releases are tagged `sutra-pro-vX.Y.Z` and are never the repository's "Latest" release (that belongs to the older product, D100), so the links name the tag:
see [all Sutra Pro releases](https://github.com/sankalpasawa/sutra/releases?q=sutra-pro).

| System | Download | Notes |
|---|---|---|
| macOS 13 or newer, Apple silicon | `Sutra-Pro-arm64.dmg` | open it, drag **Sutra Pro** onto Applications ([details](docs/RELEASE-macos.md)) |
| macOS 13 or newer, Intel | `Sutra-Pro-x86_64.dmg` | the same |
| Windows 10 and 11, 64-bit | `Sutra-Pro-Setup-x64.exe` (installer) or `Sutra-Pro-win-x64.zip` (portable) | per user, no administrator rights ([details](docs/RELEASE-windows.md)) |

```
https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.2.0/Sutra-Pro-arm64.dmg
```

The Mac app is signed with a Developer ID and notarized by Apple; the Windows files are not signed yet (D102), so SmartScreen says "Windows protected your PC" the
first time (More info, Run anyway). Every file has a `.sha256` next to it. The apps are **desktop apps** (D105): an Electron window around the local server, which
runs on a Python that ships inside the app; closing the window stops it. The logo is the old Sutra's (D106).

## Install and run from the command line

You need [uv](https://docs.astral.sh/uv/) and Python 3.11. For real work you also need the Claude CLI and the Codex CLI, signed
in with your subscriptions; `sutra-pro doctor` tells you what is missing.

```bash
uv tool install https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-v0.2.0/sutra_pro-0.2.0-py3-none-any.whl
sutra-pro doctor                   # checks Python, the data folder, the database, both CLIs, Chrome, the port
sutra-pro                          # starts the app and opens Chrome at http://127.0.0.1:8780/
sutra-pro --offline                # a demo with no model and no login: a message creates a team and a mock run finishes
sutra-pro stop                     # stops the running app
```

From a checkout, `sh scripts/install_local.sh` builds the wheel, checks it, installs `sutra-pro` with `uv tool`, and proves the installed copy works.

Your data (database, departments, runs, logs, backups) lives in `~/.sutra-pro` (`SUTRA_DATA_DIR` or `--data-dir` change it).
One app runs per data folder. `sutra-pro backup`, `restore`, `export` and `prune` look after the data; `sutra-pro config`
shows and sets the locked engine settings. Remove the command with `sh scripts/uninstall_local.sh` (your data stays).

More: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md), [docs/OPERATIONS.md](docs/OPERATIONS.md),
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Develop

From this folder (`sutra-pro/` of a checkout of the Sutra repository):

```bash
uv venv .venv --python 3.11 && uv pip install -e ".[dev]"
scripts/gate.sh                    # the merge gate: the whole Python suite and the node tests
sh scripts/run.sh                  # run from the checkout (creates the venv when it is missing)
```

Work happens on ordinary branches of the Sutra repository, gated by the `sutra-pro-ci` workflow (Linux, macOS and Windows) for any change under
`sutra-pro/`. The 62 work packages of the first build (`docs/BUILD-PLAN.md`) were merged in a repository of their own before the move; the worktree
helper `scripts/wt.sh` is retired (D98). Opt-in suites: `SUTRA_SLOW=1` (long engine suites), `SUTRA_BROWSER=1` (headless Chrome walks of the real app),
`SUTRA_LIVE=1` (the real CLIs; `scripts/live_smoke.py --max-usd 5` is the live smoke test and spends subscription quota).

The desktop app's window is in [desktop/](desktop/README.md) (`cd desktop && npm ci && npm start` runs it on this checkout's Python).

Releases (the wheel, the Mac DMGs, the Windows installer and zip) come from one tag and are built by CI only: [docs/RELEASE.md](docs/RELEASE.md),
[docs/RELEASE-macos.md](docs/RELEASE-macos.md), [docs/RELEASE-windows.md](docs/RELEASE-windows.md).

The repository's ownership audit (D69) applies to this folder: no personal identifier in any file, `~` for a home folder (D99).
Nothing here edits the older product's files.
