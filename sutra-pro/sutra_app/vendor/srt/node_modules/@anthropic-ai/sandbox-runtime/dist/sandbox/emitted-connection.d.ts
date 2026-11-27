/**
 * Workarounds for a runtime whose http.Server, serving a connection handed
 * to it with emit('connection') (Bun's), falls short of Node's server.
 */
import { type IncomingMessage } from 'node:http';
import type { Socket } from 'node:net';
/** Whether this is Bun, whose http.Server these workarounds are for. */
export declare function runsOnBun(): boolean;
/**
 * Whether this runtime's http.Server serves a connection handed to it with
 * emit('connection'): Node's and Bun's from 1.4 do, and such a server has
 * a 'connection' listener of its own. TLS termination in this process
 * hands each tunnel's decrypted connection to one.
 */
export declare function servesEmittedConnections(): boolean;
/**
 * @internal Test seam: answer servesEmittedConnections with `probe` in
 * place of the runtime's own answer (undefined restores it). Not exported
 * from the package.
 */
export declare function overrideEmittedConnectionProbe(probe: (() => boolean) | undefined): void;
/**
 * Throw where TLS termination is asked for and this runtime cannot do it
 * in-process (Bun before 1.4, see servesEmittedConnections). Called before
 * anything is started: without it, every tunnel to be terminated would be
 * answered 200 and then closed.
 */
export declare function assertTlsTerminationSupported(): void;
/**
 * The HTTP parser hands a request's head over in batches when it has many
 * header lines (every 31 in Node's and Bun's), calling onHeaders for each
 * and then onHeadersComplete with no headers and no URL of its own. Bun's
 * server for an emitted connection installs no onHeaders, so all but the
 * last batch, the request target among them, would be lost. Where the
 * parser on the socket has no onHeaders, collect the batches as Node's
 * server does and hand them to onHeadersComplete.
 *
 * The parser reports a chunked request's trailers through onHeaders too
 * (with the request's own target again), after the body and before
 * onMessageComplete. Those are not a batch of the next request's head:
 * what is held when a message completes is dropped, as Node's server
 * clears its own, so a request's trailers and target never become part of
 * the request that follows it on the connection. Where the parser has no
 * onMessageComplete to tell the two apart, nothing is installed.
 */
export declare function keepFlushedHeaderBatches(sock: Socket): void;
/**
 * A header string holds one char per byte, as the HTTP parser read it from
 * the upstream, and Node's server names latin1 when it writes a response's
 * head. Bun's server for an emitted connection names no encoding, so the
 * socket's default applies: as UTF-8, every header byte from 0x80 up would
 * reach the client as two. So latin1 is made the default of a socket about
 * to be emitted. Anything else written to it with no encoding named has to
 * be bytes or ASCII (see respondDenied).
 */
export declare function writeHeadsAsLatin1(sock: Socket): void;
/**
 * Bytes a proxy's connections together may hold for slow parties (request
 * bodies waiting for an upstream, responses waiting for a client). Each
 * connection adds what it holds to `used`; past `limit`, every one of
 * them holds no more than it must.
 */
export type ByteBudget = {
    limit: number;
    used: number;
    /** Holders paused on the budget; each is called once when `used` drops. */
    waiters: Set<() => void>;
};
export declare function createByteBudget(limit: number): ByteBudget;
/**
 * Add `delta` to what `budget`'s holders hold. A drop wakes every waiter:
 * each re-counts for itself and waits again if there is still no room.
 */
export declare function adjustByteBudget(budget: ByteBudget, delta: number): void;
/**
 * Pause req's socket whenever more than `cap` bytes of req's body sit in
 * req's buffer, or any do while `budget` is spent. Pausing the
 * IncomingMessage is not enough where the runtime keeps pushing into it
 * from a flowing socket; pausing the socket is. The server resumes the
 * socket itself when the body's reader pulls (IncomingMessage._read). Only
 * the socket is listened to: a 'data' listener on req would start the body
 * flowing before anyone reads it.
 */
export declare function gateSocketOnBufferedBody(req: IncomingMessage, cap: number, budget?: ByteBudget): void;
/**
 * Mark a TLS-terminated tunnel's socket: once a response on it is done, the
 * request is ended by ending the socket (close_notify, then a FIN once the
 * queue is flushed), not by destroying it, which would drop what the TLS
 * layer has not yet written out.
 */
export declare function markEndsGracefully(socket: object): void;
/**
 * Stop a request whose response is out: end its socket where it is marked
 * (then destroy it after a second, for a client that keeps sending), else
 * destroy the request.
 */
export declare function endRequestAfterResponse(req: IncomingMessage): void;
//# sourceMappingURL=emitted-connection.d.ts.map