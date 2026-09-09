"""workspace — the team's shared knowledge, in the company's own Supabase project.

Five modules, and they only point one way, which is what keeps this package from tangling:

    _common.py   the one HTTP call, the retry rule, and Supabase errors turned into English
    client.py    the one place Supabase is spoken to: rows over PostgREST, files over Storage
    schema.sql   the fixed create script — ten tables, ten RLS-guarded, nine triggers, one bucket
    schema.py    creating it (two routes), joining it, verifying it, and migrating it
    link.py      the share link, and the guarantee that nothing in it can create or drop a table

The rule the whole package is built to keep, from design/WORKSPACE-PLAN.md section 10:
NOTHING REPORTS SUCCESS IT HAS NOT VERIFIED. schema.verify() is the only function allowed to
say a workspace is ready, and it says so only after reading the tables, the bucket and the
workspace row back out of Supabase with the same publishable key the app itself will use.

Supabase is not where Sutra reads from. Every person keeps a full local knowledge base and
this package is only how a change gets from one person's machine to everybody else's.
"""
from . import client, link, schema                    # noqa: F401
from ._common import NotConfigured, TableMissing, WorkspaceError   # noqa: F401

__all__ = ["client", "link", "schema",
           "WorkspaceError", "TableMissing", "NotConfigured"]
