/**
 * DecisionProvenance — D2 §2.1 (HIGHEST-LEVERAGE schema; M4.3).
 *
 * The constitutional decision shape — what every consequential decision in
 * Native attributes itself with. The OTel emission gateway lands at M8;
 * M4 ships the SCHEMA only.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d2-decision-provenance-spec.md §2.1
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.3
 */
import { z } from 'zod';
/** Provenance id pattern: `dp-<lowercase-hex>`. */
export declare const DP_ID_PATTERN: RegExp;
/**
 * Decision kinds — D1 §2 Authority Map.
 *
 * AUDIT added in Group G' fix-up (2026-04-29) per codex master P2.3:
 * D2 §195 uses `decision_kind=AUDIT` for drift detection / provenance audits.
 */
export declare const DecisionKindSchema: z.ZodEnum<{
    DECIDE: "DECIDE";
    EXECUTE: "EXECUTE";
    OVERRIDE: "OVERRIDE";
    APPROVE: "APPROVE";
    REJECT: "REJECT";
    DELEGATE: "DELEGATE";
    TERMINATE: "TERMINATE";
    AUDIT: "AUDIT";
}>;
export type DecisionKind = z.infer<typeof DecisionKindSchema>;
/**
 * Decision scopes — D1 §3 Authority Map.
 *
 * PLUGIN + MARKETPLACE added in Group G' fix-up (2026-04-29) per codex master
 * P2.3: D1 §52 lists S-PLUGIN + S-MARKETPLACE as valid scopes.
 */
export declare const DecisionScopeSchema: z.ZodEnum<{
    CONSTITUTIONAL: "CONSTITUTIONAL";
    DOMAIN: "DOMAIN";
    CHARTER: "CHARTER";
    TENANT: "TENANT";
    WORKFLOW: "WORKFLOW";
    EXECUTION: "EXECUTION";
    HOOK: "HOOK";
    PLUGIN: "PLUGIN";
    MARKETPLACE: "MARKETPLACE";
}>;
export type DecisionScope = z.infer<typeof DecisionScopeSchema>;
/**
 * DecisionProvenance — D2 §2.1 verbatim.
 *
 * Required cross-coupling F-8 (partial in M4): `policy_id` and `policy_version`
 * are both `min(1)` here so neither can be empty. Full F-8 enforcement at
 * terminal_check lives in M4.9 chunk 2.
 */
export declare const DecisionProvenanceSchema: z.ZodObject<{
    id: z.ZodString;
    actor: z.ZodString;
    agent_identity: z.ZodDiscriminatedUnion<[z.ZodObject<{
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
    timestamp: z.ZodString;
    evidence: z.ZodArray<z.ZodObject<{
        kind: z.ZodString;
        schema_ref: z.ZodString;
        locator: z.ZodString;
        version: z.ZodString;
        mutability: z.ZodEnum<{
            mutable: "mutable";
            immutable: "immutable";
        }>;
        retention: z.ZodString;
        authoritative_status: z.ZodDefault<z.ZodEnum<{
            authoritative: "authoritative";
            advisory: "advisory";
        }>>;
    }, z.core.$strip>>;
    authority_id: z.ZodString;
    policy_id: z.ZodString;
    policy_version: z.ZodString;
    confidence: z.ZodNumber;
    decision_kind: z.ZodEnum<{
        DECIDE: "DECIDE";
        EXECUTE: "EXECUTE";
        OVERRIDE: "OVERRIDE";
        APPROVE: "APPROVE";
        REJECT: "REJECT";
        DELEGATE: "DELEGATE";
        TERMINATE: "TERMINATE";
        AUDIT: "AUDIT";
    }>;
    scope: z.ZodEnum<{
        CONSTITUTIONAL: "CONSTITUTIONAL";
        DOMAIN: "DOMAIN";
        CHARTER: "CHARTER";
        TENANT: "TENANT";
        WORKFLOW: "WORKFLOW";
        EXECUTION: "EXECUTION";
        HOOK: "HOOK";
        PLUGIN: "PLUGIN";
        MARKETPLACE: "MARKETPLACE";
    }>;
    outcome: z.ZodString;
    next_action_ref: z.ZodUnion<readonly [z.ZodString, z.ZodString, z.ZodNull]>;
}, z.core.$strip>;
export type DecisionProvenance = z.infer<typeof DecisionProvenanceSchema>;
/**
 * Construct a DecisionProvenance after schema validation. Throws on invalid input.
 */
export declare function createDecisionProvenance(input: DecisionProvenance): DecisionProvenance;
/**
 * Predicate: is this DecisionProvenance shape valid against D2 §2.1?
 */
export declare function isValidDecisionProvenance(v: unknown): v is DecisionProvenance;
//# sourceMappingURL=decision-provenance.d.ts.map