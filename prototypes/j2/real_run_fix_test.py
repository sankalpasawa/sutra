"""Offline checks of the real-run fixes (a run that planned a live step, offered it after a failed dry run, lost the
Requester's approval and ended ready without it): python real_run_fix_test.py

(1) a dry run that does not exit 0 is never offered: a receipt says "not offered" with the exit code and the end of
    the output, the workflow goes back to its builder with the stderr on its remaining attempts, and with none left
    the real run is closed as not run;
(2) an approval is never lost: "Run", "yes", "RUN" and a wrong code keep the question open with "Not run. Reply
    exactly RUN <code>, or decline." and write no receipt; "run a578a3" (any case, spaces trimmed) runs it; a decline
    closes it;
(3) a run with a real run that is pending, unapproved, declined or not offered never ends "Done:" or ready: the
    outcome and the closing message say the live step is not done, and why;
(4) every real-run receipt, and the dry run inside it, keeps the exit code and the last 2,000 characters of stdout
    and of stderr;
(5) a build with a requirements.txt: nothing is installed before the Requester's RUN <code> (another reply keeps the
    question open); then code makes an environment, kept by the hash of requirements.txt in the data folder, and the
    test rerun, the dry run and the real run use its python; receipts record the interpreter's path and version, the
    requirements hash and the installed versions; the approval card lists the packages; a second run with the same
    requirements.txt reuses the environment and installs nothing; a decline leaves the real run not offered;
(6) a top-level import that does not resolve blocks the offer and goes back to the builder;
(7) a requirements.txt line that is not "name==version" from PyPI is refused back to the builder; with no
    interpreter the real run is not offered, with a plain reason;
(8) with J2_SANDBOX=1 only the install step may reach the network, and only pypi.org and files.pythonhosted.org;
(9) a real run that must call a service names its hosts in its plan: with the sandbox on, none named means no network;
    named hosts are asked for before the dry run (nothing is allowed without RUN <code>, another reply keeps the
    question open), then they are the only ones reachable in the dry run and the real run, and a host that is not
    named stays blocked; the approval card lists them; the receipt and its dry run record the hosts allowed; without
    the sandbox the list is shown and recorded, and not enforced; a host that is not a plain name is refused.

No AI calls and no network: a fake python stands in for the interpreter, its venv module and pip (installing a
package writes a one-line module), and a fake sandbox runtime records the settings it is given. Nothing is written
outside temp folders.
"""
import json
import os
import shutil
import stat
import sys
import tempfile

import j2_flow_test as t          # sets STUDIO_MOCK, J2_MEMORY=0, temp runs and library folders
import j2                          # noqa: E402
import j2_runenv                   # noqa: E402

passed = 0
FT = t.FT
TMP = tempfile.mkdtemp(prefix="j2-realrun-fix-")
LOG = os.path.join(TMP, "fake.log")
KEYS = ("J2_AGENT_TOOLS", "J2_DATA_DIR", "J2_RUN_PYTHON", "J2_SANDBOX", "J2_SANDBOX_CMD", "FAKE_LOG", "FAKE_PIP_FAIL")

# TEST ONLY. A stand-in for python3.x: "-m venv" makes a folder holding a copy of itself, "-m pip install" writes one
# module per requirements line into that folder (no network), "-m pip list" lists them, and anything else runs with
# the real python, which sees those modules only when it is the environment's copy that was called.
FAKE_PYTHON = '''#!{exe}
import json, os, shutil, subprocess, sys
me, a = os.path.abspath(sys.argv[0]), sys.argv[1:]
site = os.path.join(os.path.dirname(os.path.dirname(me)), "site")
def note(kind):
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps({{"kind": kind, "argv": a, "python": me}}) + "\\n")
if a[:2] == ["-m", "venv"]:
    note("venv")
    os.makedirs(os.path.join(a[2], "bin"))
    os.makedirs(os.path.join(a[2], "site"))
    shutil.copy(me, os.path.join(a[2], "bin", "python"))
    sys.exit(0)
if a[:3] == ["-m", "pip", "install"]:
    note("pip install")
    if os.environ.get("FAKE_PIP_FAIL"):
        sys.stderr.write("ERROR: No matching distribution found for " + os.environ["FAKE_PIP_FAIL"] + "\\n")
        sys.exit(1)
    for line in open(a[a.index("-r") + 1]):
        name, _, version = line.strip().partition("==")
        if name:
            open(os.path.join(site, name.replace("-", "_") + ".py"), "w").write("VERSION = %r\\n" % version)
    sys.exit(0)
if a[:3] == ["-m", "pip", "list"]:
    rows = []
    for f in sorted(os.listdir(site)):
        if f.endswith(".py"):
            rows.append({{"name": f[:-3], "version": open(os.path.join(site, f)).read().split("'")[1]}})
    print(json.dumps(rows))
    sys.exit(0)
note("run")
env = dict(os.environ)
if os.path.isdir(site):
    env["PYTHONPATH"] = site
sys.exit(subprocess.run([{exe!r}] + a, env=env).returncode)
'''
# TEST ONLY stand-in for the sandbox runtime (srt -s <settings> -c <command>): it records the settings it was given
# and runs the command WITHOUT a sandbox.
FAKE_SANDBOX = '''import json, os, subprocess, sys
a = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"kind": "sandbox", "settings": json.load(open(a[a.index("-s") + 1])), "command": a[a.index("-c") + 1]}) + "\\n")
allowed = json.load(open(a[a.index("-s") + 1]))["network"]["allowedDomains"]      # what the command may reach: told to it as FAKE_NET
sys.exit(subprocess.run(a[a.index("-c") + 1], shell=True, env={**os.environ, "FAKE_NET": json.dumps(allowed)}).returncode)
'''
# TEST ONLY: a built script that "reaches" the hosts given after its folder. Inside the fake sandbox a host that is not
# allowed is refused, as the real one refuses the connection; outside a sandbox every host is reachable. No network.
NET = ("import json, os, sys\nallowed = json.loads(os.environ['FAKE_NET']) if 'FAKE_NET' in os.environ else None\n"
       "for h in sys.argv[2:]:\n    if allowed is not None and h not in allowed:\n"
       "        sys.stderr.write('blocked by the sandbox: ' + h + '\\n')\n        sys.exit(9)\n"
       "open(os.path.join(sys.argv[1], 'out.txt'), 'w').write('reached ' + ' '.join(sys.argv[2:]))\n")
GOOD = "import sys, os\nopen(os.path.join(sys.argv[1], 'out.txt'), 'w').write('done')\n"
BAD = "import sys\nsys.stderr.write('boom: the token file is missing\\n')\nsys.exit(3)\n"
NEEDS = "import sys, os\nimport pulsedep\nopen(os.path.join(sys.argv[1], 'out.txt'), 'w').write(pulsedep.VERSION)\n"
NEEDS_TEST = "import pulsedep\nassert pulsedep.VERSION == '1.2.0'\n"
REQ = "pulsedep==1.2.0\n"


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


def log(kind=None):
    try:
        rows = [json.loads(x) for x in open(LOG)]
    except OSError:
        return []
    return [r for r in rows if kind is None or r["kind"] == kind]


def receipts(run, kind="real_run"):
    try:
        return [r for r in map(json.loads, open(os.path.join(run.dir, "receipts.jsonl"))) if r.get("type") == kind]
    except OSError:
        return []


def system(run):
    return [m["text"] for m in run.chat if m["who"] == "system"]


def made(files, real, status="done", attempts=1, test=None, hosts=None, reaches=()):
    """A run of the folder type with one workflow that plans a real run on `real`, its files already built."""
    run = j2.J2Run()
    run.set_output(FT)
    run.goal, run.budget = {"statement": "read the folder", "done_when": ["the script has been run on the folder"]}, 300
    os.makedirs(run._out_dir(), exist_ok=True)
    for name, text in files.items():
        open(os.path.join(run._out_dir(), name), "w").write(text)
    checks = [{"text": "s.py exists", "type": "file-exists", "target": "s.py", "expect": True}] + (
        [{"text": "its test passes", "type": "test-passed", "target": test, "expect": True}] if test else [])
    w = {"id": "W-1", "name": "reader", "purpose": "read", "outputs": [f"{FT}/s.py"], "status": status,
         "calls_used": attempts, "retries_used": 0, "cost": 10, "cycle": 1, "section": "W-1", "covers": [],
         "real_run": {"command": ["python3", "s.py", real, *reaches], "folder": real, "why": "read it", "checks": [1],
                      **({"hosts": hosts} if hosts else {})},
         "atoms": [{"id": "W-1.a1", "goal": "read", "expected_output": [], "verification": checks}]}
    if status == "done":
        w["build_attempts"] = attempts
    run.workflows = [w]
    j2.add_workflow_agent("W-1")
    run.sites = ["v1"]
    run.post("user", "go")
    return run, w


def builder(run, *rounds):
    """The run's builder, scripted: each call writes the next round's files (the last one again after that)."""
    prompts = []

    def call(fn, fmt, prompt, mock, **kw):
        prompts.append(prompt)
        for name, text in rounds[min(len(prompts), len(rounds)) - 1].items():
            open(os.path.join(run._out_dir(), name), "w").write(text)
        return {"say": "@Coordination built", "human_output": "I built the reader.", "atom_human_output": "The reader."}
    run.call = call
    return prompts


def reply(run, text):
    """The Requester answers the open question; code reads the answer (Identity's turn, no model)."""
    h = run.paused["handoff"]
    run.post("user", text)
    run.paused = None
    run._turn_identity({**h, "answer": text})


def new_real():
    d = tempfile.mkdtemp(prefix="real-", dir=TMP)
    open(os.path.join(d, "mail.txt"), "w").write("one")
    return d


@t.with_folder_type
def failing_dry_run():
    real = new_real()
    run, w = made({"s.py": BAD}, real)
    ok(run._ask_real_run({}) and not run.paused, "(1) a failing dry run pauses for nobody")
    ok(not any("reply exactly: RUN" in x for x in system(run)) and "W-1" not in run.real_runs_asked,
       "(1) a failing dry run is not offered: no code is posted")
    r = receipts(run)[-1]
    ok(r["offered"] is False and not r["approved"] and not r["ran"] and r["evidence"] == "not offered: its dry run on copies exited 3",
       f"(1) the receipt says not offered: {r}")
    ok(r["dry_run"]["exit"] == 3 and "boom: the token file is missing" in r["dry_run"]["stderr"], "(1) the receipt keeps the dry run's exit code and stderr")
    ok(run.turn == "W-1" and run.handoff == {"kind": "build", "wid": "W-1"} and w["resume"]["attempt"] == 1,
       f"(1) it goes back to its builder: {run.turn} {run.handoff}")
    prompts = builder(run, {"s.py": GOOD})
    run._turn_workflow_agent(run.handoff)
    ok(len(prompts) == 1 and "ATTEMPT 2 OF 3" in prompts[0] and "boom: the token file is missing" in prompts[0]
       and "exited 3" in prompts[0], "(1) the builder is told the failure with its stderr, as its next attempt")
    ok(w["status"] == "done" and w["build_attempts"] == 2 and not os.path.exists(os.path.join(real, "out.txt")),
       "(1) rebuilt on attempt 2; nothing ran on the real folder")
    ok(run._ask_real_run({}) and run.paused["kind"] == "real_run" and "dry run on a copy: exit 0" in system(run)[-1],
       "(1) after the fix the dry run exits 0 and is offered")
    # never fixed: its attempts run out, the real run is closed as not run, and the run does not end ready
    run, w = made({"s.py": BAD}, real, attempts=j2.MAX_CHECK_ATTEMPTS)
    ok(run._ask_real_run({}) is False and run.real_runs_done["W-1"] is False and not run.paused,
       "(1) with no attempts left it is not offered and not sent back")
    run._goal_done({})
    ok(run.outcome.startswith("Done with open items: The live step is not done. W-1's real run did not run: its dry run on copies exited 3"),
       f"(1) the outcome says why: {run.outcome}")
    print("a failing dry run is not offered: a receipt with its exit code and stderr, back to the builder on its "
          "remaining attempts, closed as not run when none is left ok")


@t.with_folder_type
def approval_not_lost():
    real = new_real()
    keep = j2.secrets.token_hex
    j2.secrets.token_hex = lambda n=3: "a578a3"
    try:
        run, w = made({"s.py": GOOD}, real)
        ok(run._ask_real_run({}) and run.real_runs_asked["W-1"] == "a578a3", "(2) asked with a code")
        for text in ("Run", "yes", "RUN", "RUN a578a4", "run it"):
            reply(run, text)
            ok(run.paused and run.paused["kind"] == "real_run" and run.paused["handoff"]["wid"] == "W-1",
               f"(2) {text!r} keeps the question open")
            ok(system(run)[-1] == "Not run. Reply exactly RUN a578a3, or decline.", f"(2) {text!r} gets the plain message: {system(run)[-1]}")
            ok(not receipts(run) and not os.path.exists(os.path.join(real, "out.txt")) and "W-1" not in run.real_runs_done,
               f"(2) {text!r} runs nothing and closes nothing")
        reply(run, "run a578a3")
        r = receipts(run)[-1]
        ok(r["approved"] and r["ran"] and r["exit"] == 0 and open(os.path.join(real, "out.txt")).read() == "done",
           f"(2) 'run a578a3' is accepted and runs it: {r}")
        ok(len(receipts(run)) == 1 and run.outcome.startswith("Done:") and not run._real_run_open(), f"(2) one receipt, a clean end: {run.outcome}")
        for text in ("  RUN   A578A3  ", "Run a578a3."):
            os.remove(os.path.join(real, "out.txt"))
            run, w = made({"s.py": GOOD}, real)
            run._ask_real_run({})
            reply(run, text)
            ok(receipts(run)[-1]["approved"] and os.path.exists(os.path.join(real, "out.txt")), f"(2) {text!r} is accepted")
        os.remove(os.path.join(real, "out.txt"))
        run, w = made({"s.py": GOOD}, real)
        run._ask_real_run({})
        run.post("user", "RUN a578a3", auto=True)      # the exact code, but sent by Decide for me: never an approval
        h, run.paused = run.paused["handoff"], None
        run._turn_identity({**h, "answer": "RUN a578a3"})
        ok(run.paused and not receipts(run) and not os.path.exists(os.path.join(real, "out.txt")), "(2) Decide for me never approves")
        reply(run, "Decline")
        r = receipts(run)[-1]
        ok(r["declined"] and not r["approved"] and not r["ran"] and not run.paused and not os.path.exists(os.path.join(real, "out.txt")),
           f"(2) a decline closes the question and runs nothing: {r}")
    finally:
        j2.secrets.token_hex = keep
    print("an approval is never lost: a reply without the exact code keeps the question open with the plain message; "
          "the code in any case with spaces trimmed runs it; a decline closes it ok")


@t.with_folder_type
def never_ready_with_a_pending_real_run():
    real = new_real()
    ends = lambda run: (run.outcome, next(m["text"] for m in reversed(run.chat) if m["who"] == "identity" and m.get("done")))
    # asked, never answered
    run, w = made({"s.py": GOOD}, real)
    run._ask_real_run({})
    run.paused = None
    run._goal_done({})
    out, said = ends(run)
    ok(out.startswith("Done with open items: The live step is not done. W-1's real run did not run: it waits for the "
                      "Requester's approval") and not out.startswith("Done:"), f"(3) asked and unanswered: {out}")
    ok("not ready" in said and "ready." not in said.replace("not ready.", ""), f"(3) the closing message never says ready: {said}")
    # declined
    run, w = made({"s.py": GOOD}, real)
    run._ask_real_run({})
    reply(run, "decline")
    out, said = ends(run)
    ok(out.startswith("Done with open items") and "did not run: the Requester declined it" in out and "not ready" in said, f"(3) declined: {out}")
    # never asked for: its workflow did not finish, or the run is shipped as it is
    run, w = made({"s.py": GOOD}, real, status="failed")
    run._goal_done({})
    ok("W-1's real run did not run: its workflow is failed, not done" in run.outcome and run.outcome.startswith("Done with open items"),
       f"(3) a failed workflow's real run: {run.outcome}")
    run, w = made({"s.py": GOOD}, real)
    out = run._ship_outcome("on the Requester's decision")
    ok(out.startswith("Done with open items: shipped as is") and "The live step is not done" in out and "it was not asked for" in out, f"(3) shipped as is: {out}")
    # the run that ran and passed ends clean
    run, w = made({"s.py": GOOD}, real)
    run._ask_real_run({})
    reply(run, f"RUN {run.real_runs_asked['W-1']}")
    ok(run.outcome.startswith("Done:") and run._live_step_note() == "", f"(3) approved and exit 0 ends Done: {run.outcome}")
    print("a run with a real run that is pending, unapproved, declined or never asked for doesn't end ready: the "
          "outcome and the closing message say the live step is not done and why ok")


@t.with_folder_type
def receipts_keep_the_evidence():
    real = new_real()
    noisy = ("import sys, os\nsys.stdout.write('o' * 2990 + 'OUT-END')\nsys.stderr.write('e' * 2990 + 'ERR-END')\n"
             "open(os.path.join(sys.argv[1], 'out.txt'), 'w').write('x')\n")
    run, w = made({"s.py": noisy}, real)
    run._ask_real_run({})
    reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = receipts(run)[-1]
    for name, x in (("the real run", r), ("its dry run", r["dry_run"])):
        ok(x["exit"] == 0 and len(x["stdout"]) == 2000 and x["stdout"].endswith("OUT-END") and len(x["stderr"]) == 2000
           and x["stderr"].endswith("ERR-END") and "OUT-END" not in x["stderr"], f"(4) {name} keeps the exit code and both tails")
        ok(x["env"]["python"] and x["env"]["python_version"], f"(4) {name} records the interpreter's path and version: {x['env']}")
    failing = "import sys\nprint('started')\nsys.stderr.write('E' * 2500 + 'LAST-LINE')\nsys.exit(7)\n"
    run, w = made({"s.py": failing}, real, attempts=j2.MAX_CHECK_ATTEMPTS)
    run._ask_real_run({})
    d = receipts(run)[-1]["dry_run"]
    ok(d["exit"] == 7 and d["stdout"] == "started\n" and len(d["stderr"]) == 2000 and d["stderr"].endswith("LAST-LINE"),
       "(4) a failed dry run's receipt keeps exit 7 and the end of stdout and stderr")
    ok(j2_runenv.TAIL == 2000 and j2_runenv.tail("x" * 5000) == "x" * 2000 and j2_runenv.tail(b"ab") == "ab" and j2_runenv.tail(None) == "",
       "(4) the tail is the last 2,000 characters")
    print("receipts keep the evidence: the exit code and the last 2,000 characters of stdout and of stderr, for the "
          "dry run and the real run, passed or failed ok")


@t.with_folder_type
def requirements_get_an_environment():
    real = new_real()
    files = {"s.py": NEEDS, "test_s.py": NEEDS_TEST, "requirements.txt": REQ}
    run, w = made({}, real, status="running", attempts=0, test="test_s.py")
    prompts = builder(run, files)
    run._turn_workflow_agent({"wid": "W-1"})
    plan = j2_runenv.plan(run._out_dir())
    card = system(run)[-1]
    code = run.env_asked[plan["hash"]]
    ok(run.paused and run.paused["kind"] == "real_run" and run.paused["handoff"]["kind"] == "env_install" and run._auto_pick() is None,
       "(5) the build pauses to ask for its packages; Decide for me never answers")
    ok("pulsedep==1.2.0" in card and "from PyPI only" in card and f"RUN {code}" in card and "Nothing is installed until you approve" in card,
       f"(5) the card lists the packages and versions: {card}")
    ok(plan["dir"].startswith(os.path.realpath(os.environ["J2_DATA_DIR"])) and not j2.llm.inside(plan["dir"], j2.HERE) and not j2.llm.inside(plan["dir"], run.dir),
       "(5) the environment is kept in the data folder, outside the repo and the run")
    ok(not log("venv") and not log("pip install") and not os.path.exists(plan["dir"]) and not receipts(run, "env_install"),
       "(7) nothing is installed before the approval")
    ok(not any(x.get("check") == "its test passes" for x in run.receipts), "(5) the test is not rerun before its packages are there")
    reply(run, "yes install")
    ok(run.paused and system(run)[-1] == f"Not installed. Reply exactly RUN {code}, or decline." and not log("pip install"),
       "(7) a reply without the code installs nothing and keeps the question open")
    reply(run, f"run {code}")
    ok(len(log("venv")) == 1 and len(log("pip install")) == 1 and not run.paused, "(5) RUN <code> makes the environment and installs, once")
    argv = log("pip install")[0]["argv"]
    ok(argv[argv.index("--index-url") + 1] == "https://pypi.org/simple" and "--isolated" in argv and "--extra-index-url" not in argv,
       f"(5) the install names PyPI as its only index: {argv}")
    e = receipts(run, "env_install")[-1]
    ok(e["approved"] and e["exit"] == 0 and e["requirements_sha256"] == plan["hash"] and e["installed"] == {"pulsedep": "1.2.0"}
       and e["python"] == j2_runenv.env_python(plan["dir"]) and e["python_version"] and e["packages"] == ["pulsedep==1.2.0"],
       f"(5) the install receipt records the interpreter, the hash and the installed versions: {e}")
    ok(run.turn == "W-1" and run.handoff == {"kind": "build", "wid": "W-1"}, "(5) the build goes on from its checks")
    run._turn_workflow_agent(run.handoff)
    test = next(x for x in run.receipts if x["check"] == "its test passes")
    ok(len(prompts) == 1 and w["status"] == "done" and test["pass"] is True, f"(5) no second builder call; the test rerun passes: {test}")
    ran = [r for r in log("run") if r["python"] == j2_runenv.env_python(plan["dir"]) and r["argv"] == ["test_s.py"]]
    ok(len(ran) == 1, "(5) the test rerun used the environment's python, not the system one (which has no pulsedep)")
    ok(run._ask_real_run({}) and run.paused["handoff"]["kind"] == "real_run", "(5) the real run is offered")
    ask = system(run)[-1]
    ok("Packages it runs with" in ask and "pulsedep==1.2.0" in ask and "dry run on a copy: exit 0" in ask and "approves running with them" in ask,
       f"(5) the approval card lists the packages: {ask}")
    reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = receipts(run)[-1]
    want = {"python": j2_runenv.env_python(plan["dir"]), "requirements_sha256": plan["hash"], "installed": {"pulsedep": "1.2.0"}}
    for name, x in (("the real run", r), ("its dry run", r["dry_run"])):
        ok(x["exit"] == 0 and {k: x["env"].get(k) for k in want} == want and x["env"]["python_version"],
           f"(5) {name} used the environment's python and its receipt records it: {x.get('env')}")
    ok(open(os.path.join(real, "out.txt")).read() == "1.2.0" and run.outcome.startswith("Done:"),
       "(5) the script ran for real with its package (python3 alone has no pulsedep)")
    # a second run with the same requirements.txt: the environment is reused, nothing is asked or installed
    os.remove(os.path.join(real, "out.txt"))
    n = len(log("pip install"))
    run2, w2 = made({}, real, status="running", attempts=0, test="test_s.py")
    builder(run2, files)
    run2._turn_workflow_agent({"wid": "W-1"})
    ok(not run2.paused and w2["status"] == "done" and len(log("pip install")) == n and len(log("venv")) == 1 and not run2.env_asked,
       "(5) a cached environment is reused: no question, no install")
    ok(next(x for x in run2.receipts if x["check"] == "its test passes")["pass"] is True and j2_runenv.plan(run2._out_dir())["ready"],
       "(5) the second run's test passes in the cached environment")
    # a decline: nothing installed, the test is not rerun with another python, the real run is not offered
    run3, w3 = made({}, real, status="running", attempts=0, test="test_s.py")
    other = {**files, "requirements.txt": "pulsedep==1.2.0\nextra-lib==0.3\n"}
    builder(run3, other)
    run3._turn_workflow_agent({"wid": "W-1"})
    ok(run3.paused and "extra-lib==0.3" in system(run3)[-1], "(5) another requirements.txt is another environment, asked for")
    reply(run3, "decline")
    run3._turn_workflow_agent(run3.handoff)
    t3 = next(x for x in run3.receipts if x["check"] == "its test passes")
    ok(len(log("pip install")) == n and t3["pass"] is None and "the Requester declined installing them" in t3["evidence"],
       f"(7) declined: nothing installed and the test is not rerun: {t3}")
    ok(run3._ask_real_run({}) is False and "its packages are not installed: the Requester declined installing them" in run3._live_step_note(),
       f"(5) declined packages: the real run is not offered, with why: {run3._live_step_note()}")
    # a failed install goes back to the builder with pip's error
    os.environ["FAKE_PIP_FAIL"] = "nosuch==9.9"
    try:
        run4, w4 = made({}, real, status="running", attempts=0, test="test_s.py")
        p4 = builder(run4, {**files, "requirements.txt": "pulsedep==1.2.0\nnosuch==9.9\n"}, files)
        run4._turn_workflow_agent({"wid": "W-1"})
        reply(run4, f"RUN {next(iter(run4.env_asked.values()))}")
        e4 = receipts(run4, "env_install")[-1]
        ok(e4["approved"] and e4["exit"] == 1 and "No matching distribution found for nosuch==9.9" in e4["stderr"]
           and not os.path.exists(j2_runenv.plan(run4._out_dir())["dir"]), f"(5) a failed install keeps its exit code and stderr, and no environment: {e4}")
    finally:
        os.environ.pop("FAKE_PIP_FAIL", None)
    run4._turn_workflow_agent(run4.handoff)
    ok(len(p4) == 2 and "No matching distribution found for nosuch==9.9" in p4[1] and "ATTEMPT 2 OF 3" in p4[1] and w4["status"] == "done",
       "(5) the builder is told pip's error and fixes requirements.txt")
    print("requirements.txt gets an environment: asked for with the packages listed, nothing installed before RUN "
          "<code>, PyPI only, its python used for the test rerun, the dry run and the real run, recorded in the "
          "receipts, reused when cached; a decline or a failed install is said plainly ok")


@t.with_folder_type
def missing_import_blocks_the_offer():
    real = new_real()
    run, w = made({"s.py": "import sys\nimport notinstalledmod\nfrom helper import go\n", "helper.py": "def go():\n    pass\n"}, real)
    ok(run._ask_real_run({}) and not run.paused and "W-1" not in run.real_runs_asked and not run.real_runs_dry,
       "(6) a missing import blocks the offer, before any dry run")
    r = receipts(run)[-1]
    ok(r["offered"] is False and "imports notinstalledmod, which is not installed" in r["evidence"] and "helper" not in r["evidence"],
       f"(6) the receipt names the module (a module built beside the script resolves): {r['evidence']}")
    ok(run.turn == "W-1" and "notinstalledmod" in w["resume"]["evidence"] and "requirements.txt" in w["resume"]["evidence"],
       "(6) it goes back to the builder, told to name the package in requirements.txt")
    ok(j2_runenv.top_imports(os.path.join(run._out_dir(), "s.py")) == ["sys", "notinstalledmod", "helper"], "(6) top-level imports only")
    # a requirements.txt line that is not name==version from PyPI is refused back to the builder, never asked for
    run, w = made({}, real, status="running", attempts=0)
    rounds = [{"s.py": GOOD, "requirements.txt": text} for text in
              ("requests>=2\n", "--extra-index-url https://example.invalid/simple\npulsedep==1.2.0\n", "git+https://example.invalid/x.git\n")]
    prompts = builder(run, *rounds)
    n = len(log("pip install"))
    run._turn_workflow_agent({"wid": "W-1"})
    ok(len(prompts) == 3 and w["status"] == "failed" and not run.paused and not run.env_asked and len(log("pip install")) == n,
       f"(7) lines code will not install are never asked for or installed: {w['status']}")
    ok("requests>=2" in prompts[1] and "exact version" in prompts[1] and "--extra-index-url" in prompts[2], "(7) the builder is told which lines")
    # no interpreter to make the environment with: not offered, with a plain reason
    keep = os.environ["J2_RUN_PYTHON"]
    os.environ["J2_RUN_PYTHON"] = os.path.join(TMP, "no-such-python")
    try:
        run, w = made({"s.py": NEEDS, "requirements.txt": "pulsedep==7.0.0\n"}, real, attempts=j2.MAX_CHECK_ATTEMPTS)
        ok(run._env_ask(w, 1, run._out_dir()) is False and run._ask_real_run({}) is False, "(7) no interpreter: nothing asked, not offered")
        ok("which is not a Python that runs" in run._live_step_note() and "J2_RUN_PYTHON" in run._live_step_note(), f"(7) the reason is plain: {run._live_step_note()}")
    finally:
        os.environ["J2_RUN_PYTHON"] = keep
    print("a missing import blocks the offer and goes back to the builder; a requirements.txt line that is not a "
          "pinned PyPI package is refused; with no interpreter the real run is not offered, with the reason ok")


@t.with_folder_type
def sandbox_opens_the_network_for_the_install_only():
    real = new_real()
    fake = os.path.join(TMP, "fake_srt.py")
    open(fake, "w").write(FAKE_SANDBOX)
    os.environ.update(J2_SANDBOX="1", J2_SANDBOX_CMD=f"{sys.executable} {fake}")
    try:
        run, w = made({}, real, status="running", attempts=0, test="test_s.py")
        builder(run, {"s.py": NEEDS, "test_s.py": NEEDS_TEST, "requirements.txt": "pulsedep==1.2.0\nsandboxed==2.0\n"})
        before = len(log("sandbox"))
        run._turn_workflow_agent({"wid": "W-1"})
        reply(run, f"RUN {next(iter(run.env_asked.values()))}")
        run._turn_workflow_agent(run.handoff)
        run._ask_real_run({})
        reply(run, f"RUN {run.real_runs_asked['W-1']}")
        rows = log("sandbox")[before:]
        installs = [r for r in rows if " -m pip install " in r["command"]]
        others = [r for r in rows if r not in installs]
        ok(len(installs) == 1 and installs[0]["settings"]["network"]["allowedDomains"] == ["pypi.org", "files.pythonhosted.org"],
           f"(8) the install step may reach PyPI and nothing else: {[r['settings']['network'] for r in installs]}")
        env_dir = j2_runenv.plan(run._out_dir())["dir"]
        ok(installs[0]["settings"]["filesystem"]["allowWrite"] == [env_dir], "(8) the install writes only its environment's folder")
        ok(len(others) == 3 and all(r["settings"]["network"]["allowedDomains"] == [] for r in others),
           f"(8) the test rerun, the dry run and the real run have no network: {[(r['command'][:40], r['settings']['network']) for r in others]}")
        ok(all(env_dir in r["settings"]["filesystem"]["allowRead"] for r in others), "(8) each may read the environment it runs with")
        ok(receipts(run)[-1]["exit"] == 0 and receipts(run, "env_install")[-1]["sandbox"]["network"]["allowedDomains"] == list(j2_runenv.PYPI_HOSTS),
           "(8) the install receipt records the sandbox settings it ran with")
    finally:
        os.environ.pop("J2_SANDBOX", None)
        os.environ.pop("J2_SANDBOX_CMD", None)
    print("J2_SANDBOX=1 opens the network for the install step only, to pypi.org and files.pythonhosted.org; the test "
          "rerun, the dry run and the real run stay without network ok")


@t.with_folder_type
def hosts_are_named_approved_and_the_only_ones_allowed():
    real = new_real()
    fake = os.path.join(TMP, "fake_srt.py")
    open(fake, "w").write(FAKE_SANDBOX)
    A, B, C = "api.example.com", "auth.example.com", "other.example.com"
    nets = lambda rows: [r["settings"]["network"]["allowedDomains"] for r in rows]
    # the plan's hosts are data, checked by code
    rr = {"command": ["python3", "s.py", real], "folder": real, "why": "x"}
    P = lambda hosts: j2.real_run_problems({**rr, "hosts": hosts}, j2.squash(f"run it on {real}"), ("python3", "{target}"), "/nowhere/run")
    ok(P([A, B]) == [] and P([]) == [], f"(9) plain host names are accepted: {P([A, B])}")
    for bad in (["*.example.com"], ["https://api.example.com"], ["api.example.com:443"], ["10.0.0.1"], ["localhost"], "api.example.com", [7]):
        ok(any("real_run hosts must be a list of the plain host names" in x for x in P(bad)), f"(9) {bad!r} is refused")
    ok(j2.real_hosts({"hosts": [" API.Example.com ", A, B]}) == [A, B] and j2.real_hosts({}) == [] and j2.real_hosts(None) == [],
       "(9) hosts are used in lower case, each once")
    os.environ.update(J2_SANDBOX="1", J2_SANDBOX_CMD=f"{sys.executable} {fake}")
    try:
        # no hosts named: no network, so a script that calls a service fails its dry run and is not offered
        n = len(log("sandbox"))
        run, w = made({"s.py": NET}, real, attempts=j2.MAX_CHECK_ATTEMPTS, reaches=[A])
        ok(run._ask_real_run({}) is False and not run.paused and nets(log("sandbox")[n:]) == [[]], f"(9) no hosts listed = no network: {nets(log('sandbox')[n:])}")
        d = receipts(run)[-1]["dry_run"]
        ok(d["exit"] == 9 and f"blocked by the sandbox: {A}" in d["stderr"] and d["network"] == {"hosts": [], "enforced": True},
           f"(9) the dry run was blocked and its receipt says no host was allowed: {d['network']}")
        # hosts named: asked for first; nothing is allowed, and nothing runs, before the approval
        n = len(log("sandbox"))
        run, w = made({"s.py": NET}, real, hosts=[A, B], reaches=[A, B])
        ok(run._ask_real_run({}) and run.paused["kind"] == "real_run" and run.paused["handoff"]["kind"] == "real_run_hosts"
           and run._auto_pick() is None, "(9) the hosts are asked for before the dry run; Decide for me never answers")
        card, code = system(run)[-1], run.hosts_asked["W-1"]
        ok(f"Hosts it would reach, and no others: {A}, {B}" in card and f"RUN {code}" in card and "Nothing is allowed until you approve" in card,
           f"(9) the question lists the hosts: {card}")
        ok(len(log("sandbox")) == n and not run.hosts_ok and not run.real_runs_dry and "W-1" not in run.real_runs_asked,
           "(9) nothing is allowed and nothing runs without approval")
        reply(run, "ok go ahead")
        ok(run.paused and run.paused["handoff"]["kind"] == "real_run_hosts" and system(run)[-1] == f"Not allowed. Reply exactly RUN {code}, or decline."
           and len(log("sandbox")) == n and not run.hosts_ok, "(9) a reply without the code allows nothing and keeps the question open")
        reply(run, f"run {code}")
        ok(run.hosts_ok == {"W-1": [A, B]} and nets(log("sandbox")[n:]) == [[A, B]], f"(9) approved: the dry run may reach exactly those hosts: {nets(log('sandbox')[n:])}")
        ok(run.paused and run.paused["handoff"]["kind"] == "real_run", "(9) the dry run passed, so the real run is offered")
        ask = system(run)[-1]
        ok(f"Network: it can reach only {A}, {B}. RUN {run.real_runs_asked['W-1']} approves them." in ask and "dry run on a copy: exit 0" in ask,
           f"(9) the approval card lists the hosts: {ask}")
        ok(not os.path.exists(os.path.join(real, "out.txt")), "(9) the dry run reached the hosts from copies, not the real folder")
        reply(run, f"RUN {run.real_runs_asked['W-1']}")
        r = receipts(run)[-1]
        ok(r["approved"] and r["exit"] == 0 and open(os.path.join(real, "out.txt")).read() == f"reached {A} {B}" and nets(log("sandbox")[n:]) == [[A, B], [A, B]],
           "(9) the real run reached the approved hosts, and only they were allowed")
        ok(r["hosts"] == [A, B] and r["network"] == {"hosts": [A, B], "enforced": True} and r["dry_run"]["network"] == r["network"],
           f"(9) the receipt and its dry run record the hosts allowed: {r['network']}")
        os.remove(os.path.join(real, "out.txt"))
        # a host that is not named stays blocked, also after the others were approved
        run, w = made({"s.py": NET}, real, attempts=j2.MAX_CHECK_ATTEMPTS, hosts=[A], reaches=[A, C])
        run._ask_real_run({})
        reply(run, f"RUN {run.hosts_asked['W-1']}")
        d = receipts(run)[-1]
        ok(d["offered"] is False and d["dry_run"]["exit"] == 9 and f"blocked by the sandbox: {C}" in d["dry_run"]["stderr"]
           and d["dry_run"]["network"]["hosts"] == [A] and not run.paused, f"(9) an unlisted host is blocked and the run is not offered: {d['evidence']}")
        ok(run.outcome.startswith("Done with open items") and "its dry run on copies exited 9" in run.outcome, f"(9) the outcome says so: {run.outcome}")
        # a decline: nothing allowed, no dry run, not offered
        n = len(log("sandbox"))
        run, w = made({"s.py": NET}, real, hosts=[A], reaches=[A])
        run._ask_real_run({})
        reply(run, "decline")
        ok(len(log("sandbox")) == n and not run.hosts_ok and not run.paused and receipts(run)[-1]["offered"] is False
           and f"the Requester declined letting it reach {A}" in run.outcome, f"(9) declined hosts: nothing ran, and the outcome says why: {run.outcome}")
    finally:
        os.environ.pop("J2_SANDBOX", None)
        os.environ.pop("J2_SANDBOX_CMD", None)
    # without the sandbox: no extra question, the list is shown and recorded, and nothing is enforced
    run, w = made({"s.py": NET}, real, hosts=[A, B], reaches=[A, B])
    ok(run._ask_real_run({}) and run.paused["handoff"]["kind"] == "real_run" and not run.hosts_asked, "(9) without the sandbox there is no hosts question")
    ask = system(run)[-1]
    ok(f"Network: it says it reaches {A}, {B}. No sandbox is on, so this is not enforced." in ask, f"(9) the card still lists them: {ask}")
    reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = receipts(run)[-1]
    ok(r["exit"] == 0 and r["hosts"] == [A, B] and r["network"] == {"hosts": [A, B], "enforced": False} and r["dry_run"]["network"]["enforced"] is False,
       f"(9) recorded, and marked as not enforced: {r['network']}")
    run, w = made({"s.py": GOOD}, real)
    run._ask_real_run({})
    ok("Network: it names no hosts. No sandbox is on, so the network is not blocked." in system(run)[-1], "(9) a plan without hosts says so on the card")
    ok("REAL RUN AND THE NETWORK" in j2.REAL_RUN_HOSTS_RULE and '"hosts"' in j2.REAL_RUN_HOSTS_RULE, "(9) the planning rules name the field")
    print("a real run's hosts: named in the plan and checked by code; with the sandbox on none named means no network, "
          "named ones are approved before the dry run and are the only ones reachable, an unlisted host stays blocked; "
          "the card lists them and the receipt records them; without the sandbox they are shown and recorded ok")


def main():
    keep = {k: os.environ.get(k) for k in KEYS}
    fake = os.path.join(TMP, "python3.12")
    open(fake, "w").write(FAKE_PYTHON.format(exe=sys.executable))
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
    os.environ.update(J2_AGENT_TOOLS="1", J2_DATA_DIR=os.path.join(TMP, "data"), J2_RUN_PYTHON=fake, FAKE_LOG=LOG)
    os.environ.pop("J2_SANDBOX", None)
    try:
        failing_dry_run()
        approval_not_lost()
        never_ready_with_a_pending_real_run()
        receipts_keep_the_evidence()
        requirements_get_an_environment()
        missing_import_blocks_the_offer()
        sandbox_opens_the_network_for_the_install_only()
        hosts_are_named_approved_and_the_only_ones_allowed()
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"real_run_fix_test: {passed} checks passed")


if __name__ == "__main__":
    main()
