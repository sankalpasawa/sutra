# CI note: "dmg (arm64)" cancelled in run 44333095382 (sutra-pro-v0.6.2)

Status: diagnosis only. No workflow or product code was changed. Date: 2026-11-18.

## Verdict
Not a timeout and not a hang in our steps. The arm64 job never got a runner: it sat queued on `macos-15` for about 15 minutes and
GitHub gave up. The cause is hosted Apple Silicon capacity, not anything that changed between 0.6.1 and 0.6.2.

## Proven (API evidence)
- Attempt 1 job 134902615054 "dmg (arm64)": `steps: []`, `runner_name: ""`, `runner_group_name: ""`, labels `[macos-15]`.
  Started 15:13:39Z, completed 15:28:40Z, conclusion `cancelled`. No step ever ran.
- The check-run annotations of that job say: failure "The job was not acquired by Runner of type hosted even after multiple attempts"
  and three notices "Due to capacity constraints, jobs targeting macOS arm64 runners may experience longer queue times."
- 15 min is not our `timeout-minutes: 60` (a job-level timeout applies to a running job and would show steps and a runner).
  It matches GitHub's allocation retry giving up.
- Sibling "dmg (x86_64)" on `macos-15-intel` got a runner in 3 s and passed in about 8 min (15:13:42 to 15:21:57); every step green, so the
  commit, wheel, signing and notarization are fine on 0.6.2 (at least on Intel; arm64 never executed).
- Not a concurrency cancel: the group is `sutra-pro-release-macos-<tag>` with `cancel-in-progress: false`, and there is no newer run for the tag.
  `verify` then failed by design ("the dmg job finished as 'cancelled'").
- Earlier arm64 legs: v0.6.0 about 6 min, v0.6.1 about 7 min, both with a runner and success. No history of slow arm64 builds.
- Attempt 2 (15:29:20Z) is also `queued` with no runner at the time of writing: the shortage is ongoing.

## Hypotheses (not proven)
- Manual cancel by a person: the API shows no actor. The annotation text points to the platform, so unlikely. A line that would settle it:
  the run's audit/"cancelled by" event in the web UI.
- A real build problem on arm64 in 0.6.2: untestable until a runner is acquired. The first arm64 step log would settle it
  (and "Prove the bundle runs offline" is the 0.6.2-specific risk; it passed on x86_64).
- The raw job log is 404 (BlobNotFound) because no log was ever produced, consistent with the above.

## Recommended minimal fix
1. Now: no code change is needed to ship. When capacity returns, "Re-run failed jobs" on run 44333095382 (attempt 2 may already do it
   if it gets a runner); the x86_64 DMG on the release is replaced in place by design and the upload is idempotent.
2. Hardening (workflow, developer, small):
   - Keep `timeout-minutes: 60` (real runtime is 6 to 9 min; 25 would still be generous), but add `timeout-minutes` on the long steps
     (Build Sutra Pro.app, Prove the bundle runs offline: 10; each notarytool step: 25) so a hang names its step.
   - Add `--timeout 20m` to both `notarytool submit --wait` calls so a stalled Apple queue fails with a clear error.
   - Make `verify` message distinguish "never got a runner" (job steps empty) from a build failure, and say "re-run failed jobs".
   - Optional: fall back to `macos-26` (arm64) via a second matrix entry or a manual dispatch input `runner`, since macos-15 arm64 is the
     constrained pool. Not automatic: a fallback runner changes the toolchain, so decide deliberately.
3. Verify: re-run through workflow_dispatch/re-run for the existing tag sutra-pro-v0.6.2 (the tag must already exist; guard checks it).
   If the workflow file is changed, prove the change on a new beta tag (`sutra-pro-v0.6.2-beta.N`, a prerelease) first, per
   sutra-pro/AGENTS.md and docs/RELEASE.md, then release. Success means both DMGs plus checksums on the release and `verify` green.

## Update 2026-11-18 (evidence)
- Attempts 1, 2 (and 3 queued) of run 44333095382 all never got a macos-15 runner. In sutra-pro-ci the same label queued 2-3 s until today, then 303-604 s.
- Local Apple Silicon build of the 0.6.2 tree (wheel, app, ad hoc signing, offline proof, DMG) all succeeded: the tree is not the cause.
- Fix shipped: step timeouts, notarytool --timeout, a verify message that tells "no runner" from a build failure, and a dispatch input arm64_runner (default macos-15, never automatic).
