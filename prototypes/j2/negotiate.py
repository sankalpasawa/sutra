"""Conflict demo: department agents negotiate a budget split, and escalate to a CEO agent if stuck.

Run:  python negotiate.py                      (uses scenarios/budget.json)
      python negotiate.py scenarios/other.json
      STUDIO_MOCK=1 python negotiate.py          (offline, simple rule-based agents)

Nothing about the conversation is scripted. Each turn, the speaking agent reads the whole chat and
decides what to say, whether to propose, accept, reject or escalate, and who speaks next.
Code only enforces the limits: proposals must add up, escalation unlocks after a few turns,
and a time box sends the group to the CEO if they talk too long.
"""
import json
import os
import random
import re
import sys
import time

import llm

HERE = os.path.dirname(os.path.abspath(__file__))
STANCES = ("propose", "accept", "reject", "escalate")
COLORS = {"Marketing": "\033[35m", "Engineering": "\033[36m", "Sales": "\033[33m", "CEO": "\033[32m",
          "system": "\033[90m"}
RESET = "\033[0m"
# Pause between live model calls so the Gemini free tier's per-minute limit isn't hit. Mock mode never waits.
DELAY = 0 if llm.MOCK else float(os.getenv("NEGOTIATE_DELAY", "4"))


def load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Negotiation:
    def __init__(self, scenario):
        self.s = scenario
        self.names = [a["name"] for a in scenario["agents"]]
        self.budget = scenario["budget"]
        self.limits = scenario.get("limits", {})
        self.rules = load(os.path.join(HERE, "scenarios", "rules.md"))
        self.chat = []           # every message, public to all agents
        self.table = None        # latest valid proposal: {"split": {...}, "by": name}
        self.accepted = set()    # agents who accept the split on the table
        self.reserve = None      # CEO's held-back money: {"amount": int, "release": str}
        self.phase = "negotiating"  # negotiating -> ceo -> commit -> done (read by the web page)
        self.thinking = None     # who the model is currently writing for
        self.result = None       # final summary, set when the run ends
        self.error = None
        self.calls = 0
        run = time.strftime("%Y%m%d-%H%M%S")
        self.dir = os.path.join(HERE, "runs", run)
        n = 1
        while os.path.exists(self.dir):  # two runs in the same second
            n += 1
            self.dir = os.path.join(HERE, "runs", f"{run}-{n}")
        os.makedirs(self.dir)

    # ---------- chat ----------
    def post(self, who, text, **meta):
        msg = {"who": who, "text": text, **meta}
        self.chat.append(msg)
        with open(os.path.join(self.dir, "transcript.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        color = COLORS.get(who, "")
        extra = ""
        if meta.get("split"):
            extra = "  " + " / ".join(f"{k} ${v:,}" for k, v in meta["split"].items())
        tag = f" [{meta['stance']}]" if meta.get("stance") else ""
        print(f"{color}{who}{tag}:{RESET} {text}{COLORS['system'] if extra else ''}{extra}{RESET}\n", flush=True)

    def transcript(self):
        lines = []
        for m in self.chat:
            line = f"{m['who']}: {m['text']}"
            if m.get("split"):
                line += "  [split: " + ", ".join(f"{k} ${v:,}" for k, v in m["split"].items()) + "]"
            if m.get("stance"):
                line += f"  [stance: {m['stance']}]"
            lines.append(line)
        return "\n".join(lines) or "(no messages yet)"

    def table_text(self):
        if not self.table:
            return "No split on the table yet."
        t = ", ".join(f"{k} ${v:,}" for k, v in self.table["split"].items())
        if self.table["by"] == "CEO" and self.reserve:
            t += f", reserve ${self.reserve['amount']:,} (day 30: {self.reserve['release']})"
        who = ", ".join(sorted(self.accepted)) or "nobody"
        return f"On the table (from {self.table['by']}): {t}. Accepted by: {who}."

    # ---------- model calls ----------
    def ask(self, system, user, mock, retry=True):
        if self.calls and DELAY:
            time.sleep(DELAY)
        self.calls += 1
        for wait in (5, 15, None):  # the model being busy shouldn't end the negotiation
            try:
                raw = llm.ask(system, user, mock, max_tokens=600, effort="low", json_mode=True)
                break
            except Exception as e:  # noqa: BLE001
                code = getattr(e, "code", None)
                if wait is None or code == 429 or code not in (500, 503, None):
                    self.error = f"Model error ({code or type(e).__name__}): {str(e)[:200]}"
                    print("\n" + self.error)
                    print(f"Stopped. Chat so far is saved in {os.path.relpath(self.dir, HERE)}/\n")
                    raise SystemExit(1)
                self.post("system", f"Model busy ({code}), waiting {wait}s and retrying.")
                time.sleep(wait)
        try:
            return llm.extract_json(raw)
        except ValueError:  # malformed JSON: ask once more rather than print raw JSON into the chat
            if retry:
                return self.ask(system, user, mock, retry=False)
            return {"say": raw[:300]}

    def valid_split(self, split, total=None):
        total = self.budget if total is None else total
        if not isinstance(split, dict):
            return None
        try:
            clean = {n: int(split.get(n, 0)) for n in self.names}
        except (TypeError, ValueError):
            return None
        return clean if sum(clean.values()) == total and min(clean.values()) >= 0 else None

    def agent_turn(self, name, turn):
        self.thinking = name
        a = next(x for x in self.s["agents"] if x["name"] == name)
        others = [n for n in self.names if n != name]
        can_escalate = turn >= self.limits.get("min_turns_before_escalation", 6)
        system = (f"You are {name}. {a['role']}\nPrivate (only you know this): {a['private_goal']}\n\n"
                  f"{self.rules}\n\n"
                  f"Reply with one JSON object only:\n"
                  '{"say": "...", "stance": "propose|accept|reject|escalate", '
                  f'"split": {{{", ".join(f"{json.dumps(n)}: 0" for n in self.names)}}} or null, '
                  f'"next": one of {others + ["CEO"] if can_escalate else others}}}\n'
                  f"Include \"split\" only when stance is propose. Splits must add up to exactly ${self.budget:,}.")
        if not can_escalate:
            system += "\nEscalating is not available yet: the group must try to settle it first."
        user = (f"Goal: {self.s['goal']}\nTotal budget: ${self.budget:,}\n{self.table_text()}\n\n"
                f"Chat so far:\n{self.transcript()}\n\nYour turn, {name}.")
        r = self.ask(system, user, lambda: self.mock_agent(name, turn))

        stance = r.get("stance") if r.get("stance") in STANCES else "reject"
        note = None
        split = self.valid_split(r.get("split")) if stance == "propose" else None
        if stance == "propose" and not split:
            got = r.get("split")
            total = sum(v for v in got.values() if isinstance(v, (int, float))) if isinstance(got, dict) else 0
            note = f"{name}'s split adds up to ${total:,.0f}, not ${self.budget:,}, so it doesn't count."
            stance = "reject"
        if stance == "escalate" and not can_escalate:
            note = f"{name} asked for the CEO, but the group hasn't tried long enough yet. Keep talking."
            stance = "reject"
        if stance == "accept" and not self.table:
            stance = "reject"

        self.post(name, r.get("say", "").strip() or "(no message)", stance=stance, split=split)
        if note:
            self.post("system", note)
        if stance == "propose":
            self.table = {"split": split, "by": name}
            self.accepted = {name}
        elif stance == "accept":
            self.accepted.add(name)
        elif stance == "reject":
            self.accepted.discard(name)
        nxt = r.get("next")
        allowed = self.names + (["CEO"] if can_escalate else [])
        return stance, (nxt if nxt in allowed and nxt != name else None)

    def ceo_turn(self, reason, objections=None, may_ask=False):
        self.thinking = "CEO"
        c = self.s["ceo"]
        ask_rule = ("Before ruling you MAY ask one department head one sharp question, only if the answer would "
                    "change your decision. To ask, reply {\"question\": {\"to\": \"<name>\", \"text\": \"...\"}} "
                    "and nothing else. Otherwise rule now.\n") if may_ask else ""
        system = (f"You are the {c['name']}. {c['role']}\n"
                  "Your department heads couldn't agree on their own and brought it to you. Read the whole chat. "
                  "Find a real middle ground: don't just average the numbers or pick a loser. Weigh each argument, "
                  "say what each person gets right, and what each one has to give up.\n"
                  "You have more levers than the split:\n"
                  "- Reserve: hold back part of the budget and release it on day 30 to whoever hits a target you set. "
                  "This lets a team below its minimum earn the rest instead of simply losing.\n"
                  "- Trades: ask one team to help another with something that isn't money (shared leads, "
                  "engineers on a demo, ad budget that doubles as sales collateral).\n"
                  "Use them only if they make the outcome better. Be decisive and fair. Keep \"say\" under 130 words.\n"
                  + ask_rule +
                  "To rule, reply with one JSON object only:\n"
                  '{"say": "...", "split": {' + ", ".join(f'"{n}": 0' for n in self.names) + "}, "
                  '"reserve": {"amount": 0, "release": "who gets it on day 30 and on what measurable condition"} or null, '
                  '"trades": ["one short line per trade"] or [], '
                  '"conditions": {"<name>": "one short condition or expectation for that person"}}\n'
                  f"split + reserve amount must add up to exactly ${self.budget:,}.")
        user = (f"Goal: {self.s['goal']}\nTotal budget: ${self.budget:,}\nWhy you were called: {reason}\n"
                f"{self.table_text()}\n\nChat so far:\n{self.transcript()}")
        if objections:
            user += ("\n\nYou already decided, and these people objected:\n" + objections +
                     "\nGive your final ruling. You may adjust the split if an objection is genuinely strong, "
                     "but this is the last word. Your first ruling's reserve and trades are cancelled unless you "
                     "restate them in this reply, and split + reserve must still add up to the budget. Objecting is not a reason to cut someone further: nobody who "
                     "objected should end up with less than in your first ruling. If one gains, say who pays for it "
                     "and why.")
        r = self.ask(system, user, lambda: self.mock_ceo(may_ask))
        q = r.get("question") if may_ask else None
        if isinstance(q, dict) and q.get("to") in self.names and q.get("text"):
            self.post("CEO", f"@{q['to']}, {q['text'].strip()}")
            self.answer_ceo(q["to"])
            return self.ceo_turn(reason, objections)
        res = r.get("reserve") if isinstance(r.get("reserve"), dict) else {}
        try:
            amount = max(0, int(res.get("amount") or 0))
        except (TypeError, ValueError):
            amount = 0
        split = self.valid_split(r.get("split"), self.budget - amount)
        if not split:  # numbers don't add up: drop the reserve rather than invent money
            amount, split = 0, self.valid_split(r.get("split")) or self.fallback_split()
            self.post("system", "The CEO's numbers didn't add up to the budget, so the reserve was dropped.")
        self.reserve = {"amount": amount, "release": res.get("release", "")} if amount else None
        text = (r.get("say") or "").strip()
        if self.reserve:
            text += f"\n  Reserve: ${amount:,}, released on day 30: {self.reserve['release']}"
        for t in r.get("trades") or []:
            text += f"\n  Trade: {t}"
        for k, v in (r.get("conditions") or {}).items():
            text += f"\n  @{k}: {v}"
        self.post("CEO", text, split=split)
        self.table = {"split": split, "by": "CEO"}
        return split

    def answer_ceo(self, name):
        self.thinking = name
        a = next(x for x in self.s["agents"] if x["name"] == name)
        system = (f"You are {name}. {a['role']}\nPrivate: {a['private_goal']}\n"
                  "The CEO asked you a question. Answer it honestly and specifically, under 60 words.\n"
                  'Reply with one JSON object only: {"say": "..."}')
        user = f"Goal: {self.s['goal']}\n\nChat so far:\n{self.transcript()}\n\nYour answer, {name}."
        r = self.ask(system, user, lambda: json.dumps({"say": "Without it, my part of the launch fails."}))
        self.post(name, (r.get("say") or "").strip() or "(no answer)")

    def commit(self, name):
        self.thinking = name
        """After the group agrees on its own: each agent says what it will do with its share."""
        a = next(x for x in self.s["agents"] if x["name"] == name)
        system = (f"You are {name}. {a['role']}\nThe group has agreed the budget split. Commit to what you will do "
                  "with your share and what you need from the others. Under 50 words.\n"
                  'Reply with one JSON object only: {"say": "...", "plan": "one sentence"}')
        user = f"Goal: {self.s['goal']}\n{self.table_text()}\n\nChat so far:\n{self.transcript()}\n\nYour turn, {name}."
        r = self.ask(system, user, lambda: self.mock_respond(name, True))
        self.post(name, (r.get("say") or "").strip() + (f"\n  Plan: {r['plan']}" if r.get("plan") else ""))
        return r.get("plan")

    def respond_to_ceo(self, name, final):
        self.thinking = name
        a = next(x for x in self.s["agents"] if x["name"] == name)
        system = (f"You are {name}. {a['role']}\nPrivate: {a['private_goal']}\n"
                  "The CEO has made a decision on the budget. Read it, including any reserve and trades. "
                  "Either accept it fully and commit to a plan, or object with a specific reason and what would fix it. "
                  "Don't accept 'under protest': if your guaranteed share is below your firm minimum and the reserve "
                  "or trades don't realistically cover the gap, object. "
                  + ("This is the CEO's final ruling: you must accept it and commit. " if final else "")
                  + "Keep \"say\" under 60 words.\nReply with one JSON object only:\n"
                  '{"say": "...", "stance": "accept|object", "plan": "what you will do with your share, one sentence"}')
        user = (f"Goal: {self.s['goal']}\n{self.table_text()}\n\nChat so far:\n{self.transcript()}\n\nYour turn, {name}.")
        r = self.ask(system, user, lambda: self.mock_respond(name, final))
        stance = "accept" if final or r.get("stance") != "object" else "object"
        text = (r.get("say") or "").strip()
        if stance == "accept" and r.get("plan"):
            text += f"\n  Plan: {r['plan']}"
        self.post(name, text, stance=stance)
        return stance, r.get("plan")

    # ---------- the loop ----------
    def run(self):
        s = self.s
        print(f"\n=== {s['title']} ===\n{s['goal']}\nBudget: ${self.budget:,}   "
              f"Mode: {'MOCK' if llm.MOCK else llm.PROVIDER + ' ' + llm.MODEL}\n")
        cap = self.limits.get("max_turns_before_ceo", 10)
        speaker = random.choice(self.names)
        outcome, reason = None, None
        for turn in range(cap):
            stance, nxt = self.agent_turn(speaker, turn)
            if self.table and self.accepted >= set(self.names):
                outcome = "agreed"
                break
            if stance == "escalate" or nxt == "CEO":
                outcome, reason = "escalated", f"{speaker} asked the CEO to step in."
                break
            if not nxt:  # nobody named: give the floor to whoever has spoken least recently
                spoken = [m["who"] for m in self.chat]
                nxt = min((n for n in self.names if n != speaker),
                          key=lambda n: max((i for i, w in enumerate(spoken) if w == n), default=-1))
            speaker = nxt
        else:
            outcome, reason = "escalated", f"No agreement after {cap} turns (time box)."
            self.post("system", f"Time box hit after {cap} turns. Escalating to the CEO.")

        if outcome == "agreed":
            self.post("system", "Everyone accepted the same split. No CEO needed.")
            self.phase = "commit"
            final = self.table["split"]
            plans = {n: self.commit(n) for n in self.names}
        else:
            self.post("system", f"Escalated to the CEO. {reason}")
            self.phase = "ceo"
            final = self.ceo_turn(reason, may_ask=True)
            self.phase = "commit"
            plans, objections = {}, []
            for n in self.names:
                stance, plan = self.respond_to_ceo(n, final=False)
                if stance == "object":
                    objections.append(n)
                else:
                    plans[n] = plan
            if objections:
                objs = "\n".join(f"{m['who']}: {m['text']}" for m in self.chat[-len(self.names):]
                                 if m["who"] in objections)
                first = dict(final)
                final = self.ceo_turn(reason, objections=objs)
                # objectors, plus anyone whose share moved, commit to the final ruling
                for n in self.names:
                    if n in objections or final[n] != first[n]:
                        _, plans[n] = self.respond_to_ceo(n, final=True)

        self.thinking = None
        self.summary(outcome, final, plans)
        self.phase = "done"

    def summary(self, outcome, split, plans):
        lines = [f"# {self.s['title']}", "", f"Outcome: **{outcome}** after {self.calls} model calls.", ""]
        if self.reserve and outcome != "agreed":
            lines += [f"Reserve: ${self.reserve['amount']:,}, released on day 30: {self.reserve['release']}", ""]
        lines += [
                 "| Department | Wanted | Firm minimum (private) | Final | Plan |", "|---|---|---|---|---|"]
        for n in self.names:
            want, floor = self._ask_of(n)
            lines.append(f"| {n} | ${want:,} | ${floor:,} | ${split[n]:,} | {plans.get(n) or '-'} |")
        self.result = {"outcome": outcome, "calls": self.calls, "reserve": self.reserve if outcome != "agreed" else None,
                       "rows": [{"name": n, "want": self._ask_of(n)[0], "floor": self._ask_of(n)[1],
                                 "final": split[n], "plan": plans.get(n) or ""} for n in self.names]}
        text = "\n".join(lines)
        with open(os.path.join(self.dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\n" + text + f"\n\nSaved to {os.path.relpath(self.dir, HERE)}/\n")

    # ---------- offline mock (rule-based, varies per run) ----------
    def _ask_of(self, name):
        goal = next(a["private_goal"] for a in self.s["agents"] if a["name"] == name)
        nums = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", goal)]
        return nums[0], nums[1] if len(nums) > 1 else nums[0]

    @staticmethod
    def _floor(goal):
        """Private minimum from a goal like 'You need $6,000 ... firm minimum is $4,500'."""
        nums = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", goal)]
        return nums[1] if len(nums) > 1 else (nums[0] if nums else 0)

    def mock_agent(self, name, turn):
        want, floor = self._ask_of(name)
        others = [n for n in self.names if n != name]
        mine = self.table["split"][name] if self.table else 0
        if self.table and mine >= floor + random.randint(0, 800):
            return json.dumps({"say": f"I can live with ${mine:,}. @{others[0]}, can you?", "stance": "accept",
                               "next": others[0]})
        if turn >= self.limits.get("min_turns_before_escalation", 6) and random.random() < 0.5:
            return json.dumps({"say": "We keep going in circles. Let's get the CEO to make the call.",
                               "stance": "escalate", "next": "CEO"})
        give = min(want, max(floor, want - turn * 300))
        rest = self.budget - give
        split = {name: give}
        for i, n in enumerate(others):
            split[n] = rest // len(others) + (rest % len(others) if i == 0 else 0)
        return json.dumps({"say": f"I need ${give:,} or my part of the launch doesn't work. "
                                  f"@{others[1]}, you can do more with less.", "stance": "propose",
                           "split": split, "next": random.choice(others)})

    def fallback_split(self):
        wants = {n: self._ask_of(n)[0] for n in self.names}
        total = sum(wants.values())
        split = {n: int(self.budget * w / total) // 100 * 100 for n, w in wants.items()}
        split[self.names[0]] += self.budget - sum(split.values())
        return split

    def mock_ceo(self, may_ask=False):
        if may_ask and random.random() < 0.5:
            return json.dumps({"question": {"to": random.choice(self.names), "text": "What breaks if you get less?"}})
        split = self.fallback_split()
        split[self.names[-1]] -= 500
        return json.dumps({"say": "Everyone has a point. I'm splitting it in proportion to need, rounded.",
                           "split": split, "reserve": {"amount": 500, "release": f"{self.names[-1]} if 5 deals close"},
                           "trades": [f"{self.names[0]} shares webinar leads with {self.names[-1]}"], "conditions": {n: "Report results in 30 days." for n in self.names}})

    def mock_respond(self, name, final):
        if not final and random.random() < 0.3:
            return json.dumps({"say": "This leaves me under my minimum. Can we revisit?", "stance": "object"})
        return json.dumps({"say": "Understood. I'll make it work.", "stance": "accept",
                           "plan": f"Spend ${self.table['split'][name]:,} on the highest-impact items first."})


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "scenarios", "budget.json")
    with open(path, encoding="utf-8") as f:
        Negotiation(json.load(f)).run()


if __name__ == "__main__":
    main()
