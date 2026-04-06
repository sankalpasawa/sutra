# Client Onboarding — Changelog

> Version-specific changes to onboarding. For current process, see [CLIENT-ONBOARDING.md](CLIENT-ONBOARDING.md).
> Split per PROTO-011 (Version Focus) — sessions load CLIENT-ONBOARDING.md only.

---

## Learnings from Evolution Cycles (2026-04-05)

### What We Learned Deploying to 4 Companies

| Company | Type | Onboarding Used | Key Learning |
|---------|------|----------------|-------------|
| Maze | New (B2C content) | Full 8-phase | Works well but compliance audit showed gaps — retroactive artifacts don't count |
| DayFlow | Mid-stage (mobile) | MID-STAGE-DEPLOY.md | Existing conventions must be respected — OS adapts to company, not vice versa |
| Jarvis | New (AI tool) | Fast scaffold | 8-phase is heavy for a solo founder's personal tool — Tier 1 needs a lighter path |
| PPR | New (personal) | Full 8-phase | Worked but most departments are stubs at Tier 1 |

### Changes Made Based on Learnings

1. **Phase 7 updated**: Mandatory identity declaration, boundary hook installation, isolation tests
2. **MID-STAGE-DEPLOY.md created**: 7-step protocol for existing codebases (AUDIT → CLASSIFY → MAP → DEPLOY → VERIFY → ACTIVATE → LEARN)
3. **Engines deploy during Phase 7**: Not as a separate step — estimation, routing, enforcement review all installed during onboarding
4. **Sensitivity map auto-seeded**: During Phase 7, scan codebase for auth/, env, migrations → seed sensitivity.jsonl
5. **Skill tier assigned during Phase 6**: SUTRA-CONFIG.md includes skill_tier based on complexity tier

### What Still Needs Improvement

1. Tier 1 needs a lighter onboarding path (< 30 min instead of 60 min)
2. The 8 phases could collapse to 5 for Tier 1 (INTAKE → SHAPE → BUILD → DEPLOY → ACTIVATE)
3. Automated scaffolding (npx sutra-init) would eliminate manual file creation
