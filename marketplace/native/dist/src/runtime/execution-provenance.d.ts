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
import type { DecisionProvenance } from '../schemas/decision-provenance.js';
export interface ExecutionDecisionInput {
    readonly workflow_id: string;
    readonly execution_id: string;
    readonly stage: 'STARTED' | 'COMPLETED' | 'FAILED';
    readonly ts_ms: number;
    readonly outcome: string;
    /** Optional: when failed, the reason string. */
    readonly failure_reason?: string;
    /** Optional: charter operationalizing this Workflow (for evidence link). */
    readonly charter_id?: string;
}
/**
 * Build a DecisionProvenance record for a Workflow Execution event.
 * Deterministic id: sha256(stage|workflow|execution|ts).slice(0,16).
 */
export declare function buildExecutionDecisionProvenance(input: ExecutionDecisionInput): DecisionProvenance;
//# sourceMappingURL=execution-provenance.d.ts.map