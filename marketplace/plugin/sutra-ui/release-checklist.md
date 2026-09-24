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

### 0. Beta first (founder D80, 2026-09-21)

Every version is released twice: `scripts/release-desktop.sh release --beta` cuts `vX.Y.Z-beta.N-desktop`
(the pipeline builds the coexisting "Sutra Beta" app as a prerelease); the founder installs it and looks at
the features; then `scripts/release-desktop.sh release` cuts `vX.Y.Z-desktop`. The script refuses the stable
tag when no beta of that version exists. Founder skip, audited to `.enforcement/release-beta-skips.jsonl`:
`RELEASE_SKIP_BETA=1 RELEASE_SKIP_BETA_REASON='<why>'`.

Pass condition: `scripts/release-desktop.sh check` prints `PASS  beta: vX.Y.Z-beta.N-desktop went before vX.Y.Z-desktop (D80)`.

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

Wired 2026-09-16. The step ran three suites — `test_panel.js`, `test_nav.js`,
`test_charter_filter.js` — and every `test_shadow_*.js` was invisible to the DMG build, so a
regression in Shadow home, the overlay or the settings screen shipped without failing a single leg.
All of them now run in that step, listed one per line.

Pass condition — these two print the SAME number, and it is `33` today (was `11` when this check
was written, `30` before the Shadow conversation work of 2026-09-21 added `test_shadow_hi_trace.js`,
and `31` before `test_shadow_done_history.js` and `test_shadow_order.js` on 2026-09-23;
the number in this sentence is documentation, the equality of the two commands is the check):

```bash
grep -c 'node test_shadow_.*\.js' .github/workflows/release-dmg.yml
ls marketplace/plugin/sutra-ui/test_shadow_*.js | wc -l
```

Two numbers, not one, because a single hardcoded count is what went stale here (see the correction
below). The wiring is an explicit list rather than a glob precisely so the first command can count
it; the cost is that a NEW suite must be added to the workflow by hand, and the second command is
what catches you forgetting.

Keep the counted pattern out of the workflow's own comments. A comment containing it inflates the
first number, and the check then lies in the safe-looking direction.

Then prove the wiring bites: break one assertion in `test_shadow_home.js` on a scratch branch, cut a
`-beta.N` tag, and confirm the `dmg` leg fails at the Panel step before any DMG is built. Revert.

Corrected 2026-09-16: this check said `11`, and the tree carried 12. The count was stale twice over.
It was written against `e2ffd5b5`, where only **10** `test_shadow_*.js` were tracked — the eleventh
was `test_shadow_check_progress.js`, untracked on disk, which check 1 flagged and which has since
been **deleted** rather than committed. Two real suites landed after: `test_shadow_rhs.js`
(2026-09-15) and `test_shadow_presence.js` (2026-09-16). Counting files on disk instead of files in
the tree is what let a deleted file hold a slot in the total.

Wiring this check red-flagged two suites that had been failing unnoticed. Both are resolved as of
2026-09-16 and all 11 are green:

* `test_shadow_overlay.js` — STALE, corrected. It pinned the literal re-read ladder
  `[250, 750, 2000, 5000]`; `SH_START_BACKOFF` (`static/js/15-shadow-overlay.js`) is now geometric
  out to 90s, because the old tail gave up before the slowest measured start finished provisioning.
  The watcher's stop condition also gained `target_chat` alongside the state. Both changes are
  deliberate and commented in the product. The suite now asserts the ladder's SHAPE — starts at
  250ms (ahead of the ~394ms chat publish), only climbs, reaches the slow tail — rather than a list
  of literals that would go stale on the next re-tune. No product code changed.

* `test_shadow_briefing.js` — RETIRED. It tested "the Briefing", the one-vertical-spine Shadow Home
  of V5 slice 11. That screen was replaced on purpose on 2026-09-11 by `43aba037` ("Shadow Home
  reads like a supervisor's desk, not a list of bands") and `d47b2067`; `shadowHomeHtml()` returns
  the two-column `shwork` workspace and emits no `shbrief`, `shcalm`, `shdeck`, `shasg` or `shmast`
  anywhere. 122 assertions across 33 sections, 24 of them calling `shadowHomeHtml()` directly, all
  describing a container that ships nowhere. The suite was red from the day the screen was replaced
  and nobody retired it with the screen; the checklist inherited it as a known failure instead. The
  replacement screen is covered by `test_shadow_home.js`, which is green. Recover the file from
  `git show 989e1123:marketplace/plugin/sutra-ui/test_shadow_briefing.js` if it is ever wanted.

The Panel step runs under `bash -e`, so any one of the 11 going red aborts it before a DMG is built.
That is the gate doing its job.

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

Then verify the artifact on a Mac, not from CI output alone. Since D82 (2026-09-21) this table is
run by `scripts/beta-smoke.sh <beta-tag>` inside `scripts/release-desktop.sh release --auto`, on the
Mac that releases, with no human step; the rows stay here as the contract the script implements:

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

Checks 5–6 assert the code is right; this asserts the built app answers right. Since D82
(2026-09-21) the walk is `scripts/beta-smoke.sh`: it launches the installed beta on its own port,
waits for the backend's health answer, mints the panel token and reads `/`, state, sessions and the
Shadow surfaces (status, settings, missions, feed); every route must answer 200 before the stable
tag is cut. The rows below are what the suites in check 5 pin; nobody walks them by hand:

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
