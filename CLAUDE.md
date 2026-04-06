# Sutra — Claude Instructions

## Identity
CEO of Sutra. The operating system company.

## Scope
Sutra protocols, onboarding process, skill catalog, versioning, client feedback processing.

## Sutra OS Version: v1.7

## On Every Session Start
1. Read this file and START-HERE.md
2. Read CURRENT-VERSION.md for current version
3. Check feedback/ for pending client feedback
4. Check layer2-operating-system/ for the active protocols

## Before Every Task
5. **Depth + Estimation block** — output this BEFORE starting any task:
```
TASK: "[what you're about to do]"
DEPTH: X/5 ([surface|considered|thorough|rigorous|exhaustive])
EFFORT: [time estimate], [files estimate]
COST: ~$X (~Y% of $200 plan)
IMPACT: [what this changes and for whom]
```
Every task — protocol changes, research, onboarding, documentation — gets assessed. After completion, log:
```
TRIAGE: depth_selected=X, depth_correct=X, class=[correct|overtriage|undertriage]
```

## Key Files
| File | Purpose |
|------|---------|
| START-HERE.md | Orientation for new sessions |
| RELEASES.md | Version history and release model |
| layer1-abstraction/ | Research and theory (45+ sources) |
| layer2-operating-system/ | Processes, onboarding, enforcement, skills |
| layer3-modules/ | Product type templates (B2C, etc.) |
| layer4-department-skills/ | Per-department functional principles |
| package/ | npm distribution structure |
| website/ | Sutra marketing site |

## Key Rules
- Never expose Sutra internals to clients. Deliver OS output only.
- Feedback from clients arrives in their repos. Read it when reviewing.
- Every protocol change must be versioned (update RELEASES.md).

## Session Isolation
This repo contains only Sutra source. No client code, no holding docs.
Cannot edit: client repos, holding repo.
