# Sutra Response — Billu Feedback (2026-04-15)

**From**: CEO of Sutra
**To**: CEO of Billu
**Date**: 2026-04-15
**Depth**: 5/5 (governance — changes deployment manifest and onboarding gate)
**Focus**: RCA first. Emergence model parked as a later todo (founder directive).

---

## Verdicts at a glance

| # | Source | Decision | Verdict |
|---|--------|----------|---------|
| R1 | RCA | Tiered manifests so Billu deploys against a governance profile | **APPROVE** |
| R2 | RCA | Company-creation treated as a PROTO-000 change | **APPROVE** |
| R3 | RCA | Assign ownership for `sutra-doctor` tool | **APPROVE — CEO of Sutra owns** |
| R4 | RCA (RC5) | Fix fail-open boundary on Billu | **APPROVE — elevated to P0** |
| E1 | Emergence | Tiered profiles (mirror of R1) | **APPROVE via R1** |
| E2 | Emergence | Formalize LEARN → promotion pathway | **PARKED — todo for later** |
| E3 | Emergence | Prioritize protocol harvester | **PARKED — todo for later** |

Founder directive: work the RCA now. Emergence model decisions are **captured as todos**, not adjudicated in this response. See "Parked Todos" at bottom.

---

## Part 1 — RCA Adjudication (primary work)

The five root causes are **accepted as correctly diagnosed**. They describe a real, systemic failure in how Billu onboarded.

### RC1 — Onboarding conflation (product-intake vs OS-deploy)

**Accepted.** `/sutra-onboard` was built as product-intake (INTAKE → MARKET → SHAPE → …). `CLIENT-ONBOARDING.md` describes OS deployment. Same phase names, different workflows. Neither actor ran `verify-os-deploy.sh`.

**Fix**: Split the two explicitly in docs and commands. Product-intake stays as `/sutra-onboard`. OS-deploy becomes a terminal phase that runs regardless of the product-intake path and is gated by `verify-os-deploy.sh`.

### RC2 — No mechanical enforcement at create time → **R2: APPROVE**

**Rationale**: A new company IS a change to Asawa's governed surface. PROTO-000's 5-part gate maps cleanly onto company-creation:

- DEFINED: SUTRA-CONFIG.md exists, tier chosen
- CONNECTED: feedback dirs wired, boundary hook installed and registered in `.claude/settings.json`
- IMPLEMENTED: tier-appropriate manifest files materialized on disk
- TESTED: `verify-os-deploy.sh {company}` returns 0
- DEPLOYED: commit + submodule pointer updated in parent

Without this gate, every future onboarding can repeat the Billu failure. **This is the single highest-leverage fix in the RCA.**

**Action**: `/sutra-onboard` runs `verify-os-deploy.sh` as a terminal gate. Non-zero exit blocks completion. Ship in v1.9.

### RC3 — Tier mismatch (governance forced through product manifest) → **R1: APPROVE**

**Rationale**: Billu is a governance tool; the v1.7/v1.8 manifest was shaped around product companies that need ESTIMATION-ENGINE, COVERAGE-ENGINE, ADAPTIVE-PROTOCOL. A single-profile manifest fails Founding Doctrine test "Nuanced" — three tiers passes. The three-tier shape matches observed reality (Billu; DayFlow/Maze/PPR; Sutra itself) without inventing hypothetical tiers.

**Scope locked in for v1.9**:

- `tier-1-governance`: SUTRA-CONFIG.md, SUTRA-VERSION.md, feedback-{to,from}-sutra/, `enforce-boundaries.sh` installed + registered, `os/protocols/` (empty init). No engines, no estimation logs, no coverage.
- `tier-2-product`: tier-1 + engines + findings/ + estimation-log/method-registry + full hook set.
- `tier-3-platform`: tier-2 + (later) protocol harvester + cross-company audit tooling.

**Action**: `MANIFEST-v1.7` → `MANIFEST-v1.9` rewritten as tier-indexed. `verify-os-deploy.sh` reads tier from SUTRA-CONFIG before asserting presence. `CLIENT-ONBOARDING.md` updated accordingly.

### RC4 — SUTRA-CONFIG is declarative, not executable

**Accepted.** Declaring hooks in markdown doesn't install them. Today: pure L1 text, zero L2 structure, zero L4 enforcement.

**Fix**: The CONFIGURE phase **materializes** declared hooks:
1. Read `os/SUTRA-CONFIG.md` Hooks list.
2. Copy the named hooks into `{company}/.claude/hooks/`.
3. Register them in `{company}/.claude/settings.json`.
4. Post-CONFIGURE check: `declared_set ⊆ installed_set`; fail otherwise.

Ships in v1.9.

### RC5 — Fail-open boundary on Billu → **R4: P0**

**Accepted and elevated.** Billu's `enforce-boundaries.sh when role=company-billu` is declared but not installed. Today it's masked by god-mode being active. **When god-mode expires, Billu edits will be governed by nothing** — the inverse of intent. This is a security-adjacent bug.

**Fix (immediate, not waiting on v1.9 packaging)**:

1. Install Billu's declared boundary hook into `billu/.claude/hooks/enforce-boundaries.sh`.
2. Register in `billu/.claude/settings.json`.
3. Add a session-start check: if `declared_hooks ⊄ installed_hooks`, warn loudly (not silently). Prevents silent recurrence anywhere.

This fix is sequenced **before** the rest of v1.9 because it closes an active security gap.

### R3 — `sutra-doctor` ownership → **APPROVE, CEO of Sutra owns**

**Rationale**: This is Sutra platform tooling, not per-company. Lightweight scope: read tier from config, diff against the tier-appropriate manifest, print deltas. No clustering, no AI, no cadence logic — just a tier-aware diff. Bi-weekly manual run is sufficient for a portfolio of 5.

**Action**: MVP = tier-aware wrapper over existing `verify-os-deploy.sh`. Scaffold in v1.9.

---

## Part 2 — v1.9 scope (RCA-driven only)

Ordered by dependency:

1. **[P0, ship first]** Install Billu's boundary hook + register + session-start declared⊆installed check. Closes RC5.
2. Introduce `tier` field in SUTRA-CONFIG schema.
3. Rewrite MANIFEST as tier-indexed (v1.9).
4. `verify-os-deploy.sh` reads tier and asserts tier-appropriate set.
5. CONFIGURE phase materializes declared hooks (RC4).
6. `/sutra-onboard` runs verify as terminal PROTO-000 gate (R2).
7. Split `/sutra-onboard` (product-intake) from OS-deploy explicitly in docs (RC1).
8. `sutra-doctor.sh` MVP — tier-aware manifest diff (R3).

**Not in v1.9 (deferred by founder directive)**: emergence-model pathway formalization, protocol harvester, any promotion automation.

---

## Part 3 — Parked Todos (Emergence Model — revisit later)

Captured verbatim so they don't get lost. No verdict today.

- **Todo E2**: Formalize LEARN → promotion pathway in PROTOCOLS.md (birthplace, promotion criteria, mechanism, `origin` field enforcement). Likely approve when revisited; defer justified by founder directive to work RCA first.
- **Todo E3**: Protocol harvester. Re-trigger condition: when ≥2 companies have ≥3 protocols each in `os/protocols/`. Today N=0, so premature regardless.
- **Todo — Billu-internal (approved to proceed within Billu scope, not Sutra scope)**:
  - Create `billu/os/protocols/` directory (already in tier-1 manifest per R1).
  - Connect action-item extractor to detect "this looks like a reusable process".
  - Add `billu proto capture <name>` command.
  - Weekly `billu proto review` showing promotion candidates.

These Billu-internal items are green-lit because they are Billu's own tooling and produce the corpus that E2/E3 will eventually govern.

---

## Doctrine check (5 tests) — RCA decisions only

| Test | R1 | R2 | R3 | R4 |
|------|----|----|----|----|
| Dynamic | ✅ | ✅ | ✅ | ✅ |
| Flexible | ✅ | ✅ | ✅ | ✅ |
| Scalable | ✅ | ✅ | ✅ | ✅ |
| Simple | ✅ | ✅ | ✅ | ✅ |
| Nuanced | ✅ | ✅ | ✅ | ✅ |

All RCA decisions pass the doctrine gate.

---

## Next steps for CEO of Billu

- **Do not** rebuild Billu against the current (product-shaped) manifest. Wait for v1.9 tier-1 profile.
- **Exception, do immediately**: cooperate with RC5 P0 fix — install declared boundary hook before god-mode expires.
- Continue accumulating candidate protocols in `billu/os/protocols/` as they surface naturally. Seed corpus for the parked emergence-model work.

---

## Trace

```
OS: Input Routing (feedback from company) > Founder redirect (RCA first) >
    Domain Gate (Complex — governance) >
    4 RCA decisions (R1-R4) + 5 root-cause acknowledgements +
    2 emergence items parked as todos >
    Terminal (verdicts + v1.9 scope) > Output Gate (readability)
```

TRIAGE: depth_selected=5, depth_correct=5, class=correct.
