# Release Checklist — Sutra Desktop

**status**: active · **updated**: 2026-09-15 · **applies to**: the next tag after `v2.274.1-desktop`
**pipeline**: `.github/workflows/release-dmg.yml` (jobs: `guard` → `dmg` → `verify`)

**Prioritized risk: release safety.** Checks 1–4 carry that risk and come first; they are blocking.
Checks 5–7 cover correctness and user experience and follow. Every check below has a command to run
or a stated pass condition — none is a judgement call.

Why release safety and not correctness: v2.274.0 shipped Apple Silicon only. The Intel `dmg` leg lost
a wall-clock race at the Panel step, before the DMG was built, and `verify` refused the
one-architecture release. The code was correct; the artifact was not.

---

## Release safety — blocking

### 1. Clean working tree, and a tag the `guard` job will accept

The pipeline builds the tag, not your working tree. Anything uncommitted is absent from the DMG.

Pass condition — this prints nothing:

```bash
cd "$(git rev-parse --show-toplevel)/marketplace/plugin/sutra-ui" && git status --short
```

As of 2026-09-15 it prints 5 modified and 14 untracked paths, including the 254-line rewrite of
`static/js/16-shadow-home.js`, its companion suites (`test_shadow_home.js`, `test_goal_live.js`,
`test_shadow_completion_ui.js`), the new `test_shadow_check_progress.js`, `qa/shadow-signs/`,
`qa-shell/g16-progress-check.mjs`, and this checklist. Commit or revert each before tagging.

Tag form must be `vX.Y.Z[-beta.N]-desktop`; `guard` rejects anything else. A `-beta.N` tag validates
against the same base `X.Y.Z`, so a branch may cut `beta.1`, `beta.2` … against one target version.

### 2. The Shadow suites must be wired into the "Panel tests" step

Today that step runs three suites — `test_panel.js`, `test_nav.js`, `test_charter_filter.js` — out
of 32 in `sutra-ui/`. All 11 `test_shadow_*.js` suites are invisible to the DMG build, so a
regression in the rewritten Shadow home ships without failing a single leg.

Add them to the `run:` block of the "Panel tests" step in `.github/workflows/release-dmg.yml`.

Pass condition — this prints `11`:

```bash
grep -c 'node test_shadow_.*\.js' .github/workflows/release-dmg.yml
```

Then prove the wiring bites: break one assertion in `test_shadow_home.js` on a scratch branch, cut a
`-beta.N` tag, and confirm the `dmg` leg fails at the Panel step before any DMG is built. Revert.

### 3. Both DMGs must be present, stapled, and launch

`verify` runs on `ubuntu-latest` after both `dmg` legs and must end green. It requires four assets:

```text
Sutra-arm64.dmg     Sutra-arm64.dmg.sha256
Sutra-x86_64.dmg    Sutra-x86_64.dmg.sha256
```

A one-architecture release is not shippable. Confirm `fail-fast: false` is still on the `dmg` matrix
before tagging — without it an Intel failure deletes the arm64 build instead of preserving it. If a
leg is missing, check whether it failed or was never assigned a runner; a retired runner label queues
forever rather than failing.

Then verify the artifact by hand, not from CI output alone:

| Step | Pass condition |
|---|---|
| `gh release view <TAG> --json assets --jq '.assets[].name'` | all four names above |
| `shasum -a 256 -c Sutra-arm64.dmg.sha256` (and x86_64) | `OK` |
| `xcrun stapler validate Sutra-arm64.dmg` | `The validate action worked!` |
| Mount, drag to Applications, launch | opens; no "Apple could not verify" dialog |

`make-dmg.sh` degrades to ad-hoc signing when `APPLE_CERT_P12` is absent, so confirm that secret is
set — the "A signed build must actually be notarized" and "Refuse to downgrade a notarized release"
guards only bite when `HAVE_SIGNING_CERT` is `true`. A cold start on a fresh install can take ~85s
before the bundled backend answers; a refused connection inside that window is not a failed launch.

### 4. Bump the version in all four places

`guard` compares the tag's base version against two manifests and refuses the release on any
mismatch. Both read `2.274.1` today, and `v2.274.1-desktop` is already cut — a new tag without a bump
fails before anything builds. The two docs are not machine-checked and are the ones that get missed.

| Surface | File | Checked by |
|---|---|---|
| `.version` | `marketplace/plugin/.claude-plugin/plugin.json` | `guard` job |
| core plugin version | `.claude-plugin/marketplace.json` | `guard` job |
| Release entry | `marketplace/plugin/CHANGELOG.md` | this checklist |
| Current version header | `CURRENT-VERSION.md` | this checklist |

Pass condition — all three lines below print the same new `X.Y.Z`:

```bash
jq -r .version marketplace/plugin/.claude-plugin/plugin.json
jq -r '.plugins[]|select(.name=="core")|.version' .claude-plugin/marketplace.json
grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' CURRENT-VERSION.md
```

`marketplace/plugin/CHANGELOG.md` must carry an entry for that version describing what changed.

Corrected 2026-09-15: this row named `RELEASES.md`, which has never carried per-version
entries -- it documents the release MODEL (how clients fetch a version), and `grep -cE "^## v?2\."`
over it returns 0. The version log is `marketplace/plugin/CHANGELOG.md`, where 2.274.0 and
2.274.1 both live. Following the old row would have meant writing an entry nobody reads.

---

## Correctness

### 5. All 32 `sutra-ui` suites green

Four fail as of 2026-09-15:

| Suite | Failing assertion |
|---|---|
| `test_goal_control.js` | the same copy on Home |
| `test_shadow_briefing.js` | the calm greeting |
| `test_shadow_check_progress.js` | no count on an untouched task |
| `test_shadow_overlay.js` | retry re-reads too |

Pass condition — this prints nothing:

```bash
cd marketplace/plugin/sutra-ui
for t in test_*.js; do node "$t" >/dev/null 2>&1 || echo "FAIL $t"; done
```

`test_shadow_check_progress.js` is untracked; check 1 forces the decision to commit or delete it. An
untracked failing test is invisible to CI and to the loop above.

### 6. No assertion may read the clock it is testing against

This flake class cost v2.274.0 its Intel build. `W3-3c` (`test_panel.js:5440`) captures `now` while
`usageResetText` reads `Date.now()` a moment later: same millisecond passes, one millisecond later
renders "in 4 hr 60 min". v2.274.1 fixed that string, not the pattern.

Pass a frozen timestamp into the function under test at each live clock call site in the Panel suites
— `test_panel.js` lines 5287, 5410, 5429, 5441 among them:

```bash
grep -n 'Date.now()\|new Date()' test_panel.js test_nav.js test_charter_filter.js
```

Pass condition: five consecutive green runs of `node test_panel.js`. Four green and one red means the
assertion is still racing, and the Intel runner will find it.

---

## User experience

### 7. Walk the rewritten Shadow home in the installed app

Checks 5–6 assert the code is right; this asserts the founder sees something right. On the DMG
installed in check 3, open Shadow home and confirm each row:

| Surface | Pass condition |
|---|---|
| Task card | Turn budget draws as a length; "last updated" key does not wrap in the left column |
| Delete | One click deletes — no confirmation dialog, one POST |
| Polling | Navigating away stops the poll; a slow read does not stack overlapping polls |
| Completion pane | Says what was done, above why it counts |
| Usage card | Reset line never reads "in 4 hr 60 min" — check across an hour boundary |

---

## Sign-off

The release ships when checks 1–4 pass and are recorded, checks 5–7 pass, and the tag's `verify` job
is green.

---

provenance: written 2026-09-15 from direct inspection of `main` @ `e2ffd5b5` (v2.274.1) —
`.github/workflows/release-dmg.yml`, the two version manifests, and a full run of all 32
`sutra-ui/test_*.js` suites (28 pass, 4 fail). The founder chose release safety as the prioritized
risk for this release, which is why checks 1–4 lead and block.
