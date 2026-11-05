"""The node linker (orchestrator 3.4, S2-models-11, D63): a graph node and its chat session are made together, here and nowhere else.

    ensure_node(tx, spec, graph=graph)      # graph_nodes row + chat_sessions row + the denormalised chat_session_id; returns GraphNodeOut
    node_init(node, title=...)              # NodeInit for a library Node (kind -> session kind, writable for root, department, division)

`ensure_node` is the ONLY creator of a `graph_nodes` row and of a `chat_sessions` row (invariant I1: every graph node has exactly
one ACTIVE session and its `chat_session_id` names it). It is idempotent: a node that exists keeps its session, a node whose
session is gone gets a new one, and the payload is stored through `GraphStore.put_node` (False, no event, when nothing changed).

One session per node [D63]: the root's is the fixed `cs_org`; a department's and a division's are writable (the owner talks to
Identity there); the five function nodes and the step nodes have read-only working logs.
"""
import secrets
from typing import Any

from sutra_app.library.gate import GATE
from sutra_app.library.node import Node
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.db import Tx
from sutra_app.orchestrator.graph import _NODE_COLUMNS, GraphStore
from sutra_app.orchestrator.ids import ORG_SESSION_ID
from sutra_app.orchestrator.models import GraphNodeOut, NodeInit
from sutra_app.orchestrator.records import ChatSession

__all__ = ["ensure_node", "node_init", "session_kind", "WRITABLE_KINDS"]

WRITABLE_KINDS = ("root", "department", "division")      # the owner can write in these chats; function and step logs are read-only


def session_kind(node_kind: str) -> str:
    """The kind of chat session a node of `node_kind` has: root -> org, the five functions -> function, else the node's own kind."""
    if node_kind == "root":
        return "org"
    if node_kind in FUNCTIONS:
        return "function"
    if node_kind in ("department", "division", "step"):
        return node_kind
    raise ValueError(f"no chat session kind for a node of kind {node_kind!r}")


def node_init(node: Node, *, title: str | None = None, session_id: str | None = None) -> NodeInit:
    """What `ensure_node` needs for a library `Node`: its JSON, a session title (default: the node's label) and whether the
    owner may write in the session (root, department, division). The root's session id is the fixed `cs_org`."""
    sid = session_id if session_id is not None else (ORG_SESSION_ID if node.kind == "root" else None)
    return NodeInit(node=node.model_dump(mode="json"), session_title=title or node.label, writable=node.kind in WRITABLE_KINDS, session_id=sid)


def ensure_node(tx: Tx, spec: NodeInit, *, graph: GraphStore, new_session_id: Any = None) -> GraphNodeOut:
    """Make the graph node of `spec.node` and its chat session in the open transaction `tx`, or find them.

    `graph` is the one `GraphStore` of the app (its per-transaction batch keeps a transaction at one `graph.updated`);
    `new_session_id` is a callable returning a fresh `cs_<12 hex>` (default: random), so tests can make ids predictable.
    The node payload is gated with the session id filled in; a session is made only when the node has no active one."""
    payload = dict(spec.node)
    node_id, kind = payload.get("id"), payload.get("kind")
    if not isinstance(node_id, str) or not isinstance(kind, str):
        raise ValueError("a node payload carries its id and kind")
    conn, now = tx.conn, tx.now()
    active = conn.execute("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", (node_id,)).fetchone()
    new_session: ChatSession | None = None
    if active is not None:
        session_id = active["id"]
    else:
        session_id = spec.session_id or (new_session_id() if new_session_id is not None else f"cs_{secrets.token_hex(6)}")
        new_session = GATE.check("chat_session", ChatSession(
            kind=session_kind(kind), id=session_id, node_id=node_id, title=spec.session_title, writable=spec.writable,
            created_at=now, updated_at=now), ctx=tx.ctx).model
    payload["chat_session_id"] = session_id
    checked_node = GATE.check("node", payload, ctx=tx.ctx)            # both are gated before either is written, so a refusal leaves nothing
    if new_session is not None:
        s = new_session
        conn.execute(
            "INSERT INTO chat_sessions(id, node_id, kind, title, writable, status, filed_under, connector, model, provider_session_id,"
            " last_message_id, note, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.id, s.node_id, s.kind, s.title, int(s.writable), s.status, s.filed_under, s.connector, s.model, s.provider_session_id,
             s.last_message_id, s.note, s.created_at, s.updated_at))
    graph.put_node(tx, checked_node)
    row = conn.execute(f"SELECT {_NODE_COLUMNS} FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
    return graph._outs(conn, [row], detail=False)[0]
