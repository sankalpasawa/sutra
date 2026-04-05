# Sutra — How Protocols Get Created

ENFORCEMENT: HARD — every new protocol follows this process. No exceptions.

## The Protocol Lifecycle

```
OBSERVATION → DRAFT → TEST → REVIEW → PUBLISH → MONITOR → EVOLVE/RETIRE
```

### 1. OBSERVATION (a gap is noticed)

A protocol starts when someone notices a repeated problem:
- A gap report identifies the same issue 2+ times
- A founder complains about the same friction repeatedly
- An agent makes the same mistake across multiple features
- A security/data issue is discovered

**Trigger rule**: No protocol is created for a one-time problem. The problem must recur.

**Output**: One sentence describing the problem. Filed in `holding/evolution/protocol-candidates.md`.

### 2. DRAFT (write the protocol)

Every protocol has exactly this structure:

```markdown
# PROTO-XXX: [Name]

ENFORCEMENT: [HARD | SOFT | FOUNDER-OVERRIDE]
STATUS: EXPERIMENTAL
ORIGIN: [which company, which cycle, what happened]
CREATED: [date]

## Rule
One sentence. What must happen, when.

## Trigger
When does this protocol activate? Be specific.

## Check
How do you verify compliance? (Must be automatable — if you can't write a hook for it, it's not a protocol.)

## Violation Signal
What does it look like when this protocol is broken?

## Evidence
What artifact proves this protocol was followed?
```

**Key rules for drafting:**
- One protocol = one rule. Not two. Not "and also."
- If you can't state the rule in one sentence, it's not clear enough.
- If you can't automate the check, it's a guideline, not a protocol.
- Every protocol must have an ORIGIN (which real incident created it).

### 3. TEST (use it on 2+ features)

The protocol starts as EXPERIMENTAL:
- Apply it to the next 2 features in the originating company
- The Founder Agent can reject it without reason
- Track: did it catch something? Did it add friction? Was the friction worth it?

**Output**: 2+ feature cycles with the protocol active. Notes on usefulness.
**Gate**: 2 features must use it before promotion.

### 4. REVIEW (decide: promote or kill)

After 2 feature tests, evaluate:

| Question | If YES | If NO |
|----------|--------|-------|
| Did it catch a real problem? | Evidence for keeping | Evidence for removing |
| Did it add friction without catching anything? | Candidate for removal | — |
| Was the friction proportional to the risk? | Keep | Simplify or remove |
| Would the Founder Agent accept this long-term? | Keep | Rethink |

**Decision**: PROMOTE to TESTED, or REMOVE with documented reason.

### 5. PUBLISH (deploy to other companies)

If promoted to TESTED:
- Deploy to at least 1 other company (different product type)
- Track: does it work across product types, or is it company-specific?
- If company-specific: stays in company config, not Sutra core

**Gate**: Must work in 2+ companies to become STABLE.

### 6. MONITOR (track effectiveness)

For every STABLE protocol:
- Count: how many times did it fire per month?
- Count: how many times was it overridden?
- Track: false positive rate (fired when it shouldn't have)

**Demotion triggers**:
- 0 fires in 30 days → candidate for DEPRECATED
- >50% override rate → protocol is wrong, not the users
- >30% false positive rate → check logic is broken

### 7. EVOLVE or RETIRE

**Evolve**: If the protocol works but needs adjustment, update it. Version the change.
**Retire**: If the protocol no longer serves a purpose:
- Move to DEPRECATED (30-day warning)
- Then REMOVED (archived in PROTOCOL-ARCHIVE.md with full history)

---

## Protocol Registry

All protocols live in `sutra/layer2-operating-system/PROTOCOLS.md`.
Each has: ID, name, status, origin, last-tested date, fire count.

## Anti-Patterns (don't create protocols for these)

| Pattern | Why Not |
|---------|---------|
| One-time incidents | Protocols are for recurring problems |
| Personal preferences | "I like X" is not a protocol trigger |
| Theoretical risks | Until it actually happens, it's not protocol-worthy |
| Process for process's sake | Every protocol must catch real problems |
| Duplicate coverage | If an existing protocol covers it, don't add another |

## The Simplicity Check

Before creating any new protocol, answer:
1. Can an existing protocol cover this? (If yes: extend, don't create new)
2. Will this protocol fire at least once per 10 features? (If no: too rare to justify)
3. Can this be a company-level config instead of a Sutra protocol? (If yes: do that)
4. Does this take the protocol count above 10? (If yes: which existing protocol do you remove?)

**Total protocol count target: ≤ 10.** Addition requires removal or merger.
