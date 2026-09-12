# ADR-041 — App packages are signed by their publisher: ed25519 over a canonical entry payload

**Status**: Accepted · **updated**: 2026-09-12 · author: CEO of Asawa

## Status

Accepted — 2026-09-12 by the Publish program (`holding/plans/apps-publish/PROGRAM.md`, atom a-c0a2923c-37), which hosted the registry (Q-1: `website/apps/registry.json` in the sutra repo, served by GitHub Pages at https://sankalpasawa.github.io/sutra/apps/registry.json) and declared `cryptography==46.0.0` in `sutra-ui/requirements.txt` after a wheel check for both macOS arches. Three amendments from the codex plan review, folded into the Decision below: the implementation is the `cryptography` library and never a hand-written curve; an entry without a signature is refused for a registry install whatever the flag says; a downgrade needs `replace=1` and `downgrade=1`. Extends ADR-039 (the folder is the package). Proposed 2026-09-11.

## Context

Import verifies the tarball `sha256` carried by the registry entry (integrity). Nothing binds an artifact to a publisher (authenticity): a host that can rewrite the index can swap tarball and checksum together, or point an entry at an older, validly built artifact. Installs are unattended, and page apps run HTML inside the panel (sandboxed, no network, D-M5). Signing must need no infrastructure today; the registry is static JSON.

### Alternatives considered

| Alternative | Rejected because |
|---|---|
| sha256 only (today) | integrity, not authenticity |
| TLS / trust the host | trusts the host, not the publisher; hosts move (Q-1) |
| Sigstore keyless | OIDC plus a transparency log to run |
| GPG | tooling weight; no clean library in the panel venv |

## Decision

- The signature MUST be ed25519 over the canonical JSON (sorted keys, no spaces) of `{publisher_id, app_id, version, manifest_schema, artifact_sha256, sutra_version_range}`; import MUST check every field against the registry entry before extraction (codex R-J P1).
- The registry entry carries `signature {alg: "ed25519", value: base64, key_id}`; `key_id` is the first 16 hex of sha256(public key). Publisher keys live in an optional top-level `publishers` list of the index.
- Trust is split (P3): the default registry the plugin ships with MUST carry its publisher keys pinned in the plugin; any other registry pins a publisher's key on first install (TOFU) and MUST show the fingerprint.
- Rotation (P4) is a `rotations` entry `{publisher_id, old_key_id, new_key_id, new_pubkey, created_at}` signed by the old key, which MUST already be pinned.
- A bad or mismatched signature MUST land nothing and append `app.imported {result: failed_verification, reason}` (the APPS-THREATS X-8 row; there is no separate event); the manifest never carries that state (schema-2 `publish.state` excludes it). An unsigned entry is refused for a registry install, flag or no flag (amended 2026-09-12; the earlier `app.unsigned` allowance is withdrawn). A plain import of a local tarball the operator chose stays what X-1..X-10 made it.
- Import MUST refuse a lower `version` over an installed higher one unless `replace=1` AND `downgrade=1` are both given, appending `app.downgrade_blocked` (P2; amended 2026-09-12: X-6 already needs `replace=1` for any replacement, so going back needs its own word).
- The implementation is the `cryptography` library (`sutra-ui/modules_sign.py`); a hand-written ed25519 is never an acceptable fallback. Where the library is missing, signing refuses and every registry install refuses (an entry nobody can verify never lands).
- Pins: the default registry's publisher keys ship in `sutra-ui/registries.json` and the index's own `publishers` list never widens them; any other registry pins its publishers on first install into `~/.sutra-ui/registries-pinned.json` and the install response carries the fingerprints; a rotation is accepted only when signed by a key already pinned.
- The private key lives at `~/.sutra-ui/keys/<key_id>.ed25519`, mode 0600, generated on first Publish, and never leaves the machine.

## Consequences

| Kind | Effect |
|---|---|
| Positive | Authenticity survives a registry move or a compromised host; the index format needs no change (`signature` is already optional) |
| Positive | Downgrade and substitution are refused by fields the publisher signed, not by host behaviour |
| Negative | One optional dependency; a lost key is a new publisher identity (rotation only runs forward) |
| Neutral | Nothing changes until Publish exists; export/import stay behind `flags.apps_publish` (off) |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-20) from ADR-039, `apps-registry.schema.json`, and codex review R-J P1-P4; program `holding/plans/apps-program/PROGRAM.md` step 98.
