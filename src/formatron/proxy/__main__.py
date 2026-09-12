"""Command line entry point: ``python -m formatron.proxy --upstream http://127.0.0.1:8000``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import typing

from .policy import (
    GRAMMAR_DIALECTS,
    INVALID_ACTIONS,
    POLICIES,
    ProxySettings,
    engine_limit_names,
    parse_limit_assignments,
    parse_limit_value,
    proxy_limit_names,
    schema_limit_names,
)

ENV_PREFIX = "GRAMMAR_GUARD_"


def _env(name: str, default: typing.Any = None) -> typing.Any:
    return os.environ.get(ENV_PREFIX + name, default)


def _env_list(name: str) -> list[str]:
    value = _env(name)
    return [value] if value else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m formatron.proxy",
        description=(
            "GrammarGuard admission proxy: checks user-supplied JSON schemas, regexes, choices "
            "and grammars against a resource policy in an isolated worker before forwarding "
            "requests to a vLLM / OpenAI-compatible server. Every flag has a GRAMMAR_GUARD_* "
            "environment variable equivalent (e.g. GRAMMAR_GUARD_UPSTREAM)."
        ),
    )
    parser.add_argument("--upstream", default=_env("UPSTREAM", "http://127.0.0.1:8000"),
                        help="base URL of the inference server (default: %(default)s)")
    parser.add_argument("--host", default=_env("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(_env("PORT", 8080)))
    parser.add_argument("--timeout-s", type=float, default=float(_env("TIMEOUT_S", 2.0)),
                        help="wall-clock limit of one grammar check in the isolated worker (default: %(default)s)")
    parser.add_argument("--memory-mb", type=int, default=int(_env("MEMORY_MB", 1024)),
                        help="best-effort worker address-space limit; 0 disables (default: %(default)s)")
    parser.add_argument("--cpu-seconds", type=int, default=_env("CPU_SECONDS"),
                        help="best-effort worker CPU-time limit (default: none)")
    parser.add_argument("--admission-timeout-s", type=float, default=_env("ADMISSION_TIMEOUT_S"),
                        help="per-request admission budget (default: workers * timeout + 2)")
    parser.add_argument("--admission-workers", type=int, default=int(_env("ADMISSION_WORKERS", 4)))
    parser.add_argument("--policy", choices=POLICIES, default=_env("POLICY", "hardened"))
    parser.add_argument("--schema-limit", action="append", default=_env_list("SCHEMA_LIMITS"), metavar="NAME=VALUE",
                        help=f"override a SchemaLimits field (VALUE integer or 'none'); names: {', '.join(schema_limit_names())}")
    parser.add_argument("--engine-limit", action="append", default=_env_list("ENGINE_LIMITS"), metavar="NAME=VALUE",
                        help=f"override a KBNF engine limit; names: {', '.join(engine_limit_names())}")
    parser.add_argument("--proxy-limit", action="append", default=_env_list("PROXY_LIMITS"), metavar="NAME=VALUE",
                        help=f"override a proxy-level lexical limit; names: {', '.join(proxy_limit_names())}")
    parser.add_argument("--grammar-dialect", choices=GRAMMAR_DIALECTS, default=_env("GRAMMAR_DIALECT", "passthrough"),
                        help="how guided_grammar is checked: passthrough = size and nesting only (vLLM's "
                             "dialects are not KBNF); kbnf = compile in the isolated worker (default: %(default)s)")
    parser.add_argument("--on-invalid", choices=INVALID_ACTIONS, default=_env("ON_INVALID", "reject"),
                        help="schemas Formatron cannot convert: reject (fail closed) or forward unverified after "
                             "the schema-level limits passed (default: %(default)s)")
    parser.add_argument("--check-all-tool-schemas", action="store_true",
                        default=_env("CHECK_ALL_TOOL_SCHEMAS", "").lower() in {"1", "true", "yes"},
                        help="also check tools[*].function.parameters when tool_choice is auto")
    parser.add_argument("--cache-size", type=int, default=int(_env("CACHE_SIZE", 1024)))
    parser.add_argument("--max-body-mb", type=float, default=float(_env("MAX_BODY_MB", 32)),
                        help="largest request body parsed; 0 disables (default: %(default)s)")
    parser.add_argument("--no-scan-all-json", action="store_true",
                        default=_env("NO_SCAN_ALL_JSON", "").lower() in {"1", "true", "yes"},
                        help="only inspect the guarded completion paths, not every JSON request")
    parser.add_argument("--log-level", default=_env("LOG_LEVEL", "info"))
    return parser


def settings_from_args(args: argparse.Namespace) -> ProxySettings:
    schema_overrides = parse_limit_assignments(args.schema_limit, schema_limit_names(), "schema limit")
    engine_overrides = parse_limit_assignments(args.engine_limit, engine_limit_names(), "engine limit")
    proxy_overrides = parse_limit_assignments(args.proxy_limit, proxy_limit_names(), "proxy limit")
    cpu_seconds = args.cpu_seconds
    if isinstance(cpu_seconds, str):
        cpu_seconds = parse_limit_value(cpu_seconds)
    admission_timeout = args.admission_timeout_s
    if isinstance(admission_timeout, str):
        admission_timeout = float(admission_timeout)
    return ProxySettings(
        upstream=args.upstream,
        policy=args.policy,
        schema_limit_overrides=schema_overrides,
        engine_limit_overrides=engine_overrides,
        timeout_s=args.timeout_s,
        memory_bytes=None if args.memory_mb <= 0 else args.memory_mb << 20,
        cpu_seconds=cpu_seconds,
        admission_timeout_s=admission_timeout,
        admission_workers=args.admission_workers,
        grammar_dialect=args.grammar_dialect,
        on_invalid=args.on_invalid,
        check_all_tool_schemas=args.check_all_tool_schemas,
        cache_size=args.cache_size,
        max_body_bytes=None if args.max_body_mb <= 0 else int(args.max_body_mb * (1 << 20)),
        scan_all_json_requests=not args.no_scan_all_json,
        **proxy_overrides,
    )


def build_settings(argv: typing.Sequence[str] | None = None) -> tuple[ProxySettings, argparse.Namespace]:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return settings_from_args(args), args
    except ValueError as error:
        parser.error(str(error))
        raise AssertionError("unreachable")  # pragma: no cover


def main(argv: typing.Sequence[str] | None = None) -> int:
    settings, args = build_settings(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
