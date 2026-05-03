/**
 * proposal-ledger — durable record of pattern → proposal → decision lifecycle.
 *
 * Required by SPEC v1.2 §4.2 and codex P1 finding "thing missed":
 * the H-Sutra connector replays the JSONL log from byte 0 on daemon start, so
 * without a durable ledger the same pattern would be re-proposed forever after
 * any restart.
 *
 * Storage layout (per-user, NOT shipped with plugin):
 *   $SUTRA_NATIVE_HOME/user-kit/proposals/<pattern_id>.json
 *
 * One JSON file per ProposalEntry; pattern_id is the filename.
 *
 * Status state machine: pending → approved | rejected. Once decided, the
 * entry is preserved (audit trail) but won't be re-proposed.
 */
import { type UserKitOptions } from './user-kit.js';
export type ProposalStatus = 'pending' | 'approved' | 'rejected';
export interface ProposalEntry {
    /** P-<sha8>; stable across restarts because derived from normalized_phrase. */
    readonly pattern_id: string;
    /** The normalized phrase the detector grouped on. */
    readonly normalized_phrase: string;
    /** How many input_text events matched the normalized phrase when proposed. */
    readonly evidence_count: number;
    /** First H-Sutra event ts that contributed to the pattern, in unix ms. */
    readonly first_seen_ms: number;
    /** Last H-Sutra event ts that contributed to the pattern, in unix ms. */
    readonly last_seen_ms: number;
    /** First few raw input_text samples for founder context (capped). */
    readonly utterance_samples: ReadonlyArray<string>;
    /** Proposed Workflow id (pre-creation; matches builder output). */
    readonly proposed_workflow_id: string;
    /** Proposed TriggerSpec id (pre-creation). */
    readonly proposed_trigger_id: string;
    /** Charter the proposal will attach to (default 'C-daily-pulse'). */
    readonly proposed_charter_id: string;
    /** Domain the proposal will attach to (default 'D1'). */
    readonly proposed_domain_id: string;
    /** Lifecycle. */
    readonly status: ProposalStatus;
    /** When the proposal was first written. */
    readonly proposed_at_ms: number;
    /** When approved/rejected; null while pending. */
    readonly decided_at_ms: number | null;
    /** Free-form reason on decision; null while pending. */
    readonly decision_reason: string | null;
}
export declare function isProposalEntry(value: unknown): value is ProposalEntry;
export declare function persistProposal(entry: ProposalEntry, opts?: UserKitOptions): string;
export declare function loadProposal(pattern_id: string, opts?: UserKitOptions): ProposalEntry | null;
export declare function listProposals(opts?: UserKitOptions, status_filter?: ProposalStatus): ProposalEntry[];
export declare function updateProposalStatus(pattern_id: string, next_status: 'approved' | 'rejected', decision_reason: string, opts?: UserKitOptions, now_ms?: number): ProposalEntry;
//# sourceMappingURL=proposal-ledger.d.ts.map