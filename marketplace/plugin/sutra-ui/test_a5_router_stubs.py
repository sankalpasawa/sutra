"""A5 P1.8: the three routers P3 and P4 fill exist, are empty, and app.py includes them (so they never edit app.py for routers)."""
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
STUBS = ("dept_list_api", "shadow_dept_api", "shadow_graph_api")


@pytest.mark.parametrize("name", [n for n in STUBS if n != "shadow_graph_api"])      # P4 filled the graph router (test_shadow_graph_api.py)
def test_the_stub_is_an_empty_router(name):
    import importlib
    from fastapi import APIRouter
    m = importlib.import_module(name)
    assert isinstance(m.router, APIRouter)
    src = (HERE / (name + ".py")).read_text(encoding="utf-8")
    assert re.search(r"^router = APIRouter\(\)$", src, re.M)


def test_app_includes_the_three_and_the_department_list_comes_before_the_ref_routes():
    src = (HERE / "app.py").read_text(encoding="utf-8")
    at = {n: src.index("app.include_router(%s.router)" % n) for n in STUBS + ("website_api", "models_api")}
    assert at["dept_list_api"] < at["website_api"], "`_departments` is registered before any /{ref} native route"
    assert all(src.count("app.include_router(%s.router)" % n) == 1 for n in STUBS)
    import app
    paths = {getattr(r, "path", "") for r in app.app.routes}
    assert not [p for p in paths if p.startswith("/api/native/_departments") ], "the stubs add no route"
