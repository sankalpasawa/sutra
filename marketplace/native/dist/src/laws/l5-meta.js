/**
 * L5 META law — V2 spec §3 row L5
 *
 * Rule: "Use containment ONLY when removing parent revokes authority/
 *        accountability. Otherwise → typed graph link."
 *
 * Mechanization: "Single containment edge: `Domain.contains(Charter)`.
 *                 All others typed: operationalizes, decomposes_into,
 *                 depends_on, produces, consumes, activates, interfaces_with."
 *
 * V2.1 §11 added `propagates_to` to the edge list. The full V2.x edge
 * inventory used by the Workflow Engine is enumerated here for the
 * `isValidGraphEdge` predicate.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md §3 L5
 *                  + §11 (V2.1 §A1 propagates_to addition)
 */
const TYPED_EDGES = new Set([
    'operationalizes',
    'decomposes_into',
    'depends_on',
    'produces',
    'consumes',
    'activates',
    'interfaces_with',
    'propagates_to',
]);
const VALID_PRIMITIVE_KINDS = new Set([
    'domain',
    'charter',
    'workflow',
    'execution',
]);
export const l5Meta = {
    /**
     * Predicate: is this containment edge (`contains`) valid under L5 META?
     *
     * True iff (parent='domain' AND child='charter'). All other shapes are
     * rejected — they MUST be expressed as typed graph edges.
     */
    isValidContainment(parent, child) {
        if (!VALID_PRIMITIVE_KINDS.has(parent))
            return false;
        if (!VALID_PRIMITIVE_KINDS.has(child))
            return false;
        return parent === 'domain' && child === 'charter';
    },
    /**
     * Predicate: is this edge spec valid under L5 META?
     *
     * - `contains` edges: only Domain→Charter permitted.
     * - typed edges:      any kind in TYPED_EDGES (V2 §3 L5 + V2.1 §A1).
     *
     * Note we do not enforce per-typed-edge source/target shapes here (that
     * lives at the schema layer in M4); this predicate proves L5 META alone.
     */
    isValidEdge(kind, parent, child) {
        if (!VALID_PRIMITIVE_KINDS.has(parent))
            return false;
        if (!VALID_PRIMITIVE_KINDS.has(child))
            return false;
        if (kind === 'contains')
            return this.isValidContainment(parent, child);
        return TYPED_EDGES.has(kind);
    },
    /** Read-only view of the V2.x typed-edge inventory. */
    typedEdges() {
        return TYPED_EDGES;
    },
};
//# sourceMappingURL=l5-meta.js.map