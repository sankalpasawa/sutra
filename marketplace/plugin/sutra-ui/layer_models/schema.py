"""The JSON Schema export (A4.3.6): the dict layer_schema.DEFS holds for a class, key for key.

Pydantic's schema through the `Dialect` generator, then `export` closes the differences that exist between the two dialects:
pydantic names a definition by its class (the interface's names are kept for the classes in `names`), writes `title` (dropped),
writes `default: null` for an optional field (dropped: absent is not a value here) and leaves out `required: []` (written back)."""
from pydantic import TypeAdapter
from pydantic.json_schema import GenerateJsonSchema

_REF = '#/$defs/'


class Dialect(GenerateJsonSchema):
    """Leaves out the null default of an optional field, and keeps a nullable union a union of its own (the interface writes
    nullable(any_of(a, b)) as an anyOf inside an anyOf; pydantic would flatten it into one)."""

    def nullable_schema(self, schema):
        inner = self.generate_inner(schema['schema'])
        if inner.get('type') == 'null':
            return inner
        return {'anyOf': [inner, {'type': 'null'}]}

    def default_schema(self, schema):
        if schema.get('default') is None:
            return self.generate_inner(schema['schema'])
        return super().default_schema(schema)


def export(cls, names=None):
    """DEFS[name]-shaped dict of a model class (or of any annotation). `names` maps the class name of a nested model to its
    definition name: such a class stays {'$ref': '#/$defs/<def name>'}; any other nested class is written inline."""
    names = dict(names or {})
    js = TypeAdapter(cls).json_schema(schema_generator=Dialect)
    defs = js.pop('$defs', {})
    if '$ref' in js and len(js) == 1:
        js = defs[js['$ref'].rsplit('/', 1)[-1]]

    def fix(x):
        if isinstance(x, list):
            return [fix(v) for v in x]
        if not isinstance(x, dict):
            return x
        if 'x-defref' in x:
            return dict({'$ref': _REF + x['x-defref']}, **{k: fix(v) for k, v in x.items() if k not in ('x-defref', 'title')})
        ref = x.get('$ref')
        if isinstance(ref, str) and ref.startswith(_REF):
            cname = ref.rsplit('/', 1)[-1]
            rest = {k: fix(v) for k, v in x.items() if k not in ('$ref', 'title')}
            if cname in names:
                return dict({'$ref': _REF + names[cname]}, **rest)
            if cname in defs:
                return dict(fix(defs[cname]), **rest)
        # `title` is pydantic's own key; a property that is called title is a field of the interface and stays
        return {k: (({pk: fix(pv) for pk, pv in v.items()} if k == 'properties' and isinstance(v, dict) else fix(v)))
                for k, v in x.items() if not (k == 'title' and isinstance(v, str))}

    out = fix(js)

    def req(x):
        if isinstance(x, dict):
            if x.get('type') == 'object' and 'properties' in x and 'required' not in x:
                x['required'] = []
            for v in x.values():
                req(v)
        elif isinstance(x, list):
            for v in x:
                req(v)
    req(out)
    return out
