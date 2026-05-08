/**
 * Contract tests — extraction prompt (Verifier Engine v1, Wave 3.1).
 *
 * Coverage:
 *   - frozen prompt contains every canonical Goal Contract field
 *   - prompt asks for JSON-only output
 *   - buildExtractionPrompt embeds the user utterance + carries the prompt
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §6
 */

import { describe, it, expect } from 'vitest'
import {
  CONTRACT_EXTRACTION_PROMPT,
  buildExtractionPrompt,
} from '../../../../src/runtime/verifier-engine/contract-extractor/prompt.js'

describe('CONTRACT_EXTRACTION_PROMPT', () => {
  it('contains all required output fields', () => {
    for (const field of [
      'situation',
      'motivation',
      'outcome',
      'beneficiary',
      'hard_constraints',
      'non_goals',
      'acceptance_examples',
      'evidence_required',
      'execution_preferences',
      'confidence',
      'ambiguity_flags',
      'clarification_required',
    ]) {
      expect(CONTRACT_EXTRACTION_PROMPT).toContain(field)
    }
  })

  it('asks for JSON-only output', () => {
    expect(CONTRACT_EXTRACTION_PROMPT.toLowerCase()).toContain('json')
  })

  it('buildExtractionPrompt embeds the utterance', () => {
    const p = buildExtractionPrompt('I want a website for my pets')
    expect(p).toContain('I want a website for my pets')
    expect(p).toContain(CONTRACT_EXTRACTION_PROMPT)
  })
})
