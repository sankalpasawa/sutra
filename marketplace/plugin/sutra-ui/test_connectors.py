"""Unit tests for the MCP-connectors backend (connectors_store + app endpoints).

WHY A SEPARATE FILE (same rationale as test_activity.py)
-------------------------------------------------------
No server, no network, no extra deps — just the store functions and the endpoint
handlers, called in-process against an isolated tempdir store. That makes them
runnable under the SHIPPED interpreter (electron/payload/python/bin/python3),
which carries fastapi/starlette but NOT httpx/pytest — so starlette's TestClient
is off the table and calling the handlers directly is the only dependency-free
way in. stdlib unittest only.

Run (bundled interpreter, no pytest):
    electron/payload/python/bin/python3 test_connectors.py -v
Run (dev venv, same as the rest of the suite):
    .venv/bin/python -m unittest test_connectors -v

connectors_store globs/writes ONE file, CONNECTORS_PATH. Every test repoints
that module attribute at a fresh tempdir and restores it — so a run never reads
(or writes) the operator's real ~/.sutra-ui/connectors.json. app imports the
SAME module object (import connectors_store), so the rebind is seen by
app._sutra_mcp_config's merge too.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# importing app has import-time banners (org_api/providers) but no server side
# effects — same as test_activity.
import app  # noqa: E402
import connectors_store as cs  # noqa: E402


class _IsolatedStore(unittest.TestCase):
    """Base: give each test a fresh, isolated CONNECTORS_PATH and restore it."""

    def setUp(self):
        self._saved = cs.CONNECTORS_PATH
        self.dir = Path(tempfile.mkdtemp(prefix="sutra-test-connectors-"))
        cs.CONNECTORS_PATH = self.dir / "connectors.json"
        # app referenced the SAME module object (import connectors_store), so
        # this one rebind is seen by _sutra_mcp_config's merge.
        self.assertIs(app.connectors_store, cs,
                      "app must share the connectors_store module")

    def tearDown(self):
        cs.CONNECTORS_PATH = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)


# ------------------------------------------------------------- validation ----
class TestValidate(_IsolatedStore):
    def test_minimal_stdio_normalises_all_fields(self):
        c = cs.validate({"name": "github", "transport": "stdio", "command": "npx"})
        self.assertEqual(set(c.keys()),
                         {"id", "name", "transport", "command", "args", "env",
                          "url", "enabled"})
        self.assertEqual(c["name"], "github")
        self.assertEqual(c["transport"], "stdio")
        self.assertEqual(c["command"], "npx")
        self.assertEqual(c["args"], [])
        self.assertEqual(c["env"], {})
        self.assertEqual(c["url"], "")
        self.assertTrue(c["enabled"])          # defaults to enabled
        self.assertEqual(c["id"], "")          # validate does NOT mint ids

    def test_bad_names_are_rejected(self):
        for bad in ["", "A", "Github", "has space", "-lead", "_lead",
                    "way-too-long-" + "x" * 40, "punct!", "café"]:
            with self.assertRaises(ValueError, msg="should reject %r" % bad):
                cs.validate({"name": bad, "transport": "stdio", "command": "x"})

    def test_good_names_pass(self):
        for ok in ["a", "0", "github", "brave-search", "my_server", "x" * 39]:
            c = cs.validate({"name": ok, "transport": "stdio", "command": "x"})
            self.assertEqual(c["name"], ok)

    def test_sutra_name_is_reserved(self):
        with self.assertRaises(ValueError) as ctx:
            cs.validate({"name": "sutra", "transport": "stdio", "command": "x"})
        self.assertIn("reserved", str(ctx.exception).lower())

    def test_unknown_transport_rejected(self):
        with self.assertRaises(ValueError):
            cs.validate({"name": "x", "transport": "grpc", "command": "y"})

    def test_stdio_requires_command(self):
        with self.assertRaises(ValueError) as ctx:
            cs.validate({"name": "x", "transport": "stdio"})
        self.assertIn("command", str(ctx.exception))

    def test_http_and_sse_require_url(self):
        for t in ("http", "sse"):
            with self.assertRaises(ValueError) as ctx:
                cs.validate({"name": "x", "transport": t})
            self.assertIn("url", str(ctx.exception))
        # ... and pass when a url is present
        c = cs.validate({"name": "x", "transport": "sse", "url": "https://h/sse"})
        self.assertEqual(c["url"], "https://h/sse")

    def test_args_drop_non_strings_env_keeps_blanks(self):
        c = cs.validate({"name": "x", "transport": "stdio", "command": "npx",
                         "args": ["-y", 3, None, "pkg"],
                         "env": {"TOK": "", "N": None, "K": "v", 5: "z"}})
        self.assertEqual(c["args"], ["-y", "pkg"])
        self.assertEqual(c["env"], {"TOK": "", "N": "", "K": "v"})


# --------------------------------------------------------------- CRUD --------
class TestCrud(_IsolatedStore):
    def test_load_missing_file_is_empty(self):
        self.assertEqual(cs.load(), [])

    def test_load_corrupt_file_is_empty(self):
        cs.CONNECTORS_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(cs.load(), [])

    def test_add_assigns_id_and_persists(self):
        c = cs.add_or_update({"name": "github", "transport": "stdio",
                              "command": "npx"})
        self.assertTrue(c["id"].startswith("cx_"))
        self.assertTrue(cs.CONNECTORS_PATH.exists(), "add must write the store")
        stored = cs.load()
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], c["id"])

    def test_update_by_id_replaces_in_place(self):
        c = cs.add_or_update({"name": "github", "transport": "stdio",
                              "command": "npx"})
        c2 = cs.add_or_update({"id": c["id"], "name": "github",
                               "transport": "stdio", "command": "docker"})
        self.assertEqual(c2["id"], c["id"])
        rows = cs.load()
        self.assertEqual(len(rows), 1, "update must not append a second row")
        self.assertEqual(rows[0]["command"], "docker")

    def test_duplicate_name_rejected(self):
        cs.add_or_update({"name": "dup", "transport": "stdio", "command": "a"})
        with self.assertRaises(ValueError) as ctx:
            cs.add_or_update({"name": "dup", "transport": "stdio", "command": "b"})
        self.assertIn("already exists", str(ctx.exception))
        self.assertEqual(len(cs.load()), 1, "the rejected add must not persist")

    def test_toggle_flips_and_persists(self):
        c = cs.add_or_update({"name": "github", "transport": "stdio",
                              "command": "npx", "enabled": True})
        t = cs.toggle(c["id"])
        self.assertFalse(t["enabled"])
        self.assertFalse(cs.load()[0]["enabled"], "toggle must persist")
        t2 = cs.toggle(c["id"])
        self.assertTrue(t2["enabled"])

    def test_toggle_unknown_id_returns_none(self):
        self.assertIsNone(cs.toggle("cx_nope"))

    def test_remove_true_then_false(self):
        c = cs.add_or_update({"name": "github", "transport": "stdio",
                              "command": "npx"})
        self.assertTrue(cs.remove(c["id"]))
        self.assertEqual(cs.load(), [])
        self.assertFalse(cs.remove(c["id"]), "removing a gone id is False, not a raise")

    def test_save_is_atomic_shape(self):
        cs.add_or_update({"name": "github", "transport": "stdio", "command": "npx"})
        data = json.loads(cs.CONNECTORS_PATH.read_text(encoding="utf-8"))
        self.assertIn("connectors", data)
        self.assertIsInstance(data["connectors"], list)


# ------------------------------------------------------- servers fragment ----
class TestFragment(_IsolatedStore):
    def test_only_enabled_are_included_with_correct_shapes(self):
        cs.add_or_update({"name": "gh", "transport": "stdio", "command": "npx",
                          "args": ["-y", "pkg"], "env": {"T": "1"}, "enabled": True})
        cs.add_or_update({"name": "off", "transport": "stdio", "command": "npx",
                          "enabled": False})
        cs.add_or_update({"name": "lin", "transport": "sse",
                          "url": "https://mcp.linear.app/sse", "enabled": True})

        frag = cs.mcp_servers_fragment()
        self.assertEqual(set(frag.keys()), {"gh", "lin"},
                         "disabled connectors must be excluded")
        # stdio shape: command/args/env, NO type key
        self.assertEqual(frag["gh"], {"command": "npx", "args": ["-y", "pkg"],
                                      "env": {"T": "1"}})
        self.assertNotIn("type", frag["gh"])
        # http/sse shape: type + url only
        self.assertEqual(frag["lin"], {"type": "sse",
                                       "url": "https://mcp.linear.app/sse"})

    def test_empty_store_is_empty_fragment(self):
        self.assertEqual(cs.mcp_servers_fragment(), {})


# --------------------------------------------------------------- catalog -----
class TestCatalog(unittest.TestCase):
    EXPECTED = {"github", "filesystem", "slack", "puppeteer", "brave-search",
                "linear"}

    def test_catalog_has_the_six_presets(self):
        names = {e["name"] for e in cs.CATALOG}
        self.assertEqual(names, self.EXPECTED)

    def test_every_entry_has_the_required_keys(self):
        for e in cs.CATALOG:
            self.assertEqual(
                set(e.keys()),
                {"name", "transport", "command", "args", "env_keys", "url",
                 "description"},
                "catalog entry %r has the wrong key set" % e.get("name"))
            self.assertIn(e["transport"], cs.TRANSPORTS)
            self.assertIsInstance(e["env_keys"], list)

    def test_catalog_entries_are_valid_connectors(self):
        # every stdio preset carries a command; the remote one carries a url —
        # i.e. every preset would pass validate() once its secrets are filled.
        for e in cs.CATALOG:
            c = cs.validate({k: e[k] for k in
                             ("name", "transport", "command", "args", "url")})
            self.assertEqual(c["name"], e["name"])

    def test_linear_is_the_remote_sse_example(self):
        lin = next(e for e in cs.CATALOG if e["name"] == "linear")
        self.assertEqual(lin["transport"], "sse")
        self.assertEqual(lin["url"], "https://mcp.linear.app/sse")


# --------------------------------------------------- endpoints + the merge ---
class TestEndpointsAndMerge(_IsolatedStore):
    def test_list_and_upsert_handlers(self):
        self.assertEqual(app.api_connectors(), {"connectors": []})
        out = app.api_connectors_upsert({"name": "github", "transport": "stdio",
                                         "command": "npx"})
        self.assertIn("connector", out)
        self.assertEqual(out["connector"]["name"], "github")
        self.assertEqual(len(app.api_connectors()["connectors"]), 1)

    def test_upsert_bad_input_is_400_error_body(self):
        resp = app.api_connectors_upsert({"name": "BAD NAME",
                                          "transport": "stdio", "command": "x"})
        # JSONResponse, not a dict — assert status + {"error": ...} body
        self.assertEqual(resp.status_code, 400)
        body = json.loads(bytes(resp.body))
        self.assertIn("error", body)

    def test_toggle_handler_404_then_ok(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            app.api_connectors_toggle("cx_nope")
        self.assertEqual(ctx.exception.status_code, 404)
        c = app.api_connectors_upsert({"name": "gh", "transport": "stdio",
                                       "command": "npx"})["connector"]
        toggled = app.api_connectors_toggle(c["id"])
        self.assertEqual(toggled["connector"]["enabled"], not c["enabled"])

    def test_delete_handler_ok_then_404(self):
        from fastapi import HTTPException
        c = app.api_connectors_upsert({"name": "gh", "transport": "stdio",
                                       "command": "npx"})["connector"]
        self.assertEqual(app.api_connectors_delete(c["id"]), {"ok": True})
        with self.assertRaises(HTTPException) as ctx:
            app.api_connectors_delete(c["id"])
        self.assertEqual(ctx.exception.status_code, 404)

    def test_catalog_endpoint(self):
        out = app.api_connectors_catalog()
        self.assertIn("catalog", out)
        self.assertEqual({e["name"] for e in out["catalog"]},
                         TestCatalog.EXPECTED)

    def test_routes_are_registered(self):
        paths = {getattr(r, "path", "") for r in app.app.routes}
        for p in ("/api/connectors", "/api/connectors/{cid}/toggle",
                  "/api/connectors/{cid}", "/api/connectors/catalog"):
            self.assertIn(p, paths, "missing route %s" % p)

    def test_merge_adds_enabled_connector_alongside_sutra(self):
        app.api_connectors_upsert({"name": "lin", "transport": "sse",
                                   "url": "https://mcp.linear.app/sse",
                                   "enabled": True})
        cfg = app._sutra_mcp_config()
        self.assertTrue(cfg, "config must be a non-empty JSON string")
        servers = json.loads(cfg)["mcpServers"]
        self.assertIn("lin", servers, "the enabled connector must be merged")
        self.assertEqual(servers["lin"], {"type": "sse",
                                          "url": "https://mcp.linear.app/sse"})
        # sutra_mcp.py ships in this dir, so sutra is present too.
        if (Path(HERE) / "sutra_mcp.py").is_file():
            self.assertIn("sutra", servers,
                          "sutra's own server must remain in the merged config")

    def test_disabled_connector_is_not_merged(self):
        app.api_connectors_upsert({"name": "off", "transport": "stdio",
                                   "command": "npx", "enabled": False})
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertNotIn("off", servers)

    def test_build_agent_args_spawns_with_zero_connectors(self):
        """The core fail-safe: with NO connectors, build_agent_args still emits a
        working argv — --mcp-config carrying only sutra, plus --strict-mcp-config
        — exactly as before this feature."""
        self.assertEqual(cs.load(), [], "precondition: empty store")
        args = app.build_agent_args("claude", "hello", "plan")
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--mcp-config", args)
        cfg = args[args.index("--mcp-config") + 1]
        servers = json.loads(cfg)["mcpServers"]
        # only sutra when there are no connectors (sutra_mcp.py ships here)
        self.assertEqual(set(servers.keys()), {"sutra"})
        # the message is still passed positionally, unchanged
        self.assertIn("hello", args)

    def test_broken_store_falls_back_to_sutra_only(self):
        """Fail-soft: a corrupt store must not break turn spawning — the merge
        swallows it and falls back to just sutra."""
        cs.CONNECTORS_PATH.write_text("{ corrupt", encoding="utf-8")
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertEqual(set(servers.keys()), {"sutra"})


if __name__ == "__main__":
    # Plain-python entry point so the SHIPPED interpreter (no pytest) can run
    # this directly: electron/payload/python/bin/python3 test_connectors.py -v
    unittest.main()
