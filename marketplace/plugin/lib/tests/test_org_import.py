#!/usr/bin/env python3
"""test_org_import.py — the published export is losslessly invertible.

PROTO-000: every shipped change carries a test. org_import.py claims that a
generated domains site can be turned back into the registry that produced it.
The only honest proof of that is a ROUND TRIP: import the export, re-run the
generator over the imported registry, and require the two documents to agree
on every load-bearing fact.

Stdlib `unittest` only. Python 3.9: no `match`, no PEP-604 unions.

HARNESS — the same reload dance test_phase0.py documents
-------------------------------------------------------
`placement_engine` resolves HOME/DOMAINS/CHARTERS at IMPORT time, so setting
SUTRA_NATIVE_HOME afterwards does nothing. Every setUp() mints a fresh
tempfile.mkdtemp(), exports it, and reloads the module. `_assert_sandboxed()`
aborts if any path escapes the temp dir, so a bug here can never write to the
real registry at ~/.sutra-native/user-kit.

The export under test is the one checked into this repo at website/domains/ —
verified byte-identical to the live published page. If it is absent the site
tests skip rather than fail: a checkout without the website is not a defect.
"""
import html
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.dirname(HERE)


def _find_export():
    """Walk up for website/domains. Counting `..` hops is how this suite
    silently skipped its entire self on the first run — a skip that looks
    exactly like a pass in the output."""
    d = LIB
    for _ in range(6):
        cand = os.path.join(d, "website", "domains")
        if os.path.isdir(cand):
            return cand
        d = os.path.dirname(d)
    return os.path.join(LIB, "website", "domains")   # non-existent: tests skip


EXPORT = _find_export()
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import org_import  # noqa: E402


def _txt(x):
    return html.unescape(re.sub(r"<[^>]+>", "", x or "")).strip()


@unittest.skipUnless(os.path.isdir(EXPORT), "no published export in this checkout")
class ParseExport(unittest.TestCase):
    """The export is read exactly, or the parse refuses."""

    @classmethod
    def setUpClass(cls):
        cls.p = org_import.parse_export(EXPORT)

    def test_every_domain_is_found_and_parented(self):
        p = self.p
        self.assertEqual(len(p["parent"]), 55)
        for ref, pa in p["parent"].items():
            self.assertTrue(pa == "ROOT" or pa in p["parent"],
                            "%s has an unresolved parent %s" % (ref, pa))

    def test_exactly_five_top_level_departments_in_published_order(self):
        tops = [self.p["name"][r] for r in self.p["kids"]["ROOT"]]
        self.assertEqual(tops, ["Sutra OS", "Holding Departments",
                                "Portfolio (T2)", "Client Projects (T3)",
                                "Fleet (T4)"])

    def test_child_counts_match_the_published_page(self):
        want = {"Sutra OS": 6, "Holding Departments": 9, "Portfolio (T2)": 6,
                "Client Projects (T3)": 0, "Fleet (T4)": 0, "Core Plugin": 4,
                "Governance Hooks": 11, "Skills Catalog": 7}
        byname = {n: r for r, n in self.p["name"].items()}
        for n, k in want.items():
            self.assertEqual(len(self.p["kids"].get(byname[n], [])), k,
                             "%s should have %d children" % (n, k))

    def test_all_charters_recovered_with_a_page_each(self):
        self.assertEqual(len(self.p["charters"]), 162)
        for cid in self.p["charters"]:
            self.assertTrue(os.path.exists(os.path.join(EXPORT, cid + ".html")),
                            "%s has no charter page" % cid)

    def test_descriptions_are_never_the_truncated_card_text(self):
        """Card text is clipped with an ellipsis; the domain's own page has the
        full sentence. Importing the clipped one would silently lose content."""
        for ref, d in self.p["desc"].items():
            self.assertFalse(d.endswith("..."),
                             "%s kept a truncated description" % ref)

    def test_lane_inversion_is_checked_not_assumed(self):
        """verify_lanes() must actually compare cells — a version that compared
        nothing would pass every other test in this file. Published says the
        charter links into dref-b; the recovered links say it does not."""
        args = ({"C-x": {"id": "C-x", "owner": "dref-a"}},
                {"C-x": set()},
                {"C-x": {"ROOT": {"dref-a": "O", "dref-b": "L"}}},
                {"ROOT": ["dref-a", "dref-b"]},
                {"dref-a": "ROOT", "dref-b": "ROOT"})
        with self.assertRaises(org_import.ImportError_):
            org_import.verify_lanes(*args)
        # and it PASSES once the link is recovered -- otherwise the check above
        # could be satisfied by a function that always raises
        ok = (args[0], {"C-x": {"dref-b"}}) + args[2:]
        self.assertEqual(org_import.verify_lanes(*ok), 1)

    def test_resolve_links_prefers_the_deepest_lane(self):
        """An L on a parent page AND on the child page means the link is deeper;
        only the deepest one is the real linked domain."""
        per_page = {"ROOT": {"dref-top": "L"},
                    "dref-top": {"dref-leaf": "L"}}
        self.assertEqual(org_import.resolve_links(per_page), {"dref-leaf"})


@unittest.skipUnless(os.path.isdir(EXPORT), "no published export in this checkout")
class RoundTrip(unittest.TestCase):
    """Import into a sandbox registry, then re-render and compare."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="org-import-test-")
        os.environ["SUTRA_NATIVE_HOME"] = self.home
        import placement_engine
        self.E = importlib.reload(placement_engine)
        self._assert_sandboxed()
        self.parsed = org_import.parse_export(EXPORT)
        plan = org_import.build_plan(self.parsed, self.home)
        org_import.apply_plan(plan)
        self.plan = plan

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("SUTRA_NATIVE_HOME", None)

    def _assert_sandboxed(self):
        for p in (self.E.HOME, self.E.DOMAINS, self.E.CHARTERS):
            self.assertTrue(os.path.abspath(p).startswith(os.path.abspath(self.home)),
                            "engine path %s escaped the sandbox" % p)

    def test_registry_holds_every_department_and_charter(self):
        """55 departments plus the root they hang from. An empty target gets the
        root created; a target that already has one has it aliased."""
        domains = self.E.load_domains()
        self.assertEqual(len(domains), 56)
        self.assertEqual(len(self.E.charter_body_files()), 162)

    def test_one_root_only(self):
        domains = self.E.load_domains()
        roots = [r for r, d in domains.items() if not d.get("parent_ref")]
        self.assertEqual(len(roots), 1, "a registry with two roots is broken")

    def test_d_paths_match_the_published_order(self):
        """The whole point of the synthetic ts_minted_ms ordering.

        Published chips are PAGE-RELATIVE ("Governance Hooks" is D1 on the Core
        Plugin page), so the comparison is against the GLOBAL path composed from
        the parsed tree, plus the handful of globals index.html states outright.
        """
        domains = self.E.load_domains()
        expect = {}

        def walk(ref, prefix):
            for i, kid in enumerate(self.parsed["kids"].get(ref, []), 1):
                path = "%s%d" % (prefix, i)
                expect[kid] = path
                walk(kid, path + ".D")

        walk("ROOT", "D")
        wrong = [(self.parsed["name"].get(r), want, self.E.domain_path(r, domains))
                 for r, want in expect.items()
                 if self.E.domain_path(r, domains) != want]
        self.assertEqual(wrong, [], "D-paths diverged from the published order")

        # the globals index.html states outright, as an independent anchor
        byname = {n: r for r, n in self.parsed["name"].items()}
        for n, path in (("Sutra OS", "D1"), ("Holding Departments", "D2"),
                        ("Portfolio (T2)", "D3"), ("Client Projects (T3)", "D4"),
                        ("Fleet (T4)", "D5"), ("Core Plugin", "D1.D1"),
                        ("Reflection", "D3.D6")):
            self.assertEqual(self.E.domain_path(byname[n], domains), path, n)

    def test_charters_land_on_their_published_owners(self):
        for cid, c in self.parsed["charters"].items():
            body = self.E.load_charter(cid)
            self.assertIsNotNone(body, "%s was not written" % cid)
            owner = self.plan["alias"].get(c["owner"], c["owner"])
            self.assertEqual(body["domain_ref"], owner)

    def test_status_and_links_survive_in_the_sidecar(self):
        view = self.E.charter_view("C-00f213b12f61c3ca")
        self.assertEqual(view["status"], "shipped")
        n_linked = sum(len(self.E.charter_view(c)["linked_domain_refs"])
                       for c in self.parsed["charters"])
        self.assertEqual(n_linked, 80)

    def test_links_are_the_union_of_both_witnesses(self):
        """The lane grid and the byline each under-report, in different places.
        Taking either alone silently loses links -- and drops rows from the
        published table, because row inclusion counts lanes."""
        self.assertTrue(self.parsed["link_disagreements"],
                        "if these ever agree everywhere, simplify this")
        grid_only = any(set(g) - set(b) for _, g, b in self.parsed["link_disagreements"])
        byline_only = any(set(b) - set(g) for _, g, b in self.parsed["link_disagreements"])
        self.assertTrue(grid_only and byline_only,
                        "neither witness contains the other -- that is why it is a union")

    def test_charter_extras_survive(self):
        """registry.json carries goals/metrics/milestones for one charter; an
        import that dropped them would still pass every other assertion."""
        cid = "C-3c9561433663be10"
        view = self.E.charter_view(cid)
        self.assertTrue(view.get("milestones"), "milestones were dropped")

    def test_regenerated_site_reproduces_the_published_tree(self):
        """The round trip: generate a site from the imported registry and
        require the same departments, in the same order, under the same refs."""
        import domains_page
        importlib.reload(domains_page)
        out = os.path.join(self.home, "site")
        domains_page.build_site(out, label="Departments")
        idx = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        pub = open(os.path.join(EXPORT, "index.html"), encoding="utf-8").read()

        sect = re.compile(r'<span class="chip big">([^<]*)</span><div><h2>'
                          r'<a class="dlink" href="(dref-[0-9a-f]+)\.html">(.*?)</a>', re.S)
        got = [(c, r, _txt(n)) for c, r, n in sect.findall(idx)]
        want = [(c, r, _txt(n)) for c, r, n in sect.findall(pub)]
        self.assertEqual(got, want, "top-level sections diverged")

    def test_regenerated_charter_table_has_the_same_rows(self):
        import domains_page
        importlib.reload(domains_page)
        out = os.path.join(self.home, "site2")
        domains_page.build_site(out, label="Departments")
        row = re.compile(r'<tr class="chtr[^"]*" data-status="([^"]*)" '
                         r'data-owner="([^"]*)">.*?href="(C-[0-9a-f]+)\.html"', re.S)
        got = sorted(row.findall(open(os.path.join(out, "index.html"),
                                      encoding="utf-8").read()))
        want = sorted(row.findall(open(os.path.join(EXPORT, "index.html"),
                                       encoding="utf-8").read()))
        self.assertEqual(len(got), len(want), "charter row count diverged")
        self.assertEqual(got, want, "charter rows diverged (status/owner/id)")

    def test_import_is_idempotent(self):
        """Re-running must add nothing and touch nothing."""
        before = json.dumps(sorted(os.listdir(os.path.join(self.home, "domains"))))
        plan2 = org_import.build_plan(self.parsed, self.home)
        self.assertEqual(len(plan2["domains"]), 0)
        self.assertEqual(len(plan2["charters"]), 0)
        wrote = org_import.apply_plan(plan2)
        self.assertEqual(wrote["domains"], 0)
        self.assertEqual(wrote["charters"], 0)
        after = json.dumps(sorted(os.listdir(os.path.join(self.home, "domains"))))
        self.assertEqual(before, after)

    def test_existing_local_domains_are_never_overwritten(self):
        """A machine with its own departments keeps them: the import grafts,
        it does not replace."""
        ref, _ = self.E.mint_domain(None, "Local Only", ["local"], "T-local")
        plan = org_import.build_plan(self.parsed, self.home)
        org_import.apply_plan(plan)
        self.assertIn(ref, self.E.load_domains())


if __name__ == "__main__":
    unittest.main(verbosity=2)
