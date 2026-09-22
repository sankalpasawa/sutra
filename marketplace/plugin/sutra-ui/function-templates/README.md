# Function templates

**Status**: v1, 15 templates. **Updated**: 2026-09-22. **Owner**: Sutra Desktop. **Tested by**: `sutra-ui/test_function_templates.py`.

Every department has five functions: Identity, Adaptation, Priority, Coordination and Audit. A template brings one function to life. It says what the function always does, what it decides, what it reads, what it may propose, when it runs, how we know it did its job, and the opening turn of its chat. Templates are helpers shipped with the app. They are not a new object in the model.

## How templates relate

Each function has one Default. A use-case template derives from its function's Default and may only add or tighten. Its floor carries every line of the Default's floor, word for word, plus its own lines. A template that drops or loosens a floor line is invalid, and the test refuses it. This is the same law the builders follow.

A department with no pick runs the Default. Adaptation proposes a use-case template, or the owner asks for one from the function's card. Either way the owner stamps the ask before anything changes.

## The fields

| Field | What it holds |
|---|---|
| `id` | `<function>/<slug>`, matching the file path |
| `function` | identity, adaptation, priority, coordination or audit |
| `name` | the name the card shows |
| `derives_from` | null for a Default, else `<function>/default` |
| `use_case` | one line: when this template is picked |
| `floor` | what it always does |
| `choices` | what it decides for itself |
| `reads` | the records it reads |
| `may_propose` | the asks it may file; it never applies a change |
| `schedule` | when it runs |
| `checks` | how we know it did its job this cycle |
| `chat_brief` | the opening turn of its chat; the app fills `{department}`, `{goal}`, `{done}`, `{rules}`, `{owner}` and `{folder}` |

## The repository

| Function | Template | Use case | File |
|---|---|---|---|
| Identity | Default | Any department | `identity/default.json` |
| Identity | Money movement | A department that moves or posts money | `identity/money-movement.json` |
| Identity | Product build | A department that builds and ships a product | `identity/product-build.json` |
| Adaptation | Default | Any department | `adaptation/default.json` |
| Adaptation | Money movement | A department that moves or posts money | `adaptation/money-movement.json` |
| Adaptation | Product build | A department that builds and ships a product | `adaptation/product-build.json` |
| Priority | Default | Any department | `priority/default.json` |
| Priority | Money movement | A department that moves or posts money | `priority/money-movement.json` |
| Priority | Product build | A department that builds and ships a product | `priority/product-build.json` |
| Coordination | Default | Any department | `coordination/default.json` |
| Coordination | Money movement | A department that moves or posts money | `coordination/money-movement.json` |
| Coordination | Product build | A department that builds and ships a product | `coordination/product-build.json` |
| Audit | Default | Any department | `audit/default.json` |
| Audit | Money movement | A department that moves or posts money | `audit/money-movement.json` |
| Audit | Product build | A department that builds and ships a product | `audit/product-build.json` |

## Adding a template

Copy the function's Default, set `id`, `name`, `derives_from` and `use_case`, keep every floor line, then add or tighten. Add a row to the table above and run the test.

---
provenance: {author: claude, date: 2026-09-22, session: b1732518, inputs: [the founder's direction of 2026-09-21 on templates per function, the five functions as ruled on the department screen, the Native builders page], review: the test in this folder's parent, confidence: high on structure, moderate on the use-case lines until a department runs them}
