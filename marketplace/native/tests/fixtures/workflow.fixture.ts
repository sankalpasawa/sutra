/**
 * Workflow fixture factories — M4.10 baseline + M5 Group J variants.
 *
 * Spec source: V2 §1 P3 + V2.1-V2.4 amendments + `src/primitives/workflow.ts`.
 *
 * Note: this fixture was EXTENDED in M4.4 to include `custody_owner`, and again
 * in M5 Group J / T-048 with `validMinimalAutonomous` / `validSemiAutonomy` /
 * `invalidAutonomyLevel` factories for the new `autonomy_level` routing field.
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
    autonomy_level: 'manual',
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
    autonomy_level: 'manual',
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

// -----------------------------------------------------------------------------
// M5 Group J / T-048 — autonomy_level fixture variants
//
// These factories cover the 3-enum routing field added in T-045. Sourced from
// `validMinimal` and tweaked so consumers get a deterministic record per level.
// Round-trip + reject contracts asserted in `tests/fixtures/fixtures.test.ts`.
// -----------------------------------------------------------------------------

/**
 * Minimal valid Workflow with autonomy_level='autonomous' — runtime is
 * permitted to advance without human gate. Useful as a positive test for
 * Group K's failure_policy auto-escalate path.
 */
export function validMinimalAutonomous(): Workflow {
  const step: WorkflowStep = {
    step_id: 0,
    action: 'wait',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  return {
    id: 'W-min-autonomous',
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
    autonomy_level: 'autonomous',
  }
}

/**
 * Minimal valid Workflow with autonomy_level='semi' — human-in-loop default.
 */
export function validSemiAutonomy(): Workflow {
  const step: WorkflowStep = {
    step_id: 0,
    action: 'wait',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  return {
    id: 'W-min-semi',
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
    autonomy_level: 'semi',
  }
}

/**
 * Invalid: autonomy_level outside the {manual,semi,autonomous} enum.
 * Constructor MUST throw; validator MUST return false. Returned as
 * `Partial<Workflow>` so the type system permits the invalid literal value.
 */
export function invalidAutonomyLevel(): Partial<Workflow> {
  const step: WorkflowStep = {
    step_id: 0,
    action: 'wait',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  return {
    id: 'W-bad-autonomy',
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
    // intentionally invalid — constructor + validator must reject.
    autonomy_level: 'fully_automatic' as unknown as Workflow['autonomy_level'],
  }
}
