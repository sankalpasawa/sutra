"""The studio's view of a run (schema studio/1): what the Simple view draws, built by code from the run's own state, so the page only
draws it and every number on it has one source.

build(snap, docs) is code only, no model call, for a live run (J2Run.snapshot) or a saved one (saved_snapshot). It gives:
- parts: one per section of the output (a fix rewrites its section, so it is the same part, marked fixing), in plan order, each with
  the document it belongs to (documents.json: each finished document's workflows; else the stage under way), its kind of work and the
  person who makes it, and its state (done, doing, fix, next, bad, ask).
- stream: the team at work, one plain line per function message, written here from what each message is (the speaker, its act and
  the workflow ids it names), never the agents' own words, so no internal term reaches the page.
- qsec: the part the open question is about (its workflow, else the part covering what is still not right), or None (the top).
record(snap, docs, sec) is one part's goal, method, output and check; deliverable_record() is the same for a whole deliverable
(artifacts/types.json, so any output type the run lists). Both are served by /api/record.

The people are fixed: Asha (Client Lead: Identity), the Makers Mira (Writer), Kabir (Designer) and Dev (Developer), and Nora (Quality
check: Audit). Behind the scenes the functions keep their role names: Planner, Budget lead, Scheduler, Gatekeeper.
"""
import re

SCHEMA = "studio/1"
PEOPLE = {"asha": "Client Lead", "mira": "Writer", "kabir": "Designer", "dev": "Developer", "nora": "Quality check"}
KIND_PERSON = {"writer": "mira", "designer": "kabir", "developer": "dev"}
DOC_KIND = {"prd": "writer", "hld": "designer", "lld": "developer"}      # the PRD is written, the HLD designed, the LLD detailed for building
ROLES = {"adaptation": "Planner", "priority": "Budget lead", "coordination": "Scheduler", "validator": "Gatekeeper"}
# A part's kind from its name: something that works (a form, a button, a script) is a developer's, the look a designer's, the rest words.
DEVELOPER = re.compile(r"form|calculat|filter|search|countdown|timer|toggle|sticky|\bnav|navigation|button|order|booking|\bbook\b|cart|"
                       r"checkout|\bmap\b|script|interactive|slider|carousel|accordion|send|email|subscribe|shell|responsive|loyalty card|"
                       r"tabs?\b|code|api|data|integration|automation", re.I)
DESIGNER = re.compile(r"style|styling|layout|\blook|design|hero|gallery|photo|image|visual|theme|colou?r|contrast|banner|logo|portfolio|"
                      r"lookbook|diagram", re.I)
DONE_NOT = ("done", "failed", "refused", "unfunded")
STREAM_MAX = 40       # the newest lines the state carries; the page shows fewer


def part_name(name):
    """A workflow's name as a part's name: "PRD Problem section revision 2" reads "Problem", "Build_menu" reads "Menu"."""
    t = re.sub(r"_", " ", str(name or ""))
    t = re.sub(r"\bbuilders?\b", "maker", t, flags=re.I)
    t = re.sub(r"^(?:PRD|HLD|LLD)\s+", "", t)
    t = re.sub(r"\s+section(?:\s+revision(?:\s+\d+)?)?$|\s+revision(?:\s+\d+)?$", "", t, flags=re.I)
    t = re.sub(r"^(?:Build|Write|Make)\s+(?=\S)", "", t, flags=re.I).strip()
    return (t[:1].upper() + t[1:]) if t else "A part"


def doc_map(docs):
    """workflow id -> the document it wrote, from the run's documents record ({kind: {"workflows": [...]}})."""
    return {w: k for k, v in (docs or {}).items() for w in (v or {}).get("workflows") or []}


def _base(wfs, w):
    """The workflow that first built w's section (a fix names it in "section")."""
    return next((x for x in wfs if x.get("id") == w.get("section") and not x.get("revises")), None) \
        or next((x for x in wfs if x.get("section") == w.get("section") and not x.get("revises")), None) or w


def doc_of(snap, dm, w):
    """The output a workflow belongs to: a finished document (documents record), else the name's PRD/HLD/LLD, else the stage under
    way (a document stage, else the site)."""
    b = _base(snap.get("workflows") or [], w)
    k = dm.get(b.get("id")) or dm.get(w.get("id"))
    if not k:
        m = re.match(r"(PRD|HLD|LLD)\b", str(b.get("name") or ""))
        k = m[1].lower() if m else None
    return k or (snap.get("output") if snap.get("doc") else "site")


def kind_of(name, doc):
    """writer, designer or developer: a document by its type, else the part's name."""
    if doc in DOC_KIND:
        return DOC_KIND[doc]
    return "developer" if DEVELOPER.search(str(name or "")) else "designer" if DESIGNER.search(str(name or "")) else "writer"


def _open_question(snap):
    p = snap.get("paused")
    return p if p and snap.get("status") != "running" and not snap.get("saved") else None


def _q_section(snap, wfs):
    """The part the open question is about: its workflow (an approval names one), else the latest workflow covering an item the last
    check found not met (a limit, a fact, an audit question), else None."""
    p = _open_question(snap)
    if not p:
        return None
    if p.get("workflow"):
        w = next((x for x in wfs if x.get("id") == p["workflow"]), None)
        return (w or {}).get("section") or p["workflow"]
    if p.get("kind") in ("limit", "fact", "audit"):
        au = (snap.get("audits") or [None])[-1]
        bad = {str(r.get("item") or str(r.get("id") or "").replace("F-", "")) for r in (au or {}).get("results") or []
               if not str(r.get("verdict") or "").startswith("PASS")}
        w = next((x for x in reversed(wfs) if any(str(c) in bad for c in x.get("covers") or [])), None)
        return (w.get("section") or w.get("id")) if w else None
    return None


def parts(snap, docs=None):
    """One part per section, in plan order: {sec, id, name, doc, kind, person, st, fixing, fixes, workflows}."""
    wfs = [w for w in snap.get("workflows") or [] if w.get("section") != "style"]
    dm, by, qsec = doc_map(docs), {}, _q_section(snap, wfs)
    for w in wfs:
        by.setdefault(w.get("section") or w.get("id"), []).append(w)
    out = []
    for sec, ws in by.items():
        base = next((w for w in ws if not w.get("revises")), ws[0])
        last = ws[-1]
        run = next((w for w in ws if w.get("status") == "running" or snap.get("thinking") == w.get("id")), None)
        done = any(w.get("status") == "done" for w in ws)
        pend = [w for w in ws if w.get("status") not in DONE_NOT]
        st = ("doing" if run else "done" if last.get("status") == "done" else "bad" if last.get("status") in ("failed", "refused") and not done
              else "fix" if done and pend else "next")
        doc = doc_of(snap, dm, base)
        kind = kind_of(base.get("name"), doc)
        out.append({"sec": sec, "id": base.get("id"), "name": part_name(base.get("name")), "doc": doc, "kind": kind,
                    "person": KIND_PERSON[kind], "st": "ask" if sec == qsec else st, "fixing": bool(run and run.get("revises")),
                    "fixes": sum(1 for w in ws if w.get("revises")), "workflows": [w.get("id") for w in ws]})
    return out


def stream(snap, ps=None):
    """The team at work: {id, t, who (a person) or role, text} per function message, newest last."""
    wfs = snap.get("workflows") or []
    ps = ps if ps is not None else parts(snap)
    person = {w: p["person"] for p in ps for w in p["workflows"]}
    name = {w: p["name"].lower() for p in ps for w in p["workflows"]}
    W = lambda i: name.get(i, "a part")
    out, audits = [], 0
    for m in snap.get("allChat") or snap.get("chat") or []:
        who, t = m.get("who"), str(m.get("text") or "")
        ids = re.findall(r"\bW-\d+\b", t)
        line = None
        if who == "identity" and not m.get("to_user") and not m.get("test"):
            line = {"who": "asha", "text": "wrote down what you asked for and handed it to the team." if m.get("artifact") == "charter"
                    or re.search(r"charter (?:is )?(?:recorded|ready)", t, re.I) else "passed on what you chose to leave out." if re.search(r"\bdrop|leave out", t, re.I)
                    else "passed the next step to the team."}
        elif who == "adaptation":
            line = {"role": ROLES[who], "text": "reworked the plan." if re.search(r"resubmit|revis|rework", t, re.I) else "planned a fix." if re.search(r"\bfix", t, re.I)
                    else "noted a lesson for next time." if re.search(r"lesson", t, re.I) else "proposed the parts to make."}
        elif who == "priority":
            line = {"role": ROLES[who], "text": f"gave the go-ahead for {W(ids[0])}." if ids and re.search(r"envelope check|runs now", t, re.I)
                    else "agreed the plan." if re.search(r"\bGRANT\b", t) else "asked for a smaller plan." if re.search(r"\bCOUNTER\b", t)
                    else "turned down part of the plan." if re.search(r"\bREFUSE\b", t) else "checked the effort."}
        elif who == "coordination":
            line = {"role": ROLES[who], "text": f"lined up {W(ids[-1] if len(ids) > 1 and re.search(r'done', t, re.I) else ids[0])} next." if ids else "scheduled the work."}
        elif who == "validator":
            line = {"role": ROLES[who], "text": f"opened {len(ids) or 'the'} part{'' if len(ids) == 1 else 's'} for the team." if "Registered" in t
                    else "sent the plan back: some details were missing." if re.search(r"Rejected", t, re.I)
                    else "checked the plan: ready to start." if re.search(r"valid", t, re.I) else "checked the work order."}
        elif who == "audit":
            a = (snap.get("audits") or [None] * (audits + 1))[audits] if audits < len(snap.get("audits") or []) else None
            audits += 1
            n = len((a or {}).get("results") or [])
            ok = sum(1 for r in (a or {}).get("results") or [] if str(r.get("verdict") or "").startswith("PASS"))
            line = {"who": "nora", "text": (f"checked everything on your list: all {n} good." if ok == n else
                                            f"checked your list: {ok} of {n} good, the rest goes back to the team.") if a else "checked the result."}
        elif re.fullmatch(r"W-\d+", str(who or "")):
            w = next((x for x in wfs if x.get("id") == who), None)
            if w:
                line = {"who": person.get(who, "mira"), "text": f"{'fixed' if w.get('revises') else 'finished'} {W(who)}."}
        if line:
            out.append({"id": m.get("id"), "t": str(m.get("t") or "")[:5], **line})
    return out[-STREAM_MAX:]


def build(snap, docs=None):
    """The studio's model of a run (studio/1): parts, the stream, the part the open question is about."""
    ps = parts(snap, docs)
    return {"schema": SCHEMA, "parts": ps, "stream": stream(snap, ps), "qsec": next((p["sec"] for p in ps if p["st"] == "ask"), None),
            "done": sum(1 for p in ps if p["st"] == "done"), "total": len(ps)}


def _clip(t, n):
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def record(snap, docs, sec):
    """One part's record: goal (its atom's goal, else its purpose), method (how it was made), output (what it promised, each met or
    not), check (the last check's results on the items it covers), and its history (the fixes). None for an unknown part."""
    ps = parts(snap, docs)
    p = next((x for x in ps if x["sec"] == sec), None)
    if not p:
        return None
    wfs = [w for w in snap.get("workflows") or [] if w.get("id") in p["workflows"]]
    w = next((x for x in reversed(wfs) if x.get("status") == "done"), wfs[-1])
    a = (w.get("atoms") or [{}])[0]
    how = a.get("how") or {}
    covers = {str(c) for x in wfs for c in x.get("covers") or []}
    au = (snap.get("audits") or [None])[-1]
    checks = [{"text": _clip(r.get("criterion"), 160), "met": str(r.get("verdict") or "").startswith("PASS")}
              for r in (au or {}).get("results") or [] if str(r.get("item") or str(r.get("id") or "").replace("F-", "")) in covers]
    return {"schema": SCHEMA, "sec": sec, "name": p["name"], "person": p["person"], "kind": p["kind"], "doc": p["doc"], "st": p["st"],
            "goal": _clip(a.get("goal") or w.get("purpose") or w.get("covers_text") or "", 300) or None,
            "method": _clip(how.get("steps") if isinstance(how.get("steps"), str) else " ".join(how.get("steps") or []) or how.get("kind") or "", 300) or None,
            "output": [{"text": _clip(o.get("text"), 140), "met": o.get("met")} for o in (a.get("expected_output") or [])[:8]],
            "check": checks[:8], "checked": bool(au),
            "history": [{"name": part_name(x.get("name")) if not x.get("revises") else _clip(x.get("name"), 80), "fix": bool(x.get("revises")),
                         "status": x.get("status")} for x in wfs]}


def deliverable_record(snap, docs, row):
    """A whole deliverable's record (an artifacts listing row, any type): goal (the charter's statement), method (its parts and who made
    them), output (the file, and how the page opens it), check (its parts' state and the last check)."""
    ps = parts(snap, docs)
    kind = "site" if row.get("form") == "page" else row.get("type") or row.get("name")
    mine = [p for p in ps if p["doc"] == kind]
    au = (snap.get("audits") or [None])[-1]
    res = (au or {}).get("results") or []
    return {"schema": SCHEMA, "name": row.get("name"), "label": row.get("label") or row.get("name"), "form": row.get("form"),
            "goal": _clip((snap.get("goal") or {}).get("statement") or "", 300) or None,
            "method": [{"sec": p["sec"], "name": p["name"], "person": p["person"], "st": p["st"]} for p in mine],
            "output": {"file": row.get("file"), "version": row.get("version"), "open": row.get("open")},
            "check": {"parts_done": sum(1 for p in mine if p["st"] == "done"), "parts": len(mine), "fixed": sum(1 for p in mine if p["fixes"]),
                      "items_met": sum(1 for r in res if str(r.get("verdict") or "").startswith("PASS")), "items": len(res)}}
