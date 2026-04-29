/**
 * Activity wrapper — M5 Group I (T-043, T-044).
 *
 * Sutra's I/O boundary. Every Workflow step that needs to touch the outside
 * world (network, filesystem, clock, randomness, model calls) MUST go through
 * an Activity. Workflow code itself is pure orchestration and MUST be
 * replay-deterministic.
 *
 * The wrapper enforces F-12 ("Workflow code performs I/O") at runtime: if an
 * Activity-wrapped function is invoked from inside a Workflow execution
 * context, we throw — the boundary is real, observable, and trapped.
 *
 * F-12 scope at M5 (per codex P2.4): RUNTIME ONLY. Schema-level integration
 * with `terminalCheck` ships at M9 once the evidence-input shape exists.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I T-043, T-044
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

import type { ForbiddenCouplingId } from '../laws/l4-terminal-check.js'

/**
 * Stable string tag carried by every F-12 trap error. Tests assert by tag so
 * the message wording can evolve without breaking the contract.
 */
export const F12_ERROR_TAG: ForbiddenCouplingId = 'F-12'

/** Generic Activity function — async-only by construction. */
export type ActivityFn<Args extends unknown[], R> = (...args: Args) => Promise<R>

/**
 * Workflow-context probe. The default probe attempts to read Temporal's
 * `inWorkflowContext()` lazily (via `@temporalio/workflow`); when that import
 * is unavailable or throws (i.e. we are in regular Node runtime), the probe
 * returns `false`. Tests inject their own probe via the `__set...ForTest`
 * hooks below.
 */
type WorkflowContextProbe = () => boolean

let workflowContextProbe: WorkflowContextProbe = defaultWorkflowContextProbe

function defaultWorkflowContextProbe(): boolean {
  // We cannot statically import `@temporalio/workflow` at module load — that
  // module's runtime guards itself against being loaded outside a Workflow
  // sandbox. We attempt a guarded `require`; failure ⇒ "not in Workflow
  // context" (the safe default — Activities running on a Worker sit in
  // ordinary Node runtime where the Workflow module is absent or inert).
  try {
    // Use dynamic require via createRequire so this file remains ESM-clean.
    // The Temporal Workflow module exposes `inWorkflowContext()` from v1.x.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const wfMod: unknown = (Function('return require'))()('@temporalio/workflow')
    if (
      typeof wfMod === 'object' &&
      wfMod !== null &&
      'inWorkflowContext' in wfMod &&
      typeof (wfMod as { inWorkflowContext: unknown }).inWorkflowContext === 'function'
    ) {
      return Boolean((wfMod as { inWorkflowContext: () => boolean }).inWorkflowContext())
    }
    return false
  } catch {
    return false
  }
}

/** Test seam — override the probe (e.g. simulate Workflow context). */
export function __setWorkflowContextProbeForTest(probe: WorkflowContextProbe): void {
  workflowContextProbe = probe
}

/** Test seam — restore default probe behavior. */
export function __resetWorkflowContextProbeForTest(): void {
  workflowContextProbe = defaultWorkflowContextProbe
}

/**
 * Wrap an async impl as an Activity. The returned function:
 *  - invokes the impl when called outside a Workflow context (positive path)
 *  - throws an F-12 error when called inside a Workflow context (negative
 *    path — F-12 RUNTIME TRAP per codex P2.4)
 *
 * Registration-time guards:
 *  - impl must be a function
 *  - impl must be async (return a Promise) — enforced by inspecting
 *    `Function.prototype.constructor.name === 'AsyncFunction'`. Sync impls
 *    are rejected synchronously so misuse fails fast at startup, not at the
 *    first call.
 *
 * @template Args  Tuple of impl argument types.
 * @template R     Awaited result type.
 * @param impl     Async function to wrap as an Activity.
 * @returns ActivityFn<Args, R>
 */
export function asActivity<Args extends unknown[], R>(
  impl: ActivityFn<Args, R>,
): ActivityFn<Args, R> {
  if (typeof impl !== 'function') {
    throw new TypeError(
      `asActivity: impl must be a function; got ${typeof impl}`,
    )
  }
  // AsyncFunction constructor name is the standard discriminator.
  const isAsync =
    impl.constructor && impl.constructor.name === 'AsyncFunction'
  if (!isAsync) {
    throw new TypeError(
      'asActivity: impl must be async (declared with `async` or returning a Promise constructor). ' +
        'Sync impls violate the ActivityFn contract.',
    )
  }

  return async function activityFn(...args: Args): Promise<R> {
    if (workflowContextProbe()) {
      throw new Error(
        `[${F12_ERROR_TAG}] Forbidden coupling — Workflow code performs I/O. ` +
          'Activities must be invoked via proxyActivities() from Workflow code, ' +
          'not called directly inside the Workflow function. ' +
          'See holding/plans/native-v1.0/M5-workflow-engine.md F-12.',
      )
    }
    return impl(...args)
  }
}
