/**
 * AgentIdentity — discriminated union of agent kinds (M4.2; D1 P-A2; V2.5 §A14).
 *
 * Every Execution carries an agent_identity so audit trails can answer "which
 * LLM/agent made this decision."
 *
 * D-NS-10 founder default (c) applied: id values use a namespace prefix per
 * kind to prevent cross-kind id collisions. The expected prefix is the kind
 * itself followed by `:`. For example:
 *   - kind=claude-opus  → id="claude-opus:abc123"
 *   - kind=codex        → id="codex:session-xyz"
 *   - kind=human        → id="human:asawa@nurix.ai"
 *   - kind=system       → id="system:dispatcher"
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d1-authority-map.md §3 Agent Identity
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.2 (D-NS-10 default c)
 */
import { z } from 'zod';
/**
 * Allowed agent kinds. Discriminator field for the union.
 */
export declare const AGENT_KINDS: readonly ["claude-opus", "claude-sonnet", "codex", "subagent", "human", "system"];
export type AgentKind = (typeof AGENT_KINDS)[number];
/**
 * AgentIdentity — discriminated union on `kind`.
 *
 * Validation:
 * - `kind` ∈ AGENT_KINDS
 * - `id` non-empty AND prefixed by `<kind>:` (D-NS-10 namespace prefix)
 * - `version` optional; non-empty string when provided
 */
export declare const AgentIdentitySchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    kind: z.ZodLiteral<"claude-opus">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"claude-sonnet">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"codex">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"subagent">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"human">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>, z.ZodObject<{
    kind: z.ZodLiteral<"system">;
    id: z.ZodString;
    version: z.ZodOptional<z.ZodString>;
}, z.core.$strip>], "kind">;
export type AgentIdentity = z.infer<typeof AgentIdentitySchema>;
/**
 * Validate + return a typed AgentIdentity. Throws on invalid input.
 */
export declare function createAgentIdentity(input: AgentIdentity): AgentIdentity;
/**
 * Predicate: does this value satisfy the AgentIdentity schema?
 */
export declare function isValidAgentIdentity(v: unknown): v is AgentIdentity;
/**
 * Helper: extract the namespace prefix from an id (everything before the first `:`).
 */
export declare function namespaceOf(id: string): string | null;
//# sourceMappingURL=agent-identity.d.ts.map