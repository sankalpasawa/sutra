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

    def test_10_a_message_starts_a_run_and_a_paid_tool_stops_for_approval(self):
        llm.call = ScriptedModel([
            {"text": "I'll find topics.", "tool_calls": [_tool("suggest_topics")], "raw": None},
        ])
        cid = self.client.post(BASE + "/chats", json={"title": "t"}, headers=HDR).json()["id"]
        r = self.client.post(BASE + "/chats/%s/send" % cid, json={"text": "Suggest topics"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["run_id"]
        s = _settle(self.client, cid, rid, ("waiting",))
        self.assertEqual(s["waiting_on"]["kind"], "approval")
        self.assertEqual(s["waiting_on"]["tool"], "suggest_topics")
        self.assertEqual(s["waiting_on"]["cost_credits"], 3)
        self.assertEqual(s["request"], "Suggest topics", "the full request is kept on the run")
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
        llm.call = ScriptedModel([{"text": "Understood, I'll stop here.", "tool_calls": [], "raw": None}])
        r = self.client.post(BASE + "/chats/%s/send" % cid, json={"text": "no, too expensive"}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["answered"])
        self.assertEqual(r.json()["run_id"], rid, "same run, no new one")
        s = _settle(self.client, cid, rid, ("done",))
        self.assertEqual(s["credits_spent"], 0, "declined means nothing spent")
        ev = self.client.get(BASE + "/runs/%s/%s/events" % (cid, rid)).json()["events"]
        res = [e for e in ev if e["type"] == "resumed"]
        self.assertEqual(res[0].get("approved"), False)
        self.assertEqual(res[0].get("answer"), "no, too expensive")
        # and the model saw the reason
        msgs = store.get_messages(cid)
        last_result = msgs[-2]["content"][0]["content"]
        self.assertEqual(last_result.get("user_said"), "no, too expensive")

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
        store.save_artifact(cid, rid, "blueprint.json", {"title": "Hello there"})
        r = self.client.post(BASE + "/runs/%s/%s/publish" % (cid, rid), json={}, headers=HDR)
        self.assertEqual(r.status_code, 200, r.text)
        item = r.json()["item_id"]
        lib = self.client.get(BASE + "/library").json()
        self.assertTrue(any(i["id"] == item and i["title"] == "Hello there" for i in lib))
        one = self.client.get(BASE + "/library/%s" % item).json()
        self.assertIn("A body.", one["draft"])
        r = self.client.post(BASE + "/library/%s/status" % item, json={"status": "ready"}, headers=HDR)
        self.assertEqual(r.json()["status"], "ready")
        r = self.client.post(BASE + "/library/%s/status" % item, json={"status": "evil"}, headers=HDR)
        self.assertEqual(r.json()["status"], "draft", "unknown statuses fall back to draft")
        self.assertTrue(self.client.post(BASE + "/library/%s/delete" % item, headers=HDR).json()["ok"])
        self.assertEqual(self.client.get(BASE + "/library/%s" % item).status_code, 404)

    # ---- settings ---------------------------------------------------------------------

    def test_20_connections_never_echo_secrets_and_refuse_api_keys(self):
        r = self.client.post(BASE + "/connections", json={"dataforseo_login": "me@x.com", "dataforseo_password": "pw",
                                                          "anthropic_key": "sk-should-never-stick"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        j = self.client.get(BASE + "/connections").json()
        self.assertEqual(j, {"dataforseo_login": True, "dataforseo_password": True})
        self.assertNotIn("sk-should", json.dumps(j))
        on_disk = store.connections()
        self.assertNotIn("anthropic_key", on_disk, "an API key is dropped, the panel bills the subscription")
        mode = oct(os.stat(store.connections_file()).st_mode & 0o777)
        self.assertEqual(mode, "0o600", "secrets are owner-only")
        self.assertTrue(self.client.get(BASE + "/health").json()["dataforseo"])
        # clearing
        self.client.post(BASE + "/connections", json={"dataforseo_login": "", "dataforseo_password": ""}, headers=HDR)
        self.assertEqual(self.client.get(BASE + "/connections").json(),
                         {"dataforseo_login": False, "dataforseo_password": False})

    def test_21_memory_add_toggle_and_list(self):
        r = self.client.post(BASE + "/memory", json={"text": "Never open with a question", "kind": "rule"}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        mid = r.json()["id"]
        self.assertEqual(self.client.post(BASE + "/memory", json={"text": "  "}, headers=HDR).status_code, 400)
        self.client.post(BASE + "/memory/%s/toggle" % mid, json={"active": False}, headers=HDR)
        m = self.client.get(BASE + "/memory").json()
        row = [x for x in m["rules"] if x["id"] == mid][0]
        self.assertFalse(row["active"])

    def test_22_tools_list_carries_gates_and_costs_but_no_module_paths(self):
        tools = self.client.get(BASE + "/tools").json()
        names = {t["name"] for t in tools}
        self.assertIn("run_research", names)
        rr = [t for t in tools if t["name"] == "run_research"][0]
        self.assertEqual(rr["gate"], "ask_before")
        self.assertEqual(rr["cost_credits"], 8)
        self.assertNotIn("module", rr)

    def test_23_knowledge_round_trip(self):
        r = self.client.post(BASE + "/knowledge", json={"competitors": {"competitors": ["a.com", "b.com"]}}, headers=HDR)
        self.assertEqual(r.status_code, 200)
        k = self.client.get(BASE + "/knowledge").json()
        self.assertEqual(k["competitors"]["competitors"], ["a.com", "b.com"])

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
