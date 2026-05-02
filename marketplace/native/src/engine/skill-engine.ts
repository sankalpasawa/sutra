/**
 * SKILL ENGINE — M6 Group O (T-064..T-068).
 *
 * Resolves skill_ref → Workflow at execution time. A Skill is a Workflow with
 * `reuse_tag=true` (V2.3 §A11). Per codex P1.2 (2026-04-30) the canonical form
 * of `return_contract` is a JSON Schema STRING; the engine compiles each
 * schema once at register-time via ajv and caches the compiled validator for
 * fast child-output validation by Group P (skill-invocation adapter).
 *
 * Surface:
 *   register(skill)      — validate (Skill + non-empty + parseable JSON Schema),
 *                          insert into registry, cache compiled ajv validator
 *   unregister(skill_ref)— remove registry entry + cached validator (silent on miss)
 *   resolve(skill_ref)   — Workflow on hit; null on miss
 *   validateOutputs(...) — used by Group P at child completion to gate outputs
 *                          against the cached return_contract validator
 *
 * Sources of truth:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group O
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P1.2 + P2.1)
 *   - holding/research/2026-04-28-v2-architecture-spec.md §A11 (Skill + return_contract)
 */

// Ajv 8.x ships as CJS; under TS NodeNext the default-import resolves
// to the module namespace, not the class. `{ default as Ajv }` makes
// NodeNext synthesize the CJS default into a named binding so the
// constructor + type usage below works unchanged.
import { Ajv, type AnySchema, type ValidateFunction } from 'ajv'
import type { Workflow } from '../primitives/workflow.js'

/**
 * Result of `validateOutputs()`. A discriminated union so callers in Group P
 * can branch on `valid` without optional-property gymnastics.
 */
export type ValidateOutputsResult =
  | { valid: true }
  | { valid: false; errors: string }

export class SkillEngine {
  private readonly registry: Map<string, Workflow> = new Map()
  private readonly validatorCache: Map<string, ValidateFunction> = new Map()
  private readonly ajv: Ajv

  constructor() {
    // `strict: false` — Sutra Skills may declare schemas authored against
    // older JSON Schema drafts; permissive compilation is the right default
    // for v1.0. Strict-mode promotion is a v1.x decision (D-NS-18 future).
    this.ajv = new Ajv({ strict: false })
  }

  /**
   * Register a Skill (Workflow with reuse_tag=true) under its `id`.
   *
   * Codex P1.2 rejection paths (HARD):
   *   (a) reuse_tag !== true        → not a Skill
   *   (b) return_contract empty/null → V2 §A11 violation
   *   (c) return_contract not valid JSON Schema → ajv.compile throws
   *
   * On success, the compiled validator is cached so Group P can validate
   * child-execution outputs in O(1) without re-compiling per invocation.
   */
  register(skill: Workflow): void {
    if (skill.reuse_tag !== true) {
      throw new Error(
        `SkillEngine.register: only Skills (reuse_tag=true) can be registered; got reuse_tag=${String(skill.reuse_tag)}`,
      )
    }
    if (
      skill.return_contract === null ||
      skill.return_contract === undefined ||
      typeof skill.return_contract !== 'string' ||
      skill.return_contract.length === 0
    ) {
      throw new Error(
        `SkillEngine.register: Skill ${skill.id} missing return_contract (V2 §A11 HARD compliance)`,
      )
    }

    let compiled: ValidateFunction
    try {
      // ajv.compile accepts AnySchema (object | boolean). We accept any parsed
      // JSON shape and let ajv reject invalid schema documents at compile time;
      // the catch block converts ajv's error into the canonical SkillEngine
      // error message. Cast is safe because the failure path is the same
      // whether the JSON is structurally invalid or semantically invalid.
      const parsed = JSON.parse(skill.return_contract) as AnySchema
      compiled = this.ajv.compile(parsed)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      throw new Error(
        `SkillEngine.register: return_contract for ${skill.id} is not valid JSON Schema: ${msg}`,
      )
    }

    this.registry.set(skill.id, skill)
    this.validatorCache.set(skill.id, compiled)
  }

  /**
   * Unregister a Skill by id (== skill_ref). Removes both the registry entry
   * AND the cached validator. Silent no-op if id is unknown — keeps cleanup
   * idempotent for parent executors that don't track registration state.
   */
  unregister(skill_ref: string): void {
    this.registry.delete(skill_ref)
    this.validatorCache.delete(skill_ref)
  }

  /**
   * Resolve a skill_ref to its registered Workflow. Returns `null` on miss
   * (per codex P1.4 → Group P synthesizes a step-failure with the M5 canonical
   * failure-format on null resolution).
   */
  resolve(skill_ref: string): Workflow | null {
    return this.registry.get(skill_ref) ?? null
  }

  /**
   * Validate child-execution outputs against the cached return_contract.
   * Used by Group P at child completion. Returns a discriminated union so
   * callers can extract `errors` only when invalid.
   */
  validateOutputs(skill_ref: string, outputs: unknown): ValidateOutputsResult {
    const validator = this.validatorCache.get(skill_ref)
    if (!validator) {
      return {
        valid: false,
        errors: `no validator cached for skill_ref=${skill_ref}`,
      }
    }
    const ok = validator(outputs)
    if (ok) return { valid: true }
    return { valid: false, errors: this.ajv.errorsText(validator.errors) }
  }
}
