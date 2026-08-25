<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-031-eval-engine.md. -->
# ADR-031 — Eval Engine as audit-type glue engine

One-line: every closed Work-Atom's declared check becomes a standing eval case, re-run in batch forever; the Eval Engine is the glue engine that does this.

| meta | value |
|---|---|
| **title** | ADR-031 — Eval Engine |
| **status** | Accepted (founder full-auto grant 2026-08-07; built same day) |
| **owner** | Sutra OS decisions |
| **updated** | 2026-08-07 |
| **source inputs** | holding/plans/eval-program/ (GROUNDING, ARCHITECTURE D-1..D-7), codex consult 019fdb7d |

## Status {#status}

Accepted. Implementation live 2026-08-07 (asawa-holding L1/L2; plugin L0 promotion tracked at eval-program step 51).

## Context {#context}

A Work-Atom declares its check before work and runs it exactly once at close (ADR-029 Directional). Nothing re-runs checks afterward: decay (T1→T4 per ADR-030 four-problem-types) is unmeasured, system changes are untested against past work, and judge verdicts (codex/deepseek gate-logs) are collected but never audited. Industry (2026) commoditized single-output scoring; system-level evaluation of work records remains open — and the atom substrate already contains exactly what evals need (goal + pre-declared runnable check per unit).

## Decision {#decision}

1. Mint the **Eval Engine** as a glue engine of audit type (sibling of the daily governance audit): reads atom records, never mutates work engines.
2. **Runner = Inspect AI** (UK AISI, MIT): atoms export to Samples (goal=input; verify spec as structured JSON metadata — argv preserved exactly); decay lane runs `model=none` with a no-op solver; grader lane runs `model_graded_qa` on any Anthropic-compatible endpoint.
3. **Check execution goes through a shared verify-runner** (`holding/bin/verify-runner.sh`, L1) reproducing atom-close semantics: pinned template registry, repo-root cwd, 30s alarm, dotdot refusal, envelope containment, named-test SHA pin. Wiring `sutra-atom close` itself onto this lib is a gated follow-up (atom test suite = acceptance).
4. **Tag taxonomy governs scoring**: decay-sensitive (scored nightly) · frozen (history, excluded) · env-bound (excluded) · sandbox-required (named-test; excluded until sandboxed).
5. **Nightly contract**: launchd job → normalized findings rows (summary info / per-atom WARN decay / CRITICAL eval-infra) at `holding/observability/eval-nightly/findings.jsonl`; infra failure is never reported as decay.

## Consequences {#consequences}

| Kind | Consequence |
|---|---|
| Positive | decay is a nightly number (first run 2026-08-07: 122/132 pass, 10 real decay findings incl. one deleted shipped artifact) |
| Positive | evals-of-evals live: verify-quality judge graded 10/10 sampled checks WEAK with reasoning receipts — check-quality debt now measurable |
| Positive | third existence proof of X3 (glue engine above work engines) |
| Negative | Python/uv toolchain enters the stack (isolated venv; system Python untouched) |
| Negative | curation debt: tags need upkeep or the score dilutes |
| Open | judge calibration vs founder labels pending; docker sandbox absent on current host; decay severity ratchet policy TODO(founder) |

## Provenance {#provenance}

Authored 2026-08-07 session 2ca6e5c3 (eval-program Phase J step 48); codex consult 019fdb7d CHANGES-REQUIRED folds are decisions 3/4/2 above.

```yaml
provenance:
  authored: 2026-08-07
  session: 2ca6e5c3-30f8-4560-9a20-09e27a68f4f1
  atom: a-2ca6e5c3-10
  standard: writing-llm-md v1.1 + Nygard ADR
  supersedes: holding/plans/eval-program/ADR-031-draft.md
```
