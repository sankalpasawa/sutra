"""`LiveTurn`: one streamed direct-chat turn, as the events a page draws (streaming design D201 to D204, D213, D217 to D222; work package STR-6).

`ChatPort.stream(acc=...)` yields what the provider and the router really did (`route`, `started`, `block_*`, `restart`, `turn_done`). A `LiveTurn` is the
server's side of one such turn: it gives every event its place in a numbered, gap-free sequence, coalesces text pieces on a real timer, says "nothing is happening
but we are alive" on silence, writes a checkpoint a crash can be recovered from, and answers the question "where is this turn now" for a page that came late.

    live = LiveTurn(session_id=..., message_id=..., generation_id=..., client_id=..., attempt_no=1, token=token, bus=bus, db=db, redact=redact)
    live.start()                                    # the ticker thread
    live.accepted()                                 # turn.accepted (seq 1), before the 202 returns
    for event in port.stream(sid, turn, cancel=live.token, acc=live.acc):
        live.on_event(event)
    live.finish(reply_id, done)                     # turn.done, after the reply is stored   (or .stopped / .failed)
    live.close()                                    # always, in a finally

Order. Everything that makes an event (a provider event, the ticker's flush, a heartbeat, the route's `turn.accepted`, `request_stop`) runs under ONE lock that also guards
the accumulator, and assigns `seq` and calls the bus inside it. So the order on the bus is the order of `seq`, a flushed text piece can never overtake a later one, and a
snapshot taken under the same lock is exactly "everything up to seq N" (the design had two locks; one is simpler and the snapshot needs the pair consistent anyway). The lock is
never held across JSON encoding of a checkpoint or any SQL.

Text. The first piece of a block is sent at once. Later pieces wait at most `coalesce_ms` (33 by default) and are joined, so a page gets about 30 frames a second however fast the
provider is. The ticker is a real timer: a trailing piece is sent at its deadline, not on the next provider event.

Honesty. Every event type has a real source (the router's decisions, the provider's own lines, the clock). `heartbeat` carries the real idle time and the real idle limit. Nothing here
estimates progress. After `request_stop` the accumulator is frozen: no further text is accumulated or sent, so what is stored equals what every tab showed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sutra_app.connectors.chat_blocks import BlockAccumulator
from sutra_app.orchestrator import live_checkpoint
from sutra_app.orchestrator.events import LIVE
from sutra_app.orchestrator.live_redact import holdback_factory

__all__ = ["LiveTurn", "LiveConfig", "SCHEMA_VERSION", "TERMINAL", "STATES", "MAX_EARLIER"]

log = logging.getLogger(__name__)
SCHEMA_VERSION = 1
STATES = ("accepted", "connecting", "running", "backoff", "stopping", "done", "stopped", "failed")
TERMINAL = ("done", "stopped", "failed")
MAX_EARLIER = 5                    # earlier tries shown in a snapshot (the stored note summarises more)
JOIN_S = 2.0                                           # how long `close` waits for the ticker
CKPT_RETRY_S = 0.05                                    # the pause between looks while a due checkpoint waits for the write in flight


@dataclass(frozen=True)
class LiveConfig:
    heartbeat_s: float = 5.0
    coalesce_ms: int = 33
    checkpoint_s: float = 1.5
    checkpoint_chars: int = 256
    structural_checkpoint_s: float = 0.25     # a state change or a block end is saved at the next tick after this much time since the last save

    @classmethod
    def from_settings(cls, settings: Any) -> "LiveConfig":
        return cls(heartbeat_s=float(getattr(settings, "live_heartbeat_s", 5.0)), coalesce_ms=int(getattr(settings, "live_coalesce_ms", 33)),
                   checkpoint_s=float(getattr(settings, "live_checkpoint_s", 1.5)))


def _ts(wall: float) -> str:
    return datetime.fromtimestamp(wall, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(wall * 1000) % 1000:03d}Z"


class LiveTurn:
    def __init__(self, *, session_id: str, message_id: int, generation_id: str, client_id: Optional[str] = None, attempt_no: int = 1, token: Any = None,
                 bus: Any = None, db: Any = None, redact: Optional[Callable[[str], str]] = None, config: Optional[LiveConfig] = None,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time, folder: str = "", provider: str = "claude",
                 start_thread: bool = True) -> None:
        self.session_id = session_id
        self.message_id = int(message_id)
        self.generation_id = generation_id
        self.client_id = client_id
        self.attempt_no = int(attempt_no)
        self.token = token
        self.config = config or LiveConfig()
        self._bus, self._db, self._redact = bus, db, redact
        self._clock, self._wall = clock, wall
        self._start_thread = start_thread
        self.acc = BlockAccumulator(folder=folder, provider=provider, redact=redact, text_filter=holdback_factory(redact) if redact is not None else None)
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._thread: Optional[threading.Thread] = None
        self._closed = False
        self._seq = 0
        self._state = "accepted"
        self._attempt = 1
        self._provider = provider
        self._model: Optional[str] = None
        self._stream_mode: Optional[str] = None
        self._idle_limit: Optional[float] = None
        self._order: list[str] = []
        self._started_at = clock()
        self._last_provider = self._started_at
        self._last_heartbeat = self._started_at
        self._pending: Optional[list] = None            # [block id, offset of the first piece, joined text, time of the first piece]
        self._sent_first: set[str] = set()
        self._stopping = False
        self._done: Optional[dict] = None
        self._ckpt_dirty = False
        self._ckpt_chars = 0
        self._ckpt_last = self._started_at
        self._ckpt_thread: Optional[threading.Thread] = None
        self.ckpt_skipped = 0
        self.ckpt_saved = 0

    # ---- reading ----------------------------------------------------------------------------------------------------------------
    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    @property
    def terminal(self) -> bool:
        with self._lock:
            return self._state in TERMINAL

    @property
    def stream_mode(self) -> Optional[str]:
        return self._stream_mode

    @property
    def stopping(self) -> bool:
        """Stop was asked for: the page saw the text freeze, so the stored ending must be the stopped one whatever the provider returned."""
        with self._lock:
            return self._stopping

    def shown_text(self) -> str:
        """What the page was shown of the reply so far (the stored text of a stopped or failed turn is built from this)."""
        with self._lock:
            return self.acc.text()

    # ---- the sequence -----------------------------------------------------------------------------------------------------------
    def publish(self, type: str, payload: Optional[dict] = None, block_id: Optional[str] = None) -> dict:
        """The one way an event leaves: number it and hand it to the bus under the lock, so bus order is `seq` order."""
        with self._lock:
            return self._publish_locked(type, payload or {}, block_id)

    def _publish_locked(self, type: str, payload: dict, block_id: Optional[str] = None) -> dict:
        self._seq += 1
        envelope: dict[str, Any] = {"v": SCHEMA_VERSION, "id": f"{self.generation_id}:{self._seq}", "conversation_id": self.session_id, "message_id": self.message_id,
                                    "generation_id": self.generation_id, "attempt": self._attempt, "seq": self._seq, "ts": _ts(self._wall()), "type": type,
                                    "payload": payload}
        if block_id is not None:
            envelope["block_id"] = block_id
        if self._bus is not None:
            self._bus.publish_one(LIVE, envelope)
        return envelope

    def _set_state(self, state: str) -> None:
        if self._state in TERMINAL or state == self._state:
            return
        self._state = state
        self._ckpt_dirty = True

    def accepted(self) -> dict:
        """`turn.accepted`: the owner's line is stored and the turn is bound. Carries the `client_id` so the sender can match it before it knows the generation id."""
        with self._lock:
            self._set_state("accepted")
            return self._publish_locked("turn.accepted", {"client_id": self.client_id, "attempt_no": self.attempt_no})

    # ---- provider and router events ---------------------------------------------------------------------------------------------
    def on_event(self, event: Any) -> None:
        kind, data = event.kind, event.data
        with self._lock:
            if self._state in TERMINAL or self._stopping:
                if kind == "turn_done":
                    self._done = data
                return
            now = self._clock()
            if kind == "route":
                self._route(data, now)
            elif kind == "started":
                self._flush_locked()
                self._last_provider = now
                self._model = data.get("model") or self._model
                self._provider = data.get("provider") or self._provider
                self._set_state("running")
                self._publish_locked("turn.started", {"provider": self._provider, "model": self._model, "session_id": data.get("session_id"),
                                                       "stream_mode": self._stream_mode, "idle_limit_s": self._idle_limit})
            elif kind == "restart":
                self._flush_locked()
                self._sent_first.clear()
                self._set_state("running")
                self._publish_locked("attempt.restart", {"attempt": self._attempt, "provider": data.get("provider") or self._provider,
                                                          "after_side_effects": bool(data.get("after_side_effects"))})
            elif kind.startswith("block_"):
                self._last_provider = now
                self._block(kind[6:], data, now)
            elif kind == "turn_done":
                self._flush_locked()
                self._done = data
            self._cv.notify_all()

    def _route(self, data: dict, now: float) -> None:
        event = data.get("event")
        if event == "plan":
            self._order = [str(p) for p in data.get("order") or []]
        elif event == "attempt":
            self._flush_locked()
            self._attempt = int(data.get("n") or self._attempt)
            self._provider = data.get("provider") or self._provider
            self._model = data.get("model") or self._model
            self._stream_mode = data.get("stream_mode") or self._stream_mode
            self._idle_limit = data.get("idle_limit_s")
            self._last_provider = now
            self._last_heartbeat = now
            self._set_state("connecting")
            self._publish_locked("turn.connecting", {"provider": self._provider, "model": self._model, "stream_mode": self._stream_mode})
        elif event == "failed":
            self._flush_locked()
            self._set_state("backoff")
            self._publish_locked("attempt.failed", {key: data.get(key) for key in ("provider", "code", "reason", "action", "delay_s", "next_provider")})

    def _block(self, what: str, data: dict, now: float) -> None:
        block_id = data.get("block_id")
        payload = {k: v for k, v in data.items() if k != "block_id"}
        if what == "delta":
            self._delta(block_id, str(payload.get("delta") or ""), int(payload.get("offset") or 0), now)
            return
        self._flush_locked()
        if what == "end":
            self._ckpt_dirty = True
        self._publish_locked("block." + what, payload, block_id)

    def _delta(self, block_id: Optional[str], text: str, offset: int, now: float) -> None:
        if not text or block_id is None:
            return
        self._ckpt_chars += len(text)
        if block_id not in self._sent_first:                  # the first piece of a block is never delayed
            self._flush_locked()
            self._sent_first.add(block_id)
            self._publish_locked("block.delta", {"delta": text, "offset": offset}, block_id)
            return
        if self._pending is not None and self._pending[0] != block_id:
            self._flush_locked()
        if self._pending is None:
            self._pending = [block_id, offset, text, now]
        else:
            self._pending[2] += text
        if now - self._pending[3] >= self.config.coalesce_ms / 1000.0:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._pending is not None:
            block_id, offset, text, _ = self._pending
            self._pending = None
            self._publish_locked("block.delta", {"delta": text, "offset": offset}, block_id)

    # ---- stopping and the end ---------------------------------------------------------------------------------------------------
    def request_stop(self) -> bool:
        """Stop was asked for (any window). In one locked step: send what was already accumulated, freeze the accumulator, ask the token, publish `turn.stopping`; so the last text
        any tab received is before `turn.stopping` and equals what is stored. True when the turn was running; False when it had ended already or Stop was asked before.
        It does not run the cancel ladder: the stop route does that in the background (`Router.chat_stop`)."""
        with self._lock:
            if self._state in TERMINAL or self._stopping:
                return False
            self._flush_locked()
            self.acc.freeze()
            self._stopping = True
            if self.token is not None:
                self.token.request()
            self._set_state("stopping")
            self._publish_locked("turn.stopping", {})
            self._cv.notify_all()
            return True

    def settle_blocks(self, status: str = "interrupted") -> None:
        """End every block that is still open (a stopped or failed turn: tools end `interrupted`), publishing each end. Call before the ending is stored."""
        with self._lock:
            self._flush_locked()
            for event in self.acc.finalize(status):
                self._publish_locked("block." + event.kind, dict(event.data), event.block_id)

    def finish(self, reply_message_id: int, done: Optional[dict] = None) -> dict:
        """`turn.done`, after the reply is stored. `done` is the ChatPort's `turn_done` data: its usage and a provider switch ride here and nowhere else."""
        done = done if done is not None else (self._done or {})
        with self._lock:
            self._flush_locked()
            payload: dict[str, Any] = {"message_id_reply": int(reply_message_id), "attempt_no": self.attempt_no, "text_len": len(str(done.get("text") or self.acc.text())),
                                       "stored_order": list(done.get("stored_order") or self.acc.stored_order())}
            if done.get("usage") is not None or done.get("usd") is not None:
                payload["usage"] = {"usage": done.get("usage"), "usd": done.get("usd")}
            if done.get("switched"):
                payload["switched"] = done["switched"]
            self._set_state("done")
            return self._publish_locked("turn.done", payload)

    def stopped(self, reply_message_id: int, exit_label: str = "cancelled") -> dict:
        with self._lock:
            self._flush_locked()
            self._set_state("stopped")
            return self._publish_locked("turn.stopped", {"message_id_reply": int(reply_message_id), "attempt_no": self.attempt_no, "exit": exit_label,
                                                          "stored_order": self.acc.stored_order()})

    def failed(self, message: str, code: str, reply_message_id: int) -> dict:
        with self._lock:
            self._flush_locked()
            self._set_state("failed")
            return self._publish_locked("turn.failed", {"message": message, "code": code, "message_id_reply": int(reply_message_id), "attempt_no": self.attempt_no,
                                                         "stored_order": self.acc.stored_order()})

    def brief(self) -> dict:
        """The four fields `ChatSessionOut.live` shows (where a page that did not start the turn can attach)."""
        with self._lock:
            return {"generation_id": self.generation_id, "seq": self._seq, "state": self._state, "attempt_no": self.attempt_no}

    # ---- the snapshot -----------------------------------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Where the turn is now, exactly up to `seq`: what a page that opened late, or lost events, seeds itself with. Pending text is sent first, so the snapshot never holds
        words the events have not carried yet."""
        with self._lock:
            self._flush_locked()
            earlier = [{"provider": e["provider"], "reason": e["reason"], "lines": e["lines"], "after_side_effects": e["after_side_effects"], "blocks": e["blocks"]}
                       for e in self.acc.earlier_attempts()[-MAX_EARLIER:]]
            return {"generation_id": self.generation_id, "message_id": self.message_id, "client_id": self.client_id, "attempt": self._attempt, "attempt_no": self.attempt_no,
                    "state": self._state, "seq": self._seq, "provider": self._provider, "model": self._model, "stream_mode": self._stream_mode,
                    "elapsed_ms": int((self._clock() - self._started_at) * 1000), "idle_limit_s": self._idle_limit, "blocks": self.acc.snapshot(), "earlier": earlier}

    # ---- the ticker -------------------------------------------------------------------------------------------------------------
    def start(self) -> None:
        if not self._start_thread or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=f"live-{self.generation_id[:8]}", daemon=True)
        self._thread.start()

    def _next_timeout(self, now: float) -> Optional[float]:
        deadlines = []
        if self._pending is not None:
            deadlines.append(self._pending[3] + self.config.coalesce_ms / 1000.0)
        if self._state in ("running", "connecting") and not self._stopping:
            deadlines.append(max(self._last_provider, self._last_heartbeat) + self.config.heartbeat_s)
        # a checkpoint deadline counts only when `_checkpoint_due_locked` would act on it: a db to write to, and either a dirty state or enough chars (a smaller
        # number of unsaved chars waits for the next structural change, and a deadline for it would pass with nothing to do and spin the ticker)
        ckpt_wait = self._db is not None and not self._closed and (self._ckpt_dirty or self._ckpt_chars >= self.config.checkpoint_chars)
        if ckpt_wait:
            deadlines.append(self._ckpt_last + (self.config.structural_checkpoint_s if self._ckpt_dirty else self.config.checkpoint_s))
        if not deadlines:
            return None
        timeout = max(0.0, min(deadlines) - now)
        if timeout <= 0 and self._ckpt_thread is not None and self._ckpt_thread.is_alive() and ckpt_wait:
            # a due checkpoint is being skipped because the previous write still runs: look again soon, never spin on a deadline that stays in the past
            timeout = max(timeout, CKPT_RETRY_S)
        return timeout

    def _run(self) -> None:
        while True:
            with self._cv:
                if self._closed:
                    return
                timeout = self._next_timeout(self._clock())
                if timeout is None or timeout > 0:
                    self._cv.wait(timeout)
                if self._closed:
                    return
            try:
                self.tick()
            except Exception:                                   # noqa: BLE001  the ticker must outlive a bad checkpoint or a bad bus
                log.exception("live turn %s: a tick failed", self.generation_id)

    def tick(self, now: Optional[float] = None) -> None:
        """One pass of the ticker: send a text piece whose deadline passed, say "alive" after silence, and write a checkpoint when one is due. Public so a test can drive it
        with its own clock; the ticker thread calls it with the real one."""
        write: Optional[dict] = None
        with self._lock:
            now = self._clock() if now is None else now
            if self._pending is not None and now - self._pending[3] >= self.config.coalesce_ms / 1000.0:
                self._flush_locked()
            if self._state in ("running", "connecting") and not self._stopping and now - max(self._last_provider, self._last_heartbeat) >= self.config.heartbeat_s:
                self._last_heartbeat = now
                self._publish_locked("heartbeat", {"idle_ms": int((now - self._last_provider) * 1000), "idle_limit_s": self._idle_limit})
            write = self._checkpoint_due_locked(now)
        if write is not None:
            self._write_checkpoint(write)

    def _checkpoint_due_locked(self, now: float) -> Optional[dict]:
        if self._db is None or self._closed:
            return None
        due = ((self._ckpt_dirty and now - self._ckpt_last >= self.config.structural_checkpoint_s)
               or (self._ckpt_chars >= self.config.checkpoint_chars and now - self._ckpt_last >= self.config.checkpoint_s))
        if not due:
            return None
        if self._ckpt_thread is not None and self._ckpt_thread.is_alive():
            self.ckpt_skipped += 1                          # the previous write is still running: skip, the data is not lost, the next due tick takes it
            return None
        self._ckpt_dirty, self._ckpt_chars, self._ckpt_last = False, 0, now
        # a shallow copy of immutable pieces (strings): cheap under the lock; the JSON and the SQL happen after it is released
        return {"generation_id": self.generation_id, "session_id": self.session_id, "message_id": self.message_id, "attempt": self._attempt, "attempt_no": self.attempt_no,
                "state": self._state, "seq": self._seq, "blocks": self.acc.snapshot()}

    def _write_checkpoint(self, row: dict) -> None:
        def work() -> None:
            try:
                live_checkpoint.save(self._db, **row)
                self.ckpt_saved += 1
            except Exception:                               # noqa: BLE001  a lost checkpoint must never fail a turn
                log.warning("live turn %s: the checkpoint was not written", self.generation_id, exc_info=True)
        thread = threading.Thread(target=work, name=f"live-ckpt-{self.generation_id[:8]}", daemon=True)
        with self._lock:
            self._ckpt_thread = thread
        thread.start()

    def checkpoint_now(self) -> None:
        """Write a checkpoint synchronously (tests, and a clean shutdown)."""
        with self._lock:
            row = {"generation_id": self.generation_id, "session_id": self.session_id, "message_id": self.message_id, "attempt": self._attempt, "attempt_no": self.attempt_no,
                   "state": self._state, "seq": self._seq, "blocks": self.acc.snapshot()}
        if self._db is not None:
            live_checkpoint.save(self._db, **row)

    def close(self) -> None:
        """Stop the ticker. Idempotent, and safe to call from a `finally` whatever happened: the join has a timeout, so a ticker stuck in a slow write cannot hang the caller."""
        with self._cv:
            if self._closed:
                return
            self._closed = True
            self._cv.notify_all()
        thread, ckpt = self._thread, self._ckpt_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(JOIN_S)
        if ckpt is not None and ckpt is not threading.current_thread():
            ckpt.join(JOIN_S)
