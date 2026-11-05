# REL-1 as built: GitHub CI and wheel release workflows

## Built
- `.github/workflows/ci.yml` (name `ci`): push to main, pull_request, manual `slow`. `test` on ubuntu-latest and macos-15 (uv venv 3.11,
  `-e ".[dev]"`, Node 20, `plan_tools.py check`, `scripts/gate.sh`, slow suites only on a manual `slow=true`); `package` on ubuntu
  (`uv build`, `check_wheel.py`, install in a clean venv outside the checkout, `sutra-pro --help`, `dist/` uploaded).
- `.github/workflows/release-wheel.yml`: tags `v*` or manual `tag`. `guard` (first) -> `build` (the only job with `contents: write`)
  -> `verify` (ubuntu, macos-15, downloads the PUBLISHED assets). Assets: `sutra_pro-X.Y.Z-py3-none-any.whl`, the same bytes as
  `sutra_pro-py3-none-any.whl`, one `.sha256` each. `-beta.N` tags are pre-releases.
- `scripts/check_release_tag.py`: `check(tag, version) -> (ok, message)`, `read_version`, CLI (0 ok; 1 refused or pyproject unreadable; 2 usage).
- `scripts/check_wheel.py`: `check_wheel(wheel, root) -> list[str]` (every problem, not the first), CLI over several wheels.
- `tests/release/` (3 files, 354 tests, about 6 s of CPU (13 s on a loaded machine), none skipped here): tag cases, fixture wheels edited on purpose, wheels built by
  uv/setuptools (fixture and this repo, offline), workflow rules proved on bad workflows. `docs/RELEASE.md`.

## Deviations from the specification
1. `docs/design/release.md` does not exist in the repo; the caller's FULL SPEC (equal to the REL-1 `spec` in `docs/build-plan.json`) was the only source.
2. The alias `sutra_pro-py3-none-any.whl` is uploaded as specified, but uv 0.13.6 (and pip) refuse it as an install target ("wheel
   filename is invalid: Must have a platform tag": no version in the name). RELEASE.md installs from the versioned URL; `verify`
   installs the versioned wheel and `cmp`s the alias with it.
3. `actions/upload-artifact@v4` (the spec says "upload dist" but names no action). Top-level permissions are `contents: read` in both
   files; `build` alone gets `contents: write` (the spec asks only that the key exists).
4. Added: `guard` also requires a dispatched tag to exist (`git ls-remote`; the release action would otherwise create it); `build` checks
   that the wheel NAME carries the tag's X.Y.Z; `verify` checks checksums; `concurrency` per tag on the release; `timeout-minutes` on
   every job; `fail-fast: false` on both matrices; a release body with the install line.
5. Tests go beyond the list: rules applied to EVERY file in the folder (REL-2's workflow too): actions pinned, permissions, no secret
   echo, attacker-chosen text (tag, input, branch) only through `env:`, an upload job can write, no pull_request_target/schedule/workflow_run,
   SUTRA_LIVE and SUTRA_BROWSER never set, SUTRA_SLOW only under `inputs.slow`. `pyyaml` was already in the dev extra: no pyproject change.

## Decisions
- Every Python call in a workflow goes through `scripts/py` after `uv venv .venv --python 3.11` (the guard too): one entry, same as local.
- Tags: exactly `vX.Y.Z` or `vX.Y.Z-beta.N`, integers without leading zeros, ASCII digits, `fullmatch` (a `$` would pass a trailing newline).
  A beta publishes the wheel named for its X.Y.Z (the old repo's one-target-version-many-betas rule), each on its own release.
- `check_wheel` expands the globs over the TREE with `glob.glob(recursive=True)` (what setuptools does) and asks the wheel for those
  files; a glob with no file in the tree is an error (it cannot ship anything). Hidden files do not count, as in setuptools.
- Exactly three checks as specified; no version or filename check in `check_wheel` (`build` does the name check against the tag).
- The annotation text is escaped (`%`, CR, LF) so a hostile dispatch input cannot start a second workflow command.
- Real-build tests run `uv build` with `UV_OFFLINE=1` on a COPY of pyproject.toml and sutra_app (the tree is never written); they skip with a
  printed reason when uv is missing or cannot build offline, and fail on any other build error.

## Known limits
- Never run on GitHub. `actionlint` 1.7.12 with `shellcheck` 0.11.0 (fetched into /tmp, not part of the gate) reports 0 errors on both files.
- On TODAY's tree `check_wheel.py` fails on a real build: 8 of the 9 package-data globs (`ui/pages/*`, `engine/*`, `orchestrator/agent/templates/*.md`,
  `connectors/policy.default.json`) match no file yet. That is the specified check working. The real-wheel test asserts the report is exactly
  the empty globs and nothing else, and demands a clean wheel once they all have files. A glob that stays empty must be removed from pyproject.
- The secret-echo and untrusted-text rules are heuristics over parsed YAML. Actions are pinned by major tag as specified, not by SHA.
- Runner labels rot (see the old release-dmg.yml): `macos-15` is current as of the old file's note.

## Follow-ups and needs
- ORCH-8: `sutra_app/__main__.py` with `main()` that answers `--help` offline with exit 0 (`package` and `verify` run `sutra-pro --help`).
- E1, ORCH, CN: the data under the 8 empty globs. Owner: confirm the GitHub owner/name before the first push (D89 addendum).
- REL-2: `release-macos.yml` is held to the shared workflow rules above; `docs/RELEASE.md` points to `docs/RELEASE-macos.md`.

## Mutation self-check
A scratch harness in /tmp (not committed) copied the package to six folders and applied ONE breakage at a time: 149 mutants over the two
scripts (comparisons flipped, regex widened, validations and error branches dropped, exit codes, escapes, constants, defaults), both
workflows (branch pins, permissions, triggers, job order and `needs`, secrets, untrusted text, matrices, asset names, checksums, prerelease
marker), the YAML rule functions (weakened) and docs/RELEASE.md. All 149 are killed. The first round left 7 alive: 2 were mis-aimed (the
text hit a comment or docstring), 5 were real gaps and now have tests (`nullglob` and `-eq 1` in the staging script, the sort order of the
example file, an unchecked permissions assertion, a pipe counted as safe). Later additions: unicode-digit and `--version ""` cases.
