/**
 * v1.3.0 W6 — multi-tenant isolation fixture.
 *
 * Coverage matrix (plan §Step 5):
 *   1. Two tenants under two SUTRA_NATIVE_HOMEs in the SAME process write
 *      Domains independently; tenant A's listDomains only sees A's domains
 *      and vice versa.
 *   2. Workflow persistence is segregated: tenant A's listWorkflows returns
 *      A's workflows only.
 *   3. Cross-tenant load returns null when the id exists in the other tenant
 *      but not in the queried tenant.
 *   4. DecisionProvenance records under each HOME root stay segregated.
 *   5. Telemetry sink (W6) under each HOME root is independent — events
 *      written to tenant A's sink are absent from tenant B's replay.
 */

import { mkdtempSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { createDomain } from '../../src/primitives/domain.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import {
  listDomains,
  listWorkflows,
  loadDomain,
  loadWorkflow,
  persistDomain,
  persistWorkflow,
} from '../../src/persistence/user-kit.js'
import {
  appendTelemetry,
  replayTelemetry,
  resetTelemetryCounter,
  telemetrySinkPath,
} from '../../src/persistence/telemetry-sink.js'
import { appendDecisionProvenanceLog } from '../../src/runtime/emergence-provenance.js'
import { buildExecutionDecisionProvenance } from '../../src/runtime/execution-provenance.js'
import type { EngineEvent } from '../../src/types/engine-event.js'

let homeA: string
let homeB: string

function buildWf(id: string): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

beforeEach(() => {
  homeA = mkdtempSync(join(tmpdir(), 'native-w6-mt-a-'))
  homeB = mkdtempSync(join(tmpdir(), 'native-w6-mt-b-'))
  // Counters keyed by absolute sink path; reset to be sure each test starts fresh.
  resetTelemetryCounter({ home: homeA })
  resetTelemetryCounter({ home: homeB })
})

afterEach(() => {
  rmSync(homeA, { recursive: true, force: true })
  rmSync(homeB, { recursive: true, force: true })
})

describe('v1.3.0 W6 #1 — multi-tenant Domain isolation', () => {
  it('listDomains returns only the queried tenant\'s domains', () => {
    const dA = createDomain({
      id: 'D1',
      name: 'A-domain',
      parent_id: null,
      principles: [],
      intelligence: 'tenant A intelligence',
      accountable: ['founder'],
      authority: 'A',
      tenant_id: 'T-tenant-a',
    })
    const dB = createDomain({
      id: 'D2',
      name: 'B-domain',
      parent_id: null,
      principles: [],
      intelligence: 'tenant B intelligence',
      accountable: ['founder'],
      authority: 'B',
      tenant_id: 'T-tenant-b',
    })

    persistDomain(dA, { home: homeA })
    persistDomain(dB, { home: homeB })

    const listA = listDomains({ home: homeA })
    const listB = listDomains({ home: homeB })

    expect(listA.map((d) => d.id)).toEqual(['D1'])
    expect(listB.map((d) => d.id)).toEqual(['D2'])
    expect(listA[0]!.tenant_id).toBe('T-tenant-a')
    expect(listB[0]!.tenant_id).toBe('T-tenant-b')
  })

  it('cross-tenant loadDomain returns null when id only exists in the other tenant', () => {
    const dA = createDomain({
      id: 'D1',
      name: 'A-only',
      parent_id: null,
      principles: [],
      intelligence: '',
      accountable: ['founder'],
      authority: 'A',
      tenant_id: 'T-a',
    })
    persistDomain(dA, { home: homeA })

    expect(loadDomain('D1', { home: homeA })).not.toBeNull()
    expect(loadDomain('D1', { home: homeB })).toBeNull()
  })
})

describe('v1.3.0 W6 #2 — multi-tenant Workflow isolation', () => {
  it('listWorkflows returns only the queried tenant\'s workflows', () => {
    const wA = buildWf('W-tenant-a-wf')
    const wB = buildWf('W-tenant-b-wf')

    persistWorkflow(wA, { home: homeA })
    persistWorkflow(wB, { home: homeB })

    const listA = listWorkflows({ home: homeA })
    const listB = listWorkflows({ home: homeB })

    expect(listA.map((w) => w.id)).toEqual(['W-tenant-a-wf'])
    expect(listB.map((w) => w.id)).toEqual(['W-tenant-b-wf'])
  })

  it('cross-tenant loadWorkflow returns null', () => {
    const wA = buildWf('W-only-in-a')
    persistWorkflow(wA, { home: homeA })

    expect(loadWorkflow('W-only-in-a', { home: homeA })).not.toBeNull()
    expect(loadWorkflow('W-only-in-a', { home: homeB })).toBeNull()
  })

  it('listWorkflows on empty tenant returns empty array, not the other tenant\'s entries', () => {
    const wA = buildWf('W-a-only')
    persistWorkflow(wA, { home: homeA })

    expect(listWorkflows({ home: homeB })).toEqual([])
  })
})

describe('v1.3.0 W6 #3 — DecisionProvenance segregation', () => {
  it('DP records under HOME-A do not appear under HOME-B', () => {
    const dpA = buildExecutionDecisionProvenance({
      execution_id: 'E-a-1',
      workflow_id: 'W-a',
      stage: 'STARTED',
      ts_ms: 1_000_000_000_000,
      outcome: 'started under tenant A',
      charter_id: 'C-a',
    })
    appendDecisionProvenanceLog(dpA, { home: homeA })

    // homeA should have the DP file; homeB should not.
    const dpAPath = join(homeA, 'user-kit', 'decision-provenance.jsonl')
    const dpBPath = join(homeB, 'user-kit', 'decision-provenance.jsonl')
    expect(existsSync(dpAPath)).toBe(true)
    expect(existsSync(dpBPath)).toBe(false)
  })
})

describe('v1.3.0 W6 #4 — telemetry sink segregation across tenants', () => {
  it('events appended under HOME-A do not appear in HOME-B replay', () => {
    const ea: EngineEvent = {
      type: 'workflow_started',
      ts_ms: 1000,
      workflow_id: 'W-a',
      execution_id: 'E-a-1',
      step_count: 1,
    }
    const eb: EngineEvent = {
      type: 'workflow_started',
      ts_ms: 2000,
      workflow_id: 'W-b',
      execution_id: 'E-b-1',
      step_count: 1,
    }

    appendTelemetry(ea, { home: homeA })
    appendTelemetry(eb, { home: homeB })

    const replayedA = replayTelemetry({ home: homeA })
    const replayedB = replayTelemetry({ home: homeB })

    expect(replayedA.length).toBe(1)
    expect(replayedB.length).toBe(1)
    const aIds = replayedA.map(
      (e) => (e as { execution_id?: string }).execution_id,
    )
    const bIds = replayedB.map(
      (e) => (e as { execution_id?: string }).execution_id,
    )
    expect(aIds).toEqual(['E-a-1'])
    expect(bIds).toEqual(['E-b-1'])
  })

  it('telemetrySinkPath resolves to distinct files per HOME', () => {
    expect(telemetrySinkPath({ home: homeA })).not.toBe(
      telemetrySinkPath({ home: homeB }),
    )
    expect(telemetrySinkPath({ home: homeA }).startsWith(homeA)).toBe(true)
    expect(telemetrySinkPath({ home: homeB }).startsWith(homeB)).toBe(true)
  })
})

describe('v1.3.0 W6 #5 — same-process two-tenant interleave', () => {
  it('mixed Domain + Workflow + telemetry writes across tenants stay isolated', () => {
    // Tenant A
    persistDomain(
      createDomain({
        id: 'D1',
        name: 'A-d',
        parent_id: null,
        principles: [],
        intelligence: '',
        accountable: ['founder'],
        authority: '',
        tenant_id: 'T-a',
      }),
      { home: homeA },
    )
    persistWorkflow(buildWf('W-a-1'), { home: homeA })
    appendTelemetry(
      {
        type: 'workflow_started',
        ts_ms: 100,
        workflow_id: 'W-a-1',
        execution_id: 'E-a-1',
        step_count: 1,
      } as EngineEvent,
      { home: homeA },
    )

    // Tenant B
    persistDomain(
      createDomain({
        id: 'D1',
        name: 'B-d',
        parent_id: null,
        principles: [],
        intelligence: '',
        accountable: ['founder'],
        authority: '',
        tenant_id: 'T-b',
      }),
      { home: homeB },
    )
    persistWorkflow(buildWf('W-b-1'), { home: homeB })
    appendTelemetry(
      {
        type: 'workflow_started',
        ts_ms: 200,
        workflow_id: 'W-b-1',
        execution_id: 'E-b-1',
        step_count: 1,
      } as EngineEvent,
      { home: homeB },
    )

    // Tenant A should see only A
    expect(listDomains({ home: homeA }).map((d) => d.id)).toEqual(['D1'])
    expect(listDomains({ home: homeA })[0]!.name).toBe('A-d')
    expect(listWorkflows({ home: homeA }).map((w) => w.id)).toEqual(['W-a-1'])
    expect(loadWorkflow('W-b-1', { home: homeA })).toBeNull()
    expect(replayTelemetry({ home: homeA }).length).toBe(1)

    // Tenant B should see only B
    expect(listDomains({ home: homeB }).map((d) => d.id)).toEqual(['D1'])
    expect(listDomains({ home: homeB })[0]!.name).toBe('B-d')
    expect(listWorkflows({ home: homeB }).map((w) => w.id)).toEqual(['W-b-1'])
    expect(loadWorkflow('W-a-1', { home: homeB })).toBeNull()
    expect(replayTelemetry({ home: homeB }).length).toBe(1)
  })
})
