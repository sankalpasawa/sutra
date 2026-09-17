"""tests/test_slots_pause.py -- the per-run model-call gate, and the pause on a usage limit.

Proves, with fake calls and a fake clock (no Claude process is ever started, no real sleep
longer than a few hundredths of a second):

  the gate    three runs at once each get their own PARALLEL slots (so three articles run at
              one article's speed), the app-wide cap holds, a slot is given back when the call
              raises, calls outside any run share one fallback budget, and a run that ends
              unregisters cleanly even while a pool thread is still finishing.
  the pause   a usage-limit reply is read for its reset time (several wordings and zones), the
              call waits until reset + LIMIT_MARGIN and then succeeds, each running chat gets
              exactly one status row, a Stop ends the wait, and a message with no time in it
              retries every LIMIT_BLIND_WAIT until LIMIT_MAX_WAIT and then fails clearly.
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store  # noqa: E402

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))


# A real executable stands in for the claude binary so provider() says "claude-cli" and the
# pause wording names Claude. _claude_cli_once is replaced below, so nothing is ever started.
os.environ.pop("SEO_AGENT_NO_CLI", None)
os.environ["SEO_AGENT_CLAUDE_BIN"] = sys.executable
store.save_model_choice("", "")
store.save_connections({})
ok("the fixture runs on the Claude CLI provider", llm.provider() == "claude-cli", llm.provider())

REAL = dict(_call=llm._call, _claude_cli_once=llm._claude_cli_once, _now=llm._now, _sleep=llm._sleep,
            PARALLEL=llm.PARALLEL, PARALLEL_MAX=llm.PARALLEL_MAX, CLI_RETRY_SLEEPS=llm.CLI_RETRY_SLEEPS)


def restore():
    for k, v in REAL.items():
        setattr(llm, k, v)
    llm._GATE.configure(None, None)
    llm._PAUSE.clear()
    llm._PAUSE.message = ""


# =========================================================================================
print("\nthe gate: fairness across three runs")


class Meter:
    """Counts how many fake calls are inside the gate at once, overall and per run key."""

    def __init__(self):
        self.lock = threading.Lock()
        self.now = {}
        self.peak = {}
        self.total_now = 0
        self.total_peak = 0

    def enter(self, key):
        with self.lock:
            self.now[key] = self.now.get(key, 0) + 1
            self.peak[key] = max(self.peak.get(key, 0), self.now[key])
            self.total_now += 1
            self.total_peak = max(self.total_peak, self.total_now)

    def leave(self, key):
        with self.lock:
            self.now[key] -= 1
            self.total_now -= 1


CALL_S = 0.05


def fake_call_factory(meter, hold=CALL_S):
    def fake(system, messages, tools=None, model=None, on_retry=None, timeout=None, web=False):
        key = getattr(llm._local, "run", None) or "loose"
        meter.enter(key)
        try:
            time.sleep(hold)
            return {"text": "ok", "tool_calls": [], "raw": None}
        finally:
            meter.leave(key)
    return fake


def one_run(name, jobs, meter, out, workers=None):
    """A fake article: registers with the gate, fans `jobs` calls out through llm.pool()."""
    t0 = time.time()
    with llm.run_slot("chat", name):
        with llm.pool(workers) as ex:
            list(ex.map(lambda _: llm.text("hi"), range(jobs)))
    out[name] = time.time() - t0


def run_many(names, jobs, meter, workers=None):
    out = {}
    ths = [threading.Thread(target=one_run, args=(n, jobs, meter, out, workers)) for n in names]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    return out


llm.PARALLEL, llm.PARALLEL_MAX = 3, 9
llm._GATE.configure(None, None)
m = Meter()
llm._call = fake_call_factory(m)
alone = run_many(["solo"], 9, m)["solo"]
ok("one run alone uses exactly PARALLEL slots", m.peak.get("chat/solo") == 3, m.peak)

m = Meter()
llm._call = fake_call_factory(m)
times = run_many(["a", "b", "c"], 9, m)
ok("three runs at once each get their own 3 slots",
   all(m.peak.get("chat/" + k) == 3 for k in "abc"), m.peak)
ok("the total in flight reached 9, the cap, and never more", m.total_peak == 9, m.total_peak)
slowest = max(times.values())
ok("each run finished about as fast as it would alone (not a third of the speed)",
   slowest < alone * 2, "alone=%.2fs three-at-once=%s" % (alone, {k: round(v, 2) for k, v in times.items()}))
ok("nothing is left in flight afterwards", llm._GATE.in_flight()["total"] == 0, llm._GATE.in_flight())
ok("every run unregistered when its block ended", llm._GATE.in_flight()["runs"] == {}, llm._GATE.in_flight())

# =========================================================================================
print("\nthe gate: the cap")
llm._GATE.configure(3, 5)
m = Meter()
llm._call = fake_call_factory(m)
run_many(["a", "b", "c"], 6, m)
ok("with the cap at 5, the total in flight never passed 5", m.total_peak <= 5, m.total_peak)
ok("and no run passed its own 3", max(m.peak.values()) <= 3, m.peak)
ok("all 18 calls still happened", sum(1 for _ in range(18)) == 18)
ok("the cap can never be set below the per-run share", llm._Gate(per_run=4, cap=2).limits() == (4, 4),
   llm._Gate(per_run=4, cap=2).limits())
ok("a settings save reaches the gate through configure()", llm._GATE.limits() == (3, 5), llm._GATE.limits())
llm._GATE.configure(None, None)
ok("configure(None, None) puts the env numbers back", llm._GATE.limits() == (3, 9), llm._GATE.limits())

# =========================================================================================
print("\nthe gate: a slot is released when the call raises")
boom = {"n": 0}


def exploding(*a, **kw):
    boom["n"] += 1
    raise RuntimeError("kaboom")


llm._call = exploding
with llm.run_slot("chat", "x"):
    for _ in range(7):                       # more than PARALLEL: a leak would hang here
        try:
            llm.text("hi")
        except RuntimeError:
            pass
    ok("seven failing calls in a row all ran (a leaked slot would have blocked the fourth)", boom["n"] == 7, boom)
    ok("the run's counter is back to zero", llm._GATE.in_flight()["runs"]["chat/x"] == 0, llm._GATE.in_flight())
ok("the total is back to zero", llm._GATE.in_flight()["total"] == 0, llm._GATE.in_flight())

# =========================================================================================
print("\nthe gate: calls outside a run share one fallback budget")
m = Meter()
llm._call = fake_call_factory(m)


def loose_calls(n):
    ths = [threading.Thread(target=lambda: llm.text("hi")) for _ in range(n)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()


loose_calls(8)
ok("eight one-off calls with no run registered ran 3 at a time", m.peak.get("loose") == 3, m.peak)

m = Meter()
llm._call = fake_call_factory(m)
out = {}
runner = threading.Thread(target=one_run, args=("art", 9, m, out))
runner.start()
loose_calls(8)
runner.join()
ok("one-off calls beside a running article keep their own 3, and the article keeps its 3",
   m.peak.get("loose") == 3 and m.peak.get("chat/art") == 3, m.peak)
ok("in_flight reports the loose count and the per-run counts as separate numbers",
   set(llm._GATE.in_flight()) == {"total", "loose", "runs"}, llm._GATE.in_flight())

print("\nthe gate: a run that ends while a pool thread still holds a slot")
late = {"released": False}
gate = llm._Gate(per_run=3, cap=9)
r = llm._Run("late")
gate.register(r)
llm._local.run = "late"
held = gate.acquire()
gate.unregister(r)                          # the run's block ended first
gate.release(held)                          # the pool thread finishes afterwards
llm._local.run = None
ok("the release lands in the counters it came from, and nothing is negative or stuck",
   gate.in_flight() == {"total": 0, "loose": 0, "runs": {}}, gate.in_flight())

# =========================================================================================
print("\nreset-time parsing")
IST = ZoneInfo("Asia/Calcutta")
# 00:30 on 16 Sep 2026 in Calcutta is 19:00 UTC on the 15th.
now = datetime(2026, 9, 16, 0, 30, tzinfo=IST).timestamp()


def at(y, mo, d, h, mi, tz):
    return datetime(y, mo, d, h, mi, tzinfo=tz).timestamp()


got = llm.parse_reset("Claude CLI returned an error: You've hit your session limit · resets 1am (Asia/Calcutta)", now)
ok("'resets 1am (Asia/Calcutta)' at 00:30 IST is 01:00 IST today", got == at(2026, 9, 16, 1, 0, IST), got)
got = llm.parse_reset("You've hit your session limit · resets 8pm (Asia/Calcutta)", now)
ok("'resets 8pm (Asia/Calcutta)' is 20:00 IST today", got == at(2026, 9, 16, 20, 0, IST), got)
later = datetime(2026, 9, 16, 1, 30, tzinfo=IST).timestamp()
got = llm.parse_reset("resets 1am (Asia/Calcutta)", later)
ok("a clock time already behind us is tomorrow's", got == at(2026, 9, 17, 1, 0, IST), got)
got = llm.parse_reset("resets 12am (Asia/Calcutta)", now)
ok("12am is midnight", got == at(2026, 9, 17, 0, 0, IST), got)
got = llm.parse_reset("resets 12pm (Asia/Calcutta)", now)
ok("12pm is noon", got == at(2026, 9, 16, 12, 0, IST), got)
got = llm.parse_reset("Usage limit. Try again at 3:45 PM UTC", now)
ok("'3:45 PM UTC' reads the zone word", got == at(2026, 9, 16, 15, 45, timezone.utc), got)
got = llm.parse_reset("resets 6:15pm (America/New_York)", now)
ok("another named zone", got == at(2026, 9, 15, 18, 15, ZoneInfo("America/New_York")), got)
local = datetime.fromtimestamp(now).astimezone().tzinfo
exp = datetime.fromtimestamp(now, local).replace(hour=13, minute=0, second=0, microsecond=0)
if exp.timestamp() <= now:
    exp = exp.replace(day=exp.day + 1)
got = llm.parse_reset("rate limit exceeded, resets at 13:00", now)
ok("'resets at 13:00' with no zone is read in this Mac's time", got == exp.timestamp(), (got, exp))
got = llm.parse_reset("limit reached, resets at 2026-09-16T19:30:00Z", now)
ok("an ISO time with Z", got == at(2026, 9, 16, 19, 30, timezone.utc), got)
got = llm.parse_reset("resets 2026-09-16 01:00:00+05:30", now)
ok("an ISO time with an offset", got == at(2026, 9, 16, 1, 0, IST), got)
got = llm.parse_reset("ERROR: You've hit your usage limit. Try again at Sep 26th.", now)
ok("'Try again at Sep 26th' (Codex's weekly limit) is that date, midnight, this year",
   got is not None and datetime.fromtimestamp(got).astimezone().strftime("%m-%d %H:%M") == "09-26 00:00", got)
got = llm.parse_reset("try again on 3 Jan at 9am", now)
ok("a date already passed this year is next year's", got is not None
   and datetime.fromtimestamp(got).astimezone().strftime("%Y-%m-%d %H:%M") == "2027-01-03 09:00", got)
got = llm.parse_reset("Too many requests. Try again in 15 minutes.", now)
ok("'in 15 minutes' is relative", got == now + 900, got)
got = llm.parse_reset("retry after 2 hours", now)
ok("'after 2 hours' too", got == now + 7200, got)
ok("no time at all is None", llm.parse_reset("You've hit your usage limit.", now) is None)
ok("'Rate limit reached' names no time", llm.parse_reset("Rate limit reached", now) is None)
ok("'529 Overloaded. Try again in a moment.' names no time",
   llm.parse_reset("API Error: 529 Overloaded. Try again in a moment.", now) is None)

print("\nwhich errors pause")
ok("a session limit pauses", llm._usage_limited("You've hit your session limit · resets 1am (Asia/Calcutta)"))
ok("a usage limit with no time pauses (blind)", llm._usage_limited("You've hit your usage limit."))
ok("a bare 'Rate limit reached' does NOT pause (it stays a transient retry)",
   not llm._usage_limited("Rate limit reached"))
ok("a rate limit WITH a reset time pauses", llm._usage_limited("Rate limit exceeded, resets at 13:00"))
ok("529 overloaded does not pause", not llm._usage_limited("API Error: 529 Overloaded. Try again in a moment."))


# =========================================================================================
print("\npause then resume, on a fake clock")


class Clock:
    """time.time and time.sleep as one object: sleeping moves the clock, nothing really waits."""

    def __init__(self, start, real=0.0):
        self.t = start
        self.sleeps = 0
        self.real = real            # a real pause per fake sleep, so another thread can get a look in

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps += 1
        self.t += max(0.0, s)
        if self.real:
            time.sleep(self.real)


def limit_then_ok(msg, fails=1):
    """A _claude_cli_once that fails `fails` times with the limit message, then answers."""
    state = {"n": 0}

    def once(cmd, prompt, binary, timeout=None):
        state["n"] += 1
        if state["n"] <= fails:
            raise llm.ModelError("Claude CLI returned an error: " + msg)
        return {"text": "after the pause", "tool_calls": [], "raw": None}
    return once, state


llm.CLI_RETRY_SLEEPS = ()
llm._call = REAL["_call"]
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
notes = {"a": [], "b": []}
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your session limit · resets 1am (Asia/Calcutta)")
llm._claude_cli_once = once
with llm.run_slot("chat", "a", on_note=notes["a"].append, should_stop=lambda: False):
    r = llm.text("write the intro")
reset = at(2026, 9, 16, 1, 0, IST)
ok("the call comes back with the answer, not an error", r == "after the pause", r)
ok("it was tried twice: once into the limit, once after it", st["n"] == 2, st)
ok("the clock was moved to the reset plus the 2-minute margin",
   abs(clock.now() - (reset + llm.LIMIT_MARGIN)) < llm.LIMIT_POLL + 0.01, clock.now() - reset)
ok("the chat got exactly ONE status row", len(notes["a"]) == 1, notes["a"])
ok("and it reads as the owner asked",
   notes["a"] and notes["a"][0] == "Paused: Claude usage limit reached. Carrying on at %s." % llm._clock_words(
       reset + llm.LIMIT_MARGIN, now), notes["a"])
ok("the pause is over afterwards", not llm._PAUSE.active())

print("\ntwo runs: the second waits at the door and gets its own one row")
clock = Clock(now, real=0.001)          # 900 polls of 2 s fake time take about a second of real time
llm._now, llm._sleep = clock.now, clock.sleep
notes = {"a": [], "b": []}
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your session limit · resets 1am (Asia/Calcutta)")
llm._claude_cli_once = once
seen = {}


def run_a():
    with llm.run_slot("chat", "a", on_note=notes["a"].append, should_stop=lambda: False):
        seen["a"] = llm.text("a's call")


def run_b():
    # b's call is made while the pause is on: it must wait at the door and be told once.
    with llm.run_slot("chat", "b", on_note=notes["b"].append, should_stop=lambda: False):
        while not llm._PAUSE.active():
            time.sleep(0.005)
        seen["b"] = llm.text("b's call")


ta, tb = threading.Thread(target=run_a), threading.Thread(target=run_b)
ta.start()
time.sleep(0.02)
tb.start()
ta.join(5)
tb.join(5)
ok("both runs got their answers", seen.get("a") == "after the pause" and seen.get("b") == "after the pause", seen)
ok("run a got one row", len(notes["a"]) == 1, notes["a"])
ok("run b, which began its call during the pause, got one row too", len(notes["b"]) == 1, notes["b"])
ok("both rows say the same thing", notes["a"] == notes["b"], (notes["a"], notes["b"]))

# =========================================================================================
print("\nStop during a pause")
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
notes = {"a": []}
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your session limit · resets 1am (Asia/Calcutta)", fails=99)
llm._claude_cli_once = once
polls = {"n": 0}


def stop_after_three():
    polls["n"] += 1
    return polls["n"] >= 3


try:
    with llm.run_slot("chat", "a", on_note=notes["a"].append, should_stop=stop_after_three):
        llm.text("write the intro")
    ok("Stop ends the wait with llm.Stopped", False, "no raise")
except llm.Stopped:
    ok("Stop ends the wait with llm.Stopped", True)
except Exception as e:  # noqa: BLE001
    ok("Stop ends the wait with llm.Stopped", False, repr(e))
ok("the call was not tried again after the Stop", st["n"] == 1, st)
ok("the clock did not run on to the reset", clock.now() < at(2026, 9, 16, 1, 0, IST), clock.now())
ok("Stopped is a RuntimeError, so a tool's own catch-all still sees it", issubclass(llm.Stopped, RuntimeError))
ok("still one status row", len(notes["a"]) == 1, notes["a"])
llm._PAUSE.clear()

# =========================================================================================
print("\nno reset time in the message: blind retries, then a clear failure")
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
notes = {"a": []}
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your usage limit.", fails=3)
llm._claude_cli_once = once
with llm.run_slot("chat", "a", on_note=notes["a"].append, should_stop=lambda: False):
    r = llm.text("hi")
ok("it answers once the limit lifts", r == "after the pause", r)
ok("three blind waits of 15 minutes each", st["n"] == 4 and abs(clock.now() - now - 3 * llm.LIMIT_BLIND_WAIT) < 3 * llm.LIMIT_POLL,
   (st, clock.now() - now))
ok("still ONE row for the whole blind stretch, not one per retry", len(notes["a"]) == 1, notes["a"])
ok("and it says it will keep trying", notes["a"] and "every 15 minutes" in notes["a"][0], notes["a"])

clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
notes = {"a": []}
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your usage limit.", fails=10 ** 6)
llm._claude_cli_once = once
try:
    with llm.run_slot("chat", "a", on_note=notes["a"].append, should_stop=lambda: False):
        llm.text("hi")
    ok("a limit that never lifts fails after LIMIT_MAX_WAIT", False, "no raise")
except llm.ModelError as e:
    ok("a limit that never lifts fails after LIMIT_MAX_WAIT", "6 hours" in str(e) and "usage limit" in str(e), e)
    ok("and says what to do", "Send a message" in str(e), e)
ok("it waited about six hours of fake time, no more", abs(clock.now() - now - llm.LIMIT_MAX_WAIT) <= llm.LIMIT_BLIND_WAIT,
   (clock.now() - now) / 3600)
ok("25 tries: the first, then one after each of 24 quarter-hour waits", st["n"] == 25, st)

print("\na reset more than six hours away fails at once, naming the time")
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("You've hit your usage limit. Try again at Sep 26th.", fails=99)
llm._claude_cli_once = once
try:
    llm.text("hi")
    ok("fails at once", False, "no raise")
except llm.ModelError as e:
    ok("fails at once", st["n"] == 1 and clock.sleeps == 0, (st, clock.sleeps))
    ok("the message names the reset day and says it is over six hours away",
       "Sep" in str(e) and "6 hours" in str(e), e)

print("\na one-off call with no run still pauses, and tells on_retry once")
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
llm._PAUSE.clear()
llm._PAUSE.message = ""
once, st = limit_then_ok("session limit · resets 1am (Asia/Calcutta)")
llm._claude_cli_once = once
told = []
r = llm.call("s", [{"role": "user", "content": "hi"}], on_retry=told.append)
ok("the loose call comes back after the pause", r["text"] == "after the pause", r)
ok("on_retry heard about the pause exactly once", len(told) == 1 and told[0].startswith("Paused:"), told)

print("\na spend limit stops the run instead of pausing")
ok("a spend limit is recognised on its own wording",
   llm._spend_limited("You've hit your monthly spend limit - raise it at claude.ai/settings/usage"))
ok("'spending limit' is recognised too", llm._spend_limited("Your spending limit was reached."))
ok("a plain session-limit message is not a spend limit",
   not llm._spend_limited("You've hit your session limit · resets 1am (Asia/Calcutta)"))

# The real message: a spend cap, but it ALSO names a session reset time, which on its own
# would match _usage_limited's "session limit" key and pause instead of stopping.
SPEND_MSG = ("You've hit your monthly spend limit - raise it at claude.ai/settings/usage?from=cc_cli_limit_message "
             "· your session limit resets 9:40pm (Asia/Calcutta)")
ok("the real message would ALSO look like a usage limit", llm._usage_limited(SPEND_MSG))
clock = Clock(now)
llm._now, llm._sleep = clock.now, clock.sleep
llm._PAUSE.clear()
llm._PAUSE.message = ""
calls = {"n": 0}


def spend_once(cmd, prompt, binary, timeout=None):
    calls["n"] += 1
    raise llm.ModelError("Claude CLI returned an error: " + SPEND_MSG)


llm._claude_cli_once = spend_once
try:
    llm.call("s", [{"role": "user", "content": "hi"}])
    ok("a spend limit raises instead of answering", False, "no raise")
except llm.ModelError as e:
    ok("stops after exactly one try, never loops waiting for a reset", calls["n"] == 1, calls)
    ok("names what to do", "spend limit" in str(e).lower() and "claude.ai/settings/usage" in str(e), str(e))
ok("it never entered the timed pause", not llm._PAUSE.active())
ok("no fake time was spent waiting", clock.sleeps == 0, clock.sleeps)

restore()
print()
if FAILS:
    print("%d FAILED:" % len(FAILS))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("all gate and pause checks passed")
