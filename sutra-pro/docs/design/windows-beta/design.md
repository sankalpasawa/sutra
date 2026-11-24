# Sutra Pro Beta on Windows (short design)

## Intent
The owner works on Windows and wants to try what is on `main` without waiting for a release: a "Sutra Pro Beta" app on the PC, built from `main`, installed
beside the stable Sutra Pro, updated whenever the owner asks. Today the beta exists only on a Mac (AGENTS.md; `build_desktop_app.py` refuses a Windows beta).

## Goals
- `scripts/py scripts/install_app.py beta` works on Windows x64 as it does on the Mac: build this tree's wheel, build the packaged app (Electron plus the
  Python inside it) on the beta channel, prove that it starts offline, quit a running idle beta, install it, open it, wait for `/api/health`.
- `--pull` first fast-forwards the checkout to `origin/main` (refused when the tree has changes or is not on its tracking branch), so one command updates the beta.
- A checkout of its own that only follows `main`, so work branches never end up in the beta.
- A Start-menu shortcut "Sutra Pro Beta"; an icon with the orange BETA band, so the two apps differ in the taskbar.

## Non-goals
- No installer (.exe setup), no signing, no automatic update: the beta channel has `updates: false` and stays that way.
- The stable app, its folder and `~/.sutra-pro` are not touched. No Linux beta.

## Constraints
- Same identity as the Mac beta (desktop/src/channels.json): name "Sutra Pro Beta", id `os.sutra.pro.beta`, data `~/.sutra-pro-beta`.
- Never quit a working app: the busy check runs before the quit, exit status 3 when busy, `--force` is the owner's word. Nothing is killed: the beta is asked to
  stop (`sutra-pro stop` on its own data folder, which closes the window too) and the install waits; if it does not close, the script says so and stops.
- No home path or name in repository files: the install folder defaults to `%LOCALAPPDATA%\Programs`; `--install-dir` chooses another.

## Approaches
1. **Packaged app from the checkout (chosen by the owner).** The same app the release ships, built on this PC; an update is a pull and a 3 to 5 minute
   rebuild. Catches packaging faults (as the one that stopped 0.8.0).
2. Run the server from the checkout in a plain window. An update is a pull and a restart, but packaging faults go unseen. Not chosen.

## The how (decided)
- `install_app.py`: `host_target()` gives `win-x64` on Windows; the bundle path is a folder (`<install-dir>\Sutra Pro Beta`), not a `.app`; copy with
  `shutil.copytree` into `.new`, then swap (as on the Mac); no ad hoc signing; open with the folder's `Sutra Pro Beta.exe`; the process table from
  `Get-CimInstance Win32_Process` (as `prove_windows_app.py` does). `release` stays Mac-only.
- `build_desktop_app.py`: the beta channel builds for `win-x64` too.
- `channels.json`: the beta gets its own `.ico`, made from `sutra-pro-beta-1024.png`.
- Shortcut: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Sutra Pro Beta.lnk`, written with PowerShell's `WScript.Shell`.
- Docs: AGENTS.md ("the beta exists on a Mac and on Windows"), docs/RELEASE.md ("One Mac, two apps" covers Windows), a decision in DECISIONS.md and
  decisions.json.

## On this PC (not in the repository)
- The beta's checkout: a new worktree on D: (C: has 14 GB free), on a branch that tracks `origin/main`.
- Installed into `D:\Programs\Sutra Pro Beta`, beside the stable app in `D:\Programs\Sutra Pro`.
- To update later: in that checkout, `scripts/py scripts/install_app.py beta --pull --install-dir "D:\Programs"`.

## Left to the builder
- The exact form of the busy message and of the dry-run lines on Windows; test names.
