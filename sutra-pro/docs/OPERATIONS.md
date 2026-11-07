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
```

`python -m sutra_app` is the same program as `sutra-pro`. In a checkout, `scripts/run.sh` and `scripts/stop.sh` do the same with the checkout's own virtualenv.

| Command | Flags | Notes |
|---|---|---|
| `sutra-pro serve` | `--port N`, `--data-dir D`, `--offline`, `--no-browser`, `--browser auto\|chrome\|default`, `--verbose` | no sub-command means serve |
| `sutra-pro doctor` | `--data-dir D`, `--json`, `--offline` | exit 0 when nothing failed, 1 when a check failed |
| `sutra-pro status` | `--data-dir D`, `--json` | exit 0 running and healthy, 1 not running or unhealthy |
| `sutra-pro stop` | `--data-dir D`, `--json`, `--wait S` | SIGTERM, then waits `S` seconds (default 20); never SIGKILL |
| `sutra-pro open` | `--data-dir D`, `--json`, `--browser` | needs a running instance |
| `sutra-pro config show` | `--data-dir D`, `--json`, `--dept D` | the effective values and their source |
| `sutra-pro config set FIELD VALUE` | `--data-dir D`, `--json`, `--dept D` | the only way to set a locked engine setting |
| `sutra-pro config init` | `--data-dir D`, `--json`, `--generate-override-key` | writes a commented `.env` template (mode 600); never overwrites |
| `sutra-pro config sync-library` | `--data-dir D`, `--json` | copies seed templates the data library lacks |
| `sutra-pro backup` | `--data-dir D`, `--json`, `--to DIR`, `--no-runs`, `--include-env` | `--include-env` is refused |
| `sutra-pro restore FILE` | `--data-dir D`, `--json` | the server must be stopped |
| `sutra-pro prune` | `--data-dir D`, `--json`, `--older-than AGE`, `--dry-run`, `--yes` | a dry run unless `--yes` |
| `sutra-pro import-old-chats` | `--data-dir D`, `--json`, `--source DIR`, `--apply` | read only on the old folder; a dry run unless `--apply`; the server must be stopped |
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
  agents/j2/                         engine-owned: the agent prompts a run reads
  connectors/policy.json             optional connector routing policy (the app ships a default)                 tiny
  departments/<team>/
    department.json                  a readable mirror of the team; the database is the authority                 tiny
    engine.json                      optional per-team engine settings                                            tiny
    page.json, memory/               the team page's since-run mark; lessons and playbooks                        small
    runs/<run id>/                   one folder per run: the team's records, as the J2 prototype writes them
      task.json  inbox.jsonl  events.jsonl  trace.jsonl  snapshot.json  live.json  settings.json
      chat.jsonl  calls.jsonl  map.json  report.json  summary.json  goal.json  workflows.json  atoms.json
      run.stdout.log  run.stderr.log
      site/ (page versions, documents, shots/)  artifacts/                                                       ~0.08 MB for a mock run; MBs with screenshots
```

Which files are whose: the **server** is the only writer of the database (D16). Each run is a separate process that writes only
its own run folder. A restart reads those files again and projects them idempotently, so a crash costs no data.

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
- `restore` needs the server stopped. It verifies the manifest and every checksum, builds the new folder beside the old one, checks the database
  (`PRAGMA integrity_check`), then renames the old folder to `<data>.before-restore-<UTC>` and puts the new one in place. **Nothing is deleted**; remove the
  `.before-restore-*` folder yourself when you are happy. `.env` and `backups/` are carried over. A backup from an older version is accepted (the server migrates
  it); one from a newer version is refused.

To keep one team's deliverables or the chart outside the app: `sutra-pro export team web`, `sutra-pro export chart`, `sutra-pro export usage --csv`.
They only read; they never overwrite a file or fill a non-empty folder.

## 4. Upgrade

0. Is there a newer release? Settings, About, **Check for updates** (or `sutra-pro update-check`) asks GitHub once, only when you press it, and says "You have 0.1.0; 0.2.0 is out", "up to date" or "could not reach GitHub", with the page of the release and the one line for your kind of install. It downloads and installs nothing, it is refused under `--offline`, and nothing else in the app contacts the internet by itself. `sutra-pro update-check --json` prints one JSON document; `sutra-pro update-check --data-dir D` reads the offline setting of another data folder.
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
- Secrets are scrubbed on the way in: the per-launch token, the override key, every value in `.env`, secret-looking names, bearer tokens and `sk-` keys. If one leaks anyway, treat that as a bug.
- Each run has `run.stdout.log`, `run.stderr.log` and `trace.jsonl` in its folder. The macOS app also keeps `~/.sutra-pro/logs/app.log` for its launcher.
- For a bug report, download the diagnostics zip (section 7), not the raw folder.

## 7. The usage and cost console

Open `/console` (menu: Owner, "Usage and log"). Three parts:

- **Usage and cost**: a period (today, 7 days, 30 days, all; UTC dates) and a stub toggle. Tiles for calls, Claude cost in USD and Codex tokens; a bar per day; a table by team and
  function; the ten dearest atoms, each linking to its team page or graph node; each connector with its quota state and next reset. Claude's USD is "notional" for a subscription
  (what the same calls would cost on the API, not a bill). Codex reports tokens; a USD figure appears only when the policy file carries a rate card for the model.
- **Atom log**: the append-only ledger of every atom transition, newest first, 25 to a page, filtered by node, state, check or date.
- **Health**: the facts (version, uptime, ports, data folder, schema versions), the doctor checks with *Check again*, and *Download diagnostics* (a zip with the info, the doctor result, the last
  2000 log lines, public settings, schema versions and folder sizes; no chat, prompt, site file, `.env` or `engine.json` value).

The same data is served by `GET /api/ops/info`, `/api/ops/doctor`, `/api/ops/usage?period=` and `/api/ops/diagnostics` (the last needs the `X-Sutra-Token` header), and by the older `/api/usage/summary?by=dept|fn|provider|day|atom` and `/api/atoms/log`.

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
