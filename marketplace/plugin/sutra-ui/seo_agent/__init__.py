"""seo_agent — an agent that researches and writes SEO articles, packaged to be embedded.

Nothing is imported here on purpose. `import seo_agent` must stay cheap and must not
touch the network, the data dir or the model. Import the piece you need:

    from seo_agent import store, llm, registry, loop
    from seo_agent.checks import run_checks
    from seo_agent.editing import edit_block, make_diff

The data dir lives outside the code (see store.data_dir()), so this tree can ship
read-only.
"""
