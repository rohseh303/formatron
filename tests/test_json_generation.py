"""Correctness of the JSON grammar generator on inputs the adversarial benchmark exposed:
literal escaping (grammar injection), optional members, bounded arrays, linear grammar size."""

import json

import kbnf
import pytest

from formatron.formats.json import json_literal_term, kbnf_string_escape, regex_escape
from formatron.security import SchemaLimits, check_grammar, grammar_for_schema, hardened_json_schema

BYTE_VOCAB = kbnf.Vocabulary(
    {i: kbnf.Token(bytes([i])) for i in range(256)},
    {i: (chr(i) if i < 128 else "?") for i in range(256)},
)


def _grammar(properties, required=()):
    schema = {
        "$id": "https://example.com/t.json",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": list(required),
    }
    return grammar_for_schema(hardened_json_schema(schema, limits=SchemaLimits.unlimited()))


def _accepts(grammar, text):
    engine = kbnf.Engine(grammar, BYTE_VOCAB, kbnf.Config.hardened())
    try:
        engine.try_accept_new_bytes(text.encode("utf-8"))
    except ValueError:
        return False
    return True


def _assert_accepts(grammar, value):
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n"
    assert _accepts(grammar, text), f"grammar should accept {text!r}"


def _assert_rejects(grammar, text):
    assert not _accepts(grammar, text), f"grammar should reject {text!r}"


# ----------------------------------------------------------------- escaping helpers


def test_escape_helpers_round_trip_through_kbnf():
    assert kbnf_string_escape("it's \\ ok") == "it\\'s \\\\ ok"
    assert kbnf_string_escape("a\nb\tc\x01") == "a\\nb\\tc\\u0001"
    assert regex_escape("1e+100 (x*)") == "1e\\+100 \\(x\\*\\)"
    term = json_literal_term("k' | #'.*")
    assert term.startswith("#'") and term.endswith("'")
    grammar = f"start ::= {term};"
    assert _accepts(grammar, json.dumps("k' | #'.*"))
    assert not _accepts(grammar, '"garbage"')


# ----------------------------------------------------------------- injection & literals


def test_hostile_property_name_cannot_inject_grammar():
    grammar = _grammar({"k' | #'.*": {"type": "integer"}}, required=["k' | #'.*"])
    assert "#'.*" not in grammar.replace("\\'", "").replace("\\.", "")  # nothing raw leaked
    _assert_accepts(grammar, {"k' | #'.*": 1})
    _assert_rejects(grammar, 'garbage":1}\n')
    _assert_rejects(grammar, '{"k":1}\n')


@pytest.mark.parametrize(
    "value",
    ["+", "-", "*", "x*", "a\"b", "a\\b", "a\nb", "1e+100", "tab\there", "quote'inside", "ünïcödé", ""],
)
def test_string_enum_members_match_exactly(value):
    grammar = _grammar({"op": {"enum": [value, "other"]}}, required=["op"])
    _assert_accepts(grammar, {"op": value})
    _assert_accepts(grammar, {"op": "other"})
    _assert_rejects(grammar, '{"op":"nope"}\n')
    _assert_rejects(grammar, '{"op":""""}\n')


@pytest.mark.parametrize("value", [1e100, -0.5, 42, True, False, None])
def test_non_string_const_matches_json_encoding(value):
    grammar = _grammar({"v": {"const": value}}, required=["v"])
    _assert_accepts(grammar, {"v": value})
    _assert_rejects(grammar, '{"v":"x"}\n')


def test_pattern_with_quotes_and_top_level_alternation():
    # A `'` must not terminate the KBNF literal and a top-level `|` must stay inside the JSON quotes.
    grammar = _grammar({"s": {"type": "string", "pattern": "it's|say \\\"hi\\\"|x{2}"}}, required=["s"])
    check_grammar(grammar)
    assert _accepts(grammar, '{"s":"it\'s"}\n')
    assert _accepts(grammar, '{"s":"xx"}\n')
    _assert_rejects(grammar, '{"s":"other"}\n')
    _assert_rejects(grammar, 'it\'s\n')


# ----------------------------------------------------------------- objects


def test_optional_members_are_omitted_whole():
    grammar = _grammar(
        {"a": {"type": "integer"}, "b": {"type": "string"}, "c": {"type": "boolean"}},
        required=["a"],
    )
    for value in ({"a": 1}, {"a": 1, "b": "x"}, {"a": 1, "c": True}, {"a": 1, "b": "x", "c": False}):
        _assert_accepts(grammar, value)
    for text in ('{"a":1,"b":}\n', '{"a":1,}\n', '{"b":"x"}\n', '{}\n', '{"a":1,"c":true,"b":"x"}\n'):
        _assert_rejects(grammar, text)


def test_all_optional_object_accepts_empty_and_required_after_optional():
    grammar = _grammar({"a": {"type": "integer"}, "b": {"type": "integer"}})
    for value in ({}, {"a": 1}, {"b": 2}, {"a": 1, "b": 2}):
        _assert_accepts(grammar, value)

    grammar = _grammar({"a": {"type": "integer"}, "b": {"type": "integer"}}, required=["b"])
    for value in ({"b": 2}, {"a": 1, "b": 2}):
        _assert_accepts(grammar, value)
    _assert_rejects(grammar, '{"a":1}\n')
    _assert_rejects(grammar, '{}\n')


def test_many_optional_members_stay_linear():
    properties = {f"f{i}": {"type": "integer"} for i in range(40)}
    grammar = _grammar(properties)
    complexity = check_grammar(grammar)
    assert complexity.simplified_productions < 400, complexity.simplified_productions
    _assert_accepts(grammar, {"f3": 1, "f17": 2, "f39": 3})
    _assert_accepts(grammar, {})
    _assert_rejects(grammar, '{"f17":2,"f3":1}\n')


# ----------------------------------------------------------------- arrays


def test_bounded_arrays_keep_their_item_type():
    grammar = _grammar({"xs": {"type": "array", "items": {"type": "integer"}, "maxItems": 2}}, required=["xs"])
    for value in ({"xs": []}, {"xs": [1]}, {"xs": [1, 2]}):
        _assert_accepts(grammar, value)
    for text in ('{"xs":["s"]}\n', '{"xs":[1,2,3]}\n', '{"xs":[true]}\n'):
        _assert_rejects(grammar, text)

    grammar = _grammar({"xs": {"type": "array", "items": {"type": "string"}, "minItems": 2}}, required=["xs"])
    _assert_accepts(grammar, {"xs": ["a", "b", "c"]})
    _assert_rejects(grammar, '{"xs":["a"]}\n')
    _assert_rejects(grammar, '{"xs":[1,2]}\n')
