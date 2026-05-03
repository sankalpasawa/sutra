/**
 * NativeEngine — v1.1.0 wires the D2 vertical slice into a single
 * subscribable runtime so SessionStart hook → engine.start() → founder
 * input → SUCCESS Execution flows end-to-end.
 *
 * Composition:
 *   HSutraConnector   → reads founder events from Sutra Core JSONL log
 *   Router            → maps events to TriggerSpec → target Workflow
 *   LiteExecutor      → walks the matched Workflow's step_graph
 *   ArtifactCatalog   → records cataloged outputs (optional)
 *   RendererRegistry  → prints terminal lines per EngineEvent
 *
 * Per softened I-NPD-1: every routing decision + workflow event flows
 * through a single emit() pipeline so audit/replay sees the same stream
 * a fresh subscriber would.
 *
 * Failure isolation: any per-event handler throw is caught + logged via
 * the on_error callback (defaults to console.error). The connector's own
 * listener-throw isolation (D2.1) keeps a buggy renderer from killing
 * the whole subscription.
 */

import type { Workflow } from '../primitives/workflow.js'
import type { TriggerSpec } from '../types/trigger-spec.js'
import type { HSutraEvent } from '../types/h-sutra-event.js'
import type { EngineEvent, RoutingDecisionEvent } from '../types/engine-event.js'
import { HSutraConnector, type HSutraConnectorOptions } from './h-sutra-connector.js'
import { Router } from './router.js'
import { ArtifactCatalog, type ArtifactCatalogOptions } from './artifact-catalog.js'
import { RendererRegistry } from './renderer-registry.js'
import { executeWorkflow } from './lite-executor.js'
import { loadStarterKit, STARTER_WORKFLOW_CHARTER_MAP } from '../starter-kit/index.js'

export interface NativeEngineOptions {
  readonly connector_options?: HSutraConnectorOptions
  readonly catalog_options?: ArtifactCatalogOptions
  /** Replace the starter triggers + workflows. Default: load the v1.1.0 starter kit. */
  readonly triggers?: ReadonlyArray<TriggerSpec>
  readonly workflows?: ReadonlyArray<Workflow>
  /** Sink for rendered lines. Default: console.log. */
  readonly write?: (line: string) => void
  /** Sink for non-fatal errors. Default: console.error. */
  readonly on_error?: (err: Error) => void
}

export class NativeEngine {
  readonly connector: HSutraConnector
  readonly router: Router
  readonly catalog: ArtifactCatalog
  readonly renderer: RendererRegistry
  private readonly workflowsById: Map<string, Workflow>
  private readonly write: (line: string) => void
  private readonly onError: (err: Error) => void
  private executionCounter = 0
  private started = false

  constructor(options: NativeEngineOptions = {}) {
    const kit = loadStarterKit()
    this.connector = new HSutraConnector(options.connector_options ?? {})
    this.router = new Router()
    this.catalog = new ArtifactCatalog(options.catalog_options ?? {})
    this.renderer = new RendererRegistry()
    this.write = options.write ?? ((line) => console.log(line))
    this.onError = options.on_error ?? ((err) => console.error(`[native-engine] ${err.message}`))

    const triggers = options.triggers ?? kit.triggers
    const workflows = options.workflows ?? kit.workflows
    this.workflowsById = new Map(workflows.map((w) => [w.id, w]))

    for (const t of triggers) {
      try {
        this.router.registerTrigger(t)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }
  }

  /** Begin watching the H-Sutra log + processing events. Idempotent. */
  start(): void {
    if (this.started) return
    this.started = true

    this.connector.onEvent((evt) => {
      try {
        this.handleHSutraEvent(evt)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    })

    this.connector.start()
  }

  /** Stop watching + release resources. Idempotent. */
  stop(): void {
    if (!this.started) return
    this.started = false
    this.connector.stop()
  }

  /**
   * Process one founder event end-to-end:
   *   1. Router.route → RoutingDecision
   *   2. Emit routing_decision event → render line
   *   3. If matched: Workflow Engine executes step_graph
   *   4. Emit each workflow/step event → render line
   *
   * Returns the count of EngineEvents emitted (useful for tests + telemetry).
   */
  handleHSutraEvent(evt: HSutraEvent): number {
    let emitted = 0

    const decision = this.router.route({
      event_type: 'founder_input',
      input_text: evt.input_text,
      hsutra: evt,
    })

    const routingEvt: RoutingDecisionEvent = {
      type: 'routing_decision',
      ts_ms: decision.ts_ms,
      turn_id: decision.turn_id,
      mode: decision.mode,
      workflow_id: decision.workflow_id,
      trigger_id: decision.trigger_id,
      attempts_count: decision.attempts.length,
    }
    this.emitEvent(routingEvt, evt)
    emitted++

    if (decision.mode === 'exact' && decision.workflow_id) {
      const wf = this.workflowsById.get(decision.workflow_id)
      if (!wf) {
        this.onError(new Error(`Router matched workflow "${decision.workflow_id}" but it is not loaded`))
        return emitted
      }

      const executionId = `E-${evt.turn_id}-${++this.executionCounter}`
      executeWorkflow({
        workflow: wf,
        execution_id: executionId,
        emit: (engineEvt) => {
          this.emitEvent(engineEvt, evt)
          emitted++
        },
      })
    }

    return emitted
  }

  /**
   * Public helper: run a single founder turn synchronously (no log file
   * round-trip). Used by tests + the v1.1.0 demo path.
   */
  ingest(evt: HSutraEvent): number {
    return this.handleHSutraEvent(evt)
  }

  /** Lookup the Charter that operationalizes a Workflow (v1.1.0 starter map). */
  ownerCharterOf(workflowId: string): string | undefined {
    return STARTER_WORKFLOW_CHARTER_MAP.get(workflowId)
  }

  private emitEvent(event: EngineEvent, hsutra: HSutraEvent | null): void {
    try {
      const line = this.renderer.render(event, { hsutra: hsutra ?? null })
      if (line) this.write(line)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
  }
}

/** Convenience builder for the v1.1.0 default engine wiring. */
export function createDefaultEngine(options: NativeEngineOptions = {}): NativeEngine {
  return new NativeEngine(options)
}
