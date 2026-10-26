# Vendored artifacts manifest 

- **title**: Vendor manifest (prebuilt artifacts the panel consumes)
- **status**: active
- **updated**: 2026-08-25
- **note**: lives at the sutra-ui root because `static/vendor/` matches a
  tooling deny rule; the artifacts themselves are served normally.

| Artifact | Source | Pin | sha256 |
|---|---|---|---|
| static/vendor/sutra-editor.js | sankalpasawa/silverbullet, branch `sutra-editor` (fork of silverbulletmd/silverbullet 2.10.0, MIT — LICENSE.md preserved upstream; attribution banner in the file header) | fork commit 8c6b28d; upstream tag 2.10.0 | 96892401253820f88a3eb961b6e9475f06db31ec291c1201bf1efd2976bda112 |
| j2ui_assets/j2_ui.html | J2_Prototype `j2_ui.html` (the J2 prototype's department page), copied with three documented substitutions only: S1 relative paths, S2 one `j2host.js` script line, S3 vendored fonts (off until `scripts/fetch_j2_fonts.py` has run) | J2_Prototype@f9ceba15192bbd6f62047cb7288d0f291b2fbc4f; the prototype's own sha256 is `23549799903e98485f404872670c49e5735c7cc9962c19b42037b1bde5ebad0d` | 776aecafaa70d28a0338be94b4b87ced6d3bdd1a9623ac87bc49d1f675a1b7da |

Rebuild: `node sutra-build.mjs` at the fork root (esbuild, deterministic,
es2022 iife). Verify: `shasum -a 256 static/vendor/sutra-editor.js` must equal
the pin above; bump both together in one commit. The panel has no build step —
it consumes this file as-is (PLAN-25-EDITOR S9).

The J2 page (`j2ui_assets/`, served by `j2ui_page.py` at `/j2ui/{ref}/`): rebuild with
`J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui.py`, which reads git objects of the prototype, writes
`j2ui_assets/*` and `test_fixtures/j2ui/j2_ui_render.js` and pins every hash in `j2ui_assets/PINNED.json`.
Verify: `python3 scripts/sync_j2_ui.py --check`, and `test_j2ui_verbatim.py` (its first layer needs no prototype:
the copy with its substitutions undone must hash to the prototype's own sha256 above). `j2ui_assets/j2_schema.py`
and `test_fixtures/j2ui/j2_ui_render.js` are byte copies of the prototype's files at the same commit.

---
provenance: {author: claude (session 78660f98), date: 2026-08-25, inputs:
[PLAN-25-EDITOR S9, fork commit 0209b6d, dual consult], review: none,
supersedes: none, confidence: high, gaps: none}
