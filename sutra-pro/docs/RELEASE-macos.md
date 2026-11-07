# Releasing and installing Sutra Pro for macOS

The wheel release (`docs/RELEASE.md`, `sutra-pro-release-wheel.yml`), the Windows release (`docs/RELEASE-windows.md`) and this one share a tag.
Pushing `sutra-pro-vX.Y.Z` (or `sutra-pro-vX.Y.Z-beta.N`) runs all three; `sutra-pro-release-macos.yml` adds the app and the DMGs to the same
GitHub Release, which is never marked "Latest" (D100). Nothing here runs locally by itself.

The Mac app is the **desktop app** (D116): an Electron window around the local server, with the Python the server runs on inside the app. The 0.1.x
apps were a launcher script that opened your browser; the id, the name and the asset names are the same, so the new app replaces the old one in place.

## What a downloader gets

| Asset | For |
|---|---|
| `Sutra-Pro-arm64.dmg` and `Sutra-Pro-arm64.dmg.sha256` | Apple Silicon (M1 and later) |
| `Sutra-Pro-x86_64.dmg` and `Sutra-Pro-x86_64.dmg.sha256` | Intel |

The names carry no version, so the one thing that changes in a link is the tag:
`https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/Sutra-Pro-arm64.dmg`. (`releases/latest` belongs to the old product in the
same repository, D100.) Not sure which Mac you have? Apple menu, About This Mac:
"Apple M..." is arm64. Check the download with `shasum -a 256 -c Sutra-Pro-<arch>.dmg.sha256` in the folder it is in.

**Needs macOS 13 (Ventura) or newer**: that is the floor of Electron 45, which the app is built on (`LSMinimumSystemVersion` in its Info.plist says so, and an
older Mac is told as much instead of failing). The 0.1.x launcher ran on macOS 11 and 12; those Macs keep that release.

Open the DMG and drag **Sutra Pro** onto Applications (over an earlier Sutra Pro: your data is not in the app). Opening the app opens its window. The app
starts its own server on `127.0.0.1` (the first free port from 8780 to 8799), shows it in the window and **stops it when the window closes** (Quit, or
the red button: the app ends with its last window). Opening it a second time brings the first window forward.

- Data: `~/.sutra-pro` (override with `SUTRA_DATA_DIR`). One server per data folder, and the app **attaches** to one that is already running there (the command line's
  `sutra-pro`, the 0.1.x launcher, a window that crashed) instead of starting another; an attached server is left running when the window closes.
- Logs: `~/.sutra-pro/logs/app.log` is the server's own, rotated to `app.log.1` at 5 MB; `~/.sutra-pro/logs/desktop.log` is the window's (what it did and what the
  server printed to it). Help, Show the Log reveals the second one. A start that fails shows one dialog with the last lines the server printed and
  the choices Try Again, Show the Log and Quit.
- The app carries its own Python 3.11 and every dependency (`Contents/Resources/python`). It needs the `claude` and/or `codex` CLI signed in on the Mac for real
  model calls (it looks in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/.claude/local`, `~/.npm-global/bin`, `~/.bun/bin`
  besides the usual PATH; `SUTRA_EXTRA_PATH` adds more). Without them the app still starts; connectors report "not installed".
- The window shows the server and nothing else: a link to another site opens in your browser (web addresses only), a permission request (camera, location,
  notifications) is refused, and the page has no access to files or Node.
- First launch of an AD-HOC build (below) on another Mac: Gatekeeper refuses a plain double-click. Right-click the app, Open, Open.
  If macOS says the app is damaged after a browser download: `xattr -dr com.apple.quarantine "/Applications/Sutra Pro.app"`.

## Cutting a release

1. Bump the version in `pyproject.toml`, `sutra_app/__init__.py` and `desktop/package.json` (see `docs/RELEASE.md`), merge, tag `sutra-pro-vX.Y.Z`
   (the guard compares the tag with `pyproject.toml` and stops early on a mismatch).
2. Push the tag. `guard` (ubuntu) -> `dmg` (two legs in parallel, each built natively) -> `verify`.
3. Repair an old tag: `gh workflow run sutra-pro-release-macos -f tag=sutra-pro-vX.Y.Z --ref sutra-pro-vX.Y.Z` (dispatch from the tag's own ref).

What each `dmg` leg does:

1. builds the wheel from the tag's tree and sets up Node 22 (the packager needs 22.12 or newer);
2. `scripts/build_desktop_app.py --target mac-arm64|mac-x64` runs `npm ci` in `desktop/` (the exact versions of its lock file), has `@electron/packager` make
   `Sutra Pro.app` from Electron and `desktop/src`, unpacks the python-build-standalone CPython 3.11 (its sha256 checked, the download cached) into
   `Contents/Resources/python` and installs the wheel into it with that interpreter, then checks that every symbolic link stays inside the app;
3. `scripts/sign_desktop_app.sh` signs inside out (below) and audits every Mach-O file;
4. **proves** the signed app (`scripts/prove_desktop_app.py`, D120), with the network cut (outbound requests go to a closed proxy port): the real window
   starts its server on the Python inside the app, draws the page, gets `/api/health` from inside the page with the wheel's version, saves a picture and quits,
   which must stop the server and leave nothing running; then the server alone runs a team's first turn (a department, a task, an engine process that
   reaches `waiting_user`) and a stop request ends it. Afterwards `codesign --verify` must still pass: running the app changed no byte of what was signed.
   The picture and the logs are kept as the workflow artifact `proof-mac-arm64` or `proof-mac-x64`;
5. notarizes and staples the app, makes the DMG with `hdiutil create`, notarizes and staples that, writes the `.sha256`, uploads both.

`verify` fails unless both legs succeeded, all four assets are on the release and the published bytes match their checksums. A runner label that has been
retired does not fail, it hangs in `queued`: `verify` is what notices (see the labels in the workflow header).

## Signing

| Secrets | Result |
|---|---|
| none of the four | ad-hoc signed app and DMG: installs and runs, first launch needs right-click, Open |
| all four | Developer ID signed (hardened runtime), app and DMG notarized and stapled; the build fails if a ticket is missing |
| some | the build fails at once and names the missing ones |

`APPLE_CERT_P12` (base64 of a Developer ID Application `.p12`), `APPLE_NOTARY_KEY` (base64 of the App Store Connect `.p8`),
`APPLE_NOTARY_KEY_ID` and `APPLE_NOTARY_ISSUER` decide; `APPLE_CERT_PASSWORD` is the `.p12`'s password and is optional, because a certificate
can be exported without one (this repository's is: the first run said "missing: APPLE_CERT_PASSWORD" when all five were required). They are the
repository's secrets, the same ones the old product's `release-dmg.yml` reads; they are read by three steps only (check, import, notarize x2) and
never printed. An ad-hoc build refuses to replace a DMG on the release that is already notarized.

`scripts/sign_desktop_app.sh` signs the way the old product's `make-dmg.sh` does, for the same reasons: the Python's Mach-O files first, then every file
under `Contents/Frameworks` deepest first (a framework's own binary is signed with its `Versions/A` bundle, never alone), the helper apps, the frameworks,
and the app last; `--deep` is only used to verify. Two short entitlements files, each with the reason for every line (`desktop/entitlements.electron.plist`,
`desktop/entitlements.python.plist`): Electron's processes get `allow-jit` and `allow-unsigned-executable-memory` (V8 compiles JavaScript while it runs) and keep
library validation on; only the interpreter gets `disable-library-validation` and `allow-unsigned-executable-memory` (CPython loads its extension modules, ctypes
writes machine code). No sandbox, camera, microphone, location, Apple Events or DYLD variables. Before the round trip to Apple the script **audits** what notarization checks:
every Mach-O file in the app, found by what it is and not by its name, must carry the hardened runtime and a secure timestamp, or the build stops and names the file.

## Facts to know

- Bundle identifier `os.sutra.pro`, name "Sutra Pro", executable `Sutra Pro` (Electron's), version = the wheel's `X.Y.Z`, icon the old Sutra's
  (`assets/icon/sutra-pro.icns` is that product's `Sutra.icns` byte for byte, D117; the bundle carries it as `Contents/Resources/electron.icns`). Minimum macOS 13.
  `Contents/Resources/build-info.json` says what went in: version, target, Electron's version, the interpreter archive and its sha256, the wheel and its sha256.
- Build the app by hand (needs Node 22 or newer and the network): `scripts/py scripts/build_desktop_app.py --wheel dist/sutra_pro-X.Y.Z-py3-none-any.whl --target mac-arm64 --out build`
  on an Apple Silicon Mac (`mac-x64` on an Intel Mac); `--skip-npm` when `desktop/node_modules` is already installed, `--python-archive FILE` uses a local interpreter
  archive instead of downloading one. Sign it ad hoc with `scripts/sign_desktop_app.sh "build/Sutra Pro.app"`, or with a Developer ID in the keychain:
  `SIGN_IDENTITY="Developer ID Application: ..." SIGN_TIMESTAMP=none scripts/sign_desktop_app.sh "build/Sutra Pro.app"` (no timestamp: it needs the network).
  Prove it: `scripts/py scripts/prove_desktop_app.py --app "build/Sutra Pro.app" --version X.Y.Z` (`--keep DIR` keeps the picture and the logs).
- Run the window from a checkout, on the checkout's own Python: `cd desktop && npm ci && npm start` (`SUTRA_PRO_PYTHON` names another interpreter; see `desktop/README.md`).
- The interpreter pin: `PBS_TAG` and `PY_SERIES` in `scripts/build_macos_app.py` choose the release and the 3.11 patch; the archive is checked against the
  release's `SHA256SUMS`, and against `PINNED_SHA256` once a digest is listed there. The desktop builder uses the same table.
- The 0.1.x launcher (`scripts/macos/launcher.sh`, `Info.plist.tmpl`, `build_app` in `scripts/build_macos_app.py`) stays in the tree with its tests but no workflow builds it
  any more; its interpreter download and wheel installation are what the desktop builder reuses.
- Not done (decisions in `docs/DECISIONS.md` D116): no auto-update (the release is never "Latest", which is what an updater would read), and Electron's
  fuses (`RunAsNode` and the like) are left at their defaults.
