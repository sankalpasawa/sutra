# Vendored artifacts manifest 

- **title**: Vendor manifest (prebuilt artifacts the panel consumes)
- **status**: active
- **updated**: 2026-08-25
- **note**: lives at the sutra-ui root because `static/vendor/` matches a
  tooling deny rule; the artifacts themselves are served normally.

| Artifact | Source | Pin | sha256 |
|---|---|---|---|
| static/vendor/sutra-editor.js | sankalpasawa/silverbullet, branch `sutra-editor` (fork of silverbulletmd/silverbullet 2.10.0, MIT — LICENSE.md preserved upstream; attribution banner in the file header) | fork commit da18182; upstream tag 2.10.0 | 22da847615903a8dc121e6659f4a7d8402cdb5d1ecfb0defbed2f478e759e24c |

Rebuild: `node sutra-build.mjs` at the fork root (esbuild, deterministic,
es2022 iife). Verify: `shasum -a 256 static/vendor/sutra-editor.js` must equal
the pin above; bump both together in one commit. The panel has no build step —
it consumes this file as-is (PLAN-25-EDITOR S9).

---
provenance: {author: claude (session 78660f98), date: 2026-08-25, inputs:
[PLAN-25-EDITOR S9, fork commit 0209b6d, dual consult], review: none,
supersedes: none, confidence: high, gaps: none}
