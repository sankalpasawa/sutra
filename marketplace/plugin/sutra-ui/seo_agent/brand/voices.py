"""brand/voices.py — builder 7: the bylines, a questionnaire the team answers.

Port of 6-voices/scripts/instantiate.py. The bylines are COMPANY-GIVEN: the recipe's steps 1-4 are
questions to the team, so the builder only instantiates the skeleton, with the default byline
"<Brand> Team", and never drafts an answer. An existing voices.md is the team's SEED and is never
overwritten.

Writes: brand/voices.md
"""
from . import _common as cm

OUTPUT = "voices.md"
ASK = "*(ask"


def run(co, say, redo=False):
    if cm.exists(OUTPUT):
        say("Kept voices.md", "it exists: the team's answers are SEED, never overwritten (even on redo)")
    else:
        cm.save(OUTPUT, cm.fill(cm.template("voices"), brand=co["brand"]))
        say("Instantiated voices.md", "default byline \"%s Team\"; the team fills the rest" % co["brand"])
    notes = []
    n = cm.count_lines(cm.read(OUTPUT), ASK)
    if n:
        notes.append("voices.md: %d byline questions for the team to answer" % n)
    return {"files": [OUTPUT], "needs_review": notes}
