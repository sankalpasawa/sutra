/**
 * Tier-2 artifact assertions (v1 strict grammar; codex fold 2026-05-08).
 *
 * Supported hard_constraint patterns:
 *   forbid:   "no <term>" / "without <term>" / "do not <term>"
 *   require:  "must include <term>"
 *   count:    "<n> <unit>" (must appear literally in artifacts)
 * Anything else -> SKIPPED with id "tier-2/constraint-deferred-to-rubric/<slug>".
 * Tier-4 picks up deferred constraints.
 *
 * Cross-stage propagation invariant: Jaccard token similarity over the
 * FIRST PARAGRAPH only of consecutive stage artifacts. Threshold 0.2.
 *
 * Industry borrow: Hypothesis / fast-check property-based testing —
 * cross-stage propagation is a structural invariant.
 *
 * Industry borrow: BDD Given/When/Then — Cucumber. Acceptance examples'
 * `then` clauses become token-presence predicates over artifacts.
 *
 * SPEC: docs/superpowers/specs/2026-05-07-verifier-engine-v1-design.md §5
 */

import type { GoalContract } from '../../../types/goal-contract.js'
import type { AssertionResult, NativeRun } from '../../../types/assertion-report.js'

const SLUG = (s: string): string =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

const PROPAGATION_THRESHOLD = 0.2

const FORBID_PREFIXES = ['no ', 'without ', 'do not ']
const REQUIRE_PREFIX = 'must include '
const COUNT_RE = /^(\d+)\s+(\w+)$/

export function runTier2Artifact(contract: GoalContract, run: NativeRun): AssertionResult[] {
  const out: AssertionResult[] = []
  const allText = run.artifacts.map(a => a.content.toLowerCase()).join('\n')

  // Hard constraints -- strict grammar
  for (const hc of contract.hard_constraints) {
    out.push(checkHardConstraint(hc, allText))
  }

  // Non-goals -- must NOT appear (literal substring)
  for (const ng of contract.non_goals) {
    const found = allText.includes(ng.toLowerCase())
    out.push({
      id: `tier-2/non-goal/${SLUG(ng)}`,
      tier: 'artifact',
      axis: 'Constraint-Honor',
      status: found ? 'FAIL' : 'PASS',
      message: found ? `non-goal violated: "${ng}"` : `non-goal honored: "${ng}"`,
    })
  }

  // Evidence required -- per stage/field (strip leading § marker)
  for (const ev of contract.evidence_required) {
    const stripped = ev.field.replace(/^§/, '')
    const stageArt = run.artifacts.find(a => a.stage === ev.stage)
    const ok = !!stageArt && stageArt.content.toLowerCase().includes(stripped.toLowerCase())
    out.push({
      id: `tier-2/evidence/${ev.stage}/${SLUG(stripped)}`,
      tier: 'artifact',
      axis: 'Acceptance-Coverage',
      status: ok ? 'PASS' : 'FAIL',
      message: ok
        ? `evidence present in ${ev.stage}.md: ${ev.field}`
        : `evidence missing in ${ev.stage}.md: ${ev.field}`,
    })
  }

  // Acceptance examples -- `then` clause token presence (>=60% of >3-char tokens)
  for (const ex of contract.acceptance_examples) {
    const tokens = tokenize(ex.then)
    const hits = tokens.filter(t => allText.includes(t)).length
    const ratio = tokens.length === 0 ? 1 : hits / tokens.length
    const ok = ratio >= 0.6
    out.push({
      id: `tier-2/acceptance/${SLUG(ex.then).slice(0, 40)}`,
      tier: 'artifact',
      axis: 'Acceptance-Coverage',
      status: ok ? 'PASS' : 'FAIL',
      message: `acceptance "${ex.then}" token coverage ${(ratio * 100).toFixed(0)}%`,
    })
  }

  // Cross-stage propagation -- first-paragraph Jaccard
  if (run.artifacts.length >= 2) {
    let minSim = 1
    for (let i = 1; i < run.artifacts.length; i++) {
      const a = new Set(tokenize(firstParagraph(run.artifacts[i - 1].content)))
      const b = new Set(tokenize(firstParagraph(run.artifacts[i].content)))
      const inter = [...a].filter(t => b.has(t)).length
      const union = new Set([...a, ...b]).size
      const sim = union === 0 ? 0 : inter / union
      if (sim < minSim) minSim = sim
    }
    out.push({
      id: 'tier-2/cross-stage-drift',
      tier: 'artifact',
      axis: 'Cross-Stage-Drift',
      status: minSim >= PROPAGATION_THRESHOLD ? 'PASS' : 'FAIL',
      message: `min first-paragraph Jaccard ${minSim.toFixed(2)} (threshold ${PROPAGATION_THRESHOLD})`,
    })
  }

  return out
}

function checkHardConstraint(hc: string, haystack: string): AssertionResult {
  const lc = hc.toLowerCase().trim()

  // forbid
  for (const pfx of FORBID_PREFIXES) {
    if (lc.startsWith(pfx)) {
      const term = lc.slice(pfx.length).trim()
      const positiveCount = countOccurrences(haystack, term)
      const negationCount = countOccurrences(haystack, `${pfx}${term}`)
      const violated = positiveCount > negationCount
      return {
        id: `tier-2/hard-constraint/${SLUG(hc)}`,
        tier: 'artifact',
        axis: 'Constraint-Honor',
        status: violated ? 'FAIL' : 'PASS',
        message: violated ? `forbid violated: "${hc}"` : `forbid honored: "${hc}"`,
      }
    }
  }

  // require
  if (lc.startsWith(REQUIRE_PREFIX)) {
    const term = lc.slice(REQUIRE_PREFIX.length).trim().replace(/^§/, '')
    const found = haystack.includes(term)
    return {
      id: `tier-2/hard-constraint/${SLUG(hc)}`,
      tier: 'artifact',
      axis: 'Constraint-Honor',
      status: found ? 'PASS' : 'FAIL',
      message: found ? `require satisfied: "${hc}"` : `require violated: "${hc}"`,
    }
  }

  // count: "<n> <unit>"
  const m = lc.match(COUNT_RE)
  if (m) {
    const [, n, unit] = m
    const found = new RegExp(`\\b${n}\\s+${unit}\\b`, 'i').test(haystack)
    return {
      id: `tier-2/hard-constraint/${SLUG(hc)}`,
      tier: 'artifact',
      axis: 'Constraint-Honor',
      status: found ? 'PASS' : 'FAIL',
      message: found ? `count satisfied: "${hc}"` : `count violated: "${hc}"`,
    }
  }

  // No grammar match -> deferred to rubric tier
  return {
    id: `tier-2/constraint-deferred-to-rubric/${SLUG(hc)}`,
    tier: 'artifact',
    axis: 'Constraint-Honor',
    status: 'SKIPPED',
    message: `constraint "${hc}" not in v1 grammar; deferred to tier-4 rubric`,
  }
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0
  const re = new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')
  return (haystack.match(re) || []).length
}

function firstParagraph(s: string): string {
  const idx = s.indexOf('\n\n')
  if (idx >= 0) return s.slice(0, idx)
  return s.slice(0, 200)
}

function tokenize(s: string): string[] {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 3)
}
