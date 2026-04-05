# Sutra — Tier 1 Quick Onboarding

ENFORCEMENT: Use this for Tier 1 (Personal) companies only. Tier 2+ use full CLIENT-ONBOARDING.md.

## When to Use

Solo founder, personal tool, 0 external users. Examples: Jarvis, PPR.
These don't need market research, A/B testing, or department structures.

## 5 Phases (30 minutes total)

```
INTAKE → SHAPE → BUILD → DEPLOY → ACTIVATE
 (5 min)  (5 min) (10 min) (5 min)  (5 min)
```

### Phase 1: INTAKE (5 min)
Ask three questions:
1. What are you building? (one sentence)
2. What's the core bet? (it works IF...)
3. What platform? (web/mobile/CLI)

Output: 3 sentences in CLAUDE.md.

### Phase 2: SHAPE (5 min)
Define the MVP:
1. List 5 P0 features (the smallest version that tests the bet)
2. Pick the tech stack

Output: TODO.md with 5 items + tech stack in CLAUDE.md.

### Phase 3: BUILD (10 min)
Scaffold the project:
1. Create repo
2. Run create-next-app / expo init / etc.
3. Install core dependencies
4. Create CLAUDE.md with identity + architecture rules

### Phase 4: DEPLOY (5 min)
1. Deploy to Vercel/TestFlight/npm
2. Install boundary hooks + settings.json
3. Install Sutra engines (estimation, routing, enforcement review)
4. Seed sensitivity map
5. Run 3 isolation tests

### Phase 5: ACTIVATE (5 min)
Build the first feature through the engines:
1. Run estimation + routing on the first TODO item
2. Build it at the selected depth
3. Capture actuals
4. Ship

## What's Skipped (vs full 8-phase)

| Full Onboarding Phase | Why Skipped for Tier 1 |
|-----------------------|----------------------|
| MARKET (10 min) | Personal tool — no market to research |
| DECIDE (2 min) | Solo founder — decision is implicit |
| CONFIGURE (10 min) | Minimal config — no A/B testing, no departments |

## Graduation

When the company gets its first external user: upgrade to Tier 2.
Run the missing phases (MARKET research, A/B test config) at that point.
