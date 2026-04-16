# Sutra → Holding: v1.9 Propagation Loop Is Open (4 Bugs in holding/hooks/)

**Date**: 2026-04-17
**From**: Sutra session (triggered by DayFlow 2026-04-17 feedback)
**To**: Holding-scope CEO (requires `god-mode activate Asawa` or holding-root session)
**Severity**: High — v1.9's signature deliverable ("close the policy→implementation→deployment loop permanently") is factually open.

---

## Evidence (from 3 parallel audit agents run 2026-04-17)

**Only DayFlow is IN-SYNC at v1.9.** Every other on-disk client carries `v1.9` in `os/SUTRA-VERSION.md` but is missing the v1.9 governance artifacts (MANIFEST-v1.9.md, POLICY-COVERAGE.md). Auto-propagation (PROTO-018) has effectively never executed across the portfolio. Per-client state:

| Client | Status | Evidence |
|---|---|---|
| DayFlow | IN-SYNC | MANIFEST-v1.9 + POLICY-COVERAGE on disk |
| PPR | PARTIAL | SUTRA-VERSION=v1.9, CLAUDE.md=v1.7, no manifest on disk |
| Maze | PARTIAL | same as PPR |
| Paisa | STALE | SUTRA-VERSION=v1.4, CLAUDE.md=v1.7 (internal disagreement) |
| Asawa (holding) | STALE | holding CLAUDE.md declares v1.8 |
| Billu | IN-SYNC (tier-1 scope) | v1.9 pin + config |
| Sutra (self) | SELF-HOSTED | v1.9 canonical |
| Jarvis | GHOST | registry row; no on-disk dir |
| Dharmik | GHOST | registry row; no on-disk dir |

The reason the propagation never fired correctly: four concrete bugs in `holding/hooks/` scripts.

---

## BUG 1 — `upgrade-clients.sh` awk registry parse silently returns empty

**File**: `holding/hooks/upgrade-clients.sh` lines 38–47, 49

The parser range `awk '/^## .*[Cc]lient [Rr]egistry/,/^## /'` is applied to MANIFEST-v1.9.md. The "Client registry (v1.9 targets)" section on line 142 is the **last** `##` heading in the file — awk's range start+end match on the same line, so the range emits only the header and zero table rows. Parsed registry is empty. Script silently falls through to the hardcoded fallback on line 49:

```bash
[ "${#REGISTRY[@]}" -eq 0 ] && REGISTRY=(dayflow maze ppr billu sutra)
```

**Consequence**: Every invocation of `upgrade-clients.sh` walks 5 clients, not the 9 declared in MANIFEST. Paisa, Asawa, Jarvis, Dharmik are never touched by auto-propagation despite being declared v1.9 targets. PROTO-018's comment header (line 16: "Client list derived from MANIFEST-v*.md registry, not hardcoded") is violated at runtime.

**Proposed fix**: Replace the awk range with a two-pass approach that survives terminal sections:

```bash
awk '/^## .*[Cc]lient [Rr]egistry/{inreg=1; next} inreg && /^## /{inreg=0} inreg && /^\| *[0-9]+/' "$MANIFEST"
```

Then pipe to the column-3 extractor. Add a test in `holding/hooks/tests/` that asserts parse returns ≥8 names for MANIFEST-v1.9 — this would have caught the bug at write time.

**Severity**: High.

---

## BUG 2 — `verify-policy-coverage.sh` hardcodes the client list

**File**: `holding/hooks/verify-policy-coverage.sh` line 29

```bash
CLIENTS=(dayflow maze ppr billu sutra)
```

Contradicts the canonical-source-of-truth principle stated in MANIFEST-v1.9 §10 (POLICY-COVERAGE.md is the truth for policy enforcement). The verifier uses a frozen subset; it cannot detect deployment gaps for any client outside this array.

**Proposed fix**: Parse from MANIFEST-v{current}.md (same registry the upgrader should use after Bug 1 is fixed). Single canonical source. Electing MANIFEST as source of truth is the cleanest move — a small clarifying sentence in MANIFEST §9/§10 is warranted.

**Severity**: Medium.

---

## BUG 3 — `verify-os-deploy.sh` crashes silently on empty `tier:` parse

**File**: `holding/hooks/verify-os-deploy.sh` (tier extraction near top; `set -euo pipefail` is set)

Running against DayFlow, Maze, or PPR produces exit 1 with zero output. Cause: `tier:` line in their `os/SUTRA-CONFIG.md` does not match the exact regex the script expects (likely an indentation/space difference or the value isn't immediately numeric). `set -euo pipefail` converts the empty capture into a hard exit.

**Consequence**: `verify-os-deploy.sh` cannot actually verify the 3 most active clients. PROTO-013's "Sutra version deploy verification" is silently unusable where it matters most.

**Proposed fix**: Add a default + explicit fallback: `tier=$(grep -oE ... || echo 1)`. Emit a clear warning rather than silent exit when config can't be parsed. Add a regression test per tier parser.

**Severity**: High — masquerades as "script works" in tests that only check exit code.

---

## BUG 4 — Submodule boundary isolation is only 60% enforced

**File**: `holding/hooks/isolation-tests.sh` — 6/15 assertions fail

Boundary hooks are not actually blocking these cross-boundary edits at runtime:
- DayFlow session editing sutra/, holding/, maze/
- Sutra session editing dayflow/, holding/

This is the PROTO-011 "Company Independence" contract. It was presumed shipped; it's actually half-shipped. If this is the state today, cross-boundary edits have been passing silently for some time.

**Proposed fix**: Root-cause the per-scenario assertion failures (each scenario prints the specific boundary it expected enforced). Likely `.claude/settings.json` in one or both sides is not registering `enforce-boundaries.sh` under the right matchers, OR the hook is registered but exiting 0 when it should exit 2.

**Severity**: High — silent governance failure.

---

## Meta-observation

All four bugs share a shape: **policy text says X is enforced; at runtime X is not enforced; tests did not catch it because they tested exit codes or happy paths, not semantic coverage.**

This is PROTO-017's own thesis applied to PROTO-017's own enforcers. The coverage gate should either (a) assert that declared enforcers actually parse the canonical registry — not just exist and be executable — or (b) we accept that this category of bug needs a property-based test suite ("parser returns ≥N rows", "boundary blocks K/K scenarios", not just "exit 0").

No new protocol is being proposed here — the existing PROTO-000 5-part rule (DEFINED → CONNECTED → IMPLEMENTED → TESTED → DEPLOYED) covers this. The TESTED leg was weak. Strengthen the tests first; protocol text is fine as-is.

---

## What Sutra already did (sutra-scope)

- Reconciled `sutra/CURRENT-VERSION.md` Client Registry against verified reality (added Billu + Sutra rows, marked Jarvis/Dharmik GHOST, corrected PPR/Maze/Paisa/Asawa).
- Acknowledged DayFlow 2026-04-17 feedback: Gap D (registry row) real and fixed; Gap E (missing script) was a false alarm — the script exists at `holding/hooks/upgrade-clients.sh` per MANIFEST §9; the feedback's `find sutra -name ...` search was scoped-too-narrow, same bug this session made.
- Ran the full test framework + 3 verifiers + per-client audit. Raw reports: see session trace.

---

## What holding-scope needs to do

1. Fix Bug 1 (awk range) + add parse-count test. One commit.
2. Fix Bug 2 (delete hardcoded CLIENTS, parse from MANIFEST). Same commit or next.
3. Fix Bug 3 (tier parse fallback + test). One commit.
4. Fix Bug 4 (boundary isolation root cause). One commit.
5. Re-run `upgrade-clients.sh` with fixes → propagate v1.9 to Maze, PPR, Paisa, Asawa-holding.
6. Run `verify-policy-coverage.sh --write` → regenerate ledger.
7. Decide on Jarvis + Dharmik GHOST rows: onboard or remove.

Estimated work: one focused holding-scope session with god-mode active, ~2 hours.
