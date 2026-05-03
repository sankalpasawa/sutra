/**
 * Contract tests — user-kit TriggerSpec CRUD (v1.2 organic emergence).
 *
 * Verifies persistTrigger / loadTrigger / listTriggers round-trip + drift
 * defense via isTriggerSpec on load. Mirrors the existing Domain / Charter /
 * Workflow CRUD shape per SPEC §4.1.
 */

import { existsSync, mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  listTriggers,
  loadTrigger,
  loadUserKit,
  persistTrigger,
} from '../../../src/persistence/user-kit.js'
import type { TriggerSpec } from '../../../src/types/trigger-spec.js'

function makeTrigger(id: string, value = 'design partners'): TriggerSpec {
  return {
    id,
    event_type: 'founder_input',
    route_predicate: { type: 'contains', value, case_sensitive: false },
    target_workflow: `W-${id.slice(2)}`,
    domain_id: 'D1',
    charter_id: 'C-daily-pulse',
    description: `test trigger ${id}`,
  }
}

describe('user-kit TriggerSpec CRUD', () => {
  let HOME: string

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'user-kit-trigger-'))
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('persistTrigger writes a JSON file and returns its path', () => {
    const t = makeTrigger('T-test-1')
    const path = persistTrigger(t, { home: HOME })
    expect(path).toContain('user-kit/triggers/T-test-1.json')
    expect(existsSync(path)).toBe(true)
  })

  it('loadTrigger round-trips a persisted TriggerSpec by id', () => {
    const t = makeTrigger('T-test-2', 'pipeline review')
    persistTrigger(t, { home: HOME })
    const loaded = loadTrigger('T-test-2', { home: HOME })
    expect(loaded).not.toBeNull()
    expect(loaded?.id).toBe('T-test-2')
    expect(loaded?.event_type).toBe('founder_input')
    expect(loaded?.target_workflow).toBe('W-test-2')
    if (loaded?.route_predicate.type === 'contains') {
      expect(loaded.route_predicate.value).toBe('pipeline review')
    }
  })

  it('loadTrigger returns null when id does not exist', () => {
    expect(loadTrigger('T-missing', { home: HOME })).toBeNull()
  })

  it('listTriggers returns empty array when triggers dir does not exist', () => {
    expect(listTriggers({ home: HOME })).toEqual([])
  })

  it('listTriggers returns all persisted triggers', () => {
    persistTrigger(makeTrigger('T-a'), { home: HOME })
    persistTrigger(makeTrigger('T-b'), { home: HOME })
    persistTrigger(makeTrigger('T-c'), { home: HOME })
    const list = listTriggers({ home: HOME })
    expect(list).toHaveLength(3)
    const ids = list.map((t) => t.id).sort()
    expect(ids).toEqual(['T-a', 'T-b', 'T-c'])
  })

  it('loadTrigger returns null on malformed JSON (drift defense)', () => {
    const dir = join(HOME, 'user-kit', 'triggers')
    mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, 'T-broken.json'), '{"id":"T-broken","event_type":"BOGUS"}')
    expect(loadTrigger('T-broken', { home: HOME })).toBeNull()
  })

  it('listTriggers silently filters malformed JSON files', () => {
    persistTrigger(makeTrigger('T-good'), { home: HOME })
    const dir = join(HOME, 'user-kit', 'triggers')
    writeFileSync(join(dir, 'T-bad.json'), '{"id":"T-bad","event_type":"BOGUS"}')
    const list = listTriggers({ home: HOME })
    expect(list).toHaveLength(1)
    expect(list[0].id).toBe('T-good')
  })

  it('loadUserKit aggregate includes triggers', () => {
    persistTrigger(makeTrigger('T-agg'), { home: HOME })
    const kit = loadUserKit({ home: HOME })
    expect(kit.triggers).toHaveLength(1)
    expect(kit.triggers[0].id).toBe('T-agg')
    expect(kit.domains).toEqual([])
    expect(kit.charters).toEqual([])
    expect(kit.workflows).toEqual([])
  })

  it('persistTrigger overwrites existing JSON for same id (last-write-wins)', () => {
    persistTrigger(makeTrigger('T-mut', 'first'), { home: HOME })
    persistTrigger(makeTrigger('T-mut', 'second'), { home: HOME })
    const loaded = loadTrigger('T-mut', { home: HOME })
    if (loaded?.route_predicate.type === 'contains') {
      expect(loaded.route_predicate.value).toBe('second')
    }
  })
})
