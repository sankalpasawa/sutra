/**
 * Sutra Connectors — Audit sink (LLD §2.5 + §4 audit-write-failure row).
 *
 * Invariants:
 *   - Append-only (no rewrites)
 *   - Redaction applied BEFORE serialization (no PII/secret ever touches disk)
 *   - Required fields validated at runtime BEFORE any disk write
 *   - Failure path: write to ${os.tmpdir()}/sutra-connector-audit-<pid>.jsonl
 *     and emit a single-line stderr beacon for grep-recovery
 */
import { promises as fs } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import * as crypto from 'node:crypto';
// -----------------------------------------------------------------------------
// Required AuditEvent fields — runtime validated before serialization.
// -----------------------------------------------------------------------------
const REQUIRED_FIELDS = [
    'ts',
    'clientId',
    'tier',
    'depth',
    'capability',
    'outcome',
    'sessionId',
    'redactedArgsHash',
];
const ALLOWED_OUTCOMES = new Set([
    'allowed',
    'blocked',
    'approved-after-gate',
    'error',
]);
// -----------------------------------------------------------------------------
// Redaction — supports top-level keys, dotted nested keys, and `[*]` wildcard.
// -----------------------------------------------------------------------------
const REDACTED_SENTINEL = '<REDACTED>';
function deepClone(value) {
    // structuredClone is available on Node 17+; safe for plain JSON-shaped data.
    // Fall back to JSON round-trip if unavailable.
    if (typeof globalThis.structuredClone === 'function') {
        return globalThis.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
}
/**
 * Apply a single redaction path against the working clone.
 * Path tokens are separated by '.'. A token of the form `name[*]` means
 * "descend into name (an array) and apply the rest of the path to every element".
 */
function applyRedactionPath(target, segments) {
    if (target === null || target === undefined)
        return;
    if (segments.length === 0)
        return;
    const [head, ...rest] = segments;
    // Detect `name[*]` wildcard — array iteration.
    const wildcardMatch = head.match(/^(.+)\[\*\]$/);
    if (wildcardMatch) {
        const arrayKey = wildcardMatch[1];
        if (typeof target !== 'object' || Array.isArray(target))
            return;
        const obj = target;
        const arr = obj[arrayKey];
        if (!Array.isArray(arr))
            return;
        if (rest.length === 0) {
            // Replace each element wholesale.
            for (let i = 0; i < arr.length; i++)
                arr[i] = REDACTED_SENTINEL;
        }
        else {
            for (const item of arr)
                applyRedactionPath(item, rest);
        }
        return;
    }
    if (typeof target !== 'object' || Array.isArray(target))
        return;
    const obj = target;
    if (rest.length === 0) {
        if (head in obj)
            obj[head] = REDACTED_SENTINEL;
        return;
    }
    if (head in obj) {
        applyRedactionPath(obj[head], rest);
    }
}
function redactArgs(rawArgs, redactPaths) {
    const clone = deepClone(rawArgs);
    for (const p of redactPaths) {
        const segments = p.split('.');
        applyRedactionPath(clone, segments);
    }
    return clone;
}
// -----------------------------------------------------------------------------
// Canonical JSON — keys sorted at every level, no whitespace.
// -----------------------------------------------------------------------------
function canonicalJSON(value) {
    if (value === null)
        return 'null';
    if (typeof value === 'number') {
        // JSON cannot represent NaN/Infinity; coerce to null per JSON spec.
        if (!Number.isFinite(value))
            return 'null';
        return JSON.stringify(value);
    }
    if (typeof value === 'string' || typeof value === 'boolean') {
        return JSON.stringify(value);
    }
    if (typeof value === 'undefined')
        return 'null';
    if (Array.isArray(value)) {
        return '[' + value.map((v) => canonicalJSON(v)).join(',') + ']';
    }
    if (typeof value === 'object') {
        const obj = value;
        const keys = Object.keys(obj).sort();
        const parts = [];
        for (const k of keys) {
            const v = obj[k];
            if (typeof v === 'undefined')
                continue; // skip undefined to mirror JSON.stringify
            parts.push(JSON.stringify(k) + ':' + canonicalJSON(v));
        }
        return '{' + parts.join(',') + '}';
    }
    // Fallback for symbols/functions — should not occur in audit args.
    return 'null';
}
function sha256Hex(input) {
    return crypto.createHash('sha256').update(input).digest('hex');
}
// -----------------------------------------------------------------------------
// Required-field validation
// -----------------------------------------------------------------------------
function validateEvent(event) {
    if (event === null || typeof event !== 'object') {
        throw new Error('AuditSink.append: event must be an object');
    }
    const e = event;
    for (const field of REQUIRED_FIELDS) {
        if (!(field in e)) {
            throw new Error(`AuditSink.append: missing required field '${String(field)}'`);
        }
        const v = e[field];
        if (v === undefined || v === null) {
            throw new Error(`AuditSink.append: required field '${String(field)}' is null/undefined`);
        }
    }
    if (typeof e.ts !== 'number' || !Number.isFinite(e.ts)) {
        throw new Error("AuditSink.append: 'ts' must be a finite number");
    }
    if (typeof e.clientId !== 'string' || e.clientId.length === 0) {
        throw new Error("AuditSink.append: 'clientId' must be a non-empty string");
    }
    if (typeof e.capability !== 'string' || e.capability.length === 0) {
        throw new Error("AuditSink.append: 'capability' must be a non-empty string");
    }
    if (typeof e.sessionId !== 'string' || e.sessionId.length === 0) {
        throw new Error("AuditSink.append: 'sessionId' must be a non-empty string");
    }
    if (typeof e.tier !== 'string') {
        throw new Error("AuditSink.append: 'tier' must be a string");
    }
    if (typeof e.depth !== 'number') {
        throw new Error("AuditSink.append: 'depth' must be a number");
    }
    if (typeof e.outcome !== 'string' ||
        !ALLOWED_OUTCOMES.has(e.outcome)) {
        throw new Error("AuditSink.append: 'outcome' must be one of allowed/blocked/approved-after-gate/error");
    }
    if (typeof e.redactedArgsHash !== 'string') {
        throw new Error("AuditSink.append: 'redactedArgsHash' must be a string");
    }
}
// -----------------------------------------------------------------------------
// Build the line that goes to disk — strips undefined optional fields,
// preserves a stable property order for human readability.
// -----------------------------------------------------------------------------
function buildLine(event) {
    const ordered = {
        ts: event.ts,
        clientId: event.clientId,
        tier: event.tier,
        depth: event.depth,
        capability: event.capability,
        outcome: event.outcome,
        sessionId: event.sessionId,
        redactedArgsHash: event.redactedArgsHash,
    };
    if (event.reason !== undefined)
        ordered.reason = event.reason;
    if (event.approvalToken !== undefined)
        ordered.approvalToken = event.approvalToken;
    if (event.errorClass !== undefined)
        ordered.errorClass = event.errorClass;
    return JSON.stringify(ordered) + '\n';
}
// -----------------------------------------------------------------------------
// AuditSink — append-only, redaction-by-construction, fallback on failure.
// -----------------------------------------------------------------------------
export class AuditSink {
    cfgPath;
    redactPaths;
    parentEnsured = false;
    /** Serializes appends so concurrent callers preserve write order. */
    writeChain = Promise.resolve();
    constructor(config) {
        if (!config || typeof config.path !== 'string' || config.path.length === 0) {
            throw new Error('AuditSink: config.path must be a non-empty string');
        }
        if (!Array.isArray(config.redactPaths)) {
            throw new Error('AuditSink: config.redactPaths must be an array');
        }
        this.cfgPath = config.path;
        this.redactPaths = config.redactPaths.slice();
    }
    async append(event, rawArgs) {
        // 1. Redact + hash up-front (before any disk touch). Sink is responsible for
        //    populating redactedArgsHash deterministically from rawArgs+redactPaths,
        //    overriding whatever the caller supplied (tests pass empty-string).
        const redacted = redactArgs(rawArgs ?? {}, this.redactPaths);
        const redactedArgsHash = sha256Hex(canonicalJSON(redacted));
        const sealed = {
            ...event,
            redactedArgsHash,
        };
        // 2. Validate required fields (throws synchronously via rejected Promise).
        validateEvent(sealed);
        // 3. Build the JSONL line (strip undefined optionals, stable order).
        const line = buildLine(sealed);
        // 4. Serialize against any in-flight writes so order is preserved AND
        //    return a Promise that mirrors the underlying write outcome.
        const next = this.writeChain.then(() => this.writeLine(line, sealed));
        // Keep the chain alive even if this write rejects — we never throw on
        // primary-write failure (we fall back). But guard with a catch anyway.
        this.writeChain = next.catch(() => {
            /* swallow; writeLine already handled fallback + beacon */
        });
        return next;
    }
    async close() {
        // Drain any in-flight writes; never reject — close is best-effort.
        try {
            await this.writeChain;
        }
        catch {
            /* already handled */
        }
    }
    // ---------------------------------------------------------------------------
    // Internals
    // ---------------------------------------------------------------------------
    async ensureParent() {
        if (this.parentEnsured)
            return;
        const parent = path.dirname(this.cfgPath);
        try {
            await fs.mkdir(parent, { recursive: true });
            this.parentEnsured = true;
        }
        catch {
            // Swallow — write attempt below will surface the real error and trigger
            // fallback. Don't mark parentEnsured so we can retry on next call if
            // transient.
        }
    }
    async writeLine(line, event) {
        await this.ensureParent();
        try {
            await fs.appendFile(this.cfgPath, line, { encoding: 'utf8' });
            return;
        }
        catch (err) {
            await this.fallbackWrite(line, event, err);
        }
    }
    async fallbackWrite(line, event, primaryErr) {
        const reason = errorCode(primaryErr);
        const fallbackPath = path.join(os.tmpdir(), `sutra-connector-audit-${process.pid}.jsonl`);
        // Beacon FIRST so even a fallback failure is surfaced.
        const beacon = `CONNECTOR-AUDIT-FALLBACK pid=${process.pid} ` +
            `primary=${this.cfgPath} fallback=${fallbackPath} ` +
            `reason=${reason} ts=${Math.floor(Date.now() / 1000)} ` +
            `clientId=${event.clientId} capability=${event.capability}\n`;
        try {
            process.stderr.write(beacon);
        }
        catch {
            /* stderr is best-effort */
        }
        try {
            await fs.appendFile(fallbackPath, line, { encoding: 'utf8' });
        }
        catch {
            // Last-resort: drop on the floor. Beacon already emitted; nothing else
            // we can do without throwing (LLD §4: failure path must not crash).
        }
    }
}
function errorCode(err) {
    if (err && typeof err === 'object') {
        const e = err;
        if (typeof e.code === 'string' && e.code.length > 0)
            return e.code;
        if (typeof e.message === 'string' && e.message.length > 0)
            return 'EERR';
    }
    return 'EUNKNOWN';
}
