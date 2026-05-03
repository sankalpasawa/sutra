---
description: Create a Sutra Charter at runtime under a Domain. Wraps `sutra-native create-charter`.
allowed-tools: Bash
---

# /native:create-charter

Create a new Charter in the user-kit at runtime, optionally linked under a Domain.

**Usage:** `/native:create-charter <C-id> <D-id> <purpose...>`

**Examples:**
- `/native:create-charter C-sleep D6 "Hold a 6h floor on nightly sleep, surface drift early."`
- `/native:create-charter C-build-product D2 "Ship product changes via thin reviewed slices."`

When invoked, Claude will:

1. Parse `$ARGUMENTS`:
   - first token = `<C-id>` (must match `C-.+` per primitive validator)
   - second token = `<D-id>` (the parent Domain — use one you've already created via `/native:create-domain` or one of the starter D1-D5)
   - remaining tokens (joined) = `purpose` text (1-line outcome statement; required non-empty)

2. Resolve the `sutra-native` binary:
   ```bash
   NATIVE_BIN=$(ls -dt ~/.claude/plugins/cache/sutra/native/*/bin/sutra-native 2>/dev/null | head -1)
   ```
   If absent, surface: "native@sutra not installed; run `/plugin install native@sutra`".

3. Invoke:
   ```bash
   "$NATIVE_BIN" create-charter --id <C-id> --domain <D-id> --purpose "<purpose>"
   ```

4. Print stdout verbatim. The binary handles validation; non-zero exit → show the error and suggest the fix.

The Charter is persisted at `$SUTRA_NATIVE_HOME/user-kit/charters/<C-id>.json`. Its `acl[0].domain_or_charter_id` is set to the supplied `<D-id>` so the Domain ↔ Charter link survives reload.

**Source**: `src/cli/sutra-native.ts` `cmdCreateCharter` (v1.1.2+).
