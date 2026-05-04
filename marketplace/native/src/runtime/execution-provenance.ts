/**
 * execution-provenance — N2 wirework for v1.2.2.
 *
 * Builds DecisionProvenance records for Workflow Executions in the lite
 * path. Sibling to emergence-provenance.ts; shares the same writer
 * (appendDecisionProvenanceLog). Codex pre-dispatch verdict for v1.2.2
 * (DIRECTIVE-ID: v1.2.2-wirework-prep) confirmed: reuse existing
 * decision_kind='EXECUTE' + scope='EXECUTION' enum values.
 *
 * Closes audit-identified gap N2 — "DP-record per execution NOT written
 * by lite path (full step-graph-executor writes; lite skipped)".
 */

import { createHash } from 'node:crypto'
import { createDecisionProvenance } from '../schemas/decision-provenance.js'
import type { DecisionProvenance } from '../schemas/decision-provenance.js'

export interface ExecutionDecisionInput {
  readonly workflow_id: string
  readonly execution_id: string
  readonly stage: 'STARTED' | 'COMPLETED' | 'FAILED'
  readonly ts_ms: number
  readonly outcome: string
  /** Optional: when failed, the reason string. */
  readonly failure_reason?: string
  /** Optional: charter operationalizing this Workflow (for evidence link). */
  readonly charter_id?: string
}

/**
 * Build a DecisionProvenance record for a Workflow Execution event.
 * Deterministic id: sha256(stage|workflow|execution|ts).slice(0,16).
 */
export function buildExecutionDecisionProvenance(
  input: ExecutionDecisionInput,
): DecisionProvenance {
  const idSource = `EXECUTE|${input.stage}|${input.workflow_id}|${input.execution_id}|${input.ts_ms}`
  const idHash = createHash('sha256').update(idSource).digest('hex').slice(0, 16)
  const evidence = [
    {
      kind: 'json',
      schema_ref: 'native://execution/event/v1',
      locator: `cas://execution/${input.execution_id}/${input.stage.toLowerCase()}`,
      version: '1.0.0',
      mutability: 'immutable' as const,
      retention: 'permanent',
      authoritative_status: 'authoritative' as const,
    },
  ]
  return createDecisionProvenance({
    id: `dp-${idHash}`,
    actor: 'native-engine',
    agent_identity: { kind: 'system', id: 'system:native-lite-executor' },
    timestamp: new Date(input.ts_ms).toISOString(),
    evidence,
    authority_id: input.charter_id ?? 'native-runtime',
    policy_id: 'execution-trace',
    policy_version: '1.0.0',
    confidence: 1.0,
    decision_kind: 'EXECUTE',
    scope: 'EXECUTION',
    outcome: input.outcome,
    next_action_ref: null,
  })
}
