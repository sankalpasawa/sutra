/**
 * Workflow.extension_ref contract tests — M4.5 (D4 §7; D-NS-9 default b).
 *
 * Per codex P1.2 narrowing: M4.5 ships ONLY `extension_ref`. The 4 candidate
 * seams (`metadata`, `schema_version`, `required_capabilities`, `discipline_tag`)
 * defer to v1.x case-by-case.
 */

import { describe, expect, it } from 'vitest'
import {
  EXTENSION_REF_PATTERN,
  ExtensionRefSchema,
  isValidExtensionRef,
} from '../../../src/types/extension.js'
import { createWorkflow, isValidWorkflow } from '../../../src/primitives/workflow.js'
import * as WorkflowFx from '../../fixtures/workflow.fixture.js'
import { f11Predicate, terminalCheck } from '../../../src/laws/l4-terminal-check.js'
import type { Execution } from '../../../src/primitives/execution.js'
import type { Charter } from '../../../src/primitives/charter.js'
import type { Tenant } from '../../../src/schemas/tenant.js'

describe('ExtensionRefSchema (M4.5)', () => {
  it('accepts null', () => {
    expect(ExtensionRefSchema.safeParse(null).success).toBe(true)
    expect(isValidExtensionRef(null)).toBe(true)
  })

  it('accepts a valid `ext-<id>` string', () => {
    const ok = 'ext-mcp-bridge'
    expect(ExtensionRefSchema.safeParse(ok).success).toBe(true)
    expect(isValidExtensionRef(ok)).toBe(true)
  })

  it('rejects malformed prefix (no `ext-` prefix)', () => {
    expect(ExtensionRefSchema.safeParse('mcp-bridge').success).toBe(false)
    expect(isValidExtensionRef('mcp-bridge')).toBe(false)
  })

  it('rejects empty string', () => {
    expect(ExtensionRefSchema.safeParse('').success).toBe(false)
  })

  it('rejects uppercase characters', () => {
    expect(ExtensionRefSchema.safeParse('ext-MCP').success).toBe(false)
  })

  it('rejects whitespace', () => {
    expect(ExtensionRefSchema.safeParse('ext-mcp bridge').success).toBe(false)
  })

  it('rejects `ext-` alone (no body)', () => {
    expect(ExtensionRefSchema.safeParse('ext-').success).toBe(false)
  })

  it('EXTENSION_REF_PATTERN matches expected inputs', () => {
    expect(EXTENSION_REF_PATTERN.test('ext-x')).toBe(true)
    expect(EXTENSION_REF_PATTERN.test('ext-')).toBe(false)
    expect(EXTENSION_REF_PATTERN.test('extension-x')).toBe(false)
  })
})

describe('Workflow.extension_ref field (M4.5)', () => {
  it('defaults to null when omitted (v1.0 enforcement)', () => {
    const w = createWorkflow(WorkflowFx.validMinimal())
    expect(w.extension_ref).toBeNull()
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('explicit null accepted', () => {
    const w = createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: null })
    expect(w.extension_ref).toBeNull()
  })

  it('valid `ext-<id>` string accepted at constructor (v1.x format) — schema layer', () => {
    // Schema-level acceptance (createWorkflow + isValidWorkflow) accepts
    // well-formed `ext-<id>` strings so v1.x extensions can be authored against
    // the same API. v1.0 enforcement (extension_ref MUST be null) lives at
    // terminal_check (F-11). See test below.
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      extension_ref: 'ext-mcp-bridge',
    })
    expect(w.extension_ref).toBe('ext-mcp-bridge')
    expect(isValidWorkflow(w)).toBe(true)
  })

  it('F-11 (Group G\' 2026-04-29): terminal_check REJECTS non-null extension_ref in v1.0', () => {
    // D4 §7.3: extension_ref MUST be null in v1.0. Schema accepts non-null
    // (above test); terminal_check rejects via F-11 predicate.
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      extension_ref: 'ext-mcp-bridge',
    })
    // F-11 predicate fires (returns true = VIOLATION) for non-null extension_ref.
    expect(f11Predicate({ workflow: w })).toBe(true)

    // Aggregator surfaces F-11 in the violations list.
    const execution: Execution = {
      id: 'E-test',
      workflow_id: w.id,
      trigger_event: 'turn_start',
      state: 'success',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp',
      failure_reason: null,
      agent_identity: null,
    }
    const charter: Charter = {
      id: 'C-test',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [],
    }
    const tenant: Tenant = {
      id: 'T-default',
      name: 'default',
      isolation_contract: 'single-tenant',
      parent_tenant_id: null,
      managed_agents_session: null,
      audit_log_path: null,
    }
    const result = terminalCheck({
      workflow: w,
      execution,
      charter,
      tenant,
      operationalizes_charters: ['C-test'],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    })
    expect(result.pass).toBe(false)
    expect(result.violations).toContain('F-11')
  })

  it('F-11: terminal_check ACCEPTS null extension_ref (v1.0 default)', () => {
    const w = createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: null })
    expect(f11Predicate({ workflow: w })).toBe(false)
  })

  it('rejects malformed extension_ref (no prefix)', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: 'mcp' }),
    ).toThrow()
  })

  it('rejects empty string extension_ref', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: '' }),
    ).toThrow()
  })

  it('rejects uppercase extension_ref', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: 'ext-MCP' }),
    ).toThrow()
  })

  it('rejects "ext-" alone (no body)', () => {
    expect(() =>
      createWorkflow({ ...WorkflowFx.validMinimal(), extension_ref: 'ext-' }),
    ).toThrow()
  })

  it('isValidWorkflow rejects records with malformed extension_ref', () => {
    const ok = createWorkflow(WorkflowFx.validMinimal())
    const bad = { ...ok, extension_ref: 'not-an-ext' }
    expect(isValidWorkflow(bad)).toBe(false)
  })

  it('round-trip: createWorkflow → JSON → revalidate preserves extension_ref', () => {
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      extension_ref: 'ext-future-v1-1',
    })
    const json = JSON.stringify(w)
    const parsed = JSON.parse(json) as typeof w
    expect(parsed.extension_ref).toBe('ext-future-v1-1')
    expect(isValidWorkflow(parsed)).toBe(true)
  })

  it('fixture validMinimal declares extension_ref = null', () => {
    expect(WorkflowFx.validMinimal().extension_ref).toBeNull()
  })

  it('fixture validFull declares extension_ref = null', () => {
    expect(WorkflowFx.validFull().extension_ref).toBeNull()
  })
})
