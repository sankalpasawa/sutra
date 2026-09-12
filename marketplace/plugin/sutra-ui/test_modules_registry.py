"""test_modules_registry.py -- the Apps registry index (ADR-039; Publish program P1).

Validation refuses what the trust boundary must never accept (http URLs, a
network permission, a signed entry with no publisher, a publisher whose key_id
does not match its key); add_entry replaces the same id+version and sorts;
entry_for picks the newest semver; verdict follows APPS-LIFECYCLE; pins come
from registries.json for the default registry, from the pinned file for a
known one, and by TOFU on first contact; the shipped index and fixture validate.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

UI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, UI)
os.environ["SUTRA_UI_KEYS"] = tempfile.mkdtemp(prefix="reg-keys-")
os.environ["SUTRA_UI_PINNED"] = os.path.join(tempfile.mkdtemp(prefix="reg-pins-"), "pinned.json")
import modules_registry as R  # noqa: E402
import modules_sign as S  # noqa: E402

ENTRY = {"id": "loan-book-brief", "name": "Loan book brief", "version": "1.0.0", "manifest_schema": 2,
         "artifact_url": "https://sankalpasawa.github.io/sutra/apps/artifacts/loan-book-brief-1.0.0.tgz",
         "sha256": "3dec147953aa77ba305296e3a321f3fe589ab082442dd36ce8b88cf1a082dbee",
         "published_at": "2026-09-12T15:00:00Z", "sutra_version_range": {"min": "2.265.16", "max": None},
         "kinds": ["page"], "publisher_id": "sutra"}


def _index(apps=None, publishers=None, **extra):
    doc = {"registry_schema": 1, "name": "Test registry", "updated_at": "2026-09-12T15:00:00Z", "apps": apps or []}
    if publishers is not None:
        doc["publishers"] = publishers
    doc.update(extra)
    return doc


class Registry(unittest.TestCase):

    def test_shipped_index_fixture_and_registries_validate(self):
        site = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(UI))), "website", "apps", "registry.json")
        for path in (site, os.path.join(UI, "schemas", "fixtures", "apps-registry.example.json")):
            with open(path, encoding="utf-8") as fh:
                doc = R.load_index(fh.read())
            self.assertEqual(doc["registry_schema"], 1, path)
        regs = R.shipped_registries()
        self.assertTrue(regs, "registries.json ships at least one registry")
        d = R.default_registry()
        self.assertEqual(d["url"], "https://sankalpasawa.github.io/sutra/apps/registry.json")
        self.assertTrue(d["publishers"], "the default registry pins its publisher")
        for p in d["publishers"]:
            self.assertEqual(S.key_id(S.pub_from_b64(p["pubkey"])), p["key_id"])
        with open(site, encoding="utf-8") as fh:
            live = json.load(fh)
        self.assertEqual({p["key_id"] for p in live["publishers"]}, {p["key_id"] for p in d["publishers"]},
                         "the shipped pin and the hosted index name the same publisher key")

    def test_validate_refuses_what_the_boundary_must_never_accept(self):
        R.validate_index(_index([ENTRY]))
        cases = [
            ("http url", dict(ENTRY, artifact_url="http://example.invalid/a.tgz")),
            ("network", dict(ENTRY, permissions={"network": True})),
            ("bad sha", dict(ENTRY, sha256="zz")),
            ("bad version", dict(ENTRY, version="1.0")),
            ("bad kinds", dict(ENTRY, kinds=["widget"])),
            ("schema 3", dict(ENTRY, manifest_schema=3)),
            ("signed, no publisher", dict({k: v for k, v in ENTRY.items() if k != "publisher_id"}, signature={"alg": "ed25519", "value": "AA==", "key_id": "0" * 16})),
            ("sys id", dict(ENTRY, id="sys-home")),
        ]
        for name, bad in cases:
            with self.assertRaises(R.RegistryError, msg=name):
                R.validate_index(_index([bad]))
        with self.assertRaises(R.RegistryError):
            R.validate_index(_index([ENTRY, dict(ENTRY)]))            # the same id+version twice
        with self.assertRaises(R.RegistryError):
            R.validate_index(_index(publishers=[{"publisher_id": "x", "key_id": "0" * 16, "pubkey": S.pub_b64(b"\1" * 32), "added_at": "2026-09-12T15:00:00Z"}]))
        with self.assertRaises(R.RegistryError):
            R.load_index(b"{" * 10)
        with self.assertRaises(R.RegistryError):
            R.load_index(b"x" * (R.MAX_INDEX_BYTES + 1))

    def test_add_entry_replaces_same_version_sorts_and_stamps_updated_at(self):
        idx = _index([ENTRY])
        newer = dict(ENTRY, version="1.1.0", published_at="2026-09-13T09:00:00Z")
        other = dict(ENTRY, id="balance-shortcut", kinds=["link"])
        out = R.add_entry(R.add_entry(R.add_entry(idx, newer, now="2026-09-13T09:00:00Z"), other), dict(ENTRY, name="Renamed"))
        self.assertEqual([(e["id"], e["version"]) for e in out["apps"]],
                         [("balance-shortcut", "1.0.0"), ("loan-book-brief", "1.0.0"), ("loan-book-brief", "1.1.0")])
        self.assertEqual(R.entry_for(out, "loan-book-brief")["version"], "1.1.0")
        self.assertEqual(R.entry_for(out, "loan-book-brief", "1.0.0")["name"], "Renamed")
        self.assertIsNone(R.entry_for(out, "nope"))
        self.assertNotEqual(out["updated_at"], idx["updated_at"])

    def test_semver_and_ranges(self):
        self.assertGreater(R.compare("1.10.0", "1.9.9"), 0)
        self.assertLess(R.compare("1.0.0-rc.1", "1.0.0"), 0)
        self.assertTrue(R.in_range("2.265.16", {"min": "2.265.16", "max": None}))
        self.assertTrue(R.in_range("2.270.0", {"min": "2.265.0", "max": "2.270.0"}))
        self.assertFalse(R.in_range("2.271.0", {"min": "2.265.0", "max": "2.270.0"}))
        self.assertFalse(R.in_range("2.264.9", {"min": "2.265.0"}))
        self.assertFalse(R.in_range("2.265.0", {}))

    def test_verdict_follows_the_lifecycle(self):
        installed = {"publish": {"state": "imported", "version": "1.0.0", "published_at": "2026-09-12T15:00:00Z"}}
        self.assertEqual(R.verdict(installed, ENTRY, "2.265.16"), "current")
        self.assertEqual(R.verdict(installed, dict(ENTRY, version="1.0.1"), "2.265.16"), "update_available")
        self.assertEqual(R.verdict(installed, dict(ENTRY, published_at="2026-09-13T00:00:00Z"), "2.265.16"), "update_available")
        self.assertEqual(R.verdict(installed, dict(ENTRY, version="9.0.0", sutra_version_range={"min": "9.0.0"}), "2.265.16"), "incompatible")
        self.assertEqual(R.verdict({"publish": {"state": "imported"}}, ENTRY, "2.265.16"), "update_available")

    def test_pins_shipped_pinned_and_tofu(self):
        kid, priv, pub = S.generate()
        pubs = [{"publisher_id": "acme", "key_id": kid, "pubkey": S.pub_b64(pub), "added_at": "2026-09-12T15:00:00Z"}]
        idx = _index([], publishers=pubs)
        d = R.default_registry()
        pins, meta = R.trusted_publishers(d["url"], idx)
        self.assertEqual(meta["source"], "shipped")
        self.assertNotIn(kid, pins, "the index's own list never widens the shipped pins")
        pins, meta = R.trusted_publishers("https://acme.invalid/registry.json", idx)
        self.assertEqual(meta["source"], "tofu")
        self.assertEqual(meta["fingerprints"], [kid])
        self.assertEqual(pins[kid]["publisher_id"], "acme")
        other = _index([], publishers=[{"publisher_id": "acme", "key_id": S.generate()[0], "pubkey": S.pub_b64(S.generate()[2]), "added_at": "2026-09-12T15:00:00Z"}])
        pins, meta = R.trusted_publishers("https://acme.invalid/registry.json", other)
        self.assertEqual(meta["source"], "pinned")
        self.assertEqual(sorted(pins), [kid], "a later index cannot swap the pinned key")
        # a rotation signed by the pinned key adds the new one
        nkid, npriv, npub = S.generate()
        rot = {"publisher_id": "acme", "old_key_id": kid, "new_key_id": nkid, "new_pubkey": S.pub_b64(npub), "created_at": "2026-09-13T00:00:00Z"}
        import base64
        rot["signature"] = base64.b64encode(S.sign(priv, S.rotation_payload(rot))).decode()
        pins, meta = R.trusted_publishers("https://acme.invalid/registry.json", _index([], publishers=pubs, rotations=[rot]))
        self.assertEqual(sorted(pins), sorted([kid, nkid]))
        pins, _m = R.trusted_publishers("https://nobody.invalid/r.json", _index([]), pin_on_first_use=False)
        self.assertEqual(pins, {})

    def test_cli_check_and_add(self):
        d = tempfile.mkdtemp(prefix="reg-cli-")
        ip, ep = os.path.join(d, "index.json"), os.path.join(d, "entry.json")
        json.dump(_index([]), open(ip, "w"))
        json.dump(ENTRY, open(ep, "w"))
        r = subprocess.run([sys.executable, os.path.join(UI, "modules_registry.py"), "add", ip, ep], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, os.path.join(UI, "modules_registry.py"), "check", ip], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 app(s)", r.stdout)
        json.dump(dict(ENTRY, artifact_url="http://x.invalid/a.tgz"), open(ep, "w"))
        r = subprocess.run([sys.executable, os.path.join(UI, "modules_registry.py"), "add", ip, ep], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("https", r.stderr)


if __name__ == "__main__":
    unittest.main()
