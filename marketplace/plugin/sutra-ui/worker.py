"""worker.py -- run ONE prompt on ONE provider, headless, and hand back the text.

THE MISSING PRIMITIVE, AND NOTHING MORE. Every ingredient here already existed;
what did not exist was a way to CALL them. The three spawn recipes lived only
inline inside ws_chat (app.py:2843-3040), welded to a websocket, a resume seed,
a chat record, a switch plan and a failure/replay policy. A sub-task has none of
those and cannot borrow a socket to get at them, so this is the same three
recipes with everything socket-shaped removed.

WHAT IT IS NOT
  * not a session          one prompt, one process, one answer, then dead
  * not a pane             no websocket, no client, no `start`/`done` lifecycle
  * not a chat             writes nothing to chat_store, mints no sutra_id
  * not a switch           creates no provider_history segment, calls no
                           switch.plan/confirm, and cannot move a chat
  * not in RUNTIMES        DELIBERATELY. That registry is the address Shadow's
                           say-chain resolves (session_runtime.py:604 "one place
                           Shadow can resolve which runtime is session X"), so
                           registering a worker would make a throwaway process
                           a legal target for injected turns. A worker is owned
                           by its caller and by nothing else; the caller tracks
                           it through `on_spawn` so cancellation can reach it.

THE THREE RECIPES, which differ only in how a turn is delivered:

  claude    build_agent_args(..., session_id=None, stream_input=True)
            spawn -> send_user_frame(prompt) -> demux_turn(emit, None)
  codex     build_codex_args(..., session_id=None)   # no `resume` subcommand
            spawn -> prompt_turn(prompt, emit, None)
  deepseek  build_acp_args(bin, model)  + DEEPSEEK_API_KEY in the spawn env
            spawn (calls initialize itself) -> authenticate -> new_session
            -> prompt_turn(prompt, emit, None)

All three return the SAME 5-tuple -- codex_runtime.py:447 states the match
explicitly -- so the collection below needs no per-provider branch.

session_id IS ALWAYS None, on every path, and that is load-bearing rather than
incidental. A worker has no thread to resume; passing an id would make claude's
argv carry --resume, deepseek take session/load instead of session/new, and
codex echo the id back as its own (switch.py:120 records that measured
behaviour). None of those failures would be loud.

WHY THE ARGV BUILDERS ARE IMPORTED LAZILY
They live in app.py, and app.py imports fanout.py, which imports this. A
module-level `import app` would be a cycle. The lazy import inside a function is
the pattern this codebase already uses for exactly this
(shadow_runner.spawn_delegate_session does `import session_runtime as srt`
inside the function body); by the time any worker runs, app is fully imported.

Reads:  providers (readiness, binary, model, key), app (argv builders only)
Writes: nothing. No file, no settings, no chat record, no global.
"""
import asyncio
import os

import providers

#: A worker that has not produced a terminal event by now is abandoned and its
#: process group killed. Sub-tasks are one-shot research/analysis turns, not
#: interactive sessions -- there is no operator watching one to decide it has
#: hung. Generous rather than tight: a real turn on a slow provider can take
#: minutes, and killing a working turn is worse than waiting for a stuck one,
#: because the caller is already bounded by its own concurrency limit.
DEFAULT_TIMEOUT_S = 600

#: Providers this module can actually drive. Deliberately NOT a second opinion
#: about readiness -- providers.provider_by_id(pid)["runnable"] is the one gate
#: and it already folds in `adapter` (providers.py:1884). This exists only so a
#: caller that somehow reaches here with `gemini` gets a sentence instead of an
#: AttributeError on a runtime method that does not exist.
DRIVABLE = ("claude", "codex", "deepseek")


def _argv_builders():
    """The three builders from app.py. Lazy -- see the module header."""
    import app
    return app.build_agent_args, app.build_acp_args, app.build_codex_args


def _runtime_for(pid):
    """A FRESH runtime instance for `pid`. Same three-way choice ws_chat makes
    (app.py:2443), and the same class in every arm -- not a copy of one."""
    if pid == "claude":
        from session_runtime import SessionRuntime
        return SessionRuntime()
    if pid == "codex":
        from codex_runtime import CodexRuntime
        return CodexRuntime()
    from acp_runtime import AcpRuntime
    return AcpRuntime()


def _result(ok, text="", error=None, provider=""):
    return {"ok": bool(ok), "text": text or "", "error": error,
            "provider": provider}


async def run_one(pid, prompt, workdir, perm_mode, emit=None, model=None,
                  on_spawn=None, on_done=None, timeout=DEFAULT_TIMEOUT_S):
    """Run `prompt` on provider `pid` and return the assistant's text.

    Returns {"ok", "text", "error", "provider"} and RAISES ONLY
    asyncio.CancelledError. Every provider failure -- unrunnable, missing key,
    bad spawn, dead process, protocol error, timeout -- comes back as ok=False
    with a reason, because the caller is fanning out and one bad sub-task must
    not take down the other fourteen.

    `emit` is an async frame sink of the same shape ws_chat passes to
    demux_turn/prompt_turn. Passing None discards the provider's frames, which
    is what a sub-task usually wants: fifteen concurrent token streams into one
    pane would interleave into noise. The CALLER emits the progress the operator
    sees (fanout.py composes `tool` frames), not this function.

    `on_spawn(rt)` / `on_done(rt)` let the caller track the live runtime so a
    Stop or a disconnect can kill it. on_spawn is called AFTER the process
    exists and BEFORE the first turn, so there is no window where a running
    child is untracked.
    """
    prov = providers.provider_by_id(pid)
    if prov is None:
        return _result(False, error="unknown provider %r" % (pid,), provider=pid)
    if not prov["runnable"]:
        # The SAME gate ws_chat applies at connect and _chat_local_provider
        # applies on a recorded provider. No second notion of readiness.
        return _result(False, error=prov["reason"] or "not runnable", provider=pid)
    if pid not in DRIVABLE:
        return _result(False, error="no headless adapter for %r" % (pid,),
                       provider=pid)
    agent_bin = prov["bin_path"]
    if not agent_bin:
        return _result(False, error=prov["reason"] or "no binary", provider=pid)

    if not providers.workdir_allowed(workdir):
        # Same confinement every other spawn path applies: the workdir becomes
        # the agent's cwd, and an arbitrary one turns a sub-task into a read
        # oracle over the whole disk.
        return _result(False, error="workdir %s is not allowed" % (workdir,),
                       provider=pid)

    key = None
    if pid == "deepseek":
        # Through the resolver, never os.environ -- providers.py:1597 is the one
        # resolution path, and it is what catches a keychain/marker divergence.
        key, why = providers.deepseek_key_for_request()
        if not key:
            return _result(False, error=why, provider=pid)

    chosen = providers.clean_model(model, pid) or providers.stored_model(pid)
    build_agent_args, build_acp_args, build_codex_args = _argv_builders()

    if pid == "claude":
        # mcp=False: a sub-task has no business writing proposals through
        # Sutra's own MCP tools, and each --mcp-config spawns another python
        # server per worker. The default stays True, so no existing caller
        # changes shape.
        args = build_agent_args(agent_bin, prompt, perm_mode, session_id=None,
                                model=chosen, stream_input=True, mcp=False)
    elif pid == "codex":
        args = build_codex_args(agent_bin, perm_mode, workdir, model=chosen,
                                session_id=None)
    else:
        args = build_acp_args(agent_bin, chosen)

    rt = _runtime_for(pid)
    texts = []

    async def collect(frame):
        # `token` is the one frame every transport emits for assistant prose --
        # SessionRuntime, CodexRuntime and AcpRuntime all translate their native
        # events into it. Collecting here rather than reading a return value
        # because none of the three returns the text; ws_chat streams it to a
        # socket and a worker has to keep it.
        if frame.get("type") == "token":
            texts.append(frame.get("text") or "")
        if emit is not None:
            await emit(frame)

    spawned = False
    try:
        spawn_env = {"DEEPSEEK_API_KEY": key} if pid == "deepseek" else None
        try:
            await rt.spawn(args, workdir, tuple(args), env=spawn_env)
        except OSError as exc:
            return _result(False, error="could not start %s: %s" % (agent_bin, exc),
                           provider=pid)
        spawned = True
        if on_spawn is not None:
            on_spawn(rt)

        if pid == "deepseek":
            # BEFORE session/new. acp_runtime.authenticate's docstring carries
            # the wire evidence: the env key alone leaves the session on Gemini
            # auth, which then refuses with a Gemini error on a DeepSeek turn.
            await rt.authenticate(key)
            await rt.new_session(workdir, perm_mode, session_id=None,
                                 mcp_servers=None)

        if pid == "claude":
            await rt.send_user_frame(prompt)
            turn = rt.demux_turn(collect, None)
        else:
            turn = rt.prompt_turn(prompt, collect, None)

        (_sid, _got_text, got_result,
         result_error, eof) = await asyncio.wait_for(turn, timeout)

        text = "".join(texts).strip()
        if result_error:
            # Partial text is KEPT alongside the error. A turn that answered for
            # a page and then hit a rate limit has produced something the
            # synthesis can still use, and discarding it would turn a degraded
            # success into a total loss.
            return _result(False, text=text, error=str(result_error)[:600],
                           provider=pid)
        if eof and not got_result:
            return _result(False, text=text,
                           error="%s exited before answering" % pid, provider=pid)
        if not text:
            return _result(False, error="%s returned no text" % pid, provider=pid)
        return _result(True, text=text, provider=pid)

    except asyncio.TimeoutError:
        return _result(False, text="".join(texts).strip(),
                       error="%s did not answer within %ds" % (pid, timeout),
                       provider=pid)
    except asyncio.CancelledError:
        # The ONLY exception that propagates. A cancelled worker is not a failed
        # sub-task -- the operator stopped the whole job -- and swallowing it
        # here would leave asyncio.gather believing the task completed.
        raise
    except Exception as exc:      # noqa: BLE001 -- one bad worker, not fifteen
        return _result(False, text="".join(texts).strip(),
                       error="%s failed: %s" % (pid, str(exc)[:400]), provider=pid)
    finally:
        # UNCONDITIONAL, and it runs on the cancellation path too. kill_group
        # signals the process GROUP (spawn used start_new_session=True), so the
        # CLI's own helpers go with it -- the same reason ws_chat's finally
        # calls it rather than terminating the direct child.
        try:
            rt.kill_group()
        except Exception:
            pass
        try:
            rt.clear()
        except Exception:
            pass
        if spawned and on_done is not None:
            try:
                on_done(rt)
            except Exception:
                pass
