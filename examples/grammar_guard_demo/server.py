"""Minimal OpenAI-compatible upstream for the GrammarGuard demo.

Serves ``Qwen/Qwen2.5-0.5B-Instruct`` (loaded once, MPS if available) behind
``POST /v1/chat/completions`` and ``GET /v1/models``. When a request carries
``response_format: {"type": "json_schema", "json_schema": {"schema": ...}}`` the schema is

1. parsed fail-closed with the proxy's own parser (duplicate keys, absurd nesting),
2. admitted with :func:`formatron.security.admit_json_schema` (defense in depth: the
   GrammarGuard proxy in front of this server makes the same decision, and a rejected
   schema gets the same HTTP 400 error contract here),
3. compiled into a Formatron JSON formatter under the hardened KBNF engine config,
4. enforced token by token through a logits processor during generation.

Without a schema the model generates freely. Every request logs its timings
(schema->grammar, engine build, generation, tokens/s) and returns them in a
``grammar_guard`` extension field of the completion body.

Run: ``python server.py --port 8000`` (see ``--help``).
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import json
import logging
import os
import threading
import time
import typing
import uuid

# The model and tokenizer are expected to be in the Hugging Face cache already; stay
# offline by default so a missing network never turns into a 30 s hang. Override with
# ``HF_HUB_OFFLINE=0`` to allow downloads.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from transformers import (  # noqa: E402
    AutoModelForCausalLM,
    AutoTokenizer,
    LogitsProcessor,
    LogitsProcessorList,
)

from formatron.formatter import Formatter, FormatterBuilder  # noqa: E402
from formatron.integrations.transformers import (  # noqa: E402
    FormattersLogitsProcessor,
    create_engine_vocabulary,
)
from formatron.proxy.constraints import ConstraintError, ConstraintRejected, parse_json_body  # noqa: E402
from formatron.proxy.policy import ProxySettings  # noqa: E402
from formatron.security import (  # noqa: E402
    AdmissionResult,
    LimitViolation,
    SchemaLimits,
    admit_json_schema,
    hardened_json_schema,
)

logger = logging.getLogger("grammar_guard_demo.server")

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
HEADER_UPSTREAM_DECISION = "x-grammar-guard-upstream"
SCHEMA_PARAM = "response_format.json_schema.schema"
# The proxy fills these in for schemas that omit them (OpenAI-style schemas usually do);
# the upstream must use the same defaults so both sides convert the same document.
_PROXY_DEFAULTS = ProxySettings()
DEFAULT_SCHEMA_ID = _PROXY_DEFAULTS.default_schema_id
DEFAULT_SCHEMA_DIALECT = _PROXY_DEFAULTS.default_schema_dialect


# --------------------------------------------------------------------------------------
# Error contract (mirrors formatron.proxy so the demo can show proxy and server agree)
# --------------------------------------------------------------------------------------


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
    headers = {HEADER_UPSTREAM_DECISION: f"rejected; code={code}; elapsed_ms={elapsed_ms:.1f}"}
    return JSONResponse(body, status_code=status_code, headers=headers)


def _admission_rejection(result: AdmissionResult) -> JSONResponse:
    code = "resource_limit_exceeded" if result.outcome == "rejected" else "invalid_constraint"
    message = f"JSON schema constraint at {SCHEMA_PARAM} was not admitted: {result.reason}"
    return _error_response(
        400, message, code, SCHEMA_PARAM, violation=result.violation, elapsed_ms=result.elapsed_ms
    )


# --------------------------------------------------------------------------------------
# Logits processing on non-CPU devices
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# The engine: one model, one vocabulary, a small formatter cache, one generation at a time
# --------------------------------------------------------------------------------------


class DemoEngine:
    def __init__(self, model_name: str, device: str, default_max_new_tokens: int, max_new_tokens_cap: int):
        self.model_name = model_name
        self.default_max_new_tokens = default_max_new_tokens
        self.max_new_tokens_cap = max_new_tokens_cap
        self.lock = threading.Lock()
        self.formatter_cache: collections.OrderedDict[str, tuple[Formatter, int]] = collections.OrderedDict()
        self.formatter_cache_size = 32

        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = device
        dtype = torch.float32 if device == "cpu" else torch.float16

        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(model_name, dtype=dtype).to(device).eval()
        self.model_load_s = time.perf_counter() - started

        started = time.perf_counter()
        # Built once: it decodes the tokenizer's byte-level BPE vocabulary into raw bytes.
        self.vocabulary = create_engine_vocabulary(self.tokenizer)
        self.vocabulary_build_s = time.perf_counter() - started
        logger.info(
            "model loaded model=%s device=%s dtype=%s load_s=%.2f vocabulary_s=%.2f vocab_size=%d",
            model_name, device, dtype, self.model_load_s, self.vocabulary_build_s, len(self.tokenizer.get_vocab()),
        )

    # -- constraints ---------------------------------------------------------------------

    @staticmethod
    def prepare_schema(schema: dict[str, typing.Any]) -> dict[str, typing.Any]:
        prepared = dict(schema)
        prepared.setdefault("$id", DEFAULT_SCHEMA_ID)
        prepared.setdefault("$schema", DEFAULT_SCHEMA_DIALECT)
        return prepared

    def formatter_for(self, prepared: dict[str, typing.Any]) -> tuple[Formatter, dict[str, float | int | bool]]:
        """Return a (reset) formatter for an admitted schema plus its build timings."""
        key = json.dumps(prepared, sort_keys=True, separators=(",", ":"))
        cached = self.formatter_cache.get(key)
        if cached is not None:
            self.formatter_cache.move_to_end(key)
            formatter, grammar_bytes = cached
            formatter.reset()
            return formatter, {"schema_to_grammar_ms": 0.0, "engine_build_ms": 0.0,
                               "grammar_bytes": grammar_bytes, "engine_cached": True}

        started = time.perf_counter()
        # Limits were already enforced by admit_json_schema; this is the plain conversion.
        schema_type = hardened_json_schema(prepared, limits=SchemaLimits.unlimited())
        builder = FormatterBuilder()
        builder.append_line(f"{builder.json(schema_type, capture_name='json')}")
        grammar = builder.grammar_string()
        schema_to_grammar_ms = (time.perf_counter() - started) * 1000.0

        started = time.perf_counter()
        formatter = builder.build(self.vocabulary, lambda ids: self.tokenizer.decode(ids), hardened=True)
        engine_build_ms = (time.perf_counter() - started) * 1000.0

        grammar_bytes = len(grammar.encode("utf-8"))
        self.formatter_cache[key] = (formatter, grammar_bytes)
        while len(self.formatter_cache) > self.formatter_cache_size:
            self.formatter_cache.popitem(last=False)
        return formatter, {"schema_to_grammar_ms": schema_to_grammar_ms, "engine_build_ms": engine_build_ms,
                           "grammar_bytes": grammar_bytes, "engine_cached": False}

    # -- generation ----------------------------------------------------------------------

    def generate(
        self,
        messages: list[dict[str, typing.Any]],
        *,
        formatter: Formatter | None,
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> dict[str, typing.Any]:
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        prompt_tokens = int(inputs.input_ids.shape[1])

        kwargs: dict[str, typing.Any] = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if temperature > 0:
            kwargs.update(do_sample=True, temperature=temperature, top_p=top_p)
        else:
            kwargs.update(do_sample=False)
        inner: FormattersLogitsProcessor | None = None
        if formatter is not None:
            inner = FormattersLogitsProcessor([formatter], self.tokenizer.eos_token_id)
            kwargs["logits_processor"] = LogitsProcessorList([inner])

        with self.lock:  # one generation at a time: the model is not re-entrant
            started = time.perf_counter()
            with torch.no_grad():
                output = self.model.generate(**inputs, **kwargs)
            generation_s = time.perf_counter() - started

        new_ids = output[0][prompt_tokens:].tolist()
        stopped_on_eos = bool(new_ids) and new_ids[-1] in self._stop_ids()
        completion_ids = [tid for tid in new_ids if tid not in self._stop_ids()]
        text = self.tokenizer.decode(completion_ids, skip_special_tokens=True)
        completed = formatter.is_completed() if formatter is not None else None
        captures = inner.formatters_captures[0] if inner is not None else None
        finish_reason = "stop" if (completed or stopped_on_eos) else "length"
        tokens = len(new_ids)
        return {
            "text": text,
            "finish_reason": finish_reason,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": tokens,
            "generation_ms": generation_s * 1000.0,
            "tokens_per_s": tokens / generation_s if generation_s > 0 else 0.0,
            "completed": completed,
            "captured_json": captures.get("json") if captures else None,
        }

    def _stop_ids(self) -> set[int]:
        ids = {self.tokenizer.eos_token_id}
        pad = self.tokenizer.pad_token_id
        if pad is not None:
            ids.add(pad)
        return ids


# --------------------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------------------


def create_app(engine_factory: typing.Callable[[], DemoEngine]) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> typing.AsyncIterator[None]:
        app.state.engine = await run_in_threadpool(engine_factory)
        yield

    app = FastAPI(title="GrammarGuard demo upstream", lifespan=lifespan, openapi_url=None, docs_url=None,
                  redoc_url=None)

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        engine: DemoEngine | None = getattr(request.app.state, "engine", None)
        if engine is None:
            return JSONResponse({"status": "loading"}, status_code=503)
        return JSONResponse({
            "status": "ok",
            "model": engine.model_name,
            "device": engine.device,
            "model_load_s": round(engine.model_load_s, 2),
            "vocabulary_build_s": round(engine.vocabulary_build_s, 2),
        })

    @app.get("/v1/models")
    def models(request: Request) -> JSONResponse:
        engine: DemoEngine = request.app.state.engine
        return JSONResponse({
            "object": "list",
            "data": [{"id": engine.model_name, "object": "model", "created": int(time.time()),
                      "owned_by": "grammar-guard-demo"}],
        })

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> JSONResponse:
        engine: DemoEngine = request.app.state.engine
        request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()

        raw = await request.body()
        try:
            body = parse_json_body(raw)
        except ConstraintRejected as error:  # e.g. nesting deep enough to exhaust the decoder
            return _error_response(400, str(error), "resource_limit_exceeded", error.param, violation=error.violation)
        except ConstraintError as error:
            return _error_response(400, str(error), "invalid_constraint", error.param,
                                   error_type="invalid_request_error")

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return _error_response(400, "messages must be a non-empty list", "invalid_request", "messages",
                                   error_type="invalid_request_error")
        if body.get("stream"):
            return _error_response(400, "streaming is not supported by the demo server", "unsupported", "stream",
                                   error_type="invalid_request_error")

        requested = body.get("max_tokens") or body.get("max_completion_tokens") or engine.default_max_new_tokens
        max_new_tokens = max(1, min(int(requested), engine.max_new_tokens_cap))
        temperature = float(body.get("temperature", 0.0) or 0.0)
        top_p = float(body.get("top_p", 1.0) or 1.0)

        # -- constraint admission + grammar construction --------------------------------
        formatter: Formatter | None = None
        grammar_guard: dict[str, typing.Any] = {"constrained": False, "admission": "unconstrained"}
        response_format = body.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            json_schema = response_format.get("json_schema")
            schema = json_schema.get("schema") if isinstance(json_schema, dict) else None
            if not isinstance(schema, dict):
                return _error_response(400, "response_format.json_schema.schema must be an object",
                                       "invalid_constraint", SCHEMA_PARAM)
            prepared = engine.prepare_schema(schema)
            admission = admit_json_schema(prepared)
            if not admission.admitted:
                logger.info("request id=%s admission=%s code=%s resource=%s elapsed_ms=%.2f",
                            request_id, admission.outcome,
                            "resource_limit_exceeded" if admission.outcome == "rejected" else "invalid_constraint",
                            admission.violation.resource if admission.violation else "-", admission.elapsed_ms)
                return _admission_rejection(admission)
            formatter, build_timings = await run_in_threadpool(engine.formatter_for, prepared)
            grammar_guard = {
                "constrained": True,
                "admission": admission.outcome,
                "admission_ms": round(admission.elapsed_ms, 3),
                "schema_complexity": admission.schema_complexity,
                **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in build_timings.items()},
            }

        # -- generation ------------------------------------------------------------------
        result = await run_in_threadpool(
            engine.generate, messages, formatter=formatter, max_new_tokens=max_new_tokens,
            temperature=temperature, top_p=top_p,
        )
        total_ms = (time.perf_counter() - started) * 1000.0
        grammar_guard.update({
            "generation_ms": round(result["generation_ms"], 1),
            "tokens_per_s": round(result["tokens_per_s"], 1),
            "grammar_completed": result["completed"],
            "device": engine.device,
            "total_ms": round(total_ms, 1),
        })
        logger.info(
            "request id=%s constrained=%s admission_ms=%s schema_to_grammar_ms=%s engine_build_ms=%s "
            "engine_cached=%s generation_ms=%.1f completion_tokens=%d tokens_per_s=%.1f finish=%s "
            "grammar_completed=%s total_ms=%.1f",
            request_id, grammar_guard["constrained"], grammar_guard.get("admission_ms", "-"),
            grammar_guard.get("schema_to_grammar_ms", "-"), grammar_guard.get("engine_build_ms", "-"),
            grammar_guard.get("engine_cached", "-"), result["generation_ms"], result["completion_tokens"],
            result["tokens_per_s"], result["finish_reason"], result["completed"], total_ms,
        )

        completion = {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": engine.model_name,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": result["text"]},
                "finish_reason": result["finish_reason"],
            }],
            "usage": {
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["prompt_tokens"] + result["completion_tokens"],
            },
            "grammar_guard": grammar_guard,
        }
        header = ("admitted; elapsed_ms=%.1f" % grammar_guard["admission_ms"]) if formatter is not None else "unconstrained"
        return JSONResponse(completion, headers={HEADER_UPSTREAM_DECISION: header})

    return app


def main(argv: typing.Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible demo upstream with Formatron-constrained decoding")
    parser.add_argument("--model", default=os.environ.get("GRAMMAR_GUARD_DEMO_MODEL", DEFAULT_MODEL))
    parser.add_argument("--device", default="auto", help="auto (mps > cuda > cpu), mps, cuda or cpu")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-new-tokens", type=int, default=200, help="default when the request omits max_tokens")
    parser.add_argument("--max-new-tokens-cap", type=int, default=512, help="hard cap on max_tokens")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app(lambda: DemoEngine(args.model, args.device, args.max_new_tokens, args.max_new_tokens_cap))
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
