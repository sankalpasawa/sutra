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

  it('rejects execution_preferences=null and array', async () => {
    const withNull = JSON.stringify({ ...JSON.parse(VALID), execution_preferences: null })
    const withArr  = JSON.stringify({ ...JSON.parse(VALID), execution_preferences: [] })
    await expect(extract('test', async () => withNull, { max_retries: 0 })).rejects.toThrow(/execution_preferences/i)
    await expect(extract('test', async () => withArr,  { max_retries: 0 })).rejects.toThrow(/execution_preferences/i)
  })

  it('rejects null situation field', async () => {
    const bad = JSON.stringify({ ...JSON.parse(VALID), situation: null })
    await expect(extract('test', async () => bad, { max_retries: 0 })).rejects.toThrow(/situation.*string/i)
  })

  it('rejects confidence out of range', async () => {
    const bad = JSON.stringify({ ...JSON.parse(VALID), confidence: 1.5 })
    await expect(extract('test', async () => bad, { max_retries: 0 })).rejects.toThrow(/confidence.*0.*1/i)
  })

  it('rejects acceptance_examples with missing field', async () => {
    const bad = JSON.stringify({ ...JSON.parse(VALID), acceptance_examples: [{ given: 'x', when: 'y' }] })  // missing then
    await expect(extract('test', async () => bad, { max_retries: 0 })).rejects.toThrow(/acceptance_examples.*then/i)
  })

  it('rejects evidence_required with non-string stage', async () => {
    const bad = JSON.stringify({ ...JSON.parse(VALID), evidence_required: [{ stage: 42, field: 'x' }] })
    await expect(extract('test', async () => bad, { max_retries: 0 })).rejects.toThrow(/evidence_required.*stage/i)
  })
})
