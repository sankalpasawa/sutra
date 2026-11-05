"""`python -m sutra_app.engine --run-dir <dir> [--mock]`: one run is one process (engine design 3.3, 4.7)."""
import sys

from .host.loop import main

if __name__ == "__main__":
    sys.exit(main())
