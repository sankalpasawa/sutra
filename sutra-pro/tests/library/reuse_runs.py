"""Child process of `test_lib_reuse_runs.py` (not a test): mock runs of the VENDORED J2 with the reuse flags in the states the sync 6 design lists, each run
folder copied to the folder given as the first argument.

    off      flags off, a document brief (a Pilates studio)
    auto     J2_AUTO_REUSE=1, the Yoga documents brief: the best run template of the library is picked and followed
    door1    J2_ARTIFACT_LIBRARY=1, the same brief: the picked run template's source run is not here, every door is "unknown"
    door2    the same brief again after run door1 was saved as a run template: every section is served (door reuse), refunded
    door3    the Pilates brief over that template: sections are reused, adapted or built, with the adapted-family keys
    tpl      J2_RUN_TEMPLATES=1, a run template chosen by name with two of its workflows (`set_run_template`)

The library is a scratch copy of the app's seed. Nothing is written outside the two folders. J2_RUN_BY and J2_PUSH_RUNS are what the host fixes."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

OUT = Path(sys.argv[1])
SEED = Path(sys.argv[2])
SCRATCH = tempfile.mkdtemp(prefix="sutra-reuse-runs-")
os.environ.update({"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_RUN_BY": "sutra-pro", "J2_PUSH_RUNS": "0",
                   "J2_MEMORY_FILE": os.path.join(SCRATCH, "lessons.jsonl"), "J2_PLAYBOOK_FILE": os.path.join(SCRATCH, "playbooks.jsonl"),
                   "J2_RUNS_DIR": os.path.join(SCRATCH, "runs"), "J2_LIBRARY_DIR": os.path.join(SCRATCH, "library")})
for flag in ("J2_ARTIFACT_LIBRARY", "J2_AUTO_REUSE", "J2_TEMPLATE_LIBRARY", "J2_RUN_TEMPLATES", "J2_ARTIFACT_SCHEMA"):
    os.environ.pop(flag, None)
shutil.copytree(SEED, os.environ["J2_LIBRARY_DIR"])

from sutra_app.engine import j2, j2_template_lib as L          # noqa: E402  (after the environment: J2 reads some of it at import)

YOGA = ("Create the design documents (PRD, HLD and LLD) for Still Point Yoga, a small yoga studio at 4th Floor, 22 Church Street, Bengaluru "
        "560001.\n\nThe page shows the name Still Point Yoga and the address as text, with no embedded map.\n\nThe weekly class list has five "
        "classes, each with day, time and price in rupees:\nMonday 7:00 am Gentle Flow 500\nTuesday 6:30 pm Strength Yoga 600\nThursday 7:00 am "
        "Breath and Stretch 450\nSaturday 9:00 am Beginners Basics 400\nSunday 8:00 am Slow Sunday 500\n\nThe page has a class booking form with "
        "the fields name, email, class and preferred date. The form sends the booking to bookings@stillpoint.example. Payment is made at the "
        "studio. No online payment is taken.\n\nThe teachers' names are not decided yet, and the studio has no phone number. Do not show teacher "
        "names or a phone number, and do not make any other detail up.\n\nThe page must work on phones.")
PILATES = (YOGA.replace("Still Point Yoga", "Flow Pilates").replace("Strength Yoga", "Strength Reformer").replace("yoga", "pilates")
           .replace("stillpoint", "flowpilates"))
BOUTIQUE = "A website for a boutique called Thread, at 12 Brigade Road, Bengaluru 560025. Show the name and the address as text."


def say(run, text):
    assert run.user_says(text)
    while run.status != "waiting":
        time.sleep(0.02)
    if getattr(run, "review_thread", None):
        run.review_thread.join()


def run_of(brief, name, before=None):
    run = j2.J2Run()
    run.budget = 1400
    if before:
        before(run)
    say(run, brief)
    for _ in range(6):
        if not run.paused:
            break
        say(run, "Option 2" if run.paused["kind"] == "conflict" else "1")
    shutil.copytree(run.dir, OUT / name)
    return run


OUT.mkdir(parents=True, exist_ok=True)
run_of(PILATES, "off")
os.environ["J2_AUTO_REUSE"] = "1"
run_of(YOGA, "auto")
del os.environ["J2_AUTO_REUSE"]
os.environ["J2_ARTIFACT_LIBRARY"] = "1"
first = run_of(YOGA, "door1")
L.save_run_template(L.run_template_from_run(first.dir, name="A rerun of Still Point Yoga"))
run_of(YOGA, "door2")
run_of(PILATES, "door3")
del os.environ["J2_ARTIFACT_LIBRARY"]
os.environ["J2_RUN_TEMPLATES"] = "1"
run_of(BOUTIQUE, "tpl", before=lambda run: print("set_run_template:", run.set_run_template("thread-boutique-website", "W-1,W-3")))
shutil.copytree(os.environ["J2_LIBRARY_DIR"], OUT / "library")
shutil.rmtree(SCRATCH, ignore_errors=True)
print("runs done")
