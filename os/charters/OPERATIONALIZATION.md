# Charter: Operationalization

**Objective**: Every shipped artifact operates in production — measured, monitored, iterated, retired on signal — not just deployed and forgotten.
**DRI**: Sutra-OS
**Contributors**: Engineering, Operations, Analytics
**Status**: ACTIVE (v2 — rewritten 2026-04-20 post-Codex round-1 + founder decisions)
**Applies to**: Sutra (self) first. Propagation to DayFlow + Billu queued (depends on upgrade-clients.sh charter-aware extension — shared dep with Tokens).
**Created**: 2026-04-20 (v1) → rewritten 2026-04-20 (v2)
**Review cadence**: Weekly; scored quarterly
**Source direction**: holding/FOUNDER-DIRECTIONS.md D30 (2026-04-20)
**Design doc**: holding/research/2026-04-20-operationalization-charter-v2-redesign.md

---

## 1. Why this charter exists

Sutra lifecycle terminates at EXECUTE → MEASURE → LEARN. Artifacts get designed, implemented, sometimes measured — but adoption, monitoring, escalation, and decommissioning get left for the next founder prompt.

Founder D30 (2026-04-20): "Whatever things we build for Sutra, Asawa, client companies — plan, design, ship, and AFTER shipping, work on operationalizing it. Can't wait for humans to operationalize — create the operational plan and execute it."

This charter inserts a **7th lifecycle phase — OPERATIONALIZE** — between MEASURE and LEARN. Every new artifact ships with a 6-section operationalization plan, enforced at git boundary.

---

## 2. Six-Section Operationalization Template

Every enforced artifact carries this inline section:

~~~markdown
## Operationalization

### 1. Measurement mechanism
What metric proves this works in prod?

### 2. Adoption mechanism
How does this reach every intended consumer?

### 3. Monitoring / escalation
Who watches, at what cadence, with what threshold triggers action?

### 4. Iteration trigger
Under what observed condition does this get revised, deprecated, or expanded?

### 5. DRI
Named role (not "author default").

### 6. Decommission criteria
Under what signal does this artifact retire?
~~~

1-3 lines per section minimum. V1 = presence gate only (quality lint deferred to V3 per founder 2026-04-20).

---

## 3. KPIs (denominator-safe)

| Metric | Formula | Null handling | Target (Q2) | Warn | Breach |
|---|---|---|---|---|---|
| New-artifact compliance | count(new_artifacts_with_ops) / count(new_artifacts) rolling 7d, denom>=2 | denom<2 → insufficient-data | 100% | <95% | <80% |
| Grandfather-revoked compliance | count(revoked_with_ops) / count(revocations) rolling 30d, denom>=2 | denom<2 → insufficient-data | 100% | <90% | <70% |
| Block-to-add time | median(commit_ts_ops_added − commit_ts_first_block) per artifact | null if no block | <=4h | >24h | >72h |
| Active artifact churn | count(retired_in_q) / count(active_at_q_start) | active=0 → N/A | 5-15% | 0% | >40% |
| Registry freshness (risk-tiered) | count(active where next_review < today - 2q) / count(active) | tier-relative | <10% | >=25% | >=50% |

---

## 4. OKRs — Q2 2026

```
OBJECTIVE: Every shipped artifact operates in prod — measured, monitored, iterated.

  KR1: Lifecycle extended (ESTIMATION-ENGINE + PROTO-000 6th criterion
       + state/system.yaml) shipped 2026-04-20 — Score: 1.0 (shipped V1)
  KR2: Hook HARD at 4 trigger points (PostToolUse + pre-commit + pre-push + CI)
       shipped 2026-04-20 — Score: 1.0 (shipped V1)
  KR3: New-artifact compliance = 100% for 14 consecutive days
       by 2026-05-05 — Score: 0.0
  KR4: Propagated to >=2 downstream companies via charter-aware
       upgrade-clients.sh (shared dep with Tokens KR4) by 2026-06-30 — Score: 0.0
```

---

## 5. Enforcement Spec

### 5.1 Enforced paths (Tier A + Tier B per founder)

**Tier A** (always enforced):
- sutra/os/charters/*.md
- sutra/**/protocols/PROTO-*.md
- sutra/**/d-engines/*.md, sutra/**/engines/*.md
- holding/departments/*/CHARTER.md
- sutra/os/SUTRA-CONFIG.md, */os/SUTRA-CONFIG.md

**Tier B** (extended):
- holding/hooks/*.sh, sutra/package/hooks/*.sh
- sutra/layer4-practice-skills/**/*.md
- sutra/package/bin/*.sh, sutra/package/bin/*.mjs
- .claude/commands/*.md
- holding/departments/*/*.sh

Editable registry: sutra/state/system.yaml.operationalization.enforced_paths.

### 5.2 Exempt paths
- holding/research/*.md, TODO/BACKLOG/CHANGELOG/MEMORY, .claude/, .enforcement/, .analytics/, *.log, *.jsonl, holding/checkpoints/*

### 5.3 Four trigger points

| Point | Location | Speed | Authority |
|---|---|---|---|
| Early feedback | PostToolUse on Edit/Write | instant | warn only |
| Pre-commit | .git/hooks/pre-commit | <1s | BLOCK commit |
| Pre-push | .git/hooks/pre-push | <2s | BLOCK push |
| CI merge gate | .github/workflows/operationalization-check.yml | ~60s | BLOCK merge |

### 5.4 Grandfathering (git-history)

- Cutover commit SHA stored in sutra/state/system.yaml.operationalization.cutover_commit
- Files existing at cutover → exempt until semantic change
- Semantic change: new file OR diff >=5 lines OR heading change OR table row change
- Pure typo/whitespace → not semantic
- Pure rename → not semantic; grandfathering transfers to new path

### 5.5 No override

Per founder 2026-04-20: no env-var override. No OPS_PLAN_ACK. Only escape is reverting the hook (visible in git blame).

---

## 6. Roadmap — V1 shipped 2026-04-20; V2 ongoing

| # | Action | Wave | Status |
|---|---|---|---|
| 1 | holding/OPERATIONALIZATION-STANDARD.md | V1 | DONE |
| 2 | holding/hooks/operationalization-check.sh | V1 | DONE |
| 3 | holding/hooks/tests/test-operationalization-check.sh | V1 | DONE |
| 4 | .git/hooks/pre-commit + pre-push wrappers | V1 | DONE |
| 5 | .github/workflows/operationalization-check.yml | V1 (flipped per founder Q2) | DONE |
| 6 | sutra/state/system.yaml operationalization block + cutover_commit | V1 | DONE |
| 7 | PROTOCOLS.md — add 6th criterion OPERATIONALIZED to PROTO-000 | V1 (flipped per founder Q5) | DONE |
| 8 | ESTIMATION-ENGINE.md — add OPERATIONALIZE phase (both paths) | V1 (flipped per founder Q5) | DONE |
| 9 | Self-test: TOKENS.md gets ops section | V1 | DONE |
| 10 | 14-day compliance window; heuristic revision if FP>10% | V2 | TODO |
| 11 | Charter-aware upgrade-clients.sh extension (shared w/ Tokens) | V2 | TODO |
| 12 | Propagate to DayFlow + Billu | V2 | TODO |
| 13 | Q2 review | — | TODO |

Deferred to V3: quality lint, system-emits-typed-data, active registry quarterly kill.

---

## 7. Active Artifact Registry

sutra/state/system.yaml.operationalization.active_artifacts — list of {path, cutover_sha, dri, tier, next_review_date, status}. Populated as artifacts get ops sections.

Quarterly: Sutra-OS scans next_review_date past-due entries, escalates to DRI. Two unresolved quarters → kill review → retired.

---

## 8. Practice Contributions

| Unit | Role | Responsibilities |
|---|---|---|
| Sutra-OS | DRI | Charter, STANDARD, engine edits, PROTO-000 extension, schema, scoring |
| Engineering | Contrib | Hook, 4-point trigger wiring, tests, upgrade-clients.sh extension |
| Operations | Contrib | Run-state monitoring, escalation, decommission |
| Analytics | Contrib | KPI collection, Pulse, 14-day audit |

---

## 9. Cross-charter links

| Link | Direction |
|---|---|
| Tokens | Each cut gets ops plan. Shared upgrade-clients.sh dep. |
| Speed | Each cut gets ops plan. |
| Artifact Structure Standard | Will require Operationalization section when shipped. |
| PROTO-000 | 6th criterion OPERATIONALIZED — this charter wires it. |
| Big Rock 2 | OPERATIONALIZE adds estimation dimension. |
| CLIENT-REGISTRY | V2 propagation tier-gated. |

---

## 10. Guardrails (forward-only, git-history)

Per founder 2026-04-20: no retroactive work. Existing artifacts (TOKENS, SPEED, PROTO-000..018, ESTIMATION-ENGINE pre-cutover) operate under old contract until a semantic change triggers revocation.

---

## 11. Operationalization (charter's own ops plan — D30 dogfood)

### 1. Measurement mechanism
New-artifact compliance % + grandfather-revoked compliance % from §3. Source: .analytics/ops-enforcement.jsonl aggregated weekly.

### 2. Adoption mechanism
Hook deploys to Sutra self first (roadmap #9 self-test on TOKENS). Propagation to DayFlow + Billu via upgrade-clients.sh extension (V2 #11).

### 3. Monitoring / escalation
Sutra-OS reviews compliance % weekly. Warn <95% → investigate. Breach <80% → revert + rework. Block-to-add time p50 >24h → rework heuristics.

### 4. Iteration trigger
FP block rate >10% after 14 days → adjust semantic-change heuristic. Zero blocks in 30 days → investigate coverage gap.

### 5. DRI
Sutra-OS (Sankalp through Q2 2026; reassigned at first quarterly review).

### 6. Decommission criteria
(a) Reflexive author habit for 6 consecutive quarters (compliance >=95%, FP<2%) → hook → SOFT sensor, merge into PROTO-000 6th criterion; or (b) codex/founder review concludes net-negative → revert + retire.

---

## 12. Related files

- Design doc: holding/research/2026-04-20-operationalization-charter-v2-redesign.md
- Standard: holding/OPERATIONALIZATION-STANDARD.md
- Hook: holding/hooks/operationalization-check.sh
- Test: holding/hooks/tests/test-operationalization-check.sh
- Git wrappers: .git/hooks/pre-commit, .git/hooks/pre-push
- CI: .github/workflows/operationalization-check.yml
- State: sutra/state/system.yaml.operationalization
- Lifecycle: sutra/os/engines/ESTIMATION-ENGINE.md (OPERATIONALIZE phase)
- PROTO-000 extension: sutra/layer2-operating-system/PROTOCOLS.md (6th criterion)
- Sister charters: sutra/os/charters/TOKENS.md, sutra/os/charters/SPEED.md
- Codex round-1: .enforcement/codex-reviews/gate-log.jsonl session 019daada-ffd0-7602-a12a-99208ff8baa1
