# Sutra OS — Improvement Synthesis from 22 Evolution Cycles

## Top Patterns from Gap Reports

### 1. Estimation Consistently Over-Predicts Time (FIXED)
- Cycles 1-3: over-predicted by 2-2.5x
- Cycles 4-8: calibrated to within 20% using 0.45x multiplier
- STATUS: RESOLVED — calibration data added to ESTIMATION-ENGINE.md

### 2. File Count Under-Predicts When Touching Navigation
- New screens always need navigator registration (missed in cycles 2, 5)
- STATUS: RESOLVED — heuristic added (new screen = 3 files)

### 3. Level 4 "Staged Rollout" Doesn't Fit All Platforms
- Edge functions are all-or-nothing (cycle 4)
- STATUS: RESOLVED — platform-specific patterns added to ADAPTIVE-PROTOCOL.md

### 4. VERIFY Is Checkboxes, Not Evidence (PROTO-010)
- Cycles 3, 4: VERIFY written but lacks hard evidence (test output, screenshots)
- STATUS: PARTIALLY RESOLVED — cycle 4 used grep as evidence. Need minimum evidence format per level.

### 5. Confidence Score Is Systematically Too Low
- When pattern is known, estimates 60-75% but actual is 100%
- STATUS: RESOLVED — "+20% for familiar patterns" rule added

### 6. No Automated Cascade Check
- Cycle 12: Sutra change wasn't propagated to companies
- STATUS: PARTIALLY RESOLVED — Architecture Awareness Sensor added (mental checklist). Need hook.

## What Needs Building in Sutra (prioritized)

### HIGH: Define minimum VERIFY evidence per depth level
Currently VERIFY is a checklist. Should be:
- L1: none (build-ship-log, no verify step)
- L2: one concrete check (e.g., "app builds clean")
- L3: test output + grep evidence (e.g., "45/45 tests pass")
- L4: test output + deployment verification + rollback plan documented

### HIGH: Automate cascade propagation
When a Sutra file changes, a hook should warn: "This file is copied to N companies. Update them?"
Currently: manual check via Change Integration Protocol.
Target: PreToolUse hook on sutra/ Edit/Write that lists downstream copies.

### MEDIUM: Lightweight Tier 1 onboarding path
8 phases in 60 min is too heavy for a personal tool.
Target: 5 phases in 30 min (INTAKE → SHAPE → BUILD → DEPLOY → ACTIVATE).
Skip: MARKET, DECIDE, CONFIGURE (personal tools don't need market research or A/B testing).

### LOW: Per-company estimation calibration
Current: one global multiplier (0.45x).
Better: per-company multipliers (Maze web: 0.4x, DayFlow mobile: 0.8x, Jarvis AI: 0.6x).
Need: 10+ data points per company before company-specific calibration.
