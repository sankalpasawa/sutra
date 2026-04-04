# Sutra — Client Onboarding

## What This Is

The full process that takes a founder from "I have an idea" to "I have a running company with a deployed operating system." This is Sutra's core product. If this doesn't work, nothing works.

Sutra is not a template factory. It's a structured thinking partner that:
1. Extracts clarity from the founder's head
2. Validates the idea against market reality
3. Generates a custom OS fitted to the product type, platform, and stage
4. Deploys that OS so the founder can start building immediately
5. Learns from every client to improve the OS for future clients

---

## The Eight Phases

```
INTAKE → MARKET → SHAPE → DECIDE → ARCHITECT → CONFIGURE → DEPLOY → ACTIVATE
 (5 min)  (10 min) (10 min) (2 min)  (15 min)    (10 min)   (5 min)  (5 min)
```

Total: ~60 minutes from raw idea to building.

Each phase has: an INPUT, a PROCESS, an OUTPUT, and a GATE (must pass to proceed).

---

## Phase 1: INTAKE — Extract the Raw Idea

**Input**: Founder shows up with an idea (could be one sentence or a rambling vision)
**Process**: Sutra asks 10 questions. Founder answers in plain language.
**Output**: Intake Card
**Gate**: All 10 questions answered. If founder can't answer #6 (the bet), loop back.

### The 10 Questions

**Identity (who and what)**

1. **What is this?** One sentence. No buzzwords. If you need two sentences, you don't know yet.
2. **Who specifically uses this?** Not "everyone." One person. Give them a name. What's their day like?
3. **What job are they hiring this product to do?** (Jobs-to-be-done framing)

**Market (where it lives)**

4. **What do they do today instead?** The current alternative, even if it's "nothing" or "something hacky."
5. **Why is that not good enough?** What's broken, slow, frustrating, or missing?
6. **What's the bet?** Complete this sentence: "This works IF _____ is true. If not, it fails." This is the hypothesis. Everything else is decoration.

**Scope (what to build first)**

7. **What's the smallest version that tests the bet?** Not the dream. The experiment.
8. **What's the platform?** Web, iOS, Android, desktop, API, hardware? Why that one first?
9. **What does the founder know how to build?** (Skills determine tech stack constraints)

**Ambition (where it goes)**

10. **If this works, what does it become in 2 years?** This reveals whether the idea has legs or is a feature.

**Founder involvement (how you want to work)**

11. **How involved do you want to be?** Sutra adapts to your style.

| Level | What It Means | Sutra's Behavior |
|-------|--------------|-----------------|
| **Hands-on** | "I want to decide everything" | Sutra presents options, founder decides. No autonomous actions. |
| **Strategic** | "I decide direction, you handle execution" | Sutra makes execution decisions autonomously. Surfaces only strategic choices. |
| **Delegated** | "Just build it. Show me when it's done." | Sutra runs autonomously. Founder reviews output, not process. |

Default: **Strategic**. The founder always has override regardless of level.

### Output: Intake Card

```yaml
company: "{name}"
one_liner: "{what it is, one sentence}"
user_persona: "{specific person description}"
job_to_be_done: "{what they hire this to do}"
current_alternative: "{what they do today}"
switch_reason: "{why current solution fails}"
core_bet: "This works IF {hypothesis}"
first_version: "{smallest experiment}"
platform: "{web/ios/android/cross-platform}"
founder_skills: "{what they can build}"
two_year_vision: "{where it goes}"
```

### Example:

```yaml
company: "ExampleCo"
one_liner: "A {product type} that {solves this problem}"
user_persona: "{Name}, {age}, {role}. {Context}. {Need}."
job_to_be_done: "{What they hire this to do}"
current_alternative: "{What they do today}"
switch_reason: "{Why current solution fails}"
core_bet: "This works IF {hypothesis}"
first_version: "{Smallest experiment that tests the bet}"
platform: "{web/ios/android} ({why this platform first})"
founder_skills: "{What they can build}"
two_year_vision: "{Where it goes if it works}"
```

---

## Phase 2: MARKET — Validate Against Reality

**Input**: Intake Card
**Process**: Sutra researches the market. Not in isolation. Not guessing.
**Output**: Market Brief
**Gate**: At least 3 comparable products found. If none exist, that's either a blue ocean or a warning.

### What Sutra Researches

| Question | How | Why |
|----------|-----|-----|
| **Who else is doing this?** | Search for competitors, adjacent products | If 10 people tried and failed, understand why before repeating |
| **What's their business model?** | Look at pricing, monetization | Validates market willingness to pay |
| **What do users complain about?** | App Store reviews, Reddit threads, Twitter complaints | Reveals unmet needs — these are your features |
| **What's the market size?** | Back-of-napkin TAM | Not for investor pitch — to know if the bet is worth making |
| **What technical approaches exist?** | How do competitors build this? What APIs? | Don't reinvent. Use what works. Innovate where it matters. |

### Research Method

```
1. Web search: "{product type} app" — find top 5-10 competitors
2. Web search: "{competitor name} reviews" — find what users hate
3. Web search: "{product type} open source" — find existing codebases to learn from
4. Web search: "{core technology} API" — find best tools (e.g., joke APIs, humor datasets)
5. Synthesize: what's the gap? What do ALL competitors miss?
```

gstack skill: `/office-hours` (Startup mode — demand reality, status quo, desperate specificity)

### Output: Market Brief

```yaml
competitors:
  - name: "{competitor 1}"
    what_they_do: "{brief}"
    strengths: "{what they do well}"
    weaknesses: "{what users complain about}"
    business_model: "{how they make money}"
  - name: "{competitor 2}"
    ...

market_gap: "{what nobody does well}"
market_size: "{back-of-napkin TAM}"
technical_landscape: "{what APIs/tools exist}"
key_insight: "{the one thing that changes our approach}"
```

### Example:

```yaml
competitors:
  - name: "{Competitor 1}"
    what_they_do: "{brief}"
    strengths: "{what they do well}"
    weaknesses: "{what users complain about}"
    business_model: "{how they make money}"

market_gap: "{what nobody does well}"
market_size: "{back-of-napkin TAM}"
technical_landscape: "{what APIs/tools exist}"
key_insight: "{the one thing that changes our approach}"
```

---

## Phase 3: SHAPE — Turn Fuzzy Into Clear

**Input**: Intake Card + Market Brief
**Process**: Three shaping exercises informed by market research
**Output**: Shape Brief (one page)
**Gate**: PR/FAQ is compelling AND P0 list has ≤7 features AND risks have mitigations

### Exercise A: PR/FAQ Test

```
FOR {persona} WHO {job to be done},
{company name} IS A {category}
THAT {key benefit informed by market gap}.
UNLIKE {strongest competitor},
{company name} {differentiator from market research}.
```

Note: the PR/FAQ now uses MARKET data, not guesses. "Unlike Reddit" is informed by knowing Reddit's actual weakness.

### Exercise B: Feature Carve (market-informed)

| Feature | P0? | Market Signal | Build/Buy |
|---------|-----|--------------|-----------|
| ... | YES/NO | "Competitor X has this" or "Users complain about missing this" | Build from scratch / Use existing API / Adapt open source |

**P0 rule**: If removing it makes the core bet untestable, it's P0.
**Build/Buy column**: Sutra checks if an API, library, or open-source solution exists BEFORE deciding to build from scratch.

### Exercise C: Risk Map (market-informed)

| Risk | Likelihood | Market Evidence | Mitigation |
|------|-----------|----------------|------------|
| ... | H/M/L | "Competitor X failed because..." or "No evidence of this risk" | ... |

### Exercise D: Success Metrics Definition

What does "working" look like? Define before building.

| Metric | Target | How to Measure | When to Check |
|--------|--------|---------------|---------------|
| Primary metric (the bet) | {number} | {method} | Daily |
| Secondary metric | {number} | {method} | Weekly |
| Guardrail metric | {threshold} | {method} | On every deploy |

### Output: Shape Brief

One page containing: PR/FAQ, P0 feature list with build/buy decisions, risk map with market evidence, success metrics.

gstack skills: `/office-hours` → `/plan-ceo-review`

---

## Phase 4: DECIDE — Commit or Kill

**Input**: Shape Brief
**Process**: Founder answers three questions
**Output**: GO / RESHAPE / KILL
**Gate**: Explicit decision recorded

### The Three Questions

1. **Is the bet clear?** Can you explain the core hypothesis to a stranger in 10 seconds?
2. **Is the scope small enough?** Can you ship V1 in one focused week (or one session with AI)?
3. **Is it worth your time?** Knowing the market, knowing the risks, is this the best use of your next week?

| Answer | Action |
|--------|--------|
| YES to all 3 | → Phase 5: ARCHITECT |
| NO to #1 | → Back to Phase 3 (reshape the bet) |
| NO to #2 | → Back to Phase 3 (cut more features) |
| NO to #3 | → KILL. Document why. Archive the intake card. Move on. |

---

## Phase 5: ARCHITECT — Technical Foundation

**Input**: Shape Brief (approved)
**Process**: Sutra selects platform, tech stack, data model, deployment, and design approach
**Output**: Architecture Card
**Gate**: Every choice has a rationale. No "it depends" left.

This is where Sutra adapts to the SPECIFIC product. Different products need different architectures.

### 5A: Product Type Classification

```yaml
product_type: "{content-platform / productivity-tool / social-network / marketplace / saas / game}"
primary_value: "{what users get — content, utility, connection, transactions, capability}"
content_source: "{user-generated / curated / ai-generated / hybrid / none}"
interaction_model: "{consume / create / collaborate / transact}"
data_sensitivity: "{public / private / mixed}"
```

| Product Type | Primary Metric | Core Technical Challenge | Key Architecture Decision |
|--------------|---------------|------------------------|--------------------------|
| Content platform | Engagement (time, votes) | Content quality + freshness | Content pipeline (source → filter → rank → serve) |
| Productivity tool | Task completion, DAU | Data integrity, offline | Local-first, sync engine |
| Social network | DAU, viral coefficient | Cold start, moderation | Graph DB, feed algorithm |
| Marketplace | GMV, liquidity | Two-sided supply/demand | Search, matching, payments |
| SaaS | MRR, churn | Multi-tenancy, reliability | Auth, billing, admin |
| Game | Session retention, D7 | Engagement loop, balance | Game state, real-time |

### 5B: Platform & Tech Stack Selection

Sutra selects tech stack based on: product type, platform, founder skills, and stage.

**Web Products:**

| Layer | Default Choice | When to Use Alternative |
|-------|---------------|----------------------|
| Framework | Next.js (App Router) | Remix if heavy forms/mutations. SvelteKit if perf-critical. |
| Styling | Tailwind CSS | Styled-components if existing design system. CSS Modules if team preference. |
| Backend | Supabase (Postgres + Auth + Edge Functions) | Firebase if real-time-heavy. Custom if enterprise. |
| AI/LLM | Gemini (free tier) | Claude if complex reasoning. OpenAI if GPT-specific features. |
| Deploy | Vercel | Netlify if static-heavy. Fly.io if needs servers. Railway if needs background jobs. |
| Analytics | PostHog (add before 100 users) | Mixpanel if team knows it. None at MVP stage. |

**iOS Products:**

| Layer | Default Choice | When to Use Alternative |
|-------|---------------|----------------------|
| Framework | React Native (Expo) | Swift if performance-critical. Flutter if cross-platform needed. |
| State | Zustand | Redux if team knows it. Jotai if many independent atoms. |
| Local DB | SQLite (expo-sqlite) | Realm if complex queries. AsyncStorage if simple K-V. |
| Backend | Supabase | Firebase if real-time. Custom if enterprise. |
| Deploy | Expo Go → TestFlight → App Store | Direct Xcode if ejected. |

### 5C: Data Model Generation

Sutra generates data models based on product type patterns.

**Content Platform Pattern:**

```sql
-- Content table (the thing users consume)
create table {content_type} (
  id uuid primary key default gen_random_uuid(),
  content text not null,
  category text not null,
  source text not null,       -- 'seed', 'ai-generated', 'user-submitted'
  metadata jsonb default '{}',
  score float default 0,      -- computed from votes/engagement
  created_at timestamptz default now()
);

-- Engagement table (how users interact with content)
create table {engagement_type} (
  id uuid primary key default gen_random_uuid(),
  {content_type}_id uuid references {content_type}(id),
  session_id text not null,   -- anonymous until auth added
  action text not null,       -- 'upvote', 'downvote', 'share', 'skip'
  created_at timestamptz default now()
);

-- Sessions (anonymous users)
create table sessions (
  id text primary key,        -- client-generated UUID
  preferences jsonb default '{}',
  created_at timestamptz default now(),
  last_seen_at timestamptz default now()
);
```

**Productivity Tool Pattern:**

```sql
-- Items (tasks, activities, notes, etc.)
create table {item_type} (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  title text not null,
  status text default 'active',
  category text,
  scheduled_at timestamptz,
  duration_minutes int default 0,
  recurrence jsonb,           -- for repeating items
  metadata jsonb default '{}',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- User preferences
create table user_settings (
  user_id text primary key,
  settings jsonb default '{}',
  created_at timestamptz default now()
);
```

### 5D: Content Strategy (for content-driven products)

If `content_source` includes 'ai-generated' or 'curated':

| Decision | Options | How to Choose |
|----------|---------|---------------|
| **Seed content** | Public domain, API, manual curation, AI-generated batch | Start with existing corpus. AI supplements, doesn't replace. |
| **Seed size** | 100 (bare min), 500 (solid), 1000+ (comfortable) | Need enough for 1 week of daily visits without repeat |
| **AI generation** | Real-time per request / Batch pre-generation / Hybrid | Batch is cheaper and allows quality filtering |
| **Quality gate** | AI self-rating / Human review / User votes / Automated checks | Start with AI self-rating + user votes. Add human review if quality drops. |
| **Moderation** | Category opt-in/out / Keyword filter / AI classification / Manual | Category system is cheapest. Add AI classification at scale. |
| **Freshness** | New content on every visit / Daily rotation / Algorithmic / Chronological | Depends on content volume. If 500+ items, algorithmic. If fewer, chronological. |

### 5E: Design Approach Selection

| Approach | When to Use | Trade-off |
|----------|------------|-----------|
| **Design-in-code** (Tailwind, iterate live) | Solo founder, web MVP, speed over polish | Fast but may accumulate design debt |
| **Design system first** (DESIGN.md → theme.ts) | Team, native app, strong aesthetic vision | Slower start but consistent output |
| **Design-then-build** (Figma → code) | Complex UI, multiple screens, design-critical product | Highest quality but requires design skills/tools |

gstack skills: `/design-consultation` (design system) or `/design-shotgun` (explore options)

### 5F: Deployment Architecture

| Platform | Default Deploy | Preview/Staging | Monitoring | Rollback |
|----------|---------------|----------------|-----------|----------|
| Web (Next.js) | Vercel | Auto preview URLs per PR | Vercel Analytics + PostHog | Instant via Vercel dashboard |
| Web (other) | Netlify / Railway | Branch deploys | Custom | Git revert + redeploy |
| iOS (Expo) | Expo Go → TestFlight | Expo Go on device | PostHog + Sentry | OTA updates via Expo |
| iOS (native) | Xcode → TestFlight | Ad-hoc builds | Sentry + Analytics | App Store review cycle |

gstack skill: `/setup-deploy`

### Output: Architecture Card

```yaml
product_type: "{type}"
platform: "{web/ios/etc}"
tech_stack:
  framework: "{choice} — {why}"
  styling: "{choice} — {why}"
  backend: "{choice} — {why}"
  ai: "{choice} — {why}"
  deploy: "{choice} — {why}"
  analytics: "{choice} — {when to add}"
data_model: "{pattern used}"
content_strategy: "{if applicable}"
design_approach: "{design-in-code / system-first / design-then-build}"
deploy_pipeline: "{how code gets to users}"
```

gstack skills: `/plan-eng-review` → `/autoplan`

---

## Phase 6: CONFIGURE — Generate the OS

**Input**: Shape Brief + Architecture Card
**Process**: Sutra assembles the OS from its modules, customized to this specific product
**Output**: Complete company folder with all operating files
**Gate**: OS file passes self-check (no DayFlow-specific references, all sections filled, tech stack matches architecture card)

### Module Selection Matrix

```
Product type → selects the Stage module
Platform → selects tech stack defaults and deployment
Content source → adds content strategy section (or skips it)
Stage → determines process intensity
```

| Stage | Team Size | Process Intensity | Departments Active |
|-------|-----------|------------------|--------------------|
| Pre-launch (0 users) | 1 | Minimal (12 rules) | Product, Design, Engineering, Quality |
| Beta (25+ users) | 1-3 | Light (add analytics, user research) | + Growth, Data |
| Growth (1000+ users) | 3-10 | Standard (full SDLC) | + Ops, Security, Content |
| Scale (10000+ users) | 10+ | Full (all processes) | All departments |

### OS Generation Steps

1. **Select base template**: `layer3-modules/{product-type}/STAGE-{N}.md`
2. **Replace all placeholders** with company-specific values from Intake Card + Architecture Card
3. **Add content strategy section** if product type is content-driven
4. **Set tech stack** from Architecture Card
5. **Set metrics** from Shape Brief success criteria
6. **Set A/B test config** (SUTRA mode for first feature, alternating after)
7. **Generate TODO.md** from P0 feature list with build order
8. **Set gstack skills** appropriate for platform and stage
9. **Configure shared infrastructure** — read `asawa-inc/shared/AI-PROVIDERS.md` and `EXTERNAL-SYSTEMS.md`:
   - Select AI provider from approved list based on use case + cost constraints
   - Copy `asawa-inc/shared/templates/ai-provider.ts` to company's `src/lib/ai.ts`
   - Configure the provider/model override for this company
   - Register any new external systems the company needs in `EXTERNAL-SYSTEMS.md`
   - Add `## AI Configuration` section to the company's OS file
   - Follow override rules from `asawa-inc/shared/OVERRIDE-RULES.md`
10. **Self-check**: grep for "DayFlow", "{placeholder}", or any generic text. Replace all.

### Output: Company OS Package

```
{company}/
├── PRODUCT-BRIEF.md          # From Phase 3 (Shape Brief + Market Brief)
├── OPERATING-SYSTEM-V1.md    # The full OS, customized
├── SUTRA-VERSION.md          # Pinned to current Sutra release
├── SUTRA-CONFIG.md           # A/B test config, mode settings
├── METRICS.md                # What to measure, empty log
├── TODO.md                   # P0 features from Shape Brief, ordered
├── CLAUDE.md                 # Dev instructions for AI agents building this product
└── feedback-to-sutra/        # Where learnings go back to Sutra
```

---

## Phase 7: DEPLOY — Activate the Company

**Input**: OS Package
**Process**: Create company in the holding structure, register with Sutra
**Output**: Live company folder, registered client
**Gate**: Company folder committed to repo, client registry updated

### Steps

1. Create `asawa-inc/{company}/` directory
2. Write all OS files from Phase 6
3. Update Sutra Client Registry (this file, bottom)
4. Update Daily Pulse to include new company
5. Run `/setup-deploy` to configure deployment automation
6. **Compile and install enforcement hooks**:
   a. Read `asawa-inc/holding/ENFORCEMENT-FRAMEWORK.md` (mechanism spec)
   b. Read `asawa-inc/sutra/layer2-operating-system/ENFORCEMENT.md` (rule definitions)
   c. Read `asawa-inc/{company}/SUTRA-CONFIG.md` (tier and mode config)
   d. For each hook template in `asawa-inc/holding/hooks/`:
      - Apply tier-based gate configuration (Tier 1: soft, Tier 2: mixed, Tier 3: hard)
      - Copy to `.claude/hooks/`
   e. Update `.claude/settings.json` with hook entries (order: boundaries → process-gate → self-assessment; PostToolUse: compliance, feedback, override-tracker)
   f. Create `.enforcement/` directory with empty `audit.log`
   g. Create `.planning/features/` directory for feature state machine
   h. Verify: trigger a test Edit action, confirm hooks fire correctly
7. Commit everything: `git add asawa-inc/{company}/ .claude/ .enforcement/ && git commit`

### Default Checklist (founder can override any item)

| Item | Default | Founder decision |
|------|---------|-----------------|
| Landing page / website | YES — deploy via Vercel | Founder can say no |
| Custom domain | NO — use Vercel subdomain until ready | Founder decides |
| Analytics (PostHog) | NO — add before 100 users | Auto-triggered |
| Privacy policy | YES — before any public launch | Required |
| Git repo | YES — committed to asawa-inc/{company}/ | Required |

The landing page is part of every company by default. Sutra builds and deploys it during onboarding. If the founder explicitly says "no landing page," skip it. Otherwise, ship it.

---

## Phase 8: ACTIVATE — Start Building

**Input**: Deployed OS
**Process**: Begin Feature #1 using the OS
**Output**: First feature shipped
**Gate**: Feature #1 deployed and metrics logged

### Activation Sequence

```
1. Read the OS (OPERATING-SYSTEM-V1.md)
2. Read the TODO (top P0 item)
3. Check SUTRA-CONFIG.md — is feature #1 in SUTRA or DIRECT mode?
4. If SUTRA mode:
   /office-hours → refine the feature idea
   /autoplan → CEO + design + eng review
   [BUILD]
   /qa → test + fix
   /ship → deploy
   /canary → post-deploy health
5. If DIRECT mode:
   [BUILD]
   /review → code review
   /ship → deploy
6. Log to METRICS.md: ship time, breaks, quality
7. Write feedback to feedback-to-sutra/ if anything was learned
```

The company is now operating.

---

## Interaction Patterns

### Sutra ↔ Client (ongoing)

```
CLIENT builds feature
  → logs metrics to METRICS.md
  → writes feedback to feedback-to-sutra/

SUTRA reads feedback
  → identifies patterns across all clients
  → publishes Sutra v{next} with improvements

CLIENT reviews new version
  → tests one feature with new OS
  → upgrades or stays
```

### Sutra ↔ gstack (per feature)

```
SUTRA OS says "use SUTRA mode for this feature"
  → triggers gstack pipeline: /office-hours → /autoplan → build → /qa → /ship → /canary

SUTRA OS says "use DIRECT mode"
  → triggers minimal pipeline: build → /review → /ship

gstack /retro produces weekly metrics
  → SUTRA reads metrics to check if OS is helping

gstack /learn stores cross-session learnings
  → SUTRA accesses learnings for version updates
```

### Sutra ↔ Holding Company

```
SUTRA publishes new version
  → Holding company Daily Pulse reports: "Sutra v1.1 available"
  → Each client decides whether to upgrade

CLIENT reports incident
  → Holding company flags in Daily Pulse
  → SUTRA analyzes: was the OS followed? Should it change?

SUTRA Agent Incentives fire:
  → Sutra OS Agent checks adoption rates across all clients
  → Sutra Quality Agent checks break rates across all clients
  → Sutra Learner Agent checks feedback backlog
```

### Client ↔ Client (cross-pollination)

```
CLIENT B discovers: "design-in-code is faster for web MVPs"
  → writes feedback to Sutra

SUTRA incorporates into v1.1:
  → "For web products at Stage 1, default design approach = design-in-code"

DAYFLOW reads v1.1 release notes:
  → "Not applicable (we're iOS), but good to know for future web components"

CLIENT B discovers: "content quality metrics > code quality metrics for content apps"
  → writes feedback to Sutra

SUTRA adds content-app metrics template to v1.1:
  → Available for all future content-platform clients
```

---

## Sutra Self-Improvement Protocol

Every client interaction teaches Sutra something. The protocol:

1. **After every client onboarding**: Review what was MISSING from the template. Was anything invented from scratch that should have been provided?
2. **After every 5 features shipped** (across all clients): Are SUTRA-mode features actually producing better outcomes than DIRECT-mode?
3. **After every incident**: Did the OS prevent this? Could it have? What sensor was missing?
4. **Monthly**: Review all feedback-to-sutra/ across all clients. Batch into version update.

### Version Release Criteria

Sutra publishes a new version when:
- 5+ feedback items have accumulated across clients
- At least 1 feedback item is a genuine gap (not just preference)
- The change doesn't break existing clients' OS (backward compatible)
- At least 1 client agrees to test the new version

---

## Client Registry

| # | Company | Type | Platform | Stage | Sutra Version | Mode | Onboarded | Status |
|---|---------|------|----------|-------|---------------|------|-----------|--------|
| 1 | DayFlow | Productivity tool | iOS (Expo) | Pre-launch | v1.0 | A/B Test | 2026-04-01 | Active |
| 2 | PPR | Productivity tool | Web (Next.js) | Pre-launch | v1.0 | A/B Test | 2026-04-03 | Active |
| 3 | Maze | Content platform | Web (Next.js) | Pre-launch | v1.0 | A/B Test | 2026-04-04 | Active |
