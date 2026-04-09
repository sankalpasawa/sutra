# Finding Tracker Template

Standard format for tracking findings from audits, QA sessions, and reviews.

## Usage

Copy this table into a task's VERIFY stage or a standalone findings file when an audit produces multiple findings. At Depth 4+, a task **cannot be marked complete** if any finding has Status=OPEN without evidence of resolution or explicit WONTFIX justification.

## Finding Table

| ID | Description | Status | Evidence | Fixed-in | Date |
|----|-------------|--------|----------|----------|------|
| F-001 | [Short description of the finding] | OPEN | [link/screenshot/command output] | [commit SHA or file path] | YYYY-MM-DD |

### Status Values

- **OPEN** — Finding identified, not yet resolved
- **FIXED** — Resolution implemented and verified
- **WONTFIX** — Explicitly decided not to fix, with justification in Evidence column

### Rules

1. **Every finding gets an ID.** Sequential within the task (F-001, F-002, ...).
2. **Evidence is mandatory for FIXED and WONTFIX.** A finding cannot move out of OPEN without evidence.
3. **At Depth >= 4, all findings must be non-OPEN before task completion.** The commit/PR/completion gate checks: if any finding is OPEN, the task is blocked.
4. **Compound findings get split.** If a finding has multiple sub-issues (e.g., "overlay color wrong AND sheet height wrong"), split into separate IDs (F-002a, F-002b). Each sub-issue tracks independently.
5. **Partial fixes are not FIXED.** If 2 of 3 sub-issues are resolved, status stays OPEN until all sub-issues are resolved or remaining are marked WONTFIX.

### Example: Design QA Findings

| ID | Description | Status | Evidence | Fixed-in | Date |
|----|-------------|--------|----------|----------|------|
| F-001 | Header font size 18px, spec says 16px | FIXED | Screenshot comparison before/after | `a3f8c2d` components/Header.tsx | 2026-04-06 |
| F-002a | Bottom sheet overlay color too dark (#000 @ 60%, spec says 40%) | FIXED | CSS updated, visual match confirmed | `b7e1d4a` styles/overlay.css | 2026-04-06 |
| F-002b | Bottom sheet height 400px, spec says 360px | OPEN | — | — | 2026-04-06 |
| F-003 | Missing loading spinner on save action | WONTFIX | Discussed with founder — save is <100ms, spinner unnecessary | N/A | 2026-04-06 |

In this example, the task **cannot be completed** at Depth 4+ because F-002b is still OPEN.

## Integration with TASK-LIFECYCLE

- **VERIFY phase**: Create the finding table when running verification checks
- **Completion gate**: Check all findings are non-OPEN before marking task complete
- **LEARN phase**: Reference finding IDs when documenting what was learned
