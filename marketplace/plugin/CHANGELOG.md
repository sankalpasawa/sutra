# Changelog

> **D# namespace cleanup wayfinder (2026-05-04)**: References below to "D43" in v2.16.0 release notes mean **OUT-DIRECT 3-check** which has been **renumbered to D46** in `holding/FOUNDER-DIRECTIONS.md`. References to "D44" in v2.17.0 release notes mean **PERMISSIONS extension** which has been **renumbered to D47**. The capability-axis charter keeps original D43; Native Workflow Personalization keeps original D44. Historical refs in this CHANGELOG are preserved unchanged — they describe what was operationally true at release time.

## v2.22.0 — 2026-05-04

**Sutra Delivery OS Wave 2 ships: second first-party Generative skill `core:architect`.**

(Note: v2.21.0 was concurrently allocated by the CSM SessionStart banner work; this Delivery OS wave bumps to v2.22.0 to avoid the version collision.)

Closes the architecture-authoring gap: gstack `plan-eng-review` reviews architecture but doesn't author; nothing in the surveyed ecosystem writes structured ARCHITECTURE.md as a first-party skill. v2.22.0 fills it with Sutra D38 Build-Layer integration as the distinctive value-add.

### What changed

1. **`sutra/marketplace/plugin/skills/architect/`** — new skill directory.
   - `SKILL.md` (~340 lines): designs and authors a single ARCHITECTURE.md covering 9 sections — Purpose+scale+constraints, C4 L1 (System Context), C4 L2 (Container), C4 L3 (Component for 1-3 high-leverage containers only), ADRs (Status / Context / Decision / Consequences with no-theater rule), STRIDE threat model with system-specific top 5-10 risks, Scaling axes (load/data/team/geography), Sutra D38 Build-Layer table (the distinctive value-add), Open questions + noted limitations. Existing-codebase mode adds D38 enforcement-category mapping (PLUGIN-RUNTIME / SHARED-RUNTIME / HOLDING-IMPL / LEGACY-HARD / SOFT) so the architecture matches what the runtime hook checks at edit time.
   - `evals/README.md` + `evals/{E1-greenfield-saas,E2-existing-codebase,E3-regulated-system}.md`: 3 structural-assertion evals. E1 covers blank-slate B2B SaaS with team-size taste check; E2 grounds in actual `sutra/marketplace/plugin/` directory and tests no-fabrication discipline (file-level path references required per L3 container); E3 covers regulated FinTech (RBI data-localization + DPDP consent) constraint-driven design.
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.21.0 → 2.22.0; description prepended.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.21.0 → 2.22.0; description synced.

### Codex REVIEW chain

Verdict: CHANGES-REQUIRED → all P0 + P1 folded.
- **P0 #1**: eval contract drift — E2/E3 required "Open questions" entry but SKILL.md's section contract didn't include one (same drift class as W1's section 6 "skip" issue). Fix: added section 9 "Open questions + noted limitations" to the always-emit contract; never silently omitted.
- **P0 #2**: D38 enforcement-mapping gap — E2 expected PLUGIN-RUNTIME / LEGACY-HARD / SOFT details but SKILL.md only defined L0/L1/L2 abstractly. Fix: added the 5-category enforcement-path mapping table to section 8, scoped to existing-codebase mode.
- **P1 #1**: telemetry append to `skill-adoption-log.jsonl` was an ecosystem anti-pattern (creates side effects unrelated to user intent, may fail in constrained environments). Fix: made the append OPTIONAL and non-blocking — silently skip if sink unwritable or telemetry opted out.
- **P1 #2**: "at least one component should be L1/L2" was build-layer cosplay — some systems legitimately are all-L0. Fix: reframed to "if all-L0, justify why everything generalizes."
- **P1 #3**: E2 "no fabrication" test was gameable (could pass with only top-level directory references). Fix: each L3 section must cite at least one file-level path within the container being decomposed.

Verdict file: `.enforcement/codex-reviews/2026-05-04-w2-architect-build-review.md`.

### Distinct from existing ecosystem skills

- gstack `plan-eng-review` — reviews an architecture proposal; this skill AUTHORS the architecture document.
- gstack `gsd-plan-phase` — phase planning (decomposition into tasks); this skill is one level higher (system structure).
- `core:incremental-architect` (W4) — evolves an existing architecture (migration patterns); this skill writes the original.

### Downstream cascade (D13)

T2/T3/T4 fleet receives via plugin update; additive, non-breaking. Self-score telemetry now optional + non-side-effecting per codex anti-pattern flag. Wave plan continues: W3 deterministic-testing, W4 incremental-architect.

---

## v2.21.0 — 2026-05-04

**CSM SessionStart banner — first execution of CSM TODO #2 visibility surface (D43).**

Per D43 + codex P2 surfacing path (CSM TODO #2, deadline 2026-05-15). 5-line banner on SessionStart shows capability bucket counts, pending fleet-parity count, latest audit timestamp, recurring-instrument pointer, and how to run the audit on demand. Closes the visibility loop the audit instrument (`holding/scripts/capability-audit.sh`, shipped same day in commit da41958) opened.

### What this delivers

For Asawa CEO sessions: every session start emits one screen of CSM state, so capability gaps are visible without manual `cat holding/CAPABILITY-MAP.md`.

```
[CSM·D43] Buckets: 13 shipping · 15 proposed · 5 asawa-only · 6 sutra-internal
[CSM·D43] Pending fleet-parity (cap-1xx proposed): 15; deadlines 2026-05-08 → 2026-06-01
[CSM·D43] Latest audit: 2026-05-04T06:01:38Z (audit jsonl: 31 rows)
[CSM·D43] Recurring instrument: holding/scripts/capability-audit.sh (L1, promote-to plugin/scripts/ by 2026-06-01)
[CSM·D43] Run audit on demand: bash holding/scripts/capability-audit.sh
```

### Behavior modes

- **Asawa-mode** (file `holding/CAPABILITY-MAP.md` present): full 5-line banner.
- **T4-mode** (file absent per D33 firewall): silent skip (`exit 0` before any output).
- **Kill-switch**: `CSM_BANNER_DISABLED=1` env or `~/.csm-banner-disabled` file.

T4 fleet doesn't carry `CAPABILITY-MAP.md` — it's Asawa-internal governance per D33. T4 visibility into the capability surface ships separately via the `/sutra-capability` skill (CSM TODO #3, deadline 2026-06-01).

### What changed under the hood

- **New hook** `sutra/marketplace/plugin/hooks/csm-sessionstart-banner.sh` (~60 LOC). Reads `holding/CAPABILITY-MAP.md` for bucket/status counts (regex grep on cap-### table rows) and `holding/state/capability-map-audit.jsonl` for latest audit timestamp (jq path lookup). Soft-fail throughout (`set -u` only, never `-e`); never blocks SessionStart.
- **`hooks/hooks.json`** — `SessionStart[0].hooks` array gains entry for the banner with timeout=3s. Now 8 entries total (was 7).
- **`.claude-plugin/plugin.json`** — `2.20.0` → `2.21.0`.
- **`.claude-plugin/marketplace.json`** — `2.20.0` → `2.21.0`.

### Verification

Banner tested in 3 modes pre-commit:
- Asawa-mode: emits 5 lines with real counts (13 shipping / 15 proposed / 5 asawa-only / 6 sutra-internal).
- T4-mode (no CAPABILITY-MAP.md): silent (exit 0).
- Kill-switch (`CSM_BANNER_DISABLED=1`): silent (exit 0).

### Codex

Not pre-consulted. Mechanical surfacing hook, reversible, ~60 LOC, soft-fail by design. Per Sutra Engine charter §16 amendment B (codex review at abstraction-freeze points, not per micro-step) and `[Right-Effort Discipline]` (surgical scope only). Post-ship review available on request.

### Coexistence note

This commit ships in parallel with v2.20.0 (Sutra Delivery OS Wave 1, `core:test-strategy` skill — separate working-tree changes by parallel Delivery OS workstream). v2.21.0 takes the next number to avoid collision. Both releases stack cleanly: v2.20.0 ships the new skill, v2.21.0 ships the new hook + version bump.

---

## v2.20.0 — 2026-05-04

**Sutra Delivery OS Wave 1 ships: first first-party Generative+Decisional skill `core:test-strategy`.**

Founder direction 2026-05-04: "I need some skills in the testing framework... in figuring out input, test, output test ways to go about writing architecture and schemas... I want these to be incorporated as part of Sutra... and I want this to be provided to clients as well of Sutra. Add this to plugins as well." Yesterday's [skill-validation framework](../../../holding/research/2026-05-04-skill-validation-framework.md) identified 4 problem-mode gaps (Diagnostic / Generative / Reactive / Refining) — all 9 existing Sutra skills are Governance-mode. v2.20.0 closes the Generative+Decisional gap with the first of 4 Delivery OS skills.

### What changed

1. **`sutra/marketplace/plugin/skills/test-strategy/`** — new skill directory.
   - `SKILL.md` (~250 lines): designs a TEST-STRATEGY.md document for any subject (function / module / system / AI prompt) before tests are written. Includes pyramid heuristics by domain (8 rows: pure compute / stateful service / API / CLI / LLM classifier / RAG / data pipeline / infra), fixture decision matrix (8 rows: own DB / managed DB / HTTP own / HTTP third-party / LLM / FS / clock / random), mock-vs-real boundary discipline, coverage targets matched to risk profile, AI eval-pack design (≥3 evals, baseline-without-skill, multi-model, structural+LLM-judge scoring, drift detection, fixture rotation), CI gate placement.
   - `evals/README.md` + `evals/E1-payment-processing.md` + `evals/E2-llm-classifier.md` + `evals/E3-cli-tool.md`: 3 structural-assertion evals covering safety-critical / user-facing / internal-tooling risk profiles. No fragile specifics (per yesterday's codex P1 fold).
2. **`sutra/marketplace/plugin/.claude-plugin/plugin.json`** — version 2.19.0 → 2.20.0; description prepended with v2.20.0 narrative.
3. **`sutra/.claude-plugin/marketplace.json`** — catalog entry version 2.19.0 → 2.20.0; description prepended (sync with plugin.json per v2.18.2 contract test).

### Codex review chain

- **CONSULT** on the original 5-skill spec: verdict RESCOPE → cut `core:idea-to-delivery` (codex P0: "product thesis, not bounded skill"), rename `io-contract-test` → `deterministic-testing` (codex P1: name now matches 4-technique scope), promote `test-strategy` to W1 (codex P1: broader demand, easier eval). All folded. Verdict at `.enforcement/codex-reviews/2026-05-04-sutra-delivery-os-spec-consult.md`.
- **REVIEW** on W1 build: verdict CHANGES-REQUIRED → all P0 (Anthropic-spec description shape: imperative second-person → third-person WHAT+WHEN; section contract: "7 sections" vs 8 listed → reconciled; section 6 "skip" vs eval expects placeholder → "always present, placeholder if no AI"; eval brittle specifics → loosened to structural-only) + all P1 (trigger discriminator added; fixture matrix DB rule corrected; own-DB threshold anti-pattern removed; infra pyramid softened) folded inline. Verdict at `.enforcement/codex-reviews/2026-05-04-w1-test-strategy-build-review.md`.

### Distinct from existing ecosystem skills

- gstack `gsd-add-tests` — generates the tests themselves; this skill plans BEFORE.
- gstack `qa` / `qa-only` — runs tests; this skill plans them.
- `superpowers:test-driven-development` — workflow (red-green-refactor); this skill is the strategy artifact.
- `superpowers:writing-plans` — generic planning; this skill is testing-specific with pyramid heuristics.

### Downstream cascade (D13)

T2 owned (DayFlow / Billu / Paisa / PPR / Maze) + T3 projects (Testlify / Dharmik) + T4 fleet — receives skill via plugin update; additive, non-breaking. No client TODO updates required. Sutra plugin self-dogfoods on the next test-strategy authoring task. Self-score appended to `holding/research/skill-adoption-log.jsonl` as telemetry only (not a ship gate, per codex P2). Wave plan: W2 architect, W3 deterministic-testing, W4 incremental-architect — all per `holding/research/2026-05-04-sutra-delivery-os-skills-spec.md`.

---

## v2.18.0 — 2026-05-03

**Opt-in telemetry push restored. Default OFF posture preserved.**

Founder direction: "make it on if the user said yes" (2026-05-03). The `--telemetry on` flag (added v2.9.1) persisted `telemetry_optin=true` to `.claude/sutra-project.json`, but `scripts/push.sh:19-24` had a hard gate from the v2.0 privacy reset that bailed out unconditionally unless `SUTRA_LEGACY_TELEMETRY=1`. Net effect: opt-in flag was theater — no transport regardless of consent. v2.18.0 lifts the gate and honors the opt-in.

### What changed

1. **`scripts/push.sh`** — drops the v2.0 hard gate. `SUTRA_TELEMETRY=0` short-circuits BEFORE the `telemetry_optin` check (uniform with capture path). All `python3` JSON probes (5 sites) replaced with `jq` to match `start.sh` v2.13.0 EDR-killed-python3 fix. Manifest writer (lines 77-95) replaced with atomic `jq | mktemp | mv -f` pattern. Missing jq → exit 127 with install hint. New `SUTRA_DATA_REMOTE` env override for testability and self-host paths.
2. **`scripts/_sutra_project_lib.sh:180-186`** — banner branches on 3 telemetry states: `SUTRA_TELEMETRY=0` kill-switched / opt-in ENABLED / off. Old "local-only — push disabled in v2.0 privacy model" wording removed (no longer accurate when opt-in=true).
3. **`scripts/go.sh`** — full jq migration (write + read paths). Without this, `/sutra-go` silently failed on EDR-killed-python3 hosts — toggle reported success but `telemetry_optin` stayed false.
4. **`scripts/status.sh`** — jq for sutra-project.json read, with graceful "(jq missing)" fallback. Surfaces `SUTRA_TELEMETRY=0` kill-switch state explicitly.
5. **`hooks/flush-telemetry.sh:97-107`** — jq replaces python3 OPTIN probe; `SUTRA_TELEMETRY=0` short-circuit added BEFORE the read. Non-blocking nohup/disown semantics preserved.
6. **`hooks/posttool-counter.sh`** — `SUTRA_TELEMETRY=0` early exit before any tool-name parsing or `.counters` write. Closes the kill-switch hole on the capture rail (per codex R4: PRIVACY.md amendment claims "stops both capture and push uniformly" — needed both rails to actually do that).
7. **`hooks/emit-metric.sh`** — `SUTRA_TELEMETRY=0` early exit before any metric write. Same R4 finding.
8. **`PRIVACY.md`** — version bump 2.0 → 2.18; top-of-doc amendment **explicitly supersedes** the v2.0 changelog "no outbound transmission in v2 default mode" sentence AND the "Tier-specific defaults" T1/T2 auto-consent paragraph (both stale post v2.9.1 decoupling). Discloses on opt-in: WHAT pushed (telemetry rows + manifest with `install_id`/`project_id`/`project_name_optional`/`sutra_version`/`push_count`/`first_seen`/`last_seen`), CADENCE (every Stop), DESTINATION (collaborator-visible `sankalpasawa/sutra-data` per PROTO-024 V1), KILL-SWITCH (`SUTRA_TELEMETRY=0` uniform across capture and push).
9. **`tests/integration/test-onboard-to-push.sh`** — full rewrite. Calls `push.sh` directly via `SUTRA_DATA_REMOTE` override against a local bare repo. Asserts: `--telemetry on` triggers push; `SUTRA_TELEMETRY=0` + `telemetry_optin=true` skips push with structured reason; jq absent → exit 127; `telemetry_optin=false` skips push. No python3 in test path.
10. **`.claude-plugin/plugin.json`**, **`marketplace.json`** — 2.17.0 → 2.18.0.

### Codex review (5 rounds, converged at PASS)

- **R1** CHANGES-REQUIRED: [P1] `SUTRA_TELEMETRY=0` not honored by push.sh; [P2] manifest leakage (`project_name_optional` + stable IDs) on collaborator-visible repo needs explicit disclosure; [P2] python3 fragility contradicts v2.13.0 jq migration.
- **R2** CHANGES-REQUIRED: [P1] `flush-telemetry.sh:101` also uses python3 OPTIN probe — same EDR fragility on the trigger side.
- **R3** CHANGES-REQUIRED: [P1] `scripts/go.sh` (opt-in toggle) and [P2] `scripts/status.sh` also use python3 — silent toggle failure on EDR-kill hosts.
- **R4** CHANGES-REQUIRED: [P1] If PRIVACY.md amendment claims `SUTRA_TELEMETRY=0` stops both capture and push uniformly, then `hooks/posttool-counter.sh` AND `hooks/emit-metric.sh` need early exits — otherwise the documented kill-switch is a lie.
- **R5** PASS: "13-file design closes the remaining R1-R4 defects... Proceed to edits exactly as specified."

Verdict file: `.enforcement/codex-reviews/2026-05-03-v2.18.0-opt-in-push.md` (DIRECTIVE-ID 1777800873).

### Deferred (codex-accepted, tracked separately)

- `hooks/flush-telemetry.sh:23,76` (session_id parsing + per-tool counter parsing) — same file but different domain (NOT opt-in control); deferred to keep diff surgical.
- `hooks/emit-metric.sh:43` (VERSION read with "unknown" fallback) — not opt-in path; the new SUTRA_TELEMETRY=0 guard at top of file makes the codepath unreachable when telemetry is off.
- `hooks/output-behavior-lint.sh`, `hooks/bash-summary-pretool.sh`, `hooks/posttool-counter.sh:17-18` (post-guard JSON parsing) — different domains; broader python3 sweep tracked separately.

### Threat-model honesty

This release **restores** outbound transport for opted-in users. That is a deliberate policy expansion vs v2.0's "no transport" framing. PRIVACY.md amendment makes the disclosure prominent (top-of-doc, table format) and supersedes — not silently amends — the prior contract.

---

## v2.17.0 — 2026-05-01

**Connector tools and routine project edits no longer prompt every time.**

Two coverage gaps in the existing permission system are closed:

1. **MCP connector tools** — Slack search/list/get, Apollo enrich/search, Atlassian search/get, Gmail search/list, Google Drive read/search, etc. now auto-approve on read-class verbs. Mutator/send tools (Slack send-message, Gmail create-draft, Atlassian create-issue, Drive copy-file, Calendar create-event, Apollo organization-create, HubSpot manage-crm, etc.) still prompt — by an explicit per-vendor denylist. Playwright observational tools (snapshot, screenshot, console-messages) auto-approve when their verb is in the read-list; stateful tools (click, fill-form, navigate, run-code-unsafe) still prompt.

2. **First-time Edit/Write inside cwd** — routine project edits no longer trigger a permission prompt the first time. The prompt-list still gates: secrets (`.env*`, `credentials.json`, `secrets.yaml`), repo metadata (`.git/`), publish auth (`.npmrc`, `.pypirc`), CI configs (`.github/workflows/`, `.circleci/`, `.gitlab-ci.yml`), deploy configs (`vercel.json`, `fly.toml`, `render.yaml`, `netlify.toml`), container/orchestration (`docker-compose*.yml`, `k8s/`, `helm/values*.yaml`), infrastructure-as-code (`.terraform/`, `*.tfvars`, `Pulumi.*`), Cloudflare/Railway/Firebase/GCP deploy configs, Supabase backend, and anything outside cwd.

### Why

Founder direction D44: *"for the permissions, create it as a separate ADR... auto approve them unless they are very big operations or delete... like connectors, first-time edits."* Sister to D43 (ADR-002 OUT-DIRECT 3-check, ships in v2.16.0) — same friction class (founder-side approval), different actor (harness vs model).

### What changed under the hood

- **New module** `sutra/marketplace/plugin/lib/mcp_trust_mode.py` (~190 LOC). Reads PermissionRequest payload on stdin; returns `{prompt: bool, category, reason}`. Read-verb allowlist regex + per-vendor mutator/send denylist. Anchored regex to keep drift-prone names like `get_or_create`, `read_write`, `fetch_and_delete` falling through to prompt.
- **Hook dispatch** `permission-gate.sh` extended with `_match_mcp` (calls the helper) and `_match_first_time_edit` (path-based allow + prompt-list).
- **Hook config** `hooks.json` PermissionRequest matcher widened: `Bash|Write|Edit|MultiEdit` → `Bash|Write|Edit|MultiEdit|mcp__.*`.
- **Charter** `PERMISSIONS.md` adds Tier 1.7 (MCP) and Tier 1.8 (first-time-edit). Sibling banner clarifies relationship to HUMAN-SUTRA-LAYER.md.
- **Cross-link** in `HUMAN-SUTRA-LAYER.md` § Related disciplines points to PERMISSIONS.md as a sibling charter.
- **Telemetry** `.enforcement/permission-gate.jsonl` schema extended with `tool_class` and `decision_basis` fields.

### Files

- `sutra/os/decisions/ADR-003-permissions-mcp-and-first-time-edit.md` (new)
- `sutra/os/charters/PERMISSIONS.md` (sibling banner + Tier 1.7 + Tier 1.8)
- `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (Related disciplines cross-link)
- `sutra/marketplace/plugin/lib/mcp_trust_mode.py` (new)
- `sutra/marketplace/plugin/hooks/permission-gate.sh` (extended dispatch)
- `sutra/marketplace/plugin/hooks/hooks.json` (matcher widened)
- `.claude-plugin/plugin.json`: 2.16.0 → 2.17.0
- `.claude-plugin/marketplace.json`: 2.16.0 → 2.17.0

### Architectural note (codex caught this)

The original brief modeled `REQUEST·HUMAN-APPROVE` as a Stage-3 OUT-DIRECT sub-form within H-Sutra. Codex R1 flagged this as a P1 blocker — Stage 3 owns founder-visible *model emission*, not harness permission dialogs (different actor). Fix: PERMISSIONS.md is a **sibling discipline** to HUMAN-SUTRA-LAYER.md, not a sub-form. ADR-001's 3-direction MECE invariant is preserved.

### Verification

- `lib/mcp_trust_mode.py` smoke-tested: Slack search auto-approves; Slack send-message prompts; Atlassian createJiraIssue prompts; Playwright click prompts; ambiguous names (e.g. `get_or_create`) fall through to prompt.
- Codex R1 CHANGES-REQUIRED (2 P1 architectural / 2 P2 / 2 P3) → all 6 folded → R2 ADVISORY (4 tighten-before-ship items folded into implementation directly per `[Converge and proceed]`). DIRECTIVE-ID 1777641500.

---

## v2.16.0 — 2026-05-01

**Sutra now self-executes terminal commands by default.**

Before this release, Sutra often asked you to run terminal commands yourself. After v2.16.0, Sutra runs the command itself — unless one of three things is true:

1. **The command needs a real terminal** — interactive auth like `gcloud auth login`, GUI tools, or anything that won't work in headless mode.
2. **The command is on the danger list** — force-pushes, recursive deletes outside safe paths, publishing to npm / Play Store / App Store, sending emails, money movement, or legal/compliance actions.
3. **You've explicitly marked the command class as "always ask me"** — opt-out for specific commands you want to keep approving by hand.

If any of those hit, Sutra surfaces the command normally. Otherwise it runs the command and tells you what it did.

Founder direction D43: *"when Sutra asked me to do some terminal things, for Sutra to do those things on its own."* The v1.0 H-Sutra layer already had a guardrail for over-*asking* (the OUT-QUERY 3-check from ADR-001). v2.16.0 adds the matching guardrail for over-*handoff* — the OUT-DIRECT 3-check.

### What ships

- New OUT-DIRECT sub-form `REQUEST·HUMAN-EXEC` (Sutra asking founder to run a terminal command) — joins existing `ASK·LATER` / `HANDOFF` / `CASCADE`.
- New Stage-3 OUT-DIRECT 3-check, parallel-but-different to OUT-QUERY 3-check:
  - **cant-self-exec** — interactive TTY / GUI / founder OAuth required, or no Bash path.
  - **denylist-hit** — falls in ADR-001 §4 Rule 4's 6-domain irreversible denylist verbatim (no fork).
  - **opt-out** — command class explicitly marked "always founder-runs".
- Default: NONE hit → demote to internal action (Sutra runs via own Bash) + OUT-ASSERT (INFORM). ANY hit → surface REQUEST·HUMAN-EXEC normally.
- Demotion telemetry: 3 new optional fields on the **existing** turn row in `holding/state/interaction/log.jsonl` (`out_direct_3check_hits` · `out_direct_demoted` · `original_out_form`). One-row-per-turn invariant preserved.
- 2 new fixtures (#14 demoted-good-case, #15 surfaced-denylist-case) + new regression test `tests/test-out-direct-3check.sh`. All 94 human-sutra tests green pre-commit.

### Why this is a safety floor, not behavior optimization

Codex R2 verdict (PASS, DIRECTIVE-ID 1777640243): the OUT-DIRECT 3-check is a *floor* analogous to OUT-QUERY 3-check, not a "v1.1+ behavior optimization." Both kill specific pathologies — over-asking and over-handoff — at Stage 3. Charter §v1.0 limits updated from "4 safety guardrails" → "5 safety guardrails."

### Files

- `sutra/os/decisions/ADR-002-out-direct-3check.md` (NEW — ADR text)
- `sutra/os/charters/HUMAN-SUTRA-LAYER.md` (extended — §OUT-DIRECT 3-check + new sub-form + 3 optional log fields + v1.0 limits update)
- `sutra/marketplace/plugin/skills/human-sutra/SKILL.md` (extended — §Stage-3 OUT-DIRECT discipline)
- `sutra/marketplace/plugin/skills/human-sutra/tests/fixtures.json` (+2 rows: #14, #15)
- `sutra/marketplace/plugin/skills/human-sutra/tests/test-out-direct-3check.sh` (NEW — 17 assertions)
- `holding/FOUNDER-DIRECTIONS.md` (D43 appended)
- `.claude-plugin/plugin.json`: 2.15.1 → 2.16.0
- `.enforcement/codex-reviews/2026-05-01-adr-002-r1-consult.md` (CHANGES-REQUIRED with 7 findings)
- `.enforcement/codex-reviews/2026-05-01-adr-002-r2-consult.md` (PASS — all 7 folded correctly)
- `holding/research/2026-05-01-adr-002-out-direct-3check-design-brief.md` (R1-folded, R2-PASSed)

### Codex convergence

R1 CHANGES-REQUIRED (1 P1 surface gate inconsistency between §1 and §2 / 4 P2: "symmetric" overstates · demotion telemetry must reuse turn row · PostToolUse hook is wrong layer · denylist must reuse ADR-001 verbatim / 2 P3: skip schema_version · row #10/#15 mirror cases) → all 7 folded → R2 PASS verbatim: *"No new findings. All seven R1 folds are closed from the text provided. ... CODEX-VERDICT: PASS"*. DIRECTIVE-ID 1777640243.

---

## v2.15.1 — 2026-05-01

**Systemic fix for the recurring nudge-skip pattern (founder direction "systemically fix it").**

Three preceding releases (v2.14.1 BLUEPRINT-not-showing → v2.15.0 4-discipline parity → this H-Sutra-header-not-showing) all had the same root cause: hook reminder phrased as `(skill: X)` parenthetical, which the model misread as "invoke skill X" rather than "emit text directly." When skill auto-discovery didn't fire, the block was silently skipped. v2.15.1 closes the pattern, not just the instance.

### What changed

- `sutra-defaults.json`: NEW `.per_turn_blocks.human_sutra_header` key (format + format_with_tense + format_stage_1_fail + emission_mode + emission_note + log paths + skill_reference). Closes the v2.14.1 deferred TODO.
- `hooks/per-turn-discipline-prompt.sh`: rewrote stderr emission with imperative phrasing — `MUST emit literal text` / `MUST invoke skill` instead of `(skill: X)` parenthetical. Reads new schema key for H-Sutra format. 7 numbered "MUST emit" lines for per-turn block stack + 4 "Conditionals" lines.
- Asawa CLAUDE.md (separate commit): NEW H-Sutra Header section above Input Routing; canonical-schema pointer at top of Mandatory Blocks pointing to sutra-defaults.json so future block additions update one place.

### Why imperative phrasing matters

`(skill: core:human-sutra)` was a hint the model treated as a Skill-tool invocation directive. Skill invocation requires intent-matching the user's prompt against the skill description — doesn't always fire (e.g., bare "hello"). When auto-discovery didn't fire, the model emitted nothing for that block. v2.15.1's `MUST emit as FIRST line of response — literal bracketed text, NOT a skill invocation` removes the ambiguity.

### Files

- `sutra-defaults.json`
- `hooks/per-turn-discipline-prompt.sh`
- `.claude-plugin/plugin.json`: 2.15.0 → 2.15.1
- `.claude-plugin/marketplace.json`: 2.15.0 → 2.15.1 + description preamble
- `SBOM-v2.15.1.txt`: NEW

---

## v2.15.0 — 2026-05-01

**Governance-parity bump: 4 Asawa-side disciplines ship to T4 fleet.**

Founder direction this session: "ship everything to clients." Closes 4 of the v2.14.1 audit gaps. Three ship as expanded `per-turn-discipline-prompt.sh` stderr emissions; the fourth (subagent dispatch briefing) was already shipping in v2.14.1 via `subagent-dispatch-brief.sh` PreToolUse:Task hook and is verified here.

### What ships

| # | Discipline | Mechanism |
|---|---|---|
| 1 | Skill-explain card (D40 G3) | per-turn-discipline-prompt.sh reads `.skill_explanation.template_lines` from sutra-defaults.json, emits reminder line on every UserPromptSubmit |
| 2 | Subagent dispatch briefing | subagent-dispatch-brief.sh PreToolUse:Task — already in v2.14.1; verified emitting 5-block briefing + 4-line footer |
| 3 | Readability gate (tables>prose, numbers>adjectives, ASCII boxes, no unicode boxes, progress bars) | per-turn-discipline-prompt.sh reads `.output_discipline.*` boolean keys, emits reminder line |
| 4 | Karpathy right-effort discipline (think first / simpler-alt / surgical scope / verify-loop) | NEW `.right_effort` key in sutra-defaults.json + reminder line in per-turn-discipline-prompt.sh |

### Files

- `sutra-defaults.json`: NEW `right_effort` section (4 principles + applies_before + kill_switch + lineage comment)
- `hooks/per-turn-discipline-prompt.sh`: +6 jq reads + 3 new printf lines after Codex-consult line
- `.claude-plugin/plugin.json`: 2.14.1 → 2.15.0
- `.claude-plugin/marketplace.json`: 2.14.1 → 2.15.0 + description preamble
- `SBOM-v2.15.0.txt`: NEW

### Remaining audit backlog (v2.16.x)

Capability Map (D43) classification gate, Customer Focus First, No-fabrication, Table Shape (Impact + Effort columns), PROTO-006 process discipline.

---

## v2.14.1 — 2026-05-01

**Per-turn-discipline reminder expanded to enumerate ALL 5 per-turn blocks (vinit feedback on v2.14.0).**

vinit reported on v2.14.0: "didn't show BLUEPRINT or H-Sutra layer." Diagnosis: `per-turn-discipline-prompt.sh` only nudged Input Routing + Depth+Estimation; BLUEPRINT, H-Sutra header tag, OUTPUT TRACE, and BUILD-LAYER marker had no hook reminder. On a T4 client without `CLAUDE.md` governance context, Claude had nothing telling it to emit those 3 blocks visibly. v2.14.1 closes the nudge gap.

### What changed

- `hooks/per-turn-discipline-prompt.sh`: read 8 additional jq fields from `sutra-defaults.json`, emit full 7-row block stack on stderr.
- Block stack order in the new emission: `[H-SUTRA HEADER]` → `INPUT ROUTING` → `DEPTH + ESTIMATION` → `BLUEPRINT` → `BUILD-LAYER marker` → tool calls → `OUTPUT TRACE`. Plus the existing Codex-consult-at-Depth-≥3 line.
- H-Sutra header is hardcoded in this hook; `sutra-defaults.json` doesn't have a `human_sutra` block key yet — adding it is a v2.15.0 candidate.

### Smoke test

```
$ echo '{"prompt":"v2.14.1 smoke"}' | bash hooks/per-turn-discipline-prompt.sh
[Sutra defaults · D40 v1.0.2] Per-turn block stack (emit in this order, top to bottom):
  1. [H-SUTRA HEADER]   single bracketed line, FIRST text in response   (skill: core:human-sutra)
  2. INPUT ROUTING      fields: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION
  3. DEPTH + ESTIMATION fields: TASK, DEPTH, EFFORT, COST, IMPACT
  4. BLUEPRINT          fields: Doing / Steps / Scale / Stops if / Switch
  5. BUILD-LAYER marker fields: BUILD-LAYER / ACTIVATION-SCOPE / TARGET-PATH
  6. ... tool calls (Edit / Write / Bash / Agent) ...
  7. OUTPUT TRACE       > route: <skill> > <domain> > <nodes> > <terminal>
```

### Governance-parity audit (NOT shipped, v2.15.x backlog)

These Asawa-side disciplines are NOT yet nudged on T4: skill-explain card (D40 G3), subagent dispatch contract briefing visibility, readability gate (tables/numbers/ASCII boxes), Karpathy right-effort discipline, Customer Focus First, Highlight decisions, No fabrication, Table Shape (Impact + Effort columns), PROTO-006 process discipline, Capability Map (D43) classification at-creation. Pattern is consistent: most exist as Asawa-only memory entries or `sutra-defaults.json` schema with no matching hook emission. Each is a candidate for a future bump.

---

## v2.14.0 — 2026-05-01

**H-Sutra Layer v1.0 ships to fleet (D42 visibility-before-influence) + marketplace catchup over v2.12.0 / v2.13.0 / post-v2.13.0 H-Sutra fold.**

D42 shipped H-Sutra Layer v1.0 to the dev tree earlier today (commits b88b7cc / f65725a / 192bea4 / a00cda3 / 7a32af4 / 106a94a + af84f15 fold) but the marketplace `version` field was stuck at 2.11.1 — cached plugin runtimes never received the per-turn-discipline H-Sutra block, so `holding/state/interaction/log.jsonl` went silent after 10:18Z while founder kept using sessions. This is exactly the merged≠shipping anti-pattern D43 ratified hours earlier today. v2.14.0 unsticks the pointer.

### What ships

| File | Change | Origin |
|---|---|---|
| `hooks/per-turn-discipline-prompt.sh` | +79 lines folded — invokes `skills/human-sutra/scripts/classify.sh`, derives `IR_TYPE` from prompt heuristics, appends a 9-cell + 3-tag + reversibility JSONL row to `holding/state/interaction/log.jsonl` (Asawa override) or `.sutra/h-sutra.jsonl` (default). Fail-open stderr-only; never blocks the prompt. | af84f15 |
| `skills/human-sutra/{SKILL.md, ACTIVATION.md, scripts/classify.sh, references/, tests/}` | Activated end-to-end (skill files were in 2.11.0/2.11.1 cache as scaffold, but no hook called classify.sh until the v2.14.0 fold) | D42 ship commits + post-fold |
| `scripts/_sutra_project_lib.sh` + `scripts/start.sh` + `scripts/onboard.sh` | python3 removed from bootstrap; bash/jq port with identical 4-subcommand surface and identical atomic-write contract | v2.13.0 (ac4e81c + 70893df) |
| 6 Asawa-coupled hooks (dispatcher-pretool / dispatcher-stop / architecture-awareness / +3) | EXTRACTED from plugin to `holding/hooks/` (Asawa-only L2); ~890 LoC dead weight removed from T4 fleet on-disk footprint | v2.12.0 (9f5a0a0) |
| `marketplace.json` | `version` 2.11.1 → 2.14.0 + description preamble freshened (was 3 versions stale at v2.10.1) | v2.14.0 |
| `.claude-plugin/plugin.json` | `version` 2.13.0 → 2.14.0 | v2.14.0 |
| `SBOM-v2.14.0.txt` | NEW supply-chain manifest (SHA256 per shipped file) | v2.14.0 |

### Why catchup vs three separate releases

v2.12.0 (dispatcher portability) and v2.13.0 (python3 removal) were merged to the dev tree but the `marketplace.json` pointer was never bumped past 2.11.1 — both versions were therefore phantom-shipped per D43's definition (merged but not released). v2.14.0 ships all three deltas in one marketplace pointer move with retroactive `core-v2.12.0` and `core-v2.13.0` tags so the version archaeology stays clean.

### Tags

- `core-v2.12.0` retroactive at `9f5a0a0` (dispatcher portability)
- `core-v2.13.0` retroactive at `70893df` (python3 removal)
- `core-v2.14.0` at HEAD (H-Sutra v1.0 + marketplace catchup)

### Verification

After `/plugin update` clients will see `~/.claude/plugins/cache/sutra/core/2.14.0/` materialize. The H-Sutra log starts appending from the next UserPromptSubmit. Smoke check: `tail -1 holding/state/interaction/log.jsonl` (or `~/.sutra/h-sutra.jsonl` on non-Asawa clients) should advance per turn after the update.

---

## v2.13.0 — 2026-05-01

**Remove python3 from /core:start bootstrap path entirely (vinit#38 escalation).**

v2.8.11 moved python3 from stdin-heredoc to file-form to dodge SIGKILL from macOS sandbox/EDR agents (vinit#38 first report). That fixed the heredoc class but not all of them. On 2026-05-01 user @abhishekshah reported that `python3 -c "print('hello')"` itself exits 137 on his machine — the binary is killed regardless of how it's invoked (quarantine xattr, AV process-name killer, codesign mismatch). File-form vs heredoc is irrelevant when python3 can't survive exec. v2.13.0 removes python3 from the bootstrap entirely.

### What changed

| File | Change |
|---|---|
| `scripts/_sutra_project_lib.py` | RETIRED → `archive/2026-05-01-py3-removed-from-bootstrap/`. Zero live callers after this release. |
| `scripts/_sutra_project_lib.sh` | NEW. Bash/jq port of all 4 subcommands (`patch-profile`, `write-onboard`, `stamp-identity`, `banner`). Atomic write via `mktemp` + `mv -f` (rename(2) atomic on same fs). Validates JSON before patching so empty/corrupt files surface a `rc=2` actionable error instead of silently writing a stale-shaped object. |
| `scripts/start.sh` | Upfront `jq` health gate with install hints (brew/apt/dnf/source). 2 lib calls switched from .py to .sh. `sutra_run_python` wrapper deleted (the 137 trap is moot once python3 is gone). |
| `scripts/onboard.sh` | 4 inline `python3 -c` reads (VERSION, EXISTING_OPTIN, FIRST_SEEN, EXISTING_IDENTITY) replaced with `jq -r` equivalents. 2 lib calls switched from .py to .sh. Falls back to "unknown" version when jq is unavailable so direct `/sutra-onboard` calls don't brick on legacy machines. |
| `.claude-plugin/plugin.json` | `version: 2.12.0` → `2.13.0`. |
| `archive/2026-05-01-py3-removed-from-bootstrap/README.md` | NEW. Lineage doc for the retired .py — explains why archived, replacement, and why kept rather than deleted. |

### Why this fix is durable

The previous fix attempts (heredoc → file form, atomic write, 137 diagnostic trap) all assumed python3 itself would run. That assumption breaks the moment a Mac's Endpoint Security / AV / Gatekeeper config refuses to let `python3` exec at all. jq has no equivalent process-name-based killers in the wild because it isn't a scripting interpreter that EDR vendors heuristically flag. Plus jq is a single static binary — `which jq` returning a path is a reliable proxy for "this will work."

### Sandbox acceptance

Tested with PATH symlinked from /usr/bin + /bin minus all `python3*`:

| Check | Result |
|---|---|
| `start.sh` rc | 0 |
| `.claude/sutra-project.json` valid JSON | yes |
| All 7 required fields present | yes |
| Profile patch (`--profile company`) sticks | yes |
| Telemetry flag (`--telemetry on`) patches | yes |
| `install_id` stable across re-runs | yes |
| `first_seen` preserved across re-runs | yes |
| Identity block preserved across re-onboard | yes |
| jq missing → actionable install hint, rc=127 | yes |
| Empty/corrupt JSON → rc=2 with recover instruction | yes |
| No leftover `.sutra-*.tmp` files after normal runs | yes |

### Scope discipline (Karpathy surgical-scope)

Test files (`tests/**/*.sh`) and other plugin hooks (`hooks/**/*.sh`) still call python3 in places. They're left as-is intentionally — those code paths run on developer machines with working python3, not on broken-python3 client machines. Migrating them would be churn without user-visible benefit. If a future user report shows a hook also dying with 137, we'll migrate that hook on demand. The bootstrap path is the one that bricks first-session installs, which is why it's the one that gets the python3-free guarantee.

### What clients on broken-python3 macOS need to do

1. `/core:update` to v2.13.0.
2. Confirm `which jq` returns a path (most macs already have it via Xcode CLT or Homebrew). If not: `brew install jq`.
3. `/core:start` — bootstrap completes, no python3 invoked.

If they prefer to debug the underlying python3 SIGKILL (recommended for general system health, not required for Sutra), the original diagnostic remains useful: `xattr $(which python3); codesign -dv $(which python3); log show --last 5m --predicate 'process == "python3"' --info`.

---

## v2.12.0 — 2026-05-01

**Dispatcher portability charter — extract Asawa-coupled hooks from plugin to holding/.**

Closes Tier 2 SHIPPED-DEAD findings from the plugin coverage audit (companion to issue #49). 6 plugin hooks were heavily Asawa-coupled (hardcoded portfolio company names dayflow|maze|ppr|jarvis|billu|paisa, holding/FOUNDER-DIRECTIONS.md reads, holding/checkpoints/ writes) — never wired in plugin/hooks/hooks.json (T4 fleet had ~890 lines of dead weight on disk). Extracted to `holding/hooks/` as L2 single-instance:asawa-holding files; Asawa wires from local `.claude/settings.json`. Plugin slimmer, separation cleaner.

**Codex consult 2026-05-01: CODEX-VERDICT ADVISORY** (acceptable extraction; sequence per codex P1: add holding-side first, rewire settings, verify, delete plugin copies last — atomic).

### What changed (plugin)

| File | Change |
|---|---|
| `hooks/dispatcher-pretool.sh` | DELETED (548 lines). 16 holding/ refs; hardcoded company switch cases at lines 117/488. Extracted to `holding/hooks/dispatcher-pretool.sh` with L2 marker. |
| `hooks/dispatcher-stop.sh` | DELETED (953 lines). 57 holding/ refs (FOUNDER-DIRECTIONS.md, DIRECTION-ENFORCEMENT.md, ESTIMATION-LOG.jsonl, holding/checkpoints/). Extracted to holding/. |
| `hooks/architecture-awareness.sh` | DELETED (51 lines). Echoed "check holding/SYSTEM-MAP.md" — useless on T4. Extracted to holding/. |
| `hooks/research-cadence-check.sh` | DELETED (135 lines). Scans `holding/research/` for staleness — useless on T4. Extracted to holding/. |
| `hooks/rtk-health-check.sh` | DELETED (88 lines). Writes `holding/observability/rtk-gain-log.md` — Asawa observability dir. Extracted to holding/. |
| `hooks/principle-regression.sh` | DELETED (250 lines). Asawa principle codes (P11/D6/D13). Extracted to holding/. |
| `.claude-plugin/plugin.json` | `version: 2.11.1` → `2.12.0`. |

### What this means for fleet

| User class | Behavior |
|---|---|
| T4 default (no Asawa context) | These 6 files no longer ship. Plugin is ~890 lines lighter. None of them were ever wired in plugin/hooks/hooks.json, so functional behavior is identical (zero hooks fire that didn't before). |
| Asawa T1 | Local `.claude/settings.json` updated to point `dispatcher-pretool` + `dispatcher-stop` invocations at `holding/hooks/...` paths. The other 4 hooks were called *from* the dispatchers — they continue to work because the dispatchers' relative-path calls now resolve inside `holding/hooks/`. |
| T2/T3 (owned + projects) | No effect — these clients don't wire dispatchers. |

### Validation

- `jq -e .` parses `hooks.json` — VALID (no Stop or PreToolUse references to deleted files; dispatcher-posttool wire from v2.10.2 unaffected).
- 6 dangling refs in remaining plugin hooks are all comments (`# Source: holding/hooks/dispatcher-stop.sh section 16`) — historical attribution, not exec dependencies.
- Holding-side smoke test: both `dispatcher-pretool.sh` and `dispatcher-stop.sh` run with stub stdin, exit 0.
- Asawa `.claude/settings.json` line 73 + 283 updated atomically (pre-delete, per codex P1).

### What's NOT in this release

- No fleet behavior change — these 6 hooks were never wired.
- No T4 functional gain (yet) — Tier 2 wins ship as separate batches.
- The `is_dispatcher_inlined()` check in `holding/hooks/verify-policy-coverage.sh:189` already gracefully handles missing plugin-side dispatchers via `[ -f "$d" ] || continue` — no update required.

---

## v2.11.1 — 2026-05-01

**`feedback-channel-guard.sh` false-positive fix.**

Caught during the v2.10.0/v2.10.1 release session: filing an Anthropic submission-pin update at `anthropics/claude-plugins-official` was blocked by `feedback-channel-guard.sh` because the issue body included `https://github.com/sankalpasawa/sutra/...` URLs. The hook's `SUTRA_TARGET` literal-substring check ran against `CMD_LOWER` (full command including `--body "..."`), so any body text mentioning a Sutra URL false-positive-triggered the gate — even when `--repo` explicitly targeted a different repository.

Same drift class as v2.8.8 (vinit#17), which fixed the ACTION match by switching to `CMD_HEAD` (command stripped at first quoted value) but missed the TARGET match.

### Fix

| Item | Change |
|---|---|
| `hooks/feedback-channel-guard.sh` | `CMD_HEAD` computation lifted out of the action-match block to right after `CMD_LOWER` declaration. The `SUTRA_TARGET` `*sankalpasawa/sutra*` case-match now operates on `CMD_HEAD` instead of `CMD_LOWER` — body content can no longer trigger the gate. Path B (git-remote inference inside a sutra checkout) still uses `CMD_LOWER` to detect the explicit `--repo`/`-R` flag presence (intentional — that's a structural check, not a body check). |
| `tests/unit/test-feedback-channel-guard.sh` | NEW. 9 cases covering: v2.11.1 false-positive (foreign --repo + body URL → exit 0), literal Sutra --repo (block), gh api POST against Sutra issues (block), read-only gh against Sutra (pass), non-gh (pass), bypass file (pass), bypass env var (pass), gh pr create against Sutra (block), unrelated external repo (pass). |

### Validation

- 9/9 new cases pass
- 15/15 full unit suite pass — zero regressions from v2.10.x / v2.11.0
- Real-world reproduction: `gh issue create --repo anthropics/claude-plugins-official --body "...sankalpasawa/sutra/issues/43..."` now exits 0, hook accepts.

### Threat model

Unchanged. The hook still blocks every previously-blocked Sutra-targeted write; only the false-positive path on body content is closed. Adversarial obfuscation remains explicitly out of scope per the original v2.6.2 design (single-trusted-operator threat model).

### Related drift in this release window

- v2.10.0 fixed `inbox-display.sh` packaging drift (vinit#43)
- v2.10.1 fixed `cascade-check.sh` stdout-vs-stderr drift
- v2.11.1 fixes `feedback-channel-guard.sh` matcher-scope drift (this release)

Three instances of the same hook-output / hook-matcher drift family, all closed in one day.

---

## v2.10.2 — 2026-05-01

**Plugin coverage trial: paused assistant layer removed; D32 posttool dispatcher wired; override-audit lib promoted; `output-behavior-lint` wired in Stop.**

Companion to `sutra` issue #49 (plugin self-inventory). Closes the "Tier 1 SHIPPED-BROKEN" + first slice of "Tier 2 SHIPPED-DEAD" findings from the audit. Net: **−888 lines, +296 lines, 8 files changed, 1 new lib**.

### What changed

| File | Change |
|---|---|
| `hooks/assistant-decommission.sh` | DELETED. Paused per D37; referenced `$REPO_ROOT/holding/state/...` paths absent on T4 machines (vinit#8 evidence). |
| `hooks/assistant-explain.sh` | DELETED. Same reason as above. |
| `hooks/assistant-feedback.sh` | DELETED. Same. |
| `hooks/assistant-observer.sh` | DELETED. Same. |
| `hooks/assistant-kill-switch.sh` | DELETED. Was wired in Stop, exec'd the now-deleted observer; default-off so harmless silent-exit for everyone except opted-in users running the paused layer. Removing it finishes the D37 pause cleanly. |
| `hooks/hooks.json` | (a) Unwired `assistant-kill-switch.sh` from Stop. (b) NEW: wired `dispatcher-posttool.sh` in PostToolUse (no matcher) — D32 hot-reload registry, silent-exits without `os/SUTRA-CONFIG.md` + `os/hooks/posttool-registry.jsonl`. (c) NEW: wired `output-behavior-lint.sh` in Stop — silent advisory scanning transcript for "Never ask to run" + "No HTML unless asked" violations, writes to `.enforcement/routing-misses.log` (mkdir -p safe). |
| `hooks/lib/override-audit.sh` | NEW. Promoted from `holding/hooks/lib/`. `cascade-check.sh` and `codex-review-gate.sh` source via `[ -f $REPO_ROOT/... ] || _OA_LIB="$(dirname "$0")/lib/override-audit.sh"` — the dirname fallback now resolves on user machines instead of degrading to the no-lib else-branch. |
| `.claude-plugin/plugin.json` | `version: 2.10.1` → `2.10.2`. |
| `CHANGELOG.md` | This entry. |

### Behavior matrix (fleet impact)

| Scenario | v2.10.1 | v2.10.2 |
|---|---|---|
| T4 default install (no opt-in to assistant layer) | 5 phantom assistant-* scripts on disk; kill-switch silently exits | Cleanly absent. -887 lines of disk weight removed. |
| T4 user with `~/.sutra-assistant-enabled` | kill-switch exec'd dead observer → broken | Layer fully gone; no enable surface remains. Revive via `holding/research/2026-04-24-assistant-layer-design.md` when un-paused. |
| Client with `os/SUTRA-CONFIG.md` + `os/hooks/posttool-registry.jsonl` | Custom posttool hooks would not fire (no dispatcher wired) | Hot-reload dispatcher fires registered hooks per matcher; no plugin reinstall required to add new hooks |
| Stop-event behavioral linting | Lived in `holding/hooks/dispatcher-stop.sh` only — Asawa-only | Fires on every fleet Stop; flags "please run", "could you run", `<!DOCTYPE html>` in assistant text when last user message didn't request HTML. Silent advisory; exits 0; needs python3. |
| `cascade-check.sh` / `codex-review-gate.sh` override audit | Fell through to no-lib else-branch on user machines (degraded but not broken) | Lib resolves via plugin path; full audit incl. PROTO-004 / D13 / D29 typed override rows |

### What's deferred (next phase: dispatcher portability charter)

| Item | Holding refs | Reason |
|---|---|---|
| Wire `dispatcher-pretool.sh` | 16 | HOOK_LOG path, hardcoded company switch cases dayflow/maze/ppr/jarvis/billu/paisa, holding/checkpoints/ whitelist |
| Wire `dispatcher-stop.sh` | 57 | Reads FOUNDER-DIRECTIONS.md, DIRECTION-ENFORCEMENT.md, ESTIMATION-LOG.jsonl, holding/checkpoints/ |
| Delete 4 Asawa-only hooks (architecture-awareness / research-cadence-check / rtk-health-check / principle-regression) | various | Referenced by deferred dispatchers; can't safely remove until charter resolves |
| Wire ~17 other unwired hooks | mixed | Most have ≥1 holding-coupling; triage as part of charter |

### Validation

- `jq -e .` parses `hooks.json` — VALID.
- `grep -l "assistant-{decommission,explain,feedback,observer,kill-switch}"` across `plugin/hooks/` + `hooks.json` — **0 matches**.
- `realpath dirname/lib/override-audit.sh` from inside `cascade-check.sh` — **RESOLVED**.
- Five fleet-effect scenarios in matrix above hand-checked.

### Operator notes

- No migration needed. Plugin auto-updates via marketplace pipeline.
- If you had `~/.sutra-assistant-enabled` set: now a no-op file (assistant layer gone). Safe to `rm` it.
- New `output-behavior-lint` requires `python3`; absent → hook exits 0 silently.

---

## v2.10.1 — 2026-05-01

**`cascade-check.sh` silent-block fix + tracking-artifact whitelist.**

Companion fix to v2.10.0. Same drift family as Vinit's #43 (silent hook diagnostics): `hooks/cascade-check.sh` was the *second* hook surfacing `Failed with non-blocking status code: No stderr output` — observed during the v2.10.0 release session itself. Two root causes:

1. **Diagnostics on stdout, not stderr.** Claude Code's PostToolUse protocol relays the hook's stderr when it exits non-zero. The hook printed BLOCKED, the policy reason, and the override hint to **stdout** via plain `echo` — Claude Code surfaces "No stderr output" because nothing reached stderr. Fix: the entire blocking diagnostic now routes via `{ echo ... } >&2`.
2. **Tracking artifacts triggered the gate.** Routine writes to research notes, session checkpoints, state ledgers, enforcement logs, telemetry — all CLAUDE.md-whitelisted as "no advisory, no block" — were firing the D13 cascade gate and demanding TODO follow-ups. Fix: the existing exempt list now matches the CLAUDE.md whitelist.

### What changed

| File | Change |
|---|---|
| `hooks/cascade-check.sh` | Block diagnostic moved into `{ ... } >&2` group; warning prelude moved out of the unconditional path into the block branch only (was printing on accept paths too). New exempt cases: `*/.claude/*`, `*/.enforcement/*`, `*/.analytics/*`, `*/holding/research/*`, `*/holding/state/*`, `*/holding/checkpoints/*`, `*/holding/hooks/hook-log.jsonl`, `*/sutra/archive/*`. Existing `*/TODO.md`, `*/BACKLOG.md`, `*/holding/*` (gated), `*/sutra/layer2-operating-system/*` (gated) preserved. |
| `tests/unit/test-cascade-check.sh` | NEW. 17 cases: 10 whitelist exit-0-silent paths, 4 blocked-path stderr-routing assertions, 1 CASCADE_ACK override accept, 1 missing-file_path defensive, 1 non-governance pass-through. |

### Behavior matrix

| Path class | Old | New |
|---|---|---|
| `holding/research/*`, `holding/state/*`, `holding/checkpoints/*`, `.enforcement/*`, `.analytics/*`, `.claude/*`, `sutra/archive/*` | BLOCKED unless TODO evidence found | exit 0 silently (whitelist exempt) |
| `holding/<governance>` non-research | BLOCKED — diagnostic to **stdout** (invisible to Claude Code) | BLOCKED — diagnostic to **stderr** (Claude Code surfaces it) |
| `holding/<governance>` with `CASCADE_ACK=1` | exit 0, message on stdout | exit 0, message on stdout (unchanged — accept paths) |
| `holding/<governance>` with TODO evidence in diff | exit 0, message on stdout | exit 0, message on stdout (unchanged — accept paths) |
| Anything outside the gated prefixes | exit 0 silently | exit 0 silently (unchanged) |

### Validation

- 14/14 unit tests pass (no regressions from v2.10.0)
- Reproduction (pre-fix): `printf '{"tool_input":{"file_path":"/foo/holding/SYSTEM-MAP.md"}}' | bash hooks/cascade-check.sh` → exit 2, stdout has 13-line diagnostic, stderr empty
- Reproduction (post-fix): same input → exit 2, stdout empty, stderr has 13-line diagnostic
- Reproduction (research path, post-fix): `/foo/holding/research/test.md` → exit 0, stdout + stderr both empty

### Why ship as v2.10.1, not fold into v2.10.0

v2.10.0 already has a tag, GitHub release, and pushed pin. Folding the cascade-check fix into v2.10.0 would mean force-bumping a published tag — disallowed. v2.10.1 is the clean increment.

### What did NOT change

- Threat model: unchanged. The D13 enforcement still HARD-blocks governance changes without TODO evidence; only the diagnostic routing + whitelist scope changed.
- API/skill/command surface: unchanged.
- Telemetry behavior: unchanged.

---

## v2.10.0 — 2026-05-01

**Inbox display ships + release packaging guard.**

Closes [issue #43](https://github.com/sankalpasawa/sutra/issues/43) (vinit, Testlify) — every `SessionStart:resume` printed `inbox-display.sh: No such file or directory` because `hooks/hooks.json` declared the hook but the script was never `git add`'d. Working tree had it; the published plugin tarball did not. Same drift class as the v2.7.1 description-vs-code incident.

### Fixes

| Item | Change |
|---|---|
| `hooks/inbox-display.sh` | Now tracked in git (was working-tree-only). FEEDBACK charter §N Close-Loop Layer V0 hook — soft-fails on every error path, two kill-switches (`SUTRA_INBOX_DISABLED=1`, `~/.sutra-inbox-disabled`). |
| `scripts/validate-hook-paths.sh` | NEW. Pre-release CI guard. Reads `hooks.json`, expands every `${CLAUDE_PLUGIN_ROOT}` command path, confirms each exists on disk AND is git-tracked. Exits non-zero with the offender list when a path is missing or untracked. |
| `tests/unit/test-validate-hook-paths.sh` | NEW. 4 cases — green plugin tree / referenced-missing-file / non-git-tree pass-with-note / empty hooks.json defensive fail. Picked up by `run-all.sh`. |

### Why this matters

Two prior releases (v2.8.5, v2.9.1) shipped the same bug because the description, the manifest, and the source tree were merged independently with no gate that all three agree. Going forward:

- Every release commit must run `scripts/validate-hook-paths.sh` and exit 0.
- `tests/run-all.sh` runs the validator's unit test, so any reviewer running tests sees the regression class is covered.

### What did NOT change

- No threat-model change.
- No API/skill/command surface change.
- No telemetry behavior change (v2.9.1 contract preserved).

### Affected versions of bug

| Version | hooks.json refs `inbox-display.sh`? | File shipped in tarball? | User-visible? |
|---|---|---|---|
| ≤ v2.7.3 | No | n/a | No |
| v2.8.5 | Yes | No | **Yes — STDERR banner on every resume** |
| v2.8.11 | Yes | No | **Yes** |
| v2.9.1 | Yes | No | **Yes** |
| **v2.10.0** | Yes | **Yes** | **No (fixed)** |

### How to update

```
/core:update
```

Or:

```
claude plugin marketplace update sutra && claude plugin update core@sutra
```

### Codex review

Validator + unit test packet self-reviewed against `validate-hook-paths.sh` v1 spec; verdict logged at `.enforcement/codex-reviews/2026-05-01-v2-10-0-release.md` if codex is reachable from the founder's session.

---

## v2.9.1 — 2026-04-30

**Telemetry: explicit opt-in during install (founder direction).**

Founder direction (2026-04-30): "when installing Sutra, give an option to switch on the telemetry — do this for the plugin." Currently `/core:start` runs onboarding silently — the user has no visible say in whether telemetry is on. v2.9.1 makes it an **explicit interactive choice** at first install.

### Behavior change

- `/core:start` now asks the user **before** running onboard:
  > "Do you want to enable Sutra telemetry to help improve the plugin? (default: no)"
- If user says **yes** → invokes onboard with `--telemetry on`
- If user says **no** (or default) → invokes onboard with `--telemetry off`
- Idempotent: skip prompt if `.claude/sutra-project.json` already exists (preserve existing setting)

### Precedence (codex review verdict ADVISORY → fold)

```
CLI flag (--telemetry on|off) > existing .claude/sutra-project.json > default OFF
```

### What changed

| File | Change |
|---|---|
| `commands/start.md` | Frontmatter description fixed (no longer claims "enables local telemetry"); body adds preflight instruction telling Claude to ASK before running; body item 2 fixed (was "telemetry_optin = true" — wrong since v2.0; now "opt-in only; default OFF"); body item 5 clarifies queue is used only if opt-in. |
| `scripts/start.sh` | New `--telemetry on\|off` CLI flag parsing. Profile-based telemetry default REMOVED (decoupled — profile governs governance enforcement only, not telemetry). New default = OFF (matches PRIVACY.md v2.0 contract; previously project/company profiles silently auto-opted-in). |

### Why default OFF (not profile-based)

Per codex consult on this design: "Keep default no. That matches PRIVACY.md v2.0 and onboard.sh's current default-false behavior. 'Ask explicitly with no default-yes' is the safest phrasing." The previous profile-based auto-opt-in for project/company silently contradicted PRIVACY.md and bypassed user consent. v2.9.1 fixes the contract gap.

### Backwards compatibility

- **Existing installs**: unchanged — `onboard.sh` preserves whatever `telemetry_optin` was already in `.claude/sutra-project.json`. No silent flip.
- **New installs of `individual` profile**: was OFF; still OFF.
- **New installs of `project`/`company` profile**: was silently ON; **now OFF unless user explicitly says yes**. Behavior change.
- **Non-interactive callers** (CI, scripts): use `--telemetry on` to get the prior default-on behavior; otherwise default OFF.

### How to flip later

- Edit `.claude/sutra-project.json` directly (`telemetry_optin: true|false`)
- Or re-run `/core:start --telemetry on` (or `off`)
- `/core:status` shows current setting

---

## v2.9.0 — 2026-04-30

**D40 governance parity — every Sutra plugin client inherits Asawa's per-turn discipline by default.**

Founder direction D40 (2026-04-30): the rich governance Asawa uses internally (Input Routing, Depth + Estimation, BLUEPRINT, codex consult before Edit/Write at Depth ≥ 3, 4-line skill cards, subagent dispatch contracts) was previously locked behind ~30 personal memories that don't ship with the plugin. Clients got skills + hooks but missed the convention layer that makes the discipline actually fire. v2.9.0 closes that gap.

### What's NEW for clients

| Surface | What you get |
|---|---|
| **Single canonical policy surface** | New `sutra-defaults.json` — machine-readable policy schema consumed by hooks at runtime via `jq`. `SUTRA-DEFAULTS.md` is the human-readable equivalent. ALL governance defaults documented in one place. |
| **Per-turn discipline reminder** | New `UserPromptSubmit` hook (`per-turn-discipline-prompt.sh`) reminds the model on every turn — including pure-question turns — to emit Input Routing + Depth blocks. Reads policy from json (no hardcoded reminder text). |
| **Codex-before-Edit policy** | `core:codex-sutra` skill now declares default policy: consult before Edit/Write/MultiEdit at Depth ≥ 3. Per `[Codex consult on everything]` discipline. |
| **4-line skill cards** | New `core:skill-explain` skill — emits 4-line WHAT/WHY/EXPECT/ASKS card before any Skill invocation so non-technical users can predict the experience. |
| **Subagent dispatch contract** | New `PreToolUse` hook on `Task` tool (`subagent-dispatch-brief.sh`) reminds Claude to brief subagent prompts with the 5-block §Sutra discipline + 4-line footer (TRIAGE/ESTIMATE/ACTUAL/OS TRACE). |
| **/core:workflow** | New slash command + skill — pedagogical wrapper that walks Claude through the full canonical Sutra discipline (8-step sequence) on a single task. Use for onboarding, pedagogy, reset, or audit. |
| **/core:start polish** | Honest inventory: 8 skills + 10 commands + 51 hooks across 6 events. Quick-start example included. References SUTRA-DEFAULTS.md for the full convention pack. |
| **5-turn acceptance harness** | New `tests/governance-parity-acceptance.sh` — `--verify <log>` checks a fresh-client session for the 5 governance behaviors using multi-line regex (perl -0777), absence assertions, and temporal ordering. Codex-reviewed 3 rounds. |

### How to update

```
/core:update
```

Or manually:
```
claude plugin marketplace update sutra && claude plugin update core@sutra
```

### Try the new surface

After update:
1. `/core:start` — see the polished onboarding with full inventory
2. `/core:workflow plan a small refactor` — see the full 8-step Sutra discipline applied
3. Run any task — observe the per-turn discipline reminder + the codex-consult policy at Depth ≥ 3

### Caveats (codex-flagged, preserved)

Hook injections of prompt text are **soft guidance only** — fragility class includes prompt dilution, prompt collision, token bloat, cosmetic emission, and subagent drift. Skills/docs EXPLAIN; hooks ENFORCE. Where a deterministic check exists, it backs the soft hint. Where it doesn't (e.g., 4-line skill cards — Claude Code lacks PreSkillUse), the convention relies on the model emitting it.

### Codex review trail

DIRECTIVE 1777505000 — D40 implementation review:
- Round 1: CHANGES-REQUIRED → v1.0.1 fold (G6 real json consumption + G7 multiline regex + kill_switches comprehensive)
- Round 2: CHANGES-REQUIRED → v1.0.2/1.0.3 fold (Q3 MultiEdit + Q1 regex tightening + Q5 contract alignment + version drift)
- Round 3: ADVISORY → gate cleared

DIRECTIVE 1777510000 — start polish + workflow skill:
- Consult: ADVISORY → renamed core:do→core:workflow + sutra-learn classification fix
- Review #1: CHANGES-REQUIRED → count drift fold (Skills 7→8, Commands 9→10, workflow.md created)
- Review #2: PASS → counts match filesystem

### Files shipped

8 new + 3 modified across plugin/:
- NEW: `SUTRA-DEFAULTS.md`, `sutra-defaults.json`, `hooks/per-turn-discipline-prompt.sh`, `hooks/subagent-dispatch-brief.sh`, `skills/skill-explain/SKILL.md`, `skills/workflow/SKILL.md`, `commands/workflow.md`, `tests/governance-parity-acceptance.sh`
- MODIFIED: `hooks/hooks.json` (registered 2 new hooks), `skills/codex-sutra/SKILL.md` (consult-before-Edit policy), `commands/start.md` (rewrite — honest inventory)

### Deferred to v2.x.y

- **G6 finalization** — rewire ALL existing Core hooks to consume `sutra-defaults.json` (currently only the 2 NEW hooks consume it; ~50 existing hooks still hardcode policies)
- **Q5 log segmentation** by tool_use boundary (full hook-vs-model provenance proof in the acceptance harness)

---

## v2.8.11 — 2026-04-28

**Vinit#38 — `/core:start` SIGKILLed by macOS sandbox/EDR on stdin-fed `python3` heredocs (P0 — bricks new-client onboarding).**

@vinitharmalkar reported (#38) on behalf of @abhishekshah that `/core:start` exits 137 (SIGKILL) on a v2.8.10 macOS install. Two `python3` subprocesses fed code via stdin heredoc (`python3 - <<'PY' ... PY`) are killed mid-execution by signal 9; bash code paths in the same script complete normally. Result: 0-byte `.claude/sutra-project.json`, partial governance block in `.claude/CLAUDE.md`, bricked onboarding.

The kill is external — likely a macOS Endpoint Detection agent (Crowdstrike, SentinelOne, Jamf MDM, Apple Endpoint Security framework, Gatekeeper) flagging stdin-fed `python3` as suspicious. Vinit's own v2.8.5 Mac on the same plugin pattern works fine, confirming this is an environment-specific kill — not a universal Sutra bug — but enough macOS setups have one of these agents that we need to defend.

### Fix (Vinit's recommendations A + B + C)

**A. File-execution form replaces stdin-fed heredocs.** All `python3 - <<'PY' ... PY` heredocs in `start.sh` and `onboard.sh` (4 total) moved into a real `.py` file: `scripts/_sutra_project_lib.py` with subcommands `patch-profile`, `write-onboard`, `stamp-identity`, `banner`. The file form is much less likely to be flagged by sandbox/EDR than stdin-fed code.

**B. SIGKILL diagnostic.** New `sutra_run_python` wrapper in `start.sh` detects exit 137 and prints a clear, actionable diagnostic — what to check (`ps -ef | grep crowdstrike/jamf/sentinel`, `codesign -d $(which python3)`), where to report, and confirmation that the user's `sutra-project.json` is not corrupted (because of fix C).

**C. Atomic writes.** All file mutations in the new helper use `tempfile + os.replace`. A SIGKILL between the temp-file create and the rename leaves the prior valid file content untouched — no more 0-byte corruption. Applies to both initial onboard write and subsequent patch.

### What changed

| File | Change |
|---|---|
| `scripts/_sutra_project_lib.py` | NEW — 4 subcommands replacing all stdin-fed python3 heredocs in start/onboard |
| `scripts/start.sh` | Heredoc 1 (line 114) + heredoc 2 (line 258) → file-form helper calls; new `sutra_run_python` wrapper with SIGKILL diagnostic |
| `scripts/onboard.sh` | Heredoc 1 (line 57, main onboard write) + heredoc 2 (line 88, identity stamp) → file-form helper calls |

### Acceptance

- `bash -n` clean on both modified shell scripts.
- `python3 -m py_compile` clean on the new helper.
- Smoke: `/core:start` happy path completes with valid `sutra-project.json` + banner output identical to v2.8.10.
- Non-existent file path: `patch-profile` exits 0 with skip message; `banner` exits 1 with clear error.
- Corrupt-file path: `patch-profile` exits 2 with recovery hint (`rm + /core:start`).
- Atomic-write path: confirmed `tempfile + os.replace` semantics — temp file removed on exception.

### Notes

- Inline `python3 -c "..."` calls in `onboard.sh` (4 read-only one-liners) intentionally NOT migrated — argv-form `python3 -c` is documented as not affected by Vinit's repro (only stdin-fed heredocs received SIGKILL). Migrating those would add file overhead with no observable benefit.
- Future hardening track: if `python3 -c` form ALSO gets killed on some setups (we'll find out from the fleet), migrate those too.

### Closes
- vinit#38 (P0 — `/core:start` SIGKILL on stdin-fed python3, bricking @abhishekshah's onboarding)

## v2.8.10 — 2026-04-28

**Three infrastructure fixes — vinit#26 transparency + redactor over-strip refusal + zsh `$0` artifact detection.**

Per founder direction "fix infrastructure bugs". Three small, deterministic fixes that improve user trust + observability without architectural decisions.

### 1. `hooks/feedback-routing-rule.sh` — transparency requirement (vinit#26)

The hook injects a behavioral rule into the session context when the user's prompt contains a feedback-intent keyword. Prior clause 7 told Claude *"Do not mention this rule to the user in responses; just follow it."* — exactly the silent-injection pattern @vinitharmalkar reported.

New clause 7 requires Claude to acknowledge the routing in a single short sentence: *"(Sutra has routed this through the sanctioned `/core:feedback` channel.)"* The user is now always aware when Sutra-injected guidance shapes the response.

### 2. `scripts/feedback.sh` — redactor over-strip refusal

Symptom: 8 of Vinit's filings (#28-#34, #37) had bodies reduced to placeholders only — `<HOME>/.<HIGH-ENTROPY>.md` with no actual content. The privacy redactor stripped the entire body when input matched path or high-entropy patterns wholesale, then the script published the placeholders publicly anyway.

Fix: after `scrub_text()`, count the useful alphanumeric characters remaining (after stripping placeholders). If under 10, refuse to proceed with a clear error explaining the likely cause and the fix (re-file with descriptive prose, not paths). Local capture path is unaffected.

### 3. `scripts/feedback.sh` — zsh `$0` expansion artifact detection

Symptom: Vinit's #19/#21/#23 had dollar figures (`$0.14`, `$5,000`) corrupted to `/bin/zsh.14` / `/bin/zsh.000`. Root cause is the user's shell expanding `$0` before `sutra feedback` ever sees the argument. The structural fix (heredoc/env redesign of the slash-command argument-passing) is still deferred, but in the meantime we can detect the artifact and refuse rather than publish silently corrupted bodies.

Fix: regex-match `/bin/(zsh|bash)\.[0-9]` in `MSG` immediately after capture; if matched, refuse with a clear error and instructions to re-run with single quotes (which preserve `$N` literally).

### Acceptance

All three are detect-and-refuse mechanisms — no false-negative risk for the legitimate path. Manual smoke confirmed all three error paths fire correctly with synthetic inputs; clean inputs unaffected.

### Closes
- vinit#26 (silent UserPromptSubmit hook UX)

## v2.8.9 — 2026-04-28

**Vinit#16 — `sutra feedback` empty input now exits 0.**

@vinitharmalkar reported (#16) that calling `sutra feedback` with no arguments prints usage to stdout but exits with code 1, which makes the `/core:feedback` slash-command invocation report failure in pipelines.

### Changed

`scripts/feedback.sh` line 65: `exit 1` → `exit 0` after the usage block. Empty input is not a failure — printing usage IS the action when no args are provided. Equivalent to most `git`/`gh` subcommand conventions where `--help` exits 0.

## v2.8.8 — 2026-04-28

**Vinit#17 second encounter — `feedback-channel-guard.sh` body-content false-positive (re-fix).**

Discovered while attempting to close vinit#36 with a comment that mentioned "gh issue create" as a concept (referring to the threat model). The shipped guard's regex `gh +issue +(create|comment)` matched the substring inside `--comment "..."` body text — same class of bug @vinitharmalkar reported in #17, which I'd previously assessed as fixed. The earlier "fix" addressed the threat-model framing but not the regex's command-vs-body discrimination.

### Root cause

`feedback-channel-guard.sh` `grep`'d the entire command line for action verbs. Any flag value (`--comment "..."`, `--body "..."`) containing the literal text `gh issue create` or `gh issue comment` triggered a false-positive block — even on legitimate operations like `gh issue close --comment "..."`.

### Fix

Replaced whole-command `grep` with explicit token parsing:

1. Strip everything after the first quoted value (`sed -E "s/[[:space:]]['\"].*$//"`) — flag bodies cannot influence the action match.
2. Read remaining tokens; locate `gh` position; extract the next two tokens (noun + verb).
3. Match against `(noun, verb)` tuples directly: `(issue, create)`, `(issue, comment)`, `(pr, create)`, `(pr, comment)`, `(pr, review)`.
4. `gh api` mutation detection unchanged (its parameters always live unquoted on the line, so whole-string scan is acceptable).

### Acceptance — 8/8 tests pass

| Test | Expected | Result |
|---|---|---|
| `gh issue close 36 ... --comment "guard blocks unsanctioned gh issue create paths"` | pass (false-positive case) | ✅ pass |
| `gh issue create -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue comment -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue close -R sankalpasawa/sutra --comment "..."` (simple) | pass | ✅ pass |
| `gh issue create -R someother/repo ...` | pass | ✅ pass |
| `gh api -X POST /repos/sankalpasawa/sutra/issues ...` | block | ✅ block |
| `gh pr create -R sankalpasawa/sutra ...` | block | ✅ block |
| `gh issue close ... --comment "...gh issue comment was matched..."` | pass | ✅ pass |

### Why this matters

The original false-positive @vinitharmalkar reported in #17 was discovered when the guard blocked legitimate `sutra feedback --public` invocations whose feedback-text body contained the repo name. The threat-model fix in v2.6.2 addressed that specific path (the sanctioned binary) but left this broader class of false-positive in place. Confirmed in the wild today (2026-04-28) when an attempt to close #36 with a descriptive comment was blocked.

## v2.8.7 — 2026-04-28

**Vinit#36 — slash-command zsh history-expansion fix (8 command files).**

@vinitharmalkar reported (issue #36, 2026-04-28) that `/core:start` fails with exit 127 on zsh: the `!`-prefix line in the slash-command file (`!${CLAUDE_PLUGIN_ROOT}/bin/sutra start`) reaches zsh's `eval`, where the leading `!` triggers history expansion (`(eval):1: no such file or directory: !/path/to/sutra`). The `!`-prefix syntax is **not the documented Claude Code slash-command auto-execute mechanism**; the canonical form is a fenced bash code block that Claude reads and executes via the Bash tool. Confirmed via Claude Code documentation lookup.

### Changed

All 8 affected command files migrated from broken `!`-prefix form to documented fenced-bash form:

| File | Subcmd |
|---|---|
| `commands/start.md` | `sutra start` |
| `commands/feedback.md` | `sutra feedback "$ARGUMENTS"` |
| `commands/learn.md` | `sutra learn $ARGUMENTS` |
| `commands/permissions.md` | `sutra permissions` |
| `commands/sbom.md` | `sutra sbom` |
| `commands/status.md` | `sutra status` |
| `commands/uninstall.md` | `sutra uninstall $ARGUMENTS` |
| `commands/update.md` | `sutra update` |

Pattern (before/after):

```diff
- !${CLAUDE_PLUGIN_ROOT}/bin/sutra start
+ Run this command via the Bash tool:
+
+ ```bash
+ ${CLAUDE_PLUGIN_ROOT}/bin/sutra start
+ ```
```

### Why the new form works

The fenced-bash block is read by Claude (the model), which then emits a `Bash` tool call. Claude Code's Bash tool runs the command in a controlled bash environment — it does NOT pass through the user's interactive zsh, so `!` history expansion never triggers. This works identically across bash, zsh, fish, and any other user shell.

### Acceptance

- `grep -rn "^!" commands/` returns zero matches.
- All 8 files contain a `\`\`\`bash` fenced block with the prior invocation.
- Plugin smoke unaffected (slash-command files are pre-Claude-rendered, no syntax to break at install time).

### Not addressed in this version

- The zsh `$0`/`$N` expansion bug in `sutra feedback --public` body (separate issue, deferred to a future round; rooted in `$ARGUMENTS` substitution semantics, not the `!`-prefix). Tracked in v2.8.6 changelog "Not addressed" section.

## v2.8.6 — 2026-04-28

**Vinit feedback round — two deterministic fixes (`vinit#25` bug 2 + `vinit#35`).**

Round of marketplace-feedback closures from @vinitharmalkar's reports filed 2026-04-28. Two bugs that had clear specs and surgical fixes are addressed here; non-deterministic issues (#8 plugin/holding L1 layering, #26 hook-transparency UX, zsh `$0` expansion at command-substitution boundary) deferred pending design decisions.

### Fixed

- **`scripts/feedback.sh` — derive GitHub issue title from first content line** (vinit#25 bug 2). Prior behavior: every `sutra feedback --public` invocation produced an issue titled `[feedback v${PLUGIN_VERSION}] from plugin`, regardless of body — making the inbox untriageable (16+ identical titles in #16-#34). New behavior: title is `[v${PLUGIN_VERSION}] <first non-blank, non-frontmatter, non-redacted content line, capped at 80 chars>`. Falls back to the legacy generic format only when the body has no usable line. Awk-based extraction (single-pass, bash-3.2-safe). Version prefix retained for filterability. Tested with 6 cases (Bug:/Feature: prefixes, leading blanks, frontmatter separators, fully-redacted bodies, long lines, empty input).

- **`scripts/start.sh` — accept `.claude/` directory as a valid project marker** (vinit#35). Prior behavior: `/core:start` refused to activate in directories that contain `.claude/settings.local.json` or `.claude/heartbeats` but lack `.git/`/`package.json`/`pyproject.toml`/`Cargo.toml`/`go.mod`/`CLAUDE.md`, requiring users to discover `--force`. New behavior: `.claude/` directory presence is sufficient to identify a Claude Code project. Marker list in error message updated to surface `.claude/`. Existing protections (HOME-dir refusal, `/`/`/tmp` refusal, canonical-path symlink-resolution) preserved. Smoke-tested: a tempdir with only `.claude/settings.local.json` is now accepted.

### Not addressed in this version (deferred)

- **vinit#8** (Assistant Interaction Layer ships as L1 in marketplace plugin; observer not registered in hooks.json; `holding/` paths missing on user machines) — requires architectural decision: promote observer to L0 + register, or strip the `sutra explain/ask/answer/pending` subcommands from `bin/sutra`. Tracked separately.
- **vinit#26** (feedback-routing-rule hook silently injected via UserPromptSubmit; user has no UI surface) — requires UX design for transparency surfacing.
- **zsh `$0` expansion bug** (dollar amounts like `$0.14` corrupted to `/bin/zsh.14` in published feedback bodies) — root cause is at the Claude-Code `$ARGUMENTS` text-substitution boundary in `commands/feedback.md`; fix requires moving body delivery to a quoted heredoc / env-passing path with split flag parsing in `feedback.sh`. Tracked separately.

### Acceptance

- `bash -n scripts/feedback.sh` and `bash -n scripts/start.sh` clean.
- 6/6 title-derivation cases pass under bash 3.2 (macOS default).
- `.claude/`-only tempdir accepted by the marker-check; HOME-dir / `/tmp` refusals preserved.

## v2.8.5 — 2026-04-28

**D38 Wave 9 — Bucket C activation: 10 promoted hooks now registered in plugin hooks.json (fleet-wide auto-fire).**

Per founder direction "finish it off as well", 10 of the 28 Bucket C hooks promoted in v2.8.4 are now activation-wired in plugin hooks.json — they fire fleet-wide automatically on /core:update, not just for Asawa via settings.json pointer.

### Hooks activated

- **SessionStart**: session-start-rotate
- **PreToolUse Edit|Write**: blueprint-check
- **PreToolUse Write|Edit|MultiEdit**: self-assess-before-foundational, input-classification-gate
- **PostToolUse Edit|Write**: process-fix-check
- **PostToolUse Bash|Edit|Write**: agent-completion-check (new matcher)
- **PostToolUse Write**: onboarding-self-check, narration-not-artifact (new matcher)
- **Stop**: policy-only-sensor, context-budget-check

### Hooks NOT activated (canonical-only, no auto-fire)

- **auto-push** — Stop hook would auto-push every session for every fleet client; deferred pending per-client config (T2/T3/T4 may not want auto-push).
- 17 other Bucket C hooks (architecture-awareness, check-graduation, hook-health-sensor, kpi-tracker, latency-collector, lifecycle-check, new-path-detector, output-behavior-lint, principle-regression, research-cadence-check, rotate-logs, rtk-health-check, session-checkpoint, test-in-production-check, time-allocation-tracker, triage-collector, tripwire-hook-sizes) — not currently invoked from holding/.claude/settings.json; canonical files exist in plugin/hooks/ for any future activation. Per-hook event-matcher analysis required for each; no need to auto-activate vestigial hooks.

### Acceptance

After /core:update, fleet clients running Sutra v2.8.5 get blueprint-check, self-assess, input-classification, process-fix, agent-completion, onboarding-self-check, narration-not-artifact, policy-only-sensor, context-budget-check, session-start-rotate firing automatically — no settings.json customization required. D38's "canonical = distributed + activation-wired + released" criterion is now met for these 10.

### Wave plan — D38 COMPLETE

This is the last D38 wave. Remaining items deferred-by-design:
- 17 vestigial Bucket C canonicals: live in plugin/hooks/ but no auto-fire registration. Future wave can activate per-hook on demand.
- Bucket D L2 in-file headers: cosmetic; promotion ledger already documents WHY_NOT_L0_KIND for each.
- Wave-3 shim deletion (pre-commit-test-gate, mark-tests-ran in holding/hooks/): safe to keep until callers all updated; revisit at 2026-05-05 retire-by.

## v2.8.4 — 2026-04-28

**D38 Waves 6+7 — Bucket C bulk promotion (28 governance hooks → plugin canonical).**

Per founder direction "finish all the rest of the things" + D38 §Acceptance ("documented disposition within 14 days, target 2026-05-12"), 28 Bucket C governance hooks moved from holding/hooks/ to sutra/marketplace/plugin/hooks/. Plugin is now the canonical home for them.

### Hooks promoted (28)

agent-completion-check, architecture-awareness, auto-push, blueprint-check, check-graduation, context-budget-check, hook-health-sensor, input-classification-gate, kpi-tracker, latency-collector, lifecycle-check, narration-not-artifact, new-path-detector, onboarding-self-check, output-behavior-lint, policy-only-sensor, principle-regression, process-fix-check, research-cadence-check, rotate-logs, rtk-health-check, self-assess-before-foundational, session-checkpoint, session-start-rotate, test-in-production-check, time-allocation-tracker, triage-collector, tripwire-hook-sizes.

### What does NOT change in this version

- These hooks are NOT yet registered in plugin hooks.json (each requires per-hook event-matcher analysis — deferred to a follow-up wave). Marketplace consumers see canonical files in plugin/hooks/ but no automatic activation. Holding-side consumers (Asawa) continue to invoke them via existing settings.json (paths updated in companion holding commit to point at plugin canonicals).
- Asawa-specific hooks (Bucket D — high holding/Asawa references) stay at holding/hooks/ with `WHY_NOT_L0_KIND=instance-only` headers (separate commit).

### What's still pending

- Wave 8 (companion holding commit): update holding/.claude/settings.json to point at plugin canonicals + delete holding/hooks/ shims and Bucket C originals.
- Wave 9 (future): per-hook plugin hooks.json registration so promoted Bucket C hooks fire fleet-wide automatically.

## v2.8.3 — 2026-04-28

**D38 Wave 3 — `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).**

Per codex amendment (DIRECTIVE-ID 1777362899), git/runtime universal hooks live at `sutra/hooks/` (parallel L0 surface to `marketplace/plugin/hooks/`). These are NOT Claude Code marketplace hooks — they're git pre-commit hooks invoked from `.git/hooks/pre-commit` wrapper. Promoting them to `sutra/hooks/` makes them canonical for Sutra-tree dev workflows.

### What changed

- `sutra/hooks/pre-commit-test-gate.sh` — synced from holding's latest. Existing file (since 6b088db); now D38-aware.
- `sutra/hooks/mark-tests-ran.sh` — synced from holding's latest. Existing file; now paired explicitly with the test-gate per codex's "treat as one mechanism" recommendation.

### Note on this version bump

This is an infrastructure update — not a marketplace plugin feature. The bumped version is for visibility in the v2.8.x sequence; consumers on `/core:update` see no behavior change in plugin hooks (the shared-runtime hooks live in the Sutra source tree, not in the marketplace plugin path).

### Wave plan continuation

- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete.

## v2.8.2 — 2026-04-28

**D38 Wave 2 — `structural-move-check.sh` (PROTO-025) plugin L0 promotion.**

PROTO-025 enforcement (unauthorized rm/mv/git mv on HARD paths — closes the 2026-04-06 evolution-archive incident) moves from `holding/hooks/` (Asawa-only) to `sutra/marketplace/plugin/hooks/` (fleet L0). Same atomic-cutover pattern as Wave 1.

### What changed

- `hooks/structural-move-check.sh` — new in plugin (211 lines). Gates Bash structural ops (`mv`, `rm`, `git mv`, `git rm`, `find -delete`, `bash -c` containing destructive shell) on the same HARD path list as `build-layer-check.sh` (PROTO-021 + D38). Same marker schema; same override path; same audit ledger.
- `hooks/hooks.json` — registers `structural-move-check.sh` on PreToolUse `Bash`.
- Plugin version 2.8.1 → 2.8.2.

### Wave plan continuation

- Wave 3: `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).
- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete.

## v2.8.1 — 2026-04-28

**D38 Wave 1 — `build-layer-check.sh` plugin L0 promotion (HARD enforcement now fleet-distributed).**

Per D38 (`holding/FOUNDER-DIRECTIONS.md` §D38) and codex consult DIRECTIVE-ID 1777362899, the `build-layer-check.sh` HARD-enforcement hook moves from `holding/hooks/` (Asawa-only) to `sutra/marketplace/plugin/hooks/` (fleet L0). The hook implements PROTO-021 + D38 with structured marker schema + plugin-first decision logic.

### What changed

- `hooks/build-layer-check.sh` — new in plugin (385 lines). Five path categories (D38_PLUGIN_RUNTIME, D38_SHARED_RUNTIME, D38_HOLDING_IMPL, LEGACY_HARD, SOFT). Codex's exact decision logic. Override audit emits `path` + `actor` + `cmd` + `reason` + `ts` + `session_id` + `declared_layer` + `override_kind`. Backward compat: LEGACY_HARD paths accept old single-line marker.
- `hooks/hooks.json` — registers `build-layer-check.sh` on PreToolUse `Write|Edit|MultiEdit`.
- Holding copy at `holding/hooks/build-layer-check.sh` (Asawa repo) becomes a 4-line shim per D38 §5 mirror retirement rule (canonical = plugin; retire-by 2026-05-05).

### Impact

Every fleet-installed Sutra plugin gets D38 HARD enforcement on next `/core:update`. Plugin-runtime files require `LAYER=L0`; holding-implementation paths require structured L1/L2 justification. Phantom-feature class becomes structurally impossible across the fleet — not just at Asawa.

### What does NOT change

- LEGACY_HARD paths (`holding/departments/**`, `holding/evolution/**`, `holding/FOUNDER-DIRECTIONS.md`, `sutra/os/charters/**`) keep PROTO-021 original semantics: marker present (any content) = pass. Backward compat preserved for clients on older marker schemas.
- Override path (`BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<reason>'`) unchanged in API; logging schema enriched.

### Codex review

Verdict files: `.enforcement/codex-reviews/d38-codex-consult-1777362899.md` (Pass 1 ADVISORY) + `d38-codex-impl-review-1777362899.md` (Pass 2 ADVISORY). Two structural refinements absorbed (canonical = distributed + activated + released; sutra/hooks/ carve-out for shared runtime; marker schema upgrade). Two implementation findings absorbed (override JSON `path` field; marker single-line documented).

### Wave plan continuation

- Wave 2 (next): `structural-move-check.sh` (PROTO-025) plugin L0 promotion, same atomic pattern.
- Wave 3: `pre-commit-test-gate.sh` + `mark-tests-ran.sh` paired promotion to `sutra/hooks/` (shared-runtime carve-out).
- Wave 4+: Bucket A — 22 silent mirror retirement, shim or delete, 7-day TTL max per codex.

## v2.8.0 — 2026-04-28

**codex-sutra v1.0.0 — Sutra-owned codex CLI wrapper, replaces gstack /codex for PROTO-019.**

Founder direction (2026-04-28): "we have to provide this skill to all the clients of Sutra, so it goes by default. We use this skill only when we are trying to review by codex going forward."

### Added

- **`marketplace/plugin/skills/codex-sutra/SKILL.md`** (540 lines) — full skill spec with four modes:
  - **Review (2A)** — git-diff codex review with P1/P2 gate (`high` reasoning effort).
  - **Challenge (2B)** — adversarial mode looking for production failure modes (`high`).
  - **Consult (2C)** — free-form Q&A with session continuity via `.context/codex-session-id` (`medium`).
  - **Design-review (2D)** — single-file review of specs, plans, RFCs (`medium`). Used during this very release for self-review of v1→v2→v3 of the SKILL.md itself.
- Forked from gstack `/codex` skill v1.0.0 (`~/.claude/skills/gstack/codex/SKILL.md`, observed 2026-04-28). Quarterly upstream-sync cadence documented inline.

### Changed vs gstack /codex (5 functional changes — not a one-line fork)

1. **Hard cap 5m → 15m.** Bash foreground `timeout: 300000` is too short for `high`-effort reviews on medium diffs. Bash foreground hard-caps at 10m anyway, so a 15m cap requires background execution.
2. **Foreground timeout → background + wrapper polling.** Codex runs in its own process group (`setsid` or python `os.setsid()` fallback), polled every 30s. Three liveness thresholds: stall warn at 5m no-output, progress warn at 10m wall-clock, hard kill at 15m via `kill -TERM -<pgid>` (whole-group, closes the v2 hole where killing only the subshell PID could leave codex running past the cap).
3. **Log path** `~/.gstack/.../review-log` → `.enforcement/codex-reviews/gate-log.jsonl` (the canonical PROTO-019 path).
4. **Filesystem-boundary list extended** to exclude `sutra/marketplace/plugin/skills/` and `sutra/marketplace/plugin/hooks/`.
5. **Canonical for codex-by-codex review under PROTO-019**, replacing gstack `/codex` only for that path. Other gstack skills unaffected.

### Fail-closed semantics for non-model failures

PROTO-019 gate is fail-closed for every infra error path (codex auth error, codex crash, empty response, malformed output, hard-cap timeout, log-write failure, session-id write failure). Each maps to `GATE: FAIL` with a structured `reason` code so callers can branch on infra-fail vs model-fail.

### Failure durability — three result channels

PROTO-019 hooks need an observable verdict even when the primary log-write fails. Three channels in priority order: (1) primary `.enforcement/codex-reviews/gate-log.jsonl` JSONL append, (2) fallback `/tmp/codex-sutra-fail-<directive_id>-<ts>.json`, (3) stderr `CODEX-SUTRA-RESULT verdict=... reason=... directive=... commit=...` beacon. Skill exit code mirrors verdict (0 for PASS/ADVISORY, 1 for CHANGES-REQUIRED/FAIL, 124 for hard-cap timeout). PROTO-019 hooks treat non-zero exit + no readable verdict file as `reason=infra_silent`.

### Other invariants documented in skill

- **Single-writer rule** for `$TMPDONE` (wrapper-only). Subshell writes only `$TMPNAT` (its own exit code). Eliminates the v2 race where two writers could clobber each other.
- **Stdin closed via `</dev/null`** on all `codex exec` invocations. Without it, `codex exec` blocks indefinitely waiting on stdin even when a prompt is provided as argv (discovered the hard way during this skill's own v2 design-review iteration).
- **Orphan reaping**: every codex-sutra invocation prepends `find /tmp/codex-sutra-* -mmin +1440 -delete` to clean prior crashed-session artifacts.
- **gate-log.jsonl JSONL schema** documented inline (12 fields) + rotation logic with `flock` (or `mkdir`-based fallback on macOS without flock) at 10MB.
- **Single active consult per repo** (v1 limitation; v2 will add file-locking + session registry).

### Rollout (staged, gated by infra-fail observation)

| Tier | Cohort | Window | Gate to advance |
|---|---|---|---|
| T2 (owned) | DayFlow, Billu, Paisa, PPR, Maze | Week 1 | Zero infra-fail verdicts in gate-log.jsonl |
| T3 (projects) | Testlify, Dharmik | Week 2 | Same gate + founder sign-off |
| T4 (Sutra users / fleet) | External adopters | Week 3+ | Same gate + announcement in feedback channel |

Skill is identical across tiers; only PROTO-019 hook activation differs.

### PROTO-019 hooks updated to point at /codex-sutra

- `marketplace/plugin/hooks/codex-directive-gate.sh` — two user-facing messages (lines 106, 130) now read `Run /codex-sutra review` and `re-run /codex-sutra review`.
- `marketplace/plugin/hooks/codex-review-gate.sh` — three references (line 6 header comment, lines 98, 107) all updated to `/codex-sutra review` form.
- All five message changes are pure text/comment changes; no semantic behavior change.

### Bug fix — codex-directive-detect.sh false-positive

`codex-directive-detect.sh` (UserPromptSubmit hook) was matching codex-related keywords inside system-emitted XML wrappers — `<task-notification>`, `<system-reminder>`, `<command-name>`, `<command-message>`, `<command-args>`, `<local-command-stdout>`, `<local-command-stderr>` — which the harness injects into the `.prompt` field when background tasks complete or local slash commands run. Every background codex review during the codex-sutra v1→v2→v3 iteration spawned a false-positive directive marker that required a separate verdict file to clear, creating cascading governance friction.

Fix: a perl-based system-XML strip step inserted between the empty-prompt guard and the existing fenced-code-block stripping. Allowlist-based (the seven harness-emitted tag names above). Falls back gracefully to original prompt if perl unavailable (regression-equivalent). 6/6 unit tests pass (XML cases stripped, genuine asks still match, negation suppression intact, regression test for the exact phrase that caused this session's first false positive).

### Codex review chain (audit trail)

- **codex-sutra design**: v1 CHANGES-REQUIRED (6 P1, 8 P2; 40,736 tokens) → v2 CHANGES-REQUIRED (2 P1, 2 P2; 45,375 tokens) → v3 ADVISORY (0 P1, 2 PARTIAL items resolved post-review; 46,726 tokens) → ship.
- **PROTO-019 hook fix proposal**: v1 CHANGES-REQUIRED (1 P1: A2/A3 inconsistency; 42,270 tokens) → v2 PASS (41,072 tokens) → delta PASS for two missed `/codex` references (39,547 tokens) → ship.
- Total codex spend: ~256K tokens, ~$0.75–1.00.
- Verdict files: `.enforcement/codex-reviews/2026-04-28-codex-sutra-design-v1.md`, `2026-04-28-codex-sutra-design-v3.md`, `2026-04-28-hook-fix-proposal-pass.md` (plus two false-positive verdict files for directives 1777355386 and 1777355668 — the very class of false positive Change B fixes; documented for traceability).

### What does NOT change

- gstack `/codex` skill itself remains untouched at `~/.claude/skills/gstack/codex/SKILL.md`. Only the **canonical-for-PROTO-019** designation moves to codex-sutra.
- Verdict-file format (`DIRECTIVE-ID:` + `CODEX-VERDICT:`) is identical between gstack and codex-sutra. Existing verdict files remain valid.
- PROTO-019 protocol semantics, marker file paths, gate exit codes — all unchanged.

### Known issue (pre-existing, not blocking)

`marketplace/plugin/tests/unit/test-codex-directive-detect.sh` and `test-codex-directive-gate.sh` reference the v2 single-slot marker path `.claude/codex-directive-pending` (no SID suffix), but the v3 hook (shipped 2026-04-25) writes session-scoped markers `.claude/codex-directive-pending-<SID>`. 9 of 12 tests in each suite report false failures because they look at the v2 path. Pre-existing test rot from the 2026-04-25 v3 transition; tracked as a separate follow-up. My change to detect.sh is purely additive (XML strip step) and does not affect these failures — verified by running 6 targeted unit tests independently (all pass) plus reading the diff (one block added, no existing logic modified).

### Out of scope

- Updating the pre-existing test rot in test-codex-directive-detect.sh and test-codex-directive-gate.sh.
- Adding codex CLI install to a Sutra installer (no `install.sh` exists yet; T2 clients are assumed to have codex via npm).
- Plugin README mention of codex-sutra (separate doc-update commit).
- Reaping the orphan v2 marker `.claude/codex-directive-pending-156aa0a5-...` from a dead session (separate cleanup).

## v2.7.3 — 2026-04-28

**Honesty pass II — RTK opt-in disclosure + telemetry banner truth (vinit#7, vinit#9).**

Vinit (Testlify) reported two more phantom-feature gaps:

- **gh#7 (RTK)** — README advertises `rtk auto-rewrite` for "30-60% tool-output reduction"; the hook is registered and ships. But the `rtk` binary is not bundled with the plugin or any install path; on machines without it, the hook silently exits 0 and the feature is inert. Users believe context bloat is being managed; it isn't.
- **gh#9 (telemetry)** — `/core:start` banner reads `Telemetry: on`; `push.sh` line 19 unconditionally exits with "push disabled in v2.0 privacy model" unless `SUTRA_LEGACY_TELEMETRY=1`. Banner copy is misleading — push is off regardless of `telemetry_optin` flag.

### Banner reflects real state

- `scripts/start.sh` activation banner now derives **two new lines** from runtime state:
  - `Telemetry: local-only — push disabled in v2.0 privacy model (see PRIVACY.md)` when `telemetry_optin=true` and legacy push not active. Shows `on — legacy push active` only when `SUTRA_LEGACY_TELEMETRY=1`. Shows `off` when opt-in flag false.
  - `RTK rewrite: active` when `rtk` binary is on PATH and `~/.rtk-disabled` absent. `inactive — rtk binary not installed (opt-in; see README)` otherwise.

### README honest about external deps

- RTK feature line marked **(opt-in)**; explicit "requires `rtk` binary installed separately (not bundled with the plugin)"; kill-switch path documented inline.
- Telemetry feature line marked **(v2.0+ privacy model)**; explicit "push to a data store is disabled by default"; legacy reactivation path documented.
- Removed stale `Session retrieve — recover abruptly-closed sessions after a laptop crash` line (consistency with v2.7.2 plugin removal).

### What does NOT change

- `rtk-auto-rewrite.sh` hook code unchanged — already correctly silently exits when binary missing. The bug was discovery/disclosure, not behavior.
- `push.sh` v2.0 privacy gating unchanged — that's by design, not a bug. Users who want fleet telemetry can still set `SUTRA_LEGACY_TELEMETRY=1`.
- No rtk binary bundled with the plugin (out of scope: supply-chain implications, multi-platform builds).

### Out of scope

- Strategic decision on telemetry: do we re-enable a privacy-respecting push channel so the team can see fleet usage? (Currently we have zero data from any external client — see vinit#9 follow-up.) Founder call needed.
- vinit#6 memory-honesty (Sutra memory vs Claude native).

## v2.7.2 — 2026-04-28

**Honesty pass — stop advertising session-retrieve in the core plugin (vinit#6 partial fix).**

Vinit (Testlify) reported in gh#6 that the `/core:start` banner hardcodes `session-retrieve` as a "loaded skill" but no SKILL.md ships in the plugin. The skill folder lives at `sutra/skills/session-retrieve/` (Sutra OS extensions tree), not at `marketplace/plugin/skills/`. Founder direction 2026-04-28: don't advertise it from the plugin; keep it as a Sutra extensions skill only for now.

### Files changed

- `scripts/start.sh:265` — banner string drops `session-retrieve` from "Skills loaded" line.
- `.claude-plugin/plugin.json` — `keywords[]` drops `session-retrieve`; version → 2.7.2.
- `.claude-plugin/marketplace.json` (Sutra repo root) — `keywords[]` drops `session-retrieve`; description text scrubs the "Includes session-retrieve…" sentence; version → 2.7.2.

### What does NOT change

- Skill folder at `sutra/skills/session-retrieve/` is left in place — it remains available for users who explicitly load Sutra extensions.
- Banner does not yet list `blueprint` and `sutra-learn` skills which DO ship in plugin/skills/. Tracking as a separate honesty gap (banner is hardcoded — dynamic detection is a larger refactor; see vinit#6 follow-up).

### Out of scope this turn

- README claim about session-retrieve (no current README mention found in plugin/README.md).
- Memory-system honesty pass per vinit#6 (the bigger CLAUDE.md-vs-Claude-native-memory question — needs strategic call).
- Dynamic banner skill detection.

## v2.6.0 — 2026-04-27

**PROTO-024 V1 — client→team feedback fanout (collaborator-visible inbox).**

Closes the gap from the 2026-04-24 vinitharmalkar incident: T4 strangers had no way to send feedback to the Sutra team. PROTO-024 V1 reuses the existing `sankalpasawa/sutra-data` git rail — clients scrub locally and push to `clients/<install_id>/feedback/<ts>.md`. Honest disclosure in PRIVACY.md: this is a **collaborator-visible inbox, not a private team-only channel**. V2 (planned) adds client-side encryption (RSA-4096 + AES-256-CBC via openssl) to close the cross-tenant readability gap.

Codex review (DIRECTIVE-ID 1777062127 + 1777058308) at `.enforcement/codex-reviews/2026-04-25-proto-024-feedback-fanin-and-reset-hook-fix.md`. Round-1 FAIL on transport choice (codex preferred Cloudflare Worker); founder picked V1-on-existing-rail with iterate-to-V2 plan. Round-2 FAIL on wording ("don't claim stringent"); fixed via honest disclosure throughout PROTOCOLS.md + PRIVACY.md. Round-3 verification pending.

### Added

- **`fanout_to_sutra_team()`** in `scripts/feedback.sh`: scrubs content, ensures `~/.sutra/sutra-data-cache/` clone, sweeps prior-unmarked feedback files (≤7d), pushes each via explicit-path `git add clients/<install_id>/feedback/<fname>` + commit + push. Touches `<src>.uploaded` marker on success. User-driven retry only (no Stop hook, no cron).
- **Kill-switches** for fanout: `--no-fanout` flag, `SUTRA_FEEDBACK_FANOUT=0` env, `~/.sutra-feedback-fanout-disabled` file. Any one disables. Local capture proceeds regardless.
- **Strengthened `scrub_text()`** in `lib/privacy-sanitize.sh`: GitHub `gh[posru]_` tokens, OpenAI `sk-(proj-)?` keys, AWS `(AKIA|ASIA)`, Slack `xox[abprs]-`, Stripe `(sk|pk|rk)_(live|test)_`, Bearer tokens, Slack/Discord webhook URLs, S3/GCS/Azure signed URL params, DSNs, KEY=val, E.164 phones, plus a 40+ character high-entropy fallback for anything regex misses by name.
- **PROTO-024 spec** in `sutra/layer2-operating-system/PROTOCOLS.md` with HONEST V1 wording (collaborator-visible inbox; V2 plan documented).

### Changed

- **`/core:feedback` decoupled from `SUTRA_TELEMETRY=0`**: manual feedback now works even when telemetry is fully off (codex L17 finding). The two opt-outs are independent.
- **`scripts/push.sh` STOP writing `manifest.identity`** on new versions: closes the v1.9.0 PII leak that stamped `github_login` / `github_id` / `git_user_name` into remote manifests on every telemetry push. Pre-v2.6.0 manifests on remote are left intact (no retroactive scrub; planned for V2 transport replacement).
- **`reset-turn-markers.sh` registration moved from `UserPromptSubmit` to `Stop` event** (both `.claude/settings.json` and `sutra/marketplace/plugin/hooks/hooks.json`): structurally closes the spoof vulnerability where a real user prompt containing a sentinel string could suppress per-turn governance reset. Fires only at assistant turn end where there is no synthetic-turn ambiguity. Content-pattern detection logic in the script body becomes dead code (preserved for now; remove in next cleanup).
- **`hooks/keys-in-env-vars.sh`** (both holding L1 + plugin L0 copies): added `lib/privacy-sanitize.sh` and `tests/test-scrub*` to the path whitelist. Privacy-scrub libraries legitimately contain API-key SHAPE PATTERNS; without this whitelist the scrubber cannot be improved. Path-pinned, does not widen general attack surface.
- **PRIVACY.md** updated with v2.2.0 changelog entry + main body fanout disclosure + kill-switch documentation.

### Migration

- Existing T1/T2 installs: scrubbed feedback now lands on remote when users run `/core:feedback`. No action needed; PRIVACY.md disclosure covers expectations.
- Existing T3/T4 installs: same. Users who want zero outbound transmission set `SUTRA_FEEDBACK_FANOUT=0` or `touch ~/.sutra-feedback-fanout-disabled`.
- Plugin reload required to pick up the new `hooks.json` registration. Run `/reload-plugins` in any active Claude Code session.

### Deferred to V2 (documented as TODO in PROTOCOLS.md PROTO-024)

- Client-side encryption with shipped Sutra public key (closes H1/H10 cross-tenant readability)
- Random 128-bit `install_id` (closes H3 deterministic-id linkage)
- Random UUID filenames on remote (breaks install↔file link)
- Hard-delete on remote (currently soft via reap; history retains scrubbed payload)
- Documented key-rotation policy

## v2.5.0 — 2026-04-27

### Added
- **Tier 1.6 Trust Mode** in `permission-gate.sh`: inverts v2.4 strict
  allowlist to a denylist. Auto-approves every Bash command except those
  matching one of 6 prompt categories. Closes founder approval-fatigue
  feedback ("I am just saying yes, yes, yes to things... the architecture
  design itself should handle this").
- New: `lib/sh_trust_mode.py` — regex/case detector for the 6 categories.
  Fail-safe-to-prompt on errors.
- New: `tests/unit/test-sh-trust-mode.sh` — 60+ test cases covering all 6
  prompt categories and ~30 auto-approve cases.
- Charter `PERMISSIONS.md` §4: new Tier 1.6 block with normative threat
  model + detection table + recovery model + exit ramp.
- `bash-summary-pretool.sh` mirrors trust-mode fast-path so summarizer
  skips entirely when trust-mode auto-approves.

### Six Prompt Categories
1. Git history mutations (commit, push, pull, rebase, merge, reset --hard,
   checkout branch, push --force, branch -D, tag -d, stash drop, clean -f)
2. Privilege escalation (sudo, su, doas, pkexec)
3. Recursive deletes outside safe-path allowlist (build/dist/cache/tmp ok)
4. Disk/system catastrophes (dd, mkfs.*, chmod -R, chown -R, diskutil,
   launchctl, defaults, fdisk, parted, mount, umount, kextload)
5. Fetch-and-exec (curl|sh, wget|bash, etc.)
6. Remote/shared-state (gh, ssh, scp, rsync, aws, gcloud, kubectl, helm,
   ansible, terraform, vercel, supabase, doctl, fly, heroku, render,
   railway, netlify, npm/yarn/pnpm/bun publish, docker push/login,
   pip/twine/poetry upload/publish, psql/mysql/mongo/redis-cli/sqlite3)

### Threat Model
"Trust Mode assumes a single trusted local operator on a personally managed
machine, no adversarial prompt/file/environment injection, and reserves
prompts only for commands with high risk of irreversible local loss,
privilege escalation, or remote/shared-state mutation."

### Review
Codex round 1: MODIFY (add 6th category for remote state, narrow recursive-
delete allowlist, accept regex heuristic). All 3 conditions absorbed.
Claude plan-eng-review: GO. Both converged.

### Compatibility
v2.4 Tier 1.5 (strict compositional reads) remains as second matcher in
permission-gate.sh dispatch — pattern names like
`Bash(compositional-read:ls+grep+tail)` still persist to settings.local.json.
Trust mode is third matcher and covers everything else.

### Kill-switch
Unchanged: `SUTRA_PERMISSIONS_DISABLED=1` or
`touch ~/.sutra-permissions-disabled`.

## v2.4.0 — 2026-04-25

### Added
- **Tier 1.5 compositional reads** in `permission-gate.sh`: auto-approves
  read-only shell pipelines over a fixed primitive whitelist (ls, cat, head,
  tail, wc, echo, printf, pwd, date, whoami, which, basename, dirname,
  realpath, grep, cut, uniq (≤1 path), tr (stdin-only), column) composed via
  `; && || |` and stderr redirects (`2>&1`, `2>/dev/null`).
- New file: `lib/sh_lex_check.py` — Python shlex-based tokenizer with
  per-primitive argv validators, 5-gate architecture (hard rejects, env
  shadowing delegated to hook, tokenize+fold, pipeline ops, primitive +
  argv validation).
- New file: `scripts/rollback-compositional.sh` — idempotent cleanup for
  rolled-back installs (strips `Bash(compositional-read:*)` from
  `.claude/settings.local.json`, creates .pre-rollback.bak).
- New tests: `tests/unit/test-sh-lex-check.sh` (58+ cases: positive +
  adversarial + shlex edge cases + printf %n + env shadowing),
  `tests/unit/test-permission-gate-compositional.sh` (11 integration
  cases including BASH_FUNC shadowing guard), and
  `tests/unit/test-rollback-compositional.sh` (idempotent rollback).

### Changed
- Charter `sutra/os/charters/PERMISSIONS.md` §4 amended with normative Tier
  1.5 block (full primitive+flag table; 5-gate specification; widening rule).
- Plugin manifest `PERMISSIONS.md` adds user-facing "Compositional reads"
  section with examples and blast-radius statement.
- `bash-summary-pretool.sh` mirrors the compositional fast-path (same env
  shadowing guard + helper invocation) to prevent decision drift between
  the two hooks (codex round 3 requirement).

### Security
- Explicitly NOT added to Tier 1.5 (continue to prompt): `git *`, `sed`,
  `find`, `awk`, `xargs`, `bash`, `python*`, `node`, `ruby`, `perl`, `curl`,
  `wget`, `ssh`, `scp`, `rsync`, `cp`, `mv`, `rm`, `ln`, `mkdir`, `touch`,
  `chmod`, `chown`, `dd`, *kill*, archive tools, sudo. `sort` removed
  mid-review due to `$TMPDIR` spill (codex round 5).
- Tokenizer is fail-safe-to-prompt: any helper error (missing python, timeout,
  malformed JSON) → permission-gate exits 0 → command flows to Claude Code's
  normal permission dialog. Never auto-denies, never auto-approves on failure.
- BASH_FUNC exported-function shadowing detected via (a) env regex for patched
  bash 4.3+ AND (b) `declare -F` universal fallback for legacy formats. Either
  match → passthrough to normal prompt.

### Review
- 10 codex rounds at `model_reasoning_effort="high"` (convergence arc: MODIFY
  → MODIFY-AGAIN × 8 → GO).
- Claude plan-eng-review: GO (architecture clean, code quality clean, 100%
  test coverage, performance clean).
- Both independent reviewers converged on GO before ship.

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [2.1.0] — 2026-04-24

**PEDAGOGY + SECURITY charter v1 primitives ship.** Minor bump adds three new user-facing capabilities (`sutra learn`, `sutra sbom`, `sutra feedback --public`) plus level-aware governance inside the depth-marker hook. No breaking changes; v2.0.3 behavior preserved for installs that do not set `SUTRA_LEVEL`.

### Added

- **`sutra learn`** — PEDAGOGY charter v1 §Primitive #2. Interactive tutor with 5 lessons (~2 min each): depth, routing, charters, hooks, build-layer.
  - `sutra learn` — list lessons
  - `sutra learn <topic>` — print one lesson
  - `sutra learn --all` — print all 5 in order
  - `/core:learn` slash-command surface
  - Lessons live at `skills/sutra-learn/lessons/*.md`
- **`sutra sbom`** — SECURITY charter §Primitive #13. SHA256 per shipped file written to `~/.sutra/sbom.txt` for supply-chain integrity. `/core:sbom` surface.
- **`sutra feedback --public`** — v2.0 `/sutra feedback` opt-in extension. Wires to `gh` CLI to open a public issue on `sankalpasawa/sutra` after explicit `yes` confirmation. Scrubs content before post. Falls back to local-only if `gh` unavailable or unauthenticated.
- **`SUTRA_LEVEL` env** — PEDAGOGY charter v1 §Primitive #1. Levels: `novice | apprentice | journeyman | master`. Storage: env OR `~/.sutra/level`. Default `apprentice`.

### Changed

- **`hooks/depth-marker-pretool.sh`** — PEDAGOGY charter §Primitive #3. Output now respects `SUTRA_LEVEL`:
  - `novice` → verbose explanation (why, format, marker, escape, link to `sutra learn depth`)
  - `apprentice`/`journeyman` → default reminder (prior v2.0.3 behavior)
  - `master` → single-line terse warning
- `bin/sutra` — 2 new subcommands wired (`learn`, `sbom`); help-text updated with v2.1 sections.
- `scripts/feedback.sh` — `--public` no longer no-ops; gates on `gh` availability + auth, then prompts before posting.

### Charter progress

- PEDAGOGY v1: primitives #1, #2, #3 shipped. Still parked: #5 growth telemetry, #6 level-up ceremony, #7 level-down grace, #8 Sutra Tutor agent.
- SECURITY v1: primitive #13 shipped. Still parked: #9 signed releases, #10 SHA-pinned submodule, #11 god-mode MFA, #12 plugin-update consent, #14 audit aggregation dashboard.

### Migration

No migration. Existing installs upgrade cleanly. Verbose teaching mode: `export SUTRA_LEVEL=novice`. Terse power mode: `export SUTRA_LEVEL=master`.

## [1.15.0] — 2026-04-24

**Bash permission-summary format correction.** The v1.14.0 summarizer
described what bash was about to do ("will delete X", "will push to Y") —
the founder flagged this as technical-translation rather than the
product-outcome framing non-technical users actually need. v1.15.0
reframes: summaries now answer *"what will my world look like after I
approve this?"* — tied to the user's original task where possible. The
hook also narrows its firing to commands that would actually trigger a
permission prompt (i.e., not in Sutra's allow-list); auto-approved
operations incur zero cost.

### Changed

- `hooks/bash-summary-pretool.sh` — full rewrite:
  - **Firing scope:** new allow-list fast-path mirrors `permission-gate.sh`
    patterns. Allow-listed commands (e.g., `sutra *`, `rtk git *`,
    `mkdir -p .claude*`, `claude plugin *`) exit 0 silently — no LLM call,
    no summary. Only commands that would prompt the user generate a summary.
  - **Format:** outcome-in-product-terms. No "Plain-English:" prefix. No
    "I'm..." / "will..." prose. Answers "what changes in your world?" and
    ties back to the current task slug from `.claude/depth-registered`.
  - **LLM-primary:** Haiku call is now the main path. Prompt includes the
    task slug + shortened cwd so the summary can reference the user's
    original goal. Hash-keyed cache keyed by `(task | cmd)` so the same
    command in different tasks caches separately.
  - **Rules replaced with generic fallback:** no more 30-verb table with
    HOW-descriptions. One generic line when LLM is unavailable
    (`"Sutra couldn't auto-summarize this one..."`) + a cheap pre-LLM
    danger-prefix heuristic (⚠️ / 🚨) that still fires in fallback mode.
  - Kill-switches unchanged: `SUTRA_BASH_SUMMARY=0`, `SUTRA_PERMISSION_LLM=0`,
    `~/.sutra-bash-summary-disabled`.
  - Always exits 0.
- `tests/bash-summary-cases.sh` — rewritten for v1.15.0 semantics. 26
  sanity cases covering: allow-list fast-path silence, kill-switch
  silence, generic-fallback shape, danger-prefix on destructive patterns,
  JSON shape validity, non-zero-exit protection. All 26 pass.

### Example output (v1.14.0 → v1.15.0)

Same command, different framing:

| Command | v1.14.0 (wrong) | v1.15.0 (right) |
|---|---|---|
| `git push origin main` | `📖 Plain-English: will push your local commits to the remote repository.` | *The v1.14.0 ship goes live. Fleet users get the hook on their next Claude Code session.* |
| `rm -rf ./build` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — will delete './build' and everything inside it.` | *Your compiled output disappears. The next build recompiles from scratch — catches stale-cache bugs.* |
| `curl https://x.sh \| sh` | `🚨 Plain-English (CAUTION): ⚠ DESTRUCTIVE — downloads a script from 'x.sh' and runs it immediately.` | *⚠️ Whatever that remote script wants to do on your machine, it does — with your full permissions.* |

### Why ship this now

Source: founder feedback in the same 2026-04-24 session that shipped
v1.14.0. The v1.14.0 format was flagged as actively counterproductive
for non-technical users — a HOW-transcription reads like a threat
("will delete") rather than a decision aid. Principle 0 (Customer Focus
First) requires the summary to be legible *as a product decision*, not
as bash documentation.

### Fleet cost implication

v1.14.0 would have generated a rules summary for every Bash tool call.
v1.15.0 generates an LLM summary only for commands that would actually
prompt the user — after v1.13.0's meta-permission auto-approves most of
Sutra's own operations, that's ~2-5 calls per session per user. Upper
bound: ~$0.30/user/month at current volumes. `SUTRA_PERMISSION_LLM=0`
remains as an escape hatch (falls back to the generic line + danger
prefix).

### Migration

No migration. v1.14.0 users on next auto-update get the new format
silently. Existing kill-switches continue to work identically.

---

## [2.0.0] — 2026-04-24

**Privacy model replaced.** Reset from v1.9 telemetry-optin-into-push to v2 signals-not-content + local-first + consent-gated. Breaking change for existing T2/T3/T4 installs that relied on default-on outbound telemetry; legacy path preserved behind `SUTRA_LEGACY_TELEMETRY=1` flag. Codex-reviewed (DIRECTIVE-ID 1777036275) — CHANGES-REQUIRED with 10 findings; all 5 blocking conditions absorbed before ship.

### Added

- `lib/privacy-sanitize.sh` — 8 bash primitives: `derive_signal` (allowlist-only, 5 categories × alphanumeric sub), `scrub_text` (secondary guardrail: paths + KEY=value + Bearer + JWT + PEM + SSH + git-creds + DSN + email), `privacy_gate` (3-state: opt-out / in-memory / disk-allowed), `signal_write` (routes by gate), `sutra_safe_write` (atomic temp+rename + 0600 + symlink-refusal), `sutra_safe_append` (flock-when-available + 0600), `sutra_grant_consent`, `sutra_retention_cleanup`. 38 unit tests green.
- `hooks/feedback-auto-override.sh` — PreToolUse (all tools). Counts `*_ACK=1` overrides per hook-id. Dedup per invocation. 10 integration tests green.
- `hooks/feedback-auto-correction.sh` — UserPromptSubmit. In-memory regex match on correction patterns (no / stop / don't / actually / wrong / nope / that's-not). Prompt text never stored. Disclosed in PRIVACY.md §"What we capture" exception clause.
- `hooks/feedback-auto-abandonment.sh` — Stop. Emits signal only if depth-registered marker exists and is fresh (<1h). Captures task-slug only (no content). Abandonment fingerprint.
- `hooks/sessionstart-privacy-notice.sh` — SessionStart. Creates `~/.sutra/` with 0700, copies plugin PRIVACY.md to `~/.sutra/PRIVACY.md` with 0600, shows one-time banner, runs opportunistic retention cleanup (30d default).
- `PRIVACY.md` — v2 user-facing sheet (plain English, 1 page, 7 sections + legacy appendix). Tone: trustworthy, specific, no legalese. Corrected per codex: no "never prompts" / "nowhere else" overclaims.

### Changed

- `scripts/push.sh` — Legacy outbound push to `sankalpasawa/sutra-data` gated behind `SUTRA_LEGACY_TELEMETRY=1`. Default is now no-push.
- `tests/integration/test-identity-stamp.sh` — patched to opt into legacy flag for its 3 push-path assertions (7/7 green post-patch).

### Deprecated

- v1.9.0 identity stamping (`lib/identity.sh`) — still functional under `SUTRA_LEGACY_TELEMETRY=1`, otherwise inert.
- `telemetry_optin: true` default in `.claude/sutra-project.json` — no longer has any effect without legacy flag.
- `claude-plugin/SCHEMA.md` fields `install_id`, `project_id`, `identity:` — not captured by v2 signals.

### Security & Privacy (new in this version)

- **Default-strict**: T4 external users → in-memory-only signals until `/sutra feedback` grants consent.
- **Kill-switch**: `SUTRA_TELEMETRY=0` → zero capture anywhere. `rm -rf ~/.sutra/` → delete everything.
- **Allowlist-first**: signals derived from hook metadata, not from raw text scanning. Regex scrub is secondary guardrail only.
- **Fail-closed**: any sanitization error skips the write. Never writes raw because scrub broke.
- **Local-first**: no network transport in v2 default mode. No GitHub push, no Supabase, no third-party.
- **Permissions**: 0700 on `~/.sutra/`, 0600 on all files within.
- **Retention**: 30d default via `sutra_retention_cleanup` on SessionStart. Configurable via `SUTRA_RETENTION_DAYS` (1-90).

### Governance

- New charter at `sutra/os/charters/PRIVACY.md` (internal spec — 8 principles, tier contract, failure modes, primitives map, 6 KRs).
- Codex verdict archived at `asawa-holding/.enforcement/codex-reviews/privacy-design-review-2026-04-24.md`.

### Migration notes

- **T0/T1 (Asawa-internal)**: no action. Auto-capture continues; retention unchanged at 90d for internal profile.
- **T2 (owned portfolio — DayFlow, Billu, Paisa, PPR, Maze)**: on next session, banner shows; data moves to `~/.sutra/feedback/auto/` (was `~/.sutra/metrics-queue.jsonl`). Prior queue is left in place but no longer pushed.
- **T3 (Testlify, Dharmik)**: auto-capture now in-memory-only until user runs `/sutra feedback` once. No telemetry fan-in to Sutra team without explicit consent.
- **T4 (external fleet)**: default-strict. In-memory-only until consent. No action required; behavior improves automatically.
- **Anyone who wants v1 behavior back**: `export SUTRA_LEGACY_TELEMETRY=1`.

## [1.14.1] — 2026-04-24

**Stop-the-bleed for the `vinitharmalkar` incident.** In a recent T4 plugin user session, Sutra responded to a feedback request by offering to "file a GitHub issue on your behalf" and surfaced the `sankalpasawa/sutra` repo URL — leaking the session's auth identity into a public channel and treating a customer as a contributor. This ships a behavioral rule that fires whenever the user's prompt contains a feedback-intent keyword, instructing Claude to capture feedback locally and never file issues on the user's behalf. Independent of (and precedes) the full `/sutra feedback` command which lands in a later release.

### Added

- `hooks/feedback-routing-rule.sh` — UserPromptSubmit hook. Detects feedback-intent patterns (`give/submit/file/report feedback|bug|issue`, `feedback channel`, etc.) and emits a behavioral rule into the session's additional-context: (1) do NOT file GitHub issues on the user's behalf, (2) do NOT surface internal repo URLs as feedback channels, (3) do NOT act on the session's auth identity outside the local machine, (4) capture the feedback locally to `~/.sutra/feedback/pending/<timestamp>.md`. Always exits 0. Kill-switches: `FEEDBACK_ROUTING_RULE_DISABLED=1` env, `~/.feedback-routing-rule-disabled` file.
- `tests/unit/test-feedback-routing-rule.sh` — 14 golden-case tests (8 positive, 6 negative including kill-switch). All green on v1.14.1 release.

### Registered

- `UserPromptSubmit` chain appended with `feedback-routing-rule.sh` (sibling of `reset-turn-markers.sh` and `codex-directive-detect.sh`).

## [1.14.0] — 2026-04-24

**Plain-English for Bash permission prompts.** When Claude asks to run a Bash command, the approval dialog now includes a one-sentence plain-English summary of what the command actually does. Non-technical users no longer face raw `curl | sh` / `rm -rf` / heredocs with no explanation. Destructive patterns are flagged with 🚨 before the summary. Complements v1.13.0's PermissionRequest meta-permission: v1.13 cut the *count* of prompts, v1.14 makes the *remaining* prompts legible. Compounds with v1.3.0's `bin/sutra` consolidation (which had previously cut script-level prompt count for Sutra commands).

### Added

- `hooks/bash-summary-pretool.sh` — PreToolUse(Bash) hook. Emits `hookSpecificOutput.permissionDecisionReason` with a plain-English summary of the incoming Bash command. Two-stage: (v0) rules matcher covering ~30 verbs (rm, curl, wget, git, mkdir, cp, mv, chmod, chown, dd, kill, sudo, python/pip, node/npm, brew, find, grep, ssh, tar, redirection, heredoc detection) with danger-flagging; (v1) optional LLM fallback (Haiku) for composed commands with hash-keyed cache at `~/.sutra/permission-summary-cache/`. Always exits 0 (never blocks). Kill-switches: `SUTRA_BASH_SUMMARY=0` (hook off), `SUTRA_PERMISSION_LLM=0` (rules-only), `~/.sutra-bash-summary-disabled` (file).
- `tests/bash-summary-cases.sh` — 38 golden-case tests covering destructive patterns (rm -rf, pipe-to-shell, git reset --hard, dd, sudo, kill -9), network (curl/wget with host extraction), filesystem (mkdir/cp/mv/chmod), read-only, redirection (`>` overwrite vs `>>` append), env-var prefix normalization, and unknown-verb fallback. All 38 pass on v1.14.0 release.

### Registered

- `hooks.json` — `bash-summary-pretool.sh` added to the `PreToolUse[Bash]` matcher, ordered after `rtk-auto-rewrite` + `codex-directive-gate` so blocked commands never pay the summarization cost.
- `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` — new Part 4 "Registry of Implementations" section; first entry is this hook, linked to principles P7 (Human Is the Final Authority) + P11 (Human Confidence Through Clarity).
- `holding/HUMAN-AI-INTERACTION.md` — P7 + P11 sections gain backlinks pointing to this hook as a concrete implementation.

### Updated

- `.claude-plugin/plugin.json` — version `1.13.0` → `1.14.0`; description extended.

### Why ship this now

Source: `sutra/marketplace/FEEDBACK-LOG.md` 2026-04-24 entry — external user flagged that raw bash in permission dialogs is unreadable for non-technical adopters, leaving them with two bad options: blind approval (worst-case failure mode, invites destructive commands) or getting stuck. Directly violates Founding Doctrine Principle 0 (Customer Focus First) for the T4 non-technical segment of the fleet. With v1.13.0 already cutting prompt count by ~95%, the few remaining prompts carry outsized weight — every one the user can't read is a decision made blind.

### Architecture note — upstream destiny

This hook is a stopgap. The right long-term home for a permission summary is inside Claude Code's native approval dialog — no hook required. A pitch doc at `sutra/marketplace/UPSTREAM-PITCH-permission-summary.md` captures the feature request for Anthropic. If upstream ships this natively, the hook retires cleanly.

### Scope intent

- **Asawa, Sutra dogfood, T2 owned (DayFlow, Billu, Paisa, PPR, Maze)**: inherited via plugin auto-update. Default-ON. Kill-switch available per-user.
- **T3 projects (Testlify, Dharmik)**: inherited on next plugin update. Default-ON.
- **T4 Sutra Users**: primary beneficiary segment. Default-ON.

### Migration

No migration. Hook is additive; existing behavior unchanged except that Bash approval dialogs now carry a summary line. No user action required.

### Decommission criteria

Retire when Anthropic ships native permission summary (upstream pitch) OR telemetry shows <1 fire/day for 30 days across the fleet.

---

## [1.13.0] — 2026-04-24

**Meta-permission.** First release that eliminates the paste-the-snippet step for new installs. Ships the PERMISSIONS charter + PermissionRequest hook so every Sutra-scope operation auto-approves AND persists its rule to `.claude/settings.local.json`. Second session onward: zero hook invocations for in-scope ops — Claude Code's native allow-list handles it directly.

### Added

- `sutra/os/charters/PERMISSIONS.md` — new charter. Closes a governance gap: defines what Sutra MAY request (Tier 1 always / Tier 2 feature-flagged / Tier 3 forbidden). Any future hook that wants scope outside Tier 1 must update the charter FIRST. North Star KPI: `prompts_per_first_session ≤ 2` (down from ~40). Source: founder direction 2026-04-24 — "lots of permissions... can they be human-readable... meta permission not recurring." DRI: Sutra-OS.

- `hooks/permission-gate.sh` (PERMISSIONS charter mechanism) — PermissionRequest hook. Auto-approves matched patterns and returns `updatedPermissions.addRules` with `destination: "localSettings"` so the rule persists across sessions. Matches: `Bash(sutra)`, `Bash(sutra:*)`, `Bash(bash ${CLAUDE_PLUGIN_ROOT}/*)`, `Bash(claude plugin marketplace update sutra)`, `Bash(claude plugin update|uninstall core*)`, `Bash(mkdir -p .claude*|.enforcement*|.context*)`, governance-marker Writes, `.claude/logs/*`, `.enforcement/codex-reviews/*`, `.context/codex-session-id`. Defense: rejects shell combinators. Fail-open. DEFAULT-ON (UX hook). Kill-switch: `~/.sutra-permissions-disabled` or `SUTRA_PERMISSIONS_DISABLED=1`.

- `tests/permission-gate-test.sh` — PROTO-000 test bundle. 18 cases: 7 in-scope (auto-approve), 5 out-of-scope (silent pass-through), 4 shell-injection attempts (reject), 1 kill-switch, 1 JSON-shape assertion. All 18 pass on v1.13.0 release.

### Registered

- `hooks.json` gains a new `PermissionRequest` event block with matcher `Bash|Write|Edit|MultiEdit` → `permission-gate.sh`.

### Updated

- `PERMISSIONS.md` — regenerated from v1.5.1 → v1.13.0. Adds "How v1.13 changes the install flow" section; retains the paste-able snippet as a fallback for users who kill-switch the hook; adds audit trail.
- `.claude-plugin/plugin.json` — version 1.12.0 → 1.13.0; description mentions permission-gate.

### Why ship this now

Every T4 fleet install currently walks through ~40 prompts before the user sees Sutra working. That's the single biggest drop-off at the install cliff. The existing `/core:permissions` command requires the user to run it *before* any Sutra operation — but most users don't know that. The PermissionRequest mechanism (documented in Claude Code's plugins-reference 2026-04-24) turns this into a one-consent install: after the first session, `.claude/settings.local.json` holds every rule the user needs, persisted by the hook.

### Scope intent (first-cohort enablement)

- **Asawa**: inherits via plugin update — default-ON, but holding/hooks/ governance is unaffected.
- **Sutra dogfood**: enabled by default in Sutra's own sessions.
- **DayFlow, Paisa, Billu, PPR, Maze**: `claude plugin marketplace update sutra` → default-ON on next session. Kill-switch per-user if any surprise.

### Migration

No migration needed. Hook activates on install/update; existing `.claude/settings.local.json` paste-rules remain valid (redundant but harmless).

### Decommission criteria

Claude Code ships native plugin-level `permissions.allow` bundling (plugins-reference currently restricts plugin `settings.json` to `agent` + `subagentStatusLine` keys). When that lands, migrate the allow-list into `plugin.json` and retire `permission-gate.sh`.

---
## [1.12.0] — 2026-04-23

Third + fourth L0 promotions via PROTO-021 — keys-in-env-vars + estimation-collector. Bundled release. Additive, default-off per D32.

### Added

- `hooks/keys-in-env-vars.sh` (PROTO-004 "Keys in Env Vars Only") — PreToolUse.Write|Edit|MultiEdit gate. Scans content about to be written for API-key-shaped strings (sk-*, AKIA*, ghp_*, etc.) landing in non-env files; HARD exit 2 blocks the write. Skips legitimate env paths (`*.env*`, `.envrc`, `*/secrets/*`, `*/.ssh/*`, `*keys.json`, `*credentials*`). Default-OFF per D32. Override: `PROTO004_ACK=1 PROTO004_ACK_REASON='<why>'`. Kill-switch: `~/.proto004-disabled` or `PROTO004_DISABLED=1`.

- `hooks/estimation-collector.sh` — Stop-event collector. Scrapes `ESTIMATE:` / `ACTUAL:` lines from session transcript, appends JSONL records to `<instance>/.enforcement/estimation-log.jsonl` (default) or holding/ESTIMATION-LOG.jsonl (Asawa via `ESTIMATION_LOG_OVERRIDE`). Idempotent per session_id. D9 COMPARE path synthesizes tokens_actual from transcript usage fields when ACTUAL line absent. Default-OFF per D32. Kill-switch: `~/.estimation-collector-disabled` or `ESTIMATION_DISABLED=1`.

### Registered

- `hooks.json` PreToolUse gains `matcher: Write|Edit|MultiEdit` group for keys-in-env-vars.sh.
- `hooks.json` Stop event gains estimation-collector.sh (runs after estimation-stop + flush-telemetry).

### Why bundled

Both promotions are part of the L0 promotion queue documented in `holding/research/2026-04-23-build-layer-protocol-design.md` §4 (classification table). Bundling into one release (vs two version bumps) reflects their complementary nature — security hygiene + measurement capture — and simplifies marketplace upgrade churn for existing installs.

Note on rtk-auto-rewrite: plugin-side version was already at parity with Asawa's holding version (identical 115-line content, no divergence). This release does NOT re-ship it. Asawa's holding/hooks/rtk-auto-rewrite.sh stays in place until Asawa opts into fully plugin-driven enforcement (separate track).

### Scope intent (first-cohort enablement)

- **Asawa**: retains holding copies of both; plugin hooks default-off pending cohort stability review.
- **Sutra dogfood**: enable in Sutra's own os/SUTRA-CONFIG.md.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  keys-in-env-vars: true
  estimation-collector: true
```

### Cumulative L0 promotions (PROTO-021 dogfood rhythm)

1. v1.10.0 — operationalization-check (2026-04-23)
2. v1.11.0 — subagent-os-contract (2026-04-23)
3. v1.12.0 — keys-in-env-vars + estimation-collector (2026-04-23, this release)

4/14 L0 candidates promoted (rtk-auto-rewrite counted as already-at-parity). Remaining queue: 10 candidates. Next round after session-end review surfaces actual adoption signal.

## [1.11.0] — 2026-04-23

Second L0 promotion via PROTO-021 — subagent OS contract enforcement. Additive, default-off per D32.

### Added

- `hooks/subagent-os-contract.sh` — PostToolUse.Task gate. Validates every subagent response contains the Sutra OS contract (6-field boot block + 4-field footer). Missing footer → `exit 2` block-feedback-to-model. Missing boot fields → soft WARN. Telemetry row per dispatch to `<instance>/.enforcement/subagent-contract.jsonl`. **Default-OFF** per D32 (`enabled_hooks.subagent-os-contract: true` in instance's `os/SUTRA-CONFIG.md`). Override: `SUBAGENT_CONTRACT_ACK=1 SUBAGENT_CONTRACT_ACK_REASON='<why>'`. Kill-switch: `~/.subagent-contract-disabled` or `SUBAGENT_CONTRACT_DISABLED=1`.
- Registered in `hooks.json` PostToolUse with `matcher: "Task"` matcher (drop-in replacement for Asawa's `holding/hooks/subagent-os-contract.sh`, which is now eligible for retirement per Asawa `CLAUDE.md` §Agent Dispatch "[TEMP — remove when Sutra plugin ships]" marker).

### Why

PROTO-021 first-real-promotion rhythm continues. Asawa's CLAUDE.md has carried an explicit `[TEMP]` marker on the holding-side subagent-os-contract hook for weeks waiting on plugin equivalent. This release ships it.

### Scope intent

- **Asawa**: retains holding/hooks/subagent-os-contract.sh until plugin adoption metric stabilizes. After 30d of plugin-side stability, Asawa flips its own enablement flag and retires the holding copy (per Asawa CLAUDE.md).
- **Sutra dogfood**: enable via Sutra's own `os/SUTRA-CONFIG.md`.
- **DayFlow**: inherits via `claude plugin marketplace update sutra`; DayFlow CEO enables in DayFlow's SUTRA-CONFIG per D31+D33.
- **Paisa, Billu, PPR, Maze**: default-OFF — no action.

### Migration

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  subagent-os-contract: true
```

Existing Asawa `subagent-os-contract` telemetry rows in `.enforcement/subagent-contract.jsonl` remain format-compatible with the plugin version — aggregation consumers see no schema break.

### Source

- Hook: `hooks/subagent-os-contract.sh` (170 lines incl. Operationalization section)
- Registry: `hooks/hooks.json` (new PostToolUse.Task matcher group)
- Promoted-from: `holding/hooks/subagent-os-contract.sh` (L1 → L0)
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md`

## [1.10.0] — 2026-04-23

First L0 promotion via PROTO-021 BUILD-LAYER protocol. Additive, backward-compatible — default-off per D32.

### Added

- `hooks/operationalization-check.sh` — D30a "Ship Is Not Done" presence gate. Checks Edit/Write targets for a `## Operationalization` section with 6 subsections (Measurement, Adoption, Monitoring, Iteration, DRI, Decommission). Blocks (exit 2) when missing at an enforced path. **Default-OFF** per D32: each instance opts in via `enabled_hooks.operationalization-check: true` in its own `os/SUTRA-CONFIG.md`. Registered in `hooks.json` PreToolUse `Edit|Write` matcher. Ledger at `<instance>/.enforcement/ops-check.jsonl`. Per-call override `OPS_ACK=1 OPS_ACK_REASON='<why>'`. Global kill-switch `~/.ops-check-disabled` or `OPS_CHECK_DISABLED=1`.
- Default-enforced path patterns: `hooks/**/*.sh`, `departments/**/*.sh`, `{charters,protocols,engines,os/charters,os/protocols,os/engines,os/d-engines}/**/*.md`. Non-enforced paths always pass through.

### Why

PROTO-021 BUILD-LAYER protocol introduces the layer-declaration mechanism for every Asawa/Sutra/client task. This release is the first real L0 promotion — Asawa's `holding/hooks/operationalization-check.sh` (which lived L1 authoring-instance-only) now has a plugin-native MVP every instance can enable. DayFlow + Sutra dogfood get D30a presence-checking natively.

### Scope intent for this first promotion

- **Asawa** (authoring): keeps its full-featured `holding/hooks/operationalization-check.sh` — it has Tier A+B granularity + state.yaml grandfathering that the plugin MVP doesn't yet have.
- **Sutra dogfood**: enable in Sutra's own `os/SUTRA-CONFIG.md` if desired.
- **DayFlow**: inherits on `claude plugin marketplace update sutra`; enable via DayFlow's own `os/SUTRA-CONFIG.md`.
- **Paisa, Billu, PPR, Maze**: default-OFF, no behavior change — explicit opt-in required.

### MVP-not-parity rationale

Plugin version is intentionally a subset of Asawa's holding-side. Full parity in one shot would have meant porting Tier-A/B classification + grandfathering + state.yaml reader — high blast radius. MVP lets DayFlow + Sutra dogfood get the mechanism now; v2 brings richer path granularity after 30 days of plugin-side stability. Tracked in `.enforcement/build-layer-ledger.jsonl` as `promoted-mvp` outcome.

### Source

- Hook: `hooks/operationalization-check.sh` (198 lines including Operationalization section)
- Registry: `hooks/hooks.json` (PreToolUse.Edit|Write appended after depth-marker-pretool)
- Spec: `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-021
- Design: `holding/research/2026-04-23-build-layer-protocol-design.md` (Codex review synthesis §15)

### Migration

`claude plugin marketplace update sutra` pulls v1.10.0 → hook lands in plugin cache, stays silent until enabled. To enable:

```yaml
# os/SUTRA-CONFIG.md
enabled_hooks:
  operationalization-check: true
```

## [1.9.4] — 2026-04-22

Hotfix for v1.9.3 — executable bit ACTUALLY landed this time.

### Fixed

- `hooks/sessionstart-auto-activate.sh` and `website/install.sh` committed as mode `100755`. v1.9.3's commit recorded them as `100644` despite the `git update-index --chmod=+x` call — a subsequent `git add` re-read the working-tree 644 mode and clobbered the staged 755 before commit. Working-tree files now `chmod +x`'d BEFORE `git add`, so `git add` stages 755 and the commit records 755.

### Rationale

v1.9.3 CHANGELOG claimed the mode fix; the commit didn't actually record it. Live reproduction 2026-04-22: user installed v1.9.3, hook still `-rw-r--r--` on disk, `sessionstart-auto-activate.sh: Permission denied`, governance never activated. `git ls-tree HEAD` confirmed `100644` persisted in the v1.9.3 commit.

### Lesson (for future mode-fix releases)

`git add` re-reads filesystem mode and CLOBBERS any prior `git update-index --chmod=+x`. Correct patterns: EITHER (a) `chmod +x` the working-tree file first, THEN `git add`, OR (b) use `git update-index --chmod=+x` alone (it stages the mode; commit can follow without a subsequent `git add` on the same file). Never both in sequence — `add` wins.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.4. The correctly-moded hook file reinstalls at `100755`, SessionStart hook actually executes, `/core:start` auto-runs, CLAUDE.md governance block lands.

## [1.9.3] — 2026-04-22

Executable-bit fix attempt — closes Finding #23 ("SessionStart hook: Permission denied"). **Note: v1.9.3 commit actually recorded mode 100644 due to `git add` clobbering the `update-index` mode change; v1.9.4 is the real fix.**

### Fixed

- `hooks/sessionstart-auto-activate.sh` mode now `100755` (was `100644`). Claude Code invokes hook scripts as executables; without the execute bit, the hook silently fails with `Permission denied` and `/core:start` never auto-runs — so v1.9.2's CLAUDE.md injection never fires for installer-driven installs. This patch makes the hook actually executable.
- `website/install.sh` mode now `100755` (was `100644`) as belt-and-suspenders; installer already works via `curl | bash` (piped to bash stdin, doesn't need +x) but explicit +x lets users download-then-run (`bash install.sh` or `./install.sh`).

### Rationale

Subagent that landed v1.8.0 (SessionStart hook registration) flagged `chmod +x` as "MANUAL FOLLOW-UP" — never done. v1.9.2's 10-test integration matrix passed because tests invoke scripts via `bash path/to/script.sh` (which doesn't need +x) — but Claude Code's real hook loader calls scripts as executables, requires +x. Test-harness gap, captured as a new dogfood finding for the next test-matrix iteration: verify file modes via `git ls-files -s`, not just functional invocation.

### Migration

Existing v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.3 and git propagates the new file modes. Fresh installs via `curl | bash` get the correct modes immediately.

## [1.9.2] — 2026-04-22

Governance injection — closes Finding #22 ("governance blocks don't fire on every turn").

### Fixed

- `/core:start` now writes `.claude/CLAUDE.md` with a marker-delimited Sutra-managed governance block containing Input Routing + Depth Estimation + Readability Gate + Output Trace templates. Claude Code loads CLAUDE.md as project system context on every session, so every response now emits governance blocks — fulfilling the sutra.os promise.
- Idempotent: re-running `/core:start` updates the managed block in-place (detected by `<!-- SUTRA GOVERNANCE ... -->` markers) without clobbering the user's other CLAUDE.md content.

### Rationale

v1.7.1 fixed alias collision. v1.8.0 wired auto-activation. v1.9.1 added identity stamping. Dogfood on 2026-04-22 revealed governance blocks still weren't emitting on every turn — Claude Code's Skill tool doesn't auto-invoke skills per turn; it fires skills on semantic match. Research question "top restaurants in Mumbai" had no semantic match to governance skills, so no blocks fired. The missing piece: instructing the LLM via CLAUDE.md (which IS loaded every session). v1.9.2 adds that injection.

### Migration

Existing v1.8.x / v1.9.x users: `claude plugin marketplace update sutra` pulls v1.9.2. Running `/core:start` in any project writes/updates the managed CLAUDE.md block. Existing CLAUDE.md content untouched — the block is marker-delimited and appendable. To opt out on a specific project: manually delete the block (between the SUTRA GOVERNANCE markers) from that project's CLAUDE.md.

## [1.9.0] — 2026-04-22

Identity stamping — know who's running the plugin. Backward-compatible, additive.

### Added

- **`lib/identity.sh`** — new library. `capture_identity <version>` emits a JSON object with git_user_name, git_user_email_hash (SHA-256[:16]), github_login, github_id, hostname_hash (SHA-256[:12]), os_name, os_version, os_pretty, arch, shell_name, locale, tz, captured_at, captured_by_version. Fallback chain: git global → git local → gh api → system GECOS → `$USER`. Every step best-effort; never fails a session. 3-second timeout on gh API calls.
- **`tests/unit/test-identity.sh`** — 10 unit tests covering JSON shape, required keys, hash field shapes, fallback when git+gh are unavailable, staleness detection.
- **`tests/integration/test-identity-stamp.sh`** — 7 integration tests: onboard stamps local JSON + cache, push stamps manifest on bare repo, 7d staleness gate holds, 8-day-old cache triggers recapture, emit-metric PII rejection still active (regression guard).

### Changed

- **`scripts/onboard.sh`** — sources `lib/identity.sh`; when `telemetry_optin=true`, captures identity and stamps it into `.claude/sutra-project.json` > `identity:`. Also caches to `$SUTRA_HOME/identity.json` (chmod 600) for push-time staleness checks.
- **`scripts/push.sh`** — sources `lib/identity.sh`; on each push, checks cache freshness (`identity_is_stale`, default 7 days). Stale or missing → recapture. Stamps the identity block into `clients/<install_id>/manifest.json` alongside existing `push_count` / `last_seen` / `sutra_version` fields. **Retroactive for existing installs** — next push after upgrade stamps the identity block without requiring a re-onboard.

### Privacy

- **Metrics channel unchanged.** `emit-metric.sh` still regex-rejects PII in `dept`/`metric`/`unit`/`window` fields (regression-tested). Telemetry `*.jsonl` rows remain PII-free.
- **Identity channel is a new, separate channel** living in `manifest.json`. Activated by existing `telemetry_optin` (default `true` when `/core:start` runs with `profile=project|company`, default `false` with `profile=individual`). Flip `telemetry_optin: false` in `.claude/sutra-project.json` to turn OFF — effect is immediate; next push omits identity.
- **Fields captured are user-supplied** (git config, gh auth) or coarse machine metadata (os, arch, tz). Raw email and raw hostname are NOT captured — both are SHA-256 hashed to 16/12 hex chars. See PRIVACY.md for full matrix.

### Rationale

Founder direction 2026-04-22 — needed a fleet view of Sutra users (portfolio + external friends who install via marketplace). Prior manifest carried only hashed install_id + project_id, leaving new installs unidentifiable. v1.9.0 closes that gap with a separate, opt-in-by-default identity channel that preserves the existing PII-free posture of the metrics channel.

Design doc (asawa-holding repo): `holding/research/2026-04-22-sutra-identity-capture-v17-design.md`.

### Migration

- Existing users: `claude plugin marketplace update sutra && claude plugin update core@sutra`. Next Stop-hook auto-push stamps identity. No manual action required.
- Users who had `telemetry_optin: false` stay unstamped until they flip the flag. No behavior change for them.
- Downstream companies (DayFlow, Billu, etc. — when plugin-installed): inherit on next auto-update.

## [1.8.0] — 2026-04-22

One-command install — closes the last mile of "one command does everything."

### Added

- **`hooks/sessionstart-auto-activate.sh`** — REGISTERED in `hooks.json` (sibling of `update-banner.sh` on SessionStart). Fires on every session start; ACTS only when the sentinel `~/.sutra/installed-via-script` exists AND the current project has no `.claude/sutra-project.json`. Runs `sutra start` via absolute `${CLAUDE_PLUGIN_ROOT}/bin/sutra` (Finding #12-safe), deletes sentinel on success (one-shot), never blocks session start (trap + `exit 0`).
- **`website/install.sh`** — committed in v1.7.1, now operative. Serves from GitHub raw at `https://raw.githubusercontent.com/sankalpasawa/sutra/main/website/install.sh`. No Vercel, no third-party deploy.

### Changed

- **User-facing install flow collapses from 4 commands to 1.** Previous: `claude plugin marketplace add` → `claude plugin install` → `/reload-plugins` → `/core:start`. New: `curl -fsSL <raw-url> | bash` → open `claude` → first session auto-activates.

### Rationale

Founder direction 2026-04-22 (memory `project_sutra_permissions_in_start.md`): "one command should do everything — no 4-step ceremony." v1.7.1 shipped the prerequisite (alias-collision fix, Finding #12). v1.8.0 completes the vision.

### Migration

- Existing v1.7.x users: `claude plugin marketplace update sutra` pulls v1.8.0. The new SessionStart hook is a no-op for already-activated installs (sentinel gate). Fresh installs via `curl | bash` get auto-activation on first `claude`.

## [1.7.1] — 2026-04-22

Shell-alias collision fix (Codex-converged Option E).

### Fixed

- **All internal `!sutra <sub>` invocations in `commands/*.md`, `scripts/*.sh`, and `hooks/*.sh` now use absolute plugin-root paths (`${CLAUDE_PLUGIN_ROOT}/bin/sutra <sub>`).** Shell aliases, functions, or PATH-shadowing `sutra` binaries can no longer intercept plugin self-invocation. Fixes dogfood Finding #12 (P0 shipping blocker, 2026-04-22).
- Regression test `tests/integration/test-alias-collision.sh` reproduces the founder-observed collision (alias hijacks the plugin's `sutra start` call and redirects into an unrelated project) and asserts activation still succeeds.

### Rationale

Initial diagnosis (`design/2026-04-22-sutra-cli-collision.md`) favored renaming `bin/sutra` → `bin/sutra-core` (Option A) plus a runtime `type -a` self-check (Option D). Codex challenge (`design/2026-04-22-sutra-cli-collision-codex-consult.md`) revealed Option D is conceptually wrong as a *runtime* safety layer — if the user's alias wins shell name resolution, the plugin binary never executes, so the self-check never fires. Option E closes the bug class for *any* name collision (not only `sutra`), ships as a patch with zero breaking changes, and touches ~15 files instead of ~35.

## [1.7.0] — 2026-04-22

C3c token-compression bundle — Tokens charter per-turn cost-component cut.

### Added

- **RTK auto-rewrite whitelist (native tools)** — `hooks/rtk-auto-rewrite.sh`. PreToolUse(Bash) hook that blocks unprefixed voluminous git commands and forces `rtk <cmd>` wrap. Whitelist v2: `git status`, `git log`, `git diff`, `git blame`, `git show`. Typical reduction 30-60% on wrapped commands (measured on Asawa repo). Kill-switch: `touch ~/.rtk-disabled` or `RTK_DISABLED=1`.
- **MCP output compression (all MCP tools)** — `hooks/posttool-mcp-compress.sh`. PostToolUse hook matched on `mcp__.*` that REPLACES large MCP outputs via `hookSpecificOutput.updatedMCPToolOutput` with a head+error+tail compressed summary. Thresholds: size ≥ 4000 bytes AND line count ≥ 80. Smoke-tested: 5,099-byte playwright snapshot → 2,583 bytes (49% cut). Telemetry at `.enforcement/c3c-compress.jsonl`. Codex-verified mechanism + docs-verified (code.claude.com/docs/en/hooks). Kill-switch: `touch ~/.c3c-disabled` or `C3C_DISABLED=1`.

### Changed

- `hooks/hooks.json` registers the two new hooks — RTK on PreToolUse(Bash), MCP-compress on PostToolUse(matcher `mcp__.*`).

### Rationale

Founder direction 2026-04-22: "don't change what I write — find background optimizations for the printing part." Output tokens can't be compressed post-generation, but TOOL OUTPUT Claude reads CAN be compressed before entering context. Native-tool track uses PreToolUse command rewriting via RTK; MCP-tool track uses PostToolUse output replacement. Paired commits ship them as one OS bundle.

### Migration

- Existing v1.6.x users: `claude plugin marketplace update sutra` picks up both hooks automatically. No config change required.
- Both hooks have individual kill-switches if needed: `~/.rtk-disabled` disables native; `~/.c3c-disabled` disables MCP.

## [1.6.0] — 2026-04-22

Per-profile enforcement + hard-block mode + release channels.

### Added

- **User profiles** — plugin.json `userConfig.profile` accepts `individual`, `project`, or `company`. Claude Code prompts at enable time. Writes to `.claude/sutra-project.json`.
- **Profile-dependent telemetry default** — `individual` = off (privacy default), `project` = on, `company` = on.
- **Hard enforcement on `company` profile** — `hooks/depth-marker-pretool.sh` reads the profile and exits 2 (blocks the tool call) when the depth marker is missing, ONLY for `company` profile. `individual` and `project` stay warn-only.
- **Escape hatch** — `SUTRA_BYPASS=1 <cmd>` prefix skips the depth check for one tool call, even on `company`. Audit trail preserved via existing routing-misses log.
- **Release channels** — two marketplace branches on the repo:
  - `main` branch = **latest** (current behavior; auto-updates push new versions immediately)
  - `stable` branch = **stable** (promoted manually once a version is proven in portfolio use)
  - Users pick: `claude plugin marketplace add sankalpasawa/sutra` (latest) or `claude plugin marketplace add sankalpasawa/sutra@stable` (stable).

### Changed

- `/core:start` accepts `--profile individual|project|company` and also reads `CLAUDE_PLUGIN_OPTION_PROFILE` env var that Claude Code injects from userConfig.
- Activation banner now shows the active profile + enforcement mode.

### Migration

- Existing v1.5.x users: no action needed — `/core:start` on v1.6.0 defaults to `project` profile which preserves current warn-only behavior and telemetry-on default.
- To opt into hard enforcement: `/core:start --profile company`.
- To opt into privacy-default: `/core:start --profile individual`.

### Rationale

Founder direction 2026-04-21: "do 14, 15, 16, 17" — collapse P3 items into one profile-aware release. Per-profile defaults (#15) enables hard enforcement (#14) without breaking casual users. Release channels (#16) shipped as a parallel git-branch pattern so stable adopters can pin without affecting latest-chasing early users. Smoke-tested: company profile exits 2 on missing marker; individual/project stay warn-only exit 0.

## [1.5.1] — 2026-04-22

### Added

- **`session-retrieve` skill** — recovers abruptly-closed Claude Code sessions after laptop shutdowns, kernel panics, or API timeouts. Scans `~/.claude/projects/*.jsonl` for orphan signatures (explicit `API Error` OR silent mid-`tool_use` deaths), returns `claude -r <id>` resume commands with correctly-decoded project roots.
- CATALOG.md §7b "Skills (by LLM interactive surface)" — new taxonomy section. Skills organized by the harness they run in (Terminal / Desktop / Web / SDK). Terminal subsection contains all 5 plugin skills; other surface subsections reserved for future.
- Trigger phrases for the skill: "figure out past sessions", "what sessions got killed", "my laptop switched off — what was I working on", "find my crashed sessions", etc.

### Why it exists

Session-retrieve was built after a laptop shutdown lost 5 mid-flight sessions. The manual recovery took ~15 min of jsonl grepping and two wrong `claude -r` attempts (wrong project root). Skill encodes the deterministic procedure: detect both orphan flavors, decode the project slug for resume (never use the `cwd` field — #1 failure mode), dedupe shared roots, and output a readability-gate compliant report.

## [1.5.0] — 2026-04-21

Plugin renamed `sutra` → `core` within the `sutra` marketplace, plus permission-prompt transparency.

### Added

- `PERMISSIONS.md` — complete, auditable list of every Bash and Write permission the plugin needs, grouped by purpose, with a paste-ready allowlist.
- `/core:permissions` (+ `sutra permissions` in terminal) — prints the exact JSON snippet to paste into `.claude/settings.local.json`. One paste, zero further prompts.

### Changed (BREAKING — plugin identifier rename)

- Plugin name `sutra` → `core`. Install is now `claude plugin install core@sutra`. Slash commands move to `/core:*` namespace.
- Marketplace name stays `sutra`. Install pattern: `core@sutra` reads as "core plugin from the sutra marketplace" (Anthropic's standard "hub + product" naming pattern, same shape as `superpowers@claude-plugins-official`).
- All docs + scripts + command files updated: `/sutra:start` → `/core:start`, `sutra@sutra` → `core@sutra`.
- Binary kept as `sutra` — terminal users still type `sutra start`, `sutra status`, etc. Slash commands use `/core:*` because Claude Code namespaces by plugin name.

### Migration for existing users

Claude Code treats the rename as a different plugin (not an update). Users on v1.4.x must:

```
claude plugin uninstall sutra@sutra
claude plugin marketplace update sutra
claude plugin install core@sutra
/core:start
```

v1.5.0 cannot auto-migrate because the plugin identifier changed. Sorry.

### Rationale

Founder direction 2026-04-21: "core@sutra" — collapse the visual stutter in `sutra@sutra` by adopting the multi-plugin marketplace naming pattern. Marketplace name remains "sutra" so future plugins (e.g., `sutra-lite`, domain-specific variants) can sit alongside `core` under the same hub.

## [1.4.0] — 2026-04-21

Radical UX simplification: **one command does everything.**

### Added

- `/sutra:start` — THE one command. Onboards the project, enables telemetry, prints the activation banner, writes a depth marker. Everything a new user needs in one invocation.
- `/sutra:update` — slash-command front-end for `claude plugin marketplace update sutra && claude plugin update sutra@sutra`.
- `/sutra:uninstall` — slash-command front-end for `claude plugin uninstall sutra@sutra`. Accepts `--purge` to also wipe `~/.sutra/`.
- `scripts/start.sh` — merged flow from prior `go.sh` + depth-marker init + richer activation banner.

### Removed (BREAKING)

- `/sutra:onboard` — merged into `/sutra:start`.
- `/sutra:go` — merged into `/sutra:start`.
- `/sutra:sutra` — activation banner now emitted by `/sutra:start`.
- `/sutra:push` — auto-push runs on Stop event; manual push moved to power-user CLI (`sutra push`).

### Changed

- `bin/sutra` collapsed to four lifecycle verbs: `start / status / update / uninstall`. `push / onboard / go / leak-audit / install-shell-helpers / version / help` kept as secondary callable subcommands for power users and shell helpers.
- Telemetry default: `/sutra:start` sets `telemetry_optin = true`. Users who want privacy can edit `.claude/sutra-project.json` post-run; `PRIVACY.md` documents the flip.

### Rationale

Founder feedback 2026-04-21: "Users don't have to do multiple things — keep it start and we do the entire install and everything." Six user-facing slash commands collapsed to five, with one clear entry point.

### Migration

- Anyone who typed `/sutra:onboard` or `/sutra:go` — use `/sutra:start` instead.
- Shell helpers: `sutra-go` will be removed in v1.5; `sutra-start` alias coming in a shell-helper patch.

## [1.3.1] — 2026-04-21

User-facing polish around v1.3.0's breaking rename.

### Added

- `hooks/update-banner.sh` — SessionStart hook prints a one-time banner when the plugin version changes (e.g., after auto-update), with a link to CHANGELOG. Silent on first run and unchanged-version runs. Writes state to `~/.sutra/last-seen-version`.
- `PRIVACY.md` — explicit statement of what's collected and never collected. Default `telemetry_optin = false`. Third-party destinations: none.
- `VERSIONING.md` — SemVer policy explaining when we bump MAJOR / MINOR / PATCH, the v1.3.0 rename exception, yanking procedure, and release-channel roadmap.

### Rationale

v1.3.0's command rename was breaking for anyone running an older version. Without a banner, users would silently hit "unknown command" on `/sutra:sutra-onboard`. The banner now surfaces the update + links CHANGELOG so the migration is discoverable.

## [1.3.0] — 2026-04-21

Permission-prompt reduction + command namespace cleanup.

### Added

- `bin/sutra` unified dispatcher — single executable replacing six script invocations. Claude Code auto-adds plugin `bin/` to PATH, so `sutra onboard`, `sutra push`, etc. run as bare commands (no Bash permission prompts per distinct script path).

### Changed

- **Command rename (BREAKING)** — `/sutra:sutra-onboard` → `/sutra:onboard`, `/sutra:sutra-push` → `/sutra:push`, `/sutra:sutra-status` → `/sutra:status`, `/sutra:sutra-go` → `/sutra:go`. Drops redundant `sutra-` prefix now that Claude Code namespaces commands as `plugin:command`.
- All command files now invoke `!sutra <sub>` instead of `!bash ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.sh`. Single permission scope.

### Migration

- Auto-update will pull new command files. Old slash commands (`/sutra:sutra-onboard` etc.) stop working; use the new names.
- First use of `sutra` bare command may surface one permission prompt per session depending on Claude Code version — one allow covers all subcommands.

## [1.2.1] — 2026-04-21

Brand-leak scrub before external launch.

### Fixed

- `plugin.json` description: removed an internal brand reference; now reads "local metric telemetry".
- `ARCHITECTURE.yaml`: internal operator paths replaced with abstract `<operator>/` placeholders.

### Added

- `marketplace/design/2026-04-21-first-run-walkthrough.md` — T+0 → T+60s scripted experience (CM3).
- Plugin leak audit now PASSES; official `claude plugin validate` PASSES.

## [1.2.0] — 2026-04-20

Per-session tool telemetry.

### Added

- `hooks/posttool-counter.sh` — PostToolUse hook tracks which tools ran per session, writes to `$SUTRA_HOME/sessions/<session_id>.counters`.
- Stop hook extended — `flush-telemetry.sh` reads session counters, emits `tool_uses_session`, `skill_uses_session`, `write_uses_session`, and related metrics; cleans up counter file after emit.
- `ARCHITECTURE.yaml` as structured source of truth (v1.0.0) — components, flows, identities, privacy matrix.

## [1.1.4] — 2026-04-20

Shell-helper installer.

### Added

- `scripts/install-shell-helpers.sh` — appends `sutra-go` / `sutra-uninstall` / `sutra-reset` / `sutra-status-global` one-word commands to user's `~/.zshrc` or `~/.bashrc`. Idempotent.
- README install flow updated for new-laptop users.

## [1.1.3] — 2026-04-19

Auto-push on Stop.

### Added

- `hooks/flush-telemetry.sh` — fire-and-forget async push on Stop event if `telemetry_optin=true`. Never blocks session teardown.

### Changed

- Per codex review: Stop hook stays light — local file writes only, no synchronous network or git.

## [1.1.2] — 2026-04-19

### Added

- `/sutra:sutra-go` — one-shot onboard + telemetry ON command.

## [1.1.1] — 2026-04-19

Plugin observability auto-emission.

### Added

- `flush-telemetry.sh` auto-emits three metrics on Stop: `sessions.session_stops_total`, `os_health.queue_depth_at_stop`, `os_health.depth_marker_present`.
- Analytics collector (operator-side) reads plugin telemetry rows and rolls up per-metric count + median.

## [1.1.0] — 2026-04-18

Layer-B metric telemetry.

### Added

- `lib/project-id.sh` — deterministic install_id (sha256 HOME+version) + project_id (sha256 git remote).
- `lib/queue.sh` — local metric queue at `~/.sutra/metrics-queue.jsonl`; rotates at 10k lines.
- `hooks/emit-metric.sh` — Layer B writer: validates numeric values, rejects PII in string fields, appends to queue.
- `commands/sutra-onboard.md` — first-time project setup writing `.claude/sutra-project.json`.
- `commands/sutra-push.md` — manual push to `sankalpasawa/sutra-data` (opt-in gated).
- `commands/sutra-status.md` — local state inspector.

## [1.0.0] — 2026-04-18

First production release. Outcome-tested.

### Added

- Outcome test suite at `tests/outcome/` — install, activation, enforcement, commands, update, logging, leak-audit as black-box scripts.
- Hooks shift from warn-only to structured: `depth-marker-pretool.sh` logs violations; `estimation-stop.sh` writes session log.

## [0.2.0] — 2026-04-19

Unified deploy.

### Changed

- Plugin strips shadow skills (they duplicated dispatcher logic) and becomes a thin bridge that invokes `npx github:sankalpasawa/sutra-os init` on first `/sutra`.

## [0.1.0] — 2026-04-18

First release. Minimum viable plugin for functional validation.

### Added

- Skills: `input-routing`, `depth-estimation`, `readability-gate`, `output-trace`
- Commands: `/sutra`, `/depth-check`
- Hooks: `depth-marker-pretool` (warn-only, PreToolUse Edit|Write), `estimation-stop` (Stop event logger)
- Audit script: `scripts/leak-audit.sh` (brand-leak mechanism)
- MIT license

### Known limitations

- Hooks warn rather than block. Hard enforcement deferred to v0.2.
- No per-profile defaults yet (individual / project / company).
- Estimation log is session-local, not cross-session.
