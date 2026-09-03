"""budget.py -- how many characters of recording will fit, for THIS model.

THE CEILING IS PER-MODEL, NOT PER-PROVIDER, and that distinction is the whole
reason this module exists. "Claude's window" is not a number: Opus 5 and
Sonnet 5 hold 1M tokens and Haiku 4.5 holds 200K, and the panel offers haiku
in its model picker (providers.py:374). A budget keyed on the provider would be
five times too generous the moment an operator selects haiku, and the failure
would land at the API as a rejected request after the payload had already been
built and sent.

TWO UNKNOWNS, AND WHICH WAY EACH ONE FAILS SAFE

1. The window when no model is selected. providers.MODELS ships "" -- "CLI
   default", whatever `claude` is configured to use -- as a real, selectable
   option, and nothing on this machine can tell us which model that resolves
   to. Assuming the largest window risks an overrun, which is a HARD failure:
   the request is rejected and the operator gets no switch at all. Assuming
   the smallest risks an unnecessary tier-2, which is a DEGRADED SUCCESS: the
   switch happens, tool I/O is left on disk for the target to read itself, and
   the prompt says so. Degraded success beats hard failure, so the floor wins
   -- and `window_source` says "assumed-floor" so the operator can see why
   their large chat shed tool output and fix it by naming a model.

2. Characters to tokens. Neither provider's tokenizer is available here, so
   this is an estimate and is labelled one. The usual 4 chars/token is a PROSE
   figure; this payload is 79.8% tool I/O by volume (transcript_ir.stats over
   24 real transcripts), and code and JSON tokenize denser than prose. So the
   divisor is 3.0, which OVERSTATES the token count for prose-heavy chats. The
   asymmetry is deliberate for the same reason as (1): overstating costs a
   needless tier-2, understating costs a rejected request.

WHAT IS RESERVED, AND WHY IT IS NOT max_tokens
The window holds the input AND the reply. Reserving the models' full output
ceilings (128K for the current Claude family, 384K for DeepSeek V4) would give
up a third of a 1M window to a reply that will not be that long. The reserve
here is a practical answer length plus room for the turns that follow the
switch -- because the replay is not the last thing in the session, it is the
FIRST thing, and turns 52, 53, 54 have to fit after it.

Reads:  providers (the model catalogue and the stored model), nothing else.
Writes: nothing.
"""
import providers

#: Context windows in TOKENS, keyed by the model ids providers.MODELS uses.
#: Kept here rather than in providers.py deliberately: providers.py probes PATH
#: and config directories on every call, and context arithmetic has no business
#: behind that. test_budget.test_every_catalogued_model_has_a_window pins the
#: two together so a new picker entry cannot silently inherit a wrong ceiling.
#:
#: Sources: the bundled claude-api model table (cached 2026-06-24) for the
#: Claude family; a live GET /models against DeepSeek on 2026-09-02 for the V4
#: family, which reported deepseek-v4-flash / -pro / -flash-vision-exp, all 1M.
CLAUDE_WINDOWS = {
    "opus": 1000000,
    "sonnet": 1000000,
    "haiku": 200000,     # Haiku 4.5. Five times smaller than its siblings.
}

#: Every current DeepSeek model is 1M, so there is nothing to key on yet. When
#: the panel gains a DeepSeek model picker this becomes a dict like the above.
DEEPSEEK_WINDOW = 1000000

#: Used whenever the selected model does not resolve to a declared window.
#: The smallest window in the catalogue, on purpose -- see unknown (1).
FLOOR_WINDOW = min(CLAUDE_WINDOWS.values())

#: Deliberately below the prose figure of ~4. See unknown (2).
CHARS_PER_TOKEN = 3.0

#: Room for the answer to the seeded turn, plus the turns after it. Not the
#: model's max output -- see the module header.
REPLY_RESERVE_TOKENS = 32000

#: What is left after the reply reserve is further discounted, because the
#: token estimate is an estimate. Without this, a payload measured at exactly
#: the ceiling would be sent at the ceiling, and a 3% estimation error becomes
#: a rejected request.
USABLE_FRACTION = 0.90


def window_for(target, model=None):
    """{tokens, source, model} for the model a switch to `target` will run on.

    `model` is the panel's stored model id ("", "opus", "sonnet", "haiku"),
    read from settings when not passed. It is meaningful for Claude only --
    DeepSeek's model is chosen inside the CLI, not by Sutra -- so it is ignored
    for other targets rather than being allowed to pick a wrong window.
    """
    if model is None:
        try:
            model = providers.stored_model() or ""
        except Exception:
            model = ""
    model = (model or "").strip()

    if target == "deepseek":
        return {"tokens": DEEPSEEK_WINDOW, "source": "declared", "model": model}
    if target == "claude":
        win = CLAUDE_WINDOWS.get(model)
        if win:
            return {"tokens": win, "source": "declared", "model": model}
        # "" (CLI default) or an id this build has not been taught.
        return {"tokens": FLOOR_WINDOW, "source": "assumed-floor", "model": model}
    # An unknown target has no window we can honestly claim.
    return {"tokens": FLOOR_WINDOW, "source": "assumed-floor", "model": model}


def for_target(target, model=None):
    """The character ceiling for a replay payload, with its full derivation.

    Every intermediate value is returned rather than folded into one number,
    because when a switch sheds tool output or refuses outright, the operator's
    next question is "why", and the answer is one of these fields.
    """
    win = window_for(target, model)
    usable_tokens = int(max(win["tokens"] - REPLY_RESERVE_TOKENS, 0)
                        * USABLE_FRACTION)
    return {
        "target": target,
        "model": win["model"],
        "window_tokens": win["tokens"],
        "window_source": win["source"],
        "reply_reserve_tokens": REPLY_RESERVE_TOKENS,
        "usable_fraction": USABLE_FRACTION,
        "usable_tokens": usable_tokens,
        "chars_per_token": CHARS_PER_TOKEN,
        "budget_chars": int(usable_tokens * CHARS_PER_TOKEN),
        "estimate": True,   # no tokenizer is in the loop; say so
        "note": _note(win),
    }


def _note(win):
    if win["source"] == "assumed-floor":
        return ("no model is selected, so the smallest catalogued window "
                "(%d tokens) is assumed rather than risking a rejected "
                "request. Selecting a model in Settings raises this."
                % win["tokens"])
    return ("%s holds %d tokens" % (win["model"] or win.get("target") or "the model",
                                    win["tokens"]))


def estimate_tokens(chars):
    """Tokens a payload of `chars` characters is assumed to occupy.

    Rounded UP: a budget check that rounds down can pass a payload that does
    not fit.
    """
    if chars <= 0:
        return 0
    return int(-(-int(chars) // int(CHARS_PER_TOKEN)))


def fits(chars, budget=None, target=None, model=None):
    """Whether a payload fits, and by how much.

    Accepts a precomputed `budget` (so a caller that already has one does not
    recompute it) or derives one from target/model.
    """
    b = budget or for_target(target, model)
    return {
        "fits": chars <= b["budget_chars"],
        "chars": chars,
        "budget_chars": b["budget_chars"],
        "headroom_chars": b["budget_chars"] - chars,
        "est_tokens": estimate_tokens(chars),
        "window_tokens": b["window_tokens"],
        "window_source": b["window_source"],
    }
