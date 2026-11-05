"""The chat agent's prompts: four template files in `templates/` read with `str.format` (orchestrator 5.3, S4-fnodes-12).

    render("decide", revision=..., digest=..., ...)    the text of one prompt
    PLACEHOLDERS                                       template name -> the placeholders it has (exactly these are passed)
    field_digest(*models)                              names and one-line docs of the library models a reply nests
    conversation(history) / pending_lines(pending)     the CONVERSATION and PENDING blocks of the decide prompt
    violation_lines(violations)                        the "- path: code: message" lines of retry.md
    changed_keys(previous, current)                    the "Changed since your last try" part

The prompts ask for structure only: there is no reply sentence to write and `{banned}` is not a placeholder of the chat agent.
A literal brace in a template file must be doubled; the files have none. `render` refuses a missing or an unknown placeholder, so a
template and its caller cannot drift apart.
"""
import string
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sutra_app.library.types import FUNCTIONS, Violation, clip

__all__ = ["TEMPLATES", "PLACEHOLDERS", "PromptError", "template", "render", "field_digest", "conversation", "pending_lines",
           "violation_lines", "changed_keys"]

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES = ("decide", "change", "assign", "retry")
PLACEHOLDERS: dict[str, frozenset[str]] = {
    "decide": frozenset({"revision", "digest", "conversation", "pending", "message", "field_digest", "schema"}),
    "change": frozenset({"revision", "digest", "field_digest", "message", "decision", "kind", "schema"}),
    "assign": frozenset({"digest", "field_digest", "message", "schema"}),
    "retry": frozenset({"n", "max", "violations", "delta"}),
}


class PromptError(ValueError):
    """A template that is missing, or a render call whose placeholders do not match the template's."""


@lru_cache(maxsize=None)
def template(name: str) -> str:
    """The text of `templates/<name>.md`."""
    if name not in TEMPLATES:
        raise PromptError(f"no prompt template {name!r} (there are {', '.join(TEMPLATES)})")
    return (TEMPLATE_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def fields_of(name: str) -> frozenset[str]:
    """The placeholders the template file really holds."""
    return frozenset(field for _, field, _, _ in string.Formatter().parse(template(name)) if field)


def render(name: str, **values: Any) -> str:
    """The template with its placeholders filled (`str.format`). Every placeholder must be given, and nothing else."""
    wanted = fields_of(name)
    given = frozenset(values)
    if wanted != given:
        missing, extra = sorted(wanted - given), sorted(given - wanted)
        raise PromptError(f"prompt {name!r}: missing {missing or 'nothing'}, unknown {extra or 'nothing'}")
    return template(name).format(**{key: str(value) for key, value in values.items()})


def _first_line(text: str | None) -> str:
    return " ".join((text or "").strip().split("\n\n")[0].split())


def field_digest(*models: type[BaseModel], functions: bool = True) -> str:
    """One line per model: `Name: field, field, ... - first line of its doc`, then the five function names. The model reads this
    beside the full transport schema, so it stays short."""
    lines = []
    for model in models:
        names = ", ".join(model.model_fields)
        notes = [f"{name}: {_first_line(info.description)}" for name, info in model.model_fields.items() if info.description]
        line = f"{model.__name__}: {names}"
        doc = _first_line(model.__doc__)
        if doc:
            line += f" - {clip(doc, 160)}"
        lines.append(line)
        lines.extend(f"  {note}" for note in notes)
    if functions:
        lines.append("Every department has five function nodes: " + ", ".join(FUNCTIONS) + ".")
    return "\n".join(lines)


def conversation(history: Sequence[tuple[str, str]], *, limit: int = 12, width: int = 400) -> str:
    """The latest `limit` lines as `Owner: ...` / `Sutra: ...`, oldest first, each cut to `width` characters."""
    if not history:
        return "(no earlier messages)"
    names = {"user": "Owner", "sutra": "Sutra"}
    return "\n".join(f"{names.get(who, who)}: {clip(' '.join(text.split()), width)}" for who, text in list(history)[-limit:])


def pending_lines(pending: Sequence[str]) -> str:
    return "\n".join(pending) if pending else "(nothing is waiting for a yes or no)"


def violation_lines(violations: Sequence[Violation | Mapping[str, str]]) -> str:
    """`- path: code: message` per violation (the path is `request` when the violation has none)."""
    lines = []
    for item in violations:
        get = item.get if isinstance(item, Mapping) else (lambda key, default="": getattr(item, key, default))
        lines.append(f"- {get('path', '') or 'request'}: {get('code', '')}: {get('message', '')}")
    return "\n".join(lines)


def changed_keys(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> str:
    """Which top-level keys differ between the model's last two answers; a plain sentence when there is nothing to compare."""
    if previous is None or current is None:
        return "nothing to compare yet; this is the first correction"
    keys = [key for key in dict.fromkeys([*previous, *current]) if previous.get(key) != current.get(key)]
    return ", ".join(keys) if keys else "nothing: your answer was the same as before"
