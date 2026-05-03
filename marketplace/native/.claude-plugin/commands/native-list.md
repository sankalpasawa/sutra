---
description: List Domains, Charters, and Workflows in the Sutra Native user-kit.
allowed-tools: Bash
---

# /native:list

Show what's been created in the user-kit.

**Usage:**
- `/native:list` — show all (domains + charters + workflows)
- `/native:list domains` — domains only
- `/native:list charters` — charters only
- `/native:list workflows` — workflows only

When invoked, Claude will:

1. Parse `$ARGUMENTS`:
   - if empty → target = `all`
   - else first token (one of: `domains|charters|workflows|all`)

2. Resolve the `sutra-native` binary (same pattern as create-domain).

3. Invoke:
   ```bash
   "$NATIVE_BIN" list <target>
   ```

4. Print stdout verbatim. Empty user-kit shows zero counts plus a hint pointing at `/native:create-domain`.

**Source**: `src/cli/sutra-native.ts` `cmdList` (v1.1.2+).
