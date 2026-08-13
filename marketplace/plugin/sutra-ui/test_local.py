"""Unit tests for the LOCAL connector (local_store + app endpoints).

Same technique as test_composio.py, and for the same reason: no server, no
network, no extra deps, so the suite runs under the SHIPPED interpreter
(electron/payload/python/bin/python3), which carries fastapi/starlette but not
httpx/pytest.

Run (bundled interpreter, no pytest):
    electron/payload/python/bin/python3 test_local.py -v
Run (dev venv, same as the rest of the suite):
    .venv/bin/python -m unittest test_local -v

THE NETWORK IS NEVER TOUCHED. local_store reuses composio_store's single HTTP
funnel (`cx._http_json`), so replacing that one function covers the registry AND
the npm version check, and the tests still exercise real request-building,
error-translating and caching code.

NEITHER IS `npx`. preflight() shells out to shutil.which, which every test that
cares about the merge stubs, so a CI box without Node produces the same result
as a developer laptop with it.

Isolation: local_store writes THREE files (STORE_PATH, the derived 1MCP
mcp.json under ONEMCP_DIR, and REGISTRY_CACHE) and reads composio_store's
catalog for its category lookups. Every one is repointed at a fresh tempdir and
restored.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app  # noqa: E402
import composio_store as cx  # noqa: E402
import local_store as lx  # noqa: E402


class _Isolated(unittest.TestCase):
    def setUp(self):
        self._saved = (lx.STORE_PATH, lx.ONEMCP_DIR, lx.REGISTRY_CACHE,
                       cx.STORE_PATH, cx.CATALOG_PATH, cx._http_json,
                       lx.shutil.which)
        self.dir = Path(tempfile.mkdtemp(prefix="sutra-test-local-"))
        lx.STORE_PATH = self.dir / "local.json"
        lx.ONEMCP_DIR = self.dir / "1mcp"
        lx.REGISTRY_CACHE = self.dir / "mcp-registry.json"
        cx.STORE_PATH = self.dir / "composio.json"
        cx.CATALOG_PATH = self.dir / "composio-catalog.json"
        self.assertIs(app.local_store, lx,
                      "app must share the local_store module")
        # Default: a machine that CAN run the aggregator. Tests that care about
        # the other case override this explicitly.
        lx.shutil.which = lambda b: "/usr/bin/" + b

    def tearDown(self):
        (lx.STORE_PATH, lx.ONEMCP_DIR, lx.REGISTRY_CACHE,
         cx.STORE_PATH, cx.CATALOG_PATH, cx._http_json,
         lx.shutil.which) = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def fake_http(self, *answers):
        self.calls = []
        seq = list(answers)

        def _fake(method, url, headers=None, body=None, timeout=None):
            self.calls.append((method, url, dict(headers or {}), body))
            ans = seq.pop(0) if len(seq) > 1 else seq[0]
            if isinstance(ans, Exception):
                raise ans
            return ans

        cx._http_json = _fake

    def add(self, **kw):
        base = {"name": "filesystem", "transport": "stdio", "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "~/work"]}
        base.update(kw)
        return lx.add_or_update(base)

    def onemcp(self):
        return json.loads(lx.config_path().read_text())

    def composio_session(self, url="https://x/mcp"):
        """A hosted connector with a LIVE cached session.

        Two steps, not one: the fingerprint is computed from the saved store, so
        building it inline against a store that has not been written yet stamps
        the fingerprint of the EMPTY store — which reads as stale and sends
        provision() to the network. Also stubs HTTP, so a regression here fails
        as a mismatch rather than as a slow test that quietly went online."""
        self.fake_http((201, {"session_id": "trs_1",
                              "mcp": {"type": "http", "url": url}}, {}))
        cx.save({"api_key": "ak_k", "user_id": "u", "enabled": ["gmail"],
                 "session": {}})
        store = cx.load()
        store["session"] = {"session_id": "trs_1", "url": url, "type": "http",
                            "fingerprint": cx._fingerprint(store),
                            "created_at": time.time()}
        cx.save(store)


# ========================================================== validation ======
class TestValidate(_Isolated):
    def test_minimal_stdio_normalises_every_field(self):
        s = lx.validate({"name": "git", "transport": "stdio", "command": "uvx"})
        self.assertEqual(set(s), {"id", "name", "title", "tag", "transport",
                                  "command", "args", "env", "url", "headers",
                                  "enabled"})
        self.assertEqual(s["args"], [])
        self.assertEqual(s["env"], {})
        self.assertEqual(s["headers"], {})
        self.assertTrue(s["enabled"])

    def test_reserved_names_are_refused(self):
        """sutra is the panel's own server, composio is the hosted connector,
        local is this aggregator. Any of the three would shadow something."""
        for name in ("sutra", "composio", "local"):
            with self.assertRaises(ValueError):
                lx.validate({"name": name, "transport": "stdio", "command": "x"})

    def test_transport_field_rules(self):
        with self.assertRaises(ValueError):     # stdio needs a command
            lx.validate({"name": "a", "transport": "stdio"})
        with self.assertRaises(ValueError):     # http needs a url
            lx.validate({"name": "a", "transport": "http"})
        with self.assertRaises(ValueError):     # unknown transport
            lx.validate({"name": "a", "transport": "carrier-pigeon"})

    def test_headers_only_ride_a_remote_transport(self):
        s = lx.validate({"name": "a", "transport": "stdio", "command": "x",
                         "headers": {"Authorization": "Bearer t"}})
        self.assertEqual(s["headers"], {})
        s = lx.validate({"name": "a", "transport": "http", "url": "https://x",
                         "headers": {"Authorization": "Bearer t"}})
        self.assertEqual(s["headers"], {"Authorization": "Bearer t"})

    def test_non_string_args_are_dropped_not_stringified(self):
        """Passing the text "None" to a subprocess is worse than passing
        nothing."""
        s = lx.validate({"name": "a", "transport": "stdio", "command": "x",
                         "args": ["-y", None, 7, "pkg"]})
        self.assertEqual(s["args"], ["-y", "pkg"])


# =========================================================== assorting ======
class TestCategorisation(_Isolated):
    def test_composio_catalog_supplies_the_category_when_the_slug_matches(self):
        """The point of the shared taxonomy: `github` is "developer tools" in
        BOTH connectors, so the two halves of the screen assort into one
        system."""
        cx._write_json(cx.CATALOG_PATH, {"toolkits": [
            {"slug": "github", "name": "GitHub", "category": "developer tools",
             "tools": 893, "triggers": 20}], "checked_at": time.time()})
        tag, source = lx._slug_category("github", "GitHub", "repos")
        self.assertEqual(tag, "developer-tools")
        self.assertEqual(source, "composio")

    def test_unknown_slug_falls_back_to_the_heuristic_and_says_so(self):
        cx._write_json(cx.CATALOG_PATH, {"toolkits": [], "checked_at": time.time()})
        tag, source = lx._slug_category(
            "chromium-thing", "Chromium Driver", "Drive a headless browser")
        self.assertEqual(tag, "browser-automation")
        self.assertEqual(source, "guess")

    def test_the_heuristic_prefers_no_answer_to_a_wrong_one(self):
        self.assertEqual(lx._guess_category("zork", "Zork", "a grue lives here"),
                         "other")

    def test_the_name_alone_is_enough_to_assort(self):
        """Regression: the add form leaves title and description blank, so a
        heuristic reading only those filed `git` and `filesystem` — the two most
        obvious cases in the table — under "other"."""
        cx._write_json(cx.CATALOG_PATH, {"toolkits": [], "checked_at": time.time()})
        for name, want in (("filesystem", "filesystem"),
                           ("git", "developer-tools"),
                           ("sqlite", "databases"),
                           ("playwright", "browser-automation")):
            srv = lx.validate({"name": name, "transport": "stdio", "command": "x"})
            self.assertEqual(srv["tag"], want, name)

    def test_a_broken_composio_catalog_does_not_break_categorisation(self):
        cx.CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cx.CATALOG_PATH.write_text("{{{ not json")
        tag, source = lx._slug_category("x", "Postgres tool", "run sql")
        self.assertEqual(source, "guess")
        self.assertEqual(tag, "databases")

    def test_category_strings_become_valid_tags(self):
        self.assertEqual(lx._slugify_tag("Images & Design"), "images-design")
        self.assertEqual(lx._slugify_tag(""), "other")
        self.assertEqual(lx._slugify_tag("!!!"), "other")

    def test_an_explicit_tag_beats_the_lookup(self):
        """A guess that is wrong must be fixable, not an argument."""
        s = lx.validate({"name": "a", "transport": "stdio", "command": "x",
                         "tag": "My Custom Group"})
        self.assertEqual(s["tag"], "my-custom-group")

    def test_state_groups_servers_by_tag(self):
        self.add(name="filesystem", tag="files")
        self.add(name="git", command="uvx", args=["mcp-server-git"], tag="developer-tools")
        self.add(name="gitlab", command="npx", args=["-y", "x"], tag="developer-tools")
        groups = {g["tag"]: len(g["servers"]) for g in lx.state()["groups"]}
        self.assertEqual(groups, {"files": 1, "developer-tools": 2})


# =============================================================== store ======
class TestStore(_Isolated):
    def test_missing_file_reads_blank_never_raises(self):
        st = lx.load()
        self.assertEqual(st["servers"], [])
        self.assertEqual(st["agent"]["version"], lx.AGENT_FALLBACK_VERSION)

    def test_corrupt_file_reads_blank_never_raises(self):
        lx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lx.STORE_PATH.write_text("{ not json")
        self.assertEqual(lx.load()["servers"], [])

    def test_one_bad_row_is_dropped_not_the_whole_set(self):
        cx._write_json(lx.STORE_PATH, {"servers": [
            {"name": "good", "transport": "stdio", "command": "npx"},
            {"name": "NOT VALID", "transport": "stdio", "command": "npx"},
            {"name": "alsogood", "transport": "http", "url": "https://x/mcp"}]})
        self.assertEqual([s["name"] for s in lx.load()["servers"]],
                         ["good", "alsogood"])

    def test_duplicate_name_is_refused(self):
        self.add(name="filesystem")
        with self.assertRaises(ValueError):
            self.add(name="filesystem")

    def test_toggle_and_remove(self):
        s = self.add()
        self.assertFalse(lx.toggle(s["id"])["enabled"])
        self.assertTrue(lx.toggle(s["id"])["enabled"])
        self.assertTrue(lx.remove(s["id"]))
        self.assertFalse(lx.remove(s["id"]))
        self.assertIsNone(lx.toggle("lx_nosuchthing"))

    def test_retag_moves_a_server(self):
        s = self.add(tag="other")
        self.assertEqual(lx.retag(s["id"], "Developer Tools")["tag"],
                         "developer-tools")
        self.assertIsNone(lx.retag("lx_nope", "x"))

    def test_server_cap_is_enforced(self):
        for i in range(lx.MAX_SERVERS):
            self.add(name="srv%d" % i)
        with self.assertRaises(ValueError):
            self.add(name="onemore")

    def test_filter_rejects_anything_that_is_not_a_tag_expression(self):
        """This lands in an argv slot."""
        for bad in ("web; rm -rf /", "$(whoami)", "`id`"):
            with self.assertRaises(ValueError):
                lx.set_options(filter_=bad)
        self.assertEqual(lx.set_options(filter_="web,api")["filter"], "web,api")


# ================================================= derived 1MCP config ======
class TestOneMcpConfig(_Isolated):
    def test_config_is_written_on_every_mutation(self):
        """Store and mcp.json must never be written apart: a store that says
        enabled while mcp.json does not list it is a panel that lies about what
        the next turn can reach."""
        self.add()
        cfg = self.onemcp()
        self.assertIn("filesystem", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["filesystem"]["command"], "npx")

    def test_disabled_servers_are_omitted(self):
        s = self.add()
        lx.toggle(s["id"])
        self.assertEqual(self.onemcp()["mcpServers"], {})

    def test_every_server_carries_its_tag_as_real_1mcp_config(self):
        """The assorting is not a UI label — `tags` is the field upstream
        describes as "Tags for filtering and organizing servers", and it is what
        --filter narrows on."""
        self.add(tag="developer-tools")
        self.assertEqual(
            self.onemcp()["mcpServers"]["filesystem"]["tags"], ["developer-tools"])

    def test_remote_servers_carry_url_and_headers(self):
        self.add(name="remote", transport="http", command="", args=[],
                 url="https://x/mcp", headers={"Authorization": "Bearer t"})
        spec = self.onemcp()["mcpServers"]["remote"]
        self.assertEqual(spec["type"], "http")
        self.assertEqual(spec["headers"], {"Authorization": "Bearer t"})

    def test_routing_composio_puts_the_hosted_endpoint_inside_the_aggregator(self):
        self.composio_session("https://app.composio.dev/x/mcp")
        lx.set_options(route_composio=True)
        spec = self.onemcp()["mcpServers"]["composio"]
        self.assertEqual(spec["url"], "https://app.composio.dev/x/mcp")
        self.assertEqual(spec["tags"], ["hosted"])

    def test_a_failing_hosted_connector_does_not_break_the_config_write(self):
        lx.set_options(route_composio=True)   # no composio credentials at all
        self.assertEqual(self.onemcp()["mcpServers"], {})


# =============================================================== merge ======
class TestMcpFragment(_Isolated):
    def test_nothing_enabled_is_an_empty_fragment(self):
        self.assertEqual(lx.mcp_servers_fragment(), {})

    def test_one_process_however_many_servers(self):
        """The whole point of the aggregator: N servers, ONE entry in the
        session's MCP config and ONE tool namespace."""
        self.add(name="filesystem")
        self.add(name="git", command="uvx", args=["mcp-server-git"])
        self.add(name="playwright", command="npx", args=["-y", "@playwright/mcp"])
        frag = lx.mcp_servers_fragment()
        self.assertEqual(list(frag), ["local"])
        self.assertEqual(frag["local"]["command"], "npx")
        self.assertEqual(len(self.onemcp()["mcpServers"]), 3)

    def test_the_aggregator_version_is_pinned_into_the_argv(self):
        """An unpinned `npx -y @1mcp/agent` could resolve something new between
        two turns of one session, swapping the process fronting every tool."""
        self.add()
        args = lx.mcp_servers_fragment()["local"]["args"]
        self.assertEqual(args[0], "-y")
        self.assertEqual(args[1], "%s@%s" % (lx.AGENT_PKG, lx.AGENT_FALLBACK_VERSION))
        self.assertIn("serve", args)
        self.assertIn("--transport=stdio", args)
        self.assertIn(str(lx.config_path()), args)

    def test_a_filter_reaches_the_command_line(self):
        self.add(tag="developer-tools")
        lx.set_options(filter_="developer-tools")
        args = lx.mcp_servers_fragment()["local"]["args"]
        self.assertEqual(args[args.index("--filter") + 1], "developer-tools")

    def test_no_filter_means_no_flag(self):
        self.add()
        self.assertNotIn("--filter", lx.mcp_servers_fragment()["local"]["args"])

    def test_a_machine_without_node_gets_no_aggregator(self):
        """Better nothing than a connector that says enabled and silently
        produces no tools."""
        self.add()
        lx.shutil.which = lambda b: None
        self.assertEqual(lx.mcp_servers_fragment(), {})
        pf = lx.preflight()
        self.assertFalse(pf["runnable"])
        self.assertIn("npx", pf["reason"])

    def test_routing_composio_alone_is_enough_to_start_the_aggregator(self):
        self.composio_session()
        lx.set_options(route_composio=True)
        self.assertEqual(list(lx.mcp_servers_fragment()), ["local"])

    def test_a_deleted_config_file_is_re_derived_on_the_hot_path(self):
        self.add()
        lx.config_path().unlink()
        lx.mcp_servers_fragment()
        self.assertTrue(lx.config_path().is_file())

    def test_a_broken_store_degrades_the_turn_it_does_not_break_it(self):
        lx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lx.STORE_PATH.write_text("{{{")
        self.assertEqual(lx.mcp_servers_fragment(), {})


class TestAppMerge(_Isolated):
    """app._sutra_mcp_config is what actually reaches the CLI."""

    def test_three_servers_at_most_however_much_is_configured(self):
        """Both connectors aggregate, so the merged config cannot grow with the
        number of services."""
        self.composio_session()
        for i in range(6):
            self.add(name="srv%d" % i)
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertEqual(sorted(servers), ["composio", "local", "sutra"])

    def test_routing_omits_the_direct_composio_entry(self):
        """Emitting both would give the session the same toolkits twice, under
        two namespaces."""
        self.composio_session()
        self.add()
        lx.set_options(route_composio=True)
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertEqual(sorted(servers), ["local", "sutra"])
        self.assertIn("composio", self.onemcp()["mcpServers"])

    def test_one_broken_connector_does_not_cost_the_other(self):
        self.composio_session()
        lx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lx.STORE_PATH.write_text("{{{ broken")
        servers = json.loads(app._sutra_mcp_config())["mcpServers"]
        self.assertIn("composio", servers)
        self.assertNotIn("local", servers)


# ============================================================ registry ======
REG_PAYLOAD = {"servers": [
    {"server": {"name": "io.github.acme/postgres-mcp", "title": "Postgres MCP",
                "description": "Query a Postgres database over SQL",
                "version": "1.2.0",
                "packages": [{"registryType": "npm", "identifier": "postgres-mcp",
                              "environmentVariables": [{"name": "PG_URL"}]}]},
     "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": True}}},
    {"server": {"name": "io.github.acme/postgres-mcp", "title": "Postgres MCP",
                "description": "old", "version": "1.0.0",
                "packages": [{"registryType": "npm", "identifier": "postgres-mcp"}]},
     "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": False}}},
    {"server": {"name": "com.example/remote", "title": "Remote Thing",
                "description": "a hosted endpoint", "version": "1.0.0",
                "remotes": [{"type": "streamable-http", "url": "https://r/mcp"}]}},
    {"server": {"name": "com.example/unlaunchable", "title": "Nope",
                "description": "x", "version": "1.0.0",
                "packages": [{"registryType": "cargo", "identifier": "nope"}]}},
    {"server": {"name": "com.example/sutra"}},   # collides with a reserved key
    "not a dict",
]}


class TestRegistry(_Isolated):
    def test_normalises_dedupes_and_assorts(self):
        rows = lx.normalize_registry(REG_PAYLOAD["servers"])
        by = {r["name"]: r for r in rows}
        self.assertEqual(sorted(by), ["postgres-mcp", "remote"])
        pg = by["postgres-mcp"]
        self.assertEqual(pg["transport"], "stdio")
        self.assertEqual(pg["command"], "npx")
        self.assertEqual(pg["args"], ["-y", "postgres-mcp"])
        self.assertEqual(pg["env_keys"], ["PG_URL"])
        self.assertEqual(pg["tag"], "databases")       # assorted
        self.assertEqual(pg["description"], "Query a Postgres database over SQL")
        self.assertEqual(by["remote"]["transport"], "http")
        self.assertEqual(by["remote"]["url"], "https://r/mcp")

    def test_unlaunchable_and_reserved_entries_are_skipped(self):
        names = [r["name"] for r in lx.normalize_registry(REG_PAYLOAD["servers"])]
        self.assertNotIn("unlaunchable", names)   # no launcher for cargo
        self.assertNotIn("sutra", names)          # reserved key

    def test_garbage_input_is_empty_not_an_exception(self):
        for bad in (None, {}, "", 7):
            self.assertEqual(lx.normalize_registry(bad), [])

    def test_browse_caches_the_default_page_but_never_a_search(self):
        """A cached search is a stale answer to a question just asked."""
        self.fake_http((200, REG_PAYLOAD, {}))
        lx.browse()
        self.assertEqual(len(self.calls), 1)
        lx.browse()                                    # cached
        self.assertEqual(len(self.calls), 1)
        lx.browse(q="postgres")                        # searches go to the wire
        self.assertEqual(len(self.calls), 2)
        self.assertIn("search=postgres", self.calls[1][1])

    def test_browse_degrades_to_the_last_good_page(self):
        self.fake_http((200, REG_PAYLOAD, {}))
        lx.browse()
        cached = json.loads(lx.REGISTRY_CACHE.read_text())
        cached["fetched_at"] = time.time() - lx.REGISTRY_TTL - 1
        lx.REGISTRY_CACHE.write_text(json.dumps(cached))

        self.fake_http(urllib.error.URLError("offline"))
        out = lx.browse()
        self.assertEqual(out["source"], "stale")
        self.assertIn("could not reach", out["error"])
        self.assertEqual(len(out["results"]), 2, "kept the copy we had")

    def test_an_http_error_is_reported_not_raised(self):
        self.fake_http((503, None, {}))
        out = lx.browse(q="x")
        self.assertEqual(out["results"], [])
        self.assertIn("503", out["error"])


# ================================================== aggregator updating =====
class TestAgentVersion(_Isolated):
    def test_adopts_npms_latest_and_reports_the_move(self):
        self.fake_http((200, {"name": lx.AGENT_PKG, "version": "9.9.9"}, {}))
        r = lx.refresh_agent(force=True)
        self.assertTrue(r["checked"] and r["updated"])
        self.assertEqual(r["from"], lx.AGENT_FALLBACK_VERSION)
        self.assertEqual(lx.load()["agent"]["version"], "9.9.9")
        self.assertIn("registry.npmjs.org", self.calls[0][1])

    def test_the_new_pin_reaches_the_launch_command(self):
        self.add()
        self.fake_http((200, {"version": "9.9.9"}, {}))
        lx.refresh_agent(force=True)
        self.assertIn("%s@9.9.9" % lx.AGENT_PKG,
                      lx.mcp_servers_fragment()["local"]["args"])

    def test_ttl_gates_the_request_unless_forced(self):
        self.fake_http((200, {"version": "9.9.9"}, {}))
        lx.refresh_agent(force=True)
        n = len(self.calls)
        self.assertFalse(lx.agent_is_stale())
        self.assertEqual(lx.refresh_agent()["reason"], "fresh")
        self.assertEqual(len(self.calls), n)

    def test_same_version_is_checked_but_not_updated(self):
        self.fake_http((200, {"version": lx.AGENT_FALLBACK_VERSION}, {}))
        r = lx.refresh_agent(force=True)
        self.assertTrue(r["checked"])
        self.assertFalse(r["updated"])

    def test_a_nonsense_version_is_refused_and_the_pin_holds(self):
        """npm answering with something unusable must not put junk in an argv."""
        for bad in ("latest", "", "1.2", "; rm -rf /"):
            self.fake_http((200, {"version": bad}, {}))
            r = lx.refresh_agent(force=True)
            self.assertFalse(r["updated"])
            self.assertIn("unusable", r["error"])
            self.assertEqual(lx.load()["agent"]["version"],
                             lx.AGENT_FALLBACK_VERSION)

    def test_network_failure_keeps_the_pin(self):
        self.fake_http(urllib.error.URLError("offline"))
        r = lx.refresh_agent(force=True)
        self.assertFalse(r["updated"])
        self.assertIn("could not reach", r["error"])
        self.assertEqual(r["version"], lx.AGENT_FALLBACK_VERSION)

    def test_a_hand_edited_bad_version_falls_back_rather_than_launching_it(self):
        cx._write_json(lx.STORE_PATH, {"servers": [],
                                       "agent": {"version": "$(id)"}})
        self.assertEqual(lx.load()["agent"]["version"], lx.AGENT_FALLBACK_VERSION)


# =========================================================== endpoints ======
class TestEndpoints(_Isolated):
    def test_get_local_returns_grouped_state(self):
        self.add(tag="files")
        out = app.api_local()
        self.assertEqual(out["enabled_count"], 1)
        self.assertEqual(out["groups"][0]["tag"], "files")
        self.assertTrue(out["preflight"]["runnable"])
        self.assertEqual(out["agent"]["package"], lx.AGENT_PKG)

    def test_upsert_and_its_400(self):
        out = app.api_local_upsert({"name": "git", "transport": "stdio",
                                    "command": "uvx"})
        self.assertEqual(out["server"]["name"], "git")
        r = app.api_local_upsert({"name": "sutra", "transport": "stdio",
                                  "command": "x"})
        self.assertEqual(r.status_code, 400)

    def test_toggle_tag_and_delete_round_trip(self):
        sid = app.api_local_upsert(
            {"name": "git", "transport": "stdio", "command": "uvx"})["server"]["id"]
        self.assertFalse(app.api_local_toggle(sid)["server"]["enabled"])
        self.assertEqual(app.api_local_retag(sid, {"tag": "vcs"})["server"]["tag"],
                         "vcs")
        self.assertEqual(app.api_local_delete(sid), {"ok": True})

    def test_missing_ids_are_404_not_500(self):
        for call in (lambda: app.api_local_toggle("lx_nope"),
                     lambda: app.api_local_retag("lx_nope", {"tag": "x"}),
                     lambda: app.api_local_delete("lx_nope")):
            with self.assertRaises(app.HTTPException) as cm:
                call()
            self.assertEqual(cm.exception.status_code, 404)

    def test_options_endpoint_and_its_400(self):
        out = app.api_local_options({"filter": "web,api", "route_composio": True})
        self.assertEqual(out["filter"], "web,api")
        self.assertTrue(out["route_composio"])
        self.assertEqual(app.api_local_options({"filter": "$(id)"}).status_code, 400)

    def test_registry_endpoint_never_500s_on_an_outage(self):
        self.fake_http(urllib.error.URLError("offline"))
        out = app.api_local_registry(q="postgres")
        self.assertEqual(out["results"], [])
        self.assertIn("error", out)

    def test_refresh_endpoint_is_the_local_auto_update_entry_point(self):
        self.fake_http((200, {"version": "9.9.9"}, {}))
        out = app.api_local_refresh({"force": True})
        self.assertTrue(out["checked"] and out["updated"])


# ============================================= provable negative (SAFETY) ===
class TestAggregatorDiscipline(unittest.TestCase):
    """Provable negatives, in the shape test_forbidden_calls.py uses.

    The pin and the preflight are the two properties that stop this connector
    doing something surprising on someone's machine. A comment cannot hold
    either in place; these fail the build if the code drifts."""

    SRC = (Path(HERE) / "local_store.py").read_text()

    def test_the_aggregator_is_never_launched_unpinned(self):
        """`npx -y @1mcp/agent` with no @version would resolve whatever npm
        calls latest, at spawn time, with nothing recorded."""
        self.assertNotIn('"%s"' % lx.AGENT_PKG, self.SRC.replace(
            'AGENT_PKG = "@1mcp/agent"', ""))
        self.assertIn('"%s@%s" % (AGENT_PKG, store["agent"]["version"])', self.SRC)

    def test_the_version_that_reaches_argv_is_pattern_checked(self):
        self.assertIn("_VERSION_RE", self.SRC)
        self.assertTrue(lx._VERSION_RE.match("0.34.4"))
        for bad in ("latest", "1.2", "; rm -rf /", "$(id)", ""):
            self.assertFalse(lx._VERSION_RE.match(bad), bad)

    def test_the_filter_that_reaches_argv_is_pattern_checked(self):
        self.assertIn("filter may contain tag names", self.SRC)

    def test_the_1mcp_config_is_derived_never_hand_kept(self):
        """Two sources of truth for what is enabled is how a panel starts lying
        about what the next turn can reach."""
        self.assertIn("write_1mcp_config(store)", self.SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
