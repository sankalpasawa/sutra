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
import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { atomicWriteSync } from './atomic-write.js';
import { userKitRoot } from './user-kit.js';
const E_ID_PATTERN = /^E-.+$/;
export function isExecutionPauseRecord(value) {
    if (typeof value !== 'object' || value === null)
        return false;
    const v = value;
    if (typeof v.execution_id !== 'string' || !E_ID_PATTERN.test(v.execution_id))
        return false;
    if (typeof v.workflow_id !== 'string' || v.workflow_id.length === 0)
        return false;
    if (typeof v.step_index !== 'number' || !Number.isInteger(v.step_index) || v.step_index < 0) {
        return false;
    }
    if (v.status !== 'pending' &&
        v.status !== 'resumed' &&
        v.status !== 'terminal')
        return false;
    if (typeof v.reason !== 'string')
        return false;
    if (typeof v.created_at_ms !== 'number' || !Number.isFinite(v.created_at_ms))
        return false;
    if (v.resumed_at_ms !== undefined && typeof v.resumed_at_ms !== 'number')
        return false;
    if (v.terminal_at_ms !== undefined && typeof v.terminal_at_ms !== 'number')
        return false;
    if (v.terminal_reason !== undefined && typeof v.terminal_reason !== 'string')
        return false;
    return true;
}
// ---------------------------------------------------------------------------
// File layout helpers (runtime/, NOT user-kit/)
// ---------------------------------------------------------------------------
function pauseDir(opts = {}) {
    return join(userKitRoot(opts), 'runtime', 'pending-pauses');
}
function ensureDir(dir) {
    mkdirSync(dir, { recursive: true });
}
function writeJson(path, value) {
    atomicWriteSync(path, JSON.stringify(value, null, 2) + '\n');
}
function readJson(path) {
    return JSON.parse(readFileSync(path, 'utf8'));
}
// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------
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
export function persistPause(rec, opts = {}) {
    if (!isExecutionPauseRecord(rec)) {
        throw new TypeError(`persistPause: malformed record (execution_id=${rec.execution_id})`);
    }
    const dir = pauseDir(opts);
    ensureDir(dir);
    const path = join(dir, `${rec.execution_id}.json`);
    writeJson(path, rec);
    return path;
}
/**
 * Load a single ExecutionPauseRecord by execution_id; returns null when the
 * file does not exist or fails the validator.
 */
export function loadPause(execution_id, opts = {}) {
    const path = join(pauseDir(opts), `${execution_id}.json`);
    if (!existsSync(path))
        return null;
    const raw = readJson(path);
    return isExecutionPauseRecord(raw) ? raw : null;
}
/**
 * List all pause records, optionally filtered by status. Used by NativeEngine
 * boot-time reload to surface pending pauses as informational logs.
 */
export function listPauses(opts = {}, status_filter) {
    const dir = pauseDir(opts);
    if (!existsSync(dir))
        return [];
    const all = readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => readJson(join(dir, f)))
        .filter(isExecutionPauseRecord);
    return status_filter ? all.filter((r) => r.status === status_filter) : all;
}
/**
 * Atomic state-machine transition: pending → resumed.
 *
 * Called by NativeEngine.resumeFromPause after the post-pause workflow run
 * completes. Marks the ledger entry as terminal-on-the-resume-side.
 */
export function markResumed(execution_id, opts = {}, now_ms = Date.now()) {
    const existing = loadPause(execution_id, opts);
    if (!existing) {
        throw new Error(`markResumed (pause-ledger): no pause record found with id "${execution_id}"`);
    }
    if (existing.status !== 'pending') {
        throw new Error(`markResumed (pause-ledger): cannot transition "${existing.status}" → "resumed" — only pending records may be resumed`);
    }
    const updated = {
        ...existing,
        status: 'resumed',
        resumed_at_ms: now_ms,
    };
    persistPause(updated, opts);
    return updated;
}
/**
 * Atomic state-machine transition: pending → terminal.
 *
 * Reserved for explicit operator termination of a paused execution that will
 * not be resumed. Future hook for `terminate E-<id> <reason>` utterance.
 */
export function markTerminal(execution_id, reason, opts = {}, now_ms = Date.now()) {
    const existing = loadPause(execution_id, opts);
    if (!existing) {
        throw new Error(`markTerminal (pause-ledger): no pause record found with id "${execution_id}"`);
    }
    if (existing.status !== 'pending') {
        throw new Error(`markTerminal (pause-ledger): cannot transition "${existing.status}" → "terminal" — only pending records may be terminalized`);
    }
    const updated = {
        ...existing,
        status: 'terminal',
        terminal_at_ms: now_ms,
        terminal_reason: reason,
    };
    persistPause(updated, opts);
    return updated;
}
//# sourceMappingURL=execution-pause-ledger.js.map