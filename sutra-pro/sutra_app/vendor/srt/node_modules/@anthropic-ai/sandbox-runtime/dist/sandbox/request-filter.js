/**
 * Request-level filter hook for the forward proxy.
 *
 * Library consumers supply a `filterRequest` callback via
 * `network.filterRequest`. It receives the parsed HTTP request (web-standard
 * `Request`) and returns a decision. Applies to plain HTTP through the proxy
 * and, when `tlsTerminate` is configured, to terminated HTTPS. The proxy
 * enforces the decision; the library does not bless any matching DSL.
 */
import { endRequestAfterResponse } from './emitted-connection.js';
import { METHODS, } from 'node:http';
import { isIP } from 'node:net';
import { PassThrough, Readable } from 'node:stream';
import { logForDebugging } from '../utils/debug.js';
import { isResolvedAddressDenied } from './resolved-address-guard.js';
import { sanitizeDenialReason } from './sandbox-violation-store.js';
export const BODYLESS_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
/** Methods whose response echoes the request; never forwarded. */
const ECHO_METHODS = new Set(['TRACE', 'TRACK']);
/**
 * User-facing reason when a filterRequest denial doesn't supply one. This
 * text reaches the sandboxed client (403 body) and the model
 * (<sandbox_violations>), so it names the policy, not the internal hook.
 */
export const DEFAULT_DENY_REASON = 'denied by sandbox policy';
/**
 * Destroy a denied client's request only after the 403 has flushed —
 * destroying the shared socket in the same tick can RST the response
 * away (observed on Node; the unread request body makes close send RST).
 */
function destroyAfterResponse(req, res) {
    if (res.destroyed) {
        req.destroy();
        return;
    }
    if (res.writableFinished) {
        endRequestAfterResponse(req);
        return;
    }
    res.once('finish', () => endRequestAfterResponse(req));
    res.once('close', () => {
        if (!res.writableFinished)
            req.destroy();
    });
}
/**
 * Build a `Request`, run the callback, and if denied write the 403 response
 * and return `null`. On allow, returns the body stream the caller must pipe
 * upstream — this is the original `IncomingMessage` when no tee was needed
 * (GET/HEAD/OPTIONS), or the upstream-side branch of the tee otherwise.
 * Callers must pipe the returned stream (not `req`) to the outbound request.
 *
 * For methods that carry a body, `req` is converted to a web stream and
 * `tee()`'d: one branch goes to the callback's `Request.body`, the other is
 * returned for the caller to forward. If the callback never reads its
 * branch, we cancel it after the decision so the tee does not buffer the
 * entire upload.
 */
export async function decideAndRespond(filterRequest, req, res, url, signal, onDeny, info, denyHeader, canSetHeaders = true) {
    const method = req.method ?? 'GET';
    let forCallback;
    let forUpstream = req;
    let shim;
    // Gate on a declared body, not just the method: a GET/HEAD/OPTIONS with
    // Content-Length or Transfer-Encoding is legal HTTP and its body must go
    // through the tee like any other — skipping it here would hide the body
    // from filterRequest AND (with transfer-encoding stripped as hop-by-hop)
    // let its decoded bytes be written raw after a complete-framed bodyless
    // request upstream: a request-smuggling primitive.
    // Truthiness, not presence: an empty Content-Length/Transfer-Encoding
    // value declares nothing and must not trigger teeing or re-framing.
    const declaresBody = Boolean(req.headers['content-length'] || req.headers['transfer-encoding']);
    const bodylessMethod = BODYLESS_METHODS.has(method);
    if (!bodylessMethod || declaresBody) {
        // Never hand toWeb a stream that can error: when its source errors,
        // the toWeb/tee/fromWeb bridge leaks the error as internal promise
        // rejections (and, under Bun, uncaught exceptions) that no userland
        // listener can catch. A client abort mid-body becomes a clean EOF on
        // the shim instead, and the abort is propagated by destroying the
        // upstream branch directly — a truncated body must never be forwarded
        // framed as complete (chunked framing would otherwise emit a valid
        // terminator; on the SigV4 path a truncated buffer would be signed).
        // The shim's own error listener covers the tee cancelling it while
        // the client is still piping.
        const teeSource = new PassThrough();
        shim = teeSource;
        teeSource.on('error', () => { });
        req.pipe(teeSource);
        const web = Readable.toWeb(teeSource);
        const [a, b] = web.tee();
        forCallback = a;
        forUpstream = Readable.fromWeb(b);
        const upstreamBranch = forUpstream;
        // The caller only wires its own 'error' handler after this function
        // resolves; a client abort during the filterRequest await must not
        // land on a listener-less stream.
        upstreamBranch.on('error', () => { });
        req.on('error', err => {
            teeSource.end();
            upstreamBranch.destroy(err);
        });
    }
    // TRACE (and TRACK, which some servers treat the same) asks the server
    // to echo the request back: forwarded with a credential the decision
    // attached, the echo would hand that credential to the client. Refused
    // here, before the callback is asked and before anything is dialled.
    // Node's and Bun's HTTP parsers reject TRACK as an unknown method (their
    // own 400) before this runs; it is listed for a parser that would not.
    if (ECHO_METHODS.has(method.toUpperCase())) {
        const reason = `the ${method} method is not forwarded`;
        onDeny?.(method, url, reason);
        deny(res, { action: 'deny', status: 405, reason, mark: 'method_refused' }, denyHeader);
        forCallback?.cancel().catch(() => { });
        endDeniedBody(req, res, forUpstream, shim);
        return null;
    }
    let webReq;
    try {
        // Fetch-spec Requests reject a body on GET/HEAD (Node throws; Bun is
        // lenient) — a GET with a declared body is still teed above so the
        // upstream leg stays framed, but the callback sees a bodyless Request.
        const callbackBody = forCallback && !bodylessMethod
            ? { body: forCallback, duplex: 'half' }
            : {};
        webReq = new Request(url, {
            method,
            headers: incomingHeaders(req),
            signal,
            ...callbackBody,
        });
    }
    catch (err) {
        // Malformed URL/headers from the client — deny rather than crash.
        const reason = `malformed request: ${err.message}`;
        onDeny?.(method, url, reason);
        deny(res, { action: 'deny', reason, mark: 'bad_request' }, denyHeader);
        forCallback?.cancel().catch(() => { });
        endDeniedBody(req, res, forUpstream, shim);
        return null;
    }
    let decision;
    try {
        decision = await filterRequest(webReq, forCallback && bodylessMethod
            ? { ...info, unshownBody: unshownBodyProbe(req, forCallback) }
            : info);
    }
    catch (err) {
        decision = {
            action: 'deny',
            reason: `sandbox policy check failed: ${err.message}`,
        };
    }
    const malformed = malformedDecisionReason(decision);
    if (malformed !== undefined) {
        decision = {
            action: 'deny',
            reason: `malformed filterRequest decision: ${malformed}`,
        };
    }
    // A caller that cannot apply header sets (cleartext, without the opt-in)
    // refuses the request: forwarding it without a header the decision relied
    // on would fail open, and the callback has no way to learn of the drop.
    if (!canSetHeaders &&
        decision.action === 'allow' &&
        (decision.setHeaders?.length ?? 0) > 0) {
        decision = {
            action: 'deny',
            reason: PLAINTEXT_HEADER_SET_REASON,
            mark: 'plaintext_header_set',
        };
    }
    // If the callback didn't read its branch, cancel it so tee() stops
    // buffering bytes nobody will consume. If it did, the tee already buffered
    // whatever was read; the upstream branch sees the same bytes.
    if (forCallback && !webReq.bodyUsed) {
        // cancel() rejects with the stream's stored error if it already
        // failed; that rejection must not escape.
        forCallback.cancel().catch(() => { });
    }
    if (decision.action === 'allow') {
        logForDebugging(`[request-filter] allow ${method} ${url}`);
        return { body: forUpstream, decision };
    }
    onDeny?.(method, url, decision.reason ?? DEFAULT_DENY_REASON);
    deny(res, decision, denyHeader);
    endDeniedBody(req, res, forUpstream, shim);
    return null;
}
/**
 * After a deny, stop the request: destroy a teed body's upstream branch at
 * once, and the request itself once the answer is out. The shim breaks the
 * old fromWeb→tee→toWeb cancel cascade that used to destroy req; without
 * this a denied client keeps uploading into a stalled pipe and holds the
 * connection open. Destroying req before the answer is flushed loses the
 * answer under Node (for a request without a body, req is what destroys
 * the socket).
 *
 * A teed body's bytes stop going to the shim at once and are dropped from
 * then on: the tee is cancelled, and a byte the shim passed on to its
 * closed web stream would throw (Bun: "Controller is already closed").
 */
function endDeniedBody(req, res, forUpstream, shim) {
    if (shim !== undefined) {
        req.unpipe(shim);
        shim.pause();
        req.resume();
    }
    if (forUpstream !== req)
        forUpstream.destroy();
    destroyAfterResponse(req, res);
}
/**
 * Whether a request whose body the callback's Request leaves out carries
 * any body bytes. A non-zero Content-Length answers at once; otherwise the
 * callback's branch of the tee is read, which holds decoded body bytes, so
 * empty reads are skipped and only the end of the body means "none".
 */
function unshownBodyProbe(req, branch) {
    let answer;
    const probe = async () => {
        if (!req.headers['transfer-encoding'] &&
            Number(req.headers['content-length']) > 0) {
            return true;
        }
        const reader = branch.getReader();
        try {
            for (;;) {
                const { done, value } = await reader.read();
                if (done)
                    return false;
                if (value.byteLength > 0)
                    return true;
            }
        }
        finally {
            reader.cancel().catch(() => { });
        }
    };
    return () => (answer ?? (answer = probe()));
}
const PLAINTEXT_HEADER_SET_REASON = 'the allow decision sets headers, and headers are not set on plain-HTTP ' +
    'requests unless plaintext header sets are enabled; nothing was forwarded';
// RFC 9110 token; the same set Node's own header-name check accepts.
const HEADER_NAME = /^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/;
/**
 * Why a decision cannot be applied as given, or undefined when it can. The
 * callback's return is only typed, not checked, and a decision that would
 * throw half-way through forwarding must deny instead.
 */
function malformedDecisionReason(decision) {
    if (typeof decision !== 'object' || decision === null)
        return 'not an object';
    const d = decision;
    if (d.action !== 'allow' && d.action !== 'deny')
        return 'unknown action';
    if (d.reason !== undefined && typeof d.reason !== 'string') {
        return 'reason is not a string';
    }
    if (d.status !== undefined && typeof d.status !== 'number') {
        return 'status is not a number';
    }
    if (d.mark !== undefined &&
        (typeof d.mark !== 'string' || !HEADER_NAME.test(d.mark))) {
        return 'mark is not a reason code';
    }
    if (d.action === 'deny')
        return undefined;
    if (d.onResponse !== undefined && typeof d.onResponse !== 'function') {
        return 'onResponse is not a function';
    }
    const removals = d.removeHeaders;
    if (removals !== undefined) {
        if (!Array.isArray(removals))
            return 'removeHeaders is not an array';
        for (const name of removals) {
            if (typeof name !== 'string' || !HEADER_NAME.test(name)) {
                return 'removeHeaders holds an invalid header name';
            }
        }
    }
    const sets = d.setHeaders;
    if (sets !== undefined) {
        if (!Array.isArray(sets))
            return 'setHeaders is not an array';
        for (const entry of sets) {
            if (!Array.isArray(entry) || entry.length !== 2) {
                return 'setHeaders holds an entry that is not a [name, value] pair';
            }
            const [name, value] = entry;
            if (typeof name !== 'string' || !HEADER_NAME.test(name)) {
                return 'setHeaders holds an invalid header name';
            }
            if (typeof value !== 'string' || !isValidHeaderValue(value)) {
                return 'setHeaders holds an invalid header value';
            }
        }
    }
    return undefined;
}
/**
 * A field value may carry HTAB but no other control character, and no
 * character above U+00FF (Node's HTTP client throws on those).
 */
function isValidHeaderValue(value) {
    for (let i = 0; i < value.length; i++) {
        const code = value.charCodeAt(i);
        if ((code < 0x20 && code !== 0x09) || code === 0x7f || code > 0xff) {
            return false;
        }
    }
    return true;
}
function deny(res, decision, denyHeader) {
    const s = decision.status;
    const status = s !== undefined && Number.isInteger(s) && s >= 400 && s <= 599 ? s : 403;
    respondDenied(res, decision.reason ?? DEFAULT_DENY_REASON, denyHeader !== undefined
        ? { name: denyHeader, value: decision.mark ?? 'denied' }
        : undefined, status);
}
/**
 * A request-target in origin form (path and query), normalized once: the
 * URL parser resolves dot segments and reads `%2e` as `.`, and a run of
 * leading slashes becomes one. Normalizing the result again changes
 * nothing, so an HTTP client that re-normalizes on the way out sends the
 * same bytes. Accepts origin form, an absolute http(s) URI (whose
 * authority is dropped; the caller names the host) and `*` for OPTIONS;
 * returns undefined for any other shape, which the caller refuses.
 */
export function normalizeRequestTarget(raw, method) {
    if (raw === '*')
        return method === 'OPTIONS' ? raw : undefined;
    let url;
    try {
        // The fixed prefix keeps an origin-form target in the path: a leading
        // `//` is never read as an authority.
        url = new URL(raw.startsWith('/') ? `http://origin.invalid${raw}` : raw);
    }
    catch {
        return undefined;
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:')
        return undefined;
    return `${url.pathname.replace(/^\/{2,}/, '/')}${url.search}`;
}
const MALFORMED_TARGET = 'malformed request-target';
const AMBIGUOUS_TARGET = 'ambiguous request-target: as spelled and normalized it names different ' +
    'paths (a dot segment, leading slashes or "\\"); nothing was forwarded ' +
    '(network.ambiguousRequestTarget in the sandbox\'s configuration is "refuse")';
const percentEncoded = (text) => Buffer.from(text).toString('hex').toUpperCase().replace(/../g, '%$&');
/**
 * Both forms of a request-target that a filterRequest judges: `spelled`, in
 * origin form as the client wrote it, and `normalized` (see
 * normalizeRequestTarget). It is `ambiguous` when the two can name different
 * resources, so that an upstream may act on another one than a policy
 * judged: a dot segment (`%2e` included), a run of leading slashes, or `\`
 * in the path. Not ambiguous, because every reader takes both forms for the
 * same resource: a character the URL parser escapes (which ones differs by
 * runtime), an empty query it drops, and the `/` an empty path becomes.
 *
 * `forwarded` is the form `mode` sends. There is none, and `refusal` says
 * why, for an ambiguous target unless `mode` picks a form, and in every mode
 * for:
 * - a shape normalizeRequestTarget refuses, an authority that ends elsewhere
 *   than the URL parser ends it, a space or a control character;
 * - bytes that are not UTF-8: a runtime that lets a byte outside ASCII
 *   through has decoded it, and has put U+FFFD for these, so what the client
 *   named is lost. (A U+FFFD of the client's own looks the same.)
 *
 * Bytes that are UTF-8 are spelled percent-encoded, which names the same
 * resource to every reader and is what an upstream's parser is sure to take.
 *
 * A `#` and what follows it are in neither form. A fragment is the client's
 * own and no part of a request-target, but some clients leave it in the
 * absolute form they send a proxy; upstreams differ in whether it ends the
 * path or belongs to it, so it is cut before anything is read, judged,
 * signed, reported or sent.
 */
export function readRequestTarget(raw, method, mode) {
    const target = raw.replace(/#.*/s, '');
    const ascii = target.replace(/[^\0-\x7f]+/g, percentEncoded);
    const normalized = normalizeRequestTarget(ascii, method);
    let spelled = ascii.replace(/^https?:\/\/[^/?#\\]+/i, '');
    if (spelled === '' || spelled.startsWith('?'))
        spelled = '/' + spelled;
    if (normalized === undefined || !/^(?:\*|\/[!-~]*)$/.test(spelled)) {
        return { refusal: MALFORMED_TARGET };
    }
    if (/[\ufffd\ud800-\udfff]/u.test(target)) {
        return {
            spelled,
            refusal: `${MALFORMED_TARGET}: it holds bytes that are not UTF-8, or U+FFFD`,
        };
    }
    const [a, b] = [spelled, normalized].map(t => t.replace(/["'<>^`{}]/g, percentEncoded));
    const ambiguous = a !== b && a !== b + '?';
    const forwarded = mode === 'normalize'
        ? normalized
        : mode === 'asSpelled' || !ambiguous
            ? spelled
            : undefined;
    return {
        spelled,
        normalized,
        ambiguous,
        forwarded,
        refusal: forwarded === undefined ? AMBIGUOUS_TARGET : undefined,
    };
}
/**
 * Refuse a request-target: 400 and a warn-level line. Returns the reason,
 * for the caller to report as it reports a denial.
 */
export function respondRefusedTarget(res, refusal = MALFORMED_TARGET, mark) {
    logForDebugging(`[proxy] ${refusal}`, { level: 'warn' });
    respondDenied(res, refusal, mark ??
        (refusal === AMBIGUOUS_TARGET ? 'ambiguous-request-target' : undefined), 400);
    return refusal;
}
/** How many bytes of a request-target the runtime's parser refused are reported. */
const MAX_REPORTED_TARGET_LENGTH = 200;
/**
 * Handle a server's 'clientError'. A request the runtime's own parser gave
 * up on, which no request handler gets to see, is refused: 400 with the
 * reason on the bare socket, which ends, and a warn-level line. Returns what
 * the caller is to report of it, as it reports a denial. Any other error (a
 * reset, a client that left) destroys the socket, with nothing to report.
 *
 * Nothing is written, and the socket is destroyed, where `mayAnswer` is
 * false (the caller's: a response to an earlier request is under way, and
 * these bytes would land inside it) or the socket takes no write. On a
 * socket that was ended nothing is done: bytes that follow a refused head
 * fail the parser again while the answer is on its way out, and that is one
 * refusal.
 *
 * The one thing read of the client's bytes is the request line, and only
 * where the parser stopped inside its target and the line is whole: the
 * method if the runtime knows it, and an origin-form target, cut, with
 * every byte outside printable ASCII percent-encoded.
 */
export function refuseUnparsedRequest(err, socket, mayAnswer, mark = DEFAULT_DENY_TAG) {
    const { code, rawPacket, bytesParsed } = err;
    if (typeof code !== 'string' ||
        !code.startsWith('HPE_') ||
        // The input ended in the middle of a message: the client left.
        code === 'HPE_INVALID_EOF_STATE') {
        socket.destroy();
        return undefined;
    }
    if (socket.writableEnded)
        return undefined;
    const refused = {
        method: '-',
        target: '',
        reason: `malformed request (${err.message})`,
    };
    if (code === 'HPE_INVALID_URL') {
        refused.reason = `${MALFORMED_TARGET}: percent-encode its bytes outside printable ASCII`;
        if (Buffer.isBuffer(rawPacket) && typeof bytesParsed === 'number') {
            const text = rawPacket.toString('latin1');
            const line = /([A-Z-]+) (\/[^ \r\n]*) HTTP\/1\.[01]\r?\n/y;
            line.lastIndex = text.slice(0, bytesParsed).lastIndexOf('\n') + 1;
            const [, method, target] = line.exec(text) ?? [];
            if (method !== undefined && METHODS.includes(method)) {
                refused.method = method;
                refused.target = target
                    .slice(0, MAX_REPORTED_TARGET_LENGTH)
                    .replace(/[^!-~]/g, c => `%${c.charCodeAt(0).toString(16).toUpperCase().padStart(2, '0')}`);
            }
        }
    }
    logForDebugging(`[proxy] ${refused.reason}`, { level: 'warn' });
    if (!mayAnswer || !socket.writable) {
        socket.destroy();
        return refused;
    }
    // The peer may reset while the answer flushes.
    socket.on('error', () => { });
    const [name, value] = denyMarkHeader(mark);
    socket.end('HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n' +
        `${name}: ${value}\r\nContent-Length: ${refused.reason.length + 1}\r\n` +
        `Connection: close\r\n\r\n${refused.reason}\n`);
    // Ended, and destroyed a second later: a body still on its way is read and
    // dropped meanwhile. Unread, it would turn the close into a reset, and the
    // reset would discard the answer.
    setTimeout(() => socket.destroy(), 1000).unref?.();
    return refused;
}
/**
 * A request-target as the client spelled it, for a proxy that forwards it
 * unchanged and lets its policy match it exactly: dot segments and
 * percent-escapes, encoded or not, are kept, so an unusual spelling of an
 * admitted path is simply not that path. Origin form only (`/` first, and
 * not `//` or `/\`), with no `#`, space, control byte or DEL; with
 * `absolute`, the path and query of an absolute http(s) URI, as spelled.
 * Any other shape (authority form, asterisk form, or absolute form where
 * origin form is required) is undefined, which the caller answers 400.
 */
export function requestTargetAsSpelled(raw, { absolute = false } = {}) {
    let target = raw;
    if (absolute) {
        const m = /^https?:\/\/[^/?#]*/i.exec(raw);
        if (!m)
            return undefined;
        target = raw.slice(m[0].length);
        if (target === '' || target.startsWith('?'))
            target = '/' + target;
    }
    if (!target.startsWith('/') || target.startsWith('//'))
        return undefined;
    if (target.startsWith('/\\'))
        return undefined;
    for (let i = 0; i < target.length; i++) {
        const c = target.charCodeAt(i);
        if (c <= 0x20 || c === 0x7f || c === 0x23)
            return undefined;
    }
    return target;
}
/**
 * A header name folded for comparison: lower case, with `_` and `.` read
 * as `-`. Upstreams differ in which separators they treat as equivalent,
 * so a removal must cover every spelling.
 */
export function foldHeaderName(name) {
    return name.toLowerCase().replace(/[_.]/g, '-');
}
const UNSETTABLE_HEADERS = new Set([
    'host',
    'connection',
    'keep-alive',
    'proxy-connection',
    'transfer-encoding',
    'te',
    'trailer',
    'upgrade',
    'content-length',
]);
/** Remove every header whose folded name is one of `names`, in place. */
export function removeHeadersFolded(headers, names) {
    const drop = new Set();
    for (const n of names)
        drop.add(foldHeaderName(n));
    if (drop.size === 0)
        return;
    for (const k of Object.keys(headers)) {
        if (drop.has(foldHeaderName(k)))
            delete headers[k];
    }
}
/**
 * Apply an allow decision's header edits to the headers about to be sent
 * upstream, in place: first remove every header whose folded name (see
 * foldHeaderName) is a removal or a name the decision sets, then add the
 * set values. Sets are grouped by folded name (`x-foo` and `x_foo` are one
 * header, emitted under the first spelling), and framing headers are
 * neither removed nor set.
 */
export function applyHeaderEdits(headers, decision) {
    // Grouped by folded name, emitted under the first spelling given.
    const sets = new Map();
    for (const [name, value] of decision.setHeaders ?? []) {
        const folded = foldHeaderName(name);
        if (UNSETTABLE_HEADERS.has(folded))
            continue;
        const entry = sets.get(folded) ?? { name: name.toLowerCase(), values: [] };
        if (!/[\r\n\0]/.test(value))
            entry.values.push(value);
        sets.set(folded, entry);
    }
    const removals = (decision.removeHeaders ?? []).filter(n => !UNSETTABLE_HEADERS.has(foldHeaderName(n)));
    removeHeadersFolded(headers, [...removals, ...sets.keys()]);
    for (const { name, values } of sets.values()) {
        if (values.length > 0) {
            headers[name] = values.length === 1 ? values[0] : values;
        }
    }
}
/** Call an allow decision's onResponse, containing its failures. */
export function notifyResponse(decision, status, headers) {
    if (!decision?.onResponse)
        return;
    const copy = {};
    for (const [name, value] of Object.entries(headers)) {
        copy[name] = Array.isArray(value) ? [...value] : value;
    }
    try {
        const returned = decision.onResponse(status, copy);
        if (isThenable(returned))
            returned.then(undefined, logResponseFailure);
    }
    catch (err) {
        logResponseFailure(err);
    }
}
function isThenable(value) {
    return (typeof value === 'object' &&
        value !== null &&
        typeof value.then === 'function');
}
function logResponseFailure(err) {
    logForDebugging(`[request-filter] onResponse failed: ${err?.message ?? String(err)}`, { level: 'error' });
}
/**
 * The Host header of a request as a list of its values, from the raw
 * header lines (a runtime keeps only the first of repeated Host headers in
 * `headers`).
 */
export function hostHeaderValues(rawHeaders) {
    const out = [];
    for (let i = 0; i + 1 < rawHeaders.length; i += 2) {
        if (rawHeaders[i].toLowerCase() === 'host')
            out.push(rawHeaders[i + 1]);
    }
    return out;
}
/**
 * Why a request's Host header, TLS server name or absolute-form authority
 * does not name the host and port it is being sent to, or undefined when
 * they agree.
 *
 * A server name must be the target's host, in any case. A Host header (or
 * the authority of an absolute-form request-target) names the target when
 * it is the target's host in any case, with the target's port after one
 * colon, or with no port when the target's port is the scheme's default,
 * and with brackets only around an IPv6 address; any other shape (an empty
 * value, a trailing colon or dot, brackets around a name) names no host.
 * More than one Host header is a mismatch; none is not (HTTP/1.1 parsers
 * already require one).
 */
export function hostMismatch(hostHeaders, serverName, target, requestTargetAuthority) {
    const want = target.hostname.toLowerCase();
    if (serverName !== undefined && serverName.toLowerCase() !== want) {
        return 'TLS server name does not match the request target';
    }
    if (requestTargetAuthority !== undefined &&
        !namesTarget(requestTargetAuthority, want, target)) {
        return 'request-target authority does not match the request target';
    }
    if (hostHeaders.length === 0)
        return undefined;
    if (hostHeaders.length > 1)
        return 'more than one Host header';
    if (!namesTarget(hostHeaders[0], want, target)) {
        return 'Host header does not match the request target';
    }
    return undefined;
}
function namesTarget(authority, want, target) {
    const parsed = hostAndPort(authority);
    if (parsed === undefined || parsed.host.toLowerCase() !== want)
        return false;
    return parsed.port === ''
        ? target.port === target.defaultPort
        : parsed.port === String(target.port);
}
/** A Host header's host and port ("" when none), or undefined for any other shape. */
function hostAndPort(h) {
    let host = h;
    let rest = '';
    if (h.startsWith('[')) {
        const end = h.indexOf(']');
        if (end < 0)
            return undefined;
        host = h.slice(1, end);
        rest = h.slice(end + 1);
        if (isIP(host) !== 6)
            return undefined;
    }
    else {
        const i = h.indexOf(':');
        if (i >= 0) {
            host = h.slice(0, i);
            rest = h.slice(i);
        }
        if (/[[\]]/.test(host))
            return undefined;
    }
    if (rest === '')
        return { host, port: '' };
    const port = rest.slice(1);
    if (rest[0] !== ':' || port === '' || /[[\]:]/.test(port))
        return undefined;
    return { host, port };
}
const DEFAULT_DENY_TAG = 'blocked-by-sandbox-runtime';
function denyMarkHeader(mark) {
    return typeof mark === 'string'
        ? ['X-Proxy-Error', mark]
        : [mark.name, mark.value];
}
export function rawDenied(reason, tag = DEFAULT_DENY_TAG, phrase = 'Forbidden') {
    const [name, value] = denyMarkHeader(tag);
    return (`HTTP/1.1 403 ${sanitizeDenialReason(String(phrase)).replace(/[^ -~]/gu, '?')}\r\n` +
        'Content-Type: text/plain\r\n' +
        `${name}: ${value}\r\n` +
        '\r\n' +
        reason);
}
/**
 * Write the proxy's standard policy-denial response: 403 with the reason
 * in the body, so the sandboxed client can tell a policy block from a
 * network failure. Shared by filterRequest denials and other in-proxy
 * policy decisions (e.g. SigV4 shapes that cannot be re-signed).
 */
export function respondDenied(res, reason, tag = DEFAULT_DENY_TAG, status = 403) {
    logForDebugging(`[proxy] deny: ${reason}`);
    if (res.headersSent || res.destroyed) {
        res.destroy();
        return;
    }
    const [name, value] = denyMarkHeader(tag);
    res.writeHead(status, {
        'Content-Type': 'text/plain',
        [name]: value,
    });
    // As bytes: a server may pass a string on to a socket whose default
    // encoding is not UTF-8 (see writeHeadsAsLatin1).
    res.end(Buffer.from(reason + '\n'));
}
/**
 * Answer a failed upstream leg: a resolved-address refusal is a policy
 * denial (403 with the reason); anything else is a 502, or a bare destroy
 * once headers are out.
 */
export function respondUpstreamError(res, err, denyHeader) {
    if (isResolvedAddressDenied(err)) {
        respondDenied(res, err.message, denyHeader !== undefined
            ? { name: denyHeader, value: 'address_not_allowed' }
            : undefined);
    }
    else if (!res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'text/plain' });
        res.end('Bad Gateway');
    }
    else {
        res.destroy();
    }
}
function incomingHeaders(req) {
    const h = new Headers();
    for (const [k, v] of Object.entries(req.headers)) {
        if (v === undefined)
            continue;
        if (Array.isArray(v)) {
            for (const vv of v)
                h.append(k, vv);
        }
        else {
            h.append(k, v);
        }
    }
    return h;
}
//# sourceMappingURL=request-filter.js.map