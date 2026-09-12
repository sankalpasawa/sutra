"""onboard.py — the setup interview: the questions the original workflow puts to a human.

Layer 01 of the original workflow has builders that cannot finish without a person.
`0-brand-facts/templates/stats.md` ends in "Seeds to mine (ask the team)".
`templates/stories.md` ends in "The interview (ask the team)". Sutra's port wrote those files and
then nobody ever asked, so they shipped with their placeholders in and stayed that way forever.
The user was never told there was anything to answer.

This asks. Four questions, one at a time, in the chat, at setup. Every one is skippable and a skip
is recorded AS a skip, so a brand file can tell "we asked and they had nothing" apart from "nobody
ever asked". The second is a bug; the first is a fact about the company.

THE TWO BYLINE QUESTIONS WERE DELETED, 2026-09-09. "Who do articles get published under" and "who
signs the leadership pieces" were asked here and filed into brand/voices.md. The owner's words:
"remove completely everything about the byline questions, everything from Sutra for now." The
questions, their prompt files, voices.md and the builder that laid it out are all gone. If bylines
come back, they come back as a whole feature, not as two questions with nowhere to land.

Reads:  knowledge/brand/company.json (for {{BRAND}}) and prompts/onboard/<id>.md.
Writes: knowledge/brand/_interview/answers.json    the ledger, and the single source of truth
        knowledge/brand/stats.md, stories.md       a managed block, rendered from it
        knowledge/competitors.json                 the competitor answer, when one is given

The ledger is the value; the markdown blocks are a rendering of it. Every answer rewrites its
whole block, so the two can never drift, and a crash halfway through the interview leaves the
answers already given on disk with the rest simply unasked.

WHY IT RUNS BEFORE learn_brand. Three of these answers belong in files that learn_brand
instantiates, and the original's rule is that an existing file is SEED and is never overwritten.
Answering first means the builders find the answers already there and keep them, which is exactly
what the original does. The block is deliberately shaped so it does NOT look like a confirmed
row to `brand/brand_facts.py::human_confirmed` (no table rows, no ⚠️), because a file that looks
confirmed makes that builder skip its own draft of the numbers your site DOES publish. Answering a
question must never cost you the machine draft.

HOW IT WAITS. It does not. `run()` returns `{"ask": {...}}` and loop.py turns that into the same
`_wait` checkpoint every approval and every `ask_user` already uses: state to disk, process
returns, the answer arrives later through `resume()`. There is no second waiting mechanism, and no
question is asked by the model, which cannot be trusted to relay an answer into a file verbatim.
"""
import re

from .. import store
from ..brand import _common as cm
from . import _shared as sh

LEDGER = "_interview/answers.json"       # under knowledge/brand/
START = "<!-- setup-interview:start -->"
END = "<!-- setup-interview:end -->"
SKIP_LABEL = "Skip this one"

# The words a person types when they mean "no answer". Checked only against the WHOLE reply, so
# "none of our competitors publish this" is an answer and "none" is a skip.
SKIP_WORDS = {"", "-", "skip", "skip this", "skip this one", "skip it", "no", "nope", "none",
              "n/a", "na", "pass", "not now", "later", "dunno", "no idea", "don't know",
              "dont know", "nothing"}

# id, the file the answer is filed in, the order they are asked in.
# Ported one for one from the original's own "ask the team" sections; prompts/onboard/README.md
# maps each id back to the file and section it came from.
QUESTIONS = [
    ("numbers", "stats.md"),
    ("origin-story", "stories.md"),
    ("lesson-learned", "stories.md"),
    ("competitors", None),               # its home is knowledge/competitors.json, not a brand file
]
IDS = [q for q, _f in QUESTIONS]
BRAND_FILES = ["stats.md", "stories.md"]


# ---- the questions themselves ------------------------------------------------------------------

_BLOCKS = ("QUESTION", "WHY", "HEADING")


def _parse(text):
    """A question file into {question, why, heading}. The format is a block name alone on a line,
    then its content. Kept this dull on purpose: the file is read by a person editing the wording,
    not by a parser that has to be clever."""
    out, key = {}, None
    for line in (text or "").splitlines():
        if line.strip() in _BLOCKS:
            key = line.strip().lower()
            out[key] = []
        elif key:
            out[key].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def question(qid, brand=""):
    """The wording for one question, brand filled in. Raises if the file is missing, because a
    question we cannot ask is a broken build, not something to paper over at runtime."""
    q = _parse(sh.fill(sh.load_prompt("onboard/" + qid), brand=brand or "the company"))
    if not q.get("question"):
        raise RuntimeError("prompts/onboard/%s.md has no QUESTION block." % qid)
    return q


# ---- the ledger ---------------------------------------------------------------------------------

def ledger():
    """The record of what has been asked. {} before the first question goes out."""
    raw = cm.read(LEDGER)
    return raw if isinstance(raw, dict) else {}


def _save_ledger(led):
    cm.save(LEDGER, led)


def status():
    """What loop.py puts in the system prompt, so the model never asks a second time.

    started  the interview has been opened
    asked    every question has been put (the interview is closed)
    done/answered/skipped/total  the counts, for the line the model reads
    """
    led = ledger()
    ans = led.get("answers") or {}
    answered = sum(1 for a in ans.values() if a.get("state") == "answered")
    return {"started": bool(led), "asked": bool(led.get("finished_at")),
            "done": len(ans), "total": len(QUESTIONS),
            "answered": answered, "skipped": len(ans) - answered}


def read_answer(answer, skip_label=SKIP_LABEL):
    """(text, skipped) from whatever the screen sent back.

    A chip posts {"choice": "<label>"}, the composer posts {"text": "..."}. Both are ordinary
    replies, so a skip is a value, never a missing field: the difference between "they said
    nothing" and "nobody asked them" is the whole point of this tool.
    """
    if not isinstance(answer, dict):
        answer = {"text": str(answer)}
    text = ""
    for key in ("text", "choice", "note", "changes"):
        v = answer.get(key)
        if isinstance(v, str) and v.strip():
            text = v.strip()
            break
    if answer.get("skipped") is True:
        return "", True
    if text.strip().lower().rstrip(".!") in SKIP_WORDS or text.strip() == skip_label:
        return "", True
    return text, False


def record(qid, text, skipped=False):
    """File one answer, then re-render every block it touches.

    Rendering on every answer rather than once at the end is deliberate: the interview can be
    abandoned at any question (the app is closed, the run is stopped) and what was already said
    must be on disk in the file that wants it, not held in a run that no longer exists.
    """
    if qid not in IDS:
        raise ValueError("Unknown setup question: %s. Known: %s" % (qid, ", ".join(IDS)))
    led = ledger()
    led.setdefault("version", 1)
    led.setdefault("started_at", store.now())
    led.setdefault("answers", {})
    led["answers"][qid] = {"state": "skipped" if skipped else "answered",
                           "text": "" if skipped else (text or "").strip(),
                           "at": store.now()}
    _save_ledger(led)
    notes = _apply(led)
    return {"state": led["answers"][qid]["state"], "notes": notes}


# ---- rendering the answers into the files that want them ----------------------------------------

def _row(qid, led, brand):
    """(heading, state, text, date) for one question, or None when it has not been asked."""
    a = (led.get("answers") or {}).get(qid)
    if not a:
        return None
    return (question(qid, brand).get("heading") or qid, a.get("state"), a.get("text") or "",
            (a.get("at") or "")[:10])


def _block(rows, brand):
    """The managed block. No table row and no `###` heading anywhere in it.

    Both are traps. `brand/brand_facts.py::human_confirmed` reads a pipe row without the draft
    marker, OR a `### ` heading without it, as "a person has confirmed something in this file",
    and its builder then skips drafting the numbers and stories the site DOES publish. Caught on
    2026-09-09 with `### ` headings in this block: answering one question silently cost the user
    the whole machine draft. Bold labels carry the same meaning to a reader and none of it to that
    check.
    """
    out = [START, "", "## Asked at setup", "",
           "> Put to the %s team in the chat, one question at a time, when the brand pack was"
           % (brand or "company"),
           "> first built. These are their own words. \"Not answered\" means the question WAS",
           "> asked and passed over, which is a fact about the company. A question that is not",
           "> listed here was never asked at all, which is a bug.", ""]
    for heading, state, text, date in rows:
        out.append("**%s**" % heading)
        out.append("")
        if state == "answered":
            out += [text, "", "*(the team, %s)*" % date, ""]
        else:
            out += ["*Not answered.* Asked on %s and passed over." % date, ""]
    out += [END, ""]
    return "\n".join(out)


def _instantiate(name, co):
    """The file's own template, brand slots filled, exactly as the builder that owns it would do
    it. Only ever called when the file is not there yet: an existing file is SEED."""
    return cm.fill(cm.template(name[:-3]), brand=co["brand"],
                   niche=co.get("niche_definition") or "the niche")


def _write_block(name, block, co):
    """Put the block in `name`, replacing an earlier one. Everything outside the two markers is
    left exactly as it was, so a builder's own drafting still owns the rest of the file."""
    text = cm.read(name)
    if not (text or "").strip():
        text = _instantiate(name, co)
    i, j = text.find(START), text.find(END)
    if i >= 0 and j > i:
        text = text[:i] + block + text[j + len(END):].lstrip("\n")
    else:
        text = text.rstrip("\n") + "\n\n" + block
    cm.save(name, text)
    return name


def _apply(led):
    """Render every answer on file into its home. Idempotent, and safe to call after any answer."""
    co = sh.company()
    brand = co.get("brand") or "the team"
    notes = []
    for name in BRAND_FILES:
        rows = [r for r in (_row(q, led, brand) for q, f in QUESTIONS if f == name) if r]
        if rows:
            _write_block(name, _block(rows, brand), co)
    notes += _save_competitors(led)
    return notes


# ---- the one answer that is not a brand file ----------------------------------------------------

# A web address inside a sentence: at least two labels, a 2-24 letter suffix. Deliberately strict.
# "TestGorilla and Vervoe" are names, not addresses, and guessing testgorilla.com from a name is
# exactly the invention this codebase refuses to do everywhere else.
_DOMAIN = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})\b", re.I)


def domains(text, own=""):
    """The web addresses in a free-text answer, lowercased, without www, the company's own dropped
    and the order the user gave them kept."""
    own = sh.normalise_url(own).split("/")[0]
    out = []
    for m in _DOMAIN.finditer(text or ""):
        d = m.group(1).lower().rstrip(".")
        if d.startswith("www."):
            d = d[4:]
        if "." not in d or d == own or d in out:
            continue
        out.append(d)
    return out


def _save_competitors(led):
    """The competitor answer into knowledge/competitors.json, the file suggest_topics already
    reads. Merged, never replaced: a list already on file was either derived or given earlier and
    is not this tool's to throw away.

    A skip writes NOTHING. That matters: with no file, `suggest_topics._derive_competitors` still
    works the list out from the brand voice, which is the honest fallback. Writing an empty list
    would look like an answer and switch that fallback off.
    """
    a = (led.get("answers") or {}).get("competitors")
    if not a or a.get("state") != "answered":
        return []
    co = sh.company()
    found = domains(a.get("text"), co.get("domain"))
    if not found:
        return ["competitors.json: you named who you compete with but not their web addresses, so "
                "the list was not saved. Add the addresses in Knowledge, or I will work them out "
                "from your own pages."]
    raw = store.knowledge("competitors.json") or {}
    have = raw.get("competitors") if isinstance(raw, dict) else raw
    rows, seen = [], set()
    for d in found:
        rows.append({"domain": d, "why": "named by the team at setup", "last_used": None})
        seen.add(d)
    for item in (have or []):
        d = item.get("domain") if isinstance(item, dict) else str(item)
        if d and d.strip().lower() not in seen:
            seen.add(d.strip().lower())
            rows.append(item if isinstance(item, dict) else {"domain": d.strip(), "last_used": None})
    store.save_knowledge("competitors.json", {"competitors": rows, "asked_at": a.get("at")})
    return []


# ---- the tool -----------------------------------------------------------------------------------

def _pending(led):
    ans = led.get("answers") or {}
    for qid in IDS:
        if qid not in ans:
            return qid
    return None


def _finish(led, say):
    led["finished_at"] = store.now()
    _save_ledger(led)
    notes = _apply(led)
    st = status()
    say("The setup questions are done",
        "%s answered, %s passed over" % (st["answered"], st["skipped"]))
    files = [f for f in BRAND_FILES if cm.exists(f)]
    summary = ("Setup questions: %d of %d answered, %d passed over. Their words are on file in %s."
               % (st["answered"], st["total"], st["skipped"], ", ".join(files) or "the brand pack"))
    return {"summary": summary, "files": files, "needs_review": notes,
            "answered": st["answered"], "skipped": st["skipped"], "asked": True,
            "hint": ("Do not repeat these questions and do not ask the user to fill anything in. "
                     "Say in one line what you now know, then carry on with setup.")}


def run(ctx, redo=False):
    """Ask the next unanswered setup question, or close the interview when there are none left.

    Returns `{"ask": {...}}` while there is a question outstanding. loop.py takes that and waits;
    it hands the answer to `record()` and calls this again. The model sees ONE tool result, at the
    end, and never sees a half-finished interview it could improvise around.
    """
    say = sh.reporter(ctx, "onboard")
    led = ledger()

    if redo and led.get("finished_at"):
        say("Going through the setup questions again", "the previous answers are replaced as you answer")
        led = {"version": 1, "started_at": store.now(), "answers": {},
               "redone_from": led.get("finished_at")}
        _save_ledger(led)

    if led.get("finished_at"):
        st = status()
        return {"summary": ("The setup questions were already put to them on %s: %d answered, %d "
                            "passed over. Nobody was asked again."
                            % (led["finished_at"][:10], st["answered"], st["skipped"])),
                "asked": False, "already_asked": True,
                "answered": st["answered"], "skipped": st["skipped"],
                "hint": "Do not ask them again unless the user asks you to."}

    qid = _pending(led)
    if qid is None:
        return _finish(led, say)

    co = sh.company()
    q = question(qid, co.get("brand"))
    n = len(led.get("answers") or {}) + 1
    if n == 1:
        # WHAT IS COMING, BEFORE IT COMES (owner, 2026-09-12: "it didn't intimate me, it didn't
        # tell me anything before asking the questions"). He skipped all four for his second
        # company because nothing said what they were for or that a number and a story were
        # wanted, and the brand pack was then built with neither.
        say("Asking the setup questions",
            "%d short questions the website cannot answer: a number you can claim, why the "
            "company was built, something that did not work, and who you compete with. Have a "
            "figure and a story handy. Every one is skippable, and the answers go to Knowledge "
            "as your own words." % len(QUESTIONS))
    return {"summary": "Asked question %d of %d." % (n, len(QUESTIONS)),
            "ask": {"id": qid, "question": q["question"], "why": q.get("why", ""),
                    "step": n, "of": len(QUESTIONS)}}
