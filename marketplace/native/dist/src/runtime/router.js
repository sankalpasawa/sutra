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
import { createHash } from 'node:crypto';
import { isTriggerSpec, } from '../types/trigger-spec.js';
import { evaluate } from './predicate.js';
/**
 * Recursive freeze. Used at register/record time so callers + sinks cannot
 * mutate router-owned state after the fact (replay determinism). Cheap for
 * our shapes (TriggerSpec is shallow with a small Predicate tree;
 * RoutingDecision has a flat attempts array).
 */
function deepFreeze(value) {
    if (value === null || typeof value !== 'object')
        return value;
    if (Object.isFrozen(value))
        return value;
    Object.freeze(value);
    for (const key of Object.keys(value)) {
        deepFreeze(value[key]);
    }
    return value;
}
export class Router {
    triggers = [];
    llmFallback;
    onDecision;
    decisionLog = [];
    constructor(options = {}) {
        this.llmFallback = options.llm_fallback;
        this.onDecision = options.on_decision;
    }
    /**
     * Register a TriggerSpec. Throws TypeError on malformed input.
     * Order matters — first-match-wins during route().
     * Spec is deep-frozen on registration (caller cannot mutate it later).
     */
    registerTrigger(spec) {
        if (!isTriggerSpec(spec)) {
            throw new TypeError(`Router.registerTrigger: malformed spec (id=${spec.id})`);
        }
        if (this.triggers.some((t) => t.id === spec.id)) {
            throw new Error(`Router.registerTrigger: duplicate trigger id "${spec.id}"`);
        }
        this.triggers.push(deepFreeze(spec));
    }
    /**
     * Replace registered triggers wholesale. Used by daemon reload paths.
     * Validates each input AND rejects the whole batch on duplicate ids.
     * Each spec is deep-frozen.
     */
    setTriggers(specs) {
        const seen = new Set();
        for (const spec of specs) {
            if (!isTriggerSpec(spec)) {
                throw new TypeError(`Router.setTriggers: malformed spec (id=${spec.id})`);
            }
            if (seen.has(spec.id)) {
                throw new Error(`Router.setTriggers: duplicate trigger id "${spec.id}"`);
            }
            seen.add(spec.id);
        }
        this.triggers = specs.map((s) => deepFreeze(s));
    }
    unregisterTrigger(trigger_id) {
        const before = this.triggers.length;
        this.triggers = this.triggers.filter((t) => t.id !== trigger_id);
        return this.triggers.length < before;
    }
    getRegisteredTriggers() {
        return [...this.triggers];
    }
    getDecisionLog() {
        return [...this.decisionLog];
    }
    /**
     * Run the deterministic predicate loop. Pure — does NOT record. Used by
     * both route() and routeAsync() so each public-method invocation produces
     * exactly one audit record (codex P1 fold 2026-05-03).
     */
    _evaluateTriggers(req) {
        const attempts = [];
        const ctx = {
            input_text: req.input_text ?? req.hsutra?.input_text,
            event_type: req.event_type,
            hsutra: req.hsutra,
        };
        for (const trigger of this.triggers) {
            // Filter by event_type first — TriggerSpec.event_type is an implicit
            // pre-filter, NOT something the predicate has to encode.
            if (trigger.event_type !== req.event_type)
                continue;
            const result = evaluate(trigger.route_predicate, ctx);
            attempts.push({
                trigger_id: trigger.id,
                matched: result.matched,
                reason: result.reason,
            });
            if (result.matched)
                return { trigger, attempts };
        }
        return { trigger: null, attempts };
    }
    /**
     * Synchronous deterministic-only route. Returns a decision with mode=
     * 'exact' on match, mode='no-match' otherwise. Does NOT invoke the LLM
     * fallback even if configured (caller must use routeAsync for that).
     * Emits exactly one audit record.
     */
    route(req) {
        const turn_id = req.hsutra?.turn_id ?? null;
        const { trigger, attempts } = this._evaluateTriggers(req);
        const decision = trigger
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
            };
        this.recordDecision(decision);
        return decision;
    }
    /**
     * Async route — deterministic match first; if none AND llm_fallback is
     * configured, invoke the fallback. Emits exactly one audit record per
     * call (codex P1 fold 2026-05-03). If the fallback throws, an audit
     * record with mode='no-match' + an error attempt is recorded BEFORE the
     * exception is re-thrown, so replay can see the attempted invocation.
     */
    async routeAsync(req) {
        const turn_id = req.hsutra?.turn_id ?? null;
        const { trigger, attempts } = this._evaluateTriggers(req);
        if (trigger) {
            const decision = {
                turn_id,
                ts_ms: Date.now(),
                mode: 'exact',
                workflow_id: trigger.target_workflow,
                trigger_id: trigger.id,
                attempts,
            };
            this.recordDecision(decision);
            return decision;
        }
        if (!this.llmFallback) {
            const decision = {
                turn_id,
                ts_ms: Date.now(),
                mode: 'no-match',
                workflow_id: null,
                trigger_id: null,
                attempts,
            };
            this.recordDecision(decision);
            return decision;
        }
        // Deterministic miss + fallback configured → invoke under guard.
        const visible = this.triggers.filter((t) => t.event_type === req.event_type);
        try {
            const fallbackResult = await this.llmFallback(req.hsutra ?? null, req.input_text ?? req.hsutra?.input_text ?? '', visible);
            const decision = {
                turn_id,
                ts_ms: Date.now(),
                mode: fallbackResult.workflow_id ? 'llm-fallback' : 'no-match',
                workflow_id: fallbackResult.workflow_id,
                trigger_id: null,
                attempts,
                prompt_hash: fallbackResult.prompt_hash,
                llm_model: fallbackResult.model,
            };
            this.recordDecision(decision);
            return decision;
        }
        catch (err) {
            // Replay-safety: record the attempt even though the fallback failed.
            // prompt_hash + llm_model are unavailable (the adapter never returned),
            // so the attempt is logged via the attempts trail with an error reason.
            const errorMessage = err instanceof Error ? err.message : String(err);
            const errorAttempt = {
                trigger_id: '__llm_fallback__',
                matched: false,
                reason: `llm-fallback threw: ${errorMessage}`,
            };
            const decision = {
                turn_id,
                ts_ms: Date.now(),
                mode: 'no-match',
                workflow_id: null,
                trigger_id: null,
                attempts: [...attempts, errorAttempt],
            };
            this.recordDecision(decision);
            throw err;
        }
    }
    recordDecision(decision) {
        const frozen = deepFreeze(decision);
        this.decisionLog.push(frozen);
        if (this.onDecision) {
            try {
                this.onDecision(frozen);
            }
            catch {
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
export function computePromptHash(prompt) {
    return createHash('sha256').update(prompt).digest('hex').slice(0, 32);
}
/**
 * Helper for tests + production: build a deterministic prompt for the LLM
 * fallback. Pinned shape so prompt_hash is stable across runs.
 */
export function buildFallbackPrompt(event_summary, triggers) {
    const triggerLines = triggers
        .map((t) => `  ${t.id} → ${t.target_workflow}: ${t.description ?? '(no description)'}`)
        .join('\n');
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
    ].join('\n');
}
//# sourceMappingURL=router.js.map