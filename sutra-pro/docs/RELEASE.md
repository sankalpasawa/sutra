# Releasing sutra-pro

sutra-pro lives in the `sutra-pro/` folder of the Sutra repository (D98); its workflows are the four `.github/workflows/sutra-pro-*.yml` files,
modelled on the old product's (`test-native.yml`, `plugin-release-gate.yml`, `release-dmg.yml`, `release-windows.yml`, D89). The old product has
workflows of its own in the same folder; none of them starts on a change to this folder or on a tag of this product, and none of this
product's starts on a change to the old one (`tests/release/` checks both directions against the old files).

One tag releases everything: the wheel, the two Mac DMGs, the Windows installer and zip land on one GitHub Release. The Mac and Windows downloads are
the **desktop app** (D120): an Electron window (`desktop/`) around the local server, which runs on a Python that ships inside the app. Releases up to
0.1.x were a launcher that opened the browser; the app ids, names and asset names are the same, so a new download replaces the old app in place.

| Part | Workflow | Doc |
|---|---|---|
| the wheel | `sutra-pro-release-wheel` | this file |
| the Mac desktop app and its DMGs (work package REL-2, D120) | `sutra-pro-release-macos` | `docs/RELEASE-macos.md` |
| the Windows desktop app: installer and zip | `sutra-pro-release-windows` | `docs/RELEASE-windows.md` |

## The tag, and why it is not `v*` (D100)

The tag is `sutra-pro-vX.Y.Z` (or `sutra-pro-vX.Y.Z-beta.N`). The old product triggers its release workflows on `v*` and its website and its
installed apps read `/releases/latest`. So a tag of this product never starts with a `v`, and **a release of this product is never marked
"Latest"**: every upload step sets `make_latest: "false"`, and `tests/release/` fails when one does not. The cost is that download links carry the tag:

    https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/<asset>

## Cut a release

1. Tag only a commit whose `sutra-pro-ci` run is green. The release workflows build and verify the artifacts; they do not run the test gate again.
2. Set the version to `X.Y.Z` (plain integers) in `pyproject.toml`, `sutra_app/__init__.py` and `desktop/package.json` (`npm version X.Y.Z --no-git-tag-version` in
   `desktop/` also updates the lock file); `tests/release/` fails when the three differ. Commit it and merge it.
3. Tag that commit and push the tag:

       git tag sutra-pro-vX.Y.Z
       git push origin sutra-pro-vX.Y.Z

   A beta of the same target version is `sutra-pro-vX.Y.Z-beta.1`, `sutra-pro-vX.Y.Z-beta.2`, ... `pyproject.toml` stays at `X.Y.Z` for the betas
   and for the stable tag that promotes them. Betas are published as pre-releases.
4. Watch the three runs. When every job is green the release page carries all the assets.

Run one again for a tag that exists (a failed leg, a bad asset): dispatch from the tag's own ref, so the tree is the tag's tree. A re-run
replaces the assets of that release.

    gh workflow run sutra-pro-release-wheel -f tag=sutra-pro-vX.Y.Z --ref sutra-pro-vX.Y.Z

(`sutra-pro-release-macos` and `sutra-pro-release-windows` take the same two arguments.) A workflow can only be dispatched once it is on the
default branch; a tag push runs the workflow files of the tagged commit.

## What runs

| Workflow | Runs on | Jobs |
|---|---|---|
| `sutra-pro-ci` | a push to any branch or a pull request that changes `sutra-pro/**` (or the workflow), manual (input `slow`) | `test` and `desktop` (ubuntu-latest, macos-15 and windows-latest), `package` (ubuntu-latest) |
| `sutra-pro-release-wheel` | push of a tag `sutra-pro-v*`, manual (input `tag`) | `guard`, `build`, `verify` (ubuntu-latest, macos-15 and windows-latest) |
| `sutra-pro-release-macos` | the same tag, manual | `guard`, `dmg` (arm64 and x86_64), `verify` |
| `sutra-pro-release-windows` | the same tag, manual | `guard`, `exe`, `verify` |

**sutra-pro-ci / test.** Python 3.11 in `.venv` (`uv venv`, then `uv pip install -e ".[dev]"`), Node 20, then
`scripts/py scripts/plan_tools.py check` and `scripts/gate.sh`: pytest and the node tests, the same gate on three systems. Live, slow and browser suites
never run by default; a manual run with `slow=true` adds `SUTRA_SLOW=1 scripts/py -m pytest`. All systems run to the end (no fail-fast), so a
macOS-only or Windows-only break is not hidden by the ubuntu leg going red first. On Windows the tests that need POSIX process semantics are
skipped by name with the reason (`tests/conftest.py`).

**sutra-pro-ci / desktop.** Node 22 (the packager needs 22.12 or newer), `npm ci --ignore-scripts` in `desktop/` (Electron's own 100 MB download is skipped: nothing
here starts it), then `npm test`: the supervisor against a fake server (attach, start, crash, slow start, the stop ladder), the navigation guard, the
pages, the menu, the log, the self-test's verdict and the packager's options. The same tests run on three systems; those that need POSIX signals say so
and skip on Windows. That the packaged app really runs is proved by the release workflows (D124).

**sutra-pro-ci / package.** `uv build` (the sdist, then the wheel from that sdist), `scripts/check_wheel.py` on the wheel, an install of the
wheel into a clean environment outside the checkout, `sutra-pro --help`, and the built `dist/` kept as a workflow artifact.

**sutra-pro-release-wheel / guard** (first, seconds, no costly runner). `scripts/check_release_tag.py` compares the tag with
`[project].version` and writes the release name and the pre-release flag the other jobs use. For a manual run it also requires that the tag already exists.

**sutra-pro-release-wheel / build** (the only job allowed to write). `uv build`, `scripts/check_wheel.py`, then the assets are named, a
checksum is written for each by this same job, and `softprops/action-gh-release@v2` attaches them to the release of the tag, which owns the
release text. A beta tag makes a pre-release.

**sutra-pro-release-wheel / verify.** Downloads what was *published* (not what the build job had on disk), checks both checksums, checks that
the stable-name file is byte-for-byte the versioned wheel, installs the wheel in a fresh environment and runs `sutra-pro --help`,
on ubuntu-latest, macos-15 and windows-latest.

**sutra-pro-release-macos / guard.** The same tag check. **sutra-pro-release-macos / dmg.** Two legs, one per architecture, each built natively: the Electron app is
built with the Python inside it, signed (ad hoc, or Developer ID and notarized when all five secrets exist; `scripts/sign_desktop_app.sh` audits every Mach-O
file before the round trip to Apple), proved by running the signed app with the network cut (`scripts/prove_desktop_app.py`: the window starts its server,
draws the page and stops it; a team runs its first turn), put into a DMG, and attached with its checksum; the proof's picture and logs are kept as an
artifact. **sutra-pro-release-macos / verify.** Both architectures are on the release and the published bytes match their checksums. Details in
`docs/RELEASE-macos.md`.

**sutra-pro-release-windows / guard.** The same tag check. **sutra-pro-release-windows / exe.** Builds the app folder (the Electron app with the Python in
`resources\python`), proves it runs, compiles the installer, proves the installer installs, runs and uninstalls, zips the folder, attaches the four files.
**sutra-pro-release-windows / verify.** Installs the *published* installer and proves the installed copy, and proves the published zip. Details in
`docs/RELEASE-windows.md`.

## Assets

| Asset | What it is |
|---|---|
| `sutra_pro-X.Y.Z-py3-none-any.whl` | The wheel. A beta tag publishes the wheel named for its `X.Y.Z`, on the beta's own release. |
| `sutra_pro-X.Y.Z-py3-none-any.whl.sha256` | Its SHA-256, in `shasum` format. |
| `sutra_pro-py3-none-any.whl` | The same bytes under a stable, version-free name, for scripts that know only the tag. |
| `sutra_pro-py3-none-any.whl.sha256` | Its SHA-256. |
| `Sutra-Pro-arm64.dmg`, `Sutra-Pro-x86_64.dmg` and their `.sha256` | The Mac app (`docs/RELEASE-macos.md`). |
| `Sutra-Pro-Setup-x64.exe`, `Sutra-Pro-win-x64.zip` and their `.sha256` | The Windows app (`docs/RELEASE-windows.md`). |

Checksums are written per asset by the job that built it, as in the old pipeline: a shared aggregate file goes stale when a re-run
replaces an asset, and `shasum -c` then reports a corrupt download that is only bookkeeping.

## The checks

| Where | Check | Failure |
|---|---|---|
| guard | The tag is exactly `sutra-pro-vX.Y.Z` or `sutra-pro-vX.Y.Z-beta.N` (integers, no leading zeros; no `v` tag, no other prefix or suffix) and `X.Y.Z` equals `[project].version`. The beta suffix is ignored in the comparison. | exit 1, one `::error::` line |
| guard | A manual run's tag exists (`git ls-remote`). | `::error::` |
| `check_wheel.py` | Every glob of `[tool.setuptools.package-data]` has at least one wheel member whose source file exists in the tree. A glob with no file in the tree fails too. | one `::error::` per problem |
| `check_wheel.py` | `entry_points.txt` declares `sutra-pro = sutra_app.__main__:main` under `console_scripts`. | same |
| `check_wheel.py` | `METADATA` has `Name: sutra-pro`. | same |
| build | `dist/` holds exactly one wheel, and its name is `sutra_pro-<tag's X.Y.Z>-py3-none-any.whl`. | `::error::` |
| every upload | `make_latest: "false"`, the release name from the guard, `fail_on_unmatched_files`. | `tests/release/` |
| verify | Checksums match, the stable name is the same file, the wheel installs and `sutra-pro --help` exits 0. | job fails |

The same checks run locally: `uv build`, `scripts/py scripts/check_wheel.py dist/*.whl`, `scripts/py scripts/check_release_tag.py sutra-pro-vX.Y.Z`.

## Install a release

Needs [uv](https://docs.astral.sh/uv/) (it fetches Python 3.11 when the machine has none). Use the versioned asset's URL:

    uv tool install https://github.com/sankalpasawa/sutra/releases/download/sutra-pro-vX.Y.Z/sutra_pro-X.Y.Z-py3-none-any.whl
    sutra-pro --help

- Update: `uv tool install --reinstall <the newer wheel's url>`. Remove: `uv tool uninstall sutra-pro`.
- Check a download: in the folder holding both files, `shasum -a 256 -c sutra_pro-X.Y.Z-py3-none-any.whl.sha256`.
- The stable-name file cannot be installed under that name: a wheel name must carry the version, and `uv` and `pip` refuse a name
  without one. It is for scripts that fetch a file knowing only the tag.
- The apps are the easier way for a person: the DMG on a Mac, the installer on Windows.

## Not built

- No upload to PyPI, no signing of the wheel (the checksums are integrity, not authorship), and no sdist among the release assets
  (`sutra-pro-ci` keeps the sdist as a workflow artifact).
- No signing of the Windows files until a certificate exists (D102); the Mac app is ad hoc signed, or Developer ID signed and notarized when all five
  secrets exist. No auto-update on either (the release is never "Latest", D100, which is what an updater would read; D120 lists the options).
