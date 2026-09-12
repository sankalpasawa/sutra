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

#: Context windows in TOKENS, keyed by provider and then by the model ids that
#: provider declares in providers.py. Kept here rather than in providers.py
#: deliberately: providers.py probes PATH and config directories on every call,
#: and context arithmetic has no business behind that.
#: test_budget.test_every_catalogued_model_has_a_window pins the two together so
#: a new picker entry cannot silently inherit a wrong ceiling.
#:
#: Sources: the bundled claude-api model table (cached 2026-06-24) for the
#: Claude family; a live GET /models against DeepSeek on 2026-09-02 for the V4
#: family, which reported deepseek-v4-flash / -pro / -flash-vision-exp, all 1M.
WINDOWS = {
    "claude": {
        "opus": 1000000,
        "sonnet": 1000000,
        "haiku": 200000,     # Haiku 4.5. Five times smaller than its siblings.
    },
    "deepseek": {
        "deepseek-v4-pro": 1000000,
        "deepseek-v4-flash": 1000000,
        "deepseek-v4-flash-vision-exp": 1000000,
    },
}

#: What `""` -- "let the CLI choose" -- resolves to, PER PROVIDER. This entry is
#: the whole reason the table above could be keyed by model without breaking
#: anything, and it is not an optimisation.
#:
#: Before models were per-provider, window_for("deepseek", ...) ignored the model
#: and returned a flat 1M. Keying by model without declaring a default would have
#: sent DeepSeek's "" -- which is the SHIPPED default, what every session runs on
#: until someone picks something -- down the unknown-model path to FLOOR_WINDOW,
#: quietly costing 800K tokens of ceiling on the switch and compaction paths. A
#: five-fold under-count that nothing would have reported.
#:
#: Claude has no entry ON PURPOSE, and that asymmetry is the point: `claude` with
#: no model selected genuinely resolves to something this panel cannot know (the
#: CLI's own configured default, which the operator may have changed), so the
#: floor is the honest answer there. DeepSeek's default IS knowable -- the fork's
#: ACP session/new reports deepseek-v4-flash, measured 2026-09-07 -- so assuming
#: the floor for it would be pessimism, not caution.
#:
#: codex ADDED 2026-09-09, and the number is 258,400 rather than the 272,000
#: raw window because that is what codex ENFORCES. Two independent sources
#: agree, both codex's own:
#:
#:   $CODEX_HOME/models_cache.json   context_window 272000 and
#:                                   effective_context_window_percent 95, for
#:                                   every visible model -> 258,400
#:   the session rollouts            model_context_window: 258400, on 70
#:                                   observations across every real rollout on
#:                                   this machine, from task_started and
#:                                   token_count alike
#:
#: WHY THIS IS MEASUREMENT AND NOT A GUESS, which is the bar DeepSeek's entry
#: had to clear too. The worry that kept codex out of this table was that ""
#: resolves to a SERVER-SIDE default that can change under us, so the panel
#: cannot know which model will answer. That is still true and no longer
#: matters: all three models codex offers this account declare the SAME
#: effective window, so the default resolves to 258,400 whichever one it picks.
#: Claude stays exempt because its "" genuinely varies -- opus and sonnet hold
#: 1M where haiku holds 200K, a five-fold spread the panel cannot resolve.
#:
#: NOT keyed per model, deliberately. codex's roster is DISCOVERED per account
#: (codex_models.cached() is None until something refreshes it), so a
#: WINDOWS["codex"] table would claim windows for ids that models_for("codex")
#: does not offer in a fresh process -- which
#: test_no_provider_declares_a_window_for_a_model_it_does_not_offer catches --
#: and would go stale silently the day OpenAI ships a fourth model. One default
#: is the honest shape while every model agrees; the moment one does not,
#: test_codex_models_all_declare_one_effective_window fails and says so.
#:
#: IT DID, 2026-09-12: gpt-5.3-codex-spark appeared at 128,000 x 95% = 121,600
#: beside gpt-5.5's 258,400. Still no static table -- window_for asks
#: codex_models.window_for(model) for the figure the roster itself declares
#: (model/list first, codex's own cache file last), and this default is what
#: "" and an unlisted id fall back to. The canary is now
#: test_every_visible_codex_model_resolves_to_its_own_declared_window: every
#: window codex's cache declares is the window window_for returns for it.
DEFAULT_WINDOWS = {
    "deepseek": 1000000,
    "codex": 258400,
}

#: Used whenever the selected model does not resolve to a declared window AND the
#: provider declares no default. The smallest window in the catalogue, on
#: purpose -- see unknown (1).
FLOOR_WINDOW = min(w for windows in WINDOWS.values() for w in windows.values())

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

    `model` is the stored model id for THAT TARGET, read from settings when not
    passed. It is meaningful for every provider that has a picker now, not just
    Claude -- DeepSeek's model used to be chosen inside the CLI and was ignored
    here; it is chosen by Sutra as of the per-provider picker, so it selects a
    window like Claude's does.

    Three outcomes, and `source` says which:
      declared          the provider declares a window for this exact model
      provider-default  no model selected (or an unrecognised one) and the
                        provider knows what its own default resolves to
      assumed-floor     neither -- the smallest catalogued window, so a payload
                        is under-sized rather than rejected at the API
    """
    if model is None:
        try:
            # THIS target's stored model, not a shared one. Reading the single
            # global scalar here meant a Claude id could be read while sizing a
            # DeepSeek payload; harmless only because the deepseek arm below
            # ignores the model entirely. Phase 4 makes the windows model-keyed,
            # at which point reading the wrong provider's id would pick the
            # wrong window -- so it is corrected before that lands, not with it.
            model = providers.stored_model(target) or ""
        except Exception:
            model = ""
    model = (model or "").strip()

    if target == "codex":
        # PER MODEL, FROM THE DISCOVERED ROSTER -- never a static table (see
        # the DEFAULT_WINDOWS note). A selected model the roster lists with a
        # window is `declared`; "" resolves to the discovered default's window
        # when the roster marks one; anything else keeps the provider default
        # below. The import is deferred the way providers defers it: cheap
        # after the first call, and no cycle at import time.
        import codex_models
        win = codex_models.window_for(model) if model else None
        if win:
            return {"tokens": win, "source": "declared", "model": model}
        if not model:
            win = codex_models.window_for(codex_models.default_id())
            if win:
                return {"tokens": win, "source": "provider-default",
                        "model": model}

    win = WINDOWS.get(target, {}).get(model)
    if win:
        return {"tokens": win, "source": "declared", "model": model}
    # "" (CLI default), an id this build has not been taught, or another
    # provider's id arriving on this path. A provider that KNOWS what its own
    # default resolves to declares it; the rest fall to the floor.
    fallback = DEFAULT_WINDOWS.get(target)
    if fallback:
        return {"tokens": fallback, "source": "provider-default", "model": model}
    # An unknown target, or a known one with nothing we can honestly claim.
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
    if win["source"] == "provider-default":
        return ("no model is selected, so this assistant's own default "
                "(%d tokens) is used -- it is a known model, not a guess."
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
