/**
 * Router — D2 step 2 of vertical slice.
 *
 * Maps events (founder_input via H-Sutra, cron tick, file_drop, webhook)
 * to target Workflows via registered TriggerSpecs. First match wins (in
 * registration order). When no deterministic match, optionally falls back
 * to an LLM classifier (per softened I-NPD-1).
 *
 * Per founder direction 2026-05-02 + C8: LLM fallback uses claude --bare
 * subprocess (subscription auth). Wiring is dependency-injected so tests
 * can stub without spawning subprocess.
 *
 * Every routing decision emits a RoutingDecision audit record. Production
 * wires these into the OpenTelemetry emitter (D2 step 4); v1.0 here just
 * collects in-memory + optionally appends to a JSONL sink.
 *
 * Replay determinism: deterministic matches ARE bit-identical replayable.
 * LLM-fallback decisions ARE replayable IF the LLM provider supports
 * temperature=0 + same prompt_hash → same response. v1.0 stores prompt
 * hash + model id; replay verification is D5 territory.
 */

import { createHash } from 'node:crypto'
import {
  isTriggerSpec,
  type Predicate,
  type TriggerEventType,
  type TriggerSpec,
} from '../types/trigger-spec.js'
import type { RoutingDecision, PredicateAttempt } from '../types/routing-decision.js'
import type { HSutraEvent } from '../types/h-sutra-event.js'
import { evaluate, type PredicateContext } from './predicate.js'

/**
 * Optional async LLM fallback. Returns the workflow_id to dispatch, or
 * null if the LLM declined. Implementations MUST be deterministic-shaped:
 * call with temperature=0 (or equivalent) so prompt_hash → same response.
 *
 * v1.0 production wiring: a thin adapter that builds the prompt from event
 * + registered triggers, spawns claude --bare, parses the response.
 * Tests inject stubs that map specific events → specific workflow_ids.
 */
export type LLMFallback = (
  event: HSutraEvent | null,
  input_text: string,
  triggers: ReadonlyArray<TriggerSpec>,
) => Promise<{ workflow_id: string | null; prompt_hash: string; model: string }>

export interface RouterOptions {
  /** Inject the LLM fallback. When omitted, no-match returns mode='no-match'. */
  readonly llm_fallback?: LLMFallback
  /** Optional sink callback for audit records (production: append to JSONL). */
  readonly on_decision?: (decision: RoutingDecision) => void
}

export interface RouteRequest {
  /** The event_type to route under. */
  readonly event_type: TriggerEventType
  /** Raw input text — used by predicates like contains/matches. */
  readonly input_text?: string
  /** Optional full H-Sutra event. */
  readonly hsutra?: HSutraEvent
}

/**
 * Recursive freeze. Used at register/record time so callers + sinks cannot
 * mutate router-owned state after the fact (replay determinism). Cheap for
 * our shapes (TriggerSpec is shallow with a small Predicate tree;
 * RoutingDecision has a flat attempts array).
 */
function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value
  if (Object.isFrozen(value)) return value
  Object.freeze(value)
  for (const key of Object.keys(value)) {
    deepFreeze((value as Record<string, unknown>)[key])
  }
  return value
}

interface EvaluationOutcome {
  readonly trigger: TriggerSpec | null
  readonly attempts: ReadonlyArray<PredicateAttempt>
}

export class Router {
  private triggers: TriggerSpec[] = []
  private llmFallback: LLMFallback | undefined
  private onDecision: ((d: RoutingDecision) => void) | undefined
  private decisionLog: RoutingDecision[] = []

  constructor(options: RouterOptions = {}) {
    this.llmFallback = options.llm_fallback
    this.onDecision = options.on_decision
  }

  /**
   * Register a TriggerSpec. Throws TypeError on malformed input.
   * Order matters — first-match-wins during route().
   * Spec is deep-frozen on registration (caller cannot mutate it later).
   */
  registerTrigger(spec: TriggerSpec): void {
    if (!isTriggerSpec(spec)) {
      throw new TypeError(`Router.registerTrigger: malformed spec (id=${(spec as { id?: unknown }).id})`)
    }
    if (this.triggers.some((t) => t.id === spec.id)) {
      throw new Error(`Router.registerTrigger: duplicate trigger id "${spec.id}"`)
    }
    this.triggers.push(deepFreeze(spec))
  }

  /**
   * Replace registered triggers wholesale. Used by daemon reload paths.
   * Validates each input AND rejects the whole batch on duplicate ids.
   * Each spec is deep-frozen.
   */
  setTriggers(specs: ReadonlyArray<TriggerSpec>): void {
    const seen = new Set<string>()
    for (const spec of specs) {
      if (!isTriggerSpec(spec)) {
        throw new TypeError(`Router.setTriggers: malformed spec (id=${(spec as { id?: unknown }).id})`)
      }
      if (seen.has(spec.id)) {
        throw new Error(`Router.setTriggers: duplicate trigger id "${spec.id}"`)
      }
      seen.add(spec.id)
    }
    this.triggers = specs.map((s) => deepFreeze(s))
  }

  unregisterTrigger(trigger_id: string): boolean {
    const before = this.triggers.length
    this.triggers = this.triggers.filter((t) => t.id !== trigger_id)
    return this.triggers.length < before
  }

  getRegisteredTriggers(): ReadonlyArray<TriggerSpec> {
    return [...this.triggers]
  }

  getDecisionLog(): ReadonlyArray<RoutingDecision> {
    return [...this.decisionLog]
  }

  /**
   * Run the deterministic predicate loop. Pure — does NOT record. Used by
   * both route() and routeAsync() so each public-method invocation produces
   * exactly one audit record (codex P1 fold 2026-05-03).
   */
  private _evaluateTriggers(req: RouteRequest): EvaluationOutcome {
    const attempts: PredicateAttempt[] = []
    const ctx: PredicateContext = {
      input_text: req.input_text ?? req.hsutra?.input_text,
      event_type: req.event_type,
      hsutra: req.hsutra,
    }

    for (const trigger of this.triggers) {
      // Filter by event_type first — TriggerSpec.event_type is an implicit
      // pre-filter, NOT something the predicate has to encode.
      if (trigger.event_type !== req.event_type) continue

      const result = evaluate(trigger.route_predicate, ctx)
      attempts.push({
        trigger_id: trigger.id,
        matched: result.matched,
        reason: result.reason,
      })
      if (result.matched) return { trigger, attempts }
    }
    return { trigger: null, attempts }
  }

  /**
   * Synchronous deterministic-only route. Returns a decision with mode=
   * 'exact' on match, mode='no-match' otherwise. Does NOT invoke the LLM
   * fallback even if configured (caller must use routeAsync for that).
   * Emits exactly one audit record.
   */
  route(req: RouteRequest): RoutingDecision {
    const turn_id = req.hsutra?.turn_id ?? null
    const { trigger, attempts } = this._evaluateTriggers(req)
    const decision: RoutingDecision = trigger
      ? {
          turn_id,
          ts_ms: Date.now(),
          mode: 'exact',
          workflow_id: trigger.target_workflow,
          trigger_id: trigger.id,
          attempts,
        }
      : {
          turn_id,
          ts_ms: Date.now(),
          mode: 'no-match',
          workflow_id: null,
          trigger_id: null,
          attempts,
        }
    this.recordDecision(decision)
    return decision
  }

  /**
   * Async route — deterministic match first; if none AND llm_fallback is
   * configured, invoke the fallback. Emits exactly one audit record per
   * call (codex P1 fold 2026-05-03). If the fallback throws, an audit
   * record with mode='no-match' + an error attempt is recorded BEFORE the
   * exception is re-thrown, so replay can see the attempted invocation.
   */
  async routeAsync(req: RouteRequest): Promise<RoutingDecision> {
    const turn_id = req.hsutra?.turn_id ?? null
    const { trigger, attempts } = this._evaluateTriggers(req)

    if (trigger) {
      const decision: RoutingDecision = {
        turn_id,
        ts_ms: Date.now(),
        mode: 'exact',
        workflow_id: trigger.target_workflow,
        trigger_id: trigger.id,
        attempts,
      }
      this.recordDecision(decision)
      return decision
    }

    if (!this.llmFallback) {
      const decision: RoutingDecision = {
        turn_id,
        ts_ms: Date.now(),
        mode: 'no-match',
        workflow_id: null,
        trigger_id: null,
        attempts,
      }
      this.recordDecision(decision)
      return decision
    }

    // Deterministic miss + fallback configured → invoke under guard.
    const visible = this.triggers.filter((t) => t.event_type === req.event_type)
    try {
      const fallbackResult = await this.llmFallback(
        req.hsutra ?? null,
        req.input_text ?? req.hsutra?.input_text ?? '',
        visible,
      )
      const decision: RoutingDecision = {
        turn_id,
        ts_ms: Date.now(),
        mode: fallbackResult.workflow_id ? 'llm-fallback' : 'no-match',
        workflow_id: fallbackResult.workflow_id,
        trigger_id: null,
        attempts,
        prompt_hash: fallbackResult.prompt_hash,
        llm_model: fallbackResult.model,
      }
      this.recordDecision(decision)
      return decision
    } catch (err) {
      // Replay-safety: record the attempt even though the fallback failed.
      // prompt_hash + llm_model are unavailable (the adapter never returned),
      // so the attempt is logged via the attempts trail with an error reason.
      const errorMessage = err instanceof Error ? err.message : String(err)
      const errorAttempt: PredicateAttempt = {
        trigger_id: '__llm_fallback__',
        matched: false,
        reason: `llm-fallback threw: ${errorMessage}`,
      }
      const decision: RoutingDecision = {
        turn_id,
        ts_ms: Date.now(),
        mode: 'no-match',
        workflow_id: null,
        trigger_id: null,
        attempts: [...attempts, errorAttempt],
      }
      this.recordDecision(decision)
      throw err
    }
  }

  private recordDecision(decision: RoutingDecision): void {
    const frozen = deepFreeze(decision)
    this.decisionLog.push(frozen)
    if (this.onDecision) {
      try {
        this.onDecision(frozen)
      } catch {
        // Sink errors are isolated; never break routing.
      }
    }
  }
}

/**
 * Helper for LLM-fallback implementations: deterministic prompt hash.
 * Implementations should compute this BEFORE calling claude --bare so the
 * audit record can be written even if the LLM call fails.
 */
export function computePromptHash(prompt: string): string {
  return createHash('sha256').update(prompt).digest('hex').slice(0, 32)
}

/**
 * Helper for tests + production: build a deterministic prompt for the LLM
 * fallback. Pinned shape so prompt_hash is stable across runs.
 */
export function buildFallbackPrompt(
  event_summary: string,
  triggers: ReadonlyArray<TriggerSpec>,
): string {
  const triggerLines = triggers
    .map((t) => `  ${t.id} → ${t.target_workflow}: ${t.description ?? '(no description)'}`)
    .join('\n')
  return [
    'You are a deterministic router. Choose ONE of the listed Workflows for the given event, or "NONE".',
    '',
    'Event:',
    `  ${event_summary}`,
    '',
    'Available Workflows:',
    triggerLines || '  (none registered)',
    '',
    'Respond with ONLY the trigger id (e.g., "T-build-product") or "NONE".',
    'No explanation. No prose.',
    '',
  ].join('\n')
}

// Re-export Predicate types so callers can `import { Predicate } from
// '@sutra/native/runtime/router'`.
export type { Predicate, TriggerSpec, RoutingDecision }
