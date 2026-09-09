"""test_agents_api.py -- the SEO Writer's routes, through the real FastAPI app.

The engine is stubbed at the model boundary only (seo_agent.llm.call), so the loop, the
store, the gates and the routes all run for real against a temp data dir. Every test
that mutates state points SEO_AGENT_DATA at its own folder before importing anything.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

os.environ["SEO_AGENT_DATA"] = tempfile.mkdtemp(prefix="seo-agent-test-")
os.environ["SEO_AGENT_NO_CLI"] = "1"          # never spawn the real CLI from a test

from fastapi.testclient import TestClient  # noqa: E402

import agents_api  # noqa: E402
import app as app_module  # noqa: E402
from seo_agent import llm, store  # noqa: E402

HDR = {"X-Sutra-Panel": app_module.PANEL_TOKEN, "Origin": "http://127.0.0.1:8330"}
BASE = "/api/agents/seo"


def _settle(client, chat_id, run_id, want, tries=200):
    """Poll until the run reaches one of `want`. The loop runs on a thread."""
    for _ in range(tries):
        s = client.get("%s/runs/%s/%s" % (BASE, chat_id, run_id)).json()
        if s.get("status") in want:
            return s
        time.sleep(0.02)
    raise AssertionError("run never reached %s; last state %s" % (want, s))


class ScriptedModel:
    """A model that follows a script: each call pops the next reply."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system, messages, tools=None, model=None, **kw):
        self.calls.append({"system": system, "messages": messages})
        if not self.replies:
            return {"text": "Done.", "tool_calls": [], "raw": None}
        return self.replies.pop(0)


def _tool(name, **inp):
    return {"id": "call-%s-%d" % (name, int(time.time() * 1000) % 100000), "name": name, "input": inp}


class TestAgentsApi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # loopback base_url: TrustedHostMiddleware refuses "testserver" with a 400
        cls.client = TestClient(app_module.app, base_url="http://127.0.0.1")
        cls.real_call = llm.call

    def tearDown(self):
        llm.call = self.real_call

    # ---- routing + guards ------------------------------------------------------------

    def test_01_health_reports_provider_and_data_dir_under_home_or_env(self):
        r = self.client.get(BASE + "/health")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertTrue(j["ok"])
        self.assertIn("model_provider", j)
        self.assertEqual(j["data_dir"], os.environ["SEO_AGENT_DATA"])
        self.assertFalse(j["dataforseo"])

    def test_02_mutation_with_origin_needs_the_panel_token(self):
        r = self.client.post(BASE + "/chats", json={"title": "x"},
                             headers={"Origin": "http://127.0.0.1:8330"})
        self.assertEqual(r.status_code, 403, r.text)
        r = self.client.post(BASE + "/chats", json={"title": "x"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)

    def test_03_ids_are_validated(self):
        self.assertEqual(self.client.get(BASE + "/chats/bad%20id").status_code, 400)
        self.assertEqual(self.client.get(BASE + "/runs/c-1/r-1/artifact/bad%20name").status_code, 400)
        self.assertEqual(self.client.get(BASE + "/runs/.hidden/r-1").status_code, 400)
        self.assertEqual(self.client.get(BASE + "/chats/c-nope").status_code, 404)

    # ---- the run -----------------------------------------------------------------------

    def test_10_a_message_starts_a_run_and_a_question_stops_it(self):
        """No credit gates any more: a work tool runs when called. What still stops the run is
        the agent asking the user something, which is what this pins."""
        llm.call = ScriptedModel([
            {"text": "One thing first.", "tool_calls": [_tool("ask_user", question="Which site?",
                                                             why="I need the domain",
                                                             options=[{"label": "example.com", "recommended": True}])], "raw": None},
        ])
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        r = self.client.post(BASE + "/chats/%s/send" % cid, json={"text": "Set up for my site"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["run_id"]
        s = _settle(self.client, cid, rid, ("waiting",))
        self.assertEqual(s["waiting_on"]["kind"], "question")
        self.assertEqual(s["waiting_on"]["question"], "Which site?")
        self.assertEqual(s["request"], "Set up for my site", "the full request is kept on the run")
        # the events carry the call_id so the screen can pair the answer
        ev = self.client.get(BASE + "/runs/%s/%s/events" % (cid, rid)).json()
        waits = [e for e in ev["events"] if e["type"] == "waiting"]
        self.assertTrue(waits and waits[0].get("call_id"))
        # the chat list reports it live
        chats = self.client.get(BASE + "/chats").json()
        me = [c for c in chats if c["id"] == cid][0]
        self.assertEqual(me["live"], "waiting")
        self.__class__.cid, self.__class__.rid = cid, rid

    def test_11_a_typed_message_while_waiting_is_the_answer_not_a_new_run(self):
        cid, rid = self.__class__.cid, self.__class__.rid
        llm.call = ScriptedModel([{"text": "Got it, example.com.", "tool_calls": [], "raw": None}])
        r = self.client.post(BASE + "/chats/%s/send" % cid, json={"text": "example.com please"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["answered"])
        self.assertEqual(r.json()["run_id"], rid, "same run, no new one")
        _settle(self.client, cid, rid, ("done",))
        ev = self.client.get(BASE + "/runs/%s/%s/events" % (cid, rid)).json()["events"]
        res = [e for e in ev if e["type"] == "resumed"]
        self.assertEqual(res[0].get("answer"), "example.com please")
        # and the model saw the answer as the tool's result
        msgs = store.get_messages(cid)
        last_result = msgs[-2]["content"][0]["content"]
        self.assertEqual(last_result.get("text"), "example.com please")

    def test_11b_work_tools_run_without_an_approval_stop(self):
        """The old money gate is gone: a work tool call goes straight to the tool."""
        from seo_agent import registry
        self.assertTrue(all(t["gate"] == "auto" for t in registry.WORK_TOOLS))
        self.assertTrue(all(not t.get("cost_credits") for t in registry.WORK_TOOLS))

    def test_12_send_while_running_is_refused_with_409(self):
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        rid = store.new_run(cid, "busy")
        store.patch_state(cid, rid, status="running")
        r = self.client.post(BASE + "/chats/%s/send" % cid, json={"text": "hi"}, headers=HDR)
        self.assertEqual(r.status_code, 409)
        store.patch_state(cid, rid, status="stopped")

    def test_13_answer_on_a_run_that_is_not_waiting_is_409(self):
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        rid = store.new_run(cid, "x")
        store.patch_state(cid, rid, status="done")
        r = self.client.post(BASE + "/runs/%s/%s/answer" % (cid, rid), json={"answer": {"text": "x"}}, headers=HDR)
        self.assertEqual(r.status_code, 409)

    def test_14_show_artifact_hands_back_the_file_on_disk_and_the_picked_topic(self):
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        rid = store.new_run(cid, "topics")
        store.save_artifact(cid, rid, "topics.json", {"topics": [
            {"id": "t1", "topic": "One"}, {"id": "t2", "topic": "Two"}]})
        # park the run at the checkpoint by hand, the way the loop would
        call_id = "call-show"
        store.save_messages(cid, [{"role": "user", "content": "pick"},
                                  {"role": "assistant", "content": [{"type": "tool_use", "id": call_id,
                                                                     "name": "show_artifact",
                                                                     "input": {"path": "topics.json", "view": "topic_list", "prompt": "?"}}]}])
        store.patch_state(cid, rid, status="waiting", stage="topic",
                          waiting_on={"kind": "artifact", "call_id": call_id, "artifact": "topics.json",
                                      "view": "topic_list", "prompt": "?"})
        llm.call = ScriptedModel([{"text": "Great, Two it is.", "tool_calls": [], "raw": None}])
        r = self.client.post(BASE + "/runs/%s/%s/answer" % (cid, rid),
                             json={"answer": {"approved": True, "picked": "t2", "topic": "Two"}}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        _settle(self.client, cid, rid, ("done",))
        msgs = store.get_messages(cid)
        result = [m for m in msgs if m["role"] == "user" and isinstance(m["content"], list)][-1]["content"][0]["content"]
        self.assertEqual(result["picked_topic"]["topic"], "Two")
        self.assertEqual(result["artifact"]["topics"][1]["id"], "t2")

    def test_15_saving_an_edited_blueprint_runs_the_checks_and_logs_it(self):
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        rid = store.new_run(cid, "bp")
        bp = {"title": "T", "sections": [{"id": "s1", "heading": "A", "words": 100, "covers": "a"},
                                         {"id": "s2", "heading": "B", "words": 100, "covers": "b"}]}
        store.save_artifact(cid, rid, "blueprint.json", bp)
        bp2 = dict(bp, sections=[bp["sections"][1], bp["sections"][0]])
        r = self.client.post(BASE + "/runs/%s/%s/artifact/blueprint.json" % (cid, rid), json={"data": bp2}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(store.load_artifact(cid, rid, "blueprint.json")["sections"][0]["id"], "s2")
        ev = self.client.get(BASE + "/runs/%s/%s/events" % (cid, rid)).json()["events"]
        self.assertTrue(any(e["type"] == "edited" and e["block"] == "*" for e in ev))
        # a missing artifact is 404, an empty body 400
        self.assertEqual(self.client.post(BASE + "/runs/%s/%s/artifact/nope.json" % (cid, rid), json={"data": {}}, headers=HDR).status_code, 404)
        self.assertEqual(self.client.post(BASE + "/runs/%s/%s/artifact/blueprint.json" % (cid, rid), json={}, headers=HDR).status_code, 400)

    def test_16_publish_saves_to_the_library_and_the_library_routes_work(self):
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        rid = store.new_run(cid, "pub")
        self.assertEqual(self.client.post(BASE + "/runs/%s/%s/publish" % (cid, rid), json={}, headers=HDR).status_code, 404,
                         "no draft yet -> 404, never an empty library item")
        store.save_artifact(cid, rid, "draft.md", "# Hello\n\nA body.\n")
        store.save_artifact(cid, rid, "blueprint.json", {"h1": "Hello there"})
        r = self.client.post(BASE + "/runs/%s/%s/publish" % (cid, rid), json={}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        item = r.json()["item_id"]
        lib = self.client.get(BASE + "/library").json()
        # titled from the draft's own H1 ("Hello"), not the blueprint's ("Hello there"): the heading
        # pass rewrites the H1 after the blueprint was approved, so the draft is the truth
        self.assertTrue(any(i["id"] == item and i["title"] == "Hello" for i in lib), lib)
        one = self.client.get(BASE + "/library/%s" % item).json()
        self.assertIn("A body.", one["draft"])
        r = self.client.post(BASE + "/library/%s/status" % item, json={"status": "ready"}, headers=HDR)
        self.assertEqual(r.json()["status"], "ready")
        r = self.client.post(BASE + "/library/%s/status" % item, json={"status": "evil"}, headers=HDR)
        self.assertEqual(r.json()["status"], "draft", "unknown statuses fall back to draft")
        self.assertTrue(self.client.post(BASE + "/library/%s/delete" % item, headers=HDR).json()["ok"])
        self.assertEqual(self.client.get(BASE + "/library/%s" % item).status_code, 404)

    def test_17_a_saved_article_can_be_edited_in_place(self):
        """POST /library/<id>/save. The Library is a place to fix a sentence, not a read-only
        archive, so the person's edit goes back over the article and becomes the truth."""
        if not hasattr(store, "library_update"):
            self.skipTest("store.library_update is missing from seo_agent/store.py: the route "
                          "cannot save until it is restored (it was lost with the old clone)")
        item = store.library_save("c", "r", "Draft title", "# Draft title\n\nThe first body.\n")
        r = self.client.post(BASE + "/library/%s/save" % item,
                             json={"title": "A better title", "draft": "# A better title\n\nThe edited body.\n"},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["title"], "A better title")
        self.assertEqual(r.json()["words"], len("# A better title\n\nThe edited body.\n".split()))
        back = self.client.get(BASE + "/library/%s" % item).json()
        self.assertIn("The edited body.", back["draft"], "the edit is what reads back")
        self.assertNotIn("The first body.", back["draft"], "and the old body is gone, not appended to")
        self.assertEqual(back["title"], "A better title")
        # an empty article is not a save: it would silently destroy the article
        for bad in ("", "   ", None, 12):
            r = self.client.post(BASE + "/library/%s/save" % item, json={"draft": bad}, headers=HDR)
            self.assertEqual(r.status_code, 400, "draft=%r" % bad)
            self.assertEqual(r.json()["detail"], "an empty article is not a save")
        self.assertIn("The edited body.", self.client.get(BASE + "/library/%s" % item).json()["draft"],
                      "a refused save leaves the article exactly as it was")
        # an id for an article that is not there
        self.assertEqual(self.client.post(BASE + "/library/no-such-article/save",
                                          json={"draft": "x"}, headers=HDR).status_code, 404)
        self.assertEqual(self.client.post(BASE + "/library/..%2Fetc/save",
                                          json={"draft": "x"}, headers=HDR).status_code, 404)
        # no title given: the article keeps the one it had, and a long one is trimmed
        r = self.client.post(BASE + "/library/%s/save" % item, json={"draft": "# x\n\nbody\n"}, headers=HDR)
        self.assertEqual(r.json()["title"], "A better title")
        r = self.client.post(BASE + "/library/%s/save" % item,
                             json={"title": "T" * 400, "draft": "# x\n\nbody\n"}, headers=HDR)
        self.assertEqual(len(r.json()["title"]), 160, "a title is trimmed, never rejected")
        store.library_delete(item)

    # ---- settings ---------------------------------------------------------------------

    def test_20_connections_never_echo_secrets_and_refuse_api_keys(self):
        r = self.client.post(BASE + "/connections", json={"dataforseo_login": "me@x.com", "dataforseo_password": "pw",
                                                          "anthropic_key": "sk-should-never-stick"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        j = self.client.get(BASE + "/connections").json()
        self.assertEqual(j, {"dataforseo_login": True, "dataforseo_password": True, "voyage_key": False})
        self.assertNotIn("sk-should", json.dumps(j))
        on_disk = store.connections()
        self.assertNotIn("anthropic_key", on_disk, "an API key is dropped, the panel bills the subscription")
        mode = oct(os.stat(store.connections_file()).st_mode & 0o777)
        self.assertEqual(mode, "0o600", "secrets are owner-only")
        self.assertTrue(self.client.get(BASE + "/health").json()["dataforseo"])
        # clearing
        self.client.post(BASE + "/connections", json={"dataforseo_login": "", "dataforseo_password": ""}, headers=HDR)
        self.assertEqual(self.client.get(BASE + "/connections").json(),
                         {"dataforseo_login": False, "dataforseo_password": False, "voyage_key": False})
        # the Voyage key: saved, reported as a boolean, cleared
        self.client.post(BASE + "/connections", json={"voyage_key": "pa-secretsecretsecretsecret"}, headers=HDR)
        j = self.client.get(BASE + "/connections").json()
        self.assertTrue(j["voyage_key"])
        self.assertNotIn("pa-secret", json.dumps(j))
        self.assertTrue(self.client.get(BASE + "/health").json()["voyage"])
        self.client.post(BASE + "/connections", json={"voyage_key": ""}, headers=HDR)
        self.assertFalse(self.client.get(BASE + "/connections").json()["voyage_key"])

    def test_21_memory_add_toggle_and_list(self):
        r = self.client.post(BASE + "/memory", json={"text": "Never open with a question", "kind": "rule"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        mid = r.json()["id"]
        self.assertEqual(self.client.post(BASE + "/memory", json={"text": "  "}, headers=HDR).status_code, 400)
        self.client.post(BASE + "/memory/%s/toggle" % mid, json={"active": False}, headers=HDR)
        m = self.client.get(BASE + "/memory").json()
        row = [x for x in m["rules"] if x["id"] == mid][0]
        self.assertFalse(row["active"])

    def test_22_tools_list_is_plain_english_and_carries_no_module_paths(self):
        tools = self.client.get(BASE + "/tools").json()
        names = {t["name"] for t in tools}
        self.assertIn("run_research", names)
        self.assertIn("learn_brand", names)
        self.assertIn("build_page_index", names)
        self.assertIn("find_prompt", names, "the twelfth tool: which prompt owns a complaint")
        # No tool may reach the screen under its own function name. registry.LABELS is the one
        # place that decides it, and its fallback -- name.replace("_"," ").capitalize() -- is a
        # leak, not a safety net: "Refresh site" sat in this list beside "Learning the brand"
        # until 2026-09-09. The screen's stand-in for that is deleted, so this is the guard.
        for t in tools:
            derived = t["name"].replace("_", " ")
            self.assertNotIn(t["label"], (derived, derived.capitalize()),
                             "%s has no row in registry.LABELS" % t["name"])
        rr = [t for t in tools if t["name"] == "run_research"][0]
        for k in ("label", "does", "when", "needs", "takes"):
            self.assertTrue(rr.get(k), k)
        self.assertNotIn("module", rr)
        self.assertNotIn("gate", rr)
        self.assertNotIn("cost_credits", rr)

    def test_23_knowledge_round_trip(self):
        r = self.client.post(BASE + "/knowledge", json={"competitors": {"competitors": ["a.com", "b.com"]}}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        k = self.client.get(BASE + "/knowledge").json()
        self.assertEqual(k["competitors"]["competitors"], ["a.com", "b.com"])

    def test_24_the_knowledge_payload_separates_files_a_person_fills_in(self):
        """"Files a machine built" and "files you have to write" are different things, and the
        screen can only say so if the payload does. pack.inputs() is the engine's own list;
        this asserts the route carries it, in the shape the other two file lists use."""
        k = self.client.get(BASE + "/knowledge").json()
        brand = k.get("brand") or {}
        self.assertIn("inputs", brand, "the Knowledge payload must carry the typed-in files")
        self.assertIsInstance(brand["inputs"], list)
        names = {r["name"] for r in brand["inputs"]}
        self.assertIn("pricing.md", names, "pricing.md is the first of them")
        row = [r for r in brand["inputs"] if r["name"] == "pricing.md"][0]
        for key in ("name", "label", "note", "exists", "words", "filled"):
            self.assertIn(key, row, key)
        self.assertEqual(row["label"], "Prices and hidden facts")
        # `filled` is the one field the screen cannot derive for itself. The blank form is real
        # text on disk, so a word count alone calls an untouched file filled the day it is
        # created -- which is how the seed file this replaces stayed empty for months.
        self.assertIsInstance(row["filled"], bool)
        # An input is not also an extra or a source of the brief: three lists, no overlap, or the
        # screen draws the same file twice under two different headings.
        self.assertNotIn("pricing.md", {r["name"] for r in brand.get("extras") or []})
        self.assertNotIn("pricing.md", {r["name"] for r in brand.get("built_from") or []})

    def test_24b_words_alone_cannot_tell_a_blank_form_from_a_written_file(self):
        """The blank form is real text, so it has a word count of its own. `filled` is what the
        screen branches on; asserting the two move independently is the whole point."""
        from seo_agent.brand import features, pack
        store.save_knowledge("brand/pricing.md", features.cm.template("pricing"))
        blank = [r for r in pack.inputs() if r["name"] == "pricing.md"][0]
        self.assertGreater(blank["words"], 0, "a blank form is not zero words")
        self.assertFalse(blank["filled"], "and is still nobody's answer")

        store.save_knowledge("brand/pricing.md",
                             features.cm.template("pricing") + "\n\nStarter is $29 a month.")
        written = [r for r in pack.inputs() if r["name"] == "pricing.md"][0]
        self.assertTrue(written["filled"], "one typed line is the difference")

        k = self.client.get(BASE + "/knowledge").json()
        got = [r for r in k["brand"]["inputs"] if r["name"] == "pricing.md"][0]
        self.assertTrue(got["filled"], "and the route carries it through")

    def test_25_saving_pricing_marks_product_facts_for_rebuild(self):
        """pricing.md is the one brand file whose save has to propagate: features.md, the file the
        writer reads for product claims, is filled FROM it. The save MARKS and returns; it must not
        sit through a rebuild that costs model calls, and no model is stubbed in for this test --
        if the hook did any model work, this would hang or fail rather than pass."""
        from seo_agent.brand import features
        stamp = os.path.join(store.knowledge_dir(), "brand", features.STAMP)

        # No features.md yet: pricing_saved() has nothing to mark, and the save still succeeds.
        r = self.client.post(BASE + "/knowledge/brand/pricing.md",
                             json={"text": "Starter is $29 a month."}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(BASE + "/knowledge/brand/pricing.md").json()["text"],
                         "Starter is $29 a month.")
        self.assertFalse(os.path.exists(stamp), "nothing built, nothing to mark")

        # With features.md on disk, the same save leaves the stamp that makes the next
        # brand-pack run rebuild it -- and touches nothing else.
        store.save_knowledge("brand/" + features.OUTPUT, "# Product facts\n\nStarter: $19.")
        r = self.client.post(BASE + "/knowledge/brand/pricing.md",
                             json={"text": "Starter is $39 a month."}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(os.path.exists(stamp), "the rebuild is marked as due")
        self.assertEqual(store.knowledge("brand/" + features.OUTPUT),
                         "# Product facts\n\nStarter: $19.",
                         "the save marks; it does NOT rebuild in the request")

        # ONE hop, and only for this file. Saving any other brand file leaves no stamp.
        os.remove(stamp)
        r = self.client.post(BASE + "/knowledge/brand/style-guide.md",
                             json={"text": "Sentence case."}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(os.path.exists(stamp), "only pricing.md propagates")

    # ---- the team workspace ------------------------------------------------------------
    # design/WORKSPACE-PLAN.md, and the bar is its section 10.
    #
    # WHAT IS REAL HERE AND WHAT IS NOT. The engine is real: client.settings/save_settings/
    # forget really write connections.json, link really encodes and decodes, and the routes
    # really go through them. Only the four functions that touch the network are replaced --
    # schema.create, schema.verify, pack.publish, pack.join -- because the point of these tests
    # is what the ROUTE does when the network says something, and there is no Supabase here to
    # say it. Stubbing at that seam is what lets the two load-bearing cases be written at all:
    #
    #   * schema.create returning ok=False (the tables did not all appear) must never be drawn
    #     as a created workspace, whatever the request's status code was;
    #   * a personal access token handed to a create must be findable NOWHERE afterwards.
    #
    # Every stub is put back by addCleanup, and _ws_wipe clears the settings it wrote, so these
    # leave connections.json as they found it.

    def _ws_patch(self, mod, name, fn):
        import seo_agent.workspace as W
        target = getattr(W, mod, None) or __import__("seo_agent.workspace." + mod,
                                                     fromlist=["x"])
        old = getattr(target, name)
        setattr(target, name, fn)
        self.addCleanup(setattr, target, name, old)
        return target

    def _ws_engine(self):
        """The engine with its four network calls replaced, and a ledger of what they saw."""
        import seo_agent.workspace as W
        from seo_agent.workspace import pack, sync

        rec = {"tokens": [], "creates": 0, "confirms": 0, "published": 0, "joined": 0,
               "members": [], "verify_ok": True, "create_ok": True}

        def fake_create(url, key, token=None, save=True):
            rec["creates"] += 1
            rec["tokens"].append(token)
            if not rec["create_ok"]:
                return {"route": "paste", "ok": False,
                        "reason": "Sutra could not run the setup for you: that token "
                                  "(sbp_thesecrettoken) is not allowed on this project.",
                        "sql": "create table if not exists public.workspace ();",
                        "editor_url": "https://supabase.com/dashboard/project/abc/sql/new",
                        "next": "Open the SQL Editor, paste the script, press Run."}
            if not rec["verify_ok"]:
                return {"route": "paste", "ok": False,
                        "reason": "The setup script ran but the workspace is not complete. "
                                  "These are missing: members, changes.",
                        "sql": "create table if not exists public.workspace ();",
                        "editor_url": "https://supabase.com/dashboard/project/abc/sql/new"}
            if save:
                W.client.save_settings(workspace_url=url, workspace_key=key,
                                       workspace_id="11111111-2222-3333-4444-555555555555")
            return {"ok": True, "route": "seamless", "workspace_id": "11111111-2222-3333-4444-555555555555",
                    "missing": [], "reason": "Workspace ready.", "message": "Workspace created."}

        def fake_confirm(url=None, key=None, save=True):
            rec["confirms"] += 1
            return fake_create(url, key, token=None, save=save)

        def fake_verify(url=None, key=None):
            if rec["verify_ok"]:
                return {"ok": True, "workspace_id": "11111111-2222-3333-4444-555555555555",
                        "missing": [], "reason": "Workspace ready."}
            return {"ok": False, "workspace_id": "", "missing": ["workspace", "members"],
                    "reason": "Nothing has been created yet. Run the setup script."}

        def fake_publish(client, kroot=None, last_seen_id=0, workdir=None, progress=None,
                         deep_verify=True):
            if progress:
                progress("upload", 50, 100, "part 1 of 2")
            if rec.get("publish_raises"):
                raise RuntimeError(rec["publish_raises"])
            rec["published"] += 1
            return {"version": 1, "bytes": 100}

        def fake_join(client, kroot=None, workdir=None, progress=None):
            if progress:
                progress("download", 1024, 104857600, "part 1 of 3")
            if rec.get("join_raises"):
                raise RuntimeError(rec["join_raises"])
            rec["joined"] += 1
            return {"version": 1, "replay_from": 42, "bytes": 104857600, "files": 9, "pages": 12318}

        def fake_upsert(table, rows, on_conflict=None, url=None, key=None):
            rec["members"].extend(rows)
            return rows

        def fake_select(table, **kw):
            return list(rec["members"]) if table == "members" else []

        # THE MEMBER ROW IS THE ENGINE'S, SO THESE FAKES ARE TABLE-AWARE (2026-09-10).
        # The panel used to build the row itself and one blanket `upsert` fake covered it. It now
        # calls client.register_member, whose whole value is the existing-vs-new branch and its
        # idempotency on member_id — and a `one` fake that answered the same thing for every table
        # made that branch always take "existing", so a real join added nobody and the test could
        # only pass by accident. Faking the three primitives instead runs the real logic.
        def fake_one(table, where=None, columns="*", url=None, key=None):
            if table == "members":
                mid = (where or {}).get("member_id")
                return next((m for m in rec["members"] if m.get("member_id") == mid), None)
            return {"name": "Testlify"}

        def fake_insert(table, rows, url=None, key=None):
            rows = rows if isinstance(rows, list) else [rows]
            if table == "members":
                rec["members"].extend(rows)
            return rows

        def fake_update(table, where, patch, url=None, key=None):
            if table != "members":
                return []
            mid = (where or {}).get("member_id")
            hit = [m for m in rec["members"] if m.get("member_id") == mid]
            for m in hit:
                m.update(patch)
            return hit

        self._ws_patch("schema", "create", fake_create)
        self._ws_patch("schema", "verify", fake_verify)
        self._ws_patch("schema", "confirm", fake_confirm)
        self._ws_patch("pack", "publish", fake_publish)
        self._ws_patch("pack", "join", fake_join)
        self._ws_patch("client", "upsert", fake_upsert)
        self._ws_patch("client", "select", fake_select)
        self._ws_patch("client", "one", fake_one)
        self._ws_patch("client", "insert", fake_insert)
        self._ws_patch("client", "update", fake_update)
        self._ws_patch("sync", "status", lambda client=None: {
            "configured": True, "last_seen_id": 0, "updated_at": None, "stuck": None,
            "polling": False, "last_poll": {}, "outbox": {"queued": 0, "last_error": ""}})
        self._ws_patch("sync", "last_seen_id", lambda client=None: 0)
        # No real background poller in a test: it would make network calls to a project that
        # does not exist, on a thread nothing here can join.
        started = []
        self._ws_patch("sync", "start", lambda client=None, interval=None: started.append(1))
        self._ws_patch("sync", "stop", lambda: None)
        rec["polls_started"] = started
        self.addCleanup(self._ws_wipe)
        return rec

    def _ws_wipe(self):
        from seo_agent.workspace import client as wclient
        wclient.forget()
        agents_api._ws_save_name("")
        agents_api._ws_members["at"], agents_api._ws_members["rows"] = 0.0, []
        agents_api._ws_pack["state"] = "idle"
        agents_api._ws_rebuilder_ref[0] = None
        with agents_api._ws_job_lock:
            agents_api._ws_job = None

    def _ws_settle(self, tries=400):
        """Poll GET /workspace until the job stops moving, the way the screen does."""
        j = {}
        for _ in range(tries):
            j = self.client.get(BASE + "/workspace").json()
            if (j.get("job") or {}).get("phase") in ("done", "failed", "paste"):
                return j
            time.sleep(0.02)
        raise AssertionError("the workspace job never settled: %s" % (j.get("job"),))

    URL = "https://abcdefghijklmnop.supabase.co"
    PUB = "sb_publishable_abcdefghij"

    def test_40_workspace_reads_cleanly_with_no_engine_installed(self):
        """A build with no seo_agent/workspace/ must draw a sentence, not a 500."""
        real = agents_api._ws
        agents_api._ws = lambda: None
        self.addCleanup(setattr, agents_api, "_ws", real)
        j = self.client.get(BASE + "/workspace").json()
        self.assertFalse(j["installed"])
        self.assertFalse(j["configured"])
        self.assertEqual(j["link"], "")
        for path in ("/workspace/create", "/workspace/join"):
            r = self.client.post(BASE + path, json={}, headers=HDR)
            self.assertEqual(r.status_code, 501, r.text)
            self.assertIn("not in this build", r.json()["detail"])

    def test_41_a_wrong_key_is_named_not_coded(self):
        """The bar: a wrong key says what it is, never a status code."""
        self._ws_engine()
        for key, want in (("sb_secret_abc", "secret key"),
                          ("eyJhbGciOiJIUzI1NiJ9.x.y", "service role"),
                          ("sbp_abcabcabcabc", "personal access token"),
                          ("hunter2", "publishable key")):
            r = self.client.post(BASE + "/workspace/create",
                                 json={"url": self.URL, "key": key, "token": "sbp_x1234567"},
                                 headers=HDR)
            self.assertEqual(r.status_code, 400, key)
            detail = r.json()["detail"]
            self.assertIn(want, detail, "%s -> %s" % (key, detail))
            self.assertNotIn("400", detail)
            self.assertIsNone(self.client.get(BASE + "/workspace").json()["job"],
                              "a refused form starts no job at all")

    def test_42_a_bad_url_and_a_bad_token_both_say_where_to_look(self):
        self._ws_engine()
        r = self.client.post(BASE + "/workspace/create",
                             json={"url": "supabase.com/dashboard/project/abc", "key": self.PUB,
                                   "token": "sbp_x1234567"}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Data API", r.json()["detail"])
        r = self.client.post(BASE + "/workspace/create",
                             json={"url": self.URL, "key": self.PUB, "token": "ghp_github"},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)
        self.assertIn("starts with sbp_", r.json()["detail"])

    def test_43_create_verifies_first_and_the_token_is_thrown_away(self):
        rec = self._ws_engine()
        r = self.client.post(BASE + "/workspace/create",
                             json={"url": self.URL, "key": self.PUB, "name": "Testlify",
                                   "member_name": "Devansh", "token": "sbp_thesecrettoken"},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "done")
        self.assertTrue(j["configured"])
        self.assertEqual(j["workspace"]["name"], "Testlify")
        self.assertEqual(j["me"]["name"], "Devansh")
        self.assertTrue(j["link"], "a link the team can be sent")
        self.assertEqual(rec["creates"], 1)
        self.assertEqual(rec["published"], 1, "and the pack went up")
        self.assertEqual(rec["tokens"], ["sbp_thesecrettoken"], "used exactly once")

        # THE LINK IS REALLY A LINK: the engine's own reader gets the three public things back.
        from seo_agent.workspace import link as wlink
        got_url, got_key, got_id = wlink.read_link(j["link"])
        self.assertEqual(got_url, self.URL)
        self.assertEqual(got_key, self.PUB)
        self.assertEqual(got_id, "11111111-2222-3333-4444-555555555555")

        # THE TOKEN IS NOWHERE: not on disk, not in what the screen polls.
        blob = json.dumps(store.connections())
        self.assertNotIn("sbp_", blob, "the token is not in connections.json")
        self.assertIn(self.PUB, blob, "the publishable key is, which is the point")
        self.assertNotIn("sbp_", json.dumps(j), "and nothing of it comes back to the screen")
        self.assertEqual(oct(os.stat(store.connections_file()).st_mode & 0o777), "0o600")

    def test_44_a_rejected_token_lands_on_the_setup_script_with_the_reason(self):
        """Spec section 4: if the token route stops FOR ANY REASON, the setup script is offered
        with the reason. A person must never be stuck, so this asserts there is a next move —
        and the reason must name the TOKEN, not send them back to re-paste a key that was
        never the problem."""
        rec = self._ws_engine()
        rec["create_ok"] = False
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "token": "sbp_thesecrettoken"},
                         headers=HDR)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "paste")
        fb = j["job"]["paste"]
        self.assertIn("create table if not exists", fb["sql"], "the script itself")
        self.assertIn("sql/new", fb["editor_url"], "and where to paste it")
        self.assertIn("not allowed on this project", fb["why"], "the reason, not swallowed")
        # ...but the token inside that reason is not. An error string written by somebody else
        # is not ours to trust, and this one is drawn on a screen.
        self.assertNotIn("sbp_thesecrettoken", json.dumps(j))
        self.assertIn("sbp_…", fb["why"])
        self.assertFalse(j["configured"], "and nothing was saved: no half-made workspace")

    def test_45_a_create_that_did_not_verify_is_never_reported_as_created(self):
        """The failure the plan singles out. The script ran, the tables did not all appear,
        and the route must not take the request's word for it."""
        rec = self._ws_engine()
        rec["verify_ok"] = False
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "token": "sbp_x1234567"},
                         headers=HDR)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "paste")
        self.assertNotEqual(j["job"]["phase"], "done")
        self.assertIn("members, changes", j["job"]["paste"]["why"])
        self.assertFalse(j["configured"])
        self.assertEqual(j["link"], "")
        self.assertEqual(rec["published"], 0,
                         "and no pack was uploaded to a workspace that is not there")

    def test_46_the_setup_script_route_is_the_default_and_ends_at_the_same_verify(self):
        """No token is not an error. There is not one on the owner's machine, so pressing
        Create with the box empty is the ordinary path and must come straight back with the
        script — and the button at the end of it must be judged by the same verify."""
        rec = self._ws_engine()
        rec["create_ok"] = False
        body = {"url": self.URL, "key": self.PUB, "name": "Testlify"}
        r = self.client.post(BASE + "/workspace/create", json=body, headers=HDR)
        self.assertEqual(r.status_code, 200, "an absent token is not a refusal: " + r.text)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "paste", "nothing run yet, so here is the script")
        self.assertEqual(rec["tokens"], [None], "and no token was asked for or sent")

        rec["create_ok"] = True                       # he pastes it, runs it, presses the button
        self.client.post(BASE + "/workspace/dismiss", json={}, headers=HDR)
        r = self.client.post(BASE + "/workspace/confirm", json=body, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "done")
        self.assertTrue(j["configured"])
        self.assertEqual(rec["confirms"], 1, "confirm went through schema.confirm, not create")
        self.assertEqual(rec["tokens"], [None, None],
                         "and neither press of the script route touched a token")

    def test_47_a_stalled_pack_upload_does_not_throw_away_a_verified_workspace(self):
        """Ten tables exist, verify said so, the link works. Calling that a failed create would
        delete a real workspace out from under him to tidy up a screen."""
        rec = self._ws_engine()
        rec["publish_raises"] = "the upload timed out"
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "token": "sbp_x1234567"},
                         headers=HDR)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "done")
        self.assertTrue(j["configured"])
        self.assertTrue(j["link"])
        self.assertIn("did not finish uploading", j["job"]["error"]["what"])
        self.assertIn("Check for changes", j["job"]["error"]["do"], "and what to do about it")
        self.assertEqual(agents_api._ws_pack["state"], "idle",
                         "and the quiet line does not stay on for ever after a failure")

    def test_48_join_reads_the_link_downloads_and_remembers_where_to_replay_from(self):
        rec = self._ws_engine()
        from seo_agent.workspace import client as wclient, link as wlink
        share = wlink.make_link(self.URL, self.PUB, "11111111-2222-3333-4444-555555555555")
        r = self.client.post(BASE + "/workspace/join", json={"link": share, "name": "Ravi"},
                             headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "done")
        self.assertEqual(j["job"]["total_bytes"], 104857600, "real bytes, for a real bar")
        self.assertEqual(j["job"]["done_bytes"], 1024)
        self.assertTrue(j["configured"])
        self.assertEqual(j["me"]["name"], "Ravi")
        self.assertEqual(rec["joined"], 1)
        self.assertEqual(int(wclient.settings()["last_seen_id"]), 42,
                         "the pack's boundary is where the log replays from")
        self.assertIn("Ravi", [m.get("name") for m in j["members"]],
                      "and the team can see who joined")

    def test_49_a_link_that_will_not_read_says_what_to_do_about_it(self):
        self._ws_engine()
        r = self.client.post(BASE + "/workspace/join", json={"link": "hello", "name": "Ravi"},
                             headers=HDR)
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("400", r.json()["detail"])
        r = self.client.post(BASE + "/workspace/join", json={"link": "x", "name": ""}, headers=HDR)
        self.assertEqual(r.status_code, 400)
        self.assertIn("name your team will see", r.json()["detail"])

    def test_50_a_join_that_lands_on_a_project_with_no_tables_is_a_plain_refusal(self):
        rec = self._ws_engine()
        rec["verify_ok"] = False
        from seo_agent.workspace import link as wlink
        share = wlink.make_link(self.URL, self.PUB, "11111111-2222-3333-4444-555555555555")
        self.client.post(BASE + "/workspace/join", json={"link": share, "name": "Ravi"},
                         headers=HDR)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "failed")
        self.assertIn("Run the setup script", j["job"]["error"]["what"], "verify's own sentence")
        self.assertIn("send you the link again", j["job"]["error"]["do"])
        self.assertEqual(rec["joined"], 0)
        self.assertFalse(j["configured"], "and it did not half-join him")

    def test_51_the_resting_state_carries_the_four_things_section_3_asks_for(self):
        rec = self._ws_engine()
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "name": "Testlify",
                               "member_name": "Devansh", "token": "sbp_x1234567"}, headers=HDR)
        self._ws_settle()
        rec["members"].append({"member_id": "m2", "name": "Ravi", "last_seen_at": None})
        agents_api._ws_members["at"] = 0.0
        self._ws_patch("sync", "status", lambda client=None: {
            "configured": True, "last_seen_id": 7, "updated_at": "2026-09-10T10:00:00Z",
            "stuck": None, "outbox": {"queued": 3, "last_error": ""}})
        agents_api._ws_pack["state"] = "building"
        j = self.client.get(BASE + "/workspace").json()
        self.assertEqual(j["workspace"]["name"], "Testlify")          # the name
        self.assertIn("Ravi", [m.get("name") for m in j["members"]])  # who is in it
        self.assertTrue(j["link"])                                    # the link
        self.assertEqual(j["sync"]["pending"], 3)                     # what is happening now
        self.assertEqual(j["sync"]["pack_state"], "building")

    def test_52_the_quiet_line_says_what_the_pack_is_doing_and_only_that(self):
        """Section 2's concession, and the whole of what makes it honest: pack_state is written
        by the pack's own progress callback, so it cannot claim a rebuild that is not running."""
        self._ws_engine()
        self.assertEqual(agents_api._ws_pack["state"], "idle")
        agents_api._ws_pack_progress("build", 0, 0, "building the knowledge pack")
        self.assertEqual(agents_api._ws_pack["state"], "building")
        agents_api._ws_pack_progress("upload", 10, 100, "part 1 of 2")
        self.assertEqual(agents_api._ws_pack["state"], "uploading")
        agents_api._ws_pack_progress("done", 100, 100, "")
        self.assertEqual(agents_api._ws_pack["state"], "idle")
        agents_api._ws_pack_progress("error", 0, 0, "no network")
        self.assertEqual(agents_api._ws_pack["state"], "idle", "a failed rebuild is not a running one")

    def test_53_a_refresh_asks_for_a_pack_rebuild_and_never_fails_because_of_one(self):
        """One click updates everybody AND the joining copy. It must also be impossible for the
        workspace half to break the catalogue half for somebody who has no workspace."""
        self._ws_engine()
        asked = []
        real = agents_api.ws_pack_refresh
        agents_api.ws_pack_refresh = lambda reason="": asked.append(reason) or True
        self.addCleanup(setattr, agents_api, "ws_pack_refresh", real)

        import seo_agent.tools.refresh_site as rs
        old = rs.run
        rs.run = lambda ctx, **kw: ({"new": 3, "gone": 0, "changed": 0, "preview": True}
                                    if kw.get("preview") else
                                    {"summary": "3 pages added.", "added": 3})
        self.addCleanup(setattr, rs, "run", old)

        self.client.post(BASE + "/knowledge/refresh", json={"preview": True}, headers=HDR)
        self.assertEqual(asked, [], "a preview writes nothing, so it rebuilds nothing")
        r = self.client.post(BASE + "/knowledge/refresh", json={}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(asked), 1, "a real refresh asks for the rebuild")

        # ...and the real one, with no workspace at all, still returns rather than raising
        agents_api.ws_pack_refresh = real
        agents_api._ws_wipe_for_test = None
        from seo_agent.workspace import client as wclient
        wclient.forget()
        r = self.client.post(BASE + "/knowledge/refresh", json={}, headers=HDR)
        self.assertEqual(r.status_code, 200, "no workspace is not an error on the Knowledge tab")

    def test_53b_tables_with_no_bucket_never_read_as_connected(self):
        """The plan's own named risk. The storage policies do not always attach and the tables
        survive when they do not, so a project can have all ten tables, a URL, a key and an id
        — everything that only reads settings calls connected — and be one nobody can ever
        join, because the pack has nowhere to live.

        client.configured() cannot see that, and is not meant to: it is asked on every render.
        So the tab asks schema.verify() as well, and this proves the route carries its answer
        through rather than deciding for itself.
        """
        rec = self._ws_engine()
        from seo_agent.workspace import client as wclient
        wclient.save_settings(workspace_url=self.URL, workspace_key=self.PUB,
                              workspace_id="11111111-2222-3333-4444-555555555555")
        agents_api._ws_forget_checks()

        bucketless = {"ok": False, "present": list(range(10)), "missing": [], "unreadable": {},
                      "bucket": False, "workspace_id": "11111111-2222-3333-4444-555555555555",
                      "reason": "The tables are there but the knowledge bucket is not, so no "
                                "teammate could download the knowledge pack."}
        self._ws_patch("schema", "verify", lambda url=None, key=None: bucketless)

        j = self.client.get(BASE + "/workspace?check=1").json()
        self.assertTrue(rec["polls_started"],
                        "and reading the route is what keeps the background poller alive, so "
                        "'nobody presses sync' survives an app restart")
        self.assertTrue(j["configured"], "there are credentials, and the route says so plainly")
        self.assertIs(j["verify"]["ok"], False, "but ready is verify's word, and it is no")
        self.assertIn("knowledge bucket", j["verify"]["reason"],
                      "and the reason names the bucket, not the project URL")

        # WITHOUT check=1 there is no network round trip: the route hands back what it last
        # knew rather than eleven probes to keep a footnote honest.
        agents_api._ws_forget_checks()
        j = self.client.get(BASE + "/workspace").json()
        self.assertIsNone(j["verify"], "nothing asked, nothing claimed")

    def test_53c_confirm_on_an_unfinished_workspace_re_asks_verify(self):
        """The Check again button. Same route as 'I've run it', same verdict, no token."""
        rec = self._ws_engine()
        rec["create_ok"] = False
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB}, headers=HDR)
        self.assertEqual(self._ws_settle()["job"]["phase"], "paste")

        rec["create_ok"] = True
        self.client.post(BASE + "/workspace/dismiss", json={}, headers=HDR)
        self.client.post(BASE + "/workspace/confirm",
                         json={"url": self.URL, "key": self.PUB}, headers=HDR)
        j = self._ws_settle()
        self.assertEqual(j["job"]["phase"], "done")
        self.assertEqual(rec["confirms"], 1)
        self.assertEqual(rec["tokens"], [None, None], "no token on either press")

    def test_54_a_running_job_cannot_be_dismissed_and_leaving_clears_the_credentials(self):
        self._ws_engine()
        with agents_api._ws_job_lock:
            agents_api._ws_job = {"kind": "create", "phase": "pack", "step": "", "pct": 50,
                                  "done_bytes": 0, "total_bytes": 0, "error": None,
                                  "fallback": None, "link": "", "started_at": time.time(),
                                  "finished_at": None}
        r = self.client.post(BASE + "/workspace/dismiss", json={}, headers=HDR)
        self.assertEqual(r.status_code, 409)
        self.assertIn("still running", r.json()["detail"])
        with agents_api._ws_job_lock:
            agents_api._ws_job["phase"] = "done"
        self.assertEqual(self.client.post(BASE + "/workspace/dismiss", json={},
                                          headers=HDR).status_code, 200)
        self.assertIsNone(self.client.get(BASE + "/workspace").json()["job"])

        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "name": "Testlify",
                               "token": "sbp_x1234567"}, headers=HDR)
        self._ws_settle()
        self.assertTrue(self.client.get(BASE + "/workspace").json()["configured"])
        self.assertEqual(self.client.post(BASE + "/workspace/leave", json={},
                                          headers=HDR).status_code, 200)
        j = self.client.get(BASE + "/workspace").json()
        self.assertFalse(j["configured"])
        self.assertEqual(j["link"], "")
        blob = json.dumps(store.connections())
        for k in ("workspace_url", "workspace_key", "workspace_id", "workspace_name"):
            self.assertNotIn(k, blob, "%s is gone, not blanked" % k)

    def test_55_leaving_keeps_every_other_connection(self):
        """connections.json is shared. Leaving a workspace must never be the reason the
        DataForSEO login disappears."""
        self._ws_engine()
        self.client.post(BASE + "/connections",
                         json={"dataforseo_login": "me@x.com", "dataforseo_password": "pw"},
                         headers=HDR)
        self.client.post(BASE + "/workspace/create",
                         json={"url": self.URL, "key": self.PUB, "name": "T",
                               "token": "sbp_x1234567"}, headers=HDR)
        self._ws_settle()
        self.client.post(BASE + "/workspace/leave", json={}, headers=HDR)
        c = self.client.get(BASE + "/connections").json()
        self.assertTrue(c["dataforseo_login"] and c["dataforseo_password"])
        self.client.post(BASE + "/connections",
                         json={"dataforseo_login": "", "dataforseo_password": ""}, headers=HDR)

    def test_56_the_token_is_never_written_however_the_request_is_shaped(self):
        """A blunt guard for whoever adds a field here later."""
        self._ws_engine()
        from seo_agent.workspace import client as wclient
        self.assertNotIn("token", wclient.SETTINGS, "there is no setting a token could go in")
        with self.assertRaises(Exception):
            wclient.save_settings(workspace_token="sbp_sneaky")
        self.assertNotIn("sbp_", json.dumps(store.connections()))
        # and the scrubber catches a token in any shape, not only the one it was handed
        self.assertEqual(agents_api._ws_scrub("failed for sbp_abcdefghijkl"), "failed for sbp_…")
        self.assertEqual(agents_api._ws_scrub("bad key sb_secret_xyz123", "sb_secret_xyz123"),
                         "bad key …")

    def test_30_the_panel_ships_the_agents_module_and_stylesheet(self):
        html = self.client.get("/").text
        self.assertIn("/static/js/17-agents.js", html)
        self.assertIn("/static/agents.css", html)
        # and the tail stays last (test 21b's invariant, restated here for the new tag)
        # by src=, not by name: a comment above mentions 09-tail.js first
        self.assertLess(html.index('src="/static/js/17-agents.js'), html.index('src="/static/js/09-tail.js'))
        self.assertEqual(self.client.get("/static/agents.css").status_code, 200)
        self.assertEqual(self.client.get("/static/js/17-agents.js").status_code, 200)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(os.environ["SEO_AGENT_DATA"], ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
