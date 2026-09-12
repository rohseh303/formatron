import copy
from unittest.mock import Mock, patch

import pytest

from formatron.formatter import FormatterBuilder
from formatron.schemas.json_schema import create_schema
from formatron.security import (
    AdmissionResult,
    LimitViolation,
    ResourceLimitExceeded,
    SchemaLimits,
    admit_json_schema,
    check_grammar,
    check_json_schema,
    grammar_for_schema,
    hardened_engine_config,
    hardened_json_schema,
    inspect_grammar,
    parse_limit_error,
)

NORMAL_SCHEMA = {
    "$id": "https://example.com/order.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "id": {"type": "integer", "minimum": 0},
        "email": {"type": "string", "pattern": "[a-z0-9._-]+@[a-z0-9.-]+"},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "status": {"enum": ["open", "closed"]},
    },
    "required": ["id", "status"],
}


def _schema(**patch_fields):
    schema = copy.deepcopy(NORMAL_SCHEMA)
    schema["properties"].update(patch_fields)
    return schema


# ------------------------------------------------------------------ engine policy


def test_hardened_defaults_and_overrides():
    config = hardened_engine_config(
        max_source_bytes=65_536,
        max_compile_millis=750,
        regex_memory_bytes=8_388_608,
        max_earley_items_per_set=4_096,
        max_cache_entries=None,
    )

    assert config.grammar_limits.max_source_bytes == 65_536
    assert config.grammar_limits.max_compile_millis == 750
    assert config.regex_config.max_memory_usage == 8_388_608
    assert config.grammar_limits.max_ast_nodes is not None
    assert config.decode_limits.max_earley_items_per_set == 4_096
    assert config.decode_limits.max_cache_entries is None
    assert config.decode_limits.max_total_earley_items is not None


def test_unknown_override_fails_closed():
    with pytest.raises(TypeError, match="unknown grammar limit"):
        hardened_engine_config(typoed_limit=1)


def test_inspection_exposes_expansion_estimate():
    complexity = inspect_grammar("start ::= 'a'? 'b'?;")
    assert complexity.simplification_expansion == 4
    assert complexity.simplified_productions == 0
    assert "simplification_expansion" in complexity.to_dict()


def test_check_grammar_reports_structured_violation():
    complexity = check_grammar("start ::= 'a' | 'b' | 'c';")
    assert complexity.simplified_productions == 3

    with pytest.raises(ResourceLimitExceeded) as info:
        check_grammar("start ::= 'a' | 'b' | 'c';", hardened_engine_config(max_simplified_productions=2))
    violation = info.value.violation
    assert violation.phase == "simplified"
    assert violation.resource == "simplified_productions"
    assert (violation.observed, violation.limit) == (3, 2)
    assert violation.to_dict()["resource"] == "simplified_productions"


def test_nested_counted_repetition_rejected_before_regex_compile():
    with pytest.raises(ResourceLimitExceeded) as info:
        check_grammar("start ::= #'(a{1,200}){1,200}';")
    assert info.value.violation.resource == "regex_size_estimate"
    assert info.value.violation.phase == "parsed"


def test_parse_limit_error_roundtrip():
    message = "grammar resource limit exceeded during parsed: nesting_depth observed 9, limit 3"
    assert parse_limit_error(message) == LimitViolation("parsed", "nesting_depth", 9, 3)
    assert parse_limit_error("KBNF parsing error: nope") is None


# ------------------------------------------------------------------ builder wiring


def test_builder_hardened_mode_passes_policy_to_engine():
    builder = FormatterBuilder()
    builder.append_str("ok")
    vocabulary = Mock()

    with patch("formatron.formatter.kbnf.Engine") as engine:
        builder.build(vocabulary, lambda _: "", hardened=True)

    config = engine.call_args.args[2]
    assert config.grammar_limits.max_source_bytes == 1_048_576
    assert config.regex_config.max_memory_usage == 67_108_864
    assert config.decode_limits.max_earley_items_per_set == 65_536


def test_builder_hardened_mode_constructs_real_engine():
    import kbnf

    builder = FormatterBuilder()
    builder.append_str("ok")
    vocabulary = kbnf.Vocabulary({0: kbnf.Token(b"ok")}, {0: "ok"})

    formatter = builder.build(vocabulary, lambda _: "ok", hardened=True)

    assert "start ::= 'ok';" in formatter.grammar_str
    assert formatter.is_completed() is False


def test_builder_rejects_ambiguous_policy():
    builder = FormatterBuilder()
    builder.append_str("ok")

    with pytest.raises(ValueError, match="cannot be combined"):
        builder.build(Mock(), lambda _: "", hardened_engine_config(), hardened=True)


def test_grammar_string_matches_built_grammar():
    import kbnf

    builder = FormatterBuilder()
    builder.append_line(f"answer: {builder.choose('yes', 'no', capture_name='answer')}")
    grammar = builder.grammar_string()
    vocabulary = kbnf.Vocabulary({0: kbnf.Token(b"yes")}, {0: "yes"})
    formatter = builder.build(vocabulary, lambda _: "yes")
    assert formatter.grammar_str == grammar
    assert grammar.strip().endswith(";")


# ------------------------------------------------------------------ schema admission


def test_normal_schema_passes_hardened_schema_limits():
    complexity = check_json_schema(NORMAL_SCHEMA)
    assert complexity.properties_total == 4
    assert complexity.enum_members == 2
    assert complexity.max_items_bound == 8
    assert complexity.depth >= 3
    schema_type = hardened_json_schema(NORMAL_SCHEMA)
    grammar = grammar_for_schema(schema_type)
    assert "start ::=" in grammar
    assert check_grammar(grammar).simplified_productions > 0


def test_create_schema_accepts_limits_keyword():
    create_schema(NORMAL_SCHEMA, limits=SchemaLimits.hardened())
    with pytest.raises(ResourceLimitExceeded):
        create_schema(NORMAL_SCHEMA, limits=SchemaLimits(max_properties_total=1))


@pytest.mark.parametrize(
    "patch_fields, resource",
    [
        ({"big": {"type": "array", "items": {"type": "integer"}, "maxItems": 10_000_000}}, "max_items_bound"),
        ({"span": {"type": "array", "items": {"type": "integer"}, "minItems": 0, "maxItems": 4_000}}, "max_items_span"),
        ({"span2": {"type": "array", "items": {"type": "integer"}, "minItems": 3_000, "maxItems": 4_000}}, "max_items_span"),
        ({"long": {"type": "string", "minLength": 0, "maxLength": 1_000_000}}, "max_length_bound"),
        ({"wide": {"enum": list(range(5_000))}}, "max_enum_members"),
        ({"blob": {"const": "x" * 100_000}}, "max_literal_bytes"),
        ({"doc": {"type": "string", "description": "x" * 300_000}}, "max_bytes"),
        ({"pat": {"type": "string", "pattern": "a" * 5_000}}, "max_pattern_bytes"),
        ({"union": {"anyOf": [{"type": "integer"}] * 100}}, "max_combinator_branches"),
    ],
)
def test_adversarial_schema_shapes_are_rejected(patch_fields, resource):
    with pytest.raises(ResourceLimitExceeded) as info:
        check_json_schema(_schema(**patch_fields))
    assert info.value.violation.resource == resource
    assert info.value.violation.phase == "schema"
    assert info.value.violation.observed > info.value.violation.limit


def test_deep_nesting_is_rejected_without_recursion():
    inner = {"type": "integer"}
    for _ in range(5_000):
        inner = {"type": "object", "properties": {"child": inner}}
    schema = _schema(deep=inner)
    with pytest.raises(ResourceLimitExceeded) as info:
        check_json_schema(schema)
    assert info.value.violation.resource in {"max_depth", "max_bytes", "max_nodes"}


def test_unlimited_schema_limits_measure_only():
    schema = _schema(wide={"enum": list(range(5_000))})
    complexity = check_json_schema(schema, SchemaLimits.unlimited())
    assert complexity.enum_members == 5_002


def test_admit_json_schema_end_to_end_in_process():
    result = admit_json_schema(NORMAL_SCHEMA)
    assert isinstance(result, AdmissionResult)
    assert result.admitted and result.outcome == "admitted"
    assert result.grammar_bytes > 0
    assert result.grammar_complexity["simplified_productions"] > 0
    assert result.schema_complexity["properties_total"] == 4
    assert result.elapsed_ms >= 0

    rejected = admit_json_schema(_schema(wide={"enum": list(range(5_000))}))
    assert not rejected.admitted and rejected.outcome == "rejected"
    assert rejected.violation.resource == "max_enum_members"

    tight = admit_json_schema(NORMAL_SCHEMA, engine_overrides={"max_simplified_productions": 1})
    assert tight.outcome == "rejected"
    assert tight.violation.resource == "simplified_productions"

    invalid = admit_json_schema({"$id": "x", "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "string"})
    assert invalid.outcome == "invalid"
    assert "Root schema type" in invalid.reason


def test_admit_json_schema_uses_supplied_checker():
    checker = Mock()
    checker.check.return_value = AdmissionResult(True, "admitted", grammar_complexity={"ast_nodes": 1})
    result = admit_json_schema(NORMAL_SCHEMA, checker=checker, engine_overrides={"max_compile_millis": 50})
    assert result.admitted
    assert result.schema_complexity is not None
    checker.check.assert_called_once()
    assert checker.check.call_args.kwargs["engine_overrides"] == {"max_compile_millis": 50}
