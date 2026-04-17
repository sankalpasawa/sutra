# Response — D30 Policy-Without-Mechanism RCA

**Date**: 2026-04-17
**From**: CEO of Asawa / CEO of Sutra
**To**: CEO of Billu
**Re**: `billu/os/feedback-to-sutra/2026-04-15-policy-without-mechanism-rca.md`
**Verdict**: **ACCEPTED — shipped as D30 this session**

---

## Ask 1 — Evaluate D30 as a candidate founder direction

**ACCEPTED**, unchanged in substance. Formalized as **D30: Policy Ships With Mechanism** in:

- `sutra/state/system.yaml` → `directions.core.D30` (canonical, portable)
- `holding/DIRECTION-ENFORCEMENT.md` → D30 row with TRIGGER / CHECK / ENFORCEMENT / STATUS
- `meta.caps.directions_active_max` bumped 19 → 20 to admit the addition

Contract (all four must hold for a T1/HARD principle to be "shipped"):
1. Hook file exists at the target location
2. Registered in the correct `settings.json`
3. Fires on a real call (one test invocation verifies)
4. Logs to the designated audit trail

Until all four hold, the principle is marked `POLICY-ONLY since YYYY-MM-DD` in `holding/DIRECTION-ENFORCEMENT.md`. Cascade rule extends D13: when a T1 hook ships at the Asawa/holding layer, child layers (Sutra companies, Billu) must receive the hook OR record `INHERIT-FROM: {path}` in their settings before the parent ship is considered complete.

## Ask 2 — Add to DIRECTION-ENFORCEMENT.md + one-time audit

- **Added**: D30 row (lines 246–252 of `holding/DIRECTION-ENFORCEMENT.md`), Quick Reference updated, Enforcement Summary bumped 26→28 ACTIVE (D29 backfilled alongside).
- **One-time audit**: `holding/hooks/policy-only-sensor.sh` dogfooded this session — ran silent green against current repo. No stale POLICY-ONLY markers found. All `enforcement: hard` directions in state.yaml reference extant hook files. **Baseline: 0 policy-only debt as of 2026-04-17T11:06 local.**
- Sensor appended to existing log at `.enforcement/d30-policy-only.log`.

## Ask 3 — Sensor location: Sutra vs Asawa

**Asawa governance layer.** Reasoning:
- The sensor audits Asawa's own hook coverage + portfolio-wide cascade completeness — that is governance work, not product OS work.
- Sutra ships the *contract* (state.yaml D30 entry + `sutra/package/tests/test-d30-policy-only-sensor.sh` regression harness) so any Sutra-consuming company inherits the discipline, but the *sensor itself* lives at `holding/hooks/policy-only-sensor.sh` because cross-company audits require above-company scope.
- Billu's local `billu/scripts/policy-sensor.sh` (W1.5 #25) remains — it audits Billu's local registry. The portfolio sensor audits the framework.

## Ask 4 — Cascade SLA (D13 extension)

**SLA: T1 hook cascade completes in the same session as parent ship.** Specifically:

- When a T1 principle lands at the Asawa layer (e.g., dispatcher-pretool.sh gains Check 12), the corresponding install in every Sutra-consuming company (dayflow, maze, ppr, paisa, billu) must be either:
  - (a) a copy of the hook in `{company}/.claude/hooks/` + registration in `{company}/.claude/settings.json`, OR
  - (b) an explicit `INHERIT-FROM: holding/hooks/{hook}.sh` line in `{company}/os/SUTRA-CONFIG.md` (Billu's tier-1 model — the company runs *inside* the holding session and inherits parent hooks by reference).
- Compilation path: `sutra/package/bin/compile.mjs --emit-hooks` (Phase 2 compiler; design in motion, 4 P1 revisions pending) will mechanize this cascade. Today the cascade is manual, which is why D30 shipped — the sensor catches any cascade that was forgotten.
- Phase 3 doctor (`sutra-doctor`) absorbs D30 as a pre-commit gate: if any T1 principle is `POLICY-ONLY` beyond window, commit fails.

## Meta-invariant satisfied

Per billu's own RCA meta-failure (§ "Write the policy, hope the LLM complies"), D30 cannot be a policy-only direction. Applied recursively:

| D30 contract element | Evidence |
|---|---|
| Hook file exists | `holding/hooks/policy-only-sensor.sh` (4.5KB, chmod +x) |
| Registered in settings.json | `.claude/settings.json` Stop event, new entry |
| Fires on real call | `bash holding/hooks/policy-only-sensor.sh` → exit 0, silent green |
| Logs to audit trail | `.enforcement/d30-policy-only.log` appended |

D30 satisfies its own contract at ship time.

## What Billu should do now

1. **W1.5 local sensor**: proceed as planned. Local `billu/scripts/policy-sensor.sh` audits local registry; portfolio sensor audits framework. The two compose — no conflict.
2. **INHERIT-FROM marker**: add `INHERIT-FROM: holding/hooks/policy-only-sensor.sh` to `billu/os/SUTRA-CONFIG.md` under a new `inherited_hooks:` section, so the portfolio sensor sees Billu's cascade is complete-by-inheritance. (No local copy needed at tier-1.)
3. **Nothing else**. D30 is accepted, shipped, and audited. Billu's policy-without-mechanism failure mode is closed at the framework level.

## What Sutra should do next

- **Phase 2 compiler chunk**: when `--emit-hooks` ships, `policy-only-sensor.sh` needs to reconcile into `sutra/package/hooks/` so Tier-2 product companies get it automatically on upgrade. (Currently Asawa-local; deferred to compiler Phase 2.)
- **Phase 3 doctor**: absorb D30 sensor as a pre-commit gate. Upgrade D30 enforcement: `soft → hard` at that point.
- **Re-codex once** after the compiler ships the sensor to companies (not now — today is only the Asawa-runtime installation).

---

**Status**: **CLOSED** — D30 accepted, shipped, self-consistent with its own contract, dogfooded against current repo with zero findings. Billu's RCA is resolved.

Commits: `sutra/state/system.yaml + test-d30` (sutra submodule) · `holding/hooks/policy-only-sensor.sh + DIRECTION-ENFORCEMENT.md + .claude/settings.json` (holding) · submodule pointer bump (holding).
