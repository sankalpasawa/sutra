# Operating Sutra Pro

For the person who runs the app. First time here: [GETTING-STARTED.md](GETTING-STARTED.md). A symptom: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
Every variable and setting: [ENVIRONMENT.md](ENVIRONMENT.md).

## 1. The commands

```bash
sutra-pro [serve] [flags]     # the server (this is what a bare `sutra-pro` does)
sutra-pro doctor              # fourteen checks of the machine and the setup
sutra-pro status              # is it running, where, and is it healthy
sutra-pro stop                # ask the running server to stop
sutra-pro open                # open the browser on the running one
sutra-pro config show         # the effective settings and where each value comes from
sutra-pro backup              # a consistent backup archive
sutra-pro restore FILE        # put a backup back
sutra-pro prune               # remove the bulky evidence of old finished runs
sutra-pro export chart        # the org chart and its change log as JSON
sutra-pro import-old-chats    # bring the old Sutra app's chats in (a dry run unless --apply)
sutra-pro nodes status        # the switch for multi-agent nodes (pause, kill) and the SUTRA_NODES_* settings
```

`python -m sutra_app` is the same program as `sutra-pro`. In a checkout, `scripts/run.sh` and `scripts/stop.sh` do the same with the checkout's own virtualenv.

| Command | Flags | Notes |
|---|---|---|
| `sutra-pro serve` | `--port N`, `--data-dir D`, `--offline`, `--no-browser`, `--browser auto\|chrome\|default`, `--exit-when-stdin-closes`, `--verbose` | no sub-command means serve; `--exit-when-stdin-closes` is for a program that starts the server and keeps its input open (the desktop app): the server stops when that input ends |
| `sutra-pro doctor` | `--data-dir D`, `--json`, `--offline` | exit 0 when nothing failed, 1 when a check failed |
| `sutra-pro status` | `--data-dir D`, `--json` | exit 0 running and healthy, 1 not running or unhealthy |
| `sutra-pro stop` | `--data-dir D`, `--json`, `--wait S` | SIGTERM, then waits `S` seconds (default 20); never SIGKILL |
| `sutra-pro open` | `--data-dir D`, `--json`, `--browser` | needs a running instance |
| `sutra-pro config show` | `--data-dir D`, `--json`, `--dept D` | the effective values and their source |
| `sutra-pro config set FIELD VALUE` | `--data-dir D`, `--json`, `--dept D` | the only way to set a locked engine setting |
| `sutra-pro config init` | `--data-dir D`, `--json`, `--generate-override-key` | writes a commented `.env` template (mode 600); never overwrites |
| `sutra-pro config sync-library` | `--data-dir D`, `--json` | adds what the seed has and the data library lacks (templates, versions, run templates and their folders, provenance keys, runs rows; 81 families, 107 versions and 4 run templates at the 0.5.0 seed) and never overwrites; the server does the same once per seed at start |
| `sutra-pro backup` | `--data-dir D`, `--json`, `--to DIR`, `--no-runs`, `--include-env` | `--include-env` is refused |
| `sutra-pro restore FILE` | `--data-dir D`, `--json` | the server must be stopped |
| `sutra-pro prune` | `--data-dir D`, `--json`, `--older-than AGE`, `--dry-run`, `--yes` | a dry run unless `--yes` |
| `sutra-pro import-old-chats` | `--data-dir D`, `--json`, `--source DIR`, `--apply` | read only on the old folder; a dry run unless `--apply`; the server must be stopped |
| `sutra-pro nodes status` | `--data-dir D`, `--json` | the switch (none, pause or kill), its two files in `<data>/nodes` and the four `SUTRA_NODES_*` settings; changes nothing |
| `sutra-pro nodes pause` | `--data-dir D`, `--json`, `--reason TEXT` | puts the `PAUSE` file there: no new agent starts, the ones that run finish |
| `sutra-pro nodes kill` | `--data-dir D`, `--json`, `--reason TEXT` | puts the `KILL` file there: a running Sutra (with `SUTRA_NODES_V1=1`) stops every agent through its stop ladder (all together: about 12 seconds at most) and starts none until you resume; you can also create the file by hand |
| `sutra-pro nodes resume` | `--data-dir D`, `--json` | removes both files |
| `sutra-pro export chart` | `--data-dir D`, `--json`, `--out FILE` | `--out -` is standard output |
| `sutra-pro export team DEPT` | `--data-dir D`, `--json`, `--out DIR` | a team's last finished run |
| `sutra-pro export usage` | `--data-dir D`, `--json`, `--csv`, `--out FILE` | every usage row |

Exit codes: 0 done, 1 refused or a problem found, 2 usage error (argparse). `--json` prints one JSON document instead of text. The
command-line text is checked against the real `--help` output by `scripts/check_docs.py`, so this table cannot drift without a test failing.

## 2. The data folder

One folder holds everything. Where it is: `SUTRA_DATA_DIR`, else `./data` in a checkout, else `~/.sutra-pro` (an installed app never
reads a checkout's data folder, D88). Everything inside is written with owner-only permissions. Sizes below were measured on a
fresh offline start and one offline (mock) run, and are only a guide; a real run with screenshots and several site versions is larger,
and runs are the part that grows.

```
<data>/
  db.sqlite3  (+ -wal, -shm)         the org chart and its change log, graph, chats, atoms, the Atom log, usage    ~0.3 MB new, grows slowly
  app.lock, app.pid                  the instance lock and "<pid> <port>" of the running server                  tiny
  .env                               optional secrets: the override key and the SMTP login (mode 600)             tiny; in a checkout it is <project>/.env
  engine.json                        optional global engine settings (what `config set` writes)                  tiny
  logs/server.log (+ .1 to .5)       the server log, rotated at 5 MB, five old files kept                         up to 30 MB in all
  backups/                           sutra-pro-backup-*.tar.gz (newest 7 kept) and pre-upgrade-*.sqlite3        0.06 MB for a new folder
  library/                           the template library (index.json and one folder per template)               ~0.5 MB seeded
  types/                             engine-owned: the types a run made (types.local.json, templates/<name>/) and their .lock    tiny
  agents/j2/                         engine-owned: the agent prompts a run reads
  connectors/policy.json             optional connector routing policy (the app ships a default)                 tiny
  connectors/slots/                  with SUTRA_NODES_SLOTS=1: one small empty file for each slot of each provider  tiny
  nodes/tools/<run id>.jsonl         with SUTRA_NODES_V1=1: for each project step, its tool calls (names and kinds only), kept by the step's own host; a record, not a proof   at most about 200 KB each; `prune` removes them with their run (D349)
  departments/<team>/
    department.json                  a readable mirror of the team; the database is the authority                 tiny
    engine.json                      optional per-team engine settings                                            tiny
    page.json, memory/               the team page's since-run mark; lessons and playbooks                        small
    runs/<run id>/                   one folder per run: the team's records, as the J2 prototype writes them
      task.json  inbox.jsonl  events.jsonl  trace.jsonl  snapshot.json  live.json  settings.json  timing.json  autofix.json
      chat.jsonl  calls.jsonl  map.json  report.json  summary.json  goal.json  workflows.json  atoms.json
      run.stdout.log  run.stderr.log
      handoff.json  handoff.accepted.json  verdict.json                  only the run of a project step: its hand-off, the checked copy and the reviewer's verdict
      site/ (page versions, documents, shots/)  artifacts/                                                       ~0.08 MB for a mock run; MBs with screenshots
```

Which files are whose: the **server** is the only writer of the database (D16). Each run is a separate process that writes only
its own run folder. A restart reads those files again and projects them idempotently, so a crash costs no data.

**Projects (multi-agent nodes, `SUTRA_NODES_V1=1` only).** A project of several steps has its own page, `/p/<id>` (the chat's question cards link to it): the questions waiting for you, the steps and the order they run in, what it has used, what Sutra decided for you, why it stopped and what happened. The same facts are in the database (`projects`, `agent_nodes`, `approvals`, `node_messages`, `node_audit`) and in the routes under `/api/projects`. `POST /api/projects` starts one from your own words, with `failure_policy` `stop_branch` (default: a step that fails stops only the steps after it) or `stop_all`. A step's tool calls are in the audit as `tool.used` rows with the tool's name, its kind and a file's base name, never what it carried (D327). With the setting off, none of this exists: the page answers 404.

Do not edit the files of a run by hand while it is live. `engine.json` files are safe to edit when the app is stopped (or use
`sutra-pro config set`, which writes them atomically).

## 3. Backup and restore

```bash
sutra-pro backup
sutra-pro backup --to ~/Backups --no-runs
sutra-pro restore ~/Backups/sutra-pro-backup-20261104T180131Z.tar.gz
```

- `backup` writes `sutra-pro-backup-<UTC>.tar.gz` (mode 600) into `<data>/backups/` (or `--to DIR`). It is safe while the server runs: the
  database is copied with SQLite's own backup call, so rows still in the write-ahead log are in it. `--no-runs` leaves every team's `runs/` out; the chart,
  chats, the Atom log and usage stay, because they are in the database.
- A backup never holds `.env`, the lock files or `logs/`: it is meant to be copied around. `--include-env` is refused with that reason.
  Keep your `.env` somewhere safe yourself.
- The default folder keeps the newest 7 backups. A backup written with `--to` is yours and is never rotated.
- `backup` first runs SQLite's `PRAGMA integrity_check` on the copy and refuses a damaged database (exit 1, nothing written, nothing rotated): such a copy could not
  be restored and would push the good backups out of the 7. `doctor` runs the same check and fails the Database line; restore the newest good backup.
- `restore` needs the server stopped. It verifies the manifest and every checksum, builds the new folder beside the old one, checks the database
  (`PRAGMA integrity_check`), then renames the old folder to `<data>.before-restore-<UTC>` and puts the new one in place. **Nothing is deleted**; remove the
  `.before-restore-*` folder yourself when you are happy. `.env` and `backups/` are carried over. A backup from an older version is accepted (the server migrates
  it); one from a newer version is refused. It also refuses an archive that lists any file a backup never writes (`.env`, `connectors/bins.json`, lock files, `logs/`):
  the manifest belongs to the archive, so a restore only trusts names it knows, and nothing is changed.

To keep one team's deliverables or the chart outside the app: `sutra-pro export team web`, `sutra-pro export chart`, `sutra-pro export usage --csv`.
They only read; they never overwrite a file or fill a non-empty folder.

## 4. Upgrade

0. Is there a newer release? Settings, About, **Check for updates** (or `sutra-pro update-check`) asks GitHub only when you press it (one request; a few more only when the first page of the release list holds no Sutra Pro release), and says "You have 0.1.0; 0.2.0 is out", "up to date" or "could not reach GitHub", with the page of the release and the one line for your kind of install. The server's check downloads and installs nothing, it is refused under `--offline`, and nothing else in the server contacts the internet by itself: the one thing that asks by itself is the DESKTOP app's own timer (about a minute after launch, then every 6 hours), through `POST /api/ops/update-plan` (the same answer plus the download of this platform; `auto: true` is refused with 409 `update_off`, and makes no request, while the owner's switch is off), and it is the only thing that downloads and installs (docs/RELEASE.md, Updates). The switch is Settings, About, **Check for updates automatically** (`GET` and `PUT /api/ops/update-setting`, default on, kept in the database's `meta` table with the last check line; the desktop app reports its progress to `POST /api/ops/update-status`). The command line and a browser-only start never check by themselves. `sutra-pro update-check --json` prints one JSON document; `sutra-pro update-check --data-dir D` reads the offline setting of another data folder.
1. Stop it: `sutra-pro stop`.
2. Back up: `sutra-pro backup`.
3. Install the new version. A release: `uv tool install --reinstall <url of the new wheel>`. A checkout: pull and `uv pip install --python .venv/bin/python -e ".[dev]"`. The Mac app: replace it in Applications.
4. Start it: `sutra-pro`.

When the new version changes the database layout, the server first copies the old database to `<data>/backups/pre-upgrade-v<old>-to-v<new>.sqlite3` and
only then migrates. If that copy fails the server does not start and says why. A database written by a **newer** version than the app is refused
(`sutra-pro doctor` check `database`); install the newer app, or restore a backup. Going back to an older app means restoring a backup made with it.

## 5. Prune

Run files are the bulk: screenshots, `trace.jsonl`, `events.jsonl`, `run.stdout.log`, `run.stderr.log`.

```bash
sutra-pro prune --older-than 30d
sutra-pro prune --older-than 30d --yes
```

The first line is a dry run (the default): it lists what would go and how much it frees. `--yes` does it. Only **finished** runs (done, done with open items,
stopped, crashed, cancelled) that ended longer ago than `--older-than` (`90d` by default; `36h`, `2w` also work) are touched. `events.jsonl` stays unless the server has
projected every byte of it. Never touched: summaries, goals, site versions, documents, chats, and any row of the database. The Atom log and the usage table are
append-only and small (about 100 KB a run), so there is no retention rule for rows in version 1 (D93); `prune` prints their row counts and sizes. With `--yes` and the server stopped it also
compacts the database (`VACUUM`) while holding the instance lock.

## 6. Logs

- `<data>/logs/server.log`: one line per event, `INFO` and up (`--verbose` adds `DEBUG`), rotated at 5 MB with five old files (mode 600). The terminal shows warnings and up.
- Every HTTP response carries `X-Request-Id` (12 hex characters), also in the log line of that request and on an error page, so a failure in the browser can be found in the log.
- Secrets are scrubbed on the way in: the per-launch token, the override key, every value in `.env`, secret-looking names, bearer and Basic values and the key and token shapes of `connectors/egress.py` (OpenAI and Anthropic keys, every GitHub token, AWS ids and secret keys, Google, GitLab, npm, Hugging Face, SendGrid, Slack, Stripe, JWTs, private-key blocks). Whatever the owner types into the org chat, a team chat or answer, a task or a schedule is stored as `[redacted:<shape>]`, as in the direct chat. If one leaks anyway, treat that as a bug.
- Two limits of that scrub, both by design (D71, the same rule as J2's). The environment rule goes by **name**: a variable whose name contains KEY, TOKEN, SECRET, PASSWORD
  or AUTH has its value hidden wherever it appears and a note that holds it is refused, so `GIT_AUTHOR_NAME`, `KEYBOARD_LAYOUT` or `SSH_AUTH_SOCK` count too. If your own name or
  your shop's name comes out as `[redacted]`, unset that variable before you start the server (`env | grep -i -E 'key|token|secret|password|auth'` lists them). A `.env`
  line is read as dotenv tools read it: ` # a comment` after a value and the quotes around it are not part of the value, `\"` inside double quotes is a quote.
- A request body over 2 MB is refused with 413 `payload_too_large` before it is read (a file attached to a chat may be 20 MB). A JSON body nested thousands of levels deep,
  or a list position or time too large for the database, is a 400 or 422, never a 500.
- Each run has `run.stdout.log`, `run.stderr.log` and `trace.jsonl` in its folder. The macOS app also keeps `~/.sutra-pro/logs/app.log` for its launcher.
- For a bug report, download the diagnostics zip (section 7), not the raw folder.

## 7. The usage and cost console

Open `/console` (menu: Owner, "Usage and log"). Three parts:

- **Usage and cost**: a period (today, 7 days, 30 days, all; UTC dates) and a stub toggle. Tiles for calls, Claude cost in USD and Codex tokens; a bar per day; a table by team and
  function; a table by purpose (what the calls were for, in plain words: agents at work, planning and judging workflows, questions to agents, and so on; it follows the period and the stub toggle);
  the ten dearest atoms, each linking to its team page or graph node; each connector with its quota state and next reset. Claude's USD is "notional" for a subscription
  (what the same calls would cost on the API, not a bill). Codex reports tokens; a USD figure appears only when the policy file carries a rate card for the model.
- **Atom log**: the append-only ledger of every atom transition, newest first, 25 to a page, filtered by node, state, check or date.
- **Health**: the facts (version, uptime, ports, data folder, schema versions), the doctor checks with *Check again*, and *Download diagnostics* (a zip with the info, the doctor result, the last
  2000 log lines, public settings, schema versions and folder sizes; no chat, prompt, site file, `.env` or `engine.json` value).

The late judge (J2's check of a workflow after the first plan; it is on by default) is billed like any other call: what it cost is the rows "Planning workflows" and "Judging workflows" of the table by purpose,
and "judging N calls, $x" under each agent in a team's Agents tab, where "questions N calls, $x" is what the answers in that agent's chat cost.

The same data is served by `GET /api/ops/info`, `/api/ops/doctor`, `/api/ops/usage?period=` and `/api/ops/diagnostics` (the last needs the `X-Sutra-Token` header), and by the older `/api/usage/summary?by=dept|fn|provider|day|atom|session|purpose` (with `since=` for a window) and `/api/atoms/log`.

## 8. One instance per data folder

An advisory lock `<data>/app.lock` plus `<data>/app.pid` guard the folder (D94). Start `sutra-pro` twice on one folder and the second prints "already running on ... (pid N)", opens the
browser on the first and exits 0. Two servers on one folder would both write the database and project every run event twice, so it is refused, not allowed.
Different folders run side by side (`--data-dir`, each on its own port). The lock dies with the process, so a crash leaves no stale lock; `sutra-pro stop` refuses to signal when the
pid file does not match.

## 9. Ports

The server binds `127.0.0.1` only (a non-loopback `SUTRA_HOST` is refused, D11). Without a port setting it takes the first free port from **8780** to **8799**. `--port N` or `SUTRA_PORT`
means exactly that port: if it is busy the server says so and exits, it does not pick another. The port actually used is in `app.pid`, in `sutra-pro status` and in the first line the server prints.
The Mac launcher honours `SUTRA_PORT`, `SUTRA_PORT_MIN` and `SUTRA_PORT_MAX`.

## 10. Offline mode

`sutra-pro --offline` (or `SUTRA_OFFLINE=1`): the stub connector answers every model call and the engine plays its deterministic mock. No CLI is needed or called,
nothing is spent, and `doctor --offline` skips the CLI and browser checks. Use it to look at the screens, to test an install, or on a machine with no login. Output is canned and a stub row
in the usage ledger is flagged so the console can hide it. `SUTRA_CONNECTOR=stub` does the connector half only; `claude` or `codex` pins one provider instead of the default order (Claude, then Codex).

## 11. Settings and secrets

`sutra-pro config show` lists every effective setting and where it came from. Engine settings can be changed in Settings, Engine, or with `sutra-pro config set budget 200`; a change applies to
the **next** run of that scope (`--dept D` for one team). Locked ones (`send_mode`, `chrome`, the test switches) change only with `config set`. Secrets (the override key, the SMTP login) live in `.env`:
`sutra-pro config init` writes a commented template with mode 600, and `--generate-override-key` fills in a fresh key. See [ENVIRONMENT.md](ENVIRONMENT.md).

## 12. Multi-agent projects: turning them on, and what to check

This is the beta of "projects": a request that the chat splits into two or more steps becomes one project. Several agents (steps) work on it, some at the same time, and you can stop all of them at once. It is **off** in every release: nothing here exists until you switch it on, and the app is exactly as it was with it off. Design: [design/multi-agent-nodes](design/multi-agent-nodes/architecture.md).

**Turn it on (the beta app only, not the one you rely on).** The app reads its settings from its environment, so set `SUTRA_NODES_V1=1` when you start the beta app (the other three, `SUTRA_NODES_LANES`, `SUTRA_NODES_REVIEWER` and `SUTRA_NODES_SLOTS`, are separate and also start at `0`; see [ENVIRONMENT.md](ENVIRONMENT.md)). `sutra-pro nodes status` shows what is on. To turn it off, stop the projects first (`sutra-pro nodes kill`, then `sutra-pro nodes resume`) or let them finish, then start the app without the variable. A step that is still waiting stays on hold; you can stop it from the task list.

**Before you try it, check these five things.**

1. The working folder is a **git folder** and its work is **committed**. Then you can see exactly what a step changed and put it back. In a folder that is not a git folder, steps change it one at a time and Sutra **cannot check** which files a step changed (the project page says so).
2. You have set your **dollar limit** (the monthly limit in the app). Credits are counted as one model call each when a step is tried a second time, so the dollar limit is the number that really holds. A project may spend what is left of your month when it starts, and each step starts with a cap of what is left then; when the month's limit is reached a running project is stopped ("Your monthly limit was reached, so the project stopped."). One model call of a step is started with at most what the step has left, not more. **Codex calls carry no dollar figure**, so neither the month nor a step's cap can stop a project that runs on Codex: its credits (calls) and its time hold, and the project page says "about" and how many calls have no price. A task that is not a project keeps the old rule: new tasks wait, and one that is already running finishes. Each step is also stopped after 60 model calls or 30 minutes, and tried again at most once.
3. Start with a small request of **two to five steps** and watch the first projects. The page of a project is `/p/<id>`; the question cards in the chat link to it.
4. Know the two ways to stop: **Stop everything** on the project page, and `sutra-pro nodes kill` (or a file called `KILL` in the `nodes` folder of the data folder) when the page does not answer. In the beta app the command is its own program: `<the app>/Contents/Resources/python/bin/python3 -I -B -m sutra_app nodes status|kill|resume --data-dir <data folder>`. `nodes status` shows the settings of the shell you typed it in (labelled so) and then what the running app says about itself; trust the second. `nodes resume` is written in the project record (the running app writes the row when it next looks, or when it starts).
5. Decide whether to switch on **Decide for me**. With it on, Sutra answers some questions for you (it allows read-only GitHub for the project and a step that changes several places of your folder). It never answers for you about your computer's permissions, about the app's own data, about a plan over 1000 credits, about what a reviewer said, or by keeping work that went outside its place.

**What Sutra does for you.** It asks before a plan estimated over 400 credits starts (five default steps are about 500). It asks before a step reads GitHub, reads the app's own data (your teams, tasks and notes), or changes files in several places. It keeps steps that change the same part of your folder apart. If a step changes files that no step of the project was given, it pauses the project and asks you: keep the work, or set it aside. It puts every grant, answer and stop in a record you can read on the project page.

**What it does not do, and you should know.**

- **Keeping apart** works among the steps of projects. A normal task of another team can still change the same folder at the same time, as two teams can today.
- **The check for files outside a step's place** uses git. It sees what git sees. It does not see a file that git ignores (for example a `.env`), more than 5000 changes at once, or a folder without git. When it cannot check, the project page says so; it does not stop the project.
- **A step that wrongly changes a file inside another step's place** is not caught. A Claude step has its editing tools limited to its own place, so the program itself refuses; a Codex step has no such limit.
- **A Codex step** can change files outside its own place while it works; Sutra finds out after it ends and asks you. A Claude step has its editing tools limited to its own place.
- **Credits.** When a step is tried again, one model call counts as one credit. Your dollar limit is the number that holds.
- **A step cannot run its own tests.** It has no shell, so a step whose output wants a test run cannot run one; J2's own checks of the output still run after each try, and a step may waste a call asking for a command that is refused.
- **The list of a step's tool calls** is kept by the step's own host and is a record, not a proof: a step with a shell runs as you and could change it (a step has no shell now, above). It is written when the step ends, so its times are the end's. It counts tool calls; `calls.jsonl` in the run folder counts model calls and is written when each call ends, so a step stopped in the middle has fewer lines there: the two numbers are not meant to match.
- **A closed laptop or a closed app** is left out of a project's running time (the 2-hour limit): a sleep while Sutra is open is noticed at once, and a closed Sutra is noticed when it starts again, from the project's last sign of life. A pause and a sleep at the same time count once. The dollar limit and the limits of each step are not affected.
- **A place with a bracket or an exclamation mark in its name** (for example a folder called `(auth)`) cannot be given to a step as its own place; the plan is refused with a sentence that says so. Name its parent folder instead.
- **Setting work aside** does not undo anything. The files stay in your folder. Sutra never moves or deletes them.
- **What a step may do (its tools).** A step of a project may look at the files it is given and write its own working files in a scratch space of its own. It may **not** run commands and may **not** use the web, whatever you approved (approving "read GitHub" gives the step GitHub reads and nothing else). This is enforced when the step's Claude program is started (its tool list is taken down to the step's grant), not by the step's own words. An ordinary run (not a project) keeps its whole tool list. A step run through **Codex** cannot be narrowed tool by tool: Codex runs a step with a read-only sandbox when its folder access is read, and may change files in the folder when it is allowed to (see the Codex step above); Sutra does not send a Codex step the builder tools at all.
- **The network.** A step of a project has no web tools at all (above). Sutra only **checks and counts** secret-like words in the prompts of the working steps (it does not change them, as with any ordinary run), so a secret that sits in your folder can reach the model program; it **removes** them from what steps hand to each other, from the planner's and reviewer's text and from the project's record. It does nothing about what a tool fetches or sends, and while a step still runs its live view holds what the tool was given; and the tool inputs in the run's record are emptied when the step's own program ends the run (done, stopped or crashed); a step that is killed hard may keep them, and the prompts and replies stay, as in any run. The project's record lists which tools a step used (name, kind, file name) and never what they carried.
- **Closing the app while a project runs** (a normal quit, or a SIGTERM) is not the end of the project: each step that was running gets a fresh attempt at the next start (it does not spend its one retry; at most two such), the steps that wait for it keep waiting, and the time the app was closed is left out of the project's running time. Stop everything, the kill switch and a limit still end the project.
- **Home's "Needs you" and Heads up** never list a step of a project that is over (stopped, could not finish or done) with "Try again"; the project's page says how it ended. The command to resume the switch by hand is printed with the kill; in an app it is the app's own Python (`<app>/Contents/Resources/python/bin/python3 -I -B -m sutra_app nodes resume --data-dir <data folder>`); there is no Resume button on the page for it.
- **A reviewer** (`SUTRA_NODES_REVIEWER`) only gives an opinion: approve, changes or reject. You decide. If you do not answer its question, or the computer sleeps or is closed, that counts as a no and the project ends as it is. If it cannot run, the project still ends done and says the review could not run. It reads the text each step wrote (the text files its report names: a few thousand characters of each, with secret-like words replaced), not only the names of its files. Its question is answered with "Send them back" or "Leave as it is". It uses the other Claude or Codex program when both are signed in, and says "not independent" when it had to use the same one.
- **If your folder is in iCloud Drive or on an external or network disk,** the check before a step starts now looks there on a Mac too (it may show your computer's own window). On Windows with Controlled folder access on, Sutra says once that the programs `claude` and `codex` are judged apart from Sutra Pro; it cannot test them without running a model, so a refusal can still show up after a step has started, as a card with "Check again".

**What is not verified yet.** Everything above was tested with stand-ins, not with a real project on a real Mac or Windows computer. Not yet seen working: a real folder check on a real project; Claude and Codex with the limits above; a real reviewer; the project page in a real browser; the first-time permission windows on a Mac and Windows; how many calls and minutes a normal step uses (the 60 and 30 are guesses); two apps sharing the Claude and Codex limit (`SUTRA_NODES_SLOTS`). If something looks wrong, press Stop everything and tell us what you saw.
