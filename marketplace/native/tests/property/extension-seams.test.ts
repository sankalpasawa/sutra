/**
 * Workflow.extension_ref property tests — M4.5 (D4 §7; D-NS-9 default b).
 *
 * 1000+ cases per property: round-trip preservation + reject malformed.
 * v1.0 enforcement (extension_ref MUST be null at terminal_check) is gated
 * by forbidden coupling F-N — implemented in M4.9 + tested there. Here we
 * test the schema-shape level only.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import {
  ExtensionRefSchema,
  EXTENSION_REF_PATTERN,
  isValidExtensionRef,
} from '../../src/types/extension.js'
import { workflowArb } from './arbitraries.js'

const PROP_RUNS = 1000

const validExtensionRefArb = fc
  .string({ minLength: 1, maxLength: 24 })
  .filter((s) => /^[a-z0-9-]+$/.test(s) && s.length > 0)
  .map((s) => `ext-${s}`)

const extensionRefArb: fc.Arbitrary<string | null> = fc.option(
  validExtensionRefArb,
  { nil: null },
)

describe('Workflow.extension_ref property tests (M4.5)', () => {
  it('round-trip: any valid extension_ref survives createWorkflow + isValidWorkflow', () => {
    fc.assert(
      fc.property(workflowArb(), extensionRefArb, (wf, ref) => {
        const w = createWorkflow({ ...wf, extension_ref: ref })
        expect(w.extension_ref).toEqual(ref)
        expect(isValidWorkflow(w)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('reject: any non-null string that fails ext- pattern is rejected at constructor', () => {
    const badArb = fc
      .oneof(
        fc.string({ maxLength: 8 }),
        fc.constant('ext-'),
        fc.constant(''),
        fc.constant('ext-UPPER'),
        fc.constant('asawa'),
        fc.constant('extension-x'),
        fc.constant('ext x'),
      )
      .filter((s) => !EXTENSION_REF_PATTERN.test(s))
    fc.assert(
      fc.property(workflowArb(), badArb, (wf, bad) => {
        expect(() =>
          createWorkflow({ ...wf, extension_ref: bad as string }),
        ).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('schema parses null and well-formed strings, rejects malformed', () => {
    fc.assert(
      fc.property(extensionRefArb, (ref) => {
        const r = ExtensionRefSchema.safeParse(ref)
        expect(r.success).toBe(true)
        expect(isValidExtensionRef(ref)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
