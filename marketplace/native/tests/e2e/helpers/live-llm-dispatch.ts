// tests/e2e/helpers/live-llm-dispatch.ts
//
// Live LLM dispatch — wraps `claude --bare` subprocess for E2E tests.
//
// Per SPEC §C8: native uses claude --bare (no @anthropic-ai/sdk).
// This helper produces a function-shaped LLMDispatch suitable for
// VerifierEngine constructor.
//
// Env-gated: only used when LIVE_LLM=1. CI keeps fixture mode.

import { execSync } from 'node:child_process'
import type { LLMDispatch } from '../../../src/runtime/verifier-engine/index.js'

export function makeLiveDispatch(label: string): LLMDispatch {
  return async (prompt: string): Promise<string> => {
    console.log(`\n>>> [${label}] LLM CALL — prompt length ${prompt.length} chars`)
    console.log(`>>> [${label}] PROMPT:\n${prompt}`)
    const result = execSync(`claude -p`, {
      input: prompt,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      timeout: 180_000,
    })
    console.log(`>>> [${label}] LLM RESPONSE (${result.length} chars):`)
    console.log(result)
    return result
  }
}

/**
 * Generate one artifact per stage via live LLM. Each stage's prompt
 * pulls in the prior stage's content for cross-stage propagation.
 */
export async function generateArtifactsLive(
  utterance: string,
  contract: unknown,
  stages: readonly string[],
): Promise<{ stage: string; path: string; content: string; sha256: string }[]> {
  const artifacts: { stage: string; path: string; content: string; sha256: string }[] = []
  for (const stage of stages) {
    const priorContext = artifacts.map(a => `## Prior: ${a.stage}\n${a.content}`).join('\n\n')
    const prompt = `
You are producing the "${stage}" artifact for a project pipeline.

User utterance: "${utterance}"
GoalContract:
${JSON.stringify(contract, null, 2)}

${priorContext ? `Prior stages:\n${priorContext}\n\n` : ''}Output ONLY the markdown content of ${stage}.md. No prose around it.

Required for ${stage} stage:
${stagePrompt(stage)}
`.trim()

    console.log(`\n>>> [stage:${stage}] LLM CALL — generating ${stage}.md`)
    const content = execSync(`claude -p`, {
      input: prompt,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      timeout: 180_000,
    })
    console.log(`>>> [stage:${stage}] LLM RESPONSE (${content.length} chars):`)
    console.log(content)

    artifacts.push({ stage, path: `${stage}.md`, content, sha256: 'live' })
  }
  return artifacts
}

function stagePrompt(stage: string): string {
  switch (stage) {
    case 'vision':
      return '- Title with "# Vision — ..."\n- 1-paragraph summary\n- Themes section with bullet list\n- Include the phrase "pet content is the first visible thing"'
    case 'prd':
      return '- Title with "# PRD — ..."\n- ## Problem section\n- ## Users section\n- Include phrase "pet content is the first visible thing"'
    case 'design':
      return '- Title with "# Design Brief — ..."\n- ## §Visual-direction section (literal §)\n- Include "pet content is the first visible thing"\n- DO NOT mention "e-commerce checkout" or "service-booking platform" (forbidden)'
    case 'tech':
      return '- Title with "# Tech Spec — ..."\n- ## Stack section\n- ## §Hosting-plan section (literal §)\n- ## Out of scope section\n- Include "pet content is the first visible thing"\n- DO NOT mention "e-commerce checkout" or "service-booking platform" (forbidden)'
    default:
      return ''
  }
}
