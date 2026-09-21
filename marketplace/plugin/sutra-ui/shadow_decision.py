"""THE DECISION PACKET. A question the founder can answer without leaving it.

THE FAILURE THIS CLOSES (founder, 2026-09-21). A task was "make a 10 line
list of the greatest MotoGP riders ever and put it in some doc". Shadow
verified what it could and then asked:

    "Does this ten-line ranking work as the greatest premier-class riders
     ever?"

That is a correct question to ask a human -- a ranking of greatness is taste,
it is exactly what `is_founder_only` is for, and no probe will ever settle
it. It is also UNANSWERABLE AS PRESENTED, because the ten riders existed only
in the worker's chat. The founder was asked to approve a list they could not
see. To answer they had to open another chat, find the message, read the
list, come back and press a button.

THE RULE THIS ESTABLISHES. Every founder confirmation must be SELF-CONTAINED.
When Shadow puts a decision to a human, the surface carrying that decision
must also carry the minimum evidence needed to make it. The worker chat stays
available as the full transcript; it stops being a REQUIRED stop on the way
to answering a question Shadow asked.

WHY THIS IS NOT A SECOND VERIFICATION LANE, and the distinction is the whole
design. D-SH-1 and the artifact lane decide WHO ANSWERS a criterion, by the
nature of the criterion: mechanically decidable goes to a probe or the judge,
taste and founder-held facts go to the founder. That ladder is untouched and
nothing here can move a check between tiers. This module answers the question
that comes AFTER the ladder has already routed a check to a human: given that
this one is genuinely theirs, what do they need in front of them to decide
it? So the two compose -- the ladder narrows what is asked, and this makes
what is left answerable.

NOTHING HERE IS PER TASK TYPE (founder, 2026-09-21: "build the confirmation
policy around the nature of the criterion"). There is no branch on ranking,
on file, on research, on MotoGP. The packet is assembled from the paths THIS
MISSION OWNS -- the ones its own probes name, or ones explicitly recorded on
its record -- and from the probe results already computed. A
ranking, a report, a config and a generated dataset all reach the founder by
the identical code path, because to this module they are all "the files the
work produced".

THE TRANSCRIPT IS NOT A SOURCE, and that exclusion is inherited rather than
re-argued. shadow_evidence reads FILES; it has no transcript parameter and
cannot acquire one without failing shadow_judge's signature test. So the
founder's decision surface cannot carry worker reasoning, control-plane
text, prompts, tool traces or unrelated conversation -- not because this
module filters them out, but because it is built on a reader that never had
access to them. That is the strong form of "do not expose irrelevant worker
reasoning": there is no code path from the worker's words to here.

MISSION ISOLATION IS AN INVARIANT (founder, 2026-09-21). A packet may carry
only what its own mission owns. It used to add every untracked file git
reported, which in a shared workdir is every file every previous mission left
behind -- a Europe trip mission's decision surface showed `marc-marquez.txt`
and `motogp-top-10-news.md`. Discovery is not ownership; see
shadow_paths.owned_artifacts, which is now the only source.

THE FIVE PARTS, as the founder specified them, and where each lives:

  1. the exact decision being asked        -> asks[].check, verbatim
  2. the minimum relevant evidence         -> artifacts[]
  3. the machine facts already established -> established[] + artifacts[].facts
  4. the boundary needing human judgement  -> asks[], which is ONLY the
                                              unmet founder_confirm rows
  5. any material caveat                   -> artifacts[].truncated, missing

NOTHING HERE DECIDES ANYTHING. The packet is read-only evidence attached to a
paused mission. It cannot satisfy a check, cannot move a tier, cannot write
`met`, and cannot change what the worker may do. MissionStore.confirm_check
remains the only writer of a founder_confirm `met` flag.
"""

import base64
import os
import time

#: How many artifacts one decision may carry. A founder deciding one question
#: needs the thing the question is about, not the workspace; the cap is lower
#: than shadow_evidence's own because this is a DECISION surface rather than
#: a judge's evidence blob, and a wall of files is the thing that made the
#: original question unanswerable.
MAX_ARTIFACTS = 4

#: Characters of text quoted per artifact. Generous enough that the shapes
#: this exists for -- a ten-line ranking, a short report, a config, a list --
#: arrive WHOLE, which is the point: an excerpt of a ranking is not a ranking.
MAX_TEXT = 12000

#: ...and the whole packet, so several artifacts cannot sum past what a
#: founder will read or what a mission record should carry.
MAX_TOTAL_TEXT = 24000

#: A visual artifact is INLINED as a data URI rather than referenced, because
#: this app serves no workspace files and a path the founder cannot open is
#: not a preview -- it is the missing ranking in a different costume. Tight
#: bounds: this rides in the mission record, which is json on disk and on the
#: wire.
MAX_IMAGE_BYTES = 192 * 1024
MAX_IMAGES = 2

#: Extensions read as visual. A SHORT, EXPLICIT list -- anything not named
#: here is treated as text or skipped, so a new binary format cannot become
#: an inlined blob by accident.
IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}

#: How many established facts to carry. The founder is being asked ONE
#: question; the settled rows are context for it, not a report.
MAX_ESTABLISHED = 8


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def open_asks(mission):
    """The rows this mission is actually waiting on a human for.

    ONLY UNMET `founder_confirm`, which is part 4 of the packet: the precise
    boundary that still requires human judgement. A row Shadow settled is
    not a question, and listing it here would re-ask something already
    answered -- the exact noise the UI fold exists to remove.

    The INDEX is the record's own, because confirm_check is by index and a
    re-numbered one would sign the wrong row.
    """
    out = []
    for i, c in enumerate((mission or {}).get("done_when") or []):
        if not isinstance(c, dict):
            continue
        if c.get("tier") == "founder_confirm" and not c.get("met") \
                and str(c.get("check") or "").strip():
            out.append({"index": i, "check": str(c["check"]).strip()})
    return out


def established_for(mission, root):
    """What Shadow has ALREADY settled, as facts rather than claims.

    PART 3 OF THE PACKET, and it is here for a reason about the decision
    rather than about completeness: a founder asked "is this ranking any
    good" decides differently if they also know the file has exactly ten
    lines, all distinct, no headings. Those are not the question -- they are
    the ground the question stands on, and without them the founder
    re-checks by hand what the machine already knows.

    Read from the row's own tier and probes, never from anything the worker
    said. A probe is RE-RUN here rather than trusted from a cached flag,
    because the packet is built at the moment of asking and the founder is
    entitled to the state of the world at that moment.
    """
    try:
        import shadow_probe
        import mission_engine
    except Exception:                    # noqa: BLE001 -- no facts, not fatal
        return []
    out = []
    for c in ((mission or {}).get("done_when") or []):
        if not isinstance(c, dict) or not str(c.get("check") or "").strip():
            continue
        if c.get("tier") == "founder_confirm":
            continue                     # a question, not an established fact
        try:
            probes = mission_engine.probes_of(c)
        except Exception:                # noqa: BLE001
            probes = []
        for p in probes:
            try:
                res = shadow_probe.run(p, root)
            except Exception:            # noqa: BLE001 -- skip, never raise
                continue
            out.append({"check": str(c["check"]).strip(),
                        "met": bool(res.met),
                        "how": str(res.reason or "")[:200]})
            if len(out) >= MAX_ESTABLISHED:
                return out
        if not probes and c.get("met"):
            # a judge row that passed: the verdict IS the established fact,
            # and its reason is the judge's own one-line citation
            judged = c.get("judged") or {}
            out.append({"check": str(c["check"]).strip(), "met": True,
                        "how": str(judged.get("reason")
                                   or "Shadow read the change and confirmed "
                                      "it")[:200]})
            if len(out) >= MAX_ESTABLISHED:
                return out
    return out


def _image(root, path):
    """One visual artifact as a data URI, or None.

    INLINED, NOT REFERENCED -- see MAX_IMAGE_BYTES. An image over the ceiling
    is reported as present-but-too-large rather than dropped, because
    "there is a screenshot and it is 4 MB" is a fact the founder can act on
    and silence is not.

    Confinement is shadow_probe.resolve, the same one comparison every other
    read in Shadow goes through.
    """
    mime = IMAGE_TYPES.get(os.path.splitext(path)[1].lower())
    if not mime:
        return None
    try:
        import shadow_probe
        real = shadow_probe.resolve(root, path)
    except Exception:                    # noqa: BLE001 -- unconfined is unsafe
        return None
    try:
        if not os.path.isfile(real):
            return None
        size = os.path.getsize(real)
        if size > MAX_IMAGE_BYTES:
            return {"path": path, "kind": "image", "too_big": True,
                    "bytes": size, "data_uri": ""}
        with open(real, "rb") as fh:
            blob = fh.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        return None
    if len(blob) > MAX_IMAGE_BYTES:
        return {"path": path, "kind": "image", "too_big": True,
                "bytes": len(blob), "data_uri": ""}
    return {"path": path, "kind": "image", "too_big": False,
            "bytes": len(blob),
            "data_uri": "data:%s;base64,%s"
                        % (mime, base64.b64encode(blob).decode("ascii"))}


def candidate_paths(mission, root):
    """The files this decision may be about. OWNERSHIP ONLY.

    THE LEAK THIS CLOSES (founder, 2026-09-21). This used to return probe
    paths PLUS every untracked path git reported, and the second half was a
    cross-mission leak: a Europe trip mission's decision surface listed
    `marc-marquez.txt`, `motogp-top-10-news.md`, `weight-loss-plan.html` and
    several of Shadow's own source files -- twelve candidates for a mission
    whose only criterion was about an itinerary.

    git status answers "what is not committed". That has nothing to do with
    which mission produced a file, and the two coincide only when exactly one
    mission has ever run in the directory. Every mission runs in the
    founder's repo, so in practice every mission could read every other
    mission's output.

    I INTRODUCED THAT MYSELF, in the artifact-lane fix that let the judge see
    a newly created file. It solved that problem by giving every mission
    access to every other mission's files, and the note here is so the trade
    is not quietly made again: discovery is not ownership.

    Ownership now lives in ONE place -- shadow_paths.owned_artifacts -- and
    means a path this mission's own probes named, or one explicitly recorded
    on its record. A mission that owns nothing sees nothing, and the packet
    says so in words rather than showing somebody else's work.
    """
    try:
        import shadow_paths
        return shadow_paths.owned_artifacts(mission)
    except Exception:                    # noqa: BLE001 -- own nothing, not fatal
        return []


def artifacts_for(mission, root):
    """The evidence, read from disk. PART 2 OF THE PACKET.

    Text arrives WHOLE where it fits, which is the difference between this
    and a summary: an excerpt of a ten-line ranking is not a ranking, and a
    founder asked to approve an order must see the order. Where it does not
    fit, the cut is ANNOUNCED -- `truncated` is a field the surface renders,
    so nobody approves a list believing they saw all of it.
    """
    try:
        import shadow_evidence
    except Exception:                    # noqa: BLE001 -- no artifacts, not fatal
        return []
    out, budget, images = [], MAX_TOTAL_TEXT, 0
    for path in candidate_paths(mission, root):
        if len(out) >= MAX_ARTIFACTS or budget <= 0:
            break
        if os.path.splitext(path)[1].lower() in IMAGE_TYPES:
            if images >= MAX_IMAGES:
                continue
            got = _image(root, path)
            if got is not None:
                out.append(got)
                images += 1
            continue
        text, note = shadow_evidence.read_artifact(root, path)
        if text is None:
            continue                     # unreadable: reported by `missing`
        facts = shadow_evidence.facts_for(text)
        body = text[:min(MAX_TEXT, budget)]
        truncated = len(body) < len(text)
        budget -= len(body)
        out.append({"path": path, "kind": "text", "text": body,
                    "truncated": truncated, "facts": facts})
    return out


def packet_for(mission, root=None):
    """The whole decision packet, or None when there is nothing to ask.

    None IS NOT AN ERROR. A mission with no outstanding founder row has no
    decision to make self-contained, and stamping an empty packet would put
    an evidence block on a surface that is not asking anything.

    `missing` IS THE HONEST ANSWER TO THE NO-CONTEXT CASE. When a question is
    outstanding and NO artifact could be gathered, the packet says so in
    words rather than presenting a bare question the founder cannot answer.
    "I am asking you about something I cannot show you" is a worse look and a
    better product than silence.

    NEVER RAISES. This is stamped on the path where a mission goes to the
    founder, and an exception there would turn "ask the founder" into a
    failed mission -- the same house rule every other Shadow read follows.
    """
    if not isinstance(mission, dict):
        return None
    asks = open_asks(mission)
    if not asks:
        return None
    if root is None:
        try:
            import shadow_probe
            root = shadow_probe.default_root()
        except Exception:                # noqa: BLE001
            root = ""
    try:
        artifacts = artifacts_for(mission, root)
    except Exception:                    # noqa: BLE001 -- ask anyway, say less
        artifacts = []
    try:
        established = established_for(mission, root)
    except Exception:                    # noqa: BLE001
        established = []
    missing = ""
    if not artifacts:
        missing = ("Shadow could not gather the artifact this question is "
                   "about — no file it checked is readable in the "
                   "workdir. Open the task's chat to see what the worker "
                   "produced.")
    # THE REVISION THIS PACKET SPEAKS FOR (founder, 2026-09-21). The
    # founder answers by index, and an amend replaces done_when wholesale --
    # so the answer has to name the version it was shown, exactly as an
    # approval does. MissionStore.confirm_check refuses a stale one.
    return {"at": _now(), "asks": asks, "established": established,
            "artifacts": artifacts, "missing": missing,
            "version": int(mission.get("version") or 1)}
