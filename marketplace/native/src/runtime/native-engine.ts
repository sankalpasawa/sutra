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
import type { Charter } from '../primitives/charter.js'
import type { TriggerSpec } from '../types/trigger-spec.js'
import type { HSutraEvent } from '../types/h-sutra-event.js'
import type {
  EngineEvent,
  RoutingDecisionEvent,
  PatternProposedEvent,
  ProposalApprovedEvent,
  ProposalRejectedEvent,
  ApprovalGrantedEvent,
  ApprovalDeniedEvent,
  ApprovalAlreadyHandledEvent,
  CommitmentBrokenEvent,
} from '../types/engine-event.js'
import { HSutraConnector, type HSutraConnectorOptions } from './h-sutra-connector.js'
import { Router } from './router.js'
import { ArtifactCatalog, type ArtifactCatalogOptions } from './artifact-catalog.js'
import { RendererRegistry } from './renderer-registry.js'
import { executeWorkflow, executeWorkflowResume } from './lite-executor.js'
import { loadStarterKit, STARTER_WORKFLOW_CHARTER_MAP } from '../starter-kit/index.js'
import {
  listTriggers as listUserKitTriggers,
  listWorkflows as listUserKitWorkflows,
  persistTrigger,
  persistWorkflow,
  type UserKitOptions,
} from '../persistence/user-kit.js'
import {
  loadProposal,
  persistProposal,
  updateProposalStatus,
} from '../persistence/proposal-ledger.js'
import {
  listApprovals,
  loadApproval,
  markResumed,
  persistApproval,
  updateApprovalStatus,
  type ExecutionApprovalRecord,
} from '../persistence/execution-approval-ledger.js'
import {
  listPauses,
  loadPause,
  markResumed as markPauseResumed,
  persistPause,
  type ExecutionPauseRecord,
} from '../persistence/execution-pause-ledger.js'
import {
  listEscalations,
  loadEscalation,
  persistEscalation,
  type ExecutionEscalationRecord,
} from '../persistence/execution-escalation-ledger.js'
import { detectPatterns, type PatternDetectorOptions } from './pattern-detector.js'
import { buildProposal } from './proposal-builder.js'
import {
  appendDecisionProvenanceLog,
  buildEmergenceDecisionProvenance,
} from './emergence-provenance.js'
import {
  BASELINE_PREDICATE_REGISTRY,
  type PredicateRegistry,
} from './pnc-predicate.js'
import { appendTelemetry } from '../persistence/telemetry-sink.js'

export interface NativeEngineOptions {
  readonly connector_options?: HSutraConnectorOptions
  readonly catalog_options?: ArtifactCatalogOptions
  /** Replace the starter triggers + workflows. Default: load the v1.1.0 starter kit. */
  readonly triggers?: ReadonlyArray<TriggerSpec>
  readonly workflows?: ReadonlyArray<Workflow>
  /**
   * v1.3.0 W5 (codex W5 BLOCKER 3 fold). Replace the starter charters. Used by
   * the commitment_broken emission path: NativeEngine looks up Charter.obligations
   * by name when a workflow declares obligation_refs and fails. Default:
   * starter-kit charters via loadStarterKit().
   */
  readonly charters?: ReadonlyArray<Charter>
  /**
   * v1.3.0 W5 — predicate atom registry for the PNC admission gate. Forwarded
   * to lite-executor as `pnc_registry`. Default: `BASELINE_PREDICATE_REGISTRY`
   * (always_true / always_false). Production deployments compose application-
   * specific atoms (`is_morning_window`, `weekly_window`, etc.) via Map
   * extension over the baseline.
   */
  readonly pnc_registry?: PredicateRegistry
  /**
   * v1.3.0 W5 — frozen evaluation context passed to PNC atom evaluators.
   * Forwarded to lite-executor as `pnc_ctx`. Default: empty frozen object.
   * Window markers (e.g. { time_of_day, iso_week }) belong here, NOT inside
   * atom evaluator function bodies (codex W5 advisory E determinism — atoms
   * read pre-computed markers; never call Date.now/random/I/O).
   */
  readonly pnc_ctx?: Readonly<Record<string, unknown>>
  /** Sink for rendered lines. Default: console.log. */
  readonly write?: (line: string) => void
  /** Sink for non-fatal errors. Default: console.error. */
  readonly on_error?: (err: Error) => void
  /**
   * v1.3.0 W6 — durable telemetry sink. When set, every emitted EngineEvent
   * is also persisted via appendTelemetry as a JSONL line under
   * `<telemetry_sink_path>/runtime/telemetry/events.jsonl` with per-event
   * fsync. Recovers seq monotonically across restart. When unset, behavior
   * is identical to v1.3.0-w5 (renderer-only).
   *
   * The path is the HOME root (NOT the events.jsonl path). Reuses the same
   * resolution as user-kit so a single $SUTRA_NATIVE_HOME drives both
   * primitives + telemetry storage.
   */
  readonly telemetry_sink_path?: string

  // -------------------------------------------------------------------------
  // SPEC v1.2 §4.5 — organic emergence v1
  // -------------------------------------------------------------------------
  /** Enable the no-match → propose loop. Default reads SUTRA_NATIVE_PROPOSER. */
  readonly proposer_enabled?: boolean
  /** UserKit storage opts (HOME override etc); shared by user-kit + ledger. */
  readonly user_kit_options?: UserKitOptions
  /** Pattern-detector knobs (k_threshold, window_ms, etc). */
  readonly pattern_detector_options?: Partial<PatternDetectorOptions>
  /** Skip loading user-kit primitives at boot. Default false. */
  readonly skip_user_kit?: boolean
  /** Override clock for deterministic tests. */
  readonly now_ms?: () => number
}

// v1.3.0 W2 (codex W2 advisory C fold) — centralized namespace dispatcher.
// PROPOSAL approvals (P-<sha8>) and EXECUTION approvals (E-<id>) flow through
// the SAME parser so future namespaces (R-<id> for runs, etc.) plug in cleanly.
//
// Pattern: `(approve|reject) (P-XXXXXXXX|E-...) [reason]`
//   - P namespace: P-<sha8> (8 lowercase hex). Reason optional on reject.
//   - E namespace: E-<turn_id>-<seq> (alphanumeric + hyphens; matches NativeEngine's
//     executionId construction). Reason optional on reject.
//
// Returned `id` is namespace-prefixed (e.g., 'P-deadbeef' or 'E-t1-1') so
// downstream loaders (loadProposal / loadApproval) work directly with it.
const APPROVAL_RE = /^\s*(approve|reject)\s+([PE]-[A-Za-z0-9_-]+)(?:\s+(.+))?\s*$/i

export interface ApprovalUtterance {
  readonly namespace: 'P' | 'E'
  readonly id: string
  readonly action: 'approve' | 'reject'
  readonly reason?: string
}

/**
 * Parse a founder utterance for approve/reject commands across ALL namespaces.
 *
 * Returns null when text doesn't match the approval grammar. Returns parsed
 * components when it does. Caller dispatches based on `namespace`:
 *   - 'P' → applyApproval / applyRejection (proposal-ledger)
 *   - 'E' → applyExecutionApproval / applyExecutionRejection (execution-approval-ledger)
 *
 * Codex W2 advisory C fold (2026-05-04): a single parser keeps the H-Sutra
 * surface coherent and lets unit tests verify "approve P-deadbeef" vs
 * "approve E-t1-1" with one set of regex assertions.
 */
export function parseApprovalUtterance(text: string): ApprovalUtterance | null {
  if (typeof text !== 'string') return null
  const m = APPROVAL_RE.exec(text.trim())
  if (!m) return null
  const action = m[1].toLowerCase() as 'approve' | 'reject'
  const id = m[2]
  const namespace = id.startsWith('P-') ? 'P' : 'E'
  const reason = m[3]?.trim()
  const out: ApprovalUtterance = reason
    ? { namespace, id, action, reason }
    : { namespace, id, action }
  return out
}

export class NativeEngine {
  readonly connector: HSutraConnector
  readonly router: Router
  readonly catalog: ArtifactCatalog
  readonly renderer: RendererRegistry
  private readonly workflowsById: Map<string, Workflow>
  /**
   * v1.3.0 W5 — Charter map keyed by Charter.id, populated from starter-kit
   * (or options.charters override). Read by the commitment_broken emission
   * path on workflow_failed: looks up the operating Charter by id, walks its
   * obligations, matches against the failing workflow's obligation_refs, and
   * emits one event per match.
   */
  private readonly chartersById: Map<string, Charter>
  /**
   * v1.3.0 W5 — predicate registry forwarded to lite-executor as `pnc_registry`
   * on every routed run. Default = BASELINE_PREDICATE_REGISTRY.
   */
  private readonly pncRegistry: PredicateRegistry
  /**
   * v1.3.0 W5 — frozen PNC evaluation context. Default = empty frozen object.
   */
  private readonly pncCtx: Readonly<Record<string, unknown>>
  private readonly write: (line: string) => void
  private readonly onError: (err: Error) => void
  /**
   * v1.3.0 W6 — when set, emitEvent also calls appendTelemetry with this
   * HOME root. Undefined → renderer-only path (v1.3.0-w5 behavior).
   */
  private readonly telemetrySinkPath: string | undefined
  private executionCounter = 0
  private started = false
  /**
   * v1.2.1: serialization queue. The connector delivers events synchronously
   * but handleHSutraEvent is now async (host-LLM dispatch may take seconds).
   * Without this chain, two founder turns could overlap and collide on
   * executionCounter / ledger state. Each event is appended to the chain so
   * they run sequentially even when the connector fires faster than dispatch
   * resolves. Codex master review (DIRECTIVE 1777839055) P1 fold.
   */
  private turnQueue: Promise<void> = Promise.resolve()

  // SPEC v1.2 §4.5 — proposer state
  private readonly proposerEnabled: boolean
  private readonly userKitOptions: UserKitOptions
  private readonly patternDetectorOptions: Partial<PatternDetectorOptions>
  private readonly nowMs: () => number

  constructor(options: NativeEngineOptions = {}) {
    const kit = loadStarterKit()
    this.connector = new HSutraConnector(options.connector_options ?? {})
    this.router = new Router()
    this.catalog = new ArtifactCatalog(options.catalog_options ?? {})
    this.renderer = new RendererRegistry()
    this.write = options.write ?? ((line) => console.log(line))
    this.onError = options.on_error ?? ((err) => console.error(`[native-engine] ${err.message}`))
    // v1.3.0 W6 — opt-in durable telemetry sink. Undefined preserves
    // v1.3.0-w5 behavior (no extra I/O on emit).
    this.telemetrySinkPath = options.telemetry_sink_path
    this.nowMs = options.now_ms ?? (() => Date.now())

    // Proposer wiring — default OFF unless env says on; explicit option wins.
    this.userKitOptions = options.user_kit_options ?? {}
    this.patternDetectorOptions = options.pattern_detector_options ?? {}
    if (typeof options.proposer_enabled === 'boolean') {
      this.proposerEnabled = options.proposer_enabled
    } else {
      const flag = (this.userKitOptions.env ?? process.env).SUTRA_NATIVE_PROPOSER
      this.proposerEnabled = flag === 'on' || flag === '1' || flag === 'true'
    }

    const starterTriggers = options.triggers ?? kit.triggers
    const starterWorkflows = options.workflows ?? kit.workflows
    const starterCharters = options.charters ?? kit.charters
    this.workflowsById = new Map(starterWorkflows.map((w) => [w.id, w]))
    this.chartersById = new Map(starterCharters.map((c) => [c.id, c]))
    this.pncRegistry = options.pnc_registry ?? BASELINE_PREDICATE_REGISTRY
    this.pncCtx = options.pnc_ctx ?? Object.freeze({})

    for (const t of starterTriggers) {
      try {
        this.router.registerTrigger(t)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    // SPEC v1.2 §4.5(a) — load user-kit Workflows + TriggerSpecs from disk so
    // emergent primitives registered in prior sessions survive daemon restart.
    if (!options.skip_user_kit) {
      try {
        const userWorkflows = listUserKitWorkflows(this.userKitOptions)
        for (const w of userWorkflows) this.workflowsById.set(w.id, w)
        const userTriggers = listUserKitTriggers(this.userKitOptions)
        for (const t of userTriggers) {
          try {
            this.router.registerTrigger(t)
          } catch (err) {
            this.onError(err instanceof Error ? err : new Error(String(err)))
          }
        }
      } catch (err) {
        // user-kit dir might not exist yet — non-fatal.
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    // v1.3.0 W2 (codex W2 BLOCKER 3 fold) — boot-time reload of pending
    // execution approvals. Per codex advisory: "the pending approval state
    // must survive restart, but DO NOT auto-resume — founder must explicitly
    // approve". So we only LIST + log; resumption is gated on the founder's
    // next `approve E-<id>` utterance.
    //
    // The list is logged via onError as informational (no dedicated info
    // sink at v1.3.0; codex P1 wave-2 will add structured operator logging).
    try {
      const pendingApprovals = listApprovals(this.userKitOptions, 'pending')
      if (pendingApprovals.length > 0) {
        this.onError(
          new Error(
            `[native-engine boot] ${pendingApprovals.length} pending step approval(s) on disk: ${pendingApprovals
              .map((r) => `${r.execution_id}@step${r.step_index}`)
              .join(', ')}. Founder must explicitly "approve E-<id>" or "reject E-<id> <reason>" to resume.`,
          ),
        )
      }
    } catch (err) {
      // pending-approvals dir might not exist on first boot — non-fatal.
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }

    // v1.3.0 W4 — boot-time reload of pending pause records. Same DO-NOT-
    // AUTO-RESUME discipline as approvals: surface as informational logs;
    // founder must explicitly call `resumeFromPause(execId)` (or future
    // `resume E-<id>` utterance routing).
    try {
      const pendingPauses = listPauses(this.userKitOptions, 'pending')
      if (pendingPauses.length > 0) {
        this.onError(
          new Error(
            `[native-engine boot] ${pendingPauses.length} pending pause(s) on disk: ${pendingPauses
              .map((r) => `${r.execution_id}@step${r.step_index}`)
              .join(', ')}. Caller must explicitly resumeFromPause("E-<id>") to continue.`,
          ),
        )
      }
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }

    // v1.3.0 W4 — boot-time reload of escalation records. Escalations are
    // TERMINAL by design (codex W4 advisory #3) — surface as informational
    // logs only; never auto-anything.
    try {
      const escalations = listEscalations(this.userKitOptions)
      if (escalations.length > 0) {
        this.onError(
          new Error(
            `[native-engine boot] ${escalations.length} escalation(s) on disk: ${escalations
              .map((r) => `${r.execution_id}@step${r.step_index}`)
              .join(', ')}. Escalations are terminal — review out-of-band.`,
          ),
        )
      }
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
  }

  /** Begin watching the H-Sutra log + processing events. Idempotent. */
  start(): void {
    if (this.started) return
    this.started = true

    this.connector.onEvent((evt) => {
      // v1.2.1 codex P1 fold: chain through turnQueue so events from the
      // synchronous connector are serialized despite handleHSutraEvent now
      // being async (host-LLM dispatch can take seconds).
      this.turnQueue = this.turnQueue.then(() =>
        this.handleHSutraEvent(evt)
          .then(() => undefined)
          .catch((err) => {
            this.onError(err instanceof Error ? err : new Error(String(err)))
          }),
      )
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
   * v1.2.1: await the queue of in-flight turns from the live connector path.
   * Useful for tests that need to assert state after an async dispatch
   * completes (since `handleHSutraEvent` returns immediately to the listener
   * but the work continues on the queue chain).
   */
  async drain(): Promise<void> {
    await this.turnQueue
  }

  /**
   * Process one founder event end-to-end:
   *   1. Router.route → RoutingDecision
   *   2. Emit routing_decision event → render line
   *   3. If matched: Workflow Engine executes step_graph
   *   4. Emit each workflow/step event → render line
   *
   * Returns the count of EngineEvents emitted (useful for tests + telemetry).
   *
   * v1.2.1: async to support invoke_host_llm dispatch through executeWorkflow.
   */
  async handleHSutraEvent(evt: HSutraEvent): Promise<number> {
    let emitted = 0

    // SPEC v1.2 §4.5(b) + v1.3.0 W2 — approve/reject command parsing PRECEDES
    // routing. Single parser handles BOTH namespaces (codex W2 advisory C):
    //   - P-<sha8> → proposal lifecycle (emergence v1)
    //   - E-<id>   → execution-approval lifecycle (step-level approval gate)
    const text = evt.input_text ?? ''
    const utt = parseApprovalUtterance(text)
    if (utt) {
      if (utt.namespace === 'P') {
        return utt.action === 'approve'
          ? this.applyApproval(utt.id, evt)
          : this.applyRejection(utt.id, utt.reason ?? 'no reason provided', evt)
      }
      // namespace === 'E' — v1.3.0 W2 step-level approval gate
      return utt.action === 'approve'
        ? await this.applyExecutionApproval(utt.id, evt)
        : this.applyExecutionRejection(utt.id, utt.reason ?? 'no reason provided', evt)
    }

    // v1.2.2 N7 (narrowed) — read evt.event_type with founder_input as default;
    // cron path now reachable when scheduler injects { event_type: 'cron', ... }
    const eventType = (evt as { event_type?: 'founder_input' | 'cron' }).event_type ?? 'founder_input'
    const decision = this.router.route({
      event_type: eventType,
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
      // v1.2.2 N2 — pass user-kit options so lite-executor writes DP-records
      // for routed executions; cmdRun direct path leaves these unset (codex
      // narrowing — keep direct executions ungated + non-DP).
      // v1.2.2 N4 — also resolve the operating Charter id (via STARTER_WORKFLOW_CHARTER_MAP
      // at v1.2.2; user-kit charter resolution is v1.x scope).
      // v1.3.0 W2 — wire approval_persist callback so a paused step writes
      // a durable ExecutionApprovalRecord to runtime/pending-approvals/.
      const charterId = STARTER_WORKFLOW_CHARTER_MAP.get(wf.id)
      await executeWorkflow({
        workflow: wf,
        execution_id: executionId,
        workflow_run_seq: this.executionCounter,
        user_kit_options_for_dp: this.userKitOptions,
        charter_id: charterId,
        // v1.3.0 W5 — wire PNC admission gate on routed runs.
        pnc_registry: this.pncRegistry,
        pnc_ctx: this.pncCtx,
        approval_persist: (rec) => {
          try {
            persistApproval(rec, this.userKitOptions)
          } catch (err) {
            // Re-throw — lite-executor turns persist failures into
            // workflow_failed reason=approval_persist_failed:<msg>, which
            // is the right founder-facing surface (no silent drop).
            throw err
          }
        },
        // v1.3.0 W4 — wire pause/escalation persist callbacks. Re-throws on
        // failure so lite-executor surfaces as workflow_failed reason
        // pause_persist_failed:<msg> / escalation_persist_failed:<msg>.
        pause_persist: (rec) => {
          persistPause(rec, this.userKitOptions)
        },
        escalation_persist: (rec) => {
          persistEscalation(rec, this.userKitOptions)
        },
        emit: (engineEvt) => {
          this.emitEvent(engineEvt, evt)
          emitted++
          // v1.3.0 W5 (codex W5 BLOCKER 3 fold) — listen for workflow_failed
          // on routed runs and emit commitment_broken when (a) the workflow
          // declares non-empty obligation_refs AND (b) charter_id is set AND
          // (c) the named obligation exists on the Charter.obligations list.
          //
          // Why HERE (NativeEngine) and NOT in lite-executor (codex W5
          // architectural note): lite-executor doesn't have the Charter map.
          // The mapping is workflow→obligation_refs (declared on Workflow) AND
          // charter→obligations (declared on Charter); only NativeEngine has
          // both halves loaded. Plus charter context is per-RUN (set when
          // routing exact-matches a trigger with a charter_id) — exactly what
          // this listener has via the closure.
          if (engineEvt.type === 'workflow_failed') {
            this.emitCommitmentBrokenIfApplicable(wf, charterId, executionId, engineEvt.reason, evt)
          }
        },
      })
      return emitted
    }

    // SPEC v1.2 §4.5(c) — no-match → run pattern detector → persist + emit
    // pattern_proposed events. Founder approves/rejects via subsequent
    // utterance ("approve P-xxx" / "reject P-xxx").
    if (decision.mode === 'no-match' && this.proposerEnabled) {
      try {
        emitted += this.runProposerPass(evt)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }

    return emitted
  }

  /** SPEC v1.2 §4.5(c) — proposer pass. Returns count of events emitted. */
  private runProposerPass(evt: HSutraEvent): number {
    const detectorOpts: PatternDetectorOptions = {
      hsutra_log_path: this.connector.getLogPath(),
      ...this.patternDetectorOptions,
      user_kit_opts: this.userKitOptions,
    }
    const triggers = this.router.getRegisteredTriggers()
    const patterns = detectPatterns(triggers, detectorOpts)
    let emitted = 0
    for (const p of patterns) {
      const built = buildProposal(p, { now_ms: this.nowMs() })
      try {
        persistProposal(built.entry, this.userKitOptions)
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
        continue
      }
      const proposedEvt: PatternProposedEvent = {
        type: 'pattern_proposed',
        ts_ms: this.nowMs(),
        pattern_id: p.pattern_id,
        normalized_phrase: p.normalized_phrase,
        evidence_count: p.evidence_count,
        proposed_workflow_id: built.workflow.id,
        proposed_trigger_id: built.trigger.id,
      }
      this.emitEvent(proposedEvt, evt)
      emitted++
    }
    return emitted
  }

  /**
   * SPEC v1.2 §4.5(b) — approve a pending proposal by pattern_id.
   *
   * Codex master P2.4 fold: ordering is now atomic-friendly:
   *   (1) Persist Workflow + TriggerSpec to user-kit (durable; survives restart)
   *   (2) Flip ledger status to 'approved' (audit truth)
   *   (3) Register trigger live + add workflow to in-memory map
   *   (4) Emit DecisionProvenance audit (P1.1 fold) + proposal_approved event
   *
   * On failure at any step the engine logs an error and returns early WITHOUT
   * emitting proposal_approved, so the founder never sees a confirmation that
   * is not backed by ledger state.
   */
  private applyApproval(pattern_id: string, evt: HSutraEvent): number {
    const entry = loadProposal(pattern_id, this.userKitOptions)
    if (!entry || entry.status !== 'pending') {
      this.onError(
        new Error(
          `applyApproval: no pending proposal for "${pattern_id}" (status=${entry?.status ?? 'absent'})`,
        ),
      )
      return 0
    }
    const built = buildProposal(
      {
        pattern_id: entry.pattern_id,
        normalized_phrase: entry.normalized_phrase,
        evidence_count: entry.evidence_count,
        utterance_samples: entry.utterance_samples,
        first_seen_ms: entry.first_seen_ms,
        last_seen_ms: entry.last_seen_ms,
      },
      {
        default_charter_id: entry.proposed_charter_id,
        default_domain_id: entry.proposed_domain_id,
        now_ms: entry.proposed_at_ms,
      },
    )

    // (1) Persist primitives first — these are durable and idempotent.
    try {
      persistWorkflow(built.workflow, this.userKitOptions)
      persistTrigger(built.trigger, this.userKitOptions)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    // (2) Flip ledger status — must succeed before live registration so a
    // crash between (1) and (3) leaves the ledger == truth on next boot.
    try {
      updateProposalStatus(
        pattern_id,
        'approved',
        `founder approved via "approve ${pattern_id}"`,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    // (3) Register live (in-memory). On failure emit nothing; next boot will
    // pick up the persisted Workflow + TriggerSpec via the user-kit loader.
    try {
      this.router.registerTrigger(built.trigger)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }
    this.workflowsById.set(built.workflow.id, built.workflow)

    // (4) Audit + UI event.
    const decided_at_ms = this.nowMs()
    try {
      appendDecisionProvenanceLog(
        buildEmergenceDecisionProvenance({
          decision_kind: 'APPROVE',
          pattern_id,
          target_workflow_id: built.workflow.id,
          decided_at_ms,
          outcome: `Approved emergent pattern ${pattern_id}; registered ${built.workflow.id} + ${built.trigger.id}`,
        }),
        this.userKitOptions,
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }

    const approvedEvt: ProposalApprovedEvent = {
      type: 'proposal_approved',
      ts_ms: decided_at_ms,
      pattern_id,
      registered_workflow_id: built.workflow.id,
      registered_trigger_id: built.trigger.id,
    }
    this.emitEvent(approvedEvt, evt)
    return 1
  }

  /** SPEC v1.2 §4.5(b) — reject a pending proposal by pattern_id. */
  private applyRejection(pattern_id: string, reason: string, evt: HSutraEvent): number {
    const entry = loadProposal(pattern_id, this.userKitOptions)
    if (!entry || entry.status !== 'pending') {
      this.onError(
        new Error(
          `applyRejection: no pending proposal for "${pattern_id}" (status=${entry?.status ?? 'absent'})`,
        ),
      )
      return 0
    }
    try {
      updateProposalStatus(pattern_id, 'rejected', reason, this.userKitOptions, this.nowMs())
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }
    const decided_at_ms = this.nowMs()
    try {
      appendDecisionProvenanceLog(
        buildEmergenceDecisionProvenance({
          decision_kind: 'REJECT',
          pattern_id,
          target_workflow_id: entry.proposed_workflow_id,
          decided_at_ms,
          outcome: `Rejected emergent pattern ${pattern_id}: ${reason}`,
        }),
        this.userKitOptions,
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    const rejectedEvt: ProposalRejectedEvent = {
      type: 'proposal_rejected',
      ts_ms: decided_at_ms,
      pattern_id,
      reason,
    }
    this.emitEvent(rejectedEvt, evt)
    return 1
  }

  /**
   * v1.3.0 W2 (codex W2 BLOCKER 3 + advisory C/D fold) — `approve E-<id>`
   * branch.
   *
   * Loads the ExecutionApprovalRecord; on status='pending' flips to
   * 'approved', emits approval_granted, then resumes the workflow run via
   * resumeApproved. On any other status (already-approved, resumed,
   * rejected, terminal) emits approval_already_handled with the original
   * decided_at_ms — never throws (advisory D: stale approve is no-op,
   * distinguishable from "never existed").
   */
  private async applyExecutionApproval(execId: string, evt: HSutraEvent): Promise<number> {
    const rec = loadApproval(execId, this.userKitOptions)
    if (!rec) {
      this.onError(
        new Error(`applyExecutionApproval: no approval record for "${execId}"`),
      )
      return 0
    }
    if (rec.status !== 'pending') {
      const handledEvt: ApprovalAlreadyHandledEvent = {
        type: 'approval_already_handled',
        ts_ms: this.nowMs(),
        execution_id: rec.execution_id,
        workflow_id: rec.workflow_id,
        step_index: rec.step_index,
        originally_decided_at_ms: rec.decided_at_ms ?? rec.created_at_ms,
      }
      this.emitEvent(handledEvt, evt)
      return 1
    }
    // v1.3.0 W4 (codex W4 advisory #3 mutual exclusion). Reject approve when
    // the same execId has a non-terminal pause OR any escalation record.
    // Approval and pause are different gates that shouldn't mix.
    const escRec = loadEscalation(execId, this.userKitOptions)
    if (escRec) {
      this.onError(
        new Error(
          `applyExecutionApproval: execution "${execId}" already escalated at step ${escRec.step_index} — escalated runs cannot be approved (mutual exclusion)`,
        ),
      )
      return 0
    }
    const pauseRec = loadPause(execId, this.userKitOptions)
    if (pauseRec && pauseRec.status === 'pending') {
      this.onError(
        new Error(
          `applyExecutionApproval: execution "${execId}" has a pending pause at step ${pauseRec.step_index} — cannot mix approval + pause gates (mutual exclusion)`,
        ),
      )
      return 0
    }

    // Atomic transition pending → approved (advisory E ordering: ledger
    // first, then runtime resume, then markResumed on completion).
    let updated: ExecutionApprovalRecord
    try {
      updated = updateApprovalStatus(
        execId,
        'approved',
        `founder approved via "approve ${execId}"`,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    const grantedEvt: ApprovalGrantedEvent = {
      type: 'approval_granted',
      ts_ms: this.nowMs(),
      execution_id: updated.execution_id,
      workflow_id: updated.workflow_id,
      step_index: updated.step_index,
    }
    this.emitEvent(grantedEvt, evt)
    let emitted = 1

    // Resume the workflow run from the paused step. The lite-executor
    // bypass at isResumeFirstStep skips the requires_approval gate exactly
    // once (for the step that was paused), so the workflow continues.
    try {
      emitted += await this.resumeApproved(updated, evt)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    return emitted
  }

  /**
   * v1.3.0 W2 — `reject E-<id> <reason>` branch.
   *
   * Loads the record; on pending flips to 'rejected', emits approval_denied
   * AND a workflow_failed (reason='approval_denied:<reason>') so the audit
   * trail shows the workflow terminated. On any other status emits
   * approval_already_handled (advisory D).
   */
  private applyExecutionRejection(execId: string, reason: string, evt: HSutraEvent): number {
    const rec = loadApproval(execId, this.userKitOptions)
    if (!rec) {
      this.onError(
        new Error(`applyExecutionRejection: no approval record for "${execId}"`),
      )
      return 0
    }
    if (rec.status !== 'pending') {
      const handledEvt: ApprovalAlreadyHandledEvent = {
        type: 'approval_already_handled',
        ts_ms: this.nowMs(),
        execution_id: rec.execution_id,
        workflow_id: rec.workflow_id,
        step_index: rec.step_index,
        originally_decided_at_ms: rec.decided_at_ms ?? rec.created_at_ms,
      }
      this.emitEvent(handledEvt, evt)
      return 1
    }

    let updated: ExecutionApprovalRecord
    try {
      updated = updateApprovalStatus(
        execId,
        'rejected',
        reason,
        this.userKitOptions,
        this.nowMs(),
      )
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
      return 0
    }

    const deniedEvt: ApprovalDeniedEvent = {
      type: 'approval_denied',
      ts_ms: this.nowMs(),
      execution_id: updated.execution_id,
      workflow_id: updated.workflow_id,
      step_index: updated.step_index,
      reason,
    }
    this.emitEvent(deniedEvt, evt)
    // Also emit workflow_failed so the audit trail closes the loop.
    const failedEvt: EngineEvent = {
      type: 'workflow_failed',
      ts_ms: this.nowMs(),
      workflow_id: updated.workflow_id,
      execution_id: updated.execution_id,
      reason: `approval_denied:${reason}`,
    }
    this.emitEvent(failedEvt, evt)
    return 2
  }

  /**
   * v1.3.0 W2 — resume an approved-and-paused execution.
   *
   * Looks up the original Workflow by workflow_id, then calls
   * executeWorkflowResume with resume_from_step_index = (paused_step_index - 1)
   * so the gated step IS the first step to run. The lite-executor bypass
   * skips its requires_approval gate exactly once.
   *
   * On completion (success or failure), markResumed flips the ledger entry
   * to 'resumed' so subsequent approve/reject for this execution returns
   * approval_already_handled.
   */
  private async resumeApproved(rec: ExecutionApprovalRecord, evt: HSutraEvent): Promise<number> {
    const wf = this.workflowsById.get(rec.workflow_id)
    if (!wf) {
      this.onError(
        new Error(`resumeApproved: workflow "${rec.workflow_id}" no longer loaded; cannot resume "${rec.execution_id}"`),
      )
      return 0
    }
    let emitted = 0
    const charterId = STARTER_WORKFLOW_CHARTER_MAP.get(wf.id)
    try {
      await executeWorkflowResume({
        workflow: wf,
        execution_id: rec.execution_id,
        workflow_run_seq: this.executionCounter,
        user_kit_options_for_dp: this.userKitOptions,
        charter_id: charterId,
        // v1.3.0 W5 — wire PNC admission gate on resumed runs too. Note: the
        // precondition gate fires only when the executor enters at step 1;
        // resume runs skip past step 1 via resume_from_step_index, so the
        // precondition_check is NOT re-emitted on resume (correct semantics —
        // the workflow was already admitted on the original run). The
        // postcondition gate may still fire if the resumed run reaches the
        // workflow_completed site.
        pnc_registry: this.pncRegistry,
        pnc_ctx: this.pncCtx,
        // Resume MUST skip steps 1..paused_step_index-1 so the gated step
        // (paused_step_index) is the first to execute. The bypass on
        // isResumeFirstStep skips its requires_approval gate.
        resume_from_step_index: rec.step_index - 1,
        // Wire approval_persist again so a SECOND requires_approval=true
        // step downstream can pause the resumed run.
        approval_persist: (r) => {
          persistApproval(r, this.userKitOptions)
        },
        // v1.3.0 W4 — wire pause/escalation persist on resumed runs too;
        // a downstream step in the resumed remainder may hit on_failure=
        // 'pause' or 'escalate'.
        pause_persist: (r) => {
          persistPause(r, this.userKitOptions)
        },
        escalation_persist: (r) => {
          persistEscalation(r, this.userKitOptions)
        },
        emit: (engineEvt) => {
          this.emitEvent(engineEvt, evt)
          emitted++
          if (engineEvt.type === 'workflow_failed') {
            this.emitCommitmentBrokenIfApplicable(wf, charterId, rec.execution_id, engineEvt.reason, evt)
          }
        },
      })
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    // Ledger transition approved → resumed (terminal sink for the resume side).
    try {
      markResumed(rec.execution_id, this.userKitOptions, this.nowMs())
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    return emitted
  }

  /**
   * v1.3.0 W4 — programmatic resume of an on_failure='pause' execution.
   *
   * Called by callers / external surfaces (future `resume E-<id>` utterance
   * routing). Loads the ExecutionPauseRecord; on status='pending' continues
   * the workflow run from step_index+1 (the failed step is NOT re-run —
   * pause means "human took over, move on").
   *
   * Codex W4 advisory #3 mutual exclusion guards (CHECKED IN ORDER):
   *   1. No pause record on disk for execId          → throws (caller bug)
   *   2. Pause record status !== 'pending'           → throws (already
   *      resumed/terminalized — distinguishable from #4 case)
   *   3. Escalation record exists for SAME execId    → throws (mutually
   *      exclusive — escalated runs are terminal by design)
   *   4. Approval record exists for SAME execId in non-terminal state
   *      → throws (mixed transition — approval and pause are different
   *      gates and shouldn't combine accidentally)
   *
   * Returns the count of EngineEvents emitted by the resumed run (matches
   * the resumeApproved return contract).
   */
  async resumeFromPause(execId: string): Promise<number> {
    const rec = loadPause(execId, this.userKitOptions)
    if (!rec) {
      throw new Error(`resumeFromPause: no pause record found with id "${execId}"`)
    }
    if (rec.status !== 'pending') {
      throw new Error(
        `resumeFromPause: pause record "${execId}" is in status "${rec.status}" — only pending pauses may be resumed`,
      )
    }
    // Mutual exclusion — escalations are terminal by design.
    const escRec = loadEscalation(execId, this.userKitOptions)
    if (escRec) {
      throw new Error(
        `resumeFromPause: execution "${execId}" already escalated at step ${escRec.step_index} — escalated runs cannot be resumed (codex W4 advisory #3 mutual exclusion)`,
      )
    }
    // Mutual exclusion — approval gate is a different surface; reject mixed
    // transitions where the same execId has both a pending pause AND a
    // non-terminal approval record.
    const apprRec = loadApproval(execId, this.userKitOptions)
    if (apprRec && apprRec.status !== 'resumed' && apprRec.status !== 'terminal') {
      throw new Error(
        `resumeFromPause: execution "${execId}" has a non-terminal approval record (status=${apprRec.status}) — approval and pause gates cannot mix (codex W4 advisory #3 mutual exclusion)`,
      )
    }

    const wf = this.workflowsById.get(rec.workflow_id)
    if (!wf) {
      throw new Error(
        `resumeFromPause: workflow "${rec.workflow_id}" no longer loaded; cannot resume "${execId}"`,
      )
    }

    let emitted = 0
    const charterId = STARTER_WORKFLOW_CHARTER_MAP.get(wf.id)
    // Resume MUST skip steps 1..rec.step_index (the failed step is NOT
    // re-run — pause semantics). The next iteration starts at step_index+1.
    try {
      await executeWorkflowResume({
        workflow: wf,
        execution_id: rec.execution_id,
        workflow_run_seq: this.executionCounter,
        user_kit_options_for_dp: this.userKitOptions,
        charter_id: charterId,
        // v1.3.0 W5 — wire PNC gate on pause-resume too (postcondition only —
        // precondition skipped because resume_from_step_index > 0).
        pnc_registry: this.pncRegistry,
        pnc_ctx: this.pncCtx,
        resume_from_step_index: rec.step_index,
        approval_persist: (r) => {
          persistApproval(r, this.userKitOptions)
        },
        pause_persist: (r) => {
          persistPause(r, this.userKitOptions)
        },
        escalation_persist: (r) => {
          persistEscalation(r, this.userKitOptions)
        },
        emit: (engineEvt) => {
          // No HSutraEvent context — emit with hsutra=null so the renderer
          // skips cell prefixing (matches in-process programmatic call).
          this.emitEvent(engineEvt, null)
          emitted++
          if (engineEvt.type === 'workflow_failed') {
            this.emitCommitmentBrokenIfApplicable(wf, charterId, rec.execution_id, engineEvt.reason, null)
          }
        },
      })
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    // Ledger transition pending → resumed (terminal sink).
    try {
      markPauseResumed(rec.execution_id, this.userKitOptions, this.nowMs())
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    return emitted
  }

  /**
   * Public helper: run a single founder turn (no log file round-trip).
   * Used by tests + the v1.1.0 demo path.
   *
   * v1.2.1: async to forward host-LLM dispatch errors / completion ordering
   * from handleHSutraEvent's executeWorkflow await.
   */
  async ingest(evt: HSutraEvent): Promise<number> {
    return this.handleHSutraEvent(evt)
  }

  /** Lookup the Charter that operationalizes a Workflow (v1.1.0 starter map). */
  ownerCharterOf(workflowId: string): string | undefined {
    return STARTER_WORKFLOW_CHARTER_MAP.get(workflowId)
  }

  /**
   * v1.3.0 W5 (codex W5 BLOCKER 3 fold) — emit commitment_broken events when
   * (a) a routed workflow fails AND (b) the workflow declares non-empty
   * obligation_refs AND (c) charter_id is set in execution context AND
   * (d) the named obligation exists on the Charter's obligations list.
   *
   * Per codex: workflow→obligation mapping is DECLARATIVE. We never infer from
   * step text. The match is a literal name comparison: workflow.obligation_refs
   * (Workflow primitive declaration) ∩ charter.obligations[].name (Charter
   * declaration). Each intersection emits one commitment_broken event.
   *
   * Skip rules:
   *   - charterId undefined         → no Charter context for this run; skip.
   *     (cmdRun direct path / no STARTER_WORKFLOW_CHARTER_MAP entry.)
   *   - obligation_refs empty       → workflow makes no Charter-level
   *     commitments; skip silently.
   *   - charter not loaded by id    → cross-reference failure; log + skip.
   *   - obligation_name not on charter → declared but missing from Charter;
   *     log + skip (the workflow promised something the Charter doesn't track).
   */
  private emitCommitmentBrokenIfApplicable(
    wf: Workflow,
    charterId: string | undefined,
    executionId: string,
    failureReason: string,
    hsutra: HSutraEvent | null,
  ): void {
    if (!charterId) return
    if (!wf.obligation_refs || wf.obligation_refs.length === 0) return
    const charter = this.chartersById.get(charterId)
    if (!charter) {
      this.onError(
        new Error(
          `[commitment_broken] charter "${charterId}" not loaded; cannot resolve obligations for workflow "${wf.id}" (codex W5 BLOCKER 3 declarative mapping)`,
        ),
      )
      return
    }
    const obligationNames = new Set(charter.obligations.map((c) => c.name))
    for (const ref of wf.obligation_refs) {
      if (!obligationNames.has(ref)) {
        this.onError(
          new Error(
            `[commitment_broken] workflow "${wf.id}" declares obligation_ref "${ref}" but charter "${charterId}" has no obligation by that name; skipping (codex W5 BLOCKER 3 — declarative join)`,
          ),
        )
        continue
      }
      const evt: CommitmentBrokenEvent = {
        type: 'commitment_broken',
        ts_ms: this.nowMs(),
        charter_id: charterId,
        obligation_name: ref,
        workflow_id: wf.id,
        execution_id: executionId,
        evidence: failureReason,
      }
      this.emitEvent(evt, hsutra)
    }
  }

  private emitEvent(event: EngineEvent, hsutra: HSutraEvent | null): void {
    try {
      const line = this.renderer.render(event, { hsutra: hsutra ?? null })
      if (line) this.write(line)
    } catch (err) {
      this.onError(err instanceof Error ? err : new Error(String(err)))
    }
    // v1.3.0 W6 — durable telemetry sink. Wrapped in its own try/catch so
    // a sink failure (disk full, permission, etc) never breaks the
    // renderer path or aborts the workflow run. Routes through onError.
    if (this.telemetrySinkPath) {
      try {
        appendTelemetry(event, { home: this.telemetrySinkPath })
      } catch (err) {
        this.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }
  }
}

/** Convenience builder for the v1.1.0 default engine wiring. */
export function createDefaultEngine(options: NativeEngineOptions = {}): NativeEngine {
  return new NativeEngine(options)
}
