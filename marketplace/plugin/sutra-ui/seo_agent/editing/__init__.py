"""editing — change one block, and show what changed.

Two jobs, kept apart on purpose. edit_block does the work and refuses to let anything it was
not asked about move. make_diff turns before and after into something a browser can render.
Neither knows about the other, so a diff can be shown for any two versions, however they
came about.
"""
from .edit_block import BlockDrift, edit_block
from .make_diff import make_diff

__all__ = ["edit_block", "make_diff", "BlockDrift"]
