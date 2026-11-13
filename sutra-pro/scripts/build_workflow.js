export const meta = {
  name: 'sutra-app-build-v2',
  description: 'Build the Sutra app work packages in dependency order (one developer agent per package in its own worktree, locked merge gate), then review each merged package with three independent lenses, verify findings adversarially, and fix them through the same gate',
  phases: [
    { title: 'Build', detail: 'a developer agent starts when its dependencies have merged; two fix attempts and one rescue attempt' },
    { title: 'Review', detail: 'three lenses per merged package: spec conformance, adversarial correctness, test adequacy (mutation)' },
    { title: 'Verify', detail: 'a skeptic tries to refute each medium or higher finding that has no reproduction' },
    { title: 'Fix', detail: 'one fixer per package applies confirmed findings through the same locked merge gate' },
  ],
}

// the plan is injected by the launcher as EMBEDDED_ARGS (written by scripts/make_build_run.py); explicit args win when given
const A = (args && Object.keys(args).length ? args : (typeof EMBEDDED_ARGS !== 'undefined' ? EMBEDDED_ARGS : {}))
const APP = A.app || '~/Desktop/development/sutra-pro'
const WT = APP + '-wt'
// an extraction of `prototypes/j2` (git archive <commit> prototypes/j2 | tar -x --strip-components=2 -C <new empty folder>): the plan's `j2` argument,
// else the environment variable SUTRA_J2_CHECKOUT (the one scripts/vendor_j2.py reads). There is no default: a path under a home folder is one machine's.
const J2 = A.j2 || (typeof process !== 'undefined' && process.env && process.env.SUTRA_J2_CHECKOUT) || ''
const PLUGIN = '~/Desktop/development/sutra/marketplace/plugin'
const WPS = A.wps || []
const ALREADY = new Set(A.alreadyMerged || [])
const REVIEWED = new Set(A.alreadyReviewed || [])
const GATED = new Set(A.gateOnReview || [])
const SKIP_REVIEW = !!A.skipReview
const REVIEW_SLOTS = A.reviewSlots || 3
const REVIEW_ONLY = A.reviewOnly ? new Set(A.reviewOnly) : null          // when given, only these packages are reviewed
const LENS_KEYS = A.reviewLenses || ['spec', 'break', 'tests']           // which review lenses run
const PRE = A.preConfirmed || {}                                         // findings already confirmed by an earlier review: fix them, skip the review
const MAX_PARALLEL = A.maxParallel || 5                                  // developer agents running at once (paces token use)
const EFFORT = A.effort || 'high'                                          // reasoning effort of the build agents (the session default, max, costs far more per package)

const STR = { type: 'string' }
const STRS = { type: 'array', items: STR }
const DEV = { type: 'object', properties: {
  merged: { type: 'boolean' }, commit: STR, summary: STR,
  files: STRS, tests: STRS,
  acceptance: { type: 'array', items: { type: 'object', properties: { cmd: STR, ok: { type: 'boolean' } }, required: ['cmd', 'ok'] } },
  mutation_check: STR, deviations: STRS, needs: STRS, risks: STRS, blocked_reason: STR }, required: ['merged', 'summary'] }
const FINDING = { type: 'object', properties: {
  severity: { type: 'string', enum: ['blocker', 'high', 'medium', 'low'] },
  kind: { type: 'string', enum: ['spec', 'bug', 'test', 'design'] },
  file: STR, line: { type: 'number' }, title: STR, detail: STR, repro: STR, proven: { type: 'boolean' }, fix_hint: STR },
  required: ['severity', 'kind', 'file', 'title', 'detail', 'proven'] }
const REVIEW = { type: 'object', properties: {
  lens: STR, not_merged: { type: 'boolean' }, summary: STR,
  findings: { type: 'array', items: FINDING }, suspicions: STRS, cross: STRS }, required: ['lens', 'summary', 'findings'] }
const VERDICT = { type: 'object', properties: { confirmed: { type: 'boolean' }, evidence: STR }, required: ['confirmed', 'evidence'] }
const FIX = { type: 'object', properties: {
  merged: { type: 'boolean' }, commit: STR, summary: STR, fixed: STRS,
  skipped: { type: 'array', items: { type: 'object', properties: { title: STR, reason: STR }, required: ['title', 'reason'] } },
  blocked_reason: STR }, required: ['merged', 'summary'] }

// at most n review-phase agents at once, so developer agents always find free slots under the workflow's own cap
function makeSemaphore(n) {
  let active = 0
  const waiters = []
  let settling = false
  // waiters are served highest priority first (equal priority: first come, first served; Array.sort is stable).
  // A free slot is not handed out at once: the requests of one burst all join the queue first, so the highest priority one starts first
  // (otherwise the first packages to reach the queue won, in the order their dependency promises happened to resolve)
  const drain = () => { while (active < n && waiters.length) { active++; waiters.shift().res() } }
  const settle = async () => { if (settling) return; settling = true; for (let i = 0; i < 300; i++) await null; settling = false; drain() }
  const acquire = prio => new Promise(res => { waiters.push({ res, prio }); waiters.sort((a, b) => b.prio - a.prio); settle() })
  const release = () => { active--; settle() }
  return { run: async (fn, prio = 0) => { await acquire(prio); try { return await fn() } finally { release() } } }
}
const sem = makeSemaphore(REVIEW_SLOTS)
const devSem = makeSemaphore(MAX_PARALLEL)
// circuit breaker: three agents in a row that return nothing (a usage limit, an outage) stop new work; what is merged stays merged,
// and the launcher can be run again later (merged packages are read from git)
let nulls = 0
let HALT = false
const noteResult = r => { if (r) nulls = 0; else if (++nulls >= 3 && !HALT) { HALT = true; log('HALT: three agents in a row returned nothing; no new work is started') } return r }

const SOURCES = J2
  ? `The J2 prototype (an extraction of prototypes/j2) at ${J2} and the Sutra plugin at ${PLUGIN} are READ-ONLY sources (never the plugin's sutra-ui folder).`
  : `No J2 folder is given for this run (SUTRA_J2_CHECKOUT names an extraction of prototypes/j2 when there is one). The Sutra plugin at ${PLUGIN} is a READ-ONLY source (never the plugin's sutra-ui folder).`
const RULES = `RULES. The repo is ${APP} (local git, branch main). Local only: never push, never open PRs, never run release scripts, touch nothing outside ${APP}, its worktree folder ${WT} and /tmp. ${SOURCES} The owner is asleep: decide on your own, never ask a question, and write every decision and deviation down. Run Python only through scripts/py of the checkout you work in (it puts that checkout's code first and pins TMPDIR); never the system python for project code. Test files must have project-unique basenames unless their folder has an __init__.py (tests/test_layout.py enforces it).`

function devPrompt(wp, attempt, prior) {
  const spec = wp.spec ? ('\nFULL SPEC (given by the caller; it adds to the section file for this package):\n' + wp.spec + '\n') : ''
  const retry = attempt === 0 ? '' : attempt < 3
    ? ('\nTHIS IS ATTEMPT ' + (attempt + 1) + '. The previous attempt reported: ' + JSON.stringify(prior || {}) + '\nInspect what exists before doing anything: run scripts/wt.sh status, look at the worktree ' + WT + '/' + wp.id + ' (git log, git status), and continue from there instead of starting over. Fix the reported cause (gate failure, conflict, missing piece) and merge.\n')
    : ('\nRESCUE ATTEMPT. Three developers failed on this package. Their last report: ' + JSON.stringify(prior || {}) + '\nDiagnose the ROOT cause first (read their worktree and logs under ' + WT + '/' + wp.id + '): an inconsistent or impossible spec, a broken dependency, a flaky or order-dependent test, an environment problem, or a plain bug. Fix it for real. If the root cause is in a file you do not own (a dependency package), you MAY make the minimal fix there, but write exactly what and why in docs/notes/' + wp.id + '.md. If the specification itself is wrong, implement the closest correct behaviour and record the deviation.\n')
  return `You are a developer on the new Sutra app. Work package ${wp.id}: ${wp.title}. Section file: docs/design/${wp.section}.md.

${RULES}

READ FIRST, in this order: (1) ${APP}/docs/DECISIONS.md (owner rules and decisions); (2) ${APP}/docs/DESIGN.md if it exists (only if it exists); (3) the settlements under ${APP}/docs/design/settlements/ are ALREADY applied to the section files (a patched paragraph carries a tag like [S1-contracts-03]); do not read the large settlement json files, grep one only for the tag a paragraph names when you need its detail; (4) your section file: grep -n '${wp.id}' and every file you own, then read those module specifications completely (signatures, fields, validators, error types and messages, tests); for every interface you consume, read the owning section's specification of it and the code that is already merged in sutra_app/; (5) when your package touches function nodes, atoms, verify checks or their events, tables or screens: docs/design/function-nodes.md (the authoritative design of the five function nodes; it supersedes any older text) and, for the concepts behind it, docs/design/function-nodes-spec.json.${spec}
WORK PACKAGE (machine copy)
- owns (the ONLY paths you may create or edit): ${JSON.stringify(wp.owns)}
- depends_on (already merged into main when you start): ${JSON.stringify(wp.depends_on || [])}
- acceptance commands: ${JSON.stringify(wp.acceptance || [])}

PROTOCOL
1. wt=$(scripts/wt.sh new ${wp.id})   # run from ${APP}; creates branch wp/${wp.id} in its own worktree and prints the path (an existing worktree is printed as it is: it then holds an earlier interrupted attempt, so read its git log, git status and docs/notes/${wp.id}.md first and continue from there instead of starting over). Work ONLY inside that path.
2. Implement exactly your owned paths, test-first where practical. Run tests with $wt/scripts/py -m pytest <paths>. Everything must be deterministic, offline and fast: use fixtures, the fake CLIs and the stub connector; never call the real claude or codex (only tests marked live, which the gate skips). Pydantic models are closed (extra='forbid') as the library section says. Real implementations only: no stubs or TODOs for specified behaviour.
3. If you need something from a file you do not own, or from a package that is not merged yet: do not create or edit that file. Write a minimal adapter or test double inside your own files, and list the need under 'needs' in your report.
4. MUTATION SELF-CHECK, ONE PASS. When your tests pass, copy your package to a scratch folder under /tmp and break it 6 to 12 different ways (flip a comparison, drop a validation, change a constant, swap two arguments, delete an error branch, return early, widen a type). Every breakage must make some test fail; add the missing test for each survivor, once. Do NOT loop: no second round, no mass-generated mutants. A survivor that needs an exotic test goes into docs/notes instead. Report the count.
   TEST BUDGET. One focused test per specified behaviour, error and edge; no combinatorial or mass-generated cases; typically 40 to 150 tests per package and under 30 seconds in total. Do not hand-verify in a real browser or against the real CLIs unless the specification of your package demands it. Aim to finish within about 40 tool calls after your first green run; more is waste.
5. Run every acceptance command, then $wt/scripts/gate.sh (the whole suite must pass in your worktree). Never weaken, delete or skip a test to get green.
6. Commit in your worktree in small steps (git -C $wt add <your paths>; git -C $wt commit). End every commit message with the line: Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
7. From ${APP}: scripts/wt.sh merge ${wp.id}. Exit 0 = merged. Exit 2 = conflict while rebasing: resolve it inside the worktree (git rebase main, fix, git add, git rebase --continue), re-run the gate, merge again. Exit 3 = the gate failed on the merge candidate and main was left untouched: fix the cause in the worktree (the failing test output is printed) and merge again. Exit 4 = lock timeout: try again. Exit 5 = the gate passed but main could not fast-forward (main moved, or someone's uncommitted edit touches a file of your merge): run merge again; if it repeats three times, report blocked with the printed message. Repeat until merged (at most 5 tries) or report blocked with the reason.
8. After a successful merge run scripts/wt.sh drop ${wp.id}.

DEFINITION OF DONE
1. Every owned path exists and matches the specification.
2. Every module has tests for every behaviour, error and edge the specification lists; the package's tests run in under 30 seconds (mark longer ones slow).
3. The acceptance commands and scripts/gate.sh pass; the merge into main succeeded.
4. docs/notes/${wp.id}.md (you own it) holds the as-built notes in at most 45 lines: what was built, each deviation from the specification and why, each decision you took, known limits, follow-ups for other packages.
${retry}
FINAL REPLY: the structured report (merged true only if scripts/wt.sh merge exited 0).`
}

const LENSES = {
  spec: `LENS: SPEC CONFORMANCE. Compare the merged code with the specification: the section file (grep for the package id and each owned file), the settlements under docs/design/settlements/ (they override the section), docs/DECISIONS.md and the developer's own account docs/notes/<id>.md (judge every deviation it lists: acceptable, harmful or wrong). For every public name, signature, field, default, validator, error type and message, constant, file path, route, event and test the specification lists: is it present and equal? Report each missing or different item. Check that the merge touched only owned paths (git log --name-only on the merge and its parents). Check that what this package exposes matches what the dependants' specifications expect (grep the other sections for the names).`,
  break: `LENS: ADVERSARIAL CORRECTNESS. Try to break the code. Read each module looking for: unhandled edges (empty, None, huge, unicode, negative, duplicate, wrong type), wrong exception types, state mutation, ordering and concurrency bugs (threads, processes, files, SQLite), resource leaks, path traversal and injection (subprocess arguments, SQL, HTML, JSON), secrets in logs or errors, missing timeouts, non-atomic file writes, dependence on time, locale, randomness or the machine. For EVERY suspected defect write a tiny failing test or script in your scratch worktree and run it. Report a defect as proven only if you reproduced it and give the exact command; list unreproduced suspicions separately.`,
  tests: `LENS: TEST ADEQUACY. Judge the tests of this package. (1) Run them three times, once with the order reversed if you can; they must be deterministic, offline, and fast. (2) MUTATION CHECK: in a scratch copy apply at least 15 deliberate mutations across the package's modules (flip comparisons, drop validations, change constants, swap arguments, remove an error branch, return early, widen types, drop a field from a model, change a default). Report every mutation the tests did NOT catch together with the test that should exist (kind 'test', proven true, repro = the mutation). (3) Find specified behaviours that have no test. (4) Find flaky, slow, network or time dependent tests and tests that assert implementation details instead of behaviour. Do not report style.`,
}

function reviewPrompt(wp, key) {
  return `You review work package ${wp.id} (${wp.title}; section ${wp.section}), which is MERGED into main of ${APP}. ${RULES}

You must not modify the main checkout and must not commit, merge or push. Make your own scratch checkout for running things: git -C ${APP} worktree add --detach ${WT}/rv-${wp.id}-${key} main , work and run scripts/py ONLY inside it, and remove it at the end (git -C ${APP} worktree remove --force ${WT}/rv-${wp.id}-${key}). FIRST verify the merge: git -C ${APP} log --oneline --grep='^Merge wp/${wp.id}$' must show it; if not, reply with not_merged true and no findings. Owned paths of this package: ${JSON.stringify(wp.owns)}. Read the section file docs/design/${wp.section}.md for the package, docs/design/settlements/, docs/DECISIONS.md and docs/notes/${wp.id}.md first.

${LENSES[key]}

REPORT findings in the structured reply: severity blocker (breaks a stated requirement or loses data), high (wrong behaviour users or other packages will hit), medium (wrong in edge cases or a missing specified test), low (small gap); kind spec / bug / test / design; the file and line; a title; the evidence; a repro command or code (empty if none); proven true only when you ran the repro and saw the failure; a fix hint. A finding about a file this package does not own goes in 'cross' (one line) instead. No style remarks, no praise.`
}

function verifyPrompt(wp, f) {
  return `A reviewer reports this finding against work package ${wp.id} merged in ${APP}: ${JSON.stringify(f)}
Your job is to REFUTE it. Make a scratch checkout (git -C ${APP} worktree add --detach ${WT}/vf-${wp.id}-${(f.title || 'x').replace(/[^a-z0-9]+/gi, '').slice(0, 12)} main), read the code and the specification, and try to reproduce the claim with a real run. Default to confirmed=false if you cannot reproduce it or if the behaviour is what the specification asks for. Remove the scratch checkout when done (git worktree remove --force). Do not modify main, do not commit.`
}

function fixPrompt(wp, confirmed, round) {
  return `You are the fixer for work package ${wp.id} (${wp.title}), round ${round}. ${RULES}

Confirmed review findings to fix (each was reproduced or verified): ${JSON.stringify(confirmed)}

PROTOCOL: wt=$(scripts/wt.sh new ${wp.id}-r${round}) from ${APP}; fix ONLY files this package owns (${JSON.stringify(wp.owns)}), adding a regression test for every finding (a mutation finding means: add the test that kills it); never weaken a test. Run the package's tests and $wt/scripts/gate.sh; commit with the trailer line 'Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>'; append a 'Review round ${round}' section to docs/notes/${wp.id}.md; then scripts/wt.sh merge ${wp.id}-r${round} (same exit codes as before: 2 conflict, 3 gate failed (main untouched), 4 lock timeout, 5 main could not fast-forward: run again; retry up to 5 times) and scripts/wt.sh drop ${wp.id}-r${round}. A finding that needs a change in a file you do not own: skip it and say so. If a finding is wrong after all, skip it and say why.`
}

async function runDev(wp) {
  if (HALT) return { id: wp.id, merged: false, skipped: true, halted: true, summary: 'not started: the circuit breaker is open' }
  let r = noteResult(await devSem.run(() => agent(devPrompt(wp, 0), { label: 'dev:' + wp.id, phase: 'Build', agentType: 'general-purpose', effort: EFFORT, schema: DEV }), height(wp.id)))
  let attempt = 1
  while ((!r || !r.merged) && attempt < 4 && !HALT) {
    log(wp.id + ' not merged after attempt ' + attempt + (r && r.blocked_reason ? ' (' + r.blocked_reason + ')' : '') + '; ' + (attempt < 3 ? 'retrying' : 'rescue attempt'))
    r = noteResult(await devSem.run(() => agent(devPrompt(wp, attempt, r), { label: (attempt < 3 ? 'fix:' : 'rescue:') + wp.id + '#' + attempt, phase: 'Build', agentType: 'general-purpose', effort: EFFORT, schema: DEV }), height(wp.id) + 2))
    attempt++
  }
  log(wp.id + (r && r.merged ? ' MERGED ' + (r.commit || '') : ' FAILED'))
  return Object.assign({ id: wp.id }, r || { merged: false, summary: 'agent returned nothing' })
}

async function reviewAndFix(wp) {
  if (PRE[wp.id]) {
    const confirmed = PRE[wp.id]
    log(wp.id + ': fixing ' + confirmed.length + ' findings confirmed by an earlier review')
    const fix = await sem.run(() => agent(fixPrompt(wp, confirmed, 1), { label: 'fix:' + wp.id + ':r1', phase: 'Fix', agentType: 'general-purpose', effort: EFFORT, schema: FIX }))
    log(wp.id + ' fix round 1: ' + (fix && fix.merged ? 'merged' : 'NOT merged'))
    return { id: wp.id, findings: confirmed.length, confirmed: confirmed.length, fixed: fix ? fix.fixed : [], skipped: fix ? fix.skipped : [], fix_merged: !!(fix && fix.merged), cross: [], suspicions: [] }
  }
  if (HALT) return { id: wp.id, halted: true }
  const reviews = await parallel(LENS_KEYS.map(key => () => sem.run(() =>
    agent(reviewPrompt(wp, key), { label: 'review:' + wp.id + ':' + key, phase: 'Review', agentType: 'general-purpose', effort: EFFORT, schema: REVIEW }))))
  const ok = reviews.filter(Boolean)
  if (ok.some(r => r.not_merged)) return { id: wp.id, not_merged: true }
  const seen = new Set()
  const findings = ok.flatMap(r => (r.findings || []).map(f => Object.assign({ lens: r.lens }, f)))
    .filter(f => { const k = f.file + '|' + (f.title || '').toLowerCase().slice(0, 60); if (seen.has(k)) return false; seen.add(k); return true })
  const cross = ok.flatMap(r => r.cross || [])
  const suspicions = ok.flatMap(r => r.suspicions || [])
  const toVerify = findings.filter(f => !f.proven && f.severity !== 'low')
  const verdicts = await parallel(toVerify.map(f => () => sem.run(() =>
    agent(verifyPrompt(wp, f), { label: 'verify:' + wp.id, phase: 'Verify', agentType: 'general-purpose', effort: EFFORT, schema: VERDICT }))))
  const confirmed = findings.filter(f => f.proven).concat(toVerify.filter((f, i) => verdicts[i] && verdicts[i].confirmed))
  log(wp.id + ' review: ' + findings.length + ' findings, ' + confirmed.length + ' confirmed, ' + cross.length + ' cross-package')
  if (!confirmed.length) return { id: wp.id, findings: findings.length, confirmed: 0, cross, suspicions }
  const fix = await sem.run(() => agent(fixPrompt(wp, confirmed, 1), { label: 'fix:' + wp.id + ':r1', phase: 'Fix', agentType: 'general-purpose', effort: EFFORT, schema: FIX }))
  log(wp.id + ' fix round 1: ' + (fix && fix.merged ? 'merged' : 'NOT merged'))
  return { id: wp.id, findings: findings.length, confirmed: confirmed.length, fixed: fix ? fix.fixed : [], skipped: fix ? fix.skipped : [], fix_merged: !!(fix && fix.merged), cross, suspicions }
}

// topological order so every package's promise exists before a dependant reads it
const byId = {}
WPS.forEach(w => { byId[w.id] = w })
const order = []
const seenIds = new Set()
function visit(w) {
  if (seenIds.has(w.id)) return
  seenIds.add(w.id)
  ;(w.depends_on || []).forEach(d => { if (byId[d]) visit(byId[d]) })
  order.push(w)
}
// critical path first: a package with a long chain of dependants gets a developer slot before a leaf (the slot queue is first come, first served)
const dependants = {}
WPS.forEach(w => (w.depends_on || []).forEach(d => { (dependants[d] = dependants[d] || []).push(w.id) }))
const heightMemo = {}
const height = id => heightMemo[id] !== undefined ? heightMemo[id] : (heightMemo[id] = 1 + Math.max(0, ...(dependants[id] || []).map(height)))
;[...WPS].sort((a, b) => height(b.id) - height(a.id)).forEach(visit)
log('build order: ' + order.map(w => w.id).join(' '))

phase('Build')
const devDone = {}
const reviewDone = {}
const ready = {}
for (const wp of order) {
  if (ALREADY.has(wp.id)) {
    devDone[wp.id] = Promise.resolve({ id: wp.id, merged: true, summary: 'already merged' })
  } else {
    devDone[wp.id] = (async () => {
      const ups = await Promise.all((wp.depends_on || []).filter(d => ready[d]).map(d => ready[d]))
      const blocked = ups.filter(r => !r || !r.merged).map(r => (r && r.id) || '?')
      if (blocked.length) {
        log('SKIP ' + wp.id + ': dependency not merged: ' + blocked.join(', '))
        return { id: wp.id, merged: false, skipped: true, summary: 'skipped, dependency not merged: ' + blocked.join(', ') }
      }
      return runDev(wp)
    })()
  }
  reviewDone[wp.id] = devDone[wp.id].then(async r => {
    if (!r || !r.merged || SKIP_REVIEW || REVIEWED.has(wp.id) || (ALREADY.has(wp.id) && !PRE[wp.id]) || (REVIEW_ONLY && !REVIEW_ONLY.has(wp.id) && !PRE[wp.id])) return r
    const review = await reviewAndFix(wp)
    return Object.assign({}, r, { review })
  })
  ready[wp.id] = GATED.has(wp.id) ? reviewDone[wp.id] : devDone[wp.id]
}
const results = await Promise.all(order.map(w => reviewDone[w.id]))
const merged = results.filter(r => r && r.merged).map(r => r.id)
const failed = results.filter(r => !r || !r.merged).map(r => (r && r.id) || '?')
const reviewed = results.filter(r => r && r.review)
const cross = reviewed.flatMap(r => (r.review.cross || []).map(c => r.id + ': ' + c))
const unfixed = reviewed.filter(r => r.review.confirmed && !r.review.fix_merged).map(r => r.id)
log('merged: ' + merged.length + ' | not merged: ' + (failed.join(' ') || 'none') + ' | confirmed findings unfixed: ' + (unfixed.join(' ') || 'none') + ' | cross-package notes: ' + cross.length)
return { merged, failed, unfixed, cross, results }
