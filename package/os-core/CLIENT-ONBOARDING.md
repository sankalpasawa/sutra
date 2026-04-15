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

## Fast Track (Tier 1 companies — <30 minutes)

For personal tools and solo founder projects, collapse to 4 phases:

```
INTAKE → SHAPE → DEPLOY → ACTIVATE
(5 min)   (10 min) (10 min)  (5 min)
```

Skip: MARKET (no competitors matter for personal tools), DECIDE (founder already decided), ARCHITECT (use default stack), CONFIGURE (use Tier 1 defaults)

**Gate — only available if:**
- Solo founder
- Personal use or <10 target users
- No revenue goal in first 6 months
- Founder explicitly requests fast track

Otherwise: full 8-phase flow below.

---

## Existing Company Track (<45 minutes)

For companies that already exist and are running (external clients, not Asawa-owned). Same 8 phases, but answers are pre-filled from what's already known. The company IS already built — Sutra is being deployed to operate it.

```
INTAKE → MARKET → SHAPE → DECIDE → ARCHITECT → CONFIGURE → DEPLOY → ACTIVATE
(5 min)  (5 min)  (5 min) (2 min)  (5 min)    (10 min)   (5 min)  (5 min)
```

**How it differs from new company onboarding:**
- INTAKE: Company already exists. Extract what they do, tech stack, team, stage, constraints. No "what do you want to build?" — it's built.
- MARKET: Competitors and domain are known. Validate, don't discover. Quick confirmation.
- SHAPE: The bet is already being tested (company is live). Capture the current bet and what needs to change.
- DECIDE: Platform is fixed (already built). Document, don't choose.
- ARCHITECT: Architecture exists. Map it, don't design it.
- CONFIGURE: Same as new — deploy Sutra OS config for this company's tier, stage, and needs.
- DEPLOY: Same as new — full OS deployment per PROTO-013.
- ACTIVATE: Same as new — first task runs under OS, verify enforcement fires.

**Gate — use this track if:**
- Company is already live with users/revenue
- Tech stack already chosen and built
- Founder is bringing Sutra in to operate, not to build from scratch

**Key principle:** An existing company gets the SAME OS as a new company. No shortcuts on enforcement, hooks, or protocols. The only thing that's faster is the intake — because the answers already exist.

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
**Process**: Conversational back-and-forth. Sutra asks one question at a time, reacts to each answer, and builds the Intake Card progressively.
**Output**: Intake Card
**Gate**: All required fields filled. If the core bet isn't clear, help the founder find it through dialogue — don't quiz them.

### How It Works

Sutra runs intake as a **conversation, not a questionnaire.** The founder never sees a list of questions. Sutra has an internal checklist (below) but uses judgment to guide the dialogue naturally.

**The flow:**

1. **Open with one question:** "What do you want to build?"
2. **React to the answer** — reflect back what you heard, add an insight or a reframe. Show the founder you're thinking with them, not evaluating them.
3. **Ask the next natural question** based on what they said. Follow the thread, don't follow a script.
4. **Infer what you can.** If the founder says "I want to build a mobile app for tracking workouts," don't ask "What's the platform?" — you already know.
5. **Build the Intake Card progressively** as answers come in. The founder never fills out a form.
6. **If the founder hasn't thought something through,** help them think it through. "You mentioned X — does that mean the bet is really about Y?" is better than "What's your core hypothesis?"

**Tone:** Sharp co-founder, not interviewer. Engaged, not neutral. React with genuine interest. Push back when something doesn't hold up. Celebrate when something clicks.

### Internal Checklist (founder never sees this)

Sutra tracks these fields internally. Every field must be filled before the Intake Card is complete, but they're gathered through conversation, not asked as a numbered list.

**Identity (who and what)**
- What is this? (one sentence, no buzzwords)
- Who specifically uses this? (one person, with a name and context)
- What job are they hiring this product to do?

**Market (where it lives)**
- What do they do today instead?
- Why is that not good enough?
- What's the bet? ("This works IF _____. If not, it fails.")

**Scope (what to build first)**
- What's the smallest version that tests the bet?
- What's the platform? (infer from context when possible)
- What does the founder know how to build?

**Ambition (where it goes)**
- If this works, what does it become in 2 years?

**Founder involvement (how you want to work)**
- How involved do you want to be?

| Level | What It Means | Sutra's Behavior |
|-------|--------------|-----------------|
| **Hands-on** | "I want to decide everything" | Sutra presents options, founder decides. No autonomous actions. |
| **Strategic** | "I decide direction, you handle execution" | Sutra makes execution decisions autonomously. Surfaces only strategic choices. |
| **Delegated** | "Just build it. Show me when it's done." | Sutra runs autonomously. Founder reviews output, not process. |

Default: **Strategic**. The founder always has override regardless of level.

### Conversation Tips

- **Don't front-load.** Even asking 3 questions at once feels like a form. One at a time.
- **The bet is the hardest question.** Most founders haven't articulated it. Help them get there: "So it sounds like you're betting that _____ — is that right?"
- **Involvement level can be inferred.** If the founder is giving detailed opinions on everything, they're hands-on. If they say "just build it," they're delegated. Only ask explicitly if unclear.
- **Short answers are fine.** "A workout tracker" is a valid answer to "What do you want to build?" Don't ask them to elaborate if you can ask a better follow-up instead.

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

### Hurdle Rate (must pass before proceeding to Phase 2)

Before the Intake Card is considered complete, the company must clear a hurdle rate. This is not a blocker — it is a checkpoint that forces the right conversation before resources are committed.

```
HURDLE RATE (must pass all 3 to proceed):
1. Domain knowledge: Does the founder have deep knowledge in this space? (YES/NO)
2. Testable bet: Can the core hypothesis be tested with <$500 and <2 weeks? (YES/NO)
3. Path to revenue: Is there a clear way this makes money within 6 months? (YES/NO)

If any NO → pause. Discuss with founder. Either sharpen the bet or don't proceed.
```

**How it works in practice:**
- Sutra evaluates these three questions from the Intake Card answers — the founder is not asked to answer them directly.
- If domain knowledge is weak: "You mentioned you haven't worked in this space. What gives you an edge here?" Push for a real answer.
- If the bet isn't testable cheaply: "The smallest version you described would take months. Can we find a smaller slice that proves the core bet?"
- If revenue path is unclear: "How does this make money? Not in 2 years — in 6 months."
- All three YES → proceed to Phase 2.
- Any NO → the conversation continues until the answer changes or the founder decides not to proceed. Log the decision either way.

*Inspired by Constellation Software's acquisition hurdle rate — adapted for pre-revenue company creation.*

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
| **Who are the best practitioners?** | Search for domain experts, advisors, thought leaders, consultants | D20/D32: Know who has solved this before and what they learned |
| **What frameworks do the best use?** | Study methodologies, playbooks, published approaches from identified experts | Adopt proven patterns instead of inventing from scratch |
| **What do the best avoid?** | Look for post-mortems, "mistakes I made" posts, anti-pattern discussions | Learn from others' failures — cheaper than making your own |

### Research Method

```
1. Web search: "{product type} app" — find top 5-10 competitors
2. Web search: "{competitor name} reviews" — find what users hate
3. Web search: "{product type} open source" — find existing codebases to learn from
4. Web search: "{core technology} API" — find best tools (e.g., joke APIs, humor datasets)
5. Web search: "{domain} expert OR consultant OR advisor" — find 3-5 best-in-class practitioners
6. Web search: "{identified expert} methodology OR framework" — extract their approaches
7. Web search: "{domain} mistakes OR anti-patterns OR post-mortem" — learn what the best avoid
8. Synthesize: what's the gap? What do ALL competitors miss? What do the best practitioners recommend?
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

# --- External Practitioner Research (D20/D32) ---

domain_experts:
  - name: "{expert 1}"
    role: "{what they do — consultant, founder, author, advisor}"
    relevance: "{why they matter for this domain}"
    key_insight: "{their most actionable insight for our product}"
    source: "{where we found them — book, talk, blog, podcast}"
  - name: "{expert 2}"
    ...
  - name: "{expert 3}"
    ...
  # Minimum 3, target 5. Not just competitors — people who advise, build, or lead in this space.

best_practices:
  - pattern: "{what the best do}"
    evidence: "{who does it, where we saw it}"
    applicability: "{how this applies to our product}"
  - pattern: "{...}"
    ...

anti_patterns:
  - pattern: "{what the best avoid}"
    evidence: "{who failed at this, or who explicitly warns against it}"
    relevance: "{why this matters for our product}"
  - pattern: "{...}"
    ...
```

**Refresh cadence**: This research is conducted during onboarding and refreshed on a tiered cadence (G13 from SYSTEM-HEALTH.md): AI/tech research refreshed weekly, framework/methodology research refreshed bi-weekly. When G13 fires, re-evaluate domain experts, check for new frameworks, and update the Market Brief. Major market shifts trigger an immediate refresh regardless of schedule.

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

domain_experts:
  - name: "{Expert Name}"
    role: "{consultant / founder / author}"
    relevance: "{why they matter}"
    key_insight: "{their most actionable insight}"
    source: "{book / talk / blog}"

best_practices:
  - pattern: "{what the best do}"
    evidence: "{who and where}"
    applicability: "{how it applies to us}"

anti_patterns:
  - pattern: "{what the best avoid}"
    evidence: "{who warns against it}"
    relevance: "{why it matters for us}"
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
product_type: "{content-platform / productivity-tool / social-network / marketplace / saas / game / ai-agent}"
primary_value: "{what users get — content, utility, connection, transactions, capability, intelligence}"
content_source: "{user-generated / curated / ai-generated / hybrid / none}"
interaction_model: "{consume / create / collaborate / transact / converse}"
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
| AI agent | Task success rate, cost/interaction | LLM reliability, cost control, safety | Prompt versioning, tool schemas, fallback chains, eval suites |

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

**AI Agent Pattern:**

```sql
-- Interactions (every agent conversation turn)
create table interactions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  session_id text not null,       -- conversation thread
  capability text not null,       -- which agent capability was invoked
  model text not null,            -- which LLM model was used
  prompt_hash text not null,      -- hash of system prompt version
  user_input text not null,
  agent_response text not null,
  tokens_in int default 0,
  tokens_out int default 0,
  cost_usd numeric(10,6) default 0,
  latency_ms int default 0,
  first_token_ms int default 0,
  cache_hit boolean default false,
  tool_calls jsonb default '[]',  -- tools the agent invoked
  eval_result text,               -- 'pass', 'fail', 'skip'
  error text,
  created_at timestamptz default now()
);

-- Prompt versions (system prompts as versioned artifacts)
create table prompt_versions (
  id uuid primary key default gen_random_uuid(),
  capability text not null,
  version int not null,
  system_prompt text not null,
  few_shot_examples jsonb default '[]',
  active boolean default false,
  created_at timestamptz default now(),
  unique(capability, version)
);

-- Eval cases (test suite for agent behavior)
create table eval_cases (
  id uuid primary key default gen_random_uuid(),
  capability text not null,
  category text not null,         -- 'happy-path', 'edge-case', 'adversarial', 'boundary', 'safety'
  input text not null,
  expected_output text not null,
  match_type text default 'semantic', -- 'exact', 'contains', 'regex', 'semantic'
  tags text[] default '{}',
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
  b2c-consumer-app: layer3-modules/b2c-consumer-app/
  b2c-ai-agent:     layer3-modules/b2c-ai-agent/
Platform → selects tech stack defaults and deployment
Content source → adds content strategy section (or skips it)
AI agent → adds prompt lifecycle, eval suites, cost management, safety pipeline
Stage → determines process intensity
```

| Stage | Team Size | Process Intensity | Practices Active |
|-------|-----------|------------------|--------------------|
| Pre-launch (0 users) | 1 | Minimal (12 rules) | Product, Design, Engineering, Quality |
| Beta (25+ users) | 1-3 | Light (add analytics, user research) | + Growth, Data |
| Growth (1000+ users) | 3-10 | Standard (full SDLC) | + Ops, Security, Content |
| Scale (10000+ users) | 10+ | Full (all processes) | All practices |

### OS Generation Steps

1. **Select base template**: `layer3-modules/{product-type}/STAGE-{N}.md`
2. **Replace all placeholders** with company-specific values from Intake Card + Architecture Card
3. **Add content strategy section** if product type is content-driven
4. **Set tech stack** from Architecture Card
5. **Set metrics** from Shape Brief success criteria
6. **Set A/B test config** (Depth 3 for first feature, alternating after)
7. **Generate TODO.md** from P0 feature list with build order
8. **Set gstack skills** appropriate for platform and stage
9. **Configure shared infrastructure** — read `asawa-inc/shared/AI-PROVIDERS.md` and `EXTERNAL-SYSTEMS.md`:
   - Select AI provider from approved list based on use case + cost constraints
   - Copy `asawa-inc/shared/templates/ai-provider.ts` to company's `src/lib/ai.ts`
   - Configure the provider/model override for this company
   - Register any new external systems the company needs in `EXTERNAL-SYSTEMS.md`
   - Add `## AI Configuration` section to the company's OS file
   - Follow override rules from `asawa-inc/shared/OVERRIDE-RULES.md`
10. **Generate OKRs.md** from company stage and strategy:
    - Tier 1: 1-2 charters (Speed + one other based on the bet)
    - Tier 2: 3-5 charters (Speed, Quality, Growth + context-specific)
    - Tier 3: Unlimited (full charter framework from `a-company-architecture/CHARTERS.md`)
    - Use charter template from CHARTERS.md, set initial KPIs from Shape Brief success metrics
11. **Configure input routing** — set enforcement level based on founder involvement:
    - Hands-on: Level 2 (protocol) — founder sees classification, catches skips
    - Strategic: Level 2 (protocol) — same default
    - Delegated: Level 3 (skill) — automated routing, less founder overhead
    - Level 1 (hook gate) available on request — recommended for governance-heavy companies
    - Write `input-routing.yaml` with chosen level
12. **Self-check**: grep for "DayFlow", "{placeholder}", or any generic text. Replace all.

### Output: Company OS Package

```
{company}/
├── PRODUCT-BRIEF.md          # From Phase 3 (Shape Brief + Market Brief)
├── OPERATING-SYSTEM-V1.md    # The full OS, customized
├── SUTRA-VERSION.md          # Pinned to current Sutra release
├── SUTRA-CONFIG.md           # A/B test config, depth settings
├── METRICS.md                # What to measure, empty log
├── TODO.md                   # P0 features from Shape Brief, ordered
├── CLAUDE.md                 # Dev instructions for AI agents building this product
├── OKRs.md                   # Company charters + OKRs (from CHARTERS.md framework)
├── input-routing.yaml        # Enforcement level config (1=hook, 2=protocol, 3=skill)
└── feedback-to-sutra/        # Where learnings go back to Sutra
```

---


### Telescoping Documentation Model

Every company gets documentation at multiple zoom levels. The founder reads the minimum; deeper layers exist when needed.

- **Zoom 0**: Quick Reference (36 lines) — daily use, before every task
- **Zoom 1**: CLAUDE.md engine section (~30 lines) — when something unexpected happens
- **Zoom 2**: Full engine specs (~500 lines each) — when customizing or debugging
- **Zoom 3**: Evolution history (gap reports, calibration logs) — Sutra internal only

Deploy Zoom 0 + Zoom 1 during Phase 6. Zoom 2 goes in os/engines/. Zoom 3 stays in holding/.

## Phase 7: DEPLOY — Activate the Company

**Input**: OS Package
**Process**: Create company in the holding structure, register with Sutra
**Output**: Live company folder, registered client
**Gate**: Company folder committed to repo, client registry updated

### Steps

1. **Create GitHub repo**: `gh repo create sankalpasawa/{company} --private`
2. **Initialize repo structure**: Write all OS files from Phase 6
3. **Declare session identity in CLAUDE.md** (MANDATORY):
   The company's root `CLAUDE.md` MUST start with:
   ```markdown
   # {Company} — Claude Instructions

   ## Identity
   You are **CEO of {Company}**. This is an isolated {Company} session.
   You can ONLY edit files in this repo. You cannot access other companies,
   Sutra source, or holding company files.

   ## Sutra OS Version: v{current_version}

   ## On Every Session Start
   ...
   - **Sutra version check**: Read `../sutra/CURRENT-VERSION.md` line 3.
     Compare to "Sutra OS Version" above. If Sutra is newer:
     - Show: "Sutra update available: v{new} (you're on v{current})"
     - Read the changelog to see what changed
     - If changes affect this company, suggest updating
     - Do NOT auto-update. Inform and let the founder decide.
   - **Before picking up any task**, assess depth:
     - Ask: what depth is this task? (1-5)
     - Depth 1 (surface): just do it
     - Depth 2 (considered): estimate, build, verify
     - Depth 3 (thorough): research, plan, build, test, review
     - Depth 4 (rigorous): HLD, research, LLD, build, staged verify
     - Depth 5 (exhaustive): full cascade, every sub-area decomposed
     - Show: `TASK: "description" | DEPTH: 3/5 (thorough)`
   - After each task: log depth + actuals to estimation log
   ```
   This ensures the LLM identifies as CEO of this company, not CEO of Asawa.
   The version check ensures companies discover Sutra updates on their own.
   The depth assessment ensures every task gets the right level of process.
4. **Install boundary enforcement hook** (MANDATORY):
   a. Create `.claude/hooks/enforce-boundaries.sh`:
      ```bash
      #!/bin/bash
      # Blocks Edit/Write/Bash to files outside this repo's root.
      REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
      REPO_NAME="$(basename "$REPO_ROOT")"
      FILE_PATH="$TOOL_INPUT_file_path"
      # For Bash: block commands referencing parent dirs or other repos
      if [ -n "$TOOL_INPUT_command" ]; then
        CMD="$TOOL_INPUT_command"
        if echo "$CMD" | grep -qE '\.\./|/Claude/asawa-holding/(holding|sutra|dayflow|maze|ppr)/' ; then
          if ! echo "$CMD" | grep -q "/asawa-holding/${REPO_NAME}/"; then
            echo "BLOCKED: Cannot access files outside ${REPO_NAME}/."
            exit 2
          fi
        fi
        exit 0
      fi
      if [ -z "$FILE_PATH" ]; then exit 0; fi
      ABS_PATH="$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd)/$(basename "$FILE_PATH")" 2>/dev/null
      if [ -n "$ABS_PATH" ]; then
        case "$ABS_PATH" in "$REPO_ROOT"*) exit 0 ;; *)
          echo "BLOCKED: Cannot edit files outside ${REPO_NAME}/."
          exit 2 ;; esac
      fi
      exit 0
      ```
   b. `chmod +x .claude/hooks/enforce-boundaries.sh`
   c. Register in `.claude/settings.json`:
      ```json
      "PreToolUse": [{"matcher": "Edit|Write|Bash", "hooks": [{"type": "command", "command": "bash .claude/hooks/enforce-boundaries.sh"}]}]
      ```
   d. **TEST**: Run the hook with a path outside the repo and verify exit code 2.
5. **Configure `.claude/settings.json`** with permissions and all hooks:
   - Permissions allow list (Read, Write, Edit, Bash, Glob, Grep, etc.)
   - PreToolUse: boundary enforcement (step 4) + process-gate + self-assessment
   - PostToolUse: compliance, feedback, override-tracker
6. Update Sutra Client Registry (this file, bottom)
7. Update Daily Pulse to include new company
8. Run `/setup-deploy` to configure deployment automation
9. **Verify external account ownership**:
   a. For each MCP-connected service (Supabase, Vercel, etc.):
      - List all organizations/projects visible on the connection
      - Ask the founder: "Which org/account is yours?" — do NOT assume
      - Record the verified owner mapping in the company's deploy log
   b. Do NOT pause, delete, or modify any resource without confirmed ownership
   c. This step is mandatory even if the founder said "full autonomy" or "don't ask me anything"
10. **Add as submodule to asawa-holding**: `cd asawa-holding && git submodule add git@github.com:sankalpasawa/{company}.git`
11. Create `.enforcement/` directory with empty `audit.log`
12. Create `.planning/features/` directory for feature state machine
13. **Verify isolation** (MANDATORY — do not skip):
    a. From the company directory, run the boundary hook with a path to `../holding/TODO.md` — must return exit 2
    b. Run the boundary hook with a path to `../sutra/RELEASES.md` — must return exit 2
    c. Run the boundary hook with a path inside the company — must return exit 0
    d. If any test fails, fix the hook before proceeding
14. Commit everything and push

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
3. Check SUTRA-CONFIG.md — what depth level for feature #1?
4. If Depth 3+:
   /office-hours → refine the feature idea
   /autoplan → CEO + design + eng review
   [BUILD]
   /qa → test + fix
   /ship → deploy
   /canary → post-deploy health
5. If Depth 1-2:
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
SUTRA OS says "use Depth 3+ for this feature"
  → triggers gstack pipeline: /office-hours → /autoplan → build → /qa → /ship → /canary

SUTRA OS says "use Depth 1-2"
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
2. **After every 5 features shipped** (across all clients): Are high-depth features actually producing better outcomes than low-depth features?
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

| # | Company | Type | Platform | Stage | Sutra Version | Tier | Onboarded | Status |
|---|---------|------|----------|-------|---------------|------|-----------|--------|
| 1 | DayFlow | Productivity tool | iOS (Expo) | Pre-launch | v1.3 | 2 (Product) | 2026-04-01 | Active — 5/6 P0s done, 123 tests |
| 2 | PPR | Wedding command center | Web (Next.js) | Pre-launch | v1.0 | 1 (Personal) | 2026-04-03 | Active |
| 3 | Maze | Humor feed | Web (Next.js) | Pre-launch | v1.3 | 2 (Product) | 2026-04-04 | Active — 42 features, web launch ready |
| 4 | Jarvis | AI chief-of-staff | Web (Next.js) | MVP | v1.3 | 1 (Personal) | 2026-04-05 | Active — deployed to Vercel |
| 5 | Asawa Inc | Holding company | Governance | Active | v1.3.1 | 1 (Governance) | 2026-04-05 | Active — governance uses Sutra tools |


---

## Learnings & Changelog

> Version-specific changes and evolution cycle learnings moved to [CLIENT-ONBOARDING-CHANGELOG.md](CLIENT-ONBOARDING-CHANGELOG.md). (PROTO-011: Version Focus)

---

## Appendix A: Complexity Tiers

ENFORCEMENT: HARD — all companies must be classified. Tier requirements are mandatory.

### How to Classify

Complexity is determined by three factors. The highest factor determines the tier.

| Factor | Low | Medium | High |
|--------|-----|--------|------|
| **People** | Solo founder, no team | 1-3 contributors | 4+ people or cross-functional |
| **Users** | Founder is the user (0 external) | 1-100 external users | 100+ users |
| **Stakes** | Personal tool, no revenue | Pre-revenue but external users depend | Revenue, contracts, or regulatory |

### The Three Tiers

**Tier 1: Personal** — "Just me, just shipping"

Mandatory: Onboarding (8 phases), product brief, tech stack, architecture rules, build order, TODO.md, session isolation, feedback to Sutra.
Scaled down: Metrics (2-3 success metrics), single-track process, self-check every 3rd feature, soft enforcement hooks.
Skip: Practice-level functions, agent incentives, Daily Pulse, standup protocol.

**Tier 2: Product** — "Real users, real consequences"

Everything in Tier 1, plus: shipping log, metrics with weekly review, compliance before every deploy, A/B testing, quality + security functions active, weekly check-in.
Enforcement: hard for file boundaries, soft for metrics.

**Tier 3: Company** — "Team, revenue, or regulation"

Full Sutra OS. Nothing optional. All practice functions, hard enforcement, agent incentives, Daily Pulse, standup, full compliance, incident response, weekly planning, decision logs.

### Classification Table

| Company | Tier | Rationale |
|---------|------|-----------|
| PPR | 1 (Personal) | Solo founder, personal wedding tool, 0 external users |
| DayFlow | 2 (Product) | Solo founder but building for external users, pre-launch |

### When to Re-classify

Re-evaluate when: new person joins, first external user, revenue starts, regulatory requirement appears. Tier only goes UP.

### Enforcement by Tier

| Enforcement aspect | Tier 1 | Tier 2 | Tier 3 |
|-------------------|--------|--------|--------|
| File boundary hooks | Soft (flag) | Hard (block) | Hard (block) |
| Metrics logging | Self-check every 3 features | Every deploy | Every commit |
| Compliance check | Every 3rd feature | Every deploy | Every deploy + pre-merge |
| Feedback to Sutra | After incidents | After every incident | After every incident + weekly |
| Shipping log | Optional | Required | Required |

---

## Appendix B: Tier 1 Quick Onboarding

ENFORCEMENT: Use this for Tier 1 (Personal) companies only. Tier 2+ use the full 8-phase process above.

### When to Use

Solo founder, personal tool, 0 external users. Examples: Jarvis, PPR. Don't need market research, A/B testing, or practice structures.

### 5 Phases (30 minutes total)

```
INTAKE → SHAPE → BUILD → DEPLOY → ACTIVATE
 (5 min)  (5 min) (10 min) (5 min)  (5 min)
```

1. **INTAKE** (5 min): Ask three questions: What are you building? What's the core bet? What platform? Output: 3 sentences in CLAUDE.md.
2. **SHAPE** (5 min): List 5 P0 features + pick tech stack. Output: TODO.md + CLAUDE.md.
3. **BUILD** (10 min): Scaffold project, create repo, install deps, create CLAUDE.md.
4. **DEPLOY** (5 min): Deploy, install hooks + settings.json, install engines, seed sensitivity map, run 3 isolation tests.
5. **ACTIVATE** (5 min): Build first feature through engines, capture actuals, ship.

### What's Skipped (vs full 8-phase)

| Phase | Why Skipped |
|-------|------------|
| MARKET (10 min) | Personal tool — no market to research |
| DECIDE (2 min) | Solo founder — decision is implicit |
| CONFIGURE (10 min) | Minimal config — no A/B testing, no practices |

### Graduation

When the company gets its first external user: upgrade to Tier 2. Run the missing phases at that point.

---

## Appendix C: Mid-Stage Company Onboarding

The process for installing Sutra on a company that already exists — running code, conventions, habits, and debt.

### The Difference from Greenfield

| | Greenfield (Phases 1-8 above) | Mid-Stage (this appendix) |
|---|---|---|
| Starting point | An idea | Running code + existing conventions |
| Risk | Building the wrong thing | Breaking what already works |
| Approach | Generate from scratch | Assess, map, adapt, deploy incrementally |
| Duration | ~60 minutes | ~2-3 sessions |

### Five Phases: ASSESS → MAP → PLAN → DEPLOY → VERIFY

**Phase 0: ASSESS** — Audit codebase health, process health, habits, existing OS, conventions vs Sutra processes. Output: ASSESSMENT.md. Gate: Founder confirms accuracy.

**Phase 1: MAP** — For each Sutra process: adopt as-is, adapt, or defer. Key rule: when company convention conflicts with Sutra, company convention wins UNLESS security/data risk. Output: MAPPING.md. Gate: Founder approves.

**Phase 2: PLAN** — Order deployments to minimize disruption: (1) invisible infrastructure, (2) structure, (3) gates, (4) sensors, (5) one end-to-end feature. Output: DEPLOYMENT-PLAN.md.

**Phase 3: DEPLOY** — Execute one phase at a time, verify after each, commit per change, don't fix old bugs during deployment.

**Phase 4: VERIFY** — Run full system through one real feature. Checklist: standup works, process-gate enforces, design mockup before code, sensors run, metrics logged, LEARN.md written.

### Tier-Specific Adjustments

| Phase | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| Infrastructure | Soft hooks only | Mixed hooks | Hard hooks |
| Structure | Simple TODO restructure | Full node structure | Full + practice tracking |
| Gates | Soft warnings | Shape is hard, rest soft | All hard |
| Sensors | 2-3 basic sensors | 5 standard sensors | 5+ custom sensors |
| Validation | 1 feature | 1 feature + metrics comparison | 3 features + team review |

---

## Appendix D: Mid-Stage Deployment Protocol (7-Step)

ENFORCEMENT: HARD — follow every step for existing codebases.

```
AUDIT → CLASSIFY → MAP → DEPLOY → VERIFY → ACTIVATE → LEARN
```

1. **AUDIT**: Read CLAUDE.md, TODO.md, codebase structure, existing OS files, deployment plans, fragile areas, security issues. Output: AUDIT-REPORT.md. Gate: No code changes during audit.
2. **CLASSIFY**: Classify complexity tier, identify active practices, map existing conventions to PROTO-XXX. Output: SUTRA-CONFIG.md tier + rationale.
3. **MAP**: Align existing patterns. Key rule: company convention wins unless security/data risk. Output: DEPLOYMENT-MAP.md. Gate: Founder approves conflicts.
4. **DEPLOY**: Install only gaps. Deploy engines, update version pin, add engine instructions to CLAUDE.md (additive only), verify boundary enforcement + 3 isolation tests.
5. **VERIFY**: Run existing hooks, boundary tests, check workflow, test one read-only operation through engines.
6. **ACTIVATE**: Pick top P0 task, run full evolution cycle (estimate, route, build, verify, gap report), log results.
7. **LEARN**: Was deployment additive? Did engines produce useful output? What doesn't apply? What's missing? Feed back to Sutra.

**Time estimate:** Steps 1-3: ~30 min, Steps 4-5: ~15 min, Steps 6-7: ~30 min. Total: ~75 min.
