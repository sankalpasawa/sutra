# Sutra Outcome Test Suite — Design

*Date: 2026-04-19*
*Status: DESIGN — awaiting Codex review + founder approval before execution*
*Trigger: founder 2026-04-19 — "Test scripts from an output point of view, from a features point of view, outside in."*

---

## Why this exists

Today Sutra has 14+ test scripts, all implementation-level:
- `test-d28-routing-gate.sh` — does the routing check block correctly?
- `test-d13-cascade.sh` — does cascade hook warn?
- `test-depth-marker-parse.sh` — does dispatcher parse markers?

These pass every time and tell us nothing about **user experience**. A user who installs Sutra doesn't care whether `dispatcher-pretool.sh` line 347 works — they care: "When I type `/sutra`, does it activate? When I try to edit without a depth marker, does it stop me?"

**Outcome tests** = outside-in. Invoke the real user-facing surface (install command → Claude Code → slash commands → hook behavior → artifacts on disk). Assert on observable outputs. Black-box. User's perspective.

## Single source of truth for "Sutra core"

```
asawa-holding/ (private monorepo — source of truth)
├── holding/hooks/*.sh                ← live hook source (used by Asawa)
├── sutra/layer2-operating-system/    ← OS docs source
├── sutra/package/                    ← publish staging (subset, Asawa-stripped)
│   ├── bin/install.mjs
│   ├── hooks/                        ← copied from holding/hooks/ (curated)
│   ├── os-core/                      ← copied from layer2/
│   ├── commands/
│   ├── templates/
│   └── tests/                        ← implementation tests (exist today)
│                                       ADD: outcome/ (this design)

~/plod/sutra-os-staging/              ← intermediate push staging (mirrors sutra/package/)

github.com/sankalpasawa/sutra-os      ← public deploy target (npx consumes this)
github.com/sankalpasawa/sutra-plugin  ← thin Claude Code plugin (discovery only)
```

Test surface: run against `npx -y github:sankalpasawa/sutra-os init` in fresh dirs — exactly what an external user experiences.

---

## Test categories (10)

| # | Category | What it proves |
|:-:|---|---|
| 1 | **Install** | Installer deploys the right files to the right places, writes version pin |
| 2 | **Activation** | `/sutra` activates Sutra mode, CEO day renders when OS is present |
| 3 | **Enforcement** | Hooks block Edit/Write without markers; allow with markers; fire in correct order |
| 4 | **Commands** | `/sutra`, `/sutra-help`, `/sutra-update`, `/sutra-onboard`, `/company` each do what their description says |
| 5 | **Update flow** | update-check.sh detects newer version; `/sutra-update` re-installs cleanly; version pin bumps |
| 6 | **Logging** | Hook fires land in `.claude/logs/hook-fires.jsonl`; enforcement events land in `.enforcement/*.log` |
| 7 | **Subagent propagation** | Task-spawned children fire the same hooks (inheritance via folder-level `.claude/hooks/sutra/`) |
| 8 | **Uninstall** | `--uninstall` removes Sutra artifacts; leaves user files + gstack + GSD intact |
| 9 | **Portability** | Everything works in a fresh `/tmp/` dir without any asawa-holding context present |
| 10 | **Leak audit** | No `asawa`, `dayflow`, `maze`, `ppr`, `billu`, `paisa` strings in user-visible surface (`.claude/commands/`, `CLAUDE.md`, installer output, banners) |

---

## File structure

```
sutra/package/tests/outcome/
├── 01-install.sh              # Category 1
├── 02-activation.sh           # Category 2
├── 03-enforcement.sh          # Category 3
├── 04-commands.sh             # Category 4
├── 05-update.sh               # Category 5
├── 06-logging.sh              # Category 6
├── 07-subagent.sh             # Category 7
├── 08-uninstall.sh            # Category 8
├── 09-portability.sh          # Category 9
├── 10-leak-audit.sh           # Category 10
├── lib/
│   └── assert.sh              # shared: assert_eq, assert_file, assert_exit, etc.
└── run-all.sh                 # aggregates all 10, returns total pass/fail + exit code
```

Each outcome script is **self-contained**: it creates its own `/tmp/sutra-outcome-N-<uuid>/`, runs what it needs, asserts, cleans up on success (not on failure so you can inspect).

---

## Sample test — `01-install.sh`

```bash
#!/bin/bash
# Outcome test: fresh install deploys correct artifacts.
set -u
source "$(dirname "$0")/lib/assert.sh"

TEST_NAME="01-install"
TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"

# Action: run the external install path
npx -y github:sankalpasawa/sutra-os init >/dev/null 2>&1
INSTALL_EXIT=$?

# Assertions
assert_eq "$INSTALL_EXIT" 0 "install exits 0"
assert_file "CLAUDE.md"                        "CLAUDE.md exists"
assert_file "TODO.md"                          "TODO.md exists"
assert_file "SUTRA-CONFIG.md"                  "SUTRA-CONFIG.md exists"
assert_file "os/STATUS.md"                     "os/STATUS.md exists"
assert_file "os/METRICS.md"                    "os/METRICS.md exists"
assert_file "os/OKRs.md"                       "os/OKRs.md exists"
assert_file ".claude/settings.json"            "settings.json exists"
assert_file ".claude/sutra-version"            "version pin exists"
assert_dir  ".claude/hooks/sutra"              "hooks dir exists"
assert_dir  ".claude/os"                       "os-core dir exists"

assert_count "ls .claude/hooks/sutra/*.sh | wc -l" 29 30 "hook count in expected range"
assert_count "ls .claude/os/*.md | wc -l" 18 25 "os docs count in expected range"

VERSION=$(head -1 .claude/sutra-version | tr -d '[:space:]')
assert_semver "$VERSION" "version pin is valid semver"

# Cleanup on success
[ "$FAILURES" -eq 0 ] && rm -rf "$TEST_DIR"

exit_with_summary
```

## Sample test — `03-enforcement.sh`

```bash
#!/bin/bash
# Outcome test: hooks block Edit/Write without markers; allow with.
set -u
source "$(dirname "$0")/lib/assert.sh"

TEST_NAME="03-enforcement"
TEST_DIR="/tmp/sutra-outcome-${TEST_NAME}-$$"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"
npx -y github:sankalpasawa/sutra-os init >/dev/null 2>&1

# Case 1: no markers → should BLOCK (exit 1)
CLAUDE_PROJECT_DIR=$(pwd) TOOL_NAME=Write TOOL_INPUT_file_path=$(pwd)/foo.md \
  bash .claude/hooks/sutra/dispatcher-pretool.sh >/dev/null 2>&1
assert_eq "$?" 1 "Write without markers exits 1 (blocked)"

# Case 2: write markers → should PASS (exit 0)
echo "$(date +%s)" > .claude/input-routed
echo "DEPTH=3 TASK=test TS=$(date +%s)" > .claude/depth-registered
echo "$(date +%s)" > .claude/sutra-deploy-depth5
CLAUDE_PROJECT_DIR=$(pwd) TOOL_NAME=Write TOOL_INPUT_file_path=$(pwd)/foo.md \
  bash .claude/hooks/sutra/dispatcher-pretool.sh >/dev/null 2>&1
assert_eq "$?" 0 "Write with markers exits 0 (allowed)"

# Case 3: hook fires logged
assert_file ".claude/logs/hook-fires.jsonl" "hook log populated"
assert_count "wc -l < .claude/logs/hook-fires.jsonl" 1 100 "hook log has entries"

[ "$FAILURES" -eq 0 ] && rm -rf "$TEST_DIR"
exit_with_summary
```

Each test is ~30-60 lines. Total suite is ~500 lines. Single-file `run-all.sh` runs them, returns aggregate pass/fail.

---

## Assertion library (`lib/assert.sh`)

Shared helpers:

```bash
FAILURES=0
PASSES=0

assert_eq()     { [ "$1" = "$2" ] && _pass "$3" || _fail "$3 (got '$1' wanted '$2')"; }
assert_file()   { [ -f "$1" ]       && _pass "$2" || _fail "$2 (missing: $1)"; }
assert_dir()    { [ -d "$1" ]       && _pass "$2" || _fail "$2 (missing: $1)"; }
assert_exit()   { eval "$1" >/dev/null 2>&1; [ "$?" -eq "$2" ] && _pass "$3" || _fail "$3 (exit=$?)"; }
assert_count()  { local n=$(eval "$1"); [ "$n" -ge "$2" ] && [ "$n" -le "$3" ] && _pass "$4" || _fail "$4 (count=$n, range=[$2,$3])"; }
assert_semver() { printf '%s' "$1" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' && _pass "$2" || _fail "$2 (not semver: $1)"; }
assert_nostring() { grep -qi "$1" "$2" 2>/dev/null && _fail "$3 ($1 found in $2)" || _pass "$3"; }
_pass()         { PASSES=$((PASSES+1)); echo "  ✓ $1"; }
_fail()         { FAILURES=$((FAILURES+1)); echo "  ✗ $1" >&2; }
exit_with_summary() {
  echo ""
  echo "Result: $PASSES passed, $FAILURES failed"
  [ "$FAILURES" -eq 0 ]
}
```

---

## `run-all.sh`

```bash
#!/bin/bash
cd "$(dirname "$0")"
TOTAL=0
FAILED=0
for test in 0[0-9]-*.sh; do
  echo "== $test =="
  bash "$test"
  if [ "$?" -ne 0 ]; then FAILED=$((FAILED+1)); fi
  TOTAL=$((TOTAL+1))
done
echo ""
echo "══════════════════════════════════════════════════"
echo "SUITE: $((TOTAL-FAILED))/$TOTAL test files passed"
echo "══════════════════════════════════════════════════"
exit "$FAILED"
```

---

## Execution plan — sequenced

| Phase | Scope | Sessions |
|---|---|---|
| A | Write `lib/assert.sh` + first 3 scripts (01-install, 03-enforcement, 10-leak-audit) + run-all.sh. Prove the pattern. | 1 (this session) |
| B | Fill in remaining 7 scripts (02, 04, 05, 06, 07, 08, 09). | 1-2 sessions |
| C | Wire into CI — run on every push to `sankalpasawa/sutra-os` via GitHub Actions. | 1 session |
| D | Add coverage KR to `sutra/marketplace/OKRs.md` (O3 already has enforcement KR; add coverage) | embedded in B |

## Review criteria

A PR to sutra-os is blocked from merging if run-all.sh fails. Goal: every change in sutra-os proves itself against user-visible outcomes, not just unit behavior.

## Scope check — what this covers + what it doesn't

**Covers:**
- Install/update/uninstall at the external-user level
- All slash commands reach their documented outcomes
- Hook enforcement behaves correctly end-to-end
- Brand-leak guarantees maintained

**Doesn't cover (out of v1):**
- Claude Code's actual LLM response quality (can't unit-test an LLM)
- Network failure modes (GitHub down, npm slow)
- Cross-platform (tests bash-only; Windows users out of scope)
- Performance regressions (add if hook-fire ms starts trending up)

---

## Dependencies on the "more programmatic" architecture question

If we adopt YAML-rule-engine (v2 change), several tests shift:
- Category 3 (enforcement) becomes easier to write — declarative rules are easier to assert on
- Unit tests of individual rules become trivial
- Outcome tests stay the same (they're black-box — don't care about internal structure)

So outcome suite is **format-agnostic**. We can build it now under current architecture and reuse every test after any v2 refactor.

## Open questions

1. **Run cadence** — run-all on every commit, or nightly? Every commit is safer but slower (7 installs × 30s = 3.5 min per run).
2. **Fixture caching** — can we cache the `npx install` step between tests? (Would cut runtime to ~1 min.)
3. **Subagent test (Category 7)** — can we verify inheritance without actually spawning a Task subagent? Today we'd need a live Claude Code session. Maybe just assert `.claude/hooks/sutra/` is readable and settings.json wiring is correct — proxy for "subagent would inherit."
4. **Flakiness policy** — network-dependent tests (update-check pulls from GitHub) can flake on offline. Mark as informational, not blocking?

These resolve in execution Phase A.
