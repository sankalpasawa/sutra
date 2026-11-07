# Troubleshooting

Start with `sutra-pro doctor` (add `--offline` to skip the CLI and browser probes): it names what is wrong and a fix. For the app's own failure
cases there is one entry below per failure code F1 to F10 and one per doctor check, then the error codes the API and the connectors use.
Related: [GETTING-STARTED.md](GETTING-STARTED.md), [OPERATIONS.md](OPERATIONS.md), [ENVIRONMENT.md](ENVIRONMENT.md).

Where to look first: the line in `<data>/logs/server.log` (every error page and every response carries an `X-Request-Id` that is also in the log), the team's
`run.stderr.log` in its run folder, and the diagnostics zip of `/console` (Health, Download diagnostics) when you want to send a report.

## 1. The failures F1 to F10

Each entry: what you see, what the app did about it, what you do.

### F1 Claude or Codex cannot be reached
- **You see:** "I can't reach Claude or Codex right now (hint). Nothing was changed." in the org chat, a Retry button, and the request marked as an error. The cause is a CLI that is missing, signed out, out of quota, or no connector at all.
- **The app:** checks the connectors before it stores your message (a 503 with `provider_unavailable` or `cli_missing`), changes nothing on the chart, and does not retry in the middle of a turn.
- **Do:** run `sutra-pro doctor`. Missing CLI: install it. The app looks on `PATH` and in the folders installers use (`~/.local/bin`, `~/.claude/local`, Homebrew, npm, yarn, bun, Volta, pnpm, mise, asdf, nodenv, n, fnm and every `~/.nvm` node version); it never runs your shell. If it still says "not installed", type the full path (`which claude` in Terminal prints it) in Settings, Connectors, Choose the file: it is checked, kept in `<data>/connectors/bins.json` and survives a relaunch. "Claude Desktop is installed, but Sutra needs Claude Code": Claude Desktop is a different product with no `claude` command; install Claude Code. Signed out: `claude auth login` or `codex login`
  (or Settings, Connectors, Sign in). Out of quota: the chip says "Out of quota until 14:05" and each usage window has a bar with its reset time in Settings, on the pill and in `/console` (kept across a restart in `<data>/connectors/quota.json`); wait for the reset, or sign in to the other CLI; calls move to it by themselves when the policy allows. Then press Retry. To look around with no model, start with `--offline`.

### F2 The model's answer was unusable
- **You see:** nothing, usually; the plan line is the normal template text, and the chart change says it was planned by keywords.
- **The app:** timeouts (120 s for the chat agent), text that is not JSON, a wrong shape, or a rule violation are tried up to 3 times per stage with the reasons fed back, then the keyword fallback plans it.
- **Do:** nothing. If it keeps happening, raise `SUTRA_CHAT_TIMEOUT`, check `claude --version` against the tested version (`doctor`, check `claude`), and look at the connector codes in section 3 (`invalid_json`, `timeout`, `reply_truncated`).

### F3 The fallback finds no team
- **You see:** a card "Which team fits best?" with choices.
- **Do:** pick one, or say what you want in other words.

### F4 The chart changed while the agent was thinking
- **You see:** "The chart changed while I was thinking. Please send that again."
- **The app:** two changes raced; nothing was applied (code `stale_chart`, HTTP 409).
- **Do:** send the message again.

### F5 The change could not be saved
- **You see:** "I could not save that. Nothing was changed."
- **The app:** a database or folder error inside the change; the whole change was undone and a failed row is in the change log.
- **Do:** run `sutra-pro doctor` (checks `disk`, `data_dir`, `database`), free space or fix permissions, send it again.

### F6 A team will not start
- **You see:** a note "could not start: ..." on the team with Retry; the team's node turns red with `!`. The run ended `crashed` with the code `start_failed`. The chart change stays; other teams go on.
- **Do:** read the text after "could not start": it names the cause (a missing run folder, a bad task file, a CLI that is not on `PATH` for the engine). Run `sutra-pro doctor`, fix, press Retry. The team's `run.stderr.log` has the engine's own message.

### F7 A run crashed or vanished
- **You see:** "Something went wrong. Try again." in the team chat, Retry, a red node. Teams that waited on it are cancelled. The code is `process_gone` when the process died without saying why, or the connector's code when a model call ended it.
- **Do:** Retry starts a fresh run (it does not resume the broken one); the new run is told how the earlier attempts ended, which done-when items their audit had met, what they left open and the end of a crash's error log. Look at `run.stderr.log` and `trace.jsonl` in the run folder. A run that went silent for 30 seconds is flagged on its step node; the server settles it at the next start.

### F8 The app was closed while teams worked
- **You see:** after the next start, the team chat offers to continue; the node is dashed "left open".
- **The app:** live runs were stopped cleanly (the work so far is kept), or, after a crash of the server itself, settled at the next start.
- **Do:** write in the team's chat; the next request is a follow-up that starts from the old records. No data is lost either way (see [OPERATIONS.md](OPERATIONS.md), section 2).
- **A request you had just sent in the org chat:** if the app stopped before Sutra answered it, the bubble comes back marked as failed with Retry, and Sutra says "The app stopped before I finished your request. Please try again." Press Retry (it runs your newest request again), or send it again. Check the org chart first when the request was about changing it: a change made before the stop stays.

### F9 A bad line in a run's event file
- **You see:** nothing.
- **The app:** a line that is not valid or has an unknown type is skipped and noted in the log; the rest of the file is read.
- **Do:** nothing, unless a team looks stuck; then look for `skipped` lines in `server.log`.

### F10 The database is busy
- **You see:** "Try again in a moment." (HTTP 503 `store_busy`).
- **The app:** SQLite stayed locked for longer than 5 seconds; nothing was half written.
- **Do:** try again. If it repeats, check for a second Sutra Pro on the same folder (`sutra-pro status`), for a backup or an editor holding `db.sqlite3`, and for a data folder on a network disk (use a local one).

## 2. The doctor checks

`sutra-pro doctor` prints `[ ok ]`, `[WARN]`, `[FAIL]` or `[skip]` for each check, with a fix on the line. Exit code 1 means at least one `[FAIL]`.

### Doctor: `python`
- Python older than 3.11. Fix: `uv venv --python 3.11` and reinstall, or use the Mac app (it carries its own Python).

### Doctor: `data_dir`
- **fail** "exists and is not a folder" or "is not writable": move the file away, `chmod u+rwx` the folder, or point `SUTRA_DATA_DIR` at another folder.
- **warn** "is mode ...": the folder holds your work and should be private. Fix: `chmod 700 <data>`.

### Doctor: `disk`
- Less than 1 GB free where the data folder is. Runs write screenshots and logs. Free some space, or `sutra-pro prune`.

### Doctor: `database`
- **fail** "cannot be opened": the file is not a Sutra database, or is damaged. Move it away, or restore a backup (`sutra-pro restore FILE`).
- **fail** "schema version N is newer than this app's": a newer version wrote it. Install that version, or restore a backup made with this one.
- **ok** "will be upgraded": normal after an update; a pre-upgrade copy is made first.

### Doctor: `env_file`
- **warn** "mode": the `.env` file holds secrets and must be mode 600. Fix: `chmod 600 <file>`.
- Missing is fine: it is only needed for the override key and live email. `sutra-pro config init` writes a template. In a checkout the file is `<project>/.env`, installed it is `<data>/.env`, or the file `SUTRA_ENV_FILE` names.

### Doctor: `claude`
- **fail/warn** "not found on PATH or in the usual install folders": install the Claude CLI, or choose its file in Settings, Connectors. "Claude Desktop is installed, but Sutra needs Claude Code": install Claude Code (Desktop has no `claude` command). "Not signed in": `claude auth login`. "Signed in with an API key, which is refused": sign out, then log in with your subscription account (D34).
- **warn** "tested with 2.1.308": another CLI version works in most cases; if calls fail, install the tested one.
- It is a warning, not a failure, while Codex works; it fails only when neither CLI is usable.

### Doctor: `codex`
- The same, for `codex`: install it, `codex login` (ChatGPT sign-in). A warning while Claude works.

### Doctor: `gh`
- Optional; only the GitHub tool uses it. "skip: not installed" is normal. "not signed in": `gh auth login`.

### Doctor: `chrome`
- **warn** "not found": Audit judges from code only, with no screenshots, and the app opens your default browser. Install Google Chrome, or `sutra-pro config set chrome /path/to/chrome`.
- **warn** "J2_CHROME points to ... which does not exist": fix the path the same way, or unset it.

### Doctor: `port`
- **fail** "every port from 8780 to 8799 is busy": stop the programs that use them, or set `SUTRA_PORT`.
- **warn** "SUTRA_PORT=N is busy or not a port": unset it or free the port; the server refuses to start on a busy exact port. `lsof -i :8780` shows who holds it.

### Doctor: `instance`
- **warn** "already runs on ...": a second launch only opens the first. `sutra-pro open` shows it, `sutra-pro stop` stops it. If `sutra-pro stop` says the pid is gone yet the folder is locked, another process holds `app.lock`; look at `lsof <data>/app.lock`.

### Doctor: `library`
- **warn** "N seed template(s) are missing": a newer version ships templates your library lacks. Fix: `sutra-pro config sync-library` (adds only what is missing, never overwrites).

### Doctor: `browser`
- **warn** "only Chrome is measured": your default browser is not Chrome and Chrome is not installed. The app works, but the pages were checked in Chrome only. Install Chrome, or open the address in Chrome yourself.

### Doctor: `settings`
- **fail** with a file name: an `engine.json` is not valid JSON, has an unknown field or a value out of range. Fix the file, or set the field again: `sutra-pro config set FIELD VALUE`.
- **fail** "send_mode is live but J2_SMTP_... is not set": put the five `J2_SMTP_*` lines in the `.env` file, or `sutra-pro config set send_mode dry-run`.

## 3. Error codes

The API answers errors as `{"error": {"code", "message", "details"}}`; the code decides the HTTP status.

| Code | HTTP | Meaning and what to do |
|---|---|---|
| `bad_token` | 401 | the page's write token is stale, usually after a restart. Reload the page |
| `bad_host` | 400 | the request came with a Host other than `127.0.0.1` or `localhost`. Use that address |
| `bad_origin` | 403 | a write came from a page of another origin. Use the app's own page |
| `validation` | 422 | the request is malformed; `details.violations` lists each path and reason |
| `payload_too_large` | 413 | the request body is over 2 MB (a chat attachment may be 20 MB). Send less; nothing was read or changed |
| `rules` | 422 | the org chart rules refused a well-formed change; the message says which rule |
| `not_found` | 404 | no such team, task, node or run |
| `busy` | 409 | the team already runs a task, or the task has ended. Wait, or stop it first |
| `stale_chart` | 409 | the chart changed under the request (F4). Send it again |
| `already_decided` | 409 | that change was already approved or declined |
| `read_only` | 403 | you wrote into a chat that is a log (a function or step chat). Write in the team chat |
| `too_many_pending` | 429 | one request is being planned at a time and too many wait behind it. Try again when one is done |
| `provider_unavailable` | 503 | no connector can serve (F1) |
| `cli_missing` | 503 | the CLI is not installed (F1) |
| `store_busy` | 503 | the database was locked for 5 s (F10) |
| `internal` | 500 | a bug; the response carries a request id, find it in `server.log` and send the diagnostics zip |

Model-call errors (the connector layer), as shown by `/console`, Settings, Connectors and the team's `run.stderr.log`. "Falls back" means the router tries the next provider.

| Code | Kind | Meaning and what to do |
|---|---|---|
| `no_model` | unavailable | no provider is enabled or installed. Run `doctor`, or start with `--offline` |
| `cli_missing` | unavailable | the CLI is not on `PATH` (F1). Falls back to the other provider |
| `cli_flag_unsupported` | unavailable | the installed CLI lacks a flag the app needs. Install the tested version |
| `not_signed_in` | auth | sign in (`claude auth login`, `codex login`). Falls back |
| `account_blocked` | auth | the account needs attention (organisation, hold, verification). Fix it on the provider's site |
| `quota` | quota | the plan's usage window is used up; the reset time is shown. Falls back |
| `rate_limited` | quota | too many calls at once; retried by itself |
| `overloaded` | unavailable | the provider is busy; retried by itself |
| `server_error` | unavailable | the provider had an error; retried by itself |
| `timeout` | timeout | a call took too long (`timeout_s` of the policy, 900 s by default; 120 s for the chat agent) or went silent for 120 s. Retry |
| `crashed` | unavailable | the CLI process died. Retry; update the CLI if it repeats |
| `protocol_error` | unavailable | the CLI printed something the app does not understand. Install the tested version |
| `provider_error` | unavailable | any other error from the provider; the text is in the log |
| `model_not_found` | unavailable | the model name is unknown to the CLI. Check `SUTRA_CLAUDE_MODEL` and your policy file |
| `session_lost` | unavailable | the CLI no longer has the conversation to resume. The call starts over |
| `empty_reply` | bad_output | the model answered nothing; retried |
| `structured` | bad_output | the answer did not fit the required shape after repair rounds. Retry |
| `invalid_json` | bad_output | the answer was not JSON after repair rounds. Retry |
| `reply_truncated` | bad_output | the answer was cut off. Retry; a smaller request may help |
| `invalid_request` | bad_output | the request itself was refused by the model. Rephrase it |
| `envelope_exceeded` | quota | one request used more calls than its envelope allows (6 by default). Split the request |
| `cancelled` | unavailable | the call was cancelled because you stopped the run |
| `policy_invalid` | unavailable | `<data>/connectors/policy.json` is not valid; the default is used. Fix or remove the file |

Run end codes in `run.ended`: `start_failed` (F6), `process_gone` (F7) and `internal` (an engine bug; read `run.stderr.log`), besides the connector codes above.

## 4. Other symptoms

- **The page says the session expired or writes fail with `bad_token`:** the server restarted and issued a new token. Reload the page.
- **The page is blank or half drawn:** use Chrome; it is the only browser the pages were measured in. Check `server.log` for the request id of the failing request.
- **"already running":** a server owns that data folder; `sutra-pro open` opens it, `sutra-pro stop` stops it.
- **The graph does not move:** the live stream is cut and the page polls every 2 seconds; a banner says so. Reload the page, check `sutra-pro status`.
- **A team asks again and again:** answer in the team's chat, not in the org chat; the org chat is for new requests.
- **The chat cannot see my files:** set the Working folder in Settings, Connectors (one folder, read-only, chats only; D121); the chat names it, or says none is set.
- **The desktop app did not update by itself:** it checks about a minute after it starts and every 6 hours, only if Check for updates automatically is on in Settings, About; it installs only a download it could verify, and only when you choose Restart Now or Install on Quit (D124).
- **Everything is red after an update:** run `sutra-pro doctor`, then `sutra-pro restore` the backup you took before the update (see [OPERATIONS.md](OPERATIONS.md), section 4).
