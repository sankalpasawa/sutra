#!/usr/bin/env python3
"""test_publish_gate.py — what a publish is allowed to emit.

PROTO-000: every shipped change carries a test.

Two publish paths existed and did NOT agree with each other:

    build() / build_site()   asserted a single live root, then walked the tree
    export_registry_only()   asserted NOTHING

The second is the FAST LANE -- the one hooks/domains-site-refresh.sh runs on a
drift timer and then commits and pushes to a public GitHub Pages repo, with no
human present. Its only input-set filter was tenant_refs(). So the moment tenant
stops being the filter, the unattended publish surface has no guard at all.

These assertions pin the replacement:
  - the input set is chosen by CONTAINMENT (subtree_refs), not by a label
  - BOTH publish paths refuse a registry with two live roots
  - retired nodes still reach the registry export (the Archive tray depends on it)

Harness: the reload dance test_phase0.py documents -- placement_engine resolves
HOME at import time, so every test mints a fresh tempdir, exports it, and
reloads. _assert_sandboxed() aborts if any path escapes.
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.dirname(HERE)
if LIB not in sys.path:
    sys.path.insert(0, LIB)


class PublishGate(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="publish-gate-")
        os.environ["SUTRA_NATIVE_HOME"] = self.home
        import placement_engine
        self.E = importlib.reload(placement_engine)
        import domains_page
        self.D = importlib.reload(domains_page)
        for p in (self.E.HOME, self.E.DOMAINS):
            self.assertTrue(os.path.abspath(p).startswith(os.path.abspath(self.home)),
                            "engine path %s escaped the sandbox" % p)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("SUTRA_NATIVE_HOME", None)

    def _domain(self, ref, name, parent, **extra):
        doc = {"ref": ref, "name": name, "parent_ref": parent, "status": "active",
               "tenant_id": "T-local", "ts_minted_ms": 1, "principles": [],
               "accountable": "tenant_owner", "authority": {}, "origin": "operator",
               "touched_by_operator": False, "mint_evidence": [name.lower()],
               "successor_refs": [], "retired_at_ms": None,
               "retire_reason_code": None, "retire_note": None,
               "disposition_event_id": None}
        doc.update(extra)
        os.makedirs(self.E.DOMAINS, exist_ok=True)
        with open(os.path.join(self.E.DOMAINS, ref + ".json"), "w") as fh:
            json.dump(doc, fh)
        return doc

    # ---------------------------------------------------------- containment --
    def test_subtree_refs_selects_by_structure_not_by_label(self):
        """The whole point of the replacement: a row belongs to the org because
        it hangs off the root, not because a string on it says so."""
        self._domain("dref-root", "Root", None)
        self._domain("dref-a", "A", "dref-root")
        self._domain("dref-deep", "Deep", "dref-a")
        # a row whose tenant label is WRONG is still part of the tree
        self._domain("dref-mislabelled", "Mislabelled", "dref-a", tenant_id="T-typo")
        # a row NOT under the root is not part of it, whatever its label says
        self._domain("dref-orphan", "Orphan", "dref-nowhere")

        domains = self.E.load_domains()
        got = set(self.E.subtree_refs(domains, "dref-root"))
        # the mistyped row is IN, because it is genuinely in the tree. Under the
        # old label filter (`tenant_id == "T-local"`) it would have been dropped
        # from the published site while still sitting in the registry -- a
        # department that exists but does not publish, from one typo.
        self.assertEqual(got, {"dref-root", "dref-a", "dref-deep", "dref-mislabelled"})
        # and a node that is NOT under the root stays out however it is labelled
        self.assertNotIn("dref-orphan", got)

    def test_subtree_refs_keeps_tombstones(self):
        """export_registry_only must keep emitting retired rows, or a charter
        homed to one vanishes from registry.json and the Archive tray dies."""
        self._domain("dref-root", "Root", None)
        self._domain("dref-dead", "Dead", "dref-root", status="retired")
        got = self.E.subtree_refs(self.E.load_domains(), "dref-root")
        self.assertIn("dref-dead", got)

    def test_subtree_refs_survives_a_parent_ref_cycle(self):
        """This runs unattended inside a publish. A damaged registry must not
        hang it."""
        self._domain("dref-root", "Root", None)
        self._domain("dref-x", "X", "dref-y")
        self._domain("dref-y", "Y", "dref-x")
        got = self.E.subtree_refs(self.E.load_domains(), "dref-root")
        self.assertEqual(set(got), {"dref-root"})

    # --------------------------------------------------------------- gating --
    def test_two_live_roots_stop_the_PAGE_build(self):
        self._domain("dref-root", "Root", None)
        self._domain("dref-other", "Other Root", None)
        with self.assertRaises(SystemExit) as cm:
            self.D.build_site(os.path.join(self.home, "site"))
        self.assertIn("parent-less", str(cm.exception))

    def test_two_live_roots_stop_the_REGISTRY_export(self):
        """The regression this whole change exists to prevent. Before, this
        function had no root assertion and would happily publish."""
        self._domain("dref-root", "Root", None)
        self._domain("dref-other", "Other Root", None)
        with self.assertRaises(SystemExit) as cm:
            self.D.export_registry_only(os.path.join(self.home, "site"))
        self.assertIn("parent-less", str(cm.exception))

    def test_an_empty_registry_stops_the_export(self):
        with self.assertRaises(SystemExit):
            self.D.export_registry_only(os.path.join(self.home, "site"))

    def test_a_rootless_registry_stops_the_export(self):
        """Every node retired: there is a tree on disk but no live root."""
        self._domain("dref-root", "Root", None, status="retired")
        with self.assertRaises(SystemExit) as cm:
            self.D.export_registry_only(os.path.join(self.home, "site"))
        self.assertIn("no live root", str(cm.exception))

    def test_a_healthy_registry_still_exports(self):
        """The gate must not be so strict that it blocks the normal case."""
        self._domain("dref-root", "Root", None)
        self._domain("dref-a", "A", "dref-root")
        out = os.path.join(self.home, "site")
        os.makedirs(out)          # the caller owns the directory, not the export
        self.D.export_registry_only(out)
        reg = json.load(open(os.path.join(out, "registry.json")))
        self.assertIn("charters", reg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
