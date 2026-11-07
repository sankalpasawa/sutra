# QA ops-cli: four bugs from the QA pass on 2ae63d11

Branch `feat/sutra-pro-qa-ops-cli` (from 2ae63d11), work only in `sutra-pro/`. Each bug was reproduced first (QA's scratch folder was copied, never written),
fixed at its cause, and given tests that fail on the old code and pass on the new. J2 engine files were not touched.

| # | Bug | Severity | Result |
|---|-----|----------|--------|
| 1 | backup of a corrupt database "succeeds", every kept backup fails restore, rotation deletes the good ones; doctor says Database ok | P1 | fixed |
| 2 | `import-old-chats --apply` dies with a traceback on a numeric id, a lone surrogate or a pre-1970 time; reruns die at the same chat | P2 | fixed |
| 3 | `import-old-chats --apply` makes a missing data folder 0755 | P2 | fixed |
| 4 | UNVERIFIED: `restore` over an existing folder fails on Windows (open lock inside the renamed folder) | P2 | fixed from the code, not run on Windows |

## 1. A damaged database was backed up, then rotated the good backups away

**Reproduced.** A data folder with a few 200-byte stretches of 0xFF written into `db.sqlite3` past its first page: `doctor --offline` printed
`[ ok ] Database: schema version 3`; `backup` wrote an archive and exited 0; `restore` of it failed `PRAGMA integrity_check`.

**Root cause.** `snapshot_database` uses `Connection.backup()`, which copies pages without reading them, so a damaged file copies "successfully".
`create_backup` then archived it and `prune_backups` (newest 7, by count) kept it. `doctor._check_database` read only `user_version` and
`sqlite_master`, which live on page 1 and survive damage elsewhere. Restore already ran `integrity_check`, so the first sign of trouble came at the
worst moment.

**Fix.** `backup.integrity_problem(conn)` is the one test (restore's own pragma): it returns None for `ok`, else one line of findings; SQLite either lists
findings or fails the pragma itself ("database disk image is malformed"), both come back as text; busy and other errors are raised, not called damage.
`create_backup` runs it on the scratch copy straight after the snapshot and raises `BackupError` (exit 1) before anything is archived or rotated, for the
default folder and for `--to` alike. The message says nothing was written, why, and points at `sutra-pro restore` and `doctor`. `doctor`'s database
check fails with a fix that names restore. `docs/OPERATIONS.md` says so.

**Tests.** `tests/ops/test_backup.py`: damaged database refused with the reason, no archive/`.part`/scratch left (default folder and `--to`); 7 good
backups survive 8 refused attempts and the newest still restores; the command exits 1 with the sentence; `integrity_problem` unit test. `tests/ops/test_doctor.py`:
a damaged file is a `fail` with a fix and the report is not ok. Before the fix the first test failed with "DID NOT RAISE".

**Not changed, on purpose.**
- Backups already in a folder from older versions stay as they are; `restore` verifies at restore time. Verifying every archive at rotation time would open each one.
- `before_upgrade` (the pre-upgrade copy) still copies whatever is there; a damaged database fails the app's own start-up.
- `export chart` and `prune` on a damaged database (QA saw `export` "succeed", `prune` refuse) were not in the expected behaviour and are left alone.
- Cost: a backup now reads the whole database copy once more (an integrity check), and the doctor does the same on every run; the running server's doctor panel
  caches its answer for 30 s, so a very large database costs a few seconds at most per refresh.

## 2. `import-old-chats --apply`: a chat the store cannot hold ended the import

**Reproduced** with fresh fixtures (one good chat set plus one bad file each): numeric `sutra_id` -> `TypeError: 'int' object is not subscriptable`; a
message or title ending in `\ud83d` -> pydantic `string_unicode`; created/updated/ts `1969-12-31T23:59:59Z` or `0001-01-01T00:00:00Z` ->
`greater_than_equal`. The dry run said nothing in all five cases; a rerun died at the same file; QA's 30-file folder gave the same.

**Root causes.**
1. `read_chats` tested `str(doc["sutra_id"])` against the hex pattern but kept the raw value, so a JSON number such as 12345678901234567890 (all digits, so
   it looks hex) got through and `id[:12]` raised. (`$` also let an id with a trailing newline through.)
2. A lone surrogate half is valid in a Python string and in JSON, but not in UTF-8: pydantic and SQLite both refuse it.
3. `_epoch` returned a negative number for a time before 1970; `created_at`/`updated_at`/`at` are `>= 0`.
4. Nothing guarded the loop: one refusal ended the command, `plan()` could not see any of it, and `cmd_import` let every error escape.

**Fix (all in `sutra_app/ops/import_old.py`).**
- `sutra_id` must be a `str` and `fullmatch` the pattern, else the file is listed under "Could not read N file(s)" (a document nested past the parser limit
  too, `RecursionError`).
- Lone surrogate halves in the parsed document are replaced by U+FFFD, counted, and reported by the dry run ("N chat(s) hold a lone surrogate half ...");
  a whole emoji is untouched. This is a choice: the QA expectation was to list such a chat as unreadable, but the chat is readable and one broken
  character is all that is lost, and the old folder must stay read only, so the owner could not fix it there. Reject-instead is one line in `read_chats` if
  that is preferred.
- `_epoch` treats a time before 1970 like one that does not parse (the existing fallback: 0 for created, the chat's created for the rest). `OverflowError`
  and `OSError` (Windows refuses a naive time before 1970) fall back too.
- `import_chats` writes each chat through `_write_chat` (still one transaction each; counters are added only after the commit, so a refused chat counts
  nowhere). A `GateError` or `ValueError` skips that chat and names its file in the result's `unstorable`; the other chats import; the line
  "Could not store N chat(s): ..." is printed and the JSON has `unstorable`. Exit stays 0, as for unreadable files.
- The dry run calls `rehearse()`: the same `import_chats` into a throwaway database in the temporary folder, so it names the chats `--apply` would skip, for
  any reason, not only today's. If the temporary folder is unusable the dry run still answers and says the check could not run. Cost: a dry run now does the
  import's work (1500 chats / 36000 messages: about 10 s, was 0.6 s); `--apply` does not rehearse.
- A failing store (a refused backup of a damaged database, a newer schema, no disk, a busy file, the lock) ends with
  `sutra-pro: the import stopped: <why>. Each chat is one transaction ...; run it again once that is fixed.` and exit 1.

**Tests** (`tests/ops/test_import_old.py`, 19 new): non-hex ids (int, bool, float, null, list, trailing newline, uppercase) are listed and the rest import with
the bad file sorting between good ones; a cut emoji in title and text is repaired and reported while a whole emoji survives; four pre-1970 forms (aware,
year 1, naive, offset) import with time 0; `_epoch` unit cases; a chat the gate refuses (a stand-in gate for one title) is skipped and named, nothing of it
is stored, a rerun ends the same way; the dry run names it and writes nothing; store failures (`sqlite3.OperationalError`, `OSError`) end with the sentence
and exit 1 and release the lock; a damaged database stops the import at the backup with the sentence; a failing rehearsal does not fail the dry run. 14 of
them failed on the old code (the other 5 are guards for ids that already failed the pattern).

**Not changed.** Two files whose ids share their first 12 characters map to one session (`cs_old_<12>`), the second reported as "already there"; QA's
`collide1/2` fixtures show it. It is not in this report, no crash, left for the owner of the design (D113).

## 3. A missing data folder was created world-readable

**Reproduced.** `import-old-chats --apply --data-dir <missing>`: folder `drwxr-xr-x`, only `db.sqlite3` inside, no `app.lock`.

**Root cause.** `cmd_import` took the instance lock only `if data_dir.exists()`, so for a new folder it took none (a server could start on it halfway
through) and `Database.__init__` created the folder with the default mode.

**Fix.** `cmd_import` takes the lock unconditionally (`InstanceLock.acquire` creates the folder 0700 and `app.lock` 0600), and `Database.__init__` creates its
missing parent with `mode=0o700` so no caller can make it open (`sutra_app/orchestrator/db.py`, one line). The result is `drwx------` plus `app.lock` and the
database. Files inside keep the same modes as after a normal server start (`db.sqlite3` 0644 under a 0700 folder); the folder is the guard, as everywhere else in the app.

**Tests.** `tests/ops/test_import_old.py`: the folder and everything made under it is private under umask 022; the instance lock is held while the chats are
written into a missing folder. `tests/orchestrator/test_schema.py`: `Database` makes its missing folder 0700. All three failed before.

**Not changed.** A folder already made 0755 by an earlier import stays so (`doctor` warns, `chmod 700` fixes it); the server does not repair modes.

## 4. UNVERIFIED on Windows: restore over an existing folder

**Read, not run.** No Windows machine was available. `restore_backup` took `InstanceLock(data_dir)` (an open `app.lock` inside the folder) and kept it
through `os.rename(data_dir, moved)`. Windows refuses to rename a folder that has a file open in it, this process's own included, so the rename ends in
"the restored folder could not be put in place (Access is denied)" and the data is left as it was. Supporting evidence in the repo: of the four restore
tests that `tests/conftest.py` skips on Windows with the reason "an open log file blocks renaming the data folder in this process", three restore over an existing
folder (the held lock), while `test_restore_into_a_new_folder_...` (no lock is taken for a missing folder) is not skipped. The listed reason may be a
mis-diagnosis of the lock.

**Fix.** On Windows (`oslayer.IS_WINDOWS`) the lock is released just before the rename. If a server starts in that instant it takes `app.lock` again and the OS
refuses the rename: the existing "could not be put in place ... left as it was" message, nothing lost. Elsewhere the lock is still held to the end of the swap
(an open lock follows a renamed folder on POSIX, and keeping it excludes a server for the whole swap). The lock is not re-taken after the rename.

**Tests** (`tests/ops/test_backup.py`): with `oslayer.IS_WINDOWS` patched and `os.rename` wrapped, the lock is not held when the data folder is renamed on
the Windows path and is held on the other (both run anywhere, no real rename); a restore completes over an existing folder when the wrapped rename refuses a
folder with an open lock like Windows does (skipped on a real Windows run, like the neighbours). The Windows case failed on the old code.

**For QA / the Windows leg.** Run `sutra-pro restore FILE` against a real Windows data folder. If it works, the three skipped restore tests in `conftest.py`
can probably be un-skipped; they were left as they are because that cannot be proved here.

## Commands run (in `sutra-pro/`)

| Command | Result |
|---------|--------|
| `scripts/py -m pytest tests/ops -o addopts= -q` | 433 passed |
| `scripts/py -m pytest tests/orchestrator -o addopts= -q` | 1288 passed, 1 skipped |
| `scripts/py -m pytest tests/library tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py -o addopts= -q` | 2453 passed, 4 skipped |
| `scripts/py -m pytest tests --ignore=tests/ops --ignore=tests/orchestrator --ignore=tests/library --ignore=tests/live -k "not node_suite"` | 4964 passed, 241 skipped, 9 deselected |
| `node --test tests/ui/js/*.test.js` | 965 tests: 963 passed, 2 skipped, 0 failed |

Order dependence found, not caused here: running `tests/orchestrator` before `tests/library` in ONE pytest process fails
`tests/library/test_lib_records.py::test_all_does_not_freeze_the_registry_and_freeze_closes_it` (the registry is already frozen); it fails the same way on 2ae63d11.
The groups above run separately.
