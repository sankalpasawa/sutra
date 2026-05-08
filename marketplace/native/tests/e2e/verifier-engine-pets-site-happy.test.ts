// tests/e2e/verifier-engine-pets-site-happy.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { VerifierEngine, generateUtterance } from '../../src/runtime/verifier-engine/index.js'
import type { UserProfile, Scenario } from '../../src/types/user-profile.js'
import { makeLiveDispatch, generateArtifactsLive } from './helpers/live-llm-dispatch.js'

const LIVE = process.env.LIVE_LLM === '1'

const SCENARIO_DIR = resolve(__dirname, 'scenarios/pets-site')
const PROFILES_DIR = resolve(__dirname, 'user-profiles')

const profile = JSON.parse(readFileSync(resolve(PROFILES_DIR, 'pet-owner-casual.json'), 'utf8')) as UserProfile
const scenario = JSON.parse(readFileSync(resolve(SCENARIO_DIR, 'scenario.json'), 'utf8')) as Scenario
const goldenContract = readFileSync(resolve(SCENARIO_DIR, 'contract.golden.json'), 'utf8')

describe('Verifier Engine v1 — pets-site happy-path E2E (AC §9.5)', () => {
  it('profile-driven utterance + happy fixtures -> PASS verdict + transcript + report', async () => {
    const utterance = generateUtterance(profile, scenario)
    expect(utterance).toBe('I want a website for my pets')

    const engine = new VerifierEngine({
      llm: LIVE ? makeLiveDispatch('extract') : async () => goldenContract,
      judge: LIVE ? makeLiveDispatch('judge') : async () => JSON.stringify({
        'Outcome-Fidelity': { score: 4, max: 5, evidence: 'pet showcase outcome captured' },
        'Constraint-Honor': { score: 5, max: 5, evidence: 'no hard constraints, non-goals honored' },
        'Cross-Stage-Drift': { score: 5, max: 5, evidence: 'pet showcase consistent across stages' },
        'Acceptance-Coverage': { score: 5, max: 5, evidence: 'visitor sees pets met' },
      }),
    })

    const contract = await engine.extract(utterance)
    if (!LIVE) expect(contract.beneficiary).toContain('self')

    const stages = ['vision','prd','design','tech'] as const
    const artifacts = LIVE
      ? await generateArtifactsLive(utterance, contract, stages)
      : readdirSync(resolve(SCENARIO_DIR, 'artifacts.fixture')).map(f => ({
          stage: f.replace(/\.md$/, ''),
          path: f,
          content: readFileSync(resolve(SCENARIO_DIR, 'artifacts.fixture', f), 'utf8'),
          sha256: 'fixture',
        }))
    const run = {
      run_id: 'pets-site-happy', scenario_id: 'pets-site',
      events: [
        { type: 'utterance', ts: 0, payload: utterance },
        { type: 'trigger_fired', ts: 100 },
        { type: 'artifact_emitted', ts: 5000, payload: { stage: 'vision' } },
      ],
      artifacts,
    }

    const report = await engine.verify(contract, run)
    if (!LIVE) {
      expect(report.verdict).toBe('PASS')
    } else {
      console.log(`\n>>> LIVE MODE verdict: ${report.verdict}`)
    }

    const out = engine.format(report, utterance, run)
    expect(out.transcript).toContain('USER')
    expect(out.transcript).toContain('I want a website for my pets')
    if (!LIVE) expect(out.report).toContain('VERDICT: PASS')

    // AC §9.5 — print BOTH sides:
    //   USER INPUT (what user typed) + LLM CAPTURED INTENT (extractor output)
    //   + LLM GENERATED ARTIFACTS (per-stage content) + VERIFIER REPORT.
    console.log('\n=== USER INPUT ===')
    console.log(`> ${utterance}`)
    console.log('\n=== LLM CAPTURED INTENT (GoalContract) ===')
    console.log(JSON.stringify(contract, null, 2))
    console.log('\n=== LLM GENERATED ARTIFACTS ===')
    for (const a of artifacts) {
      console.log(`\n--- ${a.stage}.md (${a.content.length} chars) ---`)
      console.log(a.content)
    }
    console.log('\n=== EVENT TRANSCRIPT ===\n' + out.transcript)
    console.log('\n=== VERIFIER REPORT ===\n' + out.report)
  })
})
