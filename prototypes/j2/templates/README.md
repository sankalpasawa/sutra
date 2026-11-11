# templates/

`templates/<type>/generic.json` is the single source of an output type's sections: their fields, the rules code holds
them to and how their data is written as markdown. Edit the file by hand; no Python repeats it. At load time
`j2_artifact_models.py` builds each section's Pydantic model from it, `j2_rules.py` reads each section's rules from it
and `j2_template_lib.py` reads the generic templates the library specialises. `artifacts/types.json` points to the file
(`"template"`), and a type J2 creates on the fly gets one written in the same shape.

Check every file after an edit:

    python3 j2_template_lib.py

It prints each problem with the file and section it is in, and exits 1 when there is one.

## One file

    {"schema": "template-library/1", "artifact": "<type>", "kind": "generic", "version": 1, "from": "<a note>",
     "templates": [ <one per section, in document order>, <the "Document" template, last, if the type has one> ]}

## One section

| Key | What it is |
|---|---|
| `name`, `artifact`, `section`, `version`, `kind`, `description` | The template's identity. `name` is what receipts and records show. |
| `model` | The model's class name (optional; made from `name` when left out). |
| `conditions` | The condition ids the section's rules come from, for the builder's task and the records. |
| `fields` | Each field: `name`, `type`, `required`, `description`, `nullable`, and `enum` to allow only some values. |
| `objects` | Object types the fields use: `{"name": "Goal", "fields": [...]}`. |
| `rules` | The checks run on the data (rule types in `j2_rules.py`). A `ref_exists` rule's `target` is `this.<path>` or `<another type>.<path>`: that is how a document cites an earlier one. |
| `render` | How the data becomes the section's markdown (below). A section without it is not rendered from data. |
| `reply_optional` | The field names a builder's reply may leave out. Left out: the fields that are not required. |
| `requires_one_of` | `[{"fields": [...], "message": "..."}]`: the data must carry at least one of these fields. |
| `fact_fields` | `true` when the charter's own lists become fields of this section's specialised templates. |

Field types: `string`, `integer`, `boolean`, `list[string]`, `<Object>`, `list[<Object>]`.

The `Document` template is the whole document as one object. It lists only its `fields`; the objects they use are
taken from the sections (an object a section defines, or a whole section by its `model` name), so nothing is typed twice.

## Render lines

`render` is a list of blocks, joined by a new line:

    {"text": "<line>"}                           one line from the section's own fields
    {"each": "<list field>", "line": "<line>"}   one line per item of the list

A block may add `"head"` (lines always written first, such as a table's header), `"join"` (what sits between the
lines), `"unless": "<field>"` (leave out the items that have it), `"gap": true` (an empty line before the block) and
`"after_body": true` (written after the body, one per line, as the Assumption lines are).

In a line:

| Written | Means |
|---|---|
| `{field}` | the value; a list is joined with `, ` |
| `{#}`, `{_}`, `{a.b}` | the item's number, the item itself (a list of strings), a field of an object |
| `{field\|words}` | the words when the value is empty |
| `{field:nodot}`, `{field:cap}`, `{field:yesno}` | without a closing full stop, with a capital first letter, `yes` or `no` |
| `[ ... ]` | written only when every value inside it is given |
