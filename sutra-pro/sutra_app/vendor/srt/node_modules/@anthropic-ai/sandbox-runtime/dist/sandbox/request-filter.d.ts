/**
 * Request-level filter hook for the forward proxy.
 *
 * Library consumers supply a `filterRequest` callback via
 * `network.filterRequest`. It receives the parsed HTTP request (web-standard
 * `Request`) and returns a decision. Applies to plain HTTP through the proxy
 * and, when `tlsTerminate` is configured, to terminated HTTPS. The proxy
 * enforces the decision; the library does not bless any matching DSL.
 */
import { type IncomingHttpHeaders, type IncomingMessage, type ServerResponse } from 'node:http';
import { type Duplex, Readable } from 'node:stream';
export type RequestDecision = {
    action: 'allow' | 'deny';
    /**
     * Human-readable reason. For denials this is surfaced to the sandboxed
     * client in the response body so the agent can tell a policy block from a
     * network failure.
     */
    reason?: string;
    /**
     * Deny only: the response status, 400 to 599. Anything else, or none,
     * answers 403.
     */
    status?: number;
    /**
     * Deny only: a short reason code for the refusal (an HTTP token, e.g.
     * `decider`). A proxy created with `denyHeader` sends it as that
     * header's value; `denied` when none is given. Otherwise it is unused.
     */
    mark?: string;
    /**
     * Allow only: headers to remove from the forwarded request. Names match
     * case-insensitively and with `-`, `_` and `.` treated as one character,
     * so `x-api-key` also removes `X_Api_Key` and `x.api.key`. Framing headers
     * (see setHeaders) are never removed.
     */
    removeHeaders?: string[];
    /**
     * Allow only: headers to set on the forwarded request, after
     * `removeHeaders`. A name given more than once gets every value, in
     * order; each name first removes every spelling of itself the client
     * sent. Framing headers (`host`, `content-length`, `transfer-encoding`,
     * `connection`, `upgrade`, `te`, `trailer`, `keep-alive`,
     * `proxy-connection`) are never set. A value holding a control character
     * other than tab, or a character above U+00FF, makes the whole decision
     * malformed and the request is denied. On the plain-HTTP path (`scheme`
     * is `'http'`) sets apply only when the proxy was created with
     * `plaintextHeaderSet`; without it an allow that carries any `setHeaders`
     * entry is refused with 403 rather than forwarded without them.
     */
    setHeaders?: Array<[string, string]>;
    /**
     * Allow only: called once with the upstream response's status and
     * headers (hop-by-hop headers removed), just before the response is
     * written to the client. It gets a copy of the headers, so it observes
     * and cannot change the response. It may be async: a throw, or a
     * rejection of the promise it returns, is logged and ignored, and the
     * response is not held for it.
     */
    onResponse?: (status: number, headers: IncomingHttpHeaders) => void;
};
/**
 * Called once per HTTP request that the proxy parses.
 *
 * - `request` is a web-standard `Request`: method, URL, headers, and a lazy
 *   `request.body` stream (one branch of a tee — reading it does not consume
 *   the bytes that get forwarded upstream). `request.signal` aborts when the
 *   client disconnects.
 * - **Throwing or rejecting denies the request.** This is the failure
 *   contract for a security boundary: a buggy policy fails closed. So does
 *   a decision that is not well-formed: an unknown action, a header name
 *   that is not an HTTP token, or a header value holding a control
 *   character other than tab or a character above U+00FF.
 */
export type FilterRequestCallback = (request: Request, info?: RequestInfo) => Promise<RequestDecision>;
/** What the proxy knows about a request beyond the Request itself. */
export type RequestInfo = {
    /**
     * How the proxy received the request: `'https'` on the TLS-terminated
     * path, `'http'` when it arrived in cleartext (an absolute `https://` URI
     * sent in cleartext included).
     */
    scheme?: 'http' | 'https';
    /** The TLS server name the client sent, on the TLS-terminated path. */
    sni?: string;
    /**
     * Set only for GET, HEAD and OPTIONS requests that declare a body, whose
     * Request is built without one: resolves true once the request is known
     * to carry body bytes (a non-zero Content-Length, or the first decoded
     * byte of a chunked body) and false when the body ends empty. A callback
     * that needs to have seen the whole request must refuse when it is true.
     */
    unshownBody?: () => Promise<boolean>;
    /**
     * Where the request goes: the CONNECT target on the TLS-terminated
     * path, or the absolute URI's host and port on the plain path, in the
     * canonical spelling the allowlist evaluated.
     */
    target?: {
        host: string;
        port: number;
    };
    /**
     * The request-target in origin form (path and query) as the client
     * spelled it, without a fragment, a byte outside ASCII percent-encoded.
     * These are the bytes forwarded upstream, unless the proxy was created with
     * `ambiguousRequestTarget: 'normalize'`. `request.url` is a parsed URL
     * and cannot hold them: its path has dot segments resolved already. (With
     * no filterRequest configured there is no hook to judge the target: plain
     * HTTP forwards the URL-parsed path and query, and the TLS-terminated
     * path forwards the client's bytes unchanged.)
     */
    requestTarget?: string;
    /**
     * The same target normalized (see normalizeRequestTarget): what is
     * forwarded under `'normalize'`, and one of the readings an upstream may
     * make of an ambiguous spelling. `/a\b/../c` is `/a/c` here, and `/c` to
     * an upstream that keeps the `\`.
     */
    normalizedRequestTarget?: string;
    /**
     * Whether the two forms can name different resources (see
     * readRequestTarget): what `'refuse'` refuses. They also differ, harmlessly,
     * by a character the URL parser escapes and by an empty query.
     */
    requestTargetIsAmbiguous?: boolean;
    /**
     * A copy of the client's header lines as received: name, value, name,
     * value, ... Some runtimes lower-case the names.
     */
    rawHeaders?: string[];
};
/**
 * Mutate the headers that will be sent upstream, in place.
 *
 * Runs after the allow/deny decision and hop-by-hop stripping, immediately
 * before the upstream request is built. `destHost` is the canonical
 * destination host (the CONNECT target on the TLS-terminated path, or the
 * absolute-URI host on the plain-HTTP path, after canonicalizeHost — the
 * spelling the allowlist evaluated) — never the client-supplied Host
 * header, which is spoofable.
 */
export type MutateForwardedHeaders = (headers: IncomingHttpHeaders, destHost: string) => void;
export declare const BODYLESS_METHODS: Set<string>;
/**
 * User-facing reason when a filterRequest denial doesn't supply one. This
 * text reaches the sandboxed client (403 body) and the model
 * (<sandbox_violations>), so it names the policy, not the internal hook.
 */
export declare const DEFAULT_DENY_REASON = "denied by sandbox policy";
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
export declare function decideAndRespond(filterRequest: FilterRequestCallback, req: IncomingMessage, res: ServerResponse, url: string, signal: AbortSignal, onDeny?: (method: string, url: string, reason: string) => void, info?: RequestInfo, denyHeader?: string, canSetHeaders?: boolean): Promise<{
    body: Readable;
    decision: RequestDecision;
} | null>;
/**
 * A request-target in origin form (path and query), normalized once: the
 * URL parser resolves dot segments and reads `%2e` as `.`, and a run of
 * leading slashes becomes one. Normalizing the result again changes
 * nothing, so an HTTP client that re-normalizes on the way out sends the
 * same bytes. Accepts origin form, an absolute http(s) URI (whose
 * authority is dropped; the caller names the host) and `*` for OPTIONS;
 * returns undefined for any other shape, which the caller refuses.
 */
export declare function normalizeRequestTarget(raw: string, method: string | undefined): string | undefined;
/** What a proxy with a filterRequest does with an ambiguous request-target. */
export type AmbiguousRequestTarget = 'refuse' | 'asSpelled' | 'normalize';
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
export declare function readRequestTarget(raw: string, method: string | undefined, mode?: AmbiguousRequestTarget): {
    spelled?: string;
    normalized?: string;
    ambiguous?: boolean;
    forwarded?: string;
    refusal?: string;
};
/**
 * Refuse a request-target: 400 and a warn-level line. Returns the reason,
 * for the caller to report as it reports a denial.
 */
export declare function respondRefusedTarget(res: ServerResponse, refusal?: string, mark?: DenyMark): string;
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
export declare function refuseUnparsedRequest(err: Error, socket: Duplex, mayAnswer: boolean, mark?: DenyMark): {
    method: string;
    target: string;
    reason: string;
} | undefined;
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
export declare function requestTargetAsSpelled(raw: string, { absolute }?: {
    absolute?: boolean;
}): string | undefined;
/**
 * A header name folded for comparison: lower case, with `_` and `.` read
 * as `-`. Upstreams differ in which separators they treat as equivalent,
 * so a removal must cover every spelling.
 */
export declare function foldHeaderName(name: string): string;
/** Remove every header whose folded name is one of `names`, in place. */
export declare function removeHeadersFolded(headers: IncomingHttpHeaders, names: Iterable<string>): void;
/**
 * Apply an allow decision's header edits to the headers about to be sent
 * upstream, in place: first remove every header whose folded name (see
 * foldHeaderName) is a removal or a name the decision sets, then add the
 * set values. Sets are grouped by folded name (`x-foo` and `x_foo` are one
 * header, emitted under the first spelling), and framing headers are
 * neither removed nor set.
 */
export declare function applyHeaderEdits(headers: IncomingHttpHeaders, decision: Pick<RequestDecision, 'removeHeaders' | 'setHeaders'>): void;
/** Call an allow decision's onResponse, containing its failures. */
export declare function notifyResponse(decision: RequestDecision | undefined, status: number, headers: IncomingHttpHeaders): void;
/**
 * The Host header of a request as a list of its values, from the raw
 * header lines (a runtime keeps only the first of repeated Host headers in
 * `headers`).
 */
export declare function hostHeaderValues(rawHeaders: string[]): string[];
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
export declare function hostMismatch(hostHeaders: string[], serverName: string | undefined, target: {
    hostname: string;
    port: number;
    defaultPort: number;
}, requestTargetAuthority?: string): string | undefined;
/**
 * The proxy's standard policy-denial response as raw bytes, for paths that
 * answer on a bare socket (CONNECT): 403 with an `X-Proxy-Error` tag and
 * the reason as the body. `phrase` is the status line's: of a refused CONNECT
 * that is the part clients show (the script in GIT_SSH_COMMAND among
 * them), not the body. It is cleaned and cut as a violation line's reason
 * is. What is not ASCII becomes `?`: many clients read a status line as
 * Latin-1, where UTF-8 shows as noise, C1 controls among it.
 */
/**
 * The header that marks a denial: `X-Proxy-Error: <tag>` for a tag, or a
 * caller's own header and value.
 */
export type DenyMark = string | {
    name: string;
    value: string;
};
export declare function rawDenied(reason: string, tag?: DenyMark, phrase?: string): string;
/**
 * Write the proxy's standard policy-denial response: 403 with the reason
 * in the body, so the sandboxed client can tell a policy block from a
 * network failure. Shared by filterRequest denials and other in-proxy
 * policy decisions (e.g. SigV4 shapes that cannot be re-signed).
 */
export declare function respondDenied(res: ServerResponse, reason: string, tag?: DenyMark, status?: number): void;
/**
 * Answer a failed upstream leg: a resolved-address refusal is a policy
 * denial (403 with the reason); anything else is a 502, or a bare destroy
 * once headers are out.
 */
export declare function respondUpstreamError(res: ServerResponse, err: Error, denyHeader?: string): void;
//# sourceMappingURL=request-filter.d.ts.map