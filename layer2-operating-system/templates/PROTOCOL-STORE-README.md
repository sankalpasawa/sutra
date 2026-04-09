# Protocol Store Standard

Standard location, format, and lifecycle for reusable protocols created by the LEARN phase.

## Location

Each company maintains a protocol store at:

```
{company}/os/protocols/
```

Example:
```
dayflow/os/protocols/
maze/os/protocols/
```

## File Naming

Files are named by trigger slug: `{trigger-slug}.md`

Examples:
- `sdk-integration.md` — protocol for integrating a new SDK
- `new-screen.md` — protocol for adding a new screen/page
- `api-endpoint.md` — protocol for creating a new API endpoint
- `db-migration.md` — protocol for running database migrations
- `design-qa.md` — protocol for running design QA on a completed UI

## Protocol File Format

Every protocol file uses this standard front matter + body:

```yaml
protocol: {name}
trigger: "{when this fires — natural language description}"
depth: {recommended depth, usually current task depth minus 1}
process:
  - step 1
  - step 2
  - step 3
verify: "{how to confirm the protocol worked}"
source_task: "{original task that created this protocol}"
times_used: 0
last_refined: {YYYY-MM-DD}
```

### Example: `new-screen.md`

```yaml
protocol: New Screen
trigger: "When creating a new screen or page in the app"
depth: 2
process:
  - Create the screen component file in the correct directory
  - Add navigation route entry
  - Add to tab bar or nav stack if applicable
  - Create placeholder test file
  - Run the app to verify screen renders
verify: "Screen accessible via navigation, no console errors"
source_task: "DayFlow F3 — Settings Screen (2026-04-04)"
times_used: 3
last_refined: 2026-04-06
```

## Maturity Model

| times_used | Status | Meaning |
|------------|--------|---------|
| 0 | **Candidate** | Just created by LEARN phase. Untested in practice. |
| 1-2 | **Active** | Used at least once. May need refinement. |
| 3-9 | **Proven** | Reliable. Refinements are incremental. |
| 10+ | **Locked** | Stable. Only change with explicit justification. |

## How LEARN Phase Creates Entries

From TASK-LIFECYCLE.md, the LEARN phase runs after every task. When a task reveals a repeatable pattern:

1. Check if a protocol already exists for this trigger (`os/protocols/`)
2. If yes: increment `times_used`, update `last_refined`, refine steps if the task revealed improvements
3. If no: create a new protocol file with `times_used: 0`, populate from the task's process

The LEARN phase should ask: "If I had to do this exact type of task again, what steps would I follow?" The answer becomes the protocol.

## How Adaptive Protocol Reads Entries

Before scoring a new task's complexity and process requirements:

1. Check `os/protocols/` for a matching trigger
2. If a **proven** (3+ uses) protocol exists: use its recommended depth and process steps as the baseline
3. If a **candidate** (0 uses) protocol exists: use it as a suggestion but allow the depth system to override
4. If no protocol exists: proceed with normal depth assessment

This creates a feedback loop: tasks create protocols, protocols accelerate future tasks.

## Deployment

When onboarding a new company (CLIENT-ONBOARDING.md Phase 7), create the empty directory:

```bash
mkdir -p {company}/os/protocols/
```

Protocols are company-specific. They are NOT shared across companies (different products have different patterns). Sutra provides the standard and the empty directory; companies fill it through usage.
