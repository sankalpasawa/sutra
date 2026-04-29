import { describe, it, expect } from 'vitest'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import type { DataRef, WorkflowStep } from '../../src/types/index.js'

const dr = (kind: string): DataRef => ({
  kind,
  schema_ref: 'schema://x',
  locator: 'mem://x',
  version: 'v1',
  mutability: 'immutable',
  retention: '7d',
})

describe('Workflow primitive (V2 §1 P3 + V2.1 §A4 + V2.2 §A10 + V2.3 §A11 + V2.4 §A12)', () => {
  it('creates a minimal workflow with default flag values', () => {
    const w = createWorkflow({
      id: 'W-min',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          skill_ref: 'noop',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(isValidWorkflow(w)).toBe(true)
    // V2.3 §A11 default
    expect(w.reuse_tag).toBe(false)
    // V2.4 §A12 default
    expect(w.modifies_sutra).toBe(false)
    // V2.2 §A10 default
    expect(w.on_override_action).toBe('escalate')
    // V2.1 §A4 default
    expect(w.expects_response_from).toBeNull()
    // V2.3 §A11 — return_contract optional (defaults to null)
    expect(w.return_contract).toBeNull()
  })

  it('creates a Skill (Workflow with reuse_tag=true) per V2.3 §A11', () => {
    const skill = createWorkflow({
      id: 'W-skill',
      preconditions: 'always',
      step_graph: [
        { step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'escalate' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'escalate',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      return_contract: 'schema://skill-result',
    })
    expect(skill.reuse_tag).toBe(true)
    expect(skill.return_contract).toBe('schema://skill-result')
  })

  it('rejects step with BOTH skill_ref and action (XOR violation)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            skill_ref: 'foo',
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action|mutually exclusive/i)
  })

  it('rejects step with NEITHER skill_ref nor action (L2 BOUNDARY violation)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-empty-step',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/skill_ref XOR action|must specify/i)
  })

  it('rejects empty step_graph (workflow must do something)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-empty',
        preconditions: 'true',
        step_graph: [],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/step_graph/)
  })

  it('rejects non-W-prefixed id', () => {
    expect(() =>
      createWorkflow({
        id: 'X-nope',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/Workflow\.id/)
  })

  it('accepts all stringency values', () => {
    for (const s of ['task', 'process', 'protocol'] as const) {
      const w = createWorkflow({
        id: `W-${s}`,
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: s,
        interfaces_with: [],
      })
      expect(w.stringency).toBe(s)
    }
  })

  it('accepts all on_override_action values per V2.2 §A10', () => {
    for (const action of ['pause', 'splice', 'restart', 'escalate'] as const) {
      const w = createWorkflow({
        id: `W-${action}`,
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        on_override_action: action,
      })
      expect(w.on_override_action).toBe(action)
    }
  })

  it('rejects invalid stringency value', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-string',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        // @ts-expect-error — runtime guard
        stringency: 'optional',
        interfaces_with: [],
      }),
    ).toThrow(/stringency/)
  })

  it('preserves DataRef arrays in inputs/outputs/state', () => {
    const w = createWorkflow({
      id: 'W-data',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, skill_ref: 'consume', inputs: [dr('in')], outputs: [dr('out')], on_failure: 'abort' },
      ],
      inputs: [dr('w-in')],
      outputs: [dr('w-out')],
      state: [dr('w-state')],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(w.inputs).toHaveLength(1)
    expect(w.outputs).toHaveLength(1)
    expect(w.state).toHaveLength(1)
    expect(w.inputs[0]?.kind).toBe('w-in')
  })

  it('returned Workflow is frozen', () => {
    const w = createWorkflow({
      id: 'W-froz',
      preconditions: 'true',
      step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(Object.isFrozen(w)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // P1.1 — V2.3 §A11: Skill (reuse_tag=true) MUST have a return_contract schema-ref
  // ---------------------------------------------------------------------------

  it('P1.1: rejects reuse_tag=true with return_contract=null', () => {
    expect(() =>
      createWorkflow({
        id: 'W-skill-null-rc',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        reuse_tag: true,
        return_contract: null,
      }),
    ).toThrow(/return_contract.*reuse_tag=true|V2\.3 §A11/i)
  })

  it('P1.1: rejects reuse_tag=true with return_contract omitted', () => {
    expect(() =>
      createWorkflow({
        id: 'W-skill-undef-rc',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        reuse_tag: true,
      }),
    ).toThrow(/return_contract.*reuse_tag=true|V2\.3 §A11/i)
  })

  it('P1.1: rejects reuse_tag=true with empty-string return_contract', () => {
    expect(() =>
      createWorkflow({
        id: 'W-skill-empty-rc',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        reuse_tag: true,
        return_contract: '',
      }),
    ).toThrow(/return_contract.*reuse_tag=true|V2\.3 §A11/i)
  })

  it('P2 (codex re-review): rejects reuse_tag=false with empty-string return_contract (constructor/validator alignment)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-nonskill-empty-rc',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        reuse_tag: false,
        return_contract: '',
      }),
    ).toThrow(/return_contract.*reuse_tag=false|constructor\/validator alignment/i)
  })

  it('P1.1: accepts reuse_tag=true with non-empty return_contract', () => {
    const skill = createWorkflow({
      id: 'W-skill-ok',
      preconditions: 'true',
      step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      return_contract: 'schema-ref-v1',
    })
    expect(skill.reuse_tag).toBe(true)
    expect(skill.return_contract).toBe('schema-ref-v1')
    expect(isValidWorkflow(skill)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // P1.2 — V2 §3 HARD: routing/gating fields strictly validated
  // ---------------------------------------------------------------------------

  it('P1.2(a): rejects step.on_failure outside StepFailureAction enum (createWorkflow)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-onfail',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            action: 'terminate',
            inputs: [],
            outputs: [],
            // @ts-expect-error — runtime guard
            on_failure: 'garbage',
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/on_failure.*rollback\|escalate\|pause\|abort\|continue/i)
  })

  it('P1.2(a): isValidWorkflow returns false for step.on_failure="garbage"', () => {
    // Build a record bypassing the constructor (simulating deserialized JSONL)
    const bad = {
      id: 'W-deser-onfail',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'terminate' as const,
          inputs: [],
          outputs: [],
          on_failure: 'garbage' as unknown as 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('P1.2(b): rejects expects_response_from = empty string (createWorkflow)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-erf',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        expects_response_from: '',
      }),
    ).toThrow(/expects_response_from/i)
  })

  it('P1.2(b): isValidWorkflow returns false for expects_response_from = empty string', () => {
    const bad = {
      id: 'W-deser-erf',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, action: 'terminate' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: '',
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('P1.2(c): isValidWorkflow returns false for modifies_sutra = "true" (string not bool)', () => {
    const bad = {
      id: 'W-deser-mod',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, action: 'terminate' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      // simulate deserialized record where boolean became string
      modifies_sutra: 'true' as unknown as boolean,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('P1.2(c): createWorkflow rejects non-boolean modifies_sutra at boundary', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-mod',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        // @ts-expect-error — runtime guard
        modifies_sutra: 'true',
      }),
    ).toThrow(/modifies_sutra/i)
  })

  it('P1.2: rejects on_override_action="splat" (not in V2.2 §A10 enum)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-override',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        // @ts-expect-error — runtime guard
        on_override_action: 'splat',
      }),
    ).toThrow(/on_override_action/i)
  })

  it('P1.2: isValidWorkflow returns false for on_override_action="splat" on deserialized record', () => {
    const bad = {
      id: 'W-deser-override',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, action: 'terminate' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'splat' as unknown as 'escalate',
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('P1.2: accepts expects_response_from = non-empty BoundaryEndpointRef string', () => {
    const w = createWorkflow({
      id: 'W-erf-ok',
      preconditions: 'true',
      step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      expects_response_from: 'codex://reviewer',
    })
    expect(w.expects_response_from).toBe('codex://reviewer')
    expect(isValidWorkflow(w)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // Codex M3 P1 #2 (2026-04-28) — step_id MUST be unique within step_graph.
  // L4/T3 keys per-step coverage by step_id; duplicates would silently collapse
  // coverage records and let unsoundness through.
  // ---------------------------------------------------------------------------

  it('P1.2 (codex M3 P1 #2): rejects duplicate step_ids in step_graph (createWorkflow)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-dup-step',
        preconditions: 'true',
        step_graph: [
          { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
          { step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/step_id.*duplicate|unique/i)
  })

  it('P1.2 (codex M3 P1 #2): rejects duplicate step_ids on triple-step duplicate (createWorkflow)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-dup-step-3',
        preconditions: 'true',
        step_graph: [
          { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
          { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
          { step_id: 0, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/step_id.*duplicate|unique/i)
  })

  it('P1.2 (codex M3 P1 #2): isValidWorkflow returns false for deserialized record with duplicate step_ids', () => {
    const bad = {
      id: 'W-deser-dup-step',
      preconditions: 'true',
      step_graph: [
        { step_id: 7, action: 'wait' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
        { step_id: 7, action: 'terminate' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('P1.2 (codex M3 P1 #2): accepts step_graph with all unique step_ids', () => {
    const w = createWorkflow({
      id: 'W-uniq-steps',
      preconditions: 'true',
      step_graph: [
        { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(w.step_graph).toHaveLength(3)
    expect(isValidWorkflow(w)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // M5 Group J — T-045: Workflow.autonomy_level (manual|semi|autonomous, default 'manual')
  // Spec: holding/plans/native-v1.0/M5-workflow-engine.md Group J + A-3.
  // required_capabilities[] REMOVED per codex P1.2 (deferred to v1.x per D-NS-9 (b)).
  // ---------------------------------------------------------------------------

  it('T-045: defaults autonomy_level to "manual" when omitted', () => {
    const w = createWorkflow({
      id: 'W-auto-default',
      preconditions: 'true',
      step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(w.autonomy_level).toBe('manual')
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('T-045: round-trips all 3 autonomy_level enum values', () => {
    for (const level of ['manual', 'semi', 'autonomous'] as const) {
      const w = createWorkflow({
        id: `W-auto-${level}`,
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        autonomy_level: level,
      })
      expect(w.autonomy_level).toBe(level)
      expect(isValidWorkflow(w)).toBe(true)
    }
  })

  it('T-045: rejects invalid autonomy_level value at constructor (createWorkflow)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad-autonomy',
        preconditions: 'true',
        step_graph: [{ step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' }],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
        // @ts-expect-error — runtime guard
        autonomy_level: 'fully_automatic',
      }),
    ).toThrow(/autonomy_level/i)
  })

  it('T-045: isValidWorkflow returns false for deserialized record with invalid autonomy_level', () => {
    const bad = {
      id: 'W-deser-autonomy',
      preconditions: 'true',
      step_graph: [
        { step_id: 1, action: 'terminate' as const, inputs: [], outputs: [], on_failure: 'abort' as const },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'fully_automatic' as unknown as 'manual',
    }
    expect(isValidWorkflow(bad)).toBe(false)
  })
})
