# Apps threat model and the safe-extraction contract

What can go wrong when an app is a page in a sandbox today and a tarball from a marketplace tomorrow, and the contract an import must meet before anything lands (ADR-039, decision D-E of the program).

| Field | Value |
|---|---|
| **status** | ACTIVE — program steps 27, 28 |
| **updated** | 2026-09-11 |
| Scope | page sandbox (shipped, D-M5) · export/import (behind `flags.apps_publish`, off) |
| Method | STRIDE, one row per category, top risk each |

## <a id="stride"></a>STRIDE (step 27)

| Category | Top risk | Control | Test (step 47) |
|---|---|---|---|
| Spoofing | a tarball or registry entry claims to be an app it is not | `sha256` of the tarball must equal the registry entry; `signature` (ed25519, ADR-040) once signing lands; `origin.created_by = marketplace` is set by the installer, never read from the manifest | mismatched sha256 → nothing lands, `failed_verification` |
| Tampering | a tarball member writes outside the app folder (`../`, absolute path, symlink target) | member whitelist + realpath containment inside a quarantine dir; symlinks, hardlinks, absolute paths and `..` refused | traversal fixture → refused |
| Repudiation | nobody can tell who installed or changed an app | every transition appends an event with `actor` and `key` (APPS-EVENTS.md) | import → `app.imported` row present |
| Information disclosure | a page reaches the panel token or `/api/*` | iframe `sandbox="allow-scripts"` (no same-origin) + CSP with no `connect-src`; `openExternal` never reachable from a page | `test_11` CSP assertions; step 83 Electron check |
| Denial of service | an oversized or member-heavy tarball fills the disk or hangs extraction | caps: 20 MB total · 200 members · 5 MB per file; extraction stops at the first breach | oversized fixture → refused before the cap is exceeded on disk |
| Elevation of privilege | a page or a manifest turns into code the panel runs | manifests are data (JSON Schema validated); pages run only in the sandbox; `guard` is not executed; no `network: true` accepted by the registry schema | manifest with executable-looking fields → validated, ignored |

## <a id="contract"></a>Safe-extraction contract (step 28)

| # | Rule | Codex fold |
|---|---|---|
| X-1 | Download to a quarantine dir under `~/.sutra-ui/modules/.quarantine/<op_id>/`; verify `sha256` against the registry entry BEFORE opening the archive | P5 |
| X-2 | Read the manifest member first; validate against `app-manifest.schema.json`; `id` must equal the target folder name; `schema` must equal the registry's `manifest_schema` | P4 |
| X-3 | Member whitelist: `module.json`, `index.html`, `assets/**`; anything else is a refusal, not a skip | — |
| X-4 | Every member path is normalized and `realpath`-checked to stay under the quarantine dir; `..`, absolute paths, symlinks, hardlinks, device files → refuse | — |
| X-5 | Caps: 20 MB total, 200 members, 5 MB per file, enforced while streaming; the first breach refuses | P10 |
| X-6 | If `~/.sutra-ui/modules/<id>/` already exists: refuse unless the caller asked for an explicit two-phase replace (backup to `.quarantine/<op_id>/prev/`, rename new in, delete backup on success, restore on failure) | P6 |
| X-7 | Final step is ONE atomic rename of the quarantine folder into place; on any refusal the quarantine dir is removed and nothing has landed | P5 |
| X-8 | Every outcome appends `app.imported` with `result` ok or failed_verification and a `reason`; the failed state never touches `module.json` (APPS-LIFECYCLE.md L-3) | — |
| X-9 | The installer sets `origin.created_by = marketplace` and `publish.state = imported`; values in the manifest for these two fields are overwritten | — |
| X-10 | `flags.apps_publish` off → the endpoints answer 404 with the hint; the contract is unreachable, not merely unused | program D-C |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-11) from ADR-039, the codex program review P2/P7 and the codex pre-consult P4-P6/P10; program steps 27, 28. STRIDE per the `core:architect` skill's threat-model shape.
