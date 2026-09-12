"""loop.py — think, do, look, think again. About a hundred lines, and no AI in any of it.

The rules that MUST hold are enforced here, in ordinary if-statements, never asked of the
model: stop before anything that costs money, stop when it wants to ask the user, cap the
number of moves, and write state to disk after every step. A rule the model is asked to
follow is a suggestion. A rule the loop enforces is a rule.

When it needs the user, the process does not sleep. It writes its files and RETURNS. The
answer comes back later as that tool's return value, and the model never knows it waited.
"""
import importlib
import json
import os
import re
import time
import traceback

from . import llm
from . import registry
from . import store

AUTONOMY_LIMIT = 25          # tool calls in a row before it must stop and ask
HERE = os.path.dirname(os.path.abspath(__file__))


def _system_prompt():
    with open(os.path.join(HERE, "prompts", "system.md"), encoding="utf-8") as f:
        tpl = f.read()

    voice = store.knowledge("brand_voice.json") or {}
    site = store.knowledge("site_index.json") or {}
    company = voice.get("company") or site.get("domain") or "this company"

    voice_block = ""
    if voice.get("summary"):
        voice_block = "## Their voice\n\n" + voice["summary"]
        if voice.get("avoid"):
            voice_block += "\n\nWords they never use: " + ", ".join(voice["avoid"][:15])

    rules = store.memory_rules()
    mem_block = ""
    if rules:
        mem_block = ("## Their standing rules\n\nFollow these unless they say otherwise "
                     "in this conversation:\n" + "\n".join("- " + r["text"] for r in rules))

    return (tpl.replace("{{COMPANY}}", company)
               .replace("{{KNOWLEDGE}}", _knowledge_block(site))
               .replace("{{VOICE}}", voice_block)
               .replace("{{MEMORY}}", mem_block))


_BAL = {"at": 0.0, "v": None}


def _cached_balance(dfs, ttl=300.0):
    """The DataForSEO balance, at most once every ttl seconds. The system prompt is built on
    every model turn and a network call per turn would be absurd."""
    now = time.time()
    if now - _BAL["at"] < ttl:
        return _BAL["v"]
    try:
        _BAL["v"] = float(dfs.balance())
    except Exception:  # noqa: BLE001 — never let a balance check break the prompt
        _BAL["v"] = None
    _BAL["at"] = now
    return _BAL["v"]


def _knowledge_block(site):
    """What is already on file, so the model never redoes setup that is done. Found live
    (2026-09-04): a fresh chat re-ran the whole setup because nothing told the model the site
    was catalogued, embedded and the brand pack built.

    EVERY LINE IS A FACT. Not one of them tells the model to do anything, and that is the rule,
    not a style note. This block is rebuilt into the system prompt on every single turn, so an
    instruction in here is not advice, it is a chore queued against whatever the person happened
    to type. Found live 2026-09-10: the tail said "Run onboard once, then carry on", the owner
    typed `hi` on a finished install, and the agent opened a four-question interview and left him
    waiting on it. The brief decides what to do about each state; this block only says what is so.
    """
    lines = []
    pages = site.get("pages") if isinstance(site, dict) else None
    if pages:
        lines.append("- Site catalogue: %s, %d pages, read %s." % (site.get("domain") or "the site", len(pages),
                                                                   site.get("indexed_at") or "earlier"))
    else:
        lines.append("- Site catalogue: NOT built. Nothing has been read from the website yet.")
    indexed = False
    try:
        from .tools import _index
        st = _index.status()
        indexed = bool(st.get("built"))
        lines.append("- Page index (meaning): built, %d pages, %d passages." % (st["pages"], st["chunks"])
                     if indexed else "- Page index (meaning): not built, so finding their own pages "
                                     "to link to falls back to matching title words. Building it needs a Voyage key.")
    except Exception:  # noqa: BLE001
        pass
    # what is connected, so the model says it up front instead of discovering it mid-run
    try:
        from .tools import _shared as _sh
        from .tools import dfs as _dfs
        mode = _sh.dfs_mode(_dfs)
        if mode == "live":
            bal = _cached_balance(_dfs)
            # "(too low for paid steps; they will skip and say so)" used to close this line, and it
            # was false for research: run_research refuses outright below the floor. Told "skip",
            # the agent promised to "run it and tell you exactly what came back empty", and then
            # the research did not start at all (owner's screenshot, 2026-09-11). So the line says
            # what actually happens at this balance.
            lines.append("- DataForSEO: connected%s." % ("" if bal is None else ", balance $%.2f%s"
                         % (bal, " -- NOT enough credits: research will not start until it is "
                                 "topped up, unless they ask to go ahead on placeholder numbers"
                                 if bal < 0.5 else "")))
        else:
            # "and everything else still works" used to end this line, and it was false. Asked
            # "does the research read the real Google results, yes or no", the agent reasoned
            # correctly from it and answered "Yes" — while serp_advanced was returning
            # _demo_serp_extract: ten manufactured results, an invented snippet, an invented AI
            # Overview (found 2026-09-10). A wrong capability claim is worse than a wrong number,
            # because a demo number arrives labelled and a capability claim does not.
            lines.append("- DataForSEO: NOT connected, so the volumes, the difficulty, the ranking "
                         "positions, the per-page traffic AND the search results the research "
                         "reads are all demo: manufactured, not measured.")
    except Exception:  # noqa: BLE001
        pass
    try:
        from .tools import voyage as _voy
        lines.append("- Voyage (for finding your own pages to link to): connected."
                     if _voy.available() else
                     "- Voyage: no key, so internal links fall back to title-word matching.")
    except Exception:  # noqa: BLE001
        pass

    brief = store.knowledge("brand/writer-brief.md")
    lines.append("- Brand pack: built (writer brief on file)." if isinstance(brief, str) and brief.strip()
                 else "- Brand pack: not built, so nothing on file says how they write or what they sell.")
    # Whether the setup questions have been put to them. Without this line the model has no way to
    # know, so it either never asks or asks a user who has already answered, and both are the same
    # bug the block above was written to stop: setup redone because nothing said it was done.
    interview = None
    try:
        from .tools import onboard as _onboard
        interview = _onboard.status()
        if interview["asked"]:
            lines.append("- Setup questions: all four have been put to them, %d answered and %d "
                         "passed over." % (interview["answered"], interview["skipped"]))
        elif interview["started"]:
            lines.append("- Setup questions: started but not finished, %d of %d answered; the rest "
                         "have not been put to them." % (interview["done"], interview["total"]))
        else:
            lines.append("- Setup questions: never asked, so the four answers only they can give "
                         "(their real numbers, why the company was built, what did not work, who "
                         "they compete with) are not in the brand pack.")
    except Exception:  # noqa: BLE001 — a missing ledger must never break the prompt
        pass

    done = pages and isinstance(brief, str) and brief.strip()
    tail = ("\nSetup is complete: the site is read and the brand pack is built." if done else
            "\nSetup is not finished: whatever is marked not built above is not on file.")
    # The asset sheet. STATE only. What to DO about each state is written once, in the brief's
    # "What to write next"; a rule kept in both places drifts and the model then picks whichever
    # copy it read last. Three states, and every one of them must be a LINE: absence of a line is
    # not a state a model can act on. Asked "what should I write?" with nothing saying the engine
    # had never run, it invented a topic (2026-09-09). The owner's words: "it should say 'hey look,
    # you've not updated the asset engine yet'. That's how precise I want it to be."
    #
    # The next idea's WHOLE title is here, not 70 characters of it. Truncated mid-word, the model
    # cannot offer the idea without paraphrasing the half it was given, so it re-titles the article
    # and the offer stops being the idea on the sheet (2026-09-10).
    try:
        from .tools import build_assets as _ba
        a = _ba.status()
        if a["built"] and a["next"]:
            lines.append("- Asset ideas: %d on the sheet, %d still to write. Top of the ranking, "
                         "still open: %s, \"%s\"."
                         % (a["total"], a["counts"].get("open", 0),
                            a["next"]["id"], a["next"]["title"][:200]))
        elif a["built"]:
            lines.append("- Asset ideas: %d on the sheet, none left to write." % a["total"])
        else:
            lines.append("- Asset ideas: NO sheet. The asset engine has never run, so there is "
                         "nothing to pick from and nothing to offer.")
    except Exception:   # noqa: BLE001 — a sheet we cannot read must not stop the run starting
        pass

    # An install from before the interview existed has a finished pack and an unasked user. State
    # the loss, so "setup is complete" does not read as "there is nothing left to ask" — and state
    # ONLY the loss. This line used to end "Run onboard once, then carry on", and on 2026-09-10 the
    # owner said `hi` and got question 1 of 4. Whether four questions are worth interrupting a
    # greeting for is a judgement, and judgement lives in the brief.
    if done and interview and not interview["asked"]:
        tail += " The brand pack was built without the setup answers."
    return ("## What is already in Knowledge\n\nFacts about what is on file. Nothing here is an "
            "instruction and nothing here is a job to start: the rules below decide what to do "
            "about each state.\n\n" + "\n".join(lines) + tail)



# ---- the idea an offer was made FROM ---------------------------------------------------------
# The chip on the Asset ideas tab starts a run with `idea_id` already on its state, and
# save_to_library ticks the sheet from that and from nothing else. The brief now has the agent
# OFFER the top open idea in the chat as well, and accepting that offer has to count the same way,
# or the idea he just had written is offered to him again on the next turn, for ever.
#
# PROVENANCE, NEVER MATCHING. The model was told to name the idea by id, so the id is sitting in
# its own question as data we can read straight back, and it is checked against the sheet before
# it counts. A finished article is never matched to an open idea by meaning: that was ruled out on
# 2026-09-09 and this does not revisit it.
IDEA_ID = re.compile(r"\ba\d{1,6}\b", re.I)

# The whole reply, when somebody just says yes. Longer than this and they are saying something
# else as well ("yes but write about pricing instead"), which is not an acceptance of this offer.
YES_CAP = 24
YES = ("yes", "yep", "yeah", "yup", "ok", "okay", "sure", "go ahead", "do it", "please do",
       "sounds good", "write it", "that one", "go for it")


def _open_idea_ids():
    """The ids still to write. A sheet we cannot read is treated as no sheet."""
    try:
        from .assets import _common as acm
        return {(r.get("id") or "").lower() for r in acm.ideas() if r.get("status") == "open"}
    except Exception:   # noqa: BLE001 — a sheet we cannot read must never break a question
        return set()


def _offered_idea(payload):
    """The open idea this question puts to the person, when it puts exactly one. Two ids, or an
    id that is not on the sheet, offer nothing: a guess here would tick the wrong row."""
    text = " ".join([str(payload.get("question") or ""), str(payload.get("why") or "")] +
                    [str(o.get("label") or "") + " " + str(o.get("note") or "")
                     for o in (payload.get("options") or []) if isinstance(o, dict)])
    found = {m.lower() for m in IDEA_ID.findall(text)} & _open_idea_ids()
    return found.pop() if len(found) == 1 else ""


def _took_the_offer(answer, idea):
    """Did this answer accept THAT idea? Either it names the id (the option chip carries it) or it
    is a short, plain yes. Naming another topic is not an acceptance, and neither is silence."""
    said = " ".join(str((answer or {}).get(k) or "") for k in ("choice", "text", "note")).strip()
    if not said:
        return False
    if idea and idea.lower() in {m.lower() for m in IDEA_ID.findall(said)}:
        return True
    plain = said.lower().strip(" .!,")
    return len(plain) <= YES_CAP and (plain in YES or any(plain.startswith(y + " ") or
                                                          plain.startswith(y + ",") for y in YES))



def _trailing_question(text):
    """The question a plain-prose turn ends on, or "".

    A QUESTION ASKED IN PROSE USED TO END THE RUN. The brief says to ask through `ask_user`, and
    across 18 first turns and three models, 11 of them asked in prose instead — the same model
    doing both in one conversation. The loop then filed the turn as `done`, the state a finished
    answer gets: the question sat on screen with the run over behind it, and whatever the person
    typed next opened a fresh run that knew nothing about what had been asked (2026-09-10).
    A rule the model is asked to follow is a suggestion; this is the loop making it true.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1].rstrip("*_`\"')] ").rstrip()
    return last if last.endswith("?") else ""


def _run_tool(chat_id, run_id, name, args, step_id=None):
    """Import the tool's module and call run(). Tools get the run context so they can
    write artifacts and emit their own sub-step progress.

    step_id matters: without it a tool's substeps have no parent and the screen cannot
    group them under the step that started them. They float free and read as noise.
    """
    spec = registry.get(name)
    # registry names modules relative to this package ("tools.index_site"), so the
    # import is anchored on __package__ and never on sys.path.
    mod = importlib.import_module("." + spec["module"], package=__package__)
    ctx = {"chat_id": chat_id, "run_id": run_id, "step_id": step_id,
           "emit": lambda **kw: store.emit(chat_id, run_id, **kw)}
    return mod.run(ctx, **(args or {}))


# Which checkpoints still STOP the run, and which are now just published.
#
# The owner's call, 2026-09-09, once every output began landing in the Library as it is made:
# a checkpoint that only SHOWS him something has stopped earning its interruption, because he can
# read the same thing in the Library whenever he likes. What survives is the two that are not
# reviews at all:
#
#   topic_list — a decision only he can make. The agent cannot know which idea he wants.
#   article    — the last moment before something becomes finished work.
#
# The brand pack, the research brief and the plan are now written, announced, and passed. They were
# the three that interrupted him five times a run to say "look at this", and the answer was almost
# always yes. Nothing is lost: they are in the Library, readable at any point, and a run that made
# a bad plan is still stopped at the draft.
#
# Do not add a view here without the same argument. Every stop costs a person their attention, and
# the test is whether the agent genuinely cannot continue without an answer.
WAITING_VIEWS = ("topic_list", "article")

# The three tools that only ever run while making an article. The first of them to finish opens the
# Library row, so a person can watch it fill in instead of being stopped and shown things.
ARTICLE_TOOLS = ("run_research", "build_blueprint", "write_article")
VIEW_LABEL = {"brand_pack": "the brand pack", "research_brief": "the research",
              "blueprint": "the plan", "topic_list": "the topics", "article": "the draft"}


def _wait(chat_id, run_id, kind, call_id, payload, stage=None):
    fields = {"status": "waiting",
              "waiting_on": dict(payload, kind=kind, call_id=call_id)}
    if stage:
        fields["stage"] = stage
    store.patch_state(chat_id, run_id, **fields)
    # call_id rides on the event too, so the screen can pair a later "resumed" with the
    # exact question it answered instead of guessing by order.
    store.emit(chat_id, run_id, "waiting", kind=kind, call_id=call_id, stage=stage, **payload)


STAGE_FOR = {"index_site": "setup", "build_page_index": "setup", "learn_brand": "setup",
             "onboard": "setup", "refresh_site": "setup",
             "suggest_topics": "topic", "run_research": "research",
             "build_blueprint": "blueprint", "write_article": "draft"}
VIEW_STAGE = {"brand_pack": "setup", "topic_list": "topic", "research_brief": "research",
              "blueprint": "blueprint", "article": "draft"}


def _ask_interview(chat_id, run_id, call_id, ask):
    """One setup question, through the SAME checkpoint every approval already uses.

    The kind stays "question" on purpose. The screen already draws that kind, with its option
    chips and its free-text box, and a new kind would have drawn nothing at all until the front
    end caught up. What marks it as part of the interview is the `interview` field, which carries
    the id of the question the answer belongs to, so resume() files it without guessing by order.

    Every question is skippable, and the skip is an option the user picks rather than a silence we
    infer. A run that never asked and a user who had nothing to say must not look the same.
    """
    from .tools import onboard
    _wait(chat_id, run_id, "question", call_id, {
        "question": ask.get("question", ""),
        "why": ask.get("why", ""),
        "interview": ask.get("id", ""),
        "step": ask.get("step"), "of": ask.get("of"),
        "options": [{"label": onboard.SKIP_LABEL}]}, stage="setup")


def _ask_asset_gate(chat_id, run_id, call_id, gate):
    """One asset-engine gate, through the SAME checkpoint every approval already uses.

    Two of the original's layer-02 steps stop and ask a person: the competitor shortlist
    (`1-competitor-study` step A4, "this is a gate") and the subreddit list (`3-study-trends` A2).
    Neither is a rubber stamp. A shortlist nobody looked at sends fifteen paid pulls at the wrong
    companies, and a subreddit list nobody looked at mines the wrong argument for a week.

    Same `kind: "question"` as the setup interview, for the same reason: the screen already draws
    that kind with its option chips and its free-text box. What marks it as a gate is the
    `asset_gate` field, which carries the builder's name so resume() files the answer against the
    right one instead of guessing by order.
    """
    _wait(chat_id, run_id, "question", call_id, {
        "question": gate.get("question") or gate.get("why", ""),
        "why": gate.get("why", ""),
        "asset_gate": gate.get("kind", ""),
        "builder": gate.get("builder", ""),
        "proposed": gate.get("proposed") or [],
        "options": [{"label": "Use this list"}, {"label": "Not now"}]}, stage="setup")


def _ask_words(chat_id, run_id, call_id, ask):
    """The one length question, asked once per article, through the ordinary checkpoint.

    It sits at the end of the keyword work, once the pages that rank have been measured, and
    BEFORE the research conversation. That ordering is the whole point: the four researchers are
    the longest and most expensive part of a run, so this is the last cheap moment to ask. Saying
    yes here also starts them.

    Why this is the only length question. The length used to be decided twice by two steps that
    never spoke: the architect budgeted from the band the ranking pages set, and then readable
    re-decided it from a hardcoded 2,100 that knew nothing about those pages. Competitors at 3,200
    words and competitors at 1,400 both produced an article cut to 2,100. Now one number is
    settled here, by a person, and every step downstream reads that one.
    """
    band = ask.get("band") or {}
    _wait(chat_id, run_id, "question", call_id, {
        "question": ask.get("question", ""),
        "why": ask.get("why", ""),
        "ask_words": True,
        "suggested": ask.get("suggested"),
        "band": band,
        "options": [{"label": "Yes, %s words" % "{:,}".format(int(ask.get("suggested") or 0))}]},
        stage="research")


def _resume_words(chat_id, run_id, waiting, messages, answer):
    """Take the number, write it where every later step reads it, and carry on into the research.

    A typed number WINS over the suggestion. Somebody who typed 1,800 when offered 2,700 meant it,
    and quietly using the suggestion anyway would make the question decorative.
    """
    call_id = waiting.get("call_id")
    text = (answer.get("text") or "").strip() if isinstance(answer, dict) else str(answer or "")
    picked = None
    m = re.search(r"\b(\d{3,5})\b", text.replace(",", ""))
    if m:
        picked = int(m.group(1))
    if picked is None or not (200 <= picked <= 20000):
        picked = int(waiting.get("suggested") or 0) or None

    store.patch_state(chat_id, run_id, word_target=picked)
    store.emit(chat_id, run_id, "resumed", by="user",
               answer=("%s words" % "{:,}".format(picked)) if picked else "kept the measured band")

    step_id = "s%d" % (int(time.time() * 1000) % 100000)
    store.emit(chat_id, run_id, "step_started", id=step_id,
               label=registry.label("run_research"), tool="run_research", stage="research")
    t0 = time.time()
    try:
        out = _run_tool(chat_id, run_id, "run_research", {"word_target": picked}, step_id=step_id)
    except Exception as e:  # noqa: BLE001
        out = {"error": str(e)[:600],
               "hint": "The research could not finish. Say so in one line and carry on."}
    store.emit(chat_id, run_id, "step_finished", id=step_id, label=registry.label("run_research"),
               ms=int((time.time() - t0) * 1000), summary=(out or {}).get("summary", ""))

    if isinstance(out, dict) and out.get("ask_words"):
        _ask_words(chat_id, run_id, call_id, out["ask_words"])
        return store.get_state(chat_id, run_id)

    messages.append({"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": call_id, "content": out}]})
    store.save_messages(chat_id, messages)
    store.patch_state(chat_id, run_id, status="running", waiting_on=None)
    return step(chat_id, run_id)


def _resume_asset_gate(chat_id, run_id, waiting, messages, answer):
    """File the approval, then run the engine again from where it stopped.

    The whole engine is ONE tool call and gets ONE tool result, at the end, exactly as the setup
    interview does. The model never sees a half-built sheet it could decide to finish itself, in
    its own words, with ideas it made up.
    """
    from .assets import _common as acm
    from .tools import build_assets
    call_id = waiting.get("call_id")
    text = (answer.get("text") or "").strip() if isinstance(answer, dict) else str(answer or "")
    declined = text.lower().startswith("not now") or answer.get("approved") is False

    if declined:
        store.emit(chat_id, run_id, "resumed", by="user", approved=False, answer="Not now")
        messages.append({"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": call_id,
            "content": {"summary": "The asset engine is paused: the %s list was not approved."
                                   % waiting.get("asset_gate", "proposed"),
                        "hint": "Say so in one line and carry on. Do not ask again unprompted."}}]})
        store.save_messages(chat_id, messages)
        store.patch_state(chat_id, run_id, status="running", waiting_on=None)
        return step(chat_id, run_id)

    # An edited list wins over the proposed one. A person who rewrote the list meant it, and
    # taking the proposal anyway would make the gate decorative.
    approved = acm.parse_gate_answer(waiting.get("asset_gate"), text, waiting.get("proposed") or [])
    try:
        acm.save_gate(waiting.get("builder") or waiting.get("asset_gate"), approved)
    except Exception as e:  # noqa: BLE001 — an answer we cannot file must not strand the run
        store.emit(chat_id, run_id, "step_failed", label=registry.label("build_assets"),
                   reason=str(e)[:400], detail=traceback.format_exc()[-1200:], recovering=True)
    store.emit(chat_id, run_id, "resumed", by="user", answer="%d approved" % len(approved))

    step_id = "s%d" % (int(time.time() * 1000) % 100000)
    store.emit(chat_id, run_id, "step_started", id=step_id,
               label=registry.label("build_assets"), tool="build_assets", stage="setup")
    t0 = time.time()
    try:
        out = _run_tool(chat_id, run_id, "build_assets", {}, step_id=step_id)
    except Exception as e:  # noqa: BLE001
        out = {"error": str(e)[:600],
               "hint": "The asset engine could not finish. Say so in one line and carry on."}
    store.emit(chat_id, run_id, "step_finished", id=step_id, label=registry.label("build_assets"),
               ms=int((time.time() - t0) * 1000), summary=(out or {}).get("summary", ""))

    if isinstance(out, dict) and out.get("gate"):
        _ask_asset_gate(chat_id, run_id, call_id, out["gate"])
        return store.get_state(chat_id, run_id)

    messages.append({"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": call_id, "content": out}]})
    store.save_messages(chat_id, messages)
    store.patch_state(chat_id, run_id, status="running", waiting_on=None)
    return step(chat_id, run_id)


def _resume_interview(chat_id, run_id, waiting, messages, answer):
    """File the answer, then ask the next question or hand the model the finished interview.

    The whole interview is ONE tool call, so it gets ONE tool result, at the end. The model never
    sees a half-answered interview: it cannot then decide to ask the rest itself, in its own
    words, and drop the answers into a message instead of a file.
    """
    from .tools import onboard
    call_id = waiting.get("call_id")
    text, skipped = onboard.read_answer(answer)
    try:
        onboard.record(waiting.get("interview"), text, skipped=skipped)
    except Exception as e:  # noqa: BLE001 — a question we cannot file must not strand the run
        store.emit(chat_id, run_id, "step_failed", label=registry.label("onboard"),
                   reason=str(e)[:400], detail=traceback.format_exc()[-1200:], recovering=True)
    store.emit(chat_id, run_id, "resumed", by="user",
               answer=("Skipped" if skipped else text[:200]))

    step_id = "s%d" % (int(time.time() * 1000) % 100000)
    store.emit(chat_id, run_id, "step_started", id=step_id,
               label=registry.label("onboard"), tool="onboard", stage="setup")
    t0 = time.time()
    try:
        out = _run_tool(chat_id, run_id, "onboard", {}, step_id=step_id)
    except Exception as e:  # noqa: BLE001
        out = {"error": str(e)[:600],
               "hint": "The setup questions could not be finished. Say so in one line and carry on."}
    store.emit(chat_id, run_id, "step_finished", id=step_id, label=registry.label("onboard"),
               ms=int((time.time() - t0) * 1000), summary=(out or {}).get("summary", ""))

    if isinstance(out, dict) and out.get("ask"):
        _ask_interview(chat_id, run_id, call_id, out["ask"])
        return store.get_state(chat_id, run_id)

    messages.append({"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": call_id, "content": out}]})
    store.save_messages(chat_id, messages)
    store.patch_state(chat_id, run_id, status="running", waiting_on=None)
    return step(chat_id, run_id)


def step(chat_id, run_id):
    """One pass. Runs tools until it finishes or needs the user, then returns."""
    state = store.get_state(chat_id, run_id)
    if not state or state["status"] not in ("running",):
        return state

    messages = store.get_messages(chat_id)
    moves = 0

    while True:
        if moves >= AUTONOMY_LIMIT:
            _wait(chat_id, run_id, "question", None, {
                "question": "I've run %d steps in a row without checking in. Keep going?" % moves,
                "why": "A safety limit, so nothing runs away unattended.",
                "options": [{"label": "Keep going", "recommended": True},
                            {"label": "Stop here"}]})
            store.save_messages(chat_id, messages)
            return store.get_state(chat_id, run_id)

        t_model = time.time()
        try:
            reply = llm.call(_system_prompt(), messages, registry.for_model(),
                             on_retry=lambda m: store.emit(chat_id, run_id, "note", label=m))
            # How long the model took is the one number nobody can reconstruct later, and
            # the first live run had an unexplained hour between two turns. Record it.
            store.emit(chat_id, run_id, "model_turn", ms=int((time.time() - t_model) * 1000),
                       tool_calls=len(reply.get("tool_calls") or []),
                       provider=llm.provider())
        except llm.NoKey as e:
            store.emit(chat_id, run_id, "step_failed", label="Model", reason=str(e), recovering=False)
            store.patch_state(chat_id, run_id, status="failed", error=str(e))
            return store.get_state(chat_id, run_id)
        except Exception as e:
            store.emit(chat_id, run_id, "step_failed", label="Model call",
                       reason=str(e)[:400], recovering=False)
            store.patch_state(chat_id, run_id, status="failed", error=str(e)[:400])
            return store.get_state(chat_id, run_id)

        # plain answer, no tools — the run is over, UNLESS it ended on a question
        if not reply["tool_calls"]:
            if reply["text"]:
                messages.append({"role": "assistant", "content": reply["text"]})
                store.emit(chat_id, run_id, "message", text=reply["text"])
            asked = _trailing_question(reply["text"])
            if asked:
                store.save_messages(chat_id, messages)
                payload = {"question": asked, "why": "", "options": [], "prose": True}
                offered = _offered_idea({"question": reply["text"]})
                if offered:
                    payload["offer_idea"] = offered
                _wait(chat_id, run_id, "question", None, payload)
                return store.get_state(chat_id, run_id)
            store.save_messages(chat_id, messages)
            store.patch_state(chat_id, run_id, status="done")
            store.emit(chat_id, run_id, "run_finished")
            return store.get_state(chat_id, run_id)

        # record the assistant turn (with its tool calls) before running anything
        blocks = []
        if reply["text"]:
            blocks.append({"type": "text", "text": reply["text"]})
            store.emit(chat_id, run_id, "message", text=reply["text"])
        for c in reply["tool_calls"]:
            blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"],
                           "input": c["input"]})
        messages.append({"role": "assistant", "content": blocks})

        results = []
        for call in reply["tool_calls"]:
            name, args, call_id = call["name"], call["input"] or {}, call["id"]

            # --- the pausing tools -------------------------------------------------------
            if name == "ask_user":
                store.save_messages(chat_id, messages)
                payload = {"question": args.get("question", ""),
                           "why": args.get("why", ""),
                           "options": args.get("options", [])}
                offered = _offered_idea(payload)
                if offered:
                    payload["offer_idea"] = offered
                _wait(chat_id, run_id, "question", call_id, payload)
                return store.get_state(chat_id, run_id)

            if name == "show_artifact":
                view = args.get("view", "article")
                # A STOP HAS TO HAVE SOMETHING TO LOOK AT. Asked "what topics should we cover"
                # with a sheet on file, the model showed topic_list pointing at a topics.json no
                # tool had written (found live, 2026-09-10): the run then sat waiting on an empty
                # panel, and only a Stop got it back. The file has to exist before we stop for it.
                art_name = (args.get("path") or "").strip()
                if view in WAITING_VIEWS and not (art_name and os.path.isfile(
                        store.artifact_path(chat_id, run_id, art_name))):
                    results.append({"type": "tool_result", "tool_use_id": call_id, "content": {
                        "error": "There is no artifact called %r in this run, so there is nothing "
                                 "to show." % art_name,
                        "hint": "Nothing wrote that file. Say what you have in plain words, or run "
                                "the step that writes it first. Do not show it again."}})
                    continue
                if view in WAITING_VIEWS:
                    store.save_messages(chat_id, messages)
                    _wait(chat_id, run_id, "artifact", call_id, {
                        "artifact": args.get("path", ""),
                        "view": view,
                        "prompt": args.get("prompt", "Have a look before I carry on.")},
                        stage=VIEW_STAGE.get(view))
                    return store.get_state(chat_id, run_id)
                # Everything else is PUBLISHED, not waited on. See WAITING_VIEWS for why.
                if VIEW_STAGE.get(view):
                    store.patch_state(chat_id, run_id, stage=VIEW_STAGE[view])
                store.emit(chat_id, run_id, "artifact_ready", view=view,
                           artifact=args.get("path", ""),
                           label=VIEW_LABEL.get(view, view.replace("_", " ")))
                results.append({"type": "tool_result", "tool_use_id": call_id, "content": {
                    "shown": True, "waited": False,
                    "note": ("It is on screen and in the Library. Do NOT ask whether it looks "
                             "right and do NOT wait: carry straight on to the next step. Say in "
                             "one short sentence what you made and that it is there to read.")}})
                continue

            # --- non-pausing UI tools ----------------------------------------------------
            if name == "log_step":
                store.emit(chat_id, run_id, "note", label=args.get("message", ""))
                results.append({"type": "tool_result", "tool_use_id": call_id,
                                "content": {"ok": True}})
                continue

            if name == "save_memory":
                row = store.add_memory(args.get("text", ""), args.get("kind", "rule"),
                                       source="agent", from_run=run_id)
                store.emit(chat_id, run_id, "memory_saved", text=row["text"], id=row["id"])
                results.append({"type": "tool_result", "tool_use_id": call_id,
                                "content": {"ok": True, "id": row["id"]}})
                continue

            # --- the money gate, enforced here and not by the model ----------------------
            state = store.get_state(chat_id, run_id)
            approved = set(state.get("approved_tools", []))
            if registry.gate(name) in ("ask_before", "always_approve") and name not in approved:
                store.save_messages(chat_id, messages)
                cost, mins = registry.cost(name), registry.est_minutes(name)
                bits = []
                if cost:
                    bits.append("about %d credits" % cost)
                if mins:
                    bits.append("around %d minutes" % mins)
                _wait(chat_id, run_id, "approval", call_id, {
                    "tool": name, "args": args,
                    "question": "%s needs %s. Go ahead?" % (registry.label(name),
                                                            " and ".join(bits) or "your approval"),
                    "why": "Paid step. Nothing is spent until you say yes.",
                    "cost_credits": cost, "est_minutes": mins,
                    "options": [{"label": "Go ahead", "recommended": True},
                                {"label": "Not now"}]},
                    stage=STAGE_FOR.get(name))
                return store.get_state(chat_id, run_id)

            # --- an ordinary tool --------------------------------------------------------
            step_id = "s%d" % (int(time.time() * 1000) % 100000)
            store.emit(chat_id, run_id, "step_started", id=step_id,
                       label=registry.label(name), tool=name, stage=STAGE_FOR.get(name))
            if STAGE_FOR.get(name):
                store.patch_state(chat_id, run_id, stage=STAGE_FOR[name], current_step=name)
            t0 = time.time()
            try:
                out = _run_tool(chat_id, run_id, name, args, step_id=step_id)
                ms = int((time.time() - t0) * 1000)
                # A Library row is born here, not at loop.start, because not every run is an
                # article: indexing a site or refreshing the catalogue must not leave a row behind.
                # These three tools only ever run for an article, and library_start is idempotent
                # by construction (its id is a pure function of the run), so whichever fires first
                # makes the row and the others find it.
                if name in ARTICLE_TOOLS and not (out or {}).get("error"):
                    try:
                        store.library_start(chat_id, run_id,
                                            (store.get_state(chat_id, run_id) or {}).get("request", ""))
                    except Exception:   # noqa: BLE001 — a row we cannot open must never lose the run
                        pass
                store.emit(chat_id, run_id, "step_finished", id=step_id,
                           label=registry.label(name), ms=ms,
                           summary=(out or {}).get("summary", ""))
                # A tool that came back with a question for the user (the setup interview) waits
                # here instead of answering the model. Same _wait, same resume, no second
                # mechanism: the tool decides WHAT to ask, the loop decides that we stop.
                if isinstance(out, dict) and out.get("ask"):
                    store.save_messages(chat_id, messages)
                    _ask_interview(chat_id, run_id, call_id, out["ask"])
                    return store.get_state(chat_id, run_id)
                if isinstance(out, dict) and out.get("gate"):
                    store.save_messages(chat_id, messages)
                    _ask_asset_gate(chat_id, run_id, call_id, out["gate"])
                    return store.get_state(chat_id, run_id)
                if isinstance(out, dict) and out.get("ask_words"):
                    store.save_messages(chat_id, messages)
                    _ask_words(chat_id, run_id, call_id, out["ask_words"])
                    return store.get_state(chat_id, run_id)
                if registry.cost(name):
                    s = store.get_state(chat_id, run_id)
                    store.patch_state(chat_id, run_id,
                                      credits_spent=s.get("credits_spent", 0) + registry.cost(name))
                results.append({"type": "tool_result", "tool_use_id": call_id, "content": out})
            except Exception as e:
                ms = int((time.time() - t0) * 1000)
                detail = traceback.format_exc(limit=3)
                store.emit(chat_id, run_id, "step_failed", id=step_id,
                           label=registry.label(name), ms=ms,
                           reason=str(e)[:400], detail=detail[-1200:], recovering=True)
                results.append({"type": "tool_result", "tool_use_id": call_id,
                                "content": {"error": str(e)[:600],
                                            "hint": "Tell the user what failed and what you will try instead."}})
            moves += 1

        messages.append({"role": "user", "content": results})
        store.save_messages(chat_id, messages)


def start(chat_id, run_id, user_text):
    messages = store.get_messages(chat_id)
    messages.append({"role": "user", "content": user_text})
    store.save_messages(chat_id, messages)
    store.patch_state(chat_id, run_id, status="running")
    return step(chat_id, run_id)


def resume(chat_id, run_id, answer):
    """The user's answer becomes the waiting tool's return value. Then straight back in.

    An approval is special. The user approved THIS call, so the honest thing is to run it
    now and hand back the real result. Bouncing back to the model and hoping it asks again
    wastes a turn and, worse, lets it change its mind about a step the user just paid for.
    """
    state = store.get_state(chat_id, run_id)
    if not state or state.get("status") != "waiting":
        return state
    w = state.get("waiting_on") or {}
    messages = store.get_messages(chat_id)
    call_id = w.get("call_id")

    if not isinstance(answer, dict):
        answer = {"text": str(answer)}

    # A setup-interview answer goes into a file, not into the conversation. It is checked before
    # the ordinary question branch because it looks exactly like one on the wire.
    if w.get("interview"):
        return _resume_interview(chat_id, run_id, w, messages, answer)

    # An asset-engine gate also goes into a file rather than into the conversation, and also looks
    # exactly like an ordinary question on the wire.
    if w.get("asset_gate"):
        return _resume_asset_gate(chat_id, run_id, w, messages, answer)

    # The length answer becomes a number in the run's state, not a message. Checked before the
    # ordinary question branch because on the wire it looks exactly like one.
    if w.get("ask_words"):
        return _resume_words(chat_id, run_id, w, messages, answer)

    # A question the model asked in prose has no tool call behind it, so the answer goes back as
    # an ordinary user message. Sending a tool_result with a null id here would be a malformed
    # turn, and on the API providers an outright invalid one.
    if w.get("prose"):
        offered = w.get("offer_idea")
        if offered and not str(state.get("idea_id") or "").strip() and _took_the_offer(answer, offered):
            store.patch_state(chat_id, run_id, idea_id=offered)
            store.emit(chat_id, run_id, "idea_started", idea_id=offered)
        store.emit(chat_id, run_id, "resumed", by="user", answer=_answer_summary(answer))
        said = next((str(answer.get(k)).strip() for k in ("text", "choice", "changes", "note")
                     if str(answer.get(k) or "").strip()), _answer_summary(answer))
        messages.append({"role": "user", "content": said})
        store.save_messages(chat_id, messages)
        store.patch_state(chat_id, run_id, status="running", waiting_on=None)
        return step(chat_id, run_id)

    if w.get("kind") == "approval":
        tool = w.get("tool")
        if not answer.get("approved"):
            note = (answer.get("note") or "").strip()
            store.emit(chat_id, run_id, "resumed", by="user", approved=False,
                       note="declined " + str(tool), answer=note or "Not now")
            content = {"declined": True,
                       "hint": "The user said not now. Do not retry it. Offer a cheaper "
                               "path or ask what they would prefer instead."}
            if note:
                content["user_said"] = note
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": call_id, "content": content}]})
        else:
            store.emit(chat_id, run_id, "resumed", by="user", approved=True,
                       note="approved " + str(tool), answer="Go ahead")
            approved = set(state.get("approved_tools", []))
            approved.add(tool)
            store.patch_state(chat_id, run_id, approved_tools=sorted(approved))

            # run the very call they approved, right here
            args = w.get("args") or {}
            step_id = "s%d" % (int(time.time() * 1000) % 100000)
            store.emit(chat_id, run_id, "step_started", id=step_id,
                       label=registry.label(tool), tool=tool, stage=STAGE_FOR.get(tool))
            if STAGE_FOR.get(tool):
                store.patch_state(chat_id, run_id, stage=STAGE_FOR[tool], current_step=tool)
            t0 = time.time()
            try:
                out = _run_tool(chat_id, run_id, tool, args, step_id=step_id)
                store.emit(chat_id, run_id, "step_finished", id=step_id,
                           label=registry.label(tool), ms=int((time.time() - t0) * 1000),
                           summary=(out or {}).get("summary", ""))
                cost = registry.cost(tool)
                if cost:
                    cur = store.get_state(chat_id, run_id)
                    store.patch_state(chat_id, run_id,
                                      credits_spent=cur.get("credits_spent", 0) + cost)
                result = out
            except Exception as e:
                store.emit(chat_id, run_id, "step_failed", id=step_id,
                           label=registry.label(tool), ms=int((time.time() - t0) * 1000),
                           reason=str(e)[:400], detail=traceback.format_exc()[-1200:],
                           recovering=True)
                result = {"error": str(e)[:600],
                          "hint": "Tell the user what failed and what you will try instead."}
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": call_id, "content": result}]})
    else:
        # They took the idea the question offered, so this run started from it. Recorded here, at
        # the moment of the decision, exactly as the Asset ideas chip records it before the run
        # begins. save_to_library reads it later; nothing downstream has to work anything out.
        offered = w.get("offer_idea")
        if offered and not str(state.get("idea_id") or "").strip() and _took_the_offer(answer, offered):
            store.patch_state(chat_id, run_id, idea_id=offered)
            store.emit(chat_id, run_id, "idea_started", idea_id=offered)
        store.emit(chat_id, run_id, "resumed", by="user", answer=_answer_summary(answer))
        content = dict(answer)
        if w.get("kind") == "artifact":
            # The tool promised "returns the artifact, which may have been edited", so hand
            # back what is on disk NOW, not what the model wrote. If the user picked a topic,
            # spell it out so the model does not have to look it up by id.
            if w.get("artifact") == "brand":
                # the brand pack is not one file; hand the model the pack summary plus the
                # brief it will write from, so it can answer questions about it
                try:
                    from .brand import pack as _pack
                    art = _pack.summary()
                except Exception:  # noqa: BLE001
                    art = {"files": store.list_knowledge("brand")}
            else:
                art = store.load_artifact(chat_id, run_id, w.get("artifact", ""))
            if isinstance(art, dict) and answer.get("picked") and isinstance(art.get("topics"), list):
                chosen = [t for t in art["topics"] if t.get("id") == answer.get("picked")]
                if chosen:
                    content["picked_topic"] = chosen[0]
            if art is not None:
                text = art if isinstance(art, str) else json.dumps(art, ensure_ascii=False)
                content["artifact"] = art if len(text) <= 24000 else (
                    text[:24000] + "\n... (truncated; the file on disk is complete)")
            saved = _save_if_draft_approved(chat_id, run_id, w, answer)
            if saved:
                content["saved_to_library"] = saved
                content["artifact"] = "(the approved draft; it is now in the Library as '%s')" % saved["title"]
        messages.append({"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": call_id, "content": content}]})

    store.save_messages(chat_id, messages)
    store.patch_state(chat_id, run_id, status="running", waiting_on=None)
    return step(chat_id, run_id)


def save_to_library(chat_id, run_id, title=None):
    """Save the run's draft to the Library and say so in the run log. The one place this
    happens: the publish route and the draft approval both call it. Returns
    {"item_id", "title"} or None when there is no draft yet."""
    draft = store.load_artifact(chat_id, run_id, "draft.md")
    if not draft:
        return None
    bp = store.load_artifact(chat_id, run_id, "blueprint.json") or {}
    rs = store.load_artifact(chat_id, run_id, "research.json") or {}
    state = store.get_state(chat_id, run_id) or {}
    h1 = next((ln[2:].strip() for ln in draft.splitlines() if ln.startswith("# ")), "")
    # the draft's own H1 first: the heading pass rewrites it after the blueprint was approved
    title = (title or h1 or bp.get("h1") or bp.get("title") or state.get("topic") or "Untitled").strip()[:120]
    kw = rs.get("keywords") or {}
    primary = kw.get("primary") or rs.get("primary_keyword") or {}
    idea_id = (state.get("idea_id") or "").strip()
    # RENAME the row this run already opened, never make a second one. library_save routes through
    # library_finish with the run named, so a run whose row was never opened still gets exactly one.
    # The archetype goes ONTO the row, beside the keyword, rather than being read back out of the
    # run every time the Library is drawn. A run folder can be deleted and its article kept, and a
    # finished article should still be able to say what shape it was written to. (2026-09-09.)
    fmt = (bp.get("format_archetype") or rs.get("format_archetype")
           or (rs.get("build_spec") or {}).get("format") or "").strip()
    item = store.library_save(chat_id, run_id, title, draft, {
        "primary_keyword": primary.get("keyword", "") if isinstance(primary, dict) else str(primary),
        "format_archetype": fmt,
        "idea_id": idea_id})
    store.emit(chat_id, run_id, "saved_to_library", item_id=item, title=title)

    # Tick the idea this run came FROM, and only that. `idea_id` was written into the run's state
    # by the send that started it, before the model read anything, so this is provenance and not a
    # judgement: either the run began at an idea or it did not.
    #
    # Deliberately NOT matched by meaning. The owner ruled on that 2026-09-09: matching a
    # hand-written article against open ideas adds a whole class of wrong answers to save a rare
    # piece of bookkeeping, and a wrong tick silently drops an idea out of the queue where nobody
    # would ever find it. An article somebody typed himself ticks nothing.
    if idea_id:
        try:
            from .assets import _common as _acm
            if _acm.mark_built(idea_id, item, run_id):
                store.emit(chat_id, run_id, "idea_built", idea_id=idea_id, item_id=item)
        except Exception:   # noqa: BLE001 — a sheet we cannot tick must never lose the article
            pass
    return {"item_id": item, "title": title, "idea_id": idea_id}


def _save_if_draft_approved(chat_id, run_id, waiting, answer):
    """Approving the draft IS saving it. Found live (2026-09-04): the model announced
    "Saved. It's in the Library" after an approval that saved nothing, because the save
    was a button. Now the loop saves, and the model only learns of it from the result."""
    if not isinstance(answer, dict) or answer.get("approved") is not True:
        return None
    if (waiting or {}).get("view") != "article" and (waiting or {}).get("artifact") != "draft.md":
        return None
    try:
        return save_to_library(chat_id, run_id)
    except Exception as e:  # noqa: BLE001 — a failed save must never lose the approval
        store.emit(chat_id, run_id, "note", text="Could not save to the Library: %s" % str(e)[:160])
        return None


def _answer_summary(answer):
    """One human line for the log: what the user chose or typed."""
    for key in ("choice", "text", "changes", "note", "topic"):
        v = answer.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    if answer.get("approved") is True:
        return "Approved"
    if answer.get("approved") is False:
        return "Asked for changes"
    return "answered"


def stop(chat_id, run_id):
    store.emit(chat_id, run_id, "stopped", by="user")
    return store.patch_state(chat_id, run_id, status="stopped", waiting_on=None)
