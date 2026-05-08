/**
 * execution-pause-ledger — durable record of step.on_failure='pause' lifecycle.
 *
 * v1.3.0 Wave 4 (codex W4 advisory #3 fold + advisory #2 best-effort semantics).
 *
 * Purpose: when a Workflow step has `on_failure='pause'` and FAILS at runtime,
 * lite-executor persists a durable ExecutionPauseRecord{status:'pending'} and
 * returns ExecutionResult{status:'paused'}. The founder's `resume E-<id>`
 * (or programmatic NativeEngine.resumeFromPause) flips the record's status;
 * resume re-enters the workflow at step_index+1.
 *
 * Distinction from execution-approval-ledger:
 *   - approval-ledger: pause BEFORE running a step (requires_approval=true gate)
 *   - pause-ledger:    pause AFTER a step FAILED (on_failure='pause' handler)
 *
 * Codex W4 advisory #3 fold (mutual exclusion): pause/escalate states are
 * mutually exclusive with rollback. resumeFromPause() rejects runs already
 * escalated or in rollback — guard implemented at NativeEngine layer (this
 * file is the storage primitive only).
 *
 * Mirrors execution-approval-ledger.ts at the API + state-machine + atomic-
 * write level. Replay-safe: boot-time reload via NativeEngine constructor
 * surfaces pending pauses as informational (DO NOT auto-resume — founder
 * must explicitly approve via the NativeEngine surface).
 *
 * State machine (single transition + atomic):
 *   pending → resumed              (terminal sink — resume succeeded)
 *   pending → terminal             (terminal sink — failed run that exhausted retries
 *                                   or founder explicitly terminated; future hook)
 *   any other transition → throws (caller bug; ledger == truth).
 *
 * Storage:
 *   $SUTRA_NATIVE_HOME/runtime/pending-pauses/E-<id>.json
 *
 * Written via atomicWriteSync (fsync + atomic rename). Crash-safe: a crash
 * mid-write never leaves a torn record.
 */
import { type UserKitOptions } from './user-kit.js';
export type ExecutionPauseStatus = 'pending' | 'resumed' | 'terminal';
export interface ExecutionPauseRecord {
    /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
    readonly execution_id: string;
    /** W-<id> of the paused workflow. */
    readonly workflow_id: string;
    /** 1-based step_index of the step that FAILED + triggered the pause. */
    readonly step_index: number;
    /** State machine; see file header. */
    readonly status: ExecutionPauseStatus;
    /** Original step failure reason that triggered the pause (audit trail). */
    readonly reason: string;
    /** When the record was first written (executor pause point). */
    readonly created_at_ms: number;
    /** When status flipped pending → resumed (workflow continued). */
    readonly resumed_at_ms?: number;
    /** When status flipped pending → terminal (founder terminated / abandoned). */
    readonly terminal_at_ms?: number;
    /** Free-form reason on terminal flip (operator-supplied). */
    readonly terminal_reason?: string;
}
export declare function isExecutionPauseRecord(value: unknown): value is ExecutionPauseRecord;
/**
 * Persist an ExecutionPauseRecord to its E-<id>.json file via atomic write.
 *
 * Used at three points:
 *   1. lite-executor pause (status='pending') — on_failure='pause' handler
 *   2. NativeEngine.resumeFromPause (status='resumed' after run completes)
 *   3. Operator/founder termination (status='terminal')
 *
 * Throws TypeError on malformed input.
 */
export declare function persistPause(rec: ExecutionPauseRecord, opts?: UserKitOptions): string;
/**
 * Load a single ExecutionPauseRecord by execution_id; returns null when the
 * file does not exist or fails the validator.
 */
export declare function loadPause(execution_id: string, opts?: UserKitOptions): ExecutionPauseRecord | null;
/**
 * List all pause records, optionally filtered by status. Used by NativeEngine
 * boot-time reload to surface pending pauses as informational logs.
 */
export declare function listPauses(opts?: UserKitOptions, status_filter?: ExecutionPauseStatus): ExecutionPauseRecord[];
/**
 * Atomic state-machine transition: pending → resumed.
 *
 * Called by NativeEngine.resumeFromPause after the post-pause workflow run
 * completes. Marks the ledger entry as terminal-on-the-resume-side.
 */
export declare function markResumed(execution_id: string, opts?: UserKitOptions, now_ms?: number): ExecutionPauseRecord;
/**
 * Atomic state-machine transition: pending → terminal.
 *
 * Reserved for explicit operator termination of a paused execution that will
 * not be resumed. Future hook for `terminate E-<id> <reason>` utterance.
 */
export declare function markTerminal(execution_id: string, reason: string, opts?: UserKitOptions, now_ms?: number): ExecutionPauseRecord;
//# sourceMappingURL=execution-pause-ledger.d.ts.map