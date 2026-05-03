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
import type { ForbiddenCouplingId } from '../laws/l4-terminal-check.js';
/**
 * Stable string tag carried by every F-12 trap error. Tests assert by tag so
 * the message wording can evolve without breaking the contract.
 */
export declare const F12_ERROR_TAG: ForbiddenCouplingId;
/** Generic Activity function — async-only by construction. */
export type ActivityFn<Args extends unknown[], R> = (...args: Args) => Promise<R>;
/**
 * Workflow-context probe. The default probe attempts to read Temporal's
 * `inWorkflowContext()` lazily (via `@temporalio/workflow`); when that import
 * is unavailable or throws (i.e. we are in regular Node runtime), the probe
 * returns `false`. Tests inject their own probe via the `__set...ForTest`
 * hooks below.
 */
type WorkflowContextProbe = () => boolean;
/**
 * Internal test seams — accessed via `src/engine/_test_seams.ts` so they do
 * NOT leak into the public engine barrel. Tests import from `_test_seams.ts`
 * directly.
 */
export declare function __setWorkflowContextProbeForTest(probe: WorkflowContextProbe): void;
export declare function __resetWorkflowContextProbeForTest(): void;
/**
 * Wrap an async-callable impl as an Activity. The returned function:
 *  - invokes the impl when called outside a Workflow context (positive path)
 *  - throws an F-12 error when called inside a Workflow context (negative
 *    path — F-12 RUNTIME TRAP per codex P2.4)
 *
 * Registration-time guards:
 *  - impl must be a function (any callable)
 *
 * Async-shape contract:
 *  - The public type contract is `(...args: Args) => Promise<R>` — any
 *    function returning a Promise (declared `async`, bound async, factory-
 *    produced Promise-returning callable, `() => Promise.resolve(...)`).
 *  - Codex master review 2026-04-29 P2.2 (advisory): the prior gate
 *    `impl.constructor.name === 'AsyncFunction'` was narrower than the type
 *    contract — it rejected bound-async + factory-produced Promise-returning
 *    callables despite the type permitting them. Gate is now broadened to
 *    "is a function"; the wrapper itself is an `async function` so any sync
 *    return is auto-wrapped in `Promise.resolve(...)`. A sync impl that
 *    violates the contract surfaces at first real call (TypeError on the
 *    consumer's `await`-on-non-promise expectations) rather than registration,
 *    which the wrapper's `async function` envelope already covers.
 *
 * @template Args  Tuple of impl argument types.
 * @template R     Awaited result type.
 * @param impl     Async-callable function to wrap as an Activity.
 * @returns ActivityFn<Args, R>
 */
export declare function asActivity<Args extends unknown[], R>(impl: ActivityFn<Args, R>): ActivityFn<Args, R>;
export {};
//# sourceMappingURL=activity-wrapper.d.ts.map