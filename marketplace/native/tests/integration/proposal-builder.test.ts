/**
 * Integration tests — proposal-builder.
 *
 * Covers SPEC v1.2 §4.4: built Workflow passes createWorkflow + isValidWorkflow,
 * built TriggerSpec passes isTriggerSpec, both reference existing C-daily-pulse + D1.
 */

import { describe, expect, it } from 'vitest'

import { buildProposal } from '../../src/runtime/proposal-builder.js'
import { isValidWorkflow } from '../../src/primitives/workflow.js'
import { isTriggerSpec } from '../../src/types/trigger-spec.js'
import type { DetectedPattern } from '../../src/runtime/pattern-detector.js'

function makePattern(): DetectedPattern {
  return {
    pattern_id: 'P-abcd1234',
    normalized_phrase: 'design partners track',
    evidence_count: 4,
    utterance_samples: [
      'I want to track design partners',
      'design partners outreach',
      'track design partners',
      'design partners again',
    ],
    first_seen_ms: 1700000000000,
    last_seen_ms: 1700000600000,
  }
}

describe('buildProposal', () => {
  it('produces a Workflow that passes isValidWorkflow', () => {
    const built = buildProposal(makePattern(), { now_ms: 1700001000000 })
    expect(isValidWorkflow(built.workflow)).toBe(true)
  })

  it('produces a TriggerSpec that passes isTriggerSpec', () => {
    const built = buildProposal(makePattern(), { now_ms: 1700001000000 })
    expect(isTriggerSpec(built.trigger)).toBe(true)
  })

  it('Workflow id matches W-emergent-<8hex> pattern', () => {
    const built = buildProposal(makePattern())
    expect(built.workflow.id).toBe('W-emergent-abcd1234')
  })

  it('TriggerSpec id matches T-emergent-<8hex> pattern', () => {
    const built = buildProposal(makePattern())
    expect(built.trigger.id).toBe('T-emergent-abcd1234')
  })

  it('TriggerSpec.target_workflow references the Workflow id', () => {
    const built = buildProposal(makePattern())
    expect(built.trigger.target_workflow).toBe(built.workflow.id)
  })

  it('defaults attach to C-daily-pulse + D1', () => {
    const built = buildProposal(makePattern())
    expect(built.trigger.charter_id).toBe('C-daily-pulse')
    expect(built.trigger.domain_id).toBe('D1')
    expect(built.entry.proposed_charter_id).toBe('C-daily-pulse')
    expect(built.entry.proposed_domain_id).toBe('D1')
  })

  it('honors override charter + domain', () => {
    const built = buildProposal(makePattern(), {
      default_charter_id: 'C-build-product',
      default_domain_id: 'D2',
    })
    expect(built.trigger.charter_id).toBe('C-build-product')
    expect(built.trigger.domain_id).toBe('D2')
  })

  it('TriggerSpec predicate is AND of contains over every content token (codex master P1 fold)', () => {
    const built = buildProposal(makePattern())
    expect(built.trigger.route_predicate.type).toBe('and')
    if (built.trigger.route_predicate.type === 'and') {
      const clauses = built.trigger.route_predicate.clauses
      const tokens = clauses
        .map((c) => (c.type === 'contains' ? c.value : ''))
        .sort()
      expect(tokens).toEqual(['design', 'partners', 'track'])
      for (const c of clauses) {
        expect(c.type).toBe('contains')
        if (c.type === 'contains') expect(c.case_sensitive).toBe(false)
      }
    }
  })

  it('single-token normalized phrase yields a single contains predicate', () => {
    const built = buildProposal({
      pattern_id: 'P-11111111',
      normalized_phrase: 'pipeline',
      evidence_count: 4,
      utterance_samples: ['pipeline'],
      first_seen_ms: 0,
      last_seen_ms: 0,
    })
    expect(built.trigger.route_predicate.type).toBe('contains')
    if (built.trigger.route_predicate.type === 'contains') {
      expect(built.trigger.route_predicate.value).toBe('pipeline')
    }
  })

  it('Workflow step_graph is a single wait step', () => {
    const built = buildProposal(makePattern())
    expect(built.workflow.step_graph).toHaveLength(1)
    expect(built.workflow.step_graph[0].action).toBe('wait')
  })

  it('ProposalEntry status starts at pending', () => {
    const built = buildProposal(makePattern(), { now_ms: 1700001000000 })
    expect(built.entry.status).toBe('pending')
    expect(built.entry.proposed_at_ms).toBe(1700001000000)
    expect(built.entry.decided_at_ms).toBeNull()
    expect(built.entry.decision_reason).toBeNull()
  })

  it('ProposalEntry preserves pattern provenance', () => {
    const p = makePattern()
    const built = buildProposal(p)
    expect(built.entry.pattern_id).toBe(p.pattern_id)
    expect(built.entry.normalized_phrase).toBe(p.normalized_phrase)
    expect(built.entry.evidence_count).toBe(p.evidence_count)
    expect(built.entry.utterance_samples).toEqual(p.utterance_samples)
    expect(built.entry.first_seen_ms).toBe(p.first_seen_ms)
    expect(built.entry.last_seen_ms).toBe(p.last_seen_ms)
  })
})
