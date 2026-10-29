"""A5 P4.1: shadow_graph.build()/detail() on seeded missions, goals and conversations (isolated SUTRA_SHADOW_HOME).

SOURCE TABLE (A5.2.1, finding F6): every node and edge kind, the file, function and field it reads. VERIFIED means read in this
checkout; P3 means the field is written by P3 (department create-or-reuse) and is absent on main, so it is read tolerantly (absent: no
department edge) and exercised here through the stored mission fields the fixtures write.

  node shadow       the single Now session           constant id shadow:now                              (no source)
  node conversation shadow_conversations.list_all()   rec['id'] (shc-...), rec['title'], rec['mission_id'] set by bind_mission()   VERIFIED
  node goal         goal_store.GoalStore().list()     goal['id'], ['outcome'], ['state']; mission['goal_id'] from MissionStore.create VERIFIED
  node task         mission_engine.MissionStore().list()  mission['id'], ['objective'], ['state'], ['created_at'], ['updated_at']   VERIFIED
  node task_chat    mission['task_chat_session'] stamped by app._publish_task_chat (_stamp(task_chat_session=sid)); 'task_chat' = sutra id  VERIFIED
  node worker       mission['target_session'], mission['target_mode'] ('existing'|'new') from MissionStore.create    VERIFIED
                    not drawn when mission['executor'] == 'department'                                                    P3
  node department   mission['department_decision'] (final_ref / result_ref), else mission['department_ref']; DeptRow from dept_read.rows  P3
  cost              shadow_costs.by_mission() {mid: usd}; per role shadow_costs._rows() kind now|shadow|worker             VERIFIED
  timeline          shadow_ledger.read_for_mission('missions'|'actions', mid) fields ts, state, note, kind, summary          VERIFIED
  edge has          shadow -> task, shadow -> unbound conversation      derived
  edge opened       conversation -> task                                 conversation['mission_id']
  edge attempt      goal -> task                                         mission['goal_id']
  edge steered_by   task -> task_chat                                    mission['task_chat_session']
  edge driven_by    task -> worker                                       mission['target_session']
  edge uses/spawned task -> department                                   decision final_action use / create (reason, confidence)
Left out, not verified: founder_says and revisions rows on the timeline.
"""
import json
import time
from pathlib import Path

import pytest

import layer_schema
import mission_engine as ME

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "shadow_graph_sample.json").read_text(encoding="utf-8"))
ROOT = "dref-root0001"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_SHADOW_HOME", str(tmp_path))
    import shadow_graph as G
    monkeypatch.setattr(G, "dept_read", None)
    G.clear()
    yield G
    G.clear()


def row(ref, name, state="idle", stopped=False, kind="default"):
    r = dict(SAMPLE["detail"]["departments"][0])
    r.update(ref=ref, name=name, state=state, stopped=stopped, kind=kind)
    return r


class FakeDeptRead:
    def __init__(self, rows, sig="s1"):
        self._rows, self.sig = rows, sig

    def rows(self, root):
        return list(self._rows)

    def signature(self):
        return self.sig


def decision(mid, ref, action="use", **kw):
    d = json.loads(json.dumps(SAMPLE["decision"]))
    d["mission_id"] = mid
    d["final_action"] = action
    d["choice"]["action"] = action
    if action == "use":
        d["final_ref"] = ref
        d["choice"]["ref"] = ref
    else:
        d["final_ref"] = None
        d["choice"] = {"action": "create", "kind": "organic", "name": "Reports", "goal": "Weekly reports", "reason": "No department covers recurring reports",
                       "confidence": "medium"}
        d["result_ref"] = ref
    d.update(kw)
    return d


def mission(state="running", objective="Fix the login bug", **fields):
    s = ME.MissionStore()
    m = s.create(objective, list(ME.templates())[0], target_session=fields.pop("target_session", "sess-1"))
    m.update(fields)
    m["state"] = state
    s.save(m)
    return s.load(m["id"])


def age(m, stamp):
    """save() stamps updated_at itself, so the file is rewritten."""
    path = Path(ME._home()) / (m["id"] + ".json")
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["updated_at"] = stamp
    path.write_text(json.dumps(rec), encoding="utf-8")


def kinds(g, key):
    return sorted(x["kind"] for x in g[key])


def test_01_empty_has_only_shadow(env):
    g = env.build()
    assert [n["kind"] for n in g["nodes"]] == ["shadow"] and g["edges"] == [] and g["shadow_on"] is True


def test_02_task_with_chat_worker_goal_and_conversation(env):
    import goal_store
    import shadow_conversations as C
    goal = goal_store.GoalStore().create("Keep the app healthy", "sess-9")
    m = mission(task_chat_session="sess-2", goal_id=goal["id"])
    C.create("shc-a1b2c3", "Is it slow?")
    C.bind_mission("shc-a1b2c3", m["id"])
    C.create("shc-d4e5f6", "Another thought")
    g = env.build()
    assert kinds(g, "nodes") == ["conversation", "conversation", "goal", "shadow", "task", "task_chat", "worker"]
    assert kinds(g, "edges") == ["attempt", "driven_by", "has", "has", "opened", "steered_by"]
    assert layer_schema.validate("shadow.graph", g) == []
    byid = {n["id"]: n for n in g["nodes"]}
    assert byid["task:" + m["id"]]["status"] == "working" and byid["task:" + m["id"]]["open"] == {"kind": "task", "ref": m["id"]}
    assert byid["worker:" + m["id"]]["open"] == {"kind": "session", "ref": "sess-1"} and byid["worker:" + m["id"]]["label"] == "Your chat"
    assert byid["conv:shc-d4e5f6"]["row"] > byid["task:" + m["id"]]["row"], "unbound conversations sit below the tasks"
    assert [e["source"] for e in g["edges"] if e["kind"] == "opened"] == ["conv:shc-a1b2c3"]


@pytest.mark.parametrize("state,status", [("draft", "draft"), ("brief_confirm", "draft"), ("queued", "waiting"), ("running", "working"),
                                         ("paused", "waiting"), ("blocked", "blocked"), ("done", "done"), ("failed", "failed"), ("stopped", "stopped")])
def test_03_status_map(env, state, status):
    mission(state=state)
    assert [n["status"] for n in env.build(include_done=True)["nodes"] if n["kind"] == "task"] == [status]


def test_04_states_are_the_engines(env):
    import layer_models.a5_graph as A
    assert set(A.TASK_STATES) == set(ME.STATES) and set(env.TASK_STATUS) == set(ME.STATES)


def test_05_uses_and_spawned_carry_reason_and_confidence(env, monkeypatch):
    a, b = mission(), mission(state="queued", objective="Weekly sales report")
    for m, d in ((a, decision(a["id"], "dref-billing01")), (b, decision(b["id"], "dref-reports01", action="create"))):
        m["department_decision"] = d
        ME.MissionStore().save(m)
    monkeypatch.setattr(env, "dept_read", FakeDeptRead([row("dref-billing01", "Billing"), row("dref-reports01", "Reports", kind="organic")]))
    g = env.build()
    es = {e["kind"]: e for e in g["edges"] if e["kind"] in ("uses", "spawned")}
    assert es["uses"]["reason"].startswith("Billing already") and es["uses"]["confidence"] == "high" and not es["uses"]["held"]
    assert es["spawned"]["target"] == "dept:dref-reports01" and es["spawned"]["confidence"] == "medium"
    assert layer_schema.validate("shadow.graph", g) == []


def test_06_held_edge_and_stopped_department_is_off(env, monkeypatch):
    m = mission()
    m["department_decision"] = decision(m["id"], "dref-collect01", held=True, held_reason="stopped",
                                        overrides=[{"rule": "stopped", "note": "Collections is Off"}])
    ME.MissionStore().save(m)
    monkeypatch.setattr(env, "dept_read", FakeDeptRead([row("dref-collect01", "Collections", state="stopped", stopped=True)]))
    g = env.build()
    e = [x for x in g["edges"] if x["kind"] == "uses"][0]
    assert e["held"] is True and e["reason"] == "Held: Collections is Off"
    assert [n["status"] for n in g["nodes"] if n["kind"] == "department"] == ["off"]


def test_07_missing_department_row_is_off_never_idle(env):
    m = mission(department_ref="dref-gone0001")
    g = env.build()
    d = [n for n in g["nodes"] if n["kind"] == "department"][0]
    assert d["status"] == "off" and d["tip"] == "Record not found" and d["label"] == "dref-gone0001"
    assert layer_schema.validate("shadow.graph", g) == []


def test_08_no_decision_or_none_means_no_department_edge(env):
    a = mission()
    b = mission()
    d = decision(b["id"], None, action="none")
    d["final_ref"] = None
    d["choice"] = {"action": "none", "reason": "No department needed", "confidence": "high"}
    b["department_decision"] = d
    ME.MissionStore().save(b)
    g = env.build()
    assert not [e for e in g["edges"] if e["kind"] in ("uses", "spawned")] and not [n for n in g["nodes"] if n["kind"] == "department"]


def test_09_a_decision_that_does_not_fit_is_not_drawn(env):
    m = mission()
    m["department_decision"] = {"choice": "junk"}
    ME.MissionStore().save(m)
    assert not [n for n in env.build()["nodes"] if n["kind"] == "department"]


def test_10_a_department_used_twice_sits_at_the_mean_row_and_rows_do_not_collide(env, monkeypatch):
    ms = [mission(objective="Task %d" % i) for i in range(3)]
    for m in ms[:2]:
        m["department_decision"] = decision(m["id"], "dref-billing01")
        ME.MissionStore().save(m)
    monkeypatch.setattr(env, "dept_read", FakeDeptRead([row("dref-billing01", "Billing")]))
    g = env.build()
    assert [n["id"] for n in g["nodes"] if n["kind"] == "department"] == ["dept:dref-billing01"]
    pos = [(n["col"], n["row"]) for n in g["nodes"]]
    assert len(pos) == len(set(pos)), "no two nodes share a cell"


def test_11_executor_department_draws_no_worker(env):
    mission(executor="department")
    assert not [n for n in env.build()["nodes"] if n["kind"] == "worker"]


def test_12_terminal_visibility_and_cap(env):
    old = mission(state="done", objective="Old")
    age(old, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 86400)))
    ancient = mission(state="done", objective="Ancient")
    age(ancient, "2020-01-01T00:00:00Z")
    fresh = mission(state="done", objective="Fresh")
    labels = lambda g: sorted(n["label"] for n in g["nodes"] if n["kind"] == "task")
    assert labels(env.build()) == ["Fresh"], "include_done=0 hides all but the last hour's"
    env.clear()
    assert labels(env.build(include_done=True)) == ["Fresh", "Old"], "finished tasks past 7 days are not drawn"


def test_13_more_than_sixty_tasks_are_cut_and_flagged(env):
    for i in range(62):
        mission(objective="T%d" % i)
    g = env.build()
    assert len([n for n in g["nodes"] if n["kind"] == "task"]) == 60 and g["truncated"] is True
    assert max(n["row"] for n in g["nodes"]) <= 399


def test_14_unbound_conversations_newest_twenty(env):
    import shadow_conversations as C
    for i in range(25):
        C.create("shc-aaaa%02d" % i, "Thought %d" % i)
    assert len([n for n in env.build()["nodes"] if n["kind"] == "conversation"]) == 20


def test_15_focus_draws_one_task_and_unknown_focus_falls_back(env):
    a, b = mission(), mission(objective="Other")
    g = env.build(focus=a["id"])
    assert g["focus"] == a["id"] and [n["id"] for n in g["nodes"] if n["kind"] == "task"] == ["task:" + a["id"]]
    assert env.build(focus="m-0123456789ab")["focus"] is None


def test_16_a_deleted_mission_and_a_torn_file_are_not_drawn(env, tmp_path):
    m = mission()
    (tmp_path / "missions" / "m-ffffffffffff.json").write_text("{torn", encoding="utf-8")
    ME.MissionStore().delete(m["id"]) if hasattr(ME.MissionStore, "delete") else (tmp_path / "missions" / (m["id"] + ".json")).unlink()
    assert [n["kind"] for n in env.build()["nodes"]] == ["shadow"]


def test_17_layout_is_deterministic(env):
    for i in range(4):
        mission(objective="T%d" % i)
    env.clear()
    a = env.build()
    env.clear()
    b = env.build()
    strip = lambda g: [(n["id"], n["col"], n["row"]) for n in g["nodes"]]
    assert strip(a) == strip(b)


def test_18_detail_sections(env, monkeypatch):
    import shadow_costs
    import shadow_ledger
    m = mission(task_chat_session="sess-2")
    m["department_decision"] = decision(m["id"], "dref-billing01", at=m["created_at"])
    ME.MissionStore().save(m)
    monkeypatch.setattr(env, "dept_read", FakeDeptRead([row("dref-billing01", "Billing")]))
    shadow_costs.record("sess-1", m["id"], 0.10, "worker", proc_key="a")
    shadow_costs.record("sess-3", m["id"], 0.02, "shadow", proc_key="b")
    shadow_ledger.append("actions", {"mission_id": m["id"], "kind": "decision", "summary": "ask_founder: which file?"})
    d = env.detail(m["id"])
    assert layer_schema.validate("shadow.task_detail", d) == []
    assert d["task"]["id"] == m["id"] and d["graph"]["focus"] == m["id"]
    assert d["decision"]["final_ref"] == "dref-billing01" and [x["ref"] for x in d["departments"]] == ["dref-billing01"]
    assert {c["role"] for c in d["chats"]} == {"shadow_chat", "worker", "department_page"}
    assert {c["role"]: c["usd"] for c in d["costs"]} == {"worker": 0.1, "shadow": 0.02} and d["total_usd"] == 0.12
    kinds_ = [t["kind"] for t in d["timeline"]]
    assert kinds_[0] == "said" and "state" in kinds_ and "decided" in kinds_ and "department" in kinds_
    assert [t["at"] for t in d["timeline"]] == sorted(t["at"] for t in d["timeline"])


def test_19_detail_of_unknown_task_is_none(env):
    assert env.detail("m-0123456789ab") is None and env.detail("junk") is None


def test_20_memo_validates_once_per_tick(env, monkeypatch):
    mission()
    calls = []
    real = env._validate
    monkeypatch.setattr(env, "_validate", lambda n, v: (calls.append(n), real(n, v))[1])
    env.build()                                        # the first read may make the stores' directories: not kept
    calls.clear()
    a = env.build()
    b = env.build()
    assert a is b and calls == ["shadow.graph"]
    mission(objective="Another")                       # a save moves the missions directory: the memo is dropped
    assert len([n for n in env.build()["nodes"] if n["kind"] == "task"]) == 2 and calls == ["shadow.graph"] * 2


def test_21_dept_read_failing_falls_back_to_refs(env, monkeypatch):
    class Boom:
        def rows(self, root):
            raise RuntimeError("down")
    monkeypatch.setattr(env, "dept_read", Boom())
    mission(department_ref="dref-x0001")
    assert [n["status"] for n in env.build()["nodes"] if n["kind"] == "department"] == ["off"]
