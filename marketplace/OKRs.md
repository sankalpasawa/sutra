# Sutra Marketplace — OKRs

*Purpose: track whether Sutra's plugin + npm external deployment is actually working for real users. Not just shipped — working.*

*Owners: Sankalp (founder). Cadence: weekly review until 2026-07-01, then bi-weekly.*
*Created: 2026-04-19. First review: 2026-04-26.*

---

## North Star

**An external user who has never seen Sutra can install it in one command, deploy the full OS into their project folder, and within 5 minutes be doing governed work that produces artifacts on disk.** If this works for 100 users without intervention, we've shipped.

---

## O1 — Install pipeline is reliable end-to-end

Measurable: the deploy mechanism (plugin + npm) works for strangers on the first try.

| KR | Target | Measurement | Source |
|---|---|---|---|
| 1.1 | 100 successful installs via `npx github:sankalpasawa/sutra-os` by 2026-07-01 | opt-in install telemetry (add to install.mjs in v0.3) | future `.enforcement/install-events.jsonl` |
| 1.2 | <5% install-failure rate | same telemetry, failures tagged by error type | same |
| 1.3 | 10 fresh-dir founder dogfood installs by 2026-05-01 | founder runs the test command in 10 different `/tmp/` or `~/sutra-test-*` dirs | manual log in §Dogfood Log |
| 1.4 | Install completes in <60 seconds on a typical laptop | timer in install.mjs | install output + telemetry |
| 1.5 | Zero D29 leaks visible to external users on first run | extend `leak-audit.sh` to scan installed `.claude/hooks/sutra/` + `os/` + `CLAUDE.md` | audit run post-install |

## O2 — Users actually use Sutra after installing

Measurable: governance isn't theater. Users do real work through it.

| KR | Target | Measurement | Source |
|---|---|---|---|
| 2.1 | 20 users with 2+ sessions (retention) | telemetry: sessions-per-user-folder via sutra-version mtime | install telemetry + session-logger hook |
| 2.2 | 50% of installers produce ≥1 artifact in `os/` or `docs/` within 7 days of install | file-count delta in project dir | optional file-observer script |
| 2.3 | Time-to-first-governed-task <5 minutes median | timer from install to first depth-block emission | `.claude/onboarding-start-time` + first hook-log entry |
| 2.4 | ≥3 non-founder users confirmed completing a full task cycle under Sutra | direct feedback or screen recording | founder interviews |

## O3 — Governance actually governs (enforcement works)

Measurable: hooks block what they should, let through what they shouldn't, log everything.

| KR | Target | Measurement | Source |
|---|---|---|---|
| 3.1 | Dispatcher-pretool correctly blocks ≥95% of Edit/Write attempts missing required markers | count blocked-vs-passed in hook-log.jsonl | `.enforcement/routing-misses.log` once path bug is fixed |
| 3.2 | Subagent inheritance confirmed working across 3+ different Task invocations | run Task tool from parent session, verify child fires hooks | dogfood test in v0.2 validation |
| 3.3 | Zero critical bugs in dispatcher-pretool in first 30 days post-launch | GitHub issues with `severity:critical` label | sankalpasawa/sutra-os issues |
| 3.4 | Fix the `holding/hooks/hook-log.jsonl` hardcoded path bug (portability) | 1-line change in dispatcher-pretool | v0.2.1 patch |

## O4 — Sutra evolves based on real user feedback

Measurable: the feedback loop is running, not just documented.

| KR | Target | Measurement | Source |
|---|---|---|---|
| 4.1 | 5 feedback items captured from external users by 2026-06-01 | GitHub issues + DMs + direct notes | issues + `sutra/marketplace/feedback.jsonl` |
| 4.2 | 3 improvements shipped in response to feedback | commits referencing specific feedback items | git log grep |
| 4.3 | CEO day dashboard populates real data from installed os/* files (not template stubs) | `/sutra` output inspection | dogfood session |
| 4.4 | `/sutra` command is cited by at least 1 external user as "useful" | unsolicited positive feedback | issues + DMs |

---

## Measurement infrastructure (what exists vs what's needed)

| Instrument | Status | Fix needed |
|---|---|---|
| `dispatcher-pretool.sh` logs every hook fire | ✅ works, but path bug | Change `HOOK_LOG=$REPO_ROOT/holding/hooks/...` → `${CLAUDE_PROJECT_DIR:-$REPO_ROOT}/.claude/logs/hook-log.jsonl` |
| `.enforcement/routing-misses.log` | ✅ logs enforcement events | Same path fix as above |
| `.claude/sutra-version` (install pin) | ✅ installed | None |
| Install telemetry (opt-in) | ❌ not yet | Add to install.mjs in v0.3: anonymous event to a logging endpoint |
| `sutra-estimation.log` (task-level) | Referenced but not wired in dispatcher-stop | Confirm it lands on session end |
| GitHub Issues enabled on sutra-plugin + sutra-os | ✅ public repos default | None |
| Dogfood log (founder's fresh-dir tests) | ❌ manual, not yet kept | Append to §Dogfood Log below each run |

---

## Improvement loop

Run every week until 2026-07-01.

1. **Observe** — read the latest `.enforcement/routing-misses.log` (from the founder's asawa-holding, then from external dogfood dirs). Count blocks vs passes. Flag anomalies.
2. **Interview** — reach out to 1 external user who installed this week. Ask: "what confused you? what worked?" Log in feedback.jsonl.
3. **Hypothesize** — what's the single most impactful thing to fix in v0.(N+1)?
4. **Fix** — ship the patch (chunk at Depth 3-4, not bigger).
5. **Publish** — `git push` sutra-os + sutra-plugin, bump version in both.
6. **Measure again** — does the metric move?

If KR not moving for 3 weeks in a row, either (a) the KR is wrong, (b) the strategy is wrong, or (c) the implementation is wrong. Pick one, change it.

---

## Dogfood log

| Date | Dir | Outcome | Notes |
|---|---|---|---|
| 2026-04-19 | /tmp/sutra-e2e-test | ✅ install clean, 30 hooks, 22 OS docs | Hook log path bug surfaced (O3.4). Enforcement fires correctly (BLOCKED on missing markers). |
| 2026-04-19 | /tmp/sutra-xtest3 | ✅ npx github: shorthand works | Same bug as above, same outcome. |

Founder: add one row per fresh-dir install going forward. Outcome = one of: ✅ (clean) / 🟡 (worked with warnings) / ❌ (broke).

---

## Open questions affecting OKRs

1. **Telemetry privacy** — before install.mjs pings a server, need explicit user opt-in + anonymization. Design a minimal telemetry spec in v0.3.
2. **Friend-0 vs strangers** — KRs assume external users, but founder dogfood drives most early signal. Decide when to recruit Friend-0 cohort vs rely on founder sampling.
3. **Versioning cadence** — when do we bump minor (0.2 → 0.3) vs patch (0.2.0 → 0.2.1)? Draft a policy.
4. **Dashboard** — do we need a `sutra dashboard` command that summarizes these KRs from local data? Or is manual review enough for v0.2?

## Review checkpoints

- **2026-04-26** (first review): did the measurement infra get built? Did founder hit 3+ dogfood runs?
- **2026-05-01**: O1.3 target date for 10 dogfood installs.
- **2026-05-15**: midpoint check. Are external users installing?
- **2026-07-01**: O1.1 target date (100 installs). Score all KRs. Write retrospective.

---

*This file is the source of truth for "is Sutra deployment working?" Link to it from sutra/marketplace/README.md and from holding/TODO.md. Update weekly.*
