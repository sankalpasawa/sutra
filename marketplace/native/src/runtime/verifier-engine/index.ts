/**
 * VerifierEngine — top-level orchestrator. Wires extractor + verifier +
 * reporter. Constructor takes injectable LLM dispatch + judge dispatch
 * for testability and reuse across Sutra surfaces.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §4
 */

import type { GoalContract } from '../../types/goal-contract.js'
import type { AssertionReport, NativeRun } from '../../types/assertion-report.js'
import { extract, type LLMDispatch } from './contract-extractor/extractor.js'
import { verify } from './contract-verifier/verifier.js'
import { type JudgeDispatch } from './contract-verifier/layer-rubric.js'
import { formatReport, formatTranscript } from './contract-reporter/reporter.js'

export interface VerifierEngineConfig {
  readonly llm: LLMDispatch
  readonly judge: JudgeDispatch
  readonly max_extract_retries?: number
}

export class VerifierEngine {
  constructor(private readonly cfg: VerifierEngineConfig) {}

  extract(utterance: string): Promise<GoalContract> {
    return extract(utterance, this.cfg.llm, { max_retries: this.cfg.max_extract_retries })
  }

  verify(contract: GoalContract, run: NativeRun): Promise<AssertionReport> {
    return verify(contract, run, { judge: this.cfg.judge })
  }

  format(report: AssertionReport, utterance: string, run: NativeRun) {
    return {
      transcript: formatTranscript(utterance, run),
      report: formatReport(report),
    }
  }
}

export type { GoalContract } from '../../types/goal-contract.js'
export type { AssertionReport, AssertionResult, NativeRun } from '../../types/assertion-report.js'
export type { UserProfile, Scenario } from '../../types/user-profile.js'
export type { LLMDispatch, JudgeDispatch }
export { generateUtterance } from './user-simulator/generate-utterance.js'
