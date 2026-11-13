"""The script's own test: python3 test_copy_files.py (prints ok)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copy_files  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    src, dst = os.path.join(tmp, "from"), os.path.join(tmp, "to")
    os.makedirs(os.path.join(src, "sub"))
    for rel, text in (("a.txt", "one"), ("sub/b.txt", "two")):
        with open(os.path.join(src, rel), "w", encoding="utf-8") as f:
            f.write(text)
    assert copy_files.copy_files(src, dst) == ["a.txt", "sub/b.txt"]
    assert open(os.path.join(dst, "sub", "b.txt"), encoding="utf-8").read() == "two"
    assert copy_files.copy_files(src, dst) == [], "a second copy has nothing to do"
    try:
        copy_files.copy_files(os.path.join(tmp, "missing"), dst)
        raise AssertionError("a missing folder must be refused")
    except ValueError:
        pass
print("ok")
