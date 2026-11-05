# GAP-DOCS as built: getting started, operations, environment, troubleshooting and a doc checker (G16)

Built: `docs/GETTING-STARTED.md`, `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/ENVIRONMENT.md`, `scripts/check_docs.py`, `tests/test_docs.py` (71 tests, about 4 s).
No existing test or source file was changed. The spec lists no Transfers for this package, so none were taken.

## What the checker enforces (`scripts/py scripts/check_docs.py`, exit 1 with `::error::` lines)
- **Commands.** Every `sutra-pro ...`, `python -m sutra_app ...` or `scripts/run.sh ...` in a code block or code span must name a real command (walked in the real
  `argparse` tree of `ops.cli.build_parser` and `main.build_parser`) and every `--flag` must be in the real `--help` output of that command. A table row
  whose first cell is a command is checked against the flags in its other cells. Placeholders (`[serve]`, `<x>`) and arguments after a leaf command are not commands.
- **Coverage.** The other way: every leaf command and every flag of it must be written down in the four documents, so a new flag fails the gate until documented.
- **Environment.** A row `| `NAME` | ...` is required for every name of `config.ENV_NAMES`, of `EngineSettings` (`engine.spec.ENV_NAMES`), `J2_OVERRIDE_KEY`, the
  five `J2_SMTP_*`, `SUTRA_BROWSER_APP`, the model names and every `SUTRA_*` name found in `sutra_app/**/*.py`, `scripts/macos/launcher.sh` and
  `scripts/build_macos_app.py`. The field, default, Locked and Task cells are compared with the code (defaults of computed fields are skipped).
- **Failures.** One `### F<n>` per row of the failure table of `docs/design/orchestrator.md` 5.7, one `### Doctor: `id`` per `doctor.CHECK_IDS`, one table row per API
  error code (HTTP status compared with `STATUS_BY_CODE`) and per connector error code (kind compared with `ERROR_CLASSES`).
- **Links.** Relative links must exist; a `#anchor` into a Markdown file must be one of its headings (GitHub slug rule). Scanned: the four documents, plus `README.md`
  and `docs/DESIGN.md` when present (commands and links only).

## Decisions
- Documents are tables the checker can read, on purpose: a prose-only document cannot be proved. The three tables of ENVIRONMENT.md (app, engine, secrets) are the contract.
- The sizes in OPERATIONS.md were measured: a fresh offline data folder is 0.8 MB, the seeded library 0.5 MB, one offline (mock) run folder 80 KB, one backup of that 0.06 MB.
  Real runs with screenshots are larger; no real-run size is claimed (GAP-LIVE can measure one, D93).
- `J2_*` variables of the server's own environment are documented as NOT reaching a run (the launcher passes the seven task keys only); the way in is `engine.json`.
- The error-code tables repeat the one-line meaning from `connectors/errors.py` and `orchestrator/errors.py`; wording is mine, codes and statuses are proved.
- `sutra-pro stop` is documented as the way to stop the app; stopping one run is documented as answering `stop` when the team offers it (J2's choice list), because no UI
  button for `POST /api/tasks/{id}/stop` was found in the pages. Not claimed beyond that.

## Known limits
- Prose claims (what a card means, what a ring colour is) are checked only by review: the graph legend and the atom state words were copied from `graph_view.js` and
  `fnode_view.js`; a change there is not detected.
- The checker imports the app (`ops.cli`, `config`, `engine.spec`, `connectors`), so it needs the project's virtualenv: run it with `scripts/py`.
- The `--help` text of `sutra-pro` itself still lists only "doctor, status, stop, config and open" (GAP-OPS-1's `main.py`); the documents list all nine commands.
- Anchors of a link into a non-Markdown file are not checked.

## Needs (chassis edits by the scheduler, by hand)
- `README.md`: five lines of what it is, install from a checkout (`scripts/run.sh`) and from a release, `sutra-pro doctor`, `sutra-pro`, where data lives
  (`~/.sutra-pro`, `./data` in a checkout), and links to `docs/GETTING-STARTED.md`, `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/ENVIRONMENT.md`.
  Once it has them, `check_docs.py` checks its commands and links with the others.
- `docs/DESIGN.md` overview and `docs/TRACEABILITY.md` / `traceability.json` are outside this package's owned paths (GAP-TRACE generates the matrix).
- `sutra_app/main.py` help text: name all nine commands (backup, restore, prune, export were added after the text was written).

## Mutation check (one pass, copy in /tmp)
14 breakages of `check_docs.py` (flag membership, unknown-command branch, coverage flags, float default, locked and task flags, status and kind compare, failure regex, anchor
check, pipe operator, fence toggle, Python-constant exclusion, link base folder): all 14 killed, no survivor.
