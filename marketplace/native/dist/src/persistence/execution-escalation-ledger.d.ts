/**
 * execution-escalation-ledger — durable record of step.on_failure='escalate'
 * lifecycle.
 *
 * v1.3.0 Wave 4 (codex W4 advisory #3 fold).
 *
 * Purpose: when a Workflow step has `on_failure='escalate'` and FAILS at
 * runtime, lite-executor persists a durable ExecutionEscalationRecord and
 * returns ExecutionResult{status:'failed', reason:'escalated:<orig>'}. The
 * record provides a durable audit trail for human-in-the-loop intervention
 * (e.g., on-call paging, ops review) — escalations are TERMINAL by design,
 * not resumable. Escalated runs cannot be resumed via resumeFromPause
 * (codex W4 advisory #3 mutual exclusion).
 *
 * Distinction from execution-pause-ledger:
 *   - pause:     "wait for human, then resume" (recoverable)
 *   - escalate:  "wait for human review; this run is dead" (terminal)
 *
 * Simpler than the pause/approval ledgers: no state machine, no
 * pending→resolved transitions. Append-only audit log.
 *
 * Storage:
 *   $SUTRA_NATIVE_HOME/runtime/escalations/E-<id>.json
 *
 * Written via atomicWriteSync (fsync + atomic rename). Crash-safe: a crash
 * mid-write never leaves a torn record.
 */
import { type UserKitOptions } from './user-kit.js';
export interface ExecutionEscalationRecord {
    /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
    readonly execution_id: string;
    /** W-<id> of the escalated workflow. */
    readonly workflow_id: string;
    /** 1-based step_index of the step that FAILED + triggered the escalation. */
    readonly step_index: number;
    /** Original step failure reason that triggered the escalation (audit trail). */
    readonly reason: string;
    /** When the escalation was logged (executor decision point). */
    readonly created_at_ms: number;
}
export declare function isExecutionEscalationRecord(value: unknown): value is ExecutionEscalationRecord;
/**
 * Persist an ExecutionEscalationRecord to its E-<id>.json file via atomic write.
 *
 * Append-only: a single record per execution_id (callers should not
 * double-escalate; lite-executor only writes once on the failed-step path).
 *
 * Throws TypeError on malformed input.
 */
export declare function persistEscalation(rec: ExecutionEscalationRecord, opts?: UserKitOptions): string;
/**
 * Load a single ExecutionEscalationRecord by execution_id; returns null when
 * the file does not exist or fails the validator.
 *
 * Used by NativeEngine.resumeFromPause for the codex W4 advisory #3 mutual
 * exclusion guard: if an escalation record exists for the same execId, the
 * resume MUST be rejected.
 */
export declare function loadEscalation(execution_id: string, opts?: UserKitOptions): ExecutionEscalationRecord | null;
/**
 * List all escalation records. Used by NativeEngine boot-time reload to
 * surface escalations as informational logs.
 */
export declare function listEscalations(opts?: UserKitOptions): ExecutionEscalationRecord[];
//# sourceMappingURL=execution-escalation-ledger.d.ts.map