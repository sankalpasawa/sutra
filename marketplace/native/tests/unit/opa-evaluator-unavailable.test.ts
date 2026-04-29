/**
 * OPA evaluator — OPAUnavailableError unit test.
 *
 * Asserts:
 *  - When the OPA binary is missing on $PATH, evaluate() throws
 *    OPAUnavailableError. We simulate "missing" by clobbering PATH for the
 *    duration of one invocation + resetting the cached probe state via the
 *    test seam.
 *
 * NOTE: this test mutates `process.env.PATH`. It MUST restore the original
 * PATH in afterEach so subsequent test files (which DO need the OPA binary)
 * are unaffected. The test seam `__resetOPAProbeForTest()` clears the
 * cached probe state so the next test re-checks the binary against the
 * restored PATH.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-090
 */

import { describe, it, expect, afterEach, beforeEach } from 'vitest'

import {
  evaluate,
  OPAUnavailableError,
  __resetOPAProbeForTest,
} from '../../src/engine/opa-evaluator.js'
import { compileCharter } from '../../src/engine/charter-rego-compiler.js'
import type { Charter } from '../../src/primitives/charter.js'

const ORIGINAL_PATH = process.env.PATH

function emptyCharter(): Charter {
  return {
    id: 'C-noop',
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
}

describe('opa-evaluator — OPAUnavailableError', () => {
  beforeEach(() => {
    __resetOPAProbeForTest()
  })

  afterEach(() => {
    // Restore PATH + reset probe so other tests find the real binary.
    process.env.PATH = ORIGINAL_PATH
    __resetOPAProbeForTest()
  })

  it('throws OPAUnavailableError when the binary is not on $PATH', () => {
    // Clobber PATH to a directory that cannot contain `opa`.
    process.env.PATH = '/nonexistent-dir-xyz-m7-test'
    const policy = compileCharter(emptyCharter())
    expect(() =>
      evaluate(policy, {
        step: {},
        workflow: {},
        execution_context: {},
      }),
    ).toThrow(OPAUnavailableError)
  })

  it('caches the OPA-missing decision until probe is reset', () => {
    // First call sees missing PATH → caches "unavailable".
    process.env.PATH = '/nonexistent-dir-xyz-m7-test'
    const policy = compileCharter(emptyCharter())
    expect(() =>
      evaluate(policy, {
        step: {},
        workflow: {},
        execution_context: {},
      }),
    ).toThrow(OPAUnavailableError)

    // Restore PATH but DO NOT reset the probe — the cached "unavailable"
    // verdict persists, so this second call still throws.
    process.env.PATH = ORIGINAL_PATH
    expect(() =>
      evaluate(policy, {
        step: {},
        workflow: {},
        execution_context: {},
      }),
    ).toThrow(OPAUnavailableError)

    // After reset, the next call re-probes against the restored PATH and
    // succeeds (returns the default-deny decision for an empty Charter).
    __resetOPAProbeForTest()
    const decision = evaluate(policy, {
      step: {},
      workflow: {},
      execution_context: {},
    })
    expect(decision.kind).toBe('deny')
  })
})
