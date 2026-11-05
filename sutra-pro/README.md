# Sutra Pro

A new app (no relation to the old sutra-ui; the design is the J2 prototype's). You chat with Sutra; one global org chart of
departments and divisions grows and reshapes with each request. Every department runs the five J2 functions (Identity,
Adaptation, Priority, Coordination, Audit) as agentic graph nodes that work in atoms: a goal, constraints, context, one unit of
work and a verify step that has the teeth. Model calls go through a connector layer with a Claude connector and a Codex
connector (CLI first, your own logins, never an API key). Everything runs on your Mac and listens on 127.0.0.1 only.

- Architecture diagram (published, version 6): https://claude.ai/artifact/HweydYv8jVVoZBA9SkuxVB
- Design in one page: [docs/DESIGN.md](docs/DESIGN.md); the five sections are in [docs/design/](docs/design/)
- Every decision with its why and what was rejected: [docs/DECISIONS.md](docs/DECISIONS.md)
- Rule, step, endpoint and decision to module and test: [docs/TRACEABILITY.md](docs/TRACEABILITY.md)

## Install and run

You need [uv](https://docs.astral.sh/uv/) and Python 3.11. For real work you also need the Claude CLI and the Codex CLI, signed
in with your subscriptions; `sutra-pro doctor` tells you what is missing.

```bash
sh scripts/install_local.sh        # builds the wheel, checks it, installs `sutra-pro` with `uv tool`, and proves the installed copy works
sutra-pro doctor                   # checks Python, the data folder, the database, both CLIs, Chrome, the port
sutra-pro                          # starts the app and opens Chrome at http://127.0.0.1:8780/
sutra-pro --offline                # a demo with no model and no login: a message creates a team and a mock run finishes
sutra-pro stop                     # stops the running app
```

Your data (database, departments, runs, logs, backups) lives in `~/.sutra-pro` (`SUTRA_DATA_DIR` or `--data-dir` change it).
One app runs per data folder. `sutra-pro backup`, `restore`, `export` and `prune` look after the data; `sutra-pro config`
shows and sets the locked engine settings. Remove the app with `sh scripts/uninstall_local.sh` (your data stays).

More: [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md), [docs/OPERATIONS.md](docs/OPERATIONS.md),
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md), [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Develop

```bash
uv venv .venv --python 3.11 && uv pip install --python .venv/bin/python -e ".[dev]"
scripts/gate.sh                    # the merge gate: the whole Python suite and the node tests
sh scripts/run.sh                  # run from the checkout (creates the venv when it is missing)
```

Work happens in packages (`docs/BUILD-PLAN.md`), one branch and worktree each, merged by `scripts/wt.sh merge <id>` through
the gate. Opt-in suites: `SUTRA_SLOW=1` (long engine suites), `SUTRA_BROWSER=1` (headless Chrome walks of the real app),
`SUTRA_LIVE=1` (the real CLIs; `scripts/live_smoke.py --max-usd 5` is the live smoke test and spends subscription quota).
Releases (a wheel and a macOS app) are described in [docs/RELEASE.md](docs/RELEASE.md) and [docs/RELEASE-macos.md](docs/RELEASE-macos.md).

The old Sutra repository and the J2 prototype are read-only sources: nothing here writes to them. Nothing is pushed anywhere
until the owner says so.
