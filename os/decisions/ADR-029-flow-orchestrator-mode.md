# ADR-029 — Flow Orchestrator Mode (D62 bootstrap)

## Status

ACCEPTED 2026-07-30. Founder direction D62 (`holding/FOUNDER-DIRECTIONS.md` §D62 — well-formed Work-Atom units + coherent growth). Ships OFF by default behind `feature_flags.flow_orchestrator_mode` in `sutra/marketplace/plugin/sutra-defaults.json`.

**Amended 2026-07-30 (post-audit, same day)**: Decision 5 now defines the full flag ladder `off` / `experimental` / `on`. The current shipped flag value is `"experimental"` — effective only in opt-in repos (currently asawa-holding), where operation is production discipline per the D62 amendment ("It's not an experiment. It is hardened already."); every other install behaves as `"off"`. The "Ships OFF" sentence above is the original accept-time text, preserved. **Second amendment (2026-07-31)**: flag flipped to `"on"` fleet-wide by explicit founder direction ("Do all of them.", soak waived), shipped in v2.56.1 alongside the codex-gate memory carve-out and cache sync that mooted the soak objection.

Runtime surfaces of record:

- `sutra/marketplace/plugin/skills/flow/SKILL.md` §Orchestrator mode (D62 / ADR-029)
- `sutra/marketplace/plugin/skills/flow/references/return-contract.schema.json`
- `sutra/marketplace/plugin/skills/flow/references/flow-ledger.md`
- `sutra/marketplace/plugin/bin/validate-return-contract.sh` · `bin/flow-factors.sh` · `bin/flow-ledger-append.sh` · `bin/workflow-type-match.sh` (the matcher is the deterministic v0 floor that narrows ADR-026's open matching-function item — see ADR-026 Consequences, amended 2026-07-30; the skill-judgment override layer remains open)
- Acceptance suite: `sutra/marketplace/plugin/tests/flow-orchestrator/run.sh` (fixtures f1..f8)

## Context

`core:flow` (ADR-026 + ADR-027) resolves one unit of work through a six-stage spine, with Claude as the single runtime: classifier, resolver, inner engine, worker, and closer are all the same session. That shape cannot scale past one lane. When work fans out to subagent workers, three unowned gaps appear:

1. **No return contract.** A worker's report back is free-form prose. Transcript-shaped walls of text (observed; pinned as fixture f4) force the orchestrator to re-read everything the worker did instead of consuming a bounded, typed result.
2. **No failure protocol.** A worker that fails has no bounded retry budget and the orchestrator has no closed set of responses — every failure becomes an improvised judgment call, which is neither replayable nor auditable.
3. **No close-stage record.** Measure/learn results lived only in the turn text. Parallel workers appending to a shared file would interleave and corrupt rows.

D62 requires every unit to be Bounded, Structured, Directional; the orchestrator/worker boundary is where those bounds must be enforced mechanically, not stylistically.

### Alternatives considered

- **Free-form worker reports, orchestrator summarizes** — rejected: unbounded input cost at the orchestrator, no mechanical validation possible, f4-shaped transcripts recur.
- **Full JSON-Schema engine for validation** — rejected: adds a dependency for one fixed schema; a hardcoded validator (`bash` + `python3` stdlib) is auditable and dependency-free. The schema file remains the contract of record.
- **Per-worker ledger files merged at close** — rejected: merge step reintroduces the interleaving problem it avoids and splits the audit trail.
- **Ship ON by default** — rejected: fleet installs must see zero behavior change until the mode is proven; flag defaults `"off"`.

## Decision

Eight sub-decisions define the mode.

**Decision 1 — Boundary (orchestrator/worker split).** In orchestrator mode there is exactly one orchestrator per unit of work and N worker Work-Atoms. The orchestrator owns: classification, step resolution, dispatch, contract validation, failure disposition, and CLOSE. Workers own: exactly one atom each — do the work, verify it, return the contract. Workers never dispatch sub-workers and never write shared state; recursion routes back through the orchestrator.

**Decision 2 — Work-Atom well-formedness (D62).** Every dispatched atom is Bounded (explicit GOAL + CONSTRAINTS + context, calibrated minimal-sufficient), Structured (GOAL / CONSTRAINTS / form per the Work-Atom primitive), and Directional (names its verify check before it runs). An atom that cannot be stated in that form is not dispatchable — decompose it or escalate.

**Decision 3 — return_contract.** Every worker returns exactly one JSON object per the contract of record `skills/flow/references/return-contract.schema.json`:

| Field | Type | Req | Rule |
|---|---|---|---|
| `atom_id` | string | yes | id of the atom this return belongs to |
| `status` | string | yes | enum `done` / `failed` / `blocked` / `partial` |
| `result` | string | yes | max 4000 chars — bounded summary, never a transcript |
| `verify` | string or object | yes | runnable check; object form `{check, result: PASS/FAIL/WAIVED [, detail]}` |
| `confidence` | string | yes | enum `high` / `moderate` / `low` |
| `trace_id` | string | yes | correlation id tying the return to the dispatch record |
| `evidence` | string | no | max 2000 chars — observable proof |
| `files_touched` | array | no | absolute paths created/modified |
| `risks` | array | no | max 10 items |
| `followups` | array | no | surfaced follow-up work |
| `note` | string | no | max 500 chars |

`bin/validate-return-contract.sh` hardcodes these rules (VALID/exit 0, INVALID/exit 1; stdin or file argument). Extra keys are tolerated; the six required fields, both enums, and the length caps are not negotiable. A return that fails validation is treated as a worker failure (Decision 4). Naming note: this worker-return contract is distinct from the `return_contract` field on the reusable-Workflow primitive (F-13, `primitives/workflow.md`, ADR-026 context) — that field names a per-workflow output schema; same term, two artifacts.

**Decision 4 — Failure policy (worker max 3, orchestrator five-option).** A worker gets at most 3 attempts at its atom (initial + 2 retries); each retry must carry what changed. On the third failure — or an invalid return contract, or a `blocked` status — the worker STOPS and returns; it never improvises a fourth path. The orchestrator then picks exactly one of the ADR-011 closed 5-set: `rollback` / `escalate` / `pause` / `abort` / `continue`. No sixth option without a new ADR.

**Decision 5 — feature_flags (amended 2026-07-30: three-rung ladder).** The mode is gated by `feature_flags.flow_orchestrator_mode` in `sutra/marketplace/plugin/sutra-defaults.json`. Three values:

- `"off"` — ZERO behavior change: `core:flow` runs exactly as documented pre-D62; no orchestrator machinery activates.
- `"experimental"` — opt-in rung: orchestrator machinery (Decisions 1-4, 6-8) effective ONLY in repos that have opted in; every other install behaves as `"off"`. Founder ruling 2026-07-30: opted-in operation is production discipline, not a trial (D62 amendment).
- `"on"` — the current shipped flag value (explicit founder call, 2026-07-31): enables Decisions 1-4 and 6-8 fleet-wide.

Read with:

```bash
jq -r '.feature_flags.flow_orchestrator_mode // "off"' sutra-defaults.json
```

**Decision 6 — Substrate.** The mode ships as plugin L0 (D38 PLUGIN-RUNTIME): executable `bin/` scripts + fixtures, not prose-only convention. Scripts are bash + python3-stdlib only — no network, no non-stdlib dependencies; deterministic where the contract demands it (`bin/flow-factors.sh`: `LC_ALL=C`, no clock, byte-identical double runs, pinned by fixture f6). Skills/docs EXPLAIN; scripts/hooks ENFORCE — one policy substrate consumed everywhere. These scripts are mechanical floors feeding the spine, NOT the ADR-027 axis engine: the `mint`/`pick` generator and reflexivity detector remain theory (FQ1 PROPOSED) per ADR-027.

**Decision 7 — Close checklist.** The orchestrator appends the unit's ledger row at CLOSE only when all of the following hold (mirrored in `skills/flow/references/flow-ledger.md`):

- [ ] All atoms complete (or explicitly marked skipped/blocked with note)
- [ ] Verify passed for each atom — or waiver recorded in `verify_result`
- [ ] Risks surfaced in the turn output (none silently swallowed)
- [ ] Ledger row appended (writer printed `... bytes ... APPENDED`)
- [ ] Next action named in `close.next`

**Decision 8 — Ledger (sole-writer).** The flow ledger (`<repo-root>/.sutra/flow-ledger.jsonl`, writer `bin/flow-ledger-append.sh`) has exactly ONE writer: the orchestrator, one row per unit at CLOSE. Workers report atom results up; they never append. Appends use plain `>>` with no locking — safe only under the sole-writer rule. The writer enforces: per-string cap 2048 chars (2KB) with `...[truncated]` suffix; serialized row cap 8192 bytes (8KB) with evidence-drop + degraded re-cap; and 6-pattern redaction applied to every string value BEFORE truncation:

| Pattern | Covers |
|---|---|
| `sk-[A-Za-z0-9]{8,}` | OpenAI/DeepSeek-style keys |
| `AKIA[0-9A-Z]{16}` | AWS access key ids |
| `ghp_[A-Za-z0-9]{20,}` | GitHub personal tokens |
| `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack tokens |
| `-----BEGIN [A-Z ]*KEY-----` | PEM private key headers |
| `Bearer [A-Za-z0-9._-]{15,}` | Bearer auth headers |

## Consequences

| Kind | Effect |
|---|---|
| + | Worker returns are bounded + machine-validated — orchestrator consumes typed results, not transcripts |
| + | Failure handling is replayable: 3-attempt budget + ADR-011 closed 5-set, no improvised paths |
| + | Ledger rows are capped + redacted + single-writer — durable measure/learn feed for the Estimation Engine |
| + | Flag-gated OFF: fleet installs see zero behavior change until the mode is deliberately enabled |
| − | Contract validator duplicates schema rules by design (dependency-free) — schema edits require a matching validator edit |
| − | Sole-writer ledger serializes CLOSE — parallel units in one repo must close through one orchestrator lane |
| 0 | `verify`-as-string is accepted alongside the object form (fixture-pinned); tightening to object-only would be a contract change requiring fixture + validator + schema in one commit |

## Addendum 2026-07-30 — marker state under concurrency

Orchestrator mode surfaced a race the original text never addressed: per-repo governance
markers (`.claude/<name>`) are single-slot shared state, and concurrent sessions plus
worker spawns clobbered each other's markers (19 events on 2026-07-30, including one
confirmed cross-session adoption). Root cause and migration plan:
`holding/research/2026-07-30-marker-race-root-cause.md`. Three clarifications, binding:

1. **Workers never write shared marker state.** Decision 1 ("Workers ... never write
   shared state") is made concrete for markers: a worker's marker writes land only in
   its OWN session dir; any dual-written legacy global twin is SESSION-stamped so a
   peer never adopts it and a peer's reset never deletes it.
2. **Orchestrator dispatch state lives in orchestrator context + the ledger**
   (Decision 8), never in per-repo markers. Markers carry one session's per-turn
   governance discipline; they are not a dispatch or coordination channel.
3. **Marker authority = Scheme A session dirs** (`.claude/sessions/<session-id>/<name>`,
   `hooks/marker-lib.sh`), ratified by founder 2026-07-30 — resolves the paused
   scheme-reconciliation decision. Writers go through `sutra_marker_write`; unstamped
   markers are treated as legacy during migration.
