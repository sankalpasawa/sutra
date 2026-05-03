/**
 * Contract test — Native v1.0 Starter Kit (D3 of NPD productization).
 *
 * Validates every starter Domain / Charter / Workflow / TriggerSpec
 * through the same isValid* helpers + Router boundary that production
 * code uses. If a primitive shape ever drifts (M+ engine refactor), the
 * starter kit will fail this test before users hit the broken example.
 *
 * Coverage:
 *   - 5 Domains validate via isValidDomain
 *   - 6 Charters validate via isValidCharter
 *   - 10 Workflows validate via isValidWorkflow
 *   - 5 TriggerSpecs validate via isTriggerSpec (and Router.registerTrigger
 *     accepts each in a fresh registry — proves they round-trip through
 *     the actual entry point)
 *   - loadStarterKit() returns deep-frozen snapshots
 *   - count discipline: spec'd 5/6/10/5/1 counts hold
 */

import { describe, it, expect } from 'vitest'
import {
  loadStarterKit,
  STARTER_DOMAINS,
  STARTER_CHARTERS,
  STARTER_WORKFLOWS,
  STARTER_TRIGGERS,
  STARTER_WORKFLOW_CHARTER_MAP,
  ONBOARDING_WORKFLOW,
} from '../../../src/starter-kit/index.js'
import { isValidDomain } from '../../../src/primitives/domain.js'
import { isValidCharter } from '../../../src/primitives/charter.js'
import { isValidWorkflow } from '../../../src/primitives/workflow.js'
import { Router } from '../../../src/runtime/router.js'
import { isTriggerSpec } from '../../../src/types/trigger-spec.js'

describe('Starter kit — count discipline', () => {
  it('ships exactly 5 Domains', () => {
    expect(STARTER_DOMAINS).toHaveLength(5)
  })

  it('ships exactly 6 Charters', () => {
    expect(STARTER_CHARTERS).toHaveLength(6)
  })

  it('ships exactly 10 Workflows', () => {
    expect(STARTER_WORKFLOWS).toHaveLength(10)
  })

  it('ships exactly 5 TriggerSpecs', () => {
    expect(STARTER_TRIGGERS).toHaveLength(5)
  })

  it('exports an onboarding Workflow', () => {
    expect(ONBOARDING_WORKFLOW).toBeDefined()
    expect(ONBOARDING_WORKFLOW.id).toBe('W-onboarding-tour')
  })
})

describe('Starter kit — Domains validate', () => {
  for (const d of STARTER_DOMAINS) {
    it(`Domain ${d.id} (${d.name}) passes isValidDomain`, () => {
      expect(isValidDomain(d)).toBe(true)
    })
  }

  it('all Domain ids are unique', () => {
    const ids = STARTER_DOMAINS.map((d) => d.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('all Domains belong to the default tenant', () => {
    for (const d of STARTER_DOMAINS) {
      expect(d.tenant_id).toBe('T-default')
    }
  })
})

describe('Starter kit — Charters validate', () => {
  for (const c of STARTER_CHARTERS) {
    it(`Charter ${c.id} (${c.purpose.slice(0, 40)}…) passes isValidCharter`, () => {
      expect(isValidCharter(c)).toBe(true)
    })
  }

  it('all Charter ids are unique', () => {
    const ids = STARTER_CHARTERS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every Charter has at least one obligation + one invariant', () => {
    for (const c of STARTER_CHARTERS) {
      expect(c.obligations.length).toBeGreaterThan(0)
      expect(c.invariants.length).toBeGreaterThan(0)
    }
  })

  it('every Charter declares ACL with at least one entry', () => {
    for (const c of STARTER_CHARTERS) {
      expect(c.acl.length).toBeGreaterThan(0)
    }
  })
})

describe('Starter kit — Workflows validate', () => {
  for (const w of STARTER_WORKFLOWS) {
    it(`Workflow ${w.id} passes isValidWorkflow`, () => {
      expect(isValidWorkflow(w)).toBe(true)
    })
  }

  it('all Workflow ids are unique', () => {
    const ids = STARTER_WORKFLOWS.map((w) => w.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every Workflow has a non-empty step_graph', () => {
    for (const w of STARTER_WORKFLOWS) {
      expect(w.step_graph.length).toBeGreaterThan(0)
    }
  })
})

describe('Starter kit — TriggerSpecs validate AND register through Router', () => {
  for (const t of STARTER_TRIGGERS) {
    it(`TriggerSpec ${t.id} passes isTriggerSpec`, () => {
      expect(isTriggerSpec(t)).toBe(true)
    })
  }

  it('all TriggerSpec ids are unique', () => {
    const ids = STARTER_TRIGGERS.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every trigger.target_workflow exists in the starter Workflows', () => {
    const wfIds = new Set(STARTER_WORKFLOWS.map((w) => w.id))
    for (const t of STARTER_TRIGGERS) {
      expect(wfIds.has(t.target_workflow)).toBe(true)
    }
  })

  it('every trigger.domain_id (when set) exists in the starter Domains', () => {
    const dIds = new Set(STARTER_DOMAINS.map((d) => d.id))
    for (const t of STARTER_TRIGGERS) {
      if (t.domain_id) expect(dIds.has(t.domain_id)).toBe(true)
    }
  })

  it('every trigger.charter_id (when set) exists in the starter Charters', () => {
    const cIds = new Set(STARTER_CHARTERS.map((c) => c.id))
    for (const t of STARTER_TRIGGERS) {
      if (t.charter_id) expect(cIds.has(t.charter_id)).toBe(true)
    }
  })

  it('all 5 TriggerSpecs round-trip through Router.registerTrigger', () => {
    const r = new Router()
    for (const t of STARTER_TRIGGERS) {
      expect(() => r.registerTrigger(t)).not.toThrow()
    }
    expect(r.getRegisteredTriggers()).toHaveLength(STARTER_TRIGGERS.length)
  })

  it('TriggerSpecs cover the v1.0 event_types (founder_input + cron); file_drop deferred to v1.1+', () => {
    const types = new Set(STARTER_TRIGGERS.map((t) => t.event_type))
    expect(types.has('founder_input')).toBe(true)
    expect(types.has('cron')).toBe(true)
    // file_drop is documented as v1.1+ in trigger-spec.ts; starter kit
    // does not ship triggers that depend on unimplemented intake (codex
    // P1.1 fold 2026-05-03)
    expect(types.has('file_drop')).toBe(false)
  })
})

describe('Starter kit — Charter ACL cross-references (codex P1.3 fold 2026-05-03)', () => {
  it('every Charter.acl[].domain_or_charter_id references a real starter Domain or Charter', () => {
    const domainIds = new Set(STARTER_DOMAINS.map((d) => d.id))
    const charterIds = new Set(STARTER_CHARTERS.map((c) => c.id))
    for (const c of STARTER_CHARTERS) {
      for (const acl of c.acl) {
        const ref = acl.domain_or_charter_id
        const ok = domainIds.has(ref) || charterIds.has(ref)
        expect(ok, `Charter ${c.id}.acl entry "${ref}" must reference a starter Domain or Charter`).toBe(true)
      }
    }
  })
})

describe('Starter kit — Workflow→Charter ownership map (codex P2.1 fold 2026-05-03)', () => {
  it('STARTER_WORKFLOW_CHARTER_MAP has an entry for every starter Workflow', () => {
    for (const w of STARTER_WORKFLOWS) {
      expect(STARTER_WORKFLOW_CHARTER_MAP.has(w.id)).toBe(true)
    }
  })

  it('every mapping value references a real starter Charter', () => {
    const charterIds = new Set(STARTER_CHARTERS.map((c) => c.id))
    for (const [_wfId, charterId] of STARTER_WORKFLOW_CHARTER_MAP) {
      expect(charterIds.has(charterId)).toBe(true)
    }
  })

  it('map size equals starter Workflow count (no orphans)', () => {
    expect(STARTER_WORKFLOW_CHARTER_MAP.size).toBe(STARTER_WORKFLOWS.length)
  })
})

describe('Starter kit — multi-step Workflows demonstrate real patterns (codex P1.2 fold 2026-05-03)', () => {
  it('at least 3 starter Workflows have multi-step graphs (not just `wait`)', () => {
    const multiStep = STARTER_WORKFLOWS.filter((w) => w.step_graph.length > 1)
    expect(multiStep.length).toBeGreaterThanOrEqual(3)
  })

  it('W-feature-build declares inputs + outputs (anti-cargo-cult example)', () => {
    const w = STARTER_WORKFLOWS.find((w) => w.id === 'W-feature-build')!
    expect(w.inputs.length).toBeGreaterThan(0)
    expect(w.outputs.length).toBeGreaterThan(0)
  })

  it('W-bug-fix uses policy_check on at least one step', () => {
    const w = STARTER_WORKFLOWS.find((w) => w.id === 'W-bug-fix')!
    expect(w.step_graph.some((s) => s.policy_check === true)).toBe(true)
  })

  it('multi-step Workflows show variety in on_failure (not all "continue")', () => {
    const multiStep = STARTER_WORKFLOWS.filter((w) => w.step_graph.length > 1)
    for (const w of multiStep) {
      const onFailures = new Set(w.step_graph.map((s) => s.on_failure))
      expect(onFailures.size).toBeGreaterThan(1)
    }
  })
})

describe('Starter kit — loadStarterKit() shape + immutability', () => {
  it('returns the full curated set', () => {
    const kit = loadStarterKit()
    expect(kit.domains).toEqual(STARTER_DOMAINS)
    expect(kit.charters).toEqual(STARTER_CHARTERS)
    expect(kit.workflows).toEqual(STARTER_WORKFLOWS)
    expect(kit.triggers).toEqual(STARTER_TRIGGERS)
    expect(kit.onboarding).toBe(ONBOARDING_WORKFLOW)
  })

  it('returned StarterKit object is deep-frozen', () => {
    const kit = loadStarterKit()
    expect(Object.isFrozen(kit)).toBe(true)
    expect(Object.isFrozen(kit.domains)).toBe(true)
    expect(Object.isFrozen(kit.charters)).toBe(true)
    expect(Object.isFrozen(kit.workflows)).toBe(true)
    expect(Object.isFrozen(kit.triggers)).toBe(true)
  })
})

describe('Starter kit — onboarding flow has the "first SUCCESS" path wired', () => {
  it('T-onboarding fires on founder_input (codex P1.1 fold 2026-05-03 — file_drop deferred to v1.1+)', () => {
    const onboardingTrigger = STARTER_TRIGGERS.find((t) => t.id === 'T-onboarding')
    expect(onboardingTrigger).toBeDefined()
    expect(onboardingTrigger?.event_type).toBe('founder_input')
    expect(onboardingTrigger?.target_workflow).toBe(ONBOARDING_WORKFLOW.id)
  })

  it('onboarding charter contains the obligation that "first SUCCESS Execution" emits', () => {
    const charter = STARTER_CHARTERS.find((c) => c.id === 'C-onboarding')
    expect(charter).toBeDefined()
    const obligationNames = charter!.obligations.map((o) => o.name)
    expect(obligationNames).toContain('first_success_execution_emitted')
  })
})
