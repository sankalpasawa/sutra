"""Functional test suite for the Tier-3 backend (org_api.py + app.py).

stdlib only: unittest + urllib.request + subprocess. No httpx/requests/
fastapi.testclient (not in requirements.txt). Spawns a real uvicorn
subprocess per TestCase class, bound to 127.0.0.1 on a free port, with
SUTRA_NATIVE_HOME pointed at a FRESH tempfile.mkdtemp() re-seeded via
fixture_seed.seed() -- NEVER ~/.sutra-native and NEVER the shared
scratchpad/dev-registry (that one is for manual/dev use only).

Run: .venv/bin/python -m unittest test_app -v   (from inside sutra-ui/)
"""
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.error
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http(method, path, body=None, timeout=5):
    url = "http://127.0.0.1:%d%s" % (TestApp.port, path)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _get(path):
    return _http("GET", path)


def _post(path, body):
    return _http("POST", path, body)



def _without_mcp(args):
    """The argv minus the Sutra MCP flags.

    Three tests below pin the baseline argv exactly, which is the right thing to
    pin -- flag ORDER is load-bearing and a reordering is a real regression.
    Sutra's own tool server adds --mcp-config/--strict-mcp-config and appends
    mcp__sutra__* to --allowedTools on every run, which is not what those tests
    are about. They compare the argv with those removed, and TestAgentArgsMcp
    covers the flags themselves.
    """
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--mcp-config":
            i += 2; continue
        if a == "--strict-mcp-config":
            i += 1; continue
        if a == "--allowedTools":
            vals = []
            j = i + 1
            while j < len(args) and not str(args[j]).startswith("--"):
                vals.append(args[j]); j += 1
            vals = [v for v in vals if v != "mcp__sutra__*"]
            if vals:
                out.append("--allowedTools"); out.extend(vals)
            i = j; continue
        out.append(a); i += 1
    return out

class TestApp(unittest.TestCase):
    """One shared server for the whole class -- read-mostly endpoints don't
    need per-test isolation, but the registry dir is fresh for THIS run only
    (never reused across runs, never the live one)."""

    proc = None
    port = None
    tmpdir = None
    userdir = None      # stand-in for ~/.sutra-ui (settings + drafts)
    _env_saved = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-app-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        # seed BEFORE the server imports placement_engine in the subprocess --
        # the subprocess does its own import, so we just need the files on
        # disk before it starts.
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        # ---- the OPERATOR's files are not test fixtures --------------------
        # providers.SETTINGS_PATH and org_api.DRAFTS_DIR default to the REAL
        # ~/.sutra-ui. POST /api/settings and POST /api/providers/active WRITE
        # there, so an unisolated run would rewrite the operator's chosen
        # provider / permission_mode as a side effect of `python -m unittest`,
        # and test_19 would edit their real draft. Point both at a tempdir --
        # in THIS process (test_19/test_20/test_43 import org_api and providers
        # directly, and both resolve the path at import time) and in the server
        # subprocess, so the two agree on which file is under test.
        #
        # Deliberately NOT under cls.tmpdir: test_20 and test_43 assert these
        # land OUTSIDE SUTRA_NATIVE_HOME, and nesting them inside it would make
        # that assertion pass vacuously.
        cls.userdir = tempfile.mkdtemp(prefix="sutra-test-userdir-")
        cls._env_saved = {k: os.environ.get(k)
                          for k in ("SUTRA_UI_SETTINGS", "SUTRA_UI_DRAFTS",
                                    "SUTRA_UI_PROVIDER", "SUTRA_UI_PERMISSION_MODE",
                                    "SUTRA_UI_WORKDIR_ROOT")}
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(cls.userdir, "settings.json")
        os.environ["SUTRA_UI_DRAFTS"] = os.path.join(cls.userdir, "drafts")
        # workdir is confined to $HOME by default (it becomes the spawned
        # agent's cwd, so an arbitrary path is a read oracle). These tests use
        # a tempdir, which is outside $HOME on macOS -- widen the root the same
        # way an operator would when starting the server.
        os.environ["SUTRA_UI_WORKDIR_ROOT"] = cls.userdir
        # An env override outranks settings.json in active_provider_detail(),
        # so leaving these set would make the provider/settings tests assert
        # the developer's shell config instead of the code under test.
        os.environ.pop("SUTRA_UI_PROVIDER", None)
        os.environ.pop("SUTRA_UI_PERMISSION_MODE", None)

        cls.port = _free_port()
        env = dict(os.environ)
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env.pop("SUTRA_UI_PERMISSION_MODE", None)  # exercise the real default
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 10
        last_err = None
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.25)
        else:
            out = cls.proc.stdout.read().decode("utf-8", "replace") if cls.proc.stdout else ""
            raise RuntimeError("server did not come up: %r\n%s" % (last_err, out))

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.tmpdir and os.path.isdir(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)
        if cls.userdir and os.path.isdir(cls.userdir):
            shutil.rmtree(cls.userdir, ignore_errors=True)
        for k, v in (cls._env_saved or {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ---------------------------------------------------------------- tree -

    def test_01_tree_shape_and_count(self):
        status, rows = _get("/api/org/tree")
        self.assertEqual(status, 200)
        self.assertGreater(len(rows), 0)
        for r in rows:
            for field in ("ref", "path", "name", "status", "parent_ref",
                           "tenant_id", "mint_evidence", "ts_minted_ms",
                           "successor_refs"):
                self.assertIn(field, r, "tree row missing %r: %r" % (field, r))
        # live by default. The tenant half of this assertion is GONE: tenancy
        # is removed, so /tree returns the whole registry and a second root is
        # damage to be refused at publish, not a tenant to be filtered here.
        self.assertTrue(all(row["status"] != "retired" for row in rows))

    def test_02_tree_include_retired_adds_the_tombstone(self):
        _, live_rows = _get("/api/org/tree")
        _, all_rows = _get("/api/org/tree?include_retired=true")
        self.assertGreater(len(all_rows), len(live_rows))
        self.assertTrue(any(r["status"] == "retired" for r in all_rows))

    def test_03_tenant_params_are_accepted_no_ops(self):
        """TENANCY IS REMOVED. This replaces four tests that specified it:

            test_03_tree_all_tenants_adds_the_leak
            test_29_tree_partitions_tenant_of_record_ahead_of_every_other_tenant
            test_49_the_tenant_param_actually_scopes_every_org_endpoint
            test_50_an_unknown_tenant_returns_empty_not_everything

        Together they asserted that ?tenant= selected one org's rows, that
        all_tenants=true widened it, that the tenant-of-record sorted first, and
        that an unknown tenant returned EMPTY rather than everything. All four
        described a capability that no longer exists: one registry now holds one
        org, so there is nothing to select between.

        What must still hold is compatibility. A running panel and existing
        scripts send these query params; rejecting them would 422 live callers
        for no benefit. So they are accepted and ignored -- and 'ignored' is
        exactly what has to be pinned, because the OLD failure mode was a
        parameter that looked scoped and was not.
        """
        _, base = _get("/api/org/tree?include_retired=true")
        for q in ("?include_retired=true&tenant=T-local",
                  "?include_retired=true&tenant=T-does-not-exist",
                  "?include_retired=true&all_tenants=true",
                  "?include_retired=true&all_tenants=false"):
            status, rows = _get("/api/org/tree" + q)
            self.assertEqual(status, 200, "%s must not 422 a live caller" % q)
            self.assertEqual(len(rows), len(base),
                             "%s changed the result; tenancy is removed and it "
                             "must be a no-op" % q)

        # an unknown tenant must NOT empty the response now -- the old contract
        # was "empty, never everything"; the new one is "everything, always"
        for path in ("/api/org/charters", "/api/org/placements"):
            _, plain = _get(path)
            _, ghosted = _get(path + "?tenant=T-does-not-exist")
            self.assertEqual(len(ghosted), len(plain), path)

    def test_47_the_tenants_endpoint_reports_one_registry(self):
        """TENANCY IS REMOVED. Replaces three tests that specified it:

            test_47_tenants_are_derived_from_the_registry_not_padded
            test_48_tenant_counts_match_the_scoped_endpoints_exactly
            test_51_stats_scope_follows_the_tenant_param

        They asserted that /api/tenants unioned every tenant_id seen on a domain
        or placement, that each row's counts matched that tenant's SCOPED
        endpoints, and that /stats followed ?tenant=. All three described
        per-tenant slicing, which no longer exists.

        The endpoint is kept (a running panel calls it on boot; deleting it
        would 404 a live client) and now describes the registry itself. Its
        counts must equal the UNSCOPED endpoints -- that is the whole contract,
        and it is what catches a half-removed filter where /tree and /charters
        disagree about how much of the registry exists.
        """
        _, rows = _get("/api/tenants")
        self.assertEqual(len(rows), 1,
                         "one registry, one row -- got %r" % (rows,))
        r = rows[0]
        self.assertTrue(r["is_default"])

        _, live = _get("/api/org/tree")
        _, everything = _get("/api/org/tree?include_retired=true")
        _, chs = _get("/api/org/charters")
        _, plc = _get("/api/org/placements")

        self.assertEqual(r["domains"], len(everything))
        self.assertEqual(r["domains_live"], len(live))
        self.assertEqual(r["domains_retired"], len(everything) - len(live))
        self.assertEqual(r["charters"], len(chs))
        self.assertEqual(r["placements"], len(plc))
        if r["root_ref"]:
            roots = [d["ref"] for d in everything if d["parent_ref"] is None]
            self.assertIn(r["root_ref"], roots)

    def test_03b_tool_output_is_forwarded_not_discarded(self):
        """The server used to send {id, ok} and DISCARD the whole content array,
        so an operator saw that Read ran and never what it read -- and a failing
        tool showed a red dot with no reason attached."""
        import app as A

        # a plain string result
        self.assertEqual(A._tool_output("hello"), "hello")
        # the typed-parts shape the CLI actually emits
        self.assertEqual(
            A._tool_output([{"type": "text", "text": "line one"},
                            {"type": "text", "text": "line two"}]),
            "line one\nline two")
        # a non-text part is NAMED, never inlined: a base64 image would be
        # megabytes over a websocket rendering a progress view
        self.assertEqual(A._tool_output([{"type": "image", "source": {"data": "AAAA"}}]),
                         "[image]")
        # nothing to show stays None rather than becoming an empty expander
        self.assertIsNone(A._tool_output(None))
        self.assertIsNone(A._tool_output("   "))
        self.assertIsNone(A._tool_output([]))

    def test_03c_tool_output_truncation_is_explicit(self):
        """A silent cut would let someone read half a file and believe it was the
        whole one -- worse than showing less."""
        import app as A
        out = A._tool_output("x" * 5000, limit=100)
        self.assertTrue(out.startswith("x" * 100))
        self.assertIn("truncated", out)
        self.assertIn("4900", out, "must say HOW MUCH was cut")
        self.assertLess(len(out), 200)

    def test_03d_a_tool_that_returns_nothing_is_not_an_error(self):
        """ok and output are independent: a successful tool may legitimately
        return no content, and that must not render as a failure."""
        import app as A
        self.assertIsNone(A._tool_output(""))

    def test_03e_arg_builder_baseline_is_unchanged(self):
        """The spawn was a hardcoded list; it is a builder now. The flags that
        already worked must come out in the same order -- a reorder here is a
        behaviour change nobody asked for."""
        import app as A
        a = _without_mcp(A.build_agent_args("claude", "hi", "plan"))
        self.assertEqual(a, ["claude", "-p", "hi", "--output-format", "stream-json",
                             "--verbose", "--include-partial-messages",
                             "--permission-mode", "plan"])

    def test_03f_arg_builder_validates_everything(self):
        """A value that reaches the CLI unchecked fails seconds later as a dead
        socket, which reads as 'the panel is broken' rather than 'that was
        wrong'."""
        import app as A
        a = _without_mcp(A.build_agent_args("claude", "hi", "plan", opts={
            "fallback_model": "not-a-model",   # not catalogued
            "effort": "bogus",                 # not a level
            "max_budget_usd": 0,               # 0 means "spend nothing" = a hang
            "allowed_tools": [None, "", 123],  # junk, not stringified
            "add_dir": ["/etc"],               # outside $HOME
        }))
        self.assertNotIn("--fallback-model", a)
        self.assertNotIn("--effort", a)
        self.assertNotIn("--max-budget-usd", a)
        self.assertNotIn("--allowedTools", a)
        self.assertNotIn("--add-dir", a)

    def test_03g_add_dir_is_confined_to_home(self):
        """This is a loopback web app: a directory arriving over a socket must
        not be able to hand the agent '/'."""
        import app as A
        home = os.path.expanduser("~")
        a = A.build_agent_args("claude", "hi", "plan",
                               opts={"add_dir": [home, "/etc", "/"]})
        dirs = [a[i + 1] for i, v in enumerate(a) if v == "--add-dir"]
        self.assertEqual(dirs, [os.path.realpath(home)])

    def test_03h_fork_session_needs_a_resume(self):
        """--fork-session forks a RESUMED thread. Alone the CLI ignores it, which
        would make the toggle look broken."""
        import app as A
        self.assertNotIn("--fork-session",
                         A.build_agent_args("claude", "hi", "plan",
                                            opts={"fork_session": True}))
        self.assertIn("--fork-session",
                      A.build_agent_args("claude", "hi", "plan", session_id="S",
                                         opts={"fork_session": True}))

    def test_03i_all_six_permission_modes_are_reachable(self):
        """The panel knew three; `claude --help` accepts six. auto/manual/dontAsk
        were unreachable from the UI even though the CLI has always taken them."""
        import providers as P
        for m in ("plan", "acceptEdits", "bypassPermissions", "auto", "manual", "dontAsk"):
            self.assertIn(m, P.PERMISSION_MODES, m)
        # and every one of them explains itself, including the ones whose
        # behaviour is limited until a persistent session channel exists
        for m in P.PERMISSION_MODES:
            self.assertTrue(P.PERMISSION_MODE_NOTES.get(m), "no note for %s" % m)

    def test_03j_persistent_argv_takes_the_prompt_on_stdin(self):
        """ONE PROCESS, MANY TURNS. A persistent run must NOT carry the message
        as a positional argument -- that is the one-shot form, and passing both
        would send the first message twice."""
        import app as A
        a = A.build_agent_args("claude", "hello", "plan", stream_input=True)
        self.assertIn("--input-format", a)
        self.assertEqual(a[a.index("--input-format") + 1], "stream-json")
        self.assertNotIn("hello", a, "the prompt goes on stdin, not in argv")
        self.assertEqual(a[1], "-p")

    def test_03k_one_shot_argv_is_unchanged(self):
        """The persistent path is additive: the one-shot form other callers and
        tests rely on must be byte-identical to what it always was."""
        import app as A
        self.assertEqual(
            _without_mcp(A.build_agent_args("claude", "hello", "plan")),
            ["claude", "-p", "hello", "--output-format", "stream-json",
             "--verbose", "--include-partial-messages", "--permission-mode", "plan"])

    def test_03l_spawn_time_options_change_the_spawn_key(self):
        """model / permission mode / effort / budget are SPAWN-TIME flags: they
        cannot change on a running process. The handler reuses a process only
        while the argv would be identical, so these must actually differ --
        otherwise a per-message override would be silently ignored."""
        import app as A
        base = A.build_agent_args("claude", "x", "plan", stream_input=True)
        for label, kw in (
            ("model", dict(model="haiku")),
            ("perm", dict(perm_mode="acceptEdits")),
            ("effort", dict(opts={"effort": "high"})),
            ("budget", dict(opts={"max_budget_usd": 3})),
        ):
            kw.setdefault("perm_mode", "plan")
            other = A.build_agent_args("claude", "x", kw.pop("perm_mode"),
                                       stream_input=True, **kw)
            self.assertNotEqual(tuple(base), tuple(other),
                                "%s must force a respawn" % label)

    def test_04_dpaths_are_unique_per_tenant(self):
        # D-numbering is PER TENANT TREE, not global -- T-local's "Sutra Labs"
        # and T-acme's "Client Success" are each their own root and each
        # legitimately gets "D0". Uniqueness only holds within one tenant.
        _, rows = _get("/api/org/tree?include_retired=true&all_tenants=true")
        by_tenant = {}
        for r in rows:
            by_tenant.setdefault(r["tenant_id"], []).append(r["path"])
        self.assertGreaterEqual(len(by_tenant), 2, "expected at least T-local + T-acme")
        for tenant_id, paths in by_tenant.items():
            self.assertEqual(len(paths), len(set(paths)),
                              "duplicate D-paths within tenant %r: %r" % (tenant_id, paths))
        root = [r for r in rows if r["parent_ref"] is None]
        self.assertGreaterEqual(len(root), 2)  # Sutra Labs D0 + Client Success D0

    # ------------------------------------------------------------- stats ---

    def test_05_stats_matches_tree(self):
        status, stats = _get("/api/org/stats")
        self.assertEqual(status, 200)
        for k in ("domains", "domains_live", "domains_retired", "charters",
                   "placements", "current_rows", "confidence_floor"):
            self.assertIn(k, stats)
        self.assertEqual(stats["domains"], stats["domains_live"] + stats["domains_retired"])
        self.assertAlmostEqual(stats["confidence_floor"], 0.45, places=2)
        _, all_rows = _get("/api/org/tree?include_retired=true&all_tenants=true")
        self.assertEqual(stats["domains"], len(all_rows))

    # ---------------------------------------------------------- charters --

    def test_05b_root_serves_the_studio_not_the_legacy_console(self):
        """Regression: "/" used to serve term.html (the xterm console), so the
        front door showed a completely different UI from the studio and the
        operator reported "the UI does not match" -- correctly. "/" must serve
        the studio, and it must be the same bytes as /panel."""
        def _raw(path):
            req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path))
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode("utf-8", "replace")
        s_root, root = _raw("/")
        s_panel, panel = _raw("/panel")
        self.assertEqual(s_root, 200)
        self.assertEqual(s_panel, 200)
        self.assertEqual(root, panel, "/ and /panel must serve identical bytes")
        # positively the studio, not the console
        self.assertIn("<title>Sutra</title>", root)
        self.assertIn('id="panes"', root)
        self.assertNotIn("xterm", root.lower())
        # and the legacy console is still reachable, just not on the front door
        s_legacy, legacy = _raw("/legacy/term")
        self.assertEqual(s_legacy, 200)
        self.assertIn("xterm", legacy.lower())

    def test_06b_charters_include_those_on_retired_domains(self):
        """Regression: scoping /api/org/charters to live_refs() hid the charter
        stranded on the retired 'Agent Ops' tombstone -- the exact ORG-002
        defect the Charters screen exists to surface (it renders a 'tombstone'
        pill on the owner cell). Scope by TENANT, never by liveness."""
        _, charters = _get("/api/org/charters?all_tenants=true")
        _, tree = _get("/api/org/tree?include_retired=true&all_tenants=true")
        retired_refs = {d["ref"] for d in tree if d["status"] == "retired"}
        self.assertTrue(retired_refs, "fixture must seed a retired domain")
        orphaned = [c for c in charters if c["domain_ref"] in retired_refs]
        self.assertTrue(orphaned,
            "a charter homed to a retired domain must still be returned -- "
            "hiding it hides the defect the screen exists to show")
        # and the count must equal every charter body on disk for that scope
        _, stats = _get("/api/org/stats")
        self.assertEqual(len(charters), stats["charters"],
            "charters endpoint must not silently drop rows vs the on-disk count")

    def test_06_charters_shape(self):
        status, rows = _get("/api/org/charters")
        self.assertEqual(status, 200)
        self.assertGreater(len(rows), 0)
        for c in rows:
            for field in ("id", "title", "purpose", "domain_ref"):
                self.assertIn(field, c)
        ids = [c["id"] for c in rows]
        self.assertEqual(len(ids), len(set(ids)), "duplicate charter ids returned")

    # -------------------------------------------------------- placements --

    def test_07_placements_have_derived_mode(self):
        status, rows = _get("/api/org/placements")
        self.assertEqual(status, 200)
        self.assertGreater(len(rows), 0)
        for p in rows:
            self.assertIn("mode", p)
            self.assertIn(p["mode"], ("match", "floor"))
            floor = p["mode"] == "floor"
            below = p["confidence"] < 0.45
            self.assertEqual(floor, below,
                              "mode/confidence disagree: %r" % p)
        # newest-first
        ts = [p["ts_ms"] for p in rows]
        self.assertEqual(ts, sorted(ts, reverse=True))

    def test_08_placements_all_tenants_includes_acme(self):
        _, scoped = _get("/api/org/placements")
        _, everyone = _get("/api/org/placements?all_tenants=true")
        self.assertGreaterEqual(len(everyone), len(scoped))

    # ------------------------------------------------------------ health --

    def test_09_health_surfaces_seeded_defects(self):
        status, health = _get("/api/org/health")
        self.assertEqual(status, 200)
        self.assertIn("mece", health)
        self.assertIn("lint", health)

    # ----------------------------------------------------------- history --

    def test_09b_history_returns_events_newest_first(self):
        status, h = _get("/api/org/history")
        self.assertEqual(status, 200)
        self.assertIn("events", h)
        self.assertIn("meta", h)
        self.assertGreater(len(h["events"]), 0)
        ts = [e.get("ts_ms") or 0 for e in h["events"]]
        self.assertEqual(ts, sorted(ts, reverse=True), "history must be newest-first")

    def test_09c_history_completeness_is_marked_derived(self):
        _, h = _get("/api/org/history")
        m = h["meta"]
        # history_complete_from_ms is NOT a stored engine field -- it is derived
        # from the earliest before/after-carrying event. It must say so, or a
        # caller will treat it as authoritative stored state.
        self.assertIs(m["derived"], True)
        self.assertEqual(m["domain_index_lines"], len(h["events"]))
        # enriched + events_without_before partitions EVERY row. legacy_events
        # is the narrower count (restructures only) the timeline greys out --
        # see test_09d -- so it is a subset, never the complement.
        self.assertEqual(m["enriched_events"] + m["events_without_before"], len(h["events"]))
        self.assertLessEqual(m["legacy_events"], m["events_without_before"])
        if m["enriched_events"]:
            enriched_ts = [e["ts_ms"] for e in h["events"] if e.get("before") is not None]
            self.assertEqual(m["history_complete_from_ms"], min(enriched_ts))
        else:
            self.assertIsNone(m["history_complete_from_ms"])

    def test_09d_history_legacy_rows_lack_before_snapshots(self):
        """`legacy_events` is rendered as "N legacy row(s) below the line"
        directly under the timeline, so it must count the rows the timeline
        actually greys out: `event == "domain_restructured" && !before`. A
        MINT has no `before` because there was no prior state, not because a
        snapshot was lost -- counting mints as legacy printed 5 under a
        timeline showing 1 greyed row."""
        _, h = _get("/api/org/history")
        greyed = [e for e in h["events"]
                  if e.get("event") == "domain_restructured" and e.get("before") is None]
        self.assertEqual(len(greyed), h["meta"]["legacy_events"])
        no_before = [e for e in h["events"] if e.get("before") is None]
        self.assertEqual(len(no_before), h["meta"]["events_without_before"])
        # the fixture seeds both shapes, so this is a real distinction here
        self.assertLess(len(greyed), len(no_before))

    # --------------------------------------------------------- classify ---

    def _placement_file_count(self):
        # count via the stats endpoint rather than touching the filesystem
        # directly, so the assertion exercises the same code path a real
        # client would see.
        return _get("/api/org/stats")[1]["placements"]

    def test_10_classify_dense_evidence_match_clears_the_real_floor(self):
        # NOTE: the real engine's confidence formula (score_domains' saturating
        # absolute term + margin-over-runner-up, placement_engine.py's
        # classify()) is NOT the earlier client-side Jaccard approximation --
        # verified directly against this fixture: "Draft the quarterly report
        # for Acme" scores 0.2372 (floor) against the real engine, not the
        # earlier ~0.51 "match". Dense, evidence-term-heavy phrasing is what
        # clears the real 0.45 floor; ordinary task phrasing mostly doesn't
        # with this fixture's sparse (5-7 term) mint_evidence lists. This
        # test proves match-mode is genuinely reachable end-to-end.
        before = self._placement_file_count()
        status, r = _post("/api/classify",
                           {"text": "terraform runbook backup restore infrastructure"})
        self.assertEqual(status, 200)
        self.assertEqual(r.get("mode"), "match")
        self.assertGreaterEqual(r["confidence"], 0.45)
        self.assertEqual(r.get("domain_name"), "Infrastructure")
        self.assertIn("placement", r)
        after = self._placement_file_count()
        self.assertEqual(after, before + 1, "classify must write EXACTLY one placement")

    def test_11_classify_ordinary_phrasing_holds_at_ancestor(self):
        # "Draft the quarterly report for Acme" is exactly the kind of
        # ordinary, on-topic request an operator would actually type -- and
        # against the real engine + this sparse fixture it holds at the
        # floor. That is the honest, demonstrated behavior of I-P9, not a
        # test artifact: a run of these is the signal the org is missing a
        # department, per §3.6(c) of the design doc.
        before = self._placement_file_count()
        status, r = _post("/api/classify", {"text": "Draft the quarterly report for Acme"})
        self.assertEqual(status, 200)
        self.assertEqual(r.get("mode"), "floor")
        self.assertLess(r["confidence"], 0.45)
        self.assertIn("held_at_ref", r)
        after = self._placement_file_count()
        # floor still resolves to an ancestor with a charter (root always has
        # one) and writes a row -- floor is "held", not "refused".
        self.assertEqual(after, before + 1)

    def test_11b_classify_no_candidate_at_all_is_mode_none(self):
        before = self._placement_file_count()
        status, r = _post("/api/classify",
                           {"text": "Negotiate the office lease renewal in Berlin"})
        self.assertEqual(status, 200)
        self.assertEqual(r.get("mode"), "none")
        self.assertIn("blocked", r)
        after = self._placement_file_count()
        self.assertEqual(after, before, "mode=none must never write a placement")

    def test_12_classify_never_mints_a_domain(self):
        before_domains = _get("/api/org/stats")[1]["domains"]
        texts = [
            "xyzzy plugh quux never seen before",
            "the quarterly acme report",
            "terraform runbook backup restore",
            "negotiate berlin office lease",
            "totally unrelated gibberish request zzz",
        ]
        for t in texts:
            status, _ = _post("/api/classify", {"text": t})
            self.assertEqual(status, 200)
        after_domains = _get("/api/org/stats")[1]["domains"]
        self.assertEqual(before_domains, after_domains,
                          "classify() must never mint a domain (resolve() would; we forbid it)")

    def test_13_classify_empty_text_is_400_not_500(self):
        status, r = _post("/api/classify", {"text": "   "})
        self.assertEqual(status, 400)

    def test_14_classify_concurrent_calls_do_not_corrupt_current_jsonl(self):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(
                lambda i: _post("/api/classify", {"text": "concurrent test task %d" % i}),
                range(5)))
        for status, r in results:
            self.assertEqual(status, 200)
        status, rows = _get("/api/org/placements")
        self.assertEqual(status, 200)
        ids = [p["id"] for p in rows]
        self.assertEqual(len(ids), len(set(ids)), "duplicate placement ids under concurrency")

    # ---------------------------------------------------------- simulate --

    def test_15_simulate_empty_ops_surfaces_seeded_defects(self):
        status, sim = _post("/api/org/simulate", {"ops": []})
        self.assertEqual(status, 200)
        codes = {f["code"] for f in sim["findings"]}
        self.assertIn("ORG-002", codes, "seeded tombstone charter should fire ORG-002")
        self.assertIn("ORG-001", codes, "Market Intel <-> Synthesis overlap should fire ORG-001")
        self.assertIn("ORG-008", codes, "charterless departments should fire ORG-008")
        self.assertTrue(len(sim.get("not_checked", [])) > 0)
        nc_codes = {n["code"] for n in sim["not_checked"]}
        for forbidden in ("ORG-005", "ORG-012", "ORG-019"):
            self.assertIn(forbidden, nc_codes)

    def test_16_simulate_ancestor_pair_is_exempt_from_org001(self):
        status, sim = _post("/api/org/simulate", {"ops": []})
        subjects = " ".join(f["subject"] for f in sim["findings"] if f["code"] == "ORG-001")
        self.assertNotIn("Research ↔ Market Intel", subjects)
        self.assertNotIn("Research <-> Market Intel", subjects)

    def test_17_simulate_move_creating_a_cycle_is_flagged(self):
        _, tree = _get("/api/org/tree")
        research = next(r for r in tree if r["name"] == "Research")
        child = next(r for r in tree if r["parent_ref"] == research["ref"])
        status, sim = _post("/api/org/simulate",
                             {"ops": [{"op": "move", "ref": research["ref"], "target": child["ref"]}]})
        self.assertEqual(status, 200)
        codes = {f["code"] for f in sim["findings"]}
        self.assertIn("ORG-006", codes)

    def test_18_simulate_does_not_mutate_the_registry(self):
        before = _get("/api/org/stats")[1]
        _, tree = _get("/api/org/tree")
        a, b = tree[0], tree[1]
        _post("/api/org/simulate", {"ops": [{"op": "move", "ref": a["ref"], "target": b["ref"]}]})
        after = _get("/api/org/stats")[1]
        self.assertEqual(before, after, "simulate() must be pure -- no registry mutation")

    # -------------------------------------------------------------- draft -

    def test_19_draft_roundtrip_and_forced_null_validation(self):
        # DRAFTS_DIR is a shared, persistent path by design (the dev server's
        # one real draft, analogous to ~/.sutra-ui/drafts/) -- NOT per-test
        # isolated. Back up and restore whatever was already there instead of
        # assuming an empty starting state.
        import org_api
        had_prior = org_api.DRAFT_PATH.exists()
        prior_bytes = org_api.DRAFT_PATH.read_bytes() if had_prior else None
        try:
            marker = "test-marker-%d" % int(time.time() * 1000)
            status, saved = _post("/api/org/draft", {
                "ops": [{"op": "move", "ref": "dref-x", "target": "dref-y"}],
                "rationale": marker,
                "validated_at_ms": 999999999999,  # client tries to lie
            })
            self.assertEqual(status, 200)
            self.assertIsNone(saved["validated_at_ms"], "server must force validated_at_ms null")
            self.assertEqual(saved["plan_origin"], "studio-drag")
            self.assertEqual(saved["rationale"], marker)
            self.assertEqual(len(saved["ops"]), 1)

            status, reread = _get("/api/org/draft")
            self.assertEqual(status, 200)
            self.assertEqual(reread["rationale"], marker)
            self.assertEqual(len(reread["ops"]), 1)
            self.assertIsNone(reread["validated_at_ms"])
        finally:
            if had_prior:
                org_api.DRAFT_PATH.write_bytes(prior_bytes)
            elif org_api.DRAFT_PATH.exists():
                org_api.DRAFT_PATH.unlink()

    def test_20_draft_file_lands_outside_any_sutra_native_home(self):
        import org_api
        self.assertNotIn(str(org_api.DRAFTS_DIR), self.tmpdir)
        self.assertFalse(str(org_api.DRAFT_PATH).startswith(self.tmpdir))

    # --------------------------------------------------- static / hygiene --

    def test_21_perm_mode_default_is_not_acceptedits(self):
        env = dict(os.environ)
        env.pop("SUTRA_UI_PERMISSION_MODE", None)
        out = subprocess.check_output(
            [VENV_PY, "-c", "import app; print(app.PERM_MODE)"],
            cwd=HERE, env=env, stderr=subprocess.STDOUT,
        ).decode("utf-8").strip().splitlines()[-1]
        self.assertNotEqual(out, "acceptEdits")
        self.assertEqual(out, "plan")

    def test_22_forbidden_calls_are_absent_from_new_files(self):
        # test_forbidden_calls.py already does this correctly (alias-resolved
        # `<E>.<name>(` call-site regex, so it doesn't self-match this very
        # safety docstring the way a naive substring search would). Reuse it
        # rather than duplicate a worse version.
        import test_forbidden_calls as tfc
        tfc.test_files_exist()
        tfc.test_org_api_declares_its_engine_import()
        tfc.test_no_forbidden_mutator_calls()  # raises AssertionError on violation

    def test_24_tree_orders_the_tenant_of_record_first(self):
        """D-numbering is PER TENANT, so both roots are "D0" and a sort on
        `path` alone is a tie broken by dict order -- T-acme's root could come
        out first. The panel takes `the first row with no parent_ref` as the
        create-department parent default, so that tie decided which TENANT a
        minted department landed in: the dropdown read "D0 Sutra Labs" while
        the copyable CLI string carried --parent <T-acme root>."""
        _, rows = _get("/api/org/tree?include_retired=true&all_tenants=true")
        self.assertEqual(rows[0]["tenant_id"], "T-local")
        roots = [r for r in rows if r["parent_ref"] is None]
        self.assertGreaterEqual(len(roots), 2)
        self.assertEqual(roots[0]["tenant_id"], "T-local",
                          "the tenant of record's root must lead the roots")
        # every T-local row precedes every foreign row
        tenants = [r["tenant_id"] for r in rows]
        self.assertEqual(tenants, sorted(tenants, key=lambda t: 0 if t == "T-local" else 1))
        # ...and the order is stable across reads (no dict-iteration wobble)
        _, again = _get("/api/org/tree?include_retired=true&all_tenants=true")
        self.assertEqual([r["ref"] for r in rows], [r["ref"] for r in again])

    def test_25_matched_terms_are_an_intersection_not_the_utterance(self):
        """matched_terms is rendered as "Filed to X on `a` `b`" -- a claim
        about WHY that domain won. Returning the raw utterance tokens made it
        a lie: a turn held at the root reported terms the root's mint_evidence
        does not contain."""
        _, tree = _get("/api/org/tree?all_tenants=true")
        by_ref = {r["ref"]: r for r in tree}

        # a floor hold at the root: nothing in the utterance matched the
        # winner's evidence, and [] is the honest answer
        status, held = _post("/api/classify", {"text": "Draft the quarterly report for Acme"})
        self.assertEqual(status, 200)
        self.assertEqual(held["mode"], "floor")
        root = by_ref[held["domain_ref"]]
        self.assertEqual(held["matched_terms"], [],
                          "the root's mint_evidence is %r -- none of these terms is in it"
                          % (root["mint_evidence"],))

        # a real match: every reported term is in the winner's own evidence
        status, hit = _post("/api/classify",
                             {"text": "terraform runbook backup restore infrastructure"})
        self.assertEqual(status, 200)
        self.assertEqual(hit["mode"], "match")
        won = by_ref[hit["domain_ref"]]
        allowed = set(won["mint_evidence"] or []) | set(str(won["name"]).lower().split())
        self.assertTrue(hit["matched_terms"])
        for term in hit["matched_terms"]:
            self.assertIn(term, allowed,
                           "%r is not in %r's name or mint_evidence" % (term, won["name"]))
        # and terms that were typed but are NOT the winner's evidence are gone
        self.assertNotIn("the", hit["matched_terms"])

    def test_26_simulate_measures_staleness_against_the_caller_s_clock(self):
        """reorg_sim derived "now" as max(placement.ts_ms) to stay pure, while
        the panel bands charter freshness against the browser's Date.now() --
        so ORG-009/ORG-020 and the freshness pills could contradict each other
        on the same screen. One clock, passed in."""
        _, now_default = _post("/api/org/simulate", {"ops": []})
        far_future = int(time.time() * 1000) + 400 * 86400000
        _, aged = _post("/api/org/simulate", {"ops": [], "now_ms": far_future})
        n_default = len([f for f in now_default["findings"] if f["code"] == "ORG-020"])
        n_aged = len([f for f in aged["findings"] if f["code"] == "ORG-020"])
        self.assertGreater(n_aged, n_default,
                            "a later clock must age MORE standing charters past the stale band")
        # a clock before the fixture's own placements ages nothing
        _, young = _post("/api/org/simulate", {"ops": [], "now_ms": 0})
        self.assertEqual([f for f in young["findings"] if f["code"] in ("ORG-009", "ORG-020")], [])
        # the pure default (no now_ms passed to the function) is untouched
        import reorg_sim
        import inspect
        self.assertIn("now_ms", inspect.signature(reorg_sim.simulate).parameters)
        self.assertIsNone(inspect.signature(reorg_sim.simulate).parameters["now_ms"].default)

    def test_23_panel_route_serves_the_static_file(self):
        # HTMLResponse -> json.loads (used by _http) would fail; hit it raw.
        req = urllib.request.Request("http://127.0.0.1:%d/panel" % self.port)
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8", "replace")
            self.assertIn("<title>", body)

    # ============================================================= new tier ==
    # The tests below extend (never replace) the ones above. Each one pins a
    # claim the panel renders verbatim to the operator, so a regression is a
    # visible lie on screen rather than an internal detail.

    def test_27_matched_terms_are_never_the_raw_utterance_tokens(self):
        """The generalisation of test_25: for EVERY utterance, whatever comes
        back as matched_terms must be a subset of the WINNING domain's own
        evidence token set (name tokens + mint_evidence), lexed by the engine's
        own tokenizer. The specific failure this pins is the one the panel
        renders: "Filed to <domain> on `a` `b`" where `a`/`b` were merely typed,
        not matched. An utterance built entirely from words no domain's
        evidence contains must therefore report [] -- and must NOT echo back
        what was typed."""
        import placement_engine as E  # the same lexer score_domains() uses
        import reorg_sim

        _, tree = _get("/api/org/tree?include_retired=true&all_tenants=true")
        by_ref = {r["ref"]: r for r in tree}

        def evidence_tokens(row):
            return {str(t).lower() for t in
                    E.tokenize(row.get("name") or "", *(row.get("mint_evidence") or []))}

        # (a) an utterance whose content words appear in NO domain's evidence,
        #     but which still resolves (held at an ancestor).
        offbeat = "Draft the quarterly report for Acme"
        status, r = _post("/api/classify", {"text": offbeat})
        self.assertEqual(status, 200)
        self.assertIsNotNone(r.get("domain_ref"))
        won = by_ref[r["domain_ref"]]
        typed = reorg_sim.tok(offbeat)
        self.assertTrue(typed, "the probe utterance must have content tokens")
        self.assertFalse(typed & evidence_tokens(won),
                          "probe is only meaningful if none of %r is in %r's evidence"
                          % (sorted(typed), won["name"]))
        self.assertEqual(r["matched_terms"], [],
                          "nothing in %r is in %r's evidence, so the only honest "
                          "answer is [] -- got %r"
                          % (offbeat, won["name"], r["matched_terms"]))

        # (b) the invariant across a spread of phrasings: always a SUBSET of the
        #     winner's evidence, never the raw utterance.
        probes = [
            "Draft the quarterly report for Acme",
            "terraform runbook backup restore infrastructure",
            "please review the onboarding checklist tomorrow",
            "fix the flaky evaluation harness for the agent",
            "the quarterly acme report",
        ]
        saw_nonempty = False
        saw_strict_subset = False
        for text in probes:
            status, res = _post("/api/classify", {"text": text})
            self.assertEqual(status, 200)
            got = res.get("matched_terms")
            self.assertIsInstance(got, list, "matched_terms must always be a list: %r" % res)
            if not res.get("domain_ref"):
                self.assertEqual(got, [], "no winner => nothing matched: %r" % res)
                continue
            allowed = evidence_tokens(by_ref[res["domain_ref"]])
            typed = reorg_sim.tok(text)
            got_set = {t.lower() for t in got}
            # the exact contract: matched_terms IS the intersection. Stronger
            # than "not the raw utterance" -- it pins both the passthrough bug
            # (got == typed when typed ⊄ evidence) and any over-filtering.
            self.assertEqual(got_set, typed & allowed,
                              "matched_terms for %r must be exactly (utterance ∩ %r's "
                              "evidence); got %r, expected %r"
                              % (text, res.get("domain_name"), sorted(got_set),
                                 sorted(typed & allowed)))
            self.assertTrue(got_set <= allowed)
            self.assertTrue(got_set <= typed,
                             "matched_terms must also be terms that were actually said")
            if got:
                saw_nonempty = True
            if got_set < typed:
                # words were typed that the winner's evidence does not contain,
                # and they were correctly dropped -- this is the passthrough bug
                # actually being exercised rather than trivially satisfied.
                saw_strict_subset = True
        self.assertTrue(saw_nonempty,
                         "at least one probe must genuinely match, or this test only "
                         "proves the endpoint returns [] unconditionally")
        self.assertTrue(saw_strict_subset,
                         "no probe typed a word outside the winner's evidence -- the "
                         "passthrough bug would not have been caught")

    def test_28_legacy_events_counts_only_restructures_without_before(self):
        """Sharper than test_09d: it is not enough that legacy_events <=
        events_without_before. The fixture seeds BOTH shapes -- restructures
        with no `before` (genuinely unreplayable) and mints with no `before`
        (nothing was lost; there was no prior state). legacy_events is printed
        as "N legacy row(s) below the line" under a timeline that greys exactly
        the first shape, so counting the second inflates the number the
        operator reads."""
        _, h = _get("/api/org/history")
        events = h["events"]
        meta = h["meta"]

        restructures_without_before = [
            e for e in events
            if e.get("event") == "domain_restructured" and e.get("before") is None]
        other_without_before = [
            e for e in events
            if e.get("event") != "domain_restructured" and e.get("before") is None]

        # the fixture must actually contain the distinguishing shape, or the
        # assertion below is vacuous and a naive count would pass too
        self.assertTrue(other_without_before,
                         "fixture must seed non-restructure events lacking `before` "
                         "(mints) for this distinction to be testable")
        self.assertTrue(restructures_without_before,
                         "fixture must seed at least one unreplayable restructure")

        self.assertEqual(meta["legacy_events"], len(restructures_without_before))
        self.assertNotEqual(meta["legacy_events"], meta["events_without_before"],
                             "legacy_events must NOT be the every-row-without-before count")
        self.assertEqual(meta["events_without_before"],
                          len(restructures_without_before) + len(other_without_before))
        # every mint is excluded by name, not by accident of ordering
        for e in other_without_before:
            self.assertNotEqual(e.get("event"), "domain_restructured")

    def test_30_simulate_now_ms_moves_staleness_in_both_directions(self):
        """now_ms is the ONE clock both halves of the screen band against. Pin
        it from both ends: a clock far in the past must age nothing, a clock far
        in the future must age everything, and the two answers must differ."""
        day = 86400000
        far_past = 1                      # before every seeded placement
        far_future = int(time.time() * 1000) + 3650 * day

        s_past, past = _post("/api/org/simulate", {"ops": [], "now_ms": far_past})
        s_fut, fut = _post("/api/org/simulate", {"ops": [], "now_ms": far_future})
        self.assertEqual(s_past, 200)
        self.assertEqual(s_fut, 200)

        def stale(sim):
            return [f for f in sim["findings"] if f["code"] in ("ORG-009", "ORG-020")]

        self.assertEqual(stale(past), [],
                          "a clock before every placement cannot call anything stale: %r"
                          % stale(past))
        self.assertTrue(stale(fut),
                         "a clock 10 years out must age the seeded charters past the band")
        self.assertNotEqual(len(stale(past)), len(stale(fut)),
                             "now_ms was accepted but had no effect on the answer")

        # everything that is NOT clock-dependent must be identical between the
        # two runs -- now_ms must not perturb structural findings
        def structural(sim):
            return sorted((f["code"], f["subject"]) for f in sim["findings"]
                          if f["code"] not in ("ORG-009", "ORG-020"))
        self.assertEqual(structural(past), structural(fut),
                          "now_ms changed a structural finding -- it must only band staleness")

        # the parameter is genuinely optional (a curl / this suite may omit it)
        s_none, none = _post("/api/org/simulate", {"ops": []})
        self.assertEqual(s_none, 200)
        self.assertEqual(structural(none), structural(fut))

    def test_31_org010_fires_only_when_the_captured_base_is_actually_stale(self):
        """ORG-010 is "the registry moved since this draft captured its base".
        It is the only finding that comes from the CLIENT's payload rather than
        the registry, so it needs both directions pinned: a stale base MUST
        block, and the true base must NOT -- a false ORG-010 makes Rebase the
        only reachable action on a draft that is perfectly current."""
        _, h = _get("/api/org/history")
        true_lines = h["meta"]["domain_index_lines"]
        self.assertGreater(true_lines, 0)

        def codes(body):
            status, sim = _post("/api/org/simulate", body)
            self.assertEqual(status, 200)
            return {f["code"] for f in sim["findings"]}

        # (a) deliberately stale base -> ORG-010, severity block
        status, stale_sim = _post("/api/org/simulate",
                                   {"ops": [], "base": {"domain_index_lines": true_lines + 7}})
        self.assertEqual(status, 200)
        org010 = [f for f in stale_sim["findings"] if f["code"] == "ORG-010"]
        self.assertTrue(org010, "a base that no longer matches the registry must fire ORG-010")
        self.assertEqual(org010[0]["sev"], "block")

        # (b) the true value -> no ORG-010
        self.assertNotIn("ORG-010", codes({"ops": [], "base": {"domain_index_lines": true_lines}}))
        # (c) a base that carries no fingerprint at all -> nothing to compare
        self.assertNotIn("ORG-010", codes({"ops": [], "base": {}}))
        # (d) no base at all -> nothing to compare
        self.assertNotIn("ORG-010", codes({"ops": []}))
        # (e) stale in the OTHER direction (fewer lines than reality) still fires
        self.assertIn("ORG-010",
                      codes({"ops": [], "base": {"domain_index_lines": max(0, true_lines - 1)}}))

        # and the staleness check reads the registry live: after a classify
        # writes a placement, the DOMAIN_INDEX line count is unchanged (classify
        # never mints), so the true base must STILL be clean.
        _post("/api/classify", {"text": "terraform runbook backup restore infrastructure"})
        _, h2 = _get("/api/org/history")
        self.assertEqual(h2["meta"]["domain_index_lines"], true_lines,
                          "classify must not append to the domain index")
        self.assertNotIn("ORG-010", codes({"ops": [], "base": {"domain_index_lines": true_lines}}))

    # ======================================================== providers ====
    # These endpoints shipped without a single test. Everything below asserts
    # an INVARIANT that is checkable on any machine (installed == which(), a
    # refusal carries the reason) rather than hard-coding this laptop's PATH --
    # a test that says "codex is absent" would start lying the day someone
    # installs codex, which is exactly the kind of stale claim this suite
    # exists to prevent.

    @staticmethod
    def _which(binary):
        import shutil as _sh
        return _sh.which(binary)

    def test_35_providers_installed_is_which_and_nothing_else(self):
        """`installed` is the ONE claim the panel renders as a green dot, and
        the failure mode this endpoint was written to prevent is claiming a
        provider is available on the strength of a leftover config directory.
        So: recompute shutil.which() here, independently, and require the
        endpoint to agree -- including for a provider that HAS a config dir but
        no binary, which is the case this machine actually exhibits (~/.codex
        exists, `codex` is not on PATH)."""
        status, body = _get("/api/providers")
        self.assertEqual(status, 200)
        self.assertIn("providers", body)
        ids = [p["id"] for p in body["providers"]]
        self.assertEqual(ids, ["claude", "codex", "gemini"],
                         "the catalogue is fixed and ordered by precedence")

        for p in body["providers"]:
            for field in ("id", "name", "bin", "installed", "configured",
                          "config_dir", "reason", "default", "runnable"):
                self.assertIn(field, p, "%s is missing %r" % (p["id"], field))
            self.assertEqual(
                p["installed"], self._which(p["bin"]) is not None,
                "%s: `installed` must be shutil.which(%r) and nothing else -- "
                "a config directory is not evidence of a binary"
                % (p["id"], p["bin"]))
            self.assertEqual(
                p["configured"], os.path.isdir(os.path.expanduser(p["config_dir"])),
                "%s: `configured` must be the config dir's existence" % p["id"])
            self.assertIn("adapter", p, "%s is missing 'adapter'" % p["id"])
            self.assertEqual(
                p["runnable"],
                p["installed"] and p["configured"] and p["adapter"],
                "%s: runnable == installed AND configured AND adapter -- an "
                "installed CLI we cannot drive is not runnable" % p["id"])
            if p["runnable"]:
                self.assertIsNone(p["reason"], "a runnable provider has no excuse")
            else:
                self.assertTrue(p["reason"],
                                "%s is not runnable and must say why -- the UI has "
                                "nothing else to render" % p["id"])
                # the reason must name the half that failed, with the path, so
                # "unavailable" is never bare
                if p["configured"] and not p["installed"]:
                    self.assertIn(p["bin"], p["reason"])
                    self.assertIn(p["config_dir"], p["reason"])

    def test_36_a_config_dir_alone_never_makes_a_provider_installed(self):
        """The provable negative behind test_35: for every catalogued provider
        whose binary is NOT on PATH, `installed` is False no matter what its
        config directory looks like. On this machine ~/.codex exists and
        `codex` does not -- the exact shape that would tempt an
        availability check into inferring one from the other."""
        _, body = _get("/api/providers")
        absent = [p for p in body["providers"] if self._which(p["bin"]) is None]
        self.assertTrue(absent, "no absent provider to test against on this machine")
        for p in absent:
            self.assertFalse(p["installed"], "%s has no binary" % p["id"])
            self.assertFalse(p["runnable"], "%s cannot run" % p["id"])

    def test_37_active_is_runnable_and_ignored_overrides_are_surfaced(self):
        _, body = _get("/api/providers")
        by_id = {p["id"]: p for p in body["providers"]}
        self.assertIn("active", body)
        self.assertIn("active_source", body)
        self.assertIsInstance(body.get("ignored"), list)
        if body["active"] is not None:
            self.assertTrue(by_id[body["active"]]["runnable"],
                            "the ACTIVE provider must be runnable -- handing back "
                            "an id whose binary is missing moves the failure into "
                            "the websocket, where it looks like a dead socket")
        for ig in body["ignored"]:
            self.assertIn("source", ig)
            self.assertTrue(ig.get("reason"), "a dropped override must say why")

    def test_38_setting_an_unrunnable_provider_is_REFUSED_with_the_reason(self):
        """The point of the whole module: the UI must not be able to select a
        provider that cannot start."""
        _, body = _get("/api/providers")
        before = body["active"]
        blocked = [p for p in body["providers"] if not p["runnable"]]
        self.assertTrue(blocked, "no unrunnable provider to refuse on this machine")
        for p in blocked:
            status, err = _post("/api/providers/active", {"id": p["id"]})
            self.assertEqual(status, 400,
                             "%s is not runnable and must be refused, not stored"
                             % p["id"])
            self.assertIn("not runnable", err["detail"])
            self.assertIn(p["reason"], err["detail"],
                          "the refusal must carry the SPECIFIC reason, not a "
                          "generic 'unavailable'")
        # the refusal is not a partial write: active is untouched
        _, after = _get("/api/providers")
        self.assertEqual(after["active"], before)

    def test_39_unknown_provider_id_is_400_and_lists_the_known_ids(self):
        status, err = _post("/api/providers/active", {"id": "not-a-provider"})
        self.assertEqual(status, 400)
        self.assertIn("unknown provider", err["detail"])
        for known in ("claude", "codex", "gemini"):
            self.assertIn(known, err["detail"])

    def test_40_setting_a_runnable_provider_persists_and_is_readable_back(self):
        _, body = _get("/api/providers")
        runnable = [p for p in body["providers"] if p["runnable"]]
        if not runnable:
            self.skipTest("no runnable provider on this machine")
        pid = runnable[0]["id"]
        status, out = _post("/api/providers/active", {"id": pid})
        self.assertEqual(status, 200)
        self.assertEqual(out["active"], pid)
        _, settings = _get("/api/settings")
        self.assertEqual(settings["settings"]["provider"], pid)
        self.assertEqual(settings["settings"]["provider_source"], "settings",
                         "once chosen, the choice comes from the file -- not "
                         "from the catalog-order fallback")

    # ========================================================= settings ====

    def test_41_settings_shape_and_the_default_is_plan(self):
        status, body = _get("/api/settings")
        self.assertEqual(status, 200)
        st = body["settings"]
        for key in ("provider", "permission_mode", "workdir"):
            self.assertIn(key, st, "%r is part of the contract" % key)
        self.assertEqual(st["permission_mode"], "plan",
                         "SAFETY rule 4: the default must not auto-approve edits")
        modes = {m["id"]: m for m in body["permission_modes"]}
        # SIX, not three. `claude --help` on the installed binary lists
        # acceptEdits / auto / bypassPermissions / manual / dontAsk / plan; the
        # panel offered three, so half the CLI's modes were unreachable from the
        # UI. Verified against the binary, not assumed.
        self.assertEqual(set(modes), {"plan", "acceptEdits", "bypassPermissions",
                                      "auto", "manual", "dontAsk"})
        self.assertTrue(modes["plan"]["default"])
        self.assertFalse(modes["plan"]["writes_files"])
        # the two modes that write files must SAY they write files -- this flag
        # is what the panel renders as the warning badge
        self.assertTrue(modes["acceptEdits"]["writes_files"])
        self.assertTrue(modes["bypassPermissions"]["writes_files"])
        for m in body["permission_modes"]:
            self.assertTrue(m["note"], "%s has no explanation" % m["id"])

    def test_42_settings_rejects_an_unknown_permission_mode_without_storing_it(self):
        _, before = _get("/api/settings")
        status, err = _post("/api/settings", {"permission_mode": "yolo"})
        self.assertEqual(status, 400)
        self.assertIn("unknown permission_mode", err["detail"])
        _, after = _get("/api/settings")
        self.assertEqual(after["settings"]["permission_mode"],
                         before["settings"]["permission_mode"],
                         "a rejected mode must not be silently downgraded OR stored")

    def test_43_settings_writes_outside_any_sutra_native_home(self):
        """Panel preferences are not governance state. If the settings file
        landed under SUTRA_NATIVE_HOME, POST /api/settings would be a registry
        write -- which this surface is not allowed to make."""
        _, body = _get("/api/settings")
        path = body["settings"]["settings_path"]
        self.assertFalse(path.startswith(self.tmpdir),
                         "settings must not live inside SUTRA_NATIVE_HOME (%s)" % path)
        self.assertTrue(path.startswith(self.userdir),
                        "the test run must be writing to its own tempdir, not the "
                        "operator's ~/.sutra-ui -- got %s" % path)

    def test_44_empty_settings_post_is_400_not_a_silent_noop(self):
        status, err = _post("/api/settings", {})
        self.assertEqual(status, 400)
        self.assertIn("nothing to update", err["detail"])

    def test_45_settings_partial_update_touches_only_the_key_sent(self):
        _, before = _get("/api/settings")
        target = os.path.join(self.userdir, "wd-roundtrip")
        status, out = _post("/api/settings", {"workdir": target})
        self.assertEqual(status, 200)
        self.assertEqual(out["settings"]["workdir"], target)
        # permission_mode and provider were NOT in the body and must be intact
        self.assertEqual(out["settings"]["permission_mode"],
                         before["settings"]["permission_mode"])
        self.assertEqual(out["settings"]["provider"], before["settings"]["provider"])
        _, reread = _get("/api/settings")
        self.assertEqual(reread["settings"]["workdir"], target)

    def test_46_settings_rejects_an_unrunnable_provider_like_the_other_endpoint(self):
        """POST /api/settings and POST /api/providers/active are two doors to
        the same write. A guard on only one of them is not a guard."""
        _, prov = _get("/api/providers")
        blocked = [p for p in prov["providers"] if not p["runnable"]]
        if not blocked:
            self.skipTest("every catalogued provider is runnable here")
        status, err = _post("/api/settings", {"provider": blocked[0]["id"]})
        self.assertEqual(status, 400)
        self.assertIn("not runnable", err["detail"])

    # ========================================================== tenants ====

    def test_52_sessions_are_real_files_under_dot_claude_projects(self):
        """The panel used to manufacture sessions by grouping placement rows by
        path segment ("Scratchpad -- 3 turns"). Nothing like that ever existed.
        Every id this endpoint returns must be a file that is actually on
        disk -- that is the only definition of "real" available here."""
        import glob
        status, rows = _get("/api/sessions")
        self.assertEqual(status, 200)
        self.assertIsInstance(rows, list)
        projects = os.path.expanduser("~/.claude/projects")
        if not os.path.isdir(projects):
            self.skipTest("no ~/.claude/projects on this machine")
        for r in rows:
            hits = glob.glob(os.path.join(projects, "*", r["id"] + ".jsonl"))
            self.assertTrue(hits,
                            "session %r is not a transcript on disk -- it was "
                            "invented" % r["id"])
            self.assertEqual(r["size"], os.path.getsize(hits[0]),
                             "%s: size must be the file's, not a guess" % r["id"])
            self.assertEqual(r["project"], os.path.basename(os.path.dirname(hits[0])))
            # The title must be a QUOTATION from the transcript, never
            # generated. Re-derive the candidate prompts here from the raw
            # JSONL -- independently of session_reader -- and require the
            # title to be the head of one of them.
            if r["title"] == "(no prompt)":
                continue
            prompts = []
            with io.open(hits[0], encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 400:
                        break
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("type") != "user":
                        continue
                    msg = ev.get("message")
                    if not isinstance(msg, dict):
                        continue
                    c = msg.get("content")
                    if isinstance(c, str):
                        prompts.append(c)
                    elif isinstance(c, list):
                        prompts.append("\n".join(
                            b.get("text", "") for b in c
                            if isinstance(b, dict) and b.get("type") == "text"))
            norm = lambda t: " ".join(t.split())
            title = norm(r["title"])
            self.assertTrue(
                any(norm(t).startswith(title[:40]) for t in prompts if t),
                "%s: title %r is not the head of any user prompt in the "
                "transcript -- it was manufactured" % (r["id"], r["title"]))

    def test_53_the_shipped_panel_contains_no_session_fabricator(self):
        """A provable negative for the deleted seedSessions(): the string may
        appear in the tombstone comment explaining WHY it is gone, but never as
        a definition or a call."""
        import re
        html = io.open(os.path.join(HERE, "static", "panel.html"),
                       encoding="utf-8").read()
        # strip /* ... */ comments -- the tombstone lives in one
        code = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", "", code)
        for banned in (r"function\s+seedSessions", r"seedSessions\s*\(",
                       r"seeded\s*:\s*true"):
            self.assertIsNone(re.search(banned, code),
                              "panel.html still contains %r outside a comment -- "
                              "the session fabricator is back" % banned)

    def test_32_workdir_exists_after_importing_app(self):
        """Both socket handlers spawn a subprocess with cwd=WORKDIR. If that
        directory does not exist, create_subprocess_exec raises FileNotFoundError
        BEFORE a single frame is written: the socket dies, and the operator sees
        a UI that does nothing -- no error text, no output. WORKDIR defaults to
        ~/sutra-ui-workspace, which nothing else on the system creates, so a
        fresh machine was the guaranteed-broken case. Importing the app must
        leave the directory usable."""
        probe = tempfile.mkdtemp(prefix="sutra-test-workdir-")
        try:
            target = os.path.join(probe, "does", "not", "exist", "yet")
            self.assertFalse(os.path.isdir(target))
            env = dict(os.environ)
            env["SUTRA_UI_WORKDIR"] = target
            env["SUTRA_NATIVE_HOME"] = self.tmpdir
            out = subprocess.check_output(
                [VENV_PY, "-c",
                 "import os, app; print(app.WORKDIR); print(os.path.isdir(app.WORKDIR))"],
                cwd=HERE, env=env, stderr=subprocess.DEVNULL,
            ).decode("utf-8").strip().splitlines()
            self.assertEqual(out[-2], target, "WORKDIR must honour SUTRA_UI_WORKDIR")
            self.assertEqual(out[-1], "True",
                              "importing app must leave WORKDIR on disk -- otherwise the "
                              "first /ws/chat message dies with FileNotFoundError")
            self.assertTrue(os.path.isdir(target),
                             "the directory must really be there, not merely reported")
        finally:
            shutil.rmtree(probe, ignore_errors=True)

        # the guard itself must survive a workdir it cannot create (a file in
        # the way) by returning None rather than raising into the handshake
        import app as app_mod
        blocker = tempfile.mkdtemp(prefix="sutra-test-blocker-")
        try:
            f = os.path.join(blocker, "not-a-dir")
            with open(f, "w") as fh:
                fh.write("x")
            self.assertIsNone(app_mod._ensure_workdir(f))
        finally:
            shutil.rmtree(blocker, ignore_errors=True)


class TestChatRefusesApiKey(unittest.TestCase):
    """/ws/chat with ANTHROPIC_API_KEY set in the SERVER environment.

    A key in the server env makes the spawned `claude` bill the Anthropic API
    instead of the operator's Max subscription. ws_term already refused; ws_chat
    must refuse identically, and it must refuse BEFORE spawning anything -- so
    this test never runs a real `claude`, never bills anything, and asserts on
    the refusal frame itself. CLAUDE_BIN is additionally pointed at a path that
    cannot exist, so a regression that spawns anyway fails loudly rather than
    quietly costing money.
    """

    proc = None
    port = None
    tmpdir = None

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="sutra-test-wschat-")
        sys.path.insert(0, os.path.join(HERE, "..", "lib"))
        sys.path.insert(0, HERE)
        import fixture_seed  # noqa: E402
        fixture_seed.seed(cls.tmpdir)

        cls.port = _free_port()
        env = dict(os.environ)
        env["SUTRA_NATIVE_HOME"] = cls.tmpdir
        env["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"
        # belt and braces: if the refusal ever regresses, the spawn fails
        # instead of running a real, billable claude turn.
        env["SUTRA_UI_CLAUDE_BIN"] = os.path.join(cls.tmpdir, "no-such-claude-binary")
        env["SUTRA_UI_WORKDIR"] = os.path.join(cls.tmpdir, "workspace")
        cls.proc = subprocess.Popen(
            [VENV_PY, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=HERE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/org/stats" % cls.port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        else:
            raise RuntimeError("ws-chat server did not come up")

    @classmethod
    def tearDownClass(cls):
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.tmpdir and os.path.isdir(cls.tmpdir):
            shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_33_ws_chat_refuses_when_an_api_key_is_in_the_server_env(self):
        from websockets.sync.client import connect

        url = "ws://127.0.0.1:%d/ws/chat" % self.port
        with connect(url, open_timeout=10) as ws:
            frame = json.loads(ws.recv(timeout=10))
            self.assertEqual(frame["type"], "error",
                              "an API key in the server env must produce a refusal frame")
            detail = frame["detail"]
            self.assertIn("ANTHROPIC_API_KEY", detail)
            self.assertIn("Refused", detail)
            # the refusal must be terminal: the socket closes, and no run frames
            # (start/token/done) are ever emitted -- i.e. nothing was billed.
            with self.assertRaises(Exception):
                while True:
                    nxt = json.loads(ws.recv(timeout=5))
                    self.fail("expected the socket to close after refusing, got %r" % nxt)

        # a second connection behaves identically -- the refusal is not a
        # one-shot flag that a reconnect walks around
        with connect(url, open_timeout=10) as ws2:
            again = json.loads(ws2.recv(timeout=10))
            self.assertEqual(again["type"], "error")
            self.assertIn("ANTHROPIC_API_KEY", again["detail"])

        # the server is still healthy: refusing a socket must not kill the app
        req = urllib.request.Request("http://127.0.0.1:%d/api/org/stats" % self.port)
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)

    def test_34_ws_term_refuses_on_the_same_condition(self):
        """The two sockets must agree: a key that is unsafe for /ws/chat is
        unsafe for /ws/term. ws_term answers in raw terminal text, not JSON."""
        from websockets.sync.client import connect

        with connect("ws://127.0.0.1:%d/ws/term" % self.port, open_timeout=10) as ws:
            msg = ws.recv(timeout=10)
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", "replace")
            self.assertIn("Refused", msg)
            self.assertIn("ANTHROPIC_API_KEY", msg)


class TestEffectiveModeAndOnboarding(unittest.TestCase):
    """The stored permission mode is not always the one that runs, and the panel
    used to report only the stored one -- so it rendered "nothing will prompt you
    per edit" while ws_chat was in fact spawning `plan`. These tests pin the two
    values apart, and pin the first-run flag that gates the onboarding.

    providers.py is exercised directly (not over HTTP) so SUTRA_UI_SETTINGS can
    point at a tempdir: the operator's real ~/.sutra-ui/settings.json must never
    be read or written by the suite.
    """

    def setUp(self):
        import importlib
        self.tmp = tempfile.mkdtemp(prefix="sutra-ui-settings-")
        self.path = os.path.join(self.tmp, "settings.json")
        self._old = dict(os.environ)
        os.environ["SUTRA_UI_SETTINGS"] = self.path
        os.environ.pop("SUTRA_UI_ALLOW_UNSAFE_PERM_MODES", None)
        os.environ.pop("SUTRA_UI_PERMISSION_MODE", None)
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import providers
        self.providers = importlib.reload(providers)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, obj):
        with io.open(self.path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_unsafe_stored_mode_is_reported_as_clamped(self):
        """A bypassPermissions on file without the opt-in must be reported as
        NOT running -- this is the exact state that made the panel lie."""
        self._write({"permission_mode": "bypassPermissions"})
        s = self.providers.load_settings()
        self.assertEqual(s["permission_mode"], "bypassPermissions")
        self.assertEqual(s["permission_mode_effective"], "plan")
        self.assertTrue(s["permission_mode_clamped"])
        self.assertIn("SUTRA_UI_ALLOW_UNSAFE_PERM_MODES",
                      s["permission_mode_clamp_reason"])

    def test_safe_mode_is_never_marked_clamped(self):
        self._write({"permission_mode": "plan"})
        s = self.providers.load_settings()
        self.assertEqual(s["permission_mode_effective"], "plan")
        self.assertFalse(s["permission_mode_clamped"])
        self.assertIsNone(s["permission_mode_clamp_reason"])

    def test_opt_in_honours_the_stored_unsafe_mode(self):
        """With the out-of-band env set, stored and effective must agree --
        otherwise the escape hatch documented in the UI does not exist."""
        import importlib
        self._write({"permission_mode": "bypassPermissions"})
        os.environ["SUTRA_UI_ALLOW_UNSAFE_PERM_MODES"] = "1"
        prov = importlib.reload(self.providers)
        s = prov.load_settings()
        self.assertEqual(s["permission_mode_effective"], "bypassPermissions")
        self.assertFalse(s["permission_mode_clamped"])
        self.assertTrue(s["unsafe_modes_allowed"])

    def test_onboarded_defaults_false_and_round_trips(self):
        """First run is decided by the settings FILE, not a browser flag, so the
        disclosure cannot be skipped by clearing localStorage."""
        self.assertFalse(self.providers.load_settings()["onboarded"])
        self.providers.save_settings(onboarded=True)
        self.assertTrue(self.providers.load_settings()["onboarded"])

    def test_onboarded_rejects_non_boolean(self):
        with self.assertRaises(ValueError):
            self.providers.save_settings(onboarded="yes")

    def test_onboarding_write_preserves_other_settings(self):
        """Dismissing onboarding must not reset the operator's provider/workdir."""
        self._write({"permission_mode": "plan", "provider": "claude"})
        self.providers.save_settings(onboarded=True)
        with io.open(self.path, encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertEqual(raw["provider"], "claude")
        self.assertEqual(raw["permission_mode"], "plan")
        self.assertTrue(raw["onboarded"])


class TestSkillsSignature(unittest.TestCase):
    """The catalog was read once at boot, so a plugin update or a new command was
    invisible until restart. Auto-refresh rests entirely on the signature being a
    pure function of on-disk state -- a signature that drifts refreshes forever, and
    one that misses a change never refreshes at all."""

    def setUp(self):
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import org_api
        self.org = org_api

    def _sig(self, payload):
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:32]

    def test_identical_payloads_hash_identically(self):
        p = {"items": [{"slash": "/a", "runnable": True}], "total": 1}
        self.assertEqual(self._sig(p), self._sig(dict(p)))

    def test_a_runnable_flip_changes_the_signature(self):
        """count and slash names stay identical when a provider leaves PATH -- this
        is the case a count+mtime fingerprint cannot see."""
        a = {"items": [{"slash": "/a", "runnable": True}], "total": 1}
        b = {"items": [{"slash": "/a", "runnable": False}], "total": 1}
        self.assertNotEqual(self._sig(a), self._sig(b))

    def test_a_description_edit_changes_the_signature(self):
        a = {"items": [{"slash": "/a", "description": "old"}]}
        b = {"items": [{"slash": "/a", "description": "new"}]}
        self.assertNotEqual(self._sig(a), self._sig(b))

    def test_entries_with_slash_none_do_not_raise(self):
        """7 of 44 entries on a real machine have slash=None; sorting those names
        raises TypeError, which is why the whole payload is hashed instead."""
        p = {"items": [{"slash": None, "name": "AGENTS.md"}, {"slash": "/a"}]}
        self.assertEqual(len(self._sig(p)), 32)

    def test_read_at_must_not_be_inside_the_digest(self):
        """A clock in the digest makes every call a 'change' and the panel would
        refresh on a loop forever."""
        base = {"items": [], "total": 0}
        one, two = dict(base), dict(base)
        sig = self._sig(one)                      # hash BEFORE read_at is attached
        one["read_at"], two["read_at"] = 1, 2
        self.assertEqual(sig, self._sig(base),
                         "read_at leaked into the digest")

    def test_project_dir_is_the_workdir_not_the_environment(self):
        """CLAUDE_PROJECT_DIR is set by nothing in this repo, so the project-local
        .claude/commands tier was dead code."""
        src = io.open(os.path.join(HERE, "org_api.py"), encoding="utf-8").read()
        i = src.find("def api_skills")
        body = src[i:i + 2500]
        # Assert on the USE, not on the name: the identifier appears in the comment
        # explaining why it was dropped, and a raw substring check fails on prose.
        self.assertNotIn('environ.get("CLAUDE_PROJECT_DIR")', body,
                         "api_skills still READS CLAUDE_PROJECT_DIR, which nothing sets")
        self.assertIn("workdir_allowed", body,
                      "project_dir must be validated through workdir_allowed")


class TestEditorWriteGate(unittest.TestCase):
    """The editor is the FIRST filesystem write path in this app. Reading is
    ungated (it exposes nothing the chat agent's own cwd does not already);
    WRITING is a different risk class and is gated out of band, like unsafe
    permission modes. These pin the gate and the traversal guard."""

    def setUp(self):
        import importlib
        self._old = dict(os.environ)
        os.environ.pop("SUTRA_UI_ALLOW_EDIT", None)
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import providers, org_api
        self.p = importlib.reload(providers)
        self.org = org_api

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._old)

    def test_editing_is_off_by_default(self):
        """A panel that could rewrite files the moment it starts is not a default
        anyone opted into."""
        self.assertFalse(self.p.editing_allowed())

    def test_editing_turns_on_only_via_the_env_gate(self):
        import importlib
        os.environ[self.p.EDIT_ENV] = "1"
        self.assertTrue(importlib.reload(self.p).editing_allowed())

    def test_gate_is_exact_not_truthy(self):
        """'0', 'false', 'no' must NOT enable writing -- a truthy check here would
        turn a disabling value into an enabling one."""
        import importlib
        for v in ("0", "false", "no", "", "yes", "true"):
            os.environ[self.p.EDIT_ENV] = v
            got = importlib.reload(self.p).editing_allowed()
            self.assertEqual(got, v == "1", "%r produced editing_allowed()=%s" % (v, got))

    def test_write_endpoint_takes_base_bytes_for_conflict_detection(self):
        """Without it, the agent writing a file while the pane is open would be
        silently clobbered on save."""
        self.assertIn("base_bytes", self.org.FsWriteRequest.model_fields)

    def test_skip_dirs_cover_the_expensive_trees(self):
        for d in (".git", "node_modules", "__pycache__"):
            self.assertIn(d, self.org.FS_SKIP_DIRS)

    def test_read_and_tree_limits_are_finite(self):
        self.assertTrue(0 < self.org.FS_MAX_READ <= 16 * 1024 * 1024)
        self.assertTrue(0 < self.org.FS_MAX_ENTRIES <= 100000)


class TestModelAllowList(unittest.TestCase):
    """The model string reaches `claude --model` directly. An unknown value fails
    seconds later as a dead socket instead of as a refusal the operator can read,
    so it is validated against an allow-list on the way in AND on the way out."""

    def setUp(self):
        import importlib
        self._old = dict(os.environ)
        self.tmp = tempfile.mkdtemp(prefix="sutra-model-")
        os.environ["SUTRA_UI_SETTINGS"] = os.path.join(self.tmp, "s.json")
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import providers
        self.p = importlib.reload(providers)

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_catalogued_ids_survive(self):
        for good in ("opus", "sonnet", "haiku"):
            self.assertEqual(self.p.clean_model(good), good)
        for bad in ("gpt-4", "claude-3", "", None, 7, [], "opus; rm -rf /"):
            self.assertIsNone(self.p.clean_model(bad))

    def test_save_rejects_an_unknown_model(self):
        with self.assertRaises(ValueError):
            self.p.save_settings(model="gpt-4-turbo")

    def test_empty_string_is_legal_and_means_cli_default(self):
        """"" is a real choice, not a missing value -- it must persist, not raise."""
        self.p.save_settings(model="")
        self.assertEqual(self.p.load_settings()["model"], "")
        self.assertIsNone(self.p.stored_model())

    def test_model_round_trips(self):
        self.p.save_settings(model="haiku")
        self.assertEqual(self.p.load_settings()["model"], "haiku")
        self.assertEqual(self.p.stored_model(), "haiku")

    def test_catalog_ids_are_aliases_not_pinned_snapshots(self):
        """A pinned id goes stale and the panel then offers something that cannot
        run -- the exact failure providers.py exists to prevent."""
        for m in self.p.MODELS:
            self.assertNotRegex(m["id"], r"\d{8}",
                                "model %r looks like a dated snapshot id" % m["id"])


class TestAttachmentSafety(unittest.TestCase):
    """An attachment is written INSIDE the workdir (which is already the agent's
    cwd, so no new read surface opens). These pin the properties that keep a
    filename from becoming a path."""

    def setUp(self):
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import org_api
        self.org = org_api

    def test_a_filename_can_never_become_a_path(self):
        """basename() then a character filter: '../../.ssh/authorized_keys' must
        reduce to a plain name, never traverse."""
        import re as _re
        for evil in ("../../.ssh/authorized_keys", "/etc/passwd", "..\\..\\win.ini",
                     "....//x", "a/b/c.txt"):
            safe = os.path.basename(evil).strip().lstrip(".")
            safe = _re.sub(r"[^A-Za-z0-9._-]", "_", safe)[:120]
            self.assertNotIn("/", safe)
            self.assertNotIn("\\", safe)
            self.assertFalse(safe.startswith(".."), "%r -> %r still traverses" % (evil, safe))

    def test_size_cap_is_finite_and_sane(self):
        self.assertTrue(0 < self.org.ATTACH_MAX_BYTES <= 64 * 1024 * 1024)

    def test_attachments_land_under_a_dedicated_dir(self):
        """Writing straight into the workdir root would scatter uploads through the
        operator's project."""
        self.assertTrue(self.org.ATTACH_DIR)
        self.assertNotIn("/", self.org.ATTACH_DIR.strip("/"))


class TestToolSummary(unittest.TestCase):
    """A tool row that says only "Bash" eight times tells the operator nothing.
    _tool_summary picks the identifying field; it must never raise, because an
    unexpected input shape must not take a whole turn down."""

    def setUp(self):
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import app
        self.f = app._tool_summary

    def test_prefers_the_identifying_field(self):
        self.assertEqual(self.f({"command": "ls -1", "description": "list"}), "ls -1")
        self.assertEqual(self.f({"file_path": "/tmp/x.py", "content": "..."}), "/tmp/x.py")
        self.assertEqual(self.f({"pattern": "TODO"}), "TODO")

    def test_never_forwards_a_whole_file(self):
        """A Write's `content` is the entire file; it must not reach the browser."""
        out = self.f({"file_path": "/tmp/a", "content": "x" * 50000})
        self.assertEqual(out, "/tmp/a")
        self.assertNotIn("xxxx", out)

    def test_truncates_and_marks_it(self):
        out = self.f({"command": "y" * 500})
        self.assertLessEqual(len(out), 121)
        self.assertTrue(out.endswith("…"))

    def test_collapses_newlines_so_a_row_stays_one_line(self):
        self.assertEqual(self.f({"command": "a\n  b\tc"}), "a b c")

    def test_tolerates_junk_without_raising(self):
        for junk in (None, [], "str", 3, {}, {"k": None}, {"k": {"nested": 1}}):
            self.assertIsInstance(self.f(junk), str)


class TestGitReadOnly(unittest.TestCase):
    """The git surface is read-only BY CONSTRUCTION. These pin the two properties
    that keep it so: the verb allow-list, and the fact that the repository path
    can never come from the caller."""

    def setUp(self):
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import org_api
        self.org = org_api

    def test_no_mutating_verb_is_reachable(self):
        """Adding a mutating verb to GIT_CMDS is the single change that would turn
        this endpoint into a write path. Fail loudly if one appears."""
        banned = {"commit", "push", "add", "rm", "reset", "checkout", "merge",
                  "rebase", "clean", "restore", "stash", "apply", "cherry-pick",
                  "revert", "tag", "branch", "fetch", "pull", "gc", "worktree",
                  "update-ref", "filter-branch", "config", "init", "clone"}
        for view, argv in self.org.GIT_CMDS.items():
            self.assertTrue(argv, "%s has an empty argv" % view)
            self.assertNotIn(argv[0], banned,
                             "git view %r runs mutating verb %r" % (view, argv[0]))

    def test_every_view_is_a_known_read_verb(self):
        for view, argv in self.org.GIT_CMDS.items():
            self.assertIn(argv[0], {"status", "log", "diff", "show"},
                          "unexpected verb %r for view %r" % (argv[0], view))

    def test_repo_is_never_a_caller_supplied_parameter(self):
        """api_git must not accept a repo/cwd override -- one would bypass
        workdir_allowed and make this a read oracle over the filesystem."""
        import inspect
        params = set(inspect.signature(self.org.api_git).parameters)
        self.assertEqual(params, {"what", "path"},
                         "api_git gained a parameter; a repo/cwd override would "
                         "bypass the workdir_allowed check")


class TestLoginPathRepair(unittest.TestCase):
    """A Finder-launched .app inherits launchd's PATH, so /opt/homebrew/bin is
    absent and EVERY provider reported "binary not on PATH" on a machine where
    the binary runs fine in any terminal. Chat was dead and the stated reason
    pointed at the wrong thing.

    These pin both halves: it repairs a GUI-style PATH, and it stays out of the
    way when PATH is already fine (a login-shell spawn on every CLI start would
    be pure latency plus running the operator's rc files for nothing).
    """

    def setUp(self):
        import importlib
        self._old = dict(os.environ)
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import providers
        self.providers = importlib.reload(providers)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old)

    def test_no_op_when_path_already_resolves_a_provider(self):
        """Must not spawn a login shell when it has nothing to fix."""
        import importlib
        real = shutil.which("claude") or shutil.which("codex")
        if not real:
            self.skipTest("no catalogued CLI on PATH here; nothing to no-op against")
        prov = importlib.reload(self.providers)
        called = {"n": 0}
        prov._login_shell_path = lambda: (called.__setitem__("n", called["n"] + 1), None)[1]
        self.assertFalse(prov.ensure_login_path())
        self.assertEqual(called["n"], 0, "spawned a login shell despite PATH being usable")

    def test_repairs_a_launchd_style_path(self):
        import importlib
        real = shutil.which("claude") or shutil.which("codex")
        if not real:
            self.skipTest("no catalogued CLI on PATH here to rediscover")
        os.environ["PATH"] = "/usr/bin:/bin"
        prov = importlib.reload(self.providers)
        self.assertIsNone(shutil.which("claude"), "precondition: claude must be hidden")
        prov._login_shell_path = lambda: os.path.dirname(real) + os.pathsep + "/usr/bin"
        self.assertTrue(prov.ensure_login_path())
        self.assertIn(os.path.dirname(real), os.environ["PATH"])

    def test_runs_at_most_once(self):
        import importlib
        os.environ["PATH"] = "/usr/bin:/bin"
        prov = importlib.reload(self.providers)
        prov._login_shell_path = lambda: "/some/injected/dir"
        self.assertTrue(prov.ensure_login_path())
        self.assertFalse(prov.ensure_login_path(), "repaired PATH twice")

    def test_ignores_rc_banner_noise_and_non_path_output(self):
        """An rc file that prints a banner must not poison PATH.

        _known_bin_dirs is stubbed out so this tests ONE mechanism. Without the
        stub the known-location probe (added for the undetected-`claude` field
        incident) legitimately finds a real install on the developer's own
        machine and returns True -- which is the probe working, not the banner
        parser failing. See TestShellPathHarvest for the probe's own tests.
        """
        import importlib
        os.environ["PATH"] = "/usr/bin:/bin"
        prov = importlib.reload(self.providers)
        prov._login_shell_path = lambda: None      # what the parser returns for junk
        prov._known_bin_dirs = lambda binaries: []
        self.assertFalse(prov.ensure_login_path())
        self.assertEqual(os.environ["PATH"], "/usr/bin:/bin")

    def test_appends_so_an_explicit_path_still_wins(self):
        """A PATH set deliberately for this process must keep precedence."""
        import importlib
        os.environ["PATH"] = "/usr/bin:/bin"
        prov = importlib.reload(self.providers)
        prov._login_shell_path = lambda: "/late/dir"
        prov.ensure_login_path()
        self.assertTrue(os.environ["PATH"].startswith("/usr/bin:/bin"),
                        "login PATH was prepended; it must be appended")


class TestAutomationReader(unittest.TestCase):
    """GET /api/automation reports the dispatcher from real ledgers, and reports
    the scheduler as ABSENT rather than as an empty table.

    The distinction is the whole point of the screen. Cadence lives in the Native
    daemon (ADR-017: a daemon-side tick, deliberately not OS cron/launchd); that
    daemon does not run in this install and the v1.0 scheduler does not evaluate
    cron expressions at all. A "0 runs today" table would assert that a scheduler
    ran and had nothing to do. Nothing ran.
    """

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        os.environ.setdefault("SUTRA_NATIVE_HOME",
                              os.path.expanduser("~/.sutra-native/user-kit"))
        import org_api
        self.O = org_api
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absent_file_and_empty_file_are_different_facts(self):
        """"no such ledger" must not be reported the same way as "ledger with no
        rows" -- only the second means nothing has been dispatched."""
        missing = os.path.join(self.tmp, "nope.jsonl")
        total, rows, big = self.O._read_jsonl_tail(missing)
        self.assertEqual((total, rows, big), (0, [], False))

        empty = os.path.join(self.tmp, "empty.jsonl")
        open(empty, "w").close()
        total, rows, _ = self.O._read_jsonl_tail(empty)
        self.assertEqual((total, rows), (0, []))

    def test_a_corrupt_row_does_not_empty_the_ledger(self):
        """One unparseable line is not a reason to report zero activity: it is
        counted in the total and skipped in the tail."""
        p = os.path.join(self.tmp, "led.jsonl")
        with open(p, "w") as fh:
            fh.write('{"kind":"decision","unit":"a"}\n')
            fh.write("{not json at all\n")
            fh.write('{"kind":"bind","unit":"b"}\n')
        total, rows, _ = self.O._read_jsonl_tail(p)
        self.assertEqual(total, 3, "every non-blank line counts toward the total")
        self.assertEqual([r["kind"] for r in rows], ["decision", "bind"],
                         "only the parseable rows are returned")

    def test_the_tail_is_the_newest_rows(self):
        p = os.path.join(self.tmp, "led.jsonl")
        with open(p, "w") as fh:
            for i in range(50):
                fh.write(json.dumps({"n": i}) + "\n")
        total, rows, _ = self.O._read_jsonl_tail(p, limit=5)
        self.assertEqual(total, 50)
        self.assertEqual([r["n"] for r in rows], [45, 46, 47, 48, 49])

    def test_a_runaway_ledger_is_refused_not_half_read(self):
        """A partial tail presented as the whole is worse than saying nothing."""
        p = os.path.join(self.tmp, "big.jsonl")
        with open(p, "w") as fh:
            fh.write("x" * (self.O.AUTOMATION_MAX_BYTES + 1))
        total, rows, big = self.O._read_jsonl_tail(p)
        self.assertTrue(big, "must flag the file as too large")
        self.assertEqual((total, rows), (0, []), "and must not report partial counts")

    def test_the_endpoint_states_that_there_is_no_scheduler(self):
        """Called directly: this asserts the endpoint's SHAPE, which does not
        depend on a live server, and lets the workdir be a scratch dir rather
        than whatever this machine happens to have configured."""
        import providers
        real_load, real_allow = providers.load_settings, providers.workdir_allowed
        # The allowed-root guard is exercised by its own tests; here it would only
        # stop a scratch dir from standing in for a real workdir.
        providers.load_settings = lambda: {"workdir": self.tmp}
        providers.workdir_allowed = lambda wd: True
        try:
            body = self.O.api_automation()
        finally:
            providers.load_settings, providers.workdir_allowed = real_load, real_allow

        self.assertEqual(body["root"], self.tmp)
        sch = body["scheduler"]
        self.assertIn("note", sch)
        self.assertTrue(sch["note"].strip(), "the absence must be stated, not implied")
        for key in ("daemon_running", "ready", "triggers_dir_exists", "triggers"):
            self.assertIn(key, sch, "scheduler liveness field missing: " + key)
        self.assertIn("dispatcher", body)
        for src in ("ledger", "atoms", "gate"):
            self.assertIn("path", body["dispatcher"][src],
                          "every source must name the file it read")


class TestUpdates(unittest.TestCase):
    """Version comparison and component state. No network in these tests: the
    remote lookups are stubbed, because a test that depends on GitHub fails for
    reasons that have nothing to do with this code."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import updates
        from pathlib import Path as _P
        self.U = updates
        self.Path = _P
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_version_comparison(self):
        n = self.U._newer
        self.assertTrue(n("2.68.0", "2.67.1"))
        self.assertTrue(n("2.67.1", "2.67.0"))
        self.assertTrue(n("2.7.0", "2.67.0") is False, "component-wise, not string")
        self.assertFalse(n("2.67.0", "2.67.0"))
        self.assertFalse(n("2.66.0", "2.67.0"))

    def test_an_unreadable_version_never_looks_newer(self):
        """A parse failure must not present itself as an available update --
        that would prompt an operator to install over something fine."""
        self.assertFalse(self.U._newer("", "2.67.0"))
        self.assertFalse(self.U._newer(None, "2.67.0"))
        self.assertFalse(self.U._newer("garbage", "2.67.0"))
        self.assertFalse(self.U._newer("2.68.0", None))

    def test_source_checkout_reports_unmanaged_not_broken(self):
        """Running from a checkout there is no .app to replace. That is an
        answer, not an error, and must not render as a failed check."""
        real = self.U.app_bundle
        self.U.app_bundle = lambda: None
        try:
            d = self.U.desktop_state()
            self.assertFalse(d["managed"])
            self.assertIsNone(d["installed"])
            self.assertIn("checkout", d["reason"])
            self.assertNotIn("error", d)
        finally:
            self.U.app_bundle = real

    def test_desktop_state_reports_an_available_update(self):
        app = self.Path(self.tmp) / "Sutra.app"
        (app / "Contents").mkdir(parents=True)
        import plistlib
        with open(app / "Contents" / "Info.plist", "wb") as fh:
            plistlib.dump({"CFBundleShortVersionString": "2.67.0"}, fh)
        real_app, real_latest = self.U.app_bundle, self.U._latest_desktop
        self.U.app_bundle = lambda: app
        self.U._latest_desktop = lambda: {
            "version": "2.67.1", "tag": "v2.67.1-desktop", "url": "https://x",
            "asset": "Sutra-arm64.dmg", "download_url": "https://x/d.dmg",
            "size": 1, "sha256_url": "https://x/d.sha256", "error": None}
        try:
            d = self.U.desktop_state()
            self.assertTrue(d["managed"])
            self.assertEqual(d["installed"], "2.67.0")
            self.assertEqual(d["latest"], "2.67.1")
            self.assertTrue(d["update_available"])
            # This note used to promise there was NO background updater. There
            # is one now, and a note that describes the old behaviour is worse
            # than no note -- it is the app misreporting itself.
            self.assertIn("background", d["note"])
            self.assertNotIn("no background updater", d["note"])
        finally:
            self.U.app_bundle, self.U._latest_desktop = real_app, real_latest

    def test_a_release_without_this_arch_is_not_an_update(self):
        """An asset for the other Mac is not something this one can install."""
        app = self.Path(self.tmp) / "S.app"
        (app / "Contents").mkdir(parents=True)
        import plistlib
        with open(app / "Contents" / "Info.plist", "wb") as fh:
            plistlib.dump({"CFBundleShortVersionString": "2.67.0"}, fh)
        real_app, real_latest = self.U.app_bundle, self.U._latest_desktop
        self.U.app_bundle = lambda: app
        self.U._latest_desktop = lambda: {
            "version": "2.99.0", "asset": "Sutra-arm64.dmg", "download_url": None,
            "error": "release v2.99.0-desktop has no Sutra-arm64.dmg asset"}
        try:
            d = self.U.desktop_state()
            self.assertIsNotNone(d["error"])
        finally:
            self.U.app_bundle, self.U._latest_desktop = real_app, real_latest

    def test_installed_plugin_version_is_the_highest_cache_dir(self):
        """Directories, not the manifest: an update lands as a NEW cache dir, so
        the manifest under the old root still reads the old number."""
        root = self.Path(self.tmp) / "core"
        for v in ("2.9.0", "2.66.0", "2.67.0", "not-a-version"):
            (root / v).mkdir(parents=True)
        old = os.environ.get("SUTRA_CACHE_ROOT")
        os.environ["SUTRA_CACHE_ROOT"] = str(root)
        try:
            self.assertEqual(self.U._installed_plugin_version(), "2.67.0")
        finally:
            if old is None:
                del os.environ["SUTRA_CACHE_ROOT"]
            else:
                os.environ["SUTRA_CACHE_ROOT"] = old

    def test_install_desktop_refuses_an_unwritable_target(self):
        """Rather than half-replacing a bundle it cannot finish replacing."""
        app = self.Path("/System/Library/CoreServices/Finder.app")
        if not app.is_dir():
            self.skipTest("no unwritable .app to test against")
        with self.assertRaises(RuntimeError) as cm:
            self.U.install_desktop(__file__, app_path=str(app))
        self.assertIn("writable", str(cm.exception))

    def test_install_desktop_refuses_a_missing_image(self):
        app = self.Path(self.tmp) / "W.app"
        (app / "Contents").mkdir(parents=True)
        with self.assertRaises(RuntimeError) as cm:
            self.U.install_desktop(str(self.Path(self.tmp) / "nope.dmg"), app_path=str(app))
        self.assertIn("no such disk image", str(cm.exception))


class TestAutoUpdateStaging(unittest.TestCase):
    """The staging state machine -- the part that makes an update button an
    auto-updater.

    Every test here is about a moment when NOBODY IS WATCHING: a helper that
    ran and died, a manifest that outlived the process that wrote it, a launch
    that has to work out what the previous launch did. The download path is not
    re-tested (TestUpdates covers it); what is tested is what happens to a
    staged build afterwards, because that is where an auto-updater turns into
    either a silent success or an app that will not start."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import updates
        from pathlib import Path as _P
        self.U = updates
        self.Path = _P
        self.tmp = tempfile.mkdtemp()
        self._prev = os.environ.get("SUTRA_UPDATE_DIR")
        os.environ["SUTRA_UPDATE_DIR"] = os.path.join(self.tmp, "updates")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SUTRA_UPDATE_DIR", None)
        else:
            os.environ["SUTRA_UPDATE_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _stage(self, version="2.70.0", state="staged", **kw):
        """A staged manifest over a real file, so digest checks are meaningful."""
        d = self.U.stage_dir()
        dmg = d / ("Sutra-%s.dmg" % version)
        dmg.write_bytes(b"disk image")
        man = {"state": state, "version": version, "dmg": str(dmg),
               "sha256": self.U._sha256(dmg), "sha256_url": None,
               "staged_at": 1, "armed_at": None, "lease_until": None,
               "arm_attempts": 0, "spawn_failures": 0, "install_failures": 0,
               "last_error": None}
        man.update(kw)
        self.U._write_json(self.U._pending_path(), man)
        return man

    def _result(self, ok, version="2.70.0", error=""):
        self.U._write_json(self.U._result_path(),
                           {"ok": ok, "stage": "installed" if ok else "swap",
                            "version": version, "error": error, "ts": 1})

    # -- the staging directory is a durable, writable place, so it is checked --

    def test_staging_directory_is_private(self):
        d = self.U.stage_dir()
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700,
                         "a directory holding a DMG that will be installed "
                         "unattended must not be readable by other users")

    def test_a_symlinked_staging_directory_is_refused(self):
        """The durability that makes /tmp wrong makes this necessary: a path
        that persists is a path someone can point somewhere else first."""
        real = os.path.join(self.tmp, "elsewhere")
        os.makedirs(real)
        link = os.path.join(self.tmp, "linked")
        os.symlink(real, link)
        os.environ["SUTRA_UPDATE_DIR"] = link
        with self.assertRaises(RuntimeError) as cm:
            self.U.stage_dir()
        self.assertIn("symlink", str(cm.exception))

    def test_a_loosened_staging_directory_is_repaired(self):
        """Repaired rather than refused: it is ours, so tightening it is both
        possible and better than refusing to update. Refusal is reserved for
        the case where the repair does not take."""
        d = self.U.stage_dir()
        os.chmod(d, 0o777)
        self.U.stage_dir()
        self.assertEqual(os.stat(d).st_mode & 0o777, 0o700)

    def test_a_staging_directory_owned_by_someone_else_is_refused(self):
        with mock.patch.object(self.U.os, "getuid", return_value=999999):
            with self.assertRaises(RuntimeError) as cm:
                self.U.stage_dir()
        self.assertIn("not owned by this user", str(cm.exception))

    # -- what sat on disk for days is not trusted on the way back in ---------

    def test_a_changed_image_is_not_installed(self):
        man = self._stage()
        self.Path(man["dmg"]).write_bytes(b"something else entirely")
        with self.assertRaises(RuntimeError) as cm:
            self.U._verify_staged(man, recheck_online=False)
        self.assertIn("changed on disk", str(cm.exception))

    def test_an_image_outside_the_staging_directory_is_refused(self):
        outside = self.Path(self.tmp) / "evil.dmg"
        outside.write_bytes(b"disk image")
        man = self._stage()
        man["dmg"] = str(outside)
        man["sha256"] = self.U._sha256(outside)   # digest alone would pass
        with self.assertRaises(RuntimeError) as cm:
            self.U._verify_staged(man, recheck_online=False)
        self.assertIn("not inside the staging directory", str(cm.exception))

    def test_a_missing_image_is_refused(self):
        man = self._stage()
        os.unlink(man["dmg"])
        with self.assertRaises(RuntimeError):
            self.U._verify_staged(man, recheck_online=False)

    # -- launch-time reconciliation ------------------------------------------

    def test_the_helpers_own_word_beats_a_version_comparison(self):
        """THE ATTACH-PATH TRAP. The shell can attach to an older backend still
        serving 8330, so a version read back through the API can be the
        PREVIOUS install. If success were inferred from `installed >= pending`
        this launch would call a completed update a failure and do it again."""
        self._stage()
        self._result(True)
        r = self.U.resolve_pending(installed_version="2.69.1")   # says still old
        self.assertFalse(r["pending"])
        self.assertEqual(r["applied"], "2.70.0")
        self.assertIsNone(self.U.read_pending(), "a finished update is cleared")

    def test_a_first_failure_is_retried(self):
        self._stage()
        self._result(False, error="mount failed")
        r = self.U.resolve_pending(installed_version="2.69.1")
        self.assertEqual(r["action"], "arm")
        self.assertEqual(self.U.read_pending()["install_failures"], 1)

    def test_a_second_failure_gives_up_instead_of_bricking_the_app(self):
        """The boot fallback QUITS the app to apply an update. Retrying that
        forever against a broken release is an app that cannot be opened, so
        the counter is the difference between a failed update and a failed
        product."""
        self._stage(install_failures=1)
        self._result(False, error="new bundle failed codesign")
        r = self.U.resolve_pending(installed_version="2.69.1")
        self.assertTrue(r["gave_up"])
        self.assertIn("codesign", r["error"])
        self.assertIsNone(self.U.read_pending(),
                          "giving up clears the pending state; the manual "
                          "button is the remaining path")

    def test_a_live_lease_is_waited_out_not_armed_again(self):
        """A second helper against the same bundle is how a launch loop starts:
        arm, quit, relaunch, still pending, arm again."""
        self._stage(state="installing", lease_until=int(time.time()) + 300)
        r = self.U.resolve_pending(installed_version="2.69.1")
        self.assertEqual(r["action"], "wait")
        self.assertEqual(self.U.read_pending()["install_failures"], 0,
                         "waiting is not a failure")

    def test_an_expired_lease_counts_as_an_attempt(self):
        """No result file and a dead lease means a helper was spawned and was
        never heard from. Silence is not success."""
        self._stage(state="installing", lease_until=int(time.time()) - 10)
        r = self.U.resolve_pending(installed_version="2.69.1")
        self.assertEqual(r["action"], "arm")
        self.assertEqual(self.U.read_pending()["install_failures"], 1)

    def test_an_already_updated_app_clears_the_manifest(self):
        self._stage()
        r = self.U.resolve_pending(installed_version="2.70.0")
        self.assertEqual(r["applied"], "2.70.0")
        self.assertIsNone(self.U.read_pending())

    def test_nothing_staged_is_not_an_error(self):
        self.assertEqual(self.U.resolve_pending("2.69.1"), {"pending": False})

    # -- arming ---------------------------------------------------------------

    def test_arming_twice_does_not_spawn_two_installers(self):
        """The countdown firing while the user is already quitting is not a
        hypothetical -- it is the most likely way this is reached."""
        self._stage(state="installing", lease_until=int(time.time()) + 300)
        r = self.U.arm_desktop(os.getpid(), relaunch=True)
        self.assertTrue(r["already"])

    def test_arming_refuses_a_release_that_has_already_failed_twice(self):
        self._stage(state="failed", install_failures=2,
                    last_error="new bundle failed codesign")
        with self.assertRaises(RuntimeError) as cm:
            self.U.arm_desktop(os.getpid())
        self.assertIn("will not be retried", str(cm.exception))

    def test_arming_with_nothing_staged_is_refused(self):
        with self.assertRaises(RuntimeError) as cm:
            self.U.arm_desktop(os.getpid())
        self.assertIn("no staged update", str(cm.exception))

    def test_a_spawn_failure_returns_the_update_to_staged(self):
        """A helper that never started has not failed to INSTALL anything. If
        that were counted as an install failure, two hiccups here would
        permanently suppress a perfectly good release."""
        self._stage()
        # No .app anywhere: this is a source checkout, exactly as CI sees it.
        with self.assertRaises(RuntimeError):
            self.U.arm_desktop(os.getpid(), relaunch=True)
        man = self.U.read_pending()
        self.assertEqual(man["state"], "staged", "still installable")
        self.assertEqual(man["spawn_failures"], 1)
        self.assertEqual(man["install_failures"], 0)

    # -- the installer's own contract ----------------------------------------

    def test_the_installer_is_told_which_process_to_wait_for(self):
        """getppid() is WRONG for the desktop shell: main.js has a path where it
        attaches to a backend it did not spawn, and that parent's exit would
        release the helper while Sutra is still running."""
        env = self._spawn_env(wait_pid=4242, relaunch=True, version="2.70.0")
        self.assertEqual(env["WAIT_PID"], "4242")
        self.assertEqual(env["RELAUNCH"], "1")
        self.assertEqual(env["EXPECT_VERSION"], "2.70.0")

    def test_a_quit_driven_install_does_not_reopen_the_app(self):
        """Relaunching after a deliberate Quit countermands the user."""
        env = self._spawn_env(wait_pid=4242, relaunch=False)
        self.assertEqual(env["RELAUNCH"], "0")

    def test_the_installer_checks_the_bundle_identity_not_just_the_signature(self):
        """'Validly signed' is not 'signed by us'. Without this a compromised
        release could hand over a properly notarized app belonging to someone
        else and every earlier gate would pass it."""
        s = self.U._INSTALLER
        self.assertIn("TeamIdentifier=", s)
        self.assertIn("EXPECT_BUNDLE_ID", s)
        self.assertIn("EXPECT_VERSION", s)
        self.assertIn("pgrep -f", s, "the main process exiting is not the "
                                     "bundle being free of Electron helpers")

    def test_the_installer_normalises_start_times_exactly_as_python_does(self):
        """These strings are compared for equality across a language boundary.
        If they normalised differently every update would abort as a phantom
        pid reuse -- and it would abort SILENTLY, in a detached helper."""
        pid = os.getpid()
        py = self.U._proc_start(pid)
        sh = subprocess.run(
            ["bash", "-c", 'ps -o lstart= -p "$1" 2>/dev/null | awk \'{$1=$1;print}\'',
             "_", str(pid)], capture_output=True, text=True).stdout.strip()
        self.assertTrue(py, "ps must report a start time for our own process")
        self.assertEqual(py, sh)

    def _spawn_env(self, **kw):
        """install_desktop() without actually spawning anything."""
        app = self.Path(self.tmp) / "Sutra.app"
        (app / "Contents").mkdir(parents=True)
        with open(app / "Contents" / "Info.plist", "wb") as fh:
            import plistlib
            plistlib.dump({"CFBundleIdentifier": "os.sutra.ui",
                           "CFBundleShortVersionString": "2.69.1"}, fh)
        dmg = self.Path(self.tmp) / "x.dmg"
        dmg.write_bytes(b"d")
        seen = {}

        class FakePopen(object):
            def __init__(self, argv, env=None, **kwargs):
                seen.update(env or {})

        # Only Popen is faked. subprocess.run() still has to work, because
        # install_desktop() shells out to codesign to read the bundle identity
        # it is about to require of the replacement.
        shim = types.SimpleNamespace(
            Popen=FakePopen, run=subprocess.run, DEVNULL=subprocess.DEVNULL,
            SubprocessError=subprocess.SubprocessError)
        real = self.U.subprocess
        self.U.subprocess = shim
        try:
            self.U.install_desktop(str(dmg), app_path=str(app), **kw)
        finally:
            self.U.subprocess = real
        return seen


class TestDesktopControlAuth(unittest.TestCase):
    """The three routes that can quit the app and replace the bundle on disk.

    Everything else on this API is unauthenticated because it is loopback-only
    and does nothing a local user could not already do. These do: arming hands
    an unattended helper the authority to replace /Applications/Sutra.app, and
    ANY page in ANY browser on this machine can POST to localhost. That is a
    persistence primitive, not a convenience."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import org_api
        self.api = org_api
        self._prev = org_api.DESKTOP_TOKEN

    def tearDown(self):
        self.api.DESKTOP_TOKEN = self._prev

    class _Req(object):
        def __init__(self, token=None):
            self.headers = {"x-sutra-desktop-token": token} if token else {}

    def _refusal(self, req):
        from fastapi import HTTPException
        try:
            self.api._desktop_control(req)
        except HTTPException as exc:
            return exc
        self.fail("desktop control was allowed when it should have been refused")

    def test_a_backend_we_did_not_start_cannot_be_used_to_install(self):
        """main.js attaches to a CLI-owned server when it finds one. It has no
        token for that process, so automatic updating is simply off for that
        session -- which is right anyway: quitting this window would not stop a
        backend somebody else owns."""
        self.api.DESKTOP_TOKEN = None
        exc = self._refusal(self._Req("anything"))
        self.assertEqual(exc.status_code, 403)
        self.assertIn("not started by the Sutra desktop app", exc.detail)

    def test_a_page_without_the_token_cannot_arm_an_install(self):
        self.api.DESKTOP_TOKEN = "s3cret"
        self.assertEqual(self._refusal(self._Req()).status_code, 403)
        self.assertEqual(self._refusal(self._Req("guess")).status_code, 403)

    def test_the_shell_can(self):
        self.api.DESKTOP_TOKEN = "s3cret"
        self.api._desktop_control(self._Req("s3cret"))   # must not raise

    def test_reading_staged_state_needs_no_token(self):
        """The panel polls it once a minute and it is local-only. A route that
        reached the network could not be polled without turning every open
        panel into a crawler."""
        self.assertIn("pending", self.api.api_updates_staged())


class TestShellPathHarvest(unittest.TestCase):
    """FIELD INCIDENT: `claude` undetected on other people's Macs.

    `zsh -l -c` is a LOGIN, NON-INTERACTIVE shell, and zsh reads ~/.zshrc only
    for INTERACTIVE shells. .zshrc is where nvm, npm-global and Claude Code's
    own native installer export PATH -- so the harvest could not see the
    directory holding the binary, and the app reported it missing on machines
    where it ran fine in every terminal.

    The dev machine could not reveal this: Homebrew writes its shellenv to
    .zprofile, which a login shell DOES read. These tests build the other kind
    of HOME on purpose.
    """

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.fake = os.path.join(self.bin, "claude")
        with open(self.fake, "w") as fh:
            fh.write("#!/bin/sh\necho claude\n")
        os.chmod(self.fake, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _zshrc_home(self):
        """A HOME whose PATH addition lives ONLY in .zshrc -- the common case."""
        with open(os.path.join(self.tmp, ".zshrc"), "w") as fh:
            fh.write('export PATH="%s:$PATH"\n' % self.bin)
        return self.tmp

    @unittest.skipUnless(os.path.isfile("/bin/zsh"), "zsh required")
    def test_a_path_exported_only_from_zshrc_is_harvested(self):
        """The regression itself. Before the fix this directory was invisible."""
        import importlib
        home = self._zshrc_home()
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin",
                               "SHELL": "/bin/zsh"})
            prov = importlib.reload(self.providers if hasattr(self, "providers")
                                    else __import__("providers"))
            got = prov._login_shell_path() or ""
            self.assertIn(self.bin, got.split(os.pathsep),
                          "a PATH exported from .zshrc must be harvested; "
                          "`zsh -l -c` alone cannot see it")
        finally:
            os.environ.clear()
            os.environ.update(old)

    @unittest.skipUnless(os.path.isfile("/bin/zsh"), "zsh required")
    def test_the_login_only_shell_really_does_miss_it(self):
        """Pins the CAUSE, so the -i above can never be 'simplified' away by
        someone who cannot see why it is there."""
        import importlib
        home = self._zshrc_home()
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin",
                               "SHELL": "/bin/zsh"})
            prov = importlib.reload(__import__("providers"))
            login_only = prov._shell_path_once("/bin/zsh", interactive=False) or ""
            interactive = prov._shell_path_once("/bin/zsh", interactive=True) or ""
            self.assertNotIn(self.bin, login_only.split(os.pathsep),
                             "if this ever passes, zsh changed and the comment "
                             "explaining -i is now wrong")
            self.assertIn(self.bin, interactive.split(os.pathsep))
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_known_locations_are_probed_when_no_shell_can_be_asked(self):
        """fish, a hanging rc chain, or a GUI-only account: no shell answer at
        all, and the binary must still be found where its installer puts it."""
        import importlib
        home = os.path.join(self.tmp, "home2")
        local = os.path.join(home, ".local", "bin")
        os.makedirs(local)
        target = os.path.join(local, "claude")
        shutil.copy(self.fake, target)
        os.chmod(target, 0o755)
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin",
                               "SHELL": "/nonexistent/shell"})
            prov = importlib.reload(__import__("providers"))
            self.assertIn(local, prov._known_bin_dirs(["claude"]),
                          "~/.local/bin is where the native installer puts it")
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_a_directory_without_the_binary_is_never_added(self):
        """The probe must not widen PATH on a hunch: an empty ~/.local/bin is
        not evidence of anything."""
        import importlib
        home = os.path.join(self.tmp, "home3")
        os.makedirs(os.path.join(home, ".local", "bin"))    # exists, but empty
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin"})
            prov = importlib.reload(__import__("providers"))
            self.assertNotIn(os.path.join(home, ".local", "bin"),
                             prov._known_bin_dirs(["claude"]))
        finally:
            os.environ.clear()
            os.environ.update(old)


class TestPtyWinsizeFloor(unittest.TestCase):
    """A resize the browser measured on a hidden container must not reach the PTY.

    xterm's fit addon reports 2x1 for a container with no area. Applied to the
    PTY, the TUI reflows into a garbled sliver and STAYS there, because nothing
    re-sends a size afterwards. The client refuses to send such a measurement;
    this is the server refusing to apply one, so a single buggy client cannot
    wedge a session.
    """

    def test_the_ws_term_handler_floors_the_winsize(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"),
                   encoding="utf-8").read()
        i = src.find('elif kind == "r":')
        self.assertNotEqual(i, -1, "the resize branch must exist")
        j = src.find("TIOCSWINSZ", i)
        self.assertNotEqual(j, -1, "the resize branch must ioctl the winsize")
        between = src[i:j]
        self.assertIn("continue", between,
                      "a degenerate size must be dropped BEFORE the ioctl")
        self.assertRegex(between, r"rows\s*<\s*\d+\s+or\s+cols\s*<\s*\d+",
                         "the floor must test both dimensions")


if __name__ == "__main__":
    unittest.main()


class TestRoutines(unittest.TestCase):
    """Schedule translation, validation and the permission floor.

    No launchd in these: a test that bootstraps a real job would install a real
    scheduled agent on whoever runs the suite. The launchd path is exercised by
    hand against a live server; what is pinned here is everything that decides
    WHAT gets scheduled.
    """

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import routines
        self.R = routines
        # UNDER $HOME on purpose: validate_new() confines a routine's working
        # folder to the home directory, and /var/folders is outside it. A tmp dir
        # elsewhere would fail the rule the test is not trying to test.
        self.tmp = tempfile.mkdtemp(prefix=".sutra-test-", dir=os.path.expanduser("~"))
        self._env = dict(os.environ)
        os.environ["SUTRA_UI_ROUTINES"] = os.path.join(self.tmp, "routines")
        os.environ["SUTRA_UI_RUNS"] = os.path.join(self.tmp, "runs")
        os.environ["SUTRA_UI_LAUNCHAGENTS"] = os.path.join(self.tmp, "agents")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- the five presets Claude's own Schedule control offers --------------
    def test_the_five_presets_map_to_the_right_cron(self):
        R = self.R
        self.assertIsNone(R.preset_to_cron("manual"))
        self.assertEqual(R.preset_to_cron("hourly", minute=0), "0 * * * *")
        self.assertEqual(R.preset_to_cron("daily", hour=9, minute=0), "0 9 * * *")
        self.assertEqual(R.preset_to_cron("weekdays", hour=9, minute=0), "0 9 * * 1-5")
        self.assertEqual(R.preset_to_cron("weekly", hour=18, minute=30, weekday=5),
                         "30 18 * * 5")

    def test_cron_becomes_the_calendar_launchd_actually_wants(self):
        R = self.R
        self.assertEqual(R.cron_to_calendar("0 * * * *"), {"Minute": 0})
        self.assertEqual(R.cron_to_calendar("0 9 * * *"), {"Minute": 0, "Hour": 9})
        wd = R.cron_to_calendar("0 9 * * 1-5")
        self.assertEqual(len(wd), 5, "weekdays needs one dict per day: launchd has "
                                     "no range syntax of its own")
        self.assertEqual(sorted(d["Weekday"] for d in wd), [1, 2, 3, 4, 5])
        self.assertTrue(all(d["Hour"] == 9 and d["Minute"] == 0 for d in wd))

    def test_sunday_is_both_0_and_7_in_cron_but_only_0_in_launchd(self):
        self.assertEqual(self.R.cron_to_calendar("0 9 * * 7"),
                         {"Minute": 0, "Hour": 9, "Weekday": 0})

    def test_the_once_an_hour_floor_is_enforced_at_create_time(self):
        """Not discovered at 09:00 with nobody watching."""
        with self.assertRaises(ValueError) as cm:
            self.R.validate_cron("*/15 * * * *")
        self.assertIn("once per hour", str(cm.exception))
        self.R.validate_cron("0 9,17 * * *")          # twice a day is fine

    def test_unsupported_cron_syntax_is_refused_not_misread(self):
        """A schedule that means something other than what was typed is worse
        than one that is rejected."""
        for bad in ("0 9 L * *", "0 9 * * MON", "0 9 ? * *"):
            with self.assertRaises(ValueError):
                self.R.parse_cron(bad)

    # ---- the safety floor ---------------------------------------------------
    def test_a_routine_cannot_reach_a_write_capable_mode(self):
        """POSITIVE allow-list, so editing providers.UNSAFE_PERMISSION_MODES
        cannot silently re-admit one."""
        self.assertEqual(set(self.R.ROUTINE_PERMISSION_MODES), {"dontAsk", "plan"})
        import providers
        for m in providers.UNSAFE_PERMISSION_MODES:
            self.assertNotIn(m, self.R.ROUTINE_PERMISSION_MODES)
        body = self._body(permission_mode="bypassPermissions")
        with self.assertRaises(ValueError) as cm:
            self.R.validate_new(body, set())
        self.assertIn("unattended", str(cm.exception))

    def test_the_default_is_dontAsk_not_plan(self):
        """plan unattended proposes edits nobody approves, exits 0, and the run
        reads OK while the routine does nothing forever."""
        self.assertEqual(self.R.DEFAULT_ROUTINE_MODE, "dontAsk")
        rec = self.R.validate_new(self._body(), set())
        self.assertEqual(rec["permission_mode"], "dontAsk")

    def test_a_budget_ceiling_is_required(self):
        with self.assertRaises(ValueError) as cm:
            self.R.validate_new(self._body(opts={"max_budget_usd": 0}), set())
        self.assertIn("ceiling", str(cm.exception))

    def test_the_working_folder_must_exist_and_be_inside_home(self):
        with self.assertRaises(ValueError):
            self.R.validate_new(self._body(cwd="/nope/does/not/exist"), set())
        with self.assertRaises(ValueError) as cm:
            self.R.validate_new(self._body(cwd="/usr"), set())
        self.assertIn("home", str(cm.exception))

    def test_ids_are_sanitised_because_they_become_a_launchd_label(self):
        """The id is the launchd label suffix, the run-directory name and the
        record filename, so it is normalised and constrained rather than trusted."""
        for bad in ("Has Spaces", "../escape", "", "a" * 60):
            with self.assertRaises(ValueError):
                self.R.validate_new(self._body(id=bad), set())
        # LOWERCASED, not refused -- Claude's own docs say the name is
        # "lowercased to kebab-case", and matching that is the point.
        self.assertEqual(self.R.validate_new(self._body(id="UPPER"), set())["id"],
                         "upper")

    # ---- the plist ----------------------------------------------------------
    def test_the_plist_never_fires_on_login_and_stays_in_the_gui_session(self):
        rec = self.R.validate_new(self._body(), set())
        p = self.R.build_plist(rec)
        self.assertIs(p["RunAtLoad"], False,
                      "a routine must not fire merely because you logged in")
        self.assertEqual(p["LimitLoadToSessionType"], "Aqua",
                         "claude's credentials are in the login keychain; a "
                         "non-Aqua job can meet it locked")
        self.assertTrue(all(isinstance(v, str)
                            for v in p["EnvironmentVariables"].values()),
                        "launchd silently ignores non-string env values")

    def test_a_manual_routine_gets_no_calendar_interval(self):
        rec = self.R.validate_new(self._body(schedule={"preset": "manual"}), set())
        self.assertNotIn("StartCalendarInterval", self.R.build_plist(rec))

    def test_run_records_distinguish_manual_from_scheduled(self):
        """kickstart reuses the plist's argv, so without a marker every run would
        claim to be scheduled and the UI could never tell you the schedule has
        never actually fired."""
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "routines.py"), encoding="utf-8").read()
        self.assertIn('.manual', src)
        self.assertIn('trigger = "manual"', src)

    def _body(self, **kw):
        b = {"id": "test-routine", "description": "d", "prompt": "p",
             "cwd": self.tmp, "opts": {"max_budget_usd": 1.0},
             "schedule": {"preset": "daily", "hour": 9, "minute": 0}}
        b.update(kw)
        return b


class TestProposals(unittest.TestCase):
    """The chat agent may ASK; only the operator may APPLY.

    These pin the property the whole design rests on: a proposal is INERT.
    Writing one must not create a routine, touch launchd, or change settings.
    """

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import proposals
        self.P = proposals
        self.tmp = tempfile.mkdtemp()
        self._env = dict(os.environ)
        os.environ["SUTRA_UI_PROPOSALS"] = os.path.join(self.tmp, "proposals")

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_known_kinds_can_be_proposed(self):
        """A positive allow-list: adding a tool to the MCP server is not enough
        on its own to make something applicable."""
        with self.assertRaises(ValueError):
            self.P.create("settings.write", {"permission_mode": "bypassPermissions"},
                          "turn on write mode")
        self.P.create("routine.create", {"id": "x"}, "ok")

    def test_creating_a_proposal_applies_nothing(self):
        p = self.P.create("routine.delete", {"id": "something"}, "delete it")
        self.assertEqual(p["status"], "pending")
        self.assertIsNone(p["result"])
        # proposals.py must not even be ABLE to apply: it never imports routines
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "proposals.py"), encoding="utf-8").read()
        self.assertNotIn("import routines", src,
                         "proposals.py must not be able to mutate anything itself")

    def test_rejecting_never_calls_the_applier(self):
        p = self.P.create("routine.run", {"id": "r"}, "run it")
        called = []
        out = self.P.decide(p["id"], False, apply_fn=lambda k, a: called.append(k))
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(called, [], "a rejection must not apply anything")

    def test_approving_applies_exactly_once(self):
        p = self.P.create("routine.run", {"id": "r"}, "run it")
        calls = []
        out = self.P.decide(p["id"], True,
                            apply_fn=lambda k, a: (calls.append((k, a)), {"ok": True})[1])
        self.assertEqual(out["status"], "approved")
        self.assertEqual(len(calls), 1)
        # and it cannot be applied a second time
        with self.assertRaises(ValueError):
            self.P.decide(p["id"], True, apply_fn=lambda k, a: calls.append(k))
        self.assertEqual(len(calls), 1, "a decided proposal must not re-apply")

    def test_a_failed_apply_is_recorded_not_rolled_back(self):
        """The operator already said yes. Re-offering the click would invite them
        to approve something that has already been tried and did not work."""
        p = self.P.create("routine.create", {"id": "x"}, "make it")
        def boom(kind, args):
            raise RuntimeError("launchd refused")
        out = self.P.decide(p["id"], True, apply_fn=boom)
        self.assertEqual(out["status"], "failed")
        self.assertIn("launchd refused", out["result"]["error"])
        self.assertNotEqual(out["status"], "pending")

    def test_an_old_proposal_expires_rather_than_waiting_forever(self):
        p = self.P.create("routine.delete", {"id": "r"}, "delete")
        rec = self.P.get(p["id"])
        rec["created_ms"] = int((time.time() - self.P.TTL_SECONDS - 60) * 1000)
        self.P._write(rec)
        self.assertEqual(self.P.listing()[0]["status"], "expired")
        with self.assertRaises(ValueError):
            self.P.decide(p["id"], True, apply_fn=lambda k, a: None)


class TestMcpServer(unittest.TestCase):
    """The tool surface the chat agent gets. Driven as a real subprocess over
    stdio, because that is exactly how the CLI runs it."""

    def _rpc(self, msgs, env=None):
        here = os.path.dirname(os.path.abspath(__file__))
        e = dict(os.environ); e.update(env or {})
        p = subprocess.run([sys.executable, os.path.join(here, "sutra_mcp.py")],
                           input="\n".join(json.dumps(m) for m in msgs),
                           capture_output=True, text=True, timeout=60, env=e)
        return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]

    def test_it_speaks_mcp(self):
        out = self._rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                         {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        init = [m for m in out if m.get("id") == 1][0]
        self.assertEqual(init["result"]["serverInfo"]["name"], "sutra")
        tools = [m for m in out if m.get("id") == 2][0]["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertIn("sutra_routine_create", names)
        for t in tools:
            self.assertTrue(t["description"], "every tool needs a description")
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_a_mutating_tool_returns_a_proposal_not_a_result(self):
        """The wording matters: the agent must not tell the operator it is done."""
        tmp = tempfile.mkdtemp()
        try:
            out = self._rpc(
                [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                     "name": "sutra_routine_create", "arguments": {
                         "id": "t-prop", "description": "d", "prompt": "p",
                         "cwd": os.path.expanduser("~"),
                         "schedule": {"preset": "daily", "hour": 9, "minute": 0}}}}],
                env={"SUTRA_UI_PROPOSALS": os.path.join(tmp, "props"),
                     "SUTRA_UI_ROUTINES": os.path.join(tmp, "routines"),
                     "SUTRA_UI_LAUNCHAGENTS": os.path.join(tmp, "agents")})
            txt = [m for m in out if m.get("id") == 2][0]["result"]["content"][0]["text"]
            self.assertIn("PROPOSAL", txt)
            self.assertIn("Nothing has changed yet", txt)
            # and NOTHING was created
            self.assertFalse(os.path.isdir(os.path.join(tmp, "routines"))
                             and os.listdir(os.path.join(tmp, "routines")))
            self.assertFalse(os.path.isdir(os.path.join(tmp, "agents"))
                             and os.listdir(os.path.join(tmp, "agents")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_invalid_routine_is_refused_before_it_is_proposed(self):
        """A proposal that cannot apply is worse than a refusal -- the operator
        would approve it and watch it fail for a reason nobody showed them."""
        tmp = tempfile.mkdtemp()
        try:
            out = self._rpc(
                [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                     "name": "sutra_routine_create", "arguments": {
                         "id": "Not Valid", "description": "d", "prompt": "p",
                         "cwd": "/etc"}}}],
                env={"SUTRA_UI_PROPOSALS": os.path.join(tmp, "props")})
            res = [m for m in out if m.get("id") == 2][0]["result"]
            self.assertTrue(res.get("isError"))
            self.assertFalse(os.path.isdir(os.path.join(tmp, "props"))
                             and os.listdir(os.path.join(tmp, "props")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestAgentArgsMcp(unittest.TestCase):
    def test_the_chat_run_gets_sutra_tools_and_cannot_stall_on_them(self):
        import app as A
        args = A.build_agent_args("/usr/bin/claude", "hi", "plan")
        self.assertIn("--mcp-config", args)
        self.assertIn("--strict-mcp-config", args,
                      "without this the CLI also loads the user's global servers")
        self.assertEqual(args[args.index("--allowedTools") + 1], "mcp__sutra__*",
                         "a -p run has nobody to answer a permission prompt, so "
                         "these must be pre-allowed or the turn stalls")
        cfg = json.loads(args[args.index("--mcp-config") + 1])
        self.assertEqual(cfg["mcpServers"]["sutra"]["type"], "stdio")
        self.assertTrue(cfg["mcpServers"]["sutra"]["args"][0].endswith("sutra_mcp.py"))
