# Review: pulse-gmail-reader

## Round 1  (2026-11-19, commit 0d75e86)
Verdict: **Changes requested**

Two Major findings, both on `fetch --since-last`: it can silently skip mail, and on a live run it can get stuck failing. The privacy guarantees hold: domain and allowlist checks, a profile identity check on every run, the read-only scope, modes, symlink refusal, mock/live separation, and no mail content in the audit log or stdout. Counts: 0 Blocker, 2 Major, 9 Minor, 2 Nit.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R1-1 | Major | `prototypes/pulse/cli.py:244-247` | A position is saved after **any** fetch that finishes without hitting `--max`, including filtered runs (`--query`, `--since`) and runs without `--since-last`. Later `--since-last` runs then skip every message that arrived before that save and did not match the filter. Nothing tells the user. Deviation T10 records this as a literal reading of FR-23, but it breaks the purpose of an incremental read. The 404 fallback with a filter has the same gap. | Mock run: `fetch --query "from:nobody" --max 500` exited 0 and wrote `history.mock.json` `{"history_id": "2000"}`. No test covers a filtered fetch. | Save a position only on `--since-last` runs. If the fallback list (no position, or 404) was filtered, still save, but print that mail outside the filter before this point is not covered. Add a test: a plain `fetch --query` leaves the history file unchanged. |
| R1-2 | Major | `prototypes/pulse/live_client.py:214-215`, `cli.py:171-173` | A 404 on `messages.get` maps to `internal`, which ends the whole run: no rows written, no position saved. `history.list` can still return `messagesAdded` records for messages deleted since. If it does, every later `--since-last` hits the same id and fails until the history expires (about a week), then falls back. A message deleted between list and get in a plain fetch also loses the whole run. | Stub LiveClient (scratch script, saved position 100, history returns ids `gone` and `ok1`, get `gone` gives 404): run 1 and run 2 both `exit 1 "Unexpected error: Gmail returned HTTP 404 for get_message."`, saved id stays `100`, `ok1` never written. Whether Gmail keeps those records needs a live check. | In `get_rows`, treat a 404 on get as "message gone": skip it, count it, and print `Skipped N deleted messages` (ids only). Keep the 404 as `internal` for `getProfile` and `messages.list`. Add a stub test. |
| R1-3 | Minor | `prototypes/pulse/live_client.py:205-217` | Network failures are not mapped. `google.auth.exceptions.TransportError` during token refresh, `httplib2` errors, `socket.timeout` and `ConnectionResetError` during `execute` all give exit 1 `internal` with "Unexpected error". They are not retried. implementation.md records this as a known gap. | Code: `_exec` re-raises anything that is not `RefreshError`/`HttpError`. Only `TransientError` is retried (`gmail_client.py:129`). | Map `TransportError`, `OSError` and `httplib2.HttpLib2Error` (by class name, as for the others) to `TransientError`, or to a new `network_error` code (exit 5) with retry. Message: "Could not reach Google; check the network". |
| R1-4 | Minor | `prototypes/pulse/errors.py:316-321` | Gmail also uses 403 for usage limits (`rateLimitExceeded`, `userRateLimitExceeded`, `dailyLimitExceeded`). These map to `access_denied`: no retry, and the message tells the user to enable the Gmail API. | `map_http_error` branches on status only. The reason is available (`_http_reason`) but not used for routing. | If the 403 reason is `rateLimitExceeded` or `userRateLimitExceeded`, return `TransientError(429)`. Add a mapper test row. |
| R1-5 | Minor | `prototypes/pulse/errors.py:290-310`, `live_client.py:209-210` | Every `RefreshError` that does not contain `invalid_grant` becomes `unauthorized_client` with the delegation help text, including transient token-endpoint failures. `RefreshError.retryable` is ignored. `invalid_grant` is also returned when a key has been deleted or revoked ("Invalid JWT Signature"), but the message only names the mailbox or the clock. | Code reading. Token strings unverified (A-2). | If `getattr(e, "retryable", False)`, raise `TransientError`. Add "or the key was revoked or deleted" to the `invalid_grant` message. Confirm the strings at L-5. |
| R1-6 | Minor | `prototypes/pulse/policy.py:398-399` | The key pre-check requires `type`, `client_email` and `private_key`. google-auth also requires `token_uri` and parses the PEM. A key that passes the pre-check but fails either of those raises `ValueError` inside `from_service_account_file` and exits `internal`, not `key_unreadable`. | `default_creds_builder` (`live_client.py:173-176`) is called with no `try`. | Add `token_uri` to the pre-check. Wrap `default_creds_builder` so `ValueError` becomes `key_unreadable`; the message must not include the exception text. |
| R1-7 | Minor | `prototypes/pulse/.gitignore:6-7` | `!fixtures/*.json` re-includes **any** JSON file in `fixtures/`, so a key dropped there can be committed. `*.pem` is not ignored. `test_fixture_scan` would catch a PEM key in `fixtures/` (it scans every file for `PRIVATE KEY`), but only if someone runs it, and there is no CI. | `git check-ignore`: `fixtures/sa-key.json` and `key.pem` NOT ignored. `sa-key.json`, `keys/sa.json`, `.env`, `.env.local`, `out/x.jsonl` and `state/audit.jsonl` are ignored. `.env.example` and `fixtures/inbox.json` are not ignored, as intended. | Whitelist the three fixture files by name (`!fixtures/inbox.json`, `!fixtures/scenarios.json`, `!fixtures/rules.sample.json`). Add `*.pem`, `*.p12` and `*.key`. |
| R1-8 | Minor | `prototypes/pulse/store.py:605-618` | `purge` (and the automatic purge inside every fetch and find) walks the whole `PULSE_OUT_DIR` tree at any depth. It deletes any `YYYY-MM-DD.jsonl` file older than the retention period and removes the folders that leaves empty. If `PULSE_OUT_DIR` is set to `~` or a shared folder by mistake, it deletes unrelated files. | `os.walk(out_dir)` with no depth or name limit. | Only look in `<out>/<name@domain>/` and `<out>/_mock/<name@domain>/` (folder names matching `policy.MAILBOX_RE`). |
| R1-9 | Minor | `prototypes/pulse/cli.py:227-237, 244-245` | On a mailbox with more messages than `--max` (at most 500), `--since-last` with no saved position, or after a 404 fallback, stops at `--max` and never saves a position. Every run repeats the full list, so plain `--since-last` never gets going on a real mailbox. This matches the spec (R-7), so it is a design note, not a defect. | Mock run: `fetch --max 7` printed "Stopped at --max, position not saved". | Document starting with `--since-last --since 1d` in the README, or save the starting position on a run with no saved position and say so. Decide this together with R1-1. |
| R1-10 | Minor | `prototypes/pulse/cli.py:223-224` | When a saved position is used, `--query` and `--since` are ignored (as the spec says), but the audit row still records them as `query`. The audit then claims a filter was applied that was not. | Code: `run.row["query"] = query` is set before the branch. | Set `query` to null when the history path is used, or reject `--query`/`--since` together with `--since-last` when a position exists. |
| R1-11 | Minor | `prototypes/pulse/requirements.txt:1-2` | The dependencies have no version pins. `cache_discovery=False` relies on static discovery documents, which client version 2.0 and later provide; an older version would fetch the discovery document over the network on every run. | File content. | Pin major versions (`google-auth>=2,<3`, `google-api-python-client>=2,<3`) and record the exact versions installed at L-2. |
| R1-12 | Nit | `prototypes/pulse/config.py:450`, `fixtures/scenarios.json:2` | `PULSE_MOCK_SCENARIO=_note` passes validation, then fails with `internal`. | Mock run: exit 1, "Unexpected error". | Ignore keys that start with `_` in `scenario_names()`. |
| R1-13 | Nit | `cli.py:156-200`, `cli.py:328-330`, `store.py:567-570` | `list_ids` and `history_ids` repeat the same paging loop. The "command not built yet" branch can no longer be reached. `load_history` has two `except` branches that both return `{}`. | Code reading. | Use one paging helper, remove the dead branch, merge the two `except` branches. |

### What I verified and how
| Check | Command / method | Result |
|---|---|---|
| Test suite | `cd prototypes/pulse && time python3 pulse_test.py` | 87 tests, OK (1 skipped: the read-only folder test, because this machine runs as root), 2.5 s |
| Repo unchanged by tests | `git status --porcelain` after the run | Empty |
| Scope | `git diff --name-only origin/main..HEAD`, filtered to exclude `prototypes/pulse/` and `docs/ai/` | Nothing else changed. `prototypes/j2` and the root `.gitignore` are untouched |
| CHARTER.md first (AC-1) | `git log --diff-filter=A -- prototypes/pulse` | First commit is ba6c295 (CHARTER.md and .gitignore only) |
| Ignore rules (AC-2) | `git check-ignore` on 14 paths | See R1-7 |
| Mock CLI | `PULSE_MOCK=1`, with HOME, OUT_DIR and STATE_DIR in a temp folder: check, refusals, fetch `--max 7`, fetch `--query`, `--since-last`, find, the mismatch scenario, purge `--dry-run` | Exit codes match the spec (0 / 3 / 3 / 0 / 0 / 0 / 0 / 3 / 0). The first stdout line is `MOCK MODE`. Output files are 0600 and folders 0700 (out, state, `_mock`, mailbox). Mock state is in `history.mock.json`; `history.json` is never created. Audit has 10 rows with only the schema fields and no subject, sender, snippet or body. Mismatch writes no output file |
| Allowlist / domain | `bob@example.test` gives `not_allowlisted`; `ana@sub.example.test` gives `wrong_domain` | Both refused before any client call. Domain check is an exact match after `@` (`policy.py:359`) |
| Identity check | `cli.open_mailbox` runs for every check, fetch and find before any list or get call | The profile email is compared with `--mailbox` after trimming and lowercasing; all reads in a run go through one client with that subject |
| Scope | `live_client.SCOPES` = `[errors.SCOPE]`; test asserts the exact list and subject | Only `gmail.readonly` |
| Mock/live separation | `config.load` mock branch forces the fixture domain, the fixture allowlist and no key; output goes to `_mock/`, state to `history.mock.json` | No route found for mock data into live paths. Live needs `PULSE_SA_KEY_PATH`, `PULSE_DOMAIN` and `PULSE_ALLOWLIST`, otherwise `config_missing` |
| Symlinks | Audit opened with `O_NOFOLLOW`; output `lstat` check plus `O_NOFOLLOW`; `os.replace` on history replaces the link, it does not follow it; purge uses `followlinks=False` and `lstat` | OK |
| Live 404 on get | Stub script with the real `cli.main` and `LiveClient` | Confirms R1-2 |
| Google API usage | Read `live_client.py` against the documented API | `from_service_account_file(..., scopes=).with_subject()`, `build("gmail","v1",credentials=,cache_discovery=False)`, `getProfile(userId="me")`, `messages.list(q, pageToken, maxResults)`, `messages.get(format="metadata", metadataHeaders=[...])`, `history.list(startHistoryId, historyTypes=["messageAdded"], maxResults, pageToken)`, `execute(num_retries=0)`, `HttpError.resp.status`, `.reason`, `.error_details` all match google-api-python-client 2.x. I see no call likely to break on the first live run; the risks are in error mapping (R1-2 to R1-6) |

### Acceptance criteria spot-checked (test body read, not just name)
| AC | Test | Asserts the behaviour? |
|---|---|---|
| AC-7 | `test_live_scope_and_subject` | Yes: exact scope list, subject, key path, and the only call is `getProfile` |
| AC-11 | Mock run and test names | Yes: exit 3, no output file (mock run confirms) |
| AC-14 | `test_retry_5xx_exhausted` | Yes: 5 calls, delays exactly `[1, 2, 4, 8]`, `server_error` exit 5 |
| AC-15 | `test_pagination_stops_at_max` | Yes: 7 rows, exactly 2 list calls, 7 get calls |
| AC-22 | `test_since_last_uses_history`, `test_since_last_expired` | Yes: history ids only and no list call; on 404, full list and the message. Does not assert the position after the fallback |
| AC-25 | `test_purge_boundaries` | Yes: dry run deletes nothing; only files older than 30 days deleted; symlink, files outside the pattern, history and audit untouched; audit count |
| AC-37 | `test_since_last_truncated_keeps_position` | Yes: 2 rows, message printed, history file bytes unchanged |
| AC-13(c) | `test_live_error_translation` | Partly. Stub `HttpError` sets `resp.status` and `reason` the way the real class does. `RefreshError` strings are made up (A-2) |
| AC-21 | `test_symlink_history_refused` | Yes: exit 3, target unchanged, no get call, audit `unsafe_path` |

`--max` 0 and 501 give exit 2 (`cli.py:51-58`, `test_max_bounds`). Backoff values are fixed at base 1, doubling, cap 32, 5 attempts (`gmail_client.py:122-132`).

### Only verifiable live
- The real `RefreshError` text for `invalid_grant` and `unauthorized_client` (A-2, L-5), and whether `RefreshError.retryable` is set.
- Whether `history.list` returns `messagesAdded` for messages deleted since (R1-2).
- Whether `getProfile.emailAddress` is the primary address. An allowlisted alias would be refused as `mailbox_mismatch`; that fails closed, but should be noted in the README.
- Real response shapes compared with `fixtures/inbox.json` (A-3, L-6), including `messages.list` with no `messages` key on an empty result (handled: `or []`).
- 403 usage-limit reasons and the 404 on stale history in practice.
- That the Admin console delegation entry lists only `gmail.readonly` (L-11).

### Tests run
`cd /home/claude/sutra/prototypes/pulse && python3 pulse_test.py`: 87 tests, OK, 1 skipped, 2.5 s.

### Earlier findings
None (first round).

## Round 2  (2026-11-19, commit 6fb10f4)
Verdict: **Changes requested**

All 13 round 1 findings are fixed, and both Majors were confirmed by running them again. The fix for R1-8 introduced one regression: when `PULSE_OUT_DIR` is itself a symlink, purge silently stops deleting, while fetch still writes there. That breaks the retention guarantee without telling the user. It is a one-line fix. Severity uses P0-P3 from this round on (round 1's Major = P1, Minor = P2, Nit = P3). New: 0 P0, 0 P1, 1 P2, 3 P3.

### Findings
| ID | Sev | File:line | Finding | Evidence | Suggested fix |
|---|---|---|---|---|---|
| R2-1 | P2 | `prototypes/pulse/store.py:123` | A regression from the R1-8 fix. `purge` now checks `PULSE_OUT_DIR` with `lstat`, so if the configured folder is a symlink (for example `~/.sutra-pulse/out` pointing to another disk), purge returns `[]` and prints "Deleted 0 files". `mailbox_dir` (`store.py:42`, `os.makedirs`) still follows that link and writes mail there. Old files are then kept forever, and the audit records `purged: 0`. At bafb85b the same setup deleted the file. | Scratch run: `out -> real/`, a mock fetch, then a 2020-01-01 file placed in `real/_mock/ana@example.test/`. At HEAD, `purge` printed "Deleted 0 files" and the file was kept. At bafb85b (`git archive`), the same command printed "Deleted 1 files". No test covers a symlinked OUT_DIR. | Resolve `out_dir` once (`os.path.realpath`; `config.py` already computes `real_out`) and use that path for both writing and purging. Keep `lstat` for `_mock/` and the mailbox folders. The other option is to refuse a symlinked OUT_DIR with `unsafe_path` in every command. Either way, fetch and purge must agree. Add a test. |
| R2-2 | P3 (unverified) | `prototypes/pulse/live_client.py:54-58`, `errors.py` `RATE_LIMIT_403` | The R1-4 routing reads the reason from `error_details[0]["reason"]` only. As I recall the googleapiclient source, `HttpError` fills `error_details` from `error.details` before `error.errors`. If a Gmail 403 includes a `details` array (`google.rpc.ErrorInfo`), the reason is the uppercase form, for example `RATE_LIMIT_EXCEEDED`. That does not match `rateLimitExceeded`, so the error falls through to `access_denied`. This fails closed (no retry, wrong hint), so it is low risk. | googleapiclient is not installed here and there is no network, so I could not check its source or a real Gmail response. Documented Gmail 403 examples carry only `errors[]`, and those match. | At live step L-5 or L-6, record a real 403 body. Then match case-insensitively across every `error_details` entry, including ErrorInfo `RATE_LIMIT_EXCEEDED` and `RESOURCE_EXHAUSTED`. |
| R2-3 | P3 | `docs/ai/pulse-gmail-reader/architecture.md:287`, `:394` | Both lines still say an unknown `RefreshError` maps to `unauthorized_client`. R-24 replaced that with `token_error`. implementation.md lists this as a known gap, but architecture.md is the design of record. | Lines read at HEAD. | Change both lines to `token_error` (exit 4), and note that a retryable refresh error is retried and then becomes `server_error`. |
| R2-4 | P3 | `prototypes/pulse/cli.py:272` | The start-up hint prints only when the fallback list had no filter. If someone follows the README with `--since-last --since 1d` and that day holds more than `--max` messages, they see only "Stopped at --max, position not saved", with no next step. | Code reading. `query` is set from `--since`, so `fallback and not query` is false. | When a filtered fallback stops at `--max`, also print "use a shorter window or a higher --max". |

### Round 1 findings
| ID | Status | Evidence |
|---|---|---|
| R1-1 | Fixed | Mock: plain `fetch --query from:nobody --max 500` and a plain unfiltered fetch create no `history.mock.json`. `--since-last --since 3650d` saves `2000` and prints the "did not match --query/--since was not read" note. `test_plain_fetch_never_moves_position` (4 variants plus an existing file that stays byte-identical) and `test_filtered_fallback_saves_with_note` assert this. |
| R1-2 | Fixed | The round 1 stub, given a key with `token_uri` (scratchpad `stub404_r2.py`): run 1 and run 2 both exit 0, `ok1` written, "Skipped 1 deleted messages", saved position moves 100 to 200, audit `skipped: 1`. Mock scenario `history_deleted`: 2 rows and "Skipped 2 deleted messages". In `find`, the deleted id is cached as `None` and counted once. A 404 on `getProfile` or `messages.list` is still `internal` (`live_client.py` `_exec`). |
| R1-3 | Fixed | `_is_network` covers `OSError`, `TransportError` and `HttpLib2Error`, then retries and exits with `network_error` (exit 5). `test_live_network_errors` runs 5 exception types, each with 5 attempts, delays `[1,2,4,8]`, no "Unexpected error", and a retry that then succeeds. An SSL certificate failure (an `OSError`) is also retried and gets the network message. That message names proxy and firewall, so this is acceptable. |
| R1-4 | Fixed (see R2-2) | 403 `rateLimitExceeded`/`userRateLimitExceeded` becomes `TransientError(429)`. Mapper and live tests cover both. |
| R1-5 | Fixed | `retryable` is honoured. Unknown token errors become `token_error`. The `invalid_grant` text names a revoked key. `test_live_refresh_errors` checks that the SENTINEL text is not shown and that a non-retryable error is tried once. Real token strings still need L-5. |
| R1-6 | Fixed | The pre-check needs non-empty string `client_email`, `private_key` and `token_uri`. A `ValueError` from the credentials builder becomes `key_unreadable` (`from None`). `test_live_bad_pem_is_key_unreadable` asserts that the SENTINEL text is in none of stdout, stderr or the audit log. google-auth's `MalformedError` subclasses `ValueError`, so it is caught too. |
| R1-7 | Fixed | `git check-ignore --no-index`: `fixtures/sa-key.json`, `fixtures/k.pem`, `key.pem`, `x.p12`, `a.key`, `keys/sa.json`, `.env` and `out/x.jsonl` are ignored. The three named fixtures and `.env.example` are not. |
| R1-8 | Fixed, regression R2-1 | Purge is limited to `<out>/<mailbox>/` and `<out>/_mock/<mailbox>/`, one level deep, real folders only. `test_purge_only_own_layout` covers 6 stray locations and a symlinked mailbox folder. `PULSE_OUT_DIR` set to `$HOME` or `/` exits 2 (mock run). The `realpath` check also catches `~/sub/..`. |
| R1-9 | Fixed (documented, design kept) | README section "Incremental reads", plus the hint (mock run printed it). L-8 updated. I accept keeping R-7: saving after a truncated list would skip the unread remainder. See R2-4. |
| R1-10 | Fixed | Mock run with a saved position and `--query` printed "--query/--since were not applied", and the audit `query` is null. On the expiry fallback, `query` is restored. |
| R1-11 | Fixed | `>=2.0.0,<3` for both packages. The bounds are unverified (no network). The code uses `getattr(e, "retryable", False)`, so older google-auth 2.x versions without that attribute are safe. |
| R1-12 | Fixed | `PULSE_MOCK_SCENARIO=_note` gives exit 2, `config_invalid`. |
| R1-13 | Fixed | `_paged_ids` is shared. The dead branch is gone (argparse limits the commands). `load_history` has one `except`. |

### The developer's other choices
| Choice | Judgement |
|---|---|
| First-run save on a filtered `--since-last`, with a note | Agree. It matches the round 1 suggestion, and the note is explicit. |
| New `network_error` (exit 5) and `token_error` (exit 4) | Agree. Each has its own message and fails closed. A retryable token error that is exhausted becomes `server_error`, which is fine. |
| 403 `dailyLimitExceeded` is `rate_limited` with no retry | Agree. Retrying could not succeed within 15 s, and "Try again tomorrow" is the right advice. Subject to the same caveat as R2-2. |
| R1-9 kept as documented, not changed in code | Agree, with R2-4 as a small follow-up. |
| Audit gains a 12th field, `skipped` | Fine. It holds counts only. Rows written before the change have 11 fields and nothing reads the log yet. |

### Privacy and safety re-check
| Check | Result |
|---|---|
| Allowlist and domain | Unchanged by this fix-up. Not re-tested beyond the suite (102 tests). |
| Audit content | 6 mock rows, keys are exactly the 12 schema fields, no subject, sender or snippet. Exception text from keys and tokens is suppressed (SENTINEL tests). |
| File modes | Folders 0700 (`out`, `_mock`, mailbox, `state`). Files 0600 (output, `audit.jsonl`, `history.mock.json`). |
| Purge scope | Narrower and safe, apart from R2-1, which errs on the side of not deleting. |
| Key ignore rules | See R1-7. |
| Spec coverage | AC-39 to AC-49 each map to a named test, except AC-49, which is checked by a test that reads `requirements.txt`. No regression test covers a symlinked OUT_DIR (R2-1). |

### Tests run
- `cd prototypes/pulse && python3 pulse_test.py`: 102 tests, OK (1 skipped: the read-only folder test, root user), 2.4 s. `git status --porcelain` afterwards: empty.
- Removed test lines in the diff: 5, each replaced by a stricter or updated assertion (`token_error`, the `token_uri` fixture, AC-23 now runs `--since-last`). No assertion was weakened.
- Mock CLI in a scratch HOME/out/state: plain and filtered fetch (no state), the start-up hint, the filtered fallback save, a saved position with `--query`, `history_deleted`, `_note`, OUT_DIR set to `$HOME` and to `/`, modes, audit.
- `stub404_r2.py` (live `LiveClient` and the real `cli.main`, 404 on get): see R1-2.
- Symlinked OUT_DIR purge at HEAD compared with bafb85b: see R2-1.

### Earlier findings
R1-1 to R1-13: fixed. R1-8's fix introduced R2-1, which is open.
