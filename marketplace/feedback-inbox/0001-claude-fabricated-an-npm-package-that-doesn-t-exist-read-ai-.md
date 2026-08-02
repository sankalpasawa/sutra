---
issue: 1
title: "Claude fabricated an npm package that doesn't exist (@read-ai/mcp-server)"
author: Harsh99-ship-it
state: OPEN
created: 2026-04-24T13:18:12Z
updated: 2026-04-24T13:18:12Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/1
comments: []
---

# #1 Claude fabricated an npm package that doesn't exist (@read-ai/mcp-server)

**Author:** Harsh99-ship-it  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-24T13:18:12Z  |  **Updated:** 2026-04-24T13:18:12Z
**URL:** https://github.com/sankalpasawa/sutra/issues/1

---

A Claude session using Sutra generated code that referenced @read-ai/mcp-server 
as an npm package for Read.ai integration. This package does not exist on the 
npm registry — it was fabricated.

The correct Read.ai integration path is a remote hosted MCP server at 
https://api.read.ai/mcp (Streamable HTTP + OAuth 2.1), added as a custom 
Claude connector. No npm package is involved.

The fabricated package made it into:
- MEETING_AUTOMATION_SETUP.md (Option C config block)
- connector/read-ai-to-gdoc/read_ai_to_gdoc.py (REST API approach)

This was caught and corrected manually by the team. Flagging so the Sutra 
team is aware — hallucinated package names in generated code are a real 
cost when they make it into committed files.

Repo where this happened: https://github.com/vinitharmalkar/Vinit
