#!/usr/bin/env python3
"""test_root_invariant.py — ONE ACTIVE ROOT PER REGISTRY (I-D6, founder direction D76, 2026-09-12).

The incident: the desktop's startup import minted a second parent-less domain named after the macOS account, next
to the organisation root, with the machine's project folders duplicated under it. The engine already treats a second
parent-less root as damage at every publish surface (test_phase0 test_14); this suite pins the rule at the WRITE
boundary so the damage cannot be created through the engine at all:

  - mint_domain(None, <any name>, <any tenant>) on a registry that already has an active parent-less domain returns
    that root (created=False) and appends a `root_reused` row to domains/INDEX.jsonl;
  - set_domain_fields(ref, parent_ref=None) is refused while another active root exists;
  - unretire() of a retired parent-less domain is refused while another active root exists.

Harness as in test_phase0: a throwaway SUTRA_NATIVE_HOME per test and importlib.reload of the engine.
Stdlib unittest only. Python 3.9."""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

_LIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

FORBIDDEN = os.path.realpath(os.path.expanduser("~/.sutra-native"))


class RootInvariantCase(unittest.TestCase):
    def setUp(self):
        self._env_backup = dict(os.environ)
        self.home = os.path.realpath(tempfile.mkdtemp(prefix="sutra-root-inv-"))
        os.environ["SUTRA_NATIVE_HOME"] = self.home
        os.environ["PLACEMENT_TENANT"] = "T-local"
        import placement_engine
        self.E = importlib.reload(placement_engine)
        for p in (self.E.HOME, self.E.DOMAINS, self.E.CHARTERS, self.E.PLACEMENTS):
            self.assertFalse(os.path.realpath(p).startswith(FORBIDDEN), "engine escaped the sandbox: %s" % p)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.clear()
        os.environ.update(self._env_backup)

    def _index_events(self):
        rows = []
        with open(self.E.DOMAIN_INDEX) as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        return rows

    def _active_roots(self):
        return [r for r, d in self.E.load_domains().items()
                if d.get("parent_ref") is None and d.get("status", "active") == "active"]

    def test_a_second_parentless_mint_returns_the_existing_root(self):
        E = self.E
        root, created = E.mint_domain(None, "Sutra", ["root"], "T-local", origin="operator")
        self.assertTrue(created)
        again, created2 = E.mint_domain(None, "Ramesh Asawa", ["root"], "T-local", origin="project-import")
        self.assertEqual(again, root)
        self.assertFalse(created2)
        other_tenant, created3 = E.mint_domain(None, "Acme Holdings", ["holdings"], "T-fixture", origin="operator")
        self.assertEqual(other_tenant, root, "tenant labels do not buy a second root: one registry, one root")
        self.assertFalse(created3)
        self.assertEqual(self._active_roots(), [root])
        reused = [r for r in self._index_events() if r.get("event") == "root_reused"]
        self.assertEqual(len(reused), 2)
        self.assertEqual({r["requested_name"] for r in reused}, {"Ramesh Asawa", "Acme Holdings"})
        self.assertEqual(E.load_domains()[root]["name"], "Sutra", "the existing root keeps its own name")

    def test_an_empty_registry_still_gets_its_first_root(self):
        E = self.E
        root, created = E.mint_domain(None, "Sutra", ["root"], "T-local", origin="operator")
        self.assertTrue(created)
        self.assertEqual(self._active_roots(), [root])
        self.assertEqual(E._root_ref("T-local"), root)

    def test_set_domain_fields_cannot_lift_a_node_to_root(self):
        E = self.E
        root, _ = E.mint_domain(None, "Sutra", ["root"], "T-local", origin="operator")
        child, _ = E.mint_domain(root, "Desktop", ["desktop"], "T-local", origin="operator")
        with self.assertRaises(ValueError):
            E.set_domain_fields(child, parent_ref=None)
        self.assertEqual(E.load_domains()[child]["parent_ref"], root)
        self.assertEqual(self._active_roots(), [root])

    def test_unretire_cannot_resurrect_a_second_root(self):
        E = self.E
        # damage fixture: a retired parent-less record written directly, as a recovered registry might carry
        root, _ = E.mint_domain(None, "Sutra", ["root"], "T-local", origin="operator")
        stale = {"ref": "dref-stale0000000001", "name": "Ramesh Asawa", "parent_ref": None, "origin": "project-import",
                 "status": "retired", "successor_refs": [root], "retire_reason_code": "merged", "tenant_id": "T-local",
                 "mint_evidence": ["fixture"], "ts_minted_ms": 1, "retired_at_ms": 2, "principles": [],
                 "accountable": "tenant_owner", "authority": {}}
        with open(os.path.join(E.DOMAINS, stale["ref"] + ".json"), "w") as fh:
            json.dump(stale, fh)
        manifest = os.path.join(self.home, "retire-stale.json")
        with open(manifest, "w") as fh:
            json.dump({"kind": "retire-manifest", "version": 1, "ref": stale["ref"], "reorg_id": "fixture",
                       "ts_ms": 2, "tenant_id": "T-local", "successor_ref": root, "reason_code": "merged",
                       "note": None, "prior_domain": dict(stale, status="active"), "charters": [],
                       "placements": [], "children": []}, fh)
        res = E.unretire(stale["ref"], manifest)
        self.assertFalse(res.get("ok"), res)
        self.assertEqual(self._active_roots(), [root])
        self.assertEqual(E.load_domains()[stale["ref"]]["status"], "retired")


if __name__ == "__main__":
    unittest.main()
