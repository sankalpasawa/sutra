"""Model replies: tolerant in, closed out (library design 3.5).

Model output is untrusted. It is read tolerantly (a fenced block or the first `{` to the last `}`, a reply cut short is
closed, enum words in any case, keys the class does not declare dropped and listed) and then validated strictly by the
closed class. J2 reads its replies with `.get`, so an extra key never failed a turn; this keeps that, and nothing that
is stored is ever open.

`extract_json` and `close_json` are J2's own code (llm.py:268-295): the ONE copy. `engine/llm.py` re-exports them and
`connectors/jsonio.py` imports them (S2-models-12), so they keep raising ValueError exactly as J2's did. They are J2's
code line for line except the fenced-block search, which is cut short so that it runs in linear time (review round 1:
J2's `re.search` is quadratic on a reply with many opening fences, and a reply is untrusted). The results are the same.

A reply is also refused when it is longer than the gate's payload limit, before any pattern runs.
"""
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .base import Value, discriminator_of, union_members, unwrap_annotation
from .gate import MAX_PAYLOAD_BYTES
from .registry import REGISTRY, ModelRegistry, RegistryError
from .types import Violation, clip, violation, violations_from_validation_error

__all__ = [
    "extract_json", "close_json", "ReplyInvalid", "ParsedReply", "ReplyParser", "normalise_enums", "drop_unknown",
    "tolerate", "retry_text_for", "RETRY_PREFIX",
]

log = logging.getLogger("sutra.library")


# ---- J2's own JSON extraction (llm.py:268-295), with a linear-time fence search -----------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)      # J2's pattern, character for character
_FENCE_CLOSE = re.compile(r"\}\s*```")                             # what has to follow the object for _FENCE to match


def extract_json(text):
    # J2 ran `re.search(_FENCE, text)` on the whole reply. That is quadratic when the reply holds many opening fences
    # and no closing one ("```{" x 16000 took 3.4 s), and a reply is untrusted. _FENCE can match only where a "}",
    # whitespace and "```" follow the "{": so the search stops after the LAST such closer. Every opening fence before
    # it has a closer ahead, and the first of them matches; none can fail after a long scan. Same match as J2's.
    last = None
    for last in _FENCE_CLOSE.finditer(text):
        pass
    m = _FENCE.search(text, 0, last.end()) if last else None
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise ValueError("no JSON object in reply")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        # A reply cut short or missing its last brace (runs/j2-20261013-185235: the whole proposal became a 400-char
        # "say"): close the open string and brackets and try once more; still bad -> the caller's fallback.
        return json.loads(close_json(text[start:]))


def close_json(s):
    """s with its unclosed string and brackets closed, in order."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            esc, in_str = (not esc and ch == "\\"), in_str and not (ch == '"' and not esc)
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    return s.rstrip().rstrip(",") + ('"' if in_str else "") + "".join(reversed(stack))


# ---- errors and results -------------------------------------------------------------------------------------------

RETRY_PREFIX = "THE VALIDATOR REJECTED: "          # J2's wording (j2.py:5972): the model is told what to fix
_RETRY_LIMIT = 4000


def retry_text_for(violations: Sequence[Violation]) -> str:
    """The text a retry prompt carries: the prefix, then "<path>: <message>" for each violation, joined by "; "."""
    parts = [f"{v.path}: {v.message}" if v.path else v.message for v in violations]
    return clip(RETRY_PREFIX + "; ".join(parts), _RETRY_LIMIT)


class ReplyInvalid(Exception):
    """A reply that could not be read as the class asked for. `retry_text` goes into the retry prompt; the retry
    budget stays with the caller (J2 gives a builder 3 attempts). HTTP: 422 with the violations."""

    def __init__(self, code: Literal["not_json", "not_object", "shape"], violations: Sequence[Violation],
                 retry_text: str | None = None) -> None:
        self.code = code
        self.violations = list(violations)
        self.retry_text = retry_text if retry_text is not None else retry_text_for(self.violations)
        first = self.violations[0].message if self.violations else code
        super().__init__(f"{code}: {first}")


@dataclass(frozen=True)
class ParsedReply:
    """`model` is the validated class; `dropped_keys` and `normalised` are dotted paths (a list index is a number)."""

    model: Value
    dropped_keys: list[str] = field(default_factory=list)
    normalised: list[str] = field(default_factory=list)


# ---- tolerant reading: enum words in any case, undeclared keys dropped ---------------------------------------------

def _join(path: str, part: Any) -> str:
    return f"{path}.{part}" if path else str(part)


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _literal_values(model: type[BaseModel], name: str) -> tuple[str, ...]:
    info = model.model_fields.get(name)
    core = unwrap_annotation(info.annotation)[0] if info is not None else None
    return tuple(v for v in get_args(core) if isinstance(v, str)) if get_origin(core) is Literal else ()


def _common_tag(models: list[type[BaseModel]]) -> str | None:
    """A field that is a Literal of strings in every member: `kind` first, else the first such field."""
    names = [n for n in models[0].model_fields if all(_literal_values(m, n) for m in models)]
    return "kind" if "kind" in names else (names[0] if names else None)


class _Walker:
    """Walks a reply alongside the class it should become and fixes what can be fixed without guessing."""

    def __init__(self, enums: bool, drop: bool) -> None:
        self.enums = enums
        self.drop = drop
        self.dropped: list[str] = []
        self.normalised: list[str] = []

    def value(self, annotation: Any, value: Any, path: str, hint: str | None = None) -> Any:
        core, meta = unwrap_annotation(annotation)
        origin = get_origin(core)
        if origin is Literal:
            return self._literal(core, value, path)
        members = union_members(core)
        if members is not None:
            return self._union(members, discriminator_of(meta) or hint, value, path)
        if _is_model(core):
            return self.model(core, value, path)
        args = get_args(core)
        if isinstance(value, list) and origin in (list, set, frozenset, Sequence) and args:
            return [self.value(args[0], item, _join(path, i)) for i, item in enumerate(value)]
        if isinstance(value, dict) and origin in (dict, Mapping) and len(args) == 2:
            return {k: self.value(args[1], item, _join(path, k)) for k, item in value.items()}
        return value

    def _literal(self, annotation: Any, value: Any, path: str) -> Any:
        allowed = [v for v in get_args(annotation) if isinstance(v, str)]
        if not self.enums or not isinstance(value, str) or value in allowed:
            return value
        folded = value.strip().lower()
        hits = [v for v in allowed if v.lower() == folded]
        if len(hits) == 1:
            self.normalised.append(path)
            return hits[0]
        return value

    def model(self, cls: type[BaseModel], value: Any, path: str) -> Any:
        if not isinstance(value, dict):
            return value
        declared: dict[str, Any] = {}
        for name, info in cls.model_fields.items():
            declared[name] = info
            for alias in (info.alias, info.validation_alias):
                if isinstance(alias, str):
                    declared[alias] = info
        out: dict[str, Any] = {}
        for key, item in value.items():
            info = declared.get(key)
            if info is None:
                if self.drop:
                    self.dropped.append(_join(path, key))
                else:
                    out[key] = item
                continue
            disc = info.discriminator if isinstance(info.discriminator, str) else None
            out[key] = self.value(info.annotation, item, _join(path, key), disc)
        return out

    def _union(self, members: tuple[Any, ...], disc: str | None, value: Any, path: str) -> Any:
        real = [m for m in members if m is not type(None)]
        if not isinstance(value, dict):
            for member in real:                       # a scalar or list: the first member that changes it
                trial = _Walker(self.enums, self.drop)
                changed = trial.value(member, value, path)
                if trial.normalised or trial.dropped:
                    self.normalised.extend(trial.normalised)
                    self.dropped.extend(trial.dropped)
                    return changed
            return value
        models = [unwrap_annotation(m)[0] for m in real if _is_model(unwrap_annotation(m)[0])]
        if len(models) == 1:
            return self.model(models[0], value, path)
        tag = disc or (_common_tag(models) if models else None)
        raw = value.get(tag) if tag else None
        if isinstance(raw, str):
            for exact in (True, False):
                for member in models:
                    options = _literal_values(member, tag)
                    if (raw in options) if exact else (raw.strip().lower() in {o.lower() for o in options}):
                        return self.model(member, value, path)
        return value


def tolerate(model: type[BaseModel], data: Any, *, enums: bool = True, drop: bool = True) -> tuple[Any, list[str], list[str]]:
    """(data read tolerantly for `model`, the paths of the keys dropped, the paths of the enum words fixed)."""
    walker = _Walker(enums, drop)
    return walker.model(model, data, ""), walker.dropped, walker.normalised


def normalise_enums(model: type[BaseModel], data: Any) -> tuple[Any, list[str]]:
    """Every `Literal[str]` field read case-insensitively and written back in the model's casing. Returns the new
    data and the paths it changed; unknown words are left for the strict check to refuse."""
    fixed, _, changed = tolerate(model, data, enums=True, drop=False)
    return fixed, changed


def drop_unknown(model: type[BaseModel], data: Any) -> tuple[Any, list[str]]:
    """The keys the class does not declare, at any depth, removed. Returns the new data and the dropped paths."""
    fixed, dropped, _ = tolerate(model, data, enums=False, drop=True)
    return fixed, dropped


# ---- the parser ---------------------------------------------------------------------------------------------------

def _loads(text: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(text)
    except (ValueError, RecursionError):
        return False, None


class ReplyParser:
    """text -> a validated model of a registered class, or ReplyInvalid. Never repairs and never retries."""

    def __init__(self, registry: ModelRegistry = REGISTRY) -> None:
        self._registry = registry

    def parse(self, family: str, text: str | bytes | Mapping[str, Any], *, kind: str | None = None,
              version: int | None = None) -> ParsedReply:
        data = self._object_from(text)
        cls = self._class_for(family, kind, version, data)
        data, dropped, normalised = tolerate(cls, data)
        if dropped:
            log.debug("reply for %s dropped keys: %s", family, dropped)
        try:
            model = cls.model_validate(data)
        except ValidationError as exc:
            raise ReplyInvalid("shape", violations_from_validation_error(exc)) from None
        return ParsedReply(model=model, dropped_keys=dropped, normalised=normalised)

    # ---- steps ------------------------------------------------------------------------------------------------

    @staticmethod
    def _object_from(text: Any) -> dict[str, Any]:
        """The JSON object in the reply: the whole text, else J2's `extract_json` (fence, first `{` to last `}`, a cut
        short reply closed). Valid JSON that is not an object is `not_object`; nothing parseable is `not_json`; so is
        a reply longer than `MAX_PAYLOAD_BYTES` (characters for text, bytes for bytes), refused before any pattern
        runs: the reply is untrusted and a degenerate model can send megabytes of blank lines."""
        if isinstance(text, Mapping):
            return dict(text)
        if isinstance(text, (bytes, bytearray)):
            if len(text) > MAX_PAYLOAD_BYTES:
                raise _reply_too_large(len(text), "bytes")
            text = bytes(text).decode("utf-8", errors="replace")
        if not isinstance(text, str):
            raise ReplyInvalid("not_json", [violation("", "not_json", "the reply is not text")])
        if len(text) > MAX_PAYLOAD_BYTES:
            raise _reply_too_large(len(text), "characters")
        whole_ok, whole = _loads(text.strip())
        if whole_ok:
            if isinstance(whole, dict):
                return whole
            raise ReplyInvalid("not_object", [violation(
                "", "not_object", f"the reply is JSON but not an object (it is {_kind_of(whole)}): send one JSON object")])
        try:
            found = extract_json(text)
        except (ValueError, RecursionError):
            fenced = _fenced_inner(text)
            if fenced is not None:
                ok, inner = _loads(fenced)
                if ok and not isinstance(inner, dict):
                    raise ReplyInvalid("not_object", [violation(
                        "", "not_object", f"the reply is JSON but not an object (it is {_kind_of(inner)}): send one JSON object")]) from None
            raise ReplyInvalid("not_json", [violation("", "not_json", "the reply holds no JSON object: send one JSON object")]) from None
        if not isinstance(found, dict):                     # extract_json only returns objects; kept as a guard
            raise ReplyInvalid("not_object", [violation("", "not_object", "the reply is not a JSON object")])
        return found

    def _class_for(self, family: str, kind: str | None, version: int | None, data: dict[str, Any]) -> type[BaseModel]:
        classes = self._registry.kinds(family, version)
        if kind is not None:
            if kind not in classes:
                raise RegistryError("unknown_kind", f"{family!r} has no kind {kind!r} (it has {sorted(classes)})")
            return classes[kind]
        distinct = list(dict.fromkeys(classes.values()))
        if len(distinct) == 1:
            return distinct[0]
        said = data.get("kind")
        if isinstance(said, str):
            folded = said.strip().lower()
            for name, cls in classes.items():
                if name == said or name.lower() == folded:
                    return cls
        raise ReplyInvalid("shape", [violation(
            "kind", "union_tag_invalid" if "kind" in data else "union_tag_not_found",
            f"the reply must say which kind it is: one of {', '.join(sorted(classes))}")])


def _reply_too_large(size: int, unit: str) -> ReplyInvalid:
    return ReplyInvalid("not_json", [violation(
        "", "reply_too_large", f"the reply is {size} {unit} long, the limit is {MAX_PAYLOAD_BYTES}: send one JSON object, shorter")])


def _fenced_inner(text: str) -> str | None:
    """What a reply holds when it is ONE code fence from end to end (an optional lowercase `json` tag, then the
    content), else None. Slicing and `strip`, not a pattern: a regex with a lazy group between two `\\s*` is cubic on
    a long run of blank lines, and the reply is untrusted."""
    body = text.strip()
    if len(body) < 6 or not (body.startswith("```") and body.endswith("```")):
        return None
    inner = body[3:-3]
    return (inner[4:] if inner.startswith("json") else inner).strip()


def _kind_of(value: Any) -> str:
    if isinstance(value, list):
        return "a list"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, bool):
        return "a boolean"
    if value is None:
        return "null"
    return "a number"
