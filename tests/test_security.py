from unittest.mock import Mock, patch

import pytest

from formatron.formatter import FormatterBuilder
from formatron.security import hardened_engine_config, inspect_grammar


def test_hardened_defaults_and_overrides():
    config = hardened_engine_config(
        max_source_bytes=65_536,
        max_compile_millis=750,
        regex_memory_bytes=8_388_608,
    )

    assert config.grammar_limits.max_source_bytes == 65_536
    assert config.grammar_limits.max_compile_millis == 750
    assert config.regex_config.max_memory_usage == 8_388_608
    assert config.grammar_limits.max_ast_nodes is not None


def test_unknown_override_fails_closed():
    with pytest.raises(TypeError, match="unknown grammar limit"):
        hardened_engine_config(typoed_limit=1)


def test_inspection_exposes_expansion_estimate():
    complexity = inspect_grammar("start ::= 'a'? 'b'?;")
    assert complexity.simplification_expansion == 4
    assert complexity.simplified_productions == 0


def test_builder_hardened_mode_passes_policy_to_engine():
    builder = FormatterBuilder()
    builder.append_str("ok")
    vocabulary = Mock()

    with patch("formatron.formatter.kbnf.Engine") as engine:
        builder.build(vocabulary, lambda _: "", hardened=True)

    config = engine.call_args.args[2]
    assert config.grammar_limits.max_source_bytes == 1_048_576
    assert config.regex_config.max_memory_usage == 67_108_864


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
