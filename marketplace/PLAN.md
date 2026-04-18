# Sutra Plugin v0.1 — Implementation Plan

> **Execution:** Inline in this session. No subagents (founder direction 2026-04-18).

**Goal:** Ship a minimum-viable Claude Code plugin at `sutra/marketplace/plugin/` — installable via `/plugin install sutra@<marketplace>` — delivering Sutra's core governance (input routing, depth estimation, readability gate, output trace) plus F15 Asawa-leak audit.

**Architecture:** Official Claude Code `.claude-plugin/` layout. Governance splits into three enforcement tiers per official best practice:
- **Skills** (guidance, SHOULD happen, auto-invoked via description): input-routing, depth-estimation, readability-gate, output-trace.
- **Hooks** (enforcement, MUST happen): depth-marker-pretool (warn-only v0.1), estimation-stop (log).
- **Commands** (user-triggered): `/sutra` activation, `/depth-check` manual gate.

Skills and commands auto-discovered from default dirs — `plugin.json` only carries metadata. Scripts use `${CLAUDE_PLUGIN_ROOT}`. No Asawa strings (F15 audit enforces).

**Tech stack:** JSON (manifest, hooks), Markdown (skills/commands/docs), bash (hooks/audit). No build step, no runtime deps.

---

## Research grounding

- **Official schema**: `code.claude.com/docs/en/plugins-reference` — manifest at `.claude-plugin/plugin.json`, auto-discovery from default dirs
- **Skills authoring**: `code.claude.com/docs/en/skills` — SKILL.md frontmatter; description front-loads triggers; 1,536-char cap on description+when_to_use; keep SKILL.md under 500 lines
- **Anthropic plugin README**: `github.com/anthropics/claude-code/blob/main/plugins/README.md` — standard structure, README mandatory
- **2026 convergence** (last30days 2026-04-18): plugin authors moving to skills-only + `references/` for progressive disclosure (atomic-agents v2.0.0 rewrite); both layouts work, commands/ still supported
- **Hookify pattern** (studied on disk): `hooks/hooks.json` wires events → matchers → commands with `${CLAUDE_PLUGIN_ROOT}`

---

## File structure (all at `sutra/marketplace/plugin/`)

```
.claude-plugin/
  plugin.json
skills/
  input-routing/SKILL.md
  depth-estimation/SKILL.md
  readability-gate/SKILL.md
  output-trace/SKILL.md
commands/
  sutra.md
  depth-check.md
hooks/
  hooks.json
  depth-marker-pretool.sh
  estimation-stop.sh
scripts/
  asawa-leak-audit.sh
README.md
LICENSE
CHANGELOG.md
```

Old stub `plugin/plugin.json` (wrong location) removed.

---

## Tasks (execute in order)

### T1 — Delete stub + create manifest
- Delete `plugin/plugin.json`
- Create `plugin/.claude-plugin/plugin.json` (content in §Contents below)
- Validate: `jq empty plugin/.claude-plugin/plugin.json`

### T2 — Docs + license
- Create `plugin/README.md` (user-facing)
- Create `plugin/LICENSE` (MIT)
- Create `plugin/CHANGELOG.md` (0.1.0)

### T3 — Four skills
- Create `skills/input-routing/SKILL.md`
- Create `skills/depth-estimation/SKILL.md`
- Create `skills/readability-gate/SKILL.md`
- Create `skills/output-trace/SKILL.md`

### T4 — Two commands
- Create `commands/sutra.md` (disable-model-invocation: true)
- Create `commands/depth-check.md` (disable-model-invocation: true, argument-hint: [task])

### T5 — Hooks + audit
- Create `hooks/hooks.json` (PreToolUse Edit|Write + Stop)
- Create `hooks/depth-marker-pretool.sh` (warn-only)
- Create `hooks/estimation-stop.sh`
- Create `scripts/asawa-leak-audit.sh` (F15)
- `chmod +x` all three bash files

### T6 — Validate + commit
- `jq empty` on both JSON files
- Run `bash scripts/asawa-leak-audit.sh` — must PASS
- `find plugin -type f | sort` — expect 15 files
- Commit in sutra submodule: single atomic commit
- Bump sutra pointer in holding

---

## Contents

### plugin/.claude-plugin/plugin.json
```json
{
  "name": "sutra",
  "version": "0.1.0",
  "description": "Operating system for building with AI — input routing, depth estimation, readability gate, output trace. Opinionated governance for Claude Code sessions.",
  "author": { "name": "Sutra", "url": "https://sutra.os" },
  "homepage": "https://sutra.os",
  "license": "MIT",
  "keywords": ["governance","input-routing","depth-estimation","readability","workflow","opinionated-os","session-discipline"]
}
```

### plugin/README.md
Short user-facing intro. Leads with WHAT IT DOES. Install command. v0.1 limitations. MIT license.

### plugin/LICENSE
Standard MIT. Copyright "Sutra". No Asawa string.

### plugin/CHANGELOG.md
0.1.0 entry dated 2026-04-18 with skill/command/hook list and known limitations.

### skills/input-routing/SKILL.md
Frontmatter: `name: input-routing`, `description` front-loads "at the start of every user message before any tool call." Body: 5-line routing block template + type definitions + rules.

### skills/depth-estimation/SKILL.md
Frontmatter: `name: depth-estimation`, `description` triggers on "start of any multi-step task." Body: 5-line estimation block + 1-5 scale + marker write command + post-task triage line.

### skills/readability-gate/SKILL.md
Frontmatter: `name: readability-gate`, `description` triggers on "before presenting output." Body: tables/bars/decisions rules + line budgets + self-check.

### skills/output-trace/SKILL.md
Frontmatter: `name: output-trace`, `description` triggers on "end of every response." Body: three verbosity levels + toggle rules + format.

### commands/sutra.md
Frontmatter: `name: sutra`, `disable-model-invocation: true`. Body: emits activation banner + shows current depth marker + states what changes.

### commands/depth-check.md
Frontmatter: `name: depth-check`, `disable-model-invocation: true`, `argument-hint: [task description]`. Body: emit depth block for $ARGUMENTS + write marker.

### hooks/hooks.json
```json
{
  "description": "Sutra governance hooks — warn on missing depth marker before Edit/Write, log estimation on Stop.",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/depth-marker-pretool.sh", "timeout": 5 }
      ]}
    ],
    "Stop": [
      { "hooks": [
        { "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/estimation-stop.sh", "timeout": 10 }
      ]}
    ]
  }
}
```

### hooks/depth-marker-pretool.sh (warn-only)
Shell: check `$CLAUDE_PROJECT_DIR/.claude/depth-registered`. If missing, print 6-line warning to stderr. Always exit 0 (non-blocking v0.1).

### hooks/estimation-stop.sh
Shell: append timestamp + depth marker contents (or "absent") to `$CLAUDE_PROJECT_DIR/.claude/sutra-estimation.log`. Always exit 0.

### scripts/asawa-leak-audit.sh
Shell: grep `\basawa\b` in PLUGIN_ROOT, excluding `.git`, `node_modules`, and self. Exit 1 on match, 0 otherwise.

---

## Validation

```bash
jq empty sutra/marketplace/plugin/.claude-plugin/plugin.json
jq empty sutra/marketplace/plugin/hooks/hooks.json
chmod +x sutra/marketplace/plugin/hooks/*.sh sutra/marketplace/plugin/scripts/*.sh
bash sutra/marketplace/plugin/scripts/asawa-leak-audit.sh   # expect PASS
find sutra/marketplace/plugin -type f -not -path '*/.git/*' | sort  # expect 15 files
```

## Commit

```bash
cd sutra && git add marketplace/ && \
  git commit -m "marketplace v0.1: plugin scaffold — manifest, 4 skills, 2 commands, 2 hooks, audit" && \
  cd ..
git add sutra && git commit -m "bump sutra pointer: marketplace v0.1 plugin scaffold"
```

Single atomic commit per repo (not per-task) — submodule round-trips make per-task commits too heavy. Per `feedback_converge_and_proceed`, grouped commits are the right call.

---

## Self-review

**P3 Tier 1 coverage:**
- F1 manifest schema → T1 ✓
- F2 content mapping (skills/commands/hooks) → T3-T5 ✓
- F13+CM3 first-run UX → T2 README + T4 /sutra ✓
- F15 Asawa-leak audit → T5 scripts/asawa-leak-audit.sh ✓
- CM9 DayFlow-via-plugin → deferred (v0.1 ships the installable; DayFlow-side integration = separate session)

**Placeholders:** none. `sutra.os` homepage and repo link are D29-intentional brand placeholders, not TBDs.

**Type consistency:**
- Skill names kebab-case, ≤64 chars
- Commands: `disable-model-invocation: true` (user-triggered only)
- Hooks: `${CLAUDE_PLUGIN_ROOT}` for every command path
- Zero Asawa strings (T5 audit enforces)

**Risks:**
- Hooks warn-only → non-breaking for installers
- No runtime deps → no install failures
- Atomic commits per repo → reversible

**Out of v0.1 scope:**
- Publishing to marketplace repo (F5 pending)
- npm coexistence (F17 pending)
- Friend-0 recruitment (CM5 deferred per functionality > GTM)
- Hard enforcement hooks (v0.2)
- Per-profile defaults (v0.2)
- DayFlow-via-plugin integration (CM9, separate session)
