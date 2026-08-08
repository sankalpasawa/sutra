# ADR-032 — The Verifier Layer (verification disaggregated from the atom)

| meta | value |
|---|---|
| **status** | Accepted (founder-directed 2026-08-08, session b33bbd62) |
| **context inputs** | ADR-031 (Eval Engine), VERIFIER-LEDGER.md V-1..V-68, codex challenge DIRECTIVE-ID 1786173107 round-2 PASS, deepseek P0 review |
| **supersedes** | narrows ADR-031's "atom close owns verification" framing |

## Context

Work-Atoms declared and ran their checks as one welded unit: declaration at
open, execution at close, replay at nightly. The weld produced a type error
at scale — unit goal-state snapshots were replayed forever as if they were
invariants, and 10 of 141 nightly cases failed permanently for no real
reason (2026-08-07 diagnosis).

## Decision

Verification is a standalone layer with a four-way split:

| Layer | What | Where |
|---|---|---|
| DECLARATION | check spec + SCOPE (`unit` / `invariant` / `capability`) | check registry (`holding/state/verifier/registry.jsonl`) |
| BINDING | `{attach, mode: gate\|observe, life}` | registry rows + `sutra-verify bind` |
| EXECUTION | one shared runner, zero context | `verify-runner.sh` (+ docker sandbox lane for `named-test`) |
| JUDGMENT | mechanical / model-graded (3-epoch majority) / agent-redo | decay, grader, capability lanes |

Rules with force:
1. **Supersede is the type system**: unit checks sharing a verify-target
   file collapse to the latest close; losers carry `superseded_by`. Result
   on day one: 108 of 243 checks superseded, standing fails 10 -> 1 (real).
2. **Invariants are hand-declared only** — `invariants.json` or
   `sutra-verify promote --reason`; never inferred.
3. **The nightly never gates.** Gate bindings live at `atom.close`,
   `deploy.pre` (`predeploy-check.sh`), `workflow.close`.
4. **Run outcomes** `pass|fail|skip|error|stale_binding` with full
   provenance (check_id, atom_id, commit_sha, runner_version, command,
   exit_code, duration_ms, started_at).
5. **atom open = declaration surface; atom close = one binding among many.**

## Consequences

- The nightly scorecard measures decay, not history: 92 scored (87 unit +
  5 invariant), 91 pass on cutover day.
- BLUEPRINT per-step Verify, FLOW close-measure, and PHASE-EXIT-VERIFY are
  future declaration surfaces of the same registry (V5 rebind, partially
  landed as `workflow.close` bindings).
- Capability lane (agent redo in docker) is scoped unit-only and hard-gated
  until the scorer runs container-side (V-55 sentinel; docker absent on the
  authoring host).
- Desktop app carries an Evals screen reading the registry + runs
  read-only; deep transcripts stay in Inspect's viewer.

Program of record: `holding/plans/eval-program/VERIFIER-LEDGER.md`.

## Provenance {#provenance}

```yaml
provenance:
  authored: 2026-08-08
  session: b33bbd62-a499-4ca6-b735-8e242b57200c
  atom: a-b33bbd62-13
  consult: codex DIRECTIVE-ID 1786173107 round-2 PASS + deepseek P0 (5 folds)
  standard: writing-llm-md v1.1
  supersedes: narrows ADR-031 verification framing
```
