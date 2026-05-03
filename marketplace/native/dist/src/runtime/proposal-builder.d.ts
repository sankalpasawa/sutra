/**
 * proposal-builder — turn a DetectedPattern into a registrable bundle:
 * (Workflow + TriggerSpec + ProposalEntry) attached to an existing Charter.
 *
 * SPEC v1.2 §4.4. The Workflow is a skeleton with a single `wait` step
 * (the only no-op-equivalent valid action per workflow.ts:50). Founder edits
 * step_graph after registration via the existing CLI. The TriggerSpec uses
 * `contains` over input_text (the actual primitive's matching surface — not
 * a normalized phrase, per codex P2.3).
 *
 * Defaults match the v1.1.0 starter kit: D1 Personal OS / C-daily-pulse.
 */
import { type Workflow } from '../primitives/workflow.js';
import type { TriggerSpec } from '../types/trigger-spec.js';
import type { ProposalEntry } from '../persistence/proposal-ledger.js';
import type { DetectedPattern } from './pattern-detector.js';
export interface BuildProposalOptions {
    /** Charter id the proposal attaches to. Default 'C-daily-pulse'. */
    readonly default_charter_id?: string;
    /** Domain id the proposal attaches to. Default 'D1'. */
    readonly default_domain_id?: string;
    /** Override proposed_at_ms for deterministic tests. */
    readonly now_ms?: number;
}
export interface BuiltProposal {
    readonly entry: ProposalEntry;
    readonly workflow: Workflow;
    readonly trigger: TriggerSpec;
}
export declare function buildProposal(pattern: DetectedPattern, opts?: BuildProposalOptions): BuiltProposal;
//# sourceMappingURL=proposal-builder.d.ts.map