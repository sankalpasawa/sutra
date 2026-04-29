/**
 * Workflow.custody_owner contract tests — M4.4 (D-NS-11 default c).
 */

import { describe, expect, it } from 'vitest'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import * as WorkflowFx from '../fixtures/workflow.fixture.js'

describe('Workflow.custody_owner field (M4.4)', () => {
  it('defaults to null when omitted (single-tenant v1.0)', () => {
    const w = createWorkflow(WorkflowFx.validMinimal())
    expect(w.custody_owner).toBeNull()
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('explicit null accepted', () => {
    const w = createWorkflow({ ...WorkflowFx.validMinimal(), custody_owner: null })
    expect(w.custody_owner).toBeNull()
  })

  it('valid T- pattern accepted', () => {
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      custody_owner: 'T-asawa-holding',
    })
    expect(w.custody_owner).toBe('T-asawa-holding')
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('rejects malformed custody_owner (no T- prefix)', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), custody_owner: 'asawa' }),
    ).toThrow()
  })

  it('rejects custody_owner with uppercase characters', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), custody_owner: 'T-Asawa' }),
    ).toThrow()
  })

  it('rejects empty string custody_owner', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), custody_owner: '' }),
    ).toThrow()
  })

  it('rejects "T-" alone (no body)', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), custody_owner: 'T-' }),
    ).toThrow()
  })

  it('isValidWorkflow rejects records with malformed custody_owner', () => {
    const fixture = WorkflowFx.validMinimal()
    const ok = createWorkflow(fixture)
    const bad = { ...ok, custody_owner: 'not-a-tenant' as string | null }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('fixture validFull declares custody_owner = T-asawa-holding', () => {
    const w = createWorkflow(WorkflowFx.validFull())
    expect(w.custody_owner).toBe('T-asawa-holding')
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('round-trip: createWorkflow → JSON → revalidate preserves custody_owner', () => {
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      custody_owner: 'T-billu-prod',
    })
    const json = JSON.stringify(w)
    const parsed = JSON.parse(json) as typeof w
    expect(parsed.custody_owner).toBe('T-billu-prod')
    expect(isValidWorkflow(parsed)).toBe(true)
  })
})
