"""Unit tests for the Composio connector (composio_store + app endpoints).

WHY A SEPARATE FILE (same rationale as test_activity.py, and as the
test_connectors.py this replaces)
------------------------------------------------------------------
No server, no network, no extra deps — just the store functions and the endpoint
handlers, called in-process against an isolated tempdir store. That makes them
runnable under the SHIPPED interpreter (electron/payload/python/bin/python3),
which carries fastapi/starlette but NOT httpx/pytest — so starlette's TestClient
is off the table and calling the handlers directly is the only dependency-free
way in. stdlib unittest only.

Run (bundled interpreter, no pytest):
    electron/payload/python/bin/python3 test_composio.py -v
Run (dev venv, same as the rest of the suite):
    .venv/bin/python -m unittest test_composio -v

THE NETWORK IS NEVER TOUCHED. composio_store funnels every HTTP call through
ONE function, `_http_json`, precisely so a test can replace it with a recorded
answer and still exercise the real request-building, error-translating and
caching code. Every test that would otherwise reach GitHub or
backend.composio.dev swaps that one function and asserts on what it was CALLED
WITH — which is the part a fake cannot get wrong on our behalf.

Isolation: composio_store writes exactly TWO files, STORE_PATH and
CATALOG_PATH. Every test repoints both module attributes at a fresh tempdir and
restores them, so a run never reads (or writes) the operator's real
~/.sutra-ui/composio.json. app imports the SAME module object
(import composio_store), so the rebind is seen by app._sutra_mcp_config's merge
too — asserted in setUp rather than assumed.
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

# importing app has import-time banners (org_api/providers) but no server side
# effects — same as test_activity.
import app  # noqa: E402
import composio_store as cx  # noqa: E402


class _Isolated(unittest.TestCase):
    """Base: fresh, isolated STORE_PATH + CATALOG_PATH, restored after."""

    def setUp(self):
        self._saved = (cx.STORE_PATH, cx.CATALOG_PATH, cx._http_json)
        self.dir = Path(tempfile.mkdtemp(prefix="sutra-test-composio-"))
        cx.STORE_PATH = self.dir / "composio.json"
        cx.CATALOG_PATH = self.dir / "composio-catalog.json"
        self.assertIs(app.composio_store, cx,
                      "app must share the composio_store module")

    def tearDown(self):
        cx.STORE_PATH, cx.CATALOG_PATH, cx._http_json = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- helpers ------------------------------------------------------------
    def fake_http(self, *answers):
        """Replace _http_json with a scripted responder. Each answer is a
        (status, payload, headers) tuple, or an Exception to raise. Records
        every call as (method, url, headers, body) on `self.calls`."""
        self.calls = []
        seq = list(answers)

        def _fake(method, url, headers=None, body=None, timeout=None):
            self.calls.append((method, url, dict(headers or {}), body))
            ans = seq.pop(0) if len(seq) > 1 else seq[0]
            if isinstance(ans, Exception):
                raise ans
            return ans

        cx._http_json = _fake

    def configured(self, enabled=("gmail",), key="ak_test_key_1234", user="u@x.io"):
        """A store that is ready to provision, written the way the app writes it."""
        cx.save({"api_key": key, "user_id": user,
                 "enabled": list(enabled), "session": {}})


# =========================================================== store shape =====
class TestStore(_Isolated):
    def test_missing_file_reads_as_blank_never_raises(self):
        s = cx.load()
        self.assertEqual(s, {"api_key": "", "user_id": "", "enabled": [],
                             "session": {}})

    def test_corrupt_file_reads_as_blank_never_raises(self):
        cx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cx.STORE_PATH.write_text("{not json at all")
        self.assertEqual(cx.load()["enabled"], [])

    def test_hand_edited_bad_slugs_are_dropped_not_fatal(self):
        cx.save({"api_key": "k", "user_id": "u",
                 "enabled": ["gmail", "NOT A SLUG", "", "slack", "gmail"],
                 "session": {}})
        # bad shapes dropped, duplicates collapsed, good ones kept in order
        self.assertEqual(cx.load()["enabled"], ["gmail", "slack"])

    def test_load_survives_a_non_numeric_created_at(self):
        """A hand-edited store whose session.created_at is a non-numeric string
        is VALID JSON, so it slips past _read_json's guard and would reach an
        unguarded float(). Found by the 100-agent adversarial pass."""
        cx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cx.STORE_PATH.write_text(
            '{"session":{"url":"http://x","session_id":"s",'
            '"created_at":"NOTANUMBER"}}')
        s = cx.load()                     # must not raise
        self.assertEqual(s["session"]["created_at"], 0.0)

    def test_write_forces_0600_even_when_the_temp_file_pre_exists(self):
        """os.open's mode arg is ignored for an existing file, so a stale or
        pre-planted composio.json.sutra-tmp at 0666 would carry world-rw onto
        the secret store via os.replace. fchmod forces 0600. Adversarial-pass
        finding."""
        import os
        cx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(cx.STORE_PATH) + ".sutra-tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT, 0o666)
        os.close(fd)
        os.chmod(tmp, 0o666)
        cx.save({"api_key": "ak_secret", "user_id": "u", "enabled": [],
                 "session": {}})
        self.assertEqual(os.stat(cx.STORE_PATH).st_mode & 0o777, 0o600)

    def test_store_file_is_not_world_readable(self):
        """The API key lives in this file. A 0644 store would leak it to every
        process on the machine, which is not a thing a chmod comment can fix."""
        cx.save({"api_key": "ak_secret", "user_id": "u", "enabled": [],
                 "session": {}})
        mode = os.stat(cx.STORE_PATH).st_mode & 0o777
        self.assertEqual(mode, 0o600, "store must be owner-only")


class TestAuth(_Isolated):
    def test_set_auth_stores_both_and_redacts_the_key(self):
        st = cx.set_auth(api_key="ak_abcdefgh", user_id="me@example.com")
        self.assertTrue(st["api_key_set"])
        self.assertEqual(st["api_key_hint"], "…efgh")
        self.assertEqual(st["user_id"], "me@example.com")
        # the state the panel sees must NOT carry the key in any field
        self.assertNotIn("ak_abcdefgh", json.dumps(st))

    def test_user_id_alone_does_not_clear_the_key(self):
        cx.set_auth(api_key="ak_keepme", user_id="a@b.c")
        cx.set_auth(user_id="d@e.f")
        self.assertEqual(cx.load()["api_key"], "ak_keepme")
        self.assertEqual(cx.load()["user_id"], "d@e.f")

    def test_changing_identity_drops_the_cached_session(self):
        """A session provisioned for one user must never be handed to another."""
        cx.save({"api_key": "k", "user_id": "a@b.c", "enabled": ["gmail"],
                 "session": {"session_id": "trs_1", "url": "https://x/mcp",
                             "type": "http", "fingerprint": "f", "created_at": 1}})
        cx.set_auth(user_id="d@e.f")
        self.assertEqual(cx.load()["session"], {})

    def test_bad_user_id_is_a_value_error_not_a_write(self):
        with self.assertRaises(ValueError):
            cx.set_auth(user_id="has spaces and /slashes")
        self.assertEqual(cx.load()["user_id"], "")


class TestToggle(_Isolated):
    def test_toggle_flips_and_persists(self):
        cx.toggle("gmail")
        self.assertEqual(cx.load()["enabled"], ["gmail"])
        cx.toggle("gmail")
        self.assertEqual(cx.load()["enabled"], [])

    def test_explicit_direction_is_idempotent(self):
        cx.toggle("slack", on=True)
        cx.toggle("slack", on=True)
        self.assertEqual(cx.load()["enabled"], ["slack"])

    def test_toggle_drops_the_session_so_it_is_reprovisioned(self):
        """The session is bound to the toolkits it was made with. Keeping it
        after a change would silently keep offering a disabled toolkit."""
        cx.save({"api_key": "k", "user_id": "u", "enabled": ["gmail"],
                 "session": {"session_id": "trs_1", "url": "https://x/mcp",
                             "type": "http", "fingerprint": "f", "created_at": 1}})
        cx.toggle("slack", on=True)
        self.assertEqual(cx.load()["session"], {})

    def test_bad_slug_rejected(self):
        for bad in ("", "Gmail Pro", "../etc/passwd", "x" * 80):
            with self.assertRaises(ValueError):
                cx.toggle(bad)

    def test_cap_is_enforced(self):
        cx.save({"api_key": "", "user_id": "",
                 "enabled": ["tk%d" % i for i in range(cx.MAX_ENABLED)],
                 "session": {}})
        with self.assertRaises(ValueError):
            cx.toggle("onemore", on=True)


# ============================================================== catalog ======
UPSTREAM = [
    {"slug": "gmail", "name": "Gmail", "logo": "https://l/gmail",
     "category": "email", "toolCount": 63, "triggerCount": 2},
    {"slug": "github", "name": "GitHub", "logo": "https://l/github",
     "category": "developer tools", "toolCount": 893, "triggerCount": 20},
    {"slug": "BAD SLUG", "name": "nope", "category": "x", "toolCount": 1},
    {"slug": "gmail", "name": "Gmail dupe", "category": "email", "toolCount": 1},
    "not a dict",
]


class TestCatalogNormalize(_Isolated):
    """Pure, network-free: upstream's shape -> ours."""

    def test_drops_bad_rows_dedupes_and_sorts_by_tool_count(self):
        rows = cx._normalize_upstream(UPSTREAM)
        self.assertEqual([r["slug"] for r in rows], ["github", "gmail"])
        self.assertEqual(rows[0]["tools"], 893)
        self.assertEqual(rows[1]["triggers"], 2)
        self.assertEqual(rows[1]["category"], "email")
        # logo is derivable from the slug, so it is not carried
        self.assertNotIn("logo", rows[0])

    def test_garbage_input_is_an_empty_list_not_an_exception(self):
        for bad in (None, {}, "", 7):
            self.assertEqual(cx._normalize_upstream(bad), [])


class TestVendoredCatalog(_Isolated):
    """First run, no network, no cache: the screen must still have a catalog."""

    def test_vendored_snapshot_is_present_and_well_formed(self):
        self.assertTrue(cx.VENDORED_CATALOG.is_file(),
                        "the vendored snapshot ships beside composio_store.py")
        page = cx.catalog()
        self.assertEqual(page["source"], "vendored")
        self.assertGreater(page["total"], 500)
        first = page["results"][0]
        self.assertEqual(set(first), {"slug", "name", "category", "tools",
                                      "triggers", "enabled"})

    def test_search_matches_slug_or_name_case_insensitively(self):
        self.assertTrue(any(r["slug"] == "gmail"
                            for r in cx.catalog(q="GMAIL")["results"]))
        self.assertTrue(any("github" in r["slug"]
                            for r in cx.catalog(q="GitHub")["results"]))
        self.assertEqual(cx.catalog(q="zzzz-no-such-toolkit")["total"], 0)

    def test_enabled_flag_rides_along_so_cards_render_state(self):
        cx.toggle("gmail", on=True)
        hit = [r for r in cx.catalog(q="gmail")["results"] if r["slug"] == "gmail"]
        self.assertTrue(hit and hit[0]["enabled"])


class TestCatalogRefresh(_Isolated):
    """The auto-update mechanism itself."""

    def test_fetch_adopts_upstream_and_records_provenance(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"abc123"'}))
        r = cx.refresh_catalog(force=True)
        self.assertTrue(r["checked"] and r["updated"])
        self.assertEqual(r["count"], 2)
        self.assertEqual(cx.catalog()["source"], "cache")
        self.assertEqual([r["slug"] for r in cx.catalog()["results"]],
                         ["github", "gmail"])
        # it asked the upstream file, by name
        method, url, _, _ = self.calls[0]
        self.assertEqual(method, "GET")
        self.assertIn("ComposioHQ/composio", url)
        self.assertIn("toolkits-list.json", url)

    def test_second_check_sends_if_none_match_and_a_304_changes_nothing(self):
        """The whole reason a 6h poll of a 227KB file is free."""
        self.fake_http((200, UPSTREAM, {"ETag": '"abc123"'}))
        cx.refresh_catalog(force=True)
        updated_at = cx._catalog_meta()["updated_at"]

        self.fake_http((304, None, {}))
        r = cx.refresh_catalog(force=True)
        self.assertFalse(r["updated"])
        self.assertEqual(r["reason"], "unchanged")
        self.assertEqual(self.calls[0][2].get("If-None-Match"), '"abc123"')
        # the etag is reported as the content id, so "unchanged" is verifiable
        self.assertEqual(cx._catalog_meta()["content_id"], "abc123")
        # checked moved, updated did NOT — they are different facts
        self.assertGreaterEqual(cx._catalog_meta()["checked_at"], updated_at)
        self.assertEqual(cx._catalog_meta()["updated_at"], updated_at)

    def test_ttl_gates_the_request_unless_forced(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        cx.refresh_catalog(force=True)
        n = len(self.calls)
        r = cx.refresh_catalog()            # inside the TTL
        self.assertFalse(r["checked"])
        self.assertEqual(r["reason"], "fresh")
        self.assertEqual(len(self.calls), n, "no request inside the TTL")

    def test_stale_after_ttl(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        cx.refresh_catalog(force=True)
        self.assertFalse(cx.catalog_is_stale())
        cached = json.loads(cx.CATALOG_PATH.read_text())
        cached["checked_at"] = time.time() - cx.CATALOG_TTL - 1
        cx.CATALOG_PATH.write_text(json.dumps(cached))
        self.assertTrue(cx.catalog_is_stale())

    def test_network_failure_keeps_the_catalog_we_have(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        cx.refresh_catalog(force=True)
        self.fake_http(urllib.error.URLError("Name or service not known"))
        r = cx.refresh_catalog(force=True)
        self.assertFalse(r["updated"])
        self.assertIn("could not reach", r["error"])
        self.assertEqual(cx.catalog()["total"], 2, "kept the copy we had")

    def test_upstream_shape_change_does_not_blank_the_screen(self):
        """A 200 that parses to zero toolkits is upstream changing on us. Keep
        what we have and SAY so — an empty catalog reads as 'Composio has no
        apps', which is a lie the operator cannot debug."""
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        cx.refresh_catalog(force=True)
        self.fake_http((200, {"servers": []}, {}))
        r = cx.refresh_catalog(force=True)
        self.assertFalse(r["updated"])
        self.assertIn("zero toolkits", r["error"])
        self.assertEqual(cx.catalog()["total"], 2)

    def test_added_and_removed_are_reported(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e1"'}))
        cx.refresh_catalog(force=True)
        self.fake_http((200, UPSTREAM[:1] + [
            {"slug": "linear", "name": "Linear", "category": "pm",
             "toolCount": 40, "triggerCount": 0}], {"ETag": '"e2"'}))
        r = cx.refresh_catalog(force=True)
        self.assertTrue(r["updated"])
        self.assertEqual(r["added"], ["linear"])
        self.assertEqual(r["removed"], ["github"])


# ============================================================== session ======
SESSION_OK = (201, {"session_id": "trs_abc",
                    "mcp": {"type": "http",
                            "url": "https://app.composio.dev/tool_router/v3/trs_abc/mcp"}},
              {})


class TestProvision(_Isolated):
    def test_request_matches_composios_session_contract(self):
        self.configured(enabled=("gmail", "slack"))
        self.fake_http(SESSION_OK)
        cx.provision()
        method, url, headers, body = self.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, cx.API_BASE + "/api/v3/tool_router/session")
        self.assertEqual(headers["x-api-key"], "ak_test_key_1234")
        self.assertEqual(body["user_id"], "u@x.io")
        self.assertEqual(body["toolkits"], {"enable": ["gmail", "slack"]})

    def test_toolkits_are_an_allowlist_never_omitted(self):
        """Composio's default is every toolkit. Omitting the key would hand the
        session reach the operator never granted."""
        self.configured(enabled=("gmail",))
        self.fake_http(SESSION_OK)
        cx.provision()
        self.assertIn("enable", self.calls[0][3]["toolkits"])

    def test_workbench_is_disabled_per_connectors_charter_rule_2(self):
        """CHARTER.md RULE 2: Composio's workbench (remote code execution) is
        not a surface Sutra uses. A default-on workbench would ship
        COMPOSIO_REMOTE_BASH_TOOL into every session."""
        self.configured()
        self.fake_http(SESSION_OK)
        cx.provision()
        self.assertEqual(self.calls[0][3]["workbench"], {"enable": False})

    def test_session_is_cached_not_reprovisioned_per_turn(self):
        self.configured()
        self.fake_http(SESSION_OK)
        cx.provision()
        cx.provision()
        cx.provision()
        self.assertEqual(len(self.calls), 1, "one session, reused")

    def test_force_reprovisions(self):
        self.configured()
        self.fake_http(SESSION_OK)
        cx.provision()
        cx.provision(force=True)
        self.assertEqual(len(self.calls), 2)

    def test_toolkit_change_invalidates_the_cached_session(self):
        self.configured(enabled=("gmail",))
        self.fake_http(SESSION_OK)
        cx.provision()
        cx.toggle("slack", on=True)
        cx.provision()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][3]["toolkits"], {"enable": ["gmail", "slack"]})

    def test_expired_session_is_reprovisioned(self):
        self.configured()
        self.fake_http(SESSION_OK)
        cx.provision()
        store = cx.load()
        store["session"]["created_at"] = time.time() - cx.SESSION_TTL - 1
        cx.save(store)
        cx.provision()
        self.assertEqual(len(self.calls), 2)

    def test_missing_credentials_are_named_individually(self):
        for store, want in (
            ({"api_key": "", "user_id": "u", "enabled": ["gmail"]}, "API key"),
            ({"api_key": "k", "user_id": "", "enabled": ["gmail"]}, "user id"),
            ({"api_key": "k", "user_id": "u", "enabled": []}, "toolkits"),
        ):
            cx.save(dict(store, session={}))
            with self.assertRaises(cx.ComposioError) as cm:
                cx.provision()
            self.assertIn(want, str(cm.exception))

    def test_rejected_key_says_so(self):
        self.configured()
        self.fake_http((401, {"message": "invalid api key"}, {}))
        with self.assertRaises(cx.ComposioError) as cm:
            cx.provision()
        self.assertIn("rejected the API key", str(cm.exception))

    def test_api_error_body_is_surfaced_verbatim(self):
        self.configured()
        self.fake_http((400, {"message": "unknown toolkit: nope"}, {}))
        with self.assertRaises(cx.ComposioError) as cm:
            cx.provision()
        self.assertIn("unknown toolkit: nope", str(cm.exception))

    def test_unreachable_host_is_named(self):
        self.configured()
        self.fake_http(urllib.error.URLError("connection refused"))
        with self.assertRaises(cx.ComposioError) as cm:
            cx.provision()
        self.assertIn("backend.composio.dev", str(cm.exception))

    def test_a_bare_transport_error_still_names_the_host(self):
        """urlopen raises a bare TimeoutError on a connect timeout (no .reason),
        plus ConnectionResetError / OSError on other unreachable-host modes.
        Naming the host only for URLError left "timed out" with no host — the
        most common case. Adversarial-pass finding."""
        self.configured()
        for exc in (TimeoutError("timed out"),
                    ConnectionResetError(104, "Connection reset by peer"),
                    OSError("network unreachable")):
            self.fake_http(exc)
            with self.assertRaises(cx.ComposioError) as cm:
                cx.provision(force=True)
            self.assertIn("backend.composio.dev", str(cm.exception))

    def test_response_without_an_mcp_url_is_refused(self):
        self.configured()
        self.fake_http((201, {"session_id": "trs_x", "mcp": {}}, {}))
        with self.assertRaises(cx.ComposioError):
            cx.provision()


# ================================================================ merge ======
class TestMcpFragment(_Isolated):
    def test_unconfigured_is_an_empty_fragment(self):
        self.assertEqual(cx.mcp_servers_fragment(), {})

    def test_one_server_however_many_toolkits(self):
        """The whole point of the tool router: N toolkits, ONE MCP server."""
        self.configured(enabled=("gmail", "slack", "github"))
        self.fake_http(SESSION_OK)
        frag = cx.mcp_servers_fragment()
        self.assertEqual(list(frag), ["composio"])
        self.assertEqual(frag["composio"], {
            "type": "http",
            "url": "https://app.composio.dev/tool_router/v3/trs_abc/mcp",
            "headers": {"x-api-key": "ak_test_key_1234"},
        })

    def test_key_travels_as_a_header_never_in_the_url(self):
        self.configured()
        self.fake_http(SESSION_OK)
        frag = cx.mcp_servers_fragment()
        self.assertNotIn("ak_test_key_1234", frag["composio"]["url"])

    def test_provisioning_failure_degrades_the_turn_it_does_not_break_it(self):
        """This runs on the hot path of every turn. A turn without the Composio
        connector is degraded; a turn that does not start is broken."""
        self.configured()
        self.fake_http(urllib.error.URLError("offline"))
        self.assertEqual(cx.mcp_servers_fragment(), {})

    def test_sse_type_is_honoured_if_composio_ever_returns_one(self):
        self.configured()
        self.fake_http((201, {"session_id": "trs_s",
                              "mcp": {"type": "sse", "url": "https://x/sse"}}, {}))
        self.assertEqual(cx.mcp_servers_fragment()["composio"]["type"], "sse")


class TestAppMerge(_Isolated):
    """app._sutra_mcp_config is what actually reaches the CLI."""

    def test_composio_is_merged_alongside_sutra(self):
        self.configured()
        self.fake_http(SESSION_OK)
        cfg = json.loads(app._sutra_mcp_config())
        self.assertIn("sutra", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["composio"]["url"],
                         "https://app.composio.dev/tool_router/v3/trs_abc/mcp")

    def test_a_broken_store_never_takes_the_turn_down(self):
        cx.STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cx.STORE_PATH.write_text("{{{ not json")
        cfg = json.loads(app._sutra_mcp_config())
        self.assertEqual(list(cfg["mcpServers"]), ["sutra"])


# ============================================================ endpoints ======
class TestEndpoints(_Isolated):
    """The handlers, called directly — same technique test_connectors used."""

    def test_get_connectors_returns_redacted_state(self):
        cx.set_auth(api_key="ak_supersecret", user_id="u@x.io")
        out = app.api_connectors()
        self.assertTrue(out["api_key_set"])
        self.assertNotIn("ak_supersecret", json.dumps(out))

    def test_auth_endpoint_reports_a_bad_value_as_400_not_a_crash(self):
        r = app.api_connectors_auth({"user_id": "bad id/with slash"})
        self.assertEqual(r.status_code, 400)

    def test_toggle_endpoint_round_trip(self):
        out = app.api_connectors_toolkit_toggle("gmail", {"on": True})
        self.assertEqual(out["enabled"], ["gmail"])
        out = app.api_connectors_toolkit_toggle("gmail", {})
        self.assertEqual(out["enabled"], [])

    def test_toggle_endpoint_rejects_a_bad_slug_as_400(self):
        r = app.api_connectors_toolkit_toggle("not a slug", {})
        self.assertEqual(r.status_code, 400)

    def test_catalog_endpoint_serves_without_network_when_fresh(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        cx.refresh_catalog(force=True)
        n = len(self.calls)
        out = app.api_connectors_catalog(q="git")
        self.assertEqual([r["slug"] for r in out["results"]], ["github"])
        self.assertEqual(len(self.calls), n, "a fresh catalog costs no request")

    def test_session_endpoint_reports_a_refusal_as_a_message_not_a_500(self):
        """Composio being down is not a bug in this panel."""
        self.configured()
        self.fake_http(urllib.error.URLError("offline"))
        out = app.api_connectors_session({})
        self.assertFalse(out["ok"])
        self.assertIn("could not reach", out["error"])
        self.assertIn("state", out)

    def test_session_endpoint_ok_path(self):
        self.configured()
        self.fake_http(SESSION_OK)
        out = app.api_connectors_session({"force": True})
        self.assertTrue(out["ok"])
        self.assertEqual(out["session_id"], "trs_abc")

    def test_refresh_endpoint_is_the_auto_update_entry_point(self):
        self.fake_http((200, UPSTREAM, {"ETag": '"e"'}))
        out = app.api_connectors_refresh({"force": True})
        self.assertTrue(out["checked"] and out["updated"])

    def test_drop_session_keeps_credentials(self):
        self.configured()
        self.fake_http(SESSION_OK)
        cx.provision()
        out = app.api_connectors_session_drop()
        self.assertFalse(out["session"]["active"])
        self.assertTrue(out["api_key_set"])


# ============================================== provable negative (SAFETY) ===
class TestNoDeprecatedComposioSurface(unittest.TestCase):
    """A provable negative, in the shape test_forbidden_calls.py uses.

    Upstream deprecated `composio.mcp.*` (the standalone MCP-server-management
    API) in favour of the tool router session, and says in the module docstring:
    "do not generate new code against composio.mcp". This test fails if this
    module ever starts calling those endpoints, which is the kind of drift a
    comment cannot prevent.

    It also pins the workbench refusal (CHARTER.md RULE 2) to the source, so
    deleting the flag fails a test rather than silently re-enabling remote code
    execution in every session.
    """

    SRC = (Path(HERE) / "composio_store.py").read_text()

    def test_does_not_call_the_deprecated_mcp_server_api(self):
        for path in ("/api/v3/mcp/servers", "/api/v3/mcp/servers/custom",
                     "/api/v3/mcp/servers/generate"):
            self.assertNotIn(path, self.SRC,
                             "deprecated upstream surface: %s" % path)

    def test_workbench_stays_disabled(self):
        self.assertIn('"workbench": {"enable": False}', self.SRC)

    def test_the_only_composio_api_call_is_the_session_endpoint(self):
        self.assertEqual(self.SRC.count("API_BASE +"), 1)
        self.assertIn('SESSION_PATH = "/api/v3/tool_router/session"', self.SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
