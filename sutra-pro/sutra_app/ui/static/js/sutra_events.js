/* sutra_events.js - the live-update client (work package UI-3; docs/design/ui.md sections 7, 8 and 9 X4; D80, S3-web-06).

   Events are invalidations: the page refetches what an event names (coalesced), so the stream carries no state of its own.
   One connect() makes one handle that owns one EventSource, a polling timer for when the stream is down, and a retry timer
   for when the browser has given the stream up. A classic script with ONE global, SutraEvents (see sutra_ctx.js for why);
   it needs no other script, and in node it is module.exports. */
(function (root) {
  "use strict";

  // The 17 event names of /api/events (chat.partial, ABS-7, is a streamed piece of a reply: never stored, never replayed; agent.session and chat.choice,
  // agent-sessions D130 and D131: an agent's chat opened or rolled, and a model chosen for a chat, an agent or a run). EventSource delivers a named event only
  // to a listener for that name.
  const TYPES = Object.freeze(["server.hello", "server.resync", "chat.turn", "chat.message", "chat.partial", "chart.changed", "chart.approval",
    "graph.updated", "task.updated", "atom.updated", "usage.recorded", "needs_you.changed", "connector.health",
    "connector.switch", "connector.mode", "agent.session", "chat.choice"]);
  const ERRORS_BEFORE_POLLING = 3;
  const DEFAULT_POLL_MS = 2000;
  // The wait before the page re-creates a stream the browser closed for good (readyState CLOSED), 1, 2, 4, 8, then 15 s.
  const RETRY_MS = Object.freeze([1000, 2000, 4000, 8000, 15000]);
  const CLOSED = 2;                                  // EventSource.CLOSED

  // The body of an event. One that is empty or not JSON is still an event of that type, so it arrives as {}.
  function parse(raw) {
    if (typeof raw !== "string") return {};
    try {
      return JSON.parse(raw);
    } catch (e) {
      return {};
    }
  }

  // `topics` (an array, or "a,b") narrows the stream by the part of the event name before the dot; the server always
  // passes server.* events. Added to the query of `url` without disturbing what is there.
  function streamUrl(url, topics) {
    const list = (Array.isArray(topics) ? topics : (typeof topics === "string" ? topics.split(",") : []))
      .map(t => String(t).trim()).filter(t => t !== "");
    if (list.length === 0) return url;
    const glue = url.indexOf("?") < 0 ? "?" : (url.endsWith("?") || url.endsWith("&") ? "" : "&");
    return url + glue + "topics=" + list.map(encodeURIComponent).join(",");
  }

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("SutraEvents: " + where + " failed", error);
  }

  // connect({url, topics, onEvent(type, data), onState("live"|"polling"|"offline"), EventSourceCtor, pollFn, pollMs}) -> {close(), state()}
  //
  // live       the stream is open.
  // polling    the stream failed three times in a row (or the browser has no EventSource) and pollFn runs every pollMs.
  // offline    not connected yet, closed, or down with no pollFn to fall back on.
  // The first onState can arrive before connect returns (a browser without EventSource). A callback that throws is logged
  // and never stops the stream.
  //
  // server.hello is the stream's handshake. The first one of a handle on a clean first connection is ignored (the page has
  // just loaded its data). Every other hello (the browser reconnecting, a stream this module re-created, a first hello that
  // came after an error) means events may have been missed, so it reaches onEvent as "server.resync" and the page refetches
  // what it shows. A real server.resync is forwarded as it is. Last-Event-ID is the browser's own; a stream re-created here
  // carries no `after`.
  function connect(options) {
    const o = options || {};
    if (typeof o.onEvent !== "function") throw new TypeError("SutraEvents.connect: onEvent must be a function");
    const url = streamUrl(typeof o.url === "string" && o.url !== "" ? o.url : "/api/events", o.topics);
    const pollMs = typeof o.pollMs === "number" && isFinite(o.pollMs) && o.pollMs > 0 ? o.pollMs : DEFAULT_POLL_MS;
    const Source = typeof o.EventSourceCtor === "function" ? o.EventSourceCtor : (typeof root.EventSource === "function" ? root.EventSource : null);

    let source = null;
    let current = "offline";
    let closed = false;
    let errors = 0;              // consecutive; a hello or an open stream clears it
    let attempt = 0;             // manual re-creations since the last open stream
    let ignoreHello = true;      // until the first hello, or the first error
    let pollTimer = null;
    let retryTimer = null;
    let polling = false;         // a pollFn call that has not settled

    function setState(next) {
      if (next === current) return;
      current = next;
      if (typeof o.onState !== "function") return;
      try {
        o.onState(next);
      } catch (e) {
        report("onState", e);
      }
    }

    // A callback may close the handle; nothing is called after that, not even the rest of the event that was being handled.
    function deliver(type, data) {
      if (closed) return;
      try {
        o.onEvent(type, data);
      } catch (e) {
        report("onEvent", e);
      }
    }

    // One pollFn at a time: a server that hangs must not pile up requests every pollMs.
    function poll() {
      if (polling) return;
      let result;
      try {
        result = o.pollFn();
      } catch (e) {
        report("pollFn", e);
        return;
      }
      if (result && typeof result.then === "function") {
        polling = true;
        result.then(() => { polling = false; }, e => { polling = false; report("pollFn", e); });
      }
    }

    function startPolling() {
      if (typeof o.pollFn !== "function") return setState("offline");
      if (pollTimer === null) pollTimer = setInterval(poll, pollMs);      // before the callback, so a close() in it finds the timer
      return setState("polling");
    }

    function stopPolling() {
      clearInterval(pollTimer);
      pollTimer = null;
    }

    function live() {
      errors = 0;
      attempt = 0;
      stopPolling();
      setState("live");
    }

    function scheduleRetry() {
      if (closed || retryTimer !== null) return;
      const wait = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
      attempt += 1;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        open();
      }, wait);
    }

    // An error event, or a constructor that threw. While the browser is retrying by itself (readyState CONNECTING) nothing
    // else is needed; a stream it closed for good (readyState CLOSED) is re-created here after the wait.
    function failed() {
      ignoreHello = false;
      errors += 1;
      if (errors >= ERRORS_BEFORE_POLLING) startPolling();
      if (source === null || source.readyState === CLOSED) scheduleRetry();
    }

    function receive(type, event) {
      const data = parse(event && event.data);
      if (type !== "server.hello") {
        deliver(type, data);
        return;
      }
      live();
      if (ignoreHello) {
        ignoreHello = false;
        return;
      }
      deliver("server.resync", data);
    }

    function open() {
      if (source !== null) {
        try {
          source.close();
        } catch (e) {
          /* already closed */
        }
        source = null;
      }
      let fresh;
      try {
        fresh = new Source(url);
      } catch (e) {
        report("EventSource", e);
        failed();
        return;
      }
      source = fresh;
      // Events of a stream this handle has replaced or closed are ignored.
      fresh.addEventListener("open", () => { if (fresh === source) live(); });
      fresh.addEventListener("error", () => { if (fresh === source) failed(); });
      TYPES.forEach(type => fresh.addEventListener(type, event => { if (fresh === source) receive(type, event); }));
    }

    function close() {
      closed = true;
      stopPolling();
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      if (source !== null) {
        try {
          source.close();
        } catch (e) {
          /* already closed */
        }
        source = null;
      }
      current = "offline";
    }

    if (Source === null) startPolling();
    else open();
    return {close: close, state: () => current};
  }

  // A function that runs `fn` once for any number of calls inside a window of `ms`, counted from the first call. The run gets
  // the arguments and `this` of the last call. The returned function has cancel(), which drops a pending run (a view's
  // destroy() calls it). `fn` throwing does not stop later calls from being scheduled.
  function coalesce(fn, ms) {
    const wait = typeof ms === "number" && ms > 0 ? ms : 0;
    let timer = null;
    let lastArgs = [];
    let lastThis;
    const merged = function (...args) {
      lastArgs = args;
      lastThis = this;
      if (timer !== null) return;
      timer = setTimeout(() => {
        timer = null;
        fn.apply(lastThis, lastArgs);
      }, wait);
    };
    merged.cancel = () => {
      if (timer === null) return;
      clearTimeout(timer);
      timer = null;
    };
    return merged;
  }

  const SutraEvents = {TYPES: TYPES, connect: connect, coalesce: coalesce};
  if (typeof module === "object" && module !== null && module.exports) module.exports = SutraEvents;
  else root.SutraEvents = SutraEvents;
})(globalThis);
