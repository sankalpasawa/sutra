# Sutra — Start Here

## You're a founder. You have an idea. Here's what to do.

### Prerequisites

1. [Claude Code](https://claude.ai/claude-code) installed
2. This repo cloned: `git clone <repo-url> && cd flow`
3. GSD installed: `npx get-shit-done-cc@latest --claude --global`

### One Command

Open Claude Code in the repo root and type:

```
/sutra-onboard
```

That's it. Sutra takes over.

### What Happens

Sutra walks you through 8 phases in ~60 minutes:

| Phase | What | Time | Output |
|-------|------|------|--------|
| 1. INTAKE | Sutra asks you 10 questions about your idea | 5 min | Intake Card |
| 2. MARKET | Sutra researches your market, competitors, APIs | 10 min | Market Brief |
| 3. SHAPE | PR/FAQ test, feature carve, risk map | 10 min | Shape Brief |
| 4. DECIDE | You commit: build, reshape, or kill | 2 min | GO / NO-GO |
| 5. ARCHITECT | Tech stack, data model, deployment plan | 15 min | Architecture Card |
| 6. CONFIGURE | Sutra generates your company's operating system | 10 min | OS files |
| 7. DEPLOY | Company folder created, committed to git | 5 min | Live company |
| 8. ACTIVATE | GSD project initialized, roadmap ready | 5 min | Ready to build |

### After Onboarding

Your company lives at `asawa-inc/{your-company}/`. Your OS is at `OPERATING-SYSTEM-V1.md`.

To start building:

```
/gsd:plan-phase 1     — Plan your first feature
/gsd:execute-phase 1   — Build it
/qa                     — Test it
/ship                   — Ship it
```

To check progress: `/gsd:progress`
To see stats: `/gsd:stats`
To pause and resume later: `/gsd:pause-work` → `/gsd:resume-work`

### 89 Skills Available

You have access to 89 skills (gstack + GSD). See `asawa-inc/sutra/layer2-operating-system/SKILL-CATALOG.md` for the complete catalog organized by what you're trying to do.

### How Sutra Learns

After every feature you ship, write feedback to `asawa-inc/{your-company}/feedback-to-sutra/`. Sutra reads this feedback and improves for all future companies.

### Current Companies

| Company | Type | Status |
|---------|------|--------|
| DayFlow | Productivity tool (iOS) | Active, pre-launch |
| *Your company* | *TBD* | *Start with /sutra-onboard* |
