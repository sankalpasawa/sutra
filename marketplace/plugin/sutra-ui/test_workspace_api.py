"""Unit tests for workspace_api -- no network, no uvicorn, no real registry.

test_sb_sidecar.py style: in-process, endpoint functions called directly,
policy pinned with mocks. Corpora come from workspace_corpus (PLAN-100 S53);
the registry reader (placement_engine via org_api) is pointed at each corpus
by patching the E.* path constants -- test isolation, never a mock shown to
an operator.

Covers: tree join / unfiled / counts + cap / cache invalidation (S40-S43),
search merge + snippets + ordering (S44-S46), charter (S47-S48), doc meta
(S49), typed errors (S50), resolve (S51), telemetry (S52), path traversal on
every path-taking endpoint (S54), and all five corpora end-to-end (S55, S80).

Run: .venv/bin/python -m unittest test_workspace_api -v   (from sutra-ui/)
"""
import contextlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# The registry env var must point somewhere harmless BEFORE org_api (imported
# by workspace_api) is imported -- same rule as test_perm_mode_default.py.
os.environ.setdefault("SUTRA_NATIVE_HOME",
                      tempfile.mkdtemp(prefix="ws-test-home-"))

import providers            # noqa: E402
import workspace_api        # noqa: E402
import workspace_corpus     # noqa: E402

E = workspace_api.E


def _body(resp):
    """(status, payload) whether the endpoint returned a plain dict (200) or
    a typed-envelope JSONResponse."""
    if isinstance(resp, dict):
        return 200, resp
    return resp.status_code, json.loads(resp.body)


class WsCase(unittest.TestCase):
    """Base harness: builds a corpus in a tempdir and points every seam at it
    -- registry paths, settings file (flag ON), workdir, telemetry -- then
    clears the tree cache so tests never see each other's projections."""

    def setUp(self):
        self._stack = contextlib.ExitStack()
        self.addCleanup(self._stack.close)
        workspace_api._TREE_CACHE.clear()
        self.addCleanup(workspace_api._TREE_CACHE.clear)

    def build(self, builder, **kwargs):
        base = tempfile.mkdtemp(prefix="ws-corpus-")
        self.addCleanup(shutil.rmtree, base, True)
        c = builder(base, **kwargs)
        self.telemetry = os.path.join(base, "telemetry.jsonl")
        for patch in (
            mock.patch.object(E, "HOME", c["home"]),
            mock.patch.object(E, "DOMAINS", os.path.join(c["home"], "domains")),
            mock.patch.object(E, "CHARTERS", os.path.join(c["home"], "charters")),
            mock.patch.object(E, "PLACEMENTS", os.path.join(c["home"], "placements")),
            mock.patch.object(E, "CURRENT",
                              os.path.join(c["home"], "placements", "CURRENT.jsonl")),
            mock.patch.object(providers, "SETTINGS_PATH", Path(c["settings"])),
            mock.patch.object(providers, "load_settings",
                              return_value={"workdir": c["workdir"]}),
            mock.patch.object(providers, "workdir_allowed", return_value=True),
            mock.patch.object(workspace_api, "TELEMETRY_PATH", self.telemetry),
        ):
            self._stack.enter_context(patch)
        return c


# ------------------------------------------------------------- flag gate ----

class FlagGate(WsCase):
    def test_flag_off_is_typed_404_with_hint(self):
        c = self.build(workspace_corpus.corpus_small)
        # S92 cutover: absent means ON now; the typed 404 hangs off the
        # EXPLICIT false — the recorded rollback switch (FLAG.md).
        with open(c["settings"], "w") as fh:
            json.dump({"workdir": c["workdir"], "flags": {"workspace": False}}, fh)
        for call in (workspace_api.ws_tree,
                     lambda: workspace_api.ws_search(q="x"),
                     lambda: workspace_api.ws_charter(id=c["c_eng"]),
                     lambda: workspace_api.ws_doc(path="engine/notes.md"),
                     lambda: workspace_api.ws_resolve(link="engine/notes.md")):
            status, payload = _body(call())
            self.assertEqual(status, 404)
            self.assertEqual(payload["error"]["kind"], "not_found")
            self.assertIn("workspace flag is off", payload["error"]["message"])
        # gate fires before work: no telemetry rows for refused requests
        self.assertFalse(os.path.exists(self.telemetry))

    def test_flag_false_is_off_and_true_is_on(self):
        c = self.build(workspace_corpus.corpus_small)
        with open(c["settings"], "w") as fh:
            json.dump({"flags": {"workspace": False}}, fh)
        status, _ = _body(workspace_api.ws_tree())
        self.assertEqual(status, 404)
        with open(c["settings"], "w") as fh:
            json.dump({"flags": {"workspace": True}}, fh)
        status, _ = _body(workspace_api.ws_tree())
        self.assertEqual(status, 200)


# ------------------------------------------------------------------ tree ----

class Tree(WsCase):
    def test_join_departments_charters_docs(self):
        c = self.build(workspace_corpus.corpus_small)
        status, tree = _body(workspace_api.ws_tree())
        self.assertEqual(status, 200)
        by_ref = {d["ref"]: d for d in tree["departments"]}
        self.assertIn(c["d_eng"], by_ref)
        eng = by_ref[c["d_eng"]]
        self.assertEqual(eng["name"], "Sutra OS")
        self.assertEqual(eng["count"], 2)
        charter = eng["charters"][0]
        self.assertEqual(charter["id"], c["c_eng"])
        self.assertEqual(charter["title"], "Engine Library")
        paths = [d["path"] for d in charter["docs"]]
        # sorted mtime desc: obsidian (NOW-2d) before notes (NOW-5d)
        self.assertEqual(paths, ["research/2026-08-21-obsidian-viewer.md",
                                 "engine/notes.md"])
        doc = charter["docs"][0]
        self.assertEqual(doc["title"], "Obsidian-like file viewer")
        self.assertFalse(doc["missing"])
        self.assertEqual(doc["mtime"],
                         workspace_corpus.NOW - 2 * workspace_corpus.DAY)

    def test_unfiled_named_never_hidden(self):
        c = self.build(workspace_corpus.corpus_small)
        _, tree = _body(workspace_api.ws_tree())
        unfiled = {d["path"]: d for d in tree["unfiled"]}
        self.assertIn("TODO.md", unfiled)
        self.assertEqual(unfiled["TODO.md"]["title"], "TODO")  # stem fallback
        # filed docs never leak into unfiled
        self.assertNotIn("engine/notes.md", unfiled)
        self.assertEqual(tree["doc_rows"], 4)  # 3 filed + 1 unfiled
        self.assertFalse(tree["truncated"])

    def test_empty_registry_is_200_not_error(self):
        self.build(workspace_corpus.corpus_empty)
        status, tree = _body(workspace_api.ws_tree())
        self.assertEqual(status, 200)
        self.assertEqual(tree["departments"], [])
        self.assertEqual(tree["unfiled"], [])
        self.assertEqual(tree["doc_rows"], 0)

    def test_orphaned_placement_row_kept_missing_counts_excluded(self):
        c = self.build(workspace_corpus.corpus_orphaned)
        _, tree = _body(workspace_api.ws_tree())
        res = next(d for d in tree["departments"] if d["ref"] == c["d_res"])
        docs = {r["path"]: r for r in res["charters"][0]["docs"]}
        gone = docs[c["orphan_path"]]
        self.assertTrue(gone["missing"])          # listed, struck-through
        self.assertIsNone(gone["mtime"])
        self.assertEqual(res["count"], 1)         # count reflects reality
        # missing rows sort AFTER present ones
        self.assertEqual(res["charters"][0]["docs"][-1]["path"],
                         c["orphan_path"])
        # the escaping placement contributes NO row anywhere (M5)
        all_paths = [r["path"] for d in tree["departments"]
                     for ch in d["charters"] for r in ch["docs"]]
        self.assertNotIn("../outside.md", all_paths)
        self.assertNotIn("outside.md", all_paths)

    def test_cap_and_truncated_flag_large_corpus(self):
        c = self.build(workspace_corpus.corpus_large)
        _, tree = _body(workspace_api.ws_tree())
        self.assertTrue(tree["truncated"])
        self.assertEqual(tree["doc_rows"], workspace_api.TREE_MAX_DOC_ROWS)
        bulk = tree["departments"][0]
        self.assertEqual(len(bulk["charters"][0]["docs"]), c["filed"])
        self.assertEqual(bulk["count"], c["filed"])   # full count survives cap
        self.assertEqual(len(tree["unfiled"]),
                         workspace_api.TREE_MAX_DOC_ROWS - c["filed"])


class TreeCache(WsCase):
    def test_registry_or_fs_change_invalidates(self):
        c = self.build(workspace_corpus.corpus_small)
        _, t1 = _body(workspace_api.ws_tree())
        self.assertEqual(len(t1["unfiled"]), 1)
        # a new unfiled file moves the workdir's mtime -> signature moves
        workspace_corpus.write_doc(c["workdir"], "fresh.md", title="Fresh",
                                   body="x\n")
        _, t2 = _body(workspace_api.ws_tree())
        self.assertEqual(len(t2["unfiled"]), 2)

    def test_in_place_edit_within_ttl_serves_cache_then_expires(self):
        c = self.build(workspace_corpus.corpus_small)
        _, t1 = _body(workspace_api.ws_tree())
        # rewrite a SUBDIR file's content: no dir mtime moves, signature holds
        sub = os.path.join(c["workdir"], "engine", "notes.md")
        with open(sub, "w") as fh:
            fh.write("# Renamed heading\n")
        _, t2 = _body(workspace_api.ws_tree())
        self.assertIs(t2, t1)                      # cache hit, same object
        # force the TTL backstop to lapse -> rebuild sees the edit
        workspace_api._TREE_CACHE[next(iter(workspace_api._TREE_CACHE))]["ts"] = 0
        _, t3 = _body(workspace_api.ws_tree())
        titles = [r["title"] for d in t3["departments"]
                  for ch in d["charters"] for r in ch["docs"]]
        self.assertIn("Renamed heading", titles)


# ---------------------------------------------------------------- search ----

class Search(WsCase):
    def test_empty_query_shape(self):
        self.build(workspace_corpus.corpus_small)
        status, out = _body(workspace_api.ws_search(q="  "))
        self.assertEqual(status, 200)
        self.assertEqual(out, {"query": "", "documents": [], "records": [],
                               "counts": {}, "truncated": False})

    def test_merge_docs_then_records_and_placement_folds_in(self):
        c = self.build(workspace_corpus.corpus_small)
        _, out = _body(workspace_api.ws_search(q="engine"))
        doc_paths = [d["path"] for d in out["documents"]]
        self.assertIn("engine/notes.md", doc_paths)
        kinds = {r["kind"] for r in out["records"]}
        self.assertLessEqual(kinds, {"department", "charter"})  # never a 3rd
        recs = {(r["kind"], r["ref"]) for r in out["records"]}
        self.assertIn(("charter", c["c_eng"]), recs)
        # org_search's placement hit on "engine/notes.md" folded into
        # documents (already there), never a record row
        self.assertEqual(out["counts"]["documents"], len(out["documents"]))
        charter_rec = next(r for r in out["records"] if r["kind"] == "charter")
        self.assertTrue(set(charter_rec["matched_on"])
                        & {"title", "purpose", "scope_in"})

    def test_ordering_title_hit_above_body_hit(self):
        c = self.build(workspace_corpus.corpus_small)
        # "brief" is in brief-31's TITLE (mtime NOW-1d) and only in the BODY
        # of nothing else; "pricing" is body-only. Use "viewer": title of
        # obsidian doc (NOW-2d); body of nothing. Add a body-hit doc newer
        # than the title-hit doc to prove title still wins.
        workspace_corpus.write_doc(c["workdir"], "scratch.md", title="Scratch",
                                   body="a viewer appears mid-body\n",
                                   mtime=workspace_corpus.NOW)
        _, out = _body(workspace_api.ws_search(q="viewer"))
        paths = [d["path"] for d in out["documents"]]
        self.assertEqual(paths[0], "research/2026-08-21-obsidian-viewer.md")
        self.assertIn("scratch.md", paths[1:])

    def test_snippet_is_plain_escaped_with_codepoint_ranges(self):
        c = self.build(workspace_corpus.corpus_small)
        workspace_corpus.write_doc(
            c["workdir"], "hostile.md", title="Hostile",
            body="émoji → <script>alert(1)</script> then obsidian here\n",
            mtime=workspace_corpus.NOW)
        _, out = _body(workspace_api.ws_search(q="obsidian"))
        row = next(d for d in out["documents"] if d["path"] == "hostile.md")
        text, ranges = row["snippet"]["text"], row["snippet"]["ranges"]
        self.assertNotIn("<", text)               # nothing renderable
        self.assertNotIn(">", text)
        self.assertLessEqual(len(text), workspace_api.SNIPPET_MAX)
        self.assertTrue(ranges)
        for start, end in ranges:                 # ranges index the sent text
            self.assertEqual(text[start:end].lower(), "obsidian")

    def test_filing_strings_and_unfiled_nulls(self):
        self.build(workspace_corpus.corpus_small)
        _, out = _body(workspace_api.ws_search(q="unfiled scratch"))
        row = next(d for d in out["documents"] if d["path"] == "TODO.md")
        self.assertEqual(row["filing"], {"department": None, "charter": None})
        _, out = _body(workspace_api.ws_search(q="calibration"))
        row = next(d for d in out["documents"] if d["path"] == "engine/notes.md")
        self.assertEqual(row["filing"], {"department": "Sutra OS",
                                         "charter": "Engine Library"})

    def test_caps_and_truncated(self):
        c = self.build(workspace_corpus.corpus_small)
        for i in range(workspace_api.SEARCH_DOC_CAP + 3):
            workspace_corpus.write_doc(c["workdir"], "many/m-%02d.md" % i,
                                       title="Manydoc %02d" % i,
                                       body="needleword\n",
                                       mtime=workspace_corpus.NOW - i)
        _, out = _body(workspace_api.ws_search(q="needleword"))
        self.assertEqual(len(out["documents"]), workspace_api.SEARCH_DOC_CAP)
        self.assertEqual(out["counts"]["documents"],
                         workspace_api.SEARCH_DOC_CAP + 3)
        self.assertTrue(out["truncated"])


# --------------------------------------------------------------- charter ----

class Charter(WsCase):
    def test_charter_page_payload(self):
        c = self.build(workspace_corpus.corpus_small)
        status, out = _body(workspace_api.ws_charter(id=c["c_eng"]))
        self.assertEqual(status, 200)
        ch = out["charter"]
        self.assertEqual(ch["id"], c["c_eng"])
        self.assertEqual(ch["title"], "Engine Library")
        self.assertEqual(ch["status"], "active")
        self.assertEqual(ch["department"], {"ref": c["d_eng"],
                                            "name": "Sutra OS"})
        self.assertTrue(ch["address"])            # D-path from domain_path
        self.assertEqual([d["path"] for d in out["docs"]],
                         ["research/2026-08-21-obsidian-viewer.md",
                          "engine/notes.md"])     # mtime desc
        self.assertEqual(out["doc_count"], 2)

    def test_unknown_charter_and_empty_registry(self):
        c = self.build(workspace_corpus.corpus_small)
        status, payload = _body(workspace_api.ws_charter(id="C-deadbeef"))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "not_found"))
        self.build(workspace_corpus.corpus_empty)
        status, payload = _body(workspace_api.ws_charter(id=c["c_eng"]))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "registry_empty"))

    def test_missing_file_placement_excluded_here(self):
        c = self.build(workspace_corpus.corpus_orphaned)
        _, out = _body(workspace_api.ws_charter(id=c["c_res"]))
        self.assertEqual([d["path"] for d in out["docs"]],
                         ["research/brief-31.md"])
        self.assertEqual(out["doc_count"], 1)


# ------------------------------------------------------------------- doc ----

class Doc(WsCase):
    def test_doc_meta_filed(self):
        c = self.build(workspace_corpus.corpus_small)
        status, out = _body(workspace_api.ws_doc(path="engine/notes.md"))
        self.assertEqual(status, 200)
        self.assertEqual(out["path"], "engine/notes.md")
        self.assertEqual(out["title"], "Engine notes")
        self.assertNotIn("content", out)          # rail data only, no body
        self.assertNotIn("text", out)
        self.assertEqual(out["filing"]["department"],
                         {"ref": c["d_eng"], "name": "Sutra OS"})
        self.assertEqual(out["filing"]["charter"],
                         {"id": c["c_eng"], "title": "Engine Library"})
        self.assertEqual(out["filing"]["placement_ref"], c["p_eng"])
        meta = out["meta"]
        self.assertEqual(meta["mtime"],
                         workspace_corpus.NOW - 5 * workspace_corpus.DAY)
        self.assertGreater(meta["bytes"], 0)
        self.assertEqual(meta["words"], 6)  # "# Engine notes" + 4 body words
        self.assertEqual(out["linked_from"], [])

    def test_doc_meta_unfiled_nulls(self):
        self.build(workspace_corpus.corpus_small)
        _, out = _body(workspace_api.ws_doc(path="TODO.md"))
        self.assertEqual(out["filing"], {"department": None, "charter": None,
                                         "placement_ref": None})

    def test_doc_gone_is_404_not_found(self):
        c = self.build(workspace_corpus.corpus_orphaned)
        status, payload = _body(workspace_api.ws_doc(path=c["orphan_path"]))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "not_found"))


# --------------------------------------------------------------- resolve ----

class Resolve(WsCase):
    def test_doc_path_charter_id_dept_ref(self):
        c = self.build(workspace_corpus.corpus_small)
        _, out = _body(workspace_api.ws_resolve(link="engine/notes.md"))
        self.assertEqual(out["target"], {"type": "doc",
                                         "path": "engine/notes.md"})
        _, out = _body(workspace_api.ws_resolve(link=c["c_eng"]))
        self.assertEqual(out["target"], {"type": "charter", "ref": c["c_eng"]})
        _, out = _body(workspace_api.ws_resolve(link=c["d_eng"]))
        self.assertEqual(out["target"], {"type": "department",
                                         "ref": c["d_eng"]})

    def test_deep_link_and_route_forms(self):
        c = self.build(workspace_corpus.corpus_small)
        _, out = _body(workspace_api.ws_resolve(
            link="sutra://workspace?doc=engine%2Fnotes.md"))
        self.assertEqual(out["target"]["path"], "engine/notes.md")
        # doc > charter > dept precedence
        _, out = _body(workspace_api.ws_resolve(
            link="workspace?dept=%s&doc=engine/notes.md" % c["d_res"]))
        self.assertEqual(out["target"]["type"], "doc")
        _, out = _body(workspace_api.ws_resolve(
            link="workspace?charter=%s" % c["c_res"]))
        self.assertEqual(out["target"], {"type": "charter", "ref": c["c_res"]})

    def test_bare_title_unique_and_collision(self):
        c = self.build(workspace_corpus.corpus_duplicate_titles)
        _, out = _body(workspace_api.ws_resolve(link="Engine notes"))
        self.assertEqual(out["target"]["path"], "engine/notes.md")
        self.assertNotIn("also", out)
        _, out = _body(workspace_api.ws_resolve(link="Quarterly plan"))
        self.assertEqual(out["target"]["path"], c["dup_new"])   # newest mtime
        self.assertEqual(out["also"], [{"type": "doc", "path": c["dup_old"]}])

    def test_registry_disk_mismatch_is_409(self):
        c = self.build(workspace_corpus.corpus_orphaned)
        status, payload = _body(workspace_api.ws_resolve(link=c["orphan_path"]))
        self.assertEqual((status, payload["error"]["kind"]),
                         (409, "mismatch"))

    def test_unknowns_and_empty_registry(self):
        c = self.build(workspace_corpus.corpus_small)
        status, payload = _body(workspace_api.ws_resolve(link="No Such Title"))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "not_found"))
        self.build(workspace_corpus.corpus_empty)
        status, payload = _body(workspace_api.ws_resolve(link=c["d_eng"]))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "registry_empty"))


# ---------------------------------------------------------- typed errors ----

class TypedErrors(WsCase):
    def test_engine_down_when_workdir_unavailable(self):
        self.build(workspace_corpus.corpus_small)
        with mock.patch.object(providers, "load_settings",
                               return_value={"workdir": ""}):
            status, payload = _body(workspace_api.ws_tree())
        self.assertEqual((status, payload["error"]["kind"]),
                         (503, "engine_down"))

    def test_engine_down_when_registry_store_unreadable(self):
        self.build(workspace_corpus.corpus_small)
        with mock.patch.object(E, "load_domains",
                               side_effect=OSError("permission denied")):
            status, payload = _body(workspace_api.ws_tree())
        self.assertEqual((status, payload["error"]["kind"]),
                         (503, "engine_down"))

    def test_envelope_shape_is_the_only_error_shape(self):
        self.build(workspace_corpus.corpus_small)
        status, payload = _body(workspace_api.ws_doc(path="nope.md"))
        self.assertEqual(sorted(payload), ["error"])
        self.assertEqual(sorted(payload["error"]), ["kind", "message"])


# ---------------------------------------------------------- path traversal --

class PathTraversal(WsCase):
    """S54: every endpoint that takes a path refuses escapes as not_found --
    an attacker learns nothing beyond 'no such document'."""

    ATTACKS = ("../secret.md", "../../etc/passwd.md", "/etc/passwd.md",
               "~/secret.md", "a/../../b.md", "not-markdown.txt", "")

    def test_doc_endpoint(self):
        self.build(workspace_corpus.corpus_small)
        for attack in self.ATTACKS:
            status, payload = _body(workspace_api.ws_doc(path=attack))
            self.assertEqual((status, payload["error"]["kind"]),
                             (404, "not_found"), attack)

    def test_resolve_endpoint(self):
        self.build(workspace_corpus.corpus_small)
        for attack in ("../secret.md", "/etc/passwd.md", "~/x.md",
                       "a/../../b.md", "workspace?doc=../secret.md",
                       "sutra://workspace?doc=/etc/passwd.md",
                       "a\\b.md", "col:on.md"):
            status, payload = _body(workspace_api.ws_resolve(link=attack))
            self.assertEqual((status, payload["error"]["kind"]),
                             (404, "not_found"), attack)

    def test_symlink_escape_refused(self):
        c = self.build(workspace_corpus.corpus_small)
        outside = tempfile.mkdtemp(prefix="ws-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        with open(os.path.join(outside, "leak.md"), "w") as fh:
            fh.write("# outside\n")
        os.symlink(os.path.join(outside, "leak.md"),
                   os.path.join(c["workdir"], "leak.md"))
        status, payload = _body(workspace_api.ws_doc(path="leak.md"))
        self.assertEqual((status, payload["error"]["kind"]),
                         (404, "not_found"))


# -------------------------------------------------------------- telemetry ---

class Telemetry(WsCase):
    def test_counters_are_counts_only(self):
        c = self.build(workspace_corpus.corpus_small)
        workspace_api.ws_tree()
        workspace_api.ws_search(q="engine")
        workspace_api.ws_doc(path="engine/notes.md")
        workspace_api.ws_charter(id=c["c_eng"])
        workspace_api.ws_resolve(link="engine/notes.md")
        with open(self.telemetry) as fh:
            rows = [json.loads(line) for line in fh]
        self.assertEqual([r["event"] for r in rows],
                         ["tree_served", "search_served", "doc_opened",
                          "record_opened", "resolve_served"])
        for r in rows:
            self.assertEqual(sorted(r), ["event", "ts"])  # no paths, no query

    def test_telemetry_failure_never_fails_the_read(self):
        self.build(workspace_corpus.corpus_small)
        with mock.patch.object(workspace_api, "TELEMETRY_PATH",
                               os.path.join(os.sep, "nonexistent-rootdir",
                                            "t.jsonl")):
            status, _ = _body(workspace_api.ws_tree())
        self.assertEqual(status, 200)


# ------------------------------------------------------------ corpus runs ---

class CorpusRuns(WsCase):
    """S55/S80: all five corpora through tree + search end-to-end. Individual
    behaviours are pinned above; this pins 'no corpus can crash the surface'."""

    def test_all_five_corpora_tree_and_search(self):
        for name, builder in workspace_corpus.ALL_CORPORA.items():
            with self.subTest(corpus=name):
                self.setUp()          # fresh stack per corpus
                self.build(builder)
                status, tree = _body(workspace_api.ws_tree())
                self.assertEqual(status, 200, name)
                self.assertLessEqual(tree["doc_rows"],
                                     workspace_api.TREE_MAX_DOC_ROWS)
                status, out = _body(workspace_api.ws_search(q="doc"))
                self.assertEqual(status, 200, name)
                self.assertLessEqual(len(out["documents"]),
                                     workspace_api.SEARCH_DOC_CAP)
                self._stack.close()

    def test_corrupted_rows_skipped_good_rows_survive(self):
        c = self.build(workspace_corpus.corpus_corrupted)
        status, tree = _body(workspace_api.ws_tree())
        self.assertEqual(status, 200)
        refs = {d["ref"] for d in tree["departments"]}
        self.assertIn(c["d_eng"], refs)           # good rows intact
        self.assertNotIn("dref-broken000000001", refs)
        paths = [r["path"] for d in tree["departments"]
                 for ch in d["charters"] for r in ch["docs"]]
        self.assertIn("engine/notes.md", paths)   # good placements intact


if __name__ == "__main__":
    unittest.main()


class FsTreeMd(unittest.TestCase):
    """r7: /api/fs/tree?md=1 filters DURING the walk so the entry cap applies
    to markdown docs — the lexical all-files cap was silently dropping whole
    folders from the Workspace Folders lens."""

    def test_md_filter_applies_before_the_cap(self):
        import org_api
        wd = tempfile.mkdtemp(prefix="fs-md-")
        os.makedirs(os.path.join(wd, "a", "b"))
        Path(wd, "a", "one.md").write_text("x")
        Path(wd, "a", "b", "two.md").write_text("y")
        for i in range(5):
            Path(wd, "a", "noise-%d.txt" % i).write_text("n")
        with mock.patch.object(providers, "load_settings",
                               return_value={"workdir": wd}),              mock.patch.object(providers, "workdir_allowed", return_value=True),              mock.patch.object(org_api, "FS_MAX_ENTRIES", 2):
            got = org_api.api_fs_tree(md=1)
        paths = sorted(f["path"] for f in got["files"])
        self.assertEqual(paths, ["a/b/two.md", "a/one.md"])
        # the cap counted MARKDOWN entries: 2 md == cap, txt noise never ate it
        self.assertTrue(all(p.endswith(".md") for p in paths))
        shutil.rmtree(wd, ignore_errors=True)
