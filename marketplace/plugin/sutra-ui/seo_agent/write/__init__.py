"""write — the write phase: planner, architect, writer, one module per step.

The planner vets the material (gather, select, verify_sources, freeze), the architect shapes it to
its format (fmt_router, shape, enrich, brand_cards, allocate_words, section_keywords, headings), and
the writer turns it into an article (write_body, blend, wrapper, coherence, readable, sentence_pass,
slop_pass, the links pass in editing/, clean, assemble). tools/write_article.py sequences them.

Every step is `run(<inputs>) -> dict` and knows nothing about the run folder. The tool saves each
step's output as an artifact (work-<step>.json) so a run that stops resumes where it left off.
"""
