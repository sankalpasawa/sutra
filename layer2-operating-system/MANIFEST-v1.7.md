# Sutra OS v1.7 — Deployment Manifest

This is the COMPLETE expected state for a company running Sutra OS v1.7. Deployment is binary: either every item matches, or the company is NOT fully deployed.

Both first-time onboarding (CLIENT-ONBOARDING.md) and version updates (PROTO-013) converge to this manifest. The verification script (`verify-os-deploy.sh`) checks against it.

---

## 1. FILES (must exist)

| Path | Type | Source |
|------|------|--------|
| `CLAUDE.md` | file | company-specific + Sutra-managed sections |
| `os/` | dir | — |
| `os/engines/ADAPTIVE-PROTOCOL.md` | file | copy from `sutra/layer2-operating-system/d-engines/` |
| `os/engines/ESTIMATION-ENGINE.md` | file | copy from `sutra/layer2-operating-system/d-engines/` |
| `os/engines/estimation-log.jsonl` | file | company data (create empty, never overwrite) |
| `os/SUTRA-CONFIG.md` | file | generated from Sutra templates + company customization |
| `os/METRICS.md` | file | company data |
| `os/OKRs.md` | file | company data |
| `os/findings/` | dir | Finding Resolution Gate tracker (Depth 4-5) |
| `os/protocols/` | dir | LEARN phase protocol store |
| `os/feedback-to-sutra/` | dir | upstream feedback channel |
| `os/feedback-from-sutra/` | dir | downstream push channel |
| `.claude/hooks/enforce-boundaries.sh` | file | copy from Sutra onboarding template |
| `.claude/settings.json` | file | hook registration |

## 2. CONTENT (must match — not just exist)

### CLAUDE.md required patterns
```
MUST CONTAIN:
  "Sutra OS Version: v1.7"
  "Before Every Task"
  "DEPTH: X/5"
  "COST: ~$X (~Y% of $200 plan)"
  "EFFORT:"
  "IMPACT:"
  "TRIAGE:"
  "version check" or "CURRENT-VERSION"
  "Input Routing"

MUST NOT CONTAIN:
  "Level 1-4"              (old depth system)
  "Gear"                   (old terminology)
  "THINK→PRE→EXECUTE→POST→COMPRESS"  (old lifecycle)
  "v1.4" or "v1.5" or "v1.6" in version line
```

### os/SUTRA-CONFIG.md required patterns
```
MUST CONTAIN:
  "v1.7"
  "Depth 1" through "Depth 5"
  "OBJECTIVE" "OBSERVE" "SHAPE" "PLAN" "EXECUTE" "MEASURE" "LEARN"
  "Speed" and "Precision" (governing trade-off)
  "Finding Resolution Gate" (Depth 4-5 enforcement)

MUST NOT CONTAIN:
  "Level 1-4"
  "THINK→PRE→EXECUTE→POST→COMPRESS"
  "v1.4" or "v1.5" or "v1.6" in version line
```

### os/engines/ADAPTIVE-PROTOCOL.md required patterns
```
MUST CONTAIN:
  "Adaptive Protocol Engine v3"
  "Five Depths"
  "Depth 1: Direct"
  "Speed vs Precision"
  "Company State"

MUST NOT CONTAIN:
  "Gear"
  "Level 1" through "Level 4" as depth names
  "v2" in title
```

## 3. HOOKS (must be installed and enforced)

| Hook | File | Registration | Behavior |
|------|------|-------------|----------|
| Boundary enforcement | `.claude/hooks/enforce-boundaries.sh` | PreToolUse: Edit\|Write\|Bash | exit 2 on path outside repo |

### Hook verification test
```bash
# Must return exit 2:
TOOL_INPUT_file_path="../sutra/PROTOCOLS.md" bash .claude/hooks/enforce-boundaries.sh

# Must return exit 0:
TOOL_INPUT_file_path="./TODO.md" bash .claude/hooks/enforce-boundaries.sh
```

## 4. INFRASTRUCTURE (must be operational)

| System | Location | Purpose | Verification |
|--------|----------|---------|-------------|
| Estimation log | `os/engines/estimation-log.jsonl` | Records estimates, actuals, triage | File exists, writable |
| Finding tracker | `os/findings/` | Tracks Depth 4-5 audit findings | Directory exists |
| Protocol store | `os/protocols/` | LEARN phase reusable patterns | Directory exists |
| Feedback upstream | `os/feedback-to-sutra/` | Company → Sutra feedback | Directory exists |
| Feedback downstream | `os/feedback-from-sutra/` | Sutra → Company pushes | Directory exists |

## 5. BEHAVIORAL (verified after 5 sessions)

These can't be checked at deploy time. Check after 5 real sessions:

| Behavior | Proof Artifact | Target |
|----------|---------------|--------|
| Depth assessment before every task | `depth_selected` in estimation-log.jsonl | 100% of v1.7 tasks |
| Triage logging after every task | `triage_class` in estimation-log.jsonl | 100% of v1.7 tasks |
| Estimation with actuals | estimate + actual entries | > 80% |
| Version check on session start | Session output shows version comparison | Every session |
| Feedback sent upstream | Files in `os/feedback-to-sutra/` | > 0 after 5 sessions |
| Findings tracked at Depth 4-5 | Files in `os/findings/` | 100% of Depth 4-5 tasks |
| Protocols created in LEARN | Files in `os/protocols/` | > 0 after 10 tasks |

## 6. PROCESS (must match current Sutra lifecycle)

The company's task lifecycle must follow:
```
OBJECTIVE → OBSERVE → SHAPE → PLAN → EXECUTE → MEASURE → LEARN
```

With depth controlling granularity:
```
Depth 1: OBJECTIVE → EXECUTE → MEASURE (minimal)
Depth 2: OBJECTIVE → OBSERVE → EXECUTE → MEASURE → LEARN
Depth 3: full lifecycle
Depth 4: full lifecycle + HLD + ADR + staged verify
Depth 5: full lifecycle + Finding Resolution Gate (HARD) + retro
```

## 7. VERIFICATION COMMAND

Run from the holding repo root:
```bash
bash holding/hooks/verify-os-deploy.sh {company}
```

Binary outcome: DEPLOYED (100% match) or NOT DEPLOYED.

---

## Manifest Versioning

This manifest is versioned with Sutra. When v1.8 ships:
1. Create MANIFEST-v1.8.md
2. Add new requirements
3. Update verify-os-deploy.sh to read new manifest
4. Archive MANIFEST-v1.7.md

Each company is verified against the manifest for their pinned version.
