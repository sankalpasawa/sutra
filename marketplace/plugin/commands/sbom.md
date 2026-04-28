---
name: sbom
description: Generate Software Bill of Materials — SHA256 per shipped file for supply-chain integrity check.
disable-model-invocation: false
---

# /core:sbom — Plugin integrity manifest

Writes SHA256 hash per shipped file to `~/.sutra/sbom.txt`. Diff against a stored manifest to detect tampering. SECURITY charter primitive #13.

Run this command via the Bash tool:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/sutra sbom
```
