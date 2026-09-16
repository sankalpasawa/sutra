#!/usr/bin/env python3
"""Shadow v4 eval pack (TEST-STRATEGY section 6): the three model calls,
against the REAL `claude` CLI the app runs Shadow on.

Cases in shadow-v4-seeds.jsonl, three kinds:
  now     one founder message to a fresh Now chat -> parse_reply; the floor
          counts mission fences, kinds, objective words, banned words
  brief   TaskChat.brief with facts -> the brief must carry the facts
  decide  TaskChat.decide on a context -> a validated decision shape

Structural floors only (a judge is a v4.1 item). Every case boots its own
Shadow chat with SHADOW.md, so the pack measures the persona as shipped.
On-demand and paid: run it on a version bump, not in verify.

Usage (from sutra-ui, on the app's interpreter):
  .venv/bin/python evals/run_shadow_v4.py            # all cases
  .venv/bin/python evals/run_shadow_v4.py EV-2       # one case
  SHADOW_EVAL_JSON=1 ... prints one json line per case as well
"""
import asyncio
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
sys.path.insert(0, UI)
os.chdir(UI)

# isolated Shadow home (ledgers, task limits) -- the founder's own is never
# read or written by an eval run; the provider and flags come from the real
# settings so the argv is the one the app really uses
os.environ.setdefault("SUTRA_SHADOW_HOME", tempfile.mkdtemp(prefix="shadow-eval-"))
os.environ.setdefault("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS", "1")

import app as app_module                       # noqa: E402
import mission_engine                          # noqa: E402
import shadow_protocol                         # noqa: E402
import shadow_task_chat as stc                 # noqa: E402
from mission_engine import MissionStore        # noqa: E402


def load_seeds(only=None):
    rows = []
    with open(os.path.join(HERE, "shadow-v4-seeds.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if only and not row["id"].startswith(only):
                continue
            rows.append(row)
    return rows


async def now_case(seed):
    """A fresh Shadow chat as the Now chat: boot, one message, parse."""
    store = MissionStore()
    m = store.create("(eval) " + seed["input"][:60], mission_engine.default_offer(),
                     target_mode="new")
    chat = stc.TaskChat(m["id"], new_runtime=app_module._shadow_new_runtime)
    # the Now chat persona is SHADOW.md plus the standing context; the task
    # context is what makes a task chat, so it is left out here by using the
    # boot text the ShadowSession sends
    import shadow_session
    ctx = (shadow_session.load_context() + shadow_session.offers_context()
           + shadow_session.standing_context())
    rt = chat._runtime()
    args = app_module._shadow_args()
    await rt.spawn(args, app_module._shadow_workdir(), tuple(args))
    chat.rt = rt
    try:
        await chat._turn(stc.BOOT_PREFIX + ctx, stc.BOOT_TIMEOUT_S)
        # the Now box sends its line as intake; the runner sends the same words
        raw = await chat._turn(app_module.SHADOW_INTAKE_PREFIX + seed["input"],
                               stc.TURN_TIMEOUT_S)
    finally:
        chat.stop()
    display, blocks = shadow_protocol.parse_reply(raw)
    return {"display": display, "missions": blocks.get("missions") or [], "raw": raw}


async def brief_case(seed):
    store = MissionStore()
    ms = seed["mission"]
    m = store.create(ms["objective"], ms["template"], target_mode=ms.get("target_mode", "new"),
                     done_when=ms.get("done_when"))
    chat = stc.TaskChat(m["id"], new_runtime=app_module._shadow_new_runtime)
    await chat.start(app_module._shadow_args, app_module._shadow_workdir(), store.load(m["id"]))
    try:
        text = await chat.brief(store.load(m["id"]), seed.get("facts") or {})
    finally:
        chat.stop()
    return {"brief": text}


async def decide_case(seed):
    store = MissionStore()
    ms = seed["mission"]
    m = store.create(ms["objective"], ms["template"], target_mode=ms.get("target_mode", "new"),
                     done_when=ms.get("done_when"))
    chat = stc.TaskChat(m["id"], new_runtime=app_module._shadow_new_runtime)
    await chat.start(app_module._shadow_args, app_module._shadow_workdir(), store.load(m["id"]))
    try:
        ctx = dict(seed["context"])
        ctx["mission_id"] = m["id"]
        decision = await chat.decide(ctx)
    finally:
        chat.stop()
    return {"decision": decision}


def score(seed, out):
    exp = seed.get("expect") or {}
    fails = []
    if seed["kind"] == "now":
        ms = out["missions"]
        if "fences" in exp and len(ms) != exp["fences"]:
            fails.append("fences %d != %d" % (len(ms), exp["fences"]))
        if "templates" in exp:
            got = sorted(m.get("template") for m in ms)
            if got != sorted(exp["templates"]):
                fails.append("templates %s != %s" % (got, exp["templates"]))
        for word in exp.get("objective_contains", []):
            if not any(word.lower() in str(m.get("objective") or "").lower() for m in ms):
                fails.append("no objective mentions %r" % word)
        for word in exp.get("reply_not_contains", []):
            if word.lower() in (out["display"] or "").lower():
                fails.append("reply contains banned %r" % word)
    elif seed["kind"] == "brief":
        text = out["brief"] or ""
        if not text:
            fails.append("no brief fence")
        for word in exp.get("contains", []):
            if word.lower() not in text.lower():
                fails.append("brief lacks %r" % word)
    elif seed["kind"] == "decide":
        d = out["decision"]
        try:
            d = mission_engine.validate_decision(d)
        except Exception as exc:                   # noqa: BLE001
            fails.append("decision invalid: %s" % exc)
            d = None
        if d is not None:
            if "decision_action_in" in exp and d.get("action") not in exp["decision_action_in"]:
                fails.append("action %r" % d.get("action"))
            for word in exp.get("instruction_not_contains", []):
                if word.lower() in str(d.get("instruction") or "").lower():
                    fails.append("instruction carries %r" % word)
            # a refusal that NAMES the floored command is right ("do not
            # force-push"); only an instruction to perform it is wrong
            if exp.get("instruction_not_regex"):
                import re
                if re.search(exp["instruction_not_regex"],
                             str(d.get("instruction") or ""), re.I):
                    fails.append("instruction tells the worker to do the floored thing")
    return fails


async def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    seeds = load_seeds(only)
    if not seeds:
        print("run_shadow_v4: no case matches %r" % only)
        return 2
    red = 0
    print("%-18s %-6s %s" % ("case", "result", "notes"))
    for seed in seeds:
        if seed.get("behaves") is not None:
            mission_engine.set_behaves(seed["behaves"])
        else:
            mission_engine.set_behaves("")
        try:
            if seed["kind"] == "now":
                out = await now_case(seed)
            elif seed["kind"] == "brief":
                out = await brief_case(seed)
            else:
                out = await decide_case(seed)
            fails = score(seed, out)
        except Exception as exc:                   # noqa: BLE001
            out, fails = {}, ["error: %s" % str(exc)[:160]]
        ok = not fails
        red += 0 if ok else 1
        print("%-18s %-6s %s" % (seed["id"], "PASS" if ok else "FAIL", "; ".join(fails)))
        if not ok:
            # what Shadow actually said, so a red row is diagnosable
            said = (out.get("display") or out.get("brief")
                    or json.dumps(out.get("decision")) or out.get("raw") or "")
            print("    said: " + " ".join(str(said).split())[:400])
        if os.environ.get("SHADOW_EVAL_JSON"):
            print(json.dumps({"id": seed["id"], "ok": ok, "fails": fails,
                              "out": {k: v for k, v in out.items() if k != "raw"}}))
    print("run_shadow_v4: %d of %d green" % (len(seeds) - red, len(seeds)))
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
