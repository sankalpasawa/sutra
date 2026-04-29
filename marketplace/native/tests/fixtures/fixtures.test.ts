/**
 * Fixtures self-test — every fixture round-trips through its primitive's
 * constructor and validator (or, for invalidMissingRequired, must reject).
 *
 * Spec source: tests/fixtures/README.md "Validation contract" section.
 */

import { describe, expect, it } from 'vitest'

import { createDomain, isValidDomain } from '../../src/primitives/domain.js'
import { createCharter, isValidCharter } from '../../src/primitives/charter.js'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import { createExecution, isValidExecution } from '../../src/primitives/execution.js'
import { createTenant, isValidTenant } from '../../src/schemas/tenant.js'
import {
  createDecisionProvenance,
  isValidDecisionProvenance,
} from '../../src/schemas/decision-provenance.js'

import * as DomainFx from './domain.fixture.js'
import * as CharterFx from './charter.fixture.js'
import * as WorkflowFx from './workflow.fixture.js'
import * as ExecutionFx from './execution.fixture.js'
import * as TenantFx from './tenant.fixture.js'
import * as DPFx from './decision-provenance.fixture.js'

describe('M4.10 fixtures — round-trip + reject contract', () => {
  describe('Domain', () => {
    it('validMinimal round-trips through createDomain + isValidDomain', () => {
      const d = createDomain(DomainFx.validMinimal())
      expect(isValidDomain(d)).toBe(true)
    })
    it('validFull round-trips through createDomain + isValidDomain', () => {
      const d = createDomain(DomainFx.validFull())
      expect(isValidDomain(d)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = DomainFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally missing required field
        const d = createDomain(bad)
        // If no throw, predicate must reject.
        if (!isValidDomain(d)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
    it('factories are pure (validMinimal returns fresh objects)', () => {
      const a = DomainFx.validMinimal()
      const b = DomainFx.validMinimal()
      expect(a).not.toBe(b)
      expect(a).toEqual(b)
    })
    it('factories are deep-cloneable (validFull)', () => {
      const a = DomainFx.validFull()
      const cloned = structuredClone(a)
      expect(cloned).toEqual(a)
    })
  })

  describe('Charter', () => {
    it('validMinimal round-trips through createCharter + isValidCharter', () => {
      const c = createCharter(CharterFx.validMinimal())
      expect(isValidCharter(c)).toBe(true)
    })
    it('validFull round-trips through createCharter + isValidCharter', () => {
      const c = createCharter(CharterFx.validFull())
      expect(isValidCharter(c)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = CharterFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally missing required field
        const c = createCharter(bad)
        if (!isValidCharter(c)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
  })

  describe('Workflow', () => {
    it('validMinimal round-trips through createWorkflow + isValidWorkflow', () => {
      const w = createWorkflow(WorkflowFx.validMinimal())
      expect(isValidWorkflow(w)).toBe(true)
    })
    it('validFull round-trips through createWorkflow + isValidWorkflow', () => {
      const w = createWorkflow(WorkflowFx.validFull())
      expect(isValidWorkflow(w)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = WorkflowFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally missing required field
        const w = createWorkflow(bad)
        if (!isValidWorkflow(w)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })

    // M5 Group J / T-048 — autonomy_level fixture variants
    it('validMinimalAutonomous round-trips with autonomy_level="autonomous"', () => {
      const w = createWorkflow(WorkflowFx.validMinimalAutonomous())
      expect(isValidWorkflow(w)).toBe(true)
      expect(w.autonomy_level).toBe('autonomous')
    })
    it('validSemiAutonomy round-trips with autonomy_level="semi"', () => {
      const w = createWorkflow(WorkflowFx.validSemiAutonomy())
      expect(isValidWorkflow(w)).toBe(true)
      expect(w.autonomy_level).toBe('semi')
    })
    it('invalidAutonomyLevel throws OR fails predicate', () => {
      const bad = WorkflowFx.invalidAutonomyLevel()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally has invalid enum value
        const w = createWorkflow(bad)
        if (!isValidWorkflow(w)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
  })

  describe('Tenant (M4.1)', () => {
    it('validMinimal round-trips through createTenant + isValidTenant', () => {
      const t = createTenant(TenantFx.validMinimal())
      expect(isValidTenant(t)).toBe(true)
    })
    it('validFull round-trips through createTenant + isValidTenant', () => {
      const t = createTenant(TenantFx.validFull())
      expect(isValidTenant(t)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = TenantFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally missing required field
        const t = createTenant(bad)
        if (!isValidTenant(t)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
  })

  describe('DecisionProvenance (M4.3)', () => {
    it('validMinimal round-trips', () => {
      const v = createDecisionProvenance(DPFx.validMinimal())
      expect(isValidDecisionProvenance(v)).toBe(true)
    })
    it('validFull round-trips', () => {
      const v = createDecisionProvenance(DPFx.validFull())
      expect(isValidDecisionProvenance(v)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = DPFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        // @ts-expect-error — fixture intentionally missing required field
        const v = createDecisionProvenance(bad)
        if (!isValidDecisionProvenance(v)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
  })

  describe('Execution', () => {
    it('validMinimal round-trips through createExecution + isValidExecution', () => {
      const e = createExecution(ExecutionFx.validMinimal())
      expect(isValidExecution(e)).toBe(true)
    })
    it('validFull round-trips through createExecution + isValidExecution', () => {
      const e = createExecution(ExecutionFx.validFull())
      expect(isValidExecution(e)).toBe(true)
    })
    it('invalidMissingRequired throws OR fails predicate', () => {
      const bad = ExecutionFx.invalidMissingRequired()
      let threwOrFailed = false
      try {
        const e = createExecution(bad as never)
        if (!isValidExecution(e)) threwOrFailed = true
      } catch {
        threwOrFailed = true
      }
      expect(threwOrFailed).toBe(true)
    })
  })
})
