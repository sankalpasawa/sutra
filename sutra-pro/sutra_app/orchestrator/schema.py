"""The SQL schema, version 1 (orchestrator 4.1) and the list of migrations.

The DDL is a tuple of single statements, not one script, so `Database.migrate()` can run all of them and the version bump
in ONE transaction (a trigger's body holds `;`, so the text cannot be split on it). Settled changes are included:
`chart_changes.task_title` and `result_json` [S3-web-04], `atoms.display` [S4-fnodes-08], the Atom log `atom_ledger`
with its append-only triggers [S4-fnodes-09], `chat_sessions.filed_under` and the partial unique index on active sessions
[S2-models-11], `usage_ledger.step`, `atom_id`, `detail_json` [S1-contracts-05]. All times are epoch seconds.

`MIGRATIONS[i]` takes a database from `user_version` i to i + 1. Add a new tuple (or a callable taking the connection) at the
end for the next version; never edit an old one.
"""
from collections.abc import Callable, Sequence
from sqlite3 import Connection

__all__ = ["DDL_V1", "MIGRATIONS", "SCHEMA_VERSION", "TABLES", "Migration"]

DDL_V1: tuple[str, ...] = (
    # schema version = PRAGMA user_version; 'graph_version' and 'bootstrapped_at' live here
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",

    # append-only Checked[OrgChart]; max(revision) is the chart
    "CREATE TABLE org_charts (revision INTEGER PRIMARY KEY, body TEXT NOT NULL, sha256 TEXT NOT NULL, ts INTEGER NOT NULL)",

    # the change log: one row per decision (id = 'chg-' + 4 digits of seq)
    """CREATE TABLE chart_changes (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
  task_id TEXT NOT NULL,
  task_title TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL CHECK (kind IN ('reuse','add','rearrange')),
  actor TEXT NOT NULL CHECK (actor IN ('chat_agent','user','system')),
  base_revision INTEGER NOT NULL, result_revision INTEGER,
  status TEXT NOT NULL CHECK (status IN ('applied','pending_approval','rejected','stale','failed')),
  summary TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', session_id TEXT, message_id INTEGER,
  body TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}',
  plan_json TEXT, ops_json TEXT, violations TEXT,
  before_sha TEXT NOT NULL DEFAULT '', after_sha TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL)""",
    "CREATE INDEX chart_changes_status ON chart_changes(status, seq)",

    # projection of the head OrgChart; archived rows are history and the id-reuse guard
    """CREATE TABLE org_nodes (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('root','department','division')),
  name TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','archived')),
  merged_into TEXT REFERENCES org_nodes(id), created_rev INTEGER NOT NULL, archived_rev INTEGER, ts INTEGER NOT NULL)""",
    "CREATE UNIQUE INDEX org_nodes_one_root ON org_nodes(kind) WHERE kind = 'root'",
    """CREATE TABLE org_edges (
  parent_id TEXT NOT NULL REFERENCES org_nodes(id), child_id TEXT NOT NULL REFERENCES org_nodes(id),
  position INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (parent_id, child_id), CHECK (parent_id <> child_id))""",
    "CREATE UNIQUE INDEX org_edges_child ON org_edges(child_id)",
    "CREATE INDEX org_edges_parent ON org_edges(parent_id, position)",

    # the library Department record {id, home_dir, ts_created}; home_dir is relative to the data dir
    """CREATE TABLE departments (
  id TEXT PRIMARY KEY REFERENCES org_nodes(id), home_dir TEXT NOT NULL,
  body TEXT NOT NULL, sha256 TEXT NOT NULL, ts INTEGER NOT NULL)""",

    # one run of one department; run_id names the folder runs/<run_id>
    """CREATE TABLE tasks (
  id TEXT PRIMARY KEY, dept_id TEXT NOT NULL REFERENCES departments(id), scope_node_id TEXT REFERENCES org_nodes(id),
  title TEXT NOT NULL, user_text TEXT NOT NULL, framing TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('blocked','queued','starting','running','waiting_user','done',
                              'done_with_open_items','stopped','crashed','cancelled')),
  run_id TEXT UNIQUE, parent_task_id TEXT REFERENCES tasks(id), depends_on TEXT NOT NULL DEFAULT '[]',
  request_id TEXT, origin_message_id INTEGER, change_id TEXT, settings_json TEXT NOT NULL DEFAULT '{}',
  pid INTEGER, events_offset INTEGER NOT NULL DEFAULT 0, inbox_seq INTEGER NOT NULL DEFAULT 0,
  outcome TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, started_at INTEGER, ended_at INTEGER, last_event_at INTEGER)""",
    "CREATE INDEX tasks_dept ON tasks(dept_id, created_at)",
    "CREATE INDEX tasks_open ON tasks(status) WHERE status IN ('blocked','queued','starting','running','waiting_user')",
    "CREATE UNIQUE INDEX tasks_one_live_per_dept ON tasks(dept_id) WHERE status IN ('starting','running','waiting_user')",

    # the library Node family; body = Checked[Node]; there is no outcome column and no stored 'contains' edge
    """CREATE TABLE graph_nodes (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('root','department','division','step','identity','adaptation','priority','coordination','audit')),
  department_id TEXT REFERENCES departments(id), parent_id TEXT,
  state TEXT NOT NULL DEFAULT 'idle' CHECK (state IN ('idle','running','waiting','waiting_on_you','fault','filed','done_unchecked','left_open','not_made')),
  label TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', chat_session_id TEXT,
  task_id TEXT REFERENCES tasks(id), step_ref TEXT, version INTEGER NOT NULL DEFAULT 1,
  body TEXT NOT NULL, sha256 TEXT NOT NULL, ts INTEGER NOT NULL,
  CHECK ((kind = 'step') = (task_id IS NOT NULL AND step_ref IS NOT NULL)))""",
    "CREATE UNIQUE INDEX graph_nodes_step ON graph_nodes(task_id, step_ref) WHERE kind = 'step'",
    "CREATE INDEX graph_nodes_dept ON graph_nodes(department_id, kind)",
    "CREATE INDEX graph_nodes_hot ON graph_nodes(state) WHERE state IN ('running','waiting_on_you','fault')",
    """CREATE TABLE graph_edges (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('handoff','step','speaks_to','depends_on')),
  from_id TEXT NOT NULL REFERENCES graph_nodes(id), to_id TEXT NOT NULL REFERENCES graph_nodes(id),
  status TEXT NOT NULL DEFAULT 'idle', label TEXT NOT NULL DEFAULT '', task_id TEXT REFERENCES tasks(id),
  version INTEGER NOT NULL DEFAULT 1, body TEXT NOT NULL, CHECK (from_id <> to_id))""",
    "CREATE INDEX graph_edges_to ON graph_edges(to_id, kind)",
    "CREATE INDEX graph_edges_task ON graph_edges(task_id)",

    # no UNIQUE and no REFERENCES on node_id: an archived session keeps its origin node id; one ACTIVE session per node
    """CREATE TABLE chat_sessions (
  id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('org','department','division','function','step')), title TEXT NOT NULL,
  writable INTEGER NOT NULL DEFAULT 0 CHECK (writable IN (0,1)),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  filed_under TEXT,
  connector TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', provider_session_id TEXT,
  last_message_id INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
    "CREATE UNIQUE INDEX chat_sessions_active ON chat_sessions(node_id) WHERE status = 'active'",
    """CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES chat_sessions(id),
  role TEXT NOT NULL CHECK (role IN ('user','agent','system')), who TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'text' CHECK (kind IN ('text','question','card','note','error')),
  text TEXT NOT NULL, card_json TEXT, meta_json TEXT NOT NULL DEFAULT '{}',
  pause TEXT, answered_by INTEGER REFERENCES chat_messages(id),
  task_id TEXT REFERENCES tasks(id), src_ref TEXT,
  state TEXT NOT NULL DEFAULT 'ok' CHECK (state IN ('ok','pending','error')), at INTEGER NOT NULL)""",
    "CREATE INDEX chat_messages_session ON chat_messages(session_id, id)",
    "CREATE UNIQUE INDEX chat_messages_src ON chat_messages(session_id, src_ref) WHERE src_ref IS NOT NULL",
    "CREATE INDEX chat_messages_open_q ON chat_messages(kind, answered_by) WHERE kind = 'question' AND answered_by IS NULL",

    # body = Checked[Atom] ('work-atom/0.3') or the library atom_view payload (J2 atom/1); `display` is the five-word state
    """CREATE TABLE atoms (
  id TEXT PRIMARY KEY,
  schema TEXT NOT NULL CHECK (schema IN ('work-atom/0.3','atom/1')),
  node_id TEXT NOT NULL REFERENCES graph_nodes(id), department_id TEXT REFERENCES departments(id), task_id TEXT REFERENCES tasks(id),
  state TEXT NOT NULL,
  display TEXT NOT NULL CHECK (display IN ('open','verify_failed','closed','refused','abandoned')),
  attempt INTEGER NOT NULL CHECK (attempt BETWEEN 0 AND 3),
  goal TEXT NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL, ts_open INTEGER NOT NULL, ts_closed INTEGER,
  CHECK ((schema = 'work-atom/0.3' AND state IN ('open','closed','refused','abandoned')) OR (schema = 'atom/1' AND state IN ('open','closed','verify_failed','abandoned'))))""",
    "CREATE UNIQUE INDEX one_open_atom_per_node ON atoms(node_id) WHERE state = 'open' AND schema = 'work-atom/0.3'",
    "CREATE INDEX atoms_task ON atoms(task_id, state)",
    "CREATE INDEX atoms_node_display ON atoms(node_id, display)",

    # the Atom log: append-only, one row per atom, written only by AtomStore.append_ledger
    """CREATE TABLE atom_ledger (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, atom_id TEXT NOT NULL UNIQUE, node_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('closed','verify_failed','abandoned','refused')),
  body TEXT NOT NULL, ts INTEGER NOT NULL)""",
    "CREATE TRIGGER atom_ledger_no_update BEFORE UPDATE ON atom_ledger BEGIN SELECT RAISE(ABORT, 'atom log is append-only'); END",
    "CREATE TRIGGER atom_ledger_no_delete BEFORE DELETE ON atom_ledger BEGIN SELECT RAISE(ABORT, 'atom log is append-only'); END",

    # one row per model request; stub rows (provider 'stub') are kept but excluded from totals; atom_id has no foreign key
    """CREATE TABLE usage_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('claude','codex','stub')), model TEXT NOT NULL DEFAULT '', purpose TEXT NOT NULL,
  session_id TEXT REFERENCES chat_sessions(id), node_id TEXT REFERENCES graph_nodes(id), task_id TEXT REFERENCES tasks(id),
  dept_id TEXT REFERENCES departments(id), fn TEXT, step TEXT,
  atom_id TEXT,
  usd REAL CHECK (usd IS NULL OR usd >= 0), tokens_in INTEGER CHECK (tokens_in IS NULL OR tokens_in >= 0),
  tokens_out INTEGER CHECK (tokens_out IS NULL OR tokens_out >= 0),
  seconds REAL NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1 CHECK (ok IN (0,1)), how TEXT NOT NULL DEFAULT '', call_ref TEXT, detail_json TEXT)""",
    "CREATE INDEX usage_task ON usage_ledger(task_id)",
    "CREATE INDEX usage_dept ON usage_ledger(dept_id, at)",
    "CREATE INDEX usage_atom ON usage_ledger(atom_id) WHERE atom_id IS NOT NULL",
    # re-ingest is idempotent: INSERT ... ON CONFLICT(task_id, call_ref) WHERE call_ref IS NOT NULL DO NOTHING
    "CREATE UNIQUE INDEX usage_call ON usage_ledger(task_id, call_ref) WHERE call_ref IS NOT NULL",
)

Migration = Sequence[str] | Callable[[Connection], None]
MIGRATIONS: tuple[Migration, ...] = (DDL_V1,)
SCHEMA_VERSION = len(MIGRATIONS)
TABLES = (
    "meta", "org_charts", "chart_changes", "org_nodes", "org_edges", "departments", "tasks", "graph_nodes", "graph_edges",
    "chat_sessions", "chat_messages", "atoms", "atom_ledger", "usage_ledger",
)
