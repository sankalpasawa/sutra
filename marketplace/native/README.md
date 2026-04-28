# Native — Sutra Engine Plugin (v1.0)

The deployable Claude Code plugin clients install — built fresh on the V2.4 Sutra Engine architecture (4 primitives + 6 laws + Skill Engine R4 + 6 terminal-check predicates).

Status: under construction (M1 scaffold). See `holding/plans/native-v1.0-execution-plan.md` for the 12-milestone roadmap.

## What's here (after v1.0 ships)

- `src/primitives/` — Domain, Charter, Workflow, Execution
- `src/laws/` — L1 DATA, L2 BOUNDARY, L3 ACTIVATION, L4 COMMITMENT, L5 META, L6 REFLEXIVITY
- `src/engine/` — Workflow Engine + Skill Engine + 4 starter engines (BLUEPRINT, COVERAGE, ADAPTIVE-PROTOCOL, ESTIMATION)
- `src/schemas/` — DataRef, Asset, TriggerSpec, BoundaryEndpoint, Interface, Constraint, Cohort
- `src/hooks/` — PreToolUse, PostToolUse, Stop
- `bin/` — bash thin shims that exec into TS hooks
- `skills/` — SKILL.md + schema.json sidecars per skill
- `tests/` — contract / property / integration

## Stack

- TypeScript 5.x (strict mode, ESM, ES2022)
- Bun runtime preferred; Node 20+ fallback OK
- Vitest 1.x + fast-check 3.x (property-based testing)
- JSONL append-only state with typed reducers + snapshots

## Coexistence with Core

Native is self-contained. Does NOT depend on Core plugin internals. Core (existing fleet) keeps running unchanged. Both ship to clients via Sutra Marketplace.

## Install (post-v1.0 release)

```
/plugin install native@sutra-marketplace
```

## Operationalization

1. Measurement: install count via Sutra Marketplace telemetry; Native session count vs Core
2. Adoption: T2 onboarding CM9 pattern — DayFlow first; Billu/Paisa/PPR/Maze follow
3. Monitoring: 7d canary observation post each T2 onboard; T+0→T+60s install verification
4. Iteration: client-reported issue OR codex audit finding triggers v1.x patch
5. DRI: Asawa CEO + Sutra-OS team rotation
6. Decommission: V3.0 ships breaking changes superseding V2.x, OR Native plugin discontinued
