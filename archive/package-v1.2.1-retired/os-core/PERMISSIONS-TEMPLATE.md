# Sutra — Claude Code Permissions Template

**Classification**: Core Infrastructure (Tier 2 Controlled — changes require Asawa approval)

This document defines the standard `.claude/settings.json` templates deployed to every Sutra client company. Three permission tiers map directly to the Defaults Architecture (DEFAULTS-ARCHITECTURE.md) and Session Isolation levels (SESSION-ISOLATION.md).

---

## Three Permission Tiers

### Tier 1: Internal (Full Access)

**Companies**: DayFlow, Maze, PPR, Jarvis, Asawa Inc
**Trust level**: Maximum — these are founder-owned companies within the holding structure
**Default mode**: `bypassPermissions` — no confirmation prompts, full autonomy
**Session isolation**: Levels 1-5 all active (instructions, hooks, directory, agent, fresh context)

Characteristics:
- All tools allowed without confirmation
- Full hook suite deployed (audit, KPI, lifecycle, cascade)
- Can reference Sutra-compiled OS copies in their own `os/` directory
- Boundary enforcement prevents cross-company edits but does not restrict tool types
- MCP connections to shared infrastructure (Supabase, etc.) allowed

### Tier 2: Trusted External

**Companies**: Future clients who have completed onboarding and signed terms
**Trust level**: High — vetted clients using Sutra as their operating system
**Default mode**: `allowWithPermission` — tools execute but user gets prompted for sensitive operations
**Session isolation**: Levels 1-3 active (instructions, hooks, directory)

Characteristics:
- Core tools (Read, Write, Edit, Bash, Glob, Grep) allowed without prompts
- Agent/Task tools require permission prompt
- MCP connections scoped to client's own accounts only
- Hooks enforce boundaries and process gates
- No access to Sutra source, holding docs, or other client repos
- Estimation and lifecycle hooks deployed but no KPI tracker (Asawa-internal metric)

### Tier 3: External (Restricted)

**Companies**: Trial clients, open-source users, evaluation installs
**Trust level**: Limited — no vetting, no signed terms
**Default mode**: explicit allow list only (no `bypassPermissions`, no `allowWithPermission`)
**Session isolation**: Levels 1-3 active, Level 2 hooks are hard-enforced

Characteristics:
- Only explicitly listed tools are available
- No Bash access by default (must be explicitly granted per-command pattern)
- No MCP connections
- No agent/subagent spawning
- Boundary enforcement + process gate hooks only
- No Sutra-internal hooks (no audit suite, no KPI, no lifecycle)

---

## Template settings.json Per Tier

### Tier 1: Internal

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "allow": [
      "Read", "Write", "Edit", "Bash", "Glob", "Grep",
      "WebSearch", "WebFetch", "Agent", "Skill",
      "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
      "TaskOutput", "TaskStop", "AskUserQuestion",
      "EnterPlanMode", "ExitPlanMode", "NotebookEdit",
      "ToolSearch"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/daily-pulse.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/enforce-boundaries.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/process-gate.sh"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "caffeinate -i -w $$ &>/dev/null & echo '{\"suppressOutput\": true}'",
            "statusMessage": "Preventing sleep..."
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "pkill -f 'caffeinate -i' 2>/dev/null; echo '{\"suppressOutput\": true}'"
          }
        ]
      },
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/cascade-check.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/process-fix-check.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/session-checkpoint.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/session-end-satisfaction.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/test-in-production-check.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/time-allocation-tracker.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/principle-regression.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/lifecycle-check.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/auto-push.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/kpi-tracker.sh"
          }
        ]
      }
    ]
  }
}
```

### Tier 2: Trusted External

```json
{
  "permissions": {
    "defaultMode": "allowWithPermission",
    "allow": [
      "Read", "Write", "Edit", "Bash", "Glob", "Grep",
      "WebSearch", "WebFetch", "Skill",
      "AskUserQuestion", "ToolSearch"
    ],
    "deny": [
      "NotebookEdit"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/session-start.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/enforce-boundaries.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/process-gate.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/cascade-check.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/session-checkpoint.sh"
          },
          {
            "type": "command",
            "command": "bash .claude/hooks/lifecycle-check.sh"
          }
        ]
      }
    ]
  }
}
```

### Tier 3: External (Restricted)

```json
{
  "permissions": {
    "allow": [
      "Read", "Edit", "Glob", "Grep",
      "AskUserQuestion", "ToolSearch"
    ],
    "deny": [
      "Bash", "Write", "Agent",
      "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
      "TaskOutput", "TaskStop",
      "WebSearch", "WebFetch",
      "NotebookEdit", "Skill",
      "EnterPlanMode", "ExitPlanMode"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/enforce-boundaries.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/session-checkpoint.sh"
          }
        ]
      }
    ]
  }
}
```

---

## Hook Deployment Matrix

Which hooks deploy to which tier. Hooks are compiled from Sutra source during onboarding (Phase 7 DEPLOY) and placed in the client's `.claude/hooks/` directory. Clients receive the compiled scripts, never the Sutra source templates.

| Hook | Purpose | Tier 1 | Tier 2 | Tier 3 |
|------|---------|--------|--------|--------|
| **enforce-boundaries.sh** | Block edits outside company repo | YES | YES | YES |
| **process-gate.sh** | Ensure process steps aren't skipped | YES | YES | YES |
| **session-checkpoint.sh** | Save session state on stop | YES | YES | YES |
| **cascade-check.sh** | Detect downstream impacts of edits | YES | YES | NO |
| **estimation hooks** | Pre-task cost/time estimation | YES | YES | NO |
| **lifecycle-check.sh** | Verify feature lifecycle compliance | YES | YES | NO |
| **session-start.sh** | Load OS, check feedback, orient session | YES | YES | NO |
| **process-fix-check.sh** | Verify fixes follow process | YES | NO | NO |
| **session-end-satisfaction.sh** | Founder satisfaction capture | YES | NO | NO |
| **test-in-production-check.sh** | Flag untested production changes | YES | NO | NO |
| **time-allocation-tracker.sh** | Track time across work types | YES | NO | NO |
| **principle-regression.sh** | Check for principle violations | YES | NO | NO |
| **auto-push.sh** | Auto-push commits on session end | YES | NO | NO |
| **kpi-tracker.sh** | Track company KPIs per session | YES | NO | NO |
| **daily-pulse.sh** | Generate daily pulse report | YES | NO | NO |
| **caffeinate** | Prevent macOS sleep during Bash | YES | NO | NO |

**Tier escalation**: A Tier 2 client can request Tier 1 hooks via change request to Asawa (per Defaults Architecture Tier 2 override process). A Tier 3 client must upgrade to Tier 2 first.

---

## Safe-to-Share Audit

Every setting deployed to a client repo is classified as SAFE or NOT SAFE to share outside the Asawa holding structure. This audit determines what goes into Tier 2 and Tier 3 templates.

### SAFE — Include in all client templates

| Setting | Why safe |
|---------|----------|
| Hook scripts (compiled) | Generic enforcement logic, no Asawa-specific intelligence |
| Permission allow/deny lists | Standard Claude Code tool names, publicly documented |
| Tool matcher patterns | `Edit\|Write\|Bash` etc. — generic patterns |
| Session checkpoint format | Standard JSON state capture |
| Boundary enforcement logic | Uses `git rev-parse` — tied to client's own repo, not Asawa |
| Process gate logic | Generic step-verification, no proprietary methodology exposed |
| CLAUDE.md identity block | Company-specific, generated per client |
| SUTRA-CONFIG.md tunables | Client's own configuration, they wrote it |

### NOT SAFE — Exclude from external client templates

| Setting | Why not safe | What to do instead |
|---------|--------------|-------------------|
| API keys (Supabase, Resend, etc.) | Credentials | Client provides their own keys during onboarding |
| Internal paths (`~/Claude/asawa-holding/...`) | Reveals holding structure | Use relative paths (`./`) in all client hooks |
| Sutra source references (`sutra/layer2-...`) | Exposes Sutra IP | Compile to flat files, remove source paths |
| Holding-level doc references (`holding/TODO.md`) | Internal roadmap | Never reference holding docs in client settings |
| Hook source templates | Contains Sutra methodology comments | Strip comments during compilation, ship only executable logic |
| KPI tracker internals | Reveals Asawa's measurement framework | Tier 1 only, never shared externally |
| Daily pulse template | Reveals cross-company reporting structure | Tier 1 only, never shared externally |
| Cascade check intelligence | Contains Sutra's impact analysis heuristics | Ship compiled version with generic logic for Tier 2 |
| MCP server connection strings | Infrastructure access | Client configures their own MCP connections |
| Agent incentive configurations | Asawa governance model | Never deployed to any client |

### Compilation Rule

During Phase 7 DEPLOY, hooks are **compiled** before deployment:

```
Source (Sutra repo)          →  Compiled (client repo)
─────────────────────────────────────────────────────
# SUTRA INTERNAL: ...        →  (stripped)
ASAWA_HOLDING_PATH=...       →  (removed)
source sutra/lib/utils.sh    →  (inlined)
# methodology comment        →  (stripped)
```

The compilation step is mandatory. No client repo — internal or external — should contain raw Sutra source paths. Internal clients (Tier 1) get the full compiled hooks. External clients get the subset appropriate to their tier.

---

## Integration into Onboarding (Phase 7 DEPLOY)

Phase 7 of CLIENT-ONBOARDING.md currently handles repo creation, boundary hooks, and settings.json generation. This template system extends Step 5 ("Configure `.claude/settings.json`") with tier-aware generation.

### Updated Phase 7 Step 5

```
5. Configure .claude/settings.json (TIER-AWARE):
   a. Determine client tier:
      - Tier 1: Company is in asawa-holding/ submodule list
      - Tier 2: Company has signed Sutra client agreement
      - Tier 3: All others (trial, evaluation, open-source)
   b. Copy the appropriate template from PERMISSIONS-TEMPLATE.md
   c. Replace placeholders:
      - {company} → company name
      - Hook paths → relative to client repo root
   d. For Tier 2+3: Run the safe-to-share audit checklist:
      - Grep for absolute paths → replace with relative
      - Grep for "asawa", "holding", "sutra/" → remove or replace
      - Grep for API keys or tokens → ensure none present
      - Verify no hook references Sutra source
   e. For Tier 1: Deploy full hook suite from holding/hooks/
   f. For Tier 2: Deploy scoped hook suite (see matrix above)
   g. For Tier 3: Deploy minimal hooks (boundary + checkpoint only)
   h. TEST: Run each hook with a test input and verify correct exit codes
```

### How `/sutra-onboard` Generates Settings

The `/sutra-onboard` skill should add this logic after the DEPLOY phase:

```
1. Ask: "Is this an internal Asawa company?" → Tier 1
2. If no, ask: "Has this client signed a Sutra agreement?" → Tier 2
3. If no → Tier 3
4. Generate settings.json from the appropriate template
5. Compile hooks (strip Sutra internals, inline dependencies)
6. Deploy to .claude/hooks/ and .claude/settings.json
7. Run isolation verification (existing Phase 7 Step 13)
8. Log tier assignment in Sutra Client Registry
```

### Client Registry Extension

The Client Registry in CLIENT-ONBOARDING.md gains a `Permissions Tier` column:

| # | Company | Sutra Version | Permissions Tier | Hooks Deployed |
|---|---------|---------------|-----------------|----------------|
| 1 | DayFlow | v1.3 | Tier 1 (Internal) | Full suite (17 hooks) |
| 2 | PPR | v1.0 | Tier 1 (Internal) | Full suite (17 hooks) |
| 3 | Maze | v1.3 | Tier 1 (Internal) | Full suite (17 hooks) |
| 4 | Jarvis | v1.3 | Tier 1 (Internal) | Full suite (17 hooks) |
| 5 | Asawa Inc | v1.3.1 | Tier 1 (Internal) | Full suite (17 hooks) |

---

## Tier Escalation Protocol

A client can move between tiers. Movement follows the Defaults Architecture override governance.

**Tier 3 to Tier 2**: Client completes onboarding, signs agreement, Asawa approves. Settings.json regenerated from Tier 2 template. Additional hooks deployed.

**Tier 2 to Tier 1**: Reserved for companies acquired into the Asawa holding structure. Full hook suite deployed, `bypassPermissions` enabled, submodule added to asawa-holding.

**Any tier downgrade**: Asawa revokes by regenerating settings.json from the lower tier template. Hooks removed. Logged in Client Registry.

---

*Template version: 1.0*
*Maps to: Defaults Architecture tiers (Immutable / Controlled / Tunable)*
*Enforcement: Tier 2 Controlled — template changes require Asawa approval*
