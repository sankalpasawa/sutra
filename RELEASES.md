# Sutra — Release Model

## How Sutra and Client Companies Interact

```
SUTRA (develops continuously)
  │
  │ Publishes: v1.0, v1.1, v1.2, v2.0...
  │
  ▼
RELEASE (versioned, stable snapshot)
  │
  │ Client fetches a specific version
  │
  ▼
DAYFLOW (pins to v1.0, runs it, gives feedback)
  │
  │ Feedback goes to Sutra (not to the release)
  │
  ▼
SUTRA (incorporates feedback into next version)
  │
  │ Publishes v1.1 (includes DayFlow's learnings)
  │
  ▼
DAYFLOW (decides when to upgrade: stay on v1.0 or fetch v1.1)
```

## The Versioning

### Sutra v1.2 (current)
- Phase 1 INTAKE rewritten as conversational flow: one question at a time, react-and-follow-up, build Intake Card progressively
- Internal checklist preserved (all fields still required), but founder never sees a numbered list
- Conversation tips added for handling the bet question, involvement level inference, and short answers
- Triggered by: founder feedback during onboarding — "too many questions at once, make it back and forth"

### Sutra v1.1.1
- External resource sovereignty: before pausing/deleting any external resource, verify ownership — even under full autonomy
- Phase 7 deploy step: verify MCP-connected account ownership before touching any external service
- "Full autonomy" scoped: covers product decisions, NOT destructive infrastructure actions
- Triggered by: Maze onboarding — Sutra paused wrong Supabase project on shared MCP account

### Sutra v1.1
- Complexity tiers: OS is mandatory for all companies, depth scales with company complexity (Personal → Product → Company)
- Infrastructure guardrail: parallel operations require isolation verification (from PPR deploy collision feedback)
- Enforcement tiering: compliance checks, metrics logging, and shipping log requirements scale with tier
- Clients: DayFlow (Tier 2), PPR (Tier 1)

### Sutra v1.0
- Stage 1 Pre-Launch OS (12 rules)
- Basic product knowledge system (shearing layers, flow maps, sensors)
- Functional principles (product, design, eng, security, quality)
- Intent + boundaries + effort delegation model
- One process: idea → PR/FAQ → P1 → mockup → build → test → ship

### Sutra v2.0 (future — when DayFlow hits Stage 2: 25 users)
- Analytics and metrics process
- User research process
- Onboarding optimization
- Retention tracking
- Weekly metrics review
- Expanded department functions

## How a Release Gets Created

1. Sutra works on improvements in `asawa-inc/sutra/` (the development branch)
2. When a set of improvements is ready, Sutra tags a release: `sutra-v1.1`
3. The release is a snapshot: specific versions of the operating model, principles, and modules
4. DayFlow's adapted version lives in `asawa-inc/dayflow/sutra-version`

## How DayFlow Fetches a Release

1. DayFlow reads `asawa-inc/sutra/RELEASES.md` to see what's new
2. DayFlow decides: upgrade or stay
3. If upgrade: copy the new version's files to `asawa-inc/dayflow/adapted-principles/`
4. Adapt any generic principles to DayFlow's specific context
5. Update `CLAUDE.md` if the operating process changed

## How DayFlow Sends Feedback

1. DayFlow encounters something: bug, missing principle, principle violation, or validation
2. Writes to `asawa-inc/dayflow/feedback-to-sutra/YYYY-MM-DD-topic.md`
3. Format:
   ```
   Type: incident | violation | missing | validation
   Sutra version: v1.0
   What happened: [description]
   What principle was relevant: [or "none — this is a gap"]
   What we learned: [the insight]
   Suggested update: [if any]
   ```
4. Sutra's Learner agent reads feedback and incorporates into next version

## Current State

| Company | Pinned to | Status |
|---------|-----------|--------|
| DayFlow | Sutra v1.0 | Running. No feedback sent yet. |
| PPR | Sutra v1.0 | Running. First feedback sent (parallel deploy collision). |

## Release History

| Version | Date | What changed | Triggered by |
|---------|------|-------------|-------------|
| v1.0 | 2026-04-03 | Initial: Stage 1 OS, 12 rules, basic knowledge system | DayFlow creation |
| v1.1 | 2026-04-04 | Complexity tiers, infrastructure guardrail, enforcement tiering | PPR onboarding + parallel deploy collision |
| v1.1.1 | 2026-04-04 | External resource sovereignty rule, Phase 7 ownership verification step | Maze Supabase org confusion |
| v1.2 | 2026-04-05 | Phase 1 INTAKE → conversational flow (no question dump) | Founder onboarding friction feedback |
