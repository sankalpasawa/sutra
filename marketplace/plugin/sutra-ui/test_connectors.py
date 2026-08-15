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
                          "url", "headers", "enabled"})
        self.assertEqual(c["name"], "github")
        self.assertEqual(c["transport"], "stdio")
        self.assertEqual(c["command"], "npx")
        self.assertEqual(c["args"], [])
        self.assertEqual(c["env"], {})
        self.assertEqual(c["url"], "")
        self.assertEqual(c["headers"], {})     # stdio never carries headers
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

    def test_headers_kept_for_remote_sanitised_like_env(self):
        c = cs.validate({"name": "x", "transport": "http",
                         "url": "https://h/mcp",
                         "headers": {"Authorization": "Bearer t", "Blank": None,
                                     "X-Num": 5, "  ": "dropped", 7: "dropped"}})
        # blank-keyed and non-string-keyed entries drop; a None value -> ""; a
        # non-string value is stringified (matches env sanitisation).
        self.assertEqual(c["headers"],
                         {"Authorization": "Bearer t", "Blank": "", "X-Num": "5"})

    def test_headers_dropped_for_stdio(self):
        c = cs.validate({"name": "x", "transport": "stdio", "command": "npx",
                         "headers": {"Authorization": "Bearer t"}})
        self.assertEqual(c["headers"], {}, "headers are meaningless for stdio")


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

    def test_http_headers_are_merged_when_present(self):
        cs.add_or_update({"name": "authed", "transport": "http",
                          "url": "https://h/mcp",
                          "headers": {"Authorization": "Bearer secret"},
                          "enabled": True})
        frag = cs.mcp_servers_fragment()
        self.assertEqual(frag["authed"], {
            "type": "http", "url": "https://h/mcp",
            "headers": {"Authorization": "Bearer secret"}})

    def test_http_without_headers_omits_the_key(self):
        cs.add_or_update({"name": "plain", "transport": "http",
                          "url": "https://h/mcp", "enabled": True})
        frag = cs.mcp_servers_fragment()
        # byte-for-byte the pre-headers shape: no empty headers key
        self.assertEqual(frag["plain"], {"type": "http", "url": "https://h/mcp"})
        self.assertNotIn("headers", frag["plain"])


# --------------------------------------------------------------- catalog -----
# The catalog grew from the original six presets to ~50 verified connectors
# grouped by `category`. EXPECTED is now the WHOLE catalog's name set (computed
# from cs.CATALOG) so the endpoint/normaliser/fallback tests that compare against
# it stay honest as the list evolves. ORIGINAL_SIX is the invariant that the
# first shipped presets are never dropped.
class TestCatalog(unittest.TestCase):
    EXPECTED = {e["name"] for e in cs.CATALOG}
    ORIGINAL_SIX = {"github", "filesystem", "slack", "puppeteer", "brave-search",
                    "linear"}
    # categories are a closed vocabulary — an entry using anything else is a typo.
    CATEGORIES = {"Development", "Data & Databases", "Productivity",
                  "Communication", "Search & Web", "Browser & Automation",
                  "Payments & Business", "Monitoring & Cloud", "Design",
                  "AI & Models", "Utility"}

    def test_catalog_keeps_the_original_presets(self):
        names = {e["name"] for e in cs.CATALOG}
        self.assertTrue(self.ORIGINAL_SIX <= names,
                        "the original six presets must never be dropped")

    def test_catalog_has_at_least_forty_entries(self):
        self.assertGreaterEqual(len(cs.CATALOG), 40,
                                "catalog must ship >= 40 connectors")

    def test_names_are_unique_valid_slugs_and_not_sutra(self):
        names = [e["name"] for e in cs.CATALOG]
        self.assertEqual(len(names), len(set(names)), "duplicate connector names")
        for n in names:
            self.assertRegex(n, cs.NAME_RE, "invalid slug %r" % n)
            self.assertNotEqual(n, cs.RESERVED, '"sutra" is reserved')

    def test_every_entry_has_the_required_keys_and_a_known_category(self):
        for e in cs.CATALOG:
            self.assertEqual(
                set(e.keys()),
                {"name", "title", "category", "transport", "command", "args",
                 "env_keys", "url", "description"},
                "catalog entry %r has the wrong key set" % e.get("name"))
            self.assertIn(e["transport"], cs.TRANSPORTS)
            self.assertIsInstance(e["env_keys"], list)
            self.assertIn(e["category"], self.CATEGORIES,
                          "entry %r has an unknown category %r"
                          % (e["name"], e["category"]))
            self.assertTrue(e["title"], "entry %r has a blank title" % e["name"])
            self.assertLessEqual(len(e["description"]), 150,
                                 "entry %r description exceeds 150 chars" % e["name"])

    def test_every_entry_has_a_resolvable_config(self):
        # stdio -> a command; http|sse -> a url. i.e. every preset would pass
        # validate() (and merge into --mcp-config) once its secrets are filled.
        for e in cs.CATALOG:
            if e["transport"] == "stdio":
                self.assertTrue(e["command"],
                                "stdio entry %r has no command" % e["name"])
                self.assertFalse(e["url"],
                                 "stdio entry %r must not carry a url" % e["name"])
            else:
                self.assertTrue(e["url"],
                                "%s entry %r has no url" % (e["transport"], e["name"]))
                self.assertFalse(e["command"],
                                 "remote entry %r must not carry a command" % e["name"])
            c = cs.validate({k: e[k] for k in
                             ("name", "transport", "command", "args", "url")})
            self.assertEqual(c["name"], e["name"])

    def test_breadth_across_categories(self):
        # a directory that groups connectors is only useful if the groups are
        # populated — require most categories to have at least one entry.
        present = {e["category"] for e in cs.CATALOG}
        self.assertGreaterEqual(len(present), 10,
                                "connectors should span >= 10 categories")

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
                  "/api/connectors/{cid}", "/api/connectors/catalog",
                  "/api/connectors/registry", "/api/connectors/claude-import"):
            self.assertIn(p, paths, "missing route %s" % p)

    def test_merge_carries_http_headers_into_the_config(self):
        app.api_connectors_upsert({"name": "authed", "transport": "http",
                                   "url": "https://h/mcp",
                                   "headers": {"Authorization": "Bearer secret"},
                                   "enabled": True})
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertEqual(servers["authed"], {
            "type": "http", "url": "https://h/mcp",
            "headers": {"Authorization": "Bearer secret"}})

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


# --------------------------------------------------- live registry (pure) ----
# A fabricated registry page — the exact shape the official registry returns —
# exercised through the network-free normaliser. NO test here touches the wire.
_REGISTRY_PAGE = {
    "servers": [
        # remote streamable-http -> transport "http"
        {"server": {"name": "com.example/remote-http", "title": "Remote HTTP",
                    "description": "an http one", "version": "1.0.0",
                    "remotes": [{"type": "streamable-http",
                                 "url": "https://x/mcp"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # remote sse -> transport "sse"
        {"server": {"name": "com.example/remote-sse", "version": "2.0.0",
                    "remotes": [{"type": "sse", "url": "https://x/sse"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # npm package -> npx -y <id> + pkg args, env_keys from environmentVariables
        {"server": {"name": "io.github.foo/npm-server", "version": "1.2.3",
                    "packages": [{"registryType": "npm", "identifier": "@foo/mcp",
                                  "packageArguments": [{"value": "--flag"},
                                                       {"valueHint": "PATH"}],
                                  "environmentVariables": [{"name": "FOO_TOKEN"}]}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # pypi package -> uvx <id> + pkg args
        {"server": {"name": "org/py-server", "version": "0.1.0",
                    "packages": [{"registryType": "pypi", "identifier": "py-mcp",
                                  "packageArguments": [{"value": "serve"}]}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # oci package -> docker run -i --rm <id> (pkg args intentionally ignored)
        {"server": {"name": "org/oci-server", "version": "1.0.0",
                    "packages": [{"registryType": "oci",
                                  "identifier": "ghcr.io/x/img:latest",
                                  "packageArguments": [{"value": "ignored"}]}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # dedup: same server.name twice; isLatest wins -> url of the 2.0.0 row
        {"server": {"name": "dup/multi", "version": "1.0.0",
                    "remotes": [{"type": "streamable-http", "url": "https://old"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": False}}},
        {"server": {"name": "dup/multi", "version": "2.0.0",
                    "remotes": [{"type": "streamable-http", "url": "https://new"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
        # unusable: neither remote nor package -> skipped
        {"server": {"name": "bad/empty", "version": "1.0.0"}},
        # unusable: a package type we have no launcher for -> skipped
        {"server": {"name": "bad/unknown-pkg", "version": "1.0.0",
                    "packages": [{"registryType": "cargo", "identifier": "x"}]}},
        # slug would be the reserved "sutra" -> skipped
        {"server": {"name": "reserved/sutra", "version": "1.0.0",
                    "remotes": [{"type": "sse", "url": "https://s"}]}},
    ]
}


class TestRegistryNormalize(unittest.TestCase):
    def setUp(self):
        self.by_name = {r["name"]: r
                        for r in cs.normalize_registry_servers(_REGISTRY_PAGE["servers"])}

    def test_installable_servers_survive_unusable_are_dropped(self):
        self.assertEqual(
            set(self.by_name),
            {"remote-http", "remote-sse", "npm-server", "py-server",
             "oci-server", "multi"},
            "empty/unknown-package/sutra rows must be dropped")

    def test_result_shape_matches_catalog(self):
        keys = {"name", "title", "description", "transport", "command", "args",
                "env_keys", "url"}
        for r in self.by_name.values():
            self.assertEqual(set(r), keys, "%r has the wrong key set" % r["name"])

    def test_remote_http_and_sse(self):
        h = self.by_name["remote-http"]
        self.assertEqual((h["transport"], h["url"]), ("http", "https://x/mcp"))
        self.assertEqual(h["command"], "")
        self.assertEqual(h["args"], [])
        self.assertEqual(h["title"], "Remote HTTP")
        s = self.by_name["remote-sse"]
        self.assertEqual((s["transport"], s["url"]), ("sse", "https://x/sse"))

    def test_npm_package_command_args_env(self):
        n = self.by_name["npm-server"]
        self.assertEqual(n["transport"], "stdio")
        self.assertEqual(n["command"], "npx")
        self.assertEqual(n["args"], ["-y", "@foo/mcp", "--flag", "PATH"])
        self.assertEqual(n["env_keys"], ["FOO_TOKEN"])

    def test_pypi_and_oci_commands(self):
        p = self.by_name["py-server"]
        self.assertEqual((p["command"], p["args"]), ("uvx", ["py-mcp", "serve"]))
        o = self.by_name["oci-server"]
        self.assertEqual((o["command"], o["args"]),
                         ("docker", ["run", "-i", "--rm", "ghcr.io/x/img:latest"]))

    def test_dedup_keeps_the_latest_version(self):
        self.assertEqual(self.by_name["multi"]["url"], "https://new",
                         "isLatest row (v2.0.0) must win the dedup")

    def test_garbage_input_is_empty_not_a_raise(self):
        for junk in (None, {}, "nope", [None, 5, {"server": "x"}, {"noserver": 1}]):
            self.assertEqual(cs.normalize_registry_servers(junk), [])

    def test_slug_rules(self):
        self.assertEqual(cs._slug_from_registry_name("io.github.o/My_Server-1"),
                         "my_server-1")
        self.assertEqual(cs._slug_from_registry_name("x/--weird..name"),
                         "weird--name")
        self.assertIsNone(cs._slug_from_registry_name("reserved/sutra"))
        self.assertIsNone(cs._slug_from_registry_name("x/!!!"))  # nothing valid left
        self.assertEqual(len(cs._slug_from_registry_name("x/" + "a" * 80)), 39)


class TestCatalogNormalized(unittest.TestCase):
    def test_builtin_catalog_maps_to_result_shape(self):
        norm = cs.catalog_normalized()
        self.assertEqual({r["name"] for r in norm}, TestCatalog.EXPECTED)
        keys = {"name", "title", "description", "transport", "command", "args",
                "env_keys", "url"}
        for r in norm:
            self.assertEqual(set(r), keys)
            self.assertTrue(r["title"], "title falls back to name, never blank")


class TestRegistryEndpointFailSoft(_IsolatedStore):
    """The endpoint's fail-soft contract, driven by monkeypatching the fetch so
    NO test here needs the network."""

    def setUp(self):
        super().setUp()
        self._saved_fetch = cs.fetch_registry
        self.addCleanup(lambda: setattr(cs, "fetch_registry", self._saved_fetch))

    def test_success_returns_registry_source(self):
        cs.fetch_registry = lambda q="", limit=20: _REGISTRY_PAGE["servers"]
        out = app.api_connectors_registry(q="db", limit=20)
        self.assertEqual(out["source"], "registry")
        self.assertIn("remote-http", {r["name"] for r in out["results"]})

    def test_network_error_falls_back_to_builtin(self):
        def boom(q="", limit=20):
            raise OSError("network down")
        cs.fetch_registry = boom
        out = app.api_connectors_registry()
        self.assertEqual(out["source"], "builtin")
        self.assertEqual({r["name"] for r in out["results"]},
                         TestCatalog.EXPECTED)

    def test_zero_results_falls_back_to_builtin(self):
        cs.fetch_registry = lambda q="", limit=20: []
        out = app.api_connectors_registry(q="nothing-matches")
        self.assertEqual(out["source"], "builtin")
        self.assertEqual({r["name"] for r in out["results"]},
                         TestCatalog.EXPECTED)


class TestClaudeImport(_IsolatedStore):
    def test_normalize_infers_transport_and_skips_sutra(self):
        conns = cs.normalize_claude_mcp_servers({
            "myhttp": {"type": "http", "url": "https://h/mcp",
                       "headers": {"Authorization": "Bearer x"}},
            "mysse": {"type": "sse", "url": "https://h/sse"},
            "mystdio": {"command": "npx", "args": ["-y", "pkg"], "env": {"K": "v"}},
            "urlonly": {"url": "https://u"},          # no type -> http
            "sutra": {"command": "x"},                # reserved -> skipped
            "empty": {},                              # no url/command -> skipped
            "notadict": "nope",                       # bad spec -> skipped
        })
        by = {c["name"]: c for c in conns}
        self.assertEqual(set(by), {"myhttp", "mysse", "mystdio", "urlonly"})
        self.assertTrue(all(c["enabled"] is False for c in conns),
                        "imported connectors are never auto-enabled")

        self.assertEqual(by["myhttp"]["transport"], "http")
        self.assertEqual(by["myhttp"]["url"], "https://h/mcp")
        self.assertEqual(by["myhttp"]["headers"], {"Authorization": "Bearer x"})
        self.assertEqual(by["mysse"]["transport"], "sse")
        self.assertEqual(by["urlonly"]["transport"], "http")

        st = by["mystdio"]
        self.assertEqual(st["transport"], "stdio")
        self.assertEqual(st["command"], "npx")
        self.assertEqual(st["args"], ["-y", "pkg"])
        self.assertEqual(st["env"], {"K": "v"})
        self.assertEqual(st["headers"], {}, "stdio import carries no headers")

    def test_normalize_garbage_is_empty(self):
        for junk in (None, [], "x", {"": {"command": "x"}}):
            self.assertEqual(cs.normalize_claude_mcp_servers(junk), [])

    def test_endpoint_reads_the_file_and_is_fail_soft(self):
        # point the reader at a temp ~/.claude.json via the env override
        saved = os.environ.get("SUTRA_UI_CLAUDE_JSON")
        cj = self.dir / "claude.json"
        cj.write_text(json.dumps({"mcpServers": {
            "gh": {"command": "npx", "args": ["-y", "server-github"]}}}),
            encoding="utf-8")
        os.environ["SUTRA_UI_CLAUDE_JSON"] = str(cj)
        try:
            out = app.api_connectors_claude_import()
            self.assertEqual([c["name"] for c in out["connectors"]], ["gh"])
            self.assertEqual(out["connectors"][0]["transport"], "stdio")
            # missing file -> empty list, never a raise
            os.environ["SUTRA_UI_CLAUDE_JSON"] = str(self.dir / "gone.json")
            self.assertEqual(app.api_connectors_claude_import(),
                             {"connectors": []})
        finally:
            if saved is None:
                os.environ.pop("SUTRA_UI_CLAUDE_JSON", None)
            else:
                os.environ["SUTRA_UI_CLAUDE_JSON"] = saved


# Real `claude mcp list` output captured 2026-08-15 (claude v2.1.212). The banner
# goes to stdout ahead of the rows; one server needs auth, two are connected.
_MCP_LIST_FIXTURE = (
    "Checking MCP server health…\n"
    "\n"
    "claude.ai Atlassian Rovo: https://mcp.atlassian.com/v1/mcp - ! Needs authentication\n"
    "claude.ai Google Drive: https://drivemcp.googleapis.com/mcp/v1 - ✔ Connected\n"
    "claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - ✔ Connected\n"
)


class TestParseClaudeMcpList(unittest.TestCase):
    """Pure, network-free parser for `claude mcp list` (codex risk #1: the
    output is human text, not a contract — parse best-effort, skip junk)."""

    def test_parses_the_real_fixture(self):
        rows = cs.parse_claude_mcp_list(_MCP_LIST_FIXTURE)
        self.assertEqual([r["name"] for r in rows],
                         ["claude.ai Atlassian Rovo", "claude.ai Google Drive",
                          "claude.ai Gmail"])
        self.assertEqual(rows[1]["url"], "https://drivemcp.googleapis.com/mcp/v1")
        self.assertEqual(rows[1]["transport"], "http")

    def test_state_classification(self):
        rows = cs.parse_claude_mcp_list(_MCP_LIST_FIXTURE)
        by = {r["name"]: r["state"] for r in rows}
        self.assertEqual(by["claude.ai Atlassian Rovo"], "needs_auth")
        self.assertEqual(by["claude.ai Google Drive"], "connected")

    def test_banner_blanks_and_junk_are_skipped(self):
        rows = cs.parse_claude_mcp_list(
            "Checking MCP server health…\n\nnot a server line\n"
            "ok: https://h/mcp - ✔ Connected\n")
        self.assertEqual([r["name"] for r in rows], ["ok"])

    def test_stdio_target_is_not_a_url(self):
        rows = cs.parse_claude_mcp_list("fs: npx -y server - ✔ Connected\n")
        self.assertEqual(rows[0]["transport"], "stdio")
        self.assertEqual(rows[0]["url"], "")
        self.assertEqual(rows[0]["target"], "npx -y server")

    def test_ansi_colour_codes_are_stripped(self):
        rows = cs.parse_claude_mcp_list(
            "\x1b[32mok\x1b[0m: https://h/mcp - \x1b[32m✔ Connected\x1b[0m\n")
        self.assertEqual(rows[0]["name"], "ok")
        self.assertEqual(rows[0]["state"], "connected")

    def test_empty_input_is_empty_never_raises(self):
        self.assertEqual(cs.parse_claude_mcp_list(""), [])
        self.assertEqual(cs.parse_claude_mcp_list(None), [])


class TestClaudeConfigured(unittest.TestCase):
    """claude_configured() must be fail-soft (never raise) and cached (codex
    risk #2: a health-checking CLI must not tie render speed to live health)."""

    def setUp(self):
        self._saved_run = cs.subprocess.run
        cs._CLAUDE_LIST_CACHE["ts"] = 0.0
        cs._CLAUDE_LIST_CACHE["payload"] = None

    def tearDown(self):
        cs.subprocess.run = self._saved_run
        cs._CLAUDE_LIST_CACHE["ts"] = 0.0
        cs._CLAUDE_LIST_CACHE["payload"] = None

    def _fake_run(self, stdout="", returncode=0, stderr="", exc=None, counter=None):
        class _R:
            pass
        def run(*a, **k):
            if counter is not None:
                counter.append(1)
            if exc is not None:
                raise exc
            r = _R(); r.stdout = stdout; r.stderr = stderr; r.returncode = returncode
            return r
        return run

    def test_missing_binary_is_fail_soft(self):
        cs.subprocess.run = self._fake_run(exc=FileNotFoundError())
        out = cs.claude_configured(force=True)
        self.assertEqual(out["connectors"], [])
        self.assertIn("claude", out["error"])

    def test_timeout_is_fail_soft(self):
        cs.subprocess.run = self._fake_run(
            exc=cs.subprocess.TimeoutExpired(cmd="claude", timeout=10))
        out = cs.claude_configured(force=True)
        self.assertEqual(out["connectors"], [])
        self.assertIn("timed out", out["error"])

    def test_success_parses_and_caches(self):
        calls = []
        cs.subprocess.run = self._fake_run(stdout=_MCP_LIST_FIXTURE, counter=calls)
        first = cs.claude_configured(force=True)
        self.assertIsNone(first["error"])
        self.assertEqual(len(first["connectors"]), 3)
        # second call within TTL must be served from cache — no second shell.
        second = cs.claude_configured()
        self.assertEqual(len(second["connectors"]), 3)
        self.assertEqual(len(calls), 1, "TTL cache must avoid a second `claude` shell")

    def test_endpoint_shape(self):
        cs.subprocess.run = self._fake_run(stdout=_MCP_LIST_FIXTURE)
        out = app.api_connectors_configured()
        self.assertIn("connectors", out)
        self.assertIn("error", out)
        self.assertIn("stale", out)


if __name__ == "__main__":
    # Plain-python entry point so the SHIPPED interpreter (no pytest) can run
    # this directly: electron/payload/python/bin/python3 test_connectors.py -v
    unittest.main()
