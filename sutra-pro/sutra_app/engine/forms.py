"""J2's two file form words, spelled in one place (D188, rule R-2; J2 sync 7, D241).

An output type has a form. Two make one file: `page` (a site) and `document` (a written artifact). Since J2 sync 7 the forms are data only
(`forms` in `artifacts/types.json`, read by `j2_types.forms()`; J2 no longer has a `FORMS` constant), and a form may make a folder instead
(`"output": "folder"`, J2's `agent` form: a builder writes files with its tools). The engine layer needs the two file words to ask "is this a
document?" and nowhere else. `is_document(info)` takes the entry of a type as J2 returns it (`j2_types.info(name)`), so no type is named: the
form decides. `check_forms(j2_types)` proves J2 still has these two forms and that every other form makes a folder, which J2 builds only with
builder tools on (`j2_realization.type_list`; the engine's `llm.tools_on`, D245: on live with the Claude CLI); `capabilities.register(j2)` calls it,
where J2 is already loaded and its environment is set (J2 reads some constants from the environment when it is imported, so this module imports
nothing of J2 itself). A third file form in J2 stops the engine at registration by name instead of being quietly treated as a page.
"""
from collections.abc import Mapping

__all__ = ["PAGE", "DOCUMENT", "FOLDER", "is_document", "is_page", "check_forms"]

PAGE = "page"
DOCUMENT = "document"
FOLDER = "folder"          # the `output` of a form whose builder writes a folder with its tools (J2 sync 7)


def is_document(info) -> bool:
    """True when the type entry (`j2_types.info(name)`) has the document form."""
    return isinstance(info, Mapping) and info.get("form") == DOCUMENT


def is_page(info) -> bool:
    return isinstance(info, Mapping) and info.get("form") == PAGE


def check_forms(j2_types) -> None:
    """Raise when J2's forms (`j2_types.forms()`) lack PAGE or DOCUMENT, or hold another form that does not make a folder."""
    found = j2_types.forms()
    missing = [name for name in (PAGE, DOCUMENT) if name not in found]
    other = [name for name, form in found.items() if name not in (PAGE, DOCUMENT) and form.get("output") != FOLDER]
    if missing or other:
        raise RuntimeError(f"J2's forms are {tuple(found)!r}; the engine layer knows {(PAGE, DOCUMENT)!r} and folder forms "
                           f"(missing {missing!r}, a new file form {other!r}): engine/forms.py needs the new form")
