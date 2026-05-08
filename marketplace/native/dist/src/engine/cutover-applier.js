/**
 * CutoverApplier — v1.3.0 W6 (final wave production hardening).
 *
 * DRY-RUN ONLY. The real apply-with-rollback path is DEFERRED to v1.x.1
 * per plan §6 + codex implicit advisory.
 *
 * What dryRunApplyCutover does:
 *   - Validates the input via validateCutoverContract.
 *   - Returns a CutoverPlan describing the parallel-canary cutover that
 *     WOULD happen: which engines participate, which invariants would be
 *     observed, which rollback gate would be evaluated, and how long the
 *     canary window would last.
 *   - Performs ZERO mutation. No filesystem writes, no router edits, no
 *     ledger appends.
 *
 * The plan output is a structured artifact callers can render, log, or
 * compare against the v1.x.1 actual-apply implementation when it ships.
 */
import { validateCutoverContract, isParseableDuration, } from './cutover-validator.js';
/**
 * Plan a cutover application without mutating anything. Returns the
 * CutoverPlan even when invalid — `valid=false` + `errors[]` populated —
 * so callers can render the same shape regardless of outcome.
 *
 * For `null` contracts (no cutover required), returns a degenerate plan
 * with empty mutations and valid=true.
 */
export function dryRunApplyCutover(contract, _opts = {}) {
    const validation = validateCutoverContract(contract);
    // null contract = no cutover; degenerate plan.
    if (validation.valid && contract === null) {
        return {
            source_engine: '',
            target_engine: '',
            canary_window: '',
            canary_window_seconds: null,
            behavior_invariants: [],
            rollback_gate: '',
            planned_mutations: [],
            mode: 'dry-run',
            valid: true,
            errors: [],
        };
    }
    // Invalid — return empty plan with errors. Plan shape preserved so callers
    // can render uniformly.
    if (!validation.valid) {
        return {
            source_engine: typeof contract?.source_engine === 'string'
                ? contract.source_engine
                : '',
            target_engine: typeof contract?.target_engine === 'string'
                ? contract.target_engine
                : '',
            canary_window: typeof contract?.canary_window === 'string'
                ? contract.canary_window
                : '',
            canary_window_seconds: null,
            behavior_invariants: [],
            rollback_gate: '',
            planned_mutations: [],
            mode: 'dry-run',
            valid: false,
            errors: validation.errors,
        };
    }
    // Valid contract — build the planned mutations.
    const c = contract;
    if (c === null) {
        // Defensive — should be caught by the null branch above.
        return {
            source_engine: '',
            target_engine: '',
            canary_window: '',
            canary_window_seconds: null,
            behavior_invariants: [],
            rollback_gate: '',
            planned_mutations: [],
            mode: 'dry-run',
            valid: true,
            errors: [],
        };
    }
    const planned = [
        {
            kind: 'arm_parallel_canary',
            target: 'router',
            description: `Mirror routed events to ${c.target_engine} alongside ${c.source_engine} for the canary window`,
            reversible: true,
        },
        {
            kind: 'register_invariant_observers',
            target: 'observer',
            description: `Install ${c.behavior_invariants.length} behavior invariant observer(s) over both engines`,
            reversible: true,
        },
        {
            kind: 'register_rollback_gate',
            target: 'observer',
            description: `Install rollback gate predicate "${c.rollback_gate}" — abort + rollback if true within window`,
            reversible: true,
        },
        {
            kind: 'open_canary_ledger_segment',
            target: 'ledger',
            description: `Open canary ledger segment for cutover ${c.source_engine}→${c.target_engine}`,
            reversible: true,
        },
        {
            kind: 'schedule_canary_window_close',
            target: 'router',
            description: `Schedule canary window close after ${c.canary_window} — promote ${c.target_engine} to primary if rollback_gate stayed false`,
            reversible: true,
        },
    ];
    return {
        source_engine: c.source_engine,
        target_engine: c.target_engine,
        canary_window: c.canary_window,
        canary_window_seconds: parseDurationSeconds(c.canary_window),
        behavior_invariants: c.behavior_invariants,
        rollback_gate: c.rollback_gate,
        planned_mutations: planned,
        mode: 'dry-run',
        valid: true,
        errors: [],
    };
}
/**
 * Parse a canary_window string into seconds. Returns null when unparseable
 * (which validateCutoverContract would have rejected anyway).
 */
function parseDurationSeconds(input) {
    if (!isParseableDuration(input))
        return null;
    const s = input.trim();
    if (/^\d+$/.test(s))
        return Number(s);
    const iso = /^P(?:T)?(\d+)([SMHD])$/i.exec(s);
    if (iso) {
        const n = Number(iso[1]);
        const unit = iso[2].toUpperCase();
        return scaleToSeconds(n, unit);
    }
    const short = /^(\d+)([smhd])$/.exec(s);
    if (short) {
        const n = Number(short[1]);
        const unit = short[2].toLowerCase();
        return scaleToSeconds(n, unit.toUpperCase());
    }
    return null;
}
function scaleToSeconds(n, unit) {
    switch (unit) {
        case 'S':
            return n;
        case 'M':
            return n * 60;
        case 'H':
            return n * 60 * 60;
        case 'D':
            return n * 24 * 60 * 60;
        default:
            return n;
    }
}
//# sourceMappingURL=cutover-applier.js.map