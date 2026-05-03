/**
 * EXECUTION — V2 §1 P4 + V2.4 §A12 (failure_reason)
 *
 * Runtime materialization of one Workflow activation.
 * Triggered by TriggerSpec via `activates` link (per L3 ACTIVATION).
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §1 P4 + §19 A12
 */
import type { Asset, DataRef, ExecutionState } from '../types/index.js';
import { type AgentIdentity } from '../types/agent-identity.js';
/**
 * One log entry in the Execution event journal. Shape kept open (Record) on purpose:
 * the journal accepts arbitrary structured events; the Workflow Engine writes typed entries
 * downstream, but the primitive itself does not constrain the log schema beyond "object".
 */
export type ExecutionLogEntry = Record<string, unknown>;
/**
 * Execution primitive shape — V2 §1 P4 + V2.4 §A12.
 */
export interface Execution {
    id: string;
    workflow_id: string;
    trigger_event: string;
    state: ExecutionState;
    logs: ExecutionLogEntry[];
    results: Array<DataRef | Asset>;
    parent_exec_id: string | null;
    sibling_group: string | null;
    fingerprint: string;
    /**
     * V2.4 §A12: must be non-null iff state='failed' (e.g., 'terminal_check_failed:T1').
     * For all other states this is null.
     */
    failure_reason: string | null;
    /**
     * M4.2 — D1 P-A2 / V2.5 §A14: which LLM/agent made this Execution's decisions.
     * Optional in v1.0 (default null); F-7 (modifies_sutra=true ⇒ agent_identity
     * required) lands at M4.9 chunk 2.
     */
    agent_identity: AgentIdentity | null;
}
/** Caller may omit failure_reason and agent_identity; createExecution fills defaults. */
export type ExecutionSpec = Omit<Execution, 'failure_reason' | 'agent_identity'> & {
    failure_reason?: string | null;
    agent_identity?: AgentIdentity | null;
};
/**
 * Construct an Execution after validating shape + V2.4 failure_reason invariants.
 * Returns a frozen object.
 */
export declare function createExecution(spec: ExecutionSpec): Execution;
/**
 * Predicate: is this Execution shape valid against V2 §1 P4 + V2.4 §A12?
 */
export declare function isValidExecution(e: Execution): boolean;
/**
 * Predicate: is the proposed state transition allowed by the V2 §1 P4 lifecycle?
 *
 * Used by:
 * - Workflow Engine `dispatch` → `terminate` stage (V2 §16 Layer 2)
 * - audit replay against the JSONL event log
 */
export declare function isValidStateTransition(from: ExecutionState, to: ExecutionState): boolean;
//# sourceMappingURL=execution.d.ts.map