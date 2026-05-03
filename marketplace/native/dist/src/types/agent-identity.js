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
export const AGENT_KINDS = [
    'claude-opus',
    'claude-sonnet',
    'codex',
    'subagent',
    'human',
    'system',
];
/**
 * Build an id-validator for one kind: id MUST start with `<kind>:` followed
 * by at least one non-whitespace character.
 *
 * The same id with a wrong-kind prefix is rejected at parse time.
 */
function idForKind(kind) {
    const re = new RegExp(`^${kind}:\\S+$`);
    return z
        .string()
        .min(1)
        .refine((v) => re.test(v), {
        message: `AgentIdentity.id must start with "${kind}:" and have a non-empty suffix (D-NS-10 namespace prefix)`,
    });
}
/**
 * Optional version string (free-form; non-empty when provided).
 */
const versionSchema = z.string().min(1).optional();
const claudeOpusSchema = z.object({
    kind: z.literal('claude-opus'),
    id: idForKind('claude-opus'),
    version: versionSchema,
});
const claudeSonnetSchema = z.object({
    kind: z.literal('claude-sonnet'),
    id: idForKind('claude-sonnet'),
    version: versionSchema,
});
const codexSchema = z.object({
    kind: z.literal('codex'),
    id: idForKind('codex'),
    version: versionSchema,
});
const subagentSchema = z.object({
    kind: z.literal('subagent'),
    id: idForKind('subagent'),
    version: versionSchema,
});
const humanSchema = z.object({
    kind: z.literal('human'),
    id: idForKind('human'),
    version: versionSchema,
});
const systemSchema = z.object({
    kind: z.literal('system'),
    id: idForKind('system'),
    version: versionSchema,
});
/**
 * AgentIdentity — discriminated union on `kind`.
 *
 * Validation:
 * - `kind` ∈ AGENT_KINDS
 * - `id` non-empty AND prefixed by `<kind>:` (D-NS-10 namespace prefix)
 * - `version` optional; non-empty string when provided
 */
export const AgentIdentitySchema = z.discriminatedUnion('kind', [
    claudeOpusSchema,
    claudeSonnetSchema,
    codexSchema,
    subagentSchema,
    humanSchema,
    systemSchema,
]);
/**
 * Validate + return a typed AgentIdentity. Throws on invalid input.
 */
export function createAgentIdentity(input) {
    return AgentIdentitySchema.parse(input);
}
/**
 * Predicate: does this value satisfy the AgentIdentity schema?
 */
export function isValidAgentIdentity(v) {
    return AgentIdentitySchema.safeParse(v).success;
}
/**
 * Helper: extract the namespace prefix from an id (everything before the first `:`).
 */
export function namespaceOf(id) {
    const idx = id.indexOf(':');
    if (idx <= 0)
        return null;
    return id.slice(0, idx);
}
//# sourceMappingURL=agent-identity.js.map