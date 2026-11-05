# Releasing sutra-pro

The GitHub workflows are modelled on the old Sutra repository's (`test-native.yml`, `plugin-release-gate.yml`,
`release-dmg.yml`), see D89. **Status: written, not yet run on GitHub.** The repository is local only: nothing is pushed and
no GitHub repository exists (D89 addendum; the owner and name are confirmed before the first push). Both files pass `actionlint`
with `shellcheck`, and `tests/release/` checks their structure offline.

## Cut a release

1. Tag only a commit whose `ci` run is green. `release-wheel` builds and verifies the wheel; it does not run the test gate again.
2. Set `[project].version` in `pyproject.toml` to `X.Y.Z` (plain integers), commit it and merge it.
3. Tag that commit and push the tag:

       git tag vX.Y.Z
       git push origin vX.Y.Z

   A beta of the same target version is `vX.Y.Z-beta.1`, `vX.Y.Z-beta.2`, ... `pyproject.toml` stays at `X.Y.Z` for the betas
   and for the stable tag that promotes them. Betas are published as pre-releases.
4. Watch the `release-wheel` run. When `guard`, `build` and `verify` are green, the release page carries the assets below.

Run it again for a tag that exists (a failed leg, a bad asset): dispatch from the tag's own ref, so the tree is the tag's tree.
A re-run replaces the assets of that release.

    gh workflow run release-wheel -f tag=vX.Y.Z --ref vX.Y.Z

## What runs

| Workflow | Runs on | Jobs |
|---|---|---|
| `ci` | push to `main`, every pull request, manual (input `slow`) | `test` (ubuntu-latest and macos-15), `package` (ubuntu-latest) |
| `release-wheel` | push of a tag `v*`, manual (input `tag`) | `guard`, `build`, `verify` (ubuntu-latest and macos-15) |

**ci / test.** Python 3.11 in `.venv` (`uv venv`, then `uv pip install -e ".[dev]"`), Node 20, then
`scripts/py scripts/plan_tools.py check` and `scripts/gate.sh`: the same gate every local merge passes (pytest and the node
tests). Live, slow and browser suites never run by default; a manual run with `slow=true` adds `SUTRA_SLOW=1 scripts/py -m pytest`.
Both systems run to the end (no fail-fast), so a macOS-only break is not hidden by the ubuntu leg going red first.

**ci / package.** `uv build` (the sdist, then the wheel from that sdist), `scripts/check_wheel.py` on the wheel, an install of the
wheel into a clean environment outside the checkout, `sutra-pro --help`, and the built `dist/` kept as a workflow artifact.

**release-wheel / guard** (first, seconds, no costly runner). `scripts/check_release_tag.py` compares the tag with
`[project].version`. For a manual run it also requires that the tag already exists.

**release-wheel / build** (the only job allowed to write). `uv build`, `scripts/check_wheel.py`, then the assets are named, a
checksum is written for each by this same job, and `softprops/action-gh-release@v2` attaches them to the release of the tag.
A beta tag makes a pre-release, which `releases/latest` never returns.

**release-wheel / verify.** Downloads what was *published* (not what the build job had on disk), checks both checksums, checks that
the stable-name file is byte-for-byte the versioned wheel, installs the wheel in a fresh environment and runs `sutra-pro --help`,
on ubuntu-latest and macos-15.

## Assets

| Asset | What it is |
|---|---|
| `sutra_pro-X.Y.Z-py3-none-any.whl` | The wheel. A beta tag publishes the wheel named for its `X.Y.Z`, on the beta's own release. |
| `sutra_pro-X.Y.Z-py3-none-any.whl.sha256` | Its SHA-256, in `shasum` format. |
| `sutra_pro-py3-none-any.whl` | The same bytes under a stable name, for links such as `releases/latest/download/sutra_pro-py3-none-any.whl`. |
| `sutra_pro-py3-none-any.whl.sha256` | Its SHA-256. |

Checksums are written per asset by the job that built it, as in the old pipeline: a shared aggregate file goes stale when a re-run
replaces a wheel, and `shasum -c` then reports a corrupt download that is only bookkeeping.

## The checks

| Where | Check | Failure |
|---|---|---|
| guard | The tag is exactly `vX.Y.Z` or `vX.Y.Z-beta.N` (integers, no leading zeros; no v-less tag, no other prefix or suffix) and `X.Y.Z` equals `[project].version`. The beta suffix is ignored in the comparison. | exit 1, one `::error::` line |
| guard | A manual run's tag exists (`git ls-remote`). | `::error::` |
| `check_wheel.py` | Every glob of `[tool.setuptools.package-data]` has at least one wheel member whose source file exists in the tree. A glob with no file in the tree fails too. | one `::error::` per problem |
| `check_wheel.py` | `entry_points.txt` declares `sutra-pro = sutra_app.__main__:main` under `console_scripts`. | same |
| `check_wheel.py` | `METADATA` has `Name: sutra-pro`. | same |
| build | `dist/` holds exactly one wheel, and its name is `sutra_pro-<tag's X.Y.Z>-py3-none-any.whl`. | `::error::` |
| verify | Checksums match, the stable name is the same file, the wheel installs and `sutra-pro --help` exits 0. | job fails |

The same checks run locally: `uv build`, `scripts/py scripts/check_wheel.py dist/*.whl`, `scripts/py scripts/check_release_tag.py vX.Y.Z`.

## Install a release

Needs [uv](https://docs.astral.sh/uv/) (it fetches Python 3.11 when the machine has none). Use the versioned asset's URL:

    uv tool install https://github.com/<owner>/sutra-pro/releases/download/vX.Y.Z/sutra_pro-X.Y.Z-py3-none-any.whl
    sutra-pro --help

- Update: `uv tool install --reinstall <the newer wheel's url>`. Remove: `uv tool uninstall sutra-pro`.
- Check a download: in the folder holding both files, `shasum -a 256 -c sutra_pro-X.Y.Z-py3-none-any.whl.sha256`.
- Private repository: the URL needs a login, so fetch the file with `gh release download vX.Y.Z --repo <owner>/sutra-pro --pattern 'sutra_pro-[0-9]*.whl'`
  and install the local file with `uv tool install ./sutra_pro-X.Y.Z-py3-none-any.whl`.
- The stable-name file cannot be installed under that name: a wheel name must carry the version, and `uv` and `pip` refuse a name
  without one. It is for links and scripts that fetch "the newest" without knowing the version.

## Not built yet

- The macOS app and its DMG are work package REL-2 (`release-macos.yml`, Sutra Pro.app with a bundled Python). `docs/RELEASE-macos.md` will cover it.
- Windows only on request.
- No upload to PyPI, no signing of the wheel (the checksums are integrity, not authorship), and no sdist among the release assets
  (`ci` keeps the sdist as a workflow artifact).
- `sutra-pro --help` needs `sutra_app/__main__.py`, which package ORCH-8 writes; until it is merged, the `package` and `verify` jobs
  would fail on a tree like today's.
