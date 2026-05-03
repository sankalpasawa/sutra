/**
 * Shared types — V2.3/V2.4 Sutra Engine spec §1 (Primitives) + §2 (Supporting concepts)
 *
 * Layer 1 (abstraction) — pure type definitions only. No runtime logic. No technology bindings.
 * These are imports for the 4 primitives: Domain, Charter, Workflow, Execution.
 *
 * Source-of-truth: holding/research/2026-04-28-v2-architecture-spec.md
 */
// M4.3: DataRef zod schema for use by DecisionProvenance.evidence (and other
// new M4 schemas). The TS interface remains the source-of-truth for primitives;
// this schema mirrors it for runtime parsing. Imported here so the dependency
// graph stays acyclic (schemas may import types/, never the reverse).
import { z } from 'zod';
import { AuthoritativeStatusSchema } from './authoritative-status.js';
export const DataRefSchema = z.object({
    kind: z.string().min(1),
    schema_ref: z.string().min(1),
    locator: z.string().min(1),
    version: z.string(),
    mutability: z.enum(['mutable', 'immutable']),
    retention: z.string(),
    // M4.6 — default `authoritative` per D2 §5; explicit `advisory` allowed.
    authoritative_status: AuthoritativeStatusSchema.default('authoritative'),
});
//# sourceMappingURL=index.js.map