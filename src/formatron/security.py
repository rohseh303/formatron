"""Security helpers for Formatron grammars and JSON schemas supplied by users.

Formatron turns JSON Schema, Pydantic models, regexes, and custom builders into KBNF
grammars. When a client controls any of those inputs, grammar construction and decoding
become untrusted compute workloads. This module provides:

- :func:`hardened_engine_config` — the hardened KBNF fork's conservative policy, with
  per-field overrides for both construction (``GrammarLimits``) and decoding
  (``DecodeLimits``) budgets.
- :func:`inspect_grammar` / :func:`check_grammar` — cheap, vocabulary-free complexity
  reports; ``check_grammar`` runs the whole construction pipeline under the policy.
- :class:`SchemaLimits` / :func:`check_json_schema` — admission limits applied to the
  JSON Schema *before* Formatron expands it, because several keywords (``maxItems``,
  ``minLength``/``maxLength`` spans, large ``enum`` lists, deep nesting) amplify in the
  Python grammar generator long before the KBNF engine sees anything.
- :func:`admit_json_schema` — the end-to-end admission decision a multi-tenant service
  makes for one request, optionally executed in an isolated worker process
  (see :mod:`formatron.isolation`).

Every rejection is reported as a :class:`ResourceLimitExceeded` carrying a machine-readable
:class:`LimitViolation` (phase, resource, observed, limit) suitable for logs, metrics, and
HTTP error bodies.
"""

from __future__ import annotations

import dataclasses
import json
import re
import time
import typing

import kbnf

_FORK_HINT = (
    "requires the hardened kbnf fork. "
    "Install https://github.com/rohseh303/kbnf from its grammar-guard branch."
)

_LIMIT_MESSAGE = re.compile(
    r"grammar resource limit exceeded during (?P<phase>\w+): "
    r"(?P<resource>\w+) observed (?P<observed>\d+), limit (?P<limit>\d+)"
)


def _require(owner: typing.Any, name: str, what: str) -> typing.Any:
    attribute = getattr(owner, name, None)
    if attribute is None:
        raise RuntimeError(f"{what} {_FORK_HINT}")
    return attribute


# --------------------------------------------------------------------------------------
# Structured violations
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class LimitViolation:
    """A machine-readable description of one exceeded limit."""

    phase: str
    """Where the limit was checked: ``schema``, ``source``, ``parsed``, ``validated``,
    ``simplified``, or ``decode``."""
    resource: str
    """Stable resource name, e.g. ``max_items_span`` or ``simplified_productions``."""
    observed: int
    limit: int
    path: str = ""
    """JSON-pointer-like location inside a schema, when applicable."""

    def to_dict(self) -> dict[str, typing.Any]:
        return dataclasses.asdict(self)

    def __str__(self) -> str:
        where = f" at {self.path}" if self.path else ""
        return (
            f"resource limit exceeded during {self.phase}{where}: "
            f"{self.resource} observed {self.observed}, limit {self.limit}"
        )


class ResourceLimitExceeded(ValueError):
    """Raised when a user-supplied grammar or schema exceeds the configured policy."""

    def __init__(self, violation: LimitViolation):
        self.violation = violation
        super().__init__(str(violation))


def parse_limit_error(message: str) -> LimitViolation | None:
    """Parse the hardened kbnf fork's limit error message into a :class:`LimitViolation`."""
    match = _LIMIT_MESSAGE.search(message)
    if match is None:
        return None
    return LimitViolation(
        phase=match.group("phase"),
        resource=match.group("resource"),
        observed=int(match.group("observed")),
        limit=int(match.group("limit")),
    )


# --------------------------------------------------------------------------------------
# KBNF engine policy
# --------------------------------------------------------------------------------------


def hardened_engine_config(**limit_overrides: int | None) -> kbnf.Config:
    """Return KBNF's conservative multi-tenant configuration.

    Keyword arguments override fields on ``config.grammar_limits`` (construction budgets)
    or ``config.decode_limits`` (per-token budgets). Use ``regex_memory_bytes`` to override
    the DFA compiler's memory cap. Passing ``None`` removes that one limit.

    Examples:
        ``hardened_engine_config(max_source_bytes=64_000, max_compile_millis=1_000,
        max_earley_items_per_set=4_096)``
    """
    config = _require(kbnf.Config, "hardened", "This safety policy")()
    grammar_limits = config.grammar_limits
    decode_limits = _require(config, "decode_limits", "Decode budgets")
    grammar_names = {name for name in dir(grammar_limits) if name.startswith("max_")}
    decode_names = {name for name in dir(decode_limits) if name.startswith("max_")}
    for name, value in limit_overrides.items():
        if name == "regex_memory_bytes":
            regex_config = config.regex_config
            regex_config.max_memory_usage = value
            config.regex_config = regex_config
        elif name in grammar_names:
            setattr(grammar_limits, name, value)
        elif name in decode_names:
            setattr(decode_limits, name, value)
        else:
            valid = ", ".join(sorted(grammar_names | decode_names | {"regex_memory_bytes"}))
            raise TypeError(f"unknown grammar limit {name!r}; expected one of: {valid}")
    config.grammar_limits = grammar_limits
    config.decode_limits = decode_limits
    return config


def inspect_grammar(grammar: str) -> typing.Any:
    """Return cheap deterministic complexity metrics without compiling regexes."""
    return _require(kbnf, "inspect_grammar", "Grammar inspection")(grammar)


def check_grammar(grammar: str, config: kbnf.Config | None = None) -> typing.Any:
    """Run the full construction pipeline under ``config`` without a vocabulary.

    Returns the ``GrammarComplexity`` report (including post-simplification metrics) or
    raises :class:`ResourceLimitExceeded`; other grammar errors propagate as ``ValueError``.
    """
    checker = _require(kbnf, "check_grammar", "Grammar checking")
    try:
        return checker(grammar, config if config is not None else hardened_engine_config())
    except ValueError as error:
        violation = parse_limit_error(str(error))
        if violation is not None:
            raise ResourceLimitExceeded(violation) from error
        raise


# --------------------------------------------------------------------------------------
# JSON Schema admission
# --------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SchemaLimits:
    """Admission limits applied to a JSON Schema document before grammar generation.

    ``None`` disables a limit. :meth:`hardened` returns conservative defaults sized so
    that ordinary API schemas pass while the amplification paths in Formatron's generator
    (quadratic ``maxItems`` enumeration, counted-repetition DFAs, wide enums) stay bounded.
    """

    max_bytes: int | None = None
    """Serialized size of the schema document."""
    max_depth: int | None = None
    """Nesting depth of the schema document (dict/list levels)."""
    max_nodes: int | None = None
    """Total dict and list nodes in the document."""
    max_properties_per_object: int | None = None
    max_properties_total: int | None = None
    max_enum_members: int | None = None
    """Total ``enum`` members plus ``const`` values across the document."""
    max_literal_bytes: int | None = None
    """Serialized bytes of all ``enum``/``const`` literals."""
    max_items_bound: int | None = None
    """Largest ``minItems``/``maxItems`` value."""
    max_items_span: int | None = None
    """Largest ``maxItems - minItems``; Formatron emits one production per count."""
    max_length_bound: int | None = None
    """Largest ``minLength``/``maxLength`` value; each becomes a counted-repetition DFA."""
    max_pattern_bytes: int | None = None
    max_combinator_branches: int | None = None
    """Largest ``anyOf``/``oneOf``/``allOf`` branch count."""
    max_refs: int | None = None
    """Total ``$ref``/``$dynamicRef`` occurrences."""

    @classmethod
    def hardened(cls) -> "SchemaLimits":
        return cls(
            max_bytes=262_144,
            max_depth=64,
            max_nodes=20_000,
            max_properties_per_object=256,
            max_properties_total=2_048,
            max_enum_members=2_048,
            max_literal_bytes=65_536,
            max_items_bound=4_096,
            max_items_span=256,
            max_length_bound=1_024,
            max_pattern_bytes=1_024,
            max_combinator_branches=64,
            max_refs=1_024,
        )

    @classmethod
    def unlimited(cls) -> "SchemaLimits":
        return cls()


@dataclasses.dataclass
class SchemaComplexity:
    """Deterministic measurements of a JSON Schema document."""

    bytes: int = 0
    depth: int = 0
    nodes: int = 0
    max_properties_per_object: int = 0
    properties_total: int = 0
    enum_members: int = 0
    literal_bytes: int = 0
    max_items_bound: int = 0
    max_items_span: int = 0
    max_length_bound: int = 0
    max_pattern_bytes: int = 0
    max_combinator_branches: int = 0
    refs: int = 0

    def to_dict(self) -> dict[str, int]:
        return dataclasses.asdict(self)


_COMBINATORS = ("anyOf", "oneOf", "allOf")


def _int_or_zero(value: typing.Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def check_json_schema(
    schema: typing.Any,
    limits: SchemaLimits | None = None,
) -> SchemaComplexity:
    """Measure ``schema`` and raise :class:`ResourceLimitExceeded` on the first violation.

    The walk is iterative, so hostile nesting cannot exhaust the Python stack, and every
    check is O(size of the document). ``limits`` defaults to :meth:`SchemaLimits.hardened`.
    """
    limits = SchemaLimits.hardened() if limits is None else limits
    complexity = SchemaComplexity()

    def violate(resource: str, observed: int, limit: int | None, path: str) -> None:
        if limit is not None and observed > limit:
            raise ResourceLimitExceeded(LimitViolation("schema", resource, observed, limit, path))

    stack: list[tuple[typing.Any, int, str]] = [(schema, 1, "")]
    while stack:
        node, depth, path = stack.pop()
        if not isinstance(node, (dict, list)):
            continue
        complexity.nodes += 1
        violate("max_nodes", complexity.nodes, limits.max_nodes, path)
        if depth > complexity.depth:
            complexity.depth = depth
            violate("max_depth", depth, limits.max_depth, path)
        if isinstance(node, list):
            for index, child in enumerate(node):
                stack.append((child, depth + 1, f"{path}/{index}"))
            continue

        properties = node.get("properties")
        if isinstance(properties, dict):
            count = len(properties)
            complexity.max_properties_per_object = max(complexity.max_properties_per_object, count)
            violate("max_properties_per_object", count, limits.max_properties_per_object, path)
            complexity.properties_total += count
            violate("max_properties_total", complexity.properties_total, limits.max_properties_total, path)

        literals: list[typing.Any] = []
        enum = node.get("enum")
        if isinstance(enum, list):
            literals.extend(enum)
        if "const" in node:
            literals.append(node["const"])
        if literals:
            complexity.enum_members += len(literals)
            violate("max_enum_members", complexity.enum_members, limits.max_enum_members, path)
            literal_bytes = sum(
                len(json.dumps(literal, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                for literal in literals
            )
            complexity.literal_bytes += literal_bytes
            violate("max_literal_bytes", complexity.literal_bytes, limits.max_literal_bytes, path)

        min_items = _int_or_zero(node.get("minItems"))
        max_items = _int_or_zero(node.get("maxItems"))
        bound = max(min_items, max_items)
        if bound:
            complexity.max_items_bound = max(complexity.max_items_bound, bound)
            violate("max_items_bound", bound, limits.max_items_bound, path)
        if "maxItems" in node:
            span = max(max_items - min_items, 0)
            complexity.max_items_span = max(complexity.max_items_span, span)
            violate("max_items_span", span, limits.max_items_span, path)

        length_bound = max(_int_or_zero(node.get("minLength")), _int_or_zero(node.get("maxLength")))
        if length_bound:
            complexity.max_length_bound = max(complexity.max_length_bound, length_bound)
            violate("max_length_bound", length_bound, limits.max_length_bound, path)

        pattern = node.get("pattern")
        if isinstance(pattern, str):
            size = len(pattern.encode("utf-8"))
            complexity.max_pattern_bytes = max(complexity.max_pattern_bytes, size)
            violate("max_pattern_bytes", size, limits.max_pattern_bytes, path)

        for keyword in _COMBINATORS:
            branches = node.get(keyword)
            if isinstance(branches, list):
                complexity.max_combinator_branches = max(complexity.max_combinator_branches, len(branches))
                violate("max_combinator_branches", len(branches), limits.max_combinator_branches, path)

        if "$ref" in node or "$dynamicRef" in node:
            complexity.refs += 1
            violate("max_refs", complexity.refs, limits.max_refs, path)

        for key, child in node.items():
            stack.append((child, depth + 1, f"{path}/{key}"))

    # Serialize only after the iterative walk has bounded the depth: the JSON encoder is
    # recursive and would otherwise be the first thing a hostile document exhausts.
    try:
        serialized = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
    except RecursionError as error:
        raise ResourceLimitExceeded(
            LimitViolation("schema", "python_recursion", complexity.depth, complexity.depth, "")
        ) from error
    complexity.bytes = len(serialized.encode("utf-8"))
    violate("max_bytes", complexity.bytes, limits.max_bytes, "")
    return complexity


def hardened_json_schema(
    schema: dict[str, typing.Any],
    *,
    registry: typing.Any = None,
    limits: SchemaLimits | None = None,
) -> typing.Any:
    """Check ``schema`` against ``limits`` and convert it with ``create_schema``.

    Python recursion exhaustion inside the converter is reported as a
    :class:`ResourceLimitExceeded` instead of a bare ``RecursionError``.
    """
    from formatron.schemas import json_schema

    check_json_schema(schema, limits)
    kwargs = {} if registry is None else {"registry": registry}
    try:
        return json_schema.create_schema(schema, **kwargs)
    except RecursionError as error:
        import sys

        raise ResourceLimitExceeded(
            LimitViolation("schema", "python_recursion", sys.getrecursionlimit(), sys.getrecursionlimit())
        ) from error


def grammar_for_schema(schema_type: typing.Any) -> str:
    """Return the KBNF grammar Formatron would compile for a converted schema."""
    from formatron.formatter import FormatterBuilder

    builder = FormatterBuilder()
    builder.append_line(f"{builder.json(schema_type, capture_name='json')}")
    return builder.grammar_string()


@dataclasses.dataclass
class AdmissionResult:
    """The outcome of admitting one user-supplied schema or grammar."""

    admitted: bool
    outcome: str
    """``admitted``, ``rejected``, ``invalid``, ``timeout``, or ``crashed``."""
    reason: str | None = None
    violation: LimitViolation | None = None
    schema_complexity: dict[str, int] | None = None
    grammar_complexity: dict[str, int] | None = None
    grammar_bytes: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, typing.Any]:
        data = dataclasses.asdict(self)
        return data


def admit_json_schema(
    schema: dict[str, typing.Any],
    *,
    schema_limits: SchemaLimits | None = None,
    engine_overrides: dict[str, int | None] | None = None,
    checker: typing.Any = None,
    registry: typing.Any = None,
) -> AdmissionResult:
    """Decide whether a user-supplied JSON Schema may be compiled into a constraint.

    Steps: schema admission (:func:`check_json_schema`), conversion, grammar generation,
    then a full hardened grammar check — in-process, or inside ``checker`` (an
    :class:`formatron.isolation.IsolatedGrammarChecker`) when hard wall-clock and memory
    limits are required. Never raises for input problems; the result explains them.
    """
    started = time.perf_counter()
    engine_overrides = engine_overrides or {}

    def finish(result: AdmissionResult) -> AdmissionResult:
        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        return result

    try:
        schema_complexity = check_json_schema(schema, schema_limits).to_dict()
        schema_type = hardened_json_schema(schema, registry=registry, limits=SchemaLimits.unlimited())
        grammar = grammar_for_schema(schema_type)
    except ResourceLimitExceeded as error:
        return finish(AdmissionResult(False, "rejected", str(error), error.violation))
    except RecursionError:
        violation = LimitViolation("schema", "python_recursion", 0, 0)
        return finish(AdmissionResult(False, "rejected", str(violation), violation))
    except Exception as error:  # invalid schema, unsupported keyword, ...
        return finish(AdmissionResult(False, "invalid", f"{type(error).__name__}: {error}"))

    grammar_bytes = len(grammar.encode("utf-8"))
    if checker is not None:
        result = checker.check(grammar, engine_overrides=engine_overrides)
        result.schema_complexity = schema_complexity
        return finish(result)
    try:
        complexity = check_grammar(grammar, hardened_engine_config(**engine_overrides))
    except ResourceLimitExceeded as error:
        return finish(
            AdmissionResult(
                False, "rejected", str(error), error.violation, schema_complexity, None, grammar_bytes
            )
        )
    except ValueError as error:
        return finish(
            AdmissionResult(False, "invalid", str(error), None, schema_complexity, None, grammar_bytes)
        )
    return finish(
        AdmissionResult(
            True,
            "admitted",
            None,
            None,
            schema_complexity,
            complexity.to_dict(),
            grammar_bytes,
        )
    )
