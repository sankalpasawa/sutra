# Releasing and installing Sutra Pro for Windows

The wheel release (`docs/RELEASE.md`, `sutra-pro-release-wheel.yml`), the Mac release (`docs/RELEASE-macos.md`) and this one share a tag.
Pushing `sutra-pro-vX.Y.Z` (or `sutra-pro-vX.Y.Z-beta.N`) runs all three; `sutra-pro-release-windows.yml` adds the installer and the
zip to the same GitHub Release. Nothing here runs locally by itself. The decisions behind it are D98 to D102 and D105 to D109.

The Windows app is the **desktop app** (D105): an Electron window around the local server, with the Python the server runs on inside the app. The 0.1.x app
was a launcher with a notification-area icon that opened your browser. The installer's id, the names and the asset names are the same, so installing the
new one over the old one is an upgrade: it clears what the old layout left and keeps your data.

## What a downloader gets

| Asset | For |
|---|---|
| `Sutra-Pro-Setup-x64.exe` and `.sha256` | the installer: per user, no administrator rights |
| `Sutra-Pro-win-x64.zip` and `.sha256` | the same app, portable: unzip anywhere, run `Sutra Pro.exe` |

Windows 10 or 11, 64-bit. (Windows on ARM runs it through Windows' own x64 emulation.) The release is never marked "Latest" (D100), so the
links carry the tag:

    https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/Sutra-Pro-Setup-x64.exe

Check a download with `certutil -hashfile Sutra-Pro-Setup-x64.exe SHA256` and compare it with the `.sha256` file next to it.

## Install and start

1. Run `Sutra-Pro-Setup-x64.exe`. **The build is not signed (D102), so Windows SmartScreen says "Windows protected your PC": choose
   "More info", then "Run anyway".** The installer needs no administrator rights; it installs to `%LOCALAPPDATA%\Programs\Sutra Pro`
   and adds Start menu entries: **Sutra Pro** and **Sutra Pro Doctor**. A desktop shortcut is an option.
2. Start **Sutra Pro**. A window opens. The app starts its own server on `127.0.0.1` (the first free port from 8780 to 8799), shows it in the window and
   **stops it when the window closes** (File, Exit, or the close button). Starting it again while it runs brings the first window forward. There is no
   notification-area icon any more: the window is the app.
3. For real model calls the machine needs the `claude` and/or `codex` command line tools, signed in with your own subscriptions. Run
   **Sutra Pro Doctor** to see what is missing. Without them the app still starts and says so; `sutra-pro.cmd --offline` is a demo
   with no model and no login.

- Data: `%USERPROFILE%\.sutra-pro` (override with `SUTRA_DATA_DIR`). One server per data folder; the app **attaches** to one that is already running there (the
  command line's, an older app's) instead of starting another, and leaves an attached server running when the window closes.
- Logs: `%USERPROFILE%\.sutra-pro\logs\app.log` is the server's own; `desktop.log` beside it is the window's (what it did and what the server printed to it).
  Help, Show the Log reveals it. A start that fails shows one dialog with the last lines the server printed.
- Command line: `"%LOCALAPPDATA%\Programs\Sutra Pro\sutra-pro.cmd" doctor | status | stop | config | open` (put that folder on your PATH to type `sutra-pro`).
- Quit: close the window. A server with no console cannot be signalled, so the app ends the server it started by closing the server's input (the server was
  started with `--exit-when-stdin-closes`); `sutra-pro stop` writes `app.stop` into the data folder, which the server polls and answers like a SIGTERM. Both
  work, and the app falls back from one to the other and then to `taskkill /T /F` if the server does not follow.
- Update: run the newer installer; it asks a running server to stop, then copies the new files over the old (close the window first, or the installer asks you to).
  Uninstall: Settings, Apps (or the uninstaller in the install folder). **Your data folder is never removed** by either.
- The zip needs no installation: unzip it, run `Sutra Pro.exe`. Nothing is written outside the folder, your data folder and the app's own settings
  (`%APPDATA%\Sutra Pro`, Chromium's cache).

## Cutting a release

Exactly as the Mac release, there is one tag: see `docs/RELEASE.md`. What the `sutra-pro-release-windows` run does:

| Job | What |
|---|---|
| `guard` (ubuntu) | `scripts/check_release_tag.py` compares the tag with `pyproject.toml`; a dispatched tag must exist. Seconds, no costly runner. |
| `exe` (windows-latest) | builds the wheel and sets up Node 22; `scripts/build_desktop_app.py --target win-x64` makes `Sutra Pro/`; **proves the folder runs**; compiles the installer with Inno Setup; **proves the installer** (silent install, the installed copy proved, silent uninstall, nothing left); zips the folder; writes a checksum per file; attaches all four files to the release |
| `verify` (windows-latest) | downloads what was **published**, checks the checksums and the sizes, installs the published installer and proves the installed copy, uninstalls it, **installs the real 0.1.0 installer and the published one over it** (the old layout must be gone and the new app must prove itself; skipped with a notice if the 0.1.0 release is no longer there), unzips the published zip and proves that too |

The proof (`scripts/prove_desktop_app.py`, D109) runs the app the way the Start menu entry does, offline, with every proxy pointing at a closed port. First the
window: `Sutra Pro.exe` starts with `SUTRA_PRO_SELFTEST=1`, starts its server on `resources\python\python.exe`, draws the page, and the app asks the page whether it
finished loading, is the server's own, drew something, and gets `/api/health` (with the wheel's version) from inside it; it saves a picture, writes
`selftest.json` and quits, which must stop the server and leave no process of the data folder. Then the server alone, on that interpreter: a message posts with the
page's token and its turn ends, a department can be added and given a task so an engine process starts and the task reaches `waiting_user`, `stop` ends the
server, and nothing is left. The picture and the logs are kept as the workflow artifact `proof-win-x64`.

Repair an old tag: `gh workflow run sutra-pro-release-windows -f tag=sutra-pro-vX.Y.Z --ref sutra-pro-vX.Y.Z`.

## What is in the folder

`scripts/build_desktop_app.py --target win-x64` builds `Sutra Pro/` (the folder the installer copies and the zip holds):

| Path | What |
|---|---|
| `Sutra Pro.exe` and Electron's files | the window; the exe carries the old Sutra's icon (`assets/icon/sutra-pro.ico`, D106) and the product name `Sutra Pro` |
| `resources/app.asar` | `desktop/package.json` and `desktop/src` and nothing else |
| `resources/python/` | python-build-standalone CPython 3.11 (the release pinned in `scripts/build_macos_app.py`, its sha256 checked) with the wheel and its dependencies installed by that interpreter |
| `resources/build-info.json`, `resources/sutra-pro-1024.png` | what went in; the window's own picture of the logo for its first pages |
| `sutra-pro.cmd` | the command line: the interpreter with `-I` (no `PYTHON*` variables, no user site), `-B` (no bytecode written into the install) and `-X utf8` |
| `README.txt` | the user's first page |

Nothing in it is a program of ours that is compiled, so there is nothing to sign but the installer and the exe, and nothing for a virus scanner to
guess at beyond what python.org and Electron ship. The installer script is `scripts/windows/sutra-pro-desktop.iss` (per user, `PrivilegesRequired=lowest`;
the 0.1.x script `sutra-pro.iss` stays in the tree but no workflow compiles it).

## Facts to know

- **Not signed (D102).** SmartScreen asks once per download until the file has a reputation. A code-signing certificate would remove
  it; the workflow has no step for it because there is no certificate. The checksums on the release are the integrity check meanwhile.
- **No auto-update.** A new version is a new installer.
- **The model CLIs on Windows.** They are looked up on PATH with `PATHEXT`, so an npm `claude.cmd` and a native `claude.exe` both work, and
  the connectors pass them the few variables a Windows program needs to start (`SYSTEMROOT`, `USERPROFILE`, `APPDATA`, ...) and nothing
  that looks like a secret. The window adds `%APPDATA%\npm` and `~\.local\bin` to the server's PATH. If `claude` runs in your terminal but not here,
  `sutra-pro doctor` says what it saw.
- **Ending a run.** A stopped task asks its engine to stop through the run's inbox first; only then is the process tree ended with
  `taskkill /T /F`. The model CLI children are held in a job object, so ending one ends everything it started.
- **Tests.** The Windows leg of `sutra-pro-ci` runs the suite on a Windows runner, and its `desktop` job runs the window's node tests; the tests that need POSIX
  process semantics are skipped there by name with the reason (`tests/conftest.py`), and `tests/ops/test_oslayer.py` runs on every system and is the proof of the Windows branches.
- **Not proved on a real desktop yet:** the runner has a session but nobody looks at it. The picture the proof keeps is what the window drew there.
