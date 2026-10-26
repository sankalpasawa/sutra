"""owner_words.py -- the bargain in the owner's words, for every read a screen prints (PRD M1.7; the screen word rules).

The record keeps its own words, the inside ones: a handler's name ('Priority granted the line'), a step's name ('Grant,
refuse or counter'), a function's goal ('grants each engine its envelope'), a run's line ('granted the line Plan ->
Write'), the ledger's default summaries ('Refused.') and what Identity tells the owner ('Root's check refused the
plan'). The owner's ruling is that the screen says said yes, asked for less and said no, never grant, counter or refuse.
So every read a function's pane prints passes its words through here on the way out: functions_view's five and each
function's page, and website_api's /steps, /map, /status and /engine reads, which feed the cards under the page (the
steps, gates, Moves, Stamped by rule, Runs). Nothing here writes: the record keeps its words, the screen gets the
owner's.

Phrases only, longest first, so a sentence keeps its grammar, and never a bare verb: the owner's own words (the goal,
done-when, the rules, the requests) are never passed through here, and a rule's tag (go, ask, refuse, always) is the
owner's own word for a rule and is left as it is.
"""

# The bargain in the owner's words wherever a definition's name, a run's line or a ledger row's summary carries the inside
# word. A step's name, the default summaries j2_runtime writes (J.on_post, J.refused, the owner's answer), the lines the
# functions' runs say (engine_runtime's priority_answer, adapt_*, identity_*), what Identity tells the owner (_j2_settle,
# identity_closed, identity_drop), the text of the ask it puts to the owner and a step's check notes all pass through
# here. Phrases first, longest first, then the plain verbs.
BARGAIN_WORDS = (("Send the granted line to Root's check", "Send the line Priority said yes to, to Root's check"),
                 ("Take the refusal to Identity", "Take Priority's no to Identity"),
                 ("Take the counter, or take it to Identity", "Take Priority's ask for less, or take it to Identity"),
                 ("Grant, refuse or counter", "Say yes, ask for less, or say no"),
                 ("grants each engine its envelope", "gives each engine its limit"),
                 ("granted an envelope to each engine", "gave each engine its limit"),
                 ("Granted within the envelope.", "Said yes within the limit."),
                 # Root's check, and what Identity tells the owner of it (round 2, gap 4): a plan sent back, never refused
                 ("Root's check refused the workflow", "Root's check sent the plan back"),
                 ("Root's check refused the plan", "Root's check sent the plan back"),
                 ("Root's check refused it", "Root's check sent it back"),
                 ("waits for the workflow to be granted and registered", "waits for Priority's yes and Root's check"),
                 ("passed, asked or refused", "passed, asked or stopped"),
                 # the conflict Identity puts to the owner, and the owner's no (identity_closed, identity_drop)
                 (", Refuse to drop it.", ", or say no to drop it."),
                 ("Priority did not grant", "Priority did not say yes to"), ("did not grant", "did not say yes to"),
                 ("on your refusal", "because you said no"), ("on the owner's refusal", "because the owner said no"),
                 ("your refusal", "your no"),
                 ("Take a refusal", "Take a no"), ("Drop what was refused", "Drop what was turned down"),
                 ("Hear a refusal", "Hear a no"), ("Note the refusal", "Note the no"),
                 ("The owner refused it.", "The owner said no."), ("refused by the owner", "turned down by the owner"),
                 ("the owner's refusal", "the owner's no"),
                 ("took Priority's counter", "took Priority's ask for less"), ("take Priority's counter", "take Priority's ask for less"),
                 ("Priority's counter", "Priority's ask for less"), ("Priority's refusal", "Priority's no"),
                 ("Priority's grant's stamp", "Priority's yes"), ("Priority's grant", "Priority's yes"),
                 ("Priority granted", "Priority said yes to"), ("Priority refused", "Priority said no to"),
                 ("Priority countered (", "Priority asked for less ("), ("Priority countered", "Priority asked for less on"),
                 ("countered the line", "asked for less on the line"), ("granted the line", "said yes to the line"),
                 ("refused the line", "said no to the line"), ("granted a trial", "said yes to a trial"),
                 ("refused a trial", "said no to a trial"), ("refused the ask", "said no to the ask"), ("refused: ", "said no: "),
                 ("a stamp or a refusal", "a stamp or a no"), ("or a refusal", "or a no"),
                 # what a step's check said, on its card: a decision's words, never the bargain's inside ones
                 ("the answer is accept, reject or counter", "the answer is say yes, ask for less or say no"),
                 ("the verdict is one of admit, wait, refuse", "the verdict is let through, wait or stop"),
                 ("the verdict is one of go, ask, refuse", "the verdict is go, ask or stop"),
                 ("Countered.", "Asked for less."), ("Refused.", "Said no."))


def plain(line):
    """One line in the owner's words; '' for nothing."""
    line = str(line or "")
    for inside, said in BARGAIN_WORDS:
        line = line.replace(inside, said)
    return line


def _keep(value):
    """A line that is there stays a line, said plainly; a missing one stays missing (None is not '')."""
    return plain(value) if isinstance(value, str) else value


def runs(rows):
    """Run rows as a screen prints them: each one's line ('what') in the owner's words, the rest as the record keeps it."""
    return [dict(r, what=_keep(r.get("what"))) if isinstance(r, dict) else r for r in rows or []]


def steps(view):
    """An engine or a function as its steps (engine_runtime.steps_view), as its card prints it: the description, each
    step's name, the handler it sits under, its last check notes and who moved its rung, what it hears, and the names
    of the steps that hold its start, in the owner's words. Ids, rungs, checks and numbers are left as they are."""
    if not view:
        return view
    out = dict(view, description=_keep(view.get("description")), hears=[plain(h) for h in view.get("hears") or []])
    rows = []
    for s in view.get("steps") or []:
        s = dict(s, name=_keep(s.get("name")), under=_keep(s.get("under")))
        if isinstance(s.get("last"), dict):
            s["last"] = dict(s["last"], notes=[plain(x) for x in s["last"].get("notes") or []] or s["last"].get("notes"))
        s["history"] = [dict(h, by=_keep(h.get("by"))) for h in s.get("history") or []]
        rows.append(s)
    out["steps"] = rows
    start = view.get("start")
    if isinstance(start, dict):
        out["start"] = dict(start, on=[plain(x) for x in start.get("on") or []],
                            unless=[dict(u, name=_keep(u.get("name"))) for u in start.get("unless") or []])
    return out


def status(view):
    """The department's status read (website_dept.status): what runs now, in the owner's words."""
    if not view:
        return view
    return dict(view, running=runs(view.get("running")))


def engine(view):
    """One engine's card (website_dept.engine_view): its runs' lines, and its last one's, in the owner's words."""
    if not view:
        return view
    out = dict(view)
    if "runs" in out:
        out["runs"] = runs(out["runs"])
    if isinstance(out.get("last"), dict):
        out["last"] = dict(out["last"], what=_keep(out["last"].get("what")))
    return out


def map_view(view):
    """The department's map read (website_dept.map_view), as the Map and the function cards print it: the last line of
    each function and engine, the recent runs (Identity's 'Stamped by rule'), what runs now and the day's timeline, in
    the owner's words. The goal, done-when, rules and the owner's requests are the owner's own words and stay."""
    if not view:
        return view
    out = dict(view)
    out["systems"] = [dict(s, last=_keep(s.get("last"))) for s in view.get("systems") or []]
    out["engines"] = [engine(e) for e in view.get("engines") or []]
    out["recent"] = runs(view.get("recent"))
    out["status"] = status(view.get("status"))
    health = view.get("health")
    if isinstance(health, dict):
        out["health"] = dict(health, timeline=runs(health.get("timeline")))
    return out
