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

import { existsSync, mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

import { atomicWriteSync } from './atomic-write.js'
import { userKitRoot, type UserKitOptions } from './user-kit.js'

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

export interface ExecutionEscalationRecord {
  /** E-<turn_id>-<seq>; matches NativeEngine.executionId construction. */
  readonly execution_id: string
  /** W-<id> of the escalated workflow. */
  readonly workflow_id: string
  /** 1-based step_index of the step that FAILED + triggered the escalation. */
  readonly step_index: number
  /** Original step failure reason that triggered the escalation (audit trail). */
  readonly reason: string
  /** When the escalation was logged (executor decision point). */
  readonly created_at_ms: number
}

const E_ID_PATTERN = /^E-.+$/

export function isExecutionEscalationRecord(
  value: unknown,
): value is ExecutionEscalationRecord {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<ExecutionEscalationRecord>
  if (typeof v.execution_id !== 'string' || !E_ID_PATTERN.test(v.execution_id)) return false
  if (typeof v.workflow_id !== 'string' || v.workflow_id.length === 0) return false
  if (typeof v.step_index !== 'number' || !Number.isInteger(v.step_index) || v.step_index < 0) {
    return false
  }
  if (typeof v.reason !== 'string') return false
  if (typeof v.created_at_ms !== 'number' || !Number.isFinite(v.created_at_ms)) return false
  return true
}

// ---------------------------------------------------------------------------
// File layout helpers (runtime/, NOT user-kit/)
// ---------------------------------------------------------------------------

function escalationDir(opts: UserKitOptions = {}): string {
  return join(userKitRoot(opts), 'runtime', 'escalations')
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true })
}

function writeJson(path: string, value: unknown): void {
  atomicWriteSync(path, JSON.stringify(value, null, 2) + '\n')
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'))
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

/**
 * Persist an ExecutionEscalationRecord to its E-<id>.json file via atomic write.
 *
 * Append-only: a single record per execution_id (callers should not
 * double-escalate; lite-executor only writes once on the failed-step path).
 *
 * Throws TypeError on malformed input.
 */
export function persistEscalation(
  rec: ExecutionEscalationRecord,
  opts: UserKitOptions = {},
): string {
  if (!isExecutionEscalationRecord(rec)) {
    throw new TypeError(
      `persistEscalation: malformed record (execution_id=${(rec as { execution_id?: unknown }).execution_id})`,
    )
  }
  const dir = escalationDir(opts)
  ensureDir(dir)
  const path = join(dir, `${rec.execution_id}.json`)
  writeJson(path, rec)
  return path
}

/**
 * Load a single ExecutionEscalationRecord by execution_id; returns null when
 * the file does not exist or fails the validator.
 *
 * Used by NativeEngine.resumeFromPause for the codex W4 advisory #3 mutual
 * exclusion guard: if an escalation record exists for the same execId, the
 * resume MUST be rejected.
 */
export function loadEscalation(
  execution_id: string,
  opts: UserKitOptions = {},
): ExecutionEscalationRecord | null {
  const path = join(escalationDir(opts), `${execution_id}.json`)
  if (!existsSync(path)) return null
  const raw = readJson(path)
  return isExecutionEscalationRecord(raw) ? raw : null
}

/**
 * List all escalation records. Used by NativeEngine boot-time reload to
 * surface escalations as informational logs.
 */
export function listEscalations(
  opts: UserKitOptions = {},
): ExecutionEscalationRecord[] {
  const dir = escalationDir(opts)
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => readJson(join(dir, f)))
    .filter(isExecutionEscalationRecord)
}
