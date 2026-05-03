/**
 * v1.2.1 — NativeEngine event serialization under async host-LLM dispatch.
 *
 * Codex master review DIRECTIVE 1777839055 P1 fold: handleHSutraEvent became
 * async to support invoke_host_llm. The H-Sutra connector delivers events
 * synchronously and does NOT await listeners, so without a per-engine
 * serialization queue, two founder turns could overlap mid-dispatch and
 * collide on executionCounter / ledger / proposer state.
 *
 * Test: pre-seed the log with TWO founder turns, start engine, drain queue,
 * assert routing_decision events emit in the input order. Without the
 * turnQueue chain, the second event could overtake the first when the first
 * has an async step.
 */

import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { NativeEngine } from '../../src/runtime/native-engine.js'
import type { EngineEvent } from '../../src/types/engine-event.js'

describe('NativeEngine — serialization under async dispatch (v1.2.1)', () => {
  let workdir: string
  let logPath: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'native-v1.2.1-serial-'))
    logPath = join(workdir, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('drain() awaits turnQueue; pre-seeded log lines route in input order', async () => {
    // Pre-seed the log with two founder turns. Connector reads existing
    // lines synchronously on start.
    const lines = [
      JSON.stringify({ turn_id: 't1', input_text: 'first turn' }),
      JSON.stringify({ turn_id: 't2', input_text: 'second turn' }),
    ]
    writeFileSync(logPath, lines.join('\n') + '\n')

    const observed: EngineEvent[] = []
    const engine = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: false,
      connector_options: { log_path: logPath },
      write: () => {},
    })
    engine.renderer.register('routing_decision', (e) => {
      observed.push(e)
      return ''
    })

    engine.start()
    await engine.drain()

    expect(observed).toHaveLength(2)
    if (observed[0]?.type !== 'routing_decision') throw new Error('type narrow')
    if (observed[1]?.type !== 'routing_decision') throw new Error('type narrow')
    expect(observed[0].turn_id).toBe('t1')
    expect(observed[1].turn_id).toBe('t2')

    engine.stop()
  })

  it('drain() resolves immediately when no events are pending', async () => {
    const engine = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: false,
      connector_options: { log_path: logPath },
      write: () => {},
    })
    // Don't start — drain on a fresh engine still returns.
    await engine.drain()
    expect(true).toBe(true) // reached this line means drain didn't hang
  })
})
