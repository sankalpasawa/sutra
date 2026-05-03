/**
 * Contract tests — Router (D2 step 2 of vertical slice).
 *
 * Coverage:
 *   registration       — success, malformed rejection, duplicate rejection,
 *                        setTriggers replace, unregisterTrigger
 *   route() (sync)     — event_type pre-filter, first-match-wins, no-match,
 *                        decision shape (turn_id/ts_ms/mode/workflow_id/
 *                        trigger_id/attempts) — telemetry verification
 *   routeAsync()       — exact path skips LLM, llm-fallback invoked when no
 *                        match + records prompt_hash + llm_model, no fallback
 *                        configured returns no-match, fallback returning null
 *                        produces mode='no-match' + still records prompt_hash
 *   audit              — decision log copy semantics, on_decision sink fires,
 *                        sink throw isolated (does not break routing)
 *   helpers            — computePromptHash determinism, buildFallbackPrompt
 *                        shape stability (so prompt_hash is stable run-to-run)
 *
 * Per softened I-NPD-1: every routing decision is recorded for replay; LLM
 * fallback decisions include prompt_hash + model so the LLM call itself is
 * replayable.
 */

import { describe, it, expect, vi } from 'vitest'
import {
  Router,
  computePromptHash,
  buildFallbackPrompt,
  type LLMFallback,
} from '../../../src/runtime/router.js'
import type { TriggerSpec } from '../../../src/types/trigger-spec.js'
import type { RoutingDecision } from '../../../src/types/routing-decision.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'

const triggerBuild: TriggerSpec = {
  id: 'T-build',
  event_type: 'founder_input',
  route_predicate: { type: 'contains', value: 'build' },
  target_workflow: 'wf-build',
  description: 'Build product workflow',
}

const triggerDeploy: TriggerSpec = {
  id: 'T-deploy',
  event_type: 'founder_input',
  route_predicate: { type: 'contains', value: 'deploy' },
  target_workflow: 'wf-deploy',
}

const triggerCron: TriggerSpec = {
  id: 'T-cron-daily',
  event_type: 'cron',
  route_predicate: { type: 'always_true' },
  target_workflow: 'wf-daily-pulse',
}

describe('Router — D2 step 2 contract', () => {
  describe('registration', () => {
    it('registerTrigger accepts a well-formed spec', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      expect(r.getRegisteredTriggers()).toHaveLength(1)
      expect(r.getRegisteredTriggers()[0]?.id).toBe('T-build')
    })

    it('registerTrigger throws on malformed spec', () => {
      const r = new Router()
      // Missing target_workflow → fails isTriggerSpec
      const bad = { id: 'T-x', event_type: 'founder_input', route_predicate: { type: 'always_true' } }
      expect(() => r.registerTrigger(bad as unknown as TriggerSpec)).toThrow(TypeError)
    })

    it('registerTrigger throws on duplicate id', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      expect(() => r.registerTrigger(triggerBuild)).toThrow(/duplicate/)
    })

    it('setTriggers replaces wholesale', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      r.setTriggers([triggerDeploy, triggerCron])
      const ids = r.getRegisteredTriggers().map((t) => t.id)
      expect(ids).toEqual(['T-deploy', 'T-cron-daily'])
    })

    it('setTriggers rejects entire batch on any malformed entry', () => {
      const r = new Router()
      const bad = { id: '', event_type: 'cron', route_predicate: {}, target_workflow: '' }
      expect(() => r.setTriggers([triggerBuild, bad as unknown as TriggerSpec])).toThrow(TypeError)
    })

    it('unregisterTrigger returns true on hit, false on miss', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      expect(r.unregisterTrigger('T-build')).toBe(true)
      expect(r.unregisterTrigger('T-build')).toBe(false)
      expect(r.getRegisteredTriggers()).toHaveLength(0)
    })

    it('getRegisteredTriggers returns a copy (mutation does not leak)', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      const view = r.getRegisteredTriggers() as TriggerSpec[]
      view.pop()
      expect(r.getRegisteredTriggers()).toHaveLength(1)
    })
  })

  describe('route() — synchronous deterministic path', () => {
    it('returns mode="exact" with full decision shape on match', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      const hsutra: HSutraEvent = { turn_id: 'turn-42', input_text: 'build product' }
      const d = r.route({ event_type: 'founder_input', hsutra })
      expect(d.mode).toBe('exact')
      expect(d.workflow_id).toBe('wf-build')
      expect(d.trigger_id).toBe('T-build')
      expect(d.turn_id).toBe('turn-42')
      expect(d.ts_ms).toBeTypeOf('number')
      expect(d.attempts).toHaveLength(1)
      expect(d.attempts[0]?.matched).toBe(true)
    })

    it('first-match-wins in registration order', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      r.registerTrigger(triggerDeploy)
      // input matches both ("build and deploy")
      const d = r.route({ event_type: 'founder_input', input_text: 'build and deploy' })
      expect(d.trigger_id).toBe('T-build')
      expect(d.workflow_id).toBe('wf-build')
    })

    it('event_type acts as pre-filter (cron trigger ignored on founder_input)', () => {
      const r = new Router()
      r.registerTrigger(triggerCron)
      r.registerTrigger(triggerBuild)
      const d = r.route({ event_type: 'founder_input', input_text: 'build' })
      expect(d.trigger_id).toBe('T-build')
      // cron trigger should NOT appear in attempts (filtered before evaluate)
      expect(d.attempts.map((a) => a.trigger_id)).toEqual(['T-build'])
    })

    it('returns mode="no-match" with attempts when nothing matches', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      r.registerTrigger(triggerDeploy)
      const d = r.route({ event_type: 'founder_input', input_text: 'just chatting' })
      expect(d.mode).toBe('no-match')
      expect(d.workflow_id).toBeNull()
      expect(d.trigger_id).toBeNull()
      expect(d.attempts).toHaveLength(2)
      expect(d.attempts.every((a) => !a.matched)).toBe(true)
      expect(d.attempts[0]?.reason).toBeDefined()
    })

    it('turn_id is null when no hsutra event provided', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      const d = r.route({ event_type: 'founder_input', input_text: 'build' })
      expect(d.turn_id).toBeNull()
    })
  })

  describe('routeAsync() — LLM fallback path', () => {
    it('returns deterministic match without invoking fallback', async () => {
      const fallback = vi.fn(async () => ({
        workflow_id: 'wf-fallback',
        prompt_hash: 'hash',
        model: 'm',
      }))
      const r = new Router({ llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      const d = await r.routeAsync({ event_type: 'founder_input', input_text: 'build' })
      expect(d.mode).toBe('exact')
      expect(fallback).not.toHaveBeenCalled()
    })

    it('invokes fallback on no-match + records prompt_hash + llm_model', async () => {
      const fallback: LLMFallback = vi.fn(async () => ({
        workflow_id: 'wf-classified-by-llm',
        prompt_hash: 'abc123',
        model: 'claude-bare-test',
      }))
      const r = new Router({ llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      const d = await r.routeAsync({
        event_type: 'founder_input',
        input_text: 'do the thing',
      })
      expect(d.mode).toBe('llm-fallback')
      expect(d.workflow_id).toBe('wf-classified-by-llm')
      expect(d.prompt_hash).toBe('abc123')
      expect(d.llm_model).toBe('claude-bare-test')
      expect(d.trigger_id).toBeNull()
      expect(fallback).toHaveBeenCalledTimes(1)
    })

    it('fallback receives event_type-filtered triggers only', async () => {
      const fallback = vi.fn(async () => ({
        workflow_id: null,
        prompt_hash: 'h',
        model: 'm',
      }))
      const r = new Router({ llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      r.registerTrigger(triggerCron)
      await r.routeAsync({ event_type: 'founder_input', input_text: 'unmatched' })
      const visibleTriggers = fallback.mock.calls[0]?.[2] ?? []
      expect(visibleTriggers.map((t) => t.id)).toEqual(['T-build'])
    })

    it('fallback returning null workflow_id → mode="no-match" but prompt_hash recorded', async () => {
      const fallback: LLMFallback = vi.fn(async () => ({
        workflow_id: null,
        prompt_hash: 'declined-hash',
        model: 'm',
      }))
      const r = new Router({ llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      const d = await r.routeAsync({ event_type: 'founder_input', input_text: 'unrelated' })
      expect(d.mode).toBe('no-match')
      expect(d.workflow_id).toBeNull()
      expect(d.prompt_hash).toBe('declined-hash')
    })

    it('returns no-match (sync result) when no fallback configured', async () => {
      const r = new Router() // no llm_fallback
      r.registerTrigger(triggerBuild)
      const d = await r.routeAsync({ event_type: 'founder_input', input_text: 'unrelated' })
      expect(d.mode).toBe('no-match')
      expect(d.prompt_hash).toBeUndefined()
    })
  })

  describe('audit / decision log', () => {
    it('getDecisionLog returns a copy', () => {
      const r = new Router()
      r.registerTrigger(triggerBuild)
      r.route({ event_type: 'founder_input', input_text: 'build' })
      const log1 = r.getDecisionLog() as RoutingDecision[]
      log1.pop()
      expect(r.getDecisionLog()).toHaveLength(1)
    })

    it('on_decision sink receives every decision', () => {
      const sink = vi.fn()
      const r = new Router({ on_decision: sink })
      r.registerTrigger(triggerBuild)
      r.route({ event_type: 'founder_input', input_text: 'build' })
      r.route({ event_type: 'founder_input', input_text: 'unmatched' })
      expect(sink).toHaveBeenCalledTimes(2)
      expect((sink.mock.calls[0]?.[0] as RoutingDecision).mode).toBe('exact')
      expect((sink.mock.calls[1]?.[0] as RoutingDecision).mode).toBe('no-match')
    })

    it('sink throw is isolated — routing still returns + log still appended', () => {
      const sink = vi.fn(() => {
        throw new Error('downstream sink died')
      })
      const r = new Router({ on_decision: sink })
      r.registerTrigger(triggerBuild)
      const d = r.route({ event_type: 'founder_input', input_text: 'build' })
      expect(d.mode).toBe('exact')
      expect(r.getDecisionLog()).toHaveLength(1)
    })
  })

  describe('audit cardinality (codex P1 fold 2026-05-03)', () => {
    it('routeAsync emits exactly ONE decision on no-match → llm-fallback path', async () => {
      const sink = vi.fn()
      const fallback: LLMFallback = vi.fn(async () => ({
        workflow_id: 'wf-x',
        prompt_hash: 'h',
        model: 'm',
      }))
      const r = new Router({ on_decision: sink, llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      await r.routeAsync({ event_type: 'founder_input', input_text: 'unmatched' })
      expect(sink).toHaveBeenCalledTimes(1)
      expect(r.getDecisionLog()).toHaveLength(1)
      expect(r.getDecisionLog()[0]?.mode).toBe('llm-fallback')
    })

    it('routeAsync emits ONE decision (mode=exact) when match short-circuits fallback', async () => {
      const sink = vi.fn()
      const fallback = vi.fn(async () => ({ workflow_id: null, prompt_hash: 'h', model: 'm' }))
      const r = new Router({ on_decision: sink, llm_fallback: fallback })
      r.registerTrigger(triggerBuild)
      await r.routeAsync({ event_type: 'founder_input', input_text: 'build' })
      expect(sink).toHaveBeenCalledTimes(1)
      expect(fallback).not.toHaveBeenCalled()
    })

    it('routeAsync emits ONE decision (mode=no-match) when no fallback configured', async () => {
      const sink = vi.fn()
      const r = new Router({ on_decision: sink })
      r.registerTrigger(triggerBuild)
      await r.routeAsync({ event_type: 'founder_input', input_text: 'unmatched' })
      expect(sink).toHaveBeenCalledTimes(1)
      expect(r.getDecisionLog()).toHaveLength(1)
    })
  })

  describe('llm-fallback throw safety (codex P1 fold 2026-05-03)', () => {
    it('records audit decision + re-throws when fallback rejects', async () => {
      const sink = vi.fn()
      const failing: LLMFallback = vi.fn(async () => {
        throw new Error('upstream LLM 500')
      })
      const r = new Router({ on_decision: sink, llm_fallback: failing })
      r.registerTrigger(triggerBuild)
      await expect(
        r.routeAsync({ event_type: 'founder_input', input_text: 'unmatched' }),
      ).rejects.toThrow('upstream LLM 500')

      // Replay-safety: ONE audit record persists even on throw
      expect(sink).toHaveBeenCalledTimes(1)
      expect(r.getDecisionLog()).toHaveLength(1)
      const d = r.getDecisionLog()[0]!
      expect(d.mode).toBe('no-match')
      expect(d.attempts.some((a) => a.trigger_id === '__llm_fallback__')).toBe(true)
      expect(
        d.attempts.find((a) => a.trigger_id === '__llm_fallback__')?.reason,
      ).toContain('upstream LLM 500')
    })
  })

  describe('immutability (codex P2 fold 2026-05-03)', () => {
    it('registered triggers are deep-frozen (caller cannot mutate later)', () => {
      const r = new Router()
      const spec: TriggerSpec = {
        id: 'T-mut',
        event_type: 'founder_input',
        route_predicate: { type: 'contains', value: 'a' },
        target_workflow: 'wf-mut',
      }
      r.registerTrigger(spec)
      expect(Object.isFrozen(spec)).toBe(true)
      expect(Object.isFrozen(spec.route_predicate)).toBe(true)
      expect(() => {
        ;(spec as { target_workflow: string }).target_workflow = 'wf-hacked'
      }).toThrow()
    })

    it('decision log entries are frozen (sink cannot mutate audit)', () => {
      const captured: RoutingDecision[] = []
      const r = new Router({
        on_decision: (d) => {
          captured.push(d)
        },
      })
      r.registerTrigger(triggerBuild)
      r.route({ event_type: 'founder_input', input_text: 'build' })
      const d = captured[0]!
      expect(Object.isFrozen(d)).toBe(true)
      expect(Object.isFrozen(d.attempts)).toBe(true)
      expect(() => {
        ;(d as { workflow_id: string | null }).workflow_id = 'wf-hacked'
      }).toThrow()
    })
  })

  describe('setTriggers strict validation (codex P2 fold 2026-05-03)', () => {
    it('throws on duplicate trigger ids in batch', () => {
      const r = new Router()
      const dup: TriggerSpec = {
        id: triggerBuild.id,
        event_type: 'founder_input',
        route_predicate: { type: 'always_true' },
        target_workflow: 'wf-other',
      }
      expect(() => r.setTriggers([triggerBuild, dup])).toThrow(/duplicate/)
    })

    it('atomic — failed batch leaves prior triggers untouched', () => {
      const r = new Router()
      r.registerTrigger(triggerCron)
      const dup: TriggerSpec = {
        id: triggerBuild.id,
        event_type: 'founder_input',
        route_predicate: { type: 'always_true' },
        target_workflow: 'wf-other',
      }
      expect(() => r.setTriggers([triggerBuild, dup])).toThrow(/duplicate/)
      expect(r.getRegisteredTriggers()).toHaveLength(1)
      expect(r.getRegisteredTriggers()[0]?.id).toBe('T-cron-daily')
    })
  })

  describe('isTriggerSpec strict validation (codex P2 fold 2026-05-03)', () => {
    it('rejects unknown event_type', () => {
      const r = new Router()
      const bad = {
        id: 'T-x',
        event_type: 'martian_signal',
        route_predicate: { type: 'always_true' },
        target_workflow: 'wf-x',
      }
      expect(() => r.registerTrigger(bad as unknown as TriggerSpec)).toThrow(TypeError)
    })

    it('rejects predicate without "type" discriminator', () => {
      const r = new Router()
      const bad = {
        id: 'T-y',
        event_type: 'founder_input',
        route_predicate: { kind: 'contains', value: 'x' }, // wrong field name
        target_workflow: 'wf-y',
      }
      expect(() => r.registerTrigger(bad as unknown as TriggerSpec)).toThrow(TypeError)
    })

    it('rejects predicate with unknown type literal', () => {
      const r = new Router()
      const bad = {
        id: 'T-z',
        event_type: 'founder_input',
        route_predicate: { type: 'magical_thinking' },
        target_workflow: 'wf-z',
      }
      expect(() => r.registerTrigger(bad as unknown as TriggerSpec)).toThrow(TypeError)
    })
  })

  describe('helpers', () => {
    it('computePromptHash is deterministic + 32 hex chars', () => {
      const h1 = computePromptHash('hello world')
      const h2 = computePromptHash('hello world')
      expect(h1).toBe(h2)
      expect(h1).toMatch(/^[0-9a-f]{32}$/)
    })

    it('computePromptHash differs for different inputs', () => {
      expect(computePromptHash('a')).not.toBe(computePromptHash('b'))
    })

    it('buildFallbackPrompt is stable across runs (so prompt_hash replays)', () => {
      const triggers: ReadonlyArray<TriggerSpec> = [triggerBuild, triggerDeploy]
      const p1 = buildFallbackPrompt('founder said: build something', triggers)
      const p2 = buildFallbackPrompt('founder said: build something', triggers)
      expect(p1).toBe(p2)
      expect(p1).toContain('T-build → wf-build')
      expect(p1).toContain('T-deploy → wf-deploy')
    })

    it('buildFallbackPrompt shows "(none registered)" when triggers empty', () => {
      const p = buildFallbackPrompt('any event', [])
      expect(p).toContain('(none registered)')
    })
  })
})
