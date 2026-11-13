"""Copy every file of one folder into another, keeping sub-folders. Usage: python3 copy_files.py <from> <to>"""
import os
import shutil
import sys


def copy_files(src, dst):
    """Copy each file under src to the same path under dst; an existing file with the same bytes is left alone.
    Returns the paths copied, in order."""
    if not os.path.isdir(src):
        raise ValueError(f"{src}: no such folder")
    copied = []
    for folder, _, names in sorted(os.walk(src)):
        for name in sorted(names):
            a = os.path.join(folder, name)
            rel = os.path.relpath(a, src)
            b = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(b), exist_ok=True)
            if os.path.isfile(b) and open(a, "rb").read() == open(b, "rb").read():
                continue
            shutil.copyfile(a, b)
            copied.append(rel.replace(os.sep, "/"))
    return copied


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python3 copy_files.py <from> <to>")
    for path in copy_files(sys.argv[1], sys.argv[2]):
        print(path)
