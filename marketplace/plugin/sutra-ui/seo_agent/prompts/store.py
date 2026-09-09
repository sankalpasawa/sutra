"""store.py — the owner's own copy of a prompt, and the one place a prompt is chosen.

WHAT THIS IS FOR. The craft of this agent is in its prompts, and the craft belongs to the person
who wrote it. Until now, changing a word of it meant a developer, a checkout and a new build. The
Prompts tab lets him open a prompt, edit it and save it, and the very next article is written with
his version. This module is the half of that which the engine sees.

WHERE AN EDITED PROMPT LIVES, AND WHY IT MATTERS. Never in the app bundle. The bundle is replaced
whole on every update, so a prompt edited in place would be silently thrown away by the next DMG,
and the owner would find his own writing gone with nothing to point at. So an edit is written under
the DATA dir instead, beside knowledge and the library:

    ~/.sutra-ui/agents/seo/prompts/write/readable.md          <- his version, if he saved one
    <app bundle>/seo_agent/prompts/write/readable.md          <- what shipped, never written to

At load time the edited copy wins. Delete it and the shipped one is back, which is exactly what the
Reset control does: it removes a file, it does not restore text from a backup.

HOW EVERY CALLER GETS THE OVERRIDE AT ONCE. Prompts are read through two doors and only two:

    tools/_shared.load_prompt(name)   every prompt in write/, research/ and brand/
    write/_common.format_path(arch)   the eight format rulebooks (format_rules and readable both
                                      go through it)

`install()` wraps those two functions, once, in this process. Every call site keeps calling exactly
what it called before — `C.prompt("readable")`, `cm.prompt("persona")`, `C.format_rules(arch)` —
and gets the owner's text if there is any. Patching the two doors rather than the forty call sites
is the difference between one behaviour and forty chances to forget one.

THE SAFETY RULE ON SAVE. A prompt is a template: the code fills `{{TOKEN}}` blanks before the model
sees it. Delete or mistype a token and nothing complains until the middle of a run, deep inside a
paid step, and the model is handed a prompt with a hole in it. There is already a test asserting no
prompt reaches the model with an unfilled token; the editor must not become the way that breaks. So
a save that has lost a token the shipped version had is REFUSED, and the message names the tokens.
Adding a token is refused too: nothing fills a blank the code has never heard of.

The keep-half of that applies where the code actually fills a blank, which is the six writing
prompts. A format rulebook is never filled — its words are lifted whole and handed to another
prompt as one value — so the two token names printed in its developer header are that header
describing the plumbing, not blanks of its own, and he is free to delete the sentence. See
`is_filled`. The add-half applies to both, because a rulebook's words end up inside a prompt the
model reads.
"""
import os
import re
import tempfile

from .. import store

HERE = os.path.dirname(os.path.abspath(__file__))          # .../seo_agent/prompts
SHIPPED = HERE                                              # the bundle's prompts folder
_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


# ---- what the Prompts tab offers -------------------------------------------------------------
# The order IS the order on screen, and the format rulebooks come first: they are not part of the
# architect, they are what it obeys, and of everything on this screen they are what changes an
# article the most.
#
# Deliberately NOT here: slop, links, clean. The owner named those three as the ones to skip.

FORMATS = [
    ("write/formats/answer-bait-definitional", "Answer bait and definitions",
     "The 40-60 word answer at the very top, then definition, how it works, why it matters."),
    ("write/formats/common-spine", "The common spine",
     "The house order every article falls back to when no other shape fits."),
    ("write/formats/comparison-rankings", "Comparisons and rankings",
     "The table up top, one identical block per option, an honest weakness for every one."),
    ("write/formats/data-benchmark-report", "Data and benchmark reports",
     "The big number, the findings menu, one new number per finding, the method stated."),
    ("write/formats/glossary", "Glossary",
     "One term per entry, the definition in the first line, the related terms linked sideways."),
    ("write/formats/how-to-guide", "How-to guide",
     "Steps in order, one action each, the goal and the place before the action."),
    ("write/formats/listicle", "Listicle",
     "The items are the article: flat, parallel, the supporting blocks below them."),
    ("write/formats/template-resource", "Templates and resources",
     "The asset previewed before any ask, then what you get and how to use it."),
]

WRITING = [
    ("write/write-body", "Writing the body",
     "How each section is written from its facts, its contract and its length."),
    ("write/blend", "Blending the sections into one piece",
     "The pass that turns separately written sections into one article."),
    ("write/coherence-edit", "Reading the article whole",
     "The read-through that fixes what only shows up when you read it end to end."),
    ("write/readable", "Rewriting it to be read",
     "The rewrite for a person: the basics first, every section on the headline's promise."),
    ("write/sentence-pass", "Re-shaping the sentences",
     "Sentence length and rhythm, so the prose does not march."),
    ("write/wrapper", "The intro, the TL;DR, the FAQ and the close",
     "Everything around the body, written last because it has to match what got written."),
]

GROUPS = [
    {"key": "formats", "title": "The format rules",
     "note": "Eight shapes an article can take. The rulebook decides what a section must contain, "
             "and it is the first thing the architect obeys.",
     "prompts": FORMATS},
    {"key": "writing", "title": "The writing prompts",
     "note": "How each part of the article gets written, and how it gets edited afterwards.",
     "prompts": WRITING},
]

EDITABLE = {name: (title, note) for g in GROUPS for name, title, note in g["prompts"]}

# The archetype slug the router decides -> the name a person calls that shape. Used by the Prompts
# tab AND by the Library's Format column, so the two never disagree about what "listicle" is called.
FORMAT_TITLES = {name.rsplit("/", 1)[1]: title for name, title, _n in FORMATS}


def format_title(archetype):
    """A routed archetype as a person reads it. Unknown slugs come back as themselves."""
    a = str(archetype or "").strip()
    return FORMAT_TITLES.get(a, a)


# ---- the flow drawn at the top of the tab ----------------------------------------------------
# A phrase per step, in the order a run actually takes them. Grounded in two files, not invented:
# tools/write_article.py's STEPS and its own step labels, and the original's run_article.py, whose
# STATIONS list is planner -> architect -> field -> writer (so voices from the field sits between
# the architect and the writer, not inside it).
#
# The format rules are a station of their own, BEFORE the architect. Nothing here is marked as not
# running: enrich, the replacement-source hunt and voices from the field all ship in this release.

FLOW = [
    {"key": "planner", "title": "Planner", "steps": [
        "Gather the material",
        "Decide the format",
        "Judge which sections earn their place",
        "Check every number's source, and hunt a replacement for a dead one",
        "Freeze the plan",
    ]},
    {"key": "formats", "title": "The format rules", "rules": True, "steps": [
        "The rulebook for the shape this article was routed to",
    ]},
    {"key": "architect", "title": "Architect", "steps": [
        "Design the structure",
        "Go and research the parts the structure says are thin",
        "Place the company's own material",
        "Set a length for every section",
        "Pick the section keywords",
        "Write the headings",
    ]},
    {"key": "field", "title": "Voices from the field", "steps": [
        "Read where practitioners argue in public, and weave the real arguments in",
    ]},
    {"key": "writer", "title": "Writer", "steps": [
        "Write the body",
        "Blend the sections into one piece",
        "Write the intro, the TL;DR, the FAQ and the close",
        "Read the article whole",
        "Rewrite it to be read",
        "Re-shape the sentences",
        "Remove the tells of machine writing",
        "Lay in the links",
        "Scrub stray characters",
        "Assemble it",
    ]},
]


# ---- paths -----------------------------------------------------------------------------------

class PromptError(ValueError):
    """A save that was refused, carrying the sentence to put on screen."""


def known(name):
    return str(name or "") in EDITABLE


def _check(name):
    """Only a prompt the tab offers can be read or written through here.

    An allow-list rather than a path check, so ".." never has to be reasoned about: a name that is
    not one of the fourteen simply does not resolve to a path at all.
    """
    name = str(name or "")
    if name not in EDITABLE:
        raise PromptError("That is not a prompt this screen can change.")
    return name


def shipped_path(name):
    """The file inside the app bundle. Read only, always."""
    return os.path.join(SHIPPED, *str(name).split("/")) + ".md"


def override_dir():
    """Where the owner's own copies live: beside knowledge, under the data dir."""
    return os.path.join(store.data_dir(), "prompts")


def override_path(name):
    return os.path.join(override_dir(), *str(name).split("/")) + ".md"


# ---- reading ---------------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def shipped_text(name):
    return _read(shipped_path(_check(name))) or ""


def is_edited(name):
    return os.path.exists(override_path(_check(name)))


def current_text(name):
    """What the next article would actually use: the owner's copy if he saved one, else the
    shipped one. This is the same choice `install()` makes at run time, made in one function so
    the screen cannot show him something different from what the run will read."""
    name = _check(name)
    return _read(override_path(name)) if is_edited(name) else shipped_text(name)


def tokens(text):
    """Every {{TOKEN}} in a template, as a set."""
    return set(_TOKEN.findall(text or ""))


def one(name):
    """Everything the screen needs about a single prompt."""
    name = _check(name)
    shipped = shipped_text(name)
    text = current_text(name)
    title, note = EDITABLE[name]
    return {"name": name, "title": title, "note": note, "text": text, "shipped": shipped,
            "edited": is_edited(name), "filled": is_filled(name), "tokens": sorted(tokens(shipped)),
            "lines": len(text.splitlines()), "words": len(text.split())}


def listing():
    """The whole tab's data: the flow across the top, then the prompts grouped under it."""
    groups = []
    for g in GROUPS:
        rows = []
        for name, title, note in g["prompts"]:
            text = current_text(name)
            rows.append({"name": name, "title": title, "note": note, "edited": is_edited(name),
                         "lines": len(text.splitlines()), "words": len(text.split())})
        groups.append({"key": g["key"], "title": g["title"], "note": g["note"], "prompts": rows})
    return {"flow": FLOW, "groups": groups, "edited": sorted(n for n in EDITABLE if is_edited(n))}


# ---- writing ---------------------------------------------------------------------------------

def is_filled(name):
    """Does the CODE fill this prompt's blanks?

    The six writing prompts are loaded through `load_prompt` and then run through `sh.fill`, so
    every `{{TOKEN}}` in them is a blank the code puts a value into. The eight format rulebooks are
    not: `format_rules()` lifts their text and hands it to another prompt as one value, and nothing
    fills anything inside them. The two `{{TOKEN}}` names printed in a rulebook's developer header
    are that header SAYING which slot the file feeds, not blanks of its own, and the header is
    stripped before the model ever sees the file. Refusing to let him delete a sentence that only
    describes the plumbing would be the rule eating the reason it exists.
    """
    return not str(name).startswith("write/formats/")


def check_tokens(name, text):
    """The sentence to show him, or "" when the save is safe.

    Two rules, and each exists because getting it wrong breaks a run in a way he could not diagnose
    from the article that came out three steps later:

    * A LOST token, in a prompt the code fills, means the model reads a prompt with a hole where
      the article's facts should be. Refused, with the missing ones named.
    * An ADDED token, anywhere, is a blank nothing fills, so `{{LIKE_THIS}}` reaches the model as
      literal text. Refused in a rulebook too, because a rulebook's words are injected whole into
      the prompt the architect and the rewrite actually read. There is already a test asserting no
      prompt reaches the model with an unfilled token, and this editor must not be the way that
      test starts failing.
    """
    want, got = tokens(shipped_text(name)), tokens(text)
    lost = sorted(want - got) if is_filled(name) else []
    extra = sorted(got - want)
    if lost:
        return ("This version is missing %s the agent fills in: %s. Put %s back exactly as written, "
                "or the next article will be written from a prompt with a hole in it."
                % ("a placeholder" if len(lost) == 1 else "placeholders",
                   ", ".join("{{%s}}" % t for t in lost),
                   "it" if len(lost) == 1 else "them"))
    if extra:
        return ("Nothing fills %s, so %s would reach the model as it stands. Remove %s, or use one "
                "of the placeholders this prompt already has: %s."
                % (", ".join("{{%s}}" % t for t in extra),
                   "it" if len(extra) == 1 else "they",
                   "it" if len(extra) == 1 else "them",
                   ", ".join("{{%s}}" % t for t in sorted(want)) or "(this prompt has none)"))
    return ""


def _write_atomic(path, text):
    """Temp file in the SAME directory, then rename over the target. A crash mid-write leaves a
    stray .tmp and the old file intact, never half a prompt that the next run would read."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save(name, text):
    """Write his version under the data dir. Raises PromptError with a sentence for the screen.

    Nothing is written into the app bundle, and nothing is written into his own SEO folder. His
    ruling, 2026-09-09: "it only changes the Sutra app, forget about SEO by Devansh."
    """
    name = _check(name)
    if not isinstance(text, str) or not text.strip():
        raise PromptError("An empty prompt is not a save.")
    why = check_tokens(name, text)
    if why:
        raise PromptError(why)
    _write_atomic(override_path(name), text)
    return one(name)


def reset(name):
    """Back to what shipped, by deleting his copy. There is nothing else to undo."""
    name = _check(name)
    try:
        os.remove(override_path(name))
    except OSError:
        pass
    return one(name)


# ---- the two doors ---------------------------------------------------------------------------

def _writing_rules():
    """The shared ban list `load_prompt` folds into any prompt carrying {{WRITING_RULES}}."""
    return _read(os.path.join(SHIPPED, "_writing_rules.md")) or ""


def install():
    """Make every prompt read in this process prefer the owner's copy. Idempotent.

    Called once by agents_api at import, which is the process the run actually happens in: the
    panel's routes and the agent's loop share it, because a run is a background thread and not a
    subprocess. Tests and command-line runs never call it, so they read the shipped prompts.
    """
    try:
        from ..tools import _shared as sh
    except Exception:                       # noqa: BLE001 — no engine, nothing to override
        return False
    if not getattr(sh.load_prompt, "_prompt_override", False):
        base = sh.load_prompt

        def load_prompt(name):
            p = override_path(name) if known(name) else None
            text = _read(p) if p else None
            if text is None:
                return base(name)
            # the same fold `_shared.load_prompt` does, because an override skips it
            if "{{WRITING_RULES}}" in text:
                text = text.replace("{{WRITING_RULES}}", _writing_rules().strip())
            return text

        load_prompt.__doc__ = base.__doc__
        load_prompt._prompt_override = True
        sh.load_prompt = load_prompt

    try:
        from ..write import _common as C
    except Exception:                       # noqa: BLE001 — the write phase is optional here
        return True
    if not getattr(C.format_path, "_prompt_override", False):
        base_path = C.format_path

        def format_path(archetype):
            """His rulebook for this shape, if he saved one. format_rules() and readable.py both
            reach the file through this one function, so patching it covers both."""
            key = "write/formats/" + str(archetype or "")
            p = override_path(key) if known(key) else None
            return p if p and os.path.exists(p) else base_path(archetype)

        format_path.__doc__ = base_path.__doc__
        format_path._prompt_override = True
        C.format_path = format_path
    return True
