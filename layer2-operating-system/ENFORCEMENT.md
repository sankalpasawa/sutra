# Sutra — Enforcement Protocol

## Relationship to Asawa Enforcement Framework

This document defines **process-specific** enforcement rules — what gets enforced, at what tier, for which protocols. The **universal enforcement mechanism** (how gates work, the hook API, override protocol, audit logging, deployment model) is defined in:

> `asawa-inc/holding/ENFORCEMENT-FRAMEWORK.md`

The **principles** that enforcement serves (natural language is intent, process is default, self-assessment, etc.) are defined in:

> `asawa-inc/holding/HUMAN-AI-INTERACTION.md`

Sutra compiles the rules from this document using the mechanism from the Asawa framework. Companies receive the compiled result as installed hooks.

---

## Default: Hard Enforcement

Every protocol in Sutra is HARD-enforced unless explicitly marked as soft. If a document says "do X," that means X is mandatory. Not a suggestion. Not a guideline. Mandatory.

## Complexity Tiers

Sutra OS is mandatory for all companies. The depth of enforcement scales with company complexity. See `CLIENT-ONBOARDING.md` Appendix A for the full protocol.

| Tier | Who | Enforcement depth |
|------|-----|-------------------|
| 1 (Personal) | Solo founder, no external users | Core OS mandatory. Metrics, compliance, shipping log scaled down. Hooks soft. |
| 2 (Product) | External users depend on it | Full OS minus department functions. Hooks hard for boundaries. |
| 3 (Company) | Team, revenue, or regulation | Full OS. Everything hard. Nothing optional. |

When evaluating compliance, check the company's tier first. A Tier 1 company missing a shipping log is compliant. A Tier 2 company missing one is not.

## How Enforcement Works

### Level 1: Document-Level Enforcement

Every Sutra document that contains rules must have an enforcement marker:

```
ENFORCEMENT: HARD — violations are blocked
ENFORCEMENT: SOFT — violations are flagged but allowed
ENFORCEMENT: FOUNDER-OVERRIDE — hard by default, founder can override
```

If no marker exists, the default is **HARD**.

### Level 2: Session-Level Enforcement

When a session starts for any company, the OS file is loaded. The OS file contains the protocols. The session MUST follow them.

**How to verify compliance:**

At the end of every feature (before shipping), the session runs a self-check:

```
COMPLIANCE CHECK:
- [ ] Did we follow the correct mode? (SUTRA/DIRECT per SUTRA-CONFIG.md)
- [ ] Did we log metrics? (METRICS.md updated)
- [ ] Did we write feedback? (feedback-to-sutra/ if anything was learned)
- [ ] Did we run the gstack skills specified by the mode?
- [ ] Did we stay within our file boundaries? (Session isolation)
- [ ] Did we follow the build order? (TODO.md priorities)
```

If any check fails, the feature CANNOT ship until resolved.

### Level 3: Pre-Commit Enforcement (Hooks)

These fire automatically before git commits:

| Hook | What It Checks | Blocks Commit? |
|------|---------------|---------------|
| File boundary | Edited files are within session's company scope | YES |
| Metrics logged | METRICS.md has an entry for this feature | YES (SUTRA mode only) |
| Mode compliance | Feature used the correct mode per SUTRA-CONFIG.md | YES |
| OS loaded | Session has read the company's OPERATING-SYSTEM file | YES |

### Level 4: Cross-Session Enforcement (Sutra Agent)

When Sutra runs its own session, it checks all clients:

| Check | Frequency | Action on Violation |
|-------|-----------|-------------------|
| Mode compliance | Every feature | Flag in Daily Pulse |
| Metrics logged | Every feature | Block next feature until logged |
| Feedback written | Weekly | Flag if no feedback in 7 days |
| OS version current | Monthly | Notify of available upgrade |
| Landing page exists | After deploy | Add to TODO if missing |

---

## Current Protocols and Their Enforcement Level

### CLIENT-ONBOARDING.md
| Rule | Enforcement |
|------|-------------|
| 8-phase process (no skipping) | HARD |
| Phase gates must pass before proceeding | HARD |
| Market research before shaping | HARD |
| Founder must DECIDE (Phase 4) before building | HARD |
| Landing page by default | FOUNDER-OVERRIDE (default yes) |
| Analytics before 100 users | HARD |
| Verify external account ownership before deploy (Phase 7) | HARD |
| No destructive actions on unverified resources | HARD |

### SESSION-ISOLATION.md
| Rule | Enforcement |
|------|-------------|
| Separate sessions per company | HARD |
| Level 2 hooks (file boundaries) | HARD |
| Level 3 directory isolation | HARD |
| Level 4 agent isolation (cross-company) | HARD |
| Level 5 fresh context (GSD) | SOFT (use judgment: independent tasks yes, interdependent no) |

### SKILL-CATALOG.md
| Rule | Enforcement |
|------|-------------|
| SUTRA mode uses full pipeline | HARD |
| DIRECT mode uses minimal pipeline | HARD |
| /canary after every deploy | HARD |
| /retro weekly | SOFT (but flagged if skipped 2 weeks) |

### VERSION-UPDATES.md
| Rule | Enforcement |
|------|-------------|
| Feedback written to feedback-to-sutra/ | HARD (after every incident, weekly otherwise) |
| Version update notice to clients | HARD (Sutra's job) |
| Client evaluates update | FOUNDER-OVERRIDE (can skip) |

### AGENT-INCENTIVES.md
| Rule | Enforcement |
|------|-------------|
| Metrics tracked per agent | HARD |
| Tension scenarios surfaced in Daily Pulse | HARD |
| Bypass tracking (when DIRECT used instead of SUTRA) | HARD |

### A/B-TEST-FRAMEWORK.md
| Rule | Enforcement |
|------|-------------|
| Alternating SUTRA/DIRECT per schedule | HARD |
| Metrics logged per feature per mode | HARD |
| Data decides mode after test completes | HARD |
| Founder can override at any time | FOUNDER-OVERRIDE |

---

## Infrastructure Isolation Rule

ENFORCEMENT: HARD (Tier 2+), SOFT (Tier 1)

**Principle**: Before running parallel infrastructure operations (deploys, DB migrations, CI jobs), verify they target different resources (project names, DB schemas, environments).

**Why**: Parallel deploys to the same platform can collide when directory or project names overlap, causing one deploy to overwrite another. This was discovered when two Vercel deploys from identically-named `website/` directories assigned the same project name.

**Checklist (before any parallel infra operation):**
1. Verify unique project name per deploy target
2. Verify unique domain or subdomain per deploy
3. Verify no collision with existing active deploys
4. For DB migrations: verify targeting different schemas or environments

**Tier behavior:**
| Tier | Enforcement |
|------|-------------|
| Tier 1 (Personal) | SOFT — flag if parallel operations detected, don't block |
| Tier 2 (Product) | HARD — block parallel operations unless isolation verified |
| Tier 3 (Company) | HARD — block + require written verification in deploy log |

---

## External Resource Sovereignty Rule

ENFORCEMENT: HARD (all tiers)

**Principle**: Before pausing, deleting, or modifying any external resource (Supabase projects, Vercel deploys, DNS records, third-party accounts), verify ownership — even when the founder has granted full autonomy.

**Why**: During Maze onboarding, Sutra paused a Supabase project on an MCP-connected account that wasn't the founder's. "Full autonomy" means autonomy over product decisions — it does NOT extend to destructive actions on resources whose ownership is unverified.

**Rules:**
1. MCP-connected accounts may not be the founder's personal accounts — verify before making changes
2. "Don't ask me anything" covers product decisions, NOT destructive infrastructure actions
3. Before pausing/deleting any external resource: confirm it belongs to this company
4. If uncertain about ownership, ask — this is never a violation of autonomy

**Checklist (before any external resource modification):**
1. Identify who owns the resource (which account, which org)
2. Confirm the resource belongs to this company, not a shared or different account
3. If the MCP-connected account has resources from multiple companies, do NOT touch resources that aren't explicitly this company's
4. Log the verification in the deploy log

**Tier behavior:**
| Tier | Enforcement |
|------|-------------|
| Tier 1 (Personal) | HARD — ownership verification always required |
| Tier 2 (Product) | HARD — ownership verification always required |
| Tier 3 (Company) | HARD — ownership verification + written confirmation |

---

## Adding New Protocols

When the founder adds a new protocol to Sutra:

1. Write it to the relevant document
2. Mark enforcement level: HARD, SOFT, or FOUNDER-OVERRIDE
3. If HARD: add it to the compliance check
4. Add validation task for existing clients: "validate against {company} next session"
5. Add to this file's protocol table

**Default is HARD.** If the founder doesn't specify, it's mandatory.

---

## Violation Handling

| Severity | Example | Action |
|----------|---------|--------|
| BLOCK | Skipping Phase 4 (DECIDE) | Cannot proceed. Must go back. |
| BLOCK | Editing another company's files | Hook blocks the edit. |
| FLAG | No feedback written this week | Daily Pulse highlights it. Decision needed. |
| FLAG | Skipped /canary after deploy | Added to next session's TODO. |
| LOG | Used DIRECT when schedule said SUTRA | Logged in A/B test metrics. Not blocked (founder has override). |

---

## Part 2: Enforcement Review Cadence + Adaptive Judgment

Enforcement rules decay without review. This section defines three review cadences (3-day, weekly, monthly) that keep enforcement rules calibrated, plus an adaptive sensitivity model that replaces file-count proxies with multi-dimensional scoring.

ENFORCEMENT: HARD -- the review cadence itself is mandatory. Missing a monthly calibration triggers a flag in Daily Pulse.

### Review Cadence

#### 3-Day Micro-Review (Automated)

Reads hook execution logs, counts blocked vs. allowed actions, overrides, and skipped compliance steps. Outputs a single paragraph appended to DAILY-PULSE.md. Zero human effort.

**Data source:** `.claude/logs/enforcement.jsonl`
**Trigger:** Every 3 days (SessionStart hook checks `last_micro_review` timestamp).

**Output format:**
```
### Enforcement Micro-Review (YYYY-MM-DD)
Last 3 days: {blocked_count} blocked, {allowed_count} allowed, {override_count} overrides. Top rule: "{hook_name}" fired {count} times. {override_sentence} Compliance score: {score}/100.
```

| Tier | Micro-review |
|------|-------------|
| 1 (Personal) | Off. Monthly calibration only. |
| 2 (Product) | On. Automated, appended to Daily Pulse. |
| 3 (Company) | On. Automated, appended to Daily Pulse. |

#### Weekly Enforcement Review

Part of the weekly review cadence (same session as /retro). Duration: 5-10 minutes.

**Checklist:**
1. **System working?** — Read last 2 micro-reviews. Blocked counts stable, rising, or falling?
2. **Rules bypassed?** — List overrides. Was each justified? If yes, rule may be too strict.
3. **Hooks too strict?** — >2 false positives this week? Flag for demotion.
4. **Hooks too loose?** — Any incidents that SHOULD have been blocked? Flag for promotion.
5. **New rule types needed?** — Draft but don't deploy yet (hold for monthly).
6. **Sensitivity accuracy** — Compare tier assignments vs outcomes. Record accuracy %.

#### Monthly Calibration

First session of the month. Blocking — complete before other work. Duration: 15-20 minutes.

**Calibration Decision Table:**

| Condition | Action |
|-----------|--------|
| Soft gate violated >3 times this month | PROMOTE to hard gate |
| Hard gate with 0 fires in 30 days | DEMOTE to soft gate |
| Hard gate with 0 fires in 60 days | REMOVE (dead rule) |
| Override used >2 times on same rule | Review: rule too strict or users undertrained? |
| New incident revealed uncovered area | ADD new rule (hard by default) |
| Sensitivity accuracy <70% | Recalibrate sensitivity scores |
| Sensitivity accuracy >90% | No changes needed |

| Tier | Monthly calibration |
|------|-------------------|
| 1 (Personal) | Required (simplified). |
| 2 (Product) | Required (full + sensitivity recalibration). |
| 3 (Company) | Required (full + cross-company comparison + dashboard). |

### Adaptive Judgment — Sensitivity Scoring

The sensitivity model replaces file count with multi-dimensional scoring. Each file path has a sensitivity score (1-10) computed from five dimensions:

| Dimension | Weight | Examples |
|-----------|--------|----------|
| Area sensitivity | 3x | auth/payment/migration = 9-10, UI components = 3-4, CSS = 1-2 |
| Blast radius | 2x | shared utility imported by 20+ files = 9, leaf component = 2 |
| Incident history | 3x | 0 past incidents = 0, 3+ incidents = 10 |
| Data sensitivity | 3x | PII = 10, financial = 9, credentials = 10, public = 0 |
| Coupling depth | 1x | cross-layer = 8, single-file = 1 |

**Composite score:** `raw = (area*3 + blast*2 + incidents*3 + data*3 + coupling*1) / 12`, clamped to [1, 10].

**Per-company sensitivity map:** `sensitivity.jsonl` in each company's `.claude/` directory.

| Score | Level | Enforcement behavior |
|-------|-------|---------------------|
| 1-3 | Low | Soft gates only. Standard commit flow. |
| 4-6 | Standard | Hard gates active. Compliance checklist runs. |
| 7-9 | High | Hard gates + mandatory self-review. Sensitivity reason surfaced. |
| 10 | Critical | Hard gates + founder notification. Cannot merge without approval. |

### Self-Improving Classification

When a change causes a bug: increase `incidents` dimension by 4 for affected paths. Same area has 2 incidents = locked at minimum 7 for 60 days. 3+ incidents = flag for architectural review.

**Judgment Inheritance:**
- **Asawa-level (universal):** Rules that apply to ALL companies (auth = minimum 7, migrations = 10, env files = 10). Cannot be overridden.
- **Company-level (local):** Specific to one company's codebase. Stay local, don't propagate.

**Accuracy targets:** >85% = well-calibrated, 70-85% = review misclassified areas, <70% = major recalibration needed.

### Hook Execution Log Format

All hooks write to `.claude/logs/enforcement.jsonl`:

```jsonl
{"timestamp": "ISO-8601", "hook": "hook-name", "action": "blocked|allowed|overridden|escalated|skipped_step", "file": "path-or-null", "role": "active-role", "reason": "string-or-null", "sensitivity_score": int-or-null, "session_id": "string"}
```

Retention: 90 days. Archive older logs to `.claude/logs/archive/`.

### Implementation Checklist

1. [ ] Create `.claude/logs/` directory structure in each company repo
2. [ ] Update hooks to write `enforcement.jsonl` entries
3. [ ] Create auto-seed script for `sensitivity.jsonl` initialization
4. [ ] Add micro-review logic to SessionStart hook
5. [ ] Add weekly review checklist to /retro skill
6. [ ] Add monthly calibration to session-start first-of-month check
7. [ ] Create `asawa-holding/holding/SENSITIVITY-RULES.md` with universal floor rules
8. [ ] Create dashboard generation script
9. [ ] Add sensitivity score lookup to pre-commit hooks
