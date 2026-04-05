# Sutra — Skill Acquisition Process

When a company needs a capability that no existing skill covers, Sutra finds, evaluates, and installs one.

## When This Triggers

- Agent encounters a task with no matching skill in SKILL-CATALOG.md
- Founder requests a specific capability ("I need performance benchmarking")
- A gap report identifies a missing tool

## The Process

```
NEED → SEARCH → EVALUATE → INSTALL → CONFIGURE → VERIFY → CATALOG
```

### 1. NEED
Identify what capability is missing. Be specific:
- "I need to test API performance" not "I need testing tools"

### 2. SEARCH
Look for existing solutions:
- Claude Code plugins (check plugin registry)
- npm packages (for code-level tools)
- MCP servers (for service integrations)
- Built-in Claude Code skills (check /help)
- Open source tools installable via Bash

### 3. EVALUATE
Before installing, check:
| Check | Why |
|-------|-----|
| Does it solve the specific need? | Don't install a swiss army knife for a screwdriver job |
| Is it maintained? | Last commit < 6 months |
| Security: does it need secrets/keys? | Scope per Security Model |
| Cost: free tier available? | PROTO-003 free tier first |
| Overlap: does an existing skill partially cover this? | Extend before adding |

### 4. INSTALL
Based on type:
- **Claude Code plugin**: Add to settings.json enabledPlugins
- **npm package**: `npm install` in the company's app directory
- **MCP server**: Add to Claude settings connectors
- **Shell tool**: Install via Homebrew/npm global
- **Custom skill**: Write a .claude/commands/ markdown file

### 5. CONFIGURE
- Add to company's SUTRA-CONFIG.md specialist skills list
- Set appropriate permissions (Security Model)
- Add env vars if needed

### 6. VERIFY
- Run the skill on a real task
- Does it solve the original need?
- Does it break anything existing?

### 7. CATALOG
- Add to SKILL-CATALOG.md under the right situation category
- Note: which company first used it, what it solved
- If reusable across companies: add to appropriate tier in SKILL-REGISTRY.md
