"""Locating user-supplied decoding constraints inside OpenAI / vLLM request bodies.

The proxy never trusts the request: bodies are parsed fail-closed (duplicate keys and
hostile nesting are rejected rather than resolved differently from the upstream parser),
and every field vLLM can turn into a grammar is reported as a :class:`Constraint` with the
request path (``param``) it was found at.

Request shapes handled (see the README for the vLLM versions they correspond to):

- OpenAI ``response_format: {"type": "json_schema", "json_schema": {"schema": ...}}`` and
  ``{"type": "structural_tag", ...}`` (every embedded schema); ``json_object``/``text`` carry
  no user schema and are ignored.
- vLLM legacy top-level ``guided_json`` (object or JSON string), ``guided_regex``,
  ``guided_choice``, ``guided_grammar``.
- vLLM ``structured_outputs: {"json": ..., "regex": ..., "choice": ..., "grammar": ...,
  "structural_tag": ...}``.
- The same fields nested under ``extra_body`` (clients that send the SDK convenience key
  literally).
- ``tools[*].function.parameters`` when ``tool_choice`` names a function or is
  ``required`` (vLLM compiles those into a JSON-schema constraint); optionally for
  ``auto`` too.
- Responses-API style ``text: {"format": {"type": "json_schema", "schema": ...}}``.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import typing

from formatron.security import LimitViolation

KIND_JSON_SCHEMA = "json_schema"
KIND_REGEX = "regex"
KIND_CHOICE = "choice"
KIND_GRAMMAR = "grammar"
KINDS = (KIND_JSON_SCHEMA, KIND_REGEX, KIND_CHOICE, KIND_GRAMMAR)


@dataclasses.dataclass(frozen=True)
class Constraint:
    """One user-supplied constraint found in a request."""

    kind: str
    param: str
    """Dotted request path, e.g. ``response_format.json_schema.schema`` or ``extra_body.guided_regex``."""
    value: typing.Any
    """``dict`` or unparsed ``str`` for JSON schemas, ``str`` for regex/grammar, ``list`` for choices."""


class ConstraintError(ValueError):
    """A constraint field the proxy cannot interpret (maps to ``invalid_constraint``)."""

    def __init__(self, param: str, message: str):
        self.param = param
        self.message = message
        super().__init__(f"{param}: {message}")


class ConstraintRejected(ValueError):
    """A constraint field that exceeded a proxy-level limit (maps to ``resource_limit_exceeded``)."""

    def __init__(self, param: str, violation: LimitViolation):
        self.param = param
        self.violation = violation
        super().__init__(str(violation))


# --------------------------------------------------------------------------------------
# Fail-closed JSON parsing
# --------------------------------------------------------------------------------------


def _reject_duplicate_keys(pairs: list[tuple[str, typing.Any]]) -> dict[str, typing.Any]:
    document: dict[str, typing.Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate object key {key!r}")
        document[key] = value
    return document


def parse_json_document(raw: bytes | str, *, param: str = "body") -> typing.Any:
    """Parse JSON strictly.

    Duplicate keys are rejected because the proxy and the upstream server could otherwise
    disagree about which value wins; nesting deep enough to exhaust the recursive decoder
    is reported as a resource violation.
    """
    try:
        return json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except RecursionError:
        limit = sys.getrecursionlimit()
        raise ConstraintRejected(
            param, LimitViolation("proxy", "json_nesting_depth", limit, limit, param)
        ) from None
    except (ValueError, UnicodeDecodeError) as error:
        raise ConstraintError(param, f"malformed JSON: {error}") from None


def parse_json_body(raw: bytes) -> dict[str, typing.Any]:
    document = parse_json_document(raw, param="body")
    if not isinstance(document, dict):
        raise ConstraintError("body", "request body must be a JSON object")
    return document


# --------------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------------


def extract_constraints(
    body: typing.Mapping[str, typing.Any],
    *,
    check_all_tool_schemas: bool = False,
) -> list[Constraint]:
    """Return every constraint in ``body`` in a stable order (first rejection wins later)."""
    found: list[Constraint] = []
    _extract_response_format(body.get("response_format"), "response_format", found)
    _extract_vllm_fields(body, "", found)
    extra_body = body.get("extra_body")
    if isinstance(extra_body, typing.Mapping):
        _extract_response_format(extra_body.get("response_format"), "extra_body.response_format", found)
        _extract_vllm_fields(extra_body, "extra_body.", found)
    text = body.get("text")
    if isinstance(text, typing.Mapping):
        _extract_text_format(text.get("format"), "text.format", found)
    _extract_tools(body, found, check_all_tool_schemas)
    return found


def _extract_response_format(response_format: typing.Any, param: str, found: list[Constraint]) -> None:
    if response_format is None:
        return
    if not isinstance(response_format, typing.Mapping):
        raise ConstraintError(param, "must be an object")
    kind = response_format.get("type")
    if kind == "json_schema":
        spec = response_format.get("json_schema")
        if not isinstance(spec, typing.Mapping):
            raise ConstraintError(f"{param}.json_schema", "must be an object")
        schema = spec.get("schema")
        if schema is None:
            return  # no user schema: vLLM falls back to unconstrained JSON
        if not isinstance(schema, (typing.Mapping, str)):
            raise ConstraintError(f"{param}.json_schema.schema", "must be an object or a JSON string")
        found.append(Constraint(KIND_JSON_SCHEMA, f"{param}.json_schema.schema", schema))
    elif kind == "structural_tag":
        _collect_embedded_schemas(response_format, param, found)
    # "json_object", "text", None: nothing user-controlled reaches the grammar engine.


def _extract_text_format(text_format: typing.Any, param: str, found: list[Constraint]) -> None:
    if not isinstance(text_format, typing.Mapping):
        return
    if text_format.get("type") == "json_schema":
        schema = text_format.get("schema")
        if schema is None:
            return
        if not isinstance(schema, (typing.Mapping, str)):
            raise ConstraintError(f"{param}.schema", "must be an object or a JSON string")
        found.append(Constraint(KIND_JSON_SCHEMA, f"{param}.schema", schema))


def _extract_vllm_fields(container: typing.Mapping[str, typing.Any], prefix: str, found: list[Constraint]) -> None:
    _extract_json(container.get("guided_json"), f"{prefix}guided_json", found)
    _extract_regex(container.get("guided_regex"), f"{prefix}guided_regex", found)
    _extract_choice(container.get("guided_choice"), f"{prefix}guided_choice", found)
    _extract_grammar(container.get("guided_grammar"), f"{prefix}guided_grammar", found)
    _extract_structural_tag(container.get("structural_tag"), f"{prefix}structural_tag", found)

    structured = container.get("structured_outputs")
    if structured is None:
        return
    if not isinstance(structured, typing.Mapping):
        raise ConstraintError(f"{prefix}structured_outputs", "must be an object")
    nested = f"{prefix}structured_outputs."
    _extract_json(structured.get("json"), f"{nested}json", found)
    _extract_regex(structured.get("regex"), f"{nested}regex", found)
    _extract_choice(structured.get("choice"), f"{nested}choice", found)
    _extract_grammar(structured.get("grammar"), f"{nested}grammar", found)
    _extract_structural_tag(structured.get("structural_tag"), f"{nested}structural_tag", found)


def _extract_json(value: typing.Any, param: str, found: list[Constraint]) -> None:
    if value is None:
        return
    if not isinstance(value, (typing.Mapping, str)):
        raise ConstraintError(param, "must be a JSON schema object or a JSON string")
    found.append(Constraint(KIND_JSON_SCHEMA, param, value))


def _extract_regex(value: typing.Any, param: str, found: list[Constraint]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ConstraintError(param, "must be a string")
    found.append(Constraint(KIND_REGEX, param, value))


def _extract_choice(value: typing.Any, param: str, found: list[Constraint]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ConstraintError(param, "must be a list of strings")
    found.append(Constraint(KIND_CHOICE, param, value))


def _extract_grammar(value: typing.Any, param: str, found: list[Constraint]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ConstraintError(param, "must be a string")
    found.append(Constraint(KIND_GRAMMAR, param, value))


def _extract_structural_tag(value: typing.Any, param: str, found: list[Constraint]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        value = parse_json_document(value, param=param)
    if not isinstance(value, (typing.Mapping, list)):
        raise ConstraintError(param, "must be an object or a JSON string")
    _collect_embedded_schemas(value, param, found)


_SCHEMA_KEYS = ("schema", "json_schema")


def _collect_embedded_schemas(document: typing.Any, param: str, found: list[Constraint]) -> None:
    """Report every ``schema``/``json_schema`` object nested anywhere in a structural tag.

    Structural-tag formats differ between vLLM/xgrammar versions; walking the whole
    document (iteratively, so nesting cannot recurse) is the fail-closed choice.
    """
    stack: list[tuple[typing.Any, str]] = [(document, param)]
    while stack:
        node, path = stack.pop()
        if isinstance(node, typing.Mapping):
            for key, child in node.items():
                child_path = f"{path}.{key}"
                if key in _SCHEMA_KEYS and isinstance(child, typing.Mapping):
                    found.append(Constraint(KIND_JSON_SCHEMA, child_path, child))
                    continue
                stack.append((child, child_path))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                stack.append((child, f"{path}[{index}]"))


def _extract_tools(body: typing.Mapping[str, typing.Any], found: list[Constraint], check_all: bool) -> None:
    tools = body.get("tools")
    if not isinstance(tools, list) or not tools:
        return
    tool_choice = body.get("tool_choice", "auto")
    if tool_choice == "none":
        return
    wanted: str | None = None
    if isinstance(tool_choice, typing.Mapping):
        function = tool_choice.get("function")
        if isinstance(function, typing.Mapping) and isinstance(function.get("name"), str):
            wanted = function["name"]
        else:
            raise ConstraintError("tool_choice", "must name a function")
    elif tool_choice == "required":
        wanted = None
    elif not check_all:
        return  # "auto": only constrained by servers configured for automatic tool choice
    for index, tool in enumerate(tools):
        if not isinstance(tool, typing.Mapping):
            continue
        function = tool.get("function")
        if not isinstance(function, typing.Mapping):
            continue
        if wanted is not None and function.get("name") != wanted:
            continue
        parameters = function.get("parameters")
        if parameters is None:
            continue
        param = f"tools[{index}].function.parameters"
        if not isinstance(parameters, (typing.Mapping, str)):
            raise ConstraintError(param, "must be a JSON schema object")
        found.append(Constraint(KIND_JSON_SCHEMA, param, parameters))


# --------------------------------------------------------------------------------------
# KBNF construction helpers
# --------------------------------------------------------------------------------------


def kbnf_string_literal(text: str) -> str:
    """Quote ``text`` as a KBNF single-quoted literal.

    Same escaping as Formatron's regex extractor (``repr`` of the pattern): backslashes
    and single quotes are escaped, everything else is passed through.
    """
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def regex_to_kbnf(regex: str) -> str:
    """The grammar Formatron would compile for ``guided_regex``."""
    return f"start ::= #{kbnf_string_literal(regex)};"


def choices_to_kbnf(choices: typing.Sequence[str]) -> str:
    """The grammar Formatron would compile for ``guided_choice``."""
    return "start ::= " + " | ".join(kbnf_string_literal(choice) for choice in choices) + ";"


_OPENERS = frozenset("([{")
_CLOSERS = frozenset(")]}")


def bracket_nesting_depth(grammar: str) -> int:
    """Maximum lexical bracket depth of ``grammar``.

    Every ``(``/``[``/``{`` counts, including those inside quoted terminals: the dialect is
    unknown, so this is deliberately an upper bound rather than a parse.
    """
    depth = 0
    deepest = 0
    for character in grammar:
        if character in _OPENERS:
            depth += 1
            if depth > deepest:
                deepest = depth
        elif character in _CLOSERS and depth > 0:
            depth -= 1
    return deepest
