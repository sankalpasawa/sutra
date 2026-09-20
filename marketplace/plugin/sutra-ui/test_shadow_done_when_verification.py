#!/usr/bin/env python3
"""WHO WROTE A DONE WHEN IS IRRELEVANT TO HOW IT IS VERIFIED.

THE FAILURE THIS CLOSES (founder, 2026-09-17; mission m-c973ff4adef0).
The founder typed one condition into the Delegate form:

    "The file shadow-manual-test.txt exists and contains exactly
     shadow-manual-pass."

The worker created that file, 18 bytes, exactly right, no trailing newline.
Shadow showed NEEDS YOU and asked the founder to confirm it -- over a file it
could have opened in a microsecond. Not because the check was subjective, and
not because verification was broken: `_criteria_before_first_contact` returned
early the moment the founder had supplied anything, so a founder-typed
condition could never acquire a probe no matter how mechanical it was.

`founder_confirm` was doing two jobs at once -- "the founder wrote this" and
"founder judgment is required" -- and the first meaning was silently deciding
the second.

Now there is ONE verification pass and it runs over whatever Done When exists.
It has no way to learn who authored a row, because there is no such field.
Test D is the proof: the identical file condition, written by Shadow instead
of the founder, is verified identically.

Run: marketplace/plugin/sutra-ui/run-tests.sh test_shadow_done_when_verification.py
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient      # noqa: E402

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import providers                               # noqa: E402
import shadow_probe                            # noqa: E402
import shadow_runner                           # noqa: E402
from mission_engine import MissionEngine, MissionStore   # noqa: E402

MIS = "/api/shadow/missions"

#: THE FOUNDER'S EXACT WORDING, from the live mission. Every assertion about
#: preservation compares against this constant, so a test cannot drift into
#: agreeing with a rewrite.
FOUNDER_CHECK = ("The file shadow-manual-test.txt exists and contains "
                 "exactly shadow-manual-pass.")
OBJECTIVE = "Create shadow-manual-test.txt containing exactly shadow-manual-pass."

#: What a decider that can read the condition would answer: HOW, by index.
PROBE = {"kind": "file_equals", "path": "shadow-manual-test.txt",
         "text": "shadow-manual-pass", "allow_trailing_newline": True}

#: A condition no file settles. Shadow must leave it alone.
SUBJECTIVE_CHECK = ("The README reads well and explains Shadow to someone "
                    "who has never seen it.")

CLAIM = ("I created the file with the required contents.\n"
         "DONE-CHECK: " + FOUNDER_CHECK + "\nThe task is complete.")


class Base(unittest.TestCase):
    """A real app, a real store, a real workdir, a scripted decider."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "workdir")
        os.makedirs(self.root)
        os.environ["SUTRA_SHADOW_HOME"] = self.tmp.name
        self._orig = providers.SETTINGS_PATH
        p = Path(self.tmp.name) / "settings.json"
        p.write_text(json.dumps({"shadow.enabled": True,
                                 "workdir": self.root}))
        providers.SETTINGS_PATH = p
        self.store = MissionStore()
        self._real_launch = shadow_runner._launch
        shadow_runner._launch = lambda mid, *a, **k: None
        self.asked = []          # every context the decider was handed

    def tearDown(self):
        shadow_runner._launch = self._real_launch
        providers.SETTINGS_PATH = self._orig
        os.environ.pop("SUTRA_SHADOW_HOME", None)
        self.tmp.cleanup()

    # ---- the REAL creation path ------------------------------------------

    def ui_create(self, done_when_lines):
        """EXACTLY what the Delegate form posts.

        static/js/16-shadow-home.js splits the founder's "done when" textarea
        on newlines and maps each line to {tier: "founder_confirm", check},
        then composes the manifest from the objective and those lines. This
        reproduces that payload byte for byte -- it is the path the
        programmatic probe tests never exercised, which is why they missed
        the bug this file exists for.
        """
        done_when = [{"tier": "founder_confirm", "check": c}
                     for c in done_when_lines]
        body = {
            "objective": OBJECTIVE, "template": "fix", "target_mode": "new",
            "done_when": done_when,
            "manifest": ("You are a delegate session working for the founder "
                         "via Shadow. Objective: " + OBJECTIVE
                         + (" It is done when: "
                            + "; ".join(c["check"] for c in done_when) + "."
                            if done_when else "")
                         + " Work step by step; say what you did and what is "
                           "left."),
        }
        r = self.client.post(MIS, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    # ---- deciders ---------------------------------------------------------

    def decider(self, verification=None, done_when=None):
        """Records what it was asked; answers what the test scripts."""
        async def fn(ctx):
            self.asked.append(ctx)
            out = {"action": "continue",
                   # VARIED ON PURPOSE: the ping-pong guard stops a mission
                   # that says the same thing twice, which would end these
                   # runs for a reason that has nothing to do with the probe.
                   "instruction": "carry on (%d)" % len(self.asked),
                   "reason": "r"}
            if verification is not None:
                out["verification"] = verification
            if done_when is not None:
                out["done_when"] = done_when
            return out
        return fn

    def engine(self, decider=None, transcript=CLAIM, on_say=None):
        self.says = []

        async def sayer(mission, text):
            self.says.append(text)
            if on_say is not None:
                on_say(len(self.says))
            return True

        async def waiter(mission):
            return True

        return MissionEngine(self.store, sayer, waiter,
                             lambda m: transcript, app_module._shadow_verifier,
                             decider=decider, probe_root=self.root)

    def provision(self, mid, decider, writes=None):
        """The real first-contact path: criteria, then verification, then the
        brief. The spawner records the record as the worker would see it.

        `writes` IS THE WORKER ACTING ON THE BRIEF. The spawn delivers the
        manifest and waits out a turn, so a worker that does the job
        immediately has done it before the loop evaluates anything -- which
        is exactly what happened on m-c973ff4adef0, and why that mission read
        turns_used=1.
        """
        self.at_spawn = []

        async def spawner(m):
            self.at_spawn.append(
                list(self.store.load(m["id"]).get("done_when") or []))
            if writes is not None:
                self.write(writes)
            return "sess-live"

        eng = self.engine(decider=decider)
        asyncio.new_event_loop().run_until_complete(
            eng.provision_target(mid, spawner))
        return self.store.load(mid)

    def run_to_end(self, mid, decider=None, transcript=CLAIM, on_say=None,
                   max_turns=3):
        m = self.store.load(mid)
        m["max_turns"] = max_turns
        self.store.save(m)
        if m["state"] == "brief_confirm":
            self.store.transition(mid, "running", "test")
        eng = self.engine(decider=decider, transcript=transcript,
                          on_say=on_say)
        return asyncio.new_event_loop().run_until_complete(
            eng.run_mission(mid))

    def write(self, text, name="shadow-manual-test.txt"):
        Path(self.root, name).write_text(text)


# ================================================== the invariant itself ====

class DoneWhenAlwaysExists(Base):
    def test_01_a_founder_supplied_set_is_used(self):
        m = self.provision(self.ui_create([FOUNDER_CHECK]),
                           self.decider(verification=[{"index": 0,
                                                       "probe": PROBE}]))
        self.assertEqual(len(m["done_when"]), 1)
        self.assertEqual(self.at_spawn[0][0]["check"], FOUNDER_CHECK,
                         "and it is on disk BEFORE the worker is briefed")

    def test_02_an_empty_set_is_written_before_the_worker_is_briefed(self):
        mid = self.ui_create([])
        self.assertEqual(self.store.load(mid)["done_when"], [])
        m = self.provision(mid, self.decider(
            done_when=[{"tier": "founder_confirm", "check": FOUNDER_CHECK}],
            verification=[{"index": 0, "probe": PROBE}]))
        self.assertTrue(m["done_when"], "a mission without a Done When "
                                        "must not reach the worker")
        self.assertEqual(self.at_spawn[0][0]["check"], FOUNDER_CHECK)

    def test_03_no_mission_reaches_a_worker_without_one(self):
        for lines in ([FOUNDER_CHECK], []):
            mid = self.ui_create(lines)
            self.provision(mid, self.decider(
                done_when=[{"tier": "founder_confirm", "check": "a bar"}],
                verification=[{"index": 0, "probe": PROBE}]))
            self.assertTrue(self.at_spawn[-1],
                            "briefed with no Done When: %r" % (lines,))


# ============================================== TEST A -- machine-verifiable =

class TestA_MachineVerifiableFounderCheck(Base):
    def test_04_shadow_attaches_its_own_verification(self):
        m = self.provision(self.ui_create([FOUNDER_CHECK]),
                           self.decider(verification=[{"index": 0,
                                                       "probe": PROBE}]))
        row = m["done_when"][0]
        self.assertEqual(row["tier"], "verify")
        self.assertEqual(row["probe"]["kind"], "file_equals")
        self.assertEqual(row["check"], FOUNDER_CHECK,
                         "byte for byte, the founder's sentence")

    def test_05_it_reaches_DONE_with_no_founder_confirmation(self):
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]),
                       writes="shadow-manual-pass")
        out = self.run_to_end(mid, decider=self.decider())
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 1,
                         "the worker did it on the brief, as it did live")
        self.assertIsNone(out.get("intervention"),
                          "nothing was asked of the founder")
        self.assertNotEqual(out.get("pause_reason"), "founder_confirm")

    def test_06_the_engine_really_read_the_file(self):
        self.write("shadow-manual-pass")
        mid = self.ui_create([FOUNDER_CHECK])
        m = self.provision(mid, self.decider(verification=[{"index": 0,
                                                            "probe": PROBE}]))
        done, results = mission_engine.evaluate_done_when(
            m, "", app_module._shadow_verifier, self.root)
        self.assertTrue(done)
        self.assertTrue(results[0]["met"])
        # ...and it is the FILE that decides: change the bytes, nothing else
        self.write("something else")
        self.assertFalse(mission_engine.evaluate_done_when(
            m, CLAIM, app_module._shadow_verifier, self.root)[0])


# ================================================ TEST B / F -- worker lies ==

class TestB_WorkerLies(Base):
    def setUp(self):
        super().setUp()
        self.mid = self.ui_create([FOUNDER_CHECK])
        self.provision(self.mid, self.decider(verification=[{"index": 0,
                                                             "probe": PROBE}]),
                       writes="WRONG")

    def test_07_a_perfect_DONE_CHECK_over_a_wrong_file_is_unmet(self):
        self.write("WRONG")
        m = self.store.load(self.mid)
        self.assertTrue(app_module._shadow_verifier(FOUNDER_CHECK, CLAIM),
                        "the attestation verifier accepts this claim")
        done, results = mission_engine.evaluate_done_when(
            m, CLAIM, app_module._shadow_verifier, self.root)
        self.assertFalse(done)
        self.assertFalse(results[0]["met"])

    def test_08_the_mission_does_not_become_done(self):
        out = self.run_to_end(self.mid, decider=self.decider())
        self.assertNotEqual(out["state"], "done")
        self.assertEqual(Path(self.root, "shadow-manual-test.txt").read_text(),
                         "WRONG", "and nothing in the loop rewrote it")

    def test_09_unmet_does_NOT_become_NEEDS_YOU(self):
        """THE SPECIAL BUG, pinned. check_met=false means only "not satisfied
        yet". A worker that can still fix it must keep being driven."""
        out = self.run_to_end(self.mid, decider=self.decider(), max_turns=3)
        self.assertIsNone(out.get("intervention"),
                          "no founder question was raised")
        self.assertNotEqual(out.get("block_reason"), "needs_founder")
        self.assertNotEqual(out.get("pause_reason"), "founder_confirm")
        self.assertGreaterEqual(len(self.says), 1,
                                "Shadow kept instructing the worker")
        self.assertEqual(out["turns_used"], 3,
                         "it spent the budget on the WORK, not on asking")

    def test_10_and_it_completes_the_moment_the_file_is_right(self):
        out = self.run_to_end(
            self.mid, decider=self.decider(),
            on_say=lambda n: self.write("shadow-manual-pass"))
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 2,
                         "wrong at the brief, right after one instruction")


# =========================================== TEST C -- genuinely subjective ==

class TestC_SubjectiveCheck(Base):
    def test_11_shadow_does_not_fabricate_a_probe(self):
        """The decider omits what it cannot settle -- the correct answer."""
        m = self.provision(self.ui_create([SUBJECTIVE_CHECK]),
                           self.decider(verification=[]))
        row = m["done_when"][0]
        self.assertEqual(row["tier"], "founder_confirm")
        self.assertNotIn("probe", row)
        self.assertEqual(row["check"], SUBJECTIVE_CHECK)

    def test_12_a_worker_claim_still_cannot_close_it(self):
        m = self.provision(self.ui_create([SUBJECTIVE_CHECK]),
                           self.decider(verification=[]))
        claim = "DONE-CHECK: " + SUBJECTIVE_CHECK
        self.assertFalse(mission_engine.evaluate_done_when(
            m, claim, app_module._shadow_verifier, self.root)[0],
            "only confirm_check writes that flag")

    def test_13_an_UNSAFE_probe_leaves_the_check_with_the_founder(self):
        """Shadow answering badly must not produce a fake verification."""
        for bad in ({"kind": "file_exists", "path": "../../etc/passwd"},
                    {"kind": "command_succeeds", "path": "pytest"},
                    {"kind": "file_equals", "path": "x.txt"}):
            m = self.provision(self.ui_create([SUBJECTIVE_CHECK]),
                               self.decider(verification=[{"index": 0,
                                                           "probe": bad}]))
            self.assertEqual(m["done_when"][0]["tier"], "founder_confirm",
                             repr(bad))
            self.assertNotIn("probe", m["done_when"][0], repr(bad))

    def test_14_a_mixed_set_is_split_correctly(self):
        m = self.provision(self.ui_create([FOUNDER_CHECK, SUBJECTIVE_CHECK]),
                           self.decider(verification=[{"index": 0,
                                                       "probe": PROBE}]))
        self.assertEqual([c["tier"] for c in m["done_when"]],
                         ["verify", "founder_confirm"])
        self.assertEqual([c["check"] for c in m["done_when"]],
                         [FOUNDER_CHECK, SUBJECTIVE_CHECK])


# ======================================= TEST D -- Shadow wrote it instead ===

class TestD_CreatorIdentityIsIrrelevant(Base):
    def test_15_a_shadow_written_check_is_verified_identically(self):
        mid = self.ui_create([])            # founder supplies nothing
        m = self.provision(mid, self.decider(
            done_when=[{"tier": "founder_confirm", "check": FOUNDER_CHECK}],
            verification=[{"index": 0, "probe": PROBE}]))
        self.assertEqual(m["done_when"][0]["tier"], "verify")
        self.assertEqual(m["done_when"][0]["probe"]["kind"], "file_equals")
        self.assertEqual(m["done_when"][0]["check"], FOUNDER_CHECK)

    def test_16_and_it_reaches_DONE_the_same_way(self):
        mid = self.ui_create([])
        self.provision(mid, self.decider(
            done_when=[{"tier": "founder_confirm", "check": FOUNDER_CHECK}],
            verification=[{"index": 0, "probe": PROBE}]),
            writes="shadow-manual-pass")
        out = self.run_to_end(mid, decider=self.decider())
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["turns_used"], 1)

    def test_17_the_two_records_are_indistinguishable(self):
        """THE PROOF. Same condition, two authors, byte-identical rows."""
        founder = self.provision(
            self.ui_create([FOUNDER_CHECK]),
            self.decider(verification=[{"index": 0, "probe": PROBE}]))
        shadow = self.provision(self.ui_create([]), self.decider(
            done_when=[{"tier": "founder_confirm", "check": FOUNDER_CHECK}],
            verification=[{"index": 0, "probe": PROBE}]))
        self.assertEqual(founder["done_when"], shadow["done_when"])

    def test_18_nothing_on_the_record_says_who_wrote_a_check(self):
        """There is no author field, so no code can branch on one."""
        m = self.provision(self.ui_create([FOUNDER_CHECK]),
                           self.decider(verification=[{"index": 0,
                                                       "probe": PROBE}]))
        self.assertEqual(set(m["done_when"][0]), {"tier", "check", "probe"})


# ============================================ TEST E -- restart / recovery ===

class TestE_Restart(Base):
    def test_19_verification_metadata_survives_a_fresh_store(self):
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]))
        reloaded = MissionStore().load(mid)          # a different instance
        row = reloaded["done_when"][0]
        self.assertEqual(row["tier"], "verify")
        self.assertEqual(row["probe"], {"kind": "file_equals",
                                        "path": "shadow-manual-test.txt",
                                        "text": "shadow-manual-pass",
                                        "allow_trailing_newline": True})
        self.assertEqual(row["check"], FOUNDER_CHECK)

    def test_20_and_still_verifies_after_the_reload(self):
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]))
        self.write("shadow-manual-pass")
        m = MissionStore().load(mid)
        self.assertTrue(mission_engine.evaluate_done_when(
            m, "", app_module._shadow_verifier, self.root)[0])

    def test_21_the_second_first_contact_caller_does_not_re_ask(self):
        """provision_target and run_mission turn 0 both reach the pass; it
        must cost one decider call, not two."""
        mid = self.ui_create([SUBJECTIVE_CHECK])
        self.provision(mid, self.decider(verification=[]))
        before = len(self.asked)
        self.run_to_end(mid, decider=self.decider(verification=[]),
                        max_turns=1)
        asked_at_turn_0 = [c for c in self.asked[before:]
                           if c.get("turns_used") == 0]
        self.assertTrue(self.store.load(mid).get("verification_asked"))
        self.assertLessEqual(len(asked_at_turn_0), 1,
                             "the verification question is asked once")


# ================================= TEST G -- unmet, and the worker can fix ===

class TestG_UnmetButFixable(Base):
    def test_22_a_false_machine_check_keeps_the_mission_running(self):
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]))
        # never write the file at all: the condition is simply not true yet
        out = self.run_to_end(mid, decider=self.decider(), max_turns=3)
        self.assertNotEqual(out["state"], "done")
        self.assertIsNone(out.get("intervention"),
                          "check_met=false is not a question for the founder")
        self.assertNotEqual(out.get("block_reason"), "needs_founder")
        self.assertNotEqual(out.get("pause_reason"), "founder_confirm")
        self.assertEqual(out["turns_used"], 3,
                         "every turn went to the worker")

    def test_23_confirmation_is_not_due_while_a_machine_check_is_unmet(self):
        results = [{"tier": "verify", "check": FOUNDER_CHECK, "met": False},
                   {"tier": "founder_confirm", "check": SUBJECTIVE_CHECK,
                    "met": False}]
        self.assertFalse(mission_engine.confirmation_is_due(results),
                         "a signature is not what is missing")


class TheSpecialBug(Base):
    """check_met=false MUST NOT automatically become NEEDS YOU.

    False means ONE thing: the condition is not satisfied yet. It does not
    mean the founder must intervene. If the worker can still resolve it, the
    mission keeps working.

    TWO ENGINE PREDICATES DECIDE THIS, and they are the only places that turn
    an evaluation into a founder question by themselves:

        confirmation_is_due       mid-loop: pause for a signature
        confirmation_reachable    end of road: NEEDS YOU instead of failing

    Both are answered from the RESULTS, so both are pinned directly below --
    a change to either is caught here even if no loop is run. The loop tests
    then prove the predicates are actually what the loop consults.

    (A decider may still CHOOSE ask_founder; that is Shadow judging, not the
    engine escalating, and it is not what this class is about.)
    """

    UNMET_PROBED = {"tier": "verify", "check": FOUNDER_CHECK, "met": False}
    MET_PROBED = {"tier": "verify", "check": FOUNDER_CHECK, "met": True}
    UNMET_CONFIRM = {"tier": "founder_confirm", "check": SUBJECTIVE_CHECK,
                     "met": False}

    # ---- the predicates, directly -----------------------------------------

    def test_28_an_unmet_machine_check_is_never_due_for_a_signature(self):
        for results in ([self.UNMET_PROBED],
                        [self.UNMET_PROBED, self.UNMET_CONFIRM],
                        [self.MET_PROBED, self.UNMET_PROBED,
                         self.UNMET_CONFIRM]):
            self.assertFalse(mission_engine.confirmation_is_due(results),
                             repr(results))

    def test_29_and_is_never_REACHABLE_either_at_the_end_of_the_road(self):
        for turns in (1, 5, 99):
            self.assertFalse(mission_engine.confirmation_reachable(
                [self.UNMET_PROBED], turns))
            self.assertFalse(mission_engine.confirmation_reachable(
                [self.UNMET_PROBED, self.UNMET_CONFIRM], turns))

    def test_30_the_control__a_signature_IS_due_once_machines_pass(self):
        """WITHOUT THIS THE TWO ABOVE PROVE NOTHING: they would pass against
        a predicate that is False for everything."""
        self.assertTrue(mission_engine.confirmation_is_due(
            [self.MET_PROBED, self.UNMET_CONFIRM]))
        self.assertTrue(mission_engine.confirmation_reachable(
            [self.MET_PROBED, self.UNMET_CONFIRM], 1))

    def test_31_the_difference_is_the_TIER_of_what_is_outstanding(self):
        """Same falsity, same turn count; only the tier of the unmet row
        differs, and that is what decides whether the founder is asked."""
        probed = [self.MET_PROBED,
                  {"tier": "verify", "check": "x", "met": False}]
        confirm = [self.MET_PROBED,
                   {"tier": "founder_confirm", "check": "x", "met": False}]
        self.assertFalse(mission_engine.confirmation_reachable(probed, 3))
        self.assertTrue(mission_engine.confirmation_reachable(confirm, 3))

    # ---- and the loop really consults them --------------------------------

    def test_32_the_loop_spends_its_whole_budget_on_the_worker(self):
        """THE FULL PATH. Real create route, real probe, real filesystem read,
        real loop. The file is never written, so the trusted check reads false
        on every single turn -- and every turn still goes to the worker."""
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]))
        self.assertEqual(self.store.load(mid)["done_when"][0]["tier"],
                         "verify", "the check really is machine-checked")
        out = self.run_to_end(mid, decider=self.decider(), max_turns=5)
        self.assertFalse(Path(self.root, "shadow-manual-test.txt").exists())
        self.assertEqual(out["turns_used"], 5)
        # FOUR SAYS, FIVE TURNS: provision delivered the brief, so turn 0 is
        # the briefed turn and sends nothing. Every turn that COULD carry an
        # instruction carried one, and none carried a question.
        self.assertEqual(len(self.says), 4, "every drivable turn drove")
        self.assertIsNone(out.get("intervention"))
        self.assertNotEqual(out.get("block_reason"), "needs_founder")
        self.assertNotEqual(out.get("pause_reason"), "founder_confirm")
        self.assertNotEqual(out["state"], "paused")

    def test_33_and_the_SAME_run_asks_when_the_check_is_the_founders(self):
        """THE MUTATION, RUN AS A TEST. Identical mission, identical decider,
        identical never-written file -- the ONE difference is that Shadow
        could not verify the condition, so the row stays founder_confirm. Now
        the end of the road IS a question for the founder. If test_32 ever
        starts looking like this, the bug is back."""
        mid = self.ui_create([FOUNDER_CHECK])
        self.provision(mid, self.decider(verification=[]))   # no probe
        self.assertEqual(self.store.load(mid)["done_when"][0]["tier"],
                         "founder_confirm")
        out = self.run_to_end(mid, decider=self.decider(), max_turns=5)
        self.assertEqual(out["state"], "paused")
        self.assertEqual(out["pause_reason"], "founder_confirm")

    def test_34_a_mixed_mission_is_not_asked_while_the_machine_part_fails(self):
        """The founder's signature is not collected early just because one of
        the two checks happens to be theirs."""
        mid = self.ui_create([FOUNDER_CHECK, SUBJECTIVE_CHECK])
        self.provision(mid, self.decider(verification=[{"index": 0,
                                                        "probe": PROBE}]))
        out = self.run_to_end(mid, decider=self.decider(), max_turns=4)
        self.assertNotEqual(out["state"], "paused")
        self.assertIsNone(out.get("intervention"))
        # ...and the moment the machine half passes, the signature IS due
        self.write("shadow-manual-pass")
        m = self.store.load(mid)
        _done, results = mission_engine.evaluate_done_when(
            m, "", app_module._shadow_verifier, self.root)
        self.assertTrue(mission_engine.confirmation_is_due(results))


# ========================================== the rule this sits on top of =====

class TheProbeRuleStillHolds(Base):
    def test_24_verify_without_a_probe_is_still_demoted(self):
        """DESTINATION CHANGED 2026-09-20 (D-SH-1), RULE UNCHANGED: a
        probe-less `verify` is still not a verify check and still never
        claims Shadow ran anything. It now lands on the judge, which can
        settle it by reading the diff and returns it to the founder via
        `cannot_tell` when it cannot."""
        self.assertEqual(
            mission_engine.resolve_verify_tier("verify", None),
            ("judge", None))
        m = self.store.create("x", "fix", done_when=[
            {"tier": "verify", "check": FOUNDER_CHECK}])
        self.assertEqual(m["done_when"][0]["tier"], "judge")
        self.assertEqual(m["done_when"][0]["check"], FOUNDER_CHECK,
                         "demotion never re-words a check, whatever tier it "
                         "lands on")

    def test_25_verification_metadata_carries_no_wording_at_all(self):
        """The shape is why a rewrite is impossible, not the discipline."""
        rows = mission_engine.validate_verification([
            {"index": 0, "probe": PROBE, "check": "A REWRITE",
             "tier": "contains_artifact"}])
        self.assertEqual(rows, [{"index": 0, "probe": PROBE}])

    def test_26_an_out_of_range_index_changes_nothing(self):
        m = self.provision(self.ui_create([FOUNDER_CHECK]),
                           self.decider(verification=[{"index": 7,
                                                       "probe": PROBE}]))
        self.assertEqual(m["done_when"][0]["tier"], "founder_confirm")
        self.assertEqual(m["done_when"][0]["check"], FOUNDER_CHECK)

    def test_27_a_confirmed_check_is_never_re_tiered(self):
        mid = self.ui_create([FOUNDER_CHECK])
        m = self.store.confirm_check(mid, 0)
        eng = self.engine(decider=self.decider())
        eng._adopt_verification(m, {"verification": [{"index": 0,
                                                      "probe": PROBE}]})
        self.assertEqual(m["done_when"][0]["tier"], "founder_confirm")
        self.assertTrue(m["done_when"][0]["met"],
                        "the founder already signed it; it is settled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
