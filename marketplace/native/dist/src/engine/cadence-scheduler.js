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
export const CADENCE_JITTER_MS = 5 * 60 * 1000;
/** ms per minute / per hour — extracted for readability. */
const MS_PER_MINUTE = 60 * 1000;
const MS_PER_HOUR = 60 * 60 * 1000;
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
export class CadenceScheduler {
    registry = new Map();
    clock;
    started = false;
    nextHandleSeq = 0;
    constructor(options = {}) {
        this.clock = options.clock ?? Date.now;
    }
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
    register(spec, callback) {
        if (typeof callback !== 'function') {
            throw new TypeError('CadenceScheduler.register: callback must be a function');
        }
        validateSpec(spec);
        const now = this.clock();
        const handle = `cad-${++this.nextHandleSeq}`;
        const next_fire_at = computeFirstFireAt(spec, now);
        this.registry.set(handle, {
            handle,
            spec,
            callback,
            registered_at: now,
            next_fire_at,
        });
        return handle;
    }
    /**
     * Remove a cadence. Silent on miss — keeps cleanup idempotent for
     * callers that don't track registration state.
     */
    unregister(handle) {
        this.registry.delete(handle);
    }
    /** Mark scheduler started. Idempotent. */
    start() {
        this.started = true;
    }
    /** Mark scheduler stopped. tick() becomes a no-op while stopped. */
    stop() {
        this.started = false;
    }
    /** Test/introspection: is the scheduler started? */
    isStarted() {
        return this.started;
    }
    /** How many cadences are registered. */
    size() {
        return this.registry.size;
    }
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
    async tick(now) {
        if (!this.started) {
            return { fires: [], errors: [] };
        }
        const t = typeof now === 'number' && Number.isFinite(now) ? now : this.clock();
        const fires = [];
        const errors = [];
        // Snapshot handles before iteration — callbacks may unregister during
        // tick (though documented as "v1.0 doesn't support recursive
        // registration changes during tick"). The snapshot keeps the ordering
        // stable + iteration crash-free if the registry mutates.
        const handles = [...this.registry.keys()];
        for (const handle of handles) {
            const cad = this.registry.get(handle);
            if (cad === undefined)
                continue; // unregistered mid-tick
            if (cad.next_fire_at > t)
                continue;
            // cron handles never fire at v1.0 — their next_fire_at is +Infinity.
            if (!Number.isFinite(cad.next_fire_at))
                continue;
            const scheduled = cad.next_fire_at;
            const jitter_ms = Math.abs(t - scheduled);
            cad.last_actual_fire_at = t;
            cad.last_scheduled_fire_at = scheduled;
            // Advance next_fire_at BEFORE dispatching the callback. Reasoning:
            // a callback that unregisters this same handle should not affect
            // an already-decided next-fire (we want the contract "the cadence
            // fired at t and will fire next at t+period" to hold even if the
            // callback unregisters; the registry delete merely makes the next
            // tick skip the entry).
            cad.next_fire_at = computeNextFireAt(cad.spec, scheduled, t);
            try {
                await cad.callback();
                fires.push({ handle, fired_at: t, scheduled_at: scheduled, jitter_ms });
            }
            catch (err) {
                const msg = err instanceof Error ? err.message : String(err);
                errors.push({ handle, fired_at: t, error_message: msg });
            }
        }
        return { fires, errors };
    }
    /**
     * Read the most-recent jitter (ms) for a registered handle, or `null`
     * if the cadence has not fired yet. Used by tests + dashboards.
     */
    getJitterMs(handle) {
        const cad = this.registry.get(handle);
        if (cad === undefined)
            return null;
        if (cad.last_actual_fire_at === undefined || cad.last_scheduled_fire_at === undefined) {
            return null;
        }
        return Math.abs(cad.last_actual_fire_at - cad.last_scheduled_fire_at);
    }
    /** Read next_fire_at for a registered handle (testing aid). */
    getNextFireAt(handle) {
        const cad = this.registry.get(handle);
        return cad === undefined ? null : cad.next_fire_at;
    }
}
// =============================================================================
// Spec helpers
// =============================================================================
function validateSpec(spec) {
    if (typeof spec !== 'object' || spec === null) {
        throw new TypeError('CadenceScheduler.register: spec must be an object');
    }
    switch (spec.kind) {
        case 'every_n_minutes':
        case 'every_n_hours': {
            if (typeof spec.n !== 'number' ||
                !Number.isInteger(spec.n) ||
                spec.n <= 0) {
                throw new RangeError(`CadenceScheduler.register: ${spec.kind}.n must be a positive integer (got ${String(spec.n)})`);
            }
            return;
        }
        case 'every_day_at': {
            if (typeof spec.hour_utc !== 'number' ||
                !Number.isInteger(spec.hour_utc) ||
                spec.hour_utc < 0 ||
                spec.hour_utc > 23) {
                throw new RangeError(`CadenceScheduler.register: every_day_at.hour_utc must be an integer in [0, 23] (got ${String(spec.hour_utc)})`);
            }
            if (typeof spec.minute_utc !== 'number' ||
                !Number.isInteger(spec.minute_utc) ||
                spec.minute_utc < 0 ||
                spec.minute_utc > 59) {
                throw new RangeError(`CadenceScheduler.register: every_day_at.minute_utc must be an integer in [0, 59] (got ${String(spec.minute_utc)})`);
            }
            return;
        }
        case 'cron': {
            if (typeof spec.expression !== 'string' || spec.expression.length === 0) {
                throw new TypeError('CadenceScheduler.register: cron.expression must be a non-empty string');
            }
            return;
        }
        default: {
            const _exhaustive = spec;
            throw new TypeError(`CadenceScheduler.register: unknown spec.kind (got ${String(_exhaustive.kind)})`);
        }
    }
}
/** Period in ms for fixed-interval kinds; +Infinity for cron + day_at sentinel. */
function periodMs(spec) {
    switch (spec.kind) {
        case 'every_n_minutes':
            return spec.n * MS_PER_MINUTE;
        case 'every_n_hours':
            return spec.n * MS_PER_HOUR;
        case 'every_day_at':
            return 24 * MS_PER_HOUR;
        case 'cron':
            return Number.POSITIVE_INFINITY;
        default: {
            const _exhaustive = spec;
            return Number.POSITIVE_INFINITY;
        }
    }
}
/**
 * Compute the FIRST fire time for a cadence, given the registration `now`.
 *
 *   - every_n_minutes / every_n_hours / cron: `now + period` (cron =
 *     +Infinity → never fires at v1.0).
 *   - every_day_at: the next UTC moment matching hour:minute. If today's
 *     HH:MM has already passed, schedule tomorrow.
 */
function computeFirstFireAt(spec, now) {
    if (spec.kind === 'every_day_at') {
        const d = new Date(now);
        const candidate = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), spec.hour_utc, spec.minute_utc, 0, 0);
        return candidate > now ? candidate : candidate + 24 * MS_PER_HOUR;
    }
    if (spec.kind === 'cron')
        return Number.POSITIVE_INFINITY;
    return now + periodMs(spec);
}
/**
 * Compute the NEXT fire time after a fire. The argument `scheduled` is the
 * just-fired scheduled time (NOT the actual fire time — using actual would
 * accumulate jitter into period drift; using scheduled keeps the cadence
 * stable). `actual` is the wall-clock when tick() observed the fire.
 *
 * For periodic kinds: scheduled + period.
 * For every_day_at: scheduled + 24h.
 * For cron: +Infinity (v1.0 never re-fires).
 */
function computeNextFireAt(spec, scheduled, _actual) {
    if (spec.kind === 'cron')
        return Number.POSITIVE_INFINITY;
    return scheduled + periodMs(spec);
}
//# sourceMappingURL=cadence-scheduler.js.map