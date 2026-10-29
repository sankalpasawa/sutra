"""a5_seed.py -- the records the A5 walk looks at (PRD A5.8 P5, step P5.1): one department of each kind, three tasks, a conversation, a goal.

    python qa/walks/a5_seed.py <record-dir> [--missions N]

Writes the department records where qa/walks/devserver.sh reads them (native/, registry/, proposals/, chats/) and the Shadow records
to <record-dir>/shadow (SUTRA_SHADOW_HOME), and prints one `name value` line each for the walk to read:

    root, default, organic, website   the refs: Acme Root, Billing (default), Notes (organic), a website department
    task_use      m-...  a task whose decision is `use` Billing                   (the graph draws `uses`, solid)
    task_spawn    m-...  a task whose decision is `create` Reports, the model stubbed (CHOOSER), the department made by founding.spawn
                         (the graph draws `spawned`, dashed)
    task_none     m-...  a task whose decision is `none`
    conversation  shc-.. a Shadow conversation opened on the first task          goal   g-...  a goal the second task is an attempt at
    settings      the settings file of this record (the walk sets SUTRA_UI_SETTINGS to it)

Nothing here calls a model (the tasks are paused, so the app's Shadow starts no chat or worker for them): the choice is the stub's, the offline functions answer, and no path leaves <record-dir>. With --missions N the
record also holds N further finished tasks, for the graph read-time measure (P5.5). Nothing outside the record is read or written."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parents[1]
for p in (str(UI), str(UI / "test_fixtures" / "j2ui")):
    if p not in sys.path:
        sys.path.insert(0, p)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--missions", type=int, default=0)
    a = ap.parse_args(argv)
    rec = Path(a.record).resolve()
    rec.mkdir(parents=True, exist_ok=True)
    os.environ["SUTRA_SHADOW_HOME"] = str(rec / "shadow")
    os.environ["SUTRA_UI_SETTINGS"] = str(rec / "settings.json")
    os.environ["SUTRA_MOTOR_OFF"] = "1"
    (rec / "settings.json").write_text('{"onboarded": true}\n', encoding="utf-8")      # no first-run card over the screens the walk photographs
    import seed as SEED
    m = SEED.boot(rec, layout="walk")
    import founding
    import placement_engine as E
    import mission_engine as ME
    import dept_read
    import shadow_dept
    import shadow_conversations as C
    import goal_store
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    root = founding.found_structure("Acme", owner="the owner")["root"]
    billing = founding.spawn(root, "Billing", "default", "Answer billing questions and keep the invoices filed for every customer")["ref"]
    notes = founding.spawn(root, "Notes", "organic", "Keep the meeting notes and the decisions they hold, in its own way")["ref"]
    site = founding.spawn(root, "City Care Hospital Website", "website", "Build a website that teaches algebra to Class 8 students")["ref"]
    for ref in (billing, notes, site):                  # born an hour ago: DR-6 counts the creates of the last ten minutes, and the walk's own is one
        rd = m.W.dept(ref)
        rd["created"] = "2026-10-29T09:00:00Z"
        m.W.save_dept(ref, rd)
    dept_read.forget()

    store = ME.MissionStore()
    tpl = list(ME.templates())[0]

    def task(objective, state="paused", **fields):
        t = store.create(objective, tpl, target_session="sess-a5")
        t.update(fields)
        t["state"] = state
        store.save(t)
        return t["id"]

    goal = goal_store.GoalStore().create("Keep the invoices filed", "sess-a5")
    use = task("Reply to the invoice dispute from a customer about last month's billing", task_chat_session="sess-a5-chat")
    spawn = task("Write the weekly sales report and send it to the owner each Monday", goal_id=goal["id"])
    none = task("Fix the typo on the settings page", state="paused")
    C.create("shc-a5walk1", "Is the billing dispute sorted?")
    C.bind_mission("shc-a5walk1", use)

    def stub(text):
        task = text.split("DEPARTMENTS THIS ORGANISATION HAS")[0]       # the question lists the departments too: read the task's part only
        if "typo on the settings page" in task:
            return json.dumps({"action": "none", "reason": "a one-line fix needs no department", "confidence": "medium"})
        if "invoice dispute" in task:
            return json.dumps({"action": "use", "ref": billing, "reason": "Billing files the invoices and answers disputes", "confidence": "high"})
        if "weekly sales report" in task:
            return json.dumps({"action": "create", "kind": "default", "name": "Reports", "goal": "Write the weekly sales report each Monday",
                               "reason": "no department writes recurring reports", "confidence": "high", "done_items": ["Each report is sent"]})
        return json.dumps({"action": "none", "reason": "a one-line fix needs no department", "confidence": "medium"})

    shadow_dept.CHOOSER["fn"] = stub
    loop = asyncio.new_event_loop()
    try:
        for mid in (use, spawn, none):
            loop.run_until_complete(shadow_dept.decide_and_apply(store.load(mid), root_ref=root))
    finally:
        loop.close()
        shadow_dept.CHOOSER["fn"] = None
    for i in range(a.missions):
        t = task("Seeded task %d for the read-time measure" % i)
        t2 = store.load(t)
        t2["state"] = "done"
        store.save(t2)
    for k, v in (("root", root), ("default", billing), ("organic", notes), ("website", site), ("task_use", use), ("task_spawn", spawn),
                 ("task_none", none), ("conversation", "shc-a5walk1"), ("goal", goal["id"]), ("settings", str(rec / "settings.json"))):
        print(k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
