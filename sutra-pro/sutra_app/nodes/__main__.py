"""`python -m sutra_app.nodes --run-dir <dir> [--mock]`: one light node is one process."""
import sys

from .host import main

if __name__ == "__main__":
    sys.exit(main())
