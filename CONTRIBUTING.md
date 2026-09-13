# Contributing to Sutra — the desktop development flow

One product ships from this repo: the **published GitHub release** of the Sutra
desktop app. There is no local "dev build" you install to your Dock. To try a
change, you cut a **beta**; to ship it, you **promote** the beta to stable. Both
are built by CI from a tag — never on a workstation.

This flow is the same for everyone. It exists because the desktop must only ever
run code that is on GitHub, and because past releases broke when version files
and tags drifted apart.

## The five steps

```
   feature branch ──1── beta prerelease ──2── verify in "Sutra Beta"
                                                      │
                                              3  looks good?
                                                      │
   main ◀── PR merge ──── promote ──4/5── stable release ── apps self-update
```

**1. Cut a beta from your branch.**

```bash
cd marketplace/plugin/sutra-ui
./scripts/sutra-release.sh beta
```

This pushes your branch and tags `vX.Y.Z-beta.N-desktop`. CI builds a **separate
app, "Sutra Beta"** — its own bundle id (`os.sutra.ui.beta`), its own port
(`8331`), and its own data namespace (`~/.sutra-native-beta`, `~/.sutra-ui-beta`).
It is published as a **prerelease**, so GitHub's `releases/latest` never returns
it: the production auto-updater and the website download link ignore it. Nobody
gets it unless they install it on purpose.

**2. Verify in the beta app.** Download `Sutra-<arch>.dmg` from the beta
prerelease and install it. **Sutra Beta runs alongside your production Sutra** —
both open at once, on different ports, with separate registries and chats — so
you test the flow without touching your real data. Never build or install a
local bundle to test; cut a beta.

**3. If it looks good, open a PR** and get it merged to `main`.

**4. Promote to stable** (from `main`, at the merged commit):

```bash
cd marketplace/plugin/sutra-ui
./scripts/sutra-release.sh promote X.Y.Z
```

This bumps the three version files together, commits, and tags
`vX.Y.Z-desktop`. CI publishes it as the **latest** release.

**5. Every production app applies it on its next restart** — the app auto-updates
from `releases/latest` and the plugin updates itself daily. Your local `main` is
already on the merged commit. You do not manually install stable; if you were on
beta, install the stable DMG once to leave the beta channel.

## Rules the pipeline enforces

- **Releases are CI-only.** `.github/workflows/release-dmg.yml` builds, signs and
  notarizes both architectures on a `v*` tag. Never hand-build, notarize, or
  upload a DMG.
- **The tag must match the manifests.** The CI `guard` job fails if the tag's
  version disagrees with `marketplace/plugin/.claude-plugin/plugin.json` or the
  `core` entry of `.claude-plugin/marketplace.json`. `sutra-release.sh promote`
  bumps both for you; a beta tag is validated against the same base version, so
  `beta.1`, `beta.2` … of one target need no re-bump.
- **Beta = prerelease.** A `-beta.N` tag is published as a prerelease and builds
  the coexisting "Sutra Beta"; anything else is stable.
- **Supported Python is 3.11–3.12** (cryptography needs 3.11+; numpy 2.0.2 has no
  3.13 wheel). The DMG bundles its own. If a venv mismatch ever blocks you, fix
  the version in the repo (`requirements.txt`, `electron/bundle-runtime.sh`) and
  release — never shim a local interpreter.

## Verifying code without a release

You do not need any install to run the suites or exercise the panel:

```bash
cd marketplace/plugin/sutra-ui
.venv/bin/python -m pytest                       # Python suites (3.11 venv)
node test_nav.js && node test_panel.js           # JS suites
.venv/bin/python -m uvicorn app:app --port 8399  # run the panel on a spare port
```

Running the server is not installing an app bundle. Building or installing a
desktop bundle to verify is the one thing this flow forbids.
