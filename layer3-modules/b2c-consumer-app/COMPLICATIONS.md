# Real-World Complications — How the System Handles Them

Every clean process diagram lies. Reality has complications. This document catalogs every type of complication a product company faces and shows exactly how our system handles it.

---

## The Complication Types

| Type | Example | Who surfaces it | Who resolves it |
|------|---------|----------------|-----------------|
| Engineering ↔ Design tension | Design wants scroll wheel, eng says too complex | CTO + CDO negotiation | Founder (trade-off) |
| Legal/Compliance blocker | Tags = user-generated content = GDPR implications | CISO agent | Founder + legal review |
| Competitive pressure | Sunsama just shipped tags. Do we rush? | CPO (market scan) | Founder (strategic call) |
| Financial constraint | Gemini API costs spike with tag-based queries | CDaO (cost monitoring) | CTO (optimization) + Founder (budget) |
| Vendor dependency | Supabase changes JSON column behavior | CTO (detected in testing) | CTO (workaround or migration) |
| P0 production incident | Shipped tags, users losing data | Sensors (automated) | ALL hands — drop everything |
| Scope creep during build | "While we're here, let's also add tag colors" | Builder (me) | CPO + Founder (is this P1?) |
| Upstream spec wrong | Design assumed single row, 10 tags overflow | Builder (execution) | CDO revises spec |
| Downstream impact discovered | Tags break the AI schema, Play screen crashes | Knowledge system sensors | CTO traces change flow map |
| P1 shortcut creates P2 debt | JSON array now = migration pain later | CTO annotates roadmap | Founder (speed vs future cost) |
| User feedback contradicts plan | Beta users say "I don't want tags, I want folders" | CDaO (analytics) + Growth | CPO pivots or perseveres |
| Cross-feature conflict | Tags and categories now overlap — confusing UX | CDO + CPO | Founder (which concept wins?) |
| Performance regression | Tag queries slow down canvas scroll to 30fps | CQO (perf sensor) | CTO (optimize or defer) |
| Accessibility gap | Screen reader can't navigate tag chips | CDO (accessibility check) | CDO + CTO fix together |
| Content/copy confusion | "Tags" vs "Labels" vs "Categories" — which word? | CCO agent | Founder (naming is taste) |

---

## Detailed Walkthroughs

### Complication 1: Legal / Compliance

**Scenario**: You want to add tags. Tags are user-generated strings. GDPR says users have the right to see all their data, modify it, and delete it. Tags that contain personal information ("mom's birthday", "therapy session") are personal data.

**How it surfaces**:
```
STRATEGY LAYER:
  CISO agent reads the PRD → flags:
    "Tags are user-generated text = personal data under GDPR.
     Implications:
     1. Tags must be included in data export (right of access)
     2. Tags must be deletable (right to erasure)
     3. If tags are used for AI training, user must consent
     4. Privacy policy must disclose tag collection

     BLOCKER: Privacy policy doesn't exist yet.
     Cannot ship tags to EU users without it.

     Options:
     A) Ship tags only to non-EU users (geofence) — complex
     B) Write privacy policy first, then ship tags — 1 week delay
     C) Ship tags, add privacy policy within 30 days — legal risk

     RECOMMENDATION: B. Write privacy policy. It's needed anyway."
```

**Where it lives**: `org/features/tags/IMPACT.md` → Legal section

**Who resolves**: Founder chooses B. CCO agent drafts privacy policy. CISO reviews. Founder approves. Tags ship after privacy policy is live.

**What changes**: ROADMAP.md gets a new dependency: "Privacy Policy (P0 blocker, must ship before tags)". This is a cross-feature task that affects ALL future features, not just tags.

---

### Complication 2: Competitive Pressure

**Scenario**: You're planning tags for next month. Sunsama ships tags this week. Your beta users ask "when are you getting tags?"

**How it surfaces**:
```
STRATEGY LAYER:
  CPO agent (or you directly):
    "Competitor shipped tags. Market pressure to ship faster.

    Current plan: Tags in 3 weeks (after privacy policy + full spec)
    Rush plan: Tags in 1 week (JSON array, no autocomplete, no colors)

    Trade-off:
    Rush: Ship faster, but P2 migration required. Higher bug risk.
          Design not fully spec'd. No test plan.
    Wait: Ship better, but users may perceive DayFlow as behind.

    RICE impact of rushing:
    Reach: same. Impact: same. Confidence: drops 8→5 (less tested).
    Effort: drops (simpler version). Score changes from 40 to 32.

    Market analysis: Sunsama's tags are basic (no colors, no AI).
    We can match in 1 week. We can leapfrog in 3 weeks.

    DECISION NEEDED: Match fast or leapfrog slow?"
```

**Where it lives**: `org/features/tags/PRD.md` → Market Context section. Also `org/decisions/2026-04-03-tags-rush-vs-quality.md`

**Who resolves**: Founder. This is a strategic call. No agent can make it. The system surfaces the trade-off with data. You decide.

---

### Complication 3: Financial Constraint

**Scenario**: Tags means more data per activity. The AI command layer sends all activity data to the LLM. More data = more tokens = higher Gemini API costs.

**How it surfaces**:
```
SPECIFICATION LAYER:
  CTO agent reads the tech spec → calculates:
    "Current context size: ~800 tokens per activity (title + time + category).
     With tags (avg 3 tags, 15 chars each): ~850 tokens per activity.
     With 35 activities per day: 1,750 extra tokens per AI call.

     At Gemini free tier: irrelevant (1M tokens/day limit).
     At 10K users paying $10/mo: ~500K extra tokens/day = ~$15/day extra.
     At 100K users: $150/day = $4,500/month.

     Not a blocker now. Becomes a concern at scale.

     Mitigation: Summarize tags in context instead of listing all.
     'Tags: health(3), morning(2), work(5)' instead of per-activity tags.
     Reduces token cost by 60%.

     RECOMMENDATION: Ship as-is. Add summarization at P2."
```

**Where it lives**: `org/features/tags/TECH-SPEC.md` → Cost Analysis section

**Who resolves**: CTO makes the technical call (summarize at P2). Founder validates the cost projection is acceptable.

---

### Complication 4: Vendor Dependency

**Scenario**: Tags are stored as JSON in SQLite. Supabase (the cloud sync backend) handles JSON differently than SQLite. When you eventually sync to cloud, JSON queries behave differently.

**How it surfaces**:
```
SPECIFICATION LAYER:
  CTO agent reads the tech spec + SECURITY-INFRA.md:
    "SQLite stores tags as TEXT (JSON string). Query: json_extract().
     Supabase (PostgreSQL) stores tags as JSONB. Query: @> operator.

     If we write queries that use SQLite-specific JSON functions,
     they won't work when we add Supabase sync.

     Options:
     A) Abstract the query layer now (interface for local + cloud)
     B) Write SQLite queries now, rewrite for Supabase later
     C) Store tags as comma-separated text (works everywhere, less flexible)

     Effort: A = 2 days extra, B = 0 now + 1 day later, C = same but limited

     RECOMMENDATION: B. We don't have Supabase sync yet. Don't
     over-engineer for a future that may change. YAGNI."
```

**Where it lives**: `org/features/tags/TECH-SPEC.md` → Vendor section + `org/decisions/2026-04-03-tags-json-vendor.md`

**Who resolves**: CTO recommends. Founder approves (YAGNI is a valid principle for pre-launch).

---

### Complication 5: P0 Production Incident

**Scenario**: Tags shipped yesterday. Today, 3 users report their activities disappeared. The tag migration corrupted some activity records.

**How it surfaces**:
```
EXECUTION LAYER — EMERGENCY:
  This bypasses ALL process. Speed is everything.

  1. DETECTION (< 5 minutes)
     Sensor alert: "3 error reports in 1 hour" (future: automated via Sentry)
     Currently: user reports via feedback channel

  2. TRIAGE (< 15 minutes)
     CTO agent: read error logs, identify root cause
     "The migration set tags = '[]' but for activities with NULL category_id,
      it crashed and set the entire row to NULL. 12 activities affected."

  3. SEVERITY ASSESSMENT
     P0: Data loss for real users. Drop everything.

  4. IMMEDIATE ACTION (< 1 hour)
     Option A: Revert the migration (if possible)
     Option B: Restore from backup + fix migration script
     Option C: Manual data recovery for affected users

     CTO: "Backup exists from yesterday. Restore affected rows.
           Fix migration to handle NULL category_id. Redeploy."

  5. FIX + VERIFY
     Fix the migration script
     Restore affected data
     Run sensors: all pass
     Deploy

  6. POST-MORTEM (within 24 hours)
     What happened: NULL category_id not handled in migration
     Why it wasn't caught: No test case for NULL category
     What we change:
       - Add to TEST-PLAN: "migration with NULL fields"
       - Add to PRODUCT-KNOWLEDGE-SYSTEM failure flow map:
         "Migration scripts must handle NULL in every column"
       - Add sensor: "Before any migration, check for NULL counts
         in every column being touched"

     → org/decisions/2026-04-04-tags-migration-incident.md
     → PRODUCT-KNOWLEDGE-SYSTEM.md updated with new sensor
```

**Who resolves**: CTO drives the fix. Founder is informed. Post-mortem is collaborative. The SYSTEM LEARNS from the incident.

---

### Complication 6: Upstream Spec Wrong (discovered during build)

**Scenario**: CDO designed tag chips as a horizontal row below the title. During build, you find that 8 tags overflow the pill width and the layout breaks.

**How it surfaces**:
```
EXECUTION LAYER:
  Builder (me) encounters the issue while implementing:

  1. PAUSE building (don't hack around it)

  2. Write revision note:
     org/features/tags/SPEC-REVISION-001.md
     "During implementation, found that tag chips overflow pill width
      at 5+ tags. Current spec assumes max 3 tags visible.

      Options:
      A) Wrap to second row (pill height increases)
      B) Horizontal scroll within the pill
      C) Show max 3, then '+N' chip
      D) Reduce chip size for pills (smaller than form chips)

      CDO: Please evaluate and update DESIGN-SPEC.md"

  3. CDO agent runs:
     "Option C is best. Matches iOS notification badge pattern.
      Shows 'health, morning, +3' on the pill.
      Full list visible when you tap to open the form.
      Updated DESIGN-SPEC.md section 4.2."

  4. Builder continues with updated spec.

  5. TEST-PLAN.md updated: "Add test: pill with 8 tags shows 3 + badge"
```

**Where it lives**: `org/features/tags/SPEC-REVISION-001.md` (kept for history)

**Who resolves**: CDO agent for design. Builder implements. If it's a taste call (which 3 to show?), founder decides.

---

### Complication 7: Cross-Feature Conflict

**Scenario**: Tags and categories now overlap. The form has both "Category" chips and "Tag" input. Users will be confused: "What's the difference between a tag and a category?"

**How it surfaces**:
```
SPECIFICATION LAYER:
  CPO agent flags during PRD review:
    "Tags and categories serve similar purposes.
     Both label activities. Both color-code pills.

     User confusion risk: HIGH.

     Options:
     A) Keep both. Categories = broad (Health, Work). Tags = specific (gym, morning).
        Clear but adds cognitive load.
     B) Replace categories with tags. Migration: each category becomes a tag.
        Simpler UX but breaks existing analytics and filtering.
     C) Categories become 'primary tag'. Tags are additional labels.
        Hybrid. Most flexible but most complex to implement.
     D) Ship tags as P2. For now, keep categories.
        Defers the conflict.

     CDO assessment: 'Users will ask why both exist. We need one concept.'
     CTO assessment: 'Option B is cleanest technically. Migration is 1 day.'

     RECOMMENDATION: B — one concept (tags) replaces categories.
     Cleaner for users. Cleaner for code. Migration is straightforward.

     DECISION NEEDED: Founder — do we merge or keep both?"
```

**Where it lives**: `org/features/tags/PRD.md` → Conflicts section + `org/decisions/`

**Who resolves**: Founder. This is a product philosophy decision. "One concept" (everything is an Activity) was a core principle. Extending it to "one labeling system" (everything is a tag) is consistent.

---

### Complication 8: User Feedback Contradicts Plan

**Scenario**: You shipped tags (P1). Analytics show: 80% of users use 0-1 tags. Only 5% use 3+. Users aren't adopting tags.

**How it surfaces**:
```
POST-SHIP — FEEDBACK LOOP:
  CDaO agent reads PostHog data (weekly):
    "Tag adoption after 2 weeks:
     - 80% of activities have 0 tags
     - 15% have 1 tag
     - 5% have 2+ tags
     - Most common tag: same as their old category name

     Interpretation: Users don't understand the value of multiple tags.
     They're using tags as categories (single label).

     Possible causes:
     1. UI doesn't encourage multiple tags (input is hidden)
     2. Users don't see the benefit (no tag-based features yet)
     3. Tags add friction to creation (one more thing to fill)

     RECOMMENDATION to CPO:
     - Don't build P2 tag features (autocomplete, colors) yet
     - Instead: add 'AI suggests tags' (zero-effort tagging)
     - If AI-suggested tags get accepted 50%+, users see the value
     - Then build P2 features on proven demand"
```

**Where it lives**: `org/features/tags/MONITOR.md` → Adoption section. Feeds back into Strategy layer for the NEXT decision about tags.

**Who resolves**: CPO adjusts the roadmap based on data. P2 tag features deprioritized. "AI suggests tags" becomes the new P1. Founder validates.

---

## How the System Stays Alive

The system isn't a document you write once. It's alive because:

**1. Every complication creates a record**
When a complication happens, it gets logged. Not in someone's head. In a file. In the repo. Committed. Searchable. Any future agent working on a similar feature reads these records.

**2. Every incident updates the knowledge system**
The P0 migration bug adds a new sensor. The spec revision adds a new test case. The cross-feature conflict adds a decision record. The system literally grows from its mistakes.

**3. Analytics close the loop**
Strategy makes a bet ("tags will help retention"). Execution ships it. Analytics measures it. The measurement feeds back into the next strategy decision. The loop never stops.

**4. Agents read history before acting**
When a new feature starts, agents read:
- `org/features/` for past features and their complications
- `org/decisions/` for past trade-off decisions
- `PRODUCT-KNOWLEDGE-SYSTEM.md` for current dependency state
- Incident records for what went wrong before

This is institutional memory. Not in someone's head. In files that any agent (or human, or future LLM) can read.

---

## What the System Cannot Do (Limitations)

**1. Taste decisions**: "Should the tag chip be 9px or 10px?" No agent can answer this. Only you.

**2. Strategic bets**: "Should we build tags or focus on Google Calendar integration?" Data informs but doesn't decide. You decide.

**3. Novel situations**: When something genuinely new happens (a new competitor, a new platform, a new regulation), agents can research but can't generate the creative response. You provide the creative leap.

**4. Emotional judgment**: "Is this feature delightful?" "Will users love this?" No amount of process substitutes for human intuition about what feels right.

**5. Speed under crisis**: In a real P0, the system should get out of the way. Fix first, process second. The post-mortem is where the system learns.

**6. Interpersonal dynamics**: If you eventually hire humans, agent-based processes can't resolve interpersonal conflicts, motivate people, or build culture. Those are human leadership tasks.

The system handles the 80% that is systematic. You handle the 20% that requires judgment, taste, and courage.
