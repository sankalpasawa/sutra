#!/usr/bin/env node
/* test_goal_control.js -- V5 slice 9: status, current attempt and controls.
   Every field asserted here comes from the EXISTING goal detail payload.
   Run: node test_goal_control.js */
"use strict";
const fs=require("fs"), path=require("path"), vm=require("vm"), assert=require("assert");
const css=fs.readFileSync(path.join(__dirname,"static","panel.css"),"utf8");
const L=f=>fs.readFileSync(path.join(__dirname,"static","js",f),"utf8");
const overlay=L("15-shadow-overlay.js"), home=L("16-shadow-home.js"), src=L("18-goal-workspace.js");

function fresh(opts){
  opts=opts||{};
  const posts=[],fetches=[],nudges=[],submits=[],focused=[];
  const ctx={ console,Date,setTimeout:f=>({f}),
    requestAnimationFrame(f){(ctx.rafs=ctx.rafs||[]).push(f);},
    esc:x=>String(x==null?"":x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"),
    SCREENS:{},TITLES:{},S:{ui:{dest:"focus"}},DESTS:["now","focus","chats"],
    scheduleRender(){},render(){},renderShadowCard(){},
    openScreen(id){ctx.opened=id;ctx.S.screen=id;},goDest(d){ctx.dest=d;},
    showNudge(t){nudges.push(t);},submitTurn(t,s){submits.push({t,s});},
    fetch(u){fetches.push(u); const b=(opts.responses||{})[u];
      if(b===undefined) return Promise.resolve({ok:false,status:404,json:()=>Promise.resolve({})});
      return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(b)});},
    document:{ addEventListener(t,f){(ctx.handlers[t]=ctx.handlers[t]||[]).push(f);},
      createElement(){return{setAttribute(){},remove(){},dataset:{},classList:{add(){}}};},
      body:{appendChild(){},classList:{add(){}}},
      querySelector(sel){ if(sel==="[data-goalchat]") return ctx.chatField||null; return null; } },
    handlers:{},posts,fetches,nudges,submits,focused };
  ctx.window=ctx; ctx.globalThis=ctx; ctx.__SHADOW_NO_AUTOBOOT=true;
  vm.createContext(ctx); vm.runInContext(overlay,ctx); vm.runInContext(home,ctx);
  ctx.shadowPost=(url,body)=>{posts.push({url,body});
    return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve({})});};
  vm.runInContext(src,ctx);
  return ctx;
}
/* payloads shaped exactly as /api/shadow/goals/{gid} returns them */
const base=(o)=>Object.assign({ id:"g-1", outcome:"the referral workflow is configured and verified",
  target_session:"01a081", attempt:1, current_mission_id:"m-1",
  checks_label:"1 of 2 checks", turn_label:"turn 11/20", turns_used:11, max_turns:20,
  block_reason:null, unmet:["end-to-end referral test passes"],
  checks:[{index:0,tier:"contains_artifact",check:"referral webhook returns 200",met:true},
          {index:1,tier:"verify",check:"end-to-end referral test passes",met:false}],
  attempts:[{attempt:1,mission_id:"m-1",ended_state:null,note:"attempt 1"}],
  learned:[], founder_guidance:[], blockers:[], history:[] }, o);
const WORKING=base({state:"working"});
const VERIFYING=base({state:"verifying", current_mission_id:"m-2",
  checks_label:"1 of 2 checks", turn_label:"turn 6/20",
  unmet:["founder signs off the migration"],
  checks:[{index:0,tier:"contains_artifact",check:"schema applied",met:true},
          {index:1,tier:"founder_confirm",check:"founder signs off the migration",met:false}]});
const BLOCKED=base({state:"blocked", attempt:2, current_mission_id:null,
  block_reason:"budget_exhausted", checks_label:"2 of 3 checks", turn_label:"turn 24/30",
  attempts:[{attempt:1,mission_id:"m-1",ended_state:"blocked",note:"budget_exhausted"},
            {attempt:2,mission_id:"m-2",ended_state:"blocked",note:"ping_pong"}],
  learned:[{id:"l-1",kind:"blocker",text:"attempt 1 stopped on budget_exhausted at 20/20 turns"},
           {id:"l-2",kind:"founder_guidance",text:"the retry path needs the mock server up first"}],
  founder_guidance:[{id:"l-2",kind:"founder_guidance",text:"the retry path needs the mock server up first"}],
  blockers:[{id:"l-1",kind:"blocker",text:"attempt 1 stopped on budget_exhausted at 20/20 turns"}]});
const DONE=base({state:"done", current_mission_id:null, checks_label:"2 of 2 checks", unmet:[],
  checks:[{index:0,tier:"contains_artifact",check:"referral webhook returns 200",met:true},
          {index:1,tier:"verify",check:"end-to-end referral test passes",met:true}],
  attempts:[{attempt:1,mission_id:"m-1",ended_state:"done",note:"ended done"}],
  learned:[{id:"l-9",kind:"result",text:"alembic upgrade head -> ok"}]});
const STOPPED=base({state:"stopped", current_mission_id:null, checks_label:"0 of 2 checks",
  attempts:[{attempt:1,mission_id:"m-1",ended_state:"stopped",note:"not worth it this quarter"}]});

let n=0; const ok=m=>console.log("ok "+(++n)+" "+m);
const panel=(ctx,d)=>ctx.goalPanelHtml(d);
const acts=(ctx,d)=>ctx.goalActions(d.state,d).map(a=>a.act);
const click=(ctx,ds)=>ctx.handlers.click.forEach(f=>f({target:{dataset:ds,closest:()=>null}}));

/* 1-5. every state communicates itself */
{
  const ctx=fresh();
  const w=panel(ctx,WORKING);
  assert(/gwst-working/.test(w) && />working</.test(w),"working named");
  assert(/Working through this chat toward: end-to-end referral test passes/.test(w),
    "and what it is doing, from state+unmet only");
  const v=panel(ctx,VERIFYING);
  assert(/gwst-verifying/.test(v),"verifying named");
  assert(/Chat says done — checking/.test(v),"verifying explained");
  assert(/Waiting on your sign-off/.test(v),"and what it waits on");
  const b=panel(ctx,BLOCKED);
  assert(/Shadow needs you/.test(b),"blocked leads with the ask");
  assert(/the turn budget ran out/.test(b),"human-readable blocker");
  const dn=panel(ctx,DONE);
  assert(/✓ Verified/.test(dn),"done named");
  assert(/not claimed/.test(dn),"verified, not claimed");
  const st=panel(ctx,STOPPED);
  assert(/Stopped/.test(st),"stopped named");
  assert(/You stopped this goal/.test(st),"and why nothing runs");
  ok("all five states communicate themselves");
}
/* 6. current attempt */
{
  const ctx=fresh();
  const out=panel(ctx,BLOCKED);
  assert(/Current attempt/.test(out),"section present");
  assert(/Attempt 2/.test(out),"the attempt number");
  assert(/turn 24\/30/.test(out),"the budget, from turn_label");
  assert(/2 of 3 checks/.test(out),"the check count");
  /* terminal goals have no current attempt */
  assert(!/Current attempt/.test(panel(ctx,DONE)),"none when done");
  assert(!/Current attempt/.test(panel(ctx,STOPPED)),"none when stopped");
  ok("current attempt renders from existing progress data");
}
/* 7. checks, and no percentage anywhere */
{
  const ctx=fresh();
  const out=panel(ctx,BLOCKED);
  assert(/referral webhook returns 200/.test(out),"check text");
  assert(/✓/.test(out)&&/○/.test(out),"met and unmet markers");
  for(const d of [WORKING,VERIFYING,BLOCKED,DONE,STOPPED]){
    const h=panel(ctx,d);
    assert(!/%/.test(h),"no percentage in "+d.state);
    assert(!/\b\d{1,3}\s*percent\b/i.test(h),"none spelled out either");
  }
  ok("checks render; no percentage anywhere");
}
/* 8. learned items, from the existing memory payload */
{
  const ctx=fresh();
  const out=panel(ctx,BLOCKED);
  assert(/What I learned/.test(out),"section present");
  assert(/mock server up first/.test(out),"the founder guidance row");
  assert(/founder guidance/.test(out),"kind humanised");
  assert(!/dedupe/.test(out)&&!/l-1/.test(out),"no storage mechanics leak");
  assert(!/What I learned/.test(panel(ctx,WORKING)),"absent when nothing learned");
  ok("learned memory renders from the existing store");
}
/* 9. attempt history */
{
  const ctx=fresh();
  const out=panel(ctx,BLOCKED);
  assert(/Attempts/.test(out),"section present");
  assert(/Attempt 1/.test(out)&&/Attempt 2/.test(out),"both attempts");
  assert(/the turn budget ran out/.test(out),"attempt 1's reason, humanised");
  assert(/the chat kept repeating itself/.test(out),"attempt 2's reason");
  assert(out.indexOf("Attempt 2")<out.indexOf("Attempt 1"),"newest first");
  /* a note that only restates the outcome is not repeated back */
  const doneOut=panel(ctx,DONE);
  assert(/Attempt 1/.test(doneOut),"the attempt is listed");
  assert(!/ended done/.test(doneOut),"but 'ended done' is not echoed");
  /* the LIVE attempt reads as the goal's state, never a guess */
  const w=panel(ctx,WORKING);
  assert(/Attempt 1/.test(w)&&/gwst-working/.test(w),"live attempt shows goal state");
  ok("attempt history renders from existing records");
}
/* 10. working actions */
{
  const ctx=fresh();
  assert.strictEqual(acts(ctx,WORKING).join(","),"stop,takeover","Stop + Take over");
  const out=panel(ctx,WORKING);
  assert(/Take over chat/.test(out)&&/Stop/.test(out),"both offered");
  ok("working offers Stop and Take over chat");
}
/* 11. blocked actions */
{
  const ctx=fresh();
  assert.strictEqual(acts(ctx,BLOCKED).join(","),"resume,extend,stop");
  const out=panel(ctx,BLOCKED);
  assert(/Answer &amp; resume/.test(out)&&/Extend budget/.test(out)&&/Stop/.test(out));
  ok("blocked offers Answer & resume, Extend budget, Stop");
}
/* 11b. verifying offers the EXISTING confirmation only when one is pending */
{
  const ctx=fresh();
  assert.strictEqual(acts(ctx,VERIFYING).join(","),"confirm,stop");
  const out=panel(ctx,VERIFYING);
  assert(/Confirm done/.test(out),"the confirmation action");
  assert(/data-goalindex="1"/.test(out),"on the outstanding founder check");
  const noPending=Object.assign({},VERIFYING,{checks:[
    {index:0,tier:"contains_artifact",check:"x",met:true}]});
  assert.strictEqual(acts(ctx,noPending).join(","),"stop",
    "never a confirm button with nothing to confirm");
  ok("verifying offers the existing confirmation action");
}
/* 12. done/stopped have no execution controls */
{
  const ctx=fresh();
  assert.strictEqual(acts(ctx,DONE).length,0);
  assert.strictEqual(acts(ctx,STOPPED).length,0);
  for(const d of [DONE,STOPPED]){
    const out=panel(ctx,d);
    assert(!/data-goalact/.test(out),"no action buttons for "+d.state);
    assert(/No execution controls/.test(out),"and it says so for "+d.state);
  }
  ok("done and stopped have no execution controls");
}
/* 13/14. guidance uses the existing path and stays goal-scoped */
{
  const ctx=fresh({responses:{"/api/shadow/goals/g-1":WORKING,"/api/shadow/goals":{goals:[]}}});
  ctx.goalTellShadow("g-1","you are missing the eligibility check");
  assert.strictEqual(ctx.posts.length,1,"one post");
  assert.strictEqual(ctx.posts[0].url,"/api/shadow/goals/g-1/act","the goal act route");
  assert.strictEqual(ctx.posts[0].body.action,"guidance","the existing guidance action");
  assert(/eligibility/.test(ctx.posts[0].body.text),"the text");
  assert.strictEqual(ctx.submits.length,0,"never reaches the chat");
  const out=panel(ctx,WORKING);
  assert(/YOU → SHADOW/.test(out),"audience labelled");
  assert(/Guidance about this goal/.test(out),"and its purpose stated");
  assert(/never sent into the chat/.test(out),"and its boundary");
  ok("guidance uses the existing goal-scoped path");
}
/* 15. blocker explanation */
{
  const ctx=fresh();
  const out=panel(ctx,BLOCKED);
  assert(/the turn budget ran out/.test(out),"reason in words");
  assert(/Still unmet: end-to-end referral test passes/.test(out),"what remains");
  assert(/2 of 3 checks · turn 24\/30 · attempt 2/.test(out),"with the progress");
  assert(/still alive/.test(out),"the chat is not dead");
  assert(!/failed/i.test(out),"never reads as failed");
  assert.strictEqual(ctx.goalBlockerCopy("ping_pong"),"the chat kept repeating itself");
  assert.strictEqual(ctx.goalBlockerCopy("some_new_reason"),"some new reason",
    "an unmapped reason degrades to readable text, never invented");
  ok("blocker is explained honestly");
}
/* 16. no fabricated activity or progress */
{
  const ctx=fresh();
  /* a payload with nothing to say must not produce narration */
  const bare=base({state:"working",unmet:[],turn_label:null,attempt:0,
    checks:[],checks_label:"0 of 0 checks",attempts:[]});
  const out=panel(ctx,bare);
  assert(/Working through this chat\./.test(out),"a plain statement only");
  assert(!/toward:/.test(out),"no invented target");
  assert(!/Current attempt/.test(out),"no attempt block without an attempt");
  assert(!/turn /.test(out),"no invented turn counter");
  assert.strictEqual(ctx.goalActivityLine({state:"nonsense"}),"",
    "an unknown state yields no narration at all");
  assert.strictEqual(ctx.goalActivityLine(null),"","and neither does nothing");
  ok("no fabricated activity or progress");
}
/* 17. actions re-fetch server state */
{
  const ctx=fresh({responses:{"/api/shadow/goals/g-1":BLOCKED,"/api/shadow/goals":{goals:[]}}});
  ctx.goalAct("g-1","confirm",{index:1}).then(()=>{
    assert.strictEqual(ctx.posts[0].body.action,"confirm","the existing action");
    assert.strictEqual(ctx.posts[0].body.index,1,"with the index");
    assert(ctx.fetches.includes("/api/shadow/goals/g-1"),"goal re-fetched");
    assert(ctx.fetches.includes("/api/shadow/goals"),"list re-fetched");
    ok("actions re-fetch server state");
  });
}
/* 18. the target chat pane is untouched */
{
  const ctx=fresh();
  const ws=(()=>{ctx.S.goalSel="g-1";ctx.S.goalDetail={"g-1":BLOCKED};
    ctx.S.goalTranscript={"01a081":[{role:"assistant",text:"still failing"}]};
    return ctx.goalWorkspaceHtml();})();
  assert(/Target chat/.test(ws),"the chat pane is still there");
  assert(/still failing/.test(ws),"showing the real transcript");
  assert(/YOU → CHAT/.test(ws),"with its own composer");
  assert.strictEqual((ws.match(/gwturns/g)||[]).length,1,"exactly one transcript");
  assert(/data-gwsid="01a081"/.test(ws),"bound to the existing session");
  ok("target chat remains intact");
}
/* 19. take over focuses the chat field; sends nothing, changes no state */
{
  const ctx=fresh();
  let focused=false;
  ctx.chatField={focus(){focused=true;},scrollIntoView(){},dataset:{goalchat:"01a081"}};
  click(ctx,{goalact:"takeover",goalid:"g-1"});
  assert(focused,"the chat composer is focused");
  assert.strictEqual(ctx.posts.length,0,"no lifecycle action fired");
  assert.strictEqual(ctx.submits.length,0,"and nothing was sent");
  assert(ctx.nudges.some(t=>/Shadow pauses/.test(t)),"and it says what will happen");
  ok("take over focuses the chat without sending");
}
/* 20. the slice 7 workspace shell and visual language are intact */
{
  const ctx=fresh();
  ctx.S.goalSel="g-1"; ctx.S.goalDetail={"g-1":BLOCKED}; ctx.S.goalTranscript={"01a081":[]};
  const ws=ctx.goalWorkspaceHtml();
  assert(/gwcols/.test(ws),"the 30/70 shell");
  assert.strictEqual((ws.match(/data-goalback/g)||[]).length,1,"one way back");
  assert(/gwpanel/.test(ws)&&/gwchat/.test(ws),"both panes");
  const block=css.split("slice 9")[1]||"";
  assert(/#B8945F/.test(block),"accent reused");
  assert(/#4A6B8B/.test(block),"review slate for verifying");
  assert(!/#e5484d/.test(block),"no new red alert system");
  const stray=block.replace(/#B8945F|#2D5A3E|#8B4A6B|#4A6B8B|#8B6B4A/g,"");
  assert(!/#[0-9a-fA-F]{6}/.test(stray),"no colours outside the v10 set");
  ok("slice 7 shell and v10 language intact");
}
/* 21. escaping */
{
  const ctx=fresh();
  const out=panel(ctx,base({state:"working",outcome:'<img src=x onerror=alert(1)>'}));
  assert(!/<img/.test(out)&&/&lt;img/.test(out),"escaped");
  ok("output is escaped");
}
setTimeout(()=>console.log("test_goal_control.js: all green"),40);
