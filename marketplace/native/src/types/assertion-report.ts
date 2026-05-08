/**
 * AssertionReport — output of Verifier.verify(contract, run).
 *
 * Multi-axis structure (no aggregate score) per SPEC §5 + Agentic Rubrics
 * for SWE Agents (arXiv 2601.04171) — single aggregate scores hide which
 * dimension failed.
 *
 * Industry borrow: G-Eval (Microsoft) two-step rubric judge defines the
 * 4 axes used in tier-4. Tier-1..3 results carry the same axis tag for
 * cross-tier reporting.
 *
 * NativeRun co-located here so tier modules can import the type without
 * circular dependency on the orchestrator.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

export type AssertionTier = 'schema' | 'artifact' | 'behavior' | 'rubric'

export type AssertionAxis =
  | 'Outcome-Fidelity'
  | 'Constraint-Honor'
  | 'Cross-Stage-Drift'
  | 'Acceptance-Coverage'

export type AssertionStatus = 'PASS' | 'FAIL' | 'SKIPPED'

/**
 * Verdict semantics:
 *   PASS    = no FAIL rows
 *   PARTIAL = only tier-4 (rubric/soft) FAIL — hard tiers all PASS
 *   FAIL    = any hard-tier (schema|artifact|behavior) FAIL
 *
 * Hard-vs-soft tier classification is enforced in verify() orchestrator
 * (see contract-verifier/verifier.ts in later task).
 */
export type Verdict = 'PASS' | 'FAIL' | 'PARTIAL'

export interface AssertionResult {
  readonly id: string
  readonly tier: AssertionTier
  readonly axis: AssertionAxis
  readonly status: AssertionStatus
  readonly message: string
  readonly evidence?: string
}

export interface AssertionReport {
  readonly run_id: string
  readonly scenario_id: string
  readonly duration_ms: number
  readonly results: readonly AssertionResult[]
  readonly summary: {
    readonly total: number
    readonly pass: number
    readonly fail: number
    readonly skipped: number
  }
  readonly verdict: Verdict
}

export interface NativeEvent {
  readonly type: string
  readonly ts: number
  readonly payload?: unknown
}

export interface NativeArtifact {
  readonly stage: string
  readonly path: string
  readonly content: string
  readonly sha256: string
}

export interface NativeRun {
  readonly run_id: string
  readonly scenario_id: string
  readonly events: readonly NativeEvent[]
  readonly artifacts: readonly NativeArtifact[]
}
