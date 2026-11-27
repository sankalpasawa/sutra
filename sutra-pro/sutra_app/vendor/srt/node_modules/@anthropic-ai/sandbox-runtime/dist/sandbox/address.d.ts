/**
 * IP-literal / CIDR helpers over `net.BlockList`, shared by the
 * resolved-address guard, the parent-proxy NO_PROXY matcher and config
 * validation.
 */
import { BlockList } from 'node:net';
/** Loopback in both families (BlockList matches IPv4-mapped forms against the IPv4 rule). */
export declare const LOOPBACK_RANGES: readonly string[];
type AddressFamily = 'ipv4' | 'ipv6';
type AddressRange = {
    address: string;
    prefix: number;
    family: AddressFamily;
};
/**
 * Parse an IP literal or CIDR range (`10.0.0.0/8`, `fc00::/7`, `::1`) into
 * the one form rules are stored in: an IPv4-mapped IPv6 entry becomes the
 * IPv4 rule it stands for (`::ffff:10.0.0.0/104` → `10.0.0.0/8`) and a zone
 * id is dropped, since matching treats both spellings alike and some
 * runtimes mis-evaluate or refuse the IPv6 ones. Undefined for anything
 * else; IPv6 is unbracketed.
 */
export declare function parseAddressRange(entry: string): AddressRange | undefined;
/** Add an IP literal or CIDR range to `list`; false (list untouched) if malformed or refused by the runtime. */
export declare function addRange(list: BlockList, entry: string): boolean;
/**
 * BlockList membership for an address string of either family. IPv4 rules
 * also match the IPv4-mapped IPv6 spelling (BlockList does that itself);
 * an IPv6 zone id (`fe80::1%en0`) is dropped first because a zoned address
 * is a non-match on some runtimes.
 */
export declare function addressInSet(list: BlockList, address: string): boolean;
/** The IPv4 address of an IPv4-mapped IPv6 literal (`::ffff:a.b.c.d`), or undefined. */
export declare function mappedIPv4(address: string): string | undefined;
/**
 * The IPv4 address an IPv6 address carries in one of the forms a network
 * delivers to that IPv4 destination: IPv4-mapped and IPv4-compatible
 * (`::ffff:0:0/96`, `::/96`), IPv4-translated (`::ffff:0:0:0/96`), the NAT64
 * well-known prefix (`64:ff9b::/96`) and 6to4 (`2002::/16`). Undefined for
 * anything else — including the local-use NAT64 prefix `64:ff9b:1::/48` and
 * network-specific prefixes, whose layout (RFC 6052 §2.2 allows /32…/96)
 * cannot be told from the address, so the embedded IPv4 could be anywhere;
 * an embedder on such a network lists the prefix's translations of the
 * ranges it denies.
 */
export declare function embeddedIPv4(address: string): string | undefined;
/** True for an IPv4/IPv6 loopback literal (including v4-mapped forms). */
export declare function isLoopbackAddress(address: string): boolean;
/** `localhost` and names under `.localhost` (RFC 6761 §6.3). */
export declare function isLoopbackName(hostname: string): boolean;
export {};
//# sourceMappingURL=address.d.ts.map