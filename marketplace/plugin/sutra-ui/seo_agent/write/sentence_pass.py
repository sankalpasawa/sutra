"""sentence_pass.py — Writer step 6: SENTENCE PASS. Re-shape the sentences so a reader gets through them.

Readable owns DENSITY. This step owns SENTENCE SHAPE and changes nothing else: same length, same facts,
same sections, every one of those checked in code, per block, against the block it was given:
  - word count within max(WORD_FLOOR, WORD_TOLERANCE)   - the SET of numbers (none lost, none invented)
  - the multiset of [c] tags                             - every markdown link, words and address
  - every "### " sub-heading line                        - every table row and bullet, verbatim
  - average sentence length must not RISE, and on a block of 60+ words must not fall under AVG_FLOOR
One retry, told what it broke. Then the block keeps its ORIGINAL text, loudly logged. The rhythm floor
(LONG_KEEP_RATIO) is SOFT: it buys a retry, it never discards a block.
"""
import re
import statistics
from concurrent.futures import ThreadPoolExecutor

from .. import llm
from . import _common as C
from . import tags

_NUMS = re.compile(r"\d[\d,\.]*")
_MDLINK = C._MDLINK
_TAG = re.compile(r"\[c[\d,\s c]*\]")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

MIN_BLOCK_WORDS = 25        # a block shorter than this is a caption, not prose
WORD_TOLERANCE = 0.05       # the band a rewrite must land in, as a share of the block it replaces
WORD_FLOOR = 8              # ...with a floor in words, for the FAQ
ARTICLE_DRIFT = 0.025       # how far the WHOLE article may drift before the run says so (reported)
AVG_SLACK = 0.5             # average sentence length may drift up by this much before the rewrite is pointless
AVG_FLOOR = 8.5             # ...and a floor under it: a run of six-word sentences reads like a machine
AVG_FLOOR_MIN_WORDS = 60
SPREAD_OUT_FLOOR = 5.5      # absolute spread of sentence lengths in the finished article (reported)
LONG_OUT_FLOOR = 0.18       # share of sentences still running 18+ words (reported)
SPREAD_KEPT_FLOOR = 0.90    # ...or it simply kept the variety it arrived with
LONG_KEEP_RATIO = 0.70      # the share of a block's long sentences that must SURVIVE (soft)


def _prose_lines(text):
    out = []
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith(("- ", "* ", "+ ")):
            continue
        if re.match(r"^\d+\.\s", s):
            continue
        out.append(s)
    return out


def _plain(text):
    return _TAG.sub("", _MDLINK.sub(r"\1", text or ""))


def words(text):
    return len(_plain(text).split())


def sentences(text):
    joined = " ".join(_prose_lines(_plain(text)))
    return [s for s in _SENT_SPLIT.split(joined) if len(s.split()) > 1]


def avg_sentence(text):
    ss = sentences(text)
    return round(sum(len(s.split()) for s in ss) / len(ss), 1) if ss else 0.0


def spread(text):
    L = [len(s.split()) for s in sentences(text)]
    return round(statistics.pstdev(L), 2) if len(L) > 2 else 0.0


def long_share(text, k=18):
    L = [len(s.split()) for s in sentences(text)]
    return round(sum(1 for x in L if x >= k) / len(L), 3) if L else 0.0


def _num_sig(text):
    """The SET of figures, not the multiset: splitting a sentence often repeats its subject."""
    return {n.rstrip(",.") for n in _NUMS.findall(text or "")}


def _tag_sig(text):
    return sorted(tags.ids(text))


def _link_sig(text):
    return sorted(_MDLINK.findall(text or ""))


def _head_sig(text):
    return [l.strip() for l in (text or "").split("\n") if l.strip().startswith("#")]


def _struct_sig(text):
    return [l.strip() for l in (text or "").split("\n")
            if l.strip().startswith("|") or l.strip().startswith(("- ", "* ", "+ ")) or re.match(r"^\d+\.\s", l.strip())]


def violations(before, after):
    """Every contract the rewrite broke, in plain words. Empty list means accept it."""
    bad = []
    n = words(before)
    tol = max(WORD_FLOOR, round(n * WORD_TOLERANCE))
    m = words(after)
    if abs(m - n) > tol:
        bad.append("word count %d, must be %d-%d" % (m, n - tol, n + tol))
    lost = sorted(_num_sig(before) - _num_sig(after))
    made = sorted(_num_sig(after) - _num_sig(before))
    if lost:
        bad.append("a number went missing: %s" % ", ".join(lost[:4]))
    if made:
        bad.append("a number appeared that was not there: %s" % ", ".join(made[:4]))
    if _tag_sig(after) != _tag_sig(before):
        bad.append("a [c] source tag changed")
    if _link_sig(after) != _link_sig(before):
        bad.append("a markdown link changed")
    if _head_sig(after) != _head_sig(before):
        bad.append("a ### sub-heading changed")
    if _struct_sig(after) != _struct_sig(before):
        bad.append("a table row or bullet changed")
    if avg_sentence(after) > avg_sentence(before) + AVG_SLACK:
        bad.append("average sentence length rose (%s to %s)" % (avg_sentence(before), avg_sentence(after)))
    if n >= AVG_FLOOR_MIN_WORDS and avg_sentence(after) < AVG_FLOOR:
        bad.append("chopped too fine (average sentence %s words)" % avg_sentence(after))
    return bad


def _longest(text):
    L = [len(s.split()) for s in sentences(text)]
    return max(L) if L else 0


def _long_count(text, k=18):
    return sum(1 for s in sentences(text) if len(s.split()) >= k)


def _long_target(text):
    n = _long_count(text)
    return max(1, round(n * LONG_KEEP_RATIO)) if n else 0


def _rhythm_short(before, after):
    want, got = _long_target(before), _long_count(after)
    if want and got < want:
        return ("only %d sentence(s) of 18+ words came back, and this block needs at least %d to keep the variety it arrived with"
                % (got, want))
    return ""


def shape_block(reader, label, text, memory):
    """One block through the AI, then the guards. Returns (final, moves, verdict)."""
    if words(text) < MIN_BLOCK_WORDS:
        return text, [], "too short — left alone"
    n = words(text)
    tol = max(WORD_FLOOR, round(n * WORD_TOLERANCE))
    base = C.prompt("sentence-pass", words_now=n, words_min=n - tol, words_max=n + tol, avg_now=avg_sentence(text),
                    longest_now=_longest(text), longest_keep=max(18, int(_longest(text) * 0.8)),
                    sent_now=len(sentences(text)), long_now=_long_count(text), long_keep=_long_target(text),
                    reader=reader, text=text, memory=memory)
    prompt, last, best = base, [], None
    for attempt in (1, 2):
        try:
            out = llm.json_call(prompt) or {}
        except Exception as e:      # noqa: BLE001
            return best or (text, [], "call failed: %s" % type(e).__name__)
        prose = str(out.get("prose") or "")
        if not prose.strip():
            return best or (text, [], "empty reply — original kept")
        last = violations(text, prose)
        moves = [str(m) for m in (out.get("moves") or []) if str(m).strip()]
        if not last:
            soft = _rhythm_short(text, prose)
            verdict = "reshaped" if prose.strip() != text.strip() else "already plain"
            if not soft or attempt == 2:
                if soft and best and _long_count(best[0]) > _long_count(prose):
                    return best[0], best[1], best[2] + " (kept the first, livelier attempt)"
                return prose, moves, verdict + (" — flatter than it should be" if soft else "")
            best = (prose, moves, verdict)
            prompt = (base + "\n\n════════════════════════════════════════\nREAD THE RHYTHM SECTION AGAIN. " + soft
                      + ".\nHand back the same block, same length, same facts, but leave the long sentences that carry "
                        "ONE idea alone. Only split the ones carrying two or three.")
            continue
        if attempt == 1:
            prompt = (base + "\n\n════════════════════════════════════════\nYOUR LAST REPLY WAS REJECTED BY THE CODE CHECK: "
                      + "; ".join(last) + ".\nRe-shape the SAME block again and fix exactly that. Re-say the sentences "
                        "at the same length; do not delete anything to make room.")
    return best or (text, [], "REJECTED: " + "; ".join(last) + " — original kept")


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


def run(w, plan, say=lambda *a: None):
    reader = (((plan.get("persona") or {}).get("name") if isinstance(plan.get("persona"), dict) else "") or "reader").lower()
    memory = C.sh.memory_block()
    blocks = blocks_of(w)
    whole_before = "\n\n".join(t for _, t in blocks)
    say("Re-shaping the sentences", "%d blocks, %d words, average sentence %s words" % (len(blocks), words(whole_before), avg_sentence(whole_before)))
    with ThreadPoolExecutor(max_workers=llm.PARALLEL) as ex:
        results = list(ex.map(lambda b: shape_block(reader, b[0], b[1], memory), blocks))
    out = put_back(w, [r[0] for r in results])
    whole_after = "\n\n".join(r[0] for r in results)
    report = {
        "before": {"words": words(whole_before), "sentences": len(sentences(whole_before)),
                   "avg_sentence": avg_sentence(whole_before), "spread": spread(whole_before), "long_share": long_share(whole_before)},
        "after": {"words": words(whole_after), "sentences": len(sentences(whole_after)),
                  "avg_sentence": avg_sentence(whole_after), "spread": spread(whole_after), "long_share": long_share(whole_after)},
        "blocks": [{"block": lbl, "verdict": verdict, "words_before": words(orig), "words_after": words(final),
                    "avg_before": avg_sentence(orig), "avg_after": avg_sentence(final), "moves": moves}
                   for (lbl, orig), (final, moves, verdict) in zip(blocks, results)],
    }
    drift = (report["after"]["words"] - report["before"]["words"]) / max(1, report["before"]["words"])
    report["drift"] = round(drift * 100, 2)
    report["drift_ok"] = abs(drift) <= ARTICLE_DRIFT
    ratio = (report["after"]["spread"] / report["before"]["spread"]) if report["before"]["spread"] else 1.0
    report["spread_ratio"] = round(ratio, 2)
    report["rhythm_ok"] = ((report["after"]["spread"] >= SPREAD_OUT_FLOOR and report["after"]["long_share"] >= LONG_OUT_FLOOR)
                           or ratio >= SPREAD_KEPT_FLOOR)
    rejected = [b for b in report["blocks"] if b["verdict"].startswith("REJECTED")]
    reshaped = [b for b in report["blocks"] if b["verdict"].startswith("reshaped")]
    say("Sentence pass done", "%d of %d blocks re-shaped, %d rejected; average sentence %s -> %s words"
        % (len(reshaped), len(blocks), len(rejected), report["before"]["avg_sentence"], report["after"]["avg_sentence"]))
    if not report["rhythm_ok"]:
        say("The rhythm went flat", "every sentence is landing in the same band; read it before shipping")
    return {"article": out, "report": report}
