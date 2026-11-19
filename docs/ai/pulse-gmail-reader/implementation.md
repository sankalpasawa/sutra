# Implementation: Sutra Pulse step 1, read-only Gmail reader
Branch: `pulse-gmail-reader` (from 85f10cf). Date: 2026-11-19. Not pushed; no PR.
Inputs: `spec.md` (Refined), `architecture.md`, `plan.md` (approved as written). Q-6 ruled by Kaivan Shah:
`.gitignore` and `.env.example` approved as config files for `prototypes/pulse/`; recorded in `CHARTER.md` > Rulings.

## Result
| Item | Value |
|---|---|
| Test command | `cd prototypes/pulse && python3 pulse_test.py` |
| Result | 87 tests: 86 passed, 0 failed, 1 skipped (`test_audit_unavailable_readonly_dir`, skipped because this sandbox runs as root, which ignores directory permissions) |
| Time | 2.6 s wall (`time python3 pulse_test.py`), limit 10 s (NFR-2) |
| Python | Developed on 3.13.16; the same suite also passes on 3.11 and 3.12 (`python3.11 pulse_test.py`, `python3.12 pulse_test.py`) |
| Google libs | Not installed and blocked in `sys.modules` by the test harness; sockets raise |
| Lint | The repo defines no lint or type-check command for prototypes (analysis.md); none run |
| Files outside `prototypes/pulse/` | Only this file. `git diff --name-only 85f10cf HEAD` lists nothing else |

## Steps
| Step | Commit | Files | Tests added |
|---|---|---|---|
| T1 | ba6c295 | `CHARTER.md`, `.gitignore` | none (AC-2 checked by hand with `git check-ignore`; all 5 paths ignored, `.env.example` and `fixtures/inbox.json` not) |
| T2 | f013ae9 | `pulse_test.py`, `errors.py`, `config.py`, `.env.example` | 10: config precedence, quotes, `PULSE_MOCK` and retention validation, `config_missing` naming the key, mock ignoring live values, error mapper table |
| T3 | c42e626 | `policy.py` | 7: domain, allowlist parsing and missing file, mailbox format, reason length, key-file errors without contents, permission warning |
| T4 | fa9a6e5 | `audit.py` | 5: 0600/0700 and round trip, schema-only rows, state path unusable, read-only dir (skipped as root), symlink refused |
| T5 | 3e6ccdc | `fixtures/inbox.json`, `scenarios.json`, `allowlist.txt`, `rules.sample.json` | 2: coverage, scan (example.test only, `+91 00000 \d{5}`, no PROTO-004 match; base64 bodies and RFC 2047 headers decoded before scanning) |
| T6 | 25901b5 | `gmail_client.py` | 8: paging, metadata stripping, retry 1-2 delays, 5xx exhausted with `[1, 2, 4, 8]`, 429 always, 32 s cap, history, auth scenarios |
| T7 | 68743df | `parse.py` | 6: HTML body, attachment keys, Hindi RFC 2047, metadata row shape, missing headers and quoted commas, plain preferred and 20,000 cap |
| T8 | ef3eb39 | `cli.py`, `pulse.py` | 13: check output and calls, AC-4, AC-8, not allowlisted, AC-10, mismatch, auth scenarios, audit rows, audit unavailable, `--max`/`--since` bounds, mailbox format, internal error, 2 concurrent subprocesses |
| T9 | 818e13d | `store.py`, `cli.py` | 9: pagination stop, metadata only, full, path/modes/dedupe, output-file and mailbox-dir symlinks, mismatch, retry via CLI, query and no mail on stdout |
| T10 | 9fc5429 | `store.py`, `cli.py` | 6: since-last with history, 404 fallback, no state, mock state file, truncated run keeps position, history symlink |
| T11 | 3e315ed | `store.py`, `cli.py` | 3: purge boundaries (dry run, symlinks, non-matching files, state untouched), purge in live mode with no key, auto purge |
| T12 | 139aaa3 | `rules.py`, `cli.py` | 6: sample match, 10 invalid-rule cases with zero client calls, `attachments.name` and `body_text` fields, query-only rule, mismatch, match unit |
| T13 | 1743970 | `live_client.py`, `requirements.txt`, `gmail_client.py` | 8: deps missing, scope and subject, 0644 warning, live allowlist refusal before key, key errors via CLI, error translation, request parameters, requirements set |
| T14 | c07c208 | `README.md` | 2: README items and mermaid nodes, CHARTER items |
| T15 | c3754ed | `pulse_test.py` | 2: all mock commands offline, audit schema and no mail content across all commands |

T15 checks: suite under 10 s (2.6 s); `git diff --stat main -- prototypes/j2 .gitignore` empty; `git status --porcelain` unchanged by a test run (only `__pycache__/`, which is ignored); `import google` / `from google...` appears only in `live_client._import_google`; AC-30 done on a scratch copy with an injected `self.fail()`: exit 1, repo file untouched.

## Deviations
| Step | What changed | Why |
|---|---|---|
| all | plan.md checkboxes not ticked | The user limited edits to `prototypes/pulse/` and this file |
| T1 | No placement registration was written | The Write hooks did not block or print a guard message in this environment. The Q-6 ruling is recorded in CHARTER.md as asked; the kill-switch was not used |
| T4 | Audit lock test polls `LOCK_NB` for up to 5 s instead of failing on the first `LOCK_NB` | As planned, a second concurrent run would get `audit_unavailable` while the first holds the lock for its single write, which breaks AC-34 / NFR-6 |
| T4, T8 | Unwritable `STATE_DIR` is tested by pointing it at a regular file; the chmod 0500 variant is kept but skipped as root | Root ignores directory permissions, so the chmod test would pass for the wrong reason |
| T5 | 13 messages; extra scenario `rate_limit_always` | Plan asked for 12+; the extra scenario covers "429 always gives rate_limited" from T6 |
| T6 | MockClient records `--query` / `gmail_query` but does not evaluate Gmail search syntax | Out of scope to reimplement Gmail search; documented in README. Rule matching in tests relies on local keywords and regex |
| T8 | AC-8 CLI test started with `check` only and was extended to `fetch` (T9) and `find` (T12) | Those commands did not exist yet; no assertion was weakened |
| T9, T10 | Output file and history file are checked for symlinks right after the profile call, before any message is listed | Refuses before mail is read, not only at write time (AC-21 asserts no `get_message` call) |
| T10 | Position is saved after every successful `fetch`, not only `--since-last`; a plain fetch that stops at `--max` also prints "Stopped at --max, position not saved" | Literal reading of FR-23 ("after a successful fetch") |
| T12 | `find` audit `query` = the rules' effective queries joined with ` \| ` | Spec defines `query` for one query; find has one per rule |
| T13 | `LiveClient` recognises `RefreshError` / `HttpError` by class name in the MRO, not `isinstance`; builders are `creds_builder(key_path, scopes, subject)` and `service_builder(creds)`; a 404 outside `history.list` is `internal` | Google classes cannot be imported in tests (blocked by design), so name matching lets stubs exercise the real mapping path |
| T2 | `check` writes `count: 0`; config accepts scenario `default` even if `scenarios.json` is unreadable | Spec leaves `count` for check undefined; `default` always exists |

## Acceptance criteria coverage
| AC | Test (in `pulse_test.py`) or manual |
|---|---|
| AC-1 | manual: `git log --diff-filter=A --format=%h -- prototypes/pulse \| tail -1` gives ba6c295 (T1, CHARTER.md first); `test_charter_contents` |
| AC-2 | manual: `git check-ignore` at T1 (results above) |
| AC-3 | `test_config_shell_wins` |
| AC-4 | `test_live_missing_key_config_missing`, `test_mock_ignores_live_values`, `test_live_missing_key_cli` |
| AC-5 | `test_mock_all_commands_offline` |
| AC-6 | `test_live_deps_missing` |
| AC-7 | `test_live_scope_and_subject` |
| AC-8 | `test_wrong_domain`, `test_wrong_domain_cli` |
| AC-9 | `test_allowlist_parsing`, `test_allowlist_missing_refuses_all`, `test_not_allowlisted_cli`, `test_allowlist_live_missing_refused_before_key` |
| AC-10 | `test_reason_validation`, `test_reason_length` |
| AC-11 | `test_mailbox_mismatch_check`, `test_mailbox_mismatch_fetch`, `test_mailbox_mismatch_find` |
| AC-12 | `test_check_output_and_calls` |
| AC-13 | (a) `test_auth_scenarios`; (b) `test_key_file_errors`, `test_key_file_errors_cli`; (c) `test_error_mapper`, `test_live_error_translation` |
| AC-14 | `test_retry_429_then_ok`, `test_retry_5xx_exhausted`, `test_retry_via_cli` |
| AC-15 | `test_pagination_stops_at_max` |
| AC-16 | `test_metadata_only` |
| AC-17 | `test_full_html_body` |
| AC-18 | `test_attachment_keys` |
| AC-19 | `test_rfc2047_subject` |
| AC-20 | `test_output_path_modes_dedupe` |
| AC-21 | `test_symlink_output_refused`, `test_symlink_mailbox_dir_refused`, `test_symlink_history_refused`, `test_audit_symlink_refused` |
| AC-22 | `test_since_last_uses_history`, `test_since_last_expired`, `test_since_last_no_state` |
| AC-23 | `test_history_saved_mock_file` |
| AC-24 | `test_find_sample`, `test_rules_invalid` |
| AC-25 | `test_purge_boundaries` |
| AC-26 | `test_fetch_auto_purge` |
| AC-27 | `test_audit_rows_check`, `test_audit_rows_schema_and_no_mail` |
| AC-28 | `test_audit_unavailable_cli`, `test_audit_unavailable_state_is_file` (`test_audit_unavailable_readonly_dir` skipped as root) |
| AC-29 | `test_fixture_coverage`, `test_fixture_scan` |
| AC-30 | manual: injected `self.fail()` in a scratch copy, exit 1 (T15) |
| AC-31 | `test_readme_contents` |
| AC-32 | `test_key_perms_warning`, `test_key_perms_warning_cli` |
| AC-33 | `test_max_bounds` |
| AC-34 | `test_concurrent_audit` |
| AC-35 | `test_mailbox_format`, `test_mailbox_format_cli` |
| AC-36 | `test_internal_error` |
| AC-37 | `test_since_last_truncated_keeps_position` |
| AC-38 | manual: `git status --porcelain` unchanged after a run (T15); every test passes temp `HOME`, `PULSE_OUT_DIR`, `PULSE_STATE_DIR` and a temp `.env` |

## Known gaps and unverified
| Item | Status |
|---|---|
| Live path (`live_client.py`) against real Google | Unverified. Tested only with stub builders. Token error strings (A-2) and real response shapes (A-3) are checked at L-5 / L-6 |
| `pip install -r requirements.txt` | Not run (no network allowed in this task) |
| Network failure while getting a token (`google.auth.exceptions.TransportError`) | Not mapped; would exit 1 `internal`. Follow-up if it shows up in live use |
| `fetch --full` after a metadata fetch on the same day | Rows already in the day's file keep their metadata-only form (dedupe by id, as specified). Use another day's file or delete the file to re-fetch with bodies |
| Audit log retention (365 d) | Policy only (DEC-1), not enforced |
| Read-only dir test | Skipped under root; the file-as-state-dir test covers the same refusal |

Follow-ups (from spec/impact, unchanged): CI for `prototypes/pulse/**`; root `.gitignore` rule for `**/.env`; audit retention enforcement; map `TransportError`.

## How to run (mock, works now)
```bash
cd prototypes/pulse
python3 pulse_test.py                                    # 87 tests, ~3 s
export PULSE_MOCK=1 PULSE_OUT_DIR=$(mktemp -d) PULSE_STATE_DIR=$(mktemp -d)
python3 pulse.py check --mailbox ana@example.test --reason "trying the mock inbox"
python3 pulse.py fetch --mailbox ana@example.test --reason "trying the mock inbox" --max 7
python3 pulse.py fetch --mailbox ana@example.test --reason "trying the mock inbox" --full --since-last
python3 pulse.py find  --mailbox ana@example.test --reason "trying the mock inbox" --rules fixtures/rules.sample.json
python3 pulse.py purge --dry-run
PULSE_MOCK_SCENARIO=mismatch python3 pulse.py check --mailbox ana@example.test --reason "trying the mock inbox"   # exit 3
```
All of these were run on this branch: exit 0 for the first five commands, exit 3 for the mismatch scenario.

## Live steps (when the admin-approved key arrives)
Preconditions: the admin has finished README "Admin setup"; the test mailbox owner has been told in writing
(DEC-3); the admin approved the allowlist entry.

| # | Do | Expect |
|---|---|---|
| L-1 | Store the key outside the repo, `chmod 600 /path/to/key.json`; run `git status` in the repo | No new file in the repo |
| L-2 | `cd prototypes/pulse && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` | 2 packages plus their deps; note versions |
| L-3 | `cp .env.example .env`; set `PULSE_SA_KEY_PATH`, `PULSE_DOMAIN`, `PULSE_ALLOWLIST` (file outside the repo with the 1 approved mailbox); leave `PULSE_MOCK` empty | - |
| L-4 | `.venv/bin/python pulse.py check --mailbox <approved> --reason "first live check, owner notified"` | Exit 0; printed mailbox equals `<approved>`; audit row `mode: live`, `result: ok` |
| L-5 | `check` on an allowlisted address that does not exist in the domain; with the admin, briefly remove the delegation entry and run `check` | `invalid_grant` / `unauthorized_client`, exit 4. Record the real error strings; if they differ, fix `errors.map_refresh_error` plus a test |
| L-6 | `pulse.py fetch --mailbox <approved> --reason "..." --max 5` | 5 rows, no `body_text`, under `~/.sutra-pulse/out/<mailbox>/`, file 0600, dirs 0700. Compare one raw message's keys to `fixtures/inbox.json` (A-3) |
| L-7 | `pulse.py fetch ... --max 3 --full` (on a fresh day's file, or after deleting today's) | `body_text` present and readable |
| L-8 | `pulse.py fetch ... --since-last --since 1d`, then `pulse.py fetch ... --since-last` | First run saves a position; second lists only new mail or 0; `history.json` updated, `history.mock.json` untouched (fix-up 1, R1-9) |
| L-9 | `check` on a mailbox not in the allowlist, and one outside the domain | `not_allowlisted` / `wrong_domain`, exit 3, no Google call; refusal rows in the audit log |
| L-10 | `pulse.py find --mailbox <approved> --reason "..." --rules fixtures/rules.sample.json --max 20` | Exit 0; 0 or more matches |
| L-11 | Admin console: the delegation entry lists only `https://www.googleapis.com/auth/gmail.readonly` | Exactly one scope; admin keeps a screenshot |

Any mismatch at L-5 or L-6: open `fix/pulse-live-<topic>`, update `errors.py` or `fixtures/` with a test, re-run L.
