"""J2's two form words, spelled in one place (D188, rule R-2).

An output type has a form: `page` (a site) or `document` (a written artifact). The words belong to J2 (`j2_types.FORMS`); the engine layer of the app
needs them to ask "is this a document?" and nowhere else. `is_document(info)` takes the entry of a type as J2 returns it (`j2_types.info(name)`), so
no type is named: the form decides. `check_forms(j2_types)` proves J2 still has exactly these two forms; `capabilities.register(j2)` calls it, where
J2 is already loaded and its environment is set (J2 reads some constants from the environment when it is imported, so this module imports nothing
of J2 itself). A third form in J2 stops the engine at registration by name instead of being quietly treated as a page.
"""
from collections.abc import Mapping

__all__ = ["PAGE", "DOCUMENT", "is_document", "is_page", "check_forms"]

PAGE = "page"
DOCUMENT = "document"


def is_document(info) -> bool:
    """True when the type entry (`j2_types.info(name)`) has the document form."""
    return isinstance(info, Mapping) and info.get("form") == DOCUMENT


def is_page(info) -> bool:
    return isinstance(info, Mapping) and info.get("form") == PAGE


def check_forms(j2_types) -> None:
    """Raise when J2's list of forms is not exactly (PAGE, DOCUMENT)."""
    if tuple(j2_types.FORMS) != (PAGE, DOCUMENT):
        raise RuntimeError(f"J2's forms are {tuple(j2_types.FORMS)!r}; the engine layer knows {(PAGE, DOCUMENT)!r}: engine/forms.py needs the new form")
