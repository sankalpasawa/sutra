"""test_modules_sign.py -- ed25519 signing of registry entries (ADR-041; Publish program P2).

The library is cryptography (ruling P-1). These tests pin the wrapper to RFC
8032 section 7.1 vectors (so the key, payload and signature bytes are the
standard's, not merely self-consistent), then the entry contract: a signed entry
verifies, every signed field is bound (tamper matrix), an unsigned or wrongly
keyed entry is refused with a reason, key files land 0600, rotations verify
only from a pinned old key.
"""
import base64
import json
import os
import stat
import sys
import tempfile
import unittest

UI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, UI)
os.environ["SUTRA_UI_KEYS"] = tempfile.mkdtemp(prefix="sign-keys-")
import modules_sign as S  # noqa: E402

RFC = [  # (secret seed, public key, message, signature) -- RFC 8032 section 7.1
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]

ENTRY = {"id": "loan-book-brief", "name": "Loan book brief", "version": "1.0.0", "manifest_schema": 2,
         "artifact_url": "https://sankalpasawa.github.io/sutra/apps/artifacts/loan-book-brief-1.0.0.tgz",
         "sha256": "3dec147953aa77ba305296e3a321f3fe589ab082442dd36ce8b88cf1a082dbee",
         "published_at": "2026-09-12T15:00:00Z", "sutra_version_range": {"min": "2.265.16", "max": None},
         "kinds": ["page"], "publisher_id": "sutra"}


@unittest.skipUnless(S.available(), "cryptography is not importable here (the DMG carries it)")
class Sign(unittest.TestCase):

    def test_rfc_8032_vectors(self):
        for seed, pub, msg, sig in RFC:
            priv = bytes.fromhex(seed)
            self.assertEqual(S.public_key_of(priv).hex(), pub)
            self.assertEqual(S.sign(priv, bytes.fromhex(msg)).hex(), sig)
            self.assertTrue(S.verify(bytes.fromhex(pub), bytes.fromhex(msg), bytes.fromhex(sig)))
            self.assertFalse(S.verify(bytes.fromhex(pub), bytes.fromhex(msg) + b"x", bytes.fromhex(sig)))

    def test_canonical_payload_is_sorted_compact_and_maps_entry_fields(self):
        p = S.payload_from_entry(ENTRY)
        self.assertEqual(json.loads(p), {"publisher_id": "sutra", "app_id": "loan-book-brief", "version": "1.0.0", "manifest_schema": 2,
                                         "artifact_sha256": ENTRY["sha256"], "sutra_version_range": {"min": "2.265.16", "max": None}})
        self.assertEqual(p, json.dumps(json.loads(p), sort_keys=True, separators=(",", ":")).encode())
        self.assertNotIn(b"artifact_url", p, "the URL is not signed (ruling P-2)")
        with self.assertRaises(S.SignError):
            S.payload_from_entry(dict(ENTRY, sha256=None) and {k: v for k, v in ENTRY.items() if k != "sha256"})

    def test_sign_entry_then_verify_entry_and_the_tamper_matrix(self):
        kid, priv, pub = S.generate()
        pins = {kid: {"pubkey": pub, "publisher_id": "sutra"}}
        signed = S.sign_entry(ENTRY, priv)
        self.assertEqual(signed["signature"]["alg"], "ed25519")
        self.assertEqual(signed["signature"]["key_id"], kid)
        self.assertEqual(len(base64.b64decode(signed["signature"]["value"])), 64)
        ok, why = S.verify_entry(signed, pins)
        self.assertTrue(ok, why)
        for field, bad in (("id", "other-app"), ("version", "1.0.1"), ("manifest_schema", 3), ("sha256", "0" * 64),
                           ("sutra_version_range", {"min": "1.0.0", "max": None}), ("publisher_id", "someone")):
            t = dict(signed, **{field: bad})
            ok, why = S.verify_entry(t, pins)
            self.assertFalse(ok, field)
        t = dict(signed, artifact_url="https://elsewhere.invalid/x.tgz")
        self.assertTrue(S.verify_entry(t, pins)[0], "the URL may move without breaking the signature")

    def test_verify_entry_refuses_unsigned_unknown_key_and_bad_bytes_with_reasons(self):
        kid, priv, pub = S.generate()
        pins = {kid: {"pubkey": pub, "publisher_id": "sutra"}}
        self.assertEqual(S.verify_entry(ENTRY, pins), (False, "the entry is unsigned"))
        signed = S.sign_entry(ENTRY, priv)
        self.assertIn("not a pinned", S.verify_entry(signed, {})[1])
        other_kid, _p, other_pub = S.generate()
        self.assertIn("not a pinned", S.verify_entry(signed, {other_kid: {"pubkey": other_pub, "publisher_id": "sutra"}})[1])
        self.assertIn("another publisher", S.verify_entry(signed, {kid: {"pubkey": pub, "publisher_id": "not-sutra"}})[1].replace("the key belongs to publisher", "another publisher"))
        bad = dict(signed, signature=dict(signed["signature"], value="AAAA"))
        self.assertFalse(S.verify_entry(bad, pins)[0])
        bad = dict(signed, signature=dict(signed["signature"], alg="rsa"))
        self.assertIn("algorithm", S.verify_entry(bad, pins)[1])

    def test_key_files_are_0600_and_the_machine_has_one_publisher(self):
        d = tempfile.mkdtemp(prefix="sign-home-")
        ident = S.ensure_publisher("sutra", d)
        self.assertEqual(set(ident), {"publisher_id", "key_id", "pubkey"})
        path = os.path.join(d, ident["key_id"] + ".ed25519")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(S.key_id(S.pub_from_b64(ident["pubkey"])), ident["key_id"])
        priv = S.load_private(ident["key_id"], d)
        self.assertEqual(S.public_key_of(priv), S.pub_from_b64(ident["pubkey"]))
        self.assertEqual(S.ensure_publisher("sutra", d), ident, "a second call returns the same identity")
        self.assertEqual(S.publisher(d), ident)

    def test_rotation_verifies_only_from_a_pinned_old_key(self):
        old_kid, old_priv, old_pub = S.generate()
        new_kid, new_priv, new_pub = S.generate()
        rot = {"publisher_id": "sutra", "old_key_id": old_kid, "new_key_id": new_kid, "new_pubkey": S.pub_b64(new_pub), "created_at": "2026-09-12T15:00:00Z"}
        rot["signature"] = base64.b64encode(S.sign(old_priv, S.rotation_payload(rot))).decode()
        pins = {old_kid: {"pubkey": old_pub, "publisher_id": "sutra"}}
        ok, why, pin = S.verify_rotation(rot, pins)
        self.assertTrue(ok, why)
        self.assertEqual(pin, {"pubkey": new_pub, "publisher_id": "sutra"})
        self.assertFalse(S.verify_rotation(rot, {})[0], "old key not pinned")
        forged = dict(rot, new_pubkey=S.pub_b64(S.generate()[2]))
        self.assertFalse(S.verify_rotation(forged, pins)[0])


class WithoutTheLibrary(unittest.TestCase):

    def test_verify_entry_never_passes_when_the_library_is_missing(self):
        have = S._HAVE
        S._HAVE = False
        try:
            ok, why = S.verify_entry(dict(ENTRY, signature={"alg": "ed25519", "value": "AA==", "key_id": "0" * 16}), {})
            self.assertFalse(ok)
            self.assertIn("missing", why)
            with self.assertRaises(S.SignError):
                S.generate()
        finally:
            S._HAVE = have


if __name__ == "__main__":
    unittest.main()
