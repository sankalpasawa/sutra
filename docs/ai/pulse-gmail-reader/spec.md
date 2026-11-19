# Spec: Sutra Pulse step 1, read-only Gmail reader
Status: Refined   |   Task: pulse-gmail-reader   |   Date: 2026-11-19

## Revisions (solution-architect, 2026-11-19)
| # | Change | Why |
|---|---|---|
| R-1 | Q-1..Q-5 answered by the user; moved to "Decisions" (DEC-1..DEC-5). Open questions table now empty | User accepted defaults |
| R-2 | Mock mode always uses domain `example.test` and `fixtures/allowlist.txt`; live values are ignored in mock | Contradiction: FR-4 says mock works with the same `.env`, but a real `PULSE_DOMAIN` would refuse every fixture mailbox |
| R-3 | Check order rewritten: argument parse, config, audit open, mailbox policy, rules, key file, Google imports, profile. Key file checks moved before Google imports | `key_missing`/`key_unreadable` are stdlib checks and must be testable without Google libs (AC-13) |
| R-4 | Audit rule clarified: errors before the audit log is open (`usage`, `config_*`, `audit_unavailable`) write no row; everything after writes exactly one | FR-27 ("every invocation after argument parsing") conflicted with FR-28 and with config errors that make the audit path unknown |
| R-5 | New codes: `unsafe_path` (exit 3) for a symlink at an output/state path; `internal` (exit 1) for unexpected errors | FR-21 required a refusal but named no code; unhandled exceptions had no exit code |
| R-6 | `--mailbox` format validated at parse time (`usage`): lowercase after trim, `^[a-z0-9._%+-]+@[a-z0-9.-]+$` | Mailbox becomes a directory name; blocks `/` and `..` in paths |
| R-7 | FR-23: historyId not saved when a run stops at `--max`; prints "Stopped at --max, position not saved" | Saving after a truncated `--since-last` run would silently skip the rest |
| R-8 | Mock history state kept in `history.mock.json` | A mock run must never move a live mailbox's saved position |
| R-9 | Fixture inbox needs 12+ messages (was 10+); scenarios selected by new key `PULSE_MOCK_SCENARIO`; `PULSE_DEBUG` added to config table | AC-15 needs 12; FR-29 required selection "without editing code" but named no mechanism |
| R-10 | List page size fixed: request `maxResults = min(remaining, 100)`; mock pages capped by fixture `page_size` | Makes AC-15 deterministic; 100 is Gmail's default, 500 the max (Google docs) |
| R-11 | Backoff fixed: base 1 s, doubling, cap 32 s, no jitter, `Retry-After` ignored; AC-14 delays exactly 1,2,4,8 | AC-14 allowed "or the chosen base"; untestable as written |
| R-12 | AC-13 split: mock scenarios test the CLI path; a pure mapper function is unit-tested for live error shapes | Mock cannot prove live mapping; A-2 stays unverified until a key exists |
| R-13 | No service-account fixture file in the repo; tests write a fake key into a temp dir | Removes the PROTO-004 risk in FR-30 |
| R-14 | Added NFR-9 (tests touch only temp dirs) and NFR-10 (POSIX only: `fcntl`, `O_NOFOLLOW`) | Implicit before; Windows would fail at import |
| R-15 | `find` output also de-duplicated by `id` per file | Same rule as fetch; was unstated |
| R-16 | FR-1 and FR-32 now require the allowlist approval and owner-notice rule, retention, owner and approver | DEC-3, DEC-4 |
| R-17 | A-1 verified: Google docs say a stale `startHistoryId` "typically returns an HTTP 404" and the app "should perform a full sync" | developers.google.com/gmail/api/v1/reference/users/history/list |
| R-18 | Added AC-35..AC-38 for R-5, R-6, R-7; AC-21 and AC-27 extended | Every new rule needs a test |
| R-19 | Added Q-6: creation guard blocks `.gitignore` / `.env.example` as a new kind | Found while planning T1; needs a user ruling |

## Revisions (developer, fix-up 1 after review round 1, 2026-11-19)
| # | Change | Why |
|---|---|---|
| R-20 | FR-23: only `fetch --since-last` saves a position. A plain fetch (with or without `--query`/`--since`) never reads or changes it. A `--since-last` fallback list that was filtered still saves, and prints that earlier mail outside the filter is not covered. AC-23 now uses `--since-last`; AC-39 added | Review R1-1: a filtered plain fetch moved the position and later `--since-last` runs silently skipped mail |
| R-21 | FR-22a added: 404 on `messages.get` skips and counts the message; audit row gains a 12th field `skipped`; mock scenario `history_deleted`; AC-40 added | Review R1-2: one deleted message ended the run and, on `--since-last`, blocked every later run until the history expired |
| R-22 | New code `network_error` (exit 5). Network failures during token refresh or a request are retried like 5xx; FR-14 extended; AC-41 added | Review R1-3: they exited `internal` with no retry |
| R-23 | 403 with reason `rateLimitExceeded` or `userRateLimitExceeded` is retried like 429; 403 `dailyLimitExceeded` is `rate_limited` with no retry (retrying cannot help); AC-42 added | Review R1-4: usage limits were `access_denied` with advice to enable the API |
| R-24 | Token errors: `RefreshError.retryable` is retried, then `server_error`; unknown non-retryable token errors get new code `token_error` (exit 4) instead of `unauthorized_client`; `invalid_grant` message names a revoked or deleted key; AC-43 added | Review R1-5: transient token failures got delegation advice and no retry |
| R-25 | Key pre-check also requires `token_uri`; a `ValueError` from building credentials (bad PEM, missing field) is `key_unreadable` without the exception text; AC-44 added | Review R1-6: such keys exited `internal` |
| R-26 | FR-2: only the three named fixture JSON files are re-included (not `fixtures/*.json`); `*.pem`, `*.p12`, `*.key` ignored; AC-45 added | Review R1-7: a key dropped in `fixtures/` could be committed |
| R-27 | `purge` (and the automatic purge) only looks one level inside `<OUT_DIR>/<mailbox>/` and `<OUT_DIR>/_mock/<mailbox>/`; `PULSE_OUT_DIR` resolving to home or `/` is `config_invalid` for every command; AC-46 added | Review R1-8: purge walked the whole OUT_DIR tree, so a mis-set OUT_DIR could delete unrelated dated files |

## Problem
An internal tool needs to read selected mailboxes in the company Google Workspace domain, read-only. Domain-wide delegation lets one service account open any mailbox in the domain; Google does not limit it per mailbox. So the tool itself must limit which mailboxes are opened, why, and what is kept. Credentials (admin-approved key file, domain) arrive later, so step 1 must be complete and tested offline.

## Goals
| # | Goal |
|---|---|
| G-1 | Read mail from allowlisted mailboxes via a service account, scope `gmail.readonly` only |
| G-2 | Never open the wrong mailbox (lesson: `marketplace/feedback-inbox/0039-miss-no-account-identity-verification-before-inbox-operation.md`) |
| G-3 | Keep the minimum: metadata by default, retention, output outside the repo |
| G-4 | Every access has a stated reason and an audit row |
| G-5 | Fully usable and tested in mock mode before credentials exist; switching to live needs only `.env` values |

## Non-goals
- J2 integration, or any change under `prototypes/j2/`.
- Writing to Gmail (send, label, delete, mark read). Any scope other than `https://www.googleapis.com/auth/gmail.readonly`.
- Downloading attachment contents.
- CI workflow; root `.gitignore` changes.
- OAuth user consent flow (only service account + delegation).
- Live performance targets (not measurable until a key exists).
- Enforcing audit-log retention in code (DEC-1; documented only in step 1).
- Windows support (NFR-10).

## Users
| User | Need |
|---|---|
| Builder (company employee) | Build and test now in mock mode; run live later |
| Workspace admin | Clear setup steps; confidence the tool is read-only and limited to allowlisted mailboxes |
| Mailbox owners (data subjects) | Only allowlisted mailboxes read, told in writing first, minimum kept, deleted after retention, every read audited |

## Decisions (user, 2026-11-19)
| ID | Decision | Where it lands |
|---|---|---|
| DEC-1 | Audit log kept 365 days. `purge` does not touch it in step 1; enforcement is a follow-up | CHARTER.md, README.md |
| DEC-2 | Keep `snippet` (and `subject`) in metadata mode; revisit before J2 integration | A-5; CHARTER.md data section |
| DEC-3 | Workspace admin approves every allowlist entry; each mailbox owner is told in writing before the first read. A written rule, not enforced in code | CHARTER.md, README.md, header comment in `fixtures/allowlist.txt` |
| DEC-4 | CHARTER.md owner: Kaivan Shah. Approver: the Workspace admin | CHARTER.md |
| DEC-5 | `--max` hard cap 500 | NFR-5 |

## Current behaviour
| Fact | Evidence |
|---|---|
| `prototypes/pulse/` does not exist | `ls prototypes/` shows only `j2` (checked 2026-11-19) |
| Creation guard is in hard mode: a new file needs domain, charter and session placement; a CHARTER.md up the tree satisfies domain and charter | `.claude/creation-guard-mode` = `hard`; `marketplace/plugin/hooks/creation-guard.sh:44,49-52,74` |
| Stdlib `.env` loader; skips blanks and `#` lines; strips quotes; does not override a non-empty shell value | `prototypes/j2/llm.py:21-34` |
| Root `.gitignore` does not ignore `.env` | analysis.md; `prototypes/j2/.gitignore:1-4` is the only `.env` rule |
| Tests are plain scripts run directly, not pytest | `prototypes/j2/change_test.py:1-22` |
| Privacy principles: minimise, 30d default retention, 0600 perms, symlink refusal, fail closed | `os/charters/PRIVACY.md:14-23` |
| PROTO-004 blocks key-shaped strings at write time | `os/charters/SECURITY.md:31,49`; pattern at `marketplace/plugin/hooks/keys-in-env-vars.sh:69` |
| Append-only log with `O_APPEND` + `fcntl.flock` | `marketplace/plugin/sutra-ui/shadow_ledger.py:191-199` |
| No Google auth or Gmail API code exists in source | analysis.md |
| PyYAML is only a `sutra-pro` dependency | `sutra-pro/pyproject.toml:33` |
| `history.list` with a stale `startHistoryId` returns 404; `maxResults` default 100, max 500 | developers.google.com/gmail/api/v1/reference/users/history/list (read 2026-11-19) |

## Configuration
Read from the process environment, then `prototypes/pulse/.env` for keys not set (or empty) in the shell (same rule as `prototypes/j2/llm.py:21-34`). `.env.example` lists every key with an empty or fake value.

| Key | Default | Live | Mock | Validation / error |
|---|---|---|---|---|
| `PULSE_MOCK` | unset (live) | - | `1` enables | Only `1` / `0` / unset accepted, else `config_invalid` |
| `PULSE_SA_KEY_PATH` | empty | required | ignored | Empty: "Add PULSE_SA_KEY_PATH to prototypes/pulse/.env, or set PULSE_MOCK=1 to use the fixture inbox." |
| `PULSE_DOMAIN` | empty | required | ignored; always `example.test` | Lowercase domain, no `@` |
| `PULSE_ALLOWLIST` | empty | required | ignored; always `fixtures/allowlist.txt` | Path; existence checked at policy step (FR-9) |
| `PULSE_OUT_DIR` | `~/.sutra-pulse/out` | used | used (`_mock/` subdir) | Created 0700 if missing. Must not resolve to the home folder or `/` (`config_invalid`, R-27) |
| `PULSE_STATE_DIR` | `~/.sutra-pulse/state` | used | used | Created 0700 if missing; holds `audit.jsonl`, `history.json`, `history.mock.json` |
| `PULSE_RETENTION_DAYS` | `30` | used | used | Integer 1..3650, else `config_invalid` |
| `PULSE_MOCK_SCENARIO` | `default` | ignored | used | Must be a key in `fixtures/scenarios.json`, else `config_invalid` |
| `PULSE_DEBUG` | unset | used | used | `1` prints stack traces on stderr; never prints config values |

## Commands
Common to `check`, `fetch`, `find`:
- `--mailbox` required, trimmed and lowercased, must match `^[a-z0-9._%+-]+@[a-z0-9.-]+$` (else `usage`).
- `--reason` required, 10..500 chars after trimming (else `usage`).
- Order, stopping at the first failure:
  1. Parse arguments (`usage`).
  2. Load config (`config_missing`, `config_invalid`).
  3. Open and lock-test the audit log (`audit_unavailable`). From here on, exactly one audit row is written whatever happens.
  4. Mailbox in domain (`wrong_domain`), then in allowlist (`not_allowlisted`).
  5. `find` only: load and validate the rules file (`rules_invalid`).
  6. Live only: key file exists (`key_missing`), readable service-account JSON (`key_unreadable`), permission warning (FR-34).
  7. Live only: import Google libraries (`deps_missing`).
  8. Fetch the profile; its email must equal `--mailbox` (`mailbox_mismatch`).
  9. Command work.
- No Google call happens before step 8.
- In mock mode, stdout's first line contains `MOCK MODE`.

### Exit codes and error codes
| Exit | Error code | Cause | Message must say |
|---|---|---|---|
| 0 | `ok` | Success | - |
| 1 | `internal` | Unexpected exception | "Unexpected error"; stack trace only with `PULSE_DEBUG=1` |
| 2 | `usage` | Bad/missing argument, reason length, bad mailbox format, `--max` out of range | Which argument and the valid form |
| 2 | `config_missing` | Required live key empty | "Add <KEY> to prototypes/pulse/.env" |
| 2 | `config_invalid` | Value fails validation | Key name and expected form |
| 2 | `rules_invalid` | Rules file unreadable, bad JSON, bad regex, unknown field | File, rule id, problem |
| 2 | `deps_missing` | Live mode, Google libs not installed | "pip install -r requirements.txt" |
| 3 | `wrong_domain` | Mailbox not `@<domain>` (exact, no subdomains) | Mailbox and configured domain |
| 3 | `not_allowlisted` | Mailbox not in allowlist, or allowlist missing/unreadable | Mailbox and allowlist path |
| 3 | `mailbox_mismatch` | Profile email differs from requested | Both addresses; nothing read |
| 3 | `audit_unavailable` | Audit log cannot be opened/locked/written, or is a symlink | Path; nothing read |
| 3 | `unsafe_path` | Output file, its mailbox dir, or history state file is a symlink | Path; nothing written there |
| 4 | `key_missing` | Key path does not exist | Path; "check PULSE_SA_KEY_PATH" |
| 4 | `key_unreadable` | Not readable or not valid service-account JSON (needs `type: service_account` and non-empty `client_email`, `private_key`, `token_uri`), or google-auth cannot load it (bad PEM) (R-25) | Path; never file contents or the library's error text |
| 4 | `unauthorized_client` | Delegation not set, wrong client ID, or scope not exactly gmail.readonly | Admin console path + client ID + scope to grant |
| 4 | `invalid_grant` | Mailbox not in domain, suspended, deleted, key revoked or deleted, or clock skew | Those causes |
| 4 | `token_error` | Token refused for a reason that is not `invalid_grant` or `unauthorized_client`, and not marked retryable (R-24) | Key may be revoked or deleted; delegation help; never the raw error text |
| 4 | `access_denied` | 403 from Gmail (API not enabled, policy), other than the usage-limit reasons under `rate_limited` | "Enable the Gmail API in the GCP project" and other causes |
| 5 | `rate_limited` | 429, or 403 `rateLimitExceeded`/`userRateLimitExceeded`, after all retries; 403 `dailyLimitExceeded` at once (R-23) | Attempts made (or daily limit); try later |
| 5 | `server_error` | 5xx, or a token error marked retryable (`RefreshError.retryable`), after all retries (R-24) | Attempts made |
| 5 | `network_error` | Google unreachable after all retries: token refresh `TransportError`, `httplib2` errors, socket errors and timeouts (R-22) | "Could not reach Google", attempts made, check the network |

Messages are one or two plain-English sentences on stderr, no stack trace unless `PULSE_DEBUG=1`.

### `check`
| | |
|---|---|
| Input | `--mailbox`, `--reason` |
| Google calls | `users.getProfile` only |
| Output (stdout) | Opened mailbox (profile email), messages total, threads total, mode |
| Writes | Audit row only |
| Errors | All common ones |

### `fetch`
| Input | Default | Rule |
|---|---|---|
| `--query "<gmail search>"` | none | Passed to Gmail as-is |
| `--since Nd\|Nh` | none | N is 1..3650 (d) or 1..87600 (h); adds `newer_than:N<d\|h>`; other forms are `usage` |
| `--max N` | 50 | 1..500; stop after N messages, no further page requests |
| `--full` | off | Adds `body_text` |
| `--since-last` | off | Use saved historyId for this mailbox |

Behaviour:
- Without `--full`, messages are requested with `format=metadata` and headers `From`, `To`, `Cc`, `Subject`; no body is requested. With `--full`, `format=full`.
- Effective query: `(<query>) newer_than:<since>` when both given; either alone when one is given; none otherwise.
- Pagination follows page tokens until `--max` or the end. Each list request asks for `min(remaining, 100)` results.
- `--since-last`: list message IDs added since the saved historyId via `history.list` (`historyTypes=messageAdded`). If none saved: do a normal list and print "No saved position, did a full list". If Google returns 404 (history expired): do a normal list and print "Saved position expired, did a full list". `--query`/`--since` apply to the fallback list only.
- After a successful `--since-last` run, save the historyId taken from the profile at step 8 (so mail arriving mid-run is not skipped next time), unless the run stopped at `--max` with more results available; then print "Stopped at --max, position not saved" and keep the old value. A fetch without `--since-last` never saves or changes the position (R-20). If the `--since-last` fallback list (no position, or 404) used `--query`/`--since`, the position is still saved and stdout says that earlier mail outside the filter was not read and later `--since-last` runs will not return it.
- Live state lives in `history.json`, mock state in `history.mock.json`.
- Automatic purge runs after step 4 and before step 8 (see `purge`).
- Output: JSONL rows appended to `<OUT_DIR>/<mailbox>/<YYYY-MM-DD>.jsonl` (UTC run date; mock: `<OUT_DIR>/_mock/<mailbox>/...`). File 0600, new dirs 0700. IDs already in the file are not written again.
- Stdout: count written and file path. No mail content on stdout.

### `find`
| Input | Default | Rule |
|---|---|---|
| `--rules <file.json>` | required | Schema below |
| `--since`, `--max`, `--full` | as `fetch` | Same meaning; `--max` applies per rule |

Behaviour:
- For each rule: list with the rule's `gmail_query` (combined with `--since`), or with `--since` alone if the rule has none; then apply local `keywords` / `regex` to the rule's `fields`. A rule with only `gmail_query` matches every returned message.
- A message matches a rule if any keyword or any regex hits any listed field. `fields_hit` lists the fields that hit.
- Keywords: case-insensitive substring. Regex: Python `re`, case-insensitive. All rules validated at step 5, before any Google call.
- A rule whose `fields` include `body_text` without `--full` is `rules_invalid` ("rule <id> needs --full").
- One output row per matching message (merged across rules): the fetch row plus `rules_hit` (rule ids) and `fields_hit`. Written to `<OUT_DIR>/<mailbox>/<YYYY-MM-DD>.find.jsonl` (mock: under `_mock/`), 0600, de-duplicated by `id`. Stdout: count per rule and file path.
- Does not read or change saved historyId. Automatic purge runs as for `fetch`.
- No keyword or pattern is hard-coded in the tool.

Rules format: JSON. Reason: tests and mock mode are stdlib only, and YAML would add PyYAML as a dependency for one small file. Each rule has a `description` field in place of YAML comments.
```json
{"rules": [
  {"id": "invoice-due", "description": "Invoices mentioning a due date",
   "gmail_query": "subject:invoice", "keywords": ["due date"], "regex": ["INV-\\d{4}"],
   "fields": ["subject", "snippet"]}
]}
```
Allowed rule keys: `id`, `description`, `gmail_query`, `keywords`, `regex`, `fields`; any other key is `rules_invalid`. Allowed `fields`: `from`, `to`, `cc`, `subject`, `snippet`, `attachments.name`, `body_text`. Default `["subject", "snippet"]`. `id` unique, `[a-z0-9-]{1,40}`. At least one of `gmail_query`, `keywords`, `regex` required.

### `purge`
| | |
|---|---|
| Input | `[--dry-run]` |
| Effect | Deletes dated files directly inside Pulse's own mailbox dirs, `<OUT_DIR>/<name@domain>/` and `<OUT_DIR>/_mock/<name@domain>/` (folder names match the `--mailbox` format), whose filename date is more than `PULSE_RETENTION_DAYS` days before today (UTC); removes mailbox dirs left empty. Looks nowhere else and no deeper. Does not follow symlinks (R-27) |
| Not touched | Audit log, history state, files not matching `YYYY-MM-DD.jsonl` or `YYYY-MM-DD.find.jsonl` |
| Output | Files deleted (or would delete) and count |
| Audit | One row, `mailbox` null, `count` = files deleted (0 on dry run) |
| Automatic | Also runs inside `fetch` and `find` (logged in that command's row as `purged`) |
| Config | Needs only `PULSE_OUT_DIR`, `PULSE_STATE_DIR`, `PULSE_RETENTION_DAYS`; works in live mode with no key configured |

## Data formats
### Mail row (fetch / find)
| Field | Type | Notes |
|---|---|---|
| `id`, `thread_id` | string | Gmail IDs |
| `from` | string | Decoded header (RFC 2047) |
| `to`, `cc` | list of string | Decoded, split on top-level commas; empty list if absent |
| `date` | string | Gmail `internalDate`, ISO 8601 UTC |
| `subject` | string | Decoded; `""` if absent |
| `snippet` | string | As returned by Gmail (DEC-2) |
| `labels` | list of string | Label IDs |
| `attachments` | list of `{name, mime, size}` | Parts with a filename; never contents or attachment IDs. Empty in metadata mode if Gmail returns no parts |
| `body_text` | string | Only with `--full`. `text/plain` part preferred; else HTML with tags, `script`/`style` removed and entities decoded. Max 20,000 chars |
| `body_truncated` | bool | Only with `--full` |
| `rules_hit`, `fields_hit` | list of string | `find` only |

### Audit row (`<STATE_DIR>/audit.jsonl`, append-only, 0600, exclusive `flock` per write, kept 365 days by policy, DEC-1)
| Field | Notes |
|---|---|
| `ts` | ISO 8601 UTC |
| `os_user` | Login name of the process user |
| `mode` | `live` / `mock` |
| `command` | `check` / `fetch` / `find` / `purge` |
| `mailbox` | Requested mailbox, or null for purge |
| `query` | Effective Gmail query, or null |
| `rules_file` | Path, `find` only, else null |
| `reason` | As given; null for purge |
| `count` | Messages returned/matched, or files purged |
| `purged` | Files purged automatically, `fetch`/`find` only, else null |
| `skipped` | Messages skipped because `messages.get` returned 404 (deleted since listed), `fetch`/`find` only, else null (R-21) |
| `result` | `ok` or an error code from the table above |

Never in an audit row: mail fields (subject, from, snippet, body, attachment names), key contents, tokens. One row per invocation that reaches step 3 (R-4), including refusals and errors.

### History state (`history.json` live, `history.mock.json` mock, in STATE_DIR, 0600, replaced atomically via temp file + `os.replace`)
`{"<mailbox>": {"history_id": "<string>", "updated": "<ISO 8601 UTC>"}}`

## Functional requirements
| ID | Requirement |
|---|---|
| FR-1 | `prototypes/pulse/CHARTER.md` exists before any other file in the folder: purpose, scope, data handled (incl. snippet, DEC-2), retention (output 30 d default, audit 365 d, DEC-1), allowlist approval and owner-notice rule (DEC-3), owner Kaivan Shah and approver Workspace admin (DEC-4), non-goals |
| FR-2 | `prototypes/pulse/.gitignore` ignores `.env`, `.env.*` except `.env.example`, every `*.json` except the three named fixtures (`fixtures/inbox.json`, `fixtures/scenarios.json`, `fixtures/rules.sample.json`), `*.pem`, `*.p12`, `*.key`, `out/`, `state/`, `.venv/`, `__pycache__/` (R-26) |
| FR-3 | Config loads per the Configuration table; a non-empty shell value wins over `.env` |
| FR-4 | Live command with an empty required key exits 2 `config_missing` naming that key; the same `.env` with `PULSE_MOCK=1` works (R-2) |
| FR-5 | Mock mode imports no `google*` module and opens no network socket |
| FR-6 | Live mode imports Google libraries only at step 7; missing libs give `deps_missing` |
| FR-7 | The only OAuth scope requested is `https://www.googleapis.com/auth/gmail.readonly`, with the subject set to `--mailbox` |
| FR-8 | Mailbox outside the domain is refused (`wrong_domain`) before any Google call |
| FR-9 | Mailbox not in the allowlist is refused (`not_allowlisted`) before any Google call. Allowlist: one email per line, trimmed, case-insensitive, blank and `#` lines ignored. Missing/unreadable allowlist refuses all |
| FR-10 | `--reason` missing, under 10 or over 500 chars exits 2 `usage` for check/fetch/find |
| FR-11 | check/fetch/find fetch the profile first and refuse with `mailbox_mismatch` (case-insensitive compare) if it differs; no messages read |
| FR-12 | `check` prints profile email, message total, thread total; makes no call other than getProfile |
| FR-13 | Each Google error in the error table maps to its code, exit code and message |
| FR-14 | 429, 5xx and network failures are retried with exponential backoff, max 5 attempts per request, then `rate_limited` / `server_error` / `network_error` (R-22) |
| FR-15 | Listing paginates and stops at `--max` without requesting further pages |
| FR-16 | `fetch` without `--full` requests metadata only and rows contain no `body_text` |
| FR-17 | `fetch --full` adds `body_text`; HTML-only mail yields text without tags |
| FR-18 | Attachment entries carry name, mime, size only |
| FR-19 | Non-English and RFC 2047 encoded headers decode to correct Unicode |
| FR-20 | Output path, naming, 0600/0700 modes and mock `_mock/` subdir as specified; no duplicate IDs in one file |
| FR-21 | Writes refuse to follow a symlink at the output file, mailbox dir, audit log or history file path (`unsafe_path`, or `audit_unavailable` for the audit log) |
| FR-22 | `--since-last` uses saved historyId; no saved id or 404 falls back to a full list with the stated message |
| FR-22a | A 404 on `messages.get` (message deleted after it was listed) skips that message without retry, counts it, prints "Skipped N deleted messages" (count only), and records N in the audit row `skipped`. The run still succeeds and `--since-last` still saves its position. A 404 on `getProfile` or `messages.list` stays `internal` (R-21) |
| FR-23 | After a successful `fetch --since-last` the start-of-run historyId is saved to the mode's state file, except when stopped at `--max` with more available. A fetch without `--since-last` never changes the saved position (R-20) |
| FR-24 | `find` loads JSON rules, validates all before any Google call, and outputs matches with `rules_hit` and `fields_hit` |
| FR-25 | `purge` deletes only output files older than retention, and only inside Pulse's own mailbox dirs (R-27); `--dry-run` deletes nothing; audit/state untouched |
| FR-26 | Automatic purge runs inside `fetch` and `find` before the profile call |
| FR-27 | Every invocation that reaches step 3 appends exactly one audit row with the schema above |
| FR-28 | If the audit log cannot be opened or locked, the command exits `audit_unavailable` before any Google call |
| FR-29 | Fixtures: `fixtures/inbox.json` in Gmail API response shape with 12+ synthetic messages covering plain, HTML-only, attachment, 3-message reply thread, non-English subject/body, and one matching `fixtures/rules.sample.json`; `fixtures/scenarios.json` with history, expired-history, deleted-message history (R-21), mismatched-profile, 429-then-ok, 5xx-exhausted, and each auth error; selected by `PULSE_MOCK_SCENARIO` |
| FR-30 | Fixtures use only `example.test` addresses, fake names, `+91 00000 xxxxx` phone numbers, and no strings matching the PROTO-004 pattern. No service-account file in the repo; tests create a fake one in a temp dir |
| FR-31 | `pulse_test.py` is a stdlib-only plain script, runs in mock mode, prints pass/fail per test, exits non-zero on any failure |
| FR-32 | `README.md` covers: admin setup (GCP project, enable Gmail API, service account, JSON key stored outside the repo with mode 0600, Admin console > Security > Access and data control > API controls > Domain-wide delegation, client ID + `gmail.readonly` only), the allowlist approval and owner-notice rule (DEC-3), retention (DEC-1), install, mock run, live run, mermaid flow (setup → auth → list → get → parse → store → find), "What changes when the key arrives" |
| FR-33 | Key contents, tokens and `.env` values are never printed, logged or written to output |
| FR-34 | Live mode warns (does not fail) if the key file is readable by group or others |
| FR-35 | `--mailbox` is trimmed, lowercased and format-checked at parse time (`usage`) |
| FR-36 | Unexpected exceptions exit 1 `internal` and still write the audit row if step 3 was reached |

## Non-functional requirements
| ID | Requirement | Check |
|---|---|---|
| NFR-1 | Python 3.11+; mock mode and tests use stdlib only | Test with `google` blocked in `sys.modules` |
| NFR-2 | `python3 pulse_test.py` finishes in under 10 s with no network | Timed run with `socket.socket` patched to raise |
| NFR-3 | Retry backoff does not sleep for real in tests | Injected sleep; covered by NFR-2 time limit |
| NFR-4 | Max 5 attempts per request; delay 1 s doubling, capped at 32 s, no jitter | Test counts attempts and recorded delays |
| NFR-5 | `--max` hard cap 500 (DEC-5) | Test `--max 501` exits 2 |
| NFR-6 | Two concurrent invocations produce two complete, parseable audit rows | Test with 2 subprocesses |
| NFR-7 | Live deps limited to `google-auth`, `google-api-python-client` in `requirements.txt` | Inspect file |
| NFR-8 | No file in `prototypes/j2/` or root `.gitignore` changes | `git diff --stat main -- prototypes/j2 .gitignore` is empty |
| NFR-9 | Tests write only inside temp dirs; never `~/.sutra-pulse` or the repo | Tests set `HOME`, `PULSE_OUT_DIR`, `PULSE_STATE_DIR` to temp dirs; `git status` clean after run |
| NFR-10 | POSIX only (Linux, macOS); uses `fcntl` and `os.O_NOFOLLOW` | Stated in README |

## Acceptance criteria
Each maps to a test in `pulse_test.py` unless marked (manual).

| AC | Given / When / Then | Maps to |
|---|---|---|
| AC-1 | Given a repo checkout, when listing `prototypes/pulse/`, then CHARTER.md exists, contains owner, approver, retention and the DEC-3 rule, and was added in the first commit for the folder (manual, `git log --diff-filter=A`) | FR-1 |
| AC-2 | Given `.gitignore`, when `git check-ignore` runs on `.env`, `.env.local`, `sa-key.json`, `out/x.jsonl`, `state/audit.jsonl`, then all are ignored and `.env.example` and `fixtures/inbox.json` are not (manual) | FR-2 |
| AC-3 | Given `.env` sets `PULSE_DOMAIN=a.test` and shell sets `b.test`, when config loads, then domain is `b.test`; shell empty, then `a.test` | FR-3 |
| AC-4 | Given empty `PULSE_SA_KEY_PATH` and no mock, when `check` runs, then exit 2, stderr names `PULSE_SA_KEY_PATH`, no audit row; same env plus a real-looking `PULSE_DOMAIN` with `PULSE_MOCK=1` exits 0 for `ana@example.test` | FR-4 |
| AC-5 | Given `google` blocked and sockets disabled, when check, fetch, fetch --full, find, purge run in mock, then all exit 0 | FR-5, NFR-1, NFR-2 |
| AC-6 | Given live mode with Google libs blocked and a valid fake key file, when `check` runs, then `deps_missing`, exit 2 | FR-6 |
| AC-7 | Given live mode with stubbed credentials and service builders, when `check` runs, then the requested scopes equal exactly `[gmail.readonly]` and subject equals `--mailbox` | FR-7 |
| AC-8 | Given mailbox `x@other.test` or `x@sub.example.test`, when any read command runs, then `wrong_domain`, exit 3, zero client calls | FR-8 |
| AC-9 | Given allowlist with `# c`, blank line, ` Ana@Example.test `, when `ana@example.test` is requested, then allowed; `bob@example.test` refused `not_allowlisted`; missing allowlist file refuses all (live mode, refused before key checks) | FR-9 |
| AC-10 | Given no `--reason`, `--reason "short"` or a 501-char reason, when check/fetch/find runs, then exit 2 `usage` | FR-10 |
| AC-11 | Given scenario `mismatch`, when check/fetch/find runs, then `mailbox_mismatch`, exit 3, no output file, no list call | FR-11 |
| AC-12 | Given the default scenario, when `check` runs, then stdout has the profile email and the fixture's message and thread totals, and the only call recorded is `get_profile` | FR-12 |
| AC-13 | (a) For each of `unauthorized_client`, `invalid_grant`, `access_denied` scenarios, `check` gives the listed exit code, code in audit row, and message key phrase. (b) In live mode, a missing key path gives `key_missing` and a non-JSON or non-service-account file gives `key_unreadable`, with no file contents in output. (c) The mapper turns sample live error shapes (token error strings, HTTP 403/404/429/5xx) into the right codes | FR-13 |
| AC-14 | Given 429 twice then success, when fetch runs, then exit 0 and 3 attempts recorded; given 5xx always, then `server_error` after 5 attempts and recorded delays exactly `[1, 2, 4, 8]` | FR-14, NFR-3, NFR-4 |
| AC-15 | Given 12+ fixture messages and mock page size 5, when `fetch --max 7`, then 7 rows and exactly 2 list pages requested | FR-15 |
| AC-16 | Given default fetch, then every row lacks `body_text` and every `get_message` call used `metadata` | FR-16 |
| AC-17 | Given `--full`, then the HTML-only fixture's `body_text` contains no `<` tags or script text and has decoded entities | FR-17 |
| AC-18 | Given the attachment fixture with `--full`, then `attachments` entries have exactly keys `name`, `mime`, `size` | FR-18 |
| AC-19 | Given the non-English fixture with an RFC 2047 subject, then `subject` equals the expected Unicode string | FR-19 |
| AC-20 | Given fetch run twice on the same day in mock, then one file at `<OUT_DIR>/_mock/<mailbox>/<today>.jsonl`, mode 0600, dirs 0700, no duplicate `id` | FR-20 |
| AC-21 | Given the output file path, or the history file path, is a symlink, when fetch runs, then `unsafe_path`, exit 3, symlink target unchanged; given the audit path is a symlink, then `audit_unavailable` | FR-21 |
| AC-22 | Given saved historyId and scenario `default`, when `fetch --since-last`, then only history messages are returned; given scenario `history_expired`, then full list and "expired" message; given no state, then full list and "No saved position" message | FR-22 |
| AC-23 | Given a successful mock `fetch --since-last`, then `history.mock.json` holds the profile historyId for that mailbox, mode 0600, and `history.json` does not exist | FR-23 |
| AC-24 | Given `rules.sample.json`, when `find` runs, then exactly the expected fixture message is output with the expected `rules_hit`; a rules file with a bad regex, unknown key, or `body_text` without `--full` gives `rules_invalid` and zero client calls | FR-24 |
| AC-25 | Given files dated today, today-30 and today-31 with retention 30, when `purge`, then only today-31 is deleted; `--dry-run` deletes none; audit and history files unchanged | FR-25 |
| AC-26 | Given an expired file, when `fetch` runs, then it is deleted and the audit row has `purged: 1` | FR-26 |
| AC-27 | Given one run of each command (success and a post-config refusal), then audit has one row each with all schema fields; a `usage` failure adds no row; no row contains any fixture subject, sender, snippet, body or attachment name | FR-27, FR-33 |
| AC-28 | Given `STATE_DIR` not writable, when fetch runs, then `audit_unavailable`, exit 3, zero client calls | FR-28 |
| AC-29 | Given the fixtures, then a scan finds only `example.test` addresses, phone numbers matching `\+91 00000 \d{5}`, and no strings matching the PROTO-004 pattern | FR-29, FR-30 |
| AC-30 | Given a failing assertion injected, when `python3 pulse_test.py` runs, then exit non-zero (manual) | FR-31 |
| AC-31 | Given README.md, then it contains each FR-32 item and a ```mermaid block with the 7 named steps (test greps for them) | FR-32 |
| AC-32 | Given a fake key file with mode 0644, when a live command runs with stubbed builders, then a permission warning is printed and the command continues | FR-34 |
| AC-33 | Given `--max 0` or `--max 501`, then exit 2 | NFR-5 |
| AC-34 | Given two concurrent mock `check` subprocesses, then the audit log has 2 more rows and each line parses as JSON | NFR-6 |
| AC-35 | Given `--mailbox "../x@example.test"` or `"a/b@example.test"`, then exit 2 `usage` and no directory created | FR-35 |
| AC-36 | Given a client that raises an unexpected exception, then exit 1, stderr has no traceback (without `PULSE_DEBUG`), audit row `result: internal` | FR-36 |
| AC-37 | Given saved historyId and more history messages than `--max`, when `fetch --since-last --max 2`, then 2 rows, "position not saved" printed, saved historyId unchanged | FR-23 |
| AC-38 | Given a test run, then `HOME`, OUT_DIR and STATE_DIR are temp dirs and `git status --porcelain prototypes/pulse` is unchanged after (manual once, then by construction) | NFR-9 |
| AC-39 | Given no state, when `fetch`, `fetch --query`, `fetch --since` run, then no state file is created; given a saved position, a plain `fetch --query` leaves it byte-identical; given `--since-last` with a filtered fallback, the position is saved and the "not read" note printed; an unfiltered fallback prints no note | FR-23, R-20 |
| AC-40 | Given a saved position and history that lists 2 deleted ids among 2 live ones, when `fetch --since-last`, then exit 0, 2 rows, "Skipped 2 deleted messages", audit `skipped: 2`, position saved; the same through `LiveClient` with a 404 on `messages.get`; `find` skips a deleted message the same way; a 404 on `getProfile`/`messages.list` is `internal` | FR-22a, R-21 |
| AC-41 | Given `LiveClient` whose request raises a `TransportError`, an `httplib2` error, `socket.timeout`, `ConnectionResetError` or `OSError`, when `check` runs, then 5 attempts with delays `[1, 2, 4, 8]`, exit 5 `network_error`, stderr "Could not reach Google"; two failures then success gives exit 0 | FR-14, R-22 |
| AC-42 | The mapper turns 403 `rateLimitExceeded`/`userRateLimitExceeded` into a retryable 429 and 403 `dailyLimitExceeded` into `rate_limited`; through `LiveClient`, a persistent 403 `rateLimitExceeded` gives 5 attempts and exit 5 | FR-13, FR-14, R-23 |
| AC-43 | Given a `RefreshError` with `retryable` true, then 5 attempts and `server_error` (one failure then success gives exit 0); an unrecognised non-retryable `RefreshError` gives `token_error`, exit 4, one attempt, and its text is not printed; the `invalid_grant` message says "revoked or deleted" | FR-13, R-24 |
| AC-44 | A key file without `token_uri` (or with it empty) gives `key_unreadable`; a credentials builder raising `ValueError` gives `key_unreadable`, exit 4, the key path in stderr and none of the exception text in stdout, stderr or the audit log | FR-13, FR-33, R-25 |
| AC-45 | `git check-ignore --no-index` ignores `fixtures/sa-key.json`, `fixtures/other.json`, `key.pem`, `fixtures/key.pem`, `cert.p12`, `id.key`, and keeps the three named fixtures, `fixtures/allowlist.txt` and `.env.example` (automated in `test_gitignore_keys`) | FR-2, R-26 |
| AC-46 | Given old dated files at OUT_DIR top level, in `_mock/`, in a folder not named like a mailbox, deeper trees, below a mailbox dir, and behind a symlinked mailbox dir, when `purge`, then only the file directly in a real mailbox dir is deleted; given `PULSE_OUT_DIR` set to home, `~` or `/`, then exit 2 `config_invalid` and no audit row | FR-25, R-27 |

## Assumptions
| ID | Assumption |
|---|---|
| A-1 | Verified (docs, not live): `history.list` returns 404 for a stale `startHistoryId`; the fix is a full sync |
| A-2 | `invalid_grant` vs `unauthorized_client` are distinguishable from the token endpoint error string in `google.auth.exceptions.RefreshError` (unverified until a key exists; live checklist item) |
| A-3 | Mock fixtures in Gmail API response shape keep the parser identical between modes |
| A-4 | UTC is used for output file dates and retention |
| A-5 | `snippet` and `subject` are kept in metadata mode (DEC-2), even though they are mail content |

## Open questions
| ID | Question | Who | Recommended default |
|---|---|---|---|
| Q-6 | The creation guard (hard mode) has no artifact kind for `.gitignore` or `.env.example` (`marketplace/plugin/hooks/creation-guard.sh:84-91`), so creating them exits 2 as "NEW KIND" and asks for a founder ruling. How should they be created? | User (founder) | Rule them as config files for this folder and let the developer create them at T1/T2 under that ruling; do not use the kill-switch. Blocks FR-2 and `.env.example`, not the design |

Carried from impact.md, out of scope for step 1: CI workflow for `prototypes/pulse/**`; root `.gitignore` rule for `**/.env`; audit-log retention enforcement (DEC-1 follow-up).

## Change log
| Date | Change |
|---|---|
| 2026-11-19 | First draft from analysis.md, impact.md and user decisions 1-5 |
| 2026-11-19 | solution-architect: Status Refined. Recorded DEC-1..5 and removed Q-1..5; applied R-1..R-18 (see Revisions). No requirement removed or weakened; FR-27 scope narrowed to "invocations that reach the audit step" because config/usage errors happen before the audit path is known (R-4) |
| 2026-11-19 | developer fix-up 1: R-20 onward (see second Revisions table) after review round 1 |
