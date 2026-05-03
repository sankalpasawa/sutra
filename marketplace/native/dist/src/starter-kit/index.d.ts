/**
 * Native v1.0 Starter Kit — D3 of NPD productization plan.
 *
 * Ships with the plugin so the founder gets a working set of primitives on
 * first `/start-native`. Per codex's "cargo-cult-prevention" caveat in the
 * NPD design fold: keep this curated + minimal; users should READ + EDIT,
 * not blindly clone.
 *
 * Counts (per charter §0.1 D3):
 *   - 5 Domains          (showing the range of life/work scopes)
 *   - 6 Charters         (one per Domain + 1 onboarding meta-charter)
 *   - 10 Workflows       (1-2 per Charter, demonstrating step_graph patterns)
 *   - 5 TriggerSpecs     (one per event_type alphabet that v1.0 supports)
 *   - 1 onboarding workflow (W-onboarding-tour)
 *
 * This module is DATA. The contract test
 * (tests/contract/starter-kit/starter-kit.test.ts) validates every
 * entity through createDomain / createCharter / createWorkflow + the
 * isValid* guards so primitive-shape drift is caught immediately.
 */
import { type Domain } from '../primitives/domain.js';
import { type Charter } from '../primitives/charter.js';
import { type Workflow } from '../primitives/workflow.js';
import type { TriggerSpec } from '../types/trigger-spec.js';
export declare const DOMAIN_PERSONAL: Domain;
export declare const DOMAIN_PRODUCT: Domain;
export declare const DOMAIN_RELATIONSHIPS: Domain;
export declare const DOMAIN_FINANCE: Domain;
export declare const DOMAIN_LEARNING: Domain;
export declare const STARTER_DOMAINS: ReadonlyArray<Domain>;
export declare const CHARTER_DAILY_PULSE: Charter;
export declare const CHARTER_BUILD_PRODUCT: Charter;
export declare const CHARTER_RELATIONSHIPS_TOUCHPOINTS: Charter;
export declare const CHARTER_MONTHLY_FINANCE_REVIEW: Charter;
export declare const CHARTER_WEEKLY_LEARNING_LOOP: Charter;
export declare const CHARTER_ONBOARDING: Charter;
export declare const STARTER_CHARTERS: ReadonlyArray<Charter>;
export declare const W_MORNING_PULSE: Workflow;
export declare const W_EVENING_SHUTDOWN: Workflow;
/**
 * Multi-step workflow showing on_failure variants per step + declared
 * inputs/outputs. Codex P1.2 fold 2026-05-03 — anti-cargo-cult example.
 */
export declare const W_FEATURE_BUILD: Workflow;
/**
 * Multi-step workflow with policy_check per step (codex P1.2 fold).
 * Mirrors a real bug-fix loop: assess → patch (gated) → regression test.
 */
export declare const W_BUG_FIX: Workflow;
export declare const W_ONE_ON_ONE_PREP: Workflow;
export declare const W_RELATIONSHIP_CHECKIN: Workflow;
/** Multi-step workflow with declared state (codex P1.2 fold). */
export declare const W_MONTHLY_FINANCE_REVIEW: Workflow;
export declare const W_LEARNING_SUMMARY: Workflow;
export declare const W_ONBOARDING_TOUR: Workflow;
export declare const W_ONBOARDING_CREATE_DOMAIN: Workflow;
export declare const STARTER_WORKFLOWS: ReadonlyArray<Workflow>;
export declare const T_MORNING_PULSE: TriggerSpec;
/**
 * T-build-feature — codex P2.2 fold 2026-05-03: predicate narrowed.
 * Previous version matched ANY input containing 'add', which collided with
 * everyday phrases like "add to my calendar". Now requires both a build
 * verb AND a feature-noun keyword to fire.
 */
export declare const T_BUILD_FEATURE: TriggerSpec;
export declare const T_BUG_FIX: TriggerSpec;
/**
 * T-onboarding — codex P1.1 fold 2026-05-03: switched from file_drop
 * (v1.1+ unimplemented) to founder_input so the "first founder input →
 * first SUCCESS Execution" path is genuinely runnable at v1.0. The
 * keyword set covers common first-touch phrases.
 */
export declare const T_ONBOARDING: TriggerSpec;
export declare const T_LEARNING_SUMMARY: TriggerSpec;
export declare const STARTER_TRIGGERS: ReadonlyArray<TriggerSpec>;
export declare const STARTER_WORKFLOW_CHARTER_MAP: ReadonlyMap<string, string>;
export declare const ONBOARDING_WORKFLOW: Workflow;
export interface StarterKit {
    readonly domains: ReadonlyArray<Domain>;
    readonly charters: ReadonlyArray<Charter>;
    readonly workflows: ReadonlyArray<Workflow>;
    readonly triggers: ReadonlyArray<TriggerSpec>;
    readonly onboarding: Workflow;
}
/** Returns the curated Native v1.0 starter kit (deep-frozen). */
export declare function loadStarterKit(): StarterKit;
//# sourceMappingURL=index.d.ts.map