/**
 * Parent/upstream HTTP proxy support.
 *
 * When SRT runs in an environment that requires an HTTP proxy for outbound
 * internet access (e.g. inside a VM on a host behind a corporate proxy),
 * SRT's own proxies must chain through that upstream rather than connecting
 * directly.
 *
 * This module provides:
 *   - config resolution (explicit config -> HTTP_PROXY/HTTPS_PROXY/NO_PROXY env)
 *   - NO_PROXY matching (hostname suffix + CIDR via net.BlockList). Follows
 *     golang.org/x/net/http/httpproxy semantics for suffix matching. Note:
 *     port-specific NO_PROXY entries (e.g. `host:8080`) are matched by host
 *     only; the port is ignored.
 *   - a generic CONNECT-tunnel helper that works over Unix socket, TCP, or TLS
 */
import type { LookupFunction, Socket } from 'node:net';
import type { ClientRequest, IncomingHttpHeaders, IncomingMessage, ServerResponse } from 'node:http';
import { BlockList } from 'node:net';
import { URL } from 'node:url';
import type { ParentProxyConfig } from './sandbox-config.js';
export interface ResolvedParentProxy {
    httpUrl?: URL;
    httpsUrl?: URL;
    noProxy: NoProxyRules;
}
interface NoProxyRules {
    all: boolean;
    suffixes: string[];
    cidr: BlockList;
}
/**
 * Resolve the parent proxy config, falling back to the SRT process's own
 * environment. Note: SRT later overwrites HTTP_PROXY etc. in the *sandboxed
 * child's* environment to point at itself — but process.env here reflects the
 * environment SRT itself was launched with, which is what we want.
 */
export declare function resolveParentProxy(cfg?: ParentProxyConfig): ResolvedParentProxy | undefined;
/**
 * Returns true if the given host should bypass the parent proxy and connect
 * directly. Always bypasses loopback.
 *
 * NB: the port is not consulted. NO_PROXY entries of the form `host:port` are
 * matched by host only (the port suffix is stripped during parsing).
 */
export declare function shouldBypassParentProxy(resolved: ResolvedParentProxy, host: string): boolean;
/**
 * Pick which parent proxy URL to use for a given destination.
 */
export declare function selectParentProxyUrl(resolved: ResolvedParentProxy, opts: {
    isHttps: boolean;
}): URL | undefined;
export interface ConnectTunnelOptions {
    /** Establish the transport to the proxy. */
    dial(): Socket;
    /** Fired when the transport is ready to write (e.g. 'connect'/'secureConnect'). */
    readyEvent: 'connect' | 'secureConnect';
    destHost: string;
    destPort: number;
    authHeader?: string;
    timeoutMs?: number;
}
/**
 * Generic CONNECT-tunnel: dial a proxy transport (unix/tcp/tls), send
 * `CONNECT host:port`, wait for a 2xx, and resolve with the tunnelled socket.
 * Validates destHost to prevent CRLF injection from untrusted callers.
 */
export declare function openConnectTunnel(opts: ConnectTunnelOptions): Promise<Socket>;
/**
 * Open a CONNECT tunnel through a parent HTTP(S) proxy specified by URL.
 * Thin wrapper around openConnectTunnel that dials TCP or TLS based on the
 * proxy URL scheme.
 */
export declare function connectViaParentProxy(proxyUrl: URL, destHost: string, destPort: number): Promise<Socket>;
export declare function proxyAuthHeader(proxyUrl: URL): string | undefined;
/**
 * Write an upstream response's status line and headers to the client.
 *
 * An upstream can answer with a head that `writeHead` refuses to send: a
 * status code outside 100-999 (`HTTP/1.1 099 x`), or a header name or value
 * with characters that are not allowed on the wire. `writeHead` throws
 * synchronously, and from inside a response callback that exception would be
 * uncaught and end the proxy process. Such a response is answered with
 * `502 Bad Gateway` instead: nothing from the upstream head or body is
 * relayed, and the upstream connection is closed.
 *
 * `headers` is what to send in place of the upstream's own headers with the
 * hop-by-hop ones removed, for a caller that has filtered them further.
 *
 * Returns true when the head was written and the body should be piped,
 * false when the response was replaced by the 502.
 */
export declare function relayResponseHead(res: ServerResponse, upstreamRes: IncomingMessage, headers?: IncomingHttpHeaders): boolean;
/**
 * Calls `fail` for an error of a forwarded request, unless its answer has
 * arrived whole by then. An upstream that sends more than the Content-Length
 * it declared (one that counts characters for bytes) has those bytes taken for
 * the start of a next answer, which is an error of the request: it comes after
 * the answer is complete and before that has been read. The answer is good,
 * and a client that asks the upstream itself takes it. The runtime has closed
 * the connection, so nothing that follows on it is read.
 */
export declare function onUpstreamError(upstream: ClientRequest, fail: (err: Error) => void): void;
/**
 * Strip hop-by-hop and proxy-specific headers before forwarding upstream.
 * Also strips any headers named in the incoming `Connection` header, per
 * RFC 9110 §7.6.1. With `folded`, a name also matches in any spelling of
 * `-`, `_` and `.` (`Proxy_Authorization`, `keep.alive`), for upstreams
 * that read those separators as one.
 */
export declare function stripHopByHop(h: IncomingHttpHeaders, { folded }?: {
    folded?: boolean;
}): IncomingHttpHeaders;
/** Remove surrounding square brackets from an IPv6 literal. */
export declare function stripBrackets(host: string): string;
/** Redact userinfo from a URL for safe logging. */
export declare function redactUrl(u: URL | undefined): string;
/**
 * Hostname validation: accepts DNS names and IP literals (without zone IDs).
 * Primary purpose is to block control characters (CRLF injection, null-byte
 * DNS truncation) and zone-identifier allowlist bypasses from reaching the
 * wire or the allowlist matcher.
 *
 * IPv6 zone IDs (`fe80::1%eth0`) are rejected because `isIP` accepts a very
 * permissive zone charset including dots — `::ffff:1.2.3.4%x.allowed.com`
 * would pass `isIP`, pass a `.endsWith('.allowed.com')` wildcard check, and
 * then connect to 1.2.3.4 when the OS discards the bogus scope.
 */
export declare function isValidHost(h: string): boolean;
/**
 * Canonicalize a host string via the WHATWG URL parser so that string
 * comparisons in the allowlist agree with what `net.connect()`/`getaddrinfo()`
 * will actually dial. This normalizes:
 *   - inet_aton shorthand (`127.1` → `127.0.0.1`, `2130706433` → `127.0.0.1`)
 *   - hex/octal octets (`0x7f.0.0.1` → `127.0.0.1`)
 *   - IPv6 compression (`0:0:0:0:0:0:0:1` → `::1`)
 *   - trailing dots, case, brackets
 *
 * Returns undefined if the input is not a valid URL host.
 */
export declare function canonicalizeHost(h: string): string | undefined;
/** Per-dial name resolution the proxies are handed: the guard's `lookup` for `port`, refusals recorded. */
export type DirectLookup = (port: number, encodedCommand?: string) => LookupFunction;
/** `host[:port]` as it belongs in a Host header / URL authority: IPv6 bracketed, the default port elided. */
export declare function formatAuthority(host: string, port: number, defaultPort: number): string;
export interface DirectRequestOptions {
    host: string;
    port: number;
    servername?: string;
    agent: false;
}
/**
 * Connection options for an `http(s).request` to `host:port` over the direct
 * route. The name is dialed exactly as a tunnel would be ({@link dialDirect}:
 * the guard's `lookup`, the connect timeout, the runtime's address-family
 * fallback), the address that answered is kept and that connection released;
 * the request then goes to the literal, with the name in SNI (callers keep it
 * in Host). So the vetted address is the one requested and `lookup` never
 * reaches the HTTP client: Bun's node:http client up to 1.3.x resolves through
 * a custom `lookup` but then drops or repeats a streamed request body, and
 * ignores `createConnection` (oven-sh/bun#7471), so the vetted socket cannot
 * simply be adopted. Bun 1.4 rewrote that client (oven-sh/bun#31587); once it
 * is the floor, hand the request the dialed socket and drop the second connect.
 * No agent: the global pool is shared with the embedding process (and Bun
 * caches the first request's `ca` on it), and the vetting dial runs per request
 * anyway. Without a `lookup`, or for an IP literal, the host is used as given.
 */
export declare function directRequestOptions(host: string, port: number, lookup: LookupFunction | undefined, tls: boolean): Promise<DirectRequestOptions>;
/**
 * Dial `host:port` directly with a bounded timeout. Shared by the HTTP and
 * SOCKS direct-connect paths so they get the same timeout behaviour as the
 * CONNECT-tunnelled paths. `lookup` is the resolved-address guard's (see
 * resolved-address-guard.ts); the runtime dials what it returns. It is a
 * required argument so no direct dial omits it by accident — pass
 * `undefined` explicitly to use the runtime's resolver unguarded.
 */
export declare function dialDirect(host: string, port: number, lookup: LookupFunction | undefined, timeoutMs?: number): Promise<Socket>;
export {};
//# sourceMappingURL=parent-proxy.d.ts.map