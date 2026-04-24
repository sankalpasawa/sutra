# Sutra Outcome Test Suite — Implementation Plan

*Design: `sutra/marketplace/design/2026-04-19-outcome-test-suite.md`*
*Claude + Codex converged 2026-04-19 on direction + 3 guardrails.*
*Depth: 5 for everything (founder direction).*

---

## Three guardrails (Codex)

1. **YAML rules must be narrow-schema + opinionated engine** — don't let rules become "bash with indentation."
2. **JSON state = versioned contract** — partial-writes safe, ownership declared, upgrade paths handled.
3. **Engine decisions observable** — every rule fire logs *why* it fired (or why not).

These apply to the v2 architectural work (YAML rule engine, JSON markers). They do NOT gate outcome-test suite — outcome tests are format-agnostic (black-box).

## Phases

### Phase A — outcome test suite skeleton (this session)

| Task | Files | Done when |
|---|---|---|
| A.1 | `sutra/package/tests/outcome/lib/assert.sh` (shared assertions) | `assert_eq`, `assert_file`, `assert_dir`, `assert_count`, `assert_semver`, `assert_nostring`, `_pass`, `_fail`, `exit_with_summary` work |
| A.2 | `sutra/package/tests/outcome/run-all.sh` (runner) | iterates `0[0-9]-*.sh`, aggregates pass/fail, exits correctly |
| A.3 | `sutra/package/tests/outcome/01-install.sh` | fresh npx install produces expected files, hook count, version pin |
| A.4 | `sutra/package/tests/outcome/03-enforcement.sh` | hooks block without markers (exit 1), pass with (exit 0), log correctly |
| A.5 | `sutra/package/tests/outcome/10-leak-audit.sh` | user-visible surface has zero `asawa`/`dayflow`/etc. strings |
| A.6 | `sutra/package/tests/outcome/README.md` | how to run, what each test covers, how to add new |
| A.7 | Sync to `~/plod/sutra-os-staging/` + push to `sankalpasawa/sutra-os` | commit pushed |

After Phase A: `bash tests/outcome/run-all.sh` runs on any laptop, produces pass/fail report, proves the pattern.

### Phase B — fill in remaining 7 scripts (next session, 1-2 hours)

| Task | File | Coverage |
|---|---|---|
| B.1 | `02-activation.sh` | `/sutra` command triggers CEO day render with installed OS; offers install when absent |
| B.2 | `04-commands.sh` | `/sutra-help`, `/sutra-update`, `/sutra-onboard`, `/company` each work |
| B.3 | `05-update.sh` | update-check detects newer version; `/sutra-update` re-installs; pin bumps |
| B.4 | `06-logging.sh` | hook-fires.jsonl populated; .enforcement/ logs populated; format valid JSONL |
| B.5 | `07-subagent.sh` | proxy-test: `.claude/hooks/sutra/` readable + settings.json wires hooks → subagent WOULD inherit (live Task tool test = manual) |
| B.6 | `08-uninstall.sh` | `--uninstall` removes Sutra, preserves user content + gstack + GSD |
| B.7 | `09-portability.sh` | all 9 other scripts pass in a fresh `/tmp/` with zero asawa-holding context |

### Phase C — CI (wire GitHub Actions on sankalpasawa/sutra-os repo)

| Task | Done when |
|---|---|
| C.1 | `.github/workflows/outcome-tests.yml` runs `run-all.sh` on push/PR | GitHub Actions green on main |
| C.2 | PR status check requires green before merge | branch protection enabled |

### Phase D — v2 architectural refactor (separate multi-session sprint)

Triggered by Codex review. Out of scope for outcome tests, but flagged for traceability:

| Task | Scope |
|---|---|
| D.1 | JSON marker contract (v0.3) — `.claude/depth-registered` becomes JSON with `schema_version` field |
| D.2 | Enforcement rules → YAML + single engine (v2.0) — `dispatcher-pretool.sh` becomes a dispatcher that loads rules from `rules/*.yaml` |
| D.3 | Observability: every rule fire logs reason to `.enforcement/decisions.jsonl` (JSONL + versioned schema) |
| D.4 | Statusline wiring (v0.3) — bottom-of-Claude-Code visual flag for "UPDATE AVAILABLE" |

---

## Execution order (this session, Phase A)

1. Refresh markers (Depth 5).
2. Write `lib/assert.sh` (shared helpers).
3. Write `01-install.sh`, `03-enforcement.sh`, `10-leak-audit.sh` (3 sample tests).
4. Write `run-all.sh` + `README.md`.
5. Test locally: `bash sutra/package/tests/outcome/run-all.sh` — expect 3/3 pass.
6. Sync to `~/plod/sutra-os-staging/tests/outcome/`.
7. Commit + push to sankalpasawa/sutra-os.
8. Verify external-user test: `mkdir /tmp/outcome-verify && cd /tmp/outcome-verify && bash <(npx --call 'cat tests/outcome/run-all.sh' github:sankalpasawa/sutra-os 2>/dev/null)` — future-nice-to-have.

---

## Observability requirement (per Codex)

Every test emits structured lines:

```
{"test":"01-install","assertion":"CLAUDE.md exists","status":"PASS","ts":1776543000}
{"test":"01-install","assertion":"hook count in expected range","status":"PASS","ts":1776543000}
```

Extend `_pass` and `_fail` in assert.sh to optionally write to `/tmp/sutra-outcome-run.jsonl`. Not in v1 assertion library — add when we wire CI.

---

## What this plan does NOT do

- Doesn't refactor hooks to YAML (Phase D, separate work)
- Doesn't migrate markers to JSON (Phase D)
- Doesn't wire statusline (Phase D)
- Doesn't test LLM behavior quality (untestable in bash)
- Doesn't test Windows (bash-only)

---

## Success metric

After Phase A ships: someone cloning `sankalpasawa/sutra-os` can run `bash tests/outcome/run-all.sh` and see `3/3 test files passed` in under 2 minutes. That proves the pattern.

After Phase B + C: every commit to sutra-os is gated by 10/10 outcome tests green.

After Phase D: v2 architecture lands without breaking any outcome test — because they're black-box.
