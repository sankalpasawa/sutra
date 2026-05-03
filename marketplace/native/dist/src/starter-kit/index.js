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
import { createDomain } from '../primitives/domain.js';
import { createCharter } from '../primitives/charter.js';
import { createWorkflow } from '../primitives/workflow.js';
// =============================================================================
// 5 Domains — span personal-OS, product-build, relationships, finance, learning
// =============================================================================
export const DOMAIN_PERSONAL = createDomain({
    id: 'D1',
    name: 'Personal OS',
    parent_id: null,
    principles: [
        {
            name: 'energy_aware_scheduling',
            predicate: 'do_not_book_deep_work_against_low_energy_window',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
    ],
    intelligence: 'Personal calendar + energy log; founder is the only actor.',
    accountable: ['founder'],
    authority: 'Decide own time, attention, and personal commitments.',
    tenant_id: 'T-default',
});
export const DOMAIN_PRODUCT = createDomain({
    id: 'D2',
    name: 'Product Build',
    parent_id: null,
    principles: [
        {
            name: 'ship_thin_slices',
            predicate: 'no_release_larger_than_one_day_of_review',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
        {
            name: 'tests_before_merge',
            predicate: 'every_pr_has_passing_test_suite',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
    ],
    intelligence: 'Repo state, PR queue, deploy pipeline, customer reports.',
    accountable: ['founder', 'eng-lead'],
    authority: 'Decide architecture, scope, release timing.',
    tenant_id: 'T-default',
});
export const DOMAIN_RELATIONSHIPS = createDomain({
    id: 'D3',
    name: 'Relationships',
    parent_id: null,
    principles: [
        {
            name: 'reciprocity_within_30d',
            predicate: 'no_outstanding_unanswered_message_older_than_30d',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
    ],
    intelligence: 'Contact log, last-touch dates, upcoming birthdays/anniversaries.',
    accountable: ['founder'],
    authority: 'Decide cadence + depth of personal-relationship investment.',
    tenant_id: 'T-default',
});
export const DOMAIN_FINANCE = createDomain({
    id: 'D4',
    name: 'Finance',
    parent_id: null,
    principles: [
        {
            name: 'monthly_review_completed',
            predicate: 'finance_review_run_within_first_5_days_of_month',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
    ],
    intelligence: 'Bank statements, runway calculation, recurring-expense ledger.',
    accountable: ['founder', 'cfo-or-equivalent'],
    authority: 'Decide spend categories, runway buffer, subscription churn.',
    tenant_id: 'T-default',
});
export const DOMAIN_LEARNING = createDomain({
    id: 'D5',
    name: 'Learning',
    parent_id: null,
    principles: [
        {
            name: 'weekly_summary_written',
            predicate: 'one_learning_summary_per_iso_week',
            durability: 'durable',
            owner_scope: 'domain',
            type: 'invariant',
        },
    ],
    intelligence: 'Reading queue, talk notes, course progress, distilled summaries.',
    accountable: ['founder'],
    authority: 'Decide what to study + how to integrate it into work.',
    tenant_id: 'T-default',
});
export const STARTER_DOMAINS = Object.freeze([
    DOMAIN_PERSONAL,
    DOMAIN_PRODUCT,
    DOMAIN_RELATIONSHIPS,
    DOMAIN_FINANCE,
    DOMAIN_LEARNING,
]);
// =============================================================================
// 6 Charters — 1 per Domain + 1 onboarding meta-charter
// =============================================================================
export const CHARTER_DAILY_PULSE = createCharter({
    id: 'C-daily-pulse',
    purpose: 'Maintain a daily founder pulse: morning intent + evening reflection.',
    scope_in: 'morning_intent_set OR evening_reflection_written',
    scope_out: 'mid-day_check-ins, retrospectives, async standups',
    obligations: [
        {
            name: 'morning_pulse_emitted',
            predicate: 'morning_pulse_workflow_completed_today',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'pulse_at_most_once_per_phase',
            predicate: 'morning_pulse_count_today <= 1 AND evening_pulse_count_today <= 1',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['7-day morning-pulse adherence ≥ 6/7', 'evening-pulse skipped ≤ 1/wk'],
    authority: 'Decide own daily rhythm under D1 Personal OS.',
    termination: 'Founder explicitly opts out of pulse cadence for ≥30 days.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D1', access: 'append', reason: 'Personal OS is the parent domain' }],
});
export const CHARTER_BUILD_PRODUCT = createCharter({
    id: 'C-build-product',
    purpose: 'Ship product changes via thin, reviewed slices.',
    scope_in: 'feature_change OR bug_fix OR chore',
    scope_out: 'unbounded_refactors, multi-week_efforts',
    obligations: [
        {
            name: 'slice_has_test',
            predicate: 'every_slice_includes_at_least_one_test',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
        {
            name: 'slice_under_1_day_review',
            predicate: 'pr_review_completes_under_24h',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'main_always_green',
            predicate: 'main_branch_test_status == passing',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['weekly throughput ≥ 5 slices', 'main red-time ≤ 30 min/incident'],
    authority: 'Decide slice scope, review cadence, deploy timing.',
    termination: 'Product is sunset OR engineering ownership transfers.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D2', access: 'write', reason: 'Product Build domain owns this' }],
});
export const CHARTER_RELATIONSHIPS_TOUCHPOINTS = createCharter({
    id: 'C-relationship-touchpoints',
    purpose: 'Stay in touch with key people on a humane cadence.',
    scope_in: 'birthday OR check_in OR follow_up_owed',
    scope_out: 'transactional_business_email, mass-broadcast communications',
    obligations: [
        {
            name: 'birthday_acknowledged',
            predicate: 'every_contact_birthday_acknowledged_within_24h',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'no_outstanding_owed_30d',
            predicate: 'unanswered_owed_message_age <= 30_days',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['birthday acknowledgement rate ≥ 95%', 'overdue follow-ups < 3 at any time'],
    authority: 'Decide cadence + medium of personal-relationship contact.',
    termination: 'Contact set transitions to a CRM-managed channel.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D3', access: 'append', reason: 'Relationships domain owns this' }],
});
export const CHARTER_MONTHLY_FINANCE_REVIEW = createCharter({
    id: 'C-monthly-finance-review',
    purpose: 'Run a monthly review covering spend, runway, and recurring drift.',
    scope_in: 'monthly_review_due OR runway_threshold_crossed',
    scope_out: 'tax_filing, fundraising_decisions',
    obligations: [
        {
            name: 'monthly_summary_written',
            predicate: 'finance_summary_doc_updated_in_first_5_days_of_month',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'runway_recalculated',
            predicate: 'runway_months_value_within_24h_of_review_completion',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['12/12 months reviewed in trailing year', 'recurring-expense surprises = 0'],
    authority: 'Decide which categories to inspect, escalation thresholds.',
    termination: 'Finance moves to a managed CFO+bookkeeper system.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D4', access: 'write', reason: 'Finance domain owns this' }],
});
export const CHARTER_WEEKLY_LEARNING_LOOP = createCharter({
    id: 'C-weekly-learning-loop',
    purpose: 'Distill the week\'s learning into a 1-page summary.',
    scope_in: 'sunday_close OR week_boundary_crossed',
    scope_out: 'real-time_consumption_tracking, course_completion_certificates',
    obligations: [
        {
            name: 'weekly_summary_emitted',
            predicate: 'one_summary_artifact_per_iso_week',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'summary_size_capped',
            predicate: 'summary_word_count <= 1000',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['52/52 weeks summarized in trailing year', 'summary readable in < 5 min'],
    authority: 'Decide topic depth, which sources to integrate.',
    termination: 'Founder explicitly suspends learning practice for ≥90 days.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D5', access: 'append', reason: 'Learning domain owns this' }],
});
export const CHARTER_ONBOARDING = createCharter({
    id: 'C-onboarding',
    purpose: 'Walk a new founder through the engine\'s primitives + first SUCCESS Execution.',
    scope_in: 'fresh_install OR explicit_onboarding_request',
    scope_out: 'recurring_user_education, advanced_workflow_authoring',
    obligations: [
        {
            name: 'first_success_execution_emitted',
            predicate: 'at_least_one_execution_with_status_success_within_first_session',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
        },
    ],
    invariants: [
        {
            name: 'onboarding_runs_at_most_once',
            predicate: 'onboarding_completed_marker_present XOR onboarding_in_progress',
            durability: 'durable',
            owner_scope: 'charter',
            type: 'invariant',
        },
    ],
    success_metrics: ['onboarding completion ≥ 80%', 'time-to-first-SUCCESS ≤ 5 min'],
    authority: 'Decide demo Domain/Charter/Workflow scaffolding sequence.',
    termination: 'Founder marks onboarding complete OR explicitly skips.',
    constraints: [],
    acl: [{ domain_or_charter_id: 'D1', access: 'read', reason: 'Onboarding seeds the personal-OS domain' }],
});
export const STARTER_CHARTERS = Object.freeze([
    CHARTER_DAILY_PULSE,
    CHARTER_BUILD_PRODUCT,
    CHARTER_RELATIONSHIPS_TOUCHPOINTS,
    CHARTER_MONTHLY_FINANCE_REVIEW,
    CHARTER_WEEKLY_LEARNING_LOOP,
    CHARTER_ONBOARDING,
]);
// =============================================================================
// 10 Workflows — minimal step_graphs that satisfy the primitive contract
// =============================================================================
/**
 * Build a single-step workflow (for the simplest examples).
 * Codex P1.2 fold 2026-05-03: this shape is reserved for trivial 1-step
 * cases. Multi-step examples below use multiStepWorkflow() to demonstrate
 * actual step_graph patterns (parallel-by-id, on_failure variants,
 * skill_ref + policy_check).
 */
function singleStepWorkflow(spec) {
    return createWorkflow({
        ...spec,
        step_graph: [
            spec.step ?? {
                step_id: 1,
                action: 'wait',
                inputs: [],
                outputs: [],
                on_failure: 'continue',
            },
        ],
        inputs: spec.inputs ?? [],
        outputs: spec.outputs ?? [],
        state: [],
        interfaces_with: [],
    });
}
/**
 * Build a multi-step workflow (codex P1.2 fold 2026-05-03 — anti-cargo-cult).
 * Demonstrates the step_graph shape so users see real on_failure variants +
 * input/output declarations.
 */
function multiStepWorkflow(spec) {
    return createWorkflow({
        ...spec,
        step_graph: spec.steps,
        inputs: spec.inputs ?? [],
        outputs: spec.outputs ?? [],
        state: [],
        interfaces_with: [],
    });
}
export const W_MORNING_PULSE = singleStepWorkflow({
    id: 'W-morning-pulse',
    preconditions: 'is_morning_window AND no_pulse_today',
    postconditions: 'morning_pulse_artifact_registered',
    failure_policy: 'continue',
    stringency: 'process',
});
export const W_EVENING_SHUTDOWN = singleStepWorkflow({
    id: 'W-evening-shutdown',
    preconditions: 'is_evening_window AND no_evening_pulse_today',
    postconditions: 'evening_pulse_artifact_registered',
    failure_policy: 'continue',
    stringency: 'process',
});
/**
 * Multi-step workflow showing on_failure variants per step + declared
 * inputs/outputs. Codex P1.2 fold 2026-05-03 — anti-cargo-cult example.
 */
export const W_FEATURE_BUILD = multiStepWorkflow({
    id: 'W-feature-build',
    preconditions: 'feature_request_input_received',
    postconditions: 'pr_opened_with_passing_tests',
    failure_policy: 'rollback',
    stringency: 'protocol',
    inputs: [
        {
            kind: 'json',
            schema_ref: 'native://starter/feature-request/v1',
            locator: 'cas://input',
            version: '1.0.0',
            mutability: 'immutable',
            retention: 'permanent',
        },
    ],
    outputs: [
        {
            kind: 'json',
            schema_ref: 'native://starter/pull-request/v1',
            locator: 'cas://output',
            version: '1.0.0',
            mutability: 'immutable',
            retention: 'permanent',
        },
    ],
    steps: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'spawn_sub_unit', inputs: [], outputs: [], on_failure: 'rollback' },
        { step_id: 3, action: 'wait', inputs: [], outputs: [], on_failure: 'continue' },
    ],
});
/**
 * Multi-step workflow with policy_check per step (codex P1.2 fold).
 * Mirrors a real bug-fix loop: assess → patch (gated) → regression test.
 */
export const W_BUG_FIX = multiStepWorkflow({
    id: 'W-bug-fix',
    preconditions: 'bug_report_input_received',
    postconditions: 'fix_pr_opened_with_regression_test',
    failure_policy: 'escalate',
    stringency: 'protocol',
    steps: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'pause', policy_check: false },
        { step_id: 2, action: 'spawn_sub_unit', inputs: [], outputs: [], on_failure: 'rollback', policy_check: true },
        { step_id: 3, action: 'wait', inputs: [], outputs: [], on_failure: 'escalate', policy_check: false },
    ],
});
export const W_ONE_ON_ONE_PREP = singleStepWorkflow({
    id: 'W-1on1-prep',
    preconditions: 'one_on_one_within_24h',
    postconditions: 'agenda_artifact_registered',
    failure_policy: 'continue',
    stringency: 'task',
});
export const W_RELATIONSHIP_CHECKIN = singleStepWorkflow({
    id: 'W-relationship-checkin',
    preconditions: 'contact_due_for_checkin',
    postconditions: 'message_drafted_for_review',
    failure_policy: 'continue',
    stringency: 'task',
});
/** Multi-step workflow with declared state (codex P1.2 fold). */
export const W_MONTHLY_FINANCE_REVIEW = multiStepWorkflow({
    id: 'W-monthly-finance-review',
    preconditions: 'first_5_days_of_month AND no_review_yet_this_month',
    postconditions: 'finance_summary_artifact_registered',
    failure_policy: 'pause',
    stringency: 'protocol',
    steps: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'pause' },
        { step_id: 2, action: 'spawn_sub_unit', inputs: [], outputs: [], on_failure: 'pause' },
        { step_id: 3, action: 'spawn_sub_unit', inputs: [], outputs: [], on_failure: 'continue' },
        { step_id: 4, action: 'wait', inputs: [], outputs: [], on_failure: 'escalate' },
    ],
});
export const W_LEARNING_SUMMARY = singleStepWorkflow({
    id: 'W-learning-summary',
    preconditions: 'sunday_evening AND no_summary_for_iso_week',
    postconditions: 'weekly_summary_artifact_registered',
    failure_policy: 'continue',
    stringency: 'process',
});
export const W_ONBOARDING_TOUR = singleStepWorkflow({
    id: 'W-onboarding-tour',
    preconditions: 'fresh_install_marker_present',
    postconditions: 'first_success_execution_recorded',
    failure_policy: 'pause',
    stringency: 'protocol',
});
export const W_ONBOARDING_CREATE_DOMAIN = singleStepWorkflow({
    id: 'W-onboarding-create-domain',
    preconditions: 'onboarding_step_create_domain',
    postconditions: 'first_user_domain_persisted',
    failure_policy: 'pause',
    stringency: 'process',
});
export const STARTER_WORKFLOWS = Object.freeze([
    W_MORNING_PULSE,
    W_EVENING_SHUTDOWN,
    W_FEATURE_BUILD,
    W_BUG_FIX,
    W_ONE_ON_ONE_PREP,
    W_RELATIONSHIP_CHECKIN,
    W_MONTHLY_FINANCE_REVIEW,
    W_LEARNING_SUMMARY,
    W_ONBOARDING_TOUR,
    W_ONBOARDING_CREATE_DOMAIN,
]);
// =============================================================================
// 5 TriggerSpecs — one per event_type alphabet that v1.0 supports + variety
// =============================================================================
export const T_MORNING_PULSE = {
    id: 'T-morning-pulse',
    event_type: 'cron',
    route_predicate: { type: 'always_true' },
    target_workflow: 'W-morning-pulse',
    domain_id: 'D1',
    charter_id: 'C-daily-pulse',
    description: 'Cron-fired morning pulse trigger; daily 07:00 local.',
};
/**
 * T-build-feature — codex P2.2 fold 2026-05-03: predicate narrowed.
 * Previous version matched ANY input containing 'add', which collided with
 * everyday phrases like "add to my calendar". Now requires both a build
 * verb AND a feature-noun keyword to fire.
 */
export const T_BUILD_FEATURE = {
    id: 'T-build-feature',
    event_type: 'founder_input',
    route_predicate: {
        type: 'and',
        clauses: [
            {
                type: 'or',
                clauses: [
                    { type: 'contains', value: 'build' },
                    { type: 'contains', value: 'implement' },
                    { type: 'contains', value: 'ship' },
                ],
            },
            {
                type: 'or',
                clauses: [
                    { type: 'contains', value: 'feature' },
                    { type: 'contains', value: 'product' },
                    { type: 'contains', value: 'endpoint' },
                    { type: 'contains', value: 'page' },
                ],
            },
        ],
    },
    target_workflow: 'W-feature-build',
    domain_id: 'D2',
    charter_id: 'C-build-product',
    description: 'Founder input mentioning a build verb AND a feature noun → feature workflow.',
};
export const T_BUG_FIX = {
    id: 'T-bug-fix',
    event_type: 'founder_input',
    route_predicate: {
        type: 'or',
        clauses: [
            { type: 'contains', value: 'fix the bug' },
            { type: 'contains', value: 'broken' },
            { type: 'contains', value: 'regression' },
        ],
    },
    target_workflow: 'W-bug-fix',
    domain_id: 'D2',
    charter_id: 'C-build-product',
    description: 'Founder input matching fix-the-bug/broken/regression → bug workflow.',
};
/**
 * T-onboarding — codex P1.1 fold 2026-05-03: switched from file_drop
 * (v1.1+ unimplemented) to founder_input so the "first founder input →
 * first SUCCESS Execution" path is genuinely runnable at v1.0. The
 * keyword set covers common first-touch phrases.
 */
export const T_ONBOARDING = {
    id: 'T-onboarding',
    event_type: 'founder_input',
    route_predicate: {
        type: 'or',
        clauses: [
            { type: 'contains', value: 'hello' },
            { type: 'contains', value: 'start' },
            { type: 'contains', value: 'begin' },
            { type: 'contains', value: 'onboard' },
            { type: 'contains', value: 'help me get started' },
        ],
    },
    target_workflow: 'W-onboarding-tour',
    domain_id: 'D1',
    charter_id: 'C-onboarding',
    description: 'Founder input matching first-touch phrases → onboarding tour (the "first SUCCESS" path).',
};
export const T_LEARNING_SUMMARY = {
    id: 'T-learning-summary',
    event_type: 'cron',
    route_predicate: { type: 'always_true' },
    target_workflow: 'W-learning-summary',
    domain_id: 'D5',
    charter_id: 'C-weekly-learning-loop',
    description: 'Sunday 19:00 local → weekly learning summary.',
};
export const STARTER_TRIGGERS = Object.freeze([
    T_MORNING_PULSE,
    T_BUILD_FEATURE,
    T_BUG_FIX,
    T_ONBOARDING,
    T_LEARNING_SUMMARY,
]);
// =============================================================================
// Workflow → Charter ownership map (codex P2.1 fold 2026-05-03)
//
// Native v1.0 doesn't model Workflow.charter_id directly on the Workflow
// primitive — Charter ownership is operationalized via L4 COMMITMENT
// at runtime. The starter kit makes the mapping explicit here so users
// + the contract test can see which Charter operationalizes each Workflow.
// =============================================================================
export const STARTER_WORKFLOW_CHARTER_MAP = new Map([
    [W_MORNING_PULSE.id, CHARTER_DAILY_PULSE.id],
    [W_EVENING_SHUTDOWN.id, CHARTER_DAILY_PULSE.id],
    [W_FEATURE_BUILD.id, CHARTER_BUILD_PRODUCT.id],
    [W_BUG_FIX.id, CHARTER_BUILD_PRODUCT.id],
    [W_ONE_ON_ONE_PREP.id, CHARTER_RELATIONSHIPS_TOUCHPOINTS.id],
    [W_RELATIONSHIP_CHECKIN.id, CHARTER_RELATIONSHIPS_TOUCHPOINTS.id],
    [W_MONTHLY_FINANCE_REVIEW.id, CHARTER_MONTHLY_FINANCE_REVIEW.id],
    [W_LEARNING_SUMMARY.id, CHARTER_WEEKLY_LEARNING_LOOP.id],
    [W_ONBOARDING_TOUR.id, CHARTER_ONBOARDING.id],
    [W_ONBOARDING_CREATE_DOMAIN.id, CHARTER_ONBOARDING.id],
]);
// =============================================================================
// Onboarding workflow (the primary "first SUCCESS Execution" path)
// =============================================================================
export const ONBOARDING_WORKFLOW = W_ONBOARDING_TOUR;
/** Returns the curated Native v1.0 starter kit (deep-frozen). */
export function loadStarterKit() {
    return Object.freeze({
        domains: STARTER_DOMAINS,
        charters: STARTER_CHARTERS,
        workflows: STARTER_WORKFLOWS,
        triggers: STARTER_TRIGGERS,
        onboarding: ONBOARDING_WORKFLOW,
    });
}
//# sourceMappingURL=index.js.map