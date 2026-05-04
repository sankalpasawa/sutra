/**
 * Contract tests — RendererRegistry + 8 default terminal renderers
 * (D2 step 4 of vertical slice).
 *
 * Coverage:
 *   schema           — isEngineEvent guard accepts/rejects shapes;
 *                      ENGINE_EVENT_TYPES has all 8 keys
 *   registry         — defaults registered on construction;
 *                      skip_defaults yields empty registry;
 *                      register/unregister/hasOverride/resolve/
 *                      getRegisteredTypes; rejects unknown event_type;
 *                      rejects non-function renderer
 *   render()         — delegates to resolved renderer;
 *                      returns null for unregistered type;
 *                      catches renderer exceptions (returns error line,
 *                      never throws to caller — engine render loop safety)
 *   8 defaults       — each event type produces a sensible terminal line
 *                      with cell-prefix when hsutra context provided
 *   override         — operator override produces custom output
 *                      unregister restores default
 */

import { describe, it, expect } from 'vitest'
import {
  RendererRegistry,
  DEFAULT_RENDERERS,
  defaultRenderRoutingDecision,
  defaultRenderWorkflowStarted,
  defaultRenderWorkflowCompleted,
  defaultRenderWorkflowFailed,
  defaultRenderArtifactRegistered,
  defaultRenderPolicyDecision,
  defaultRenderStepStarted,
  defaultRenderStepCompleted,
  type Renderer,
} from '../../../src/runtime/renderer-registry.js'
import {
  ENGINE_EVENT_TYPES,
  isEngineEvent,
  type EngineEvent,
  type RoutingDecisionEvent,
  type RenderContext,
} from '../../../src/types/engine-event.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'

const ts = 1700000000000

describe('engine-event schema', () => {
  it('ENGINE_EVENT_TYPES contains exactly the 25 expected types (v1.2 added 3, v1.3 W2 added 4, v1.3 W4 added 7, v1.3 W5 added 3)', () => {
    expect(ENGINE_EVENT_TYPES.size).toBe(25)
    expect(ENGINE_EVENT_TYPES.has('routing_decision')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_started')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_completed')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_failed')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('artifact_registered')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('policy_decision')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('step_started')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('step_completed')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('pattern_proposed')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('proposal_approved')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('proposal_rejected')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('approval_requested')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('approval_granted')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('approval_denied')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('approval_already_handled')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_rollback_started')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('step_compensated')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('step_compensation_failed')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_rollback_complete')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_rollback_partial')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('workflow_escalated')).toBe(true)
    expect(ENGINE_EVENT_TYPES.has('step_paused')).toBe(true)
  })

  it('isEngineEvent accepts a valid event', () => {
    expect(isEngineEvent({ type: 'workflow_started', ts_ms: ts, workflow_id: 'wf', execution_id: 'E-1' })).toBe(true)
  })

  it('isEngineEvent rejects unknown event_type', () => {
    expect(isEngineEvent({ type: 'made_up', ts_ms: ts })).toBe(false)
  })

  it('isEngineEvent rejects negative or non-finite ts_ms', () => {
    expect(isEngineEvent({ type: 'routing_decision', ts_ms: -1 })).toBe(false)
    expect(isEngineEvent({ type: 'routing_decision', ts_ms: Number.POSITIVE_INFINITY })).toBe(false)
    expect(isEngineEvent({ type: 'routing_decision', ts_ms: 'not-a-number' })).toBe(false)
  })

  it('isEngineEvent rejects null / non-object / array', () => {
    expect(isEngineEvent(null)).toBe(false)
    expect(isEngineEvent('string')).toBe(false)
    expect(isEngineEvent([{ type: 'workflow_started', ts_ms: ts }])).toBe(false)
  })
})

describe('RendererRegistry — construction + defaults', () => {
  it('registers all 25 defaults on construction (v1.2 added 3, v1.3 W2 added 4, v1.3 W4 added 7, v1.3 W5 added 3)', () => {
    const r = new RendererRegistry()
    const types = r.getRegisteredTypes()
    expect(types.length).toBe(25)
    for (const t of ENGINE_EVENT_TYPES) {
      expect(r.resolve(t)).toBe(DEFAULT_RENDERERS[t])
    }
  })

  it('skip_defaults yields empty registry', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    expect(r.getRegisteredTypes()).toEqual([])
    expect(r.resolve('routing_decision')).toBeNull()
  })

  it('hasOverride is false for defaults, true for overrides', () => {
    const r = new RendererRegistry()
    expect(r.hasOverride('workflow_started')).toBe(false)
    r.register('workflow_started', () => 'custom')
    expect(r.hasOverride('workflow_started')).toBe(true)
  })

  it('DEFAULT_RENDERERS is frozen', () => {
    expect(Object.isFrozen(DEFAULT_RENDERERS)).toBe(true)
  })
})

describe('RendererRegistry — register / unregister', () => {
  it('register overrides the default', () => {
    const r = new RendererRegistry()
    const stub: Renderer = () => 'STUB'
    r.register('workflow_started', stub)
    expect(r.resolve('workflow_started')).toBe(stub)
  })

  it('unregister restores the default', () => {
    const r = new RendererRegistry()
    r.register('workflow_started', () => 'STUB')
    expect(r.unregister('workflow_started')).toBe(true)
    expect(r.resolve('workflow_started')).toBe(DEFAULT_RENDERERS.workflow_started)
    expect(r.hasOverride('workflow_started')).toBe(false)
  })

  it('unregister returns false when no override exists', () => {
    const r = new RendererRegistry()
    expect(r.unregister('workflow_started')).toBe(false)
  })

  it('register throws on unknown event_type', () => {
    const r = new RendererRegistry()
    expect(() => r.register('made_up' as never, () => '')).toThrow(TypeError)
  })

  it('register throws when renderer is not a function', () => {
    const r = new RendererRegistry()
    expect(() => r.register('workflow_started', 'not-a-fn' as unknown as Renderer)).toThrow(TypeError)
  })

  it('unregister with skip_defaults removes the entry entirely', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    r.register('workflow_started', () => 'X')
    expect(r.unregister('workflow_started')).toBe(true)
    expect(r.resolve('workflow_started')).toBeNull()
  })
})

describe('RendererRegistry — render() safety', () => {
  it('render returns null for unregistered event type (no defaults case)', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    const event: RoutingDecisionEvent = {
      type: 'routing_decision',
      ts_ms: ts,
      turn_id: null,
      mode: 'no-match',
      workflow_id: null,
      trigger_id: null,
      attempts_count: 0,
    }
    expect(r.render(event)).toBeNull()
  })

  it('render delegates to the registered renderer + returns its string', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    r.register('workflow_started', () => 'CUSTOM-LINE')
    expect(
      r.render({
        type: 'workflow_started',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
      }),
    ).toBe('CUSTOM-LINE')
  })

  it('render catches renderer exceptions + emits a fallback line (engine render-loop safety)', () => {
    const r = new RendererRegistry()
    r.register('workflow_started', () => {
      throw new Error('renderer exploded')
    })
    const out = r.render({
      type: 'workflow_started',
      ts_ms: ts,
      workflow_id: 'wf',
      execution_id: 'E-1',
    })
    expect(out).toContain('render-error:workflow_started')
    expect(out).toContain('renderer exploded')
  })

  it('render passes RenderContext through to the renderer', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    let capturedCtx: RenderContext | null = null
    r.register('workflow_started', (_e, ctx) => {
      capturedCtx = ctx
      return 'ok'
    })
    const ctx: RenderContext = { now_ms: 12345 }
    r.render(
      {
        type: 'workflow_started',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
      },
      ctx,
    )
    expect(capturedCtx).toEqual(ctx)
  })
})

describe('default renderers — content checks', () => {
  const hsutra: HSutraEvent = { turn_id: 't-9', cell: 'DIRECT·INBOUND' }
  const ctxNoCell: RenderContext = {}
  const ctxWithCell: RenderContext = { hsutra }

  it('routing_decision (exact match) prints router + workflow + trigger + attempts', () => {
    const e: EngineEvent = {
      type: 'routing_decision',
      ts_ms: ts,
      turn_id: 't-9',
      mode: 'exact',
      workflow_id: 'wf-build',
      trigger_id: 'T-build',
      attempts_count: 1,
    }
    const out = defaultRenderRoutingDecision(e, ctxNoCell)
    expect(out).toContain('[router]')
    expect(out).toContain('exact')
    expect(out).toContain('wf-build')
    expect(out).toContain('T-build')
    expect(out).toContain('1 attempt')
    expect(out).not.toContain('1 attempts')
  })

  it('routing_decision (no-match) prints ∅ workflow + plural attempts', () => {
    const e: EngineEvent = {
      type: 'routing_decision',
      ts_ms: ts,
      turn_id: null,
      mode: 'no-match',
      workflow_id: null,
      trigger_id: null,
      attempts_count: 3,
    }
    const out = defaultRenderRoutingDecision(e, ctxNoCell)
    expect(out).toContain('∅')
    expect(out).toContain('3 attempts')
  })

  it('routing_decision prefixes cell when hsutra provided', () => {
    const e: EngineEvent = {
      type: 'routing_decision',
      ts_ms: ts,
      turn_id: 't-9',
      mode: 'exact',
      workflow_id: 'wf',
      trigger_id: 'T',
      attempts_count: 1,
    }
    const out = defaultRenderRoutingDecision(e, ctxWithCell)
    expect(out.startsWith('[DIRECT·INBOUND] ')).toBe(true)
  })

  it('workflow_started includes workflow_id + execution_id', () => {
    const out = defaultRenderWorkflowStarted(
      { type: 'workflow_started', ts_ms: ts, workflow_id: 'wf-x', execution_id: 'E-001' },
      ctxNoCell,
    )
    expect(out).toContain('wf-x')
    expect(out).toContain('E-001')
    expect(out).toContain('started')
  })

  it('workflow_completed includes duration', () => {
    const out = defaultRenderWorkflowCompleted(
      {
        type: 'workflow_completed',
        ts_ms: ts,
        workflow_id: 'wf-x',
        execution_id: 'E-001',
        duration_ms: 12345,
      },
      ctxNoCell,
    )
    expect(out).toContain('completed')
    expect(out).toContain('12345ms')
  })

  it('workflow_failed includes reason', () => {
    const out = defaultRenderWorkflowFailed(
      {
        type: 'workflow_failed',
        ts_ms: ts,
        workflow_id: 'wf-x',
        execution_id: 'E-001',
        reason: 'upstream timeout',
      },
      ctxNoCell,
    )
    expect(out).toContain('FAILED')
    expect(out).toContain('upstream timeout')
  })

  it('artifact_registered shows short sha + asset_kind + producer when present', () => {
    const out = defaultRenderArtifactRegistered(
      {
        type: 'artifact_registered',
        ts_ms: ts,
        domain_id: 'D38',
        content_sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
        asset_kind: 'json',
        producer_execution_id: 'E-build-1',
      },
      ctxNoCell,
    )
    expect(out).toContain('[catalog]')
    expect(out).toContain('D38')
    expect(out).toContain('sha:abcdef12')
    expect(out).toContain('(json)')
    expect(out).toContain('E-build-1')
  })

  it('artifact_registered omits producer prefix when absent', () => {
    const out = defaultRenderArtifactRegistered(
      {
        type: 'artifact_registered',
        ts_ms: ts,
        domain_id: 'D1',
        content_sha256: 'a'.repeat(64),
        asset_kind: 'binary',
      },
      ctxNoCell,
    )
    expect(out).not.toContain('←')
  })

  it('policy_decision shows verdict + rule + workflow + reason', () => {
    const out = defaultRenderPolicyDecision(
      {
        type: 'policy_decision',
        ts_ms: ts,
        verdict: 'DENY',
        rule_id: 'R-acl-7',
        workflow_id: 'wf-x',
        reason: 'no permission',
      },
      ctxNoCell,
    )
    expect(out).toContain('[policy]')
    expect(out).toContain('DENY')
    expect(out).toContain('R-acl-7')
    expect(out).toContain('wf-x')
    expect(out).toContain('no permission')
  })

  it('step_started shows step index over count', () => {
    const out = defaultRenderStepStarted(
      {
        type: 'step_started',
        ts_ms: ts,
        workflow_id: 'wf-x',
        execution_id: 'E-1',
        step_id: 'render-html',
        step_index: 3,
        step_count: 5,
      },
      ctxNoCell,
    )
    expect(out).toContain('3/5')
    expect(out).toContain('render-html')
  })

  it('step_completed shows duration + checkmark', () => {
    const out = defaultRenderStepCompleted(
      {
        type: 'step_completed',
        ts_ms: ts,
        workflow_id: 'wf-x',
        execution_id: 'E-1',
        step_id: 'render-html',
        step_index: 3,
        step_count: 5,
        duration_ms: 234,
      },
      ctxNoCell,
    )
    expect(out).toContain('3/5')
    expect(out).toContain('✓')
    expect(out).toContain('234ms')
  })
})

describe('isEngineEvent — per-variant strict guard (codex P1 fold 2026-05-03)', () => {
  it('rejects workflow_started missing workflow_id', () => {
    expect(isEngineEvent({ type: 'workflow_started', ts_ms: ts, execution_id: 'E-1' })).toBe(false)
  })

  it('rejects workflow_started missing execution_id', () => {
    expect(isEngineEvent({ type: 'workflow_started', ts_ms: ts, workflow_id: 'wf' })).toBe(false)
  })

  it('rejects workflow_completed with non-numeric duration', () => {
    expect(
      isEngineEvent({
        type: 'workflow_completed',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        duration_ms: 'fast',
      }),
    ).toBe(false)
  })

  it('rejects routing_decision with unknown mode', () => {
    expect(
      isEngineEvent({
        type: 'routing_decision',
        ts_ms: ts,
        turn_id: null,
        mode: 'maybe',
        workflow_id: null,
        trigger_id: null,
        attempts_count: 0,
      }),
    ).toBe(false)
  })

  it('rejects policy_decision with unknown verdict', () => {
    expect(
      isEngineEvent({ type: 'policy_decision', ts_ms: ts, verdict: 'MAYBE', rule_id: 'r' }),
    ).toBe(false)
  })

  it('rejects step_started with negative step_index', () => {
    expect(
      isEngineEvent({
        type: 'step_started',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        step_id: 's',
        step_index: -1,
        step_count: 5,
      }),
    ).toBe(false)
  })

  it('rejects artifact_registered with empty content_sha256', () => {
    expect(
      isEngineEvent({
        type: 'artifact_registered',
        ts_ms: ts,
        domain_id: 'D1',
        content_sha256: '',
        asset_kind: 'k',
      }),
    ).toBe(false)
  })

  it('accepts well-formed payloads from each variant', () => {
    expect(
      isEngineEvent({
        type: 'routing_decision',
        ts_ms: ts,
        turn_id: 't',
        mode: 'exact',
        workflow_id: 'wf',
        trigger_id: 'T',
        attempts_count: 1,
      }),
    ).toBe(true)
    expect(
      isEngineEvent({
        type: 'workflow_completed',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        duration_ms: 5,
      }),
    ).toBe(true)
    expect(
      isEngineEvent({
        type: 'artifact_registered',
        ts_ms: ts,
        domain_id: 'D1',
        content_sha256: 'a'.repeat(64),
        asset_kind: 'json',
      }),
    ).toBe(true)
  })
})

describe('cellPrefix sanitization (codex P2.2 fold 2026-05-03)', () => {
  it('hsutra present without cell → no prefix', () => {
    const out = defaultRenderWorkflowStarted(
      { type: 'workflow_started', ts_ms: ts, workflow_id: 'wf', execution_id: 'E-1' },
      { hsutra: { turn_id: 't-1' } },
    )
    expect(out.startsWith('[wf]')).toBe(true) // no `[CELL] ` prefix when cell missing
  })

  it('strips newlines + tabs from cell value', () => {
    const out = defaultRenderWorkflowStarted(
      { type: 'workflow_started', ts_ms: ts, workflow_id: 'wf', execution_id: 'E-1' },
      { hsutra: { turn_id: 't-1', cell: 'BAD\nCELL\tVALUE' } },
    )
    expect(out).not.toContain('\n')
    expect(out).not.toContain('\t')
    expect(out).toContain('[BAD?CELL?VALUE]')
  })

  it('strips ASCII control bytes from cell value', () => {
    // \x07 = bell, \x1b = ESC (terminal escape entry)
    const out = defaultRenderWorkflowStarted(
      { type: 'workflow_started', ts_ms: ts, workflow_id: 'wf', execution_id: 'E-1' },
      { hsutra: { turn_id: 't-1', cell: 'X\x07Y\x1bZ' } },
    )
    expect(out).toContain('[X?Y?Z]')
    expect(out).not.toContain('\x07')
    expect(out).not.toContain('\x1b')
  })
})

describe('register typing (codex P2.1 fold 2026-05-03)', () => {
  it('typed registration: WorkflowStartedEvent renderer reads workflow_id', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    r.register('workflow_started', (e) => `WF=${e.workflow_id}`)
    const out = r.render({
      type: 'workflow_started',
      ts_ms: ts,
      workflow_id: 'wf-typed',
      execution_id: 'E-1',
    })
    expect(out).toBe('WF=wf-typed')
  })

  it('typed registration: PolicyDecisionEvent renderer reads verdict', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    r.register('policy_decision', (e) => `V=${e.verdict}`)
    const out = r.render({ type: 'policy_decision', ts_ms: ts, verdict: 'DENY', rule_id: 'r' })
    expect(out).toBe('V=DENY')
  })

  it('typed registration: StepCompletedEvent renderer reads duration_ms', () => {
    const r = new RendererRegistry({ skip_defaults: true })
    r.register('step_completed', (e) => `D=${e.duration_ms}`)
    const out = r.render({
      type: 'step_completed',
      ts_ms: ts,
      workflow_id: 'wf',
      execution_id: 'E-1',
      step_id: 's',
      step_index: 1,
      step_count: 2,
      duration_ms: 99,
    })
    expect(out).toBe('D=99')
  })
})

describe('integration via RendererRegistry.render()', () => {
  it('routes each of the 8 event types through render() and returns a non-null string', () => {
    const r = new RendererRegistry()
    const ctx: RenderContext = {}
    const samples: EngineEvent[] = [
      {
        type: 'routing_decision',
        ts_ms: ts,
        turn_id: 't',
        mode: 'exact',
        workflow_id: 'wf',
        trigger_id: 'T',
        attempts_count: 1,
      },
      { type: 'workflow_started', ts_ms: ts, workflow_id: 'wf', execution_id: 'E-1' },
      {
        type: 'workflow_completed',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        duration_ms: 1,
      },
      {
        type: 'workflow_failed',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        reason: 'r',
      },
      {
        type: 'artifact_registered',
        ts_ms: ts,
        domain_id: 'D1',
        content_sha256: 'a'.repeat(64),
        asset_kind: 'k',
      },
      { type: 'policy_decision', ts_ms: ts, verdict: 'ALLOW', rule_id: 'r' },
      {
        type: 'step_started',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        step_id: 's',
        step_index: 1,
        step_count: 2,
      },
      {
        type: 'step_completed',
        ts_ms: ts,
        workflow_id: 'wf',
        execution_id: 'E-1',
        step_id: 's',
        step_index: 1,
        step_count: 2,
        duration_ms: 1,
      },
    ]
    for (const e of samples) {
      const out = r.render(e, ctx)
      expect(out).not.toBeNull()
      expect(typeof out).toBe('string')
      expect(out!.length).toBeGreaterThan(0)
    }
  })
})
