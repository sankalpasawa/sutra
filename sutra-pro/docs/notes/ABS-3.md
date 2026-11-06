# ABS-3 as built

`connectors/budget.py`: table `WINDOWS`/`DEFAULT_WINDOWS`, `window_for` (source `known`, `provider-default` or `assumed-floor`), `for_target`, `fits`, `estimate_tokens`, `carry_chars`.
Riders: `transcript.render_carry_over(..., budget=None)` only lowers `full_chars` and `digest_cap` (None = J2 exactly); `Router._new_session` passes the budget of the new provider's model (a one-line rider beyond the spec's list, needed for the budget to take effect).
DeepSeek rows of the old table are not ported (D7, D112). With the shipped windows the J2 caps bind for every known model; the budget bites only for a model that declares a window under about 68 000 tokens.
