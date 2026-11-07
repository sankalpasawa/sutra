# GAP3-autoupdate as built: the desktop app checks for updates by itself, verifies a download before anything is replaced, and installs only when the owner says so

The finding behind it: Settings -> About (GAP2) had an owner-click check that only tells, and nothing checked by itself or installed. This package adds the automatic check, the
verified download and the install to the **Electron desktop app** (macOS arm64 and x64, Windows x64), on Sutra Pro's own release feed only. No schema migration (two keys of the
`meta` table), no J2 file, prompt, route or golden is touched, and the release workflows were not edited: every asset the updater needs is already published (`Sutra-Pro-arm64.dmg`,
`Sutra-Pro-x86_64.dmg`, `Sutra-Pro-Setup-x64.exe`, each with `<asset>.sha256` as `<hex>  <name>`; checked against the live release list).

## What the owner gets

- The desktop app asks the local server for a plan a minute after launch and every 6 hours while it runs (a timer cleared on quit, never keeping the process alive). Never in
  offline mode (`SUTRA_OFFLINE`), with the stub connector, in the release self-test (`SUTRA_PRO_SELFTEST`), in an unpackaged checkout, or with the switch off.
- Settings -> About: a switch **Check for updates automatically** (default ON in the desktop app; stored on the server, `meta.update_auto`), in plain words what is sent (one GET to
  GitHub's release list, nothing about the owner or the files), the **Last check** line (time and result, written by the server after each check and by the app as it downloads and
  verifies) and one line saying whether **this copy installs updates itself or only tells**. The welcome card's "What leaves this computer" says the same.
- A verified update opens ONE native dialog (Electron's, not the page; the page has no IPC): "Sutra Pro X.Y.Z is ready." with **Restart Now**, **Install on Quit**, **Later**.
  Later installs nothing and asks again at the next launch (not again in the same session). The same dialog is reached from **Check for Updates...** (app menu on a Mac, Help on
  Windows), which also answers "You are up to date."
- A failed check is one plain sentence in the log and in About ("The download of Sutra Pro X did not match its published checksum, so it was deleted and nothing was installed.").

## How it works, in order

1. **Plan** (`ops/update_check.py` `plan()`, `POST /api/ops/update-plan`, token-gated): the server makes the ONE request (the shared release list, newest first, at most
   `MAX_PAGES`), picks the newest release this install may take (a stable install: stables only; a beta install: newer betas and stables; the 9-digit limit and the URL-character
   checks kept) and adds, for the release it names, the asset facts of the three platform files: https URL, size, `.sha256` URL. An asset is kept only if its name is one of the three,
   `state` is `uploaded`, its URL equals EXACTLY `https://github.com/sankalpasawa/sutra/releases/download/<its tag>/<name>`, its size is an integer from 1 to 1 GiB, and the
   `.sha256` sibling passes the same tests; anything else drops that asset (never raises). `auto: true` is refused with 409 `update_off` (no request) while the switch is off,
   and both routes are refused with 409 `offline` (no request) in offline mode.
2. **Judge** (`desktop/src/updater.js` `planFromAnswer`): the answer is untrusted text. The desktop re-checks it as a safety net: strict version patterns, strictly newer than the
   running app, the channel rule, and the asset NAME and ADDRESS are rebuilt from the version and a fixed table and must equal what the server said (so a name with `../`, a URL on
   another host or with credentials, a size that is a string, a boolean, a float, zero, negative, above 1 GiB or `1e300` all end in "did not look right" and nothing is downloaded).
3. **Can this copy verify?** macOS: `codesign -dv` of the running bundle must show a Team Identifier (an ad hoc seal says "not set") and a bundle id; Windows: the running exe's
   Authenticode status must be Valid with a publisher. A checkout, an ad hoc or an unsigned copy **only tells** (a dialog with "Open the Release Page", and About says so); it never
   downloads and never installs.
4. **Download** into `<data>/updates/<version>/` (`0700`): HTTPS only, the first address and every redirect must be `github.com` or `*.githubusercontent.com` with no credentials and no
   odd port (at most 5 hops); the byte count is capped at the size the feed promised (and 1 GiB), and must equal it; a `.part` file is renamed only when complete; any failure
   deletes it. The checksum file is read first (at most 4 KB, one line `<64 hex>  <exact asset name>`).
5. **Verify** (`hashFile` opens the file ONCE and hashes the open handle, refusing a link): SHA-256 against the published value, then
   - macOS: `hdiutil attach -nobrowse -readonly -noverify -noautoopen -mountpoint <private temp dir>`; exactly one `Sutra Pro.app` (a real directory); `codesign --verify --deep --strict`;
     the same Team Identifier and bundle id (`plutil`) as the RUNNING app; `CFBundleShortVersionString` greater than the running version and equal to the announced X.Y.Z;
     `spctl --assess --type execute` accepting it; always detached afterwards (forced if needed).
   - Windows: PowerShell `Get-AuthenticodeSignature` run with a fixed argument list and a constant script (the file reaches it through the environment, never the command line):
     status Valid and the same publisher (certificate subject) as the running exe.
   Anything that fails is deleted. The last two staged versions are kept (`pruneStaged`); a version already staged is hashed and verified again at the next launch, not downloaded again.
6. **Ask** (the dialog above). Restart Now and Install on Quit first PREPARE while the app still runs, so a failure is told now and the installed app is untouched:
   - macOS: if the install folder is not writable by the owner, nothing is elevated: the verified app is copied (`ditto`) next to the download, revealed in Finder, and the dialog says
     where to drag it. Otherwise the verified app is copied with `ditto` to `Sutra Pro.app.new` beside the installed one and that exact copy is verified again (seal, team,
     bundle id, version, Gatekeeper): the bytes that get installed are the bytes that were checked.
   - Windows: nothing to prepare.
7. **Apply, after the app's own quit path has stopped its server** (`main.js` `before-quit`: the timer is cleared first, then `supervisor.stop()`, then `updates.applyOnQuit()`):
   - macOS: a small shell script (a CONSTANT in `updater.js`, written to `<data>/updates/apply-update.sh` mode `0700`, run by `/bin/sh` detached) gets every path as an argument and uses
     it only inside double quotes. It refuses anything but `<app>.new`/`.old`/`.bad` beside an app named `Sutra Pro.app`; waits for the app's pid (and the server's) to exit; moves
     the old app to `.old`; moves the new in; starts it (`open`); removes the old only after the new one answered `/api/health` (read from `app.pid`); if the new one does not
     answer within 90 s it stops that app (its processes found by the executable path, both as given and as the system resolved it), moves the old one back and starts it.
   - Windows: the verified `Sutra-Pro-Setup-x64.exe` is hashed again and its signature checked again, then run detached with `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
     /NORESTART /SP- /SutraRelaunch=1`. `sutra-pro-desktop.iss` has `PrivilegesRequired=lowest`, so it is per user with no prompt. The `.iss` got one `[Run]` line (see riders): the
     existing one is `skipifsilent`, and by then the app has quit, so the Restart Manager has nothing to restart.
   The data folder is never touched. A crash before the quit leaves `.new` beside the app (harmless; replaced by the next attempt) and applies nothing.

## Where

- `desktop/src/updater.js` (new): the pure functions (versions, channel, `planFromAnswer`, host checks, checksum parser, staging paths, the argv of every command, the macOS script text,
  the parsers of `codesign` and the Windows signature, `hashFile`, `downloadTo`, `pruneStaged`) and `createUpdater(deps)`: the controller, with the network, the programs, the dialogs, the
  timers and the clock injected, so `node --test` runs it on all three systems.
- `desktop/src/update_main.js` (new): the Electron side: the local server over loopback (the token is read from the boot block of the server's own page, the only place it is ever
  given, and again after a 401), the HTTPS transport, `execFile`, the dialogs.
- `sutra_app/ops/update_check.py` (`AssetFact`, `Answer.tag/assets`, `plan()`), `ops/update_state.py` (new: `update_auto`, `update_last`, `update_install` in `meta`), `ops/update_api.py`
  (`POST /api/ops/update-plan`, `GET`/`PUT /api/ops/update-setting`, `POST /api/ops/update-status`, `POST /api/ops/update-install`), `ops/welcome.py` (egress fact `auto_update`).
- Page: `settings_view.js` (`aboutHtml(info, update, auto)`, `setAutoUpdate`), `home.js`, `welcome.js`.
- Riders on shared files, each small and local: `desktop/src/main.js` (create the updater, `start`/`announce` after the server answers, `stop` and `applyOnQuit` in `before-quit`, one menu
  handler), `menu.js` (the item, left out when no handler is given), `runtime.js` (`SUTRA_PRO_DESKTOP=1` in the server's environment: the server tells the page and the welcome card that
  the desktop app is the one in front), `scripts/windows/sutra-pro-desktop.iss` (a `[Run]` line with `Check: RelaunchRequested`), `docs/RELEASE.md` (Updates), `docs/OPERATIONS.md`,
  `docs/ENVIRONMENT.md` (one row), `tests/ui/fake_backend.py` and its tests, `tests/release/test_desktop_bundle.py` (one test).

## The real swap proof (this Mac, throwaway apps, never /Applications)

`node desktop/scripts/prove_mac_swap.js` (opt-in test: `SUTRA_PRO_PROVE_SWAP=1 npm test` in `desktop/`) builds two tiny `Sutra Pro.app` bundles in a temporary folder whose name has spaces,
ad hoc signs them, starts the "old" one for real with `open`, and runs THE REAL HELPER TEXT with the arguments `macHelperArgs` builds. Output of the run:

```
--- 1. success: installed app .../sutra swap proof 9IlWxx/My Apps/Sutra Pro.app
old app running as pid 10692, answering {"ok":true,"version":"0.2.0"}
helper started and is waiting: the installed app is still 0.2.0 while the old app runs
new app running as pid 10735, answering {"ok":true,"version":"0.3.0"}
installed app is now 0.3.0; .../My Apps holds only: Sutra Pro.app
  log: update helper: Sutra Pro has quit / the new app is in place: starting it / the new app answered: the old one is removed and the update is done
--- 2. forced failure (the new app never answers)
the broken new app is in place and running as pid 11183; waiting for the helper to give up (6 seconds)
rolled back: installed app is 0.2.0, running as pid 11463, answering {"ok":true,"version":"0.2.0"}
the broken new app (pid 11183) is no longer running
  log: ... the new app did not answer within 6 seconds: putting the old one back / the old app is back
--- 3. refusal (names that do not belong together)
refused: installed app still 0.2.0; log: update helper: the staging names do not belong to the installed app: nothing was changed
PROOF OK: the swap, the rollback and the refusal all behaved as designed
```

The proof found one real bug on its first run: a temporary folder is behind a link (`/var` -> `/private/var`), `ps` shows the resolved path, and the rollback looked for the new app's
processes by the path as given, so it moved the old app back but left the broken new app running. The helper now matches both spellings (`pwd -P`), a unit test pins it, and the proof
asserts the broken app is gone. No leftover process or folder remains after a run. The owner's installed `/Applications/Sutra Pro.app` was only READ (`codesign -dv`): it is ad hoc signed,
so on this Mac today the app **only tells** (see below).

The live feed was also read for real: through a local server started from this checkout the three platforms' asset facts of the newest stable release (`sutra-pro-v0.1.0`) came back and
`planFromAnswer` accepted all three; the switch persisted across a PUT; `update-plan` with `auto: true` and the switch off answered 409 `update_off`.

## Proposed decision text (the merge step numbers it; no row was added to DECISIONS.md)

> **D?? — Sutra Pro updates its own desktop app, on the owner's word, and only what it can verify.** D34 says Sutra does not install the provider CLIs (claude, codex); it does not
> forbid updating Sutra Pro itself, and the owner asked for it. The desktop app (never the command line or a browser-only server) asks GitHub's release list for the `sutra-pro-v*`
> releases of this repository (D100: never "Latest", never the older product's releases) about a minute after launch and every 6 hours, unless the owner switched "Check for updates
> automatically" off in Settings, About, or the app runs offline, with the stub connector, or in the self-test. It downloads the asset of its platform into `<data>/updates`, verifies the
> SHA-256 and then the signature (same Team Identifier, bundle id, a newer version and Gatekeeper's verdict on macOS; same Authenticode publisher on Windows) and installs only when the
> owner chooses Restart Now or Install on Quit, after the app's own quit path has stopped its server. A copy that cannot verify a signature (ad hoc, unsigned, a checkout) only tells.
> Anything that fails to verify is deleted; a failed swap puts the old app back; the data folder is never touched. Diagram label: "update: verified, then on your word".

## Not done, and why

- **Windows installs wait for a signed installer.** D102: the installer is unsigned, so no Authenticode publisher can be compared and the Windows app tells only until a certificate
  exists. The code path (signature check, hash again, run detached with the real switches, relaunch) is written and tested through fakes only: there is no Windows or Inno Setup here,
  so the `.iss` change (`RelaunchRequested`, `{param:SutraRelaunch|0}`) has not been compiled; the Windows release job compiles it first and will fail loudly if the Pascal is wrong.
- **macOS installs wait for a Developer ID build.** The release workflow signs ad hoc unless all four secrets exist. The first notarized release is the first the updater can install; a real
  signed DMG has therefore never passed through `codesign`/`spctl` here. Those two checks, the mount and the copy ran against fakes in the tests and against throwaway apps for the swap.
- **No real download was made.** The transport, the redirect rules and the caps are tested against fakes; no release asset was downloaded from GitHub in this work. One live run on the first signed release is
  the follow-up.
- **The beta channel cannot occur yet.** `pyproject.toml` stays at `X.Y.Z` for every beta of that version and the packager takes `X.Y.Z` only, so a beta app reports itself as the stable `X.Y.Z`;
  the rule (a stable install: stables only; a beta install: newer betas and stables) is implemented once on the server, re-checked on the desktop and tested, and starts to matter when a
  build can say it is a beta. For the same reason a beta app is never offered the stable of its own version.
- **No proxy support in the download**: the app's HTTPS transport is Node's, which does not read the system proxy (the server's check, `urllib`, does). A machine that needs a proxy
  gets "could not download" and the release page.
- **TOCTOU, as far as it can be closed**: the staging folder is private (`0700`), the file is hashed through one handle, macOS verifies the app inside the mount and then the copy that is
  installed, and Windows hashes and checks the signature again right before it runs the file. A process of the same user could still swap a file between a check and a run; that
  process could replace the app itself, so the folder permission is the boundary.
- **`GET /api/ops/update-setting` is an open read on loopback**, like the other ops reads (`require_token` passes safe methods); the writes (`PUT`, the three `POST`s) need the token.
- The packaged Electron app was not rebuilt or launched here: the controller, the glue and the server were exercised separately (unit tests, a throwaway local server for the glue, throwaway
  apps for the swap). The dialogs themselves are Electron's `showMessageBox` and were not seen on screen.
- Left as they were: "Releases" menu item; the About group's owner-click check (it still only tells).

## Tests

Run on this Mac at the end (all green): `cd desktop && npm test` 97 tests, 96 pass, 1 skipped (the opt-in swap proof; with `SUTRA_PRO_PROVE_SWAP=1` 97 of 97 pass); `node --test
tests/ui/js/*.test.js` 975 tests, 973 pass, 2 skipped; `tests/ops tests/contracts tests/ui tests/release tests/test_docs.py tests/test_traceability.py tests/test_ownership.py
tests/test_layout.py` 2083 passed, 220 skipped, 0 failed; `tests/library` (with its write-path allowlist test) 2347 passed, 4 skipped; the ownership audit has no hit under
`sutra-pro/`. One thing about the owner's single-command invocation: with `tests/ops` AND `tests/library` in one process, `tests/library/test_lib_records.py::test_all_does_not_freeze_the_registry_and_freeze_closes_it`
fails because `tests/ops/test_cli.py` froze the model registry earlier in the same process. It does the same on the base commit (checked on an unpacked copy of `2ae63d11`) and no file
involved was touched here; run in two halves both are green.


- Desktop (`cd desktop && npm test`, runs on the CI `desktop` job's three systems): `test/updater.test.js` (versions and channels, hostile answers, hosts and redirects, size caps, checksum
  mismatch with nothing installed, Team ID and bundle id mismatch, an unwritable install folder, the script text, the helper's arguments with spaces, the Windows argv, the timer cleared on quit,
  no check when offline, stub, self-test or switch off, the install-on-quit flag), `test/update_main.test.js` (the server glue against a throwaway local server, the menu item, the server's
  environment). The macOS swap proof is opt-in.
- Python: `tests/ops/test_update_plan.py` (asset facts, hostile assets, `plan()`, the five routes, the setting, the last check, request counting with an injected fetcher),
  `tests/ops/test_welcome.py`, `tests/release/test_desktop_bundle.py`.
- JS: `tests/ui/js/settings_about.test.js`, `tests/ui/js/welcome.test.js`; browser (opt-in, `SUTRA_BROWSER=1`): the About switch in `tests/ui/test_home_welcome_settings.py`.
