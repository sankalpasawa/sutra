/**
 * Execution fixture factories — M4.10 baseline.
 *
 * Spec source: V2 §1 P4 + V2.4 §A12 + `src/primitives/execution.ts`.
 *
 * Note: this fixture is EXTENDED in M4.2 to include `agent_identity`. M4.10
 * baseline ships the M2/M3 shape; the extension lands together with the
 * Execution schema change in M4.2.
 */

import type { Execution } from '../../src/primitives/execution.js'
import type { DataRef } from '../../src/types/index.js'

/**
 * Minimal valid Execution — terminal `success` state, empty journals,
 * agent_identity=null (M4.2 chunk 1 default).
 */
export function validMinimal(): Execution {
  return {
    id: 'E-min',
    workflow_id: 'W-min',
    trigger_event: 'tev-min',
    state: 'success',
    logs: [],
    results: [],
    parent_exec_id: null,
    sibling_group: null,
    fingerprint: 'fp-min',
    failure_reason: null,
    agent_identity: null,
  }
}

/**
 * Fully populated valid Execution — failed state with reason, sibling group,
 * one log entry, one result, and a Claude-Opus agent_identity (M4.2;
 * D-NS-10 namespace prefix applied).
 */
export function validFull(): Execution {
  const result: DataRef = {
    kind: 'json',
    schema_ref: 'native://schemas/audit',
    locator: '/tmp/audit.json',
    version: '1',
    mutability: 'immutable',
    retention: '180d',
  }
  return {
    id: 'E-full',
    workflow_id: 'W-fullexample',
    trigger_event: 'tev-full',
    state: 'failed',
    logs: [{ ts: 1700000000, kind: 'step_start', step_id: 0 }],
    results: [result],
    parent_exec_id: 'E-parent',
    sibling_group: 'sg-1',
    fingerprint: 'fp-full',
    failure_reason: 'terminal_check_failed:T1',
    agent_identity: {
      kind: 'claude-opus',
      id: 'claude-opus:session-abc',
      version: '4.7-1m',
    },
  }
}

/**
 * Invalid: state='failed' but failure_reason=null violates V2.4 §A12. Constructor must throw.
 */
export function invalidMissingRequired(): Partial<Execution> {
  return {
    id: 'E-bad',
    workflow_id: 'W-x',
    trigger_event: 'tev-x',
    state: 'failed',
    logs: [],
    results: [],
    parent_exec_id: null,
    sibling_group: null,
    fingerprint: 'fp-x',
    failure_reason: null,
  }
}
