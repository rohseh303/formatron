"""Deterministic, seeded JSON-schema corpus for the GrammarGuard benchmark.

The corpus is *generated*, never committed.  ``specs()`` returns a list of
cheap :class:`Spec` descriptors (id, family, category, expectation and a few
parameters); ``materialize(spec)`` turns one descriptor into the actual JSON
schema.  Both are fully deterministic in ``seed``, so a child process can
rebuild any single schema from its id without the parent having to pickle a
100k-member enum or an 8 MB const string.

Record format (``records()`` / ``--dump``)::

    {"id": ..., "family": ..., "category": "normal"|"adversarial",
     "expect": "admit"|"reject"|"either", "schema": {...}}

Expectation semantics:

- ``admit``  - a realistic schema; a rejection is a false positive.
- ``reject`` - a resource attack that no bounded engine should accept;
  admitting it is not a bug by itself but must be fast and must not hang.
- ``either`` - an engine may reasonably accept or reject; the only
  requirements are "no hang / crash / OOM" and "if admitted, the output must
  validate".

Run ``python -m benchmarks.grammar_guard.corpus --stats`` for family counts and
``--dump path.jsonl`` to write the materialized corpus (large!).
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import random
import sys
import typing

SEED = 20260912
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
ID_PREFIX = "https://grammar-guard.dev/schemas/"

# --------------------------------------------------------------------------
# Pools
# --------------------------------------------------------------------------

KEY_POOL = [
    "id", "name", "email", "first_name", "last_name", "username", "age",
    "status", "type", "kind", "tags", "items", "children", "value", "count",
    "total", "price", "quantity", "currency", "amount", "description",
    "title", "body", "text", "content", "url", "image", "created_at",
    "updated_at", "timestamp", "date", "start_date", "end_date", "address",
    "street", "city", "state", "zip", "country", "phone", "lat", "lng",
    "enabled", "active", "visible", "published", "version", "meta",
    "metadata", "data", "payload", "result", "error", "message", "code",
    "reason", "label", "category", "group", "role", "permissions", "scope",
    "token", "order", "customer", "product", "sku", "inventory", "rating",
    "reviews", "comment", "author", "owner", "priority", "severity",
    "project", "event", "source", "target", "user_id", "order_id",
    "product_id", "balance", "limit", "offset", "page", "size", "sort",
    "filter", "query", "options", "settings", "config", "theme", "locale",
    "language", "timezone", "format", "width", "height", "depth", "color",
    "weight", "unit", "min", "max", "avg", "first", "last", "next", "prev",
    "head", "tail", "left", "right", "node", "edges", "root", "leaf",
    "level", "path", "file", "folder", "notes", "score", "rank", "flags",
]

WORD_POOL = [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "red", "green", "blue", "yellow", "black", "white", "orange", "purple",
    "small", "medium", "large", "xlarge", "pending", "active", "done",
    "failed", "queued", "running", "paused", "archived", "draft", "public",
    "private", "internal", "admin", "user", "guest", "owner", "editor",
    "viewer", "usd", "eur", "gbp", "jpy", "cad", "aud", "north", "south",
    "east", "west", "monday", "tuesday", "wednesday", "thursday", "friday",
    "cat", "dog", "bird", "fish", "horse", "apple", "banana", "cherry",
    "low", "high", "critical", "info", "warning", "error", "debug", "trace",
]

PATTERN_POOL = {
    "email": r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}",
    "iso_date": r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])",
    "iso_datetime": r"[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z",
    "uuid": r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    "phone": r"\+?[0-9]{1,3}[- ]?[0-9]{3}[- ]?[0-9]{4}",
    "hex_color": r"#[0-9a-fA-F]{6}",
    "slug": r"[a-z0-9]+(-[a-z0-9]+)*",
    "ipv4": r"((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])",
    "semver": r"[0-9]+\.[0-9]+\.[0-9]+",
    "ticket_id": r"[A-Z]{3}-[0-9]{6}",
    "time_hhmm": r"([01][0-9]|2[0-3]):[0-5][0-9]",
    "alnum_token": r"[A-Za-z0-9_]{4,32}",
}

# Unicode strings are written with escapes so the source stays plain ASCII.
UNICODE_POOL = [
    "日本語", "中文字符", "한국어", "Ελληνικά",
    "русский", "العربية", "עברית",
    "हिन\u094dदी", "ไทย", "\U0001F600", "\U0001F44D\U0001F3FD", "\U0001F680\U0001F315",
    "\U0001F1EF\U0001F1F5", "e\u0301", "a\u0308\u0301", "\u200b", "\ufeff", "Ω≈ç√∫",
    "ｆｕｌｌｗｉｄｔｈ", "\U0001F9D1\u200d\U0001F91D\u200d\U0001F9D1",
    "\U0001D518\U0001D52B\U0001D526\U0001D520\U0001D52C\U0001D521\U0001D522", "\u202ereversed\u202c",
    "Ⅷ", "ǅ", "ﬃ", "\U0001F3F3\ufe0f\u200d\U0001F308",
]


# --------------------------------------------------------------------------
# Spec
# --------------------------------------------------------------------------


@dataclasses.dataclass
class Spec:
    id: str
    family: str
    category: str  # "normal" | "adversarial"
    expect: str  # "admit" | "reject" | "either"
    params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, typing.Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, typing.Any]) -> "Spec":
        return cls(d["id"], d["family"], d["category"], d["expect"], dict(d.get("params", {})))


def _spec_list(family: str, category: str, n: int, expect, params_fn) -> list[Spec]:
    prefix = "normal" if category == "normal" else "adv"
    out = []
    for i in range(n):
        params = params_fn(i)
        exp = expect(params) if callable(expect) else expect
        out.append(Spec(f"{prefix}/{family}/{i:04d}", family, category, exp, params))
    return out


# --------------------------------------------------------------------------
# Building blocks (all take an explicit rng)
# --------------------------------------------------------------------------


def _keys(rng: random.Random, n: int, pool: list[str] | None = None) -> list[str]:
    pool = pool or KEY_POOL
    if n <= len(pool):
        return rng.sample(pool, n)
    out = list(pool)
    i = 0
    while len(out) < n:
        out.append(f"{pool[i % len(pool)]}_{i // len(pool) + 1}")
        i += 1
    return out[:n]


def _primitive(rng: random.Random, allow_enum: bool = True) -> dict:
    roll = rng.random()
    if roll < 0.30:
        s: dict = {"type": "string"}
        r2 = rng.random()
        if r2 < 0.2:
            s["maxLength"] = rng.randint(4, 64)
        elif r2 < 0.3:
            s["minLength"] = rng.randint(1, 4)
            s["maxLength"] = s["minLength"] + rng.randint(1, 40)
        return s
    if roll < 0.50:
        s = {"type": "integer"}
        r2 = rng.random()
        if r2 < 0.25:
            s["minimum"] = 0
        elif r2 < 0.35:
            s["exclusiveMinimum"] = 0
        return s
    if roll < 0.62:
        s = {"type": "number"}
        if rng.random() < 0.25:
            s["minimum"] = 0
        return s
    if roll < 0.72:
        return {"type": "boolean"}
    if roll < 0.78:
        return {"type": "null"}
    if roll < 0.90 and allow_enum:
        k = rng.randint(2, 8)
        return {"enum": rng.sample(WORD_POOL, k)}
    if roll < 0.95:
        return {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {"type": "array", "items": {"type": rng.choice(["string", "integer", "number"])}}


def _object(rng: random.Random, n_props: int, depth: int, optional_max: int = 3,
            keys: list[str] | None = None) -> dict:
    keys = keys or _keys(rng, n_props)
    props = {}
    for k in keys:
        if depth > 0 and rng.random() < 0.35:
            props[k] = _object(rng, rng.randint(1, 4), depth - 1, optional_max=1)
        elif depth > 0 and rng.random() < 0.15:
            props[k] = {"type": "array", "items": _object(rng, rng.randint(1, 3), depth - 1, optional_max=0),
                        **({"maxItems": rng.randint(1, 8)} if rng.random() < 0.5 else {})}
        else:
            props[k] = _primitive(rng)
    n_opt = min(optional_max, len(keys), rng.randint(0, optional_max)) if optional_max else 0
    optional = set(rng.sample(keys, n_opt)) if n_opt else set()
    required = [k for k in keys if k not in optional]
    return {"type": "object", "properties": props, "required": required}


def _root(schema: dict, spec_id: str) -> dict:
    out = {"$schema": SCHEMA_URI, "$id": ID_PREFIX + spec_id}
    out.update(schema)
    return out


# --------------------------------------------------------------------------
# Normal families
# --------------------------------------------------------------------------


def _flat_object(rng, p):
    return _object(rng, p["n_props"], 0, optional_max=p["n_optional"])


def _nested_object(rng, p):
    def build(d):
        keys = _keys(rng, rng.randint(1, p["branching"]))
        props = {}
        for k in keys:
            props[k] = build(d - 1) if d > 1 else _primitive(rng)
        if d > 1 and rng.random() < 0.3:
            props["extra_" + keys[0]] = _primitive(rng)
        return {"type": "object", "properties": props, "required": list(props)}
    return build(p["depth"])


def _array_of_objects(rng, p):
    item = _object(rng, p["item_props"], 1, optional_max=1)
    arr: dict = {"type": "array", "items": item}
    if p["bounds"] == "min":
        arr["minItems"] = 1
    elif p["bounds"] == "max":
        arr["maxItems"] = p["max_items"]
    elif p["bounds"] == "both":
        arr["minItems"] = 1
        arr["maxItems"] = p["max_items"]
    if p["root"] == "array":
        return arr
    return {"type": "object", "properties": {"items": arr, "total": {"type": "integer", "minimum": 0}},
            "required": ["items", "total"]}


def _enum_fields(rng, p):
    props = {}
    for i in range(p["n_enums"]):
        kind = p["kinds"][i]
        n = p["sizes"][i]
        if kind == "string":
            vals = [f"{rng.choice(WORD_POOL)}_{j}" for j in range(n)] if n > len(WORD_POOL) else rng.sample(WORD_POOL, n)
        elif kind == "int":
            vals = rng.sample(range(-100, 1000), n)
        elif kind == "mixed":
            vals = rng.sample(WORD_POOL, min(n, 3)) + [1, 2.5, True, None][: max(1, n - 3)]
        else:  # const
            vals = None
        props[f"field_{i}"] = {"const": rng.choice(WORD_POOL)} if vals is None else {"enum": vals}
    props["id"] = {"type": "integer"}
    return {"type": "object", "properties": props, "required": list(props)}


def _enum_medium(rng, p):
    n = p["size"]
    if p["kind"] == "string":
        vals = [f"{WORD_POOL[j % len(WORD_POOL)]}_{j}" for j in range(n)]
    else:
        vals = list(range(n))
    return {"type": "object", "properties": {"choice": {"enum": vals}, "id": {"type": "integer"}},
            "required": ["choice", "id"]}


def _optional_fields(rng, p):
    keys = _keys(rng, p["n_total"])
    props = {k: _primitive(rng, allow_enum=False) for k in keys}
    optional = set(keys[: p["n_optional"]])
    return {"type": "object", "properties": props, "required": [k for k in keys if k not in optional]}


def _anyof_union(rng, p):
    kind = p["kind"]
    if kind == "root":
        return {"anyOf": [_object(rng, rng.randint(2, 4), 0, optional_max=0) for _ in range(p["n_alts"])]}
    keys = _keys(rng, 4)
    props = {}
    for i, k in enumerate(keys):
        if i == 0:
            if kind == "field":
                props[k] = {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "boolean"}][: p["n_alts"]]}
            elif kind == "nullable":
                props[k] = {"anyOf": [_primitive(rng, allow_enum=False), {"type": "null"}]}
            elif kind == "type_list":
                props[k] = {"type": ["string", "null"]}
            else:  # objects
                props[k] = {"anyOf": [_object(rng, 2, 0, optional_max=0) for _ in range(p["n_alts"])]}
        else:
            props[k] = _primitive(rng, allow_enum=False)
    return {"type": "object", "properties": props, "required": keys}


def _numeric_bounds(rng, p):
    keys = _keys(rng, p["n"])
    props = {}
    for k in keys:
        t = rng.choice(["integer", "number"])
        bound = rng.choice(["minimum", "exclusiveMinimum", "maximum", "exclusiveMaximum"])
        props[k] = {"type": t, bound: 0}
    return {"type": "object", "properties": props, "required": keys}


def _numeric_bounds_nonzero(rng, p):
    keys = _keys(rng, 3)
    props = {keys[0]: {"type": "integer", "minimum": p["lo"], "maximum": p["hi"]},
             keys[1]: {"type": "number", "minimum": 0.5},
             keys[2]: {"type": "integer"}}
    return {"type": "object", "properties": props, "required": keys}


def _string_length(rng, p):
    keys = _keys(rng, p["n"])
    props = {}
    for k in keys:
        s = {"type": "string"}
        mode = rng.choice(["min", "max", "both", "both"])
        lo = rng.randint(0, 8)
        span = rng.randint(1, 56)
        if mode in ("min", "both"):
            s["minLength"] = max(lo, 1) if mode == "min" else lo
        if mode in ("max", "both"):
            s["maxLength"] = lo + span
        props[k] = s
    return {"type": "object", "properties": props, "required": keys}


def _patterns(rng, p):
    props = {}
    for name in p["patterns"]:
        props[name] = {"type": "string", "pattern": PATTERN_POOL[name]}
    props["id"] = {"type": "integer", "minimum": 0}
    return {"type": "object", "properties": props, "required": list(props)}


def _refs_defs(rng, p):
    defs = {
        "money": {"type": "object", "properties": {"amount": {"type": "number", "minimum": 0}, "currency": {"enum": ["usd", "eur", "gbp"]}}, "required": ["amount", "currency"]},
        "address": {"type": "object", "properties": {"street": {"type": "string"}, "city": {"type": "string"}, "zip": {"type": "string", "pattern": "[0-9]{5}"}}, "required": ["street", "city", "zip"]},
        "tag": {"type": "string", "minLength": 1, "maxLength": 20},
        "timestamp": {"type": "string", "pattern": PATTERN_POOL["iso_datetime"]},
        "ident": {"type": "integer", "minimum": 0},
    }
    chosen = rng.sample(list(defs), p["n_defs"])
    props = {}
    for i in range(p["n_uses"]):
        d = chosen[i % len(chosen)]
        if d == "tag" and rng.random() < 0.5:
            props[f"{d}s_{i}"] = {"type": "array", "items": {"$ref": f"#/$defs/{d}"}}
        else:
            props[f"{d}_{i}"] = {"$ref": f"#/$defs/{d}"}
    used = set(chosen)
    if p["nested"]:
        defs["line"] = {"type": "object", "properties": {"price": {"$ref": "#/$defs/money"}, "ship_to": {"$ref": "#/$defs/address"}}, "required": ["price", "ship_to"]}
        used |= {"money", "address", "line"}
        props["lines"] = {"type": "array", "items": {"$ref": "#/$defs/line"}, "maxItems": 5}
    return {"$defs": {k: defs[k] for k in used},
            "type": "object", "properties": props, "required": list(props)}


def _recursion(rng, p):
    kind = p["kind"]
    if kind == "tree_self":
        return {"type": "object", "properties": {"value": {"type": "integer"}, "children": {"type": "array", "items": {"$ref": "#"}, **({"maxItems": p["fanout"]} if p["fanout"] else {})}}, "required": ["value", "children"]}
    if kind == "tree_defs":
        return {"$defs": {"node": {"type": "object", "properties": {"name": {"type": "string", "maxLength": 12}, "kids": {"type": "array", "items": {"$ref": "#/$defs/node"}}}, "required": ["name", "kids"]}},
                "type": "object", "properties": {"root": {"$ref": "#/$defs/node"}}, "required": ["root"]}
    if kind == "linked_list":
        return {"$defs": {"node": {"type": "object", "properties": {"value": {"type": "integer"}, "next": {"anyOf": [{"$ref": "#/$defs/node"}, {"type": "null"}]}}, "required": ["value", "next"]}},
                "type": "object", "properties": {"head": {"$ref": "#/$defs/node"}}, "required": ["head"]}
    if kind == "expression":
        return {"$defs": {
            "expr": {"anyOf": [{"$ref": "#/$defs/num"}, {"$ref": "#/$defs/binop"}, {"$ref": "#/$defs/var"}]},
            "num": {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]},
            "var": {"type": "object", "properties": {"v": {"type": "string", "pattern": "[a-z]+"}}, "required": ["v"]},
            "binop": {"type": "object", "properties": {"op": {"enum": ["+", "-", "*", "/"]}, "l": {"$ref": "#/$defs/expr"}, "r": {"$ref": "#/$defs/expr"}}, "required": ["op", "l", "r"]}},
            "type": "object", "properties": {"expr": {"$ref": "#/$defs/expr"}}, "required": ["expr"]}
    # comments thread
    return {"$defs": {"comment": {"type": "object", "properties": {"author": {"type": "string"}, "text": {"type": "string", "maxLength": 40}, "replies": {"type": "array", "items": {"$ref": "#/$defs/comment"}, "maxItems": 3}}, "required": ["author", "text", "replies"]}},
            "type": "object", "properties": {"thread": {"type": "array", "items": {"$ref": "#/$defs/comment"}}}, "required": ["thread"]}


def _tuples(rng, p):
    prefix = [_primitive(rng, allow_enum=False) for _ in range(p["n"])]
    arr: dict = {"type": "array", "prefixItems": prefix}
    if p["mode"] == "closed":
        arr["items"] = False
    elif p["mode"] == "exact":
        arr["minItems"] = p["n"]
        arr["maxItems"] = p["n"]
    elif p["mode"] == "bounded":
        arr["minItems"] = p["n"]
        arr["maxItems"] = p["n"] + 2
    if p["root"] == "array":
        return arr
    return {"type": "object", "properties": {"point": arr, "label": {"type": "string"}}, "required": ["point", "label"]}


_REALISTIC = {
    "order": {"type": "object", "properties": {
        "id": {"type": "string", "pattern": PATTERN_POOL["uuid"]},
        "customer": {"type": "object", "properties": {"id": {"type": "integer", "minimum": 0}, "name": {"type": "string", "maxLength": 40}, "email": {"type": "string", "pattern": PATTERN_POOL["email"]}}, "required": ["id", "name", "email"]},
        "items": {"type": "array", "minItems": 1, "maxItems": 10, "items": {"type": "object", "properties": {"sku": {"type": "string", "pattern": "[A-Z]{2}[0-9]{4}"}, "quantity": {"type": "integer", "exclusiveMinimum": 0}, "price": {"type": "number", "minimum": 0}}, "required": ["sku", "quantity", "price"]}},
        "status": {"enum": ["pending", "paid", "shipped", "delivered", "cancelled"]},
        "notes": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        "required": ["id", "customer", "items", "status"]},
    "user_profile": {"type": "object", "properties": {
        "username": {"type": "string", "pattern": "[a-z_][a-z0-9_]{2,15}"},
        "display_name": {"type": "string", "minLength": 1, "maxLength": 50},
        "age": {"type": "integer", "minimum": 0},
        "roles": {"type": "array", "items": {"enum": ["admin", "editor", "viewer"]}, "maxItems": 3},
        "address": {"$ref": "#/$defs/address"},
        "settings": {"type": "object", "properties": {"theme": {"enum": ["light", "dark"]}, "notifications": {"type": "boolean"}}, "required": ["theme", "notifications"]}},
        "required": ["username", "display_name", "roles", "settings"],
        "$defs": {"address": {"type": "object", "properties": {"city": {"type": "string"}, "country": {"type": "string", "pattern": "[A-Z]{2}"}}, "required": ["city", "country"]}}},
    "event_log": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
        "ts": {"type": "string", "pattern": PATTERN_POOL["iso_datetime"]},
        "level": {"enum": ["debug", "info", "warning", "error"]},
        "message": {"type": "string", "maxLength": 80},
        "context": {"type": "object"}},
        "required": ["ts", "level", "message"]}},
    "geo_feature": {"type": "object", "properties": {
        "type": {"const": "Feature"},
        "geometry": {"type": "object", "properties": {"type": {"enum": ["Point", "LineString"]}, "coordinates": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 4}}, "required": ["type", "coordinates"]},
        "properties": {"type": "object", "properties": {"name": {"type": "string"}, "population": {"type": "integer", "minimum": 0}}, "required": ["name"]}},
        "required": ["type", "geometry", "properties"]},
    "chat_message": {"type": "object", "properties": {
        "role": {"enum": ["system", "user", "assistant", "tool"]},
        "content": {"type": "string"},
        "tool_calls": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {"name": {"type": "string", "pattern": "[a-z_]+"}, "arguments": {"type": "object"}}, "required": ["name", "arguments"]}}},
        "required": ["role", "content"]},
    "search_response": {"type": "object", "properties": {
        "query": {"type": "string"},
        "total": {"type": "integer", "minimum": 0},
        "page": {"type": "integer", "exclusiveMinimum": 0},
        "hits": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {"id": {"type": "string"}, "score": {"type": "number", "minimum": 0}, "title": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5}}, "required": ["id", "score", "title"]}}},
        "required": ["query", "total", "page", "hits"]},
    "invoice": {"type": "object", "properties": {
        "number": {"type": "string", "pattern": "INV-[0-9]{6}"},
        "issued": {"type": "string", "pattern": PATTERN_POOL["iso_date"]},
        "due": {"type": "string", "pattern": PATTERN_POOL["iso_date"]},
        "lines": {"type": "array", "minItems": 1, "items": {"type": "object", "properties": {"desc": {"type": "string", "maxLength": 60}, "qty": {"type": "integer", "exclusiveMinimum": 0}, "unit_price": {"type": "number", "minimum": 0}}, "required": ["desc", "qty", "unit_price"]}},
        "total": {"type": "number", "minimum": 0},
        "paid": {"type": "boolean"}},
        "required": ["number", "issued", "due", "lines", "total", "paid"]},
    "config_file": {"type": "object", "properties": {
        "version": {"type": "string", "pattern": PATTERN_POOL["semver"]},
        "server": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "exclusiveMinimum": 0}, "tls": {"type": "boolean"}}, "required": ["host", "port"]},
        "features": {"type": "array", "items": {"enum": ["a", "b", "c", "d"]}},
        "log_level": {"enum": ["debug", "info", "warn", "error"]}},
        "required": ["version", "server"]},
    "ticket": {"type": "object", "properties": {
        "id": {"type": "string", "pattern": PATTERN_POOL["ticket_id"]},
        "title": {"type": "string", "minLength": 3, "maxLength": 80},
        "priority": {"enum": ["low", "medium", "high", "critical"]},
        "assignee": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "labels": {"type": "array", "items": {"type": "string", "pattern": "[a-z-]+"}, "maxItems": 6},
        "estimate_hours": {"type": "number", "minimum": 0}},
        "required": ["id", "title", "priority", "assignee", "labels"]},
    "product_catalog": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "object", "properties": {
        "sku": {"type": "string", "pattern": "[A-Z0-9]{8}"},
        "name": {"type": "string", "maxLength": 60},
        "price": {"type": "number", "minimum": 0},
        "in_stock": {"type": "boolean"},
        "variants": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {"color": {"enum": ["red", "green", "blue"]}, "size": {"enum": ["s", "m", "l"]}}, "required": ["color", "size"]}}},
        "required": ["sku", "name", "price", "in_stock"]}},
}


def _mixed_realistic(rng, p):
    return json.loads(json.dumps(_REALISTIC[p["template"]]))


# --------------------------------------------------------------------------
# Adversarial families
# --------------------------------------------------------------------------


def _deep_nesting(rng, p):
    depth, kind = p["depth"], p["kind"]
    leaf: dict = {"type": "integer"}
    s = leaf
    for i in range(depth):
        if kind == "object_chain":
            s = {"type": "object", "properties": {"c": s}, "required": ["c"]}
        elif kind == "array_chain":
            s = {"type": "array", "items": s}
        elif kind == "alternating":
            s = {"type": "object", "properties": {"c": s}, "required": ["c"]} if i % 2 == 0 else {"type": "array", "items": s}
        else:  # anyof_chain
            s = {"type": "object", "properties": {"c": {"anyOf": [s, {"type": "null"}]}}, "required": ["c"]}
    if s.get("type") == "array" and kind == "array_chain":
        return s
    if s.get("type") != "object":
        s = {"type": "object", "properties": {"root": s}, "required": ["root"]}
    return s


def _wide_enum(rng, p):
    n, kind = p["size"], p["kind"]
    if kind == "short_str":
        vals = [f"v{i}" for i in range(n)]
    elif kind == "long_str":
        vals = [f"value_{i:08d}_{'x' * 24}" for i in range(n)]
    elif kind == "int":
        vals = list(range(n))
    elif kind == "mixed":
        vals = [f"s{i}" if i % 3 == 0 else (i if i % 3 == 1 else float(i) + 0.5) for i in range(n)]
    else:  # unicode
        vals = [f"{UNICODE_POOL[i % len(UNICODE_POOL)]}{i}" for i in range(n)]
    return {"type": "object", "properties": {"choice": {"enum": vals}}, "required": ["choice"]}


def _giant_const(rng, p):
    size, kind = p["size"], p["kind"]
    if kind == "ascii":
        text = ("lorem ipsum dolor sit amet " * (size // 27 + 1))[:size]
        return {"type": "object", "properties": {"blob": {"const": text}}, "required": ["blob"]}
    if kind == "unicode":
        text = ("日本語テキスト\U0001F600" * (size // 20 + 1))[: size // 3]
        return {"type": "object", "properties": {"blob": {"const": text}}, "required": ["blob"]}
    if kind == "enum_of_giants":
        return {"type": "object", "properties": {"blob": {"enum": [c * (size // 3) for c in "abc"]}}, "required": ["blob"]}
    if kind == "giant_key":
        key = "k" * size
        return {"type": "object", "properties": {key: {"type": "integer"}}, "required": [key]}
    # nested const object
    return {"type": "object", "properties": {"doc": {"const": {"title": "t" * (size // 2), "tags": ["x" * (size // 4), "y" * (size // 4)]}}}, "required": ["doc"]}


def _huge_items(rng, p):
    kind = p["kind"]
    item = {"type": "integer"} if p.get("item") == "int" else {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    if kind == "max_only":
        arr = {"type": "array", "items": item, "maxItems": p["max"]}
    elif kind == "min_only":
        arr = {"type": "array", "items": item, "minItems": p["min"]}
    elif kind == "span":
        arr = {"type": "array", "items": item, "minItems": p["min"], "maxItems": p["max"]}
    elif kind == "prefix_long":
        arr = {"type": "array", "prefixItems": [{"type": "integer"}] * p["n_prefix"], "items": {"type": "string"}}
    elif kind == "prefix_long_closed":
        arr = {"type": "array", "prefixItems": [{"type": "integer"}] * p["n_prefix"], "items": False}
    else:  # nested_bounded: 3 nested arrays each with maxItems
        arr = {"type": "array", "items": {"type": "array", "items": {"type": "array", "items": item, "maxItems": p["max"]}, "maxItems": p["max"]}, "maxItems": p["max"]}
    return arr if p.get("root") == "array" else {"type": "object", "properties": {"list": arr}, "required": ["list"]}


def _huge_string_length(rng, p):
    props = {}
    for i in range(p["n_fields"]):
        s: dict = {"type": "string"}
        if p["kind"] in ("max_only", "span"):
            s["maxLength"] = p["max"]
        if p["kind"] in ("min_only", "span"):
            s["minLength"] = p["min"]
        props[f"s{i}"] = s
    return {"type": "object", "properties": props, "required": list(props)}


NESTED_QUANTIFIER_POOL = [
    r"(a+)+", r"(a+)+b", r"(a|a)*", r"(a|a)*b", r"(a|aa)+", r"((a*)*)*b", r"(x+x+)+y",
    r"(a*)*", r"(.*a){10}", r"(a?){20}a{20}", r"([a-z]+)*@", r"(a|b|ab)*c",
    r"(.*?)*", r"(a{0,5}){0,5}", r"(\w+\s?)*", r"((ab)*)*", r"(a+|b+)*c",
    r"^(a+)+$", r"(a|aa|aaa|aaaa)*b",
]

COUNTED_REPETITION_POOL = [
    (r".{1000,5000}", "either"), (r".{0,65535}", "either"), (r"[a-z]{5000}", "either"),
    (r"(a{1,100}){1,100}", "either"), (r"(ab{2,50}){2,50}", "either"),
    (r"((a{1,10}){1,10}){1,10}", "either"), (r"[0-9]{1000}", "either"),
    (r"x{100000}", "reject"), (r"(a|b){1,1000}", "either"), (r"\p{L}{100,1000}", "either"),
    (r"[^\x00-\x7f]{100,1000}", "either"), (r".{100000,}", "reject"),
    (r"(a{1,1000}){1,1000}", "reject"), (r"([a-z]{2,5}[0-9]{2,5}){50,500}", "either"),
    ("[一-鿿]{1,50}", "either"), (r"(\d{3}-){1000}", "reject"),
]


def _regex_nested_quantifiers(rng, p):
    props = {f"s{i}": {"type": "string", "pattern": NESTED_QUANTIFIER_POOL[j]} for i, j in enumerate(p["idx"])}
    return {"type": "object", "properties": props, "required": list(props)}


def _regex_counted_repetition(rng, p):
    pat, _ = COUNTED_REPETITION_POOL[p["idx"]]
    props = {f"s{i}": {"type": "string", "pattern": pat} for i in range(p["n_fields"])}
    return {"type": "object", "properties": props, "required": list(props)}


def _regex_alternation_blowup(rng, p):
    kind = p["kind"]
    if kind == "wide":
        alts = "|".join(f"w{i}" for i in range(p["n"]))
        pat = f"({alts})"
    elif kind == "wide_literal":
        alts = "|".join("".join(rng.choice("abcdefghij") for _ in range(p["lit_len"])) for _ in range(p["n"]))
        pat = f"({alts})"
    elif kind == "repeated_alt":
        pat = f"(a|b|c|d|e|f|g|h){{{p['n']}}}"
    elif kind == "prefix_ambiguous":
        pat = f"(cat|car|cart|card|care|cats){{1,{p['n']}}}"
    elif kind == "nested_product":
        pat = "((a|b)(c|d)(e|f)(g|h)){" + str(p["n"]) + "}"
    else:  # unicode_class
        pat = r"(\p{L}|\p{N}|\p{P}){1," + str(p["n"]) + "}"
    return {"type": "object", "properties": {"s": {"type": "string", "pattern": pat}}, "required": ["s"]}


def _many_optional_props(rng, p):
    n = p["n_optional"]
    t = p["ptype"]
    props = {f"opt_{i}": ({"type": t} if t != "enum" else {"enum": ["a", "b"]}) for i in range(n)}
    if p["nested"]:
        inner = {"type": "object", "properties": {f"in_{i}": {"type": "integer"} for i in range(p["nested"])}}
        props["child"] = inner
        props["child2"] = inner
    return {"type": "object", "properties": props, "required": []}


def _thousands_of_props(rng, p):
    n = p["n"]
    key = (lambda i: f"k{i}") if p["kind"] != "long_keys" else (lambda i: f"property_name_number_{i:06d}_padding_padding")
    props = {key(i): {"type": "integer"} for i in range(n)}
    if p["kind"] == "nested":
        props = {f"g{i}": {"type": "object", "properties": {f"k{j}": {"type": "integer"} for j in range(n // 20)}, "required": [f"k{j}" for j in range(n // 20)]} for i in range(20)}
    if p["kind"] == "some_optional":
        return {"type": "object", "properties": props, "required": list(props)[:-8]}
    return {"type": "object", "properties": props, "required": list(props)}


def _recursive_ref_fanout(rng, p):
    n, k = p["fanout"], p["levels"]
    defs = {"leaf": {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}}
    prev = "leaf"
    for lvl in range(k):
        name = f"l{lvl}"
        defs[name] = {"type": "object", "properties": {f"p{i}": {"$ref": f"#/$defs/{prev}"} for i in range(n)}, "required": [f"p{i}" for i in range(n)]}
        prev = name
    if p["kind"] == "mutual":
        defs["a"] = {"type": "object", "properties": {f"b{i}": {"anyOf": [{"$ref": "#/$defs/b"}, {"type": "null"}]} for i in range(n)}, "required": [f"b{i}" for i in range(n)]}
        defs["b"] = {"type": "object", "properties": {f"a{i}": {"anyOf": [{"$ref": "#/$defs/a"}, {"type": "null"}]} for i in range(n)}, "required": [f"a{i}" for i in range(n)]}
        return {"$defs": defs, "type": "object", "properties": {"root": {"$ref": "#/$defs/a"}}, "required": ["root"]}
    if p["kind"] == "array_fanout":
        return {"$defs": defs, "type": "object", "properties": {f"arr{i}": {"type": "array", "items": {"$ref": f"#/$defs/{prev}"}, "maxItems": 3} for i in range(n)}, "required": [f"arr{i}" for i in range(n)]}
    return {"$defs": defs, "type": "object", "properties": {"root": {"$ref": f"#/$defs/{prev}"}}, "required": ["root"]}


def _unicode_heavy(rng, p):
    kind = p["kind"]
    if kind == "enum":
        vals = [f"{UNICODE_POOL[i % len(UNICODE_POOL)]}{'·' * (i % 5)}{i}" for i in range(p["n"])]
        return {"type": "object", "properties": {"u": {"enum": vals}}, "required": ["u"]}
    if kind == "keys":
        keys = [f"{UNICODE_POOL[i % len(UNICODE_POOL)]}{i}" for i in range(p["n"])]
        return {"type": "object", "properties": {k: {"type": "integer"} for k in keys}, "required": keys}
    if kind == "const":
        return {"type": "object", "properties": {"u": {"const": "".join(UNICODE_POOL) * (p["n"] // 100 + 1)}}, "required": ["u"]}
    if kind == "pattern":
        pats = ["[一-鿿]{1,50}", r"\p{L}+", r"[^\x00-\x7f]{10,100}", r"(\p{Emoji}|\p{L})+", "[α-ω]{5,20}"]
        return {"type": "object", "properties": {"u": {"type": "string", "pattern": pats[p["n"] % len(pats)]}}, "required": ["u"]}
    # emoji-only enum with 4-byte code points and ZWJ sequences
    base = ["\U0001F600", "\U0001F44D\U0001F3FD", "\U0001F680\U0001F315", "\U0001F1EF\U0001F1F5",
            "\U0001F9D1\u200d\U0001F91D\u200d\U0001F9D1", "\U0001F3F3\ufe0f\u200d\U0001F308",
            "\U0001F468\u200d\U0001F469\u200d\U0001F467\u200d\U0001F466", "\U0001FAE0"]
    vals = [f"{base[i % len(base)]}{i}" for i in range(p["n"])]
    return {"type": "object", "properties": {"u": {"enum": vals}}, "required": ["u"]}


HOSTILE_KEYS = ["it's", 'a"b', "back\\slash", "new\nline", "tab\tkey", "$ref", "$id", "", "#'", "(*comment*)",
                "nul\x00char", "key with spaces", "\"quoted\"", "'single'", "${nonterminal}", "::=", "|pipe|",
                "\\u0041", "emoji\U0001F600key", "0123"]
HOSTILE_VALUES = ['a"b', "c\\d", "e\nf", "it's", "tab\t", " ", "", "#'x'", "(*", "\\", '"', "\x00", "\\u0041",
                  "\U0001F600", "a\rb", "${x}", "'", "\"\"", "\\\"", "line1\nline2\n"]
HOSTILE_CONSTS = [1e100, -0.0, 1e-7, 10 ** 30, 123456789012345678901234567890, 1.7976931348623157e308,
                  5e-324, -1e100, 0.1 + 0.2, True, False, None, 1.0, 100000000000000000000.0, 2 ** 63,
                  -(2 ** 63) - 1, [1, "a", None], {"k": [1, 2, {"z": "q"}]}, "x", 42]


def _hostile_literals(rng, p):
    kind = p["kind"]
    if kind == "key":
        k = HOSTILE_KEYS[p["idx"] % len(HOSTILE_KEYS)]
        return {"type": "object", "properties": {k: {"type": "integer"}, "ok": {"type": "boolean"}}, "required": [k, "ok"]}
    if kind == "enum":
        vals = [HOSTILE_VALUES[(p["idx"] + j) % len(HOSTILE_VALUES)] for j in range(3)]
        return {"type": "object", "properties": {"v": {"enum": vals}}, "required": ["v"]}
    if kind == "const_str":
        return {"type": "object", "properties": {"v": {"const": HOSTILE_VALUES[p["idx"] % len(HOSTILE_VALUES)]}}, "required": ["v"]}
    return {"type": "object", "properties": {"v": {"const": HOSTILE_CONSTS[p["idx"] % len(HOSTILE_CONSTS)]}}, "required": ["v"]}


def _mixed_combo(rng, p):
    kind = p["kind"]
    if kind == "deep_plus_optional":
        s = {"type": "object", "properties": {f"o{i}": {"type": "integer"} for i in range(12)}}
        for _ in range(p["n"]):
            s = {"type": "object", "properties": {"c": s}, "required": ["c"]}
        return s
    if kind == "enum_plus_refs":
        return {"$defs": {"e": {"enum": [f"v{i}" for i in range(p["n"])]}},
                "type": "object", "properties": {f"f{i}": {"$ref": "#/$defs/e"} for i in range(10)}, "required": [f"f{i}" for i in range(10)]}
    if kind == "items_plus_pattern":
        return {"type": "array", "items": {"type": "string", "pattern": PATTERN_POOL["uuid"]}, "maxItems": p["n"]}
    if kind == "recursion_plus_optional":
        return {"$defs": {"node": {"type": "object", "properties": {**{f"o{i}": {"type": "integer"} for i in range(p["n"])}, "kids": {"type": "array", "items": {"$ref": "#/$defs/node"}}}, "required": ["kids"]}},
                "type": "object", "properties": {"root": {"$ref": "#/$defs/node"}}, "required": ["root"]}
    if kind == "props_plus_enum":
        return {"type": "object", "properties": {f"k{i}": {"enum": [f"v{j}" for j in range(p["n"])]} for i in range(200)}, "required": [f"k{i}" for i in range(200)]}
    if kind == "prefix_plus_max":
        return {"type": "array", "prefixItems": [{"type": "integer"}] * p["n"], "items": {"type": "integer"}, "maxItems": p["n"] + 5}
    if kind == "nested_arrays_bounded":
        s = {"type": "integer"}
        for _ in range(5):
            s = {"type": "array", "items": s, "maxItems": p["n"]}
        return s
    if kind == "pattern_plus_length":  # mutually exclusive in Formatron
        return {"type": "object", "properties": {"s": {"type": "string", "pattern": "[a-z]+", "minLength": 1, "maxLength": p["n"]}}, "required": ["s"]}
    if kind == "anyof_many_optionals":
        return {"anyOf": [{"type": "object", "properties": {f"a{i}_{j}": {"type": "integer"} for j in range(5)}} for i in range(p["n"])]}
    if kind == "root_type_list":
        return {"type": ["object", "array"], "properties": {"a": {"type": "integer"}}, "items": {"type": "string"}, "required": ["a"], "maxItems": p["n"]}
    if kind == "enum_plus_length":  # enum wins over type; length ignored
        return {"type": "object", "properties": {"s": {"type": "string", "enum": ["a", "bb"], "minLength": 1, "maxLength": p["n"]}}, "required": ["s"]}
    if kind == "many_regex_fields":
        return {"type": "object", "properties": {f"r{i}": {"type": "string", "pattern": f"[a-z]{{{i % 7 + 1},{i % 7 + 20}}}"} for i in range(p["n"])}, "required": [f"r{i}" for i in range(p["n"])]}
    if kind == "wide_union_of_enums":
        return {"anyOf": [{"type": "object", "properties": {"t": {"const": f"t{i}"}, "v": {"enum": [f"v{i}_{j}" for j in range(20)]}}, "required": ["t", "v"]} for i in range(p["n"])]}
    # deep_plus_wide
    s = {"enum": [f"v{i}" for i in range(p["n"])]}
    for _ in range(40):
        s = {"type": "object", "properties": {"c": s, "d": {"type": "integer"}}, "required": ["c", "d"]}
    return s


# Payloads that try to break out of the KBNF terminal / regex quoting Formatron uses for
# property names, enum/const strings and patterns.  A successful injection turns the
# generated grammar into something *valid* that no longer encodes the schema, so the
# hardened admission check happily admits it and the random walk finishes with output
# that fails validation.  ``it's`` style payloads merely produce an unparseable grammar.
INJECTION_PAYLOADS = [
    ("key", "k' | #'.*"),
    ("key", "it's"),
    ("key", "a\"b'c"),
    ("key", "k\\' | #'.*"),
    ("key", "k' object_end | object_begin #'"),
    ("key", "k' comma #'.*' | #'"),
    ("enum", "v' | #'.*"),
    ("enum", "it's"),
    ("const", "c' | #'.*"),
    ("const", "c'\n' | #'.*"),
    ("pattern", "[a-z]+' | #'.*"),
    ("pattern", "x' | #'[^\"]*"),
    ("pattern", "it's"),
    ("key", "k\" | #\".*"),
    ("enum", "d\" | #\".*"),
    ("key", "k' | #'.*' | '"),
]


def _grammar_injection(rng, p):
    where, payload = INJECTION_PAYLOADS[p["idx"] % len(INJECTION_PAYLOADS)]
    if where == "key":
        return {"type": "object", "properties": {payload: {"type": "integer"}, "ok": {"type": "boolean"}},
                "required": [payload, "ok"]}
    if where == "enum":
        return {"type": "object", "properties": {"v": {"enum": [payload, "plain"]}, "ok": {"type": "boolean"}},
                "required": ["v", "ok"]}
    if where == "const":
        return {"type": "object", "properties": {"v": {"const": payload}, "ok": {"type": "boolean"}},
                "required": ["v", "ok"]}
    return {"type": "object", "properties": {"v": {"type": "string", "pattern": payload}, "ok": {"type": "boolean"}},
            "required": ["v", "ok"]}


# --------------------------------------------------------------------------
# Family registry: name -> (category, builder)
# --------------------------------------------------------------------------

FAMILIES: dict[str, tuple[str, typing.Callable[[random.Random, dict], dict]]] = {
    # normal
    "flat_object": ("normal", _flat_object),
    "nested_object": ("normal", _nested_object),
    "array_of_objects": ("normal", _array_of_objects),
    "enum_fields": ("normal", _enum_fields),
    "enum_medium": ("normal", _enum_medium),
    "optional_fields": ("normal", _optional_fields),
    "anyof_union": ("normal", _anyof_union),
    "numeric_bounds": ("normal", _numeric_bounds),
    "numeric_bounds_nonzero": ("normal", _numeric_bounds_nonzero),
    "string_length": ("normal", _string_length),
    "patterns": ("normal", _patterns),
    "refs_defs": ("normal", _refs_defs),
    "recursion": ("normal", _recursion),
    "tuples": ("normal", _tuples),
    "mixed_realistic": ("normal", _mixed_realistic),
    # adversarial
    "deep_nesting": ("adversarial", _deep_nesting),
    "wide_enum": ("adversarial", _wide_enum),
    "giant_const": ("adversarial", _giant_const),
    "huge_items": ("adversarial", _huge_items),
    "huge_string_length": ("adversarial", _huge_string_length),
    "regex_nested_quantifiers": ("adversarial", _regex_nested_quantifiers),
    "regex_counted_repetition": ("adversarial", _regex_counted_repetition),
    "regex_alternation_blowup": ("adversarial", _regex_alternation_blowup),
    "many_optional_props": ("adversarial", _many_optional_props),
    "thousands_of_props": ("adversarial", _thousands_of_props),
    "recursive_ref_fanout": ("adversarial", _recursive_ref_fanout),
    "unicode_heavy": ("adversarial", _unicode_heavy),
    "hostile_literals": ("adversarial", _hostile_literals),
    "mixed_combo": ("adversarial", _mixed_combo),
    "grammar_injection": ("adversarial", _grammar_injection),
}


def _cycle(seq, i):
    return seq[i % len(seq)]


@functools.lru_cache(maxsize=4)
def specs(seed: int = SEED) -> list[Spec]:
    """Return the full, deterministic list of corpus specs."""
    out: list[Spec] = []
    N = _spec_list  # alias

    # ---- normal (target ~610) -------------------------------------------
    out += N("flat_object", "normal", 80, "admit",
             lambda i: {"n_props": 3 + i % 10, "n_optional": [0, 0, 1, 2, 3, 4][i % 6]})
    out += N("nested_object", "normal", 70, "admit",
             lambda i: {"depth": 2 + i % 5, "branching": 1 + i % 3})
    out += N("array_of_objects", "normal", 50, "admit",
             lambda i: {"item_props": 2 + i % 5, "bounds": _cycle(["none", "min", "max", "both"], i),
                        "max_items": _cycle([3, 5, 8, 10, 20], i), "root": _cycle(["object", "object", "array"], i)})
    out += N("enum_fields", "normal", 50, "admit",
             lambda i: {"n_enums": 1 + i % 4,
                        "kinds": [_cycle(["string", "int", "mixed", "const", "string"], i + j) for j in range(4)],
                        "sizes": [_cycle([2, 3, 5, 8, 12, 20, 32, 50], i + j) for j in range(4)]})
    out += N("enum_medium", "normal", 20, "admit",
             lambda i: {"size": _cycle([64, 100, 128, 129, 150, 200, 256, 300, 400, 512], i),
                        "kind": _cycle(["string", "int"], i // 10)})
    out += N("optional_fields", "normal", 60, "admit",
             lambda i: {"n_optional": 1 + i % 16, "n_total": 1 + i % 16 + (i * 7) % 5})
    out += N("anyof_union", "normal", 40, "admit",
             lambda i: {"kind": _cycle(["root", "field", "nullable", "type_list", "objects"], i),
                        "n_alts": 2 + i % 3})
    out += N("numeric_bounds", "normal", 40, "admit", lambda i: {"n": 2 + i % 5})
    out += N("numeric_bounds_nonzero", "normal", 10, "either",
             lambda i: {"lo": _cycle([1, -5, 10, 100, 0], i), "hi": _cycle([100, 5, 1000, 10 ** 6, 1], i)})
    out += N("string_length", "normal", 40, "admit", lambda i: {"n": 1 + i % 5})
    _pat_names = list(PATTERN_POOL)
    out += N("patterns", "normal", 50, "admit",
             lambda i: {"patterns": [_pat_names[(i + j * 5) % len(_pat_names)] for j in range(1 + i % 3)]})
    out += N("refs_defs", "normal", 40, "admit",
             lambda i: {"n_defs": 1 + i % 4, "n_uses": 2 + i % 4, "nested": i % 3 == 0})
    out += N("recursion", "normal", 30, "admit",
             lambda i: {"kind": _cycle(["tree_self", "tree_defs", "linked_list", "expression", "comments"], i),
                        "fanout": _cycle([0, 2, 3], i // 5)})
    out += N("tuples", "normal", 20, "admit",
             lambda i: {"n": 2 + i % 3, "mode": _cycle(["closed", "exact", "bounded", "open"], i),
                        "root": _cycle(["array", "object"], i // 4)})
    _templates = list(_REALISTIC)
    out += N("mixed_realistic", "normal", 10, "admit", lambda i: {"template": _templates[i % len(_templates)]})

    # ---- adversarial (target ~430) --------------------------------------
    _depths = [50, 100, 150, 200, 300, 400, 600, 800, 1000, 1500, 2000]
    out += N("deep_nesting", "adversarial", 44,
             lambda p: "either" if p["depth"] <= 300 else "reject",
             lambda i: {"depth": _depths[i % len(_depths)],
                        "kind": _cycle(["object_chain", "array_chain", "alternating", "anyof_chain"], i // len(_depths))})
    _enum_sizes = [2000, 5000, 10000, 20000, 50000, 100000]
    out += N("wide_enum", "adversarial", 30,
             lambda p: "either" if p["size"] <= 20000 else "reject",
             lambda i: {"size": _enum_sizes[i % len(_enum_sizes)],
                        "kind": _cycle(["short_str", "long_str", "int", "mixed", "unicode"], i // len(_enum_sizes))})
    _const_sizes = [65536, 262144, 1048576, 2097152, 4194304, 8388608]
    out += N("giant_const", "adversarial", 30,
             lambda p: "either" if p["size"] < 1048576 else "reject",
             lambda i: {"size": _const_sizes[i % len(_const_sizes)],
                        "kind": _cycle(["ascii", "unicode", "enum_of_giants", "giant_key", "nested_const"], i // len(_const_sizes))})
    _items = (
        [{"kind": "max_only", "max": m, "item": it} for m in [1000, 5000, 10000, 100000, 1000000, 1000000000] for it in ["int", "obj"]]
        + [{"kind": "min_only", "min": m, "item": "int"} for m in [1000, 10000, 100000, 1000000, 1000000000]]
        + [{"kind": "span", "min": a, "max": b, "item": "int"} for a, b in [(1000, 2000), (10000, 11000), (100000, 101000), (1000000, 1000010), (0, 1000000), (5, 5000), (1000, 1000000)]]
        + [{"kind": "prefix_long", "n_prefix": n} for n in [100, 500, 2000, 5000]]
        + [{"kind": "prefix_long_closed", "n_prefix": n} for n in [100, 500, 2000, 5000]]
        + [{"kind": "nested_bounded", "max": m, "item": "int"} for m in [10, 20, 50, 100]]
        + [{"kind": "max_only", "max": m, "item": "int", "root": "array"} for m in [2000, 20000, 200000, 2000000]]
        + [{"kind": "span", "min": a, "max": b, "item": "obj"} for a, b in [(100, 1100), (1000, 3000), (10, 10000), (2, 2000000000)]]
        + [{"kind": "min_only", "min": m, "item": "obj"} for m in [5000, 50000, 500000, 5000000]]
    )
    out += N("huge_items", "adversarial", len(_items),
             lambda p: "either" if max(p.get("max", 0), p.get("min", 0), p.get("n_prefix", 0)) <= 1000 else "reject",
             lambda i: _items[i])
    _lens = (
        [{"kind": "max_only", "max": m, "n_fields": 1} for m in [1000, 10000, 100000, 1000000, 10000000]]
        + [{"kind": "min_only", "min": m, "n_fields": 1} for m in [1000, 10000, 100000, 1000000, 10000000]]
        + [{"kind": "span", "min": a, "max": b, "n_fields": 1} for a, b in [(1000, 10000), (10000, 1000000), (0, 100000), (100, 100100), (500000, 500001), (1, 10000000), (65535, 65536), (0, 65535)]]
        + [{"kind": "max_only", "max": m, "n_fields": 3} for m in [1000, 5000, 20000, 100000]]
        + [{"kind": "span", "min": a, "max": b, "n_fields": 2} for a, b in [(100, 2000), (2000, 4000), (0, 50000), (10000, 20000)]]
        + [{"kind": "min_only", "min": m, "n_fields": 4} for m in [500, 2000, 10000, 50000]]
        + [{"kind": "span", "min": a, "max": b, "n_fields": 1} for a, b in [(0, 2000), (0, 5000), (0, 20000), (0, 200000), (1000, 1001), (0, 10 ** 8), (10 ** 6, 10 ** 7), (0, 1 << 20), (0, 1 << 24), (0, 1 << 28)]]
    )
    out += N("huge_string_length", "adversarial", len(_lens),
             lambda p: "either" if max(p.get("max", 0), p.get("min", 0)) <= 10000 else "reject",
             lambda i: _lens[i])
    out += N("regex_nested_quantifiers", "adversarial", 30, "either",
             lambda i: {"idx": [(i + j * 7) % len(NESTED_QUANTIFIER_POOL) for j in range(1 + i % 3)]})
    out += N("regex_counted_repetition", "adversarial", 32,
             lambda p: COUNTED_REPETITION_POOL[p["idx"]][1],
             lambda i: {"idx": i % len(COUNTED_REPETITION_POOL), "n_fields": 1 + (i // len(COUNTED_REPETITION_POOL)) * 2})
    _alts = (
        [{"kind": "wide", "n": n} for n in [500, 2000, 5000, 20000, 50000]]
        + [{"kind": "wide_literal", "n": n, "lit_len": L} for n, L in [(100, 200), (1000, 50), (5000, 20), (200, 1000), (50, 5000)]]
        + [{"kind": "repeated_alt", "n": n} for n in [50, 200, 1000, 5000, 20000]]
        + [{"kind": "prefix_ambiguous", "n": n} for n in [10, 100, 1000, 10000, 100000]]
        + [{"kind": "nested_product", "n": n} for n in [5, 20, 100, 500, 2000]]
        + [{"kind": "unicode_class", "n": n} for n in [10, 100, 1000, 10000, 100000]]
    )
    out += N("regex_alternation_blowup", "adversarial", len(_alts),
             lambda p: "either" if p["n"] <= 5000 else "reject", lambda i: _alts[i])
    _opts = [12, 14, 16, 18, 20, 22, 24, 28, 32, 40, 48, 64]
    out += N("many_optional_props", "adversarial", 30, "either",
             lambda i: {"n_optional": _opts[i % len(_opts)], "ptype": _cycle(["integer", "string", "enum"], i // len(_opts)),
                        "nested": [0, 0, 10][i // len(_opts) % 3]})
    _props = [1000, 2000, 4000, 5000, 10000, 20000]
    out += N("thousands_of_props", "adversarial", 24,
             lambda p: "either" if p["n"] <= 5000 else "reject",
             lambda i: {"n": _props[i % len(_props)], "kind": _cycle(["required", "long_keys", "nested", "some_optional"], i // len(_props))})
    _fan = [(3, 3), (5, 4), (8, 6), (12, 8), (20, 10), (3, 12), (2, 20), (30, 3)]
    out += N("recursive_ref_fanout", "adversarial", 24, "either",
             lambda i: {"fanout": _fan[i % len(_fan)][0], "levels": _fan[i % len(_fan)][1],
                        "kind": _cycle(["chain", "mutual", "array_fanout"], i // len(_fan))})
    out += N("unicode_heavy", "adversarial", 20, "either",
             lambda i: {"kind": _cycle(["enum", "keys", "const", "pattern", "emoji"], i),
                        "n": _cycle([50, 200, 1000, 5000], i // 5)})
    out += N("hostile_literals", "adversarial", 40, "either",
             lambda i: {"kind": _cycle(["key", "enum", "const_str", "const_any"], i), "idx": i // 4})
    _combos = [
        ("deep_plus_optional", 60), ("deep_plus_optional", 200), ("enum_plus_refs", 200), ("enum_plus_refs", 5000),
        ("items_plus_pattern", 100), ("items_plus_pattern", 2000), ("recursion_plus_optional", 8), ("recursion_plus_optional", 20),
        ("props_plus_enum", 20), ("props_plus_enum", 200), ("prefix_plus_max", 50), ("prefix_plus_max", 500),
        ("nested_arrays_bounded", 10), ("nested_arrays_bounded", 40), ("pattern_plus_length", 10), ("pattern_plus_length", 100000),
        ("anyof_many_optionals", 10), ("anyof_many_optionals", 100), ("root_type_list", 5), ("root_type_list", 500),
        ("enum_plus_length", 10), ("enum_plus_length", 1000000), ("many_regex_fields", 100), ("many_regex_fields", 1500),
        ("wide_union_of_enums", 50), ("wide_union_of_enums", 500), ("deep_plus_wide", 100), ("deep_plus_wide", 5000),
        ("deep_plus_optional", 20), ("enum_plus_refs", 50),
    ]
    out += N("mixed_combo", "adversarial", len(_combos), "either",
             lambda i: {"kind": _combos[i][0], "n": _combos[i][1]})
    out += N("grammar_injection", "adversarial", len(INJECTION_PAYLOADS), "either", lambda i: {"idx": i})
    return out


def materialize(spec: Spec, seed: int = SEED) -> dict:
    """Build the JSON schema for one spec (deterministic in ``seed`` and ``spec.id``)."""
    rng = random.Random(f"{seed}:{spec.id}")
    category, builder = FAMILIES[spec.family]
    schema = builder(rng, spec.params)
    return _root(schema, spec.id)


def get(spec_id: str, seed: int = SEED) -> Spec:
    for s in specs(seed):
        if s.id == spec_id:
            return s
    raise KeyError(spec_id)


def records(seed: int = SEED, spec_list: typing.Iterable[Spec] | None = None) -> typing.Iterator[dict]:
    for s in spec_list or specs(seed):
        yield {"id": s.id, "family": s.family, "category": s.category, "expect": s.expect,
               "schema": materialize(s, seed)}


def filter_specs(spec_list: list[Spec], *, families: typing.Iterable[str] | None = None,
                 category: str | None = None, ids: typing.Iterable[str] | None = None,
                 limit: int | None = None, per_family: int | None = None) -> list[Spec]:
    fams = set(families) if families else None
    idset = set(ids) if ids else None
    out = []
    seen: dict[str, int] = {}
    for s in spec_list:
        if fams and s.family not in fams:
            continue
        if category and s.category != category:
            continue
        if idset and s.id not in idset:
            continue
        if per_family is not None:
            if seen.get(s.family, 0) >= per_family:
                continue
            seen[s.family] = seen.get(s.family, 0) + 1
        out.append(s)
        if limit is not None and len(out) >= limit:
            break
    return out


def stats(seed: int = SEED) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for s in specs(seed):
        fam = out.setdefault(s.family, {"category": s.category, "n": 0, "admit": 0, "reject": 0, "either": 0})
        fam["n"] += 1
        fam[s.expect] += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--dump", metavar="PATH.jsonl", help="write the materialized corpus as JSONL (large: >100 MB)")
    ap.add_argument("--stats", action="store_true", help="print per-family counts")
    ap.add_argument("--family", action="append", help="restrict to family (repeatable)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--show", metavar="ID", help="pretty-print one schema")
    args = ap.parse_args(argv)
    sl = filter_specs(specs(args.seed), families=args.family, limit=args.limit)
    if args.stats or not (args.dump or args.show):
        st = stats(args.seed)
        total = sum(v["n"] for v in st.values())
        normal = sum(v["n"] for v in st.values() if v["category"] == "normal")
        print(f"{total} schemas ({normal} normal, {total - normal} adversarial)")
        for fam, v in st.items():
            print(f"  {fam:28s} {v['category']:12s} n={v['n']:4d} admit={v['admit']:4d} reject={v['reject']:4d} either={v['either']:4d}")
    if args.show:
        rec = next(records(args.seed, [get(args.show, args.seed)]))
        print(json.dumps(rec, indent=2, ensure_ascii=False)[:20000])
    if args.dump:
        n = 0
        with open(args.dump, "w", encoding="utf-8") as f:
            for rec in records(args.seed, sl):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
        print(f"wrote {n} records to {args.dump}", file=sys.stderr)


if __name__ == "__main__":
    main()
