# Sutra Pro: how any AI agent changes, tries, pushes and releases it

Read this before you change anything under `sutra-pro/`. It binds every AI tool that works in this repository (Claude Code, Codex, Gemini, Copilot, Cursor,
the next one) and every person. `CLAUDE.md` and the pointer files at the repository root send you here. Commands run from `sutra-pro/`.

## The loop: change, test, try the beta, push, release only when asked

| # | Step | How |
|---|---|---|
| 1 | Work on a branch cut from the newest `origin/main` | `git fetch origin && git switch -c <topic> origin/main` |
| 2 | Test: targeted `pytest` while you work; before you push, the whole gate **in the foreground** (about 15 minutes) | `scripts/gate.sh` |
| 3 | **Try it: install the beta** whenever the change shows in the app (page, server behaviour, desktop window): the owner opens it beside the released app | `scripts/py scripts/install_app.py beta` |
| 4 | Push: commit, push the branch, wait for `sutra-pro-ci` to go green, then land it on `main` (a fast-forward; `main` is not protected) | `git push origin <topic>`, then `git push origin <topic>:main` |
| 5 | **Release only when the owner says release, ship or publish.** It publishes on GitHub, then installs the published release on this Mac | `scripts/py scripts/release.py` |

"Push to GitHub" is part of the job: do not stop at a local commit. The owner's standing instruction is to make the change and push it. Pull first: other people
and agents land changes on `main` all day, so `git fetch origin` and merge `origin/main` into your branch before step 2 and again before step 4 when it moved.

## Two apps on one Mac

| | Sutra Pro (stable) | Sutra Pro Beta |
|---|---|---|
| comes from | a GitHub release: `scripts/release.py`, or `scripts/py scripts/install_app.py release [TAG]` | the working tree of this checkout, built on this Mac, **never published** |
| app | `/Applications/Sutra Pro.app` (`os.sutra.pro`) | `/Applications/Sutra Pro Beta.app` (`os.sutra.pro.beta`), the icon has an orange BETA band |
| data | `~/.sutra-pro` | `~/.sutra-pro-beta` (its own, empty at first; the owner may delete it to start over) |
| updates itself | yes, from signed releases | never |

They differ in name, id, data folder and Chromium state, so both are installed and both can run at the same time (each starts its own server on the first free
port from 8780). `scripts/py scripts/install_app.py status` says what is installed, what runs, on which port. Edit `desktop/src/channels.json`, never a name in
two places (D242). Everything about the choice is in [docs/RELEASE.md](docs/RELEASE.md), "One Mac, two apps".

## After you install the beta, tell the owner

The version and the commit it was built from (`Sutra Pro Beta 0.6.1 beta 1a2b3c4`), that it is open beside Sutra Pro and keeps its data in `~/.sutra-pro-beta`, and
what to try. The build takes a few minutes the first time (Electron, the Python inside the app) and then less. The beta exists on a Mac and on a Windows x64 PC
(D432: there it is the folder `%LOCALAPPDATA%\Programs\Sutra Pro Beta`, or `--install-dir`, with a Start-menu entry). On any other machine (CI, a cloud
session, Linux) say that you could not install one, and why. Do not hunt for a way around it. On Windows the owner keeps a checkout of its own that follows
`origin/main` and updates the beta with `scripts/py scripts/install_app.py beta --pull`.

## Rules that do not bend

- **The stable app is the owner's.** Only a published release goes into `/Applications/Sutra Pro.app`, only through `release.py` or `install_app.py release`. Never copy a
  beta or a working-tree build over it, never edit the installed app, never touch `~/.sutra-pro` (no delete, no reset, no "migration" by hand, no copy into the beta
  unless the owner asks, and then only with the stable app closed).
- **Never quit a working app.** The install scripts refuse (exit status 3) while the app has an engine run or a reply in progress and name what runs. Wait, or ask. `--force`
  is the owner's word, not yours. Nothing is ever killed with SIGKILL.
- **A release needs the owner's word and a green CI.** `release.py` stops unless `sutra-pro-ci` is green on exactly the commit it tags, writes
  `docs/release-notes/X.Y.Z.md` first (a few plain lines about what is new, starting `### What is new in X.Y.Z`: write it before you run the script), never marks the
  release "Latest" (that belongs to the older product, D100), never moves or deletes a tag, and stops when the version is already tagged: somebody released it, so
  install it (`install_app.py release TAG`) instead. When a release leg fails, repair it as [docs/RELEASE.md](docs/RELEASE.md) says; do not tag again. A change to a
  `sutra-pro-*` workflow needs a `-beta.N` tag first (RELEASE.md).
- **GitHub login.** If `git push` or `gh` is refused while `GITHUB_TOKEN` or `GH_TOKEN` is set, that token is not the owner's login: run the command with `env -u GITHUB_TOKEN
  -u GH_TOKEN`. The scripts already do. A pull request cannot be opened with such a token either.
- **Names and paths.** Never write the owner's name, a login or an absolute path into a home folder into any file of `sutra-pro/` (write `~`). `scripts/ownership-audit.sh` at the
  repository root, and `tests/test_ownership.py`, fail on it.
- **Stay in `sutra-pro/`.** Everything else (the older product, the J2 departments, their workflows) is other work: do not edit it for Sutra Pro, and never touch a workflow that
  is not named `sutra-pro-*`.
- **Decisions are recorded.** A decision gets `## D<number> — title` in [docs/DECISIONS.md](docs/DECISIONS.md) (sources, decided, why, rejected, diagram label) and an
  entry in `docs/diagram/decisions.json`; `tests/test_diagram_decisions.py` fails without both. Take the next free number after fetching: others add them too.
- **Tests.** `scripts/gate.sh` runs every Python and desktop test; run it in the foreground (the SIGINT test fails when pytest is a shell background job; a harness's own
  background mode is fine). Do not run `scripts/live_smoke.py`: it spends the owner's model quota. Say what you did not verify.

## Where things are

| Need | Look |
|---|---|
| the release steps and what each workflow does | [docs/RELEASE.md](docs/RELEASE.md), [docs/RELEASE-macos.md](docs/RELEASE-macos.md), [docs/RELEASE-windows.md](docs/RELEASE-windows.md) |
| the desktop app, how it is packaged and tested | [desktop/README.md](desktop/README.md) |
| the design and every decision | [docs/DESIGN.md](docs/DESIGN.md), [docs/DECISIONS.md](docs/DECISIONS.md) |
| running and troubleshooting the app | [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md), [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
