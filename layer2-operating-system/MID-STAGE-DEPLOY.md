# Sutra — Mid-Stage Company Deployment Protocol

ENFORCEMENT: HARD — follow every step. No shortcuts.

## When This Applies

A company that already has code, conventions, and history — not a fresh onboarding.
Examples: DayFlow (400+ files, 17K lines, existing CLAUDE.md conventions).

## The 7 Steps (AUDIT → CLASSIFY → MAP → DEPLOY → VERIFY → ACTIVATE → LEARN)

---

### Step 1: AUDIT (read everything, change nothing)

Before touching any file, build a complete picture:

1. Read CLAUDE.md — all conventions, design principles, code quality rules
2. Read TODO.md — what needs building, what's blocked
3. Read the codebase structure — directory tree, key files, architecture
4. Read existing OS files — what Sutra infrastructure already exists
5. Read any deployment plan — what was planned but not executed
6. Identify fragile areas — files with known bugs, complex logic, technical debt
7. Identify security issues — auth, secrets, data access

**Output**: AUDIT-REPORT.md (the deep codebase understanding)
**Gate**: Cannot proceed until audit is complete. No code changes during audit.

---

### Step 2: CLASSIFY (determine tier and depth)

Based on the audit:

1. Classify complexity tier (1/2/3) using COMPLEXITY-TIERS.md criteria
2. Identify which departments are active (product, eng, design, security, etc.)
3. Determine which protocols are already followed (even informally)
4. Map existing conventions to Sutra protocols (CLAUDE.md rules → which PROTO-XXX?)

**Output**: Add tier + rationale to SUTRA-CONFIG.md
**Gate**: Tier must be declared before deployment begins.

---

### Step 3: MAP (align existing patterns to Sutra OS)

The company already has patterns. Don't replace them — align them:

1. Map existing CLAUDE.md conventions → Sutra principles (which principles are already followed?)
2. Map existing processes → Sutra processes (does the company already do standup? review? lifecycle?)
3. Map existing hooks → Sutra enforcement (which hooks are already installed?)
4. Identify GAPS: what Sutra offers that the company doesn't have
5. Identify CONFLICTS: where company conventions disagree with Sutra

**Key rule**: When a company convention conflicts with a Sutra protocol, the company convention wins UNLESS it creates a security or data integrity risk. The OS adapts to the company, not the other way around.

**Output**: DEPLOYMENT-MAP.md (what aligns, what's a gap, what conflicts)
**Gate**: Founder reviews conflicts and approves resolution for each.

---

### Step 4: DEPLOY (install what's missing, don't break what works)

Install only what the audit identified as gaps:

1. Deploy engines (estimation, adaptive protocol, enforcement review)
   - Create os/engines/ directory
   - Copy engine specs
   - Initialize logs (estimation-log.jsonl, routing-log.jsonl)
   - Seed sensitivity.jsonl from codebase scan (identify auth/, db/, env files)

2. Update version pin (SUTRA-VERSION.md → v1.3)

3. Add engine instructions to CLAUDE.md
   - Before every task: run estimation + routing
   - After every task: capture actuals
   - DO NOT change existing CLAUDE.md conventions — ADD the engine section

4. Verify boundary enforcement
   - Identity declared in CLAUDE.md? If not, add it.
   - enforce-boundaries.sh installed and registered? If not, install.
   - Run the 3 isolation tests (own repo PASS, other repo BLOCK, escape BLOCK)

**Key rule**: Deploy is ADDITIVE. Never remove or modify existing conventions, hooks, or files. Only ADD what's missing.

**Output**: Updated os/ with engines, logs, version pin
**Gate**: All 3 isolation tests pass. Existing hooks still work.

---

### Step 5: VERIFY (prove the deployment works without breaking anything)

1. Run all existing hooks — do they still fire correctly?
2. Run the boundary test suite — 3 tests must pass
3. Check existing processes — does the company's workflow still work?
4. Test one read-only operation through the engines:
   - Pick the top TODO item
   - Run estimation (generate table, don't build yet)
   - Run routing (score parameters, select depth, don't build yet)
   - Does the output make sense for this codebase?

**Output**: DEPLOY-VERIFY.md with test results
**Gate**: All tests pass. Engines produce sensible output. Nothing broken.

---

### Step 6: ACTIVATE (first real feature through the engines)

1. Pick the top P0 task from TODO.md
2. Run the full evolution cycle:
   - Estimate (with sensitivity map for this codebase)
   - Route (select depth based on the audit's fragility assessment)
   - Build at selected depth
   - Verify (evidence, not checkboxes)
   - Gap report (what worked, what was friction, what's missing)

3. Log to estimation-log.jsonl and routing-log.jsonl
4. Write gap report to holding/evolution/gap-reports/

**Output**: First feature shipped through engines + gap report
**Gate**: Feature ships without regression. Gap report written.

---

### Step 7: LEARN (what did the deployment teach us about Sutra?)

1. Was the deployment additive? (Did it break existing patterns?)
2. Did the engines produce useful output for this codebase type?
3. What Sutra protocols don't apply to this company type? (Mark as N/A)
4. What's missing from Sutra that this company type needs?
5. Feed learnings back: company feedback → Sutra → Asawa if principle-level

**Output**: DEPLOY-LEARN.md + feedback to Sutra
**Gate**: None — this is the end of deployment. Evolution cycles begin.

---

## Checklist Summary

- [ ] Step 1: Audit complete (AUDIT-REPORT.md)
- [ ] Step 2: Tier classified in SUTRA-CONFIG.md
- [ ] Step 3: Deployment map created (gaps + conflicts identified)
- [ ] Step 4: Engines deployed, version pinned, CLAUDE.md updated
- [ ] Step 5: All tests pass, engines produce sensible output
- [ ] Step 6: First feature shipped through engines
- [ ] Step 7: Deployment learnings fed back to Sutra

## Time Estimate

Steps 1-3: ~30 min (reading + analysis)
Steps 4-5: ~15 min (installation + verification)
Steps 6-7: ~30 min (first feature + gap report)
Total: ~75 min for a mid-stage company deployment
