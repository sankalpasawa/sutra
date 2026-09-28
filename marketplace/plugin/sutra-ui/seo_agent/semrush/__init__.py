"""semrush/ — blog performance analytics for testlify.com, sourced from Semrush.

One package, four files, same shape as the DataForSEO integration next door
(seo_agent/tools/dfs.py) so the two read the same way:

  client.py   the one place the Semrush credential and its HTTP shape live.
  db.py       the SQLite store (blog + blog_performance_snapshot) and its queries.
  sync.py     what to fetch, how often, and how it becomes rows in db.py.
  run_sync.py the CLI entrypoint a scheduled job calls. No LLM in this path.

Nothing here is wired into the chat loop's tool registry: this is a scheduled
background pipeline, not something the SEO Writer agent calls mid-conversation.
"""
