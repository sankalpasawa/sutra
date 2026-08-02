/**
 * execution-approval-ledger — durable record of step-level approval lifecycle.
 *
 * v1.3.0 Wave 2 (codex W2 BLOCKER 3 fold + advisories A,E 2026-05-04).
 *
 * Purpose: when a Workflow step has `requires_approval=true`, lite-executor
 * pauses BEFORE running the step and writes a durable
 * ExecutionApprovalRecord{status:'pending'}. The founder's `approve E-<id>`
 * or `reject E-<id> <reason>` utterance flips the record's status; resume
 * loads the record on boot and continues the run from the paused step.
 *
 * Codex W2 advisory A fold: this ledger does NOT live under user-kit/ (which
 * is reserved for founder-created primitives — Domains, Charters, Workflows,
 * Triggers, Proposals). It lives at a separate runtime/execution ledger root
 * to keep the namespace clean:
 *
 *   $SUTRA_NATIVE_HOME/runtime/pending-approvals/E-<id>.json
 *
 * Mirrors proposal-ledger.ts at the API + state-machine + atomic-write level
 * (codex W2 advisory E "reuse proposal-flow ordering" fold). Replay-safe:
 *   - boot-time reload via NativeEngine constructor (operator-visible log of
 *     pending approvals; founder must explicitly approve to resume).
 *   - stale-approve idempotency: approve E-<id> for an already-decided
 *     execution returns explicit 'no-op already-handled' — never throws.
 *
 * State machine (single transition + atomic):
 *   pending → approved → resumed              (terminal sink)
 *   pending → rejected                          (terminal sink)
 *   any other transition → throws (caller bug; ledger == truth).
 *
 * Codex W2 BLOCKER 3 fold: written via atomicWriteSync (fsync + atomic rename
 * via persistence/atomic-write.ts) so a crash mid-write never leaves a torn
 * record. Stale-approve emits approval_already_handled event distinct from
 * "never existed" (which still throws / returns null per advisory D).
 */
import { type UserKitOptions } from './user-kit.js';
export type ExecutionApprovalStatus = 'pending' | 'approved' | 'rejected' | 'resumed' | 'terminal';
export interface ExecutionApprovalRecord {
    /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
    readonly execution_id: string;
    /** W-<id> of the paused workflow. */
    readonly workflow_id: string;
    /** 1-based step_index of the paused step (matches StepStartedEvent.step_index semantics). */
    readonly step_index: number;
    /** Truncated step description for founder UI (action, host if any, locator first ~200 chars). */
    readonly prompt_summary: string;
    /** State machine; see file header. */
    readonly status: ExecutionApprovalStatus;
    /** When the record was first written (executor pause point). */
    readonly created_at_ms: number;
    /** When status flipped to approved/rejected; null while pending. */
    readonly decided_at_ms?: number;
    /** Free-form reason on decision; only set on reject (approve uses the bare verb). */
    readonly decision_reason?: string;
    /** When status flipped from approved → resumed (workflow continued past the gate). */
    readonly resumed_at_ms?: number;
}
export declare function isExecutionApprovalRecord(value: unknown): value is ExecutionApprovalRecord;
/**
 * Persist an ExecutionApprovalRecord to its E-<id>.json file via atomic write.
 *
 * Used at three points:
 *   1. lite-executor pause (status='pending')
 *   2. NativeEngine.applyExecutionApproval (status='approved' / 'rejected')
 *   3. NativeEngine.resumeApproved (status='resumed' after run completes)
 *
 * Throws TypeError on malformed input; the constructor at the lite-executor
 * pause point won't reach here unless validateStep already passed, but we
 * defend at the persistence boundary anyway (codex W2 fold: type guards
 * guard, never assume callers).
 */
export declare function persistApproval(rec: ExecutionApprovalRecord, opts?: UserKitOptions): string;
/**
 * Load a single ExecutionApprovalRecord by execution_id; returns null when
 * the file does not exist. Distinguishable from "exists but malformed"
 * (returns null after JSON parse + validator miss; codex W2 advisory D —
 * stale-approve uses this null to surface a proper error).
 */
export declare function loadApproval(execution_id: string, opts?: UserKitOptions): ExecutionApprovalRecord | null;
/**
 * List all approvals, optionally filtered by status. Used by:
 *   - NativeEngine constructor boot-time reload (codex W2 BLOCKER 3 fold —
 *     surface pending approvals to operator on restart)
 *   - operator inspection commands (future)
 */
export declare function listApprovals(opts?: UserKitOptions, status_filter?: ExecutionApprovalStatus): ExecutionApprovalRecord[];
/**
 * Atomic state-machine transition: pending → approved | rejected.
 *
 * Throws on any other transition (codex W2 fold: ledger == truth, callers
 * must not silently overwrite). Stale-approve handling (approving an
 * already-approved/resumed/terminal record) is the CALLER's responsibility
 * (NativeEngine emits approval_already_handled and skips this update) —
 * this function strictly enforces the pending→{approved,rejected} edge.
 */
export declare function updateApprovalStatus(execution_id: string, next: 'approved' | 'rejected', reason: string, opts?: UserKitOptions, now_ms?: number): ExecutionApprovalRecord;
/**
 * Atomic state-machine transition: approved → resumed.
 *
 * Called by NativeEngine.resumeApproved after the post-pause workflow run
 * completes (success or failure — either way the approval gate has done its
 * job). Marks the ledger entry as terminal-on-the-resume-side so subsequent
 * approve/reject for this execution returns approval_already_handled.
 */
export declare function markResumed(execution_id: string, opts?: UserKitOptions, now_ms?: number): ExecutionApprovalRecord;
//# sourceMappingURL=execution-approval-ledger.d.ts.map