"""Three agents and a user in one group chat, building a website together.

  Product      - moderator. Talks to the user, writes the brief, decides who speaks next.
  Design       - turns the brief into a design spec; later reviews the built site.
  Development  - builds the site as one HTML file; fixes what Design or the user flag.

How they communicate: ONE shared chat transcript. Every agent reads the whole
transcript (so nobody works blind) plus the current artifacts (brief, design,
site). Only Product decides who speaks next, so agents never talk over each other.
Code enforces the gates: no building before the user approves the plan, and a
hard cap on turns and revision rounds. Hand-offs with only one possible next step
(spec -> plan to user, build -> review, review -> fix or deliver) are routed in
code without an LLM call; Product's model is asked only after the user speaks or
something went wrong.
"""
import json
import os
import re
import threading
import time
import uuid

import llm
import mock_site

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_TURNS = 24          # safety cap on agent turns per run
MAX_REVIEW_ROUNDS = 2   # Design <-> Development fix loops before shipping anyway
MAX_QUESTIONS = 2       # teammate questions (Design <-> Development) allowed per user message

AGENTS = {
    "product": {"name": "Product", "role": "Product manager and moderator"},
    "design": {"name": "Design", "role": "UI/UX designer"},
    "development": {"name": "Development", "role": "Front-end developer"},
}

RULES_DIR = os.path.join(HERE, "agents")


def system_prompt(agent, reply_format):
    """team.md + <agent>.md + the reply format. Read on every call so rule edits apply without a restart."""
    parts = []
    for name in ("team.md", f"{agent}.md"):
        with open(os.path.join(RULES_DIR, name), encoding="utf-8") as f:
            parts.append(f.read().strip())
    parts.append(f"You are {AGENTS[agent]['name']}.\n\n## Reply format (required)\n{reply_format}")
    return "\n\n".join(parts)


def salvage_say(raw):
    """The "say" text from a reply whose JSON is broken or cut off, so the chat never shows raw JSON."""
    m = re.search(r'"say"\s*:\s*"((?:[^"\\]|\\.)*)', raw)
    if not m:
        return raw[:600] if "{" not in raw[:5] else "Sorry, my reply got cut off. Could you say that again?"
    try:
        return json.loads('"' + m.group(1) + '"')
    except ValueError:
        return m.group(1)


def current_section(text):
    """Name of the section Development is writing right now, from the streamed HTML."""
    body = text[text.lower().find("<body"):] if "<body" in text.lower() else ""
    marks = re.findall(r'<(?:section|header|footer|nav)\b[^>]*?(?:id|aria-label)="([^"]+)"|<h[12]\b[^>]*>([^<]{2,60})', body, re.I)
    if not marks:
        return "styles and setup" if text else ""
    a, b = marks[-1]
    return (a or b).strip().replace("-", " ")


class Stale(Exception):
    """Raised inside a run that belongs to a project the user has since replaced with New project."""


class Studio:
    def __init__(self):
        self.lock = threading.Lock()
        self.gen = 0                      # bumped by reset(); a run only touches the project it started in
        self._local = threading.local()   # the generation the current worker thread belongs to
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        # No lock here: a run holds the lock for its whole length. Bumping gen makes that run stop at its
        # next streamed chunk or post, without touching the new project.
        if True:
            self.gen += 1
            self.project = time.strftime("%Y%m%d-%H%M%S")
            self.messages = []
            self.brief = None
            self.design = None
            self.sites = []               # list of html strings (versions)
            self.reviewed_version = 0     # last site version Design reviewed
            self.review = None            # {"approved": bool, "issues": [...]}
            self.review_rounds = 0
            self.questions_asked = False
            self.plan_presented = False
            self.approved = False
            self.delivered = False
            self.pending_change = None    # user change request after delivery
            self.status = "idle"          # idle | thinking:<agent> | waiting | done
            self.turns = 0
            self.usage = {"calls": 0}
            self.activity = None          # the call in progress, for the UI's live status
            self.live = ""                # text streamed so far by the current call
            self.change_base = 0          # site versions that existed when the latest change request came in
            self.feasibility_checked = False  # Development checks the first spec once, before the user sees it
            self.questions_left = MAX_QUESTIONS
            self.pending_question = None  # {"from", "to", "text", "task"} while a teammate is answering

    def snapshot(self, since=0):
        return {
            "messages": self.messages[since:],
            "total": len(self.messages),
            "status": self.status,
            "brief": self.brief,
            "design": self.design,
            "versions": len(self.sites),
            "approved": self.approved,
            "mock": llm.MOCK,
            "model": None if llm.MOCK else llm.MODEL,
            "provider": None if llm.MOCK else llm.PROVIDER,
            "calls": self.usage["calls"],
            "activity": self._activity_view(),
            "steps": self.steps(),
        }

    STEPS = ["Questions", "Brief", "Design", "Approval", "Build", "Review", "Delivered"]

    def steps(self):
        """Which steps of the flow are done. A change request after delivery reopens Build and Review."""
        done = [self.questions_asked, bool(self.brief), bool(self.design), self.approved,
                len(self.sites) > self.change_base, self.reviewed_version > self.change_base,
                self.delivered and not self.pending_change]
        return [{"name": n, "done": bool(d)} for n, d in zip(self.STEPS, done)]

    def _activity_view(self):
        a = self.activity
        if not a:
            return None
        view = {k: a[k] for k in ("agent", "label", "chars", "note", "section", "expected")}
        view["elapsed"] = round(time.time() - a["started"])
        return view

    def post(self, who, text, kind="chat", **meta):
        self._check_current()
        msg = {"id": len(self.messages) + 1, "ts": time.strftime("%H:%M:%S"), "who": who,
               "text": text, "kind": kind, **meta}
        self.messages.append(msg)
        self._save_line(msg)
        return msg

    def _dir(self, *parts):
        path = os.path.join(HERE, "projects", self.project, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _save_line(self, msg):
        with open(self._dir("transcript.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def _save_json(self, name, data):
        with open(self._dir(name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _save_site(self, html):
        self.sites.append(html)
        v = len(self.sites)
        for name in (f"v{v}.html", "index.html"):
            with open(self._dir("site", name), "w", encoding="utf-8") as f:
                f.write(html)
        return v

    # ------------------------------------------------------------ transcript
    def transcript_text(self, limit=40):
        lines = []
        for m in self.messages[-limit:]:
            who = "User" if m["who"] == "user" else AGENTS.get(m["who"], {}).get("name", m["who"])
            lines.append(f"{who}: {m['text']}")
        return "\n".join(lines)

    def state_text(self):
        return json.dumps({
            "questions_asked": self.questions_asked, "brief_written": bool(self.brief),
            "design_ready": bool(self.design), "plan_presented": self.plan_presented,
            "user_approved_plan": self.approved, "site_versions": len(self.sites),
            "latest_version_reviewed_by_design": self.reviewed_version == len(self.sites) and bool(self.sites),
            "latest_review": self.review, "review_rounds": self.review_rounds,
            "delivered_to_user": self.delivered, "pending_user_change": self.pending_change,
        }, indent=1)

    # ------------------------------------------------------------- the loop
    def user_says(self, text):
        with self.lock:
            if self.status.startswith("thinking"):
                return False
            self.post("user", text)
            self.questions_left = MAX_QUESTIONS
            if self.delivered:
                self.pending_change = text
                self.change_base = len(self.sites)
            threading.Thread(target=self._run, daemon=True).start()
            return True

    def _check_current(self):
        if getattr(self._local, "gen", self.gen) != self.gen:
            raise Stale()

    def _run(self):
        gen = self.gen  # read before waiting on the lock, so a run queued behind a reset still counts
        with self.lock:
            self._local.gen = gen
            try:
                self._check_current()
                while self.turns < MAX_TURNS:
                    self.turns += 1
                    decision = self._auto_route() or self._product_turn()
                    if decision.get("run"):  # teammates talking directly, no Product hand-off
                        decision["run"]()
                        continue
                    nxt = decision["next"]
                    if nxt == "user":
                        self.status = "waiting"
                        return
                    if nxt == "done":
                        self.status = "done"
                        return
                    if nxt == "design":
                        self._design_turn(decision.get("task", ""))
                    elif nxt == "development":
                        self._dev_turn(decision.get("task", ""))
                self.post("system", f"Stopped after {MAX_TURNS} turns (safety cap).", kind="system")
                self.status = "waiting"
            except Stale:
                return  # the project was reset mid-run; leave the new one alone
            except Exception as e:  # noqa: BLE001
                if gen != self.gen:
                    return
                self.post("system", f"Error: {e}", kind="system")
                self.status = "waiting"

    def _call(self, who, system, user, mock, max_tokens=1500, label="", effort="low", expected=None,
              json_mode=True):
        """One LLM call. Streams progress into self.activity so the UI can show what the agent is doing."""
        self._check_current()
        self.status = f"thinking:{who}"
        self.usage["calls"] += 1
        self.live = ""
        a = {"agent": who, "label": label or "thinking", "started": time.time(), "chars": 0,
             "note": "", "section": "", "expected": expected}
        self.activity = a

        def progress(e):  # writes to its own dict, so a reset during the call can't break it
            self._check_current()  # stop streaming a reply for a project that no longer exists
            if "note" in e:
                a["note"] = e["note"]
            if "text" in e:
                self.live = e["text"]
                a["chars"] = e["chars"]
                a["note"] = ""
                if who == "development":
                    a["section"] = current_section(e["text"])
        try:
            raw = llm.ask(system, user, mock, max_tokens=max_tokens, effort=effort, on_progress=progress,
                          json_mode=json_mode)
        finally:
            if self.activity is a:
                self.activity = None
        self._check_current()
        return raw

    def _save_failed(self, who, raw, err):
        """Keep a reply we couldn't parse, so the cause can be read instead of guessed. Returns the file name."""
        name = f"failed-{who}-{time.strftime('%H%M%S')}.txt"
        with open(self._dir(name), "w", encoding="utf-8") as f:
            f.write(f"error: {err}\nlength: {len(raw)} chars\nmodel reply: {json.dumps(llm.LAST_META)}\n\n{raw}")
        return name

    # -------------------------------------------------------- code routing
    def _route(self, say, nxt, task=""):
        """Post a Product hand-off written by code, and return it as a Product decision."""
        self.post("product", say, next=nxt, task=task, auto=True)
        return {"say": say, "next": nxt, "task": task}

    def _auto_route(self):
        """Hand-offs with exactly one sensible next step. Returns a decision, or None to ask Product's model."""
        last = self.messages[-1] if self.messages else {}
        q = self.pending_question
        if q and last.get("question"):      # a teammate was asked something: they answer directly
            return {"next": q["to"], "run": lambda: self._answer_turn(q)}
        if q and last.get("answer"):        # answered: the asker picks its task back up
            self.pending_question = None
            resume = self._dev_turn if q["from"] == "development" else self._design_turn
            return {"next": q["from"], "run": lambda: resume(q["task"])}
        if last.get("who") == "design" and last.get("artifact") == "design" and not self.approved:
            if not self.feasibility_checked:
                self.feasibility_checked = True
                return {"next": "development", "run": self._check_turn}
            return self._present_plan()
        if last.get("who") == "development" and last.get("check"):
            c = last["check"]
            if c["ok"]:
                return self._present_plan()
            return {"next": "design", "run": lambda: self._design_turn(
                "Revise the spec to address @Development's concerns: " + "; ".join(c["concerns"]))}
        if last.get("who") == "development" and last.get("artifact") == "site":
            return self._route(f"@Design, version {len(self.sites)} is up. Please review it against your spec.",
                               "design", "Review the latest version.")
        if last.get("who") == "design" and last.get("review"):
            r = self.review
            if not r["approved"] and self.review_rounds < MAX_REVIEW_ROUNDS:
                return self._route("@Development, please fix the issues Design listed.",
                                   "development", "Fix: " + "; ".join(r["issues"]))
            self.delivered = True
            self.pending_change = None
            note = "" if r["approved"] else " Design still had notes, but we've hit the review limit."
            return self._route(f"Version {len(self.sites)} is ready and reviewed.{note} Have a look in the "
                               "preview. Anything you'd like changed? Reply **done** if you're happy.", "user")
        return None

    def _present_plan(self):
        d = self.design
        self.plan_presented = True
        sections = ", ".join(s.get("name", "") for s in d.get("sections", []))
        fonts = d.get("fonts") or {}
        return self._route("Here's the plan for your approval:\n"
                           f"- Sections: {sections}\n- Look: {d.get('style', '')}\n"
                           f"- Fonts: {fonts.get('heading', '')} and {fonts.get('body', '')}\n"
                           "Reply **approve** to start building, or tell me what to change.", "user")

    # --------------------------------------------------- teammates talking
    def _ask(self, who, to, text, task, say):
        """Post a question from one agent to another; the answer is routed back without Product."""
        self.questions_left -= 1
        self.pending_question = {"from": who, "to": to, "text": text, "task": task}
        self.post(who, say or f"@{AGENTS[to]['name']} {text}", question={"to": to})

    ANSWER_FORMATS = {
        "design": "A teammate asked you a question. Reply with JSON only: {\"say\": str (your answer, address "
                  "@Development), \"design\": object|null (the full updated spec, only if your answer changes it)}",
        "development": "A teammate asked you a question. Reply with JSON only: {\"say\": str (your answer, "
                       "address @Design)}",
    }

    def _answer_turn(self, q):
        to, frm = q["to"], q["from"]

        def mock():
            return json.dumps({"say": f"@{AGENTS[frm]['name']} Good question. Go with the simpler option; "
                                      "it fits the brief.", "design": None})
        raw = self._call(to, system_prompt(to, self.ANSWER_FORMATS[to]),
                         f"BRIEF:\n{json.dumps(self.brief)}\n\nDESIGN SPEC:\n{json.dumps(self.design)}\n\n"
                         f"QUESTION FROM {AGENTS[frm]['name'].upper()}: {q['text']}\n\n"
                         f"CHAT:\n{self.transcript_text(20)}", mock, max_tokens=800,
                         label=f"answering {AGENTS[frm]['name']}")
        try:
            r = llm.extract_json(raw)
        except Exception as e:  # noqa: BLE001
            self._save_failed(f"{to}-answer", raw, e)
            r = {"say": salvage_say(raw)}
        meta = {"answer": True}
        if to == "design" and isinstance(r.get("design"), dict) and r["design"].get("sections"):
            self.design = r["design"]
            self._save_json("design.json", self.design)
            meta["artifact_updated"] = "design"
        self.post(to, r.get("say", ""), **meta)

    DEV_CHECK_FORMAT = (
        "You are checking Design's spec before it goes to the User, so problems are caught before you build. "
        "Reply with JSON only: {\"say\": str (1-2 sentences to @Design), \"ok\": bool (false only if part of "
        "the spec can't be built within your rules or conflicts with the brief), \"concerns\": [str] "
        "(each one specific, with the fix you suggest)}"
    )

    def _check_turn(self):
        def mock():
            return json.dumps({"say": "@Design Spec looks buildable in one file. I'll use initials instead of "
                                      "photos for the doctors, as your notes say, and the form will show a "
                                      "confirmation since there's no backend.", "ok": True, "concerns": []})
        raw = self._call("development", system_prompt("development", self.DEV_CHECK_FORMAT),
                         f"BRIEF:\n{json.dumps(self.brief)}\n\nDESIGN SPEC:\n{json.dumps(self.design)}\n\n"
                         f"CHAT:\n{self.transcript_text(20)}", mock, max_tokens=800,
                         label="checking the spec is buildable")
        try:
            r = llm.extract_json(raw)
        except Exception as e:  # noqa: BLE001
            self._save_failed("development-check", raw, e)
            r = {"say": salvage_say(raw), "ok": True, "concerns": []}
        concerns = [str(c) for c in (r.get("concerns") or [])]
        check = {"ok": bool(r.get("ok", True)) or not concerns, "concerns": concerns}
        self.post("development", r.get("say", ""), check=check)

    # ------------------------------------------------------------- Product
    # Rules live in agents/product.md; the reply format stays here because the parser depends on it.
    PRODUCT_FORMAT = (
        "Reply with JSON only: {\"say\": str, \"next\": \"user\"|\"design\"|\"development\"|\"done\", "
        "\"task\": str (instruction for the next agent, empty if next is user/done), "
        "\"brief\": object|null (only when you write or update the brief: site_name, purpose, audience, "
        "pages:[{name, sections:[str]}], must_have:[str], tone), "
        "\"user_approved\": bool|null (set true only when the user's latest message approves the plan)}"
    )

    def _product_turn(self):
        def mock():
            return json.dumps(self._product_mock())
        raw = self._call("product", system_prompt("product", self.PRODUCT_FORMAT),
                         f"STATE:\n{self.state_text()}\n\nBRIEF:\n{json.dumps(self.brief)}\n\n"
                         f"CHAT SO FAR:\n{self.transcript_text()}\n\nYour move.", mock,
                         label="reading the chat and replying")
        try:
            d = llm.extract_json(raw)
        except Exception as e:  # noqa: BLE001
            self._save_failed("product", raw, e)
            d = {"say": salvage_say(raw), "next": "user", "task": ""}
        d.setdefault("task", "")
        if d.get("brief"):
            self.brief = d["brief"]
            self._save_json("brief.json", self.brief)
        if d.get("user_approved"):
            self.approved = True
        if not self.questions_asked and d["next"] == "user":
            self.questions_asked = True
        if self.design and not self.approved and d["next"] == "user":
            self.plan_presented = True
        # --- gates enforced in code, whatever the model says ---
        if d["next"] == "development" and not self.approved:
            d["next"], d["task"] = "user", ""
            d["say"] += " (Before we build: do you approve the plan above?)"
            self.plan_presented = True
        if d["next"] == "done" and not self.sites:
            d["next"] = "user"
        if d["next"] == "done":  # the user's last message was a sign-off, not a change request
            self.pending_change, self.change_base = None, 0
        if d["next"] == "user" and self.sites and self.reviewed_version == len(self.sites):
            if self.review and (self.review.get("approved") or self.review_rounds >= MAX_REVIEW_ROUNDS):
                self.delivered = True
                self.pending_change = None
        self.post("product", d["say"], next=d["next"], task=d["task"])
        return d

    def _product_mock(self):
        last_user = next((m["text"] for m in reversed(self.messages) if m["who"] == "user"), "")
        if not self.questions_asked:
            return {"say": "Hi! Happy to build this with the team. Three quick questions first:\n"
                           "1. What is the hospital's name and city?\n"
                           "2. Who is it mainly for: patients booking visits, emergency visitors, or both?\n"
                           "3. Any must-haves (online appointments, doctor profiles, emergency number)?",
                    "next": "user", "task": ""}
        if not self.brief:
            name = "CityCare Hospital"
            m = re.search(r"([A-Z][\w&]*(?:\s+[A-Z][\w&]*)*\s+Hospital)", last_user)
            if m:
                name = m.group(1)
            brief = {"site_name": name, "purpose": "A 250-bed multi-speciality hospital with 24/7 emergency care, "
                     "online appointments and experienced specialists.",
                     "audience": "Patients and families booking visits; people looking for emergency help",
                     "pages": [{"name": "Home (single page)", "sections": ["Header with Book button", "Hero",
                               "Departments", "Doctors", "Appointment form", "Contact and emergency", "Footer"]}],
                     "must_have": ["Online appointment request", "Doctor profiles", "Emergency number visible",
                                   "Mobile friendly"], "tone": "Calm, trustworthy, warm",
                     "notes_from_user": last_user}
            return {"say": f"Thanks! Brief written for **{name}**: one-page site with departments, doctors, "
                           "an appointment form and a clear emergency contact. @Design, can you propose a look "
                           "and section layout?", "next": "design", "brief": brief,
                    "task": "Create a design spec for the brief: palette, fonts, section layout."}
        if self.design and not self.plan_presented:
            d = self.design
            return {"say": "Here's the plan for your approval:\n"
                           f"- Sections: {', '.join(s['name'] for s in d['sections'])}\n"
                           f"- Look: {d['style']}\n- Fonts: {d['fonts']['heading']} and {d['fonts']['body']}\n"
                           "Reply **approve** to start building, or tell me what to change.",
                    "next": "user", "task": ""}
        if self.plan_presented and not self.approved:
            if re.search(r"\b(change|instead|different|no\b|don't|not )", last_user, re.I):
                self.plan_presented = False
                return {"say": "Got it. @Design, please update the spec with the user's feedback.",
                        "next": "design", "task": f"Revise the spec: {last_user}"}
            return {"say": "Plan approved. @Development, please build version 1 from the brief and design spec.",
                    "next": "development", "user_approved": True,
                    "task": "Build the full site as one HTML file."}
        if self.sites and self.reviewed_version < len(self.sites):
            return {"say": f"@Design, version {len(self.sites)} is up. Please review it against your spec.",
                    "next": "design", "task": "Review the latest version."}
        if self.review and not self.review.get("approved") and self.review_rounds < MAX_REVIEW_ROUNDS \
                and not self.delivered:
            return {"say": "@Development, please fix the issues Design listed.",
                    "next": "development", "task": "Fix: " + "; ".join(self.review["issues"])}
        if not self.delivered:
            return {"say": f"Version {len(self.sites)} is ready and reviewed. Have a look in the preview. "
                           "Anything you'd like changed? Reply **done** if you're happy.",
                    "next": "user", "task": ""}
        if re.search(r"\b(done|thanks|thank you|looks good|perfect|great)\b", last_user, re.I):
            return {"say": "Great, the site is final. Files are saved in the project folder.",
                    "next": "done", "task": ""}
        self.delivered = False
        return {"say": "On it. @Development, please apply the user's change.",
                "next": "development", "task": f"User change request: {last_user}"}

    # -------------------------------------------------------------- Design
    DESIGN_SPEC_FORMAT = (
        "You are writing the design spec now. "
        "Reply with JSON only: {\"say\": str (short chat message, address @Product), "
        "\"design\": {\"palette\": {\"primary\", \"secondary\", \"accent\", \"background\", \"text\"} (hex), "
        "\"fonts\": {\"heading\", \"body\"}, \"style\": str, \"sections\": [{\"name\", \"notes\"}]}}"
    )
    DESIGN_REVIEW_FORMAT = (
        "You are reviewing the built website now. "
        "Reply with JSON only: {\"say\": str (address @Product), \"approved\": bool, \"issues\": [str]}"
    )

    def _design_turn(self, task):
        if self.sites and self.reviewed_version < len(self.sites):
            v = len(self.sites)
            site = self.sites[-1]

            def mock():
                if v == 1:
                    return json.dumps({"say": "@Product Layout, colours and fonts match the spec. One issue: the "
                                              "emergency number is only in the contact section at the bottom. "
                                              "It should be visible on every screen.", "approved": False,
                                       "issues": ["Emergency number must be visible at the top of every screen "
                                                  "(sticky bar)"]})
                return json.dumps({"say": f"@Product Version {v} looks good. Emergency bar is visible and "
                                          "everything matches the spec. Approved.", "approved": True, "issues": []})
            raw = self._call("design", system_prompt("design", self.DESIGN_REVIEW_FORMAT),
                             f"BRIEF:\n{json.dumps(self.brief)}\n\nYOUR SPEC:\n{json.dumps(self.design)}\n\n"
                             f"TASK: {task}\n\nSITE v{v} HTML:\n{site[:40000]}\n\nCHAT:\n{self.transcript_text(20)}",
                             mock, max_tokens=800, label=f"reviewing v{v}")
            try:
                r = llm.extract_json(raw)
            except Exception as e:  # noqa: BLE001
                self._save_failed("design-review", raw, e)
                r = {"say": raw[:500], "approved": True, "issues": []}
            self.review = {"approved": bool(r.get("approved")), "issues": r.get("issues") or [], "version": v}
            self.reviewed_version = v
            if not self.review["approved"]:
                self.review_rounds += 1
            self.post("design", r.get("say", ""), review=self.review)
            return

        def mock():
            return json.dumps({"say": "@Product Here's the spec: calm teal and navy for trust, a warm coral "
                                      "accent reserved for emergency and alerts. Serif headings for warmth, "
                                      "a clean sans-serif for body text. One page, seven sections.",
                               "design": {"palette": {"primary": "#0f766e", "secondary": "#1e3a8a",
                                                      "accent": "#e2553f", "background": "#f6faf9",
                                                      "text": "#10231f"},
                                          "fonts": {"heading": "Merriweather", "body": "Source Sans 3"},
                                          "style": "Calm and trustworthy: teal/navy gradient hero, white cards, "
                                                   "coral only for emergency",
                                          "sections": [{"name": "Header", "notes": "Logo, nav, Book button"},
                                                       {"name": "Hero", "notes": "Headline, 2 buttons, 4 stats"},
                                                       {"name": "Departments", "notes": "6 cards in a 3-col grid"},
                                                       {"name": "Doctors", "notes": "4 profiles with initials"},
                                                       {"name": "Appointment", "notes": "Name, phone, dept, date"},
                                                       {"name": "Contact", "notes": "Address, OPD hours, emergency"},
                                                       {"name": "Footer", "notes": "Copyright"}]}})
        fmt = self.DESIGN_SPEC_FORMAT
        if self.questions_left > 0:
            fmt += (" If you truly can't write the spec without an answer from Development, instead reply "
                    "{\"say\": str, \"design\": null, \"question\": str (for @Development)}.")
        raw = self._call("design", system_prompt("design", fmt),
                         f"BRIEF:\n{json.dumps(self.brief)}\n\nCURRENT SPEC (if revising):\n"
                         f"{json.dumps(self.design)}\n\nTASK: {task}\n\nCHAT:\n{self.transcript_text(20)}", mock,
                         label="revising the design spec" if self.design else "writing the design spec")
        try:
            r = llm.extract_json(raw)
            if r.get("question") and not r.get("design") and self.questions_left > 0:
                return self._ask("design", "development", r["question"], task, r.get("say"))
            if not isinstance(r.get("design"), dict):
                raise ValueError("no design object in reply")
            self.design = r["design"]
        except Exception as e:  # noqa: BLE001
            name = self._save_failed("design", raw, e)
            self.post("system", f"Design reply was not valid JSON ({e}). Raw reply saved to {name}.", kind="system")
            return
        self._save_json("design.json", self.design)
        self.post("design", r.get("say", ""), artifact="design")

    # --------------------------------------------------------- Development
    DEV_FORMAT = (
        "Reply with one short chat line addressed to @Product (if you disagree with a review issue, say which "
        "and why, and skip that fix), then the full file in a ```html code block."
    )

    def _dev_turn(self, task):
        v = len(self.sites) + 1
        fixes = set()
        if self.review and self.review.get("issues"):
            if any("emergency" in i.lower() for i in self.review["issues"]):
                fixes.add("sticky-emergency")
        if self.sites and 'class="ebar"' in self.sites[-1]:
            fixes.add("sticky-emergency")   # keep earlier fixes in later versions
        if "testimonial" in task.lower() or (self.sites and 'id="stories"' in self.sites[-1]):
            fixes.add("testimonials")

        def mock():
            html = mock_site.build(self.brief, self.design, v, fixes)
            note = ("@Product Version 1 is built: all seven sections, appointment form works."
                    if v == 1 else f"@Product Version {v} is up: {task[:120]}")
            return f"{note}\n```html\n{html}\n```"
        prev = self.sites[-1] if self.sites else ""
        fmt = self.DEV_FORMAT
        if self.questions_left > 0:
            fmt += (" If something in the spec or task blocks you and you can't make a sensible call yourself, "
                    "instead reply with one line only: QUESTION @Design: <your question>")
        raw = self._call("development", system_prompt("development", fmt),
                         f"BRIEF:\n{json.dumps(self.brief)}\n\nDESIGN SPEC:\n{json.dumps(self.design)}\n\n"
                         f"TASK: {task}\n\nLATEST REVIEW: {json.dumps(self.review)}\n\n"
                         f"PREVIOUS VERSION (edit this if it exists):\n{prev[:40000]}\n\n"
                         f"CHAT:\n{self.transcript_text(20)}", mock, max_tokens=16000, effort="high", json_mode=False,
                         label=f"building v{v}" if not prev else f"editing v{v - 1} into v{v}",
                         expected=len(prev) or None)
        m = re.match(r"\s*QUESTION\s+@Design\s*:?\s*(.+)", raw, re.S | re.I)
        if m and "```html" not in raw.lower() and self.questions_left > 0:
            text = m.group(1).strip()
            return self._ask("development", "design", text, task, f"@Design {text}")
        try:
            html = llm.extract_html(raw)
        except Exception as e:  # noqa: BLE001
            name = self._save_failed("development", raw, e)
            self.post("system", f"Development reply had no HTML ({e}). Raw reply saved to {name}.", kind="system")
            return
        note = raw.split("```")[0].strip() or f"@Product Version {v} is up."
        v = self._save_site(html)
        self.post("development", note, artifact="site", version=v, size=len(html))
