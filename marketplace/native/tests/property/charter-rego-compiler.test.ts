/**
 * M7 Group U property tests — Charter→Rego compiler (T-088).
 *
 * Two properties (≥1000 cases each):
 *
 * 1. HAPPY: arbitrary Charters with allowed-Rego predicates (or empty
 *    predicates) compile to source that `opa parse` accepts. We can't
 *    feed the property test fully-random predicate strings — they almost
 *    never form valid Rego — so we curate a pool of known-good predicates
 *    and randomize Charter shape (id, name, count, ACL, etc.) around them.
 *    This isolates the property: "the compiler emits structurally-valid
 *    Rego given valid predicates and any Charter shape".
 *
 * 2. ADVERSARIAL: Charters whose predicates smuggle a forbidden builtin
 *    (`http.send`, `time.now_ns`, `rand.intn`, etc.) MUST be rejected with
 *    BuiltinNotAllowedError before any policy_version is computed.
 *    Coverage spans all 9 forbidden namespaces.
 *
 * The `opa parse` binary lives at `/opt/homebrew/bin/opa` (system-installed,
 * version 1.15.2, Rego v1). We invoke it once per case via execSync — at
 * 50–100ms per call, 1000 cases lands in 50–100s, acceptable for a property
 * test gate. Group V will replace this with a long-lived OPA evaluator;
 * here we just need parse-correctness as the property.
 *
 * Source-of-truth: holding/plans/native-v1.0/M7-opa-compiler.md Group U
 *                   §T-088
 */

import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { execSync } from 'node:child_process'
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  compileCharter,
  BuiltinNotAllowedError,
} from '../../src/engine/charter-rego-compiler.js'
import type { Charter } from '../../src/primitives/charter.js'
import { aclEntryArb } from './arbitraries.js'
import type {
  Constraint,
  ConstraintDurability,
  ConstraintOwnerScope,
} from '../../src/types/index.js'

const OPA_BIN = '/opt/homebrew/bin/opa'

// -----------------------------------------------------------------------------
// Curated predicate pools
// -----------------------------------------------------------------------------

/**
 * Allowed Rego predicates — valid expressions that use only the
 * compiler's allowlisted builtins + operators. Mixed shape on purpose:
 *  - empty string (skipped by the compiler — no rule emitted)
 *  - simple equality / comparison
 *  - allowlisted builtin calls
 *  - boolean composition
 */
const VALID_PREDICATE_POOL: readonly string[] = [
  '',
  'true',
  'false',
  'input.x == 1',
  'input.x != 0',
  'input.count > 5',
  'input.count >= 0',
  'count(input.items) > 0',
  'count(input.items) == 0',
  'startswith(input.id, "C-")',
  'endswith(input.path, ".md")',
  'contains(input.text, "ok")',
  'regex.match("^[a-z]+$", input.name)',
  'input.a == "x"; input.b == "y"',
  'input.flag == true',
]

/**
 * Adversarial predicates — each smuggles a forbidden builtin. The
 * compiler MUST reject every Charter that includes one in any of its
 * obligation / invariant / constraint pools.
 */
const ADVERSARIAL_PREDICATE_POOL: readonly string[] = [
  'http.send({"url": "https://x"})',
  'net.lookup_ip_addr("x.com")',
  'time.now_ns()',
  'rand.intn("x", 100, _)',
  'uuid.rfc4122("uid", _)',
  'os.getenv("HOME")',
  'opa.runtime()',
  'crypto.hmac.sha256("k", "m")',
  'env.vars.HOME',
]

// -----------------------------------------------------------------------------
// Constraint + Charter arbitraries with curated predicate pools
// -----------------------------------------------------------------------------

interface ConstraintArbOpts {
  predicateArb: fc.Arbitrary<string>
  forceType?: Constraint['type']
}

function constraintWithPredicateArb(
  opts: ConstraintArbOpts,
): fc.Arbitrary<Constraint> {
  return fc.record({
    name: fc.string({ minLength: 1, maxLength: 24 }),
    predicate: opts.predicateArb,
    durability: fc.constantFrom<ConstraintDurability>('durable', 'episodic'),
    owner_scope: fc.constantFrom<ConstraintOwnerScope>(
      'domain',
      'charter',
      'workflow',
      'execution',
    ),
    type: opts.forceType !== undefined
      ? fc.constant(opts.forceType)
      : fc.constant<Constraint['type']>(undefined),
  })
}

/**
 * Charter arbitrary with predicates drawn from the supplied pool. Charter
 * id is randomized across a wide alphabet to surface sanitization edge
 * cases (digits, unicode, special chars). All other fields are minimal but
 * shape-valid.
 */
function charterWithPredicatePoolArb(
  predicatePool: readonly string[],
): fc.Arbitrary<Charter> {
  const predicateArb = fc.constantFrom(...predicatePool)
  return fc.record({
    id: fc.string({ minLength: 1, maxLength: 32 }).map((s) => `C-${s}`),
    purpose: fc.string({ minLength: 1, maxLength: 30 }),
    scope_in: fc.string({ maxLength: 20 }),
    scope_out: fc.string({ maxLength: 20 }),
    obligations: fc.array(
      constraintWithPredicateArb({ predicateArb, forceType: 'obligation' }),
      { maxLength: 3 },
    ),
    invariants: fc.array(
      constraintWithPredicateArb({ predicateArb, forceType: 'invariant' }),
      { maxLength: 3 },
    ),
    success_metrics: fc.array(fc.string({ minLength: 1, maxLength: 16 }), {
      maxLength: 3,
    }),
    authority: fc.string({ maxLength: 16 }),
    termination: fc.string({ maxLength: 16 }),
    constraints: fc.array(constraintWithPredicateArb({ predicateArb }), {
      maxLength: 3,
    }),
    acl: fc.array(aclEntryArb, { maxLength: 3 }),
  }) as fc.Arbitrary<Charter>
}

/**
 * Charter arbitrary that injects ONE adversarial predicate into a random
 * pool slot. Other slots come from VALID_PREDICATE_POOL so the
 * BuiltinNotAllowedError is the only failure mode under test.
 */
function charterWithAdversarialPredicateArb(
  adversarialPredicate: string,
): fc.Arbitrary<Charter> {
  const validArb = fc.constantFrom(...VALID_PREDICATE_POOL)
  // Poison slot: replace one random constraint with the adversarial
  // predicate. Place it in obligations to exercise the most heavily-used
  // pool (obligations contribute BOTH allow and deny rules).
  return fc.record({
    id: fc.string({ minLength: 1, maxLength: 32 }).map((s) => `C-${s}`),
    purpose: fc.string({ minLength: 1, maxLength: 30 }),
    scope_in: fc.string({ maxLength: 20 }),
    scope_out: fc.string({ maxLength: 20 }),
    obligations: fc
      .array(
        constraintWithPredicateArb({
          predicateArb: validArb,
          forceType: 'obligation',
        }),
        { minLength: 0, maxLength: 2 },
      )
      .map((rest) => [
        // Force the adversarial predicate into slot 0; rest follow.
        {
          name: 'poisoned',
          predicate: adversarialPredicate,
          durability: 'durable' as ConstraintDurability,
          owner_scope: 'charter' as ConstraintOwnerScope,
          type: 'obligation' as Constraint['type'],
        },
        ...rest,
      ]),
    invariants: fc.array(
      constraintWithPredicateArb({
        predicateArb: validArb,
        forceType: 'invariant',
      }),
      { maxLength: 2 },
    ),
    success_metrics: fc.array(fc.string({ minLength: 1, maxLength: 16 }), {
      maxLength: 2,
    }),
    authority: fc.string({ maxLength: 16 }),
    termination: fc.string({ maxLength: 16 }),
    constraints: fc.array(
      constraintWithPredicateArb({ predicateArb: validArb }),
      { maxLength: 2 },
    ),
    acl: fc.array(aclEntryArb, { maxLength: 2 }),
  }) as fc.Arbitrary<Charter>
}

// -----------------------------------------------------------------------------
// opa parse helper — one tmpdir per test, cleaned up at end
// -----------------------------------------------------------------------------

interface OpaParseHarness {
  parse(rego_source: string, name: string): boolean
  cleanup(): void
}

function makeOpaParseHarness(): OpaParseHarness {
  const dir = mkdtempSync(join(tmpdir(), 'm7-charter-rego-'))
  let counter = 0
  return {
    parse(rego_source: string, name: string): boolean {
      counter += 1
      const file = join(dir, `${name}-${counter}.rego`)
      writeFileSync(file, rego_source)
      try {
        execSync(`${OPA_BIN} parse "${file}"`, { stdio: 'pipe' })
        return true
      } catch {
        return false
      }
    },
    cleanup(): void {
      try {
        rmSync(dir, { recursive: true, force: true })
      } catch {
        // best-effort
      }
    },
  }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe('Charter→Rego compiler (M7 Group U property tests)', () => {
  it('arbitrary valid Charters compile to opa-parseable Rego (≥1000 cases)', () => {
    const harness = makeOpaParseHarness()
    try {
      fc.assert(
        fc.property(charterWithPredicatePoolArb(VALID_PREDICATE_POOL), (charter) => {
          const compiled = compileCharter(charter)
          // Property: rego_source is non-empty, policy_version is hex
          // sha256 (64 chars), policy_id is a Rego identifier.
          if (compiled.rego_source.length === 0) return false
          if (!/^[a-f0-9]{64}$/.test(compiled.policy_version)) return false
          if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(compiled.policy_id)) return false
          // Property: opa parse accepts the source.
          return harness.parse(compiled.rego_source, compiled.policy_id)
        }),
        { numRuns: 1000 },
      )
    } finally {
      harness.cleanup()
    }
  }, 240_000)

  it('Charters with forbidden builtins are rejected (≥1000 cases)', () => {
    fc.assert(
      fc.property(
        fc
          .constantFrom(...ADVERSARIAL_PREDICATE_POOL)
          .chain((adv) => charterWithAdversarialPredicateArb(adv)),
        (charter) => {
          try {
            compileCharter(charter)
            return false // should have thrown
          } catch (e) {
            if (!(e instanceof BuiltinNotAllowedError)) return false
            if (e.charter_id !== charter.id) return false
            if (typeof e.builtin_name !== 'string' || e.builtin_name.length === 0) {
              return false
            }
            return true
          }
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('policy_version is deterministic for identical Charter input', () => {
    const charter: Charter = {
      id: 'C-determ',
      purpose: 'deterministic test',
      scope_in: '',
      scope_out: '',
      obligations: [
        {
          name: 'must_log',
          predicate: 'count(input.events) > 0',
          durability: 'durable',
          owner_scope: 'charter',
          type: 'obligation',
        },
      ],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [],
    }
    const a = compileCharter(charter)
    const b = compileCharter(charter)
    if (a.policy_version !== b.policy_version) {
      throw new Error(
        `policy_version not deterministic: ${a.policy_version} vs ${b.policy_version}`,
      )
    }
    if (a.rego_source !== b.rego_source) {
      throw new Error('rego_source not deterministic')
    }
  })

  it('policy_version differs when Charter content differs', () => {
    const base: Charter = {
      id: 'C-x',
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
    const variant: Charter = {
      ...base,
      obligations: [
        {
          name: 'extra',
          predicate: 'input.x == 1',
          durability: 'durable',
          owner_scope: 'charter',
          type: 'obligation',
        },
      ],
    }
    const a = compileCharter(base)
    const b = compileCharter(variant)
    if (a.policy_version === b.policy_version) {
      throw new Error('policy_version collided across distinct Charters')
    }
  })

  it('every adversarial predicate namespace is independently rejected', () => {
    // Direct unit-style coverage — each forbidden namespace must trigger
    // BuiltinNotAllowedError. Property tests above cover them too, but
    // this gives a fast O(N) signal when one regex regresses.
    for (const adversarial of ADVERSARIAL_PREDICATE_POOL) {
      const charter: Charter = {
        id: 'C-poisoned',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [
          {
            name: 'x',
            predicate: adversarial,
            durability: 'durable',
            owner_scope: 'charter',
            type: 'obligation',
          },
        ],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [],
      }
      let threw = false
      try {
        compileCharter(charter)
      } catch (e) {
        if (e instanceof BuiltinNotAllowedError) threw = true
      }
      if (!threw) {
        throw new Error(
          `expected BuiltinNotAllowedError for predicate "${adversarial}"`,
        )
      }
    }
  })
})
