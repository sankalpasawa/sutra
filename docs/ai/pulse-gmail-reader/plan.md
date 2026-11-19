# Plan: Sutra Pulse step 1, read-only Gmail reader
Branch: `pulse-gmail-reader` (already exists and is pushed; used instead of `feat/<slug>` per the user)

Inputs: `spec.md` (Refined), `architecture.md`. All paths below are under `prototypes/pulse/` unless they start with `docs/` or `/`.
Test command for every step: `cd prototypes/pulse && python3 pulse_test.py` (stdlib only, no venv needed).
Rules for every step: one commit; build green after it; tests written first where practical; no file outside `prototypes/pulse/`; never create or read a real `.env` or key.

Estimates are planning guesses for one developer with an AI assistant, not measurements. Confidence: moderate.

## Before T1: creation guard (stop point)
The guard is in hard mode (`.claude/creation-guard-mode`). Two facts from `marketplace/plugin/hooks/creation-guard.sh`:
1. Every new file needs session placement registered (`:44-45`). Register placement for this turn before the first write, per the per-turn prompt.
2. `.gitignore` and `.env.example` match no artifact kind (`:84-86` fall through to `KIND=""`), so the guard exits 2 with "NEW KIND DETECTED" and asks for a founder ruling (`:87-91`). Do not bypass it with Bash or the kill-switch. Ask the user for the ruling, then write the files the way the user approves.

## Steps
| Step | Goal | Est. |
|---|---|---|
| T1 | CHARTER.md + .gitignore | 20 min |
| T2 | Test harness, errors, config, .env.example | 50 min |
| T3 | Policy checks | 45 min |
| T4 | Audit log | 30 min |
| T5 | Fixtures + fixture scan | 60 min |
| T6 | Client interface, MockClient, retry | 60 min |
| T7 | Parser | 60 min |
| T8 | CLI skeleton + `check` | 75 min |
| T9 | Store + `fetch` | 60 min |
| T10 | History + `--since-last` | 45 min |
| T11 | `purge` + auto purge | 30 min |
| T12 | Rules + `find` | 45 min |
| T13 | LiveClient + requirements.txt | 60 min |
| T14 | README | 45 min |
| T15 | Full suite, timing, guards | 30 min |
| **Total** | 15 commits | **~12 h** (715 min) |
| L | Live checklist, when the key arrives (no commit unless a fix is needed) | 60-90 min with the admin |

- [ ] **T1: CHARTER.md and .gitignore, first files in the folder**
  - Files: `CHARTER.md`, `.gitignore`
  - Change: CHARTER.md with purpose, scope, non-goals, data handled (metadata incl. subject and snippet per DEC-2; body only with `--full`; no attachment contents), retention (output 30 d default; audit 365 d, not enforced in step 1, DEC-1), the rule "the Workspace admin approves every allowlist entry and each mailbox owner is told in writing before the first read" (DEC-3), owner Kaivan Shah, approver the Workspace admin (DEC-4), OAuth scope `gmail.readonly` only. Write CHARTER.md first (it satisfies the guard's domain and charter for later files). `.gitignore`: `.env`, `.env.*`, `!.env.example`, `*.json`, `!fixtures/*.json`, `out/`, `state/`, `.venv/`, `__pycache__/`.
  - Tests: none (docs and ignore rules).
  - Done when: `git check-ignore -q .env .env.local sa-key.json out/x.jsonl state/audit.jsonl` exits 0 for each, and `git check-ignore .env.example fixtures/inbox.json` prints nothing; `git log --diff-filter=A --format=%h -- prototypes/pulse | tail -1` is this commit.
  - Covers: FR-1, FR-2, AC-1, AC-2

- [ ] **T2: Test harness, errors, config**
  - Files: `pulse_test.py`, `errors.py`, `config.py`, `.env.example` (guard ruling from T1 applies)
  - Change: `pulse_test.py` header blocks `google`/`googleapiclient` in `sys.modules` and replaces `socket.socket` with a raising class; `BaseCase.setUp` makes a temp dir with `out/`, `state/`, `home/`, `.env` and an `env()` helper returning a dict with `HOME`, `PULSE_OUT_DIR`, `PULSE_STATE_DIR`; `unittest.main(verbosity=2)`. `errors.py`: `EXIT`, `PulseError`, `TransientError`, `HistoryExpired`, `map_refresh_error`, `map_http_error` (architecture "Interfaces" and "Live error mapping"). `config.py`: `read_env_file`, `Config`, `load(environ, env_file, need_live_keys)` with every rule in the spec Configuration table; mock forces `example.test` and `fixtures/allowlist.txt`. `.env.example` lists all 9 keys, empty values except defaults.
  - Tests first: shell beats `.env`; empty shell falls back to `.env`; quotes stripped; `PULSE_MOCK=yes` is `config_invalid`; `PULSE_RETENTION_DAYS=0` and `3651` invalid; live with empty `PULSE_SA_KEY_PATH` raises `config_missing` naming the key and not echoing any value; mock with a real-looking domain gives `example.test`; mapper table cases (403, 404, 429, 503, 418, refresh strings).
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-3, FR-4 (config part), FR-13 (mapper), FR-31, AC-3, AC-13(c)

- [ ] **T3: Policy checks**
  - Files: `policy.py`, `pulse_test.py`
  - Change: `normalise_mailbox`, `check_domain` (exact match, no subdomains), `load_allowlist` / `check_allowlist` (trim, lowercase, skip blank and `#`; missing or unreadable gives empty set), reason length check helper, `check_key_file` (missing gives `key_missing`; unreadable, non-JSON, or JSON without `type == "service_account"` gives `key_unreadable`; messages contain the path only; returns a warning if mode has group/other read bits).
  - Tests first: AC-8 cases; AC-9 allowlist file with `# c`, blank line, ` Ana@Example.test `; missing allowlist refuses; AC-35 bad mailbox forms; key file cases written into the temp dir (fake JSON with `"type": "service_account"` and placeholder strings that do not match the PROTO-004 pattern); assert no file content appears in the error message; 0644 file returns a warning.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-8, FR-9, FR-10 (helper), FR-13 (key part), FR-34, FR-35, AC-9, AC-13(b), AC-35 (unit)

- [ ] **T4: Audit log**
  - Files: `audit.py`, `pulse_test.py`
  - Change: `AuditLog(state_dir)` creates dir 0700, opens `audit.jsonl` with `O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW`, mode 0600, tries `flock(LOCK_EX|LOCK_NB)` then releases; any failure raises `audit_unavailable`. `write(row)` locks, writes one JSON line with one `os.write`, unlocks. A `build_row(...)` helper accepts only the 11 schema fields.
  - Tests first: file created 0600; row round-trips; read-only state dir gives `audit_unavailable`; symlinked `audit.jsonl` gives `audit_unavailable` and target unchanged; `build_row` rejects unknown keys.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-21 (audit part), FR-27 (writer), FR-28 (unit)

- [ ] **T5: Fixtures and fixture scan**
  - Files: `fixtures/inbox.json`, `fixtures/scenarios.json`, `fixtures/allowlist.txt`, `fixtures/rules.sample.json`, `pulse_test.py`
  - Change: 12+ full Gmail Message resources (plain, HTML-only with `<script>` and `&amp;`, one with a PDF attachment part, a 3-message thread, one Hindi subject encoded as RFC 2047 `=?UTF-8?B?...?=` with Hindi body, one matching the sample rule), profile (`ana@example.test`, totals matching the data), `page_size: 5`, history with `start_id` and 3 added ids. Scenarios as in architecture "Data model", plus `history_many` (6 added ids, for AC-37). Allowlist: header comment stating DEC-3, then `ana@example.test`. Only `example.test` addresses, fake names, `+91 00000 xxxxx` numbers.
  - Tests first: coverage test (count >= 12, each required case present by id); scan test over every file in `fixtures/`: all emails end `@example.test`, all `+91` numbers match `\+91 00000 \d{5}`, nothing matches the PROTO-004 pattern copied from `marketplace/plugin/hooks/keys-in-env-vars.sh:69`.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-29, FR-30, AC-29

- [ ] **T6: Client interface, MockClient, retry**
  - Files: `gmail_client.py`, `pulse_test.py`
  - Change: `GmailClient` Protocol; `MockClient(mailbox, fixtures_dir, scenario)` with recorded `calls`, page-size capping, metadata filtering (headers only, filtered to requested names), history serving, scenario hooks (`profile_email`, `history_status`, `fail`, `auth_error` via `errors.map_refresh_error`, `http_error` via `map_http_error`, `raise`); `with_retry(fn, sleep, attempts=5, base=1.0, cap=32.0)`; `make_client(cfg, mailbox)` returns `MockClient` in mock and imports `live_client` lazily otherwise (stub until T13).
  - Tests first: list returns at most `page_size` with `nextPageToken`; metadata strips `parts` and body; `rate_limit_then_ok` succeeds with 3 attempts and delays `[1, 2]`; `server_error` raises `server_error` after 5 attempts with delays exactly `[1, 2, 4, 8]`; 429-always gives `rate_limited`; `history_expired` raises `HistoryExpired`.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-5 (mock half), FR-14, NFR-3, NFR-4, AC-14 (unit)

- [ ] **T7: Parser**
  - Files: `parse.py`, `pulse_test.py`
  - Change: `to_row(msg, full)` per spec "Mail row"; `decode_header_value` with `email.header.decode_header` + `make_header`; `split_addresses` with `email.utils.getaddresses` returning formatted strings; `internalDate` ms to ISO 8601 UTC; part walk for attachments (`filename` non-empty, keys `name`, `mime`, `size` only); body: prefer `text/plain`, else `html_to_text` (an `html.parser.HTMLParser` subclass dropping `script`/`style`, `convert_charrefs=True`), base64url decode, cap 20,000 chars with `body_truncated`.
  - Tests first: AC-17, AC-18, AC-19 against fixture messages; metadata row has no `body_text`/`body_truncated`; missing Subject gives `""`; missing Cc gives `[]`.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-17, FR-18, FR-19, AC-17, AC-18, AC-19

- [ ] **T8: CLI skeleton and `check`**
  - Files: `cli.py`, `pulse.py`, `pulse_test.py`
  - Change: argparse with 4 subcommands, `error()` override mapping to `usage`; `--max` type 1..500; `--since` regex `^\d+[dh]$` with ranges; `--mailbox` via `normalise_mailbox`. `main(...)` signature from architecture. Pipeline steps 1-8 from spec "Commands", single `try/except PulseError/except Exception` and a `finally` that writes the audit row once the log is open. `MOCK MODE` first stdout line. `cmd_check` prints profile email, totals, mode. `pulse.py` is the 5-line entry.
  - Tests first: AC-4 (live missing key: exit 2, names the key, no audit file; mock: exit 0), AC-8 via CLI with zero `calls`, AC-10, AC-11 for `check`, AC-12, AC-13(a) for the 3 auth scenarios, AC-27 for `check` success, refusal, and `usage` (no row), AC-28 with zero calls, AC-33 (`--max 0`, `501` on fetch parse), AC-35 via CLI (no dir created), AC-36 with scenario `boom` (exit 1, no traceback, row `internal`), AC-34 (two `subprocess.Popen` of `python3 pulse.py check` with explicit env, all `PULSE_*` and `HOME` set to temp values).
  - Done when: `python3 pulse_test.py` exits 0 and `PULSE_MOCK=1 PULSE_OUT_DIR=$(mktemp -d) PULSE_STATE_DIR=$(mktemp -d) python3 pulse.py check --mailbox ana@example.test --reason "manual smoke test"` exits 0.
  - Covers: FR-4, FR-8, FR-10, FR-11, FR-12, FR-13, FR-27, FR-28, FR-35, FR-36, NFR-5, NFR-6, AC-4, AC-8, AC-10, AC-11 (check), AC-12, AC-13(a), AC-28, AC-33, AC-34, AC-35, AC-36

- [ ] **T9: Store and `fetch`**
  - Files: `store.py`, `cli.py`, `pulse_test.py`
  - Change: `mailbox_dir` (0700 chain, `lstat` each level, `unsafe_path` on symlink), `append_rows` (open with `O_NOFOLLOW`, `flock`, read existing ids, append new rows, 0600). `cmd_fetch` without `--since-last`: effective query, list loop with `min(remaining, 100)`, `get_message` per id with `metadata` or `full`, `to_row`, append, print count and path. History save is added in T10.
  - Tests first: AC-15 (7 rows, exactly 2 `list_messages` calls), AC-16, AC-20 (two runs, one file, modes, no duplicate ids), AC-21 output-file symlink case, AC-11 for fetch (no output file, no list call), AC-14 via CLI (`rate_limit_then_ok` exit 0; `server_error` exit 5), stdout contains no fixture subject.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-15, FR-16, FR-20, FR-21, AC-11 (fetch), AC-14, AC-15, AC-16, AC-20, AC-21 (output)

- [ ] **T10: History state and `--since-last`**
  - Files: `store.py`, `cli.py`, `pulse_test.py`
  - Change: `load_history` / `save_history` (`history.json` live, `history.mock.json` mock; temp file + `os.replace`; refuse if target is a symlink). `--since-last` branch with both fallbacks and messages. Save the step-8 profile historyId after success unless stopped at `--max` with more available, then print "Stopped at --max, position not saved".
  - Tests first: AC-22 (three cases), AC-23 (mock file 0600, no `history.json`), AC-37 with `history_many` and `--max 2`, AC-21 history-file symlink case.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-21 (state), FR-22, FR-23, AC-21 (state), AC-22, AC-23, AC-37

- [ ] **T11: `purge` and automatic purge**
  - Files: `store.py`, `cli.py`, `pulse_test.py`
  - Change: `purge(out_dir, retention_days, today, dry_run)` matching only `YYYY-MM-DD.jsonl` / `YYYY-MM-DD.find.jsonl`, not following symlinks, removing empty mailbox dirs. `cmd_purge` (needs no live keys: `need_live_keys=False`). Call purge in fetch/find after step 4, record `purged` in the row.
  - Tests first: AC-25 with fixed `now` (today, today-30, today-31; dry run; audit and history bytes unchanged; a non-matching file untouched), AC-26 (`purged: 1`), purge audit row has `mailbox: null`.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-25, FR-26, AC-25, AC-26

- [ ] **T12: Rules and `find`**
  - Files: `rules.py`, `cli.py`, `pulse_test.py`
  - Change: `load_rules(path, full)` with every validation in spec "find"; `match(rule, row)`; `cmd_find` running validation at step 5, per-rule list + local match, merged rows with `rules_hit`/`fields_hit`, written to `.find.jsonl` with dedupe, per-rule counts on stdout.
  - Tests first: AC-24 (sample matches exactly the expected id and rule; bad regex, unknown key, duplicate id, `body_text` without `--full` each give `rules_invalid` with zero calls), AC-11 for find, `attachments.name` field matching.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-24, AC-11 (find), AC-24

- [ ] **T13: LiveClient and requirements**
  - Files: `live_client.py`, `requirements.txt`, `gmail_client.py` (wire `make_client`), `pulse_test.py`
  - Change: `LiveClient` per architecture; default builders import `google.oauth2.service_account` and `googleapiclient.discovery` inside a function, `ImportError` gives `deps_missing`; `execute(num_retries=0)`; translate `RefreshError` and `HttpError` with the T2 mappers; metadata requests pass `metadataHeaders=["From","To","Cc","Subject"]`. `requirements.txt`: `google-auth` and `google-api-python-client`, nothing else.
  - Tests first: AC-6 (live, valid fake key, Google blocked: `deps_missing`, exit 2); AC-7 (stub `creds_builder` records scopes and subject, stub service returns a fixture profile: scopes exactly `[gmail.readonly]`, subject equals mailbox); AC-32 (0644 fake key: warning on stderr, exit 0); requirements file has exactly the 2 names (NFR-7); AC-9 live missing allowlist refused before key checks.
  - Done when: `python3 pulse_test.py` exits 0. Optional, if the developer has network: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -c "import live_client"` succeeds (not required for green).
  - Covers: FR-6, FR-7, FR-34, NFR-7, AC-6, AC-7, AC-9 (live), AC-32

- [ ] **T14: README**
  - Files: `README.md`, `pulse_test.py`
  - Change: sections: What it is; Rules before first use (DEC-3 approval and written notice; retention DEC-1); Admin setup (GCP project, enable Gmail API, create service account, create JSON key and store it outside the repo with `chmod 600`, Admin console > Security > Access and data control > API controls > Domain-wide delegation, add client ID with scope `https://www.googleapis.com/auth/gmail.readonly` only); Install; Mock run; Live run; Commands and exit codes table; Mermaid `flowchart` with nodes setup, auth, list, get, parse, store, find; "What changes when the key arrives" (set 4 `.env` keys, unset `PULSE_MOCK`, run `check` first); Platform: POSIX only.
  - Tests first: `test_readme_contents` greps each FR-32 item, the 7 node names inside a ```mermaid block, and "POSIX"; CHARTER grep for owner, approver, 365, DEC-3 wording.
  - Done when: `python3 pulse_test.py` exits 0.
  - Covers: FR-1 (grep), FR-32, NFR-10, AC-31

- [ ] **T15: Full suite and guards**
  - Files: `pulse_test.py` only if a gap is found
  - Change: add `test_mock_all_commands_offline` (AC-5: check, fetch, fetch --full, find, purge in one temp env with Google blocked and sockets disabled) and `test_audit_rows_schema_and_no_mail` (AC-27 across all commands, scanning every audit line for every fixture subject, sender, snippet, body and attachment name) if not already present.
  - Done when, all of:
    - `cd prototypes/pulse && time python3 pulse_test.py` exits 0 in under 10 s (NFR-2)
    - `git diff --stat main -- prototypes/j2 .gitignore` prints nothing (NFR-8)
    - `git status --porcelain prototypes/pulse` is empty after the run (NFR-9, AC-38)
    - Manual AC-30: add `self.fail()` to one test, run, see exit 1, revert
    - `grep -rn "import google\|from google" prototypes/pulse --include=*.py` shows hits only in `live_client.py`, inside a function
  - Covers: FR-5, FR-27, FR-31, FR-33, NFR-1, NFR-2, NFR-8, NFR-9, AC-5, AC-27, AC-30, AC-38

## L: Live checklist (when the admin-approved key arrives; no commit unless a fix is needed)
Preconditions: admin completed README "Admin setup"; the owner of the test mailbox has been told in writing (DEC-3); the allowlist entry was approved by the admin.

| # | Check | Expected | Records |
|---|---|---|---|
| L-1 | Key stored outside the repo, `chmod 600`; `git status` in repo shows nothing new | No key path under the repo | - |
| L-2 | `.venv/bin/pip install -r requirements.txt` | Installs 2 packages plus their deps | Versions installed |
| L-3 | `.env`: `PULSE_SA_KEY_PATH`, `PULSE_DOMAIN`, `PULSE_ALLOWLIST` (file outside repo, 1 approved mailbox); `PULSE_MOCK` unset | - | - |
| L-4 | `check --mailbox <approved> --reason "..."` | Exit 0; profile email equals mailbox; totals look plausible | Audit row present, `mode: live` |
| L-5 | Negative auth: `check` on an allowlisted-but-non-existent domain address; temporarily wrong client ID scope (admin) | `invalid_grant` / `unauthorized_client` with the right message | Real `RefreshError` strings (confirms or fixes A-2 mapping) |
| L-6 | `fetch --max 5` | 5 rows, no `body_text`; output under `~/.sutra-pulse/out/<mailbox>/` with 0600/0700 | Compare one row's source keys to fixture keys (A-3) |
| L-7 | `fetch --max 3 --full` | `body_text` present, readable | - |
| L-8 | `fetch --since-last` twice | Second run lists only new mail or 0 | `history.json` updated, `history.mock.json` untouched |
| L-9 | `check` on a mailbox not in the allowlist, and one outside the domain | `not_allowlisted` / `wrong_domain`, exit 3, no Google call | Audit rows show refusals |
| L-10 | `find --rules fixtures/rules.sample.json --max 20` | Runs; 0 or more matches | - |
| L-11 | Admin console: delegation entry lists only `gmail.readonly` | Exactly one scope | Screenshot kept by admin |

Any mismatch at L-5 or L-6: open a fix step (`fix/pulse-live-<topic>`), update `errors.py` or `fixtures/` plus a test, then re-run L.
