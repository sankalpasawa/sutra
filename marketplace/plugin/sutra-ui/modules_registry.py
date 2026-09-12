"""modules_registry.py -- the Apps registry index (ADR-039; Publish program Q-1).

An index is static JSON (schemas/apps-registry.schema.json, registry_schema 1).
The default one lives in the sutra repo at website/apps/registry.json and is
served by GitHub Pages at https://sankalpasawa.github.io/sutra/apps/registry.json;
the plugin pins that URL and its publisher keys in registries.json beside this
file, and pins any other registry's publishers on first install (TOFU) into
~/.sutra-ui/registries-pinned.json ($SUTRA_UI_PINNED).

    python3 modules_registry.py check <index.json>
    python3 modules_registry.py add <index.json> <entry.json>   # same id+version replaced; sorted; updated_at now

Verdicts for an installed app against an entry: update_available (a newer
version, or the same version published later, inside a compatible
sutra_version_range), incompatible (the range excludes this plugin), current.
Everything here is a read: no manifest and no event is written by this module
(APPS-LIFECYCLE: no state is entered by a read; ruling P-7).
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import modules_sign  # noqa: E402

REGISTRY_SCHEMA = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_RE = re.compile(r"^[0-9a-f]{16}$")
KINDS = ("chat", "page", "link")
ENTRY_REQUIRED = ("id", "name", "version", "manifest_schema", "artifact_url", "sha256", "published_at", "sutra_version_range", "kinds")
SCHEMA_PATH = os.path.join(HERE, "schemas", "apps-registry.schema.json")
REGISTRIES_PATH = os.path.join(HERE, "registries.json")
PINNED_ENV = "SUTRA_UI_PINNED"
MAX_INDEX_BYTES = 1024 * 1024


class RegistryError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _iso(s, what):
    try:
        datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise RegistryError(400, "%s is not an ISO date-time" % what)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- semver + ranges -----------------------------------------------------------

def semver_key(v):
    """Sortable key: a pre-release sorts below its release."""
    core, _, pre = str(v).partition("-")
    nums = tuple(int(p) for p in core.split("."))
    return (nums, 1 if not pre else 0, pre)


def compare(a, b):
    ka, kb = semver_key(a), semver_key(b)
    return (ka > kb) - (ka < kb)


def in_range(version, rng):
    """min <= version <= max (max null = open)."""
    if not isinstance(rng, dict) or not rng.get("min"):
        return False
    try:
        if compare(version, rng["min"]) < 0:
            return False
        return rng.get("max") is None or compare(version, rng["max"]) <= 0
    except (ValueError, AttributeError):
        return False


def plugin_version():
    """The core plugin version this panel ships with (marketplace/plugin/.claude-plugin/plugin.json)."""
    path = os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "0.0.0")
    except (OSError, ValueError):
        return "0.0.0"


# ---- validation ----------------------------------------------------------------

def _validate_entry(e, i):
    tag = "apps[%d]" % i
    if not isinstance(e, dict):
        raise RegistryError(400, tag + " is not an object")
    for k in ENTRY_REQUIRED:
        if k not in e:
            raise RegistryError(400, "%s lacks %s" % (tag, k))
    if not isinstance(e["id"], str) or not ID_RE.match(e["id"]) or e["id"].startswith("sys-"):
        raise RegistryError(400, tag + " id is not a valid app id")
    if not isinstance(e["name"], str) or not e["name"].strip():
        raise RegistryError(400, tag + " name is empty")
    if not isinstance(e["version"], str) or not SEMVER_RE.match(e["version"]):
        raise RegistryError(400, tag + " version is not semver")
    if e["manifest_schema"] != 2:
        raise RegistryError(400, tag + " manifest_schema must be 2")
    if not isinstance(e["artifact_url"], str) or not e["artifact_url"].startswith("https://"):
        raise RegistryError(400, tag + " artifact_url must be an https URL")
    if not isinstance(e["sha256"], str) or not SHA_RE.match(e["sha256"]):
        raise RegistryError(400, tag + " sha256 is not 64 hex")
    _iso(e["published_at"], tag + " published_at")
    rng = e["sutra_version_range"]
    if not isinstance(rng, dict) or not isinstance(rng.get("min"), str) or not SEMVER_RE.match(rng["min"]):
        raise RegistryError(400, tag + " sutra_version_range.min is not semver")
    if rng.get("max") is not None and (not isinstance(rng["max"], str) or not SEMVER_RE.match(rng["max"])):
        raise RegistryError(400, tag + " sutra_version_range.max is not semver or null")
    kinds = e["kinds"]
    if not isinstance(kinds, list) or not kinds or any(k not in KINDS for k in kinds):
        raise RegistryError(400, tag + " kinds must name chat, page or link")
    perms = e.get("permissions")
    if isinstance(perms, dict) and perms.get("network") is True:
        raise RegistryError(400, tag + " permissions.network true is not accepted (D-M5)")
    sig = e.get("signature")
    if sig is not None:
        if not isinstance(sig, dict) or sig.get("alg") != modules_sign.ALG or not isinstance(sig.get("value"), str) \
                or not isinstance(sig.get("key_id"), str) or not KEY_RE.match(sig["key_id"]):
            raise RegistryError(400, tag + " signature must carry alg ed25519, a base64 value and a 16-hex key_id")
        if not isinstance(e.get("publisher_id"), str) or not e["publisher_id"].strip():
            raise RegistryError(400, tag + " is signed but names no publisher_id")


def _validate_publisher(p, i):
    tag = "publishers[%d]" % i
    if not isinstance(p, dict):
        raise RegistryError(400, tag + " is not an object")
    for k in ("publisher_id", "key_id", "pubkey", "added_at"):
        if not isinstance(p.get(k), str) or not p[k].strip():
            raise RegistryError(400, "%s lacks %s" % (tag, k))
    if not KEY_RE.match(p["key_id"]):
        raise RegistryError(400, tag + " key_id is not 16 hex")
    try:
        raw = modules_sign.pub_from_b64(p["pubkey"])
    except modules_sign.SignError as e:
        raise RegistryError(400, "%s pubkey: %s" % (tag, e))
    if modules_sign.key_id(raw) != p["key_id"]:
        raise RegistryError(400, tag + " key_id does not match its pubkey")
    _iso(p["added_at"], tag + " added_at")


def validate_index(doc):
    """The JSON Schema when importable, PLUS the explicit checks the trust
    boundary needs regardless (the modules_pkg.validate_manifest pattern)."""
    if not isinstance(doc, dict):
        raise RegistryError(400, "index is not an object")
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        try:
            jsonschema.validate(doc, schema)
        except jsonschema.ValidationError as e:
            raise RegistryError(400, "index fails the schema: %s" % e.message)
    except ImportError:
        pass
    if doc.get("registry_schema") != REGISTRY_SCHEMA:
        raise RegistryError(400, "registry_schema must be %d" % REGISTRY_SCHEMA)
    if not isinstance(doc.get("name"), str) or not doc["name"].strip():
        raise RegistryError(400, "index name is empty")
    _iso(doc.get("updated_at"), "updated_at")
    apps = doc.get("apps")
    if not isinstance(apps, list):
        raise RegistryError(400, "apps must be a list")
    seen = set()
    for i, e in enumerate(apps):
        _validate_entry(e, i)
        key = (e["id"], e["version"])
        if key in seen:
            raise RegistryError(400, "apps[%d] repeats %s %s" % (i, e["id"], e["version"]))
        seen.add(key)
    pubs = doc.get("publishers")
    if pubs is not None:
        if not isinstance(pubs, list):
            raise RegistryError(400, "publishers must be a list")
        for i, p in enumerate(pubs):
            _validate_publisher(p, i)
    rots = doc.get("rotations")
    if rots is not None and (not isinstance(rots, list) or any(not isinstance(r, dict) for r in rots)):
        raise RegistryError(400, "rotations must be a list of objects")
    return doc


def load_index(data):
    """bytes or str -> validated index dict. Caps the size before parsing."""
    if isinstance(data, (bytes, bytearray)):
        if len(data) > MAX_INDEX_BYTES:
            raise RegistryError(413, "index exceeds the 1 MB cap")
        try:
            data = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            raise RegistryError(400, "index is not UTF-8")
    try:
        doc = json.loads(data)
    except ValueError as e:
        raise RegistryError(400, "index is not valid JSON: %s" % e)
    return validate_index(doc)


# ---- the index as data ---------------------------------------------------------

def publishers_of(index):
    """-> {key_id: {"pubkey": raw, "publisher_id"}} from the index's own list (untrusted until pinned)."""
    out = {}
    for p in index.get("publishers") or []:
        try:
            out[p["key_id"]] = {"pubkey": modules_sign.pub_from_b64(p["pubkey"]), "publisher_id": p["publisher_id"]}
        except (KeyError, TypeError, modules_sign.SignError):
            continue
    return out


def entry_for(index, app_id, version=None):
    """The newest entry for an id (by semver), or the exact version, or None."""
    cands = [e for e in index.get("apps") or [] if e.get("id") == app_id and (version is None or e.get("version") == version)]
    if not cands:
        return None
    return max(cands, key=lambda e: semver_key(e["version"]))


def add_entry(index, entry, now=None):
    """-> the index with the entry in place (same id+version replaced), apps
    sorted by id then semver, updated_at set. Validates the result."""
    apps = [e for e in index.get("apps") or [] if not (e.get("id") == entry.get("id") and e.get("version") == entry.get("version"))]
    apps.append(entry)
    apps.sort(key=lambda e: (str(e.get("id")), semver_key(e.get("version") or "0.0.0")))
    out = dict(index, apps=apps, updated_at=now or _now())
    return validate_index(out)


def verdict(installed_manifest, entry, plugin_ver=None):
    """-> update_available | incompatible | current (for an app the entry describes)."""
    pv = plugin_ver or plugin_version()
    if not in_range(pv, entry.get("sutra_version_range")):
        return "incompatible"
    pub = installed_manifest.get("publish") if isinstance(installed_manifest, dict) and isinstance(installed_manifest.get("publish"), dict) else {}
    iv = pub.get("version")
    try:
        if iv and compare(entry["version"], iv) > 0:
            return "update_available"
        if iv and compare(entry["version"], iv) == 0 and pub.get("published_at") and str(entry.get("published_at")) > str(pub["published_at"]):
            return "update_available"
    except (ValueError, AttributeError):
        return "current"
    if not iv:
        return "update_available"          # installed before entries carried a version: the registry's is newer by definition
    return "current"


# ---- pins ----------------------------------------------------------------------

def shipped_registries():
    """registries.json beside this file: [{name, url, default, publishers: [...]}]."""
    try:
        with open(REGISTRIES_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return []
    regs = doc.get("registries") if isinstance(doc, dict) else None
    return [r for r in (regs or []) if isinstance(r, dict) and isinstance(r.get("url"), str)]


def default_registry():
    for r in shipped_registries():
        if r.get("default"):
            return r
    return None


def pinned_path():
    return os.path.realpath(os.path.expanduser(os.environ.get(PINNED_ENV) or "~/.sutra-ui/registries-pinned.json"))


def read_pins():
    try:
        with open(pinned_path(), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def write_pins(doc):
    path = pinned_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _pins_to_map(pubs):
    out = {}
    for p in pubs or []:
        try:
            out[p["key_id"]] = {"pubkey": modules_sign.pub_from_b64(p["pubkey"]), "publisher_id": p["publisher_id"]}
        except (KeyError, TypeError, modules_sign.SignError):
            continue
    return out


def trusted_publishers(url, index, pin_on_first_use=True):
    """The keys an install from `url` may trust: the shipped pins for the
    default registry (the index's own list never widens them; a valid
    rotation signed by a pinned key does), the pinned file for any other,
    or -- first contact -- the index's publishers, pinned now (TOFU).
    -> (map, {"source": shipped|pinned|tofu, "fingerprints": [key_id...]})."""
    for r in shipped_registries():
        if r.get("url") == url:
            pins = _pins_to_map(r.get("publishers"))
            source = "shipped"
            break
    else:
        rec = read_pins().get(url)
        if isinstance(rec, dict) and rec.get("publishers"):
            pins, source = _pins_to_map(rec["publishers"]), "pinned"
        elif pin_on_first_use:
            pubs = [p for p in (index.get("publishers") or []) if isinstance(p, dict)]
            pins, source = _pins_to_map(pubs), "tofu"
            if pins:
                doc = read_pins()
                doc[url] = {"publishers": pubs, "pinned_at": _now()}
                write_pins(doc)
        else:
            pins, source = {}, "none"
    for rot in index.get("rotations") or []:
        ok, _why, new_pin = modules_sign.verify_rotation(rot, pins)
        if ok:
            pins[str(rot["new_key_id"])] = new_pin
    return pins, {"source": source, "fingerprints": sorted(pins)}


# ---- fetch ----------------------------------------------------------------------

def fetch_bytes(url, cap, timeout=10.0):
    """GET an https URL, at most `cap` bytes, no redirects (a registry that moves
    changes its pinned URL on purpose; a redirect could send the fetch off-host).
    Raises ValueError on a non-https URL, a redirect, or a body over the cap;
    OSError (urllib's) on network failure."""
    import urllib.error
    import urllib.request
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("only https URLs are fetched")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("redirect refused (%s -> %s)" % (url, newurl))

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "sutra-desktop-apps/1", "Accept": "application/json, application/gzip, */*"})
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read(cap + 1)
    if len(data) > cap:
        raise ValueError("response exceeds the %d byte cap" % cap)
    return data


# ---- CLI -----------------------------------------------------------------------

def main(argv):
    if len(argv) >= 2 and argv[0] == "check":
        with open(argv[1], encoding="utf-8") as fh:
            doc = load_index(fh.read())
        print("ok: %d app(s), %d publisher(s), registry_schema %d" % (len(doc["apps"]), len(doc.get("publishers") or []), doc["registry_schema"]))
        return 0
    if len(argv) >= 3 and argv[0] == "add":
        with open(argv[1], encoding="utf-8") as fh:
            index = load_index(fh.read())
        with open(argv[2], encoding="utf-8") as fh:
            entry = json.load(fh)
        out = add_entry(index, entry)
        with open(argv[1], "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("added %s %s; %d app(s)" % (entry.get("id"), entry.get("version"), len(out["apps"])))
        return 0
    print("usage: modules_registry.py check <index.json> | add <index.json> <entry.json>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RegistryError as e:
        print("refused: %s" % e, file=sys.stderr)
        sys.exit(1)
