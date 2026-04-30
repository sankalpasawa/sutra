/**
 * Sutra Connectors — Capability model + tier→capability map
 * Frozen by LLD §2.3.
 *
 * Pure functions (no side effects). Implementation lands iter 8 of the
 * autonomous build loop — flips ~18 capability tests RED→GREEN.
 */
// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------
/**
 * Split a capability id into [connector, action, resource?] segments.
 * Resource is everything after the second `:` (may itself contain colons).
 * Returns undefined for `resource` when the capability has only two segments.
 */
function splitCapability(capability) {
    const firstColon = capability.indexOf(':');
    if (firstColon === -1) {
        return { connector: capability, action: '', resource: undefined };
    }
    const connector = capability.slice(0, firstColon);
    const rest = capability.slice(firstColon + 1);
    const secondColon = rest.indexOf(':');
    if (secondColon === -1) {
        return { connector, action: rest, resource: undefined };
    }
    const action = rest.slice(0, secondColon);
    const resource = rest.slice(secondColon + 1);
    return { connector, action, resource };
}
/**
 * True iff `pattern` is a glob (contains `*`).
 */
function isGlob(pattern) {
    return pattern.includes('*');
}
/**
 * Apply a glob to a literal value. Supported forms:
 *   '*'         → matches anything (including empty)
 *   'prefix*'   → matches anything starting with `prefix` (including '#*')
 *   exact       → exact string match
 *
 * Empty / undefined patterns never match.
 */
function globMatch(value, pattern) {
    if (pattern === undefined || pattern === null || pattern === '') {
        return false;
    }
    if (pattern === '*') {
        return true;
    }
    if (isGlob(pattern)) {
        // Translate glob to regex: escape regex specials, replace `*` with `.*`.
        const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
        const re = new RegExp(`^${escaped}$`);
        return re.test(value);
    }
    return value === pattern;
}
/**
 * Find the CapabilityDecl in the manifest whose id matches the invoked
 * capability. Matching strategy: the decl's id and the invoked capability
 * must share the same `connector:action` prefix. The resource portion is
 * compared via the decl's `resourcePattern` (which the decl id typically
 * already encodes).
 *
 * If no decl shares the connector+action prefix → undefined (unknown).
 */
function findDecl(capability, manifest) {
    const { connector, action } = splitCapability(capability);
    const prefix = `${connector}:${action}`;
    return manifest.capabilities.find((decl) => {
        const split = splitCapability(decl.id);
        return split.connector === connector && split.action === action;
        void prefix;
    });
}
/**
 * Does an entry in `tierAccess[tier]` cover the invoked capability?
 *  - Exact string match → yes
 *  - Entry has a glob in its resource segment AND shares connector:action
 *    prefix with the capability → yes (we still validate the resource via
 *    the decl's resourcePattern downstream)
 */
function tierEntryCovers(entry, capability) {
    if (entry === capability) {
        return true;
    }
    const e = splitCapability(entry);
    const c = splitCapability(capability);
    if (e.connector !== c.connector || e.action !== c.action) {
        return false;
    }
    // Same connector:action prefix. If the tier entry's resource is a glob,
    // treat the connector:action pair as covered (resourcePattern decides).
    if (e.resource !== undefined && isGlob(e.resource)) {
        return true;
    }
    return false;
}
// ---------------------------------------------------------------------------
// Public API — LLD §2.3
// ---------------------------------------------------------------------------
export function tierGrants(tier, capability, manifest) {
    // 1. Capability must be declared in manifest.capabilities (by connector+action).
    const decl = findDecl(capability, manifest);
    if (decl === undefined) {
        return { granted: false, reason: 'unknown-capability' };
    }
    // 2. Tier must list the capability (exact or glob-prefix coverage).
    const tierList = manifest.tierAccess[tier] ?? [];
    const tierCovers = tierList.some((entry) => tierEntryCovers(entry, capability));
    if (!tierCovers) {
        return { granted: false, reason: 'tier-denied' };
    }
    // 3. Resource portion must satisfy the decl's resourcePattern.
    if (!matchesResourcePattern(capability, decl.resourcePattern)) {
        return { granted: false, reason: 'pattern-mismatch' };
    }
    return { granted: true, reason: 'tier-allowed' };
}
export function matchesResourcePattern(capability, declaredPattern) {
    if (declaredPattern === undefined || declaredPattern === null || declaredPattern === '') {
        return false;
    }
    // Universal glob accepts everything, including capabilities without a
    // resource segment.
    if (declaredPattern === '*') {
        return true;
    }
    const { resource } = splitCapability(capability);
    if (resource === undefined) {
        // No resource segment → only the universal glob matches; everything else fails.
        return false;
    }
    return globMatch(resource, declaredPattern);
}
export function isOverbroadCapability(capability) {
    if (!capability) {
        return false;
    }
    const { connector, action } = splitCapability(capability);
    // A capability is overbroad if the connector OR action segment is a bare
    // wildcard or contains a wildcard. The resource segment is intentionally
    // excluded — scoped wildcards there (e.g. '#*', 'users/*') are how
    // legitimate capabilities are written.
    if (connector === '' || action === '') {
        return false;
    }
    if (connector.includes('*') || action.includes('*')) {
        return true;
    }
    return false;
}
