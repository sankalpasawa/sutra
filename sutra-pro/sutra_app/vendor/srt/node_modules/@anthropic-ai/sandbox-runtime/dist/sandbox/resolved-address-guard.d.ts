/**
 * Resolved-address guard for hostname destinations.
 *
 * The domain allowlist decides by name, but whoever controls a permitted
 * name's DNS records (or any label under a permitted wildcard) decides what
 * that name resolves to. Without a check on the resolved address, an
 * allow-listed name can be pointed at the loopback interface, a link-local
 * address, or address space the embedder considers private, and the proxy
 * will dial it. This module wraps `dns.lookup` so a direct dial resolves
 * once, drops denied addresses, and connects to a surviving one — the
 * address that passed the check is the address dialed, with no second
 * resolution in between.
 *
 * Scope: hostnames only. An IP literal on the allowlist is an explicit
 * choice and is never re-judged here; conversely, a name may resolve to a
 * denied address only when that address (and port) is itself allow-listed,
 * so reaching it by name grants nothing the literal entry did not — and an
 * IP literal on the deny list is refused by name too, allowlist or not. The
 * reserved loopback names (`localhost` and anything under `.localhost`,
 * RFC 6761) resolve to loopback — that is what allow-listing them asks for —
 * or to an allow-listed literal, and to nothing else. Connections routed
 * through a parent proxy or a MITM socket are not resolved locally at all;
 * that hop resolves the name and is responsible for its own address policy.
 */
import type { LookupAddress, LookupAllOptions } from 'node:dns';
import type { LookupFunction } from 'node:net';
/** Unicast addresses currently assigned to this host's network interfaces. */
export declare function localInterfaceAddresses(): string[];
export declare class ResolvedAddressDeniedError extends Error {
    readonly hostname: string;
    readonly reason: string;
    readonly addresses: readonly string[];
    readonly code = "ERR_SRT_RESOLVED_ADDRESS_DENIED";
    /**
     * @param reason parenthetical for the violation line and the client, e.g.
     *   `resolved to a loopback address` — the class, never the address, which
     *   the sandboxed client should not learn from a refusal.
     * @param addresses the refused addresses, for operator logs.
     */
    constructor(hostname: string, reason: string, addresses: readonly string[]);
}
export declare function isResolvedAddressDenied(err: unknown): err is ResolvedAddressDeniedError;
export type Resolver = (hostname: string, options: LookupAllOptions, callback: (err: NodeJS.ErrnoException | null, addresses: LookupAddress[]) => void) => void;
/**
 * The guard reads the same three lists the name filter does, in the same
 * order of precedence: an IP literal in `deniedDomains` is refused however
 * it is reached; an IP literal in `allowedDomains` (with its `:port`) is
 * what a name MAY resolve to even though the address is otherwise denied —
 * so a name reaches nothing the literal entry does not already permit; and
 * `deniedResolvedAddresses` extends the built-in denied set.
 */
export interface ResolvedAddressGuardOptions {
    allowedDomains?: readonly string[];
    deniedDomains?: readonly string[];
    /** IPs / CIDRs denied in addition to the built-in {@link DENIED_CLASSES} and this host's own addresses. */
    deniedResolvedAddresses?: readonly string[];
    /** Name resolver; defaults to `dns.lookup`. Test seam. */
    resolve?: Resolver;
    /** This host's interface addresses; defaults to {@link localInterfaceAddresses}, read per lookup. Test seam. */
    localAddresses?: () => readonly string[];
}
export interface ResolvedAddressGuard {
    /**
     * Whether a connection to `hostname:port` may use resolved `address`.
     * Always true when `hostname` is itself an IP literal.
     */
    permits(hostname: string, address: string, port: number): boolean;
    /**
     * `lookup` for a `net.connect` to `port` (see `dialDirect`): resolves via
     * the configured resolver, removes addresses `permits` rejects, and fails
     * with {@link ResolvedAddressDeniedError} when none remain.
     */
    lookupFor(port: number): LookupFunction;
}
export declare function createResolvedAddressGuard(opts?: ResolvedAddressGuardOptions): ResolvedAddressGuard;
//# sourceMappingURL=resolved-address-guard.d.ts.map