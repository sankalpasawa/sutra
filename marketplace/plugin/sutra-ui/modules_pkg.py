"""modules_pkg.py -- the Apps package: export a folder as a tarball, import a
tarball as a folder (ADR-039; APPS-THREATS.md X-1..X-10; program steps 59-60).

Both entry points are pure functions over the modules home; the routes live in
modules_api.py behind `flags.apps_publish` (default OFF -> 404 with the hint,
X-10). Stdlib only. The import is the marketplace trust boundary, so:

  X-1  sha256 of the bytes is checked BEFORE tarfile.open
  X-2  the manifest is read and validated from the member list before any
       file is written; id must equal the target; schema must be 2
  X-3  member whitelist: <id>/module.json, <id>/index.html, <id>/assets/**
  X-4  POSIX-normalised names; absolute, '..', empty, symlink, hardlink, device,
       fifo -> refused; only regular files (and bare dirs under the prefix)
  X-5  caps: 200 members, 5 MB per file, 20 MB total, declared AND actual
  X-6  an existing folder is refused unless replace=1 (backup, rename, restore)
  X-7  extraction into a quarantine dir; ONE os.rename into place at the end
  X-8  every outcome appends app.imported {result, reason}
  X-9  origin.created_by and publish.state are set by the installer

Publish program P2 (2026-09-12, ADR-041 Accepted): a REGISTRY install is
verified before the archive is opened -- the entry's id, sha256 and
manifest_schema must match the artifact, and its ed25519 signature must verify
against a pinned publisher key (an unsigned entry is refused, ruling P-3); a
version lower than the installed one is refused unless replace=1 AND
downgrade=1 (ruling P-4, `app.downgrade_blocked`). install_app() is the fetch
wrapper: index (validated, publishers pinned or TOFU), entry, artifact, import.
"""
import hashlib
import io
import json
import os
import posixpath
import shutil
import tarfile
import uuid

import modules_events
import modules_registry
import modules_sign
from json_store import read_json, write_json

MAX_MEMBERS = 200
MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
KINDS = ("chat", "page", "link")
STATUSES = ("draft", "ready", "archived")
EXPORTS = ".exports"
QUARANTINE = ".quarantine"


class PkgError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _whitelisted(rel):
    """rel is '<id>/…' already stripped of the id prefix."""
    return rel in ("module.json", "index.html") or rel.startswith("assets/")


def _norm_member(name, mid):
    """POSIX-normalise a member name and return the path relative to the app
    folder, or raise PkgError(400) for anything unsafe (codex P5)."""
    if not name or name.startswith("/") or "\\" in name:
        raise PkgError(400, "path traversal: member %r is absolute or malformed" % (name,))
    n = posixpath.normpath(name)
    parts = n.split("/")
    if n in (".", "") or any(p in ("..", "") for p in parts) or n.startswith("../"):
        raise PkgError(400, "path traversal: member %r escapes the app folder" % (name,))
    if parts[0] != mid:
        raise PkgError(400, "path traversal: member %r is outside %s/" % (name, mid))
    return "/".join(parts[1:])


_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas", "app-manifest.schema.json")
_SCHEMA = None


def _schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as fh:
            _SCHEMA = json.load(fh)
    return _SCHEMA


def validate_manifest(raw, mid):
    """X-2: the full JSON Schema (when the validator is importable) PLUS the
    explicit checks the import contract needs regardless (codex R3 P1b). The
    explicit checks never depend on the library, so a fleet install without it
    still refuses the dangerous cases."""
    if not isinstance(raw, dict):
        raise PkgError(400, "manifest is not an object")
    try:
        import jsonschema
        try:
            jsonschema.validate(raw, _schema())
        except jsonschema.ValidationError as e:
            raise PkgError(400, "manifest fails the schema: %s" % (e.message,))
    except ImportError:
        pass
    if raw.get("id") != mid:
        raise PkgError(400, "manifest id %r differs from the target %r" % (raw.get("id"), mid))
    if raw.get("schema") != 2:
        raise PkgError(400, "manifest schema must be 2 (registry manifest_schema); got %r" % (raw.get("schema"),))
    if not isinstance(raw.get("name"), str) or not raw["name"].strip():
        raise PkgError(400, "manifest name is required")
    if raw.get("kind") not in KINDS:
        raise PkgError(400, "manifest kind must be chat, page or link")
    if raw.get("status") not in STATUSES:
        raise PkgError(400, "manifest status must be draft, ready or archived")
    v = raw.get("version")
    if not isinstance(v, int) or v < 1:
        raise PkgError(400, "manifest version must be a positive integer")
    return raw


# ------------------------------------------------------------------ export --

def export_app(home, mid, actor="app"):
    """Tar the app folder (whitelisted members only) into <home>/.exports and
    record publish.state=exported + the checksum on the manifest (write-back
    patches the raw file, never a normalised row -- MIGRATIONS M-2)."""
    import re
    if not isinstance(mid, str) or not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", mid) or mid.startswith("sys-"):
        raise PkgError(404, "no app named %r" % (mid,))      # reserved / malformed ids: same policy as every write (codex R3 P2c)
    src = os.path.realpath(os.path.join(home, mid))
    if not src.startswith(os.path.realpath(home) + os.sep) or not os.path.isfile(os.path.join(src, "module.json")):
        raise PkgError(404, "no app named %r" % (mid,))
    raw = read_json(os.path.join(src, "module.json"), {})
    if raw.get("schema") != 2:
        raise PkgError(409, "this app is still manifest schema %r; edit it once so the write-back bumps it to 2, then export" % (raw.get("schema"),))
    members = []
    for rel in ("module.json", "index.html"):
        if os.path.isfile(os.path.join(src, rel)):
            members.append(rel)
    assets = os.path.join(src, "assets")
    if os.path.isdir(assets):
        for root, _dirs, files in os.walk(assets):
            for f in sorted(files):
                full = os.path.join(root, f)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                members.append(os.path.relpath(full, src))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for rel in members:
            t.add(os.path.join(src, rel), arcname=posixpath.join(mid, rel.replace(os.sep, "/")), recursive=False)
    blob = buf.getvalue()
    sha = hashlib.sha256(blob).hexdigest()
    out_dir = os.path.join(home, EXPORTS)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%s-%s.tgz" % (mid, raw.get("version", 1)))
    tmp = out + ".tmp.%d" % os.getpid()
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, out)
    pub = raw.get("publish") if isinstance(raw.get("publish"), dict) else {}
    pub.update({"state": "exported", "checksum": {"sha256": sha}})
    raw["publish"] = pub
    write_json(os.path.join(src, "module.json"), raw)
    modules_events.append(home, "app.exported", mid, kind=raw.get("kind"), version=raw.get("version"),
                          department_ref=(raw.get("department") or {}).get("ref") if isinstance(raw.get("department"), dict) else None,
                          actor=actor, sha256=sha, bytes=len(blob), publish_version=pub.get("version"))
    return {"id": mid, "sha256": sha, "artifact_path": out, "bytes": len(blob), "members": members}


# ------------------------------------------------------------------ import --

class _IdLock(object):
    """One import per app id at a time (codex R3 P1c): the existence check and
    the final rename happen under this lock, so a folder cannot appear between
    them. flock on <home>/.locks/<id>; released on exit even on failure."""

    def __init__(self, home, mid):
        self.dir = os.path.join(home, ".locks")
        self.path = os.path.join(self.dir, mid + ".lock")
        self.fd = None

    def __enter__(self):
        import fcntl
        os.makedirs(self.dir, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
        return False


def _verify_entry(entry, publishers, mid, sha256):
    """ADR-041: every field the publisher signed, checked against the entry and
    the bytes BEFORE the archive is opened. -> {publisher_id, key_id, version,
    published_at}. PkgError 409 on a mismatch, 403 on a signature refusal."""
    if not isinstance(entry, dict):
        raise PkgError(403, "a registry install needs the registry entry to verify against")
    if entry.get("id") != mid:
        raise PkgError(409, "the registry entry describes %r, not %r" % (entry.get("id"), mid))
    if str(entry.get("sha256") or "").lower() != str(sha256 or "").lower():
        raise PkgError(409, "the registry entry's sha256 is not the artifact's")
    if entry.get("manifest_schema") != 2:
        raise PkgError(409, "the registry entry's manifest_schema must be 2")
    ok, why = modules_sign.verify_entry(entry, publishers or {})
    if not ok:
        raise PkgError(403, "signature refused: %s" % why)
    return {"publisher_id": entry.get("publisher_id"), "key_id": entry["signature"]["key_id"],
            "version": entry.get("version"), "published_at": entry.get("published_at")}


def import_app(home, mid, blob, sha256, replace=False, actor="marketplace", registry=None, op_id=None,
               entry=None, publishers=None, downgrade=False):
    """Install a tarball as <home>/<mid>/ under the extraction contract. On any
    refusal -- contract or otherwise -- nothing lands and app.imported records
    result=failed_verification (codex R3 P2a: OSErrors too).

    With `entry` (or `registry`) the install is VERIFIED (ADR-041): the signed
    fields are checked against the entry and the bytes before extraction, an
    unsigned entry is refused, and the manifest's publish.version must agree.
    A lower version than the installed one needs replace AND downgrade."""
    op_id = op_id or uuid.uuid4().hex[:12]
    home_real = os.path.realpath(home)
    quarantine = os.path.join(home_real, QUARANTINE, op_id)
    try:
        return _import_locked(home_real, mid, blob, sha256, replace, actor, registry, op_id, quarantine,
                              entry, publishers, downgrade)
    except PkgError as e:
        modules_events.append(home_real, "app.imported", mid, actor=actor, op_id=op_id,
                              result="failed_verification", reason=str(e), status=e.status)
        raise
    except Exception as e:                      # noqa: BLE001 -- the log row is the contract
        modules_events.append(home_real, "app.imported", mid, actor=actor, op_id=op_id,
                              result="failed_verification", reason="%s: %s" % (e.__class__.__name__, e), status=500)
        raise PkgError(500, "import failed: %s" % (e.__class__.__name__,))
    finally:
        shutil.rmtree(quarantine, ignore_errors=True)


def _import_locked(home, mid, blob, sha256, replace, actor, registry, op_id, quarantine,
                   entry=None, publishers=None, downgrade=False):
    import re
    if not isinstance(mid, str) or not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", mid) or mid.startswith("sys-"):
        raise PkgError(400, "id %r is not a valid app id" % (mid,))
    # X-1: the bytes first
    if not isinstance(sha256, str) or hashlib.sha256(blob).hexdigest() != sha256.lower():
        raise PkgError(409, "sha256 mismatch: the artifact is not the one the registry describes")
    if len(blob) > MAX_TOTAL:
        raise PkgError(413, "artifact exceeds the 20 MB total cap")
    # ADR-041: a registry install verifies the signed entry before the archive is opened
    signer = _verify_entry(entry, publishers, mid, sha256) if (entry is not None or registry) else None
    # pass 1 (X-2..X-5): scan the member list, nothing written
    members = []
    manifest = None
    total = 0
    seen = 0                                   # EVERY entry counts toward the cap, dirs included (codex R3 P1a)
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
            for ti in t:
                seen += 1
                if seen > MAX_MEMBERS:
                    raise PkgError(413, "archive exceeds the %d member cap" % MAX_MEMBERS)
                rel = _norm_member(ti.name, mid)
                if ti.issym() or ti.islnk():
                    raise PkgError(400, "symlink or hardlink member %r refused" % (ti.name,))
                if ti.isdir():
                    if rel not in ("", "assets") and not rel.startswith("assets/"):
                        raise PkgError(400, "member %r is not in the whitelist" % (ti.name,))
                    continue
                if not ti.isfile():
                    raise PkgError(400, "member %r is not a regular file" % (ti.name,))
                if not _whitelisted(rel):
                    raise PkgError(400, "member %r is not in the whitelist (module.json, index.html, assets/**)" % (ti.name,))
                if ti.size > MAX_FILE:
                    raise PkgError(413, "member %r exceeds the 5 MB per-file cap" % (ti.name,))
                total += ti.size
                if total > MAX_TOTAL:
                    raise PkgError(413, "archive exceeds the 20 MB total cap")
                members.append((ti.name, rel, ti.size))
                if rel == "module.json":
                    fh = t.extractfile(ti)
                    data = fh.read(MAX_FILE + 1) if fh else b""
                    try:
                        manifest = json.loads(data.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        raise PkgError(400, "manifest is not valid JSON")
    except (tarfile.ReadError, EOFError, OSError, ValueError) as e:
        if isinstance(e, PkgError):
            raise
        raise PkgError(400, "archive is unreadable: %s" % (e.__class__.__name__,))
    if manifest is None:
        raise PkgError(400, "archive has no %s/module.json" % mid)
    validate_manifest(manifest, mid)
    if not members:
        raise PkgError(400, "archive has no members")
    pubm = manifest.get("publish") if isinstance(manifest.get("publish"), dict) else {}
    if signer and pubm.get("version") and str(pubm["version"]) != str(signer["version"]):
        raise PkgError(409, "the artifact's manifest says version %s, the registry entry %s" % (pubm["version"], signer["version"]))
    new_version = signer["version"] if signer else pubm.get("version")
    # pass 2 (X-7): extract manually into quarantine, enforcing actual bytes (codex P6)
    stage = os.path.join(quarantine, mid)
    os.makedirs(stage, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        for name, rel, size in members:
            ti = t.getmember(name)
            dest = os.path.realpath(os.path.join(stage, rel))
            if not dest.startswith(os.path.realpath(stage) + os.sep):
                raise PkgError(400, "path traversal: member %r escapes the app folder" % (name,))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            fh = t.extractfile(ti)
            if fh is None:
                raise PkgError(400, "member %r could not be read" % (name,))
            written = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > size or written > MAX_FILE:
                        raise PkgError(413, "member %r is larger than declared" % (name,))
                    out.write(chunk)
            if written != size:
                raise PkgError(400, "member %r is truncated" % (name,))
    # X-9: the installer owns origin + publish state
    manifest["origin"] = {"created_by": actor if actor in ("marketplace", "app") else "marketplace",
                          "session_id": None, "at": modules_events._now()[:19] + "Z"}
    pub = manifest.get("publish") if isinstance(manifest.get("publish"), dict) else {}
    pub.update({"state": "imported", "checksum": {"sha256": sha256.lower()}})
    if registry:
        pub["source"] = {"registry": registry}
    if signer:                                      # the installer records who signed what it installed
        pub["source"] = dict(pub.get("source") or {}, registry=registry, publisher_id=signer["publisher_id"], key_id=signer["key_id"])
        pub["version"] = signer["version"]
        if signer.get("published_at"):
            pub["published_at"] = signer["published_at"]
    manifest["publish"] = pub
    write_json(os.path.join(stage, "module.json"), manifest)
    # X-6 + X-7 under the per-id lock: check, back up, place, restore on failure
    final = os.path.join(home, mid)
    backup = None
    with _IdLock(home, mid):
        if os.path.lexists(final):
            if not replace:
                raise PkgError(409, "an app with id %s already exists; pass replace=1 to replace it" % mid)
            # ADR-041 P2 / ruling P-4: going back a version is refused unless asked for twice
            installed = read_json(os.path.join(final, "module.json"), {}) or {}
            ipub = installed.get("publish") if isinstance(installed.get("publish"), dict) else {}
            if new_version and ipub.get("version"):
                try:
                    lower = modules_registry.compare(str(new_version), str(ipub["version"])) < 0
                except (ValueError, AttributeError):
                    lower = False
                if lower and not downgrade:
                    modules_events.append(home, "app.downgrade_blocked", mid, kind=manifest.get("kind"), version=manifest.get("version"),
                                          actor=actor, op_id=op_id, installed_version=str(ipub["version"]), offered_version=str(new_version))
                    raise PkgError(409, "version %s is lower than the installed %s; pass replace=1 and downgrade=1 to go back on purpose"
                                   % (new_version, ipub["version"]))
            backup = os.path.join(quarantine, "prev")
            os.rename(final, backup)
        try:
            os.rename(stage, final)                     # X-7: one rename, same filesystem
        except OSError as e:
            if backup:
                os.rename(backup, final)
            raise PkgError(500, "could not place the app folder: %s" % (e,))
    modules_events.append(home, "app.imported", mid, kind=manifest.get("kind"), version=manifest.get("version"),
                          department_ref=(manifest.get("department") or {}).get("ref") if isinstance(manifest.get("department"), dict) else None,
                          actor=actor, op_id=op_id, result="ok", sha256=sha256.lower(), replaced=bool(backup),
                          registry=registry, publisher_id=signer["publisher_id"] if signer else None, key_id=signer["key_id"] if signer else None)
    return {"id": mid, "sha256": sha256.lower(), "replaced": bool(backup), "members": [m[1] for m in members],
            "verified": bool(signer), "publisher_id": signer["publisher_id"] if signer else None,
            "key_id": signer["key_id"] if signer else None, "version": new_version}


# ---------------------------------------------------------------- install --

def install_app(home, registry_url, mid, version=None, replace=False, downgrade=False, actor="marketplace", fetch=None):
    """Fetch an app from a registry and import it VERIFIED: the index (validated,
    publishers pinned or pinned now on first contact), the entry (newest, or the
    version asked for), the artifact (https only, capped), then import_app with
    the entry. -> the import result plus registry, version, pin_source and the
    publisher fingerprints the install trusted."""
    fetch = fetch or modules_registry.fetch_bytes
    if not isinstance(registry_url, str) or not registry_url.startswith("https://"):
        raise PkgError(400, "registry must be an https URL")
    try:
        index = modules_registry.load_index(fetch(registry_url, modules_registry.MAX_INDEX_BYTES))
    except modules_registry.RegistryError as e:
        raise PkgError(e.status, "registry index: %s" % e)
    except (OSError, ValueError) as e:
        raise PkgError(502, "could not fetch the registry index: %s" % (e.__class__.__name__,))
    entry = modules_registry.entry_for(index, mid, version)
    if not entry:
        raise PkgError(404, "the registry has no app %r%s" % (mid, (" at version " + str(version)) if version else ""))
    pins, meta = modules_registry.trusted_publishers(registry_url, index)
    url = entry.get("artifact_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise PkgError(400, "artifact_url must be an https URL")
    try:
        blob = fetch(url, MAX_TOTAL)
    except (OSError, ValueError) as e:
        raise PkgError(502, "could not fetch the artifact: %s" % (e.__class__.__name__,))
    res = import_app(home, mid, blob, str(entry.get("sha256") or ""), replace=replace, actor=actor, registry=registry_url,
                     entry=entry, publishers=pins, downgrade=downgrade)
    res.update({"registry": registry_url, "version": entry["version"], "pin_source": meta["source"], "fingerprints": meta["fingerprints"]})
    return res
