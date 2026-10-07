# Desktop install and update design: full images, delta packs, and the pipeline that proves them

**Status**: Draft for founder review · **updated**: 2026-09-25 · author: Claude Fable 5.1 with Sankalp Asawa
**Scope**: first-install downloads from the website, in-app updates on macOS (the new delta lane), the Windows plan, the update feed with rollout and kill switch (phase 2), the threat model, failure modes, testing, CI, and a phased plan.
**Branch**: `desktop-delta-updates` (worktree `/Users/asawa/Claude/sutra-release-delta-wt`). Nothing here is on `main`.
**Related**: `updates.py`, `updates_delta.py`, `test_update_delta.py`, `test_update_e2e.py`, `.github/workflows/release-dmg.yml`, `website/index.html`, `release-checklist.md`.

## 1. The problem, measured

Every desktop release re-signs every Mach-O in the bundle with a fresh timestamped signature, so consecutive releases differ in about 1,300 of 25,700 files even when only a couple of dozen source files changed. The updater only knew how to download the whole notarized DMG.

| Measurement (2.300.0 -> 2.302.0, arm64) | Value |
|---|---|
| Files in the bundle | 25,726 (682 MB) |
| Files identical between the two releases | 24,403 |
| Files changed or added | 1,323 |
| Bytes of changed files, taken whole | 448 MB |
| Bytes that actually differ inside those files | 1.4 MB |
| Full DMG download today | 310 MB (arm64), 393 MB (x86_64) |
| Delta pack with this design | 0.48 MB |
| Manifest per release | 5.4 MB, fetched only when an update exists |
| Pack build time on this Mac | 17 s |
| Rebuild time on this Mac (hash base, clone, overlay, verify) | 17 to 27 s |

Where the differences live, and the encoder that catches each:

| Shape of change | Files | Encoder |
|---|---|---|
| Signature blob at the end of a thin Mach-O | ~40 dylibs, python3.12, node, Electron Framework | trim (common prefix and suffix) |
| Signature blob at the end of each slice of a universal binary | 37 `.so` from universal wheels | fat (per-slice trim) |
| Code-directory header hash near the front of a same-size file | Electron Framework, python3.12 | aligned (4 KiB blocks) |
| pyc header (16 bytes) | 1,221 files | trim |
| Hashes changed on scattered lines of a plist | `_CodeSignature/CodeResources` (9.8 MB) | lines |
| Entirely new content | 10 files (asar, STAMP, added scripts) | full |

The rebuilt 2.302.0 bundle was byte-identical to the installed one (`diff -rq`), passed `codesign --verify --deep --strict`, was accepted by Gatekeeper as "Notarized Developer ID", and validated with `stapler`. The CDHash matched the released app. The same run was repeated with the exact CI step script under bash and the system python.

## 2. What ships in this branch, and what does not

| Surface | Today (main) | This branch | Phase 2 |
|---|---|---|---|
| macOS in-app update transport | full DMG | delta pack with full-DMG fallback | unchanged |
| Release assets per arch | DMG + .sha256 | plus manifest.json, delta.tar.xz, their .sha256 | plus update feed |
| CI proof | stapler validate, four assets present | pack rebuilt and codesigned before upload; manifests required by verify | feed published after verify |
| Website Mac links | /releases/latest | unchanged | protocol handoff |
| Website Windows link | pinned to beta v2.291.8-beta.6 | /releases/latest/download/Sutra-Setup-x64.exe | unchanged |
| Windows in-app update | none | none (design only, section 7) | electron-updater with NSIS blockmap |
| Rollout, kill switch, minimum version | none | none (design only, section 8) | feed-driven |
| End-to-end tests of the pipeline | none | 8 scenarios, real helper, real hdiutil and codesign | Windows job on windows-latest |

## 3. Architecture

Actors and systems: a Mac running `Sutra.app`; the website on GitHub Pages; GitHub Releases as the artifact store and its API; the release workflow on macOS runners; the Windows installer path (out of scope for the lane).

Containers inside the app: the Electron shell (`electron/main.js`) owns the schedule (90 s after boot, then every 6 h) and every quit and relaunch decision. The Python backend owns the update state machine, downloads, verification and the detached bash helper (`updates.py`). The new module `updates_delta.py` owns manifests, packs and reconstruction, and is shared with CI. `updates_cli.py` exposes the same verbs to the shell in attach mode.

The delta lane sits inside `download_and_verify` and changes nothing downstream: it produces a bundle directory instead of a DMG, and the manifest record carries `artifact_kind: "app"`. Staging, arming, the lease, the helper's gates and the two-rename swap are the existing code; the helper only learns to skip `hdiutil attach` for a directory source and to clone instead of `ditto`.

Trust anchor: the reconstructed bundle is byte-identical to what CI signed, so `codesign --verify --deep --strict`, Gatekeeper's `spctl -a -t execute`, TeamIdentifier continuity, bundle id and version gates all still hold. The manifest and pack need no signature of their own: a tampered manifest or pack yields a bundle that fails codesign, and the lane falls back to the DMG. Their `.sha256` files guard transport only.

## 4. Artifacts and formats

Per stable release and per arch, beside `Sutra-<arch>.dmg`:

| Asset | Content |
|---|---|
| `Sutra-<arch>.manifest.json` | schema 1; version, arch, channel, bundle_id, tag, previous_version, app_name, files, bytes, tree_sha256; `entries[]` sorted by path with `t` = f (sha256 `h`, size `s`, mode `m`), l (target `l`), d (empty dir, mode) |
| `Sutra-<arch>.delta.tar.xz` | `index.json` (from_version, to_version, per new-file-hash entry: kind full or delta with `base` hash and `ops`), then `blobs/<sha256>` literal members |
| `*.sha256` | `shasum -a 256` output, one per asset, written by the leg that built it |

Delta ops are a list over the base file: `["c", offset, length]` copies a run of the base, `["l", length]` takes literal bytes. Every encoder is self-verified at pack time by applying it. The manifest is built from the app inside the DMG the leg actually published, never from a rebuild.

Pack safety: packs are streamed, never `extractall`; member names must be exactly `index.json` or `blobs/<64 hex>`, regular files, under a size bound. Manifest paths must be relative with no empty, `.` or `..` component, must not repeat, and nothing may sit under a symlink entry. Ops are bounds-checked. Every rebuilt file is re-hashed.

## 5. Client flow: the delta lane

1. `check`: the release JSON now also reports `delta` (manifest and pack present for this arch) and `pack_size`.
2. `stage` (no lock held): if the release has delta assets and the app runs from a bundle, fetch the manifest (bounded size), require and verify its published `.sha256`, validate its schema, require version and arch to match and `bundle_id` to equal the installed bundle's.
3. Chain: if `previous_version` is not the installed version, walk back through the previous releases' manifests by their deterministic per-tag URLs, at most `MAX_CHAIN` (5) hops, collecting one pack per hop. A gap or a longer chain is a miss.
4. Fetch each pack with the existing resumable download (Range, 4 tries), verify its published checksum, stream it into a scratch dir.
5. Reconstruct beside the staging dir: hash the installed bundle; plan every file the manifest wants (kept, copied from elsewhere in the base, or rebuilt from packs, recursively for deltas whose base is itself a delta); check free space; clone the base with `cp -c` (APFS copy-on-write, instant) or copy; remove everything the manifest does not list; write rebuilt files; recreate symlinks and empty dirs; set modes; verify the whole tree independently against the manifest.
6. Gates before staging: `codesign --verify --deep --strict` and `spctl -a -t execute` on the rebuilt bundle.
7. Commit under the lock as today, with `artifact_kind: "app"`, the manifest kept beside it; older images, bundles and manifests in the staging dir are removed.
8. `arm`: re-verify the staged bundle file by file against its manifest and re-check the manifest's digest against the published one online, then stamp `installing` and spawn the helper.
9. Helper: identical gates (codesign, team, bundle id, version), clone beside the app, rename swap with the nesting guard, executable check, result file, optional relaunch.
10. `resolve` on next launch: unchanged; clearing removes the staged bundle directory and its manifest.

Any failure at steps 2 through 6 is logged as "delta update not possible (reason); downloading the full image" and the DMG path runs in the same stage call. `SUTRA_UPDATE_DELTA=0` forces the DMG path.

## 6. First install from the website

Today the button resolves the Mac architecture with a five-probe ladder and links `/releases/latest/download/Sutra-<arch>.dmg`; unknown goes to the releases page. Windows was pinned to an old beta tag; this branch points it at `/releases/latest/download/Sutra-Setup-x64.exe`.

A browser cannot apply a delta, read the installed version, or write to Applications, so the download button always serves the full installer to new users. For existing users the useful handoff is a `sutra://update` link that the installed app registers (`CFBundleURLTypes` on Mac, NSIS protocol registration on Windows) and that only triggers "check now"; the page falls back to the full download after about two seconds. The handler must accept no parameter that influences what is downloaded.

Known first-install gaps to close: the page shows no version, size or checksum; Firefox on Apple Silicon usually lands on the chooser; a translated (Rosetta) install is never offered the native build; the page claims "signed and notarized" even for an ad-hoc build; nothing checks the page's link constants against the workflow's asset names before deploy.

## 7. Windows

There is no updater on Windows today, the installer is unsigned, and providers do not yet work there. The right lane is electron-updater with NSIS differential (blockmap) downloads, which needs: a `publish` block so `app-update.yml` is generated; `latest.yml` and `Sutra-Setup-x64.exe.blockmap` published beside the installer; `allowPrerelease: false` and `allowDowngrade: false`; the beta build excluded exactly as on Mac; the portable exe detecting itself and disabling updates; per-user, elevation-free installs kept; the backend's whole process tree terminated before `quitAndInstall`; a per-version attempt counter mirroring `MAX_APPLY_ATTEMPTS`; a file logger. The first in-app update is a full download because nothing seeds electron-updater's cache; differential applies from the second. Code signing (Authenticode) should precede shipping an updater that silently replaces the app. This cannot be exercised from a Mac; it needs a windows-latest job that installs v1 silently and updates to v2 from a local static server.

## 8. Update feed, rollout, kill switch (phase 2)

The app polls GitHub's API unauthenticated, which allows 60 requests per hour per IP; an office behind one NAT can exhaust that on a release morning, and the API offers no rollout percentage, minimum version or kill switch. A static feed JSON on the website origin (or a fixed release asset) removes the API from the steady-state path and adds control:

`{schema, channel, generated_at, generated_from_tag, latest: {version, tag, min_supported, rollout_percent, rollout_started_at, killed}, assets: {arm64: {dmg, dmg_sha256, manifest, pack}, x86_64: {...}, win_x64: {...}}}`

Rules: the feed is advisory indirection; every artifact it names is still verified by the existing gates. A held-back client is a first-class state, and rollout is a delay never a decline (mandatory updates). `min_supported` bypasses rollout. `killed` stops staging and discards a staged, not-armed bundle. Unreachable feed falls back to the API. The feed is published only after the verify job, and the website deploy must be triggered by `workflow_run`, not by a token-authored commit (which GitHub does not run workflows for). Client id for bucketing is a random UUID stored 0600 in the staging dir, never sent anywhere.

The release itself should be created as a draft by all legs and published from verify: today the Windows leg publishes the shared release minutes before the DMGs land, so `/releases/latest` points at a tag with no DMG for 3 to 9 minutes.

## 9. Threat model (STRIDE)

| Threat | Scenario | Mitigation in this branch | Still open |
|---|---|---|---|
| Tampering, pack or manifest | attacker swaps an asset on GitHub | rebuilt bundle fails codesign or Gatekeeper; fallback to DMG which is notarized | none for code execution; a bad manifest is a denial of the delta lane only |
| Tampering, path traversal | pack member `../x`, symlink then write-through | member names restricted; manifest paths validated; nothing under a symlink entry; no extractall | none |
| Spoofing, wrong signer | notarized app from another team | TeamIdentifier continuity and bundle id gates, unchanged | continuity accepts ad-hoc to ad-hoc; add a compiled allowlist of teams |
| Elevation, environment | harvested PATH or DYLD vars reach the helper | none new | helper and sidecar should run with a fixed PATH and absolute tool paths; the E2E shims rely on PATH today and would need a test seam |
| Repudiation | no record of what installed and why | manifest record keeps `delta` stats and the fallback note | helper log still lives in a temp dir; move it into the staging dir |
| Denial of service, rate limit | office NAT exhausts 60 requests/hour | delta chain uses deterministic download URLs, not the API | feed (section 8), jitter, conditional requests |
| Downgrade | old but validly signed release served | version gate against the staged version | no monotonic floor on the installed version; add one in the helper |
| Missing checksum | `.sha256` absent or unreachable | delta lane refuses without a published checksum | the DMG lane still skips gate 1 silently; make it fail closed |
| Information disclosure | telemetry of update outcomes | none sent | keep it that way; local counters only |

## 10. Failure modes

| Failure | Behaviour |
|---|---|
| Installed bundle modified by the user or a scanner | hash miss, delta miss, full DMG |
| Pack blob corrupted or tampered | rebuilt file fails its hash, reconstruction discarded, full DMG |
| Manifest for an intermediate release missing (older than the lane, or pulled) | chain miss, full DMG |
| More than 5 releases behind | full DMG |
| Not enough free space | delta miss before any write, full DMG (which has its own check to add) |
| Crash during reconstruction | the destination is removed on any exception; the staging dir sweeps stale work dirs |
| Crash during the swap | unchanged: recover.json breadcrumb, nesting guard, executable check, rollback |
| Non-APFS volume | clone falls back to a copy, with a second free-space check |
| Pack download dropped | Range resume, 4 tries, then full DMG |
| Release for another bundle id or channel | refused before download of the pack |

## 11. Operations

Storage: about 5.9 MB of extra assets per stable release per arch. Packs chain, so no combinatorial set is needed. Cadence measured at 2 to 16 stable tags per day means a client away for a weekend can exceed 5 hops; raising `MAX_CHAIN` costs only manifest fetches, or the feed can name a periodic full anchor.

Support: the manifest record shows `delta.hops`, `delta.rebuilt`, `delta.seconds` and the fallback note. Recommended next: persist helper logs under the staging dir, add an `updates_cli diagnostics` verb, and a `release-desktop.sh pause <version>` runbook that flips the feed rather than deleting assets (deleting a `.sha256` today silently disables the checksum gate).

## 12. Testing

`test_update_delta.py` (22 tests): every encoder on a synthetic file of its real-world shape; encode must pick a delta, not full, for each; manifest exactness; tamper, traversal, duplicate and symlink-ancestor refusal; pack membership; foreign tar members refused; exact rebuild including renames, deletions, additions, symlink retargeting, mode changes and empty dirs; user-added junk removed; modified base is a miss; tampered blob fails closed; two-hop chain and a gap; CLI round trip.

`test_update_e2e.py` (8 scenarios, macOS): a local release server speaking GitHub's two shapes with Range support and fault injection; real ad-hoc-signed bundles with a Mach-O main executable; real UDZO DMGs; the shipped `updates_cli` subprocess for check, stage, arm and resolve; the real detached helper waiting on a real pid; PATH shims only for `spctl` and `open`. Scenarios: full image end to end with relaunch; delta end to end without touching the DMG; modified base falls back; tampered pack falls back and never stages; another bundle id refused by the lane and then by the helper's gate on the image; two-hop chain from v1 to v3 via deterministic tag URLs; dropped pack download resumes with a Range request; `SUTRA_UPDATE_DELTA=0` takes the image.

CI: the delta step rebuilds the previous app with the pack, diffs it against the released app, and runs codesign before upload; a pack over half the DMG is withheld with a warning; the verify job requires both manifests on stable releases. Not testable locally: notarization, Gatekeeper on a stranger's Mac, Windows.

Existing lanes unchanged and green: swap nesting, install guard, download resume, channel pins, CLI contract (39 tests).

## 13. Gaps in the existing pipeline found on the way (not fixed here)

- The DMG lane skips the checksum gate when the `.sha256` asset is missing or unreachable.
- The CLI `stage` verb does not call `install_blocker`, so an app running from the DMG downloads 300 MB every 6 h in attach mode.
- Download resume does not survive a process restart; each stage uses a fresh work dir.
- The manual `POST /api/updates/desktop` route is untokened, writes no manifest, and can race an armed helper.
- Stable and beta share one staging directory; a beta launch can consume stable's staged update.
- `recover.json` is never consumed; a crash inside the rename window leaves no launchable bundle and no automatic recovery.
- Helper logs live in a temp dir that macOS purges.
- The verify job checks four names; the founder's script requires six (Windows too); no verify job on the Windows workflow.
- The release is published by the first leg to finish (Windows), so `/releases/latest` briefly names a tag without DMGs.
- The payload ships 85 MB of test artifacts (`hooks/tests`, `sutra-ui/qa/runs`), and pyc files are compiled with timestamp headers, so both churn every release.
- No sutra-ui Python test runs in any GitHub workflow; `run-tests.sh` reports PASS for a lane that ran zero tests.

## 14. Phased plan

| Phase | Work | Effort |
|---|---|---|
| 0 | Trim test artifacts from the payload; compile pycs with `unchecked-hash` | hours |
| 1 (this branch) | delta module, updater integration, helper directory source, CI proof and upload, verify list, website link, E2E harness | done, needs review and a beta |
| 1b | fixed PATH in the helper, checksum gate fail-closed in the DMG lane, helper logs into the staging dir, `MAX_CHAIN` sized to cadence | 1 to 2 days |
| 2 | update feed with rollout, kill switch, minimum version; draft-then-publish release; `workflow_run` website deploy | 3 to 4 days |
| 3 | Windows electron-updater with blockmap, windows-latest E2E job, Authenticode signing | 3 to 5 days plus signing setup |
| 4 | Website: version, size and checksum on the page; `sutra://` handoff; link-constant check at deploy | 1 to 2 days |

## 15. Open questions for the founder

1. Ship the lane behind a beta first (D80) and watch the pack sizes and `delta.hops` on real installs before the stable tag?
2. Is a 5-hop chain acceptable, or should the feed name a periodic full anchor given 2 to 16 stable tags a day?
3. Should the helper's TeamIdentifier gate gain a compiled allowlist now, ahead of any signing identity change?
4. Should the manifest be published gzipped (5.4 MB becomes about 0.9 MB) at the cost of one more asset name?

provenance: written 2026-09-25 by Claude Fable 5.1 on branch desktop-delta-updates from measurements on the real 2.300.0 and 2.302.0 bundles, the reader and sweep workflows of this session, and the test runs recorded in the same session; supersedes nothing.
