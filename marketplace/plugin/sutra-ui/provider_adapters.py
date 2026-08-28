"""What it takes for a provider other than Claude Code to drive a Sutra chat.

THE WALL THIS REPLACES

ws_chat refused outright:

    if active_id != "claude":
        ... "no adapter has been written"

The refusal was honest -- the chat loop parses Claude Code's
`--output-format stream-json`, and running another vendor's CLI with those
flags would fail on argument parsing and look like a broken provider. But the
provider identity was hardcoded, so "add a provider" meant "edit the chat
socket", and nothing described what a provider actually has to supply.

WHAT A PROVIDER HAS TO SUPPLY

An adapter answers four questions and nothing else:

  argv()          how to start it for one turn
  encode_user()   how to hand it the operator's message
  translate()     how to turn one line of its output into Sutra frames
  capabilities    whether it can resume natively, whether it streams

THE CANONICAL FRAME VOCABULARY

`FRAMES` below is what Sutra's client speaks. It is Sutra's vocabulary, not
Claude's -- today it happens to resemble Claude's stream-json because that is
the only protocol implemented, and an adapter's whole job is to translate INTO
it. A provider that reports something with no frame here does not get a new
frame invented for it at the socket layer; either it maps onto one of these or
the vocabulary is extended deliberately, here, once.

WHY CLAUDE IS NOT ROUTED THROUGH translate()

ClaudeAdapter declares `protocol = PROTO_CLAUDE` and the socket keeps using the
existing loop for it. That loop is ~160 lines in which nearly every branch
encodes a separately MEASURED behaviour of a specific CLI build -- that
tool_result arrives on user messages, that a background agent's result is a
launch receipt rather than a completion, that tool_use never arrives as a text
delta. Re-expressing all of that through a new interface, with no second
implementation to check it against, would risk regressions that the suite
cannot see and the operator would find as a chat that quietly stops showing
tool output.

So the seam is introduced WITHOUT touching the path that works: Claude keeps
its proven loop, a second protocol runs through the generic one, and both are
reachable from the same registry. When a real second provider exists and its
adapter has exercised the generic path, the Claude branch can be folded in
against something that can contradict it. That is a transitional duplication
and it is deliberate.
"""

#: Sutra's frame vocabulary. Anything an adapter emits must be one of these.
FRAMES = (
    "session",    # {"id": ...}          provider's handle for this thread
    "token",      # {"text": ...}        answer text, streamed or whole
    "thinking",   # {}                   presence only, never the scratchpad text
    "tool",       # {"phase","id",...}   a tool call starting or finishing
    "notice",     # {"text": ...}        something the operator should know
    "retrying",   # {"detail": ...}      transient failure, turn continues
    "done",       # {...}                this turn ended
)

PROTO_CLAUDE = "claude_stream_json"
PROTO_LINES = "sutra_lines"

_REGISTRY = {}


def register(cls):
    """Register an INSTANCE, keyed by id, and hand the class back.

    Registering the class itself looks equivalent and is not: every method here
    is an instance method, so `cls.argv(bin, msg, opts)` binds self=bin and
    shifts every argument one place. That produced a spawn whose program name
    was the operator's message -- `No such file or directory: 'hello'` -- and it
    only surfaced when a real turn ran end to end.
    """
    _REGISTRY[cls.id] = cls()
    return cls


def for_provider(pid):
    """The adapter for a provider id, or None. None is the honest answer that
    produces a refusal naming what IS available -- not a crash."""
    return _REGISTRY.get(pid)


def available():
    return sorted(_REGISTRY)


class Adapter(object):
    """Base. Subclasses override what differs; the defaults are the common case."""

    id = ""
    display = ""
    protocol = PROTO_LINES

    #: Can the provider continue a thread from its own id? When False, Sutra
    #: replays its own transcript instead (sessions_store.resume_plan).
    native_resume = True
    #: Does it accept turns on stdin for the life of a process, or is it one
    #: process per turn?
    stream_input = True

    def argv(self, bin_path, msg, opts=None):
        raise NotImplementedError

    def encode_user(self, msg):
        """Bytes to write to the process's stdin for one operator message."""
        raise NotImplementedError

    def parse_line(self, line):
        """One raw output line -> an event object, or None to ignore it."""
        raise NotImplementedError

    def translate(self, ev, st):
        """(frames, done, error) for one event.

        `st` is a per-turn dict the adapter owns -- for whatever it needs to
        remember across events, such as whether any text has been seen.
        """
        raise NotImplementedError

    def session_id(self, ev):
        return None


@register
class ClaudeAdapter(Adapter):
    """Claude Code. Handled by the socket's existing stream-json loop.

    Present in the registry so provider selection is data, not an `if` in
    ws_chat, and so the refusal for anything else can name what does exist.
    translate() is deliberately not implemented -- see the module docstring.
    """

    id = "claude"
    display = "Claude Code"
    protocol = PROTO_CLAUDE
    native_resume = True
    stream_input = True


@register
class LinesAdapter(Adapter):
    """A minimal line protocol, and the proof that the seam is real.

    Not a vendor. It exists so the generic path is exercised by something that
    is NOT Claude's stream-json -- a second implementation is the only thing
    that can show the interface is an interface rather than a description of
    one program. A real provider's adapter subclasses this shape.

    The wire format is one directive per line:

        SESSION <id>          the provider's own id for this thread
        TOKEN <text>          answer text
        THINKING              it is working; no scratchpad is forwarded
        TOOL <id> <name>      a tool call started
        TOOLEND <id> <ok>     that call finished
        NOTICE <text>         something worth showing the operator
        RETRY <detail>        transient failure; the turn continues
        END                   this turn is over
        ERROR <detail>        this turn failed
    """

    id = "lines"
    display = "Line protocol (reference)"
    protocol = PROTO_LINES
    native_resume = False          # so resume_plan() replays Sutra's transcript
    stream_input = True

    def argv(self, bin_path, msg, opts=None):
        return [bin_path]

    def encode_user(self, msg):
        return (msg.replace("\n", " ") + "\n").encode("utf-8")

    def parse_line(self, line):
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        line = line.rstrip("\n")
        if not line.strip():
            return None
        head, _, rest = line.partition(" ")
        return {"op": head.strip().upper(), "arg": rest}

    def session_id(self, ev):
        return ev["arg"].strip() if ev and ev.get("op") == "SESSION" else None

    def translate(self, ev, st):
        op, arg = ev.get("op"), ev.get("arg", "")
        if op == "TOKEN":
            st["got_text"] = True
            return ([{"type": "token", "text": arg}], False, None)
        if op == "THINKING":
            return ([{"type": "thinking"}], False, None)
        if op == "TOOL":
            tid, _, name = arg.partition(" ")
            return ([{"type": "tool", "phase": "start", "id": tid,
                      "name": name, "summary": "", "command": "",
                      "caller": None}], False, None)
        if op == "TOOLEND":
            tid, _, ok = arg.partition(" ")
            return ([{"type": "tool", "phase": "end", "id": tid,
                      "ok": ok.strip().lower() not in ("0", "false", "no"),
                      "output": ""}], False, None)
        if op == "NOTICE":
            return ([{"type": "notice", "text": arg}], False, None)
        if op == "RETRY":
            return ([{"type": "retrying", "detail": arg}], False, None)
        if op == "END":
            return ([], True, None)
        if op == "ERROR":
            return ([], True, arg or "the provider reported an error")
        if op == "SESSION":
            return ([], False, None)      # the id is taken by session_id()
        # An unknown directive is NOT a crash and NOT silence: a provider that
        # grows a new one should be visible to whoever is watching the pane.
        return ([{"type": "notice",
                  "text": "unrecognised directive %r from %s" % (op, self.id)}],
                False, None)
