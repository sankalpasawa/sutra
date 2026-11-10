# Environment and settings

Every name the app reads, with its default. Related: [OPERATIONS.md](OPERATIONS.md) (the commands), [GETTING-STARTED.md](GETTING-STARTED.md),
[TROUBLESHOOTING.md](TROUBLESHOOTING.md). `scripts/check_docs.py` fails when a name, a default or a locked flag in the first three tables
below differs from the code, so these tables are the source of truth you can trust.

Three layers carry settings, and each has its own place:

| Layer | Where it is set | Read by | Changes apply |
|---|---|---|---|
| App (`SUTRA_*`) | the process environment, or a flag of `sutra-pro` | the server | at the next start |
| Secrets | `.env` (mode 600) or the process environment | the server (the override key) and the engine (the SMTP login) | at the next start |
| Engine (`J2_*` names, `engine.json` fields) | Settings, Engine; `sutra-pro config set`; the files `<data>/engine.json` and `<data>/departments/<team>/engine.json` | each run, once, at its start | at the next run of that scope |

A flag beats the environment, which beats the default: `--port 9000` beats `SUTRA_PORT=8800`. `sutra-pro config show` prints the effective values and where each came from.
A boolean accepts `1`, `true`, `yes`, `on` and `0`, `false`, `no`, `off`; this document writes `1` and `0`. An empty value counts as not set.

## 1. App settings

| Variable | Field | Default | Meaning |
|---|---|---|---|
| `SUTRA_DATA_DIR` | `data_dir` | `./data` in a checkout, `~/.sutra-pro` installed | where the database, run folders and logs live (flag `--data-dir`) |
| `SUTRA_HOST` | `host` | `127.0.0.1` | `127.0.0.1` or `localhost` only; anything else is refused (D11) |
| `SUTRA_PORT` | `port` | `8780` | an exact port; unset means the first free port from 8780 to 8799 (flag `--port`) |
| `SUTRA_TOKEN` | `token` | random at every launch | the write token (16 to 200 visible characters); it travels in the `X-Sutra-Token` header only and is never written to disk |
| `SUTRA_CONNECTOR` | `connector` | `auto` | `auto` (Claude, then Codex), `claude`, `codex` or `stub` |
| `SUTRA_ENGINE` | `engine` | `process` | `process` (one process per run) or `fake` (tests only) |
| `SUTRA_OFFLINE` | `offline` | `0` | `1`: no model calls, the stub connector and the engine's mock mode (flag `--offline`) |
| `SUTRA_CHAT_TIMEOUT` | `chat_timeout` | `120` | seconds one turn of the chat agent may take (1 to 3600) |
| `SUTRA_CHAT_ATTEMPTS` | `chat_attempts` | `3` | tries per stage of a chat turn (1 to 5) |
| `SUTRA_MAX_RUNS` | `max_runs` | `3` | teams running at the same time (1 to 64); more wait in a queue |
| `SUTRA_MAX_LIVE` | `max_live` | `12` | most live engine processes, those waiting for you included; at least `SUTRA_MAX_RUNS` |
| `SUTRA_WATCH_MS` | `watch_ms` | `400` | how often the server reads each run's event file, in milliseconds (20 to 10000) |
| `SUTRA_LIVE` | `live` | `0` | `1`: allow the tests marked `live` that call the real CLIs |
| `SUTRA_ENV_FILE` | `env_file` | `<project>/.env` in a checkout, `<data>/.env` installed | the file that holds the secrets of section 3 |

Flags with no variable: `--no-browser`, `--browser auto|chrome|default`, `--exit-when-stdin-closes`, `--verbose`.

## 2. Engine settings

These are the J2 flags, each with J2's own default (the pacing delay is 0 because the connector layer paces). The variable name is what J2 reads and what
`sutra-pro config show` prints; in `engine.json` and in `config set` you use the field name. **Locked** fields are not editable in Settings (they can send mail, run a browser or force a
failure) and change only with `sutra-pro config set`. **Task** fields may also be given by a single request (the eight keys a task may carry); every other field reaches a run only through the
two `engine.json` files. A run does not pass the server's own `J2_*` variables on to its engine process: the files are the way in.

| Variable | Field | Default | Locked | Task | Meaning |
|---|---|---|---|---|---|
| `J2_OUTPUT` | `output` | `auto` | no | yes | what the team builds: `auto` (the engine decides from the brief and the working folder: project work for a project, else the website or the document asked for), `website`, `prd`, `hld`, `lld` or `project` |
| `J2_WORKSPACE` | `workspace` | `auto` | no | no | `auto`: every agent of the engine may read the owner's working folder (project work may change it, within the owner's access setting); `off`: none |
| `J2_FIXES` | `fixes` | `0` | no | yes | `1` turns on the two flow fixes of the J2 loop |
| `J2_BUDGET` | `budget` | `100` | no | yes | starting budget in work credits; a full documents-plus-website run needs 500 or more |
| `J2_BUDGET_CAP` | `budget_cap` | `unset` | no | yes | the most your approvals can raise the budget to; unset means twice the budget |
| `J2_MAX_CYCLES` | `max_cycles` | `6` | no | no | plan, build, audit cycles before Identity asks you what to do |
| `J2_LIMIT_ADD` | `limit_add` | `30` | no | no | credits the "keep working" choice adds when the budget has run out |
| `J2_BARGAIN_MINUTES` | `bargain_minutes` | `15` | no | no | minutes the bargain between two disagreeing functions (J2.c) may take |
| `J2_BARGAIN_CALLS` | `bargain_calls` | `8` | no | no | model calls that bargain may spend |
| `J2_MAX_TURNS` | `max_turns` | `30` | no | no | agent turns per cycle |
| `J2_CHAT_FULL_CHARS` | `chat_full_chars` | `60000` | no | no | above this many characters a chat is given to the model as a summary plus the recent messages |
| `J2_DELAY` | `delay` | `0` | no | no | seconds between model calls (J2 used 2 for free API tiers) |
| `J2_RATES` | `rates` | `1` | no | yes | `0` turns the rate card off |
| `J2_SLIM` | `slim` | `1` | no | yes | builders get their own section plus a short list of the others, not the whole page; `0` turns it off |
| `J2_MEMORY` | `memory` | `1` | no | yes | `0`: lessons and playbooks are neither read nor written |
| `J2_DECIDE_FOR_ME` | `decide_for_me` | `0` | no | yes | the team answers its own questions with the suggested option and keeps going (the Simple view's Decide for me); `1` turns it on |
| `J2_REALIZATION` | `realization` | `1` | no | no | Adaptation's first plan of a website goes through realization and certainty, and a separate judge scores each workflow |
| `J2_CHANGE` | `change` | `0` | no | no | `1`: the charter of the last full plan is kept and a change request is handled as a change |
| `J2_BOARD` | `board` | `0` | no | no | `1`: the message board between the function nodes |
| `J2_ARTIFACT_SCHEMA` | `artifact_schema` | `0` | no | no | `1`: a builder answers with one JSON object that the three artifact layers check |
| `J2_TEMPLATE_LIBRARY` | `template_library` | `0` | no | no | `1`: each workflow's builder fills a template chosen from the library (implies the artifact schema) |
| `J2_SEND_MODE` | `send_mode` | `dry-run` | yes | no | `dry-run`, `mock` (tests) or `live`; live also needs the SMTP login of section 3 |
| `J2_SEND_CAP` | `send_cap` | `10` | yes | no | at most this many live emails per run |
| `J2_MILESTONE_EMAILS` | `milestone_emails` | `0` | yes | no | `1`: one milestone email per goal reached |
| `J2_TEST_EMAIL` | `test_email` | `unset` | yes | no | the only address a send may go to |
| `J2_TEST_SLACK_TARGET` | `test_slack_target` | `unset` | yes | no | the only Slack target a send may go to |
| `J2_TAP_MIN` | `tap_min` | `44` | no | no | the smallest tap target in pixels that Audit's page check accepts |
| `J2_CHROME` | `chrome` | `unset` | yes | no | path of Chrome for Audit's screenshots; unset means look in the usual places |
| `J2_FORCE_AUDIT_FAIL` | `force_audit_fail` | `0` | yes | no | test switch: Audit fails this many times on purpose |
| `J2_FORCE_AUDIT_NOTE` | `force_audit_note` | `unset` | yes | no | test switch: the text of that forced failure |
| `J2_FORCE_QUESTION` | `force_question` | `unset` | yes | no | test switch: a comma list of functions that must ask one question (mock mode) |
| `J2_MEMORY_TEST_LESSONS` | `memory_test_lessons` | `0` | yes | no | demo switch: Adaptation may read lessons that test runs wrote |

How the layers combine, lowest first: the defaults, `<data>/engine.json`, a `J2_*` variable in the server's environment (development and tests), the team's
`<data>/departments/<team>/engine.json`, and last the eight task keys of one request. The effective values are written to `<run>/settings.json` when the run starts and the engine never re-reads them; the one later write is the Simple view's Decide for me switch, which adds `decide_for_me` to the same file (a running team takes the switch at once, as a line in its inbox).
A value that is not valid (a word that is neither on nor off, a number out of range) is an error naming the layer, not a silent default.

## 3. Secrets: the override key and the SMTP login

Both live in `.env` (`sutra-pro config init` writes the template) or in the real environment, which wins. They are never fields of a settings object, never printed, never in a backup or a diagnostics zip.

| Variable | Default | Meaning |
|---|---|---|
| `J2_OVERRIDE_KEY` | `unset` | the owner override key: chat overrides such as `budget +N`, `ship` and `drop` are accepted only when it is set; read by the server, never passed to a run |
| `J2_SMTP_HOST` | `unset` | the mail server, for live email only |
| `J2_SMTP_PORT` | `unset` | its STARTTLS port, for example 587 |
| `J2_SMTP_USER` | `unset` | the login |
| `J2_SMTP_PASSWORD` | `unset` | the password |
| `J2_SMTP_FROM` | `unset` | the sender address |

`send_mode` set to `live` needs all five SMTP names; `sutra-pro doctor` fails the check `settings` when one is missing.

## 4. Other names the app reads

These are optional, mostly for the Mac launcher, for development and for tests.

| Variable | Default | Meaning |
|---|---|---|
| `SUTRA_BROWSER_APP` | `unset` | another application to open instead of Chrome (an application name on macOS, an executable elsewhere); beaten only by `--browser default` |
| `SUTRA_CLAUDE_MODEL` | `unset` | overrides the model the Claude connector asks for (the policy default is `sonnet`); wins over `CLAUDE_CLI_MODEL` |
| `CLAUDE_CLI_MODEL` | `unset` | the same, under J2's old name |
| `SUTRA_NODES` | `on` | `off` runs the engine without the function-node layer (no atoms); `enforce` is reserved and refused |
| `SUTRA_HOOKS` | `sutra_app.engine.fnodes.layer:factory` | `package.module:function` that builds the engine's hooks (tests) |
| `SUTRA_RECORDS` | `log` | `log` or `strict`: whether a record that fails the library's checks is only logged or refused |
| `SUTRA_RECORDS_HOOK` | `sutra_app.library.records:gate_record` | `package.module:function` that validates records |
| `SUTRA_HEARTBEAT_S` | `5` | seconds between the heartbeat lines of a running engine; a bad value means 5 |
| `SUTRA_DB_RO` | `unset` | path of the database for the read-only Sutra tools; the connectors set it for the tool server they start |
| `SUTRA_MOCK` | `unset` | `1`: the engine plays J2's mock mode (so do `SUTRA_OFFLINE=1` and `STUDIO_MOCK=1`) |
| `SUTRA_FAKE_SCRIPT` | `unset` | the script file of the fake engine process (tests) |
| `SUTRA_J2_CHECKOUT` | `unset` | a J2 checkout whose own page the J2 server adapter may serve (development) |
| `SUTRA_SCHEMA_DIR` | `unset` | where the schema export writes (default `docs/schemas`) |
| `SUTRA_TEMPLATES_DIR` | `unset` | where the generated generic templates go (default `docs/schemas/templates`) |
| `SUTRA_BUNDLE_CACHE` | `unset` | download cache of the Mac and Windows app builders |
| `SUTRA_EXTRA_PATH` | `unset` | Mac launcher and desktop app: extra folders appended to `PATH` so it finds `claude` and `codex` |
| `SUTRA_NO_DIALOG` | `0` | Mac launcher and Windows app: `1` shows no error dialog |
| `SUTRA_NO_TRAY` | `unset` | Windows app: `1` starts it without the notification-area icon (the server then owns the process; quit with `sutra-pro stop`) |
| `SUTRA_PORT_MIN` | `8780` | Mac launcher: first port to try |
| `SUTRA_PORT_MAX` | `8799` | Mac launcher: last port to try |
| `SUTRA_START_TIMEOUT` | `60` | Mac launcher: seconds to wait for `/api/health` |
| `SUTRA_PRO_START_TIMEOUT` | `60` | desktop app: seconds to wait for the server to answer, 1 to 600 (a cold machine that is scanning a fresh install is slow) |
| `SUTRA_PRO_PYTHON` | `unset` | desktop app run from a checkout (`npm start`): the Python that runs the server; default the checkout's `.venv`, else `python3`. An installed app always runs the Python inside it |
| `SUTRA_PRO_DESKTOP` | `unset` | set to `1` by the desktop app in the environment of the server it starts: Settings, About and the welcome card then say the automatic update check applies to this copy (the server itself checks nothing by itself; the app's timer does) |
| `SUTRA_PRO_DEVTOOLS` | `unset` | desktop app: `1` adds View, Toggle Developer Tools to an installed app (a checkout has it) |
| `SUTRA_PRO_SELFTEST` | `unset` | desktop app: `1` runs the self-test and quits with its verdict as the exit status (`scripts/prove_desktop_app.py` does this on the packaged app) |
| `SUTRA_PRO_SELFTEST_DIR` | `<data>/selftest` | desktop app: where the self-test writes `selftest.json` and `selftest.png` |
| `SUTRA_PRO_EXPECT_VERSION` | `unset` | desktop app: the version the self-test requires the server to report |
| `SUTRA_SLOW` | `unset` | `1`: the test suite also runs the tests marked `slow` |
| `SUTRA_BROWSER` | `unset` | `1`: the test suite also runs the tests marked `browser` (they need Chrome) |

The connectors give a run's child processes (the CLIs) one fixed allowlist of environment names: the `SUTRA_*` and `J2_*` names above are not passed on, and neither is any name that looks like a key,
a token or a secret.

## 5. Connector policy

Which provider and model serve a call is a small JSON policy: the app ships a default (Claude `sonnet`, Codex `gpt-5.6-luna`, order Claude then Codex, 900 s timeout, one retry). To change it, put your own at
`<data>/connectors/policy.json`; a policy that does not validate is ignored: the default is used and the reason is reported in the connector status. Tested CLI versions: Claude 2.1.308, Codex 0.146.0; `sutra-pro doctor` warns about any other.
