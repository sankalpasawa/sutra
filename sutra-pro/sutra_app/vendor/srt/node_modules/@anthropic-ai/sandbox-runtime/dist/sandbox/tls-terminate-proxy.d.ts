/**
 * In-process TLS termination for HTTPS traffic through the forward proxy.
 *
 * When a MitmCA is configured, the forward proxy hands CONNECT requests here
 * instead of opening an opaque byte tunnel. We terminate the client's TLS
 * with a per-host leaf cert (see mitm-leaf.ts), parse the decrypted stream
 * as HTTP/1.1, and re-issue each request upstream over a real TLS
 * connection. The optional `filterRequest` callback runs on each parsed
 * request before it is forwarded.
 */
import type { Server } from 'node:http';
import type { LookupFunction } from 'node:net';
import { TLSSocket } from 'node:tls';
import type { TLSSocketOptions } from 'node:tls';
import { Duplex } from 'node:stream';
import type { Writable } from 'node:stream';
import { type ByteBudget } from './emitted-connection.js';
import type { MitmCA } from './mitm-ca.js';
import { type AmbiguousRequestTarget, type FilterRequestCallback, type MutateForwardedHeaders } from './request-filter.js';
import { type GetBodySubstitutions } from './body-substitution.js';
import type { PlanSigv4 } from './credential-aws-pairs.js';
/**
 * Upper bound on the request body the proxy will buffer to recompute a
 * literal SigV4 body hash. The signature must cover the exact bytes sent
 * upstream, so buffering is unavoidable for that shape — but without a
 * cap a sandboxed client could pin arbitrary host memory with one large
 * signed upload (awslabs/aws-sigv4-proxy buffers with no limit; we fail
 * closed instead). Bodies over the cap are denied with a 403; clients
 * with larger payloads should sign UNSIGNED-PAYLOAD, which streams.
 */
export declare const MAX_SIGV4_RESIGN_BODY_BYTES: number;
/**
 * True if `buf` starts with a TLS Handshake record header.
 *
 * Three bytes: content type 0x16 (Handshake) + legacy_record_version
 * 0x03,0x00–0x03. RFC 8446 §5.1 froze the record-layer version (TLS 1.3+
 * negotiate via the supported_versions extension, the wire header stays
 * ≤0x0303), so this holds for current and future TLS. Same predicate as
 * mitmproxy `starts_like_tls_record`; nginx `ssl_preread` routes on byte 0
 * alone and HAProxy `req.ssl_hello_type` reads 9 bytes to also extract the
 * handshake type — 3 is the established middle ground for "is this TLS".
 *
 * Routing heuristic, not a security check: a non-TLS stream that happens to
 * start 16 03 0x is handed to the TLS server, which then rejects it properly.
 */
export declare function looksLikeClientHello(buf: Buffer): boolean;
/**
 * Wait for the client's first post-CONNECT bytes and report whether they look
 * like a TLS ClientHello. The caller must already have written the
 * `200 Connection Established` line — clients don't send until they see it.
 *
 * Any bytes consumed here are returned in `.head` so the caller can forward
 * them to whichever downstream (terminate or opaque tunnel) it picks. The
 * socket is left paused so further bytes buffer until the downstream
 * `pipe()` resumes it.
 */
export declare function peekForClientHello(socket: Duplex, head: Buffer): Promise<{
    isTLS: boolean;
    head: Buffer;
}>;
/**
 * Start the server side of TLS on a tunnel's own socket, in this process:
 * no listener, so no other process can reach the tunnel's plaintext side.
 * Under Node the TLS socket runs on the socket itself. Under Bun it runs on
 * a duplex over it: Bun's TLS socket on a net.Socket leaves every byte it
 * reads in that socket's own buffer too, which grows by the whole upload.
 * `outbound` is the stream whose write queue holds what is on its way to
 * the client.
 *
 * @internal Exported for its test.
 */
export declare function serverTlsOn(socket: Duplex, head: Buffer, options: TLSSocketOptions, onClosed: (how: string) => void): {
    tls: TLSSocket;
    outbound: Writable;
};
/** How long a tunnel may stay as it is before boundTunnel closes it. */
export type TunnelTimeouts = {
    /** From the ClientHello to the first request's whole head. */
    firstRequestMs: number;
    /** What `Keep-Alive: timeout` says: from a response to the next request. */
    keepAliveMs: number;
    /** How much later than it says an idle tunnel is ended, for a client that takes it at its word. */
    keepAliveMarginMs: number;
    /** With a request or a response under way that does not move. */
    stalledMs: number;
};
export declare const TUNNEL_TIMEOUTS: TunnelTimeouts;
export type TerminateTarget = {
    /**
     * Canonical (see canonicalizeHost) CONNECT target: what the allowlist
     * evaluated. Used verbatim for the minted leaf, the filterRequest URL,
     * the credential hooks' destHost, and the upstream host/SNI, so all of
     * them agree with the policy decision regardless of how the client
     * spelled the name.
     */
    hostname: string;
    port: number;
    /**
     * Additional trusted CA(s) for the proxy's outbound TLS leg. Unset → system
     * roots + NODE_EXTRA_CA_CERTS. Primarily a test seam (NODE_EXTRA_CA_CERTS
     * is read at process start, so tests can't set it from inside the suite).
     */
    upstreamCA?: string | Buffer | Array<string | Buffer>;
    /** Upstream-leg name resolution, already bound for this target (see HttpProxyServerOptions.lookupFor). */
    lookup?: LookupFunction;
    /**
     * Called when filterRequest denies a parsed request, with the verified
     * method/URL and the decision reason. Carried on the target so the
     * per-connection request handler (which closes over `target`) can reach
     * it without an extra parameter on every layer.
     */
    onFilterRequestDeny?: (method: string, url: string, reason: string) => void;
    /** Response headers removed before the response reaches the client. */
    stripResponseHeaders?: string[];
    /** Answer 421 when the Host header or TLS server name is not the target. */
    requireHostMatch?: boolean;
    /** The largest request head parsed in the tunnel; past it, 400 (see HttpProxyServerOptions.maxHeaderSize). */
    maxHeaderSize?: number;
    /** Drop hop-by-hop headers in any separator spelling (see HttpProxyServerOptions.foldHopByHop). */
    foldHopByHop?: boolean;
    /** The header that marks the proxy's own refusals (see HttpProxyServerOptions.denyHeader). */
    denyHeader?: string;
    /** Forward the request-target as spelled (see HttpProxyServerOptions.requestTargetAsSpelled). */
    requestTargetAsSpelled?: boolean;
    /** What becomes of an ambiguous request-target (see HttpProxyServerOptions.ambiguousRequestTarget). */
    ambiguousRequestTarget?: AmbiguousRequestTarget;
    /** The TLS server name the client sent (set by terminateAndForward). */
    clientServerName?: string;
    /** The ClientHello carries a server name that could not be read (see serverNameFromClientHello). */
    clientServerNameUnreadable?: boolean;
    /** Called once the tunnel's TLS handshake is done. */
    onEstablished?: () => void;
    /** Given a way to ask, at any later time, whether the tunnel's TLS handshake is done. */
    onHandshakeProbe?: (isDone: () => boolean) => void;
    /** Shared across a proxy's tunnels: bytes they may hold for slow parties (see ByteBudget). */
    byteBudget?: ByteBudget;
    /** In place of TUNNEL_TIMEOUTS (see HttpProxyServerOptions.tunnelTimeouts). */
    timeouts?: Partial<TunnelTimeouts>;
};
/**
 * Terminate the client's TLS on `socket`, parse the decrypted HTTP/1.1
 * stream, and forward each request to `target` over an upstream TLS
 * connection kept alive for the life of the client's connection (see
 * {@link createUpstreamLeg}).
 *
 * Preconditions: the caller has already validated `target` against the
 * domain allowlist; this function does not re-check it.
 *
 * Implementation: the TLS runs in this process on the tunnel's own socket
 * (serverTlsOn), and the decrypted connection is handed with
 * `emit('connection')` to an http.Server that never listens, so nothing
 * another process can connect to exists. A server per tunnel lets the
 * request handler close over `target` (which carries the originally-
 * requested host:port) without socket-keyed lookups.
 */
export declare function terminateAndForward(ca: MitmCA, filterRequest: FilterRequestCallback | undefined, mutateHeaders: MutateForwardedHeaders | undefined, getBodySubstitutions: GetBodySubstitutions | undefined, socket: Duplex, head: Buffer, target: TerminateTarget, planSigv4?: PlanSigv4, maxSigv4BodyBytes?: number): void;
/**
 * Close a tunnel that would otherwise stay open, and hold its slot, for as
 * long as its client or its upstream leaves it so. Its server never listens,
 * so of a server's connection timeouts the runtime applies keepAliveTimeout
 * alone (Node) or none (Bun).
 *
 * - Idle, that is no response owed (no request yet, between two, part of a
 *   head) and nothing queued for the client: ended with close_notify and a
 *   FIN, and destroyed if it is still there, and idle, as long again.
 * - Under way, that is a request not all in, the tunnel paused for an
 *   upstream that takes no more of one (so that not even its client's
 *   leaving is seen), or bytes queued for a client: destroyed once nothing
 *   has moved for `stalledMs`. A client that goes on reading loses nothing.
 *   That it reads is seen when the kernel takes more, which it does once a
 *   good part of its send buffer is free: up to a megabyte or two at a time.
 *
 * A whole request that waits for its response is left alone: the tunnel is
 * read meanwhile, so it closes when its client does.
 *
 * @internal Exported for its test.
 */
export declare function boundTunnel(inner: Server, tls: TLSSocket, outbound: Writable, socket: Duplex, { firstRequestMs, keepAliveMs, keepAliveMarginMs, stalledMs }: TunnelTimeouts, handshakeDone: () => boolean): void;
/** The server name a ClientHello carries: none, a plain DNS name, or one that cannot be read. */
export type ServerName = {
    kind: 'absent';
} | {
    kind: 'name';
    name: string;
} | {
    kind: 'unreadable';
};
/**
 * The server name a TLS ClientHello record carries (the server_name
 * extension's host_name), lower-cased.
 *
 * `unreadable` whenever a name may be there but cannot be taken as a plain
 * DNS name: the extension is malformed, lists more than one name, or names
 * something other than a host; the name is empty, too long, not ASCII
 * letters, digits, - and . in non-empty labels, or ends in a dot; or the
 * record ends (a ClientHello split across records) before the extensions
 * have all been read. `absent` only when every extension was read and none
 * is server_name.
 */
export declare function serverNameFromClientHello(record: Buffer): ServerName;
/**
 * Close a socket once what is written to it has gone out and the client
 * has seen it: end it, and once the writes are flushed, destroy it when
 * the client ends its side, or after a grace period. Until then what the
 * client sends is read and dropped, since unread input when the socket
 * closes turns the close into a reset, and a reset discards what the
 * client has not read yet. A client that has not taken it all in
 * `stalledMs` is cut: what is queued leaves the queue all at once, so one
 * that reads slowly cannot be told from one that has stopped.
 */
export declare function closeAfterFlush(socket: Duplex, done: (how: string) => void, stalledMs?: number): void;
//# sourceMappingURL=tls-terminate-proxy.d.ts.map