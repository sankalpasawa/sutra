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

  it('valid `ext-<id>` string accepted at constructor (v1.x format)', () => {
    const w = createWorkflow({
      ...WorkflowFx.validMinimal(),
      extension_ref: 'ext-mcp-bridge',
    })
    expect(w.extension_ref).toBe('ext-mcp-bridge')
    expect(isValidWorkflow(w)).toBe(true)
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
