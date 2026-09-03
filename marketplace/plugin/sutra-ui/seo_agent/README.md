# seo_agent

An agent that researches and writes SEO articles, packaged so a host app can import it.
It brings the loop, the tools, the checks and the editor. It does not bring a server or a
screen; the host owns those. Everything a user's install creates lives outside this
folder, so the code can ship read-only.

## The folder

    __init__.py       empty on purpose; import the piece you need
    store.py          run state, events, artifacts, knowledge, memory, library. Owns data_dir()
    llm.py            the one place a model gets called: claude-cli, anthropic or openai
    registry.py       the tool list, with costs and gates
    loop.py           the agent loop: think, do, look, think again
    prompts/          every prompt, one file each. Never inline in code
    tools/            the five work tools plus _shared.py and the DataForSEO client dfs.py
    checks/           quality gates. They report, never rewrite
    editing/          change one block and show the diff
    tests/            six suites and the runner
    HISTORY.md        the build log from the standalone app this came from

## Use it

    from seo_agent import store, loop, registry, llm

    chat = store.new_chat("First article")
    run = store.new_run(chat, "executive education")
    state = loop.start(chat, run, "write me an article")      # runs until it needs you
    state = loop.resume(chat, run, {"approved": True})        # answer, and it carries on

`loop.start` and `loop.resume` return when the run finishes or when it is waiting on the
user. Read `state["waiting_on"]` to see what it wants, and `store.get_events(chat, run)`
for the log a screen would show.

## Where the data goes

`store.data_dir()` decides, on every call:

1. `SEO_AGENT_DATA` if that env var is set,
2. otherwise `~/.sutra-ui/agents/seo`.

`store.set_data_dir(path)` overrides both for the current process. Under that root the
layout is unchanged from the standalone app: `chats/`, `knowledge/`, `library/`,
`memory.jsonl`, `connections.json`. Nothing is ever written under the package.

## The model

`llm.provider()` returns the first of these that is available:

| provider     | when                                                                 |
|--------------|----------------------------------------------------------------------|
| `claude-cli` | the `claude` binary is on PATH (or named by `SEO_AGENT_CLAUDE_BIN`) and `SEO_AGENT_NO_CLI` is not `1` |
| `anthropic`  | an `anthropic_key` is saved in connections.json                      |
| `openai`     | an `openai_key` is saved in connections.json                         |
| `None`       | none of the above; `llm.call` raises `llm.NoKey`                     |

The CLI is billed to the user's Claude subscription, never to an API key. The exact call:

    claude -p --output-format json --no-session-persistence --tools "" \
      --setting-sources "" --strict-mcp-config --disable-slash-commands \
      --system-prompt <SYSTEM> --json-schema <SCHEMA> [--model <SEO_AGENT_MODEL>]

The prompt goes in on stdin. `--model` is only added when `SEO_AGENT_MODEL` is set. The
timeout is 300 seconds. `--bare` is never passed; it breaks login. The subprocess runs
with `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID`,
`CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_PID`, `CLAUDE_CODE_MESSAGING_SOCKET`,
`CLAUDE_CODE_MESSAGING_TOKEN` and `ANTHROPIC_API_KEY` removed from its environment.

Tool calling through the CLI: the tools go into the system prompt as a "Tools you can
call" section, the conversation is flattened into one transcript, and `--json-schema`
forces the reply into `{"text": ..., "tool_calls": [{"name", "input"}]}`. Call ids are
generated locally as `call-<8 hex>`. The result has the same shape as the API providers,
so nothing above `llm.py` knows which one answered. A logged-out CLI raises
`llm.NoKey("Claude CLI is not logged in. Run `claude` once in a terminal and sign in.")`.

One wording detail matters. The CLI runs each turn with a single real tool,
`StructuredOutput`, so a plain list of "tools" makes the model emit a native tool_use for
one of them, which fails. The section therefore opens by saying none of them exist in the
session and that the only way to call one is through the `tool_calls` array
(`llm.CLI_TOOL_INTRO`). Without that sentence a live run answered "the tool isn't
available"; with it, the round trip works.

## Env vars

| var                    | what it does                                              |
|------------------------|-----------------------------------------------------------|
| `SEO_AGENT_DATA`       | the data root. Default `~/.sutra-ui/agents/seo`           |
| `SEO_AGENT_CLAUDE_BIN` | path to the claude binary. Default: `claude` on PATH      |
| `SEO_AGENT_NO_CLI`     | `1` disables the CLI provider, so a saved key is used     |
| `SEO_AGENT_MODEL`      | passed to the CLI as `--model`. Unset means the CLI's default |

## Tests

One command, from anywhere:

    seo_agent/tests/run_all.sh

It points `SEO_AGENT_DATA` at a fresh temp folder, sets `SEO_AGENT_NO_CLI=1`, runs all six
suites with `python3 -m seo_agent.tests.<suite>`, and deletes the folder. Set `PYTHON` to
use a different interpreter. The suites stub the model and DataForSEO; nothing is billed.

Python 3.9 or newer. Dependencies: `httpx` and `beautifulsoup4`, pinned in the host app's
`requirements.txt` (sutra-ui). Pure Python on purpose, so the DMG bundle can carry them;
sitemaps are read with the HTML parser rather than lxml for the same reason.
