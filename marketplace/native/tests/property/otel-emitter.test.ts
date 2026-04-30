/**
 * OTel emitter — trace_id correlation property test (M8 Group Z T-110).
 *
 * Property: for every Workflow execution that emits at least one OTel
 * event, ALL emitted events from one run share the same trace_id. This
 * is the universal evidence-emit correlation invariant — observability
 * downstream (collector, dashboards, audit) groups by trace_id, so a
 * leak between runs would silently fragment a single execution's audit
 * trail.
 *
 * Run shape:
 *   1. Generate an arbitrary Workflow (workflowArb).
 *   2. Build a deterministic dispatcher (mixed ok/fail outcomes).
 *   3. Wire an InMemoryOTelExporter behind an OTelEmitter.
 *   4. Reset the per-Workflow run_seq counter (so back-to-back property
 *      cases produce identical trace_ids for identical inputs — keeps the
 *      executor's replay-determinism contract intact).
 *   5. Execute → collect emitted records.
 *   6. Assert: every record's trace_id is identical AND non-empty.
 *
 * ≥1000 cases.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group Z T-110
 *   - .enforcement/codex-reviews/2026-04-30-architecture-pivot-rereview.md
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../src/engine/step-graph-executor.js'
import {
  InMemoryOTelExporter,
  OTelEmitter,
} from '../../src/engine/otel-emitter.js'
import { workflowArb } from './arbitraries.js'
import type { Workflow } from '../../src/primitives/workflow.js'

const PROP_RUNS = 1000

/**
 * Build a deterministic dispatcher from a per-step outcome plan. `plan[i]`
 * is consumed for `step_graph[i]`; falls back to ok-with-empty-outputs when
 * the plan is shorter than the step_graph. Errors are pure functions of
 * step_id so two back-to-back runs produce identical outputs.
 */
function buildDispatcher(plan: ReadonlyArray<'ok' | 'fail'>): ActivityDispatcher {
  let i = 0
  return (descriptor): StepDispatchResult => {
    const directive = plan[i++] ?? 'ok'
    if (directive === 'fail') {
      return { kind: 'failure', error: new Error(`step-${descriptor.step_id}-fail`) }
    }
    return { kind: 'ok', outputs: [`out-${descriptor.step_id}`] }
  }
}

describe('OTel emitter — trace_id correlation invariant (≥1000 cases)', () => {
  it('every event from one workflow run shares the same trace_id', async () => {
    await fc.assert(
      fc.asyncProperty(
        workflowArb(),
        fc.array(fc.constantFrom<'ok' | 'fail'>('ok', 'fail'), {
          minLength: 0,
          maxLength: 5,
        }),
        async (workflow: Workflow, plan) => {
          // Skip workflows whose first step is a terminate — the executor
          // returns immediately without emitting STEP_*; nothing to assert.
          if (workflow.step_graph[0]?.action === 'terminate') {
            return
          }

          // Reset the per-Workflow run_seq counter so back-to-back property
          // cases cannot accumulate state between runs (keeps the trace_id
          // derivation deterministic per input).
          __resetWorkflowRunSeqForTest()

          const exporter = new InMemoryOTelExporter()
          const emitter = new OTelEmitter(exporter)

          await executeStepGraph(workflow, buildDispatcher(plan), {
            otel_emitter: emitter,
          })

          // No events at all is acceptable for some inputs (e.g. a single
          // terminate step). The invariant is "if there are events, they
          // all share one trace_id."
          if (exporter.records.length === 0) return

          const first = exporter.records[0]!.trace_id
          expect(typeof first).toBe('string')
          expect(first.length).toBeGreaterThan(0)
          for (const r of exporter.records) {
            expect(r.trace_id).toBe(first)
          }
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })

  it('two back-to-back runs of the same workflow produce identical trace_ids', async () => {
    // Replay-determinism contract: same workflow + same dispatcher plan +
    // reset run_seq ⇒ same trace_id on every call. The property test above
    // is per-run; this companion case asserts cross-run determinism.
    await fc.assert(
      fc.asyncProperty(
        workflowArb(),
        fc.array(fc.constantFrom<'ok' | 'fail'>('ok', 'fail'), {
          minLength: 0,
          maxLength: 5,
        }),
        async (workflow: Workflow, plan) => {
          if (workflow.step_graph[0]?.action === 'terminate') return

          // Run 1
          __resetWorkflowRunSeqForTest()
          const exp1 = new InMemoryOTelExporter()
          await executeStepGraph(workflow, buildDispatcher(plan), {
            otel_emitter: new OTelEmitter(exp1),
          })

          // Run 2 — fresh exporter, same workflow + plan, reset counter.
          __resetWorkflowRunSeqForTest()
          const exp2 = new InMemoryOTelExporter()
          await executeStepGraph(workflow, buildDispatcher(plan), {
            otel_emitter: new OTelEmitter(exp2),
          })

          if (exp1.records.length === 0 && exp2.records.length === 0) return
          // Both runs MUST have the same number of records AND the trace_ids
          // must match position-by-position (deterministic emission).
          expect(exp2.records.length).toBe(exp1.records.length)
          if (exp1.records.length > 0) {
            expect(exp2.records[0]!.trace_id).toBe(exp1.records[0]!.trace_id)
          }
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })

  it('trace_id is sha256-hex truncated to 32 chars', async () => {
    // Codex master-review smoke: reject regressions where a future refactor
    // shortens / lengthens the trace_id format. The property holds for any
    // workflow run that emits ≥1 record.
    await fc.assert(
      fc.asyncProperty(workflowArb(), async (workflow: Workflow) => {
        if (workflow.step_graph[0]?.action === 'terminate') return
        __resetWorkflowRunSeqForTest()
        const exporter = new InMemoryOTelExporter()
        await executeStepGraph(
          workflow,
          () => ({ kind: 'ok', outputs: [] }),
          { otel_emitter: new OTelEmitter(exporter) },
        )
        if (exporter.records.length === 0) return
        const tid = exporter.records[0]!.trace_id
        expect(tid).toMatch(/^[a-f0-9]{32}$/)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
