# Sutra outcome tests

Outside-in, feature-level tests. Each script exercises a user-facing outcome end-to-end: run the installer, invoke a hook, verify an artifact — the way an external user would experience Sutra.

## Why outcome tests (vs the unit tests in `../`)

| | Unit tests (`../test-d28-routing-gate.sh` etc.) | Outcome tests (this dir) |
|---|---|---|
| Perspective | "Does this function behave correctly?" | "Does the user see the right thing?" |
| Granularity | Per-hook, per-function | Per-feature, end-to-end |
| Runs against | Source code directly | The installed Sutra (via `npx`) |
| Stability goal | Prevent regressions | Prove the deployment pipeline works |

Outcome tests treat Sutra as a black box. Unit tests ensure the pieces work; outcome tests ensure the **promise** works.

## Running

```bash
# Default: pull the installer from github (what external users get)
bash run-all.sh

# Faster during development: use the local source
SUTRA_PACKAGE_DIR=/Users/abhishekasawa/Claude/asawa-holding/sutra/package bash run-all.sh

# Run one test
bash 01-install.sh
SUTRA_PACKAGE_DIR=... bash 01-install.sh
```

Each test writes to `/tmp/sutra-outcome-<testname>-<pid>/` and cleans up on success. Failures keep the dir so you can inspect.

## Layout

```
outcome/
├── lib/assert.sh          shared helpers (assert_eq, assert_file, assert_count, ...)
├── 01-install.sh          installer produces the right layout
├── 03-enforcement.sh      hooks block without markers, pass with
├── 10-leak-audit.sh       no brand leaks in user-visible surface
├── run-all.sh             runner
└── README.md              this
```

Numbered 01–10 so ordering is deterministic. Odd gaps (02, 04–09) reserved for Phase B coverage:
- `02-activation.sh` — `/sutra` command behavior
- `04-commands.sh` — `/sutra-help`, `/sutra-update`, `/sutra-onboard`
- `05-update.sh` — update-check + re-install flow
- `06-logging.sh` — log file formats + rotation
- `07-subagent.sh` — subagent inheritance proxy test
- `08-uninstall.sh` — `--uninstall` preserves user files
- `09-portability.sh` — runs cleanly in fresh `/tmp/` with zero asawa-holding context

## Exit codes

- `0` — all tests passed
- `N` — `N` test files had failures

## Adding a new test

1. Copy an existing script (e.g., `01-install.sh`) to `NN-<name>.sh`.
2. Set `TEST_NAME` to match filename.
3. Write assertions using helpers from `lib/assert.sh`.
4. Ensure each script creates its own `/tmp/sutra-outcome-*-$$/` dir and cleans up on success.
5. Run it locally: `bash NN-<name>.sh`.
6. Add to the list above.

## What these tests do NOT cover

- LLM response quality (can't unit-test an LLM)
- Live Claude Code session behavior with subagents (needs interactive runtime — use `claude --print` for scripted subsets)
- Network failure modes (GitHub down, npm slow)
- Cross-platform (bash-only)

For those, rely on founder dogfood sessions + GitHub Issues + monitoring of `.claude/logs/hook-fires.jsonl`.
