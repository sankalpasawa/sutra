# ABS-2 as built

`connectors/egress.py`: shape table (13 shapes ported from the old scrubber, PEM body bounded to 20 000 characters so a long text cannot go quadratic), `Egress.check(text, session, provider, replace)`, append-only 0600 `<data>/connectors/egress.jsonl` (time, session, provider, mode, bytes, shape counts; never a match).
Hooks in `Router` (`router.egress`, None by default; the factory sets it for live routers, not for the offline/stub router so the demo is unchanged): `_ask` = engine path, observe only; `call_json` = orchestrator path, replace; `_chat_turn` = chat prompt including the carry-over, replace.
Known secret VALUES (`Redactor`) are supported through the optional `redactor` argument; the factory does not pass one (connectors must not import the orchestrator). Wiring one in is ABS-8.
