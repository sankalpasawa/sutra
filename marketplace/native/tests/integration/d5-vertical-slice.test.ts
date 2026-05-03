/**
 * D5.8 — Native v1.0 vertical-slice integration test.
 *
 * Wires the four D2 components end-to-end:
 *
 *   founder input → H-Sutra log row
 *                 → HSutraConnector emits event
 *                 → Router routes → Workflow id
 *                 → ArtifactCatalog.register(produced asset)
 *                 → RendererRegistry renders the audit line
 *
 * This is the proof that the v1.0 vertical slice composes without manual
 * gluing. Failure here means a contract drift between adjacent modules,
 * even when each module's own contract tests pass.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  appendFileSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import {
  HSutraConnector,
} from '../../src/runtime/h-sutra-connector.js'
import { Router, type LLMFallback } from '../../src/runtime/router.js'
import { ArtifactCatalog } from '../../src/runtime/artifact-catalog.js'
import { RendererRegistry } from '../../src/runtime/renderer-registry.js'
import type { TriggerSpec } from '../../src/types/trigger-spec.js'
import type { Asset } from '../../src/types/index.js'
import type { HSutraEvent } from '../../src/types/h-sutra-event.js'
import type {
  EngineEvent,
  RoutingDecisionEvent,
  ArtifactRegisteredEvent,
} from '../../src/types/engine-event.js'

function asset(over: Partial<Asset> = {}): Asset {
  return {
    kind: 'json',
    schema_ref: 'sutra://schema/build/v1',
    locator: 'cas://content',
    version: '1.0.0',
    mutability: 'immutable',
    retention: 'permanent',
    stable_identity: 'build-output',
    lifecycle_states: ['draft', 'published'],
    ...over,
  }
}

function row(event: Partial<HSutraEvent> & { turn_id: string }): string {
  return JSON.stringify(event) + '\n'
}

describe('D5.8 — vertical slice (connector → router → catalog → renderer)', () => {
  let workdir: string
  let logPath: string
  let artifactRoot: string

  beforeEach(() => {
    workdir = mkdtempSync(join(tmpdir(), 'd5-slice-'))
    logPath = join(workdir, 'h-sutra.jsonl')
    artifactRoot = join(workdir, 'artifacts')
  })

  afterEach(() => {
    if (existsSync(workdir)) rmSync(workdir, { recursive: true, force: true })
  })

  it('founder input → routed → asset cataloged → terminal lines emitted', async () => {
    // ─── Wire ──────────────────────────────────────────────────────────
    const connector = new HSutraConnector({ log_path: logPath })
    const router = new Router()
    const catalog = new ArtifactCatalog({ root_dir: artifactRoot })
    const renderer = new RendererRegistry()
    const lines: string[] = []

    // 1. Register a TriggerSpec
    const trigger: TriggerSpec = {
      id: 'T-build-product',
      event_type: 'founder_input',
      route_predicate: { type: 'contains', value: 'build' },
      target_workflow: 'wf-build',
      domain_id: 'D38',
      description: 'Build product workflow',
    }
    router.registerTrigger(trigger)

    // 2. Connector listener → router → catalog
    let capturedHSutra: HSutraEvent | null = null
    connector.onEvent((evt) => {
      capturedHSutra = evt

      // Router decides
      const decision = router.route({
        event_type: 'founder_input',
        input_text: evt.input_text,
        hsutra: evt,
      })

      // Engine event for the routing decision
      const routingEvt: RoutingDecisionEvent = {
        type: 'routing_decision',
        ts_ms: decision.ts_ms,
        turn_id: decision.turn_id,
        mode: decision.mode,
        workflow_id: decision.workflow_id,
        trigger_id: decision.trigger_id,
        attempts_count: decision.attempts.length,
      }
      const routingLine = renderer.render(routingEvt, { hsutra: evt })
      if (routingLine) lines.push(routingLine)

      // If routed, "execute" the workflow → register an asset
      if (decision.mode === 'exact' && decision.workflow_id === 'wf-build') {
        const cataloged = catalog.register({
          domain_id: 'D38',
          content: `built artifact for turn ${evt.turn_id}`,
          asset: asset(),
          producer_execution_id: `E-${evt.turn_id}`,
        })

        const artifactEvt: ArtifactRegisteredEvent = {
          type: 'artifact_registered',
          ts_ms: cataloged.cataloged_at_ms,
          domain_id: cataloged.domain_id,
          content_sha256: cataloged.content_sha256,
          asset_kind: cataloged.asset.kind,
          producer_execution_id: cataloged.producer_execution_id,
        }
        const artifactLine = renderer.render(artifactEvt, { hsutra: evt })
        if (artifactLine) lines.push(artifactLine)
      }
    })

    // 3. Founder input arrives via the H-Sutra log
    writeFileSync(
      logPath,
      row({
        turn_id: 'turn-100',
        cell: 'DIRECT·INBOUND',
        verb: 'DIRECT',
        direction: 'INBOUND',
        input_text: 'build the new dashboard',
      }),
    )
    connector.start()
    // Connector reads on start; give it a tick for the listener to fire.
    await new Promise((r) => setImmediate(r))

    // ─── Assertions ────────────────────────────────────────────────────
    expect(capturedHSutra).not.toBeNull()
    expect(capturedHSutra!.turn_id).toBe('turn-100')

    // Two render lines: routing_decision + artifact_registered
    expect(lines).toHaveLength(2)

    // Routing line shows the cell prefix + exact match + workflow
    expect(lines[0]).toContain('[DIRECT·INBOUND]')
    expect(lines[0]).toContain('exact')
    expect(lines[0]).toContain('wf-build')
    expect(lines[0]).toContain('T-build-product')

    // Artifact line shows the catalog entry under D38
    expect(lines[1]).toContain('[DIRECT·INBOUND]')
    expect(lines[1]).toContain('[catalog]')
    expect(lines[1]).toContain('D38')
    expect(lines[1]).toContain('E-turn-100')

    // Catalog persistence: index.jsonl + content/<sha>
    const catalogedEntries = catalog.getByDomain('D38')
    expect(catalogedEntries).toHaveLength(1)
    const sha = catalogedEntries[0]!.content_sha256
    const indexFile = readFileSync(join(artifactRoot, 'D38', 'index.jsonl'), 'utf8')
    expect(indexFile).toContain(sha)
    expect(existsSync(join(artifactRoot, 'D38', 'content', sha))).toBe(true)

    // Router audit log: one decision, exact, wf-build
    const auditLog = router.getDecisionLog()
    expect(auditLog).toHaveLength(1)
    expect(auditLog[0]?.mode).toBe('exact')
    expect(auditLog[0]?.workflow_id).toBe('wf-build')

    connector.stop()
  })

  it('founder input that does NOT match a trigger → no-match decision, NO writes anywhere', async () => {
    // Codex P2.2 fold 2026-05-03: tighten the "untouched" assertions.
    // - router.getDecisionLog() must show exactly 1 'no-match' entry
    // - catalog.byDomain(*) must be empty for ANY domain (not just D38)
    // - artifactRoot must contain no files at all (no stray writes)

    const connector = new HSutraConnector({ log_path: logPath })
    const router = new Router()
    const catalog = new ArtifactCatalog({ root_dir: artifactRoot })
    const renderer = new RendererRegistry()
    const lines: string[] = []

    router.registerTrigger({
      id: 'T-build',
      event_type: 'founder_input',
      route_predicate: { type: 'contains', value: 'build' },
      target_workflow: 'wf-build',
    })

    connector.onEvent((evt) => {
      const decision = router.route({
        event_type: 'founder_input',
        input_text: evt.input_text,
        hsutra: evt,
      })
      const routingEvt: RoutingDecisionEvent = {
        type: 'routing_decision',
        ts_ms: decision.ts_ms,
        turn_id: decision.turn_id,
        mode: decision.mode,
        workflow_id: decision.workflow_id,
        trigger_id: decision.trigger_id,
        attempts_count: decision.attempts.length,
      }
      const line = renderer.render(routingEvt, { hsutra: evt })
      if (line) lines.push(line)
    })

    writeFileSync(
      logPath,
      row({
        turn_id: 'turn-200',
        input_text: 'just chatting',
      }),
    )
    connector.start()
    await new Promise((r) => setImmediate(r))

    // Render output assertion
    expect(lines).toHaveLength(1)
    expect(lines[0]).toContain('no-match')

    // Router audit log: exactly one 'no-match' decision recorded
    const log = router.getDecisionLog()
    expect(log).toHaveLength(1)
    expect(log[0]?.mode).toBe('no-match')
    expect(log[0]?.workflow_id).toBeNull()

    // Catalog state: no entries under ANY domain id we'd plausibly use
    expect(catalog.getByDomain('D38')).toHaveLength(0)
    expect(catalog.getByDomain('D1')).toHaveLength(0)

    // Strong assertion: no FS writes anywhere under artifactRoot
    expect(existsSync(artifactRoot)).toBe(false)

    connector.stop()
  })

  it('LLM-fallback path → connector listener drives async route + catalog + render', async () => {
    // Codex P1.2 fold 2026-05-03: scenario must wire fallback FROM the
    // connector listener, not in the test body. Listener invokes routeAsync
    // → catalog.register → renderer.render in one promise chain. The test
    // body only awaits the chain to settle.

    const connector = new HSutraConnector({ log_path: logPath })
    const fallback: LLMFallback = async () => ({
      workflow_id: 'wf-llm-classified',
      prompt_hash: 'a'.repeat(32),
      model: 'claude-bare-test',
    })
    const router = new Router({ llm_fallback: fallback })
    const catalog = new ArtifactCatalog({ root_dir: artifactRoot })
    const renderer = new RendererRegistry()
    const lines: string[] = []
    const pipelineDone: Promise<void>[] = []

    connector.onEvent((evt) => {
      const p = (async () => {
        const decision = await router.routeAsync({
          event_type: 'founder_input',
          input_text: evt.input_text,
          hsutra: evt,
        })
        const routingEvt: RoutingDecisionEvent = {
          type: 'routing_decision',
          ts_ms: decision.ts_ms,
          turn_id: decision.turn_id,
          mode: decision.mode,
          workflow_id: decision.workflow_id,
          trigger_id: decision.trigger_id,
          attempts_count: decision.attempts.length,
        }
        const routingLine = renderer.render(routingEvt, { hsutra: evt })
        if (routingLine) lines.push(routingLine)

        if (decision.mode === 'llm-fallback' && decision.workflow_id) {
          const cataloged = catalog.register({
            domain_id: 'D1',
            content: `llm-classified output ${evt.turn_id}`,
            asset: asset(),
            producer_execution_id: `E-${evt.turn_id}`,
          })
          const artifactEvt: ArtifactRegisteredEvent = {
            type: 'artifact_registered',
            ts_ms: cataloged.cataloged_at_ms,
            domain_id: cataloged.domain_id,
            content_sha256: cataloged.content_sha256,
            asset_kind: cataloged.asset.kind,
            producer_execution_id: cataloged.producer_execution_id,
          }
          const artifactLine = renderer.render(artifactEvt, { hsutra: evt })
          if (artifactLine) lines.push(artifactLine)
        }
      })()
      pipelineDone.push(p)
    })

    writeFileSync(
      logPath,
      row({
        turn_id: 'turn-300',
        cell: 'QUERY·INBOUND',
        input_text: 'do the thing',
      }),
    )
    connector.start()
    // Drain the listener-spawned async pipelines.
    await new Promise((r) => setImmediate(r))
    await Promise.all(pipelineDone)

    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain('llm-fallback')
    expect(lines[0]).toContain('wf-llm-classified')
    expect(lines[0]).toContain('[QUERY·INBOUND]')
    expect(lines[1]).toContain('[catalog]')
    expect(lines[1]).toContain('D1')

    // Router audit + catalog state confirm the fallback wiring landed
    expect(router.getDecisionLog()).toHaveLength(1)
    expect(router.getDecisionLog()[0]?.mode).toBe('llm-fallback')
    expect(router.getDecisionLog()[0]?.prompt_hash).toBe('a'.repeat(32))
    expect(catalog.getByDomain('D1')).toHaveLength(1)

    connector.stop()
  })

  it('multiple turns → catalog accumulates per-domain history', async () => {
    const connector = new HSutraConnector({ log_path: logPath })
    const router = new Router()
    const catalog = new ArtifactCatalog({ root_dir: artifactRoot })

    router.registerTrigger({
      id: 'T-build',
      event_type: 'founder_input',
      route_predicate: { type: 'contains', value: 'build' },
      target_workflow: 'wf-build',
    })

    connector.onEvent((evt) => {
      const decision = router.route({
        event_type: 'founder_input',
        input_text: evt.input_text,
        hsutra: evt,
      })
      if (decision.mode === 'exact' && decision.workflow_id === 'wf-build') {
        catalog.register({
          domain_id: 'D38',
          content: `output for ${evt.turn_id}`,
          asset: asset(),
          producer_execution_id: `E-${evt.turn_id}`,
        })
      }
    })

    // Three founder turns
    writeFileSync(logPath, '')
    appendFileSync(logPath, row({ turn_id: 't-1', input_text: 'build A' }))
    appendFileSync(logPath, row({ turn_id: 't-2', input_text: 'build B' }))
    appendFileSync(logPath, row({ turn_id: 't-3', input_text: 'build C' }))
    connector.start()
    await new Promise((r) => setImmediate(r))

    const history = catalog.getByDomain('D38')
    expect(history).toHaveLength(3)
    expect(history.map((h) => h.producer_execution_id)).toEqual(['E-t-1', 'E-t-2', 'E-t-3'])

    // Router audit log mirrors the routing decisions
    expect(router.getDecisionLog()).toHaveLength(3)
    expect(router.getDecisionLog().every((d) => d.mode === 'exact')).toBe(true)

    connector.stop()
  })
})
