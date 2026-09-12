"""End-to-end tests of the GrammarGuard admission proxy.

The proxy app is exercised through ``httpx.ASGITransport``; its upstream is an in-process
ASGI mock that records every forwarded request and answers with JSON or an SSE stream.
One isolated grammar checker (one worker process) is shared by every app in this module.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import time
import typing

import anyio
import httpx
import pytest

from formatron.isolation import IsolatedGrammarChecker
from formatron.proxy import ProxySettings, create_app
from formatron.proxy.constraints import (
    Constraint,
    bracket_nesting_depth,
    choices_to_kbnf,
    extract_constraints,
    kbnf_string_literal,
    regex_to_kbnf,
)
from formatron.security import AdmissionResult, LimitViolation

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------------------
# Test doubles: a recording upstream and a transport that streams ASGI responses
# --------------------------------------------------------------------------------------


class MockUpstream:
    """An ASGI app standing in for vLLM: records requests, echoes JSON, streams SSE."""

    def __init__(self) -> None:
        self.requests: list[dict[str, typing.Any]] = []
        self.gate: anyio.Event | None = None
        """When set, the SSE stream pauses after its first event until the gate is set."""

    async def __call__(self, scope, receive, send) -> None:
        assert scope["type"] == "http"
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        record = {
            "method": scope["method"],
            "path": scope["path"],
            "query": scope["query_string"],
            "headers": {name.decode(): value.decode() for name, value in scope["headers"]},
            "body": body,
        }
        self.requests.append(record)

        if scope["path"] == "/v1/models":
            await self._json(send, 200, {"object": "list", "data": [{"id": "mock-model"}]})
            return
        if scope["path"] == "/broken":
            await self._json(send, 503, {"error": "upstream exploded"})
            return
        payload = json.loads(body) if body else None
        if isinstance(payload, dict) and payload.get("stream"):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"text/event-stream"), (b"cache-control", b"no-cache")],
                }
            )
            await send({"type": "http.response.body", "body": b"data: {\"chunk\": 1}\n\n", "more_body": True})
            if self.gate is not None:
                await self.gate.wait()
            await send({"type": "http.response.body", "body": b"data: {\"chunk\": 2}\n\n", "more_body": True})
            await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})
            return
        await self._json(send, 200, {"id": "cmpl-mock", "echo": payload}, extra=[(b"x-upstream", b"mock")])

    @staticmethod
    async def _json(send, status: int, document: typing.Any, extra: list[tuple[bytes, bytes]] | None = None) -> None:
        content = json.dumps(document).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(content)).encode())]
        headers.extend(extra or [])
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": content, "more_body": False})


class _ASGIBodyStream(httpx.AsyncByteStream):
    def __init__(self, receive_stream, task: asyncio.Task, disconnect: anyio.Event):
        self._receive = receive_stream
        self._task = task
        self._disconnect = disconnect

    async def __aiter__(self) -> typing.AsyncIterator[bytes]:
        async with self._receive:
            async for chunk in self._receive:
                yield chunk
        await self._task  # surface application exceptions

    async def aclose(self) -> None:
        self._disconnect.set()
        if not self._task.done():
            self._task.cancel()
        await self._receive.aclose()


class StreamingASGITransport(httpx.AsyncBaseTransport):
    """Like ``httpx.ASGITransport`` but relays body chunks as the app produces them.

    ``httpx.ASGITransport`` collects the whole response body before returning, which would
    make a "does the proxy buffer SSE?" test vacuous. This transport runs the ASGI app as a
    task and hands each ``http.response.body`` chunk to the reader immediately.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request_body = b"".join([chunk async for chunk in request.stream])  # type: ignore[union-attr]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?", 1)[0],
            "query_string": request.url.query,
            "root_path": "",
            "headers": [(name.lower(), value) for name, value in request.headers.raw],
            "server": (request.url.host, request.url.port or 80),
            "client": ("127.0.0.1", 12345),
        }
        send_stream, receive_stream = anyio.create_memory_object_stream[bytes](math.inf)
        started = anyio.Event()
        disconnect = anyio.Event()
        head: dict[str, typing.Any] = {}
        body_delivered = False

        async def receive() -> dict[str, typing.Any]:
            nonlocal body_delivered
            if body_delivered:
                await disconnect.wait()
                return {"type": "http.disconnect"}
            body_delivered = True
            return {"type": "http.request", "body": request_body, "more_body": False}

        async def send(message: dict[str, typing.Any]) -> None:
            if message["type"] == "http.response.start":
                head["status"] = message["status"]
                head["headers"] = list(message.get("headers", []))
                started.set()
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    await send_stream.send(chunk)
                if not message.get("more_body", False):
                    await send_stream.aclose()

        async def run() -> None:
            try:
                await self.app(scope, receive, send)
            finally:
                await send_stream.aclose()
                started.set()

        task = asyncio.create_task(run())
        await started.wait()
        if "status" not in head:
            await task  # raises the app's exception
            raise RuntimeError("ASGI app finished without starting a response")
        stream = _ASGIBodyStream(receive_stream, task, disconnect)
        return httpx.Response(head["status"], headers=head["headers"], stream=stream, request=request)


# --------------------------------------------------------------------------------------
# Fixtures: one worker, one proxy app, one client per module
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def checker() -> typing.Iterator[IsolatedGrammarChecker]:
    with IsolatedGrammarChecker(timeout_s=5.0, memory_bytes=None) as instance:
        instance.check("start ::= 'warm';")
        yield instance


@pytest.fixture(scope="module")
def upstream() -> MockUpstream:
    return MockUpstream()


def _settings(upstream: MockUpstream, **overrides: typing.Any) -> ProxySettings:
    defaults = dict(
        upstream="http://upstream.invalid",
        upstream_transport=StreamingASGITransport(upstream),
        timeout_s=5.0,
        memory_bytes=None,
        cache_size=64,
    )
    defaults.update(overrides)
    return ProxySettings(**defaults)


@pytest.fixture(scope="module")
async def proxy(checker: IsolatedGrammarChecker, upstream: MockUpstream):
    app = create_app(_settings(upstream), checker=checker)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy.invalid") as client:
            yield client, app


@pytest.fixture(scope="module")
async def kbnf_proxy(checker: IsolatedGrammarChecker, upstream: MockUpstream):
    """A second app over the same worker with ``guided_grammar`` compiled as KBNF."""
    app = create_app(_settings(upstream, grammar_dialect="kbnf"), checker=checker)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy.invalid") as client:
            yield client, app


@pytest.fixture
def client(proxy) -> httpx.AsyncClient:
    return proxy[0]


@pytest.fixture(autouse=True)
def _reset_upstream(upstream: MockUpstream) -> None:
    upstream.requests.clear()
    upstream.gate = None


# --------------------------------------------------------------------------------------
# Request builders
# --------------------------------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string", "maxLength": 32}, "age": {"type": "integer"}},
    "required": ["name"],
}


def chat(**extra: typing.Any) -> dict[str, typing.Any]:
    body = {"model": "mock-model", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8}
    body.update(extra)
    return body


def response_format(schema: dict[str, typing.Any]) -> dict[str, typing.Any]:
    return {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}


def error_of(response: httpx.Response) -> dict[str, typing.Any]:
    assert response.status_code == 400, response.text
    document = response.json()
    error = document["error"]
    assert error["type"] == "grammar_guard_rejected"
    assert set(error) == {"message", "type", "code", "param", "violation", "elapsed_ms"}
    return error


# --------------------------------------------------------------------------------------
# Forwarding
# --------------------------------------------------------------------------------------


async def test_admitted_chat_request_is_forwarded_verbatim(client, upstream):
    body = chat(response_format=response_format(SCHEMA), temperature=0.2)
    raw = json.dumps(body, indent=1).encode()  # non-canonical bytes must survive untouched
    response = await client.post(
        "/v1/chat/completions?trace=1",
        content=raw,
        headers={"content-type": "application/json", "authorization": "Bearer secret", "x-request-id": "r1",
                 "connection": "keep-alive"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["echo"] == body
    assert response.headers["x-upstream"] == "mock"
    verdict = response.headers["x-grammar-guard"]
    assert verdict.startswith("admitted; elapsed_ms=")
    assert "x-grammar-guard-unverified" not in response.headers

    assert len(upstream.requests) == 1
    forwarded = upstream.requests[0]
    assert forwarded["method"] == "POST"
    assert forwarded["path"] == "/v1/chat/completions"
    assert forwarded["query"] == b"trace=1"
    assert forwarded["body"] == raw
    assert forwarded["headers"]["authorization"] == "Bearer secret"
    assert forwarded["headers"]["x-request-id"] == "r1"
    assert forwarded["headers"]["host"] == "upstream.invalid"


async def test_schema_without_id_and_dialect_is_admitted(client, upstream):
    assert "$id" not in SCHEMA and "$schema" not in SCHEMA
    response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_json": SCHEMA})
    assert response.status_code == 200, response.text
    assert upstream.requests[0]["body"] == response.request.content  # defaults are not written back


async def test_sse_stream_is_relayed_without_buffering(checker, upstream):
    app = create_app(_settings(upstream), checker=checker)
    upstream.gate = anyio.Event()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=StreamingASGITransport(app), base_url="http://proxy.invalid") as client:
            request = chat(stream=True, guided_regex="[a-z]{1,8}")
            async with client.stream("POST", "/v1/chat/completions", json=request) as response:
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream"
                assert response.headers["x-grammar-guard"].startswith("admitted; ")
                received: list[bytes] = []
                async for chunk in response.aiter_raw():
                    received.append(chunk)
                    if len(received) == 1:
                        # The first event arrived while the upstream is still blocked on the gate:
                        # the proxy relays chunks as they come instead of buffering the body.
                        assert not upstream.gate.is_set()
                        upstream.gate.set()
                assert b"".join(received) == b'data: {"chunk": 1}\n\ndata: {"chunk": 2}\n\ndata: [DONE]\n\n'
                assert received[0] == b'data: {"chunk": 1}\n\n'


async def test_catch_all_get_is_forwarded(client, upstream):
    response = await client.get("/v1/models?limit=5", headers={"authorization": "Bearer t"})
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "mock-model"
    assert response.headers["x-grammar-guard"] == "passthrough"
    forwarded = upstream.requests[0]
    assert (forwarded["method"], forwarded["path"], forwarded["query"]) == ("GET", "/v1/models", b"limit=5")
    assert forwarded["headers"]["authorization"] == "Bearer t"
    assert "content-length" not in forwarded["headers"]


async def test_unconstrained_completion_and_json_object_are_forwarded(client, upstream):
    response = await client.post("/v1/chat/completions", json=chat(response_format={"type": "json_object"}))
    assert response.status_code == 200
    assert response.headers["x-grammar-guard"] == "unconstrained"
    assert len(upstream.requests) == 1


async def test_upstream_status_is_relayed(client):
    response = await client.post("/broken", json={"anything": True})
    assert response.status_code == 503
    assert response.json() == {"error": "upstream exploded"}


async def test_other_json_posts_are_scanned_for_constraints(client, upstream):
    body = {"model": "m", "input": "x", "text": {"format": {"type": "json_schema", "schema": {"enum": list(range(5000))}}}}
    response = await client.post("/v1/responses", json=body)
    error = error_of(response)
    assert error["param"] == "text.format.schema"
    assert error["violation"]["resource"] == "max_enum_members"
    assert upstream.requests == []


async def test_no_scan_all_json_only_guards_completion_paths(checker, upstream):
    app = create_app(_settings(upstream, scan_all_json_requests=False), checker=checker)
    hostile = {"type": "json_schema", "schema": {"enum": list(range(5000))}}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy.invalid") as client:
            response = await client.post("/v1/responses", json={"model": "m", "text": {"format": hostile}})
            assert response.status_code == 200
            assert response.headers["x-grammar-guard"] == "passthrough"
            assert len(upstream.requests) == 1

            response = await client.post("/v1/chat/completions", json=chat(guided_regex="(a{1,200}){1,200}"))
            assert error_of(response)["code"] == "resource_limit_exceeded"
            assert len(upstream.requests) == 1


# --------------------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------------------


async def test_oversized_enum_schema_is_rejected(client, upstream):
    schema = {"enum": list(range(5000))}
    response = await client.post("/v1/chat/completions", json=chat(response_format=response_format(schema)))
    error = error_of(response)
    assert error["code"] == "resource_limit_exceeded"
    assert error["param"] == "response_format.json_schema.schema"
    assert error["violation"]["resource"] == "max_enum_members"
    assert error["violation"]["observed"] == 5000
    assert error["violation"]["limit"] == 2048
    assert error["violation"]["phase"] == "schema"
    assert response.headers["x-grammar-guard"].startswith("rejected; code=resource_limit_exceeded")
    assert upstream.requests == []


async def test_nested_counted_repetition_regex_is_rejected(client, upstream):
    response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_regex": "(a{1,200}){1,200}"})
    error = error_of(response)
    assert error["code"] == "resource_limit_exceeded"
    assert error["param"] == "guided_regex"
    assert error["violation"]["resource"] == "regex_size_estimate"
    assert error["violation"]["phase"] == "parsed"
    assert upstream.requests == []


async def test_oversized_choice_list_is_rejected(client, upstream):
    choices = [f"option-{index}" for index in range(2000)]
    response = await client.post("/v1/chat/completions", json=chat(guided_choice=choices))
    error = error_of(response)
    assert error["code"] == "resource_limit_exceeded"
    assert error["param"] == "guided_choice"
    assert error["violation"] == {"phase": "proxy", "resource": "max_choices", "observed": 2000, "limit": 1024,
                                  "path": "guided_choice"}
    assert upstream.requests == []


async def test_reasonable_choice_list_with_quotes_is_admitted(client, upstream):
    choices = ["yes", "no", "it's complicated", "back\\slash", "日本語"]
    response = await client.post("/v1/chat/completions", json=chat(extra_body={"guided_choice": choices}))
    assert response.status_code == 200, response.text
    assert response.headers["x-grammar-guard"].startswith("admitted; ")
    assert len(upstream.requests) == 1


async def test_passthrough_grammar_nesting_limit_and_unverified_header(client, upstream):
    deep = "root ::= " + "(" * 65 + "'a'" + ")" * 65 + "\n"
    response = await client.post("/v1/chat/completions", json=chat(guided_grammar=deep))
    error = error_of(response)
    assert error["code"] == "resource_limit_exceeded"
    assert error["param"] == "guided_grammar"
    assert error["violation"]["resource"] == "max_grammar_nesting"
    assert error["violation"]["observed"] == 65
    assert upstream.requests == []

    lark = 'start: "yes" | "no"\n%import common.WS\n'
    response = await client.post("/v1/chat/completions", json=chat(guided_grammar=lark))
    assert response.status_code == 200, response.text
    assert response.headers["x-grammar-guard"].startswith("admitted; ")
    assert response.headers["x-grammar-guard-unverified"] == "guided_grammar; reason=dialect-passthrough"
    assert len(upstream.requests) == 1


async def test_kbnf_dialect_grammar_is_compiled_in_the_worker(kbnf_proxy, upstream):
    client, _ = kbnf_proxy
    hostile = "start ::= #'(a{1,200}){1,200}';"
    response = await client.post("/v1/chat/completions", json=chat(guided_grammar=hostile))
    error = error_of(response)
    assert error["code"] == "resource_limit_exceeded"
    assert error["param"] == "guided_grammar"
    assert error["violation"]["resource"] == "regex_size_estimate"

    response = await client.post("/v1/chat/completions", json=chat(guided_grammar="start ::= ;;; nonsense"))
    error = error_of(response)
    assert error["code"] == "invalid_constraint"
    assert error["violation"] is None

    response = await client.post("/v1/chat/completions", json=chat(guided_grammar="start ::= 'yes' | 'no';"))
    assert response.status_code == 200, response.text
    assert "x-grammar-guard-unverified" not in response.headers
    assert len(upstream.requests) == 1


async def test_invalid_schema_is_rejected_as_invalid_constraint(client, upstream):
    response = await client.post("/v1/chat/completions", json=chat(response_format=response_format({"type": "string"})))
    error = error_of(response)
    assert error["code"] == "invalid_constraint"
    assert error["param"] == "response_format.json_schema.schema"
    assert error["violation"] is None
    assert "Root schema type" in error["message"]
    assert upstream.requests == []


async def test_malformed_and_duplicate_key_bodies_fail_closed(client, upstream):
    headers = {"content-type": "application/json"}
    response = await client.post("/v1/chat/completions", content=b'{"model": "m", "messages": [', headers=headers)
    error = error_of(response)
    assert error["code"] == "invalid_constraint"
    assert error["param"] == "body"

    duplicate = b'{"model": "m", "messages": [], "guided_regex": "a", "guided_regex": "(a{1,200}){1,200}"}'
    response = await client.post("/v1/chat/completions", content=duplicate, headers=headers)
    error = error_of(response)
    assert error["code"] == "invalid_constraint"
    assert "duplicate" in error["message"]
    assert upstream.requests == []


async def test_first_rejection_wins_with_multiple_constraints(client, upstream):
    body = chat(
        response_format=response_format(SCHEMA),
        guided_regex="[0-9]+",
        guided_choice=[f"c{index}" for index in range(2000)],
        extra_body={"guided_regex": "(a{1,200}){1,200}"},
    )
    response = await client.post("/v1/chat/completions", json=body)
    error = error_of(response)
    assert error["param"] == "guided_choice"  # checked in extraction order: the first failure is reported
    assert upstream.requests == []


async def test_string_guided_json_and_structured_outputs_nesting(client, upstream):
    structured = {"structured_outputs": {"json": json.dumps({"enum": list(range(5000))})}}
    response = await client.post("/v1/chat/completions", json=chat(**structured))
    error = error_of(response)
    assert error["param"] == "structured_outputs.json"
    assert error["violation"]["resource"] == "max_enum_members"

    response = await client.post("/v1/chat/completions", json=chat(structured_outputs={"regex": "[a-z]+"}))
    assert response.status_code == 200, response.text
    assert len(upstream.requests) == 1


async def test_named_tool_parameters_are_checked(client, upstream):
    tool = {"type": "function", "function": {"name": "pick", "parameters": {"type": "object", "properties": {
        "n": {"enum": list(range(5000))}}}}}
    body = chat(tools=[tool], tool_choice={"type": "function", "function": {"name": "pick"}})
    response = await client.post("/v1/chat/completions", json=body)
    error = error_of(response)
    assert error["param"] == "tools[0].function.parameters"

    body = chat(tools=[tool], tool_choice="auto")
    response = await client.post("/v1/chat/completions", json=body)
    assert response.status_code == 200  # auto tool choice is not a constraint by default


# --------------------------------------------------------------------------------------
# Cache, timeouts, crashes
# --------------------------------------------------------------------------------------


async def test_second_identical_request_hits_the_cache(client, upstream):
    schema = copy.deepcopy(SCHEMA)
    schema["properties"]["cache_probe"] = {"type": "boolean"}
    body = chat(response_format=response_format(schema))
    before = (await client.get("/grammar-guard/stats")).json()["cache"]["hits"]

    first = await client.post("/v1/chat/completions", json=body)
    assert first.headers["x-grammar-guard"].startswith("admitted; ")
    second = await client.post("/v1/chat/completions", json=body)
    assert second.status_code == 200
    assert second.headers["x-grammar-guard"].startswith("cached; elapsed_ms=")

    after = (await client.get("/grammar-guard/stats")).json()["cache"]
    assert after["hits"] == before + 1
    assert after["size"] >= 1
    assert len(upstream.requests) == 2


async def test_worker_timeout_maps_to_constraint_check_timeout(client, upstream, checker, monkeypatch):
    def stalled(grammar, *, engine_overrides=None, timeout_s=None):
        violation = LimitViolation("isolation", "wall_clock_ms", 5000, 5000)
        return AdmissionResult(False, "timeout", "grammar check exceeded 5.000s wall clock; worker killed", violation)

    monkeypatch.setattr(checker, "check", stalled)
    response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_regex": "timeout-probe-[a-z]+"})
    error = error_of(response)
    assert error["code"] == "constraint_check_timeout"
    assert error["param"] == "guided_regex"
    assert error["violation"]["resource"] == "wall_clock_ms"
    assert upstream.requests == []


async def test_worker_crash_and_checker_exception_fail_closed(client, upstream, checker, monkeypatch):
    def crashed(grammar, *, engine_overrides=None, timeout_s=None):
        return AdmissionResult(False, "crashed", "grammar checker worker died (exit code 9)",
                               LimitViolation("isolation", "worker_exit", 9, 0))

    monkeypatch.setattr(checker, "check", crashed)
    response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_regex": "crash-probe-[a-z]+"})
    error = error_of(response)
    assert error["code"] == "constraint_check_failed"
    assert error["violation"]["resource"] == "worker_exit"

    def exploding(grammar, *, engine_overrides=None, timeout_s=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(checker, "check", exploding)
    response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_regex": "boom-probe-[a-z]+"})
    error = error_of(response)
    assert error["code"] == "constraint_check_failed"
    assert error["violation"] is None
    assert upstream.requests == []


async def test_per_request_budget_maps_to_constraint_check_timeout(upstream):
    class SlowChecker:
        def check(self, grammar, *, engine_overrides=None, timeout_s=None):
            time.sleep(0.5)
            return AdmissionResult(True, "admitted")

        def close(self) -> None:
            pass

    settings = _settings(upstream, admission_timeout_s=0.05, admission_workers=1)
    app = create_app(settings, checker=SlowChecker())  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy.invalid") as client:
            response = await client.post("/v1/completions", json={"model": "m", "prompt": "x", "guided_regex": "[a-z]+"})
            error = error_of(response)
            assert error["code"] == "constraint_check_timeout"
            assert error["violation"]["resource"] == "admission_timeout_ms"
            assert error["violation"]["limit"] == 50
            # Load-dependent budget timeouts are not cached: the retry gets a fresh check.
            stats = (await client.get("/grammar-guard/stats")).json()
            assert stats["cache"]["size"] == 0
    assert upstream.requests == []


# --------------------------------------------------------------------------------------
# Introspection endpoints
# --------------------------------------------------------------------------------------


async def test_stats_shape(client):
    stats = (await client.get("/grammar-guard/stats")).json()
    assert set(stats) == {"uptime_s", "requests", "constraints", "admission_latency_ms", "cache"}
    assert set(stats["requests"]) == {"total", "forwarded", "rejected", "unconstrained", "too_large", "upstream_errors"}
    assert set(stats["constraints"]["by_outcome"]) == {"admitted", "rejected", "invalid", "timeout", "crashed"}
    assert stats["constraints"]["by_outcome"]["rejected"] >= 1
    assert stats["constraints"]["by_violation_resource"]["regex_size_estimate"] >= 1
    assert stats["constraints"]["by_code"]["resource_limit_exceeded"] >= 1
    latency = stats["admission_latency_ms"]
    assert set(latency) == {"samples", "p50", "p99", "max", "mean"}
    assert latency["samples"] > 0 and 0 <= latency["p50"] <= latency["p99"] <= latency["max"]
    assert set(stats["cache"]) == {"hits", "misses", "size", "capacity"}
    assert stats["cache"]["capacity"] == 64


async def test_policy_shape(client):
    policy = (await client.get("/grammar-guard/policy")).json()
    assert policy["policy"] == "hardened"
    assert policy["grammar_dialect"] == "passthrough"
    assert policy["schema_limits"]["max_enum_members"] == 2048
    assert policy["proxy_limits"] == {
        "max_constraint_bytes": 1 << 20, "max_regex_bytes": 65_536, "max_choices": 1024,
        "max_choice_bytes": 65_536, "max_grammar_bytes": 65_536, "max_grammar_nesting": 64,
    }
    assert "max_source_bytes" in policy["engine_limits"]["grammar"]
    assert "max_earley_items_per_set" in policy["engine_limits"]["decode"]
    assert policy["isolation"]["timeout_s"] == 5.0
    assert policy["schema_defaults"]["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert policy["guarded_paths"] == ["/v1/chat/completions", "/v1/completions"]
    assert len(policy["fingerprint"]) == 16


async def test_health(client):
    response = await client.get("/grammar-guard/health")
    assert response.json()["status"] == "ok"


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------


def test_kbnf_construction_matches_formatron_escaping():
    # Formatron quotes regexes with repr(); for strings without quote characters the two agree
    # byte for byte, and KBNF un-escapes both ``\\\\`` and ``\\'`` inside a single-quoted literal.
    assert kbnf_string_literal("a\\d+ b") == repr("a\\d+ b") == "'a\\\\d+ b'"
    assert kbnf_string_literal("it's \\ done") == "'it\\'s \\\\ done'"
    assert regex_to_kbnf("\\d+") == "start ::= #'\\\\d+';"
    assert choices_to_kbnf(["a", "b'c"]) == "start ::= 'a' | 'b\\'c';"
    assert bracket_nesting_depth("a(b[c{d}])e)") == 3
    assert bracket_nesting_depth("no brackets") == 0


def test_extract_constraints_order_and_paths():
    body = {
        "response_format": response_format(SCHEMA),
        "guided_regex": "x",
        "extra_body": {"guided_choice": ["a"], "structured_outputs": {"grammar": "g"}},
        "tools": [{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}],
        "tool_choice": "required",
    }
    found = extract_constraints(body)
    assert [(item.kind, item.param) for item in found] == [
        ("json_schema", "response_format.json_schema.schema"),
        ("regex", "guided_regex"),
        ("choice", "extra_body.guided_choice"),
        ("grammar", "extra_body.structured_outputs.grammar"),
        ("json_schema", "tools[0].function.parameters"),
    ]
    assert isinstance(found[0], Constraint)
    assert extract_constraints({"response_format": {"type": "json_object"}}) == []
