#!/usr/bin/env node
/* test_shadow_task_spinner.js -- a running task has to LOOK running.
 *
 * THE ASK (founder, 2026-09-18): "add a spinner when the status of the shadow
 * instance is running".
 *
 * WHAT IT WAS. The status pill was a bordered word. RUNNING and STOPPED
 * differed by a border colour and a noun -- both of them perfectly still --
 * so the one state where something is actually HAPPENING was the state with
 * nothing to show for it. A founder glancing at the pane could not tell work
 * in flight from work that had ended without stopping to read.
 *
 * WHAT IT IS. The running pill leads with the same ring the agent roster
 * already spins for a live turn (.trow.run .tstate), in currentColor so it is
 * the pill's own green rather than a second accent to reconcile.
 *
 * THE THREE SURFACES ARE ONE SOURCE. The pill was printed in three places --
 * the task list row, the detail card and the workspace header. Three copies
 * meant a spinner could land on one and be forgotten on another, and the
 * founder would learn which surface to distrust. shadowTaskPillHtml is now
 * the only thing that prints a pill; test 1 asserts all three carry the ring.
 *
 * SPINNING IS READ FROM THE FACE, NOT FROM m.state. Two states are not their
 * own face -- a founder-pause (`paused` that reads NEEDS YOU) and a start
 * already accepted (`brief_confirm` that reads QUEUED). Neither is work in
 * flight, and test 4 holds them still.
 *
 * Run: node test_shadow_task_spinner.js
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function fresh(){
  const ctx = {
    console, Date, setTimeout: () => ({}),
    S: {}, SCREENS: {}, TITLES: {},
    esc: (x) => String(x == null ? "" : x).replace(/</g, "&lt;"),
    document: {
      addEventListener(){}, body: { appendChild(){} },
      createElement(){ return { setAttribute(){}, remove(){}, dataset: {} }; },
      querySelector(){ return null; },
    },
  };
  vm.createContext(ctx);
  for (const f of ["15-shadow-overlay.js", "16-shadow-home.js"])
    vm.runInContext(fs.readFileSync(
      path.join(__dirname, "static", "js", f), "utf8"), ctx);
  return ctx;
}

const M = (over) => Object.assign({
  id: "m", objective: "o", template: "fix", target_mode: "new",
  target_session: "sess-1", target_chat: "c-1", turns_used: 1, max_turns: 20,
  done_when: [],
}, over);

/* aria-hidden is part of the assertion, not incidental: the ring is
   DECORATION. The word RUNNING beside it is what carries the state, and that
   is what lets the reduced-motion rule stop the ring without losing anything. */
const SPIN = /<span class="shtpillspin" aria-hidden="true"><\/span>/;

/* the same mission through all three surfaces that draw a pill */
function surfaces(state, extra){
  const m = M(Object.assign({ id: "m-x", state }, extra));
  const ctx = fresh();
  ctx.S.shadowMissions = [m];
  ctx.S.goals = [];
  ctx.S.shadowTaskSel = "m-x";
  return { list: ctx.shadowTaskListHtml(), card: ctx.shadowTaskCardHtml(m),
           header: ctx.shadowHomeHtml() };
}

/* ONE SURFACE SINCE 2026-09-19, not three. The founder took the pill off the
   list row and the detail card -- "remove Running status in 2 places, keep
   only 1" -- so the ring has exactly one place left to be, and the other two
   are asserted to carry no pill at all rather than a still one. The rule the
   original three-surface sweep protected is intact and cheaper to hold: one
   printer, one caller. */
const SURFACES = ["header"];
const NO_PILL = ["list", "card"];

/* 1. the ask itself, on every surface that shows a status */
{
  const r = surfaces("running");
  for (const k of SURFACES)
    assert(SPIN.test(r[k]), "a running task must spin on the " + k);
  for (const k of NO_PILL)
    assert(!/shtpill/.test(r[k]), k + " must no longer print a pill at all");
  assert(/shtaskdot d-running/.test(r.list),
    "…and the list row says running through its dot");
  console.log("ok 1 running spins on the one surface that still has a pill");
}

/* 2. inside the pill and BEFORE the word -- the ring is part of the status,
      not a second indicator floating beside it */
{
  const r = surfaces("running");
  assert(/shtpill shtpill-running"><span class="shtpillspin" aria-hidden="true"><\/span>RUNNING</
    .test(r.header),
    "the ring must be the pill's first child, with RUNNING still its word");
  console.log("ok 2 the ring leads the pill and RUNNING still reads RUNNING");
}

/* 3. nothing else moves. A still pill is the whole signal that a task is NOT
      running, so any other state that spins is a lie. */
{
  for (const st of ["brief_confirm", "queued", "paused", "blocked", "done",
                    "failed", "stopped", "draft"]){
    const h = surfaces(st);
    for (const k of SURFACES)
      assert(!SPIN.test(h[k]), st + " must not spin on the " + k);
  }
  console.log("ok 3 no state other than running spins, on any surface");
}

/* 4. THE TWO STATES THAT ARE NOT THEIR OWN FACE. Both read as something else,
      and neither is work in flight. */
{
  /* READ OFF THE HEADER since 2026-09-19 -- it is the surface that still
     prints the word. The face logic under test is untouched. */
  const fc = surfaces("paused", { pause_reason: "founder_confirm" });
  assert(/NEEDS YOU/.test(fc.header) && !SPIN.test(fc.header),
    "a founder-pause reads NEEDS YOU and waits on a person, it is not running");
  const st = surfaces("brief_confirm",
    { start_requested_at: "2026-09-14T12:09:35Z" });
  assert(/QUEUED/.test(st.header) && !SPIN.test(st.header),
    "an accepted-but-unstarted start reads QUEUED and has not begun");
  console.log("ok 4 a founder-pause and an accepted start keep still");
}

/* 5. the pill is otherwise untouched -- ONE PER WORKSPACE, every state. It
      was "one per card"; the card stopped drawing one (founder, 2026-09-19)
      and the count that matters is now the whole screen's, which is the
      founder's rule stated as an assertion. */
{
  for (const state of ["running", "blocked", "done", "stopped", "failed",
                       "queued"]){
    const h = surfaces(state);
    assert.strictEqual((h.header.match(/class="shtpill /g) || []).length, 1,
      state + ": the workspace must draw exactly one pill");
    assert(!/shtpill/.test(h.card),
      state + ": the card must not draw a second one");
  }
  console.log("ok 5 exactly one pill per workspace, for every state");
}

/* 6. MOTION IS NEVER THE MESSAGE -- the rule the rest of this pane already
      keeps. The ring stops when the founder has asked the OS for less motion,
      and it CLOSES: an open top edge that is not turning reads as a broken
      circle rather than as a spinner deliberately held still. */
{
  const css = fs.readFileSync(
    path.join(__dirname, "static", "panel.css"), "utf8");
  assert(/\.shtpillspin\{[^}]*animation:sutraSpin/.test(css),
    "the ring must actually be animated");
  const rm = css.match(/@media \(prefers-reduced-motion:reduce\)\{[\s\S]*?\n\}/g)
    .filter(b => b.indexOf(".shtpillspin") !== -1);
  assert.strictEqual(rm.length, 1,
    "the ring must appear in exactly one reduced-motion block");
  assert(/\.shtpillspin\{[^}]*animation:none/.test(rm[0]),
    "reduced motion must stop the ring");
  assert(/\.shtpillspin\{[^}]*border-top-color:currentColor/.test(rm[0]),
    "a stopped ring must close, or it reads as broken rather than held still");
  console.log("ok 6 reduced motion stops the ring and closes it");
}

console.log("\nall shadow task spinner checks passed");
