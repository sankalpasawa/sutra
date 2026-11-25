"""Offline checks of how J2 treats the programs it builds and runs: python own_runs_test.py

Each is modelled on a run of the Pulse agent that went wrong (the engineering runs 3429 and 87be, the pulse run 52c5).

(A) an agent stage after the documents is a program, not a document: it starts with its own intake and its charter
    names its files and its test (87be: "Next: the PULSE_AGENT, written from the HLD's agent_output", a charter with
    no files and no test); a folder's open problems never list the browser check (52c5: "the browser check didn't
    run"), a page's still do; code's workable messages name a folder by its own noun, a page stays "site";
(B) Decide for me goes by subject: a question about a real run, an install or the folder a real run uses is never
    answered, whatever its kind (52c5: "Is ... the folder where the install and the read of your mail should run?"
    was answered "Yes, that folder is right"), and code says so once; a question tagged with a real-run item, and a
    decision whose leave-out option names one, wait too; a limit question and a pending real-run question wait; an
    ordinary question is still answered and nothing is dropped;
(C) an approved real run that prints and writes out.json leaves a run-output record: the exit code, the end of its
    output, out.json (created, its size, hash and text) and the file it changed; the receipt names the record, and
    artifacts.json lists it; a declined run leaves none;
(D) C2 finds the test the builder wrote: a charter that names no test falls back to the workflow's test check
    (87be: "the test '' is not a file in the folder"), for a builder writing tests/test_x.py with checks naming
    tests/test_x.py, and for the run-relative form (3429: copy_script/tests/test_x.py); a list target is checked
    item by item (87be: a list of files was read as one file name); a recheck without a folder keeps the folder
    (87be: "unknown check test-passed"); a workflow whose checks mix the two forms is refused, and one that names
    every file with the folder in front has it taken off;
(E) a requirements.txt that names no package plans no environment and asks nothing (52c5: an install card with an
    empty package list); after a declined install a test that needs only the standard library and the folder's own
    modules is still rerun, and one that imports the package is not.

No AI calls and no network: the builder's files are written by the test, a fake python stands in for the interpreter.
Nothing is written outside temp folders.
"""
import json
import os
import shutil
import stat
import sys
import tempfile

import j2_flow_test as t          # sets STUDIO_MOCK, J2_MEMORY=0, temp runs and library folders
import j2                          # noqa: E402
import j2_artifacts                # noqa: E402
import j2_runenv                   # noqa: E402

passed = 0
FT = t.FT
TMP = tempfile.mkdtemp(prefix="j2-own-runs-")
KEYS = ("J2_AGENT_TOOLS", "J2_DATA_DIR", "J2_RUN_PYTHON", "J2_SANDBOX", "J2_SANDBOX_CMD")
PRINTS = ("import json, os, sys\nprint('read 3 threads')\nsys.stderr.write('1 warning\\n')\n"
          "json.dump({'threads': 3}, open(os.path.join(sys.argv[1], 'out.json'), 'w'))\n"
          "open(os.path.join(sys.argv[1], 'mail.txt'), 'a').write(' two')\n")
TEST_OK = "import unittest\nimport helper\nassert helper.VALUE == 1\nprint('OK')\n"
TEST_NEEDS = "import pulsedep\nprint('OK')\n"


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


def receipts(run, kind="real_run"):
    try:
        return [r for r in map(json.loads, open(os.path.join(run.dir, "receipts.jsonl"))) if r.get("type") == kind]
    except OSError:
        return []


def system(run):
    return [m["text"] for m in run.chat if m["who"] == "system"]


def write(folder, files):
    for name, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(folder, name)) or folder, exist_ok=True)
        open(os.path.join(folder, name), "w").write(text)


def made(files, checks, goal=None, real=None):
    """A run of the folder type with one built workflow: its files in the folder, its checks on its atom."""
    run = j2.J2Run()
    run.set_output(FT)
    run.goal = goal or {"statement": "read the folder", "done_when": ["the script has been run on the folder"]}
    run.budget = 300
    os.makedirs(run._out_dir(), exist_ok=True)
    write(run._out_dir(), files)
    w = {"id": "W-1", "name": "reader", "purpose": "read", "outputs": [f"{FT}/s.py"], "status": "done", "calls_used": 1,
         "retries_used": 0, "cost": 10, "cycle": 1, "section": "W-1", "covers": [], "build_attempts": 1,
         **({"real_run": {"command": ["python3", "s.py", real], "folder": real, "why": "read it", "checks": [1]}} if real else {}),
         "atoms": [{"id": "W-1.a1", "goal": "read", "expected_output": [], "verification": checks}]}
    run.workflows = [w]
    j2.add_workflow_agent("W-1")
    run.sites = ["v1"]
    run.post("user", "go")
    return run, w


def check(kind, target):
    return {"text": f"{kind} {target}", "type": kind, "target": target, "expect": True}


def reply(run, text):
    h = run.paused["handoff"]
    run.post("user", text)
    run.paused = None
    run._turn_identity({**h, "answer": text})


@t.with_folder_type
def agent_stage_is_a_program():
    run = j2.J2Run()
    run.set_output("prd")
    run.request = "Build a script for Pulse, with a PRD first."
    run.post("user", run.request)
    base = {"statement": "A PRD for Pulse", "product_name": "Pulse", "site_name": "Pulse", "business_type": "prd",
            "done_when": ["The Problem section is written for Pulse"]}
    run.goal, run.docset = base, ["prd"]
    run.stages, run.stage_i, run.stage_archive = ["prd", FT], 1, [{"stage": "prd", "goal": base, "audits": [], "sections": {}}]
    run._begin_stage(FT, base)
    ok(run.folder and run.goal is None and run.turn == "identity" and run.handoff.get("kind") == "intake",
       f"(A) the agent stage starts with its own intake, no charter made by code: {run.turn} {run.handoff} {run.goal}")
    ok(system(run)[-1] == "The documents are done. Now the script, built from them.", f"(A) the chat says so: {system(run)[-1]}")
    ok(not any("written from the" in x for x in system(run)), "(A) never 'written from the HLD's agent_output'")
    run._turn_identity(run.handoff)
    g = run.goal or {}
    ok(g.get("files") == ["main.py", "test_main.py", "README.md"] and g.get("test") == "test_main.py",
       f"(A) its charter names its files and its test: {g.get('files')} {g.get('test')}")
    ok(g.get("statement") != f"An {FT.upper()} for Pulse" and "item_checks" not in g, "(A) it is not stage_goal's document charter")
    # the browser check: a page's, never a folder's
    audit = {"version": 1, "output": FT, "results": [], "rubric": [], "conditions": [], "mechanical": {}}
    run.sites = ["v1"]
    ok("the browser check didn't run" not in run._open_list(audit, []), f"(A) a folder's open problems: {run._open_list(audit, [])}")
    page = j2.J2Run()
    page.set_output("website")
    page.goal, page.sites = {"done_when": []}, ["v1"]
    ok("the browser check didn't run" in page._open_list({**audit, "output": "website"}, []), "(A) a page still lists its browser check")
    ok(run._thing() == j2.output_def(FT)["noun"] != "site" and page._thing() == "site", f"(A) code's words for the output: {run._thing()} {page._thing()}")
    print("an agent stage is a program: its own intake and charter (files, test), no browser check, its own noun ok")


@t.with_folder_type
def decide_for_me_by_subject():
    real = tempfile.mkdtemp(prefix="real-", dir=TMP)
    run, w = made({"s.py": "print('x')\n"}, [check("file-exists", "s.py")], real=real)
    run.auto = True
    ok("limit" in j2.AUTO_ASK and "real_run" in j2.AUTO_ASK, "(B) a limit question and a real-run question are never answered")
    folder_q = ("Is /Users/x/Documents/Pulse the folder where the agent should be written and where the install and "
                "the read of your mail should run?")
    for kind, q in (("question", folder_q), ("info", "May the team install what the script needs?"),
                    ("question", "Should the live read of the mailboxes go ahead now?"),
                    ("conflict", "Do you want the real run kept in the plan?")):
        run._ask_user("One thing to confirm.", [{"question": q, "options": ["Yes", "No"]}], kind, handoff={"kind": "x"})
        n = len(run.chat)
        ok(run._auto_pick() is None and run.paused and run.paused["kind"] == kind, f"(B) not answered ({kind}): {q}")
        ok(len(run.chat) == n + 1 and system(run)[-1].startswith("Decide for me did not answer this question: it is about "),
           f"(B) code says it waits: {system(run)[-1]}")
        run._auto_go()
        ok(run._auto_pick() is None and len(run.chat) == n + 1 and not any(m.get("auto") for m in run.chat),
           "(B) said once, and no answer is posted")
    ok(system(run)[-1].endswith("a real run. It waits for you."), f"(B) the reason is the subject: {system(run)[-1]}")
    # a question tagged with the item a real run decides; a decision whose leave-out option names that item
    run._ask_user("A fact.", [{"question": "Did it happen?", "kind": "decision", "item": 1, "options": ["Yes", "No"]}], "fact")
    ok(run._auto_pick() is None, "(B) a question tagged with a real-run item waits")
    item = run.goal["done_when"][0]
    run._ask_user("A choice.", [{"question": "Keep going or leave something out?", "options": ["Keep going", "Leave it out"]}],
                  "conflict", handoff={"kind": "x", "drop_texts": [item]})
    ok(run._auto_pick() is None, "(B) an option that leaves out a real-run item is never picked")
    ok(run.goal["done_when"] == [item] and not run.real_runs_done and not receipts(run), "(B) no item dropped, nothing closed")
    # a pending real-run question stays open
    run._ask_real_run({})
    ok(run.paused and run.paused["kind"] == "real_run" and run._auto_pick() is None, "(B) the real-run question waits")
    run._auto_go()
    ok(run.paused and run.paused["kind"] == "real_run" and not receipts(run) and run.goal["done_when"] == [item],
       "(B) still waiting: not approved, not declined, no item dropped")
    # an ordinary question is still answered, and the chat shows what was answered
    run._ask_user("One choice is up to you.", [{"question": "Which heading colour?", "options": ["Blue", "Green"]}],
                  "question", handoff={"kind": "x"})
    ok(run._auto_pick() == ("Option 1", "Blue", 1), f"(B) an ordinary question is answered: {run._auto_pick()}")
    print("Decide for me goes by subject: a real run, an install and a run's folder wait for the Requester; ordinary questions are answered ok")


@t.with_folder_type
def run_output_is_recorded():
    real = tempfile.mkdtemp(prefix="real-", dir=TMP)
    open(os.path.join(real, "mail.txt"), "w").write("one")
    open(os.path.join(real, "untouched.txt"), "w").write("same")
    keep = j2.secrets.token_hex
    j2.secrets.token_hex = lambda n=3: "a578a3"
    try:
        run, w = made({"s.py": PRINTS}, [check("file-exists", "s.py")], real=real)
        ok(run._ask_real_run({}) and run.paused["kind"] == "real_run", "(C) asked")
        reply(run, "RUN a578a3")
        r = receipts(run)[-1]
        ok(r["approved"] and r["ran"] and r["exit"] == 0 and r.get("run_output") == "run_output/W-1-1.json", f"(C) the receipt names the record: {r}")
        rec = json.load(open(os.path.join(run.dir, r["run_output"])))
        ok(rec["schema"] == "run-output/1" and rec["exit"] == 0 and rec["workflow"] == "W-1" and rec["folder"] == real,
           f"(C) the record has the exit code: {rec}")
        ok(rec["stdout"].strip() == "read 3 threads" and rec["stderr"].strip() == "1 warning", "(C) and the end of stdout and of stderr")
        files = {f["name"]: f for f in rec["files"]}
        ok(sorted(files) == ["mail.txt", "out.json"] and not rec["deleted"] and rec["files_left_out"] == 0, f"(C) the files it made or changed: {sorted(files)}")
        out = files["out.json"]
        data = open(os.path.join(real, "out.json"), "rb").read()
        ok(out["change"] == "created" and out["size"] == len(data) and out["sha256"] == j2.hashlib.sha256(data).hexdigest()
           and json.loads(out["text"]) == {"threads": 3}, f"(C) out.json: created, with its size, hash and text: {out}")
        ok(files["mail.txt"]["change"] == "changed" and files["mail.txt"]["text"] == "one two", "(C) a changed file is marked changed")
        rows = [x for x in j2_artifacts.rows(run.dir) if x["type"] == "run_output"]
        ok(len(rows) == 1 and rows[0]["file"] == "run_output/W-1-1.json" and rows[0]["kind"] == "record" and rows[0]["name"] == "Run output"
           and rows[0]["deliverable"] is False, f"(C) artifacts.json lists it: {rows}")
        ok("run_output" not in {x["name"] for x in j2_artifacts.load_types()["types"]}, "(C) it is not a type an agent can choose")
        # a text file over the cap keeps its name, size and hash, never its text; the output keeps its end
        cfg = j2.OWN_RUNS["run_output"]
        big = "x" * (cfg["text_bytes"] + 1)
        run, w = made({"s.py": f"import os, sys\nprint('y' * {cfg['output_chars'] + 5})\n"
                               f"open(os.path.join(sys.argv[1], 'big.txt'), 'w').write({big!r})\n"}, [check("file-exists", "s.py")], real=real)
        run._ask_real_run({})
        reply(run, "RUN a578a3")
        rec = json.load(open(os.path.join(run.dir, receipts(run)[-1]["run_output"])))
        bigrow = next(f for f in rec["files"] if f["name"] == "big.txt")
        ok("text" not in bigrow and bigrow["size"] == len(big) and bigrow["sha256"] and len(rec["stdout"]) == cfg["output_chars"],
           "(C) the caps hold: a large file's text is left out, the output keeps its end")
        # a decline: no record
        run, w = made({"s.py": PRINTS}, [check("file-exists", "s.py")], real=real)
        run._ask_real_run({})
        reply(run, "decline")
        ok("run_output" not in receipts(run)[-1] and not os.path.isdir(os.path.join(run.dir, "run_output")), "(C) a declined run leaves no record")
    finally:
        j2.secrets.token_hex = keep
    print("an approved real run leaves a run-output record (exit code, output, the files it made or changed), named in its receipt and listed in artifacts.json ok")


@t.with_folder_type
def c2_finds_the_builders_test():
    doc_charter = {"statement": "An agent for Pulse", "site_name": "Pulse", "business_type": FT, "done_when": ["it runs"]}
    c2 = lambda: {"id": "C2", "check": "test-passed"}
    files = {"tests/test_x.py": "print('OK')\n", "pulse/run.py": "X = 1\n", "README.md": "# Pulse\n"}
    for target in ("tests/test_x.py", f"{FT}/tests/test_x.py", ["tests/test_x.py"]):
        run, w = made(files, [check("test-passed", target)], goal=dict(doc_charter))
        met, why = run._folder_condition(c2())
        ok(met and "tests/test_x.py exited 0" in why, f"(D) C2 passes with the workflow's test {target!r}: {why}")
    run, w = made(files, [check("file-exists", "README.md")], goal=dict(doc_charter))
    ok(run._folder_condition(c2()) == (False, "code reran the test itself, on a copy of the folder, not the builder's own run: "
                                              "the test '' is not a file in the folder"), "(D) no test anywhere: still unmet, as before")
    run, w = made(files, [check("test-passed", "missing.py")], goal={**doc_charter, "test": "tests/test_x.py"})
    ok(run._folder_condition(c2())[0], "(D) the charter's test comes first")
    # a list target: each item checked
    run, w = made(files, [check("file-exists", ["pulse/run.py", "tests/test_x.py", "README.md"]),
                          check("test-passed", ["tests/test_x.py"])], goal=dict(doc_charter))
    ok(run._run_checks(w, 1, "", folder=run._out_dir()) == [], "(D) a list of files that are all there passes")
    w["atoms"][0]["verification"] = [check("file-exists", ["pulse/run.py", "gone.py"])]
    failed = run._run_checks(w, 1, "", folder=run._out_dir())
    ok(len(failed) == 1 and "gone.py" in failed[0]["evidence"] and "pulse/run.py" not in failed[0]["evidence"],
       f"(D) one missing file of the list fails the check and is named: {failed}")
    # the run-relative form resolves to the builder's folder
    w["atoms"][0]["verification"] = [check("file-exists", f"{FT}/pulse/run.py"), check("test-passed", f"{FT}/tests/test_x.py")]
    ok(run._run_checks(w, 1, "", folder=run._out_dir()) == [], "(D) '<folder>/x' is read as x in the folder")
    # a recheck that passes no folder keeps the folder
    w["atoms"][0]["verification"] = [check("test-passed", "tests/test_x.py"), check("inside-folder", ".")]
    ok(run._run_checks(w, j2.MAX_CHECK_ATTEMPTS, "", atoms=w["atoms"], recheck="check corrected by Adaptation") == [],
       "(D) a corrected check's recheck keeps its folder")
    ok(not any("unknown check" in r.get("evidence", "") for a in w["atoms"] for r in a.get("results") or []), "(D) never 'unknown check'")
    # one path form: a mix is refused, the folder's name in front of every target is taken off
    mix = {"name": "build", "atoms": [{"verification": [check("file-exists", f"{FT}/pulse/run.py"), check("test-passed", "tests/test_x.py")]}]}
    probs, n = j2.path_form_problems(mix, FT)
    ok(len(probs) == 1 and "two forms" in probs[0] and n == 0 and mix["atoms"][0]["verification"][0]["target"] == f"{FT}/pulse/run.py",
       f"(D) a mix of the two forms is refused, nothing changed: {probs}")
    front = {"name": "build", "atoms": [{"verification": [check("file-exists", [f"{FT}/pulse/run.py", f"{FT}/README.md"]),
                                                             check("test-passed", f"{FT}/tests/test_x.py")],
                                         "expected_output": [{"text": "the test", "kind": "file", "target": f"{FT}/tests/test_x.py"}]}]}
    probs, n = j2.path_form_problems(front, FT)
    a = front["atoms"][0]
    ok(not probs and n == 4 and a["verification"][0]["target"] == ["pulse/run.py", "README.md"]
       and a["verification"][1]["target"] == "tests/test_x.py" and a["expected_output"][0]["target"] == "tests/test_x.py",
       f"(D) all in the run-relative form: now relative to the folder: {a}")
    ok(j2.path_form_problems({"atoms": [{"verification": [check("file-exists", "pulse/run.py"), check("file-exists", f"./{FT}/x.py")]}]}, FT) == ([], 0),
       "(D) './<folder>/x' names a subfolder of that name: no mix")
    ok(j2.path_form_problems({"atoms": [{"verification": [check("file-exists", "../x.py")]}]}, FT)[0], "(D) a path that climbs out is refused")
    print("C2 finds the test the builder wrote; list targets, the recheck's folder and one path form hold ok")


@t.with_folder_type
def empty_requirements_and_declined_installs():
    files = {"helper.py": "VALUE = 1\n", "test_ok.py": TEST_OK, "test_needs.py": TEST_NEEDS}
    for text in ("", "\n", "# nothing to install\n\n"):
        run, w = made({**files, "requirements.txt": text}, [check("test-passed", "test_ok.py")])
        ok(j2_runenv.plan(run._out_dir()) is None, f"(E) a requirements.txt with no package plans no environment: {text!r}")
        n = len(run.chat)
        ok(run._env_ask(w, 1, run._out_dir()) is False and not run.paused and len(run.chat) == n, "(E) no install card, no question")
        ok(run._run_checks(w, 1, "", folder=run._out_dir()) == [] and w["atoms"][0]["results"][0]["pass"] is True, "(E) and its test is rerun")
    run, w = made({**files, "requirements.txt": "pulsedep==1.2.0\n"}, [check("test-passed", "test_ok.py")],
                  goal={"statement": "x", "done_when": ["it runs"], "test": "test_ok.py"})
    p = j2_runenv.plan(run._out_dir())
    ok(p and not p["ready"] and p["packages"] == ["pulsedep==1.2.0"], "(E) a requirements.txt with a package still plans one")
    run.env_why[p["hash"]] = "the Requester declined installing them"
    ok(j2_runenv.beyond_stdlib(os.path.join(run._out_dir(), "test_ok.py"), run._out_dir()) == []
       and j2_runenv.beyond_stdlib(os.path.join(run._out_dir(), "test_needs.py"), run._out_dir()) == ["pulsedep"],
       "(E) what a test needs beyond the standard library and the folder's own modules")
    ok(run._run_checks(w, 1, "", folder=run._out_dir()) == [] and "exited 0" in w["atoms"][0]["results"][0]["evidence"],
       f"(E) after a declined install a standard-library test is still rerun: {w['atoms'][0]['results']}")
    met, why = run._folder_condition({"id": "C2", "check": "test-passed"})
    ok(met and "exited 0" in why, f"(E) and C2 is met by it: {why}")
    w["atoms"][0]["verification"] = [check("test-passed", "test_needs.py")]
    run._run_checks(w, 1, "", folder=run._out_dir())
    res = w["atoms"][0]["results"][0]
    ok(res["pass"] is None and res["evidence"] == "the test was not rerun: its packages are not installed: the Requester declined installing them",
       f"(E) a test that imports the package is not run with another python: {res}")
    print("an empty requirements.txt asks nothing; a declined install never blocks a standard-library test ok")


def main():
    keep = {k: os.environ.get(k) for k in KEYS}
    fake = os.path.join(TMP, "python3.12")
    open(fake, "w").write(f"#!{sys.executable}\nimport subprocess, sys\nsys.exit(subprocess.run([{sys.executable!r}] + sys.argv[1:]).returncode)\n")
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
    os.environ.update(J2_AGENT_TOOLS="1", J2_DATA_DIR=os.path.join(TMP, "data"), J2_RUN_PYTHON=fake)
    os.environ.pop("J2_SANDBOX", None)
    try:
        agent_stage_is_a_program()
        decide_for_me_by_subject()
        run_output_is_recorded()
        c2_finds_the_builders_test()
        empty_requirements_and_declined_installs()
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"own_runs_test: {passed} checks passed")


if __name__ == "__main__":
    main()
