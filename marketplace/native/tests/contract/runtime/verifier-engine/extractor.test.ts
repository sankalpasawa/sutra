import { describe, it, expect } from 'vitest'
import { extract, type LLMDispatch }
  from '../../../../src/runtime/verifier-engine/contract-extractor/extractor.js'

const VALID = JSON.stringify({
  situation: 'pets owner', motivation: 'showcase pets',
  outcome: 'public site live', beneficiary: 'self',
  hard_constraints: [], non_goals: [],
  acceptance_examples: [{ given: 'site live', when: 'visitor opens', then: 'sees pets' }],
  evidence_required: [{ stage: 'tech', field: '§Hosting' }],
  execution_preferences: { voice: 'first-person' },
  confidence: 0.8, ambiguity_flags: [], clarification_required: false,
})

describe('extract', () => {
  it('returns typed GoalContract on valid JSON response', async () => {
    const llm: LLMDispatch = async () => VALID
    const c = await extract('I want a website for my pets', llm)
    expect(c.beneficiary).toBe('self')
    expect(c.confidence).toBe(0.8)
  })

  it('strips markdown fences if present', async () => {
    const llm: LLMDispatch = async () => '```json\n' + VALID + '\n```'
    const c = await extract('test', llm)
    expect(c.outcome).toBe('public site live')
  })

  it('retries with validation error message on bad JSON; succeeds on second try', async () => {
    const responses = ['not json at all', VALID]
    let i = 0
    const seen: string[] = []
    const llm: LLMDispatch = async (p) => { seen.push(p); return responses[i++] }
    const c = await extract('test', llm, { max_retries: 2 })
    expect(c.confidence).toBe(0.8)
    expect(seen[1]).toContain('PREVIOUS ATTEMPT FAILED')
  })

  it('throws after exhausting retries', async () => {
    const llm: LLMDispatch = async () => 'still not json'
    await expect(extract('test', llm, { max_retries: 1 })).rejects.toThrow(/extraction.*failed/i)
  })

  it('passes utterance into the prompt', async () => {
    let prompt_seen = ''
    const llm: LLMDispatch = async (p) => { prompt_seen = p; return VALID }
    await extract('build a meditation app', llm)
    expect(prompt_seen).toContain('build a meditation app')
  })
})
