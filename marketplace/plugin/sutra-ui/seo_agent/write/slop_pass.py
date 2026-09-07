"""slop_pass.py — Writer step 7: SLOP PASS. Strip AI writing tells from the finished article.

The AI proposes, CODE verifies, per block:
  - the multiset of numbers must be identical before and after (facts survive style)
  - the multiset of [c] tags must be identical (provenance survives)
  - a malformed reply, or any violation -> that block keeps its ORIGINAL text, loudly logged.
Clean text passes through untouched. The ruleset is prompts/write/slop-rules.md, THE place to tune a rule.
The counts (em dashes, tier-1 words, "not just", "let's", "in conclusion") are taken before and after.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as C
from . import tags

_NUMS = re.compile(r"\d[\d,\.]*")
_TIER1 = ["delve", "leverage", "robust", "seamless", "comprehensive", "landscape", "navigate",
          "crucial", "pivotal", "foster", "bolster", "underscore", "harness", "unlock", "elevate",
          "streamline", "empower", "myriad", "plethora", "utilize", "facilitate", "testament",
          "realm", "embark", "game-chang", "cutting-edge"]


def rules():
    return C.sh.load_prompt("write/slop-rules")


def counts(text):
    low = (text or "").lower()
    return {"em_dashes": (text or "").count("—"),
            "tier1_words": sum(low.count(w) for w in _TIER1),
            "not_just": len(re.findall(r"\bnot (?:just|only)\b", low)),
            "lets": len(re.findall(r"\blet'?s \b", low)),
            "in_conclusion": len(re.findall(r"\bin conclusion\b|\bat the end of the day\b", low))}


def _num_sig(text):
    return sorted(_NUMS.findall(text or ""))


def _tag_sig(text):
    return sorted(tags.ids(text))


def clean_block(rules_text, label, text, memory):
    """One block through the AI, then the guards. Returns (final_text, changes, verdict)."""
    if not (text or "").strip():
        return text, [], "empty"
    try:
        out = llm.json_call(C.prompt("slop", rules=rules_text, text=text, memory=memory)) or {}
    except Exception as e:      # noqa: BLE001
        return text, [], "call failed: %s" % type(e).__name__
    prose = str(out.get("prose") or "")
    if not prose.strip():
        return text, [], "empty reply — original kept"
    if _num_sig(prose) != _num_sig(text):
        return text, [], "REJECTED: a number changed — original kept"
    if _tag_sig(prose) != _tag_sig(text):
        return text, [], "REJECTED: a [c] tag changed — original kept"
    changes = [c for c in (out.get("changes") or []) if isinstance(c, dict) and c.get("before")]
    return prose, changes, "cleaned" if prose != text else "already clean"


def blocks_of(w):
    blocks = [("intro", w.get("intro") or "")]
    blocks += [("quick answer", w.get("quick_answer") or "")] if w.get("quick_answer") else []
    blocks += [(s["heading"], s["prose"]) for s in w.get("sections") or []]
    blocks += [("FAQ: %s" % f["question"][:60], f["answer"]) for f in w.get("faq") or []]
    blocks.append(("close", w.get("close") or ""))
    return blocks


def put_back(w, results):
    out = C.deep(w)
    i = 0
    out["intro"] = results[i]; i += 1
    if w.get("quick_answer"):
        out["quick_answer"] = results[i]; i += 1
    for s in out.get("sections") or []:
        s["prose"] = results[i]; i += 1
    for f in out.get("faq") or []:
        f["answer"] = results[i]; i += 1
    out["close"] = results[i]
    return out


def run(w, say=lambda *a: None):
    rules_text, memory = rules(), C.sh.memory_block()
    blocks = blocks_of(w)
    before_all = counts("\n\n".join(t for _, t in blocks))
    say("Removing the tells of machine writing", "%d blocks; %d em dashes, %d flagged words before"
        % (len(blocks), before_all["em_dashes"], before_all["tier1_words"]))
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        results = list(ex.map(lambda b: clean_block(rules_text, b[0], b[1], memory), blocks))
    out = put_back(w, [r[0] for r in results])
    after_all = counts("\n\n".join(r[0] for r in results))
    report = {"before": before_all, "after": after_all,
              "blocks": [{"block": lbl, "verdict": verdict, "changes": changes}
                         for (lbl, _), (_, changes, verdict) in zip(blocks, results)]}
    rejected = [b for b in report["blocks"] if b["verdict"].startswith("REJECTED")]
    changed = [b for b in report["blocks"] if b["verdict"] == "cleaned"]
    say("Slop pass done", "%d of %d blocks cleaned, %d changes, %d blocks kept as written after a guard fired; "
        "%d em dashes, %d flagged words after"
        % (len(changed), len(blocks), sum(len(b["changes"]) for b in report["blocks"]), len(rejected),
           after_all["em_dashes"], after_all["tier1_words"]))
    return {"article": out, "report": report}
