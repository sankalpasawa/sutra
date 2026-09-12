# ADR-039 — The app folder is the package, and the package is the marketplace unit

**Status**: Proposed · **updated**: 2026-09-11 · author: CEO of Asawa

## Status

Proposed — 2026-09-11. Supersedes nothing; extends D-M1 (the folder is the module) in `holding/departments/experience/desktop-app/2026-09-08-modules-design.md`.

Note 2026-09-12: only the terminology in this ADR ("App" as the user-facing word, "module" internal) is accepted, under D74 Rulings 2026-09-12; the package and marketplace mechanics stay Proposed.

## Context

Sutra Desktop Apps (user-facing word App; internal name module) live as one folder each under `~/.sutra-ui/modules/<id>/` with `module.json` as the only record (D-M1). The founder wants an app to be publishable to a marketplace later, with a Publish button that is NOT built now. The architecture must therefore make an app installable and verifiable today without adding a second store or a second identity.

Forces: the Claude-plugin marketplace (`.claude-plugin/marketplace.json`) is an index discipline for Claude Code extension packages, not runtime content; import of third-party content is a trust boundary (path traversal, symlinks, oversized files, unsandboxed HTML); `module.json` carries `schema` (format) and `version` (revision), and publishing needs a semver.

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| Apps as Claude-plugin marketplace entries | plugins install hooks and skills into Claude Code; apps are runtime content for the panel (codex P1/P10) |
| A separate database of published apps inside the panel | a second store contradicts D-M1 and doubles identity |
| Publish UI now | founder deferred it; the package format is the part that must not be redone |

## Decision

The app folder MUST be the package and `module.json` MUST be its manifest.

- Publishing MUST produce a tarball of the folder plus one entry in a Sutra Apps registry index (schema in `sutra-ui/schemas/apps-registry.schema.json`: `id`, `version`, `manifest_schema`, `artifact_url`, `sha256`, `signature`, `min_sutra_version`, `permissions`, `department_hint`). The registry is separate from the Claude-plugin marketplace.
- Installing MUST unpack into `~/.sutra-ui/modules/<id>/` with `origin.created_by = "marketplace"` and MUST validate the manifest before any file lands; extraction MUST refuse symlinks, path escapes, and files beyond declared size and count caps.
- `module.json` MUST keep `schema` (format, migrates 1→2) separate from `version` (app revision); the optional `publish` block carries `version` (semver), `author`, `license`, `homepage`, `checksum`, `published_at`, `source`. Unknown fields MUST be preserved.
- Lifecycle state MUST be carried in `origin` / `publish`: local, exported, imported, published, update_available, incompatible, revoked, failed_verification.
- Export and import endpoints MUST sit behind `flags.apps_publish`, default off, until a threat model and its tests exist.

## Consequences

| Kind | Effect |
|---|---|
| Positive | One identity per app from creation to marketplace; no migration of storage when Publish arrives |
| Positive | A chat, Shadow, disk, or the marketplace all produce the same folder shape |
| Negative | Import carries a real security surface that needs its own tests before the flag turns on |
| Negative | Schema v2 migration must handle every existing folder on disk |
| Neutral | The Publish button is a later program; this ADR only fixes the package |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-07) from the founder direction of 2026-09-11 and the codex program review P1/P2/P6/P9/P10; program `holding/plans/apps-program/PROGRAM.md` step 21.
