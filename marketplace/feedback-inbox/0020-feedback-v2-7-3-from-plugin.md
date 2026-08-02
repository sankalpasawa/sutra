---
issue: 20
title: "[feedback v2.7.3] from plugin"
author: vinitharmalkar
state: OPEN
created: 2026-04-28T07:44:50Z
updated: 2026-04-28T07:44:50Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/20
comments: []
---

# #20 [feedback v2.7.3] from plugin

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-28T07:44:50Z  |  **Updated:** 2026-04-28T07:44:50Z
**URL:** https://github.com/sankalpasawa/sutra/issues/20

---

---
title: Feature: Approval Visibility Layer — visibility = trust
type: feature-request
source: user-session
date: 2026-04-28
public: true
---

Feature: Approval Visibility Layer — visibility = trust

## Core Insight

Sutra silently approves permissions — which reduces friction but destroys the trust signal. Every auto-approval is a micro-moment of 'we had your back' that's currently invisible. This proposes a full Approval Visibility Layer to surface those decisions to users in green, building trust through transparency.

Filed from a user session. User's words: 'permission bypass is invisible — visibility = trust'

---

## Feature Suite

### 1. Real-Time Approval Toast (P0)
Every time Sutra fires, emit one green line:
  [SUTRA ✓] Bash(git status) — matched: read-only-git rule
User sees what ran and why it was safe. Zero friction, full signal.

### 2. Blueprint Pre-Approval Tagging (P0)
Inside every BLUEPRINT block, tag each step with its approval status before execution:
  1. Read /src/config.ts        [SUTRA ✓ auto]
  2. Edit /src/config.ts        [SUTRA ✓ auto — file-write rule]
  3. git push origin main       [⚠ ESCALATE — destructive + remote]
User sees the full decision map before anything runs.

### 3. Risk-Colored Approval Tiers (P1)
Color-code approvals by risk:
  🟢 Green  = read-only / safe (auto-approved)
  🟡 Yellow = write op (auto-approved, watch)
  🟠 Orange = bash/network (auto-approved, logged)
  🔴 Red    = escalated to user

### 4. Session Approval Digest with Counterfactual (P0)
  Auto-approved:   23 actions  82%
  Escalated:        5 actions  18%
  Without Sutra:   ~28 prompts you didn't see
The counterfactual ('28 prompts you didn't see') is the highest-leverage trust signal.

### 5. /core:why Explainer Command (P2)
  /core:why
  → Last approval: Bash(find . -name '*.ts')
     Rule matched: read-only-bash-commands
     Risk score: 0.1/1.0
     Would have prompted: YES

### 6. Approval Diff Mode (P2)
Show what Claude would have asked vs what Sutra handled:
  [SUTRA ✓ intercepted] 'Allow Claude to run: find . -name *.ts?'
                          → matched allowlist, skipped prompt

### 7. Trust Score in /core:status (P2)
  Trust coverage this session: ▓▓▓▓▓▓▓▓░░ 82% (23/28 actions auto-approved)

### 8. Per-Category Approval Breakdown (P2)
  File reads   ▓▓▓▓▓▓▓▓▓▓ 100% (12/12)
  File writes  ▓▓▓▓▓▓▓▓░░  80%  (8/10)
  Bash         ▓▓▓▓▓░░░░░  50%  (3/6)
  Network      ░░░░░░░░░░   0%  (0/0)

### 9. Sutra Shield Indicator (P3)
Persistent [S] in Claude's status line while Sutra is active. Goes dim/red if enforcement drops.

### 10. Approval Export for Audit (P3)
/core:export-approvals → JSON of every approval this session. For enterprise security review.

---

## Priority Matrix

P0 (ship first): Real-time approval toast, Blueprint pre-approval tagging, Session digest with counterfactual
P1: Risk-colored tiers
P2: /core:why command, approval diff mode, trust score, per-category breakdown
P3: Shield indicator, audit export

The counterfactual number is the single highest-leverage feature — recommend it ships in P0 digest.
