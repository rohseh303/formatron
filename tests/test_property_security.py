"""Property-based tests: the admission layer must never crash, hang, or leak exceptions
other than its documented ones, whatever a client sends."""

import json
import time

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from formatron.security import (
    ResourceLimitExceeded,
    SchemaLimits,
    check_grammar,
    check_json_schema,
    hardened_engine_config,
    inspect_grammar,
)

KEYWORDS = [
    "type", "properties", "items", "prefixItems", "enum", "const", "anyOf", "oneOf", "allOf",
    "minItems", "maxItems", "minLength", "maxLength", "pattern", "required", "$ref", "$defs",
    "minimum", "maximum", "description", "additionalProperties",
]
TYPES = ["object", "array", "string", "integer", "number", "boolean", "null"]

scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10, max_value=10_000_000),
    st.text(max_size=40),
    st.sampled_from(TYPES),
)
schema_documents = st.recursive(
    scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=6),
        st.dictionaries(st.sampled_from(KEYWORDS) | st.text(max_size=8), children, max_size=6),
    ),
    max_leaves=60,
)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(schema_documents)
def test_check_json_schema_is_total_and_bounded(document):
    started = time.perf_counter()
    try:
        complexity = check_json_schema(document, SchemaLimits.hardened())
    except ResourceLimitExceeded as error:
        assert error.violation.phase == "schema"
        assert error.violation.observed > error.violation.limit
    else:
        measured = check_json_schema(document, SchemaLimits.unlimited())
        assert measured.to_dict() == complexity.to_dict()
        assert complexity.bytes == len(json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode())
    assert time.perf_counter() - started < 2.0


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(schema_documents)
def test_unlimited_measurements_never_raise_limit_errors(document):
    complexity = check_json_schema(document, SchemaLimits.unlimited())
    assert complexity.nodes >= (1 if isinstance(document, (dict, list)) else 0)
    assert complexity.depth >= complexity.nodes.__class__(0)


grammar_fragments = st.sampled_from(
    [
        "start", "::=", ";", "|", "(", ")", "?", "*", "+", "'a'", "'b'", "\"c\"", "#'[a-z]+'",
        "#'(a{1,50}){1,50}'", "#e'x'", "#substrs'abc'", "item", "\n", " ", "(*", "*)", "\\", "'",
        "'\\u0000'", "#'.{0,4096}'", "start ::= item;", "item ::= 'x' | item ',' item;",
    ]
)
grammars = st.one_of(
    st.lists(grammar_fragments, min_size=1, max_size=40).map(" ".join),
    st.text(max_size=200),
    st.binary(max_size=200).map(lambda b: b.decode("utf-8", "replace")),
)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(grammars)
def test_grammar_checks_only_raise_documented_errors(grammar):
    started = time.perf_counter()
    for call in (lambda: inspect_grammar(grammar), lambda: check_grammar(grammar, hardened_engine_config())):
        try:
            complexity = call()
        except ResourceLimitExceeded as error:
            assert error.violation.observed > error.violation.limit
        except ValueError:
            pass  # syntax / validation error reported by kbnf
        else:
            assert complexity.source_bytes == len(grammar.encode("utf-8"))
    assert time.perf_counter() - started < 5.0, "hardened checks must stay fast on arbitrary input"


@pytest.mark.parametrize(
    "grammar",
    [
        "start ::= " + "(" * 200 + "'a'" + ")" * 200 + ";",
        "start ::= " + " ".join(["'a'?"] * 40) + ";",
        "start ::= #'((a{1,30}){1,30}){1,30}';",
        "start ::= " + " | ".join(f"'{i}'" for i in range(20_000)) + ";",
    ],
)
def test_named_amplifiers_are_rejected_quickly(grammar):
    started = time.perf_counter()
    with pytest.raises(ResourceLimitExceeded):
        check_grammar(grammar, hardened_engine_config(max_source_bytes=16_384, max_simplified_productions=4_096))
    assert time.perf_counter() - started < 2.0
