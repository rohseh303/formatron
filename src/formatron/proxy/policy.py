"""Settings and the effective resource policy of the GrammarGuard admission proxy.

:class:`ProxySettings` is what the CLI (or an embedding application) fills in;
:func:`resolve_policy` turns it into an :class:`EffectivePolicy` — every limit fully
resolved — which is what the admission service enforces, what ``GET /grammar-guard/policy``
reports, and what the decision cache keys on (via :attr:`EffectivePolicy.fingerprint`).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import typing

import kbnf

from formatron.security import SchemaLimits, hardened_engine_config

POLICIES = ("hardened", "unlimited")
GRAMMAR_DIALECTS = ("passthrough", "kbnf")
INVALID_ACTIONS = ("reject", "forward")

DEFAULT = "default"
"""Sentinel for proxy-level limits: resolve to the policy's default (hardened or unlimited)."""

_HARDENED_PROXY_LIMITS: dict[str, int] = {
    # Raw size of a constraint delivered as a JSON string, before it is parsed.
    "max_constraint_bytes": 1 << 20,
    # Mirrors the engine's ``max_regex_bytes`` so oversized regexes never reach the worker.
    "max_regex_bytes": 65_536,
    "max_choices": 1_024,
    "max_choice_bytes": 65_536,
    "max_grammar_bytes": 65_536,
    # Lexical bracket nesting of a ``guided_grammar`` in vLLM's own (unverified) dialect.
    "max_grammar_nesting": 64,
}


def engine_limit_names() -> tuple[str, ...]:
    """Every override name :func:`formatron.security.hardened_engine_config` accepts."""
    config = kbnf.Config.hardened()
    names = {name for name in dir(config.grammar_limits) if name.startswith("max_")}
    names |= {name for name in dir(config.decode_limits) if name.startswith("max_")}
    names.add("regex_memory_bytes")
    return tuple(sorted(names))


def schema_limit_names() -> tuple[str, ...]:
    return tuple(field.name for field in dataclasses.fields(SchemaLimits))


def proxy_limit_names() -> tuple[str, ...]:
    return tuple(_HARDENED_PROXY_LIMITS)


def parse_limit_value(text: str) -> int | None:
    """Parse ``VALUE`` of a ``NAME=VALUE`` limit: a non-negative integer or ``none``."""
    normalized = text.strip().lower().replace("_", "")
    if normalized in {"none", "null", "unlimited", "off"}:
        return None
    try:
        value = int(normalized)
    except ValueError:
        raise ValueError(f"limit value {text!r} must be an integer or 'none'") from None
    if value < 0:
        raise ValueError(f"limit value {text!r} must not be negative")
    return value


def parse_limit_assignments(
    items: typing.Iterable[str] | None,
    valid_names: typing.Collection[str],
    what: str,
) -> dict[str, int | None]:
    """Parse ``NAME=VALUE`` strings (CLI or comma-separated env var) into a dict."""
    overrides: dict[str, int | None] = {}
    for item in items or ():
        for assignment in item.split(","):
            assignment = assignment.strip()
            if not assignment:
                continue
            name, separator, value = assignment.partition("=")
            name = name.strip()
            if not separator:
                raise ValueError(f"{what} {assignment!r} must look like NAME=VALUE")
            if name not in valid_names:
                raise ValueError(f"unknown {what} {name!r}; expected one of: {', '.join(sorted(valid_names))}")
            overrides[name] = parse_limit_value(value)
    return overrides


@dataclasses.dataclass(frozen=True)
class ProxySettings:
    """Everything the proxy needs to run; see ``python -m formatron.proxy --help``."""

    upstream: str = "http://127.0.0.1:8000"
    """Base URL of the vLLM / OpenAI-compatible server requests are forwarded to."""
    policy: str = "hardened"
    """``hardened`` (conservative defaults) or ``unlimited`` (measure only, no rejections)."""
    schema_limit_overrides: typing.Mapping[str, int | None] = dataclasses.field(default_factory=dict)
    """Per-field overrides of :class:`formatron.security.SchemaLimits`."""
    engine_limit_overrides: typing.Mapping[str, int | None] = dataclasses.field(default_factory=dict)
    """Per-field overrides for :func:`formatron.security.hardened_engine_config`."""

    timeout_s: float = 2.0
    """Hard wall-clock limit of one grammar check inside the isolated worker."""
    memory_bytes: int | None = 1 << 30
    """Best-effort address-space limit of the worker (effective on Linux)."""
    cpu_seconds: int | None = None
    admission_timeout_s: float | None = None
    """Per-request budget for the whole admission (schema conversion + queueing + worker
    check). ``None`` derives ``admission_workers * timeout_s + 2``. Expiry is reported as
    ``constraint_check_timeout``."""
    admission_workers: int = 4
    """Threads that may run admission checks concurrently (the worker itself is serialized)."""

    grammar_dialect: str = "passthrough"
    """``passthrough``: ``guided_grammar`` is only size/nesting checked (vLLM's dialects are not
    KBNF). ``kbnf``: the grammar is compiled in the isolated worker."""
    on_invalid: str = "reject"
    """What to do with a JSON schema Formatron cannot convert (unsupported keyword, root type
    not object/array): ``reject`` (fail closed) or ``forward`` after the schema-level limits
    passed, flagged in ``x-grammar-guard-unverified``."""
    check_all_tool_schemas: bool = False
    """Also check ``tools[*].function.parameters`` when ``tool_choice`` is ``auto``/absent.
    Named-function and ``required`` tool choices are always checked."""

    cache_size: int = 1024
    """Entries of the LRU decision cache (0 disables it)."""
    latency_window: int = 4096
    """Admission latency samples kept for the p50/p99 statistics."""

    max_body_bytes: int | None = 32 << 20
    """Largest request body the proxy will parse; larger bodies get HTTP 413."""
    max_constraint_bytes: typing.Any = DEFAULT
    max_regex_bytes: typing.Any = DEFAULT
    max_choices: typing.Any = DEFAULT
    max_choice_bytes: typing.Any = DEFAULT
    max_grammar_bytes: typing.Any = DEFAULT
    max_grammar_nesting: typing.Any = DEFAULT

    guarded_paths: tuple[str, ...] = ("/v1/chat/completions", "/v1/completions")
    """Paths whose bodies must parse as JSON and are always inspected for constraints."""
    scan_all_json_requests: bool = True
    """Inspect every other ``POST``/``PUT``/``PATCH`` with a JSON content type too, so
    constraints cannot be smuggled through e.g. ``/v1/responses``."""

    upstream_connect_timeout_s: float = 10.0
    upstream_read_timeout_s: float | None = None
    """``None`` because streaming completions can legitimately stay silent for a long time."""
    upstream_transport: typing.Any = None
    """Optional ``httpx.AsyncBaseTransport`` (tests inject ``httpx.ASGITransport``)."""

    default_schema_id: str = "https://grammar-guard.invalid/request-schema.json"
    default_schema_dialect: str = "https://json-schema.org/draft/2020-12/schema"
    """Filled into schemas that omit ``$id`` / ``$schema`` (OpenAI ``response_format`` usually does)."""

    def __post_init__(self) -> None:
        if self.policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}, got {self.policy!r}")
        if self.grammar_dialect not in GRAMMAR_DIALECTS:
            raise ValueError(f"grammar_dialect must be one of {GRAMMAR_DIALECTS}, got {self.grammar_dialect!r}")
        if self.on_invalid not in INVALID_ACTIONS:
            raise ValueError(f"on_invalid must be one of {INVALID_ACTIONS}, got {self.on_invalid!r}")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.admission_workers < 1:
            raise ValueError("admission_workers must be at least 1")
        unknown = set(self.schema_limit_overrides) - set(schema_limit_names())
        if unknown:
            raise ValueError(f"unknown schema limits: {sorted(unknown)}")
        unknown = set(self.engine_limit_overrides) - set(engine_limit_names())
        if unknown:
            raise ValueError(f"unknown engine limits: {sorted(unknown)}")


@dataclasses.dataclass(frozen=True)
class EffectivePolicy:
    """Every limit the proxy enforces, fully resolved."""

    name: str
    schema_limits: SchemaLimits
    engine_overrides: dict[str, int | None]
    """Passed to the isolated checker / :func:`formatron.security.admit_json_schema`."""
    engine_limits: dict[str, typing.Any]
    """The resolved engine configuration, for reporting."""
    proxy_limits: dict[str, int | None]
    grammar_dialect: str
    on_invalid: str
    check_all_tool_schemas: bool
    timeout_s: float
    memory_bytes: int | None
    cpu_seconds: int | None
    admission_timeout_s: float
    admission_workers: int
    max_body_bytes: int | None
    default_schema_id: str
    default_schema_dialect: str

    def limit(self, name: str) -> int | None:
        return self.proxy_limits[name]

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            "policy": self.name,
            "schema_limits": dataclasses.asdict(self.schema_limits),
            "engine_limits": self.engine_limits,
            "proxy_limits": dict(self.proxy_limits),
            "grammar_dialect": self.grammar_dialect,
            "on_invalid": self.on_invalid,
            "check_all_tool_schemas": self.check_all_tool_schemas,
            "isolation": {
                "timeout_s": self.timeout_s,
                "memory_bytes": self.memory_bytes,
                "cpu_seconds": self.cpu_seconds,
                "admission_timeout_s": self.admission_timeout_s,
                "admission_workers": self.admission_workers,
            },
            "max_body_bytes": self.max_body_bytes,
            "schema_defaults": {"$id": self.default_schema_id, "$schema": self.default_schema_dialect},
        }

    @property
    def fingerprint(self) -> str:
        """Stable hash of everything that can change an admission decision."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _engine_limits_report(overrides: typing.Mapping[str, int | None]) -> dict[str, typing.Any]:
    config = hardened_engine_config(**overrides)
    grammar = config.grammar_limits
    decode = config.decode_limits
    return {
        "grammar": {name: getattr(grammar, name) for name in dir(grammar) if name.startswith("max_")},
        "decode": {name: getattr(decode, name) for name in dir(decode) if name.startswith("max_")},
        "regex_memory_bytes": config.regex_config.max_memory_usage,
    }


def resolve_policy(settings: ProxySettings) -> EffectivePolicy:
    """Resolve ``settings`` into the concrete limits the proxy enforces."""
    unlimited = settings.policy == "unlimited"

    base_schema_limits = SchemaLimits.unlimited() if unlimited else SchemaLimits.hardened()
    schema_limits = dataclasses.replace(base_schema_limits, **dict(settings.schema_limit_overrides))

    engine_overrides: dict[str, int | None] = {}
    if unlimited:
        engine_overrides.update({name: None for name in engine_limit_names()})
    engine_overrides.update(settings.engine_limit_overrides)

    proxy_limits: dict[str, int | None] = {}
    for name, hardened_value in _HARDENED_PROXY_LIMITS.items():
        configured = getattr(settings, name)
        if configured == DEFAULT:
            proxy_limits[name] = None if unlimited else hardened_value
        else:
            proxy_limits[name] = configured

    admission_timeout_s = settings.admission_timeout_s
    if admission_timeout_s is None:
        admission_timeout_s = settings.admission_workers * settings.timeout_s + 2.0

    return EffectivePolicy(
        name=settings.policy,
        schema_limits=schema_limits,
        engine_overrides=engine_overrides,
        engine_limits=_engine_limits_report(engine_overrides),
        proxy_limits=proxy_limits,
        grammar_dialect=settings.grammar_dialect,
        on_invalid=settings.on_invalid,
        check_all_tool_schemas=settings.check_all_tool_schemas,
        timeout_s=settings.timeout_s,
        memory_bytes=settings.memory_bytes,
        cpu_seconds=settings.cpu_seconds,
        admission_timeout_s=admission_timeout_s,
        admission_workers=settings.admission_workers,
        max_body_bytes=settings.max_body_bytes,
        default_schema_id=settings.default_schema_id,
        default_schema_dialect=settings.default_schema_dialect,
    )
