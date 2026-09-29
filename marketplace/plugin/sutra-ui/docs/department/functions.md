# The five functions

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop) |
| Code | `engine_defs/website.json` (`engines.Identity / Priority / Coordination / Adaptation / Audit`), `engine_runtime.py` (the step functions named below), `function-templates/<fn>/*.json` |

Every function is an engine on the board: it starts on a post addressed to it (`start.on: post`; Adaptation and Audit also on a checked `Live site` version). A function's steps run like any engine's (`run_engine`), on a rung its record has earned (`rung_of`), each step a row (`run_step`). On the screen the five are functions (`FUNCTIONS`).

## Identity

| Hears | Steps | What happens |
|---|---|---|
| a request from the owner, or from Root handed on | `identity.read` (code) → `identity.recognise` (model) → one of `identity.take` / `identity.answer` / `identity.rule` / `identity.weigh` (model, by `only_if` on the journey) → `identity.file` (code) | `recognise` names the journey: task, query, directive, feedback, new-idea (`p_identity_recognise`) |
| task | `identity.take` | returns `verdict` go / ask / refuse, `why`, `unsure` (facts the owner is not sure of), `rule` (a standing rule the words state, tag always / refuse / ask, or null), `thin` (`p_identity_take`) |
| query | `identity.answer` | answers from the record lines: the plan and the site for a website, version counts, what waits, and the latest text filed, last artifact first (`_record_lines`, `p_identity_answer`) |
| directive | `identity.rule` | restates the words as one rule with a tag (always / ask / refuse / goal) and a scope (standing / one-time) (`p_identity_rule`) |
| feedback | `identity.weigh` | names the page, what changes now, and a rule to carry forward if any (`p_identity_weigh`); the correction is filed to the line and marked against the step that made the page (`_mark`) |
| new-idea | (to Adaptation) | the words go to Adaptation as an idea (`identity_file` → `post(... word "idea")`) |
| a proposal from Adaptation (word engine) | `identity.engine` | puts the priced engine to the owner: "Add the engine X to Y? What it does: … Stamp to add it, Refuse to leave the idea parked." (`identity_engine`) |
| a finding from Audit | `identity.finding` | holes (places a page says "to be confirmed") become a facts question in the chat; when an engine with web tools of its own is on the record the holes are filed once as "Look up: …" for it (`identity_finding`, `_web_engine`, `d["looked_up"]`); other findings of high severity become an ask of kind `finding` |
| a stamp or a refusal | `identity.apply` | applies what was stamped by the ask's kind (`identity_apply`; see asks-and-rules.md) |

What `identity_file` does with the take's verdict: `go` files the words as the Brief (the goal when first) and tells "filed in the Brief"; `ask` puts an ask of kind `request` ("Your words reach outside the site…", `_reaches`); `refuse` tells why; a `rule` in the take's answer is put back as a rule ask before any of that (`_rule_ask`, "A rule, as understood: …"); `thin` first words get one question (birth.md). No branch names the internet: every agent step has the web tools (engines-and-library.md).

Identity's gates, run as blockers of other engines' starts (`blocked`):

| Gate | Code | Holds when |
|---|---|---|
| `identity.gate` | `identity_gate` | Publish, until the first publish ask is stamped (the ask carries where the site is served from, `host`; a refused one is skipped; a new goal asks again, `publish_asks_from`); Setup, until the setup ask is stamped |
| `identity.wait_engine` | `identity_wait_engine` | an ask of kind `engine` is pending in this department: every work engine waits; the owner is told once "The line waits for your stamp on X: nothing is built until the engine your words need is in place, or you refuse it." (`told` on the ask row); a Root is never held |

## Priority

- Gate `priority.envelope` (`priority_envelope`): an engine past its day's calls or USD is held and an ask of kind `envelope` is put up, escalated (`_today_spend`).
- `priority.read` → `priority.bargain` → `priority.post`: on a proposal from Adaptation it answers accept / reject; for an engine offer the prompt carries the engine, what it does, what it needs and what it costs (`_offer_lines`, `p_priority_bargain`); a refusal is told to the owner and the idea marked `priced: refused` (`adapt_priced`).
- The limits a department is born with come from Priority's template (`priority_template`: calls and USD a day per engine, `work_calls` times for a work engine); the owner sets one engine's limits on Priority's Settings tab (`/{ref}/envelope`).

## Coordination

- Rules on the code rung (`engine_defs`, `rules`): `coord.busy` (one run at a time), `coord.pick` (who goes first: the table's order posts / line / functions; inside the line, while an engine is held the ones after it wait), `coord.edge`, `coord.verdict` (asks a function to judge a gate that is not on the code rung), `coord.bounds`, `coord.alarm` (a run past its window).
- Gate `coord.chain`: a chain of runs from one owner's ask stops at `CHAIN_LIMIT` (12) (`_chain_of`).
- Steps `coord.ready`, `coord.tie` (a model call only when two are equally ready and the read is not a peek), `coord.record`; the table lives on the record (`coordination.json`) and `grow_line` adds an engine to it.

## Adaptation

- On a checked Live site: `adapt.sense` → `adapt.ladder` → `adapt.act`: proposes a step's move up the ladder to Priority and, granted, to the owner as an ask of kind `rung`.
- On an idea from Identity: `adapt.hear` (code) → `adapt.shape` (model: the idea reflected back in shapes, a Library engine picked if one fits, else an engine shaped with a name, what it does and what it needs, `p_adapt_shape`) → `adapt.park` (the idea on `ideas.json`) → `adapt.offer` (the engine to Priority, `engine_from_shape`) → `adapt.priced` (to Identity, or the refusal told).

## Audit

- On a checked Live site, sampled (versions 1-3 and every third, `audit_pick`): `audit_mechanical` (code: every version has its run and check; the site traces back to the owner's words; the holes, `placeholders()`, which skips nav, header, footer and link text) → `audit.judge` (model: facts on the pages that neither the Brief nor what the department's own engines filed gives, `p_audit_judge` with `_context_block`) → `audit_file` (a finding to Identity).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine_defs/website.json; engine_runtime.py: identity_file, identity_apply, identity_engine, identity_finding, identity_gate, identity_wait_engine, p_identity_*, priority_*, coord_*, adapt_*, audit_*], review: none by a second model, confidence: high}
