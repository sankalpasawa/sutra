"""shadow_intervention.py -- ONE typed question Shadow can put to the founder.

WHY THIS EXISTS. Shadow's only way of asking for something was the
`ask_founder` decision, which carries a single `reason` string capped at 300
characters. That can say "I need to know the region"; it cannot say "pick
one of these three, and tell me the budget cap, and confirm you accept the
cost". Everything richer than a sentence had to become a bespoke endpoint.

WHAT THIS IS. One request object with N typed fields, and one validator for
the answer. A "form" is not a new concept here -- it is simply an
intervention whose `fields` has more than one entry. There is no new mission
state, no new lifecycle, and no per-type API: `ask_founder` still exits
through store.block() exactly as it did, and the request rides BESIDE the
state on the record, the same way pause_reason, block_reason and
pending_floor_say already do.

WHAT THIS IS NOT. It is not a replacement for `confirm_check` (the
founder_confirm tier keeps its own writer and its own dual-lane rule) and
not a replacement for goal `guidance` (free text against a goal). Both are
untouched and keep working for missions that never see an intervention.

THE EXTENSION POINT IS THE TYPE TABLE AND NOTHING ELSE. Adding a type later
means adding one entry to FIELD_TYPES (a value validator) and one branch to
the renderer. It does not touch STATES, TRANSITIONS, the /act verb list, the
feed contract, the decision loop, or the scheduler.

SECURITY. Values are DATA, never instructions: every value is validated
against its field's declared type and constraints before it is stored, and
the decision context carries them as a labelled block, not as prose Shadow
could mistake for the worker talking. Secrets are deliberately NOT carried
here -- see DEFERRED_FIELD_TYPES.
"""
import re
import uuid
from datetime import datetime

#: Bumped only when the REQUEST shape changes in a way an older renderer
#: could mis-draw. Adding a field type does not bump it; the renderer already
#: has to skip a type it does not know.
SCHEMA_VERSION = 1

#: Answerable today: Shadow may ask for these and the founder can submit them.
ACTIVE_FIELD_TYPES = (
    "boolean", "choice", "multi_choice", "text", "long_text", "number",
    "currency", "percent", "date", "datetime", "url", "email", "ranking",
)

#: RESERVED, AND DELIBERATELY NOT ANSWERABLE YET. The vocabulary is declared
#: here so the protocol is the extension point rather than the schema, but a
#: request carrying one is REFUSED at creation: a form the founder cannot
#: complete would block a mission with no way out, which is strictly worse
#: than Shadow asking in prose.
#:
#:   file / image / artifact_ref  need an upload substrate this repo does not
#:                                have for founder -> Shadow direction.
#:   secret_ref                   must route through the EXISTING keychain
#:                                mechanism (deepseek_auth.KeychainCredentialStore,
#:                                service "com.sutra.provider"), which stores
#:                                the secret and persists only a mask. A
#:                                credential must never travel as an ordinary
#:                                intervention value, be ledgered, or reach a
#:                                transcript.
DEFERRED_FIELD_TYPES = ("file", "image", "artifact_ref", "secret_ref")

MAX_FIELDS = 12
MAX_OPTIONS = 40
QUESTION_MAX = 400
CONTEXT_MAX = 2000
LABEL_MAX = 200
HELP_MAX = 400
TEXT_MAX = 500              # default cap for `text`
LONG_TEXT_MAX = 20000       # default cap for `long_text`
EVIDENCE_MAX = 8
EVIDENCE_TEXT_MAX = 600

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def _s(v, limit):
    return str(v if v is not None else "").strip()[:limit]


def new_id():
    return "iv-%s" % uuid.uuid4().hex[:12]


# ------------------------------------------------------------- request ----

def _option(raw):
    if isinstance(raw, str):
        return {"value": raw[:200], "label": raw[:LABEL_MAX], "help": ""}
    if not isinstance(raw, dict):
        return None
    value = _s(raw.get("value"), 200)
    if not value:
        return None
    return {"value": value,
            "label": _s(raw.get("label"), LABEL_MAX) or value,
            "help": _s(raw.get("help"), HELP_MAX)}


def _field(raw):
    """One typed ask, or None if it is not one. Strict by the same rule
    validate_decision follows: a malformed field must not degrade into a
    guess, because the founder would be answering a question nobody wrote."""
    if not isinstance(raw, dict):
        return None
    key = _s(raw.get("key"), 40)
    if not _KEY_RE.match(key):
        return None
    ftype = _s(raw.get("type"), 40)
    if ftype not in ACTIVE_FIELD_TYPES:
        return None                 # deferred types are refused here
    out = {
        "key": key,
        "type": ftype,
        "label": _s(raw.get("label"), LABEL_MAX) or key,
        "help": _s(raw.get("help"), HELP_MAX),
        "required": bool(raw.get("required", False)),
        "default": raw.get("default"),
        "options": [],
        "constraints": {},
    }
    if ftype in ("choice", "multi_choice", "ranking"):
        seen = set()
        for o in (raw.get("options") or [])[:MAX_OPTIONS]:
            opt = _option(o)
            if opt and opt["value"] not in seen:
                seen.add(opt["value"])
                out["options"].append(opt)
        if len(out["options"]) < 2:
            return None             # a choice of one is not a choice
    c = raw.get("constraints")
    if isinstance(c, dict):
        for k in ("min", "max", "min_len", "max_len", "pattern",
                  "min_select", "max_select", "must_be_true", "step",
                  "currency_code", "decimals"):
            if k in c:
                out["constraints"][k] = c[k]
    return out


def _evidence(raw):
    out = []
    for e in (raw or [])[:EVIDENCE_MAX]:
        if isinstance(e, str):
            out.append({"kind": "note", "ref": "",
                        "text": _s(e, EVIDENCE_TEXT_MAX)})
        elif isinstance(e, dict):
            out.append({"kind": _s(e.get("kind"), 40) or "note",
                        "ref": _s(e.get("ref"), 400),
                        "text": _s(e.get("text"), EVIDENCE_TEXT_MAX)})
    return [e for e in out if e["text"] or e["ref"]]


def _confirms_check(raw, fields):
    """The `founder_confirm` check this question closes, or None.

    WHY THIS EXISTS (founder, 2026-09-15, mission m-cd009367d41a). Shadow
    asked "do you accept the test evidence as passing?", the founder answered
    `tests_pass: True`, and the mission still could not complete: the answer
    landed in `founder_response` while done_when[2] ("Relevant tests pass.",
    tier founder_confirm) stayed unmet. Four of five checks had passed; the
    mission burned its remaining budget and died `failed` on max turns. The
    founder had said the exact thing the check was asking for, in the only
    place Shadow had asked it, and nothing carried it across.

    THE ANSWER MUST BE AFFIRMATIVE, NOT MERELY VALID. "Valid" includes "no".
    So the target names BOTH the check index and the BOOLEAN field that gates
    it, and the check is confirmed only when that field comes back True. A
    founder who answers "no, the tests do not pass" must not thereby sign off
    that the tests pass -- which a value-blind rule would do.

    Boolean ONLY, on purpose. A choice or a text field would need a policy
    for which answers count as yes, and that policy is exactly the kind of
    inference this module refuses to make on the founder's behalf.

    Absent, malformed, or pointing at a field that is not a declared boolean
    -> None, and the intervention behaves exactly as it always has. This is
    an OPT-IN marker: everything without it is untouched.
    """
    got = raw.get("confirms_check")
    if not isinstance(got, dict):
        return None
    idx = got.get("index")
    if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0:
        return None
    key = _s(got.get("field"), 40)
    if not key:
        return None
    if not any(f["key"] == key and f["type"] == "boolean" for f in fields):
        return None                 # the gate must be a boolean we asked for
    return {"index": idx, "field": key}


def confirmed_index(intervention, values):
    """The done_when index this ANSWER confirms, or None.

    Read by the /act intervene handler, which passes it to the EXISTING
    MissionStore.confirm_check -- still the one and only writer of a
    founder_confirm `met` flag, still stamping confirmed_by/confirmed_at.
    Nothing here writes mission state.
    """
    target = (intervention or {}).get("confirms_check")
    if not isinstance(target, dict):
        return None
    if (values or {}).get(target.get("field")) is not True:
        return None                 # answered "no", or not answered at all
    idx = target.get("index")
    return idx if isinstance(idx, int) and not isinstance(idx, bool) else None


def validate_request(raw):
    """A founder-intervention request, or None if it is not one.

    None is not an error path: `ask_founder` without a usable intervention
    keeps its historical prose-only behaviour untouched.
    """
    if not isinstance(raw, dict):
        return None
    question = _s(raw.get("question"), QUESTION_MAX)
    if not question:
        return None
    fields = []
    seen = set()
    for f in (raw.get("fields") or [])[:MAX_FIELDS]:
        got = _field(f)
        if got is None:
            return None             # one bad field invalidates the form
        if got["key"] in seen:
            return None
        seen.add(got["key"])
        fields.append(got)
    if not fields:
        return None
    return {
        "id": _s(raw.get("id"), 40) or new_id(),
        "schema_version": SCHEMA_VERSION,
        "question": question,
        "context": _s(raw.get("context"), CONTEXT_MAX),
        "evidence": _evidence(raw.get("evidence")),
        "fields": fields,
        "submit_label": _s(raw.get("submit_label"), 60) or "Send to Shadow",
        "expires_at": raw.get("expires_at") or None,
        # OPTIONAL, and absent for every intervention that does not ask the
        # founder to sign off a specific check. See _confirms_check.
        "confirms_check": _confirms_check(raw, fields),
    }


# -------------------------------------------------------------- values ----

def _num(v):
    if isinstance(v, bool):
        raise ValueError("expected a number")
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace(",", "")
    if not s:
        raise ValueError("expected a number")
    return float(s) if ("." in s or "e" in s.lower()) else int(s)


def _bounded(n, c, label="value"):
    if "min" in c and n < c["min"]:
        raise ValueError("%s must be at least %s" % (label, c["min"]))
    if "max" in c and n > c["max"]:
        raise ValueError("%s must be at most %s" % (label, c["max"]))
    return n


def _v_boolean(v, f):
    if isinstance(v, bool):
        b = v
    elif str(v).strip().lower() in ("true", "yes", "1", "on"):
        b = True
    elif str(v).strip().lower() in ("false", "no", "0", "off"):
        b = False
    else:
        raise ValueError("expected yes or no")
    if f["constraints"].get("must_be_true") and not b:
        raise ValueError("this must be approved to continue")
    return b


def _v_choice(v, f):
    s = str(v).strip()
    if s not in [o["value"] for o in f["options"]]:
        raise ValueError("pick one of the offered options")
    return s


def _v_multi(v, f):
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        raise ValueError("expected a list of options")
    allowed = [o["value"] for o in f["options"]]
    out = []
    for item in v:
        s = str(item).strip()
        if s not in allowed:
            raise ValueError("%r is not one of the offered options" % s)
        if s not in out:
            out.append(s)
    c = f["constraints"]
    if "min_select" in c and len(out) < c["min_select"]:
        raise ValueError("choose at least %d" % c["min_select"])
    if "max_select" in c and len(out) > c["max_select"]:
        raise ValueError("choose at most %d" % c["max_select"])
    return out


def _v_text(v, f, cap=TEXT_MAX):
    s = str(v if v is not None else "").strip()
    c = f["constraints"]
    limit = int(c.get("max_len") or cap)
    if len(s) > limit:
        raise ValueError("at most %d characters" % limit)
    if "min_len" in c and len(s) < c["min_len"]:
        raise ValueError("at least %d characters" % c["min_len"])
    pattern = c.get("pattern")
    if pattern:
        try:
            if not re.fullmatch(pattern, s):
                raise ValueError("does not match the required format")
        except re.error:
            pass                    # a bad pattern must not block the founder
    return s


def _v_long_text(v, f):
    return _v_text(v, f, cap=LONG_TEXT_MAX)


def _v_number(v, f):
    return _bounded(_num(v), f["constraints"])


def _v_currency(v, f):
    n = _bounded(_num(v), f["constraints"], "amount")
    decimals = f["constraints"].get("decimals")
    return round(float(n), int(decimals)) if decimals is not None else n


def _v_percent(v, f):
    c = dict(f["constraints"])
    c.setdefault("min", 0)
    c.setdefault("max", 100)
    return _bounded(_num(v), c, "percentage")


def _v_date(v, f):
    s = str(v).strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise ValueError("expected a date as YYYY-MM-DD")
    return s


def _v_datetime(v, f):
    s = str(v).strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(s)
    except ValueError:
        raise ValueError("expected a date and time (ISO-8601)")
    return s


def _v_url(v, f):
    s = str(v).strip()
    if not re.match(r"^https?://[^\s/]+\.[^\s]*$", s):
        raise ValueError("expected an http(s) URL")
    return s


def _v_email(v, f):
    s = str(v).strip()
    if not _EMAIL_RE.match(s):
        raise ValueError("expected an email address")
    return s


def _v_ranking(v, f):
    if not isinstance(v, (list, tuple)):
        raise ValueError("expected the options in order")
    allowed = [o["value"] for o in f["options"]]
    out = [str(x).strip() for x in v]
    if sorted(out) != sorted(allowed):
        raise ValueError("rank every option exactly once")
    return out


#: THE EXTENSION POINT. One entry per answerable type; adding a type here and
#: a branch in the renderer is the whole of "support a new input".
FIELD_TYPES = {
    "boolean": _v_boolean,
    "choice": _v_choice,
    "multi_choice": _v_multi,
    "text": _v_text,
    "long_text": _v_long_text,
    "number": _v_number,
    "currency": _v_currency,
    "percent": _v_percent,
    "date": _v_date,
    "datetime": _v_datetime,
    "url": _v_url,
    "email": _v_email,
    "ranking": _v_ranking,
}


def _empty(v):
    return v is None or (isinstance(v, str) and not v.strip()) \
        or (isinstance(v, (list, tuple)) and len(v) == 0)


def validate_values(request, values):
    """(clean, errors). `errors` is field key -> message, empty when valid.

    An unknown submitted key is IGNORED rather than rejected: the founder's
    browser may be a version behind, and dropping an extra is safer than
    refusing an otherwise-good answer. What is never ignored is a declared
    field: every one is validated, and a required one must be present.
    """
    if not isinstance(values, dict):
        return {}, {"_": "expected an object of field values"}
    clean, errors = {}, {}
    for f in (request or {}).get("fields") or []:
        key = f["key"]
        raw = values.get(key, f.get("default"))
        if _empty(raw):
            if f["required"]:
                errors[key] = "this is required"
            continue
        fn = FIELD_TYPES.get(f["type"])
        if fn is None:
            errors[key] = "this input type is not supported yet"
            continue
        try:
            clean[key] = fn(raw, f)
        except ValueError as exc:
            errors[key] = str(exc)
        except Exception:           # noqa: BLE001 -- never 500 on bad input
            errors[key] = "could not read this value"
    return clean, errors


def summarise(request, clean):
    """What Shadow is shown. A LABELLED BLOCK, never prose: the founder's
    answer must not be mistakable for something the worker said, and it must
    not be re-read as an instruction. Bounded, like every other decision
    input."""
    rows = []
    by_key = {f["key"]: f for f in (request or {}).get("fields") or []}
    for key, value in (clean or {}).items():
        f = by_key.get(key) or {"label": key}
        if isinstance(value, (list, tuple)):
            shown = ", ".join(str(x) for x in value)
        else:
            shown = str(value)
        rows.append({"key": key, "label": f.get("label") or key,
                     "value": shown[:600]})
    return rows
