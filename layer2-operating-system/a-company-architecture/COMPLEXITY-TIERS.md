# Sutra — Complexity Tiers

ENFORCEMENT: HARD — all companies must be classified. Tier requirements are mandatory.

## Principle

Sutra OS is mandatory for every company in the Asawa Inc. portfolio. The depth of implementation scales with the complexity of the company. A solo founder building a personal tool doesn't need the same process weight as a team shipping to thousands of users.

The OS is always present. The surface area changes.

## How to Classify

Complexity is determined by three factors:

| Factor | Low | Medium | High |
|--------|-----|--------|------|
| **People** | Solo founder, no team | 1-3 contributors | 4+ people or cross-functional |
| **Users** | Founder is the user (0 external) | 1-100 external users | 100+ users |
| **Stakes** | Personal tool, no revenue | Pre-revenue but external users depend on it | Revenue, contracts, or regulatory |

Score each factor. The highest factor determines the tier.

## The Three Tiers

### Tier 1: Personal — "Just me, just shipping"

*Solo founder building for themselves or a tiny audience. Hard deadline > perfect process.*

**Mandatory (non-negotiable):**
- Onboarding (8 phases — the thinking matters even for personal tools)
- Product brief (the bet, the user, the P0 features)
- Tech stack decision with rationale
- Architecture rules (even 3-5 rules prevent drift)
- Build order (what ships first and why)
- Categories/taxonomy (domain structure)
- TODO.md (single source of truth for what's next)
- Session isolation (don't contaminate other companies)
- Feedback to Sutra (even one insight per feature helps the OS evolve)

**Scaled down:**
- Metrics: track 2-3 success metrics, no shipping log required
- Process: single-track flow (need → build → test → ship). No mode switching.
- Compliance: self-check after every 3rd feature, not every feature
- Weekly check-in: optional (replace with "check TODO.md")
- A/B testing (SUTRA vs DIRECT): skip. Use whatever is fastest.
- Enforcement hooks: soft (flag, don't block)

**Skip entirely:**
- Department-level functions (one person = all departments)
- Agent incentives (no competing agents)
- Daily Pulse format
- Standup protocol

### Tier 2: Product — "Real users, real consequences"

*Small team or solo founder with external users depending on the product.*

**Everything in Tier 1, plus:**
- Shipping log (what shipped, when, what broke)
- Metrics with weekly review
- Compliance check before every deploy
- A/B testing for process improvement (SUTRA vs DIRECT mode)
- Quality function active (QA before ship, test on device/browser)
- Security function active (API keys, input sanitization, auth if needed)
- Feedback to Sutra after every incident or process gap
- Weekly check-in (brief, 5 minutes)

**Scaled down:**
- Enforcement hooks: hard for file boundaries, soft for metrics
- Standup: async, written, not a ceremony
- Department functions: product + engineering + quality active. Others as needed.

### Tier 3: Company — "Team, revenue, or regulation"

*Multiple contributors, external accountability, or regulatory requirements.*

**Full Sutra OS. Nothing optional.**
- All department functions active
- Hard enforcement on everything
- Agent incentives (competing perspectives)
- Daily Pulse
- Standup protocol
- Full compliance checks
- Incident response process
- Weekly planning process
- Decision-making process with logs

---

## Classification Table

| Company | Tier | Rationale |
|---------|------|-----------|
| PPR | 1 (Personal) | Solo founder, personal wedding tool, hard deadline, 0 external users |
| DayFlow | 2 (Product) | Solo founder but building for external users, pre-launch |

## When to Re-classify

Re-evaluate tier when:
- A new person joins the project
- The product gets its first external user
- Revenue starts flowing
- A regulatory or compliance requirement appears

Tier only goes UP, never down. Once you have external users, you don't go back to personal-tier process.

---

## How This Affects Onboarding

During Phase 1 (INTAKE), Sutra asks the 10 questions. After question 2 ("Who specifically uses this?"), Sutra classifies complexity:

- "Just me" or "my family" → Tier 1
- "A specific group of people" with < 100 expected → Tier 2
- Team, revenue model, or regulatory mention → Tier 3

This classification determines which OS features get generated in Phase 5 (ARCHITECT) and configured in Phase 6 (CONFIGURE).

## How This Affects Enforcement

| Enforcement aspect | Tier 1 | Tier 2 | Tier 3 |
|-------------------|--------|--------|--------|
| File boundary hooks | Soft (flag) | Hard (block) | Hard (block) |
| Metrics logging | Self-check every 3 features | Every deploy | Every commit |
| Compliance check | Every 3rd feature | Every deploy | Every deploy + pre-merge |
| Feedback to Sutra | After incidents or sessions | After every incident | After every incident + weekly |
| Shipping log | Optional | Required | Required |
| Mode compliance (SUTRA/DIRECT) | Skip — use fastest | Enforced per config | Enforced per config |
