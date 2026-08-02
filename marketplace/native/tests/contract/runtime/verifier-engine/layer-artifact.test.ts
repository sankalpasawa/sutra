/**
 * Tier-2 artifact layer tests (strict v1 grammar).
 *
 * Slug fixes applied vs plan source (SLUG lowercases input):
 *   - 'must-include-Hosting' -> 'must-include-hosting'
 *   - '5-pates' (plan typo) -> '5-pages'
 *   - 'evidence/tech/Hosting' -> 'evidence/tech/hosting'
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 * Plan: docs/superpowers/plans/2026-05-07-verifier-engine-v1.md Task 8
 */

import { describe, it, expect } from 'vitest'
import { runTier2Artifact } from '../../../../src/runtime/verifier-engine/contract-verifier/layer-artifact.js'
import type { GoalContract } from '../../../../src/types/goal-contract.js'
import type { NativeRun } from '../../../../src/types/assertion-report.js'

const c = (over: Partial<GoalContract> = {}): GoalContract => ({
  situation: 's',
  motivation: 'm',
  outcome: 'o',
  beneficiary: 'self',
  hard_constraints: [],
  non_goals: [],
  acceptance_examples: [],
  evidence_required: [],
  execution_preferences: {},
  confidence: 0.9,
  ambiguity_flags: [],
  clarification_required: false,
  ...over,
})

const run = (artifacts: { stage: string; content: string }[]): NativeRun => ({
  run_id: 'r',
  scenario_id: 's',
  events: [],
  artifacts: artifacts.map(a => ({ ...a, path: `${a.stage}.md`, sha256: 'x' })),
})

describe('runTier2Artifact (strict v1 grammar)', () => {
  it('forbid pattern PASS when term absent', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['no ads'] }),
      run([{ stage: 'tech', content: 'No ads will be displayed.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/no-ads')!.status).toBe('PASS')
  })

  it('forbid pattern FAIL when term present in positive context', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['no ads'] }),
      run([{ stage: 'tech', content: 'Monetize via ad-supported tier with display ads.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/no-ads')!.status).toBe('FAIL')
  })

  it('require pattern PASS when term present', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['must include §Hosting'] }),
      run([{ stage: 'tech', content: '## §Hosting\nVercel.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/must-include-hosting')!.status).toBe('PASS')
  })

  it('count pattern PASS when literal "5 pages" appears', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['5 pages'] }),
      run([{ stage: 'tech', content: 'The site has 5 pages: ...' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/5-pages')!.status).toBe('PASS')
  })

  it('count pattern FAIL when count missing', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['5 pages'] }),
      run([{ stage: 'tech', content: 'The site has six pages.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/5-pages')!.status).toBe('FAIL')
  })

  it('count pattern PASS with "exactly N unit" prefix', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['exactly 5 pages'] }),
      run([{ stage: 'tech', content: 'The site has 5 pages.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/hard-constraint/exactly-5-pages')!.status).toBe('PASS')
  })

  it('non-grammar constraint emits SKIPPED deferred-to-rubric', () => {
    const r = runTier2Artifact(
      c({ hard_constraints: ['shipping plan fits 4-week timeline'] }),
      run([{ stage: 'tech', content: '4 weeks shipping.' }]),
    )
    const ids = r.map(x => x.id)
    expect(ids.some(id => id.startsWith('tier-2/constraint-deferred-to-rubric/'))).toBe(true)
  })

  it('non_goals FAIL when violated', () => {
    const r = runTier2Artifact(
      c({ non_goals: ['e-commerce checkout'] }),
      run([{ stage: 'tech', content: 'Add Stripe e-commerce checkout flow.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/non-goal/e-commerce-checkout')!.status).toBe('FAIL')
  })

  it('evidence_required PASS when section header present', () => {
    const r = runTier2Artifact(
      c({ evidence_required: [{ stage: 'tech', field: '§Hosting' }] }),
      run([{ stage: 'tech', content: '## §Hosting\nDeploy to Vercel.' }]),
    )
    expect(r.find(x => x.id === 'tier-2/evidence/tech/hosting')!.status).toBe('PASS')
  })

  it('cross-stage propagation uses first-paragraph only', () => {
    const r = runTier2Artifact(
      c(),
      run([
        { stage: 'vision', content: 'A pet showcase site for pet owners.\n\nMore detail later.' },
        { stage: 'prd', content: 'PRD for the pet showcase site. Pet owners visit.\n\n(other content)' },
      ]),
    )
    expect(r.find(x => x.id === 'tier-2/cross-stage-drift')!.status).toBe('PASS')
  })

  it('cross-stage FAIL when first paragraphs share no tokens', () => {
    const r = runTier2Artifact(
      c(),
      run([
        { stage: 'vision', content: 'unrelated alpha bravo.\n\nfiller.' },
        { stage: 'prd', content: 'completely different gamma delta.\n\nfiller.' },
      ]),
    )
    expect(r.find(x => x.id === 'tier-2/cross-stage-drift')!.status).toBe('FAIL')
  })
})
