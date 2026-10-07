"""Regression floor for desktop modules that must import on Windows."""
import importlib.util
from pathlib import Path


def test_placement_engine_imports_without_posix_fcntl(monkeypatch):
    """A Windows desktop must reach founding; POSIX-only imports must not abort it."""
    source = Path(__file__).resolve().parents[1] / "placement_engine.py"
    real_import = __import__

    def without_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ModuleNotFoundError("No module named 'fcntl'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", without_fcntl)
    spec = importlib.util.spec_from_file_location("placement_engine_without_fcntl", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module._lock)
