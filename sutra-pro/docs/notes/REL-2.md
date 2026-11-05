# REL-2 as built: macOS app bundle, DMG and its release workflow

## Built
- `scripts/build_macos_app.py` (stdlib only): `--wheel --arch --out [--python-archive --cache-dir --allow-foreign-arch]`. Makes `<out>/Sutra Pro.app` = `Contents/{Info.plist,PkgInfo,MacOS/SutraPro,Resources/python,Resources/build-info.json}`. Builds in a stage folder beside the target and renames at the end (a failed build leaves the earlier app). Never signs. Exit 0 / 1 (`error:` line) / 2 (usage).
- `scripts/macos/launcher.sh` (bash 3.2 safe), `scripts/macos/Info.plist.tmpl` (three fields), `.github/workflows/release-macos.yml` (`guard` -> `dmg` x2 -> `verify`), `docs/RELEASE-macos.md`, `tests/release/test_macos_bundle.py` (113 tests, about 15 s: 12 s of them run the real launcher).

## Decisions
- Bundle id `os.sutra.pro` (the old app was `os.sutra.ui`; same namespace, no clash), executable `SutraPro` (no space), min macOS 11, no icon.
- App version = the wheel's METADATA version, which must be X.Y.Z (a CFBundleVersion is three integers); a beta tag builds the wheel of its X.Y.Z.
- The wheel is installed by the bundled interpreter at build time (`pip install`, dependencies from the index); the console scripts pip adds to `python/bin` are deleted (absolute shebang naming the build folder). The bundle must then import `sutra_app` at the wheel's version.
- Native builds only: a foreign `--arch` is refused unless `--allow-foreign-arch` (tests with a fake interpreter use it).
- Launcher: port from `SUTRA_PORT` or the first free of 8780-8799 (`SUTRA_PORT_MIN/MAX` exist for tests), probed with bash `/dev/tcp`; passes `--no-browser --port --data-dir`; one instance per data folder via `app.pid` ("pid port", checked with /api/health); a second launch opens the browser on the first. PATH is extended AFTER the system PATH with the usual CLI folders (a GUI app gets a bare PATH). Python env is scrubbed (`PYTHONPATH` etc. unset, `PYTHONNOUSERSITE`, `PYTHONDONTWRITEBYTECODE`: nothing may write into the signed bundle). A detached watchdog stops the server within ~1 s even when the launcher is SIGKILLed. Start failure: one osascript dialog (`SUTRA_NO_DIALOG=1` silences it) and exit 1.
- Secrets: one step ("Check the signing secrets") reads all five and publishes `enabled`; all five = Developer ID + notarize + staple, none = ad hoc, some = the build FAILS (not a quiet downgrade). Secrets appear only in the env of the 4 steps that need them (test enforced).
- Signing is inside out: every Mach-O under `Contents/Resources`, then the bundle. Entitlements (written by the step itself, since this package owns no entitlements file): `disable-library-validation` and `allow-unsigned-executable-memory`, nothing else.
- The signed bundle is proved BEFORE notarizing: real launcher, network cut (proxy vars to a closed port, `PIP_NO_INDEX`), `/api/health` must report `ok` and the wheel's version, SIGTERM must stop the server, `codesign --verify` again afterwards.
- Downgrade guard: an ad-hoc leg refuses to replace its OWN architecture's DMG when that DMG has a stapled ticket (the old workflow refused on any DMG, which fails the second parallel leg of the same run).
- The release body is NOT set (release-wheel.yml owns it; two writers would overwrite each other). Upload is `softprops/action-gh-release@v2`.
- `verify` runs on ubuntu, also fails when the `dmg` job result is not success (the old file's `always()` could pass on assets of an earlier run).

## Deviations from the specification
1. `docs/design/release.md` does not exist; the caller's FULL SPEC and `build-plan.json` were the only source (as in REL-1).
2. "Pinned checksum": the tag (`PBS_TAG` 20260901, the one the old repo's DMG pins) and series 3.11 are pinned; the exact patch is resolved from the release's `SHA256SUMS` and the archive is verified against it. A hard digest table `PINNED_SHA256` exists but is EMPTY: no network was allowed here, so no real digest could be read. The first CI build prints `pin candidate: ...`; copying it in makes the pin independent of the release page.
3. `--python-archive` is trusted as given (no digest check): it is the offline/test path and the workflow never uses it.
4. Secrets presence is not a job-level boolean as in the old file ("secrets only in the env of signing steps" forbids it); a step output replaces it.

## Known limits
- Never run on GitHub or on a real signing identity; `PINNED_SHA256` empty; the 3.11 archive name was not checked against the real release listing.
- A bash-script app has no AppKit loop: Dock "Quit" may need Force Quit (SIGTERM and SIGKILL both end the server cleanly). No icon.
- `/api/health` and `python -m sutra_app --no-browser --port --data-dir` do not exist yet (ORCH-8): the proof step and a real app need them.
- Data folder: the launcher sets `SUTRA_DATA_DIR=~/.sutra-pro`; the orchestrator design's own fallback is `~/.sutra-app`.

## Follow-ups and needs
- ORCH-8: `__main__` must accept `--no-browser --port N --data-dir D --offline`, answer `GET /api/health` with `{ok: true, version}`, and stop on SIGTERM.
- Owner: GitHub owner/name (D89 addendum); add the five secrets for a notarized release; fill `PINNED_SHA256` after the first CI run.

## Mutation self-check
One pass, 25 single breakages (builder 9, launcher 7, plist template 1, workflow 8): 24 killed at once, 1 survivor (the watchdog's SIGTERM
before its SIGKILL was removable). Closed with a test: the fake server leaves a marker on SIGTERM and the hard-kill test requires it; re-run, killed.
