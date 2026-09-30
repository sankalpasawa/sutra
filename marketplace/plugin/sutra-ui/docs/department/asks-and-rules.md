# Asks and rules

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `website_dept.py` (`_put_ask`, `asks`, `decide_ask`, `/{ref}/asks/{aid}`), `engine_runtime.py` (`identity_gate`, `identity_file`, `_rule_ask`, `identity_engine`, `identity_finding`, `identity_rung`, `priority_envelope`, `on_stamp`, `identity_apply`, `check_rules_of`, `p_check_rules`, `check_build`) |

## Every ask

An ask is a row on `asks.json` (`_put_ask`: id, kind, engine, slot, text, status pending / stamped / refused, created, thread). The screen shows pending asks under "Waiting for you" with Stamp and Refuse; a decision posts `accept-proposal` or `reject-proposal` in the ask's own thread (`on_stamp`), and Identity applies it (`identity_apply`).

| Kind | Put by | Text | A stamp | A refusal |
|---|---|---|---|---|
| setup | Root's Identity, gate on Setup (`identity_gate`) | "Set up a department for: <first sentence, ≤120 chars>" | Setup runs: the department is shaped and born | the request is skipped |
| publish | Identity, gate on Publish (`identity_gate`) | "Publish: go live for the first time, served from <host> unless you say where else" | Publish runs; the host stays on the record; later publishes ask no more until a new goal (`publish_asks_from`) | the build is skipped, never live |
| request | Identity's take, verdict ask (`identity_file`) | "Your words reach outside the site<: why>. Put them on the site as said? Stamp to go ahead, Refuse to leave them out. <words>" | the words are filed as a Brief version ("the owner's ask, stamped", `_file_brief`) | left out |
| rule | Identity's take (`rule` in its answer) or the directive journey (`_rule_ask`) | "A rule, as understood: <line>" (a directive: "A new goal, as understood" when tagged goal) | the rule is written onto `d["rules"]` with its tag and the words it came from; a goal-tagged one replaces the goal and makes the next publish ask again; the Brief gets a line "A rule, from now on: …" | nothing kept |
| engine | Identity on Adaptation's priced offer (`identity_engine`) | "Add the engine X to Y? What it does: … Stamp to add it, Refuse to leave the idea parked." | `W.add_engine`: the engine on the record and in the line, born into the Library when shaped (engines-and-library.md) | the idea stays parked |
| finding | Identity on a high-severity Audit finding (`identity_finding`) | "Audit found: <where, what>. Stamp to have it put right." | a Brief line "Correct this: …" sends it to the line | nothing |
| rung | Identity on Adaptation's granted proposal (`identity_rung`) | "Move “<step>” from <rung> to <rung>" | the step's ladder moves (`move`) | nothing |
| envelope | Priority's gate (`priority_envelope`) | "<engine> is out of today's envelope" (escalated) | the engine goes on | held |

Words the take marks `thin`, and holes Audit found, are questions in the chat, not asks (birth.md, functions.md). A directive the owner means once ("just this once", `scope: one-time`) is applied once and not kept.

## Rules on the record

- Born rules come from the kind (`kinds.<kind>.rules`, birth.md); stamped rules are added with an id, a tag (always / refuse / ask), the line and the words (`identity_apply`, kind rule). A rule already on the record is said back, not added twice.
- The rules are shown to every agent step (`card()` names them) and to Identity's take ("THE RULES").
- `check.rules_of` (code) lists the stamped rules that apply to the pages; `check.rules` (model, only when there are any) reads each page against them and names what breaks which rule (`p_check_rules`, `c_rules_are_listed`); `check_build` files the Build failed when a rule is broken, and the line sends the build back with the finding, twice at most, then the owner is told (`_send_back`).
- A Root's child's rules can only tighten the Root's (a Root rule at birth; `identity_apply` applies Identity's own check "set its rules within the parent's" at birth).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [website_dept.py: _put_ask, decide_ask; engine_runtime.py: identity_gate, identity_file, _rule_ask, identity_engine, identity_finding, identity_rung, priority_envelope, on_stamp, identity_apply, check_rules_of, p_check_rules, check_build, _send_back], review: none by a second model, confidence: high}
