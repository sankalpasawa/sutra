/**
 * user-kit — runtime persistence for founder-created Domains, Charters, Workflows.
 *
 * Storage layout (per-user, NOT shipped with plugin):
 *   $SUTRA_NATIVE_HOME/user-kit/domains/<id>.json
 *   $SUTRA_NATIVE_HOME/user-kit/charters/<id>.json
 *   $SUTRA_NATIVE_HOME/user-kit/workflows/<id>.json
 *
 * Default $SUTRA_NATIVE_HOME = ~/.sutra-native
 *
 * Every load round-trips through createDomain / createCharter / createWorkflow
 * so primitive validators run on disk content too — defense against drift if
 * a founder hand-edits the JSON.
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { createCharter, type Charter } from '../primitives/charter.js'
import { createDomain, type Domain } from '../primitives/domain.js'
import { createWorkflow, type Workflow } from '../primitives/workflow.js'

export interface UserKitOptions {
  /** Override storage root. Defaults to $SUTRA_NATIVE_HOME or ~/.sutra-native. */
  readonly home?: string
  /** env override for testing. */
  readonly env?: NodeJS.ProcessEnv
}

export function userKitRoot(opts: UserKitOptions = {}): string {
  const env = opts.env ?? process.env
  if (opts.home) return opts.home
  if (env.SUTRA_NATIVE_HOME) return env.SUTRA_NATIVE_HOME
  const home = env.HOME ?? '/tmp'
  return `${home}/.sutra-native`
}

function entityDir(kind: 'domains' | 'charters' | 'workflows', opts: UserKitOptions = {}): string {
  return join(userKitRoot(opts), 'user-kit', kind)
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true })
}

function writeJson(path: string, value: unknown): void {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8' })
}

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf8'))
}

// ---------------------------------------------------------------------------
// Domain
// ---------------------------------------------------------------------------

export function persistDomain(d: Domain, opts: UserKitOptions = {}): string {
  const dir = entityDir('domains', opts)
  ensureDir(dir)
  const path = join(dir, `${d.id}.json`)
  writeJson(path, d)
  return path
}

export function loadDomain(id: string, opts: UserKitOptions = {}): Domain | null {
  const path = join(entityDir('domains', opts), `${id}.json`)
  if (!existsSync(path)) return null
  return createDomain(readJson(path) as Parameters<typeof createDomain>[0])
}

export function listDomains(opts: UserKitOptions = {}): Domain[] {
  const dir = entityDir('domains', opts)
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => createDomain(readJson(join(dir, f)) as Parameters<typeof createDomain>[0]))
}

// ---------------------------------------------------------------------------
// Charter
// ---------------------------------------------------------------------------

export function persistCharter(c: Charter, opts: UserKitOptions = {}): string {
  const dir = entityDir('charters', opts)
  ensureDir(dir)
  const path = join(dir, `${c.id}.json`)
  writeJson(path, c)
  return path
}

export function loadCharter(id: string, opts: UserKitOptions = {}): Charter | null {
  const path = join(entityDir('charters', opts), `${id}.json`)
  if (!existsSync(path)) return null
  return createCharter(readJson(path) as Parameters<typeof createCharter>[0])
}

export function listCharters(opts: UserKitOptions = {}): Charter[] {
  const dir = entityDir('charters', opts)
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => createCharter(readJson(join(dir, f)) as Parameters<typeof createCharter>[0]))
}

// ---------------------------------------------------------------------------
// Workflow
// ---------------------------------------------------------------------------

export function persistWorkflow(w: Workflow, opts: UserKitOptions = {}): string {
  const dir = entityDir('workflows', opts)
  ensureDir(dir)
  const path = join(dir, `${w.id}.json`)
  writeJson(path, w)
  return path
}

export function loadWorkflow(id: string, opts: UserKitOptions = {}): Workflow | null {
  const path = join(entityDir('workflows', opts), `${id}.json`)
  if (!existsSync(path)) return null
  return createWorkflow(readJson(path) as Parameters<typeof createWorkflow>[0])
}

export function listWorkflows(opts: UserKitOptions = {}): Workflow[] {
  const dir = entityDir('workflows', opts)
  if (!existsSync(dir)) return []
  return readdirSync(dir)
    .filter((f) => f.endsWith('.json'))
    .map((f) => createWorkflow(readJson(join(dir, f)) as Parameters<typeof createWorkflow>[0]))
}

// ---------------------------------------------------------------------------
// Aggregate
// ---------------------------------------------------------------------------

export interface UserKit {
  readonly domains: ReadonlyArray<Domain>
  readonly charters: ReadonlyArray<Charter>
  readonly workflows: ReadonlyArray<Workflow>
}

export function loadUserKit(opts: UserKitOptions = {}): UserKit {
  return {
    domains: listDomains(opts),
    charters: listCharters(opts),
    workflows: listWorkflows(opts),
  }
}
