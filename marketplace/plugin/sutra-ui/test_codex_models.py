"""The Codex model picker: asked of Codex, never guessed.

WHAT THIS REPLACED. providers._CODEX_MODELS declared one entry -- "CLI default"
-- on the finding that codex-cli publishes no model roster. That was checked
four ways (no `models` subcommand, nothing in `exec --help`, `doctor` says
`model <default> · openai`, zero model ids in the 1.79 MB app-server JSON
schema) and all four are STILL TRUE. They were the wrong question: the roster is
an RPC. `model/list` exists, and its own params type says what it is for --
`includeHidden`: "When true, include models that are hidden from the default
picker list."

WHY NOTHING HERE ASSERTS A CATALOGUE. Three sources exist and they disagree
(measured 2026-09-08): model/list answered 3 visible models, ~/.codex/
models_cache.json held the same 5, and the 210 MB Rust binary carries 11 --
including `gpt-6-astra` and `gpt-5.6-sol`, both real, both documented, both live
in the OpenAI API, and NEITHER selectable on the measured account. A picker
built from the binary offers six models that do not work, and each fails
silently: an unknown `-m` is accepted with a "Model metadata not found" warning
and then runs on degraded fallback metadata. So every test drives a STUB
app-server, and the assertions are about the MAPPING and the FALLBACK.

No real codex, no network, no credential, no model turn.
"""
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import codex_models
import providers

#: Shaped like the measured response: two visible, two hidden, one isDefault.
#: The ids are real only because a fixture must say something; no assertion
#: treats them as the product's catalogue.
_VISIBLE = [
    {"id": "gpt-5.6-terra", "model": "gpt-5.6-terra",
     "displayName": "GPT-5.6-Terra",
     "description": "Balanced agentic coding model for everyday work.",
     "hidden": False, "isDefault": True},
    {"id": "gpt-5.6-luna", "model": "gpt-5.6-luna",
     "displayName": "GPT-5.6-Luna",
     "description": "Fast and affordable agentic coding model.",
     "hidden": False, "isDefault": False},
]
_HIDDEN = [
    {"id": "gpt-reserve", "displayName": "GPT-Reserve", "hidden": True},
    {"id": "codex-auto-review", "displayName": "Codex Auto Review",
     "hidden": True},
]


def _script(body):
    """A stub `codex` whose `app-server` answers the protocol.

    Emits a notification line between the two replies, because the real server
    does and a reader that could not skip it would pass here and fail in the
    field. Ends by draining stdin so the child does not die before the parent
    has read its answer.
    """
    return ("#!/bin/sh\n"
            "read _a\n"
            'echo \'{"id":1,"result":{"codexHome":"/tmp"}}\'\n'
            'echo \'{"method":"remoteControl/status/changed","params":{}}\'\n'
            "read _b\n"
            "cat <<'JSON'\n"
            + json.dumps({"id": 2, "result": {"data": body}}) + "\n"
            "JSON\n"
            "cat > /dev/null\n")


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self._orig = providers.SETTINGS_PATH
        providers.SETTINGS_PATH = self.dir / "settings.json"
        self.addCleanup(setattr, providers, "SETTINGS_PATH", self._orig)

        self._env = dict(os.environ)
        self.addCleanup(self._restore)
        # A CODEX_HOME of our own: the last-resort models_cache.json read and
        # the config scan must never reach the operator's real files.
        os.environ["CODEX_HOME"] = str(self.dir / "codexhome")
        (self.dir / "codexhome").mkdir()
        os.environ.pop("SUTRA_UI_CODEX_BIN", None)

        self._done = providers._LOGIN_PATH_DONE
        providers._LOGIN_PATH_DONE = True
        self.addCleanup(setattr, providers, "_LOGIN_PATH_DONE", self._done)
        kb = mock.patch.object(providers, "_known_bin_dirs", return_value=[])
        kb.start()
        self.addCleanup(kb.stop)
        providers._CODEX_MODEL_CACHE.clear()

        codex_models._reset_for_tests()
        self.addCleanup(codex_models._reset_for_tests)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._env)

    def codex(self, script):
        p = self.dir / "codex"
        p.write_text(script)
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        os.environ["SUTRA_UI_CODEX_BIN"] = str(p)
        return p

    def serve(self, body):
        return self.codex(_script(body))

    def ids(self):
        return [m["id"] for m in providers.models_for("codex")]


class VisibleModelsAppear(_Base):

    def test_the_picker_offers_what_codex_answered(self):
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(self.ids(), ["", "gpt-5.6-terra", "gpt-5.6-luna"])

    def test_displayName_and_description_become_the_label_and_note(self):
        self.serve(_VISIBLE)
        got = codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(got[0]["name"], "GPT-5.6-Terra")
        self.assertIn("Balanced agentic coding", got[0]["note"])

    def test_isDefault_is_preserved(self):
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_default_model(), "gpt-5.6-terra")

    def test_cli_default_is_first_and_keeps_the_empty_id(self):
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        first = providers.models_for("codex")[0]
        self.assertEqual((first["id"], first["name"]), ("", "CLI default"))

    def test_the_PUBLISHED_payload_carries_the_discovered_models(self):
        """THE BUG THIS PINS, and it shipped past every other test in this file.

        all_models_by_provider() built its dict from `spec["models"]` -- the
        STATIC catalogue tuple -- while clean_model, selectable_model_ids_for
        and model_ids_for all went through models_for(). So a discovered model
        VALIDATED and reached `-m` correctly, and the picker had no row to
        select it from: the live dev server answered
        models_by_provider.codex = [CLI default] on a machine where discovery
        had just returned three models.

        Every other assertion here reads models_for() directly. This one reads
        what /api/settings actually PUBLISHES, which is the only thing the
        picker renders -- the gap was in what was asserted, not just in the
        code.
        """
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        published = providers.all_models_by_provider()["codex"]
        self.assertEqual([m["id"] for m in published],
                         ["", "gpt-5.6-terra", "gpt-5.6-luna"])
        self.assertEqual(published[1]["name"], "GPT-5.6-Terra")

    def test_the_published_payload_hides_hidden_models_too(self):
        self.serve(_VISIBLE + _HIDDEN)
        codex_models.refresh_if_stale("chatgpt")
        ids = [m["id"] for m in providers.all_models_by_provider()["codex"]]
        self.assertNotIn("gpt-reserve", ids)
        self.assertNotIn("codex-auto-review", ids)

    def test_the_published_payload_degrades_with_discovery(self):
        """No discovery -> the payload is exactly what it was before the
        feature, so a failure cannot empty the picker."""
        with mock.patch.object(providers, "provider_bin", return_value=None):
            codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(
            [m["id"] for m in providers.all_models_by_provider()["codex"]], [""])

    def test_the_published_payload_is_unchanged_for_other_providers(self):
        """models_for() returns spec["models"] verbatim for every id but codex,
        so this must stay byte-identical -- and gemini must stay ABSENT rather
        than appearing as an empty picker."""
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        published = providers.all_models_by_provider()
        for pid in ("claude", "deepseek"):
            spec = next(s for s in providers._CATALOG if s["id"] == pid)
            self.assertEqual(published[pid], list(spec["models"]), pid)
        self.assertNotIn("gemini", published,
                         "a provider with no static models gained a picker")


class HiddenModelsAreExcluded(_Base):

    def test_internal_models_never_reach_the_picker(self):
        """`gpt-reserve` is a reserve pool and `codex-auto-review` is an
        approval-review model. Codex marks them hidden precisely so a picker
        does not offer them."""
        self.serve(_VISIBLE + _HIDDEN)
        codex_models.refresh_if_stale("chatgpt")
        got = self.ids()
        self.assertEqual(got, ["", "gpt-5.6-terra", "gpt-5.6-luna"])
        self.assertNotIn("gpt-reserve", got)
        self.assertNotIn("codex-auto-review", got)

    def test_includeHidden_is_sent_as_false_explicitly(self):
        """The protocol default is the picker list already, but naming it is
        what stops a later default from putting internal models on screen.

        The stub writes NOTHING to stdout, so this also exercises the timeout
        bound -- and it is the case that hung the first draft of this file,
        because the read loop checked its deadline between reads and never
        during one."""
        seen = self.dir / "req.txt"
        self.codex("#!/bin/sh\ncat > %s\n" % seen)
        with mock.patch.object(codex_models, "TIMEOUT_SECONDS", 1):
            self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        body = seen.read_text() if seen.exists() else ""
        self.assertIn('"model/list"', body)
        self.assertIn('"includeHidden": false', body)


class TheSelectionReachesTheCli(_Base):

    def test_a_selected_model_emits_exactly_one_m_flag(self):
        args = app.build_codex_args("/x/codex", "plan", "/wd",
                                    model="gpt-5.6-luna")
        self.assertEqual(args.count("-m"), 1)
        self.assertEqual(args[args.index("-m") + 1], "gpt-5.6-luna")

    def test_cli_default_emits_no_m_at_all(self):
        for model in (None, ""):
            args = app.build_codex_args("/x/codex", "plan", "/wd", model=model)
            self.assertNotIn("-m", args, "model=%r emitted a flag" % model)

    def test_a_discovered_model_survives_validation(self):
        """THE WHOLE POINT: a picked model must REACH codex. clean_model gates
        every value against the selectable set, so a discovered id that did not
        pass would be a control that silently did nothing."""
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.clean_model("gpt-5.6-luna", "codex"),
                         "gpt-5.6-luna")

    def test_a_model_this_account_does_not_have_is_refused(self):
        """The failure a binary-scraped catalogue would have shipped: an id
        that exists upstream but not for this account."""
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        self.assertIsNone(providers.clean_model("gpt-5.6-sol", "codex"))
        self.assertIsNone(providers.clean_model("gpt-6-astra", "codex"))


class DiscoveryFailureFallsBackSafely(_Base):
    """Every one of these must leave the provider on the behaviour it had
    before this feature: CLI default only, no -m, nothing invented."""

    def _assert_cli_default_only(self):
        self.assertEqual(self.ids(), [""])

    def test_no_binary(self):
        with mock.patch.object(providers, "provider_bin", return_value=None):
            self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_the_app_server_refuses_to_start(self):
        self.codex("#!/bin/sh\nexit 1\n")
        self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_a_malformed_response(self):
        self.codex("#!/bin/sh\nread a\necho 'not json at all'\n"
                   "echo '{\"id\":2,\"result\":\"a string, not an object\"}'\n"
                   "cat > /dev/null\n")
        self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_data_that_is_not_a_list(self):
        self.serve("nope")
        self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_entries_that_are_not_dicts(self):
        self.serve(["a string", 7, None])
        self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_a_jsonrpc_error(self):
        self.codex("#!/bin/sh\nread a\necho '{\"id\":1,\"result\":{}}'\n"
                   "read b\necho '{\"id\":2,\"error\":{\"code\":-32601,"
                   "\"message\":\"method not found\"}}'\ncat > /dev/null\n")
        self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_a_silent_server_is_bounded_and_falls_back(self):
        """The defect this file's first draft found in the implementation: a
        child that starts and never answers must not park the caller. This runs
        inside GET /providers/codex/auth, so an unbounded read would hang the
        provider screen with nothing to cancel it."""
        self.codex("#!/bin/sh\ncat > /dev/null\n")
        with mock.patch.object(codex_models, "TIMEOUT_SECONDS", 1):
            self.assertEqual(codex_models.refresh_if_stale("chatgpt"), ())
        self._assert_cli_default_only()

    def test_the_config_scan_remains_as_a_lower_priority_fallback(self):
        """A `model` the operator wrote into their own codex config is a
        legitimate custom choice reachable only through that path, so it is
        kept BEHIND discovery rather than deleted."""
        (Path(os.environ["CODEX_HOME"]) / "config.toml").write_text(
            'model = "my-own-model"\n')
        providers._CODEX_MODEL_CACHE.clear()
        with mock.patch.object(providers, "provider_bin", return_value=None):
            codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(self.ids(), ["", "my-own-model"])

    def test_discovery_wins_over_the_config_scan(self):
        (Path(os.environ["CODEX_HOME"]) / "config.toml").write_text(
            'model = "my-own-model"\n')
        providers._CODEX_MODEL_CACHE.clear()
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(self.ids(), ["", "gpt-5.6-terra", "gpt-5.6-luna"])


class DiscoveryIsNotOnTheRenderPath(_Base):
    """providers.models_for() is reached by load_settings(), and every fs/tree,
    fs/read and settings GET goes through that."""

    def test_models_for_never_spawns(self):
        import subprocess as sp
        self.serve(_VISIBLE)
        with mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("models_for spawned")):
            providers.models_for("codex")
            providers.all_models_by_provider()
        self.assertIsNone(codex_models.cached())

    def test_repeated_refreshes_inside_the_ttl_spawn_once(self):
        import subprocess as sp
        calls, real = [], sp.Popen
        self.serve(_VISIBLE)
        with mock.patch.object(sp, "Popen",
                               side_effect=lambda *a, **k: (calls.append(1),
                                                            real(*a, **k))[1]):
            for _ in range(5):
                codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(len(calls), 1, "spawned %d times" % len(calls))

    def test_a_credential_change_re_asks(self):
        """A ChatGPT plan and an API key are scoped by different things and may
        offer different models, so a state change invalidates the list rather
        than assuming they match."""
        import subprocess as sp
        calls, real = [], sp.Popen
        self.serve(_VISIBLE)
        with mock.patch.object(sp, "Popen",
                               side_effect=lambda *a, **k: (calls.append(1),
                                                            real(*a, **k))[1]):
            codex_models.refresh_if_stale("chatgpt")
            codex_models.refresh_if_stale("chatgpt")    # cached
            codex_models.refresh_if_stale("api_key")    # re-asked
        self.assertEqual(len(calls), 2)


class OtherProvidersAreUntouched(_Base):

    def test_claude_and_deepseek_catalogues_are_unchanged(self):
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        for pid in ("claude", "deepseek", "gemini"):
            spec = next(s for s in providers._CATALOG if s["id"] == pid)
            self.assertEqual(providers.models_for(pid), spec["models"], pid)

    def test_a_codex_model_cannot_validate_for_another_provider(self):
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        for pid in ("claude", "deepseek"):
            self.assertIsNone(providers.clean_model("gpt-5.6-luna", pid), pid)

    def test_no_model_id_is_hardcoded_in_the_module(self):
        """A provable negative: the module may not hold a catalogue."""
        import re
        src = Path(__file__).with_name("codex_models.py").read_text()
        code = re.sub(r'""".*?"""', "", src, flags=re.S)
        code = "\n".join(l for l in code.split("\n")
                         if not l.lstrip().startswith("#"))
        hits = re.findall(
            r'["\'](gpt-[0-9][A-Za-z0-9._-]*|gpt-reserve|codex-auto-review)["\']',
            code)
        self.assertEqual(hits, [], "a model id is hardcoded: %r" % hits)


if __name__ == "__main__":
    unittest.main()


class ReasoningEffortComesFromTheModel(_Base):
    """The other axis from Reasoning summary: effort is how much reasoning codex
    DOES, summary is how much it SHOWS. They share no values.

    It waited for model/list because `-c model_reasoning_effort` ACCEPTS an
    unknown value without complaint -- measured on 0.153.2, "__bogus__" sailed
    through where a made-up KEY was refused outright. So before there was an
    enumeration, any list would have been guesses. model/list supplies one, per
    model, and the sets genuinely differ -- which is what every test here is
    really about.
    """

    #: Two models with DIFFERENT effort sets. The ids are fixture names on
    #: purpose: nothing about this feature may depend on a real catalogue.
    _EFFORTS = [
        {"id": "m-alpha", "displayName": "Alpha", "description": "a",
         "hidden": False, "isDefault": True,
         "supportedReasoningEfforts": [{"reasoningEffort": "low"},
                                       {"reasoningEffort": "high"},
                                       {"reasoningEffort": "ultra"}]},
        {"id": "m-beta", "displayName": "Beta", "description": "b",
         "hidden": False, "isDefault": False,
         "supportedReasoningEfforts": [{"reasoningEffort": "low"},
                                       {"reasoningEffort": "high"}]},
    ]

    def test_efforts_are_read_off_the_model(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_efforts_for("m-alpha"),
                         ("low", "high", "ultra"))

    def test_different_models_expose_different_sets(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_efforts_for("m-beta"), ("low", "high"))
        self.assertNotIn("ultra", providers.codex_efforts_for("m-beta"))

    def test_cli_default_resolves_to_the_default_models_efforts(self):
        """The picker's "" row and this validator must resolve the same model,
        or the control offers a value the server then drops."""
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_efforts_for(None),
                         providers.codex_efforts_for("m-alpha"))

    def test_the_published_entries_carry_efforts_and_the_default_marker(self):
        """Both are for the CLIENT: the control offers the selected model's
        efforts, and on "CLI default" it has to know which model that is."""
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        pub = {m["id"]: m for m in providers.all_models_by_provider()["codex"]}
        self.assertEqual(list(pub["m-alpha"]["efforts"]), ["low", "high", "ultra"])
        self.assertTrue(pub["m-alpha"]["default"])
        self.assertFalse(pub["m-beta"]["default"])

    def test_a_bare_string_list_is_accepted_too(self):
        """The cheaper shape a future build is likelier to move to; misreading
        it would silently empty the picker rather than fail."""
        self.serve([{"id": "m-x", "hidden": False,
                     "supportedReasoningEfforts": ["low", "high"]}])
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_efforts_for("m-x"), ("low", "high"))

    # ---------------------------------------------------------- the argv ----

    def test_an_explicit_effort_emits_the_config(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(
            app.codex_turn_config({"reasoning_effort": "ultra"}, "m-alpha"),
            ["-c", 'model_reasoning_effort="ultra"'])

    def test_default_emits_nothing(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        for v in ("", "   ", None):
            self.assertEqual(
                app.codex_turn_config({"reasoning_effort": v}, "m-alpha"), [],
                "effort=%r emitted something" % v)

    def test_an_effort_this_model_does_not_support_is_dropped(self):
        """codex takes an unsupported value SILENTLY, so the turn would run at
        something other than what the control said. This is the guard."""
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(
            app.codex_turn_config({"reasoning_effort": "ultra"}, "m-beta"), [])

    def test_an_unknown_model_drops_every_effort(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(
            app.codex_turn_config({"reasoning_effort": "low"}, "nope"), [])

    def test_no_discovery_drops_every_effort(self):
        with mock.patch.object(providers, "provider_bin", return_value=None):
            codex_models.refresh_if_stale("chatgpt")
        self.assertEqual(providers.codex_efforts_for("m-alpha"), ())
        self.assertEqual(
            app.codex_turn_config({"reasoning_effort": "low"}, "m-alpha"), [])

    def test_junk_types_are_survived(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        for v in (7, None, ["low"], {"a": 1}, True):
            self.assertEqual(
                app.codex_turn_config({"reasoning_effort": v}, "m-alpha"), [],
                repr(v))

    def test_it_reaches_the_full_argv_before_resume(self):
        """`codex exec resume` accepts no flags after it -- measured."""
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        args = app.build_codex_args("/x/codex", "plan", "/wd", model="m-alpha",
                                    session_id="T1",
                                    opts={"reasoning_effort": "high"})
        self.assertIn('model_reasoning_effort="high"', args)
        self.assertLess(args.index('model_reasoning_effort="high"'),
                        args.index("resume"))
        self.assertEqual(args[-1], "-")

    def test_the_effort_is_validated_against_the_TURNS_model(self):
        """build_codex_args passes its own `model` through, so a pane on beta
        cannot borrow alpha's ultra."""
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        args = app.build_codex_args("/x/codex", "plan", "/wd", model="m-beta",
                                    opts={"reasoning_effort": "ultra"})
        self.assertNotIn("model_reasoning_effort=\"ultra\"", args)

    # ------------------------------------------------- nothing else moved ----

    def test_reasoning_summary_is_unchanged(self):
        self.assertEqual(providers.CODEX_REASONING_SUMMARY,
                         ("", "auto", "concise", "detailed", "none"))
        self.assertEqual(app.codex_turn_config({"reasoning_summary": "detailed"}),
                         ["-c", 'model_reasoning_summary="detailed"'])

    def test_verbosity_is_unchanged(self):
        self.assertEqual(providers.CODEX_VERBOSITY, ("", "low", "medium", "high"))
        self.assertEqual(app.codex_turn_config({"verbosity": "high"}),
                         ["-c", 'model_verbosity="high"'])

    def test_all_three_compose(self):
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        got = app.codex_turn_config(
            {"reasoning_summary": "concise", "verbosity": "low",
             "reasoning_effort": "high"}, "m-alpha")
        self.assertEqual(got, [
            "-c", 'model_reasoning_summary="concise"',
            "-c", 'model_verbosity="low"',
            "-c", 'model_reasoning_effort="high"'])

    def test_the_provider_declares_all_three(self):
        self.assertEqual(providers.turn_options_for("codex"),
                         ("reasoning_summary", "verbosity", "reasoning_effort"))

    def test_other_providers_turn_options_are_untouched(self):
        self.assertEqual(providers.turn_options_for("deepseek"), ())
        self.assertNotIn("reasoning_effort", providers.turn_options_for("claude"))

    def test_efforts_lookup_never_spawns(self):
        import subprocess as sp
        self.serve(self._EFFORTS)
        codex_models.refresh_if_stale("chatgpt")
        with mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("efforts spawned")):
            providers.codex_efforts_for("m-alpha")
            providers.codex_efforts_for(None)
            app.codex_turn_config({"reasoning_effort": "high"}, "m-alpha")


def _plan_script(result):
    """A stub `codex app-server` answering account/rateLimits/read."""
    return ("#!/bin/sh\n"
            "read _a\n"
            'echo \'{"id":1,"result":{"codexHome":"/tmp"}}\'\n'
            'echo \'{"method":"remoteControl/status/changed","params":{}}\'\n'
            "read _b\n"
            "cat <<'JSON'\n"
            + json.dumps({"id": 2, "result": result}) + "\n"
            "JSON\n"
            "cat > /dev/null\n")


#: The shape measured live on 2026-09-09 -- planType "go", ONE 30-day window,
#: no `secondary`, credits all-null. Kept verbatim because it is the shape that
#: disproves the "5-hour and weekly" assumption this feature was nearly built on.
_MEASURED = {
    "rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 43200,
                               "resetsAt": 1791134890},
                   "planType": "go", "limitId": "codex",
                   "rateLimitReachedType": None, "spendControlReached": False,
                   "credits": {"hasCredits": False, "unlimited": False,
                               "balance": None}},
    "rateLimitsByLimitId": {"codex": {
        "primary": {"usedPercent": 5, "windowDurationMins": 43200,
                    "resetsAt": 1791134890},
        "planType": "go", "limitId": "codex"}},
    "rateLimitResetCredits": {"availableCount": 0},
}


class PlanUsageIsReadFromCodex(_Base):
    """`account/rateLimits/read` over the SAME transport model/list uses.

    Measured live: answers in under a second and consumes NO model turn.

    NOTHING HERE ASSERTS A WINDOW DURATION AS A CONSTANT. The measured account
    returns one 30-day window; other plans return the five-hour/weekly pair. A
    build that hardcoded either would mislabel the other, so every assertion is
    about the MAPPING.
    """

    def plan(self, result):
        self.codex(_plan_script(result))
        return codex_models.refresh_plan_if_stale("chatgpt")

    def setUp(self):
        super().setUp()
        codex_models._reset_plan_for_tests()
        self.addCleanup(codex_models._reset_plan_for_tests)

    # ------------------------------------------------------------ parsing ----

    def test_the_measured_response_parses(self):
        p = self.plan(_MEASURED)
        self.assertEqual(p["plan_type"], "go")
        self.assertEqual(p["limit_id"], "codex")
        self.assertEqual(len(p["windows"]), 1)
        w = p["windows"][0]
        self.assertEqual((w["used_percent"], w["duration_mins"], w["resets_at"]),
                         (5.0, 43200, 1791134890))

    def test_the_mirrored_bucket_is_not_drawn_twice(self):
        """rateLimits is the protocol's own "backward-compatible single-bucket
        view" of rateLimitsByLimitId, so on a one-limit account the same window
        arrives twice and would render twice."""
        self.assertEqual(len(self.plan(_MEASURED)["windows"]), 1)

    def test_one_window_response(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 12,
                                                  "windowDurationMins": 300,
                                                  "resetsAt": 111}}})
        self.assertEqual([w["duration_mins"] for w in p["windows"]], [300])

    def test_multiple_windows_are_all_returned(self):
        p = self.plan({"rateLimits": {
            "primary": {"usedPercent": 12, "windowDurationMins": 300, "resetsAt": 111},
            "secondary": {"usedPercent": 44, "windowDurationMins": 10080, "resetsAt": 222}}})
        self.assertEqual([(w["duration_mins"], w["used_percent"]) for w in p["windows"]],
                         [(300, 12.0), (10080, 44.0)])

    def test_a_missing_secondary_is_a_normal_answer(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 1,
                                                  "windowDurationMins": 60}}})
        self.assertEqual(len(p["windows"]), 1)
        self.assertIsNone(p["windows"][0]["resets_at"])

    def test_windows_from_rateLimitsByLimitId_are_included(self):
        p = self.plan({"rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 7, "windowDurationMins": 300},
                      "planType": "plus"},
            "other": {"primary": {"usedPercent": 9, "windowDurationMins": 10080}}}})
        self.assertEqual(sorted(w["duration_mins"] for w in p["windows"]),
                         [300, 10080])
        self.assertEqual(p["plan_type"], "plus")

    def test_any_duration_is_carried_through_untouched(self):
        """The durations are DATA. Nothing in this module may special-case one."""
        for mins in (5, 60, 300, 1440, 10080, 43200, 99999, None):
            # The cache is per-state and the state does not change across these,
            # so each iteration has to bypass it -- otherwise every assertion
            # after the first reads the first answer back. (It did, and said so.)
            codex_models._reset_plan_for_tests()
            p = self.plan({"rateLimits": {"primary": {"usedPercent": 3,
                                                      "windowDurationMins": mins}}})
            self.assertEqual(p["windows"][0]["duration_mins"], mins, repr(mins))

    def test_reset_timestamps_are_passed_through_as_unix_seconds(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 3,
                                                  "resetsAt": 1791134890}}})
        self.assertEqual(p["windows"][0]["resets_at"], 1791134890)

    def test_a_window_with_no_percentage_is_not_a_window(self):
        p = self.plan({"rateLimits": {"primary": {"windowDurationMins": 300},
                                      "planType": "go"}})
        self.assertEqual(p["windows"], [])
        self.assertEqual(p["plan_type"], "go")

    # ------------------------------------------------------------ credits ----

    def test_credits_absent_when_openai_reports_none(self):
        """THE null RULE. {hasCredits:false, unlimited:false, balance:null} is
        "no credits here", NOT "your balance is zero" -- rendering 0 would read
        as an exhausted balance, which is a different and alarming claim."""
        self.assertIsNone(self.plan(_MEASURED)["credits"])

    def test_credits_present_when_a_balance_is_reported(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 1},
                                      "credits": {"hasCredits": True,
                                                  "unlimited": False,
                                                  "balance": "12.50"}}})
        self.assertEqual(p["credits"], {"unlimited": False, "balance": "12.50",
                                        "has_credits": True})

    def test_unlimited_credits_are_reported_without_a_balance(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 1},
                                      "credits": {"hasCredits": True,
                                                  "unlimited": True,
                                                  "balance": None}}})
        self.assertTrue(p["credits"]["unlimited"])
        self.assertIsNone(p["credits"]["balance"])

    def test_a_zero_balance_is_still_a_balance(self):
        p = self.plan({"rateLimits": {"primary": {"usedPercent": 1},
                                      "credits": {"hasCredits": False,
                                                  "unlimited": False,
                                                  "balance": "0"}}})
        self.assertEqual(p["credits"]["balance"], "0")

    # ------------------------------------------------------- degradation ----

    def test_an_rpc_failure_degrades_to_no_plan(self):
        self.codex("#!/bin/sh\nexit 1\n")
        self.assertIsNone(codex_models.refresh_plan_if_stale("chatgpt"))
        self.assertIsNone(codex_models.plan_cached())

    def test_a_malformed_response_degrades_to_no_plan(self):
        self.codex("#!/bin/sh\nread a\necho 'not json'\n"
                   "echo '{\"id\":2,\"result\":\"a string\"}'\ncat > /dev/null\n")
        self.assertIsNone(codex_models.refresh_plan_if_stale("chatgpt"))

    def test_a_silent_server_is_bounded(self):
        self.codex("#!/bin/sh\ncat > /dev/null\n")
        with mock.patch.object(codex_models, "TIMEOUT_SECONDS", 1):
            self.assertIsNone(codex_models.refresh_plan_if_stale("chatgpt"))

    def test_no_binary_degrades_to_no_plan(self):
        with mock.patch.object(providers, "provider_bin", return_value=None):
            self.assertIsNone(codex_models.refresh_plan_if_stale("chatgpt"))

    def test_an_empty_answer_is_no_plan(self):
        self.assertIsNone(self.plan({}))

    # --------------------------------------------------- the auth gate ------

    def test_api_key_mode_never_asks_codex(self):
        """A rate-limit window is a property of a ChatGPT PLAN -- the protocol's
        own PlanType enum has no API-key member. So this must not merely hide
        the answer, it must not request it."""
        import subprocess as sp
        self.codex(_plan_script(_MEASURED))
        with mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("api_key mode spawned")):
            self.assertIsNone(codex_models.refresh_plan_if_stale("api_key"))

    def test_logged_out_never_asks_codex(self):
        import subprocess as sp
        self.codex(_plan_script(_MEASURED))
        with mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("logged_out spawned")):
            self.assertIsNone(codex_models.refresh_plan_if_stale("logged_out"))

    def test_a_chatgpt_to_api_key_transition_CLEARS_the_plan(self):
        """Not stale -- gone. A percentage left after a credential change
        describes an allowance nothing is metering."""
        self.plan(_MEASURED)
        self.assertIsNotNone(codex_models.plan_cached())
        codex_models.refresh_plan_if_stale("api_key")
        self.assertIsNone(codex_models.plan_cached())

    # ------------------------------------------------------------ caching ---

    def test_repeated_reads_inside_the_ttl_spawn_once(self):
        import subprocess as sp
        calls, real = [], sp.Popen
        self.codex(_plan_script(_MEASURED))
        with mock.patch.object(sp, "Popen",
                               side_effect=lambda *a, **k: (calls.append(1),
                                                            real(*a, **k))[1]):
            for _ in range(4):
                codex_models.refresh_plan_if_stale("chatgpt")
        self.assertEqual(len(calls), 1, "spawned %d times" % len(calls))

    def test_plan_cached_is_pure(self):
        import subprocess as sp
        with mock.patch.object(sp, "Popen",
                               side_effect=AssertionError("plan_cached spawned")):
            self.assertIsNone(codex_models.plan_cached())

    def test_the_plan_cache_is_separate_from_the_model_cache(self):
        """The two reads answer different questions and go stale for different
        reasons; a plan refresh must not invalidate a model list."""
        self.serve(_VISIBLE)
        codex_models.refresh_if_stale("chatgpt")
        before = codex_models.cached()
        self.plan(_MEASURED)
        self.assertEqual(codex_models.cached(), before)

    def test_the_model_list_still_works_over_the_shared_transport(self):
        """_rpc was generalised to take a method; model/list must be untouched."""
        self.serve(_VISIBLE)
        got = codex_models.refresh_if_stale("chatgpt")
        self.assertEqual([m["id"] for m in got],
                         ["gpt-5.6-terra", "gpt-5.6-luna"])
