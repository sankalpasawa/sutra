# QA security-privacy: bugs, root causes, fixes, tests

QA found 11 bugs on commit 2ae63d11 (1 P1, 2 P2, 8 P3). Branch `feat/sutra-pro-qa-security-privacy`. 10 are fixed, 1 is by design (its limit is now documented).
Every fix has a test that fails without it (checked by putting the old code back) and passes with it. The J2 engine files, the J2 page, J2 prompts, routes and goldens
are untouched.

## P1: a credential typed into the org chat, a team chat or answer, recurring work or a task is stored and echoed in clear

- **Root cause.** Only `/direct` ran the owner's text through the redactor and the egress shapes (`chat_v2._clean`). `POST /api/chats/<id>/messages`, a team answer,
  `POST /api/tasks` and `POST /api/recurring` stored the raw text; the task row, the team's first chat line, `department.json`, the run files (`task.json`, `chat.jsonl`,
  `calls.jsonl`, `events.jsonl`, `report.*`), `inbox.jsonl`, SSE frames, search and, offline, the team name all copied it. A known `.env` value or the launch token typed as a
  team answer or a task reached the same files.
- **Fix** (commit 51e9eab8). One helper, `connectors.egress.scrubbed(text, redact)` (the redactor's values, then every shape, replaced), runs where the words enter:
  `TurnRunner.post_user_message` (stored line, first line of the team, task), `TaskService.deliver_to_department` (answer, follow-up, chat line and inbox; the owner override
  is still read from the raw text because its key is one of the app's secrets), `TaskService._insert` (text and title of every task, `POST /api/tasks` included) and
  `Recurring` create and update. The stored line, the line a model gets and the files of a run are the same text, and nothing is stored in clear in the app's own tables.
- **Engine path (D109).** The egress scrub stays observe-only for J2's prompts, byte-identical, as decided. Two things make it safe without editing J2: the text
  that reaches the engine is already scrubbed where it entered (above), and the missing audit row of a department run is written by the dept-run fix branch
  (`feat/sutra-pro-qa-dept-run`, commit 8d48d688: `port_from_config` sets `router.egress`). I did not repeat that change here, so the two branches do not conflict in
  `connectors/engine_port.py`.
- **Tests.** `tests/orchestrator/test_api_agent.py` (the org chat message, the team's first line and task; a team chat post), `test_tasks.py` (a task's words, title and run files; an answer
  with a shape, a known `.env` secret and the launch token; a follow-up; the owner override still works when its key is one of the secrets), `test_api_tasks.py` (`POST /api/tasks` text and title),
  `test_recurring.py` and `test_api_recurring.py` (the standing words and every task they make). Live check on my own server (offline, private port and data folder): all 24 shapes of QA's
  sample set, a `.env` value and the launch token were sent through the org chat, tasks and a schedule; a scan of the whole data folder found none of them.

## P2: the shape list misses common tokens

- **Root cause.** `SHAPES` matched only `ghp_` and `github_pat_`, `AKIA`, and a narrow `key=value` line.
- **Fix** (commit d0cf8f57). Added: every GitHub token (`gh[pousr]_`, so `gho_` which `gh auth token` prints, `ghs_`, `ghu_`, `ghr_`), AWS `ASIA` temporary ids, Google (`AIza`), GitLab
  (`glpat-`), npm, Hugging Face, SendGrid, `Basic <base64>` (needs a base64-looking value, so the word "basic" is safe), a PGP private-key block, a bearer value with `/`, `~`, `+`, `=`,
  `client_secret=`, `aws_secret_access_key=`, `private_key=`, `passphrase=`, `name: value` and JSON `"name": "value"` forms, symbols in a password, and a bare `token:`/`secret:` whose value holds a digit.
- **Tests.** `tests/connectors/test_egress.py` (each GitHub prefix, AKIA and ASIA, PGP, bearer with `/` or `+`, assigned secrets, Basic auth, and ordinary words that must stay), `test_owner_notes.py` and `test_standing_rules.py` (a note or rule holding each is refused, commit 764d671a).

## P2: restore accepts a crafted archive that plants `.env` and `connectors/bins.json`

- **Root cause.** The archive's own `MANIFEST.json` was treated as the allow-list. A planted `bins.json` was then read by `BinStore` with no re-check, so `{"claude": "/bin/sh"}` ran as the model CLI.
- **Fix** (commit 971dd75c). `ops/backup._manifest_files` refuses every name `create_backup` cannot write (database, the four root files, files in departments, library, agents) before anything is
  changed; `BinStore.stored()` drops an entry `check_path` would refuse, whatever put it there.
- **Tests.** `tests/ops/test_backup.py`, `tests/connectors/test_bins.py`. QA's four archives (`.env`, `bins.json`, symlink, traversal) were run again: each is refused, "Nothing was changed".

## P3 fixed

| # | Bug | Root cause | Fix (commit) | Test |
|---|---|---|---|---|
| 3 | Deeply nested JSON gives 500 on `/api/say`, `/api/engine/settings`, `/api/connectors/policy`, `/api/reset` | `json.loads` raises `RecursionError`, which is not a `ValueError` | `read_json_body` and `parse_policy` catch it: 400 `bad json`, 422 `policy_invalid` (3a44c73d) | `tests/engine/test_engine_api_commands.py`, `tests/orchestrator/test_api_security.py` |
| 4 | No body size limit: 600 MB post grew the server to 2 GB, read before the token check | no limit anywhere but `/api/schemas/validate` | `BodyLimitMiddleware` in `main.py`, behind the Host guard: a declared `Content-Length` over 2 MiB is 413 `payload_too_large` before a byte is read, a chunked body is cut off at the cap; the attachment upload keeps room for 20 MB as base64 (3a44c73d) | `tests/orchestrator/test_api_security.py` (middleware unit tests with a receive that fails if called, chunked, whole app, a 3 MB upload still works) |
| 5 | An integer above 2^63 in `after`, `offset`, `since` gives 500 on six list routes | no upper bound; SQLite cannot hold it | `le=2**53 - 1` (as `/api/events` has) on the five query models; `parse_since` accepts up to the year 9999 (3a44c73d) | `tests/orchestrator/test_api_security.py` (9 paths), `test_atoms_usage.py` |
| 6 | Quadratic regex: 20 000 colons after `postgres://` took 2.3 s, 60 000 took 21 s | `[^\s/@]*:[^\s]*@` backtracks with no `@` | the user stops at its first colon, user and password are bounded (256, 1024). The same scan of every other shape found three more quadratic cases (bare `token=` and `secret:` look-ahead, `eyJ` repeated), fixed the same way (d979d719). 60 000-character inputs of every kind now scan in under 0.35 s (only the existing bounded PEM shape is not instant) | `tests/connectors/test_egress.py` (5 timing guards, db-uri semantics, JWT after a label) |
| 8 | `.env` parser misses values with an inline comment or escaped quotes | `value.strip().strip('"').strip("'")` | `config.env_value` reads a line as dotenv tools do; the redactor also keeps the whole-line reading (Docker's `--env-file` keeps comments), so either reading is hidden (e130408b) | `tests/orchestrator/test_config.py` (12 line forms, redactor over a real file) |
| 9 | Team names such as Con, Aux, Nul, Prn, Com1, Lpt1 become folder names Windows reserves | `slug_id` has no reserved-name rule | the 22 device names count as taken, so the id is `con-2`, `lpt9-2`, ... (74084285) | `tests/library/test_lib_chart_change.py` |
| 10 | Offline demo: with an owner note saved, task titles read `<words> OWNER NOTES (facts and house rules the` | the demo's regex read the notes block as part of the message | the message ends where the `OWNER NOTES (` block starts (54bc82eb) | `tests/orchestrator/test_agent_demo.py` (decide and assign prompts as the real templates render them) |

## Skipped

- **7. The redactor treats any env var named `*AUTH*` or `*KEY*` as a secret** (P3). By design: D71 and `orchestrator.md` say "name contains KEY, TOKEN, SECRET, PASSWORD or AUTH", the same
  rule as J2's `j2_server.py`, and `test_records.py::test_redaction_rules` pins it on purpose (`KEYBOARD_X` is hidden "as in J2"). Narrowing it would make Pro differ from J2 and could let a real
  secret through. What was wrong is that the limit was not written down: `docs/OPERATIONS.md` section 6 now says it, with how to find and unset the variable. No code changed.

## Other changes and follow-ups

- Docs: `docs/OPERATIONS.md` (restore refuses files a backup never writes; the credential shapes; the two limits of the scrub; the 2 MB body cap) and `docs/TROUBLESHOOTING.md` (a row for `payload_too_large`, 413).
- `payload_too_large` is answered in the standard envelope but is not added to the closed `STATUS_BY_CODE` (`test_records.py` pins that list); the library API and the connectors API already use their own codes the same way.
- The offline demo now names a team from the scrubbed words, so a message that starts with a key gives a team called "Redacted Openai Key ...". Cosmetic and offline only.
- A route that takes a body model still parses it before `require_token` runs (a nested or invalid body is 400 or 422, not 401). The body cap now bounds the cost of that; reordering the dependency is a framework-level change left alone.
- A team folder that already exists under a reserved name (made on macOS or Linux, restored on Windows) is not renamed; only new ids avoid the names.
- J2's own code: nothing in it was changed. If a secret appears in what J2's agents write on their own (not the owner's words), the D109 audit row of the dept-run branch is the record.

## Verification

Commands and pass counts are in the answer of the run that wrote this note (tests touched, `node --test tests/ui/js/*.test.js`, the docs, traceability, ownership and layout tests,
`tests/library` on its own, `tests/connectors/test_env_process.py` was not needed: no connector environment code changed).
