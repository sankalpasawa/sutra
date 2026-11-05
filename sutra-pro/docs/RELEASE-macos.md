# Releasing and installing Sutra Pro for macOS

The wheel release (`docs/RELEASE.md`, `release-wheel.yml`) and this one share a tag. Pushing `vX.Y.Z` (or `vX.Y.Z-beta.N`) runs both;
`release-macos.yml` adds the app and the DMGs to the same GitHub Release. Nothing here runs locally by itself.

## What a downloader gets

| Asset | For |
|---|---|
| `Sutra-Pro-arm64.dmg` and `Sutra-Pro-arm64.dmg.sha256` | Apple Silicon (M1 and later) |
| `Sutra-Pro-x86_64.dmg` and `Sutra-Pro-x86_64.dmg.sha256` | Intel |

The names carry no version, so `https://github.com/<owner>/<repo>/releases/latest/download/Sutra-Pro-arm64.dmg` always finds the newest
stable release (a `-beta.N` tag is a pre-release and never answers `latest`). Not sure which Mac you have? Apple menu, About This Mac:
"Apple M..." is arm64. Check the download with `shasum -a 256 -c Sutra-Pro-<arch>.dmg.sha256` in the folder it is in.

Open the DMG and drag **Sutra Pro** onto Applications. Opening the app starts the server on `127.0.0.1` (first free port from 8780 to 8799)
and opens your default browser on it. There is no window of its own (D12): quit the app (Dock icon, Quit, or Force Quit if the Dock
does not answer) and the server stops. Opening it again while it runs opens the browser on the running one.

- Data: `~/.sutra-pro` (override with `SUTRA_DATA_DIR`). One running instance per data folder.
- Log: `~/.sutra-pro/logs/app.log`, rotated to `app.log.1` at 5 MB. A start failure shows one dialog and names this file.
- The app carries its own Python 3.11 and every dependency. It needs the `claude` and/or `codex` CLI signed in on the Mac for real
  model calls (it looks in `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/.claude/local`, `~/.npm-global/bin`, `~/.bun/bin`
  besides the usual PATH; `SUTRA_EXTRA_PATH` adds more). Without them the app still starts; connectors report "not installed".
- First launch of an AD-HOC build (below) on another Mac: Gatekeeper refuses a plain double-click. Right-click the app, Open, Open.
  If macOS says the app is damaged after a browser download: `xattr -dr com.apple.quarantine "/Applications/Sutra Pro.app"`.

## Cutting a release

1. Bump `[project].version` in `pyproject.toml`, merge, tag `vX.Y.Z` (the guard compares the two and stops early on a mismatch).
2. Push the tag. `guard` (ubuntu) -> `dmg` (two legs in parallel, each built natively) -> `verify`.
3. Repair an old tag: `gh workflow run release-macos -f tag=vX.Y.Z --ref vX.Y.Z` (dispatch from the tag's own ref).

What each `dmg` leg does: builds the wheel from the tag's tree; `scripts/build_macos_app.py` makes `Sutra Pro.app` (a launcher script, a
python-build-standalone CPython 3.11 verified against its sha256 and cached, the wheel installed into it with the bundled
interpreter); signs every Mach-O file and then the bundle; **proves** the signed bundle by running its own launcher with the network cut
(outbound requests go to a closed proxy port) until `/api/health` answers with the wheel's version, then quitting it; makes the DMG with
`hdiutil create`; writes the `.sha256` of that DMG; uploads both. `verify` fails unless both legs succeeded, all four assets are on the
release and the published bytes match their checksums. A runner label that has been retired does not fail, it hangs in `queued`:
`verify` is what notices (see the labels in the workflow header).

## Signing

| Secrets | Result |
|---|---|
| none of the five | ad-hoc signed app and DMG: installs and runs, first launch needs right-click, Open |
| all five | Developer ID signed (hardened runtime), app and DMG notarized and stapled; the build fails if a ticket is missing |
| some | the build fails at once and names the missing ones |

`APPLE_CERT_P12` (base64 of a Developer ID Application `.p12`), `APPLE_CERT_PASSWORD`, `APPLE_NOTARY_KEY` (base64 of the App Store
Connect `.p8`), `APPLE_NOTARY_KEY_ID`, `APPLE_NOTARY_ISSUER`. They are read by three steps only (check, import, notarize x2) and never
printed. An ad-hoc build refuses to replace a DMG on the release that is already notarized.

## Facts to know

- Bundle identifier `os.sutra.pro`, name "Sutra Pro", executable `SutraPro` (a bash launcher, `scripts/macos/launcher.sh`), version = the
  wheel's `X.Y.Z`. Minimum macOS 11.
- Build the bundle by hand (needs network for the dependencies): `scripts/py scripts/build_macos_app.py --wheel dist/sutra_pro-X.Y.Z-py3-none-any.whl --arch arm64 --out build`
  on an Apple Silicon Mac (use `x86_64` on an Intel Mac). `--python-archive FILE` uses a local interpreter archive instead of downloading one.
- The interpreter pin: `PBS_TAG` and `PY_SERIES` in the script choose the release and the 3.11 patch; the archive is checked against the
  release's `SHA256SUMS`, and against `PINNED_SHA256` once a digest is listed there. The first CI build prints `pin candidate: ...`; copy
  that line into the table to make the pin independent of the release page.
- Not done (decisions in `docs/notes/REL-2.md`): no icon, no auto-update, no Windows build.
