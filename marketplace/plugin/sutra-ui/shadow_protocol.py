"""The structured-reply protocol (GAP-AUDIT row 4; R6/R18/R19).

Shadow's replies may carry fenced blocks the app parses DETERMINISTICALLY:

    ```mission
    {"objective": "...", "template": "fix", "target_session": "s-1"}
    ```
    ```goal
    {"outcome": "...", "done_when": [{"tier": "contains_artifact", "check": "..."}]}
    ```
    ```chips
    ["Review the brief", "Stop mission"]
    ```
    ```remember
    {"text": "...", "precedence": "taste"}
    ```
    ```module
    {"name": "...", "kind": "chat"}
    ```
    ```brief
    <the worker's opening brief, in prose; a task chat's answer, v4>
    ```
    ```limits
    {"scope": "task", "turns": 100}          (v4.1; "turns": "none" = no limit;
                                              "scope": "default" = the sheet;
                                              "running_at_once": n)
    ```
    ```answer
    {"kind": "approve|confirm|withdraw|change", "index": 0, "text": "..."}
    ```                                      (v4.2; the founder's line answers
                                              a pending ask; the app binds it)
    ```forward
    {"worker": true}
    ```

Blocks are stripped from the displayed reply. remember rows land UNCONFIRMED
(inert until the founder taps Confirm). SHADOW.md documents the same protocol
to the model; the fake claude in tests emits these blocks.

`forward` IS A TASK-CHAT FENCE AND IS DELIBERATELY NOT IN SHADOW.md. It is
Shadow's verdict on whether the founder's line must reach the WORKER of one
task (shadow_forward), so it is instructed per task in
shadow_task_chat.task_context, where a worker exists to forward to. The Now
chat has no worker and is never asked for it.

A `goal` block is a PROPOSAL, never a creation (slice 8): unlike `mission`,
nothing is written when it arrives. It is echoed back to the surface, the
founder reads and edits it in a confirmation card, and only their Confirm
POSTs to /api/shadow/goals. `done_when` is deliberately OPTIONAL here --
Shadow is told not to invent completion criteria it cannot honestly derive,
and the card makes the founder supply them rather than fabricating.

A `module` fence creates an app (Org > Apps) immediately as a draft -- see
the D-M10 note in parse_reply.

HISTORY, so this merge is not undone again: the goal fence and the tier
contract landed in 051b130 (2026-09-11); the module fence landed the same day
from a working copy that predated that commit and replaced the file, which
dropped both (test_proposal_tiers, test_goal_creation went red while app.py
kept handling `blocks["goal"]`). Both fences are load-bearing; keep both.
"""
import json
import re

_BLOCK = re.compile(r"```(mission|goal|chips|remember|module|brief|limits|answer|forward)\s*\n(.*?)```", re.S)

#: Shadow v4.2: what a typed answer may say it is. The SAME closed list
#: mission_engine.apply_answer accepts; the app binds it to the one pending ask.
_ANSWER_KINDS = ("approve", "confirm", "withdraw", "change")


def parse_answer(val):
    """An `answer` fence -> {kind, index?, text?}, or None.

    THE FOUNDER'S TYPED LINE ANSWERS THE ASK (founder 2026-09-21). Shadow is
    told the pending asks, reads the founder's line, and says which ask it
    answers; the app -- never the model -- applies it, bound to that ask
    (approve_held_say's one-use object, confirm_check's index). Strict like
    every fence: a shape this does not recognise stays visible and does
    nothing. No key here can name another task or reach a floor."""
    if not isinstance(val, dict) or val.get("kind") not in _ANSWER_KINDS:
        return None
    if set(val) - {"kind", "index", "text"}:
        return None
    out = {"kind": val["kind"]}
    if "index" in val:
        ix = val["index"]
        if isinstance(ix, bool) or not isinstance(ix, int) or ix < 0:
            return None
        out["index"] = ix
    if "text" in val:
        if not isinstance(val["text"], str):
            return None
        out["text"] = val["text"].strip()[:2000]
    return out

#: Shadow v4.1 (V4-7): what the founder may say for "no limit". A closed list,
#: matched whole, and deliberately the SAME list mission_engine coerces with.
_NO_LIMIT_WORDS = ("none", "no limit", "unlimited", "off")
_LIMITS_SCOPES = ("task", "default")


def parse_limits(val):
    """A `limits` fence -> {scope, turns?, running_at_once?}, or None.

    THE FOUNDER'S WORDS SET THE TASK (SHADOW-V3 section 13.1). Shadow hears
    "no turn limit" / "give it 100 turns" / "run 8 at once" and emits ONE
    fence; the app -- never a model -- writes the store. This only says
    whether the fence is well-formed; clamping and every refusal that needs
    the task record (already-spent turns, a kind that never speaks) belong to
    mission_engine, which is the one writer.

    STRICT, like every other fence: a shape this does not recognise returns
    None and the caller leaves the block VISIBLE in the reply. There is no
    key here that reaches a floor, another task, or anything but the two
    numbers the sheet already exposes.
    """
    if not isinstance(val, dict):
        return None
    scope = val.get("scope", "task")
    if scope not in _LIMITS_SCOPES:
        return None
    if set(val) - {"scope", "turns", "running_at_once"}:
        return None
    out = {"scope": scope}
    if "turns" in val:
        t = val["turns"]
        if t is None or (isinstance(t, str)
                         and t.strip().lower() in _NO_LIMIT_WORDS):
            out["turns"] = "none"
        elif isinstance(t, int) and not isinstance(t, bool) and t >= 1:
            out["turns"] = t
        else:
            return None
    if "running_at_once" in val:
        r = val["running_at_once"]
        if isinstance(r, int) and not isinstance(r, bool) and r >= 1:
            out["running_at_once"] = r
        else:
            return None
    if len(out) == 1:
        return None                     # a scope and nothing to set
    return out

# A `module` fence creates a module (Org > Modules). Kinds mirror
# modules_api.KINDS; kept literal here so the parser stays import-free.
_MODULE_KINDS = ("chat", "page", "link")


# ---------------------------------------------------- the tier contract ---
# WHY THIS EXISTS (live flight, goal g-d804849d1400, 2026-09-11). Shadow
# proposed two checks under `contains_artifact`:
#
#   "An explicit winner named as the final choice -- the word 'Python' or
#    'Go' stated as the pick, not a 'depends' or 'both work' hedge"
#   "Three distinct concrete reasons listed for that pick, each tied to a
#    specific tradeoff ... rather than generic praise"
#
# `contains_artifact` is a LITERAL SUBSTRING TEST (mission_engine:284) and
# always will be -- it is the one tier with no judgement in it. A criterion
# DESCRIPTION can never appear verbatim in a transcript, so both checks were
# structurally unsatisfiable. The chat answered perfectly ("## Winner:
# **Python**", three reasons); both checks still read False, the unmet list
# never changed, the follow-up say repeated itself and the ping-pong guard
# correctly stopped the attempt. Nothing was broken except the contract.
#
# SHADOW.md already says contains_artifact is "a string that must appear in
# the chat". The model had the right instruction and produced the wrong
# thing, so the boundary enforces it rather than asking again.
#
# THE RULE: a proposal's tier is ADVISORY. What decides is the SHAPE of the
# check, and a check that is not literal-shaped becomes founder_confirm --
# kept, never dropped, and answerable by the one party who can judge it.

#: THE INVERSION (founder D-SH-1, 2026-09-20). Everything below this line
#: used to end at the founder. It does not any more, and this is the note
#: that explains the reversal so it is not quietly undone.
#:
#: WHAT THE OLD RULE COST. `FALLBACK_TIER` was `founder_confirm` and the
#: comment above it read "when machine-checking is not available, the founder
#: is". That was true, and it was measured on the founder's own install:
#: across every mission that had ever run, 9 done-when checks out of 9 were
#: founder_confirm. Zero were ever settled by Shadow. The founder was the
#: test runner and the code reviewer, three clicks per task, forever.
#:
#: WHY THE OLD RULE WAS RIGHT WHEN IT WAS WRITTEN. Demoting was a ONE-WAY
#: DOOR: a check sent to the founder had no way back, so sending it anywhere
#: else risked a check nobody would ever settle -- or worse, one the worker
#: could close by uttering a sentence (m-245777cf1467). Against those two
#: outcomes, "when in doubt, ask the founder" was the only safe answer.
#:
#: WHY IT IS NOT A ONE-WAY DOOR ANY MORE, which is the whole reason this can
#: change. `judge` (shadow_judge) has THREE verdicts, and the third is
#: `cannot_tell`. A check routed to the judge that the judge cannot settle
#: comes BACK to the founder automatically. So a wrong routing now costs one
#: extra model call instead of a check that never gets answered, and the
#: conservative direction is no longer "ask the founder" -- it is "try, and
#: fall back to the founder when trying does not work".
#:
#: `verify` IS ALSO BACK. The comment that removed it said "NO production
#: caller passes a verifier". That stopped being true on 2026-09-17 when
#: probes shipped, and stayed in the code afterwards: app.py passes
#: `_shadow_verifier` at four call sites and `resolve_verify_tier` settles a
#: probe-backed row against the real filesystem. A `verify` row carrying a
#: valid probe is the single most trustworthy tier there is, and it was being
#: demoted to a signature.
PROPOSAL_TIERS = ("contains_artifact", "verify", "judge", "founder_confirm")

#: WHERE A CHECK GOES WHEN NOTHING ELSE CLAIMS IT. This is the inversion in
#: one constant: it was `founder_confirm` and it is now `judge`.
FALLBACK_TIER = "judge"

#: ...and where a check goes when it is genuinely the founder's. Named
#: separately from FALLBACK_TIER because they were the same string for a
#: reason that no longer holds, and a future edit must be able to move one
#: without moving the other.
FOUNDER_TIER = "founder_confirm"

#: a literal artifact is a MARKER, not a sentence: short, few words, and
#: free of the punctuation and vocabulary that only appear when someone is
#: DESCRIBING a requirement rather than quoting one.
_ARTIFACT_MAX_CHARS = 60
_ARTIFACT_MAX_WORDS = 8
_CRITERION_MARKER = re.compile(
    "(—|–"              # em/en dash: introduces an aside
    "|\\b(?:not|rather|instead|each|either|such as|e\\.g\\.|etc"
    "|distinct|concrete|explicit(?:ly)?|genuine|generic|appropriate"
    "|relevant|valid|reasonable|must|should|listed|stated|named"
    "|tied|hedge|at least|no more than)\\b)", re.I)

#: OUTCOME-SHAPED CRITERIA ARE NOT ARTIFACTS (founder, 2026-09-15).
#:
#: THE LIVE FAILURE, mission m-245777cf1467. The founder wrote "The task
#: reaches DONE." as a criterion. It is short, five words, and carries no
#: marker above -- so is_literal_artifact called it literal, tier_for kept
#: contains_artifact, and evaluate_done_when tests that tier with
#:
#:     met = check["check"] in transcript_text
#:
#: which made the criterion satisfiable by the WORKER SAYING ITS WORDS. The
#: delegate duly wrote "Committed as f96c3ade. The task reaches DONE." A
#: check about whether the work finished became a check about whether the
#: chat contained a sentence.
#:
#: The distinction the shape test could not draw is KIND, not form: an
#: artifact is a string that will appear in the transcript because the work
#: PRODUCED it (a filename, a marker, an exact output line); an outcome is a
#: statement ABOUT the work, and only the founder can judge one. These are
#: the phrasings that describe a state of the task itself.
#:
#: Demotion is the safe direction and the existing one: tier_for already
#: sends everything non-literal to founder_confirm, which no machine can
#: satisfy. A false demotion costs one sign-off; a false artifact is a check
#: the worker can close by talking, which is what this prevents.
_OUTCOME_MARKER = re.compile(
    "\\b(?:reach(?:es|ed)?|is|are|was|were|be|becomes?)\\s+"
    "(?:done|complete[d]?|finished|working|ready|green|passing)\\b"
    "|\\b(?:task|mission|work|feature|it)\\s+(?:is|was)\\s+"
    "(?:done|complete[d]?|finished)\\b"
    "|\\bstill\\s+works?\\b"
    "|\\btests?\\s+pass(?:es|ed)?\\b"
    "|\\bcover(?:s|ed)?\\s+the\\b", re.I)


def is_literal_artifact(check):
    """Could this string plausibly appear VERBATIM in a transcript?

    Deterministic and deliberately conservative: every false negative costs
    one founder sign-off, while a false positive is the unsatisfiable check
    this whole function exists to prevent. Erring toward the founder is the
    cheap direction.
    """
    s = str(check or "").strip()
    if not s or len(s) > _ARTIFACT_MAX_CHARS:
        return False
    if len(s.split()) > _ARTIFACT_MAX_WORDS:
        return False
    if _OUTCOME_MARKER.search(s) is not None:
        return False                  # a statement ABOUT the work, not a
                                      # string the work produces
    return _CRITERION_MARKER.search(s) is None


#: THE ONLY THINGS THAT STILL REACH THE FOUNDER (founder D-SH-1, 2026-09-20):
#: taste, and facts only they hold. The direction was "only matter of taste
#: and absolute essential stuff", and this regex is that sentence made
#: deterministic so it can be audited instead of trusted.
#:
#: TASTE is a question with no correct answer, only the founder's: whether
#: something reads well, looks right, is worth doing, is acceptable to them.
#: No diff settles it and no command settles it, because there is nothing in
#: the artifact to settle it against -- the answer lives in the founder.
#:
#: A FACT ONLY THEY HOLD is a question with a correct answer that is not
#: written anywhere Shadow can read: a credential, a budget ceiling, which
#: region, which of two things they want.
#:
#: DELIBERATELY NARROW, and this is the opposite of the old bias. Every word
#: here sends a check away from Shadow and onto the founder's desk, so the
#: cost of a false positive is exactly the cost this whole change exists to
#: remove. A check that should have been the founder's and is not still ends
#: up with them: the judge answers `cannot_tell` and it comes back. There is
#: no such recovery in the other direction, which is why this list is short.
_FOUNDER_ONLY_MARKER = re.compile(
    r"\b(?:"
    r"taste|aesthetic|aesthetics"
    r"|(?:looks?|reads?|feels?|sounds?|scans?)\s+"
    r"(?:good|well|right|fine|ok|okay|off|wrong|natural|clean|polished)"
    r"|(?:you|founder)\s+(?:are\s+)?(?:happy|satisfied|content)\s+with"
    r"|(?:your|founder\'?s?)\s+(?:call|choice|preference|judgement|judgment|taste)"
    r"|(?:you|founder)\s+(?:prefers?|preferred|decides?|decided|chooses?|chose"
    r"|picks?|picked|approves?|approved|wants?|wanted|asked\s+for"
    r"|signs?|meant)"
    r"|sign(?:s|ed)?[\s-]?off|signoff"
    r"|acceptable\s+to\s+(?:you|the\s+founder)"
    r"|(?:founder|you)\s+(?:confirms?|confirmed|accepts?|accepted)"
    r"|worth\s+(?:doing|shipping|the)"
    r"|api[\s_-]?key|credential|password|secret\s+key|access\s+token"
    r"|budget|which\s+region|spend(?:ing)?\s+(?:cap|limit)"
    r")\b", re.I)


def is_founder_only(check):
    """Is this a question ONLY the founder can answer?

    Deterministic, and deliberately conservative in the NEW direction: a
    false negative here costs one judge call that returns `cannot_tell` and
    routes to the founder anyway, while a false positive costs exactly the
    thing this whole change removes -- a click the founder should never have
    been asked for.
    """
    return _FOUNDER_ONLY_MARKER.search(str(check or "")) is not None


def tier_for(check, proposed=None, probe=None):
    """The tier a proposed check ACTUALLY gets.

    `proposed` is what Shadow asked for and is still never trusted on its
    own -- but what an untrusted proposal now falls back TO is the judge, not
    the founder. See PROPOSAL_TIERS above for why that reversal is safe.

    THE LADDER, in order, and the order is the design:

      1. contains_artifact + a literal-shaped string  -> kept. The one tier
         with no judgement in it, and a marker really can appear verbatim.
      2. verify + a valid probe                       -> kept. A probe reads
         the real filesystem or runs a real command; nothing is more certain
         than this and it used to be thrown away.
      3. the check is taste, or a fact only the founder holds -> the founder.
         This is now the ONLY road to a signature.
      4. everything else                              -> judge.

    NOTE WHAT IS NOT IN THE LADDER: a branch on who wrote the check. There is
    no such field and there must not be one -- a condition the founder typed
    and a condition Shadow wrote are the same object, something Shadow is
    responsible for establishing. That rule was written for
    `_apply_verification` on 2026-09-17 and it applies here unchanged.

    A PROPOSED `founder_confirm` IS NOT ENOUGH ON ITS OWN, and that is the
    sharp edge of this change. On the founder's live install every one of the
    9 checks reached them with `proposed_tier` of NONE -- Shadow named no
    tier at all and the fallback did the rest. Honouring a bare
    `founder_confirm` would leave exactly that door open under a new name, so
    a check routed to the founder has to LOOK like the founder's question.
    When one genuinely is and does not look like it, the judge says
    `cannot_tell` and it arrives on their desk one call later.
    """
    want = str(proposed or "").strip()
    if want == "contains_artifact" and is_literal_artifact(check):
        return "contains_artifact"
    if want == "verify" and shadow_probe_ok(probe):
        return "verify"
    if is_founder_only(check):
        return FOUNDER_TIER
    # missing, unknown, a semantic string under contains_artifact, a probeless
    # `verify`, or a `founder_confirm` on something Shadow could establish --
    # all one answer, and it is still never "drop the check"
    return FALLBACK_TIER


def shadow_probe_ok(raw):
    """Is this a probe the engine would actually run? Imported lazily and
    NEVER RAISES, for the same reason offered_kinds() does not: this module
    sits on the path of every Shadow reply and is deliberately import-light.
    A probe that cannot be validated is simply not a probe, which drops the
    row to the judge rather than to an exception."""
    if not raw:
        return False
    try:
        import shadow_probe
        return shadow_probe.validate_probe(raw) is not None
    except Exception:                      # noqa: BLE001 -- see docstring
        return False


def offered_kinds():
    """The kinds a mission block may name: the founder's Delegate offers.

    THIS USED TO BE THE TUPLE ("feature", "fix", "research", "watch"), typed
    inline at the membership test below and duplicated in three other files.
    It is now one read of the setting the founder actually edits, taken at
    parse time so a kind added or removed in Settings binds the very next
    reply rather than the next restart.

    NEVER RAISES, and that is load-bearing rather than defensive: this sits
    on the path of every Shadow reply, and a corrupt settings file must cost
    the founder their custom kinds, never an exception thrown into the middle
    of a conversation. The fallback is what an unconfigured install offers.

    Imported lazily. mission_engine pulls in providers, the ledger and the
    intervention validator; shadow_protocol is deliberately a two-import
    module and is loaded by things that have no business starting an engine.
    """
    try:
        import mission_engine
        kinds = mission_engine.offered_kinds()
    except Exception:                      # noqa: BLE001 -- see docstring
        return list(_BUILTIN_KINDS)
    return list(kinds) or list(_BUILTIN_KINDS)


#: What an install with no offers file accepts. The ONLY place these four
#: names still appear in this module, and only as the degraded answer.
_BUILTIN_KINDS = ("fix", "feature", "research", "watch")


def parse_reply(text, kinds=None):
    """Returns (display_text, {mission?, goal?, chips?, remember?, module?}).
    Malformed json in a block drops THAT block (kept in display so nothing
    is lost) and never raises.

    `kinds` overrides which mission templates are acceptable; None asks the
    founder's Delegate offers. Resolved ONCE per reply rather than per block,
    so a reply carrying several fences cannot see the list change mid-parse.
    """
    out = {}
    allowed = list(kinds) if kinds is not None else offered_kinds()

    def _eat(match):
        kind, body = match.group(1), match.group(2)
        # Shadow v4 (ADR-043): the brief is PROSE, not json -- the task chat's
        # answer to "write the opening brief". Kept off the display and handed
        # back whole; shadow_task_chat.brief reads the same fence.
        if kind == "brief":
            text = body.strip()
            if not text:
                return match.group(0)
            out["brief"] = text
            return ""
        try:
            val = json.loads(body)
        except ValueError:
            return match.group(0)      # malformed: leave visible, honest
        # STRICT validation (deepseek fold): a block that does not meet its
        # shape stays VISIBLE in the reply -- an invalid instruction must
        # never become an invisible side effect.
        if kind == "mission" and isinstance(val, dict) \
                and val.get("objective") and val.get("template") in allowed:
            # Shadow v4 (C3, ADR-043): ONE REPLY MAY CARRY SEVERAL TASKS. The
            # Now chat splits one founder message into one fence per task;
            # every fence lands in `missions` (reply order) and `mission`
            # stays the FIRST one so every existing reader is unchanged.
            out.setdefault("missions", []).append(val)
            out.setdefault("mission", val)
        elif kind == "goal" and isinstance(val, dict) \
                and str(val.get("outcome") or "").strip():
            # An OUTCOME is the only hard requirement. done_when is kept
            # only when it is a list of usable check rows -- anything else
            # is dropped rather than coerced, so the card can say "Shadow
            # could not determine completion criteria" instead of showing
            # something Shadow did not actually mean.
            checks = []
            for c in (val.get("done_when") or []):
                if isinstance(c, dict) and str(c.get("check") or "").strip():
                    text = str(c["check"]).strip()[:300]
                    # THE PROBE TRAVELS WITH THE PROPOSAL (D-SH-1). Without
                    # it a `verify` row could never survive step 2 of the
                    # ladder, and the tier would be decided against evidence
                    # the caller was holding but never passed.
                    tier = tier_for(text, c.get("tier"), c.get("probe"))
                    row = {"tier": tier, "check": text}
                    if tier == "verify":
                        row["probe"] = c.get("probe")
                    if tier != c.get("tier"):
                        # what the card tells the founder, so a re-tier is
                        # visible rather than a silent correction
                        row["proposed_tier"] = c.get("tier") or None
                    checks.append(row)
            out["goal"] = {"outcome": str(val["outcome"]).strip()[:500],
                           "done_when": checks,
                           "target_session": val.get("target_session") or None}
        elif kind == "forward" and isinstance(val, dict) \
                and isinstance(val.get("worker"), bool):
            # THE FORWARDING VERDICT (founder, 2026-09-21). Shadow's own
            # judgement, on the turn it was already taking, about whether the
            # founder's line can change / constrain / authorize / clarify /
            # correct the worker's task. It rides HERE rather than on a
            # second model call so that the supervisory authority and the
            # forwarding authority cannot be two different opinions.
            #
            # STRICTLY A BOOLEAN, and the text is never read from the block.
            # What gets forwarded is the founder's own sentence, verbatim,
            # straight off the mission record -- so a Shadow that rewrites,
            # summarizes or invents an instruction here cannot put words in
            # the founder's mouth. Shadow decides WHETHER; the record decides
            # WHAT. See shadow_forward.classify.
            out["forward"] = {"worker": val["worker"]}
        elif kind == "chips" and isinstance(val, list) and val:
            out["chips"] = [str(c) for c in val][:3]
        elif kind == "remember" and isinstance(val, dict) \
                and val.get("text") and val.get("precedence") in \
                ("session", "project", "d_ledger", "taste", "history"):
            out["remember"] = val
        elif kind == "module" and isinstance(val, dict) \
                and isinstance(val.get("name"), str) and val.get("name").strip() \
                and (val.get("kind") or "chat") in _MODULE_KINDS:
            # D-M10 (2026-09-08): the app creates the module IMMEDIATELY as a
            # draft -- stronger than mission (brief_confirm) and remember
            # (unconfirmed). Deliberate: a draft module runs nothing until the
            # operator opens it, and archive is one click.
            out["module"] = val
        elif kind == "answer" and parse_answer(val) is not None:
            # v4.2: first fence wins, one line answers one ask
            out.setdefault("answer", parse_answer(val))
        elif kind == "limits" and parse_limits(val) is not None:
            # v4.1 (V4-7). FIRST FENCE WINS, like `mission`: one founder line
            # states one change, and a second fence must not quietly override
            # the first.
            out.setdefault("limits", parse_limits(val))
        else:
            return match.group(0)
        return ""

    display = _BLOCK.sub(_eat, text or "").strip()
    display = _strip_governance_noise(display)
    return display, out


_NOISE = re.compile(
    r"^(\[[A-Z][A-Z0-9·\-]*·[^\]]*\]"      # H-Sutra headers
    r"|(INPUT|TYPE|EXISTING HOME|ROUTE|FIT CHECK|ACTION|TASK|DEPTH"
    r"|EFFORT|COST|IMPACT|PLACEMENT|FLOW|TRIAGE|ESTIMATE|ACTUAL|OS):.*"
    r")\s*$", re.M)


def _strip_governance_noise(text):
    """Belt to SHADOW.md's braces: the user-scope CLAUDE.md trains the model
    to emit per-turn governance blocks in every workdir. The persona forbids
    them; anything that leaks is stripped line-wise so the founder reads an
    answer, not scaffolding."""
    lines = [l for l in (text or "").splitlines()
             if not _NOISE.match(l.strip())]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
