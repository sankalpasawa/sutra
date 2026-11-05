# Releasing and installing Sutra Pro for Windows

The wheel release (`docs/RELEASE.md`, `sutra-pro-release-wheel.yml`), the Mac release (`docs/RELEASE-macos.md`) and this one share a tag.
Pushing `sutra-pro-vX.Y.Z` (or `sutra-pro-vX.Y.Z-beta.N`) runs all three; `sutra-pro-release-windows.yml` adds the installer and the
zip to the same GitHub Release. Nothing here runs locally by itself. The decisions behind it are D98 to D102.

## What a downloader gets

| Asset | For |
|---|---|
| `Sutra-Pro-Setup-x64.exe` and `.sha256` | the installer: per user, no administrator rights |
| `Sutra-Pro-win-x64.zip` and `.sha256` | the same app, portable: unzip anywhere, run `Sutra Pro.cmd` |

Windows 10 or 11, 64-bit. (Windows on ARM runs it through Windows' own x64 emulation.) The release is never marked "Latest" (D100), so the
links carry the tag:

    https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/Sutra-Pro-Setup-x64.exe

Check a download with `certutil -hashfile Sutra-Pro-Setup-x64.exe SHA256` and compare it with the `.sha256` file next to it.

## Install and start

1. Run `Sutra-Pro-Setup-x64.exe`. **The build is not signed (D102), so Windows SmartScreen says "Windows protected your PC": choose
   "More info", then "Run anyway".** The installer needs no administrator rights; it installs to `%LOCALAPPDATA%\Programs\Sutra Pro`
   and adds Start menu entries: **Sutra Pro**, **Quit Sutra Pro**, **Sutra Pro Doctor**. A desktop shortcut is an option.
2. Start **Sutra Pro**. It starts a server on `127.0.0.1` (the first free port from 8780 to 8799) and opens your browser on it
   (Chrome when it is installed, else the default browser). There is no window of its own (D12): an icon appears in the notification
   area with **Open Sutra Pro** and **Quit Sutra Pro**. Starting it again while it runs just opens the browser on the running one.
3. For real model calls the machine needs the `claude` and/or `codex` command line tools, signed in with your own subscriptions. Run
   **Sutra Pro Doctor** to see what is missing. Without them the app still starts and says so; `sutra-pro.cmd --offline` is a demo
   with no model and no login.

- Data: `%USERPROFILE%\.sutra-pro` (override with `SUTRA_DATA_DIR`). One running instance per data folder.
- Log: `%USERPROFILE%\.sutra-pro\logs\app.log`. A start that failed before logging began is in `desktop.log` there, and one message box names it.
- Command line: `"%LOCALAPPDATA%\Programs\Sutra Pro\sutra-pro.cmd" doctor | status | stop | config | open` (put that folder on your PATH to type
  `sutra-pro`).
- Quit: the notification-area icon, **Quit Sutra Pro** in the Start menu, or `sutra-pro stop`. A server with no console cannot be
  signalled, so quitting writes `app.stop` into the data folder, which the server polls once a second and answers like a SIGTERM.
- Update: run the newer installer; it asks the running app to stop, then copies the new files over the old. Uninstall: Settings, Apps
  (or the uninstaller in the install folder). **Your data folder is never removed** by either.
- The zip needs no installation: unzip it, run `Sutra Pro.cmd`. Nothing is written outside the folder and your data folder.

## Cutting a release

Exactly as the Mac release, there is one tag: see `docs/RELEASE.md`. What the `sutra-pro-release-windows` run does:

| Job | What |
|---|---|
| `guard` (ubuntu) | `scripts/check_release_tag.py` compares the tag with `pyproject.toml`; a dispatched tag must exist. Seconds, no costly runner. |
| `exe` (windows-latest) | builds the wheel; `scripts/build_windows_app.py` makes `Sutra Pro/`; **proves the folder runs**; compiles the installer with Inno Setup; **proves the installer** (silent install, the installed copy proved, silent uninstall, nothing left); zips the folder; writes a checksum per file; attaches all four files to the release |
| `verify` (windows-latest) | downloads what was **published**, checks the checksums and the sizes, installs the published installer and proves the installed copy, uninstalls it, unzips the published zip and proves that too |

The proof (`scripts/prove_windows_app.py`) runs the folder the way the Start menu entry does: `SutraPro.exe -I -X utf8 -m sutra_app.desktop`,
offline, with every proxy pointing at a closed port. It checks that `/api/health` answers with the wheel's version, that a message posts
with the page's token and its turn ends, that a department can be added and given a task so an engine process starts and the task
reaches `waiting_user`, that `stop` ends the server, and that no process of the data folder is left. A tray icon that cannot be shown
(a CI session has no notification area) is logged and does not fail the proof.

Repair an old tag: `gh workflow run sutra-pro-release-windows -f tag=sutra-pro-vX.Y.Z --ref sutra-pro-vX.Y.Z`.

## What is in the folder

`scripts/build_windows_app.py` builds `Sutra Pro/` (the folder the installer copies and the zip holds):

| Path | What |
|---|---|
| `python/` | python-build-standalone CPython 3.11 (the release pinned in `scripts/build_macos_app.py`, its sha256 checked) with the wheel, its dependencies and the tray extra (`pystray`, Pillow) installed by that interpreter |
| `python/SutraPro.exe` | a copy of `pythonw.exe`: the app's process, so Task Manager says SutraPro and no console window opens |
| `Sutra Pro.cmd`, `Quit Sutra Pro.cmd`, `sutra-pro.cmd` | start, stop, command line; each runs the interpreter with `-I` (no `PYTHON*` variables, no user site) and `-X utf8` |
| `icon/sutra-pro.ico`, `README.txt`, `build-info.json` | the icon, the user's first page, what went in |

Nothing in it is a compiled program of ours, so there is nothing to sign but the installer, and nothing for a virus scanner to guess at
beyond what python.org ships. The installer script is `scripts/windows/sutra-pro.iss` (per user, `PrivilegesRequired=lowest`).

## Facts to know

- **Not signed (D102).** SmartScreen asks once per download until the file has a reputation. A code-signing certificate would remove
  it; the workflow has no step for it because there is no certificate. The checksums on the release are the integrity check meanwhile.
- **No auto-update.** A new version is a new installer.
- **The model CLIs on Windows.** They are looked up on PATH with `PATHEXT`, so an npm `claude.cmd` and a native `claude.exe` both work, and
  the connectors pass them the few variables a Windows program needs to start (`SYSTEMROOT`, `USERPROFILE`, `APPDATA`, ...) and nothing
  that looks like a secret. If `claude` runs in your terminal but not here, `sutra-pro doctor` says what it saw.
- **Ending a run.** A stopped task asks its engine to stop through the run's inbox first; only then is the process tree ended with
  `taskkill /T /F`. The model CLI children are held in a job object, so ending one ends everything it started.
- **Tests.** The Windows leg of `sutra-pro-ci` runs the suite on a Windows runner; the tests that need POSIX process semantics are skipped there
  by name with the reason (`tests/conftest.py`), and `tests/ops/test_oslayer.py` runs on every system and is the proof of the Windows branches.
