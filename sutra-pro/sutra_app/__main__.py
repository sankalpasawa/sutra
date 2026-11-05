"""`python -m sutra_app` and the `sutra-pro` command (pyproject `[project.scripts]`): a thin dispatcher.

    sutra-pro [serve] [flags]                  the server (`sutra_app.main.run`); no subcommand means serve
    sutra-pro doctor | status | stop | config | open ...      the operator commands (`sutra_app.ops.cli`)

`--help` is answered by argparse before the app, the database or any model is touched, so it works offline and costs nothing.
"""
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    from sutra_app import oslayer
    oslayer.setup_stdio()                      # Windows only: a console's legacy code page must not turn a message into an error
    from sutra_app.ops.cli import dispatch
    return dispatch(argv)


if __name__ == "__main__":
    sys.exit(main())
