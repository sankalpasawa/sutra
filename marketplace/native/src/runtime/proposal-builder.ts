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

import { createWorkflow, type Workflow } from '../primitives/workflow.js'
import type { Predicate, TriggerSpec } from '../types/trigger-spec.js'
import type { ProposalEntry } from '../persistence/proposal-ledger.js'
import type { DetectedPattern } from './pattern-detector.js'

export interface BuildProposalOptions {
  /** Charter id the proposal attaches to. Default 'C-daily-pulse'. */
  readonly default_charter_id?: string
  /** Domain id the proposal attaches to. Default 'D1'. */
  readonly default_domain_id?: string
  /** Override proposed_at_ms for deterministic tests. */
  readonly now_ms?: number
}

export interface BuiltProposal {
  readonly entry: ProposalEntry
  readonly workflow: Workflow
  readonly trigger: TriggerSpec
}

/**
 * Build the predicate from a normalized phrase. Codex P1 fold (master review):
 * single-token `contains` was too broad and would route unrelated future
 * input. v2 requires ALL content tokens to be present (any order, anywhere)
 * via an AND of `contains` clauses. For a 1-token phrase this collapses to a
 * single contains; for 0 tokens we fall back to always_true (caller already
 * guards against empty normalized phrases via detector dedup).
 */
function buildPredicate(normalized_phrase: string): Predicate {
  const tokens = normalized_phrase.split(/\s+/).filter((t) => t.length > 0)
  if (tokens.length === 0) {
    return { type: 'always_true' }
  }
  if (tokens.length === 1) {
    return { type: 'contains', value: tokens[0], case_sensitive: false }
  }
  return {
    type: 'and',
    clauses: tokens.map((t) => ({
      type: 'contains',
      value: t,
      case_sensitive: false,
    })),
  }
}

export function buildProposal(
  pattern: DetectedPattern,
  opts: BuildProposalOptions = {},
): BuiltProposal {
  const charter_id = opts.default_charter_id ?? 'C-daily-pulse'
  const domain_id = opts.default_domain_id ?? 'D1'
  const now_ms = opts.now_ms ?? Date.now()

  const workflow_id = `W-emergent-${pattern.pattern_id.slice(2)}`
  const trigger_id = `T-emergent-${pattern.pattern_id.slice(2)}`

  // Skeleton Workflow — single 'wait' step. Founder edits step_graph after
  // registration via existing CLI. createWorkflow validates everything.
  const workflow: Workflow = createWorkflow({
    id: workflow_id,
    preconditions: `founder_input_matches_pattern_${pattern.pattern_id}`,
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'continue',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'emergent_workflow_skeleton_complete',
    failure_policy: 'continue',
    stringency: 'process',
    interfaces_with: [],
  })

  const trigger: TriggerSpec = {
    id: trigger_id,
    event_type: 'founder_input',
    route_predicate: buildPredicate(pattern.normalized_phrase),
    target_workflow: workflow_id,
    domain_id,
    charter_id,
    description: `Emergent (proposed from pattern ${pattern.pattern_id}; "${pattern.normalized_phrase.slice(0, 60)}")`,
  }

  const entry: ProposalEntry = {
    pattern_id: pattern.pattern_id,
    normalized_phrase: pattern.normalized_phrase,
    evidence_count: pattern.evidence_count,
    first_seen_ms: pattern.first_seen_ms,
    last_seen_ms: pattern.last_seen_ms,
    utterance_samples: [...pattern.utterance_samples],
    proposed_workflow_id: workflow_id,
    proposed_trigger_id: trigger_id,
    proposed_charter_id: charter_id,
    proposed_domain_id: domain_id,
    status: 'pending',
    proposed_at_ms: now_ms,
    decided_at_ms: null,
    decision_reason: null,
  }

  return { entry, workflow, trigger }
}
