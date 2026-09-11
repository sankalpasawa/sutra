# ADR-040 — Sutra Runtime: the per-turn pipeline runs as a program

## Status

**Status**: Proposed (2026-09-11); Accepted when W3 lands (EXECUTION step 40). Author: CEO of Asawa. Direction: D73. Plan: `holding/plans/sutra-runtime/PLAN.md`.

## Context

The plugin governs each turn through 105 bash hooks (13,740 LOC, 88 registrations). Only 2 reach the model; the rest print to stderr the model cannot read. Of 72 per-turn block fields, 48 are computable today, yet the model narrates all of them; the H-Sutra header is computed every turn by `classify.sh` and discarded. Seven markers are model-written and read by 12 exit-2 hooks: self-reported evidence, the D61 theater class. Two registrations have no timeout, the auto-update hook is committed non-executable, and overhead is unmeasured.

D73 (2026-09-10): run the pipeline as a program; an LLM only where an instruction needs interpretation.

### Alternatives considered

| Option | Judge score (determinism / feasibility / fit) | Rejected because |
|---|---|---|
| Compile-first binary | 9 / 7 / 8 | editing a skill drops every gate to WARN until a recompile ships |
| Native TypeScript daemon as host | 8 / 5.5 / 6 | no synchronous return channel; Node dependency on T4; 93,690 zero-work rows |
| Status quo | n/a | gates advisory by construction; theater recurs (D61, D70) |
| Strangler over the hooks | 8.5 / 8.5 / 9 | chosen |

## Decision

The per-turn pipeline MUST run as a program that writes the evidence its gates read; the model fills judgment slots only.

- One program per hook event, driven by a declarative spec, shipped at plugin L0 (PLAN s3).
- Gate evidence is the program's own turn ledger plus host-written inputs; a model-written file is never evidence (PLAN s6).
- A block the program did not compute renders as unavailable, never as a plausible default (PLAN s6).
- Judgment stays with the session model, in its own turn; no subprocess LLM in the runtime path (PLAN s3.4).
- Replacement is family by family behind a golden corpus and a shadow window (PLAN s5).

## Consequences

| Kind | Effect |
|---|---|
| positive | gates measure truth against computed values instead of presence; header, placement, flow type, routing and trace stop being invented |
| positive | 88 registrations become 9; about 40 forks per prompt become at most 4; 13 Stop parses become 1 |
| positive | a program that did not run is detected at the next event, not passed silently |
| negative | 8 releases over about 10 weeks, each needing `/reload-plugins` per fleet box; two code paths per family until its decommission row |
| negative | sh + jq once grew to 13,740 LOC; a LOC tripwire and spec-as-data are the guard |
| neutral | a blocking prompt-hook grader (Lane B) waits for the W4 spike and a founder decision |

provenance: workflow `wf_2c287a7b-ebf`; codex on PLAN.md and on this record; D73 in `holding/FOUNDER-DIRECTIONS.md`; authored 2026-09-11, session `52fba9d2-1c6c-45c1-8071-cab86f1f0ce5`.
