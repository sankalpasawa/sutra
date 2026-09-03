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


def _knowledge_block(site):
    """What is already on file, so the model never redoes setup that is done. Found live
    (2026-09-04): a fresh chat re-ran the whole setup because nothing told the model the site
    was catalogued, embedded and the brand pack built."""
    lines = []
    pages = site.get("pages") if isinstance(site, dict) else None
    if pages:
        lines.append("- Site catalogue: %s, %d pages, read %s." % (site.get("domain") or "the site", len(pages),
                                                                   site.get("indexed_at") or "earlier"))
    else:
        lines.append("- Site catalogue: NOT built. Ask for the website if you do not have it, then run index_site.")
    try:
        from .tools import _index
        st = _index.status()
        lines.append("- Page index (meaning): built, %d pages, %d passages." % (st["pages"], st["chunks"])
                     if st.get("built") else "- Page index (meaning): not built. Run build_page_index (needs a Voyage key).")
    except Exception:  # noqa: BLE001
        pass
    brief = store.knowledge("brand/writer-brief.md")
    lines.append("- Brand pack: built (writer brief on file)." if isinstance(brief, str) and brief.strip()
                 else "- Brand pack: not built. Run learn_brand after the site is read.")
    done = pages and isinstance(brief, str) and brief.strip()
    tail = ("\nSetup is complete. Do NOT run index_site, build_page_index or learn_brand again unless the user "
            "asks for a rebuild. Go straight to the article." if done else
            "\nFinish setup first, in the order above, then the article.")
    return "## What is already in Knowledge\n\n" + "\n".join(lines) + tail


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


def _wait(chat_id, run_id, kind, call_id, payload, stage=None):
    fields = {"status": "waiting",
              "waiting_on": dict(payload, kind=kind, call_id=call_id)}
    if stage:
        fields["stage"] = stage
    store.patch_state(chat_id, run_id, **fields)
    # call_id rides on the event too, so the screen can pair a later "resumed" with the
    # exact question it answered instead of guessing by order.
    store.emit(chat_id, run_id, "waiting", kind=kind, call_id=call_id, **payload)


STAGE_FOR = {"index_site": "setup", "build_page_index": "setup", "learn_brand": "setup",
             "suggest_topics": "topic", "run_research": "research",
             "build_blueprint": "blueprint", "write_article": "draft"}
VIEW_STAGE = {"brand_pack": "setup", "topic_list": "topic", "research_brief": "research",
              "blueprint": "blueprint", "article": "draft"}


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

        # plain answer, no tools — the run is over
        if not reply["tool_calls"]:
            if reply["text"]:
                messages.append({"role": "assistant", "content": reply["text"]})
                store.emit(chat_id, run_id, "message", text=reply["text"])
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
                _wait(chat_id, run_id, "question", call_id, {
                    "question": args.get("question", ""),
                    "why": args.get("why", ""),
                    "options": args.get("options", [])})
                return store.get_state(chat_id, run_id)

            if name == "show_artifact":
                store.save_messages(chat_id, messages)
                view = args.get("view", "article")
                _wait(chat_id, run_id, "artifact", call_id, {
                    "artifact": args.get("path", ""),
                    "view": view,
                    "prompt": args.get("prompt", "Have a look before I carry on.")},
                    stage=VIEW_STAGE.get(view))
                return store.get_state(chat_id, run_id)

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
                       label=registry.label(name), tool=name)
            if STAGE_FOR.get(name):
                store.patch_state(chat_id, run_id, stage=STAGE_FOR[name], current_step=name)
            t0 = time.time()
            try:
                out = _run_tool(chat_id, run_id, name, args, step_id=step_id)
                ms = int((time.time() - t0) * 1000)
                store.emit(chat_id, run_id, "step_finished", id=step_id,
                           label=registry.label(name), ms=ms,
                           summary=(out or {}).get("summary", ""))
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
                       label=registry.label(tool), tool=tool)
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
    item = store.library_save(chat_id, run_id, title, draft, {
        "primary_keyword": primary.get("keyword", "") if isinstance(primary, dict) else str(primary)})
    store.emit(chat_id, run_id, "saved_to_library", item_id=item, title=title)
    return {"item_id": item, "title": title}


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
