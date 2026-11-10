"""Agent view (agent/1): who one agent talked to and how it decided, read from a run's own chat.jsonl and calls.jsonl.

view(run_dir, who) returns its summary, its conversations grouped by counterpart and one card per AI call (what it was given,
its stated reason, its reply). Read-only, code only; nothing new is captured. The page turns ids into names (personas, workflow
short names) and every response goes through the server's redact().
"""
import json
import os
import re

NL = chr(10)

TECH_MAX = 40_000      # prompt, system text and raw output are kept for "Show technical details", cut to this many characters
FUNCS = ("identity", "adaptation", "priority", "coordination", "audit", "validator")
MENTION = re.compile(r"^@(Requester|User|Identity|Adaptation|Priority|Coordination|Audit|Validator|W-\d+)\b", re.I)


def _jsonl(d, name):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except (OSError, ValueError):
        return []


def _read(d, name, default=None):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def messages(d):
    """The chat's messages (the meta line left out)."""
    return [m for m in _jsonl(d, "chat.jsonl") if not m.get("meta") and m.get("who")]


def recipients(m):
    """Who a message was for, from what the chat recorded: next, audience, to_user, and an @name it starts with."""
    out = []
    for k in (m.get("next"), m.get("audience")):
        if k:
            out.append(str(k))
    if m.get("to_user"):
        out.append("user")
    hit = MENTION.match(str(m.get("text") or ""))
    if hit:
        n = hit.group(1)
        out.append("user" if n.lower() in ("requester", "user") else n if n.upper().startswith("W-") else n.lower())
    return [x for x in dict.fromkeys(out) if x != m.get("who")]


def _short(v, n=600):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n - 1] + "…"


def _reply(c):
    """The reply as sentences and labelled lines: to_requester and say as text; other short fields as lines; long ones by size."""
    r, rest = c.get("reply"), ""
    if not isinstance(r, dict):      # a builder's reply: a JSON record, then the code it wrote
        raw = str(c.get("raw") or "")
        try:
            r, end = json.JSONDecoder().raw_decode(raw[raw.index("{"):]) if "{" in raw else (None, 0)
            rest = raw[raw.index("{") + end:].strip()
        except ValueError:
            r = None
    if not isinstance(r, dict):
        return {"text": [], "fields": [], "reason": None, "note": "the reply was not a record (see technical details)" if c.get("raw") else "no reply recorded"}
    text = [str(r[k]) for k in ("to_requester", "say", "human_output") if isinstance(r.get(k), str) and r[k].strip()]
    fields = []
    for k, v in r.items():
        if k in ("to_requester", "say", "human_output", "reason") or v in (None, "", [], {}):
            continue
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        fields.append([k, s if len(s) <= 400 else f"{len(s):,} characters (in the technical details)"])
    return {"text": text, "fields": fields, "reason": r.get("reason") if isinstance(r.get("reason"), str) else None, "note": f"and {len(rest):,} characters of code (in the technical details)" if rest else None}


def load(d):
    """The run's records the view reads, once: (chat messages, AI calls, workflow short names)."""
    return (messages(d), _jsonl(d, "calls.jsonl"),
            {w["id"]: w.get("name") or w["id"] for w in _read(d, "workflows.json", []) or [] if isinstance(w, dict) and w.get("id")})


def view(d, who, loaded=None):
    """agent/1 for one agent (a function id, or a workflow id W-n) in a run folder. loaded: load(d), to reuse."""
    who = str(who or "")
    if not d or not os.path.isdir(d) or not who:
        return {"schema": "agent/1", "who": who, "found": False}
    chat, every, names = loaded or load(d)
    calls = [c for c in every if str(c.get("fn")) == who]
    groups, order = {}, []
    for m in chat:
        to = recipients(m)
        if m["who"] == who:
            peers = to or [None]      # posted with no one named: its own group
        elif who in to:
            peers = [m["who"]]
        else:
            continue
        for p in peers:
            if p not in groups:
                groups[p] = []
                order.append(p)
            groups[p].append({"id": m.get("id"), "t": m.get("t"), "step": m.get("step"), "from": m["who"], "to": to,
                              "text": str(m.get("text") or ""), "sent": m["who"] == who})
    talks = [{"with": p, "count": len(groups[p]), "messages": groups[p]} for p in order]
    thinking = []
    for c in calls:
        rep = _reply(c)
        thinking.append({"id": c.get("id"), "step": c.get("step"), "cycle": c.get("cycle"), "t": c.get("t"), "seconds": c.get("seconds"),
                         "model": c.get("model"), "tokens": c.get("tokens"), "atom": c.get("atom"),
                         "given": [[str(x[0]), _short(x[1])] for x in (c.get("inputs") or []) if isinstance(x, (list, tuple)) and len(x) == 2],
                         "reason": c.get("reason") or rep["reason"], "reply": rep,
                         "technical": {k: (str(c.get(k) or "")[:TECH_MAX]) for k in ("system", "prompt", "raw")}})
    busiest = max(talks, key=lambda g: g["count"]) if talks else None
    models = sorted({c.get("model") for c in calls if c.get("model")})
    tok = {"input": sum(int((c.get("tokens") or {}).get("input") or 0) for c in calls),
           "output": sum(int((c.get("tokens") or {}).get("output") or 0) for c in calls)}
    return {"schema": "agent/1", "who": who, "found": bool(calls or talks), "names": names,
            "summary": {"calls": len(calls), "seconds": round(sum(float(c.get("seconds") or 0) for c in calls), 1), "models": models,
                        "tokens": tok, "messages": sum(1 for m in chat if m["who"] == who),
                        "most": {"with": busiest["with"], "count": busiest["count"]} if busiest else None},
            "conversations": talks, "thinking": thinking}


PERSONA = {"identity": "Client Lead", "adaptation": "Strategist", "priority": "Prioritiser", "coordination": "Scheduler", "audit": "Quality Reviewer"}
GATE = 0.80


def _t(m):
    return str((m or {}).get("t") or "")


def _plan_events(d, chat, who):
    """Adaptation's planning, judging and revising, from realization.json: one event per decision. They carry the time of the chat message
    that announced the plan (realization: true), else the first message Adaptation sent, else no time."""
    rz = _read(d, "realization.json")
    if who != "adaptation" or not isinstance(rz, dict) or not isinstance(rz.get("plan"), dict):
        return []
    p = rz["plan"]
    at = next((m for m in chat if m.get("who") == who and m.get("realization")), None) or next((m for m in chat if m.get("who") == who), None)
    t, out = _t(at), []
    ca = p.get("certainty_assessment") or {}
    if ca.get("zone"):
        out.append({"kind": "plan", "t": t, "title": f"Judged the goal's certainty: {ca['zone']}", "text": ca.get("rationale") or "",
                    "items": [f"{k}: {v.get('answer')} — {v.get('evidence')}" if isinstance(v, dict) else f"{k}: {v}" for k, v in (ca.get("signals") or {}).items()]})
    a = p.get("analysis") or {}
    if a.get("chosen") or a.get("options"):
        out.append({"kind": "plan", "t": t, "title": f"Weighed the options and chose {a.get('chosen') or '?'}", "text": a.get("why") or "", "items": list(a.get("options") or [])})
    st = p.get("stages") or []
    if st:
        out.append({"kind": "plan", "t": t, "title": f"Chose {len(st)} stage{'' if len(st) == 1 else 's'}: {', '.join(s.get('id') or '' for s in st)}",
                    "text": "", "items": [f"{s.get('id')}: {s.get('thinking') or ''}{(' — ' + s['goal']) if s.get('goal') else ''}" for s in st]})
    for w in p.get("workflows") or []:
        out.append({"kind": "wf", "t": t, "title": f"Created {w.get('name')} in {w.get('stage')} · {w.get('certainty') or 'no zone'}",
                    "text": w.get("approach") or w.get("goal") or "", "items": list(w.get("certainty_signals") or []), "workflow": w.get("name")})
    for r in rz.get("rounds") or []:
        sc = r.get("scores") or {}
        low = [(n, s) for n, s in sc.items() if isinstance(s, dict) and s.get("score") is not None and s["score"] < GATE]
        weak = [(n, s) for n, s in sc.items() if isinstance(s, dict) and s.get("weakest") and (n, s) not in low]
        n_ok = sum(1 for s in sc.values() if isinstance(s, dict) and s.get("score") is not None and s["score"] >= GATE)
        items = [f"{n}: {s['score']:.2f} · weakest {s.get('weakest')}" + (f" — {s['missing'][0]}" if s.get("missing") else "") for n, s in low + weak]
        out.append({"kind": "judge", "t": t, "title": f"Judge round {r.get('round')}: {n_ok} at or above {GATE:.2f}, {len(low)} below",
                    "text": ("; ".join(str(f) for f in r.get("plan_faults") or []) or ""), "items": items,
                    "scores": {n: s.get("score") for n, s in sc.items() if isinstance(s, dict)}})
        for c in r.get("changes") or []:
            out.append({"kind": "revise", "t": t, "title": f"Revised {c.get('workflow')}: {c.get('weakest') or 'the weakest check'}", "text": c.get("remedy") or "", "items": [], "workflow": c.get("workflow")})
    for e in rz.get("late") or []:      # a fix, a replacement or a relay revision judged after the plan, at its own time
        sc = e.get("score")
        out.append({"kind": "judge", "t": _t(e), "title": (f"Judged {e.get('workflow')}" + (f" (revises {e['revises']})" if e.get("revises") else "")
                    + (f": {sc:.2f}" + (" after one improvement" if len(e.get("rounds") or []) > 1 else "") + (", below the gate" if sc < GATE else "") if sc is not None else ": not scored")),
                    "text": (f"weakest {e.get('weakest')}: " + "; ".join(e.get("missing") or [])) if e.get("weakest") else (e.get("note") or ""),
                    "items": [f"zone {e.get('zone') or 'none'} · stage {e.get('stage') or 'none'}"] + ([f"rounds: {' → '.join(f'{x:.2f}' for x in e['rounds'])}"] if len(e.get("rounds") or []) > 1 else []),
                    "workflow": e.get("workflow")})
    if rz.get("plan_confidence") is not None:
        nr, held = list(rz.get("not_ready") or []), list(rz.get("held") or [])
        out.append({"kind": "plan", "t": t, "title": f"Plan confidence {rz['plan_confidence']:.2f} · {len(p.get('workflows') or [])} workflows" + (f" · {len(nr)} not ready" if nr else "") + (f" · {len(held)} held" if held else ""),
                    "text": f"{rz.get('calls') or 0} AI calls · {round(float(rz.get('seconds') or 0))} s", "items": [f"not ready: {x}" for x in nr] + [f"held: {x}" for x in held]})
    return out


def _change_events(d, chat, who):
    """The changes (change.json), as Adaptation handled them: the request, the charter's diff, where the change started, the revisions, the readers asked."""
    recs = _read(d, "change.json", []) or []
    recs = [c for c in (recs if isinstance(recs, list) else [recs]) if isinstance(c, dict)]
    if who != "adaptation":
        return []
    out = []
    for i, c in enumerate(recs, 1):
        cid = c.get("id") or f"C-{i}"
        at = chat[c["chat0"]] if isinstance(c.get("chat0"), int) and 0 <= c["chat0"] < len(chat) else None
        t = _t(at)
        diff = c.get("diff") or {}
        added = [f"item {x[0]}: {x[1]}" if isinstance(x, (list, tuple)) and len(x) == 2 else str(x) for x in diff.get("added") or []]
        rules = [f"rule: {x}" for x in ((diff.get("rules") or {}).get("added") or [])]
        out.append({"kind": "change", "t": t, "title": f"{cid}: {c.get('request') or 'a change'}", "text": f"phase {c.get('phase')}" if c.get("phase") else "", "items": added + rules, "change": cid})
        for wid, n in (c.get("nodes") or {}).items():
            n = n if isinstance(n, dict) else {}
            out.append({"kind": "change", "t": t, "title": f"{wid} {n.get('name') or ''}: {n.get('verdict') or 'looked at'}" + (f", revised as {', '.join(n['revisions'])}" if n.get("revisions") else ""),
                        "text": n.get("reason") or "", "items": list(n.get("changes") or []), "change": cid, "workflow": wid})
        for r in c.get("relay") or []:
            if isinstance(r, dict) and r.get("name"):
                out.append({"kind": "change", "t": t, "title": f"Asked {r['name']} to reread {r.get('doc') or 'the revised document'}: " + ("affected, revised" if r.get("affected") else "agreed" if r.get("agree") else f"objected, round {r.get('round')}" if r.get("round") else "no answer recorded"),
                            "text": r.get("what") or "", "items": [], "change": cid})
        for o in c.get("objections") or []:
            if isinstance(o, dict):
                out.append({"kind": "change", "t": t, "title": f"{o.get('name')} objected" + (f" (round {o.get('round')})" if o.get("round") else ""), "text": o.get("what") or o.get("reason") or "", "items": [], "change": cid})
        for r in c.get("rulings") or []:
            if isinstance(r, dict):
                out.append({"kind": "change", "t": t, "title": f"Identity ruled: keep {r.get('keep')}", "text": r.get("reason") or "", "items": [], "change": cid})
    return out


def activity(d, who, loaded=None):
    """activity/1: everything one function did in a run, in order, from the run's own records and nothing else. Messages it sent or was
    addressed in (chat.jsonl), its AI calls with their stated reasons (calls.jsonl) and, for Adaptation, its planning, judging and revising
    (realization.json) and the changes it handled (change.json). {"found": False} for a run with nothing recorded for it."""
    who = str(who or "")
    if not d or not os.path.isdir(d) or not who:
        return {"schema": "activity/1", "who": who, "found": False, "events": []}
    chat, every, names = loaded or load(d)
    ev = []
    for m in chat:
        to = recipients(m)
        if m["who"] == who or who in to:
            ev.append({"kind": "msg", "t": _t(m), "id": m.get("id"), "msg": m})
    for c in every:
        if str(c.get("fn")) != who:
            continue
        rep = _reply(c)
        ev.append({"kind": "call", "t": _t(c), "id": c.get("id"), "title": f"AI call {c.get('id')} · step {c.get('step')} · cycle {c.get('cycle') or 1} · {round(float(c.get('seconds') or 0), 1)} s",
                   "text": c.get("reason") or rep.get("reason") or "", "items": [f"{k}: {v}" for k, v in rep.get("fields") or []][:8],
                   "given": [str(x[0]) for x in (c.get("inputs") or []) if isinstance(x, (list, tuple)) and x]})
    ev += _plan_events(d, chat, who) + _change_events(d, chat, who)
    ev = [dict(e, n=i) for i, e in enumerate(ev)]      # by time; at one time a call before the message it produced, then the order the records hold
    ev.sort(key=lambda e: (e["t"] or "", 0 if e["kind"] == "call" else 1, e["n"]))
    for e in ev:
        del e["n"]
    return {"schema": "activity/1", "who": who, "persona": PERSONA.get(who, ""), "found": bool(ev), "names": names, "events": ev}


def _lines(act, kinds=False):
    """The feed as plain lines, for the question's context and for the records-only answer; kinds=True pairs each line with its event's kind."""
    out = []
    for e in act.get("events") or []:
        if e["kind"] == "msg":
            m = e["msg"]
            out.append((e["kind"], f"[{m.get('t') or ''}] {m.get('who')} said: {str(m.get('text') or '')}"))
        else:
            out.append((e["kind"], f"[{e.get('t') or ''}] {e.get('title') or ''}" + (f" — {e['text']}" if e.get("text") else "")))
            out += [(e["kind"], f"    - {x}") for x in e.get("items") or []]
    return out if kinds else [ln for _, ln in out]


TOPICS = (      # a question's words that name a kind of record: those records come first in a records-only answer
    ({"score", "scored", "scores", "judge", "judged", "lowest", "highest", "gate", "below", "weakest", "check", "checks", "round", "rounds"}, ("judge", "revise")),
    ({"zone", "zones", "certainty", "operate", "analyze", "experiment", "stabilize", "stage", "stages", "plan", "planned", "created"}, ("plan", "wf")),
    ({"change", "changed", "changes", "revised", "revision", "revisions", "reread", "relay", "charter", "v2"}, ("change", "revise")),
    ({"call", "calls", "model", "reason", "reasons", "thinking", "prompt"}, ("call",)))
STOP = {"what", "which", "when", "where", "why", "how", "did", "does", "the", "and", "for", "you", "your", "about", "this", "that", "with", "was", "were",
        "are", "is", "it", "its", "of", "to", "in", "on", "a", "an", "do", "workflow", "workflows"}


def answer(d, who, question, ask=None):
    """A question to one function about this run, answered from its records only. ask(system, user, mock) is llm.ask; without a model
    (mock mode, or none given) the answer is the lines of its records that share the question's words, so it is never invented."""
    act = activity(d, who)
    q = str(question or "").strip()
    name = PERSONA.get(who, who)
    if not q:
        return {"who": who, "answer": "", "from": "records"}
    if not act["found"]:
        return {"who": who, "answer": f"This run recorded nothing for {name}.", "from": "records"}
    pairs = _lines(act, kinds=True)
    lines = [ln for _, ln in pairs]
    qwords = set(re.findall(r"[a-z0-9][a-z0-9.-]{1,}", q.lower()))
    words = {w for w in qwords if w not in STOP}
    stems = {re.sub(r"(ing|ed|es|s)$", "", w) for w in words if len(w) > 3} | {w for w in words if len(w) <= 3}

    def records_only():      # the records the question is about first (judge rounds for a score question, and so on), then the lines that share its words
        kinds = [k for ws, ks in TOPICS if ws & qwords for k in ks]
        topic = [ln for k, ln in pairs if k in kinds]
        hits = [ln for ln in lines if ln not in topic and any(st in ln.lower() for st in stems)] if stems else []
        got = topic + hits
        if not got:
            return f"{name}'s records say nothing about that. They hold {len(lines)} lines: its messages, AI calls and planning." + (" Try a workflow's name or id, a check such as done_test, or a word like 'judge' or 'revised'." if words else "")
        return "From the records:" + "".join(NL + h.strip() for h in got[:12]) + (f"{NL}…and {len(got) - 12} more lines" if len(got) > 12 else "")
    if ask is None:
        return {"who": who, "answer": records_only(), "from": "records"}
    ctx = "\n".join(lines)
    if len(ctx) > 60_000:
        ctx = ctx[-60_000:]
    system = (f"You are {name} ({who}), one function of the J2 team that built this run. The Requester asks you a question about what you did. "
              "Answer only from the records below, which are your own messages, AI calls, planning, judging and revisions. Say plainly when the records do not hold the answer. "
              "Plain words, short sentences, no headings; name workflows by id and name; quote a score or a reason when it answers the question.")
    user = f"YOUR RECORDS\n{ctx}\n\nQUESTION\n{q}"
    try:
        text = ask(system, user, records_only, max_tokens=700, effort="low")
    except TypeError:
        text = ask(system, user, records_only)
    return {"who": who, "answer": str(text or "").strip() or records_only(), "from": "model"}
