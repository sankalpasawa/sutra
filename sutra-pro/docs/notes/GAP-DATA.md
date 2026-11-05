# GAP-DATA as built: backup, restore, pre-upgrade backup, export, prune (G13)

Built: `sutra_app/ops/{backup,retention,exporter}.py` (each has `register(sub)`, picked up by `cli.build_parser()`; `backup.before_upgrade` is picked up by `cli.before_start`).
Tests: `tests/ops/test_{backup,retention,exporter}.py`, 109 tests in about 8 s (backup 44 incl. the live-app round trip, retention 42, exporter 23).
Changed an existing test (intended behaviour change, not weakened): `tests/ops/test_cli.py::test_modules_of_other_packages_register_commands_and_a_missing_one_is_skipped`
now simulates the absence of `ops.backup` (the real module exists), the assertions are the same.

## What it does
- `backup [--to DIR] [--no-runs]`: `sutra-pro-backup-<UTC>.tar.gz`, mode 0600, `MANIFEST.json` last (format 1, app version, `user_version`, time, path/size/sha256 per file).
  DB through `sqlite3.Connection.backup()` from a read-only connection (WAL rows included, tested with an open writer). Each file is copied to a scratch file, hashed and archived from the copy.
  Never `.env`, `app.lock`, `app.pid`, `logs/`; `--include-env` prints the reason and exits 2. Rotation keeps the newest 7 `sutra-pro-backup-*.tar.gz` of the DEFAULT folder only.
- `restore FILE`: lock must be free (it is held through the swap), manifest format and `user_version` checked, every member a plain file listed in the manifest with matching size and
  sha256, staged in `<data>.restore-<UTC>`, `PRAGMA integrity_check` and `user_version` of the staged DB, then `<data>` -> `<data>.before-restore-<UTC>` and staging -> `<data>`.
  `backups/` is moved and `.env` copied from the old folder into the new one. A failed stage removes only its own staging folder. An older database version is accepted.
- `before_upgrade(settings)`: `pre-upgrade-v<old>-to-v<new>.sqlite3` (database only, 0600, replaced if it exists) when `PRAGMA user_version` < `schema.SCHEMA_VERSION`; failure raises `BackupError`
  whose text is a doctor line (`[FAIL] ... -> fix: ...`), which `main._serve` prints as "cannot start" (exit 1).
- `export chart|team DEPT|usage --csv`: see the module docstring. Read-only (a test hashes the whole data folder before and after). Never overwrites a file or a non-empty folder.
- `prune [--older-than 90d] [--dry-run] [--yes]`: terminal tasks (done, done_with_open_items, stopped, crashed, cancelled) older than the age; per spec files only; prints the
  row counts and sizes of `atom_ledger` and `usage_ledger`; `VACUUM` only with `--yes`, holding the instance lock, skipped with a reason when the server runs.

## Decisions and deviations
- Rotation applies to the default `<data>/backups/` only; `--to DIR` is the owner's own copy and is never rotated (the spec's "automatic backups" has no other meaning). `pre-upgrade-*.sqlite3` is never rotated or pruned.
- `export team` charter: `goal.json` lives in the run folder, not the department folder, so `goal.json` and `goal.v<N>.json` come from the last finished run (done or done_with_open_items, newest end time).
  "documents" = `documents.json`, `artifacts.json`, `artifacts/` and the document files inside `site/`; `site/shots/` is left out (screenshots are evidence, not deliverables).
  Layout is flat (`goal.json`, `summary.json`, `site/`, `atom-ledger.jsonl`, `EXPORT.json`). Atom log rows are those whose node (`graph_nodes.department_id`) or atom (`atoms.department_id`) belongs to the team.
- `export chart`: change 1 stores the seed `OrgChart` in `chart_changes.body`, not a `ChartChange`; it is exported with `change: null` and `seed_chart`. Both models are validated, a bad row stops the export.
- `export usage` takes `--csv` (required; the only format); times as UTC ISO; `--out -` prints to standard output for chart and usage.
- prune's "finished" includes crashed/stopped/cancelled runs (their evidence is just as bulky); the `events_offset == size` rule keeps events the server has not projected. Screenshots = `site/shots/**`, `screenshots/**`, `*.png` directly in the run folder (a `site/*.png` is a site asset and stays).
- `before_upgrade` returns without error when the database cannot be read (the app's own start-up reports that) and when the file is newer than this build.
- Restore of a data folder that does not exist yet needs no lock and makes no `.before-restore` folder.

## Known limits
- Backup of a live server is consistent for the database; run files are copied one by one, so a file written during the copy is a prefix of itself (the manifest matches the archive, not a later state).
- A run pruned of `trace.jsonl`/`events.jsonl` cannot be replayed from them; follow-ups seed from the other records (rehydrate skips those host files anyway).
- No pre-upgrade backup rotation; there is one file per schema step. The CSV is not escaped against spreadsheet formulas (values are app-made).
- `restore` does not check free disk space; staging needs about the archive's unpacked size next to the data folder.

## Follow-ups for other packages
- GAP-DOCS: document the five commands and the exit codes (0 ok, 1 refused/problem, 2 usage). `sutra_app/main.py` `--help` text still lists only "doctor, status, stop, config and open" (GAP-OPS-1 file).
- Chassis: README could name `sutra-pro backup` before upgrading by hand.

## Mutation check (one pass, copy in /tmp)
19 breakages (log age, newer-version check, sha check, pre-upgrade comparison, file mode, `--to` rotation, lock check on restore, keep count, carry-over of backups/, events rule, finished set,
age direction, vacuum lock, last-run order, shots excluded, ledger OR, overwrite guard, old-log filter, `--no-runs`): all 19 killed, no survivor.
