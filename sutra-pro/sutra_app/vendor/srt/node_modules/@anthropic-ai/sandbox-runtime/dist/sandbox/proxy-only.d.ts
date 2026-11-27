/**
 * Proxy-only mode: SRT's HTTP proxy with no sandboxed child, for a host
 * that runs the workload elsewhere (a VM, a container) and points it at
 * this proxy.
 *
 * - Serves a listening socket the host hands in as an inherited fd (the
 *   host binds it and owns its path), or a loopback port for tests. A
 *   net.Server accepts on it and passes each connection to the HTTP proxy
 *   server, so the runtime only needs net-level listen-on-fd support.
 * - Every request is decided by an external decider (decider-client.ts).
 *   There is no other policy source: the host allowlist comes from the
 *   decider's hello, and no request is forwarded without an allow verdict.
 * - Only TLS-terminated or plain-HTTP requests are served: CONNECTs that
 *   cannot be terminated are refused, so nothing bypasses the decider.
 * - A lifeline stream (the read end of a pipe the host holds) ending
 *   shuts the proxy down, as does the decider's stream ending.
 */
import { type Server as NetServer } from 'node:net';
import type { Server } from 'node:http';
import { Readable, Writable } from 'node:stream';
import { type CredentialPlacement, type Decider } from './decider-client.js';
/** The largest request head proxy-only mode parses (see maxHeaderSize). */
export declare const REQUEST_HEAD_LIMIT: number;
/** Private and shared address space a proxy-only upstream dial never reaches by name. */
export declare const DEFAULT_DENIED_RESOLVED_ADDRESSES: string[];
/**
 * Where an allow's credential goes when its placement isn't configured:
 * `Authorization: Bearer <value>`, except that a credential of class
 * "github" sent to github.com's git transport goes as HTTP Basic with the
 * user "x-access-token", as that transport expects.
 */
export declare const DEFAULT_CREDENTIAL_PLACEMENTS: CredentialPlacement[];
/**
 * Where the proxy accepts connections: an inherited listening socket
 * (`fd`), or a loopback address it binds itself (tests and development).
 */
export type ProxyListen = {
    fd: number;
} | {
    host: string;
    port: number;
};
export type ProxyOnlyOptions = {
    listen: ProxyListen;
    /** The decider's streams: required, the proxy forwards nothing without one. */
    decider: {
        input: Readable;
        output: Writable;
    };
    deciderTimeoutMs?: number;
    /** CA (PEM private key and certificate) for TLS termination. Without it, every CONNECT is refused. */
    caPem?: string;
    /** Stream whose end (or error) shuts the proxy down. */
    lifeline?: Readable;
    stripResponseHeaders?: string[];
    deniedResolvedAddresses?: string[];
    /** Let allow verdicts set headers on plain-HTTP requests (cleartext). Default off. */
    plaintextHeaderSet?: boolean;
    /** Where credential classes' values go (first match wins; default Bearer). */
    credentialPlacements?: CredentialPlacement[];
    /** Upstream CA override for the terminated leg. Test seam. */
    upstreamCA?: string;
    /** Called once when the proxy has shut down; `why` names the cause. */
    onClosed?: (why: string) => void;
};
export type ProxyOnly = {
    /** The HTTP proxy server. It never listens itself; `listener` feeds it. */
    server: Server;
    /** The net.Server accepting on the handed fd (or loopback address). */
    listener: NetServer;
    decider: Decider;
    /** Resolves once the decider's hello is in and the listener is serving. */
    ready: Promise<void>;
    close(why?: string): Promise<void>;
};
export declare function isBunRuntime(): boolean;
export declare function startProxyOnly(opts: ProxyOnlyOptions): ProxyOnly;
/** Read a whole PEM from an inherited fd (a pipe the host closes after writing). */
export declare function readPemFromFd(fd: number): string;
/**
 * Streams over an inherited fd (a pipe or a socket).
 *
 * Node: a net.Socket on the fd, which libuv drives non-blockingly. An
 * fs stream would park a threadpool thread in read(), and process.exit()
 * then waits for that read to return, so the proxy could not exit while
 * the peer keeps the fd open.
 * Bun: the runtime's own file streams, which poll the fd as Node's sockets
 * do. Bun's net.Socket({fd}) does not read or write an inherited fd, and an
 * fs stream parks a thread-pool thread in each blocking read(): with the
 * decider and the lifeline both waiting, a machine with one or two CPUs has
 * no thread left to write the next frame to the decider, and every request
 * times out. The writer is opened on first write, so an fd used only for
 * input (the lifeline) gets none.
 */
export declare function openFdStreams(fd: number): {
    input: Readable;
    output: Writable;
};
//# sourceMappingURL=proxy-only.d.ts.map