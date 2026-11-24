# Sutra Pro Beta on Windows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/py scripts/install_app.py beta [--pull]` builds, proves, installs and opens "Sutra Pro Beta" on Windows x64, as it does on a Mac.

**Architecture:** The builder, the proof and the installer learn the Windows layout of the beta (a folder holding `Sutra Pro Beta.exe`, `resources/build-info.json`). The installer's Mac-only calls (ps, ditto, xattr, codesign, osascript, open) get Windows counterparts chosen by `sys.platform`; the Mac path is unchanged.

**Tech Stack:** Python 3.11 standard library (scripts), PowerShell for the process table and the shortcut, Electron packager (existing), Pillow only when the icon is regenerated.

**Spec:** `docs/design/windows-beta/design.md`

## Global Constraints
- Channel identity from `desktop/src/channels.json` only: "Sutra Pro Beta", `os.sutra.pro.beta`, `~/.sutra-pro-beta`, `updates: false`.
- Never quit a working app (exit 3, `--force` is the owner's word); never kill: a Windows quit is `taskkill /PID <window>` without `/F` (WM_CLOSE, the window's own quit path, which stops its server).
- No home path or name in repository files; the Windows default install folder is `%LOCALAPPDATA%\Programs`.
- `release` stays Mac-only. The Mac beta path does not change (its tests stay green unchanged).

## Review Focus
1. A beta running while the install runs: busy means exit 3 and nothing replaced; idle means closed, then replaced.
2. `--pull` on a dirty tree or a branch without upstream: refused before anything is built.
3. The installed folder name differs from the built one (`--install-dir`): the proof and the bundle check read the app name from build-info.json, not the folder name.
4. A stable "Sutra Pro" folder in the same install dir: never touched, never matched as the beta's processes (`D:\Programs\Sutra Pro\` vs `D:\Programs\Sutra Pro Beta\`).
5. A failed copy leaves the old beta in place.

---

### Task 1: The builder and the proof know a Windows beta
**Files:** Modify `scripts/build_desktop_app.py` (the refusal at the channel check), `scripts/prove_desktop_app.py` (`layout`), `desktop/src/channels.json` (beta `ico`, `windowsIconName`), `scripts/make_beta_icon.py` (derive the Windows beta icon); add `assets/icon/sutra-pro-beta-windows.ico`, `assets/icon/sutra-pro-beta-windows-1024.png`. Test: `tests/release/test_beta_channel.py`.
- [ ] Test: `test_a_channel_must_exist_and_a_beta_builds_for_windows_too` — `build(work, "win-x64", channel="beta")` returns `<out>/Sutra Pro Beta`, its build-info says `bundle_id == "os.sutra.pro.beta"`, `channel == "beta"`; unknown channel still raises. Replaces `test_a_beta_is_a_mac_app_and_a_channel_must_exist`.
- [ ] Test: `test_the_windows_proof_starts_the_exe_its_build_info_names` — with `WINDOWS=True`, a folder `x/installed` whose `resources/build-info.json` says `"app": "Sutra Pro Beta"` gives `x/installed/Sutra Pro Beta.exe`; without build-info, `Sutra Pro.exe`.
- [ ] Test: the committed beta icon test also checks `channels.json` beta `ico`/`windowsIconName` exist and differ from the stable ones.
- [ ] Implement; regenerate icons with `uv run --with pillow python scripts/make_beta_icon.py`.
- [ ] `pytest tests/release/test_beta_channel.py` passes; commit.

### Task 2: The installer's Windows layer
**Files:** Modify `scripts/install_app.py`. Test: `tests/release/test_install_app.py` (a `windows_system` fixture: `sys.platform = "win32"`, `platform.machine() = "AMD64"`, fake `powershell`/`taskkill` commands).
**Produces:** `host_target() -> ("win-x64", "x64")` on Windows; `bundle(channel, dir)` -> `dir/<appName>` on Windows; `bundle_facts` from `resources/build-info.json` (`bundle_id`, `version`, `app`, `build`); `check_bundle` without codesign on Windows; `running(app)` marker `str(app) + os.sep`; `process_table()` from `Get-CimInstance Win32_Process` (pid, ppid, command line); `quit_app` closes the window (`taskkill /PID <oldest window pid>`, no `/F`); `replace_bundle` with `shutil.copytree`; `open_and_check` starts `<app>/<appName>.exe` detached; `DEFAULT_INSTALL_DIR` is `%LOCALAPPDATA%\Programs` on Windows.
- [ ] Tests (each fails first): target on Windows; folder bundle path; facts from build-info; the beta's processes exclude the stable folder's; a busy beta is not closed; an idle one gets `taskkill` without `/F`; a failed copy keeps the old beta; open starts the exe and waits for the version.
- [ ] Implement; Mac tests untouched and green.
- [ ] Commit.

### Task 3: `install_beta` on Windows, `--pull`, the shortcut
**Files:** `scripts/install_app.py`, `tests/release/test_install_app.py`.
**Produces:** `pull_main() -> None` (refuses a dirty tree or no upstream; `git fetch origin`, `git merge --ff-only @{u}`); `write_shortcut(app: Path, channel: str) -> Path` (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\<appName>.lnk` via PowerShell `WScript.Shell`); `install_beta(..., pull=False)` skips ad hoc signing on Windows and writes the shortcut.
- [ ] Tests: a Windows beta is built for `win-x64`, proved, installed beside a stable folder that stays as it was, no `sign_desktop_app.sh` call, the shortcut is written; `--pull` on a dirty tree raises before `uv build`; `--pull` runs fetch then `merge --ff-only`.
- [ ] Implement; commit.

### Task 4: Rules and docs
**Files:** `AGENTS.md` (the beta exists on a Mac and on Windows), `docs/RELEASE.md` (the two-apps table gets the Windows column and the update command), `docs/DECISIONS.md` + `docs/diagram/decisions.json` (next free D number), module docstrings of the three scripts.
- [ ] `pytest tests/test_diagram_decisions.py tests/test_ownership.py tests/release` green (Windows-only symlink test excepted, pre-existing); commit; push to main.

### Task 5: On this PC
- [ ] `git worktree add D:\sutra-beta -b beta-main origin/main` (upstream `origin/main`).
- [ ] From `D:\sutra-beta\sutra-pro`: `scripts/py scripts/install_app.py beta --install-dir "D:\Programs"`; report version, commit, data folder.
