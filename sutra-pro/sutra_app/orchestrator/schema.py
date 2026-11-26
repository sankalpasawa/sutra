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

__all__ = ["DDL_V1", "DDL_V3_RECURRING", "DDL_V4_AGENT_SESSIONS", "DDL_V5_TURN_CHECKPOINT", "DDL_V6_NODES", "DDL_V7_WORK", "DDL_V8_RECIPES", "DDL_V9_HIDDEN_TEAMS", "MIGRATIONS", "SCHEMA_VERSION", "TABLES", "Migration"]

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

_SESSION_COLUMNS = ("id, node_id, kind, title, writable, status, filed_under, connector, model, provider_session_id, last_message_id, "
                    "note, created_at, updated_at")


def _v2(conn: Connection) -> None:
    """Chat storage v2 (absorb design 2.3, D108), inside the migration's one transaction.

    1. `chat_sessions` is rebuilt (SQLite cannot alter a CHECK): kind gains 'legacy', column `pinned` is added. The rows are copied aside, the table is
       dropped and created again, and the rows are put back. Foreign keys cannot be switched off inside a transaction, so their check is
       deferred to the commit, where each re-inserted session has cleared the `chat_messages` and `usage_ledger` rows that point at it.
    2. `chat_segments`: one row per provider the session has run on.
    3. `chat_search`: FTS5 over message text and session titles, kept in step by triggers and filled from what exists.
    """
    conn.execute("PRAGMA defer_foreign_keys = ON")
    conn.execute("CREATE TABLE chat_sessions_copy AS SELECT * FROM chat_sessions")          # the rows wait here while the table is rebuilt
    conn.execute("DROP TABLE chat_sessions")                                               # children now count as violations, deferred to COMMIT
    conn.execute("""CREATE TABLE chat_sessions (
  id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('org','department','division','function','step','legacy')), title TEXT NOT NULL,
  writable INTEGER NOT NULL DEFAULT 0 CHECK (writable IN (0,1)),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  filed_under TEXT,
  connector TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', provider_session_id TEXT,
  last_message_id INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  pinned TEXT NOT NULL DEFAULT '' CHECK (pinned IN ('','claude','codex')))""")
    conn.execute(f"INSERT INTO chat_sessions({_SESSION_COLUMNS}) SELECT {_SESSION_COLUMNS} FROM chat_sessions_copy ORDER BY rowid")      # each insert clears its children
    conn.execute("DROP TABLE chat_sessions_copy")
    conn.execute("CREATE UNIQUE INDEX chat_sessions_active ON chat_sessions(node_id) WHERE status = 'active'")

    conn.execute("""CREATE TABLE chat_segments (
  session_id TEXT NOT NULL REFERENCES chat_sessions(id), seq INTEGER NOT NULL, connector TEXT NOT NULL,
  provider_session_id TEXT, from_message_id INTEGER NOT NULL DEFAULT 0, at INTEGER NOT NULL, PRIMARY KEY (session_id, seq))""")

    # one row per message (message_id > 0) and one per session title (message_id = 0)
    conn.execute("CREATE VIRTUAL TABLE chat_search USING fts5(body, session_id UNINDEXED, message_id UNINDEXED, tokenize='unicode61')")
    conn.execute("INSERT INTO chat_search(body, session_id, message_id) SELECT title, id, 0 FROM chat_sessions")
    conn.execute("INSERT INTO chat_search(body, session_id, message_id) SELECT text, session_id, id FROM chat_messages WHERE text <> ''")
    for statement in _FTS_TRIGGERS:
        conn.execute(statement)


_FTS_TRIGGERS: tuple[str, ...] = (
    "CREATE TRIGGER chat_search_msg_ai AFTER INSERT ON chat_messages WHEN new.text <> '' BEGIN "
    "INSERT INTO chat_search(body, session_id, message_id) VALUES (new.text, new.session_id, new.id); END",
    "CREATE TRIGGER chat_search_msg_au AFTER UPDATE OF text ON chat_messages BEGIN "
    "DELETE FROM chat_search WHERE message_id = old.id; "
    "INSERT INTO chat_search(body, session_id, message_id) SELECT new.text, new.session_id, new.id WHERE new.text <> ''; END",
    "CREATE TRIGGER chat_search_msg_ad AFTER DELETE ON chat_messages BEGIN DELETE FROM chat_search WHERE message_id = old.id; END",
    "CREATE TRIGGER chat_search_title_ai AFTER INSERT ON chat_sessions BEGIN "
    "INSERT INTO chat_search(body, session_id, message_id) VALUES (new.title, new.id, 0); END",
    "CREATE TRIGGER chat_search_title_au AFTER UPDATE OF title ON chat_sessions BEGIN "
    "DELETE FROM chat_search WHERE message_id = 0 AND session_id = old.id; "
    "INSERT INTO chat_search(body, session_id, message_id) VALUES (new.title, new.id, 0); END",
)

# Recurring work (gap package routines-limits): one row per standing task, one row per due time that was dealt with. UNIQUE(recurring_id,
# due_at) is what makes a restart unable to fire the same slot twice; `cursor_at` is the last due time dealt with (fired, folded or skipped);
# `streak_after` is the run row id above which crashes count toward the three-in-a-row pause (switching a schedule on again starts a new streak).
DDL_V3_RECURRING: tuple[str, ...] = (
    """CREATE TABLE recurring (
  id TEXT PRIMARY KEY, dept_id TEXT NOT NULL REFERENCES departments(id), text TEXT NOT NULL, schedule_json TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), paused_reason TEXT NOT NULL DEFAULT '',
  cursor_at INTEGER NOT NULL, streak_after INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
    "CREATE INDEX recurring_dept ON recurring(dept_id)",
    """CREATE TABLE recurring_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, recurring_id TEXT NOT NULL REFERENCES recurring(id) ON DELETE CASCADE,
  due_at INTEGER NOT NULL, at INTEGER NOT NULL,
  trigger TEXT NOT NULL CHECK (trigger IN ('schedule','catch_up','manual')),
  outcome TEXT NOT NULL CHECK (outcome IN ('started','skipped')),
  task_id TEXT REFERENCES tasks(id), folded INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
  UNIQUE (recurring_id, due_at))""",
    "CREATE INDEX recurring_runs_of ON recurring_runs(recurring_id, id)",
)

# Agent sessions and picks (agent-sessions design 3.2, D130, D131): additive, three ALTER TABLE ... ADD COLUMN on chat_sessions and one on tasks, no rebuild.
# `pinned_model` / `pinned_effort` are the owner's model and effort beside `pinned` (the provider); `run_id` is the run a function or step session belongs to;
# `tasks.pick_json` is the run-level choice for the agents that have none of their own. Every old row gets the empty value: nothing is backfilled.
DDL_V4_AGENT_SESSIONS: tuple[str, ...] = (
    "ALTER TABLE chat_sessions ADD COLUMN pinned_model TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE chat_sessions ADD COLUMN pinned_effort TEXT NOT NULL DEFAULT '' CHECK (pinned_effort IN ('','low','medium','high','xhigh','max'))",
    "ALTER TABLE chat_sessions ADD COLUMN run_id TEXT",
    "CREATE INDEX chat_sessions_run ON chat_sessions(run_id) WHERE run_id IS NOT NULL",
    "ALTER TABLE tasks ADD COLUMN pick_json TEXT NOT NULL DEFAULT ''",
)

# In-flight direct-chat turns (streaming design D211, migration v5): one row per live generation, rewritten every second or so while a turn streams and deleted in the transaction
# that stores the final reply. It is what a restart after a crash turns into the partial reply. Additive: no table that exists is touched, `chat_messages` and its FTS triggers
# stay as they are, and an older build ignores the table. No foreign key: a row must outlive nothing it depends on, and a cleanup must never be blocked.
DDL_V5_TURN_CHECKPOINT: tuple[str, ...] = (
    """CREATE TABLE chat_turn_checkpoint (
  generation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, message_id INTEGER NOT NULL, attempt INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
  state TEXT NOT NULL, seq INTEGER NOT NULL, blocks_json TEXT NOT NULL, updated_at REAL NOT NULL)""",
    "CREATE INDEX chat_turn_checkpoint_session ON chat_turn_checkpoint(session_id)",
)

# Multi-agent nodes (design docs/design/multi-agent-nodes, D253, D254, D258, D262, D264, D280; migration v6). Inert: nothing reads these tables or the `lane` column until
# SUTRA_NODES_V1 is on and a later package wires them. Additive: five new tables, one new column with an empty default on `tasks`, and one index swap.
# * `projects`, `agent_nodes`, `approvals`: the identity and the permissions of a request's nodes. A node is a `tasks` row plus a row in `agent_nodes` (D253).
# * `node_messages`: written only by the server. `seq` is per project and gap-free, so the primary key is (project_id, seq) and the writer takes `MAX(seq) + 1` inside its one
#   write transaction (a table-wide AUTOINCREMENT would leave holes inside a project: see docs/design/multi-agent-nodes/dev-notes.md). `src_ref` is unique per project, so a
#   message that arrives twice is stored once (D264). Append-only, like the audit.
# * `node_audit`: append-only (the triggers copy `atom_ledger`), names and shapes and hashes only, never a payload (D280). No foreign keys: the audit outlives what it names.
# * `tasks.lane`: '' for every task there is. The one-live-task rule becomes "one live task per (team, lane)"; with lane '' on every row it forbids exactly what the old index
#   forbade (D258).
DDL_V6_NODES: tuple[str, ...] = (
    """CREATE TABLE projects (
  id TEXT PRIMARY KEY, request_id TEXT UNIQUE, title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planning' CHECK (status IN ('planning','awaiting_approval','running','reviewing','done','done_with_open_items','stopped','failed')),
  failure_policy TEXT NOT NULL DEFAULT 'stop_branch' CHECK (failure_policy IN ('stop_branch','stop_all')),
  decide_for_me INTEGER NOT NULL DEFAULT 0 CHECK (decide_for_me IN (0,1)),
  paused INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0,1)),
  review_loops INTEGER NOT NULL DEFAULT 0 CHECK (review_loops >= 0),
  caps_json TEXT NOT NULL DEFAULT '{}', budget_credits INTEGER CHECK (budget_credits IS NULL OR budget_credits >= 0),
  budget_usd REAL CHECK (budget_usd IS NULL OR budget_usd >= 0),
  client_id TEXT UNIQUE, created_at INTEGER NOT NULL, ended_at INTEGER, stop_reason TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX projects_status ON projects(status)",
    """CREATE TABLE agent_nodes (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), task_id TEXT UNIQUE REFERENCES tasks(id),
  role TEXT NOT NULL CHECK (role IN ('planner','worker','reviewer')),
  runtime TEXT NOT NULL CHECK (runtime IN ('inline','engine','light')),
  plan_ref TEXT NOT NULL DEFAULT '', depends_on TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'planned' CHECK (state IN ('planned','awaiting_approval','awaiting_system','ready','queued','leased','running','handing_off',
                                                          'done','failed','cancelled','expired')),
  attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1), grants_json TEXT NOT NULL DEFAULT '{}', writes_json TEXT NOT NULL DEFAULT '[]',
  slice_credits INTEGER CHECK (slice_credits IS NULL OR slice_credits >= 0),
  lease_expires_at INTEGER, last_beat_at INTEGER, failure_reason TEXT NOT NULL DEFAULT '', torn_down_at INTEGER,
  created_at INTEGER NOT NULL, ended_at INTEGER)""",
    "CREATE INDEX agent_nodes_project ON agent_nodes(project_id, state)",
    "CREATE INDEX agent_nodes_live ON agent_nodes(state) WHERE state IN ('leased','running','handing_off')",
    """CREATE TABLE node_messages (
  project_id TEXT NOT NULL REFERENCES projects(id), seq INTEGER NOT NULL CHECK (seq >= 1),
  from_node TEXT NOT NULL DEFAULT '', to_node TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL CHECK (kind IN ('handoff','verdict','gate_request','gate_decision','control','status')),
  src_ref TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', body_sha256 TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL,
  PRIMARY KEY (project_id, seq), UNIQUE (project_id, src_ref))""",
    "CREATE TRIGGER node_messages_no_update BEFORE UPDATE ON node_messages BEGIN SELECT RAISE(ABORT, 'node messages are append-only'); END",
    "CREATE TRIGGER node_messages_no_delete BEFORE DELETE ON node_messages BEGIN SELECT RAISE(ABORT, 'node messages are append-only'); END",
    """CREATE TABLE node_audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, project_id TEXT, node_id TEXT, role TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL CHECK (actor IN ('conductor','gatekeeper','node','owner','system')),
  action TEXT NOT NULL CHECK (length(action) BETWEEN 1 AND 80), tier INTEGER CHECK (tier IS NULL OR tier BETWEEN 0 AND 6),
  target TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT 'n/a' CHECK (decision IN ('allow','deny','ask','asked_allow','asked_deny','n/a')),
  reason TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 200), ref TEXT NOT NULL DEFAULT '', hash TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX node_audit_project ON node_audit(project_id, seq)",
    "CREATE TRIGGER node_audit_no_update BEFORE UPDATE ON node_audit BEGIN SELECT RAISE(ABORT, 'node audit is append-only'); END",
    "CREATE TRIGGER node_audit_no_delete BEFORE DELETE ON node_audit BEGIN SELECT RAISE(ABORT, 'node audit is append-only'); END",
    """CREATE TABLE approvals (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), node_id TEXT NOT NULL DEFAULT '',
  tier INTEGER NOT NULL CHECK (tier BETWEEN 0 AND 6), request_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','allowed_once','allowed_project','denied','expired')),
  decided_by TEXT NOT NULL DEFAULT '', decided_at INTEGER, expires_at INTEGER NOT NULL, client_id TEXT, created_at INTEGER NOT NULL)""",
    "CREATE INDEX approvals_open ON approvals(project_id, status)",
    "CREATE UNIQUE INDEX approvals_client ON approvals(project_id, client_id) WHERE client_id IS NOT NULL",
    "ALTER TABLE tasks ADD COLUMN lane TEXT NOT NULL DEFAULT ''",
    "DROP INDEX tasks_one_live_per_dept",
    "CREATE UNIQUE INDEX tasks_one_live_per_dept_lane ON tasks(dept_id, lane) WHERE status IN ('starting','running','waiting_user')",
)

# The work list (Devin parity DV-2, docs/design/devin-parity.md; migration v7). Inert: nothing reads the table until SUTRA_WORK_V1 is on. Additive: one new table. A tag is a plain word the
# owner puts on a task or a project so the Work page can find it; `item_id` names a task or a project and has no foreign key (a tag outlives nothing it depends on and is never a reason a
# task or a project cannot be removed).
DDL_V7_WORK: tuple[str, ...] = (
    """CREATE TABLE work_tags (
  item_kind TEXT NOT NULL CHECK (item_kind IN ('task','project')), item_id TEXT NOT NULL, tag TEXT NOT NULL CHECK (length(tag) BETWEEN 1 AND 30),
  created_at INTEGER NOT NULL, PRIMARY KEY (item_kind, item_id, tag))""",
    "CREATE INDEX work_tags_tag ON work_tags(tag, item_kind)",
)

# Recipes (Devin parity DV-3; migration v8). Inert until SUTRA_RECIPES_V1 is on; additive: two new tables. A recipe is a title and a status; its words live in `recipe_versions`, which only
# ever grows (the triggers copy `node_audit`): a change is a new version, a revert is a new version that copies an old one, so the owner can always go back and nothing is lost.
DDL_V8_RECIPES: tuple[str, ...] = (
    """CREATE TABLE recipes (
  id TEXT PRIMARY KEY, title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80), status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  current_version INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
    """CREATE TABLE recipe_versions (
  recipe_id TEXT NOT NULL REFERENCES recipes(id), version INTEGER NOT NULL CHECK (version >= 1), body_json TEXT NOT NULL, sha256 TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL, PRIMARY KEY (recipe_id, version))""",
    "CREATE TRIGGER recipe_versions_no_update BEFORE UPDATE ON recipe_versions BEGIN SELECT RAISE(ABORT, 'recipe versions are append-only'); END",
    "CREATE TRIGGER recipe_versions_no_delete BEFORE DELETE ON recipe_versions BEGIN SELECT RAISE(ABORT, 'recipe versions are append-only'); END",
)

# Named projects (D426; migration v9): the owner may delete a project, which hides its team. The row, the id, the runs and the folder stay
# (DL5: a department is never removed); `hidden_at` is when it was hidden, NULL for every visible team.
DDL_V9_HIDDEN_TEAMS: tuple[str, ...] = (
    "ALTER TABLE departments ADD COLUMN hidden_at INTEGER",
)

# Project files (D451; migration v10): a project (a team) keeps files, instructions and an earlier-context memory. The BYTES stay in the attachment store (`<data>/attachments/<sha256>.<ext>`, D440);
# this table lists which stored files belong to which project and holds their flags. No foreign key to `departments`: rows outlive a hidden team (DL5), like `work_tags`. A remove sets `removed_at`
# (the row stays for audit) and the bytes are released when nothing else names them. Instructions and memory are JSON documents in `meta` (`pinstr:<dept>`, `pmem:<dept>`), no table. `tasks.input_files_json`
# is the snapshot of the files that came with one request (a list of {id, name, kind, size, chars}); older code ignores the column. DDL only: no data work, so a rollback that keeps the DDL is harmless.
DDL_V10_PROJECT_FILES: tuple[str, ...] = (
    """CREATE TABLE project_files (
  id TEXT PRIMARY KEY, dept_id TEXT NOT NULL, sha TEXT NOT NULL CHECK (length(sha) = 64), name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  kind TEXT NOT NULL CHECK (kind IN ('text','image','pdf')), size INTEGER NOT NULL CHECK (size >= 0), chars INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)), added_at INTEGER NOT NULL, removed_at INTEGER)""",
    "CREATE UNIQUE INDEX project_files_live ON project_files(dept_id, sha) WHERE removed_at IS NULL",
    "CREATE INDEX project_files_dept ON project_files(dept_id, removed_at)",
    "ALTER TABLE tasks ADD COLUMN input_files_json TEXT NOT NULL DEFAULT '[]'",
)

Migration = Sequence[str] | Callable[[Connection], None]
MIGRATIONS: tuple[Migration, ...] = (DDL_V1, _v2, DDL_V3_RECURRING, DDL_V4_AGENT_SESSIONS, DDL_V5_TURN_CHECKPOINT, DDL_V6_NODES, DDL_V7_WORK, DDL_V8_RECIPES,
                                     DDL_V9_HIDDEN_TEAMS, DDL_V10_PROJECT_FILES)
SCHEMA_VERSION = len(MIGRATIONS)
TABLES = (
    "meta", "org_charts", "chart_changes", "org_nodes", "org_edges", "departments", "tasks", "graph_nodes", "graph_edges",
    "chat_sessions", "chat_messages", "chat_segments", "atoms", "atom_ledger", "usage_ledger", "recurring", "recurring_runs", "chat_turn_checkpoint",
    "projects", "agent_nodes", "node_messages", "node_audit", "approvals", "work_tags", "recipes", "recipe_versions", "project_files",
)
