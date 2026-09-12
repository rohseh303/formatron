"""Security helpers for Formatron grammars supplied by users."""

from __future__ import annotations

import typing

import kbnf


def hardened_engine_config(**limit_overrides: int | None) -> kbnf.Config:
    """Return KBNF's conservative multi-tenant configuration.

    Keyword arguments override fields on ``config.grammar_limits``. Use
    ``regex_memory_bytes`` to override the DFA compiler's memory cap.

    Examples:
        ``hardened_engine_config(max_source_bytes=64_000,
        max_compile_millis=1_000)``
    """
    hardened = getattr(kbnf.Config, "hardened", None)
    if hardened is None:
        raise RuntimeError(
            "This safety policy requires the hardened kbnf fork. "
            "Install https://github.com/rohseh303/kbnf from its grammar-guard branch."
        )
    config = hardened()
    limits = config.grammar_limits
    valid_limits = {
        name
        for name in dir(limits)
        if name.startswith("max_") and not name.startswith("__")
    }
    for name, value in limit_overrides.items():
        if name == "regex_memory_bytes":
            regex_config = config.regex_config
            regex_config.max_memory_usage = value
            config.regex_config = regex_config
        elif name in valid_limits:
            setattr(limits, name, value)
        else:
            valid = ", ".join(sorted(valid_limits | {"regex_memory_bytes"}))
            raise TypeError(f"unknown grammar limit {name!r}; expected one of: {valid}")
    config.grammar_limits = limits
    return config


def inspect_grammar(grammar: str) -> typing.Any:
    """Return cheap deterministic complexity metrics without compiling regexes."""
    inspect = getattr(kbnf, "inspect_grammar", None)
    if inspect is None:
        raise RuntimeError(
            "Grammar inspection requires the hardened kbnf fork. "
            "Install https://github.com/rohseh303/kbnf from its grammar-guard branch."
        )
    return inspect(grammar)
