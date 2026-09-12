"""The FastAPI application: admission on completion routes, transparent passthrough elsewhere."""

from __future__ import annotations

import contextlib
import logging
import time
import typing

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from formatron.isolation import IsolatedGrammarChecker
from formatron.security import LimitViolation

from .admission import CODE_INVALID, CODE_RESOURCE_LIMIT, AdmissionService, Decision
from .constraints import ConstraintError, ConstraintRejected, extract_constraints, parse_json_body
from .policy import ProxySettings, resolve_policy

logger = logging.getLogger("formatron.proxy")

HEADER_DECISION = "x-grammar-guard"
HEADER_UNVERIFIED = "x-grammar-guard-unverified"

_HOP_BY_HOP = {
    b"connection",
    b"keep-alive",
    b"proxy-authenticate",
    b"proxy-authorization",
    b"te",
    b"trailer",
    b"trailers",
    b"transfer-encoding",
    b"upgrade",
}
_REQUEST_DROP = _HOP_BY_HOP | {b"host", b"content-length"}
_RESPONSE_DROP = _HOP_BY_HOP  # content-length / content-encoding stay valid: the body is relayed raw
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_INSPECTED_METHODS = {"POST", "PUT", "PATCH"}

MODE_GUARDED = "guarded"
"""The body must be a JSON object and is always inspected (the completion routes)."""
MODE_SCAN = "scan"
"""JSON bodies of ``POST``/``PUT``/``PATCH`` are inspected; everything else is forwarded."""
MODE_FORWARD = "forward"
"""Never inspected (``--no-scan-all-json``)."""


class _BodyTooLarge(Exception):
    def __init__(self, observed: int, limit: int):
        self.observed = observed
        self.limit = limit


def _error_response(
    status_code: int,
    message: str,
    code: str,
    param: str | None,
    *,
    violation: LimitViolation | None = None,
    elapsed_ms: float = 0.0,
    error_type: str = "grammar_guard_rejected",
) -> JSONResponse:
    body = {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
            "param": param,
            "violation": violation.to_dict() if violation else None,
            "elapsed_ms": round(elapsed_ms, 3),
        }
    }
    headers = {HEADER_DECISION: f"rejected; code={code}; elapsed_ms={elapsed_ms:.1f}"}
    return JSONResponse(body, status_code=status_code, headers=headers)


def _rejection_response(decision: Decision) -> JSONResponse:
    body = decision.error_body()
    headers = {HEADER_DECISION: f"rejected; code={decision.code}; elapsed_ms={decision.elapsed_ms:.1f}"}
    return JSONResponse(body, status_code=400, headers=headers)


async def _read_body(request: Request, limit: int | None) -> bytes:
    declared = request.headers.get("content-length")
    if limit is not None and declared and declared.isdigit() and int(declared) > limit:
        raise _BodyTooLarge(int(declared), limit)
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if limit is not None and total > limit:
            raise _BodyTooLarge(total, limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _is_json_request(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _log_decision(request: Request, status: str, decisions: list[Decision], elapsed_ms: float) -> None:
    last = decisions[-1] if decisions else None
    logger.info(
        "decision path=%s status=%s outcome=%s kind=%s param=%s code=%s resource=%s cached=%s "
        "constraints=%d elapsed_ms=%.2f",
        request.url.path,
        status,
        last.outcome if last else "unconstrained",
        last.constraint.kind if last else "-",
        last.constraint.param if last else "-",
        last.code if last else "-",
        last.resource if last else "-",
        all(decision.cached for decision in decisions) if decisions else "-",
        len(decisions),
        elapsed_ms,
        extra={
            "grammar_guard": {
                "path": request.url.path,
                "status": status,
                "decisions": [
                    {
                        "kind": decision.constraint.kind,
                        "param": decision.constraint.param,
                        "outcome": decision.outcome,
                        "code": decision.code,
                        "resource": decision.resource,
                        "cached": decision.cached,
                        "elapsed_ms": round(decision.elapsed_ms, 3),
                    }
                    for decision in decisions
                ],
            }
        },
    )


def create_app(settings: ProxySettings | None = None, *, checker: IsolatedGrammarChecker | None = None) -> FastAPI:
    """Build the proxy application.

    The isolated grammar checker and the upstream HTTP client are created on startup and
    closed on shutdown. Pass ``checker`` to share an existing checker (it is then not closed
    by the app); tests use this to keep one worker per module.
    """
    settings = settings or ProxySettings()
    policy = resolve_policy(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> typing.AsyncIterator[None]:
        owns_checker = checker is None
        active_checker = checker or IsolatedGrammarChecker(
            timeout_s=settings.timeout_s,
            memory_bytes=settings.memory_bytes,
            cpu_seconds=settings.cpu_seconds,
            engine_overrides=policy.engine_overrides,
        )
        client = httpx.AsyncClient(
            base_url=settings.upstream,
            transport=settings.upstream_transport,
            timeout=httpx.Timeout(
                connect=settings.upstream_connect_timeout_s,
                read=settings.upstream_read_timeout_s,
                write=settings.upstream_connect_timeout_s,
                pool=settings.upstream_connect_timeout_s,
            ),
            follow_redirects=False,
        )
        guard = AdmissionService(
            policy,
            active_checker,
            cache_size=settings.cache_size,
            latency_window=settings.latency_window,
        )
        app.state.settings = settings
        app.state.policy = policy
        app.state.checker = active_checker
        app.state.client = client
        app.state.guard = guard
        logger.info(
            "grammar-guard proxy ready upstream=%s policy=%s dialect=%s fingerprint=%s",
            settings.upstream,
            policy.name,
            policy.grammar_dialect,
            policy.fingerprint,
        )
        try:
            yield
        finally:
            await client.aclose()
            if owns_checker:
                active_checker.close()

    app = FastAPI(
        title="GrammarGuard admission proxy",
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )

    # -- forwarding ---------------------------------------------------------------------

    async def forward(request: Request, body: bytes, extra_headers: dict[str, str]) -> Response:
        client: httpx.AsyncClient = request.app.state.client
        guard: AdmissionService = request.app.state.guard
        raw_path = request.scope.get("raw_path")
        path = raw_path.decode("latin-1") if raw_path else request.url.path
        query = request.scope.get("query_string", b"")
        url = path + ("?" + query.decode("latin-1") if query else "")
        headers = [(name, value) for name, value in request.headers.raw if name.lower() not in _REQUEST_DROP]
        upstream_request = client.build_request(request.method, url, headers=headers, content=body or None)
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as error:
            guard.stats.record_upstream_error()
            logger.warning("upstream request failed path=%s error=%s", request.url.path, error)
            return _error_response(
                502,
                f"upstream request failed: {type(error).__name__}: {error}",
                "upstream_unavailable",
                None,
                error_type="grammar_guard_upstream_error",
            )
        response = StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            background=BackgroundTask(upstream.aclose),
        )
        relayed = [(name, value) for name, value in upstream.headers.raw if name.lower() not in _RESPONSE_DROP]
        relayed.extend((name.encode("latin-1"), value.encode("latin-1")) for name, value in extra_headers.items())
        response.raw_headers = relayed
        return response

    async def inspect_and_forward(request: Request, *, mode: str) -> Response:
        guard: AdmissionService = request.app.state.guard
        started = time.perf_counter()
        try:
            body = await _read_body(request, policy.max_body_bytes)
        except _BodyTooLarge as error:
            guard.stats.record_request("too_large")
            violation = LimitViolation("proxy", "max_body_bytes", error.observed, error.limit, "body")
            return _error_response(413, str(violation), CODE_RESOURCE_LIMIT, "body", violation=violation)

        inspect = mode == MODE_GUARDED or (
            mode == MODE_SCAN and request.method in _INSPECTED_METHODS and _is_json_request(request)
        )
        if not inspect:
            guard.stats.record_request("unconstrained")
            return await forward(request, body, {HEADER_DECISION: "passthrough"})

        try:
            payload = parse_json_body(body)
            constraints = extract_constraints(payload, check_all_tool_schemas=policy.check_all_tool_schemas)
        except ConstraintRejected as error:
            guard.stats.record_request("rejected")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info("decision path=%s status=rejected code=%s param=%s resource=%s",
                        request.url.path, CODE_RESOURCE_LIMIT, error.param, error.violation.resource)
            return _error_response(400, str(error), CODE_RESOURCE_LIMIT, error.param,
                                   violation=error.violation, elapsed_ms=elapsed_ms)
        except ConstraintError as error:
            guard.stats.record_request("rejected")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info("decision path=%s status=rejected code=%s param=%s reason=%s",
                        request.url.path, CODE_INVALID, error.param, error.message)
            return _error_response(400, str(error), CODE_INVALID, error.param, elapsed_ms=elapsed_ms)

        if not constraints:
            guard.stats.record_request("unconstrained")
            _log_decision(request, "unconstrained", [], (time.perf_counter() - started) * 1000.0)
            return await forward(request, body, {HEADER_DECISION: "unconstrained"})

        decisions = await guard.admit(constraints)
        elapsed_ms = sum(decision.elapsed_ms for decision in decisions)
        last = decisions[-1]
        if not last.admitted:
            guard.stats.record_request("rejected")
            _log_decision(request, "rejected", decisions, elapsed_ms)
            return _rejection_response(last)

        guard.stats.record_request("forwarded")
        _log_decision(request, "forwarded", decisions, elapsed_ms)
        verdict = "cached" if all(decision.cached for decision in decisions) else "admitted"
        extra_headers = {HEADER_DECISION: f"{verdict}; elapsed_ms={elapsed_ms:.1f}; constraints={len(decisions)}"}
        unverified = [f"{d.constraint.param}; reason={d.unverified}" for d in decisions if d.unverified]
        if unverified:
            extra_headers[HEADER_UNVERIFIED] = ", ".join(unverified)
        return await forward(request, body, extra_headers)

    # -- routes -------------------------------------------------------------------------

    @app.get("/grammar-guard/stats")
    async def stats(request: Request) -> JSONResponse:
        guard: AdmissionService = request.app.state.guard
        return JSONResponse(guard.stats.snapshot(guard.cache))

    @app.get("/grammar-guard/policy")
    async def policy_view(request: Request) -> JSONResponse:
        document = policy.to_dict()
        document["fingerprint"] = policy.fingerprint
        document["upstream"] = settings.upstream
        document["guarded_paths"] = list(settings.guarded_paths)
        document["scan_all_json_requests"] = settings.scan_all_json_requests
        document["cache_size"] = settings.cache_size
        return JSONResponse(document)

    @app.get("/grammar-guard/health")
    async def health(request: Request) -> JSONResponse:
        checker_state: IsolatedGrammarChecker = request.app.state.checker
        return JSONResponse({"status": "ok", "checker_alive": bool(getattr(checker_state, "alive", True))})

    async def guarded(request: Request) -> Response:
        return await inspect_and_forward(request, mode=MODE_GUARDED)

    passthrough_mode = MODE_SCAN if settings.scan_all_json_requests else MODE_FORWARD

    async def passthrough(request: Request, path: str) -> Response:  # noqa: ARG001 - path is in scope
        return await inspect_and_forward(request, mode=passthrough_mode)

    for guarded_path in settings.guarded_paths:
        app.add_api_route(guarded_path, guarded, methods=["POST"], name=f"guarded:{guarded_path}")
    app.add_api_route("/{path:path}", passthrough, methods=_METHODS, name="passthrough")
    return app
