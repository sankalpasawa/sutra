/**
 * Contract tests — ProposalLedger CRUD + status state machine.
 *
 * Verifies SPEC v1.2 §4.2: persist/load/list/update + state machine
 * (pending → approved | rejected, single decision only).
 */

import { existsSync, mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  isProposalEntry,
  listProposals,
  loadProposal,
  persistProposal,
  updateProposalStatus,
  type ProposalEntry,
} from '../../../src/persistence/proposal-ledger.js'

function makeEntry(pattern_id: string, overrides: Partial<ProposalEntry> = {}): ProposalEntry {
  return {
    pattern_id,
    normalized_phrase: 'design partner outreach',
    evidence_count: 4,
    first_seen_ms: 1700000000000,
    last_seen_ms: 1700000600000,
    utterance_samples: ['design partners', 'design partner outreach'],
    proposed_workflow_id: `W-emergent-${pattern_id.slice(2)}`,
    proposed_trigger_id: `T-emergent-${pattern_id.slice(2)}`,
    proposed_charter_id: 'C-daily-pulse',
    proposed_domain_id: 'D1',
    status: 'pending',
    proposed_at_ms: 1700000700000,
    decided_at_ms: null,
    decision_reason: null,
    ...overrides,
  }
}

describe('ProposalLedger schema + CRUD', () => {
  let HOME: string

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'proposal-ledger-'))
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  describe('isProposalEntry', () => {
    it('accepts a well-formed entry', () => {
      expect(isProposalEntry(makeEntry('P-abcd1234'))).toBe(true)
    })

    it('rejects malformed pattern_id', () => {
      expect(isProposalEntry(makeEntry('P-XYZ'))).toBe(false)
      expect(isProposalEntry({ ...makeEntry('P-abcd1234'), pattern_id: 'bad-id' })).toBe(false)
    })

    it('rejects unknown status', () => {
      expect(isProposalEntry({ ...makeEntry('P-abcd1234'), status: 'bogus' })).toBe(false)
    })

    it('rejects non-array utterance_samples', () => {
      expect(isProposalEntry({ ...makeEntry('P-abcd1234'), utterance_samples: 'not array' })).toBe(false)
    })

    it('accepts approved/rejected with decided_at_ms set', () => {
      expect(
        isProposalEntry({
          ...makeEntry('P-abcd1234'),
          status: 'approved',
          decided_at_ms: 1700000800000,
          decision_reason: 'looks right',
        }),
      ).toBe(true)
    })
  })

  describe('persist + load', () => {
    it('persists and round-trips an entry', () => {
      const e = makeEntry('P-11111111')
      const path = persistProposal(e, { home: HOME })
      expect(path).toContain('user-kit/proposals/P-11111111.json')
      expect(existsSync(path)).toBe(true)
      const loaded = loadProposal('P-11111111', { home: HOME })
      expect(loaded?.pattern_id).toBe('P-11111111')
      expect(loaded?.evidence_count).toBe(4)
      expect(loaded?.status).toBe('pending')
    })

    it('persistProposal throws on malformed entry', () => {
      expect(() =>
        persistProposal({ ...makeEntry('P-abcd1234'), status: 'bogus' as 'pending' }, { home: HOME }),
      ).toThrow(TypeError)
    })

    it('loadProposal returns null when id does not exist', () => {
      expect(loadProposal('P-deadbeef', { home: HOME })).toBeNull()
    })

    it('loadProposal returns null on malformed JSON (drift defense)', () => {
      const dir = join(HOME, 'user-kit', 'proposals')
      mkdirSync(dir, { recursive: true })
      writeFileSync(join(dir, 'P-broken1.json'), '{"pattern_id":"P-broken1","status":"BOGUS"}')
      expect(loadProposal('P-broken1', { home: HOME })).toBeNull()
    })
  })

  describe('listProposals', () => {
    it('returns empty when dir does not exist', () => {
      expect(listProposals({ home: HOME })).toEqual([])
    })

    it('returns all persisted entries', () => {
      persistProposal(makeEntry('P-aaaaaaaa'), { home: HOME })
      persistProposal(makeEntry('P-bbbbbbbb'), { home: HOME })
      const all = listProposals({ home: HOME })
      expect(all).toHaveLength(2)
    })

    it('filters by status when provided', () => {
      persistProposal(makeEntry('P-11111111'), { home: HOME })
      persistProposal(
        makeEntry('P-22222222', {
          status: 'approved',
          decided_at_ms: 1700000800000,
          decision_reason: 'ok',
        }),
        { home: HOME },
      )
      expect(listProposals({ home: HOME }, 'pending')).toHaveLength(1)
      expect(listProposals({ home: HOME }, 'approved')).toHaveLength(1)
      expect(listProposals({ home: HOME }, 'rejected')).toHaveLength(0)
    })

    it('silently filters malformed JSON files', () => {
      persistProposal(makeEntry('P-aaaaaaaa'), { home: HOME })
      const dir = join(HOME, 'user-kit', 'proposals')
      writeFileSync(join(dir, 'P-bad.json'), '{"pattern_id":"P-bad","status":"BOGUS"}')
      const list = listProposals({ home: HOME })
      expect(list).toHaveLength(1)
      expect(list[0].pattern_id).toBe('P-aaaaaaaa')
    })
  })

  describe('updateProposalStatus state machine', () => {
    it('transitions pending → approved with decision metadata', () => {
      persistProposal(makeEntry('P-11111111'), { home: HOME })
      const updated = updateProposalStatus(
        'P-11111111',
        'approved',
        'looks right',
        { home: HOME },
        1700000900000,
      )
      expect(updated.status).toBe('approved')
      expect(updated.decided_at_ms).toBe(1700000900000)
      expect(updated.decision_reason).toBe('looks right')
      expect(loadProposal('P-11111111', { home: HOME })?.status).toBe('approved')
    })

    it('transitions pending → rejected', () => {
      persistProposal(makeEntry('P-22222222'), { home: HOME })
      const updated = updateProposalStatus(
        'P-22222222',
        'rejected',
        'too noisy',
        { home: HOME },
      )
      expect(updated.status).toBe('rejected')
    })

    it('throws when transitioning from non-pending (decided once)', () => {
      persistProposal(makeEntry('P-33333333'), { home: HOME })
      updateProposalStatus('P-33333333', 'approved', 'first decision', { home: HOME })
      expect(() =>
        updateProposalStatus('P-33333333', 'rejected', 'second try', { home: HOME }),
      ).toThrow(/decided once/)
    })

    it('throws when proposal does not exist', () => {
      expect(() =>
        updateProposalStatus('P-deadbeef', 'approved', 'no entry', { home: HOME }),
      ).toThrow(/no proposal found/)
    })
  })
})
