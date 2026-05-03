/**
 * CadenceScheduler — M9 Group GG (T-156..T-160).
 *
 * Per-cadence callback dispatcher with DETERMINISTIC clock injection so the
 * Native runtime can register a recurring "fire callback every N minutes/
 * hours" semantic without depending on real wall-clock time. Production code
 * supplies `Date.now`-based clock; tests pass a deterministic seam so the
 * suite never sleeps and properties run ≥1000 cases in milliseconds.
 *
 * The scheduler is a SCHEDULER not a daemon: there is no background timer.
 * The host process drives time forward by calling `tick(now?)` whenever it
 * wants to dispatch any callbacks whose next-fire-time is ≤ `now`. v1.0
 * intentionally omits the daemon loop — D-NS-34 "NO REAL DAEMON at v1.0"
 * (M9 plan §Architecture decisions). When a v1.x consumer wants daemon
 * semantics they wrap `tick()` in setInterval / a Temporal periodic
 * Workflow / a cron job — the scheduler makes no claim about how time
 * advances.
 *
 * Cadence spec kinds (D-NS-34):
 *   - 'every_n_minutes' / 'every_n_hours' — uniform period; first fire is
 *     `start_at + period`, subsequent fires are `last_fire_at + period`.
 *   - 'every_day_at'    — daily at HH:MM (UTC). next-fire-time recomputes
 *     against the supplied clock; jitter applies same as periodic.
 *   - 'cron'            — escape hatch carrying a raw cron expression for
 *     v1.x adopters; the scheduler stores it but does NOT evaluate cron
 *     at v1.0 (would require a parser the runtime has no place for yet).
 *     A cron handle's next-fire-time is `+Infinity` until the v1.x cron
 *     evaluator lands; tick() never fires it. Documented escape so the
 *     API surface is forward-compatible.
 *
 * Jitter (I-12 invariant):
 *   - Each fire records `actual_fire_at`; the scheduler asserts
 *     `|actual - scheduled| ≤ 5 minutes` (300_000 ms) per D5 §6 + memory
 *     [Cadence is hours not days]. The property test
 *     `tests/property/cadence-scheduler-jitter.test.ts` covers ≥1000 cases.
 *
 * Deterministic clock seam:
 *   - `new CadenceScheduler({ clock })` accepts a `() => number` callable.
 *     Default = `Date.now`. `tick(now?)` accepts an optional override —
 *     when omitted it pulls from the configured clock. This 2-tier seam
 *     lets a host process (production: `Date.now`) and a test case (a
 *     deterministic counter) share the same scheduler without dance.
 *
 * State + concurrency:
 *   - Pure JS Map<handle_id, RegisteredCadence>. No I/O, no Promise scheduling
 *     except the user's callback (awaited). Concurrent tick() calls are
 *     not supported at v1.0 (the host must serialize tick() calls); a
 *     future v1.x async-fence wraps tick() in an internal mutex.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group GG T-156..T-160
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §1 I-12
 *   - memory entry [Cadence is hours not days]
 */
/**
 * Default jitter band (ms): ±5 minutes per I-12 (D5 §6).
 *
 * Made a module-level constant rather than a private field so tests +
 * external observers can reference it without instance access. Mirrors
 * the `SKILL_RECURSION_CAP` pattern in skill-invocation.ts.
 */
export declare const CADENCE_JITTER_MS: number;
/**
 * One of four cadence-spec shapes. Discriminated by `kind`. The spec is
 * the immutable scheduling contract the registrant supplies; the engine
 * derives next-fire-time from it.
 *
 * Why 4 kinds (not 1 generic millisecond-period field): the founder
 * memory [Cadence is hours not days] frames cadence in units. Modeling
 * the unit explicitly (minutes / hours / day-time / cron) keeps the
 * registration call site readable + downstream observability surfaces
 * the cadence kind verbatim (e.g. dashboards: "fired 6× per hour").
 */
export type CadenceSpec = {
    kind: 'every_n_minutes';
    n: number;
} | {
    kind: 'every_n_hours';
    n: number;
} | {
    kind: 'every_day_at';
    hour_utc: number;
    minute_utc: number;
} | {
    kind: 'cron';
    expression: string;
};
/** Registrant-supplied callback. Async to allow cadence-driven I/O. */
export type CadenceCallback = () => Promise<void> | void;
/**
 * Opaque handle returned by `register()`. Pass to `unregister()` to remove.
 *
 * Internally it's just a string id; the scheduler keeps the actual cadence
 * record in a private Map so no consumer can mutate registration state by
 * twisting the handle.
 */
export type CadenceHandle = string;
/** Construction options. Defaults documented inline. */
export interface CadenceSchedulerOptions {
    /**
     * Deterministic clock seam. Default: `Date.now`. Tests pass a counter
     * or a fast-check arbitrary so they never sleep.
     */
    clock?: () => number;
}
/**
 * The scheduler. Stateless across construction (no global state); each
 * instance owns its own Map of registered cadences + own clock.
 *
 * Lifecycle:
 *   1. const sched = new CadenceScheduler({ clock })
 *   2. sched.start()  — sets the "started" flag; primes next_fire_at on
 *      every registered cadence (computed against the configured clock).
 *      Cadences registered AFTER start() get their next_fire_at primed
 *      at register-time too.
 *   3. sched.tick(now?) — dispatches every cadence whose next_fire_at ≤ now
 *      (or the clock-supplied now when omitted). Each fire awaits the
 *      callback; failures are surfaced via the returned TickReport but
 *      do NOT halt remaining dispatches in the same tick.
 *   4. sched.stop() — clears the "started" flag; tick() becomes a no-op.
 *
 * Idempotent: start() / stop() are safe to call repeatedly. unregister()
 * is silent on miss.
 */
export declare class CadenceScheduler {
    private readonly registry;
    private readonly clock;
    private started;
    private nextHandleSeq;
    constructor(options?: CadenceSchedulerOptions);
    /**
     * Register a cadence. Returns an opaque handle the caller can pass to
     * `unregister()`. The first fire time is computed at registration; if
     * the scheduler is not yet started, it stays primed but won't fire
     * until `start()` is called AND tick() reaches its time.
     *
     * Validation:
     *   - `every_n_minutes` / `every_n_hours`: n MUST be a positive integer.
     *   - `every_day_at`: hour_utc ∈ [0, 23], minute_utc ∈ [0, 59], integers.
     *   - `cron`: expression non-empty string.
     *   - callback MUST be a function.
     */
    register(spec: CadenceSpec, callback: CadenceCallback): CadenceHandle;
    /**
     * Remove a cadence. Silent on miss — keeps cleanup idempotent for
     * callers that don't track registration state.
     */
    unregister(handle: CadenceHandle): void;
    /** Mark scheduler started. Idempotent. */
    start(): void;
    /** Mark scheduler stopped. tick() becomes a no-op while stopped. */
    stop(): void;
    /** Test/introspection: is the scheduler started? */
    isStarted(): boolean;
    /** How many cadences are registered. */
    size(): number;
    /**
     * Drive the clock forward to `now` (or the configured clock's value
     * when omitted). For every cadence whose next_fire_at ≤ now, dispatch
     * the callback (awaited) and advance next_fire_at by the cadence's
     * period.
     *
     * Returns a TickReport summarizing fires + errors so the caller can
     * propagate to OTel / observability without the scheduler doing I/O
     * itself.
     *
     * No-op when not started.
     */
    tick(now?: number): Promise<TickReport>;
    /**
     * Read the most-recent jitter (ms) for a registered handle, or `null`
     * if the cadence has not fired yet. Used by tests + dashboards.
     */
    getJitterMs(handle: CadenceHandle): number | null;
    /** Read next_fire_at for a registered handle (testing aid). */
    getNextFireAt(handle: CadenceHandle): number | null;
}
/** A successful fire entry surfaced on the TickReport. */
export interface TickFireEntry {
    readonly handle: CadenceHandle;
    readonly fired_at: number;
    readonly scheduled_at: number;
    readonly jitter_ms: number;
}
/** A failed fire entry surfaced on the TickReport. */
export interface TickErrorEntry {
    readonly handle: CadenceHandle;
    readonly fired_at: number;
    readonly error_message: string;
}
/** Output of `tick()`. */
export interface TickReport {
    readonly fires: ReadonlyArray<TickFireEntry>;
    readonly errors: ReadonlyArray<TickErrorEntry>;
}
//# sourceMappingURL=cadence-scheduler.d.ts.map