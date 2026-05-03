/**
 * Native v1.0 edge types — M4.8 (Group C in TASK-QUEUE.md §1).
 *
 * Three new edge types per D4 §2.2:
 *   - `owns`          : Tenant → Domain        (P-A1, sovereignty)
 *   - `delegates_to`  : Tenant → Tenant        (P-B8, cross-tenant delegation)
 *   - `emits`         : Workflow/Execution/Hook → DecisionProvenance  (P-A3, attribution)
 *
 * IMPORTANT — L5 META law preserves only `Domain.contains.Charter` as
 * containment. The `owns` edge here is sovereignty-not-containment:
 * Tenant OWNS Domain (sovereignty boundary) but does NOT contain it.
 * Containment edges remain limited to Domain → Charter only.
 *
 * Per D4 §2.2 + D1 P-A1 + D2 P-A3.
 *
 * Note on cross-kind validation: id-pattern guards at the schema level catch the
 * common "wrong primitive in source/target" mistakes (e.g. `owns` with a
 * Workflow id as target). Stricter constraints — like "delegates_to source !==
 * target" or "emits source must already exist in registry" — are runtime
 * concerns, not schema concerns, and live at terminal_check (M4.9) and the
 * Workflow Engine (M5+).
 */
import { z } from 'zod';
export declare const OwnsEdgeSchema: z.ZodObject<{
    kind: z.ZodLiteral<"owns">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>;
export type OwnsEdge = z.infer<typeof OwnsEdgeSchema>;
export declare const DelegatesToEdgeSchema: z.ZodObject<{
    kind: z.ZodLiteral<"delegates_to">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>;
export type DelegatesToEdge = z.infer<typeof DelegatesToEdgeSchema>;
export declare const EmitsEdgeSchema: z.ZodObject<{
    kind: z.ZodLiteral<"emits">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>;
export type EmitsEdge = z.infer<typeof EmitsEdgeSchema>;
export declare const EdgeSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    kind: z.ZodLiteral<"owns">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"delegates_to">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"emits">;
    source: z.ZodString;
    target: z.ZodString;
}, z.core.$strip>], "kind">;
export type Edge = z.infer<typeof EdgeSchema>;
/**
 * Predicate: is this Edge shape valid against D4 §2.2?
 */
export declare function isValidEdge(e: unknown): e is Edge;
//# sourceMappingURL=edges.d.ts.map