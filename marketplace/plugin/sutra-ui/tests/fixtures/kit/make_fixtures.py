#!/usr/bin/env python3
"""make_fixtures.py -- build the Apps frameworks runner fixtures.

    python3 make_fixtures.py [<target dir>]      default: this directory

Writes pass/<kind>/ for page, chat and link from the kit templates with every
required answer filled (a digital-lending example), the stamp on APP.md line 1
mirrored into module.json, and a `mutate(kind, check_id, folder)` helper the
runner test uses to derive one failing folder per must-fix id in a temp dir.
Deterministic: no clock reads in the fixtures themselves.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
KIT = os.path.join(UI, "apps-frameworks")
CREATED = "2026-09-12T09:00:00Z"
DATE = "2026-09-12"

ANSWERS = {
    "P1": "A collections analyst opens it to see which loans slipped past 60 days late this week and who owns each one.",
    "P2": "Loan book by bucket: the late loans, oldest first, with the owner beside each.",
    "P3": "When I open it tomorrow the top row reads LN-1877 at 63 days and the count of loans over 60 days matches the collections sheet.",
    "P4": "Open the app, scan the top rows, click Sort by days late, note the owners of the top three, close it.",
    "P5": "The worst wrong thing is a paid-off loan still shown as late; it should show the paid date instead, and I re-paste the rows from the ledger export.",
    "P6": "Priya (collections lead) keeps it; look at it again on 2026-12-12.",
    "P7": "Just me for now.",
    "S1": "I open the ledger export in a spreadsheet and filter by days late by hand.",
    "S2": "It replaces the weekly filtered spreadsheet; it extends nothing else.",
    "S3": "Keep it under Lending.",
    "DS1": "A table of loans sorted by days late, the oldest at the top.",
    "DS2": "A table of rows.",
    "DS3": "Over 60 days is blocked, 30 to 60 is warning, under 30 is good.",
    "DS4": "It talks to the collections analyst on shift; it must never quote a borrower's phone number or promise a settlement.",
    "DS6": "Late loans, one line under it; it sits next to the Balance row and looks the same.",
    "E1": "index.html opens first; module.json is the manifest; APP.md is this record",
    "E2": "Open the app and see the top row read LN-1877 at 63 days after any edit.",
    "E3": "One loan row: LN-1877, 63 days late, owner Priya; it shows as blocked at the top.",
    "B1": "Three loan rows pasted from the ledger export; they live inside the file itself.",
    "B2": "Made-up: the loan numbers are examples, not real borrowers.",
    "B3": "Only the collections folder under my home.",
    "B4": "It must never run commands, install anything or send messages on its own.",
    "B5": "balance",
    "F1": "- Sort by days late",
    "F2": "Resets each time; the rows are baked into the file.",
    "F3": "No pictures, icons or fonts.",
}
INSTRUCTIONS = ("You are the late-loans desk for the collections analyst on shift.\n"
                "- Only discuss loans in the rows the analyst pastes.\n- Never quote a borrower's phone number.\n"
                "- Never promise a settlement.\n- When a row is missing a date, say so instead of guessing.\n"
                "Which loans do you want to look at first?")


def stamp(kind):
    kit = json.load(open(os.path.join(KIT, "kit.json"), encoding="utf-8"))
    return {"kit": "apps-frameworks", "version": kit["version"], "digest": kit["digest_short"], "created_at": CREATED, "kind": kind}


def fill_record(kind, name, tagline, department, screen="balance"):
    text = open(os.path.join(KIT, "templates", kind, "APP.md"), encoding="utf-8").read()
    text = (text.replace("{{STAMP}}", json.dumps(stamp(kind), separators=(",", ":")))
                .replace("{{NAME}}", name).replace("{{TAGLINE}}", tagline).replace("{{KIT_VERSION}}", stamp(kind)["version"])
                .replace("{{DEPARTMENT}}", department).replace("{{SCREEN}}", screen).replace("{{DATE}}", DATE))
    out = []
    for line in text.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] in ANSWERS and not cells[2]:
                line = "| %s | %s | %s |" % (cells[0], cells[1], ANSWERS[cells[0]])
            elif len(cells) == 7 and cells[0] == "Backend" and kind == "chat":
                cells[6] = "commands it may run, word for word: none"
                line = "| " + " | ".join(cells) + " |"
        out.append(line)
    return "\n".join(out) + "\n"


def manifest(kind, mid, name, tagline, extra_surface=None):
    surface = {"page": {"entry": "index.html"}, "chat": {"instructions": INSTRUCTIONS}, "link": {"screen": "balance"}}[kind]
    if extra_surface:
        surface.update(extra_surface)
    return {"schema": 2, "id": mid, "name": name, "tagline": tagline, "kind": kind,
            "status": "ready" if kind == "link" else "draft", "version": 1,
            "origin": {"created_by": "app", "session_id": None, "at": CREATED},
            "surface": surface, "guard": {}, "created_at": CREATED, "updated_at": CREATED, "updated_ms": 1789200000000,
            "department": None, "publish": None, "frameworkKit": stamp(kind)}


NAMES = {"page": ("Loan book by bucket", "the late loans, oldest first, with the owner beside each"),
         "chat": ("Late loans desk", "the late loans, oldest first, with the owner beside each"),
         "link": ("Balance shortcut", "the late loans, oldest first, with the owner beside each")}


def make_pass(kind, target):
    mid = os.path.basename(target)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)
    name, tagline = NAMES[kind]
    if kind == "page":
        shutil.copy(os.path.join(KIT, "templates", "page", "index.html"), os.path.join(target, "index.html"))
    with open(os.path.join(target, "APP.md"), "w", encoding="utf-8") as fh:
        fh.write(fill_record(kind, name, tagline, "Unassigned"))
    with open(os.path.join(target, "module.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest(kind, mid, name, tagline), fh, indent=1)
    return target


def _edit(path, fn):
    text = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(fn(text))


def _edit_json(path, fn):
    doc = json.load(open(path, encoding="utf-8"))
    fn(doc)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)


# One mutation per must-fix id that makes exactly that check fail on a pass folder.
MUTATIONS = {
    "C1": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace("| P1 | Who opens this, and what are they trying to get done? | " + ANSWERS["P1"], "| P1 | Who opens this, and what are they trying to get done? | "))),
    "C2": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace(ANSWERS["P3"], "It works."))),
    "C3": ("page", lambda d: _edit_json(d + "/module.json", lambda m: m.update(tagline=m["name"]))),
    "C4": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace(ANSWERS["P1"], ANSWERS["P1"] + " Filed under dref-0123456789abcdef by ADR-039."))),
    # kit 1.1.0 promotions: C6 fails on a malformed ref before the registry is read (no registry state needed)
    "C6": ("page", lambda d: _edit_json(d + "/module.json", lambda m: m.update(department={"ref": "not-a-ref"}))),
    "C7": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace(ANSWERS["P6"], "Priya (collections lead) keeps it; look at it again next quarter."))),
    "C10": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("color:var(--ink);max-width", "color:#1f2937;max-width"))),
    "C11": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("<style>", "<style>:root{--ink:red}"))),
    "C17": ("page", lambda d: _edit_json(d + "/module.json", lambda m: m.update(id="somebody-else"))),
    "C18": ("page", lambda d: open(d + "/run.sh", "w").write("#!/bin/sh\necho no\n")),
    "C19": ("page", lambda d: open(d + "/index.html", "a").write("<!-- " + ("x" * (513 * 1024)) + " -->")),
    "C20": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace('"digest":"', '"digest":"deadbeefcaf'))),
    "C22": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace(ANSWERS["E2"], "Should still work fine afterwards."))),
    "C25": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("draw(rows);\n    })();", "draw(rows); fetch('/api/modules');\n    })();"))),
    "C26": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("<h1>", '<img src="assets/logo.png" alt="logo"><h1>'))),
    "C28": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("var rows = [", "var apiKey = \"sk-ABCDEFGHIJKLMNOPQRSTUVWX\"; var rows = ["))),
    "C29": ("chat", lambda d: _edit_json(d + "/module.json", lambda m: m["surface"].update(cwd="/definitely/not/home"))),
    "C32": ("link", lambda d: _edit_json(d + "/module.json", lambda m: m["surface"].update(screen="terminal"))),
    "C33": ("page", lambda d: _edit(d + "/index.html", lambda t: "<!doctype html><html><body>" + t + "</body></html>")),
    "C35": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("draw(rows);\n    })();", "draw(rows); localStorage.setItem('x', '1');\n    })();"))),
    # C36: a page that throws on load; Runtime.exceptionThrown in render_check.mjs (needs node + Chrome to run)
    "C36": ("page", lambda d: _edit(d + "/index.html", lambda t: t.replace("draw(rows);\n    })();", "draw(rows); throw new Error(\"render check: boom\");\n    })();"))),
    "C37": ("page", lambda d: _edit(d + "/APP.md", lambda t: t.replace(ANSWERS["F2"], "It should remember the sort order."))),
    "C38": ("chat", lambda d: open(d + "/data-policy.json", "w").write('{"panel_apis": []}')),
}


def mutate(check_id, target_root):
    """Build pass/<kind> under target_root/<check_id> and apply the mutation. -> (kind, folder)"""
    kind, fn = MUTATIONS[check_id]
    folder = os.path.join(target_root, check_id.lower())
    make_pass(kind, folder)
    fn(folder)
    return kind, folder


def main(argv):
    root = argv[0] if argv else HERE
    for kind in ("page", "chat", "link"):
        make_pass(kind, os.path.join(root, "pass", kind))
        print("pass/%s" % kind)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
