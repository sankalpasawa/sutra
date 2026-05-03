---
description: Create a Sutra Domain at runtime (no TypeScript needed). Wraps `sutra-native create-domain`.
allowed-tools: Bash
---

# /native:create-domain

Create a new Domain in the user-kit at runtime.

**Usage:** `/native:create-domain <D-id> <name> [authority...]`

**Examples:**
- `/native:create-domain D6 Health`
- `/native:create-domain D6 Health "Decide own training, recovery, sleep cadence."`

When invoked, Claude will:

1. Parse `$ARGUMENTS`:
   - first token = `<D-id>` (must match `D\d+(\.D\d+)*` per primitive validator — D6, D1.D2, etc.)
   - second token = `<name>` (single word; quote it for multi-word)
   - remaining tokens (joined) = `authority` text (optional; if absent, sensible default applied)

2. Resolve the latest installed `sutra-native` binary:
   ```bash
   NATIVE_BIN=$(ls -dt ~/.claude/plugins/cache/sutra/native/*/bin/sutra-native 2>/dev/null | head -1)
   ```
   Fall back to `command -v sutra-native` if the cache path doesn't exist.
   If neither resolves, surface: "native@sutra not installed; run `/plugin install native@sutra`".

3. Invoke in a single Bash call:
   ```bash
   "$NATIVE_BIN" create-domain --id <D-id> --name <name> [--authority "<authority>"]
   ```

4. Print the binary's stdout verbatim. Exit code 2 → flag a usage error inline. Exit code 0 → tell the founder where the JSON landed (the binary already prints the path).

The Domain is persisted as JSON under `$SUTRA_NATIVE_HOME/user-kit/domains/<D-id>.json` (default `~/.sutra-native/user-kit/domains/`). Re-create with the same id will overwrite — current behavior, not a bug.

**Source**: `src/cli/sutra-native.ts` `cmdCreateDomain` (v1.1.2+).

**Dependency**: native@sutra v1.1.2 or later. v1.1.1 lacks this subcommand — run `/plugin update native@sutra` first if you're on the older version.
