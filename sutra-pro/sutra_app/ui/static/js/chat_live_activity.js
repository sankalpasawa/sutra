/* chat_live_activity.js - the honest activity timeline of a chat turn (work package STR-10; streaming design "Activity timeline", D203, D206).

   Pure helpers, no DOM. A turn's activity is its blocks: a thinking block (presence and duration only, never the thinking text), a tool block (the tool's own title and
   target, its real status and duration), a text block. Everything here is read from block fields and from the `ts` of the events that opened and closed them. Nothing is
   estimated: there is no percentage, no step count that the wire did not carry, and "N tool calls" counts real tool blocks.

     describe(block)         {kind, title, target, status, statusWord, durationMs, durationText, detail} of one block (a tool, or thinking)
     durationText(ms)        "" under a second, "1.4 s", "12 s", "1 min 5 s"
     statusWord(status, kind)  "Running", "Done", "Failed", "Interrupted, may have partly run"
     counts(blocks)          {tools, running, failed, interrupted, thinking} counted from the blocks
     summary(blocks)         "3 tool calls" / "1 tool call, 1 failed" / "" (no tool block)
     fromStored(blocks, opts)  the blocks of a stored message as the view's blocks (tool_use and its tool_result become ONE block): opts {ids, failed}
     parts(label)            {text, clock}: a label without its trailing "in 6 s" / "for 25 s", so the part that changes every second is not announced (aria-live)

   A classic script with ONE global, ChatLiveActivity; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const str = v => (typeof v === "string" ? v : "");
  const WORDS = Object.freeze({open: "Running", ok: "Done", error: "Failed", interrupted: "Interrupted, may have partly run"});
  const KIND_WORDS = Object.freeze({read: "Read", edit: "Edit", run: "Run", search: "Search", web: "Web", other: "Tool"});
  const RESULT_CHARS = 2000;

  const statusWord = status => (Object.prototype.hasOwnProperty.call(WORDS, status) ? WORDS[status] : WORDS.ok);

  function durationText(ms) {
    if (!Number.isFinite(ms) || ms < 1000) return "";
    const s = ms / 1000;
    if (s < 10) return s.toFixed(1) + " s";
    if (s < 60) return Math.round(s) + " s";
    const m = Math.floor(s / 60);
    return m + " min " + Math.round(s - m * 60) + " s";
  }

  function tsMs(ts) {
    const n = Date.parse(str(ts));
    return Number.isFinite(n) ? n : null;
  }

  function describe(block) {
    const b = isObj(block) ? block : {};
    const start = tsMs(b.startTs);
    const end = tsMs(b.endTs);
    const ms = start !== null && end !== null && end >= start ? end - start : null;
    const kind = Object.prototype.hasOwnProperty.call(KIND_WORDS, b.kind) ? b.kind : "other";
    let title = str(b.title).trim();
    if (b.type === "thinking") title = "Thinking";
    else if (title === "") title = b.status === "open" ? "Using " + (str(b.name).trim() || "a tool") : (str(b.name).trim() || KIND_WORDS[kind]);
    const lines = [];
    if (b.type === "tool_use") {
      if (str(b.target).trim() !== "") lines.push(str(b.target).trim());
      if (str(b.name).trim() !== "") lines.push(KIND_WORDS[kind] + " (" + str(b.name).trim() + ")");
    }
    return {kind, title, target: str(b.target).trim(), status: str(b.status) || "ok", statusWord: b.type === "thinking" && b.status !== "open" ? "Done" : statusWord(b.status),
      durationMs: ms, durationText: ms === null ? "" : durationText(ms), detail: lines, output: str(b.output).slice(0, RESULT_CHARS), truncated: b.truncated === true || str(b.output).length > RESULT_CHARS};
  }

  function counts(blocks) {
    const out = {tools: 0, running: 0, failed: 0, interrupted: 0, thinking: 0};
    (Array.isArray(blocks) ? blocks : []).forEach(b => {
      if (!isObj(b)) return;
      if (b.type === "thinking") out.thinking += 1;
      if (b.type !== "tool_use") return;
      out.tools += 1;
      if (b.status === "open") out.running += 1;
      else if (b.status === "error" || b.isError === true) out.failed += 1;
      else if (b.status === "interrupted") out.interrupted += 1;
    });
    return out;
  }

  function summary(blocks) {
    const c = counts(blocks);
    if (c.tools === 0) return "";
    const parts = [c.tools + " tool call" + (c.tools === 1 ? "" : "s")];
    if (c.failed > 0) parts.push(c.failed + " failed");
    if (c.interrupted > 0) parts.push(c.interrupted + " interrupted");
    return parts.join(", ");
  }

  // The stored blocks of a message as the view's blocks. A tool_use followed by its tool_result is ONE block (the pair shares an id live); blocks that share an id and are
  // text (a long text cut into several stored blocks) are ONE text block. opts {ids: the live block id of each stored element (turn.done's stored_order), failed: the turn ended badly (a tool with no result was interrupted, not done)}.
  function fromStored(blocks, options) {
    const o = isObj(options) ? options : {};
    const ids = Array.isArray(o.ids) ? o.ids : [];
    const list = (Array.isArray(blocks) ? blocks : []).filter(isObj);
    const out = [];
    const idAt = i => (typeof ids[i] === "string" && ids[i] !== "" ? ids[i] : "s" + i);
    let lastTool = null;
    list.forEach((b, i) => {
      const id = idAt(i);
      if (b.type === "tool_result") {
        if (lastTool !== null) {                                                       // the result of the tool call just before it: one block
          lastTool.status = b.is_error === true ? "error" : "ok";
          lastTool.isError = b.is_error === true;
          lastTool.output = str(b.text);
          lastTool.truncated = b.truncated === true;
          lastTool.resultSeen = true;
          lastTool = null;
          return;
        }
        out.push({id, type: "tool_use", kind: str(b.kind) || "other", name: str(b.name), title: str(b.name) || "Tool result", target: "", status: b.is_error === true ? "error" : "ok",
          text: "", isError: b.is_error === true, truncated: b.truncated === true, output: str(b.text), startTs: "", endTs: ""});
        return;
      }
      if (b.type === "tool_use") {
        const block = {id, type: "tool_use", kind: str(b.kind) || "other", name: str(b.name), title: str(b.text), target: "", status: "ok", text: "",
          isError: false, truncated: b.truncated === true, output: "", startTs: "", endTs: "", resultSeen: false};
        out.push(block);
        lastTool = block;
        return;
      }
      if (b.type === "thinking") {
        out.push({id, type: "thinking", kind: "other", name: "", title: "", target: "", status: "ok", text: "", isError: false, truncated: false, output: "", startTs: "", endTs: ""});
        return;
      }
      const prev = out[out.length - 1];
      if (b.type === "text" && prev && prev.type === "text" && prev.id === id) { prev.text += str(b.text); return; }
      out.push({id, type: "text", kind: "other", name: "", title: "", target: "", status: "ok", text: str(b.text), isError: false, truncated: b.truncated === true, output: "", startTs: "", endTs: ""});
    });
    // a tool call with no result on a turn that ended badly was cut off; on a turn that ended well it is simply done
    out.forEach(b => { if (b.type === "tool_use") { if (b.resultSeen !== true && o.failed === true) b.status = "interrupted"; delete b.resultSeen; } });
    return out;
  }

  const CLOCK = /^(.*?)\s+((?:in|for) \d+ s)$/;
  function parts(label) {
    const s = str(label);
    const m = CLOCK.exec(s);
    return m ? {text: m[1], clock: m[2]} : {text: s, clock: ""};
  }

  const ChatLiveActivity = {describe, durationText, statusWord, counts, summary, fromStored, parts, RESULT_CHARS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatLiveActivity;
  else root.ChatLiveActivity = ChatLiveActivity;
})(globalThis);
