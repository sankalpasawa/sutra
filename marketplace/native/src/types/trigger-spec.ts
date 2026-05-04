/**
 * TriggerSpec — D2 step 2 schema (deferred-to-Phase-3 primitive,
 * v1.0 inline form per V2 §8 lines 240-243).
 *
 * Per founder direction 2026-05-02: TriggerSpec is the routing primitive
 * that binds an EVENT shape (cron tick, founder input matching keywords,
 * file drop, webhook) to a TARGET WORKFLOW id. The Router consults the
 * registered TriggerSpecs and dispatches the first whose predicate matches.
 *
 * Predicate flavor (v1.0): STRUCTURED only — no string parsing. A string
 * predicate parser ("contains('X') AND contains('Y')") is deferred to v1.1
 * to keep the deterministic-routing surface minimal + auditable.
 *
 * I-NPD-1 (softened): predicates are evaluated deterministically. LLM
 * fallback is OPTIONAL, opt-in per Router config, and every fallback call
 * records prompt_hash for replay.
 */

export type TriggerEventType =
  | 'founder_input' // Founder typed something in CC; H-Sutra layer classified it
  | 'cron'          // Scheduled trigger
  | 'file_drop'     // File appeared in inbox dir (v1.1+)
  | 'webhook'       // External HTTP event (v1.2+)

/** Runtime allow-list — kept in sync with TriggerEventType. */
export const TRIGGER_EVENT_TYPES: ReadonlySet<TriggerEventType> = new Set([
  'founder_input',
  'cron',
  'file_drop',
  'webhook',
])

/**
 * Structured predicate. Either a leaf condition (contains, matches, eq)
 * or a logical combinator (and, or, not).
 *
 * Leaf predicates examine a context object (input text + H-Sutra fields).
 * Combinators recurse over child predicates.
 */
export type Predicate =
  | { readonly type: 'contains'; readonly value: string; readonly case_sensitive?: boolean }
  | { readonly type: 'matches'; readonly pattern: string; readonly flags?: string }
  | { readonly type: 'event_type_eq'; readonly value: TriggerEventType }
  | { readonly type: 'cell_eq'; readonly value: string }
  | { readonly type: 'verb_eq'; readonly value: 'DIRECT' | 'QUERY' | 'ASSERT' }
  | { readonly type: 'direction_eq'; readonly value: 'INBOUND' | 'INTERNAL' | 'OUTBOUND' }
  | { readonly type: 'risk_eq'; readonly value: 'LOW' | 'MEDIUM' | 'HIGH' }
  | { readonly type: 'always_true' }
  | { readonly type: 'and'; readonly clauses: ReadonlyArray<Predicate> }
  | { readonly type: 'or'; readonly clauses: ReadonlyArray<Predicate> }
  | { readonly type: 'not'; readonly clause: Predicate }

/**
 * v1.3.0 W1.8 + W3 fold (codex): payload for cron triggers. The CadenceSpec
 * shape is owned by `src/engine/cadence-scheduler.ts` (4 kinds:
 * every_n_minutes / every_n_hours / every_day_at / cron). It's redeclared
 * here as a structural type — kept identical to the scheduler's CadenceSpec
 * so trigger-spec stays zero-runtime-dependency on the scheduler module
 * (which pulls async machinery this primitive should not).
 *
 * v1.3 W1.8 scope: TriggerSpec ACCEPTS + PERSISTS cadence_spec; the actual
 * scheduler wiring (CadenceScheduler.register-from-trigger) is W3 work.
 * Shipping the field early closes the codex W3 fold "TriggerSpec lacks
 * cadence payload" so when W3 lands, on-disk triggers are forward-
 * compatible.
 */
export type CadenceSpec =
  | { readonly kind: 'every_n_minutes'; readonly n: number }
  | { readonly kind: 'every_n_hours'; readonly n: number }
  | { readonly kind: 'every_day_at'; readonly hour_utc: number; readonly minute_utc: number }
  | { readonly kind: 'cron'; readonly expression: string }

export interface TriggerSpec {
  /** Stable id, e.g. 'T-build-product'. */
  readonly id: string
  /** Event class this trigger listens for. */
  readonly event_type: TriggerEventType
  /** Predicate evaluated against the event + input text. */
  readonly route_predicate: Predicate
  /** Workflow id to dispatch on match. */
  readonly target_workflow: string
  /** Owning Domain id (for audit + Charter lookup). */
  readonly domain_id?: string
  /** Owning Charter id (for ACL). */
  readonly charter_id?: string
  /** Free-form description for operators. */
  readonly description?: string
  /**
   * v1.3.0 W1.8 + W3 fold (codex). When event_type='cron', the cadence
   * scheduler payload describing the firing schedule. Persisted at v1.3 W1
   * — actually consumed by CadenceScheduler at v1.3 W3.
   */
  readonly cadence_spec?: CadenceSpec
}

/** Runtime allow-list of Predicate.type literals — kept in sync with Predicate union. */
export const PREDICATE_TYPES: ReadonlySet<string> = new Set([
  'contains',
  'matches',
  'event_type_eq',
  'cell_eq',
  'verb_eq',
  'direction_eq',
  'risk_eq',
  'always_true',
  'and',
  'or',
  'not',
])

/**
 * Structural type guard for a Predicate — verifies the discriminator only.
 * Deep-validity (e.g. that an `and` clause's children are themselves valid)
 * is intentionally NOT checked here — `evaluate()` is total over the union
 * and any leaves with unknown discriminator return false at evaluation time.
 * The point of this guard is to catch obvious misuse at the registration
 * boundary, not to fully type-check user input.
 */
export function isPredicate(value: unknown): value is Predicate {
  if (typeof value !== 'object' || value === null) return false
  const t = (value as { type?: unknown }).type
  return typeof t === 'string' && PREDICATE_TYPES.has(t)
}

/**
 * Type guard — used by the Router on registration to reject malformed specs.
 * Tightened per codex master review (2026-05-03): event_type is checked
 * against the runtime allow-list, and route_predicate must have a known
 * Predicate.type discriminator.
 */
export function isTriggerSpec(value: unknown): value is TriggerSpec {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Partial<TriggerSpec>
  return (
    typeof v.id === 'string' &&
    v.id.length > 0 &&
    typeof v.event_type === 'string' &&
    TRIGGER_EVENT_TYPES.has(v.event_type as TriggerEventType) &&
    typeof v.target_workflow === 'string' &&
    v.target_workflow.length > 0 &&
    isPredicate(v.route_predicate)
  )
}
