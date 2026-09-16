"""shadow_presence.py -- the founder's per-app Presence choices, on disk.

WHAT PRESENCE IS: the corner dot (`.shdot`) and its card, mounted by
mountShadowOverlay() in static/js/15-shadow-overlay.js. Until now the only
two ways to hide it were memory-only flags on the client (S.shadowHideSession
and S.shadowQuiet) -- a reload brought the dot straight back -- and the
global shadow-enabled kill switch (the providers accessor), which is all-or-nothing and takes the
engine down with the widget.

THIS IS THE THIRD STORE UNDER THE SHADOW HOME, not a second settings store.
static/js/16-shadow-home.js warns that the settings page "must not become" a
second store, and it is right: the rule it is defending is that a setting
lives with the subsystem that enforces it, reached through one route per
field. That is exactly what this is -- a sibling of task-limits.json
(mission_engine.limits_path) and delegate-offers.json
(mission_engine.offers_path), under the same resolver, for a concern neither
of those two owns. Folding "which apps hide the dot" into a file named
task-limits.json would be the actual sprawl.

AN APP IS ITS FOLDER NAME. modules_api's header states it: "THE FOLDER IS
THE MODULE (D-M1). A module exists iff ~/.sutra-ui/modules/<id>/module.json
parses." So an id is all this store needs to key on, and a stored id whose
app has since been deleted is inert rather than broken -- it simply never
matches again.

NEVER RAISES ON READ. hidden_apps() is on the overlay's boot path: it is
answered inside GET /api/shadow/status, which is the one fetch that decides
whether the dot mounts at all. A corrupt file or an unreadable home must
cost the founder their hide list, not their Presence.

QUIET HOURS IS THE ONE KEY WITH A CLOCK BEHIND IT. The other three answer
"would Shadow show up at all"; this one answers "not at this hour", so it is
the only setting here whose effective value changes without anyone writing
it. The window is stored; whether it is CURRENTLY quiet is derived, by
window_active() -- one pure function, mirrored in JS by shadowQuietWindowNow
in static/js/15-shadow-overlay.js and pinned against it by the shared case
table in test_quiet_hours_cases.json.

TIMEZONE: local wall clock, on the machine running the app. Backend and
renderer are the same machine in this desktop shell, so the server's
quiet_now and the client's live evaluation agree by construction. That is an
assumption, and the place it breaks is a remotely-served panel, where the two
clocks would sit in different zones; the fix then is for the server to stop
reporting quiet_now and let the client own it alone. No such deployment
exists, so it is not built.
"""
import datetime
import os
import re

import json_store
import shadow_ledger

#: A COPY of modules_api.ID_RE, and deliberately a copy rather than an import.
#: modules_api pulls in FastAPI and placement_engine; this module is imported
#: by a bare interpreter in the restart test (and, more importantly, on the
#: status path where the Apps surface may be flagged off entirely), so it must
#: stay dependency-free. test_shadow_presence.py pins the two patterns equal,
#: so the copy cannot drift silently.
_APP_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")

#: The key inside presence.json. Named for what it holds rather than for the
#: control that writes it: the row is called "Hide for this app", but what is
#: stored is the set of apps that hide it.
_KEY = "hidden_apps"

#: The second key in the same file, for the row above it: "Corner card on
#: every screen". TWO KEYS, ONE FILE, and they share it safely because every
#: writer here read-modify-writes the whole dict -- hiding the dot for one app
#: must not silently clear the standing choice, or vice versa.
_CORNER_KEY = "corner_card"

#: SHOWN is the default, and the default is not neutral: an install nobody has
#: configured must still have a way to reach Shadow, and the dot is it. An
#: absent key therefore means "shown", and the file stays sparse -- a read
#: never creates it.
CORNER_CARD_DEFAULT = True

#: The THIRD key in the same file: "Nudges per hour", the rate pillAllowed
#: enforces on the unsolicited pill in static/js/15-shadow-overlay.js. It joins
#: the other two here rather than getting a store of its own for the reason the
#: module header gives -- one file per subsystem, one route per field -- and it
#: is read-modify-written like them, so setting a rate cannot clear a hide.
_NUDGES_KEY = "nudges_per_hour"

#: THREE IS THE RATE THE CODE HAS ALWAYS ENFORCED. It was the JS constant
#: SH_PILLS_PER_HOUR until this became settable; the number does not change,
#: only who owns it. The client no longer carries a copy at all -- if this
#: value never reaches the browser the pill stays silent rather than falling
#: back to a second, unowned 3.
NUDGES_PER_HOUR_DEFAULT = 3

#: ZERO IS A REAL CHOICE, not a disabled state: "never interrupt me unasked".
#: It is the floor rather than 1 because a founder who wants silence should not
#: have to reach for the kill switch and take the engine down with the widget.
MIN_NUDGES_PER_HOUR = 0

#: The ceiling is a guard against a stepper held down, not a considered maximum
#: -- ten unsolicited interruptions an hour is already past anything Shadow
#: should want, and the number exists so the store has an outer edge to clamp
#: to rather than to invite the founder to it.
MAX_NUDGES_PER_HOUR = 10

#: The FOURTH key in the same file: "Quiet hours", the window inside which
#: Shadow stops speaking unasked. Same file and same read-modify-write as the
#: three above -- setting a window must not clear a hide, and a hide must not
#: clear the window.
_QUIET_KEY = "quiet_hours"

#: ABSENT MEANS NOT SET, and that is the whole reason clearing is a DELETE
#: rather than a stored null: an install whose founder cleared the window must
#: be byte-identical to one that never set it, so there is exactly one shape
#: that reads back as "no quiet hours". A sentinel would give "cleared" a
#: second spelling that every reader downstream would have to know about --
#: the rule set_turn_budget already follows for reset-to-auto.
QUIET_HOURS_DEFAULT = None

#: 24-hour wall clock, zero-padded, and ANCHORED at both ends on purpose. An
#: unanchored search would accept "09:00 ish" and a looser hour group would
#: accept "9:00", both of which have a plausible reading and neither of which
#: is what was typed -- this module refuses rather than guesses (clean_app_id).
#: <input type="time"> emits exactly this shape, so the strict form is also the
#: form the control actually sends.
_HHMM = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def presence_path():
    """The one file the per-app Presence choices live in.

    Beside task-limits.json and delegate-offers.json under the SAME resolver
    (shadow_ledger.shadow_home), so a test that redirects the shadow home
    redirects this too and can never write a hide into the live install.
    """
    return os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                        "presence.json")


def _read():
    return json_store.read_json(presence_path(), {})


def clean_app_id(app_id):
    """Coerce anything to a legal app id, or raise ValueError.

    Raises rather than sanitising, for the reason clamp_running raises on
    "five" and clean_offer_name raises on "Code Review!": a settings write
    that quietly stores a DIFFERENT id has hidden the dot for an app the
    founder was not looking at, and the control they would use to undo it is
    on the app they were.

    Surrounding space is forgiven -- that is typing, not meaning. Case is
    NOT: unlike a kind name, an app id is a folder name on a case-preserving
    filesystem, and lowercasing it would invent a path.
    """
    s = str(app_id or "").strip()
    if not s:
        raise ValueError("an app id is required")
    if not _APP_ID.match(s):
        raise ValueError(
            "%r is not a usable app id -- 2 to 41 characters, lowercase "
            "letters, digits and hyphens, starting with a letter or digit"
            % (s,))
    return s


def clean_corner_card(v):
    """Coerce a corner-card value, or raise ValueError.

    STRICTER THAN clean_app_id, and stricter than clamp_running: there is no
    out-of-band-but-meaningful value for a boolean the way there is for a
    stepper held past its ceiling. "off", 0 and None are all things a confused
    caller sends, and every one of them has a plausible-looking coercion that
    would store the OPPOSITE of what someone meant.
    """
    if v is True or v is False:
        return v
    raise ValueError("corner_card must be true or false")


def corner_card():
    """Whether the corner card is shown at all: the founder's standing choice,
    else the default.

    NEVER RAISES, for the reason in the module header -- this is answered
    inside the settings GET that the overlay's own boot awaits before it may
    mount, so a corrupt file must cost the default rather than leave the
    founder with no way to reach Shadow.

    THE STANDING CHOICE, NOT A DISMISSAL. The card's own hide control is a
    browser-lifetime flag meaning "not right now" and the server has never
    known it. The card is visible when both agree. This is also not
    app_hidden(): that answers "not on THIS app", this answers "not at all".
    """
    try:
        raw = _read().get(_CORNER_KEY)
    except Exception:                     # noqa: BLE001 -- see module header
        return CORNER_CARD_DEFAULT
    if raw is None:
        return CORNER_CARD_DEFAULT
    try:
        return clean_corner_card(raw)
    except ValueError:
        return CORNER_CARD_DEFAULT        # a hand-edited junk value


def set_corner_card(v):
    """Persist the standing choice. Returns the value actually stored.

    Read-modify-write, so the hide list living in this same file survives a
    corner-card change -- and so a corner-card change survives a hide.
    """
    val = clean_corner_card(v)
    cur = _read()
    if not isinstance(cur, dict):
        cur = {}
    cur[_CORNER_KEY] = val
    json_store.write_json(presence_path(), cur)
    return val


def clamp_nudges(n):
    """Coerce anything to a legal nudge rate, or raise ValueError.

    CLAMPS NUMBERS, RAISES ON JUNK -- clamp_running's split, for clamp_running's
    reason: a stepper held past the ceiling should stop at the ceiling, while a
    write that quietly stores 3 when the founder sent "three" is worse than one
    that says no.

    BOOLEANS ARE JUNK HERE, which is where this parts company with
    clamp_running. int(True) is 1, so a client that sent a switch's value onto
    a stepper's field would silently store "one nudge an hour" and look like it
    worked. There is no reading of True that means a rate.
    """
    if isinstance(n, bool):
        raise ValueError("nudges_per_hour must be a whole number")
    try:
        v = int(n)
    except (TypeError, ValueError):
        raise ValueError("nudges_per_hour must be a whole number")
    return max(MIN_NUDGES_PER_HOUR, min(MAX_NUDGES_PER_HOUR, v))


def nudges_per_hour():
    """The rate the pill ACTUALLY enforces: the founder's setting, else the
    default.

    NEVER RAISES, for the reason corner_card() does not: it is answered inside
    the settings GET the overlay's boot awaits. A corrupt file must cost the
    founder their chosen rate, not their Presence.
    """
    try:
        raw = _read().get(_NUDGES_KEY)
    except Exception:                     # noqa: BLE001 -- see module header
        return NUDGES_PER_HOUR_DEFAULT
    if raw is None:
        return NUDGES_PER_HOUR_DEFAULT
    try:
        return clamp_nudges(raw)
    except ValueError:
        return NUDGES_PER_HOUR_DEFAULT    # a hand-edited junk value


def set_nudges_per_hour(n):
    """Persist the rate. Returns the value actually stored (post-clamp).

    Read-modify-write, like the two writers above it: three keys share this
    file, and a rate change must not cost the standing choice or the hide list.
    """
    val = clamp_nudges(n)
    cur = _read()
    if not isinstance(cur, dict):
        cur = {}
    cur[_NUDGES_KEY] = val
    json_store.write_json(presence_path(), cur)
    return val


def _minutes(hhmm):
    """"HH:MM" -> minutes past midnight. Raises ValueError on anything else."""
    m = _HHMM.match(hhmm if isinstance(hhmm, str) else "")
    if not m:
        raise ValueError("%r is not a time of day -- use HH:MM, 24-hour"
                         % (hhmm,))
    return int(m.group(1)) * 60 + int(m.group(2))


def clean_quiet_hours(v):
    """Coerce a quiet-hours window, or raise ValueError. None CLEARS it.

    STRICT, like clean_corner_card and for the same reason: there is no
    out-of-band-but-meaningful window the way there is for a stepper held past
    its ceiling, and a window stored as something other than what was typed
    silences Shadow at hours the founder never chose -- at hours, by
    definition, when they are not watching it happen.

    REFUSES start == end, which is the one case with two honest readings and
    no way to tell them apart. "22:00 to 22:00" is either a zero-length window
    (never quiet) or a whole day of silence, the two are the same two strings,
    and guessing picks one of them to be wrong about. The founder wanting
    permanent silence has a control that says so -- nudges per hour at 0.

    NORMALISES to exactly {"start", "end"}: extra keys are dropped rather than
    rejected, so a client sending back a richer GET payload is not punished for
    it, but nothing unrecognised reaches the disk.
    """
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("quiet_hours must be an object with start and end, "
                         "or null to clear it")
    for key in ("start", "end"):
        if key not in v:
            raise ValueError("quiet_hours needs both start and end")
    start, end = v["start"], v["end"]
    _minutes(start)                       # raises with the offending value
    _minutes(end)
    if start == end:
        raise ValueError(
            "quiet hours need a start and an end that differ -- set nudges "
            "per hour to 0 for silence that never lifts")
    return {"start": start, "end": end}


def quiet_hours():
    """The founder's quiet window, else None.

    NEVER RAISES, for the reason corner_card() does not: it is answered inside
    the settings GET the overlay's boot awaits. A hand-edited window must cost
    the founder their quiet hours, not their Presence -- and the failure
    direction matters here, because degrading to None means Shadow SPEAKS when
    it was unsure, which the founder can see and correct. Degrading the other
    way would be silence they have no way to notice.
    """
    try:
        raw = _read().get(_QUIET_KEY)
    except Exception:                     # noqa: BLE001 -- see module header
        return QUIET_HOURS_DEFAULT
    if raw is None:
        return QUIET_HOURS_DEFAULT
    try:
        return clean_quiet_hours(raw)
    except ValueError:
        return QUIET_HOURS_DEFAULT        # a hand-edited junk window


def set_quiet_hours(v):
    """Persist the window; `None` clears it. Returns what is stored after the
    write -- the window, or None.

    CLEARING DELETES THE KEY rather than storing a null, so "cleared" and
    "never set" are one state on disk and not two. See QUIET_HOURS_DEFAULT.

    Read-modify-write, like the three writers above it: four keys share this
    file now, and a window change must not cost the standing choice, the rate
    or the hide list.
    """
    val = clean_quiet_hours(v)
    cur = _read()
    if not isinstance(cur, dict):
        cur = {}
    if val is None:
        cur.pop(_QUIET_KEY, None)
    else:
        cur[_QUIET_KEY] = val
    json_store.write_json(presence_path(), cur)
    return val


def window_active(window, at=None):
    """Is `at` inside `window`? The whole of the quiet-hours rule, in one
    pure function so the JS copy has exactly one thing to match.

    INCLUSIVE START, EXCLUSIVE END. "Quiet from 21:00 until 08:00" is read by
    the person saying it as: 21:00 is already quiet, 08:00 is not any more.
    Half-open also makes two adjacent windows meet without overlapping, which
    a closed interval could not.

    IT WRAPS MIDNIGHT, and that is the case a naive `start <= t < end` gets
    silently wrong -- 21:00->08:00 would be empty under it, so the setting
    would appear to store fine and simply never fire. When start > end the
    window is the two arcs either side of midnight: `t >= start or t < end`.

    NEVER RAISES. A junk window is not quiet, for the reason quiet_hours()
    degrades to None: the safe direction is Shadow speaking when unsure.
    """
    if not window:
        return False
    try:
        start = _minutes(window.get("start"))
        end = _minutes(window.get("end"))
    except (ValueError, AttributeError):
        return False
    if start == end:
        return False                      # clean refuses it; be inert if hand-edited
    now = at or datetime.datetime.now()
    t = now.hour * 60 + now.minute
    if start < end:
        return start <= t < end
    return t >= start or t < end


def quiet_now(at=None):
    """Is it quiet RIGHT NOW, per the stored window? Never raises.

    LOCAL WALL CLOCK, which in this desktop shell is the same clock the
    renderer reads -- backend and browser are one machine, so the server's
    answer and the client's agree by construction. A remotely-served panel
    would put the two in different zones; see the module header note.
    """
    try:
        return window_active(quiet_hours(), at)
    except Exception:                     # noqa: BLE001 -- see docstring
        return False


def hidden_apps():
    """The apps Presence is hidden for. NEVER RAISES -- see the module header.

    SORTED, and re-validated on the way out. This file is hand-editable and
    the list is a SET (membership is the only question anyone asks of it), so
    there is no founder-chosen order to preserve the way offered_kinds() has
    one -- and a junk entry must cost itself rather than the whole list.
    """
    try:
        raw = _read().get(_KEY)
    except Exception:                     # noqa: BLE001 -- see module header
        return []
    if not isinstance(raw, list):
        return []
    out = set()
    for item in raw:
        try:
            out.add(clean_app_id(item))
        except ValueError:
            continue                      # a hand-edited junk id
    return sorted(out)


def app_hidden(app_id):
    """Is Presence hidden for this app? NEVER RAISES, including on a junk id
    -- the question "should the dot mount here" has an answer for every
    string, and that answer is no-it-should-not-be-hidden."""
    try:
        return clean_app_id(app_id) in hidden_apps()
    except ValueError:
        return False


def set_app_hidden(app_id, hidden):
    """Persist one app's Presence choice. Returns the whole list after the
    write, so the caller repaints rather than patching.

    ONE APP PER WRITE, and the whole list back. The same reasoning as
    add_offer/remove_offer: a whole-list body makes two quick clicks a lost
    update, because the second POST carries a list built before the first
    landed and silently undoes it.

    IDEMPOTENT. Hiding an already-hidden app and showing an already-shown one
    both succeed and write nothing new. The founder's gesture is "make it so",
    not "toggle", and a 400 on the second click of a double-click would be a
    race wearing an error's clothes.
    """
    key = clean_app_id(app_id)
    cur = _read()
    if not isinstance(cur, dict):
        cur = {}
    have = set(hidden_apps())
    if hidden:
        have.add(key)
    else:
        have.discard(key)
    cur[_KEY] = sorted(have)
    json_store.write_json(presence_path(), cur)
    return cur[_KEY]
