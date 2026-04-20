# Sutra — TODO

## GTM / Marketplace — License Review Before External Launch (MAJOR)

**Founder direction 2026-04-20**: "Asawa is a personal project for now, so it's fine. [Use token-optimizer for now]. This is a to-do when we fully launch it to external clients. This is a major to-do of GTM or somewhere in Sutra."

Before Sutra marketplace publishes to external users, OR before any portfolio company (DayFlow/Maze/PPR/Paisa) ships with token-optimizer as a transitive dep, audit license compatibility.

### Checklist (must complete before Sutra v2.0 external launch / first paid client)

- [ ] **token-optimizer** (alexgreensh/token-optimizer) — PolyForm Noncommercial 1.0.0. For personal use (current Asawa) OK. For commercial distribution via Sutra marketplace: need commercial license from Alex Greenshpun. Action: email with use-case, get quote/terms.
- [ ] Sweep all plugins/hooks bundled in Sutra marketplace for noncommercial-only or GPL-incompatible licenses. Record in a LICENSE-AUDIT.md.
- [ ] Every external-facing Sutra component (plugin, skill, hook) must have a clear LICENSE + ATTRIBUTION statement.
- [ ] Define Sutra's own license (commercial? dual-license? open core?) before first paid deployment.
- [ ] Privacy/telemetry audit — Analytics Dept `TELEMETRY-CONTRACT.md` rules apply to any bundled tool.

### Why this is GTM-critical

Shipping noncommercial-licensed deps in a commercial product = legal exposure. Different from using them internally as a solo dev. The switch happens at FIRST PAID OR EXTERNAL DEPLOYMENT — catch it before, not after.

### Linked

- License finding: `holding/research/2026-04-20-token-optimizer-i2-spike.md` §4
- Adoption: `holding/research/2026-04-20-token-optimization-w1-before-after.md` §5
- Marketplace: `sutra/marketplace/`

---

## Charter: Tokens (Q2 2026, created 2026-04-20)

**File**: `os/charters/TOKENS.md` — full charter with KRAs, KPIs, OKRs, roadmap
**DRI**: Sutra-OS · **Contributors**: Analytics, Engineering, Operations
**Why**: Unmeasured governance overhead; founder direction "A lot of tokens have been used; we need to find some optimization ways."

### W1 (due 2026-04-26) — Measurement

- [ ] Define `token-telemetry.jsonl` schema; extend `holding/departments/analytics/TELEMETRY-CONTRACT.md` (Analytics, KR1, 2026-04-23)
- [ ] Write `holding/hooks/session-token-snapshot.sh` (SessionStart) — capture boot context size per company (Engineering, KR1, 2026-04-23)
- [ ] Extend `holding/hooks/dispatcher-stop.sh` to emit `task_end` events with governance-vs-work categorization (Engineering, KR1, 2026-04-24)
- [ ] Deploy hooks + telemetry into 6 companies (Sutra, Asawa, DayFlow, Maze, PPR, Billu) via god mode (Sutra-OS, KR1, 2026-04-25)
- [ ] Collect 10+ sessions per company; publish `holding/research/2026-04-26-token-baseline.md` (Analytics, KR1, 2026-04-26)

### W2–W4

- [ ] Rank 7 hypothesis cuts against baseline data; select top 3 (Sutra-OS, KR2, 2026-04-29)
- [ ] Draft TOKEN-BUDGET-PROTOCOL (candidate PROTO-019); add to `state/system.yaml` (Sutra-OS, KR2+KR3, 2026-05-01)
- [ ] Ship cut #1 (MEMORY.md indexed retrieval) — pilot DayFlow first (Engineering, KR2, 2026-05-07)
- [ ] Ship cuts #2–3 (L1 block compression; CLAUDE.md split) (Engineering, KR2, 2026-05-21)
- [ ] Add per-session + per-task budget alerts to Analytics Pulse (Analytics, KR3, 2026-05-28)
- [ ] Propagate charter + mechanisms via `upgrade-clients.sh` to Asawa, DayFlow, +1 (Sutra-OS, KR4, 2026-06-10)
- [ ] Q2 review: score KRs, decide Q3 continuation (Sutra-OS, 2026-06-30)

### Related meta-work (founder direction 2026-04-20)

- [ ] Formalize the unit-architecture model (every unit = definition charter + skills + initiative charters) as PROTO-019 (candidate). Current sketch lives in `os/charters/README.md` sections 1–4.
- [ ] Formalize `ADDING-DEPARTMENTS.md` protocol (sketch in charters README section 4)
- [ ] Audit existing departments for charter + skills + participation completeness (exemplar: `holding/departments/analytics/`)
- [ ] Extend `state/system.yaml` schema to register charters as first-class objects (currently registered only in OKRs.md prose)

---

## Restructure: Separate Problem-Solving from Implementation Bureaucracy

**Source**: Maze F7 Optional Auth — full SUTRA pipeline run (2026-04-05). CEO feedback: "We don't need to follow a process if we directly know the answer."

**The Problem**: Sutra conflates two distinct things:

1. **Problem-solving process** — forcing you to think through edge cases, risks, practice impacts, security implications BEFORE writing code. This is the thinking layer. It earned its keep on F7 (caught a real RLS security hole).

2. **Implementation bureaucracy** — writing INTAKE.md, SHAPE.md, SPEC.md files on disk, compliance gates between stages, artifact depth by tier, practice sign-off tables. This is the paperwork layer. It added zero value for trivial features (privacy policy = 28 audit FAILs on process, but the code was fine).

**The Principle**: If you know the answer, just do it. Process should only trigger when the problem is genuinely ambiguous, risky, or cross-cutting.

**The Deeper Problem**: The process doesn't know WHERE you're entering the problem lifecycle. Every problem goes through stages:

```
1. IDENTIFY  — recognize there IS a problem ("users lose preferences when clearing cookies")
2. ANALYZE   — understand the problem deeply ("affects retention, touches auth, sessions, RLS")
3. DESIGN    — figure out WHAT to build ("magic link, session migration, scoped RLS")
4. IMPLEMENT — build it
```

But these stages don't all happen in the same session or by the same person. F7 auth was IDENTIFIED in the HOD meeting. It was ANALYZED when the CPO/CEO prioritized it. By the time it reached the build session, stages 1-2 were already done — they exist in meeting notes (`os/meetings/`), in the INTAKE, in the TODO priority order.

The current SUTRA pipeline forces you to re-document stages that already happened upstream. The INTAKE for F7 was essentially restating what the HOD meeting already decided. The process should detect: "this problem was already identified and analyzed — pick up from DESIGN."

**The principle**: decisions need to be traceable (you should be able to find WHY something was decided), but the trace doesn't need to be a fresh artifact. It can be a pointer to where the thinking already lives — a meeting note, a TODO comment, a prior session's output.

### What to Restructure

- [ ] **Split process into thinking vs artifacts** — the thinking prompts (edge cases? RLS? sign-out path? practice impact?) are valuable. The mandatory file artifacts (INTAKE.md, SHAPE.md, SPEC.md as separate files with section requirements) are overhead when the answer is obvious.
- [ ] **Auto-route by complexity** — trivial/standard features go DIRECT with optional thinking prompts. Significant/horizontal features get the full problem-solving layer. The current complexity tiers exist but don't affect the process depth enough.
- [ ] **Kill artifact-as-compliance** — the compliance agent should check "did you think about X?" not "does SHAPE.md have a per-practice section?" Checking for thinking is valuable. Checking for word counts and section headers is bureaucracy.
- [ ] **Make the compliance agent problem-focused** — instead of "file exists? section exists? depth matches tier?", it should ask: "did you consider RLS implications? is there a rollback plan? what happens on sign-out?" Problem-solving questions, not format compliance.
- [ ] **Evidence from Maze F7**: SUTRA compliance caught 1 security hole, 1 incomplete migration, 2 scope gaps, 1 missing risk. All of these were *thinking* catches, not *artifact format* catches. The value was in the questions asked, not the documents produced.
- [ ] **Evidence from Maze INIT-0.1/0.2**: 28 FAIL verdicts on process compliance, but code quality was 7-8/10. The process was theater — auditing paperwork, not catching bugs. DIRECT mode would have shipped identical code faster.
- [ ] **Reconcile the three competing pipelines** into one that scales: minimal for trivial (just build), thinking-prompts for standard (are there edge cases?), full problem-solving for horizontal (per-practice analysis, compliance audit).
- [ ] **Detect lifecycle entry point** — when a task arrives, ask: "where in the lifecycle is this?" If IDENTIFY and ANALYZE are already done (HOD meeting decided priority, INTAKE exists), skip to DESIGN. If DESIGN is also done (SPEC exists from a prior session), skip to IMPLEMENT. Don't re-document what's already documented elsewhere.
- [ ] **Trace decisions with pointers, not duplicates** — instead of writing a fresh INTAKE that restates the HOD meeting, write: "See `os/meetings/2026-04-04-hod-q2-kickoff.md` — priority decided there. Problem: users lose preferences. Why now: retention is the bet." One paragraph pointing to the source of truth, not a re-creation of it.
- [ ] **Make org knowledge cumulative** — the HOD meeting notes, TODO priorities, feature INTAKEs, and session outputs should form a connected graph. Each artifact should reference where the upstream thinking lives. The process adds value by connecting existing knowledge, not by generating fresh paperwork that duplicates it.
- [ ] **Remove mandatory artifacts for trivial features** — a one-file bug fix does not need INTAKE.md + SHAPE.md + SPEC.md + VERIFY.md + LEARN.md. A commit message with "what and why" is sufficient.
- [ ] **Keep LEARN.md for ALL features** — the one artifact that consistently produced value across every feature, including trivial ones. The "every increment needs a decrement" insight from INIT-0.3 came from LEARN. Learnings compound; paperwork doesn't.

### When to Restructure

Now. This blocks the next version (v2.0). The current process creates friction that makes companies fake compliance instead of doing real thinking. That's worse than no process at all.

---

## Version Upgrade Pipeline (major — build when ready for multi-company upgrades)

When Sutra pushes a new version, existing companies can break. Every company has different tiers, stages, conventions, and file structures. A one-size-fits-all push will cause conflicts.

**Required capability: staged rollout with per-company compatibility testing.**

### The Pipeline

```
Sutra builds new version
    → Compile per company (tier-aware, not one-size-fits-all)
    → Dry run: diff new OS against company's current OS
    → Compatibility report per company (conflicts, breaking changes)
    → Resolve: auto-fix path differences, flag process conflicts for CEO
    → Push only clean updates to company repos
    → Verify: next session confirms hooks fire, no crashes
```

### What to Build

- [ ] **Per-company compiler** — takes Sutra version + Asawa framework + company config → produces company-specific bundle. Already conceptually defined in CLIENT-ONBOARDING.md Phase 7, but needs to handle UPGRADES not just first-time installs.
- [ ] **Diff engine** — compare new compiled OS against company's current OS. Flag: new files, changed files, removed files, hook conflicts, process conflicts.
- [ ] **Compatibility report generator** — for each company, produce a report: what changes, what conflicts, what needs manual resolution.
- [ ] **Auto-resolver** — handle simple conflicts automatically (path renames, config key additions, hook reordering).
- [ ] **Manual conflict protocol** — when auto-resolve can't handle it, produce a clear question for the company CEO: "New version adds X, but your setup has Y. Choose: A) adopt X and migrate Y, B) keep Y and skip X, C) custom."
- [ ] **Rollback mechanism** — if an upgrade breaks a company, revert to previous version. Git makes this possible (revert the commit), but the tooling should make it one command.
- [ ] **Version compatibility matrix** — track which companies are on which version, what's required for each upgrade path (v1.0→v1.1, v1.0→v2.0, v1.1→v2.0).
- [ ] **`/sutra-upgrade` command** — single command that runs the full pipeline for one or all companies.

### When to Build

Not now. Build this when:
- There are 3+ companies on different versions
- A version upgrade has broken a company at least once
- The manual push-and-pray approach becomes painful

### Current State
- Manual file copying works for 3 companies (DayFlow, Maze, PPR)
- All on v1.0/v1.1, minimal divergence
- No upgrade has broken anything yet (because upgrades are rare and manual)

---

## Feedback-Derived: Enforcement Gaps (from DayFlow 2026-04-06)

- [x] **Submodule boundary enforcement** — Boundary hook fails to block edits to git submodules because they share the parent repo's filesystem path. Agent edited `../sutra/` files from DayFlow session. Fix: check if target file is inside a git submodule (via `.gitmodules` or `git ls-files`), block with logged reason, allow only `asawa` role to bypass.
  - Source: dayflow/os/feedback-to-sutra/2026-04-06-boundary-hook-gap.md
  - RESOLVED: submodule detection added to enforce-boundaries.sh v2

- [x] **Depth block enforcement hook** — Agent executed ~15 tasks without a single depth assessment block. The depth system is documented but has zero enforcement. Fix: PreToolUse hook that checks if depth block was output before first Edit/Write on a task. Block and remind if missing.
  - Source: dayflow/os/feedback-to-sutra/2026-04-06-depth-block-skipped.md
  - RESOLVED: depth-enforcement-hook.sh + register-depth.sh created as standard Sutra module

- [x] **v1.7 missing infrastructure** — Four processes introduced in v1.7 require infrastructure that doesn't exist: (1) Finding Resolution Gate needs persistent finding storage schema, (2) LEARN phase needs protocol store with directory/format/retrieval, (3) Verification cron outputs logs but nothing reads them, (4) Sensitivity Map infrastructure from ENFORCEMENT-REVIEW.md is entirely undeployed (10 unchecked items). Fix: define standard infrastructure modules (`.claude/findings/`, `os/protocols/`, `.claude/logs/` standardization).
  - Source: dayflow/os/feedback-to-sutra/2026-04-06-v17-infrastructure-gaps.md
  - RESOLVED: 4 modules created (finding tracker, protocol store, depth hook, sensitivity deferred to v2)

- [x] **VERIFY hard gate for multi-finding audits** — Agent ran depth-5 visual QA, found 9 issues, fixed 8 fully but only partially fixed #2 (compound problem: overlay color + sheet height). Committed as complete. Founder caught the miss. Fix: at depth >= 4, require finding tracking IDs and block commits without resolution evidence for each finding. Add `interaction_frequency` as 6th sensitivity dimension.
  - Source: dayflow/os/feedback-to-sutra/2026-04-06-verify-gate-miss.md
  - RESOLVED: FINDING-TRACKER-TEMPLATE.md provides persistence for finding resolution gate

## Feedback-Derived: Process Gaps (from Maze 2026-04-04/05)

- [x] **Supabase org confusion** — MCP-connected accounts may not be the founder's personal accounts. External Resource Sovereignty Rule added to ENFORCEMENT.md.
  - Source: maze/os/feedback-to-sutra/2026-04-04-supabase-org-confusion.md
  - RESOLVED

- [ ] **Pipeline stress test: tracking sync + A/B exemptions** — Remaining open items from Maze pipeline stress test: (1) tracking sync — docs fall behind reality during build, need automated sync or post-commit reminder, (2) A/B test exemptions — bug fixes and infra tasks should be exempt from SUTRA/DIRECT alternation.
  - Source: maze/os/feedback-to-sutra/2026-04-05-sutra-pipeline-stress-test.md
  - PARTIALLY RESOLVED: v2 domain gate addresses pipeline modes, terminal check addresses VERIFY timing. These 2 items remain open.

## Feedback-Derived: Process Gaps (from Dharmik 2026-04-07)

- [ ] **Wait gate for parallel agents at depth 5** — Orchestrator compiled final SEO audit report before 4 parallel agents returned their findings. At depth 5 (exhaustive), the process should enforce a wait gate: no final compilation until all dispatched agents complete. Fix: add rule to depth 5 process — "if agents dispatched, block final deliverable until all return."
  - Source: projects/dharmik/os/feedback-to-sutra/001-wait-for-data.md
