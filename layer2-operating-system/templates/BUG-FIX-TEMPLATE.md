# Bug Fix: [Short description]

> Required for all bug fixes at L2+. Every fix must include the test that would have caught it.

## Bug Description
What's broken? How was it discovered? (2-3 sentences)

## Root Cause
Why did this happen? (Not "what file" -- WHY did the system allow this?)

## Fix Approach
What changes fix the root cause? (Brief -- the diff tells the rest)

## Regression Test
**Test that reproduces the bug before the fix:**
```
// The test that FAILS on the bug and PASSES on the fix
```

- [ ] Test written
- [ ] Test fails without fix (reproduces the bug)
- [ ] Test passes with fix

## Process Fix
What process change prevents this CLASS of bug? (Not just this instance)
- Example: "Add input validation to all API endpoints" not "add validation to /users"
- Example: "Null-check pattern in data layer" not "fix null check in getUserById"

---
*Fix the bug. Write the test. Fix the process. In that order.*
