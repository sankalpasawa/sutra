// tests/e2e/verifier-engine-pets-site-broken.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { VerifierEngine, generateUtterance } from '../../src/runtime/verifier-engine/index.js'
import type { UserProfile, Scenario } from '../../src/types/user-profile.js'

const SCENARIO_DIR = resolve(__dirname, 'scenarios/pets-site')
const PROFILES_DIR = resolve(__dirname, 'user-profiles')
const profile = JSON.parse(readFileSync(resolve(PROFILES_DIR, 'pet-owner-casual.json'), 'utf8')) as UserProfile
const scenario = JSON.parse(readFileSync(resolve(SCENARIO_DIR, 'scenario.json'), 'utf8')) as Scenario
const goldenContract = readFileSync(resolve(SCENARIO_DIR, 'contract.golden.json'), 'utf8')

describe('Verifier Engine v1 — pets-site broken-fixture E2E (AC §9.6 — failure surface)', () => {
  it('profile-driven utterance + broken fixtures -> FAIL on Constraint-Honor', async () => {
    const utterance = generateUtterance(profile, scenario)
    const engine = new VerifierEngine({
      llm: async () => goldenContract,
      judge: async () => JSON.stringify({
        'Outcome-Fidelity':    { score: 4, max: 5, evidence: 'mostly captured' },
        'Constraint-Honor':    { score: 1, max: 5, evidence: 'tech-spec violates non_goal e-commerce-checkout' },
        'Cross-Stage-Drift':   { score: 4, max: 5, evidence: 'mostly consistent' },
        'Acceptance-Coverage': { score: 4, max: 5, evidence: 'partial' },
      }),
    })
    const contract = await engine.extract(utterance)
    const artifactsDir = resolve(SCENARIO_DIR, 'artifacts.broken-fixture')
    const artifacts = readdirSync(artifactsDir).map(f => ({
      stage: f.replace(/\.md$/, ''), path: f,
      content: readFileSync(resolve(artifactsDir, f), 'utf8'), sha256: 'broken-fixture',
    }))
    const run = {
      run_id: 'pets-site-broken', scenario_id: 'pets-site',
      events: [{ type: 'utterance', ts: 0, payload: utterance }],
      artifacts,
    }
    const report = await engine.verify(contract, run)

    // Verdict must be FAIL — non_goal e-commerce-checkout violated
    expect(report.verdict).toBe('FAIL')
    const violations = report.results.filter(r =>
      r.tier === 'artifact' && r.id.includes('non-goal/e-commerce-checkout') && r.status === 'FAIL'
    )
    expect(violations.length).toBeGreaterThanOrEqual(1)

    // Tier-1 still PASS (contract well-formed)
    expect(report.results.filter(r => r.tier === 'schema').every(r => r.status === 'PASS')).toBe(true)

    const out = engine.format(report, utterance, run)
    console.log('\n=== TRANSCRIPT ===\n' + out.transcript)
    console.log('\n=== REPORT ===\n' + out.report)
  })
})
