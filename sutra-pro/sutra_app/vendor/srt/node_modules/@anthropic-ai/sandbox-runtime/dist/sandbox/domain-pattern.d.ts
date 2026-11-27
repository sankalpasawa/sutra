/**
 * Domain-pattern matching shared between runtime host filtering
 * (sandbox-manager) and config-time validation (sandbox-config).
 * Lives in its own module so the schema can import it without pulling
 * in sandbox-manager (which imports the schema — circular).
 *
 * The validity check for a list entry lives here too, so the manager can
 * apply it to lists registered at run time without loading the schema module.
 */
/**
 * Split an optional `:port` suffix off a domain pattern.
 *
 * `api.github.com:443` → `{ hostPattern: 'api.github.com', port: 443 }`
 * `api.github.com`     → `{ hostPattern: 'api.github.com', port: undefined }`
 * `[::1]:443`          → `{ hostPattern: '::1', port: 443 }`
 * `[2001:db8::1]`      → `{ hostPattern: '2001:db8::1', port: undefined }`
 *
 * Only a strictly-numeric suffix in 1–65535 (no leading zeros) counts as a
 * port, so a smuggled host suffix like `evil.com:443.allowed.com` is left
 * whole (and then fails host validation on the remaining `:`).
 *
 * IPv6 literals must be bracketed (RFC 3986 / RFC 5952 §6: `[addr]` or
 * `[addr]:port`); the returned hostPattern is the bare, canonically
 * compressed address so it compares equal to what {@link canonicalizeHost}
 * yields for a destination. An *unbracketed* string with two or more colons
 * is ambiguous (`::1:443` is itself a valid address) — it is returned whole
 * with no port, never split, so a trailing hextet can't be mistaken for a
 * port and silently narrow the entry. The config schema rejects that form;
 * this fallback only matters for embedders passing config programmatically.
 */
export declare function splitDomainPatternPort(pattern: string): {
    hostPattern: string;
    port: number | undefined;
};
/**
 * Host-only pattern check (e.g., "example.com", "*.npmjs.org"). Rejects
 * protocols, paths, ports, and overly broad wildcards.
 */
export declare function isValidDomainPattern(val: string): boolean;
export declare const DOMAIN_PATTERN_MESSAGE = "Invalid domain pattern. Must be a valid domain (e.g., \"example.com\"), a wildcard (e.g., \"*.example.com\"), or a bracketed IPv6 literal (e.g., \"[::1]\", \"[2001:db8::1]:443\"). Overly broad patterns like \"*.com\" or \"*\" are not allowed for security reasons.";
/**
 * Raw-entry rule applied before the port split: an entry with two or more
 * colons is an IPv6 literal and must use RFC 3986 brackets (`[::1]`,
 * `[::1]:443`). Unbracketed it is ambiguous (`2001:db8::1:443` is itself a
 * valid 8-hextet address), so reject it and make the user say which they
 * mean, rather than accept an entry that can silently match the wrong thing.
 */
export declare function hasValidIpv6Bracketing(val: string): boolean;
/**
 * The check an allow-list entry gets: a domain pattern with an optional
 * `:port` suffix. Shared by the `network.allowedDomains` schema and the lists
 * registered at run time, so neither accepts what the other refuses.
 */
export declare function isValidAllowedDomainEntry(val: string): boolean;
export declare const ALLOWED_DOMAIN_ENTRY_MESSAGE: string;
/**
 * The IP-literal entries of an allow/deny list as `{ range, port? }` rules
 * for the resolved-address check: an address the list names explicitly is
 * judged the same way when a hostname resolves to it.
 */
export declare function ipLiteralRules(entries: readonly string[]): Array<{
    range: string;
    port?: number;
}>;
/** Drop a `:port` suffix, if any (see {@link splitDomainPatternPort}). */
export declare function stripDomainPatternPort(pattern: string): string;
/**
 * Match a hostname against a domain pattern.
 *
 * Patterns:
 *   - `*` matches everything (deny-all; the schema only accepts this in
 *     deniedDomains).
 *   - `*.example.com` matches any strict subdomain of example.com.
 *   - anything else matches exactly (case-insensitive).
 *
 * Wildcard suffix matching is refused for IP literals so an IPv6 zone-ID
 * payload like `::ffff:1.2.3.4%x.allowed.com` cannot pass `.endsWith()`
 * while the OS connects to the bare IP. isValidHost already rejects `%`,
 * but we refuse here too for defence in depth.
 */
export declare function matchesDomainPattern(hostname: string, pattern: string): boolean;
/**
 * {@link matchesDomainPattern} with an optional `:port` suffix on the
 * pattern (`example.com:443`, `*.example.com:8443`, `*:22`). A pattern
 * without a port matches every port; a pattern with one matches only when
 * the destination port is equal.
 */
export declare function matchesDomainPatternWithPort(hostname: string, port: number, pattern: string): boolean;
/**
 * Decide whether a per-credential `injectHosts` entry is reachable via
 * `network.allowedDomains` — i.e. every concrete host that could match
 * `injectHost` is allowed by at least one entry in `allowedDomains`.
 *
 * For an exact `injectHost` (`api.github.com`) this is just
 * `matchesDomainPattern` against each allowed pattern.
 *
 * For a wildcard `injectHost` (`*.X`), an exact allowedDomain can never
 * cover it (it admits only one host), so coverage requires an allowed
 * wildcard `*.Y` whose base is `X` or an ancestor of `X` — e.g.
 * `*.api.github.com` is covered by `*.github.com`.
 *
 * `:port` suffixes on allowedDomains entries are ignored: injection is
 * host-scoped, and a port-scoped allow still makes the host reachable.
 */
export declare function isInjectHostCoveredByAllowedDomains(injectHost: string, allowedDomains: readonly string[]): boolean;
//# sourceMappingURL=domain-pattern.d.ts.map