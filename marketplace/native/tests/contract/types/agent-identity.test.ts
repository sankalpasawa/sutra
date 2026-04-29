/**
 * AgentIdentity contract tests — M4.2 (D1 P-A2; V2.5 §A14; D-NS-10 default c).
 */

import { describe, expect, it } from 'vitest'
import {
  AGENT_KINDS,
  AgentIdentitySchema,
  createAgentIdentity,
  isValidAgentIdentity,
  namespaceOf,
  type AgentIdentity,
} from '../../../src/types/agent-identity.js'
import { createExecution, isValidExecution } from '../../../src/primitives/execution.js'

describe('AgentIdentity discriminated union (M4.2)', () => {
  it('accepts each kind with namespace-prefixed id', () => {
    for (const kind of AGENT_KINDS) {
      const id = `${kind}:test-id-1`
      const v = createAgentIdentity({ kind, id } as AgentIdentity)
      expect(v.kind).toBe(kind)
      expect(v.id).toBe(id)
    }
  })

  it('rejects id missing the kind prefix (impersonation prevention)', () => {
    expect(() =>
      createAgentIdentity({ kind: 'claude-opus', id: 'codex:abc' } as AgentIdentity),
    ).toThrow()
  })

  it('rejects id with no prefix at all', () => {
    expect(() =>
      createAgentIdentity({ kind: 'codex', id: 'just-an-id' } as AgentIdentity),
    ).toThrow()
  })

  it('rejects empty id', () => {
    expect(() =>
      // @ts-expect-error — intentionally invalid
      createAgentIdentity({ kind: 'human', id: '' }),
    ).toThrow()
  })

  it('rejects unknown kind', () => {
    expect(() =>
      // @ts-expect-error — invalid kind for the discriminated union
      createAgentIdentity({ kind: 'mystery-llm', id: 'mystery-llm:abc' }),
    ).toThrow()
  })

  it('accepts version when provided (non-empty string)', () => {
    const v = createAgentIdentity({
      kind: 'claude-sonnet',
      id: 'claude-sonnet:abc',
      version: '4.5',
    })
    expect(v.version).toBe('4.5')
  })

  it('rejects empty version when provided', () => {
    expect(() =>
      createAgentIdentity({
        kind: 'claude-sonnet',
        id: 'claude-sonnet:abc',
        version: '',
      }),
    ).toThrow()
  })

  it('isValidAgentIdentity rejects non-objects', () => {
    expect(isValidAgentIdentity(null)).toBe(false)
    expect(isValidAgentIdentity(undefined)).toBe(false)
    expect(isValidAgentIdentity('string')).toBe(false)
    expect(isValidAgentIdentity(42)).toBe(false)
  })

  it('namespaceOf returns the prefix portion', () => {
    expect(namespaceOf('claude-opus:abc')).toBe('claude-opus')
    expect(namespaceOf('codex:session-1')).toBe('codex')
    expect(namespaceOf('no-colon')).toBeNull()
    expect(namespaceOf(':leading-colon')).toBeNull()
  })

  it('detects impersonation: same id used across two kinds is rejected per kind', () => {
    // claim "claude-opus" but use a "codex:" prefix → reject
    expect(() =>
      createAgentIdentity({
        kind: 'claude-opus',
        id: 'codex:cross-kind-id',
      } as AgentIdentity),
    ).toThrow()
    // claim "codex" but use a "claude-opus:" prefix → reject
    expect(() =>
      createAgentIdentity({
        kind: 'codex',
        id: 'claude-opus:cross-kind-id',
      } as AgentIdentity),
    ).toThrow()
  })

  it('round-trip via JSON.stringify → AgentIdentitySchema.parse preserves shape', () => {
    const v = createAgentIdentity({
      kind: 'subagent',
      id: 'subagent:m4-implementer',
      version: '1.0',
    })
    const parsed = AgentIdentitySchema.parse(JSON.parse(JSON.stringify(v)))
    expect(parsed).toEqual(v)
  })
})

describe('Execution.agent_identity field (M4.2)', () => {
  function baseExec() {
    return {
      id: 'E-test',
      workflow_id: 'W-test',
      trigger_event: 'tev-test',
      state: 'success' as const,
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp-test',
    }
  }

  it('createExecution defaults agent_identity to null when omitted', () => {
    const e = createExecution(baseExec())
    expect(e.agent_identity).toBeNull()
    expect(isValidExecution(e)).toBe(true)
  })

  it('createExecution accepts a valid AgentIdentity', () => {
    const e = createExecution({
      ...baseExec(),
      agent_identity: { kind: 'claude-opus', id: 'claude-opus:abc' },
    })
    expect(e.agent_identity).toEqual({ kind: 'claude-opus', id: 'claude-opus:abc' })
    expect(isValidExecution(e)).toBe(true)
  })

  it('createExecution rejects an AgentIdentity with wrong-prefix id', () => {
    expect(() =>
      createExecution({
        ...baseExec(),
        agent_identity: { kind: 'claude-opus', id: 'codex:abc' } as AgentIdentity,
      }),
    ).toThrow()
  })

  it('isValidExecution rejects an AgentIdentity with wrong-prefix id', () => {
    const e = {
      ...baseExec(),
      failure_reason: null,
      agent_identity: { kind: 'codex', id: 'human:no-prefix-match' } as AgentIdentity,
    }
    expect(isValidExecution(e as never)).toBe(false)
  })
})
