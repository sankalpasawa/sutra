# GAP-providers as built: plan meters that survive a restart, and the Claude and Codex CLIs found where installers put them

Package key `providers` of the absorb-old-sutra gap review: two verified gaps, built together because both live in the connector layer and
the Settings, Connectors rows. Branch `feat/sutra-pro-gap-providers`. No J2 file, prompt, route or golden is touched; nothing is pushed.

## 1. Plan meters, the plan named, remembered across restarts (and Settings no longer says Ready when a provider is out of quota)

What the owner sees:
- Settings, Connectors: under each signed-in row, one bar per usage window of the plan ("5-hour 62%, resets in 1 h 10 min", "Weekly 81%,
  resets Tue 09:00"), green under 80 %, amber from 80 %, red from 95 % (the old app's thresholds), then "as of 14:05", then one plain line
  "Claude Max, counted against your plan, not billed per call". A window whose reset time has passed reads "reset" instead of a stale
  percent; a window with no figure draws no bar. A provider out of quota says "Out of quota" (not "Ready") with "usage limit reached,
  until 14:05"; cooling down and paused have their own words.
- /console: the same meters per connector and the plan line with the account ("Claude Max, you@example.com, ..."); an older snapshot
  without windows keeps its one text line.
- The provider pill (Home and the node panel on Home): each ready provider's button carries its fullest live window ("Claude 5-hour 62%"),
  coloured the same way, the reset time in its title.
- After a restart the last snapshot is still shown (with its "as of" time), and an exhausted one still blocks that provider until its reset.

Where:
- `sutra_app/connectors/orchestrator_port.py`: `status()` sends `health` as the `HealthState` object `{state, until, reason}` (it was the
  bare string, so `settings_view.healthChip` fell back to Ready/Signed out and the chip never said quota), plus `quota` and `plan_label`.
  `account` stays out of this view (CN-7): /api/health is polled by the launcher and the macOS proof step.
- `sutra_app/connectors/models.py`: closed `QuotaWindow {key, label, used, resets_at}`; `Quota` gains the additive `windows` and `seen_at`
  (old snapshots still validate).
- `sutra_app/connectors/quota_windows.py` (new, pure): `windows_from_claude` (every entry of `unifiedWindows`, else the `rateLimitType`
  window), `windows_from_codex` (primary and secondary, keyed by `window_minutes`; an unknown duration is named from its number),
  `window_label`, `plan_label` (claude free/pro/max/team/enterprise, codex free/go/plus/pro/team/business/enterprise/edu; an unknown plan is
  title-cased, never dropped). `claude.py` and `codex.py` keep every window; the metering window (`window`, `used`, `resets_at`) is unchanged,
  so the router blocks exactly as before. Codex's `_window_name` is now the same table.
- `sutra_app/connectors/quota_store.py` (new): `<data>/connectors/quota.json`, mode 0600, atomic; `HealthBook` stamps `seen_at`, reports every
  snapshot change to `on_quota_change` listeners (a success that clears an exhausted snapshot clears it in the file too), and
  `restore_quota` puts a stored snapshot back with its own `seen_at`. The factory attaches it for every non-stub router. A file that does not
  read or validate is ignored and replaced by the next snapshot; only claude and codex are written; the file holds figures only.
- `router.py`: `ProviderStatus.plan_label`; the plan falls back to the quota's plan (Codex names its plan only in a quota, so it now survives
  a restart too).
- `chat_models.ProviderPill.quota` (additive) and one keyword in `chat_port.providers()`.
- `sutra_app/ui/static/js/plan_meter.js` (new, pure strings, ONE global `PlanMeter`): `severity`, `resetText`, `windowsOf`, `windowHtml`,
  `planLine`, `asOf`, `meterHtml`, `clockOf`. Used by `settings_view.connectorRow`, `console_view.connectorsHtml` and `chat_pill.pill`
  (each looks it up when it draws, a `require` in node). Script tags in `ui/pages/home.html` and `ui/pages/console.html`.
- CSS: `.pmeter`/`.pmw`/`.pmbar`/`.cpill-q` in `sutra-panel.css` (a new block after the department rail, loaded by Home and /console),
  the chip tones and the file box in `sutra-shell.css`, the row width in `sutra-console.css`. J2's tokens only; the amber is J2's
  `--validator`, already used by the Settings chips. The contrast test passes.

## 2. The CLIs found where installers put them, a file the owner can choose, and "Claude Desktop is not Claude Code"

What the owner sees:
- A Mac app opened from Finder finds `claude` and `codex` installed through nvm (every node version, newest first), Volta, pnpm, mise,
  asdf, nodenv, n, fnm, yarn, bun, npm's prefix, Homebrew or Claude Code's own installer; the folder is appended to that CLI's PATH so a
  `#!/usr/bin/env node` shim starts. Sutra never runs the owner's shell or its startup files and installs nothing (D34).
- If a CLI is still not found, its Settings row has an open "Choose the file" box (folded as "Use another file" under a row that was
  found): the path is checked (a full path, `~` allowed, to a file this account may run, named claude or codex), stored, survives a
  relaunch, and the row turns Ready at once; a refused path says why ("There is no file at ...", "Choose the file named claude: rm is not
  the Claude command"). "Find it again" forgets the choice. A stored file that later vanishes is ignored, not honoured.
- With /Applications/Claude.app (or ~/Applications) and no `claude` command, every surface says "Claude Desktop is installed, but Sutra
  needs Claude Code, a separate command-line tool: install Claude Code (claude.com/claude-code), or choose its file in Settings,
  Connectors": the Settings row, the pill's reason, the plan's skip reason, the CLI-missing error and `sutra-pro doctor`. It never says
  PATH. Without Desktop the PATH wording each surface had is kept.

Where:
- `sutra_app/connectors/discover.py` (new): `known_dirs`, `find_cli` (stored file, then PATH, then the known folders that exist and hold an
  executable command), `augment_path` (appends, never prepends), `claude_desktop_installed`, `explain_missing`, `connector_config` (the
  running app's `ConnectorConfig`: full paths, the child PATH, `claude_desktop`) and `use_cli` (the running router follows a new choice:
  the connector's executable and PATH change, its cached sign-in, flags and version are forgotten, the health book forgets installed and
  auth, `connector.health` goes out). POSIX only; Windows keeps the installer's PATH.
- `sutra_app/connectors/bins.py` (new): `<data>/connectors/bins.json`, mode 0600, atomic; `check_path` refuses with `InvalidRequestError`
  (a 422 with the reason). The name is the name of the chosen path, not of its target, because nvm, Volta and the native installer use
  links to files with other names (`.../versions/2.1.308`, `volta-shim`, `cli.js`).
- `models.ConnectorConfig.claude_desktop` (additive, default False); `factory.build_router`, `ops/doctor.run` and a live
  `engine_port.make_port` (the engine host's port, so a department run uses the same file as Settings and the chat; a stub-only port keeps
  the defaults) use `connector_config` when no config is handed in (every test hands one in, so no test depends on this machine's CLIs).
- Wording: `errors.DESKTOP_ONLY` and `CliMissingError.user_message` (`detail.desktop`, set in `base._execute` for Claude when the flag is on);
  `router._skip_reason` and `provider_summary`; `chat_port._why_not` returns the router's detail (one line); `doctor._judge` gains the
  Desktop branch and names the Settings box in its fix.
- `sutra_app/connectors/api.py`: `PUT /api/connectors/{provider}/path` `{"path": "..." | null}`, behind the write guard (D81), refused offline
  (409), 404 for a provider other than claude and codex, answers `{provider, path, installed, signed_in, detail}`.
- `settings_view.js`: `pathBox` in `connectorRow` and the flow `setCliPath(api, provider, path)`; `home.js` (Settings section only):
  `data-act="set-path"` and `"clear-path"`, what was typed is kept across a repaint, the rows refetch afterwards.
- Docs: TROUBLESHOOTING F1 and the doctor `claude` entry, RELEASE-macos, connectors design section 6 (the status fields and the route).

## Decisions taken here (decide-and-document; numbered at the merge to avoid a collision with the parallel packages)
- PROV-1: `/api/health` keeps leaving out `account` (CN-7). Settings shows the plan and how it is billed; /console, whose route already
  carries the account, shows it too. Rejected: adding the e-mail to a route the launcher polls and may log.
- PROV-2: the plan label is built in Python (`quota_windows.plan_label`), the billing words in JS (`plan_meter.planLine`). The meter
  thresholds are the old bars' 80 and 95, not the old usage guard's 70 and 80.
- PROV-3: the snapshot file is written on every change under the health book's lock (writes stay in order); a failed write is logged and
  never fails a call.
- PROV-4: discovery runs only where no config is handed in (the app, its engine host and the doctor), so tests stay hermetic; the system folders are a
  separate tuple (`SYSTEM_DIRS`) that tests leave out.
- PROV-5: a chosen file must be named as the command (claude, codex; .exe/.cmd on Windows), checked on the chosen path, not its target.
- PROV-6: no `SUTRA_CLAUDE_BIN`-style variable: it is useless from Finder (the old app's own note), and the Settings box covers a terminal
  start too. `launcher.sh`'s fixed PATH append stays (harmless).

## Tests added or changed
- New: `tests/connectors/test_quota_windows.py` (28), `test_quota_store.py` (15), `test_discover.py` (15), `test_bins.py` (17),
  `tests/ui/js/plan_meter.test.js` (11).
- Added cases: `test_orchestrator_port.py` (the status has the shape the page reads, matched key for key against `tests/ui/fixtures/health.json`;
  `plan_label`), `test_api.py` (the path route: chosen, followed at once, forgotten, refused with the reason, unknown provider, bad body,
  offline; it is in the guarded write list), `test_chat_port.py` (the pill carries the quota), `tests/ops/test_doctor.py` (the Desktop
  wording), `settings_connectors.test.js` (quota is never Ready, meters and plan line, reset, until, the file box, setCliPath),
  `console_view.test.js` (meters with the account), `chat_pill.test.js` (the fullest window), `test_fake_backend.py` (the fake's path
  route, and the write-route list), `tests/ui/test_home.py` (a real-Chrome case: plan line, two bars, the file box PUT with the token).
- Changed on purpose: `test_orchestrator_port.py` pinned the bare-string `health` (the defect); `tests/ui/fixtures/health.json` now has
  the real status shape (`plan`, `plan_label`, `quota` with windows) and `test_fake_backend.py` names the full key set.

## Commands run (all green)
- `scripts/py -m pytest tests/connectors -q -p no:warnings`: 1508 passed, 5 skipped
- `scripts/py -m pytest tests/ops`: 298 passed; `tests/ui`: 741 passed, 173 skipped (browser cases skip without SUTRA_BROWSER);
  `tests/contracts`: 136 passed; `tests/orchestrator`: 925 passed, 1 skipped; `tests/e2e`: 35 passed, 6 skipped;
  `tests/test_docs.py tests/test_ownership.py tests/test_traceability.py tests/test_layout.py`: 106 passed
- `node --test tests/ui/js/*.test.js`: 682 tests, 680 passed, 2 skipped (contrast included)
- `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_home.py -k claude_row`: 1 passed in real Chrome

## Not done, and why
- The J2 team page's pill shows no quota figure: `plan_meter.js` would have to join the list injected by `dept_ext.js:138`, the one line
  the chat-comfort and attention packages also add to. A one-word rider for the merge (`"plan_meter"` in that list).
- No Home chip of its own beyond the pill: the pill is where Home shows providers; a second chip would compete with it.
- Not taken from the old app (as the review said): the OAuth usage endpoint and ~/.claude.json (D34), so no "20x" tier; the login-shell
  PATH harvest; any installer or updater.
- Pre-existing, not this package: `tests/ui/fake_backend.py` serves no `/api/chats/{sid}/providers`, which `home.js` renderPill has
  fetched since the import, so the Home browser cases that load the page (run with SUTRA_BROWSER=1; the gate skips them) end with an
  unannounced 404 at teardown. Neither the route nor its caller is touched here; the new browser case announces that 404 with
  `expect_failed`. Adding the route to the fake is a small follow-up for the chat package.
- `MediatedConnectors` (the Claude-held connectors panel) keeps the executable it was built with until a restart after a new choice.
