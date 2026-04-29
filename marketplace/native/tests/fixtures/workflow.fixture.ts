/**
 * Workflow fixture factories — M4.10 baseline.
 *
 * Spec source: V2 §1 P3 + V2.1-V2.4 amendments + `src/primitives/workflow.ts`.
 *
 * Note: this fixture is EXTENDED in M4.4 to include `custody_owner`. M4.10
 * baseline ships the M2/M3 shape; the extension lands together with the
 * Workflow schema change in M4.4.
 */

import type { Workflow } from '../../src/primitives/workflow.js'
import type { DataRef, WorkflowStep } from '../../src/types/index.js'

/**
 * Minimal valid Workflow — single-step task, no interfaces, all defaults.
 */
export function validMinimal(): Workflow {
  const step: WorkflowStep = {
    step_id: 0,
    action: 'wait',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  return {
    id: 'W-min',
    preconditions: '',
    step_graph: [step],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    expects_response_from: null,
    on_override_action: 'escalate',
    reuse_tag: false,
    return_contract: null,
    modifies_sutra: false,
    custody_owner: null,
    extension_ref: null,
  }
}

/**
 * Fully populated valid Workflow — multi-step Skill (reuse_tag=true) with a
 * return_contract, no modifies_sutra. M4.4: explicit custody_owner declared.
 * M4.5: extension_ref left null (v1.0 enforcement).
 */
export function validFull(): Workflow {
  const dataRef: DataRef = {
    kind: 'json',
    schema_ref: 'native://schemas/checkpoint',
    locator: '/tmp/checkpoint.json',
    version: '1',
    mutability: 'immutable',
    retention: '30d',
  }
  const step1: WorkflowStep = {
    step_id: 0,
    skill_ref: 'core:depth-estimation',
    inputs: [dataRef],
    outputs: [dataRef],
    on_failure: 'rollback',
  }
  const step2: WorkflowStep = {
    step_id: 1,
    action: 'spawn_sub_unit',
    inputs: [dataRef],
    outputs: [],
    on_failure: 'escalate',
  }
  return {
    id: 'W-fullexample',
    preconditions: 'depth_marker_present',
    step_graph: [step1, step2],
    inputs: [dataRef],
    outputs: [dataRef],
    state: [dataRef],
    postconditions: 'execution_log_emitted',
    failure_policy: 'rollback-then-escalate',
    stringency: 'process',
    interfaces_with: [],
    expects_response_from: null,
    on_override_action: 'pause',
    reuse_tag: true,
    return_contract: 'native://schemas/checkpoint',
    modifies_sutra: false,
    custody_owner: 'T-asawa-holding',
    extension_ref: null,
  }
}

/**
 * Invalid: missing required `step_graph`. Constructor must throw.
 */
export function invalidMissingRequired(): Partial<Workflow> {
  return {
    id: 'W-no-steps',
    preconditions: '',
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: '',
    stringency: 'task',
    interfaces_with: [],
  }
}
