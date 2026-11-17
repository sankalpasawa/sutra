"""Copy all files from test-A to test-B, keeping the same folder structure.

Rule: skip any file that’s already in test-B, don’t overwrite it
Existing files in the destination are never overwritten.

The source is only read. Writes happen only inside the destination.
"""

import os
import shutil

DEFAULT_SOURCE = '__SOURCE__'
DEFAULT_DESTINATION = '__DESTINATION__'


def copy_files(source=DEFAULT_SOURCE, destination=DEFAULT_DESTINATION):
    """Copy files and nested folders from source to destination.

    Files already present in the destination are skipped, never overwritten.
    Returns (copied, skipped) lists of relative paths.
    """
    copied = []
    skipped = []
    for root, _dirs, names in os.walk(source):
        rel_root = os.path.relpath(root, source)
        target_root = destination if rel_root == '.' else os.path.join(destination, rel_root)
        os.makedirs(target_root, exist_ok=True)
        for name in names:
            src = os.path.join(root, name)
            dst = os.path.join(target_root, name)
            rel = os.path.relpath(src, source)
            if os.path.lexists(dst):
                skipped.append(rel)
                continue
            shutil.copy2(src, dst)
            copied.append(rel)
    return copied, skipped


if __name__ == '__main__':
    done, left = copy_files()
    print(f'Copied {len(done)} file(s), skipped {len(left)} existing file(s).')
