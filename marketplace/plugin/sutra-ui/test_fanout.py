"""test_fanout.py -- /fanout V1: trigger, planning, cost routing, concurrency,
failure isolation, cancellation, and the promise that normal chat is untouched.

NO SUBPROCESS, NO SERVER, NO PROVIDER BINARY. Every test here injects a fake
`runner` into fanout.run/execute, which is the reason run() takes one. The real
three-provider execution path is asserted separately, against the qa stubs, in
test_fanout_worker.py -- a fake runner can prove the ORCHESTRATION is right and
can prove nothing at all about whether `codex exec` was spawned correctly.

WHAT THE ROUTING TESTS ARE REALLY GUARDING. The requirement is "cheapest
suitable", and the failure mode it replaces is "spread the work around". Those
two produce the same answer whenever the task levels happen to be mixed, so
every routing test below either pins an ALL-SAME-LEVEL job (where balancing
would show up as multiple providers and cost-routing shows up as one) or pins
the specific provider a cost comparison must pick. A test that merely asserted
"more than one provider was used" would pass for the behaviour we do not want.
"""
import asyncio
import os
import unittest

import fanout
import providers


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _plan_json(*levels):
    rows = ['{"instruction": "do thing %d", "capability": "%s"}' % (i + 1, lv)
            for i, lv in enumerate(levels)]
    return "[" + ",".join(rows) + "]"


class FakeRunner:
    """An injectable stand-in for worker.run_one.

    Records every call, can be told to fail specific prompts, and tracks how
    many calls are IN FLIGHT at once -- which is the only honest way to assert
    a concurrency limit (counting completions proves nothing about overlap).
    """

    def __init__(self, plan_text="[]", reply="RESULT", fail_on=(),
                 delay=0.0, plan_ok=True):
        self.plan_text = plan_text
        self.reply = reply
        self.fail_on = set(fail_on)
        self.delay = delay
        self.plan_ok = plan_ok
        self.calls = []
        self.inflight = 0
        self.peak = 0
        self.planner_calls = 0

    async def __call__(self, pid, prompt, workdir, perm_mode, orch):
        is_plan = prompt.startswith("You are planning how to execute one job")
        self.inflight += 1
        self.peak = max(self.peak, self.inflight)
        try:
            self.calls.append({"pid": pid, "prompt": prompt, "plan": is_plan})
            if is_plan:
                self.planner_calls += 1
                if not self.plan_ok:
                    return {"ok": False, "text": "", "error": "planner exploded",
                            "provider": pid}
                return {"ok": True, "text": self.plan_text, "error": None,
                        "provider": pid}
            if self.delay:
                await asyncio.sleep(self.delay)
            for needle in self.fail_on:
                if needle in prompt:
                    return {"ok": False, "text": "", "error": "worker died",
                            "provider": pid}
            return {"ok": True, "text": "%s for: %s" % (self.reply, prompt),
                    "error": None, "provider": pid}
        finally:
            self.inflight -= 1

    def worker_pids(self):
        return [c["pid"] for c in self.calls if not c["plan"]]


class _Billing:
    """Pin the billing map so run() routes deterministically.

    Without this, fanout.cost_map() resolves codex by shelling out to
    `codex login status` -- slow, and its answer depends on whoever is signed
    in on the machine running the suite.
    """

    def __init__(self, models):
        self.models = dict(models)
        self._orig = None

    def __enter__(self):
        self._orig = fanout.cost_map
        fanout.cost_map = lambda pids: {p: self.models.get(p, "unknown")
                                        for p in pids}
        return self

    def __exit__(self, *a):
        fanout.cost_map = self._orig
        return False


class _Eligible:
    """Pin eligible_providers() without touching providers.py or the machine."""

    def __init__(self, ids):
        self.ids = list(ids)
        self._orig = None

    def __enter__(self):
        self._orig = fanout.eligible_providers
        fanout.eligible_providers = lambda: list(self.ids)
        return self

    def __exit__(self, *a):
        fanout.eligible_providers = self._orig
        return False


# ══════════════════════════════════════════════════════════ trigger ══════

class TriggerTest(unittest.TestCase):

    def test_fanout_message_enters_orchestration(self):
        self.assertTrue(fanout.should_orchestrate("/fanout research six things"))
        self.assertTrue(fanout.should_orchestrate("  /fanout do it  "))
        self.assertTrue(fanout.should_orchestrate("/FANOUT do it"))

    def test_a_normal_message_does_not(self):
        """The fast path. Anything that is not the command must be invisible
        to this feature."""
        for msg in ("research six competitors",
                    "what does /fanout do?",
                    "tell me about /fanout",
                    "please /fanout this",          # not at the start
                    "//fanout x", "", "   "):
            self.assertFalse(fanout.should_orchestrate(msg), msg)

    def test_a_longer_command_with_the_same_prefix_is_not_swallowed(self):
        """The day /fanoutv2 exists, /fanout must not eat it."""
        self.assertFalse(fanout.should_orchestrate("/fanoutv2 do it"))
        self.assertFalse(fanout.should_orchestrate("/fanout-all do it"))

    def test_non_string_is_not_a_trigger(self):
        for junk in (None, 17, {"message": "/fanout x"}, ["/fanout"]):
            self.assertFalse(fanout.should_orchestrate(junk))

    def test_bare_fanout_is_a_clean_error_not_an_empty_job(self):
        for msg in ("/fanout", "/fanout   ", "  /fanout\n"):
            got = fanout.parse_request(msg)
            self.assertFalse(got["ok"], msg)
            self.assertIn("needs a job", got["error"])
            self.assertEqual(got["job"], "")

    def test_the_job_is_the_text_after_the_command(self):
        got = fanout.parse_request("/fanout  Research these 6 competitors. ")
        self.assertTrue(got["ok"])
        self.assertEqual(got["job"], "Research these 6 competitors.")
        self.assertIsNone(got["error"])

    # ---- the grounding prefix: what the CLIENT actually sends -----------

    #: What 01-state.js groundingPrefix emits when nothing resolved -- the
    #: common case, and the exact bytes that reach ws_chat in front of every
    #: message typed in the real UI.
    GROUNDED = ("PLACEMENT: unresolved -- no department could be resolved "
                "for this turn.\n"
                "(confidence 0.00, mode none)\n"
                "Do not invent an address. Proceed, and name the gap if it "
                "matters.\n\n")

    def test_a_grounded_fanout_is_still_recognised(self):
        """THE BUG THIS CLOSES. askClaude sends
        `groundingPrefix(turn) + turn.text` (02-helpers.js), and
        groundingPrefix is never empty -- so a raw startswith() was False for
        every /fanout an operator could actually type, and the feature did
        nothing in the real UI while every server-side test passed."""
        msg = self.GROUNDED + "/fanout Research six competitors"
        self.assertTrue(fanout.should_orchestrate(msg))
        got = fanout.parse_request(msg)
        self.assertTrue(got["ok"])
        self.assertEqual(got["job"], "Research six competitors")
        self.assertEqual(got["prefix"], self.GROUNDED)

    def test_a_resolved_placement_block_is_handled_too(self):
        grounded = ('PLACEMENT: /eng/platform Platform | "Run the platform"\n'
                    "CHARTER PURPOSE: keep it up\n"
                    "(confidence 0.82, mode match)\n\n")
        got = fanout.parse_request(grounded + "/fanout do six things")
        self.assertTrue(got["ok"])
        self.assertEqual(got["job"], "do six things")
        self.assertEqual(got["prefix"], grounded)

    def test_the_prefix_is_returned_so_grounding_survives(self):
        """The PLACEMENT block is ADR-028 context the model is meant to see.
        Stripping it for detection must not mean dropping it from the turn."""
        got = fanout.parse_request(self.GROUNDED + "/fanout do six things")
        self.assertEqual(got["prefix"] + got["job"],
                         self.GROUNDED + "do six things")

    def test_a_grounded_normal_message_is_still_not_a_fanout(self):
        for tail in ("research six competitors",
                     "what does /fanout do?",
                     "tell me about /fanout"):
            self.assertFalse(fanout.should_orchestrate(self.GROUNDED + tail),
                             tail)

    def test_a_grounded_bare_command_is_a_clean_error(self):
        got = fanout.parse_request(self.GROUNDED + "/fanout")
        self.assertFalse(got["ok"])
        self.assertIn("needs a job", got["error"])

    def test_an_ungrounded_message_is_never_altered(self):
        """The strip only takes effect when what it uncovers IS the command,
        so an ordinary message cannot lose its first paragraph."""
        self.assertEqual(fanout.operator_text("plain text"), ("", "plain text"))
        odd = "PLACEMENT: I am writing about placement.\n\nAnd more."
        self.assertFalse(fanout.should_orchestrate(odd))
        got = fanout.parse_request(odd)
        self.assertFalse(got["ok"])

    def test_a_grounding_block_with_nothing_after_it_strips_nothing(self):
        self.assertEqual(fanout.operator_text("PLACEMENT: alone")[0], "")

    def test_operator_text_tolerates_non_strings(self):
        self.assertEqual(fanout.operator_text(None), ("", None))

    def test_the_engine_never_sees_the_command(self):
        """THE ARCHITECTURAL PROMISE. Replacing the trigger must not touch the
        engine, so nothing below should_orchestrate/parse_request may mention
        the literal string. Checked against the source, because a reviewer
        adding `if msg.startswith("/fanout")` inside route() is exactly the
        drift this is written to catch."""
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "fanout.py")).read()
        body = src.split("# ────────────────────────────────────────────── cost and capability ───────")[1]
        self.assertNotIn("/fanout", body,
                         "the orchestration engine must not know the trigger string")

    def test_worker_module_does_not_know_the_trigger_either(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "worker.py")).read()
        self.assertNotIn("/fanout", src)


# ═════════════════════════════════════════════════════════ planning ══════

class ParsePlanTest(unittest.TestCase):

    def test_a_clean_array_parses_in_order(self):
        tasks, err = fanout.parse_plan(
            '[{"instruction":"A","capability":"light"},'
            ' {"instruction":"B","capability":"deep"}]')
        self.assertIsNone(err)
        self.assertEqual([t["instruction"] for t in tasks], ["A", "B"])
        self.assertEqual([t["id"] for t in tasks], ["t1", "t2"])
        self.assertEqual(tasks[1]["capability"], "deep")

    def test_a_markdown_fence_is_tolerated(self):
        tasks, err = fanout.parse_plan(
            '```json\n[{"instruction":"A"},{"instruction":"B"}]\n```')
        self.assertIsNone(err)
        self.assertEqual(len(tasks), 2)

    def test_prose_around_the_array_is_tolerated(self):
        """Models ignore "no prose" often enough that failing the whole job
        over a preamble would be the common case, not the edge one."""
        tasks, err = fanout.parse_plan(
            'Sure! Here is the plan:\n[{"instruction":"A"},{"instruction":"B"}]\n'
            'Let me know if you want changes.')
        self.assertIsNone(err)
        self.assertEqual(len(tasks), 2)

    def test_an_object_wrapper_is_unwrapped(self):
        tasks, _ = fanout.parse_plan('{"tasks":[{"instruction":"A"},'
                                     '{"instruction":"B"}]}')
        self.assertEqual(len(tasks), 2)

    def test_bare_strings_are_accepted_as_instructions(self):
        tasks, _ = fanout.parse_plan('["A","B"]')
        self.assertEqual([t["instruction"] for t in tasks], ["A", "B"])
        self.assertEqual(tasks[0]["capability"], fanout.DEFAULT_CAPABILITY)

    def test_invalid_json_is_an_error_not_a_crash(self):
        for junk in ("not json at all", "{oh no", "", "   "):
            tasks, err = fanout.parse_plan(junk)
            self.assertEqual(tasks, [])
            self.assertTrue(err)

    def test_a_non_list_is_refused(self):
        tasks, err = fanout.parse_plan('{"answer": 42}')
        self.assertEqual(tasks, [])
        self.assertIn("not a list", err)

    def test_empty_array_yields_no_tasks(self):
        tasks, err = fanout.parse_plan("[]")
        self.assertEqual(tasks, [])
        self.assertIsNone(err)

    def test_blank_instructions_are_dropped(self):
        tasks, _ = fanout.parse_plan(
            '[{"instruction":"A"},{"instruction":"  "},{"instruction":"B"}]')
        self.assertEqual([t["instruction"] for t in tasks], ["A", "B"])

    def test_an_unknown_capability_falls_back_to_the_default(self):
        tasks, _ = fanout.parse_plan('[{"instruction":"A","capability":"cosmic"}]')
        self.assertEqual(tasks[0]["capability"], fanout.DEFAULT_CAPABILITY)

    def test_a_runaway_plan_is_capped_and_says_so(self):
        big = "[" + ",".join('{"instruction":"t%d"}' % i for i in range(80)) + "]"
        tasks, err = fanout.parse_plan(big)
        self.assertEqual(len(tasks), fanout.MAX_TASKS)
        self.assertIn("were not run", err)


# ═════════════════════════════════════════════════════ cost routing ══════

class BillingModelTest(unittest.TestCase):
    """Cost is DERIVED from how each provider bills, not from a price list.

    These pin the derivation against providers.py's own declarations, so the
    day a catalogue row changes usage_kind the routing follows it instead of
    silently keeping a stale opinion.
    """

    def test_claude_is_a_subscription_because_it_declares_a_window(self):
        self.assertEqual(providers.usage_kind_for("claude"), "window-percent")
        self.assertEqual(fanout.billing_model("claude"), "subscription")

    def test_deepseek_is_metered_because_it_declares_a_balance(self):
        self.assertEqual(providers.usage_kind_for("deepseek"), "balance")
        self.assertEqual(fanout.billing_model("deepseek"), "metered")

    def test_codex_follows_its_credential(self):
        """The one provider that must be ASKED: the two logins bill
        differently, so a lookup table would be wrong half the time."""
        import providers as P
        orig = P.codex_auth
        try:
            P.codex_auth = lambda: {"state": "chatgpt"}
            self.assertEqual(fanout.billing_model("codex"), "subscription")
            P.codex_auth = lambda: {"state": "api_key"}
            self.assertEqual(fanout.billing_model("codex"), "metered")
            P.codex_auth = lambda: {"state": "logged_out"}
            self.assertEqual(fanout.billing_model("codex"), "unknown")
        finally:
            P.codex_auth = orig

    def test_a_codex_probe_failure_is_unknown_not_a_guess(self):
        import providers as P
        orig = P.codex_auth
        try:
            def boom():
                raise RuntimeError("probe died")
            P.codex_auth = boom
            self.assertEqual(fanout.billing_model("codex"), "unknown")
        finally:
            P.codex_auth = orig

    def test_subscription_is_cheaper_than_metered(self):
        """THE correction. The first version of this file had it backwards:
        it ranked DeepSeek cheapest on public list price, when DeepSeek is the
        only provider here that spends the operator's actual money."""
        self.assertEqual(fanout.BILLING_COST["subscription"], "low")
        self.assertEqual(fanout.BILLING_COST["metered"], "high")

    def test_unknown_billing_is_never_preferred(self):
        self.assertEqual(fanout.BILLING_COST["unknown"], "high")

    def test_cost_map_resolves_once_for_a_whole_run(self):
        """billing_model("codex") shells out; per-task resolution would add a
        subprocess to every routing decision."""
        import providers as P
        orig, calls = P.codex_auth, []
        try:
            def counted():
                calls.append(1)
                return {"state": "chatgpt"}
            P.codex_auth = counted
            m = fanout.cost_map(["claude", "codex", "deepseek"])
            self.assertEqual(len(calls), 1)
            for _ in range(10):
                fanout.provider_cost("codex", m)
            self.assertEqual(len(calls), 1, "the map was not reused")
        finally:
            P.codex_auth = orig


class RoutingTest(unittest.TestCase):
    """Routing is asserted against EXPLICIT billing scenarios rather than this
    machine's credentials, so the same test means the same thing anywhere.

    THE RULE UNDER TEST (2026-09-10): among runnable providers whose
    capability clears the task, pick the LEAST LOADED; break ties by cost,
    then catalogue order. Capability is still a hard gate -- load never
    promotes a provider that cannot do the work.
    """

    ALL = ["claude", "codex", "deepseek"]

    #: The shipped setup: Claude Max, Codex on a ChatGPT plan, DeepSeek on
    #: pay-as-you-go credit. This is the configuration measured on the
    #: founder's machine 2026-09-10.
    SUBS = {"claude": "subscription", "codex": "subscription",
            "deepseek": "metered"}
    #: The same machine after `codex login` with an API key.
    API = {"claude": "subscription", "codex": "metered", "deepseek": "metered"}

    @staticmethod
    def _spread(levels, eligible, models):
        tasks = [{"instruction": "t%d" % i, "capability": lv}
                 for i, lv in enumerate(levels)]
        got = {}
        for t in fanout.route(tasks, eligible, models):
            got[t["provider"]] = got.get(t["provider"], 0) + 1
        return got

    # ---- 4. capability is still a hard gate ------------------------------

    def test_capability_is_a_hard_gate_load_never_overrides_it(self):
        """THE regression this must never develop: balancing must not promote
        a provider that cannot do the work."""
        self.assertEqual(self._spread(["deep"] * 6, self.ALL, self.SUBS),
                         {"claude": 6})
        for t in fanout.route([{"instruction": "x", "capability": "deep"}] * 6,
                              self.ALL, self.SUBS):
            self.assertEqual(t["provider"], "claude")

    def test_a_standard_task_never_reaches_the_light_provider(self):
        got = self._spread(["standard"] * 8, self.ALL, self.SUBS)
        self.assertNotIn("deepseek", got)

    def test_suitable_providers_is_the_capability_answer(self):
        self.assertEqual(set(fanout.suitable_providers("light", self.ALL)[0]),
                         {"claude", "codex", "deepseek"})
        self.assertEqual(set(fanout.suitable_providers("standard", self.ALL)[0]),
                         {"claude", "codex"})
        self.assertEqual(fanout.suitable_providers("deep", self.ALL)[0],
                         ["claude"])

    # ---- 5. unavailable providers are excluded ---------------------------

    def test_an_unavailable_provider_never_receives_work(self):
        got = self._spread(["light"] * 9, ["claude", "codex"], self.SUBS)
        self.assertNotIn("deepseek", got)
        self.assertEqual(sum(got.values()), 9)

    def test_no_runnable_provider_returns_none(self):
        self.assertEqual(fanout.choose_provider("light", [], self.SUBS)[0], None)

    def test_eligibility_excludes_a_provider_with_no_adapter(self):
        self.assertNotIn("gemini", fanout.eligible_providers())

    # ---- 6/7/8. several suitable providers actually share the work -------

    def test_six_light_tasks_spread_across_every_suitable_provider(self):
        """6 and 7 together: work is shared, and Claude is not the answer to
        everything."""
        got = self._spread(["light"] * 6, self.ALL, self.SUBS)
        self.assertEqual(got, {"claude": 2, "codex": 2, "deepseek": 2})

    def test_deepseek_wins_routing_when_it_is_runnable_and_suitable(self):
        """8. It was previously UNREACHABLE -- cost led the key, DeepSeek was
        the only metered provider, and Claude was suitable for everything, so
        it lost even the light sub-tasks it was the exact match for."""
        got = self._spread(["light"] * 6, self.ALL, self.SUBS)
        self.assertIn("deepseek", got)
        self.assertGreater(got["deepseek"], 0)

    def test_selection_does_not_always_choose_claude(self):
        """7, stated as its own assertion because it is the observed
        symptom: six sub-tasks, six Claude workers."""
        got = self._spread(["light"] * 3 + ["standard"] * 3, self.ALL, self.SUBS)
        self.assertLess(got.get("claude", 0), 6)
        self.assertGreaterEqual(len(got), 2, "work stacked on one provider")

    def test_a_mixed_job_uses_every_provider_it_can(self):
        got = self._spread(["light"] * 3 + ["standard"] * 2 + ["deep"],
                           self.ALL, self.SUBS)
        self.assertEqual(sum(got.values()), 6)
        self.assertEqual(set(got), {"claude", "codex", "deepseek"})

    def test_the_spread_is_balanced_not_merely_nonzero(self):
        """Balanced, not token diversity: 9 light tasks over 3 providers is
        3/3/3, never 7/1/1."""
        got = self._spread(["light"] * 9, self.ALL, self.SUBS)
        self.assertEqual(got, {"claude": 3, "codex": 3, "deepseek": 3})

    # ---- 9. fallback when DeepSeek is gone -------------------------------

    def test_routing_falls_back_cleanly_when_deepseek_is_unavailable(self):
        got = self._spread(["light"] * 6, ["claude", "codex"], self.SUBS)
        self.assertEqual(got, {"claude": 3, "codex": 3})

    def test_only_one_provider_runnable_means_it_gets_everything(self):
        for level in fanout.CAPABILITY_ORDER:
            self.assertEqual(self._spread([level] * 5, ["claude"], self.SUBS),
                             {"claude": 5})

    def test_nothing_capable_enough_uses_the_best_available_and_says_so(self):
        pid, note = fanout.choose_provider("deep", ["deepseek"], self.SUBS)
        self.assertEqual(pid, "deepseek")
        self.assertIn("most capable", note)

    # ---- cost is a tie-break, not a gate ---------------------------------

    def test_cost_decides_between_equally_idle_equally_suitable_providers(self):
        """One task, nothing assigned yet: load ties, so cost is consulted.
        DeepSeek is metered, so it does not take the first light task."""
        self.assertNotEqual(
            fanout.choose_provider("light", self.ALL, self.SUBS)[0], "deepseek")

    def test_the_cost_override_still_steers_the_tie_break(self):
        self.assertNotEqual(
            fanout.choose_provider("light", self.ALL, self.SUBS)[0], "deepseek")
        os.environ[fanout.COST_ENV] = "deepseek=low,claude=high,codex=high"
        try:
            self.assertEqual(
                fanout.choose_provider("light", self.ALL, self.SUBS)[0],
                "deepseek")
        finally:
            del os.environ[fanout.COST_ENV]

    def test_a_junk_override_is_ignored_not_obeyed(self):
        os.environ[fanout.COST_ENV] = "claude=free,,garbage,deepseek"
        try:
            self.assertEqual(fanout.provider_cost("claude", self.SUBS), "low")
            self.assertEqual(fanout.provider_cost("deepseek", self.SUBS), "high")
        finally:
            del os.environ[fanout.COST_ENV]

    def test_an_unknown_provider_is_treated_as_expensive(self):
        self.assertEqual(fanout.provider_cost("nope", {}), "high")
        self.assertEqual(fanout.provider_capability("nope"), "light")

    def test_signing_codex_into_an_api_key_still_moves_the_tie_break(self):
        """The billing derivation is live, and still observable at equal
        load: with codex metered, the first light task goes to claude."""
        self.assertEqual(
            fanout.choose_provider("light", self.ALL, self.API)[0], "claude")

    # ---- determinism -----------------------------------------------------

    def test_routing_is_deterministic(self):
        levels = ["light"] * 4 + ["standard"] * 3 + ["deep"]
        tasks = [{"instruction": "t%d" % i, "capability": lv}
                 for i, lv in enumerate(levels)]
        a = [t["provider"] for t in fanout.route(tasks, self.ALL, self.SUBS)]
        b = [t["provider"] for t in fanout.route(tasks, self.ALL, self.SUBS)]
        self.assertEqual(a, b, "the same plan routed two different ways")

    def test_a_planner_named_provider_is_still_ignored(self):
        """The planner never gets the vendor decision -- that is the one route
        by which a model could reintroduce arbitrary assignment."""
        routed = fanout.route(
            [{"instruction": "x", "capability": "deep", "provider": "deepseek"}],
            self.ALL, self.SUBS)
        self.assertEqual(routed[0]["provider"], "claude")

    def test_parse_plan_drops_a_provider_field(self):
        tasks, _ = fanout.parse_plan(
            '[{"instruction":"A","capability":"light","provider":"claude"}]')
        self.assertNotIn("provider", tasks[0])

    def test_route_initialises_every_task_field(self):
        routed = fanout.route([{"instruction": "x"}], self.ALL, self.SUBS)
        self.assertEqual(routed[0]["status"], "pending")
        self.assertIsNone(routed[0]["result"])
        self.assertIsNone(routed[0]["error"])
        self.assertTrue(routed[0]["id"])


class RoutingTableTest(unittest.TestCase):
    """The tables must cover what the panel can actually drive -- the same
    pinning test_budget applies to its window table."""

    def test_every_drivable_adapter_has_a_capability_and_a_billing_model(self):
        """codex_auth is stubbed here DELIBERATELY. Unstubbed, billing_model
        ("codex") runs `codex login status` against whatever real CLI is on
        the machine -- a unit test must not shell out to the operator's own
        tooling, and the answer would vary with who is signed in."""
        import providers as P
        import worker
        orig = P.codex_auth
        try:
            P.codex_auth = lambda: {"state": "chatgpt"}
            for pid in worker.DRIVABLE:
                self.assertIn(pid, fanout.PROVIDER_CAPABILITY, pid)
                self.assertIn(fanout.PROVIDER_CAPABILITY[pid],
                              fanout.CAPABILITY_ORDER)
                self.assertIn(fanout.billing_model(pid),
                              ("subscription", "metered", "unknown"), pid)
                self.assertIn(fanout.provider_cost(pid), fanout.COST_ORDER, pid)
        finally:
            P.codex_auth = orig

    def test_drivable_is_a_subset_of_the_catalogue_adapters(self):
        import worker
        self.assertTrue(set(worker.DRIVABLE) <= set(providers.ADAPTERS))

    def test_gemini_is_not_routable(self):
        """It has no adapter, so it must never appear as a worker target."""
        import worker
        self.assertNotIn("gemini", worker.DRIVABLE)
        self.assertNotIn("gemini", fanout.PROVIDER_CAPABILITY)
        self.assertNotIn("gemini", fanout.eligible_providers())


class EligibleProvidersTest(unittest.TestCase):

    def test_eligibility_is_runnable_and_drivable_only(self):
        """No second opinion about readiness -- it reads the one flag."""
        import worker
        got = fanout.eligible_providers()
        runnable = {p["id"] for p in providers.runnable_providers()}
        for pid in got:
            self.assertIn(pid, runnable)
            self.assertIn(pid, worker.DRIVABLE)


# ════════════════════════════════════════════════════════ execution ══════

class ExecuteTest(unittest.TestCase):

    def _tasks(self, n, level="light"):
        return fanout.route(
            [{"instruction": "task %d" % i, "capability": level}
             for i in range(n)],
            ["claude", "codex", "deepseek"])

    def test_results_keep_task_order_not_completion_order(self):
        """Completion order is deliberately reversed by the delay, so a
        results list built from as-completed would come back backwards."""
        tasks = self._tasks(5)

        async def runner(pid, prompt, workdir, perm_mode, orch):
            n = int(prompt.split()[-1]) if prompt.split()[-1].isdigit() else 0
            await asyncio.sleep(0.02 * (5 - n))
            return {"ok": True, "text": "R%d" % n, "error": None, "provider": pid}

        out = _run(fanout.execute(tasks, runner, "/tmp", "plan"))
        self.assertEqual([t["result"] for t in out],
                         ["R0", "R1", "R2", "R3", "R4"])
        self.assertEqual([t["index"] for t in out], [0, 1, 2, 3, 4])

    def test_the_v1_concurrency_ceiling_is_five(self):
        self.assertEqual(fanout.MAX_CONCURRENT_WORKERS, 5)
        self.assertEqual(fanout.DEFAULT_LIMIT, fanout.MAX_CONCURRENT_WORKERS)

    def test_exactly_five_workers_overlap(self):
        """PEAK IN FLIGHT, not completions. Counting finishes proves nothing
        about overlap -- five sequential workers and five simultaneous ones
        both complete five times."""
        tasks = self._tasks(12)
        r = FakeRunner(delay=0.03)
        out = _run(fanout.execute(tasks, r, "/tmp", "plan"))
        self.assertEqual(len(out), 12)
        self.assertLessEqual(r.peak, 5, "the concurrency ceiling was exceeded")
        self.assertEqual(r.peak, 5, "five workers did not genuinely overlap")

    def test_a_sixth_task_waits_for_a_slot(self):
        """Six tasks, five slots: the sixth must not start until one of the
        first five has finished -- and it must still run."""
        tasks = self._tasks(6)
        events = []

        async def runner(pid, prompt, workdir, perm_mode, orch):
            events.append(("start", prompt))
            await asyncio.sleep(0.05)
            events.append(("end", prompt))
            return {"ok": True, "text": "x", "error": None, "provider": pid}

        out = _run(fanout.execute(tasks, runner, "/tmp", "plan"))
        self.assertEqual(len(out), 6)
        self.assertTrue(all(t["status"] == "done" for t in out),
                        "the queued task never ran")
        starts = [i for i, e in enumerate(events) if e[0] == "start"]
        first_end = next(i for i, e in enumerate(events) if e[0] == "end")
        self.assertEqual(len([i for i in starts if i < first_end]), 5,
                         "more or fewer than five started before any finished")
        self.assertTrue(starts[5] > first_end,
                        "the sixth task started before a slot freed")

    def test_concurrency_is_never_unbounded(self):
        """Twenty tasks must still peak at five."""
        r = FakeRunner(delay=0.02)
        _run(fanout.execute(self._tasks(20), r, "/tmp", "plan"))
        self.assertEqual(r.peak, 5)

    def test_the_limit_is_configurable_and_still_bounded(self):
        tasks = self._tasks(6)
        r = FakeRunner(delay=0.02)
        _run(fanout.execute(tasks, r, "/tmp", "plan",
                            orch=fanout.Orchestration(limit=2)))
        self.assertEqual(r.peak, 2)

    def test_cancellation_still_kills_workers_at_the_higher_limit(self):
        """Raising the ceiling must not leave more children unreachable."""
        class FakeRt:
            def __init__(self):
                self.killed = 0

            def kill_group(self):
                self.killed += 1

        orch = fanout.Orchestration()
        rts = [FakeRt() for _ in range(5)]
        for rt in rts:
            orch.add(rt)
        orch.cancel()
        self.assertTrue(all(rt.killed >= 1 for rt in rts))
        self.assertEqual(orch.live, set())

    def test_one_failure_does_not_stop_the_others(self):
        tasks = self._tasks(5)
        r = FakeRunner(fail_on=["task 2"])
        out = _run(fanout.execute(tasks, r, "/tmp", "plan"))
        self.assertEqual([t["status"] for t in out],
                         ["done", "done", "failed", "done", "done"])
        self.assertEqual(out[2]["error"], "worker died")
        self.assertTrue(all(t["result"] for t in out if t["status"] == "done"))

    def test_several_failures_leave_the_successes_intact(self):
        tasks = self._tasks(6)
        r = FakeRunner(fail_on=["task 0", "task 3", "task 5"])
        out = _run(fanout.execute(tasks, r, "/tmp", "plan"))
        self.assertEqual([t["status"] for t in out],
                         ["failed", "done", "done", "failed", "done", "failed"])

    def test_a_raising_worker_is_contained(self):
        """return_exceptions=True is what keeps one bad coroutine from
        cancelling the gather and taking the rest with it."""
        tasks = self._tasks(4)
        calls = []

        async def runner(pid, prompt, workdir, perm_mode, orch):
            calls.append(prompt)
            if "task 1" in prompt:
                raise RuntimeError("boom")
            return {"ok": True, "text": "fine", "error": None, "provider": pid}

        out = _run(fanout.execute(tasks, runner, "/tmp", "plan"))
        self.assertEqual(len(calls), 4, "the other workers must still have run")
        self.assertEqual(out[1]["status"], "failed")
        self.assertEqual([t["status"] for t in out],
                         ["done", "failed", "done", "done"])

    def test_partial_text_from_a_failed_worker_is_kept(self):
        tasks = self._tasks(1)

        async def runner(pid, prompt, workdir, perm_mode, orch):
            return {"ok": False, "text": "half an answer",
                    "error": "rate limited", "provider": pid}

        out = _run(fanout.execute(tasks, runner, "/tmp", "plan"))
        self.assertEqual(out[0]["status"], "failed")
        self.assertEqual(out[0]["result"], "half an answer")

    def test_progress_rides_existing_tool_frames_only(self):
        tasks = self._tasks(3)
        frames = []

        async def emit(f):
            frames.append(f)

        _run(fanout.execute(tasks, FakeRunner(), "/tmp", "plan", emit=emit))
        self.assertTrue(frames)
        self.assertEqual({f["type"] for f in frames}, {"tool"},
                         "no new frame type may be introduced")
        starts = [f for f in frames if f["phase"] == "start"]
        ends = [f for f in frames if f["phase"] == "end"]
        self.assertEqual(len(starts), 3)
        self.assertEqual(len(ends), 3)
        # id pairs a start with its end -- the only thing the client can
        # correlate on (01-state.js keys toolRuns by it)
        self.assertEqual({f["id"] for f in starts}, {f["id"] for f in ends})
        for f in starts:
            self.assertTrue(f["name"])
            self.assertIn("Sub-task", f["summary"])
        for f in ends:
            self.assertIn("ok", f)

    def test_a_dead_emit_does_not_fail_the_job(self):
        async def emit(f):
            raise RuntimeError("socket gone")

        out = _run(fanout.execute(self._tasks(2), FakeRunner(), "/tmp", "plan",
                                  emit=emit))
        self.assertEqual([t["status"] for t in out], ["done", "done"])


# ═════════════════════════════════════════════════════ cancellation ══════

class CancellationTest(unittest.TestCase):

    class FakeRt:
        def __init__(self):
            self.killed = 0

        def kill_group(self):
            self.killed += 1

    def test_cancel_kills_every_live_runtime(self):
        orch = fanout.Orchestration()
        rts = [self.FakeRt() for _ in range(3)]
        for rt in rts:
            orch.add(rt)
        orch.cancel()
        self.assertTrue(all(rt.killed >= 1 for rt in rts))
        self.assertEqual(orch.live, set())
        self.assertTrue(orch.cancelled)

    def test_cancel_is_idempotent(self):
        orch = fanout.Orchestration()
        orch.cancel()
        orch.cancel()          # must not raise on an empty set
        self.assertTrue(orch.cancelled)

    def test_a_runtime_registered_after_a_cancel_is_killed_immediately(self):
        """The race: cancel() sweeps, then an in-flight spawn lands. Without
        this the one child that raced the sweep outlives the stop."""
        orch = fanout.Orchestration()
        orch.cancel()
        rt = self.FakeRt()
        orch.add(rt)
        self.assertEqual(rt.killed, 1)

    def test_done_untracks_so_a_later_cancel_does_not_rekill(self):
        orch = fanout.Orchestration()
        rt = self.FakeRt()
        orch.add(rt)
        orch.done(rt)
        orch.cancel()
        self.assertEqual(rt.killed, 0)

    def test_cancelling_mid_flight_stops_the_remaining_workers(self):
        tasks = fanout.route([{"instruction": "t%d" % i, "capability": "light"}
                              for i in range(9)], ["deepseek"])
        orch = fanout.Orchestration()
        started = []

        async def runner(pid, prompt, workdir, perm_mode, orch_):
            started.append(prompt)
            if len(started) == 2:
                orch_.cancel()
            await asyncio.sleep(0.01)
            return {"ok": True, "text": "x", "error": None, "provider": pid}

        out = _run(fanout.execute(tasks, runner, "/tmp", "plan", orch=orch))
        self.assertLess(len(started), 9,
                        "workers kept starting after the cancel")
        self.assertTrue(any(t["status"] == "cancelled" for t in out))
        self.assertEqual(len(out), 9, "every task must still be accounted for")

    def test_no_task_is_left_pending_or_running(self):
        """A row still marked running after execute() returns would be
        presented to the synthesis as though a result might arrive."""
        tasks = fanout.route([{"instruction": "t%d" % i} for i in range(4)],
                             ["deepseek"])
        orch = fanout.Orchestration()
        orch.cancel()
        out = _run(fanout.execute(tasks, FakeRunner(), "/tmp", "plan", orch=orch))
        self.assertEqual({t["status"] for t in out}, {"cancelled"})
        self.assertTrue(all(t["error"] for t in out))


# ════════════════════════════════════════════════════════ run() ══════════

class RunTest(unittest.TestCase):

    JOB = "Research six competitors and compare pricing"

    SUBS = {"claude": "subscription", "codex": "subscription",
            "deepseek": "metered"}

    def test_the_happy_path_plans_routes_runs_and_reports(self):
        r = FakeRunner(plan_text=_plan_json("light", "light", "deep"))
        with _Eligible(["claude", "codex", "deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["tasks"]), 3)
        # light -> claude then codex (least loaded each time), deep -> claude
        self.assertEqual(out["counts"], {"claude": 2, "codex": 1})
        self.assertEqual(r.planner_calls, 1)
        self.assertEqual(r.worker_pids(), ["claude", "codex", "claude"])

    def test_the_metered_provider_is_used_when_it_is_the_only_one(self):
        r = FakeRunner(plan_text=_plan_json("light", "light"))
        with _Eligible(["deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "deepseek", "/tmp", "plan", runner=r))
        self.assertTrue(out["ok"])
        self.assertEqual(out["counts"], {"deepseek": 2})

    def test_the_planner_runs_on_the_parent_provider(self):
        """Not on the cheapest one. The parent owns planning and synthesis."""
        r = FakeRunner(plan_text=_plan_json("light", "light"))
        with _Eligible(["claude", "codex", "deepseek"]), _Billing(self.SUBS):
            _run(fanout.run(self.JOB, "codex", "/tmp", "plan", runner=r))
        plan_calls = [c for c in r.calls if c["plan"]]
        self.assertEqual(len(plan_calls), 1)
        self.assertEqual(plan_calls[0]["pid"], "codex")

    def test_the_planner_is_asked_for_capability_not_for_a_provider(self):
        prompt = fanout.planner_prompt(self.JOB)
        self.assertIn("capability", prompt)
        self.assertIn(self.JOB, prompt)
        for pid in ("claude", "codex", "deepseek"):
            self.assertNotIn(pid, prompt.lower(),
                             "naming providers invites the planner to balance them")

    def test_planner_failure_falls_back_without_running_workers(self):
        r = FakeRunner(plan_ok=False)
        with _Eligible(["claude", "deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "planner-failed")
        self.assertEqual(r.worker_pids(), [])

    def test_invalid_planner_output_falls_back(self):
        r = FakeRunner(plan_text="I'm not going to do that")
        with _Eligible(["claude", "deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no-tasks")
        self.assertEqual(r.worker_pids(), [])

    def test_an_empty_plan_falls_back(self):
        r = FakeRunner(plan_text="[]")
        with _Eligible(["claude", "deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no-tasks")

    def test_a_single_subtask_is_not_worth_fanning_out(self):
        r = FakeRunner(plan_text=_plan_json("light"))
        with _Eligible(["claude", "deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "not-worth-it")
        self.assertEqual(r.worker_pids(), [], "no worker should have spawned")

    def test_all_workers_failing_is_reported_not_fabricated(self):
        r = FakeRunner(plan_text=_plan_json("light", "light"),
                       fail_on=["do thing"])
        with _Eligible(["deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "all-failed")

    def test_partial_success_still_synthesises(self):
        r = FakeRunner(plan_text=_plan_json("light", "light", "light"),
                       fail_on=["do thing 2"])
        with _Eligible(["deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertTrue(out["ok"])
        self.assertEqual([t["status"] for t in out["tasks"]],
                         ["done", "failed", "done"])

    def test_no_runnable_provider_is_refused_before_anything_spawns(self):
        r = FakeRunner(plan_text=_plan_json("light", "light"))
        with _Eligible([]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan", runner=r))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "no-providers")
        self.assertEqual(r.calls, [])

    def test_cancel_during_planning_stops_before_any_worker(self):
        orch = fanout.Orchestration()

        async def runner(pid, prompt, workdir, perm_mode, orch_):
            orch_.cancel()
            return {"ok": True, "text": _plan_json("light", "light"),
                    "error": None, "provider": pid}

        with _Eligible(["deepseek"]), _Billing(self.SUBS):
            out = _run(fanout.run(self.JOB, "claude", "/tmp", "plan",
                                  runner=runner, orch=orch))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "cancelled")
        self.assertEqual(out["tasks"], [])


# ════════════════════════════════════════════════════════ synthesis ══════

class SynthesisTest(unittest.TestCase):

    def _done(self):
        tasks = fanout.route([{"instruction": "A", "capability": "light"},
                              {"instruction": "B", "capability": "light"}],
                             ["deepseek"])
        for i, t in enumerate(tasks):
            t["index"] = i
            t["status"] = "done"
            t["result"] = "answer %s" % t["instruction"]
        return tasks

    def test_the_block_carries_the_job_and_every_result_in_order(self):
        block = fanout.results_block("THE JOB", self._done())
        self.assertIn("THE JOB", block)
        self.assertLess(block.index("answer A"), block.index("answer B"))
        self.assertIn("2 succeeded", block)

    def test_failures_are_stated_not_hidden(self):
        tasks = self._done()
        tasks[1]["status"] = "failed"
        tasks[1]["result"] = None
        tasks[1]["error"] = "deepseek timed out"
        block = fanout.results_block("THE JOB", tasks)
        self.assertIn("NOT COMPLETED", block)
        self.assertIn("deepseek timed out", block)
        self.assertIn("1 succeeded, 1 did not", block)
        self.assertIn("say plainly what is missing", block)

    def test_compose_appends_and_does_not_replace(self):
        """It must survive a provider-switch replay already sitting in `msg`."""
        base = "<<<A SWITCH REPLAY PAYLOAD>>>"
        out = fanout.compose(base, "THE JOB", self._done())
        self.assertTrue(out.startswith(base))
        self.assertIn("answer A", out)

    def test_the_synthesis_asks_for_one_answer_not_a_process_report(self):
        out = fanout.compose("x", "THE JOB", self._done())
        self.assertIn("ONE coherent answer", out)
        self.assertIn("Do not describe the sub-tasks", out)


# ═══════════════════════════════════════════════════════ regression ══════

class NoSideEffectsTest(unittest.TestCase):
    """The engine must be incapable of the four mutations it is forbidden."""

    #: Names whose APPEARANCE IN EXECUTABLE CODE would mean this feature can
    #: mutate something it promised not to. Prose is exempt on purpose -- both
    #: modules discuss switch.plan and append_turn at length in order to
    #: explain why they do not call them, and a grep-based version of this test
    #: failed on its own documentation.
    FORBIDDEN_CALLS = ("save_settings", "begin_segment", "append_turn",
                       "confirm", "plan", "register_runtime",
                       "unregister_runtime")
    FORBIDDEN_IMPORTS = ("chat_store", "switch", "switch_egress", "replay",
                         "transcript_ir", "org_api")

    def _names_used(self, path):
        """Every attribute and bare name in the module's real CODE.

        AST rather than substring search: docstrings and comments are where
        these modules EXPLAIN the prohibition, so a text scan flags the
        explanation and passes the violation the day someone writes
        `getattr(switch, "plan")`. Parsing is the only version that reads code
        as code.
        """
        import ast
        tree = ast.parse(open(path).read())
        attrs, imports = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attrs.add(node.attr)
            elif isinstance(node, ast.Name):
                attrs.add(node.id)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        return attrs, imports

    def test_the_modules_never_call_the_forbidden_machinery(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("fanout.py", "worker.py"):
            attrs, imports = self._names_used(os.path.join(here, name))
            for bad in self.FORBIDDEN_IMPORTS:
                self.assertNotIn(bad, imports,
                                 "%s must not import %s" % (name, bad))
            for bad in self.FORBIDDEN_CALLS:
                if bad in ("plan", "confirm") and name == "fanout.py":
                    # fanout defines its own planner_prompt/parse_plan; the
                    # import guard above is what proves switch.plan is
                    # unreachable, since `switch` is never imported.
                    continue
                self.assertNotIn(bad, attrs,
                                 "%s must not call %s" % (name, bad))

    def test_chat_store_is_not_imported_at_all(self):
        import worker
        self.assertFalse(hasattr(fanout, "chat_store"))
        self.assertFalse(hasattr(worker, "chat_store"))

    def test_switch_is_not_imported_at_all(self):
        import worker
        self.assertFalse(hasattr(fanout, "switch"))
        self.assertFalse(hasattr(worker, "switch"))


class BuildAgentArgsTest(unittest.TestCase):
    """The one existing function this feature modified."""

    def test_default_is_unchanged(self):
        """mcp defaults to True, so every existing caller builds the same argv
        it always did. If this fails, normal chat has changed."""
        import app
        explicit = app.build_agent_args("/bin/claude", "hi", "plan",
                                        stream_input=True, mcp=True)
        default = app.build_agent_args("/bin/claude", "hi", "plan",
                                       stream_input=True)
        self.assertEqual(explicit, default)

    def test_mcp_false_drops_the_sutra_server_and_its_allowlist(self):
        import app
        on = app.build_agent_args("/bin/claude", "hi", "plan", stream_input=True)
        off = app.build_agent_args("/bin/claude", "hi", "plan",
                                   stream_input=True, mcp=False)
        self.assertNotIn("--mcp-config", off)
        self.assertNotIn("--strict-mcp-config", off)
        self.assertNotIn("mcp__sutra__*", off)
        if "--mcp-config" in on:
            self.assertLess(len(off), len(on))

    def test_mcp_false_changes_nothing_else(self):
        import app
        off = app.build_agent_args("/bin/claude", "hi", "acceptEdits",
                                   model="opus", stream_input=True, mcp=False)
        self.assertEqual(off[:2], ["/bin/claude", "-p"])
        self.assertIn("--input-format", off)
        self.assertIn("--permission-mode", off)
        self.assertIn("acceptEdits", off)
        self.assertIn("--model", off)
        self.assertIn("opus", off)


if __name__ == "__main__":
    unittest.main()
