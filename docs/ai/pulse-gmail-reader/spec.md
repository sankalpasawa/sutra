# Spec: Sutra Pulse step 1, read-only Gmail reader
Status: Draft   |   Task: pulse-gmail-reader   |   Date: 2026-11-19

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

## Users
| User | Need |
|---|---|
| Builder (company employee) | Build and test now in mock mode; run live later |
| Workspace admin | Clear setup steps; confidence the tool is read-only and limited to allowlisted mailboxes |
| Mailbox owners (data subjects) | Only allowlisted mailboxes read, minimum kept, deleted after retention, every read audited |

## Current behaviour
| Fact | Evidence |
|---|---|
| `prototypes/pulse/` does not exist | `ls prototypes/pulse` fails (checked 2026-11-19) |
| Creation guard is in hard mode: new files need a CHARTER.md up the tree | `.claude/creation-guard-mode`; `marketplace/plugin/hooks/creation-guard.sh:50,74` (per analysis.md) |
| Stdlib `.env` loader; skips blanks and `#` lines; does not override a non-empty shell value | `prototypes/j2/llm.py:21-34` |
| Root `.gitignore` does not ignore `.env` | analysis.md; `prototypes/j2/.gitignore:1-4` is the only `.env` rule |
| Tests are plain scripts run directly, not pytest | `prototypes/j2/*_test.py` (e.g. `change_test.py`) |
| Privacy principles: minimise, 30d default retention, 0600 perms, symlink refusal, fail closed | `os/charters/PRIVACY.md:14-23` |
| PROTO-004 blocks key-shaped strings at write time | `os/charters/SECURITY.md:29,49` |
| Append-only 0600 log with file lock exists as a pattern | `marketplace/plugin/sutra-ui/shadow_ledger.py:191` (per analysis.md, not re-read) |
| No Google auth or Gmail API code exists in source | analysis.md |
| PyYAML is only a `sutra-pro` dependency | `sutra-pro/pyproject.toml:33` |

## Configuration
Read from the process environment, then `prototypes/pulse/.env` for keys not set in the shell (same rule as `prototypes/j2/llm.py:21-34`). `.env.example` lists every key with an empty or fake value.

| Key | Default | Live | Mock | Validation / error |
|---|---|---|---|---|
| `PULSE_MOCK` | unset (live) | - | `1` enables | Only `1` / `0` / unset accepted |
| `PULSE_SA_KEY_PATH` | empty | required | ignored | Empty: "Add PULSE_SA_KEY_PATH to prototypes/pulse/.env, or set PULSE_MOCK=1 to use the fixture inbox." |
| `PULSE_DOMAIN` | empty | required | `example.test` if empty | Lowercase domain, no `@` |
| `PULSE_ALLOWLIST` | empty | required | `fixtures/allowlist.txt` if empty | File must exist and be readable |
| `PULSE_OUT_DIR` | `~/.sutra-pulse/out` | used | used (`_mock/` subdir) | Created 0700 if missing |
| `PULSE_STATE_DIR` | `~/.sutra-pulse/state` | used | used | Created 0700 if missing; holds audit log and history state |
| `PULSE_RETENTION_DAYS` | `30` | used | used | Integer 1..3650, else config error |

## Commands
Common to `check`, `fetch`, `find`:
- `--mailbox` required; `--reason` required (10..500 chars after trimming).
- Order before any Google call: config valid → audit log writable → mailbox in domain → mailbox in allowlist → (live) key file readable → profile fetched and its email equals `--mailbox`.
- In mock mode, stdout's first line contains `MOCK MODE`.

### Exit codes and error codes
| Exit | Error code | Cause | Message must say |
|---|---|---|---|
| 0 | `ok` | Success | - |
| 2 | `usage` | Bad/missing argument, reason too short | Which argument and the valid form |
| 2 | `config_missing` | Required live key empty | "Add <KEY> to prototypes/pulse/.env" |
| 2 | `config_invalid` | Value fails validation | Key name and expected form |
| 2 | `rules_invalid` | Rules file unreadable, bad JSON, bad regex, unknown field | File, rule id, problem |
| 2 | `deps_missing` | Live mode, Google libs not installed | "pip install -r requirements.txt" |
| 3 | `wrong_domain` | Mailbox not `@<PULSE_DOMAIN>` (exact, no subdomains) | Mailbox and configured domain |
| 3 | `not_allowlisted` | Mailbox not in allowlist | Mailbox and allowlist path |
| 3 | `mailbox_mismatch` | Profile email differs from requested | Both addresses; nothing read |
| 3 | `audit_unavailable` | Audit log cannot be opened/locked/written | Path; nothing read |
| 4 | `key_missing` | Key path does not exist | Path; "check PULSE_SA_KEY_PATH" |
| 4 | `key_unreadable` | Not readable or not valid service-account JSON | Path; never file contents |
| 4 | `unauthorized_client` | Delegation not set, wrong client ID, or scope not exactly gmail.readonly | Admin console path + client ID + scope to grant |
| 4 | `invalid_grant` | Mailbox not in domain, suspended, deleted, or clock skew | Those causes |
| 4 | `access_denied` | 403 from Gmail (API not enabled, policy) | "Enable the Gmail API in the GCP project" and other causes |
| 5 | `rate_limited` | 429 after all retries | Attempts made; try later |
| 5 | `server_error` | 5xx after all retries | Attempts made |

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
| `--since Nd\|Nh` | none | Adds `newer_than:N<d\|h>`; other forms are `usage` |
| `--max N` | 50 | 1..500; stop after N messages, no further page requests |
| `--full` | off | Adds `body_text` |
| `--since-last` | off | Use saved historyId for this mailbox |

Behaviour:
- Without `--full`, Google is asked for metadata only; no message body is requested.
- Effective query: `(<query>) newer_than:<since>` when both given.
- Pagination follows page tokens until `--max` or the end.
- `--since-last`: list message IDs added since the saved historyId via history. If none saved: do a normal list and print "No saved position, did a full list". If Google returns 404 (history expired): do a normal list and print "Saved position expired, did a full list". `--query`/`--since` apply to the fallback list.
- After success (any mode), save the historyId taken from the profile at the start of the run (so mail arriving mid-run is not skipped next time).
- Automatic purge runs at the start (see `purge`).
- Output: JSONL rows appended to `<OUT_DIR>/<mailbox>/<YYYY-MM-DD>.jsonl` (UTC run date; mock: `<OUT_DIR>/_mock/<mailbox>/...`). File and new dirs 0600 / 0700. Duplicate IDs within one file are not written twice.
- Stdout: count written and file path. No mail content on stdout.

### `find`
| Input | Default | Rule |
|---|---|---|
| `--rules <file.json>` | required | Schema below |
| `--since`, `--max`, `--full` | as `fetch` | Same meaning |

Behaviour:
- For each rule: list with the rule's `gmail_query` (combined with `--since`), or with `--since` alone if the rule has none; then apply local `keywords` / `regex` to the rule's `fields`. A rule with only `gmail_query` matches every returned message.
- Keywords: case-insensitive substring. Regex: Python `re`, case-insensitive. All rules validated before any Google call.
- A rule whose `fields` include `body_text` without `--full` is `rules_invalid` ("rule <id> needs --full").
- One output row per matching message: the fetch row plus `rules_hit` (rule ids) and `fields_hit`. Written to `<OUT_DIR>/<mailbox>/<YYYY-MM-DD>.find.jsonl`, 0600. Stdout: count per rule and file path.
- Does not read or change saved historyId. Automatic purge runs at start.
- No keyword or pattern is hard-coded in the tool.

Rules format: JSON. Reason: tests and mock mode are stdlib only, and YAML would add PyYAML as a dependency for one small file. Each rule has a `description` field in place of YAML comments.
```json
{"rules": [
  {"id": "invoice-due", "description": "Invoices mentioning a due date",
   "gmail_query": "subject:invoice", "keywords": ["due date"], "regex": ["INV-\\d{4}"],
   "fields": ["subject", "snippet"]}
]}
```
Allowed `fields`: `from`, `to`, `cc`, `subject`, `snippet`, `attachments.name`, `body_text`. Default `["subject", "snippet"]`. `id` unique, `[a-z0-9-]{1,40}`.

### `purge`
| | |
|---|---|
| Input | `[--dry-run]` |
| Effect | Deletes `*.jsonl` under OUT_DIR (incl. `_mock/`) whose filename date is more than `PULSE_RETENTION_DAYS` days before today (UTC); removes empty mailbox dirs |
| Not touched | Audit log, history state, files not matching `YYYY-MM-DD*.jsonl` |
| Output | Files deleted (or would delete) and count |
| Audit | One row, `mailbox` null, `count` = files deleted |
| Automatic | Also runs at the start of `fetch` and `find` (logged inside that command's row as `purged`) |

## Data formats
### Mail row (fetch / find)
| Field | Type | Notes |
|---|---|---|
| `id`, `thread_id` | string | Gmail IDs |
| `from` | string | Decoded header (RFC 2047) |
| `to`, `cc` | list of string | Decoded; empty list if absent |
| `date` | string | Gmail internal date, ISO 8601 UTC |
| `subject` | string | Decoded; `""` if absent |
| `snippet` | string | As returned by Gmail |
| `labels` | list of string | Label IDs |
| `attachments` | list of `{name, mime, size}` | Parts with a filename; never contents or attachment IDs |
| `body_text` | string | Only with `--full`. `text/plain` part preferred; else HTML with tags, `script`/`style` removed and entities decoded. Max 20,000 chars |
| `body_truncated` | bool | Only with `--full` |
| `rules_hit`, `fields_hit` | list of string | `find` only |

### Audit row (`<STATE_DIR>/audit.jsonl`, append-only, 0600, exclusive lock per write)
| Field | Notes |
|---|---|
| `ts` | ISO 8601 UTC |
| `os_user` | Login name of the process user |
| `mode` | `live` / `mock` |
| `command` | `check` / `fetch` / `find` / `purge` |
| `mailbox` | Requested mailbox, or null for purge |
| `query` | Effective Gmail query, or null |
| `rules_file` | Path, `find` only |
| `reason` | As given |
| `count` | Messages returned/matched, or files purged |
| `purged` | Files purged automatically, `fetch`/`find` only |
| `result` | `ok` or an error code from the table above |

Never in an audit row: mail fields (subject, from, snippet, body, attachment names), key contents, key path contents, tokens. One row per invocation, including refusals and errors after argument parsing.

### History state (`<STATE_DIR>/history.json`, 0600, replaced atomically)
`{"<mailbox>": {"history_id": "<string>", "updated": "<ISO 8601 UTC>"}}`

## Functional requirements
| ID | Requirement |
|---|---|
| FR-1 | `prototypes/pulse/CHARTER.md` exists before any other file in the folder (purpose, scope, data handled, owner, non-goals) |
| FR-2 | `prototypes/pulse/.gitignore` ignores `.env`, `.env.*` except `.env.example`, `*.json` key-file patterns outside `fixtures/`, `out/`, `state/`, `.venv/` |
| FR-3 | Config loads per the Configuration table; shell value wins over `.env` |
| FR-4 | Live command with an empty required key exits 2 `config_missing` naming that key; mock commands still work with the same `.env` |
| FR-5 | Mock mode imports no `google*` module and opens no network socket |
| FR-6 | Live mode imports Google libraries only when a live command runs; missing libs give `deps_missing` |
| FR-7 | The only OAuth scope requested is `https://www.googleapis.com/auth/gmail.readonly`, with the subject set to `--mailbox` |
| FR-8 | Mailbox outside `PULSE_DOMAIN` is refused (`wrong_domain`) before any Google call |
| FR-9 | Mailbox not in the allowlist is refused (`not_allowlisted`) before any Google call. Allowlist: one email per line, trimmed, case-insensitive, blank and `#` lines ignored. Missing/unreadable allowlist refuses all |
| FR-10 | `--reason` missing or under 10 chars exits 2 `usage` for check/fetch/find |
| FR-11 | check/fetch/find fetch the profile first and refuse with `mailbox_mismatch` (case-insensitive compare) if it differs; no messages read |
| FR-12 | `check` prints profile email, message total, thread total; makes no call other than getProfile |
| FR-13 | Each Google error in the error table maps to its code, exit code and message |
| FR-14 | 429 and 5xx are retried with exponential backoff, max 5 attempts per request, then `rate_limited` / `server_error` |
| FR-15 | Listing paginates and stops at `--max` without requesting further pages |
| FR-16 | `fetch` without `--full` requests metadata only and rows contain no `body_text` |
| FR-17 | `fetch --full` adds `body_text`; HTML-only mail yields text without tags |
| FR-18 | Attachment entries carry name, mime, size only |
| FR-19 | Non-English and RFC 2047 encoded headers decode to correct Unicode |
| FR-20 | Output path, naming, 0600/0700 modes and mock `_mock/` subdir as specified; no duplicate IDs in one file |
| FR-21 | Writes refuse to follow a symlink at the output file, audit log or state file path |
| FR-22 | `--since-last` uses saved historyId; no saved id or 404 falls back to a full list with the stated message |
| FR-23 | After a successful fetch the start-of-run historyId is saved |
| FR-24 | `find` loads JSON rules, validates all before any Google call, and outputs matches with `rules_hit` and `fields_hit` |
| FR-25 | `purge` deletes only output files older than retention; `--dry-run` deletes nothing; audit/state untouched |
| FR-26 | Automatic purge runs at the start of `fetch` and `find` |
| FR-27 | Every invocation after argument parsing appends exactly one audit row with the schema above |
| FR-28 | If the audit log cannot be written, the command exits `audit_unavailable` before any Google call |
| FR-29 | Fixtures: `fixtures/inbox.json` in Gmail API response shape with 10+ synthetic messages covering plain, HTML-only, attachment, 3-message reply thread, non-English subject/body, and one matching `fixtures/rules.sample.json`; plus history fixture, expired-history case, mismatched-profile case, 429-then-ok, 5xx-exhausted, and each auth error; all selectable without editing code |
| FR-30 | Fixtures use only `example.test` addresses, fake names, `+91 00000 xxxxx` phone numbers, and no key-shaped strings; the fixture service-account file (if any) is clearly fake and passes PROTO-004 |
| FR-31 | `pulse_test.py` is a stdlib-only plain script, runs in mock mode, prints pass/fail per test, exits non-zero on any failure |
| FR-32 | `README.md` covers: admin setup (GCP project, enable Gmail API, service account, JSON key stored outside the repo, Admin console > Security > Access and data control > API controls > Domain-wide delegation, client ID + `gmail.readonly` only), install, mock run, live run, mermaid flow (setup → auth → list → get → parse → store → find), "What changes when the key arrives" |
| FR-33 | Key contents, tokens and `.env` values are never printed, logged or written to output |
| FR-34 | Live mode warns (does not fail) if the key file is readable by group or others |

## Non-functional requirements
| ID | Requirement | Check |
|---|---|---|
| NFR-1 | Python 3.11+; mock mode and tests use stdlib only | Test with `google` blocked in `sys.modules` |
| NFR-2 | `python3 pulse_test.py` finishes in under 10 s with no network | Timed run with `socket.socket` patched to raise |
| NFR-3 | Retry backoff does not sleep for real in tests | Covered by NFR-2 time limit |
| NFR-4 | Max 5 attempts per request; delay doubles each retry, capped at 32 s | Test counts attempts and recorded delays |
| NFR-5 | `--max` hard cap 500 | Test `--max 501` exits 2 |
| NFR-6 | Two concurrent invocations produce two complete, parseable audit rows | Test with 2 subprocesses |
| NFR-7 | Live deps limited to `google-auth`, `google-api-python-client` in `requirements.txt` | Inspect file |
| NFR-8 | No file in `prototypes/j2/` or root `.gitignore` changes | `git diff --stat main` |

## Acceptance criteria
Each maps to a test in `pulse_test.py` unless marked (manual).

| AC | Given / When / Then | Maps to |
|---|---|---|
| AC-1 | Given a repo checkout, when listing `prototypes/pulse/`, then CHARTER.md exists and was added in the first commit for the folder (manual, `git log`) | FR-1 |
| AC-2 | Given `.gitignore`, when `git check-ignore` runs on `.env`, `.env.local`, `sa-key.json`, `out/x.jsonl`, `state/audit.jsonl`, then all are ignored and `.env.example` and `fixtures/inbox.json` are not (manual) | FR-2 |
| AC-3 | Given `.env` sets `PULSE_DOMAIN=a.test` and shell sets `b.test`, when config loads, then domain is `b.test` | FR-3 |
| AC-4 | Given empty `PULSE_SA_KEY_PATH` and no mock, when `check` runs, then exit 2, stderr names `PULSE_SA_KEY_PATH`; same env with `PULSE_MOCK=1` exits 0 | FR-4 |
| AC-5 | Given `google` blocked and sockets disabled, when check, fetch, fetch --full, find, purge run in mock, then all exit 0 | FR-5, NFR-1, NFR-2 |
| AC-6 | Given live mode with Google libs blocked, when `check` runs with config set, then `deps_missing`, exit 2 | FR-6 |
| AC-7 | Given live mode with a stubbed credentials builder, when `check` runs, then the requested scopes equal exactly `[gmail.readonly]` and subject equals `--mailbox` | FR-7 |
| AC-8 | Given mailbox `x@other.test` or `x@sub.example.test`, when any read command runs, then `wrong_domain`, exit 3, zero fixture calls | FR-8 |
| AC-9 | Given allowlist with `# c`, blank line, ` Ana@Example.test `, when `ana@example.test` is requested, then allowed; `bob@example.test` refused `not_allowlisted`; missing allowlist file refuses all | FR-9 |
| AC-10 | Given no `--reason` or `--reason "short"`, when check/fetch/find runs, then exit 2 `usage` | FR-10 |
| AC-11 | Given the mismatched-profile fixture, when check/fetch/find runs, then `mailbox_mismatch`, exit 3, no output file, no list call | FR-11 |
| AC-12 | Given the fixture inbox, when `check` runs, then stdout has the profile email and the fixture's message and thread totals, and the only call recorded is getProfile | FR-12 |
| AC-13 | For each of `unauthorized_client`, `invalid_grant`, `access_denied`, `key_missing`, `key_unreadable`: given its fixture, when `check` runs, then the listed exit code, code in audit row, and message containing the key phrase from the error table | FR-13 |
| AC-14 | Given 429 twice then success, when fetch runs, then exit 0 and 3 attempts recorded; given 5xx always, then `server_error` after 5 attempts and delays 1,2,4,8 (or the chosen base, doubling, cap 32) | FR-14, NFR-4 |
| AC-15 | Given 12 fixture messages and page size 5, when `fetch --max 7`, then 7 rows and 2 list pages requested | FR-15 |
| AC-16 | Given default fetch, then every row lacks `body_text` and every get call used metadata format | FR-16 |
| AC-17 | Given `--full`, then the HTML-only fixture's `body_text` contains no `<` tags or script text and has decoded entities | FR-17 |
| AC-18 | Given the attachment fixture, then `attachments` entries have exactly keys `name`, `mime`, `size` | FR-18 |
| AC-19 | Given the non-English fixture with an RFC 2047 subject, then `subject` equals the expected Unicode string | FR-19 |
| AC-20 | Given fetch run twice on the same day in mock, then one file at `<OUT_DIR>/_mock/<mailbox>/<today>.jsonl`, mode 0600, dirs 0700, no duplicate `id` | FR-20 |
| AC-21 | Given the output file path is a symlink, when fetch runs, then it refuses and the symlink target is unchanged | FR-21 |
| AC-22 | Given saved historyId and the history fixture, when `fetch --since-last`, then only history messages are returned; given the expired fixture, then full list and "expired" message; given no state, then full list and "No saved position" message | FR-22 |
| AC-23 | Given a successful fetch, then `history.json` holds the profile historyId for that mailbox, mode 0600 | FR-23 |
| AC-24 | Given `rules.sample.json`, when `find` runs, then exactly the expected fixture message is output with the expected `rules_hit`; a rules file with a bad regex or `body_text` without `--full` gives `rules_invalid` and zero Google calls | FR-24 |
| AC-25 | Given files dated today, today-30 and today-31 with retention 30, when `purge`, then only today-31 is deleted; `--dry-run` deletes none; audit and history files unchanged | FR-25 |
| AC-26 | Given an expired file, when `fetch` runs, then it is deleted and the audit row has `purged: 1` | FR-26 |
| AC-27 | Given one run of each command (success and refusal), then audit has one row each with all schema fields, and no row contains any fixture subject, sender, snippet, body or attachment name | FR-27, FR-33 |
| AC-28 | Given `STATE_DIR` not writable, when fetch runs, then `audit_unavailable`, zero fixture calls | FR-28 |
| AC-29 | Given the fixtures, then a scan finds only `example.test` addresses, phone numbers matching `\+91 00000 \d{5}`, and no strings matching the PROTO-004 patterns | FR-29, FR-30 |
| AC-30 | Given a failing assertion injected, when `python3 pulse_test.py` runs, then exit non-zero (manual) | FR-31 |
| AC-31 | Given README.md, then it contains each FR-32 item and a ```mermaid block with the 7 named steps (test greps for them) | FR-32 |
| AC-32 | Given a fake key file with mode 0644, when a live command runs with stubbed credentials, then a permission warning is printed and the command continues | FR-34 |
| AC-33 | Given `--max 501`, then exit 2 | NFR-5 |
| AC-34 | Given two concurrent mock `check` runs, then the audit log has 2 more rows and each line parses as JSON | NFR-6 |

## Assumptions
| ID | Assumption |
|---|---|
| A-1 | Gmail API `history.list` returns 404 when the start historyId is too old (Google docs; not tested live) |
| A-2 | `invalid_grant` vs `unauthorized_client` are distinguishable from the token endpoint error body (unverified until a key exists) |
| A-3 | Mock fixtures in Gmail API response shape keep the parser identical between modes |
| A-4 | UTC is used for output file dates and retention |
| A-5 | `snippet` and `subject` are kept in metadata mode because the user listed them, even though they are mail content |

## Open questions
| ID | Question | Who | Suggested default |
|---|---|---|---|
| Q-1 | Audit log retention? It holds mailbox names and reasons (personal data) | Workspace admin | Keep 365 days; purge does not touch it in step 1 |
| Q-2 | Should metadata mode drop `snippet` (it is ~200 chars of body)? | Builder + admin | Keep (A-5); revisit before J2 integration |
| Q-3 | Who approves allowlist entries, and are mailbox owners told their mail is read? (Indian DPDP Act may apply; unverified) | Workspace admin / legal | Admin approves; owner notified in writing before first read |
| Q-4 | CHARTER.md owner name | Builder | Builder as owner, admin as approver |
| Q-5 | `--max` cap of 500 enough? | Builder | Yes for step 1 |

## Change log
| Date | Change |
|---|---|
| 2026-11-19 | First draft from analysis.md, impact.md and user decisions 1-5 |
