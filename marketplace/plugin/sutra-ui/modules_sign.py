"""modules_sign.py -- ed25519 signing and verification of Apps registry entries
(ADR-041, Accepted 2026-09-12 by the Publish program; ruling P-1: the
`cryptography` library, never a hand-written curve).

Keys. A publisher's private key is the 32-byte ed25519 seed at
<keys dir>/<key_id>.ed25519 (hex, mode 0600; the keys dir is ~/.sutra-ui/keys
or $SUTRA_UI_KEYS), generated on the first publish and never copied anywhere
by this module. <keys dir>/publisher.json records {publisher_id, key_id,
pubkey} so one machine carries one publisher identity. The public key travels
in the registry index's `publishers` list; the plugin pins the default
registry's keys in registries.json and pins any other registry's publishers on
first install (TOFU).

Payload. ADR-041: the signature covers the canonical JSON (sorted keys, no
spaces) of {publisher_id, app_id, version, manifest_schema, artifact_sha256,
sutra_version_range}, read from the registry entry (`id` -> app_id, `sha256`
-> artifact_sha256; `artifact_url` is not signed, ruling P-2: the digest binds
the bytes and URLs move). key_id = the first 16 hex of sha256(raw public key).
The entry carries signature {alg: "ed25519", value: base64(64 bytes), key_id}.

No fallback. When `cryptography` is missing, available() is False: signing
refuses and modules_pkg refuses every registry install, because an entry
nobody can verify never lands (ruling P-3). The wheel ships in the DMG
(requirements.txt, after wheels-check.sh passed for both macOS arches).
"""
import base64
import hashlib
import json
import os

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    _HAVE = True
except Exception:  # pragma: no cover -- the DMG carries the wheel; a bare venv may not
    _HAVE = False

ALG = "ed25519"
KEYS_ENV = "SUTRA_UI_KEYS"
#: payload field -> registry entry field
ENTRY_TO_PAYLOAD = (("publisher_id", "publisher_id"), ("app_id", "id"), ("version", "version"),
                    ("manifest_schema", "manifest_schema"), ("artifact_sha256", "sha256"),
                    ("sutra_version_range", "sutra_version_range"))
ROTATION_FIELDS = ("publisher_id", "old_key_id", "new_key_id", "new_pubkey", "created_at")


class SignError(ValueError):
    pass


def available():
    return _HAVE


def _need():
    if not _HAVE:
        raise SignError("signing needs the cryptography library (requirements.txt); it is not importable here")


def keys_dir():
    return os.path.realpath(os.path.expanduser(os.environ.get(KEYS_ENV) or "~/.sutra-ui/keys"))


def key_id(pub_raw):
    return hashlib.sha256(bytes(pub_raw)).hexdigest()[:16]


def _canon(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_from_entry(entry):
    """The canonical bytes for a registry entry; SignError names a missing field."""
    if not isinstance(entry, dict):
        raise SignError("entry is not an object")
    doc = {}
    for field, src in ENTRY_TO_PAYLOAD:
        if src not in entry:
            raise SignError("entry lacks the signed field %r" % src)
        doc[field] = entry[src]
    return _canon(doc)


def rotation_payload(rot):
    if not isinstance(rot, dict) or any(f not in rot for f in ROTATION_FIELDS):
        raise SignError("a rotation carries " + ", ".join(ROTATION_FIELDS))
    return _canon({f: rot[f] for f in ROTATION_FIELDS})


# ---- keys --------------------------------------------------------------------

def generate():
    """-> (key_id, priv_raw, pub_raw)."""
    _need()
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key_id(pub), priv, pub


def public_key_of(priv_raw):
    _need()
    k = Ed25519PrivateKey.from_private_bytes(bytes(priv_raw))
    return k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def sign(priv_raw, payload):
    _need()
    return Ed25519PrivateKey.from_private_bytes(bytes(priv_raw)).sign(bytes(payload))


def verify(pub_raw, payload, sig):
    _need()
    try:
        Ed25519PublicKey.from_public_bytes(bytes(pub_raw)).verify(bytes(sig), bytes(payload))
        return True
    except (InvalidSignature, ValueError):
        return False


def pub_b64(pub_raw):
    return base64.b64encode(bytes(pub_raw)).decode("ascii")


def pub_from_b64(s):
    try:
        raw = base64.b64decode(str(s or ""), validate=True)
    except (ValueError, TypeError) as e:
        raise SignError("public key is not base64: %s" % e)
    if len(raw) != 32:
        raise SignError("a public key is 32 bytes")
    return raw


def save_private(priv_raw, pub_raw, publisher_id, directory=None):
    """Write <keys dir>/<key_id>.ed25519 (hex, 0600) and publisher.json; -> key_id."""
    d = directory or keys_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    kid = key_id(pub_raw)
    path = os.path.join(d, kid + ".ed25519")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (bytes(priv_raw).hex() + "\n").encode("ascii"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    with open(os.path.join(d, "publisher.json"), "w", encoding="utf-8") as fh:
        json.dump({"publisher_id": publisher_id, "key_id": kid, "pubkey": pub_b64(pub_raw)}, fh, indent=1)
    return kid


def load_private(kid, directory=None):
    path = os.path.join(directory or keys_dir(), str(kid) + ".ed25519")
    with open(path, encoding="ascii") as fh:
        raw = bytes.fromhex(fh.read().strip())
    if len(raw) != 32:
        raise SignError("private key file is not a 32-byte seed")
    return raw


def publisher(directory=None):
    """This machine's publisher identity {publisher_id, key_id, pubkey}, or None."""
    path = os.path.join(directory or keys_dir(), "publisher.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("key_id") and doc.get("pubkey") else None


def ensure_publisher(publisher_id, directory=None):
    """The machine's identity, generated on first use; -> {publisher_id, key_id, pubkey}."""
    cur = publisher(directory)
    if cur:
        return cur
    kid, priv, pub = generate()
    save_private(priv, pub, publisher_id, directory)
    return {"publisher_id": publisher_id, "key_id": kid, "pubkey": pub_b64(pub)}


# ---- entries -----------------------------------------------------------------

def sign_entry(entry, priv_raw):
    """-> a copy of the entry carrying signature {alg, value, key_id}."""
    pub = public_key_of(priv_raw)
    sig = sign(priv_raw, payload_from_entry(entry))
    out = dict(entry)
    out["signature"] = {"alg": ALG, "value": base64.b64encode(sig).decode("ascii"), "key_id": key_id(pub)}
    return out


def verify_entry(entry, publishers):
    """publishers: {key_id: {"pubkey": raw 32 bytes, "publisher_id": str}}.
    -> (ok, reason). Never raises on a malformed entry; never passes without
    the library (an unverifiable entry is refused, not waved through)."""
    if not _HAVE:
        return False, "signing library missing; the entry cannot be verified"
    sig = entry.get("signature") if isinstance(entry, dict) else None
    if not isinstance(sig, dict):
        return False, "the entry is unsigned"
    if sig.get("alg") != ALG:
        return False, "unknown signature algorithm %r" % (sig.get("alg"),)
    kid = str(sig.get("key_id") or "")
    pin = publishers.get(kid) if isinstance(publishers, dict) else None
    if not isinstance(pin, dict) or not pin.get("pubkey"):
        return False, "key %s is not a pinned publisher key" % (kid or "?")
    pub = bytes(pin["pubkey"])
    if key_id(pub) != kid:
        return False, "the pinned key does not match its key_id"
    if str(entry.get("publisher_id") or "") != str(pin.get("publisher_id") or ""):
        return False, "the key belongs to publisher %r, the entry claims %r" % (pin.get("publisher_id"), entry.get("publisher_id"))
    try:
        raw = base64.b64decode(str(sig.get("value") or ""), validate=True)
        payload = payload_from_entry(entry)
    except (ValueError, TypeError, SignError) as e:
        return False, "malformed signature: %s" % e
    if len(raw) != 64:
        return False, "signature is not 64 bytes"
    if not verify(pub, payload, raw):
        return False, "signature does not verify against the pinned key"
    return True, "signed by %s (%s)" % (pin.get("publisher_id"), kid)


def verify_rotation(rot, publishers):
    """A rotation is accepted only when its old key is pinned and signed it;
    -> (ok, reason, new_pin) with new_pin = {"pubkey": raw, "publisher_id"}."""
    if not _HAVE:
        return False, "signing library missing", None
    try:
        payload = rotation_payload(rot)
        new_pub = pub_from_b64(rot["new_pubkey"])
        raw = base64.b64decode(str(rot.get("signature") or ""), validate=True)
    except (SignError, ValueError, TypeError) as e:
        return False, "malformed rotation: %s" % e, None
    old = publishers.get(str(rot["old_key_id"])) if isinstance(publishers, dict) else None
    if not isinstance(old, dict) or not old.get("pubkey"):
        return False, "rotation from a key that is not pinned", None
    if str(old.get("publisher_id")) != str(rot["publisher_id"]):
        return False, "rotation names another publisher", None
    if key_id(new_pub) != str(rot["new_key_id"]):
        return False, "new_key_id does not match new_pubkey", None
    if len(raw) != 64 or not verify(bytes(old["pubkey"]), payload, raw):
        return False, "rotation signature does not verify against the old key", None
    return True, "rotated %s -> %s" % (rot["old_key_id"], rot["new_key_id"]), {"pubkey": new_pub, "publisher_id": str(rot["publisher_id"])}
