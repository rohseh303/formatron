"""Code that runs *inside* the isolated child process.

``child_main`` is the ``multiprocessing`` target.  It rebuilds the schema from
its spec (deterministic corpus), runs the requested engine, streams progress
messages back over the pipe (so the parent knows which phase a timeout hit),
and finally sends one result dict.

Nothing in here is protected against hangs or memory blow-ups on purpose: the
parent (``runner.py``) enforces the wall-clock timeout and the RSS watchdog by
killing the whole process.

kbnf paths
----------

``config == "hardened"`` is the multi-tenant admission path a server would use::

    admit_json_schema(schema)                  # SchemaLimits.hardened() + check_grammar()
    create_schema(schema); FormatterBuilder    # Python schema -> KBNF grammar
    builder.build(vocab, decode, hardened=True)  # kbnf.Engine under hardened GrammarLimits/DecodeLimits
    random walk with per-token limits

``config == "default"`` is the stock, unlimited path::

    create_schema(schema); FormatterBuilder
    builder.build(vocab, decode)               # no limits at all
    random walk

Both configs then run the same biased random walk over the vocabulary and
validate the finished document against the original schema.

The vocabulary is the synthetic ~3k-token one from ``vocab.py`` unless
``options["vocab_file"]`` names a pickle written by ``vocab.build_vocab_file``
(``runner.py --tokenizer``), in which case the child reconstructs the real
tokenizer's ``kbnf.Vocabulary`` from it and decodes with the real token bytes.
"""

from __future__ import annotations

import functools
import json
import re
import resource
import sys
import time
import traceback
import typing
import zlib

from . import corpus, vocab

# kbnf's structured message (also embedded in Formatron's ResourceLimitExceeded, which
# additionally carries an optional ``at <path>``).
LIMIT_RE = re.compile(
    r"resource limit exceeded during (?P<phase>\w+)(?: at (?P<path>\S*))?: "
    r"(?P<resource>\w+) observed (?P<observed>\d+), limit (?P<limit>\d+)"
)

OUTCOMES = ("admitted", "rejected", "timeout", "crash", "oom")

_UNSUPPORTED_MARKERS = (
    "not supported", "mutually exclusive", "anchors", "root schema", "duplicate", "circular",
    "unsupported", "empty union", "empty literal", "greater than the number of prefix",
    "must be", "cannot", "is not allowed", "recursive array",
)


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes.
    return usage / (1024 * 1024) if sys.platform == "darwin" else usage / 1024


def apply_rlimits(mem_mb: int | None) -> dict[str, str]:
    """Best-effort address-space / data-segment caps.  macOS largely ignores them."""
    applied: dict[str, str] = {}
    if not mem_mb:
        return applied
    for name, factor in (("RLIMIT_AS", 2), ("RLIMIT_DATA", 1)):
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            cap = int(mem_mb * factor) * 1024 * 1024
            soft, hard = resource.getrlimit(limit)
            if hard != resource.RLIM_INFINITY:
                cap = min(cap, hard)
            resource.setrlimit(limit, (cap, hard))
            applied[name] = "ok"
        except (ValueError, OSError) as exc:  # pragma: no cover - platform dependent
            applied[name] = f"failed: {exc}"
    return applied


def _dumps(obj: typing.Any) -> str:
    """json.dumps with a raised recursion limit (deep schemas are a corpus feature)."""
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(max(old, 50_000))
        return json.dumps(obj, ensure_ascii=False)
    finally:
        sys.setrecursionlimit(old)


# --------------------------------------------------------------------------
# Reason classification
# --------------------------------------------------------------------------


def _limit_fields(message: str) -> dict[str, typing.Any] | None:
    m = LIMIT_RE.search(message)
    if not m:
        return None
    return {"limit_phase": m["phase"], "resource": m["resource"], "observed": int(m["observed"]),
            "limit": int(m["limit"]), "path": m["path"] or ""}


def classify_message(message: str, phase: str, exc_name: str = "") -> dict[str, typing.Any]:
    """Turn an error string into a structured ``reason`` dict.

    ``kind`` is one of: ``schema_limit`` (Formatron ``SchemaLimits``), ``grammar_limit``
    (kbnf ``GrammarLimits``), ``decode_limit`` (kbnf ``DecodeLimits``), ``regex_limit``,
    ``unsupported_schema``, ``invalid_schema``, ``kbnf_parse_error``,
    ``kbnf_semantics_error``, ``recursion_error``, ``memory_error``, ``engine_error``,
    ``python_exception``.
    """
    reason: dict[str, typing.Any] = {"kind": "python_exception", "phase": phase,
                                     "exception": exc_name, "message": message[:600]}
    fields = _limit_fields(message)
    if fields:
        reason.update(fields)
        if fields["limit_phase"] == "schema":
            reason["kind"] = "schema_limit"
        elif fields["limit_phase"] == "decode":
            reason["kind"] = "decode_limit"
        else:
            reason["kind"] = "grammar_limit"
        return reason
    low = message.lower()
    if exc_name == "MemoryError" or "memoryerror" in low:
        reason["kind"] = "memory_error"
    elif exc_name == "RecursionError" or "recursion" in low:
        reason["kind"] = "recursion_error"
    elif "dfa exceeded size limit" in low or "exceeded the configured" in low or (
            "regex" in low and ("limit" in low or "too big" in low or "size" in low)):
        reason["kind"] = "regex_limit"
    elif "kbnf parsing error" in low:
        reason["kind"] = "kbnf_parse_error"
    elif "kbnf semantics error" in low:
        reason["kind"] = "kbnf_semantics_error"
    elif exc_name == "AcceptTokenError":
        reason["kind"] = "decode_limit"
    elif exc_name in ("ValidationError", "SchemaError"):
        reason["kind"] = "invalid_schema"
    elif any(s in low for s in _UNSUPPORTED_MARKERS):
        reason["kind"] = "unsupported_schema"
    elif exc_name in ("ValueError", "RuntimeError", "AssertionError") and phase in ("create_schema", "grammar_gen", "admission"):
        reason["kind"] = "unsupported_schema"
    elif phase in ("compile", "schema_to_grammar") and exc_name in ("RuntimeError", "ValueError"):
        reason["kind"] = "engine_error"
    return reason


def classify_exception(exc: BaseException, phase: str) -> dict[str, typing.Any]:
    reason = classify_message(str(exc), phase, type(exc).__name__)
    violation = getattr(exc, "violation", None)
    if violation is not None:  # formatron.security.ResourceLimitExceeded
        reason.update(limit_phase=violation.phase, resource=violation.resource, observed=violation.observed,
                      limit=violation.limit, path=getattr(violation, "path", "") or "")
        reason["kind"] = "schema_limit" if violation.phase == "schema" else (
            "decode_limit" if violation.phase == "decode" else "grammar_limit")
    return reason


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p99": None, "max": None, "mean": None}
    vs = sorted(values)

    def pct(q: float) -> float:
        if len(vs) == 1:
            return vs[0]
        pos = q * (len(vs) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(vs) - 1)
        return vs[lo] + (vs[hi] - vs[lo]) * (pos - lo)

    return {"p50": pct(0.5), "p99": pct(0.99), "max": vs[-1], "mean": sum(vs) / len(vs)}


# --------------------------------------------------------------------------
# Random walk
# --------------------------------------------------------------------------


class _Sampler:
    """Biased random token sampler.

    Early in the walk longer tokens are preferred (make structural progress);
    as the step budget is consumed, tokens containing closing punctuation are
    boosted and tokens containing opening punctuation are suppressed, so that
    the walk terminates instead of nesting forever.  Non-ASCII single bytes and
    long digit runs are damped so strings/numbers do not grow without bound.
    """

    def __init__(self, tokens: typing.Sequence[bytes], seed: int, cap: int):
        import numpy as np

        self.np = np
        self.rng = np.random.default_rng(seed)
        self.cap = cap
        n = len(tokens)
        self.length = np.array([min(len(t), 8) for t in tokens], dtype=np.float64)
        self.closer = np.array([any(c in t for c in b'}]"') for t in tokens], dtype=np.float64)
        self.opener = np.array([any(c in t for c in b'{[') for t in tokens], dtype=np.float64)
        self.digit = np.array([t.isdigit() for t in tokens], dtype=np.float64)
        self.high_byte = np.array([len(t) == 1 and t[0] >= 0x80 for t in tokens], dtype=np.float64)
        self.control = np.array([len(t) == 1 and t[0] < 0x20 for t in tokens], dtype=np.float64)
        self.single = np.array([len(t) == 1 for t in tokens], dtype=np.float64)
        self.whitespace = np.array([t.strip(b" \t\r\n") == b"" for t in tokens], dtype=np.float64)
        self.n = n

    def choose(self, allowed: typing.Sequence[int], step: int, digit_run: int) -> int:
        if len(allowed) == 1:
            return allowed[0]
        np = self.np
        idx = np.fromiter(allowed, dtype=np.int64, count=len(allowed))
        progress = step / self.cap
        w = np.ones(len(idx), dtype=np.float64)
        if progress < 0.25:
            w *= 1.0 + self.length[idx] * (1.0 - self.whitespace[idx])
        w *= np.where(self.whitespace[idx] > 0, 0.04, 1.0)
        w *= 1.0 + 15.0 * progress * self.closer[idx]
        w *= np.where(self.opener[idx] > 0, max(0.02, 1.0 - 2.5 * progress), 1.0)
        w *= np.where(self.high_byte[idx] > 0, 0.15, 1.0)
        w *= np.where(self.control[idx] > 0, 0.3, 1.0)
        if digit_run >= 2:
            w *= np.where(self.digit[idx] > 0, 0.15, 1.0)
        if progress > 0.25:
            w *= np.where(self.single[idx] > 0, 0.6, 1.0)
        w /= w.sum()
        return int(idx[self.rng.choice(len(idx), p=w)])


def random_walk(formatter, tokens: typing.Sequence[bytes], seed: int, cap: int,
                progress: typing.Callable[[str], None]) -> dict[str, typing.Any]:
    """Drive ``formatter`` with biased random tokens until it finishes or ``cap`` is hit.

    Records per-step mask (``compute_allowed_tokens``) and accept latencies, Earley chart
    and allowed-token-cache peaks, and the raw generated bytes.
    """
    sampler = _Sampler(tokens, seed, cap)
    engine = getattr(formatter, "_engine", None)
    out = bytearray()
    mask_ms: list[float] = []
    accept_ms: list[float] = []
    allowed_counts: list[int] = []
    chart_newest_peak = 0
    chart_total_peak = 0
    cache_peak = 0
    completed = False
    error = None
    steps = 0
    digit_run = 0
    t_start = _now_ms()
    for step in range(cap):
        t = _now_ms()
        try:
            formatter.compute_allowed_tokens()
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            mask_ms.append(_now_ms() - t)
            error = classify_exception(exc, "generate")
            error["where"] = "compute_allowed_tokens"
            break
        mask_ms.append(_now_ms() - t)
        allowed = formatter.get_allowed_tokens_since_last_computation()
        allowed_counts.append(len(allowed))
        if not allowed:
            error = {"kind": "no_allowed_tokens", "phase": "generate",
                     "message": "engine returned an empty allowed set before completion (dead end)"}
            break
        tok = sampler.choose(allowed, step, digit_run)
        t = _now_ms()
        try:
            formatter.accept_token(tok)
        except BaseException as exc:  # AcceptTokenError from decode limits, capture errors, ...
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            accept_ms.append(_now_ms() - t)
            error = classify_exception(exc, "generate")
            error["where"] = "accept_token"
            if formatter.is_completed():
                # The engine accepted the final token; the Python-side capture / extractor
                # raised.  Keep the output so validation can still run.
                out += tokens[tok]
                steps = step + 1
                completed = True
                error["kind"] = "capture_error"
            break
        accept_ms.append(_now_ms() - t)
        out += tokens[tok]
        digit_run = digit_run + 1 if tokens[tok].isdigit() else 0
        steps = step + 1
        if engine is not None:
            try:
                newest, total = engine.earley_chart_size()
                chart_newest_peak = max(chart_newest_peak, newest)
                chart_total_peak = max(chart_total_peak, total)
                cache_peak = max(cache_peak, engine.cache_size())
            except Exception:  # pragma: no cover - older engine without the accessors
                engine = None
        if formatter.is_completed():
            completed = True
            break
        if steps % 64 == 0:
            progress(f"generate:{steps}")
    total_ms = _now_ms() - t_start
    return {
        "tokens": steps,
        "completed": completed,
        "hit_token_cap": (not completed and error is None),
        "error": error,
        "total_ms": total_ms,
        # everything that is not the engine: allowed-list materialisation, sampling, chart probes
        "walk_overhead_ms": total_ms - sum(mask_ms) - sum(accept_ms),
        "mask_ms": _percentiles(mask_ms),
        "accept_ms": _percentiles(accept_ms),
        "allowed_mean": (sum(allowed_counts) / len(allowed_counts)) if allowed_counts else None,
        "chart_peak_newest": chart_newest_peak,
        "chart_peak_total": chart_total_peak,
        "cache_peak": cache_peak,
        "output_bytes": len(out),
        "output": bytes(out),
    }


def validate_output(raw: bytes, schema: dict) -> tuple[bool, str | None, str]:
    """Return (valid, error, preview).  ``error`` is prefixed with its class."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"utf8: {exc}", raw[:200].decode("utf-8", "replace")
    preview = text[:200]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, f"json: {exc}", preview
    except RecursionError as exc:
        return False, f"json_recursion: {exc}", preview
    try:
        import jsonschema

        old = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old, 50_000))
        try:
            validator = jsonschema.Draft202012Validator(schema)
            validator.validate(obj)
        finally:
            sys.setrecursionlimit(old)
    except Exception as exc:  # ValidationError, SchemaError, re.error, RecursionError...
        msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return False, f"{type(exc).__name__}: {msg[:300]}", preview
    return True, None, preview


# --------------------------------------------------------------------------
# kbnf / Formatron
# --------------------------------------------------------------------------


def _admission_to_reason(adm) -> dict[str, typing.Any]:
    """Map a ``formatron.security.AdmissionResult`` that did not admit into a reason dict."""
    if adm.violation is not None:
        v = adm.violation
        kind = "schema_limit" if v.phase == "schema" else ("decode_limit" if v.phase == "decode" else "grammar_limit")
        return {"kind": kind, "phase": "admission", "limit_phase": v.phase, "resource": v.resource,
                "observed": v.observed, "limit": v.limit, "path": getattr(v, "path", "") or "",
                "exception": "ResourceLimitExceeded", "message": (adm.reason or "")[:600]}
    message = adm.reason or adm.outcome
    exc_name = message.split(":", 1)[0] if ":" in message and " " not in message.split(":", 1)[0] else ""
    reason = classify_message(message, "admission", exc_name)
    if adm.outcome == "invalid" and reason["kind"] == "python_exception":
        reason["kind"] = "unsupported_schema"
    if adm.outcome in ("timeout", "crashed"):
        reason["kind"] = adm.outcome
    return reason


@functools.lru_cache(maxsize=2)
def _real_token_table(path: str) -> tuple[bytes, ...]:
    return vocab.token_table(vocab.load_vocab_file(path)["id_to_bytes"])


def load_kbnf_vocabulary(options: dict) -> tuple[typing.Sequence[bytes], typing.Any, dict[str, typing.Any]]:
    """Return ``(tokens, kbnf.Vocabulary, info)`` for the run's vocabulary.

    ``tokens[id]`` are the raw bytes the walk appends when token ``id`` is
    sampled.  With ``options["vocab_file"]`` set these are the real tokenizer's
    bytes (after Formatron's byte-level unmangling); otherwise the synthetic
    vocabulary.  A fresh ``kbnf.Vocabulary`` is built per call (it is not
    shareable across processes and must not be shared between engines).
    """
    path = options.get("vocab_file")
    if not path:
        tokens = vocab.build_vocabulary(tuple(corpus.KEY_POOL))
        return tokens, vocab.kbnf_vocabulary(tokens), {"name": "synthetic", "tokenizer": None, "size": len(tokens)}
    data = vocab.load_vocab_file(path)
    tokens = _real_token_table(path)
    vocabulary = vocab.kbnf_vocabulary_from_maps(data["id_to_bytes"], data["id_to_str"])
    info = {"name": options.get("vocab_name") or data["name"], "tokenizer": data["tokenizer"], "size": data["size"],
            "max_id": data.get("max_id"), "id_holes": data.get("id_holes", 0),
            "missing_single_bytes": data.get("missing_single_bytes", 0)}
    return tokens, vocabulary, info


def run_kbnf(spec: corpus.Spec, schema: dict, options: dict, progress) -> dict:
    result: dict[str, typing.Any] = {"engine": "kbnf", "config": options["config"], "phase_reached": "start"}
    t_all = _now_ms()
    hardened = options["config"] == "hardened"

    phase = "import"
    progress(phase)
    import kbnf  # noqa: F401  (may transiently fail while the fork is rebuilt)
    from formatron.formatter import FormatterBuilder
    from formatron.schemas.json_schema import create_schema
    from formatron.security import admit_json_schema, inspect_grammar

    phase = "vocab"
    progress(phase)
    t = _now_ms()
    tokens, vocabulary, result["vocab"] = load_kbnf_vocabulary(options)
    result["vocab_load_ms"] = _now_ms() - t
    result["vocab_size"] = len(tokens)

    # --- admission (hardened only): SchemaLimits + full hardened grammar check -------
    if hardened:
        phase = "admission"
        progress(phase)
        t = _now_ms()
        try:
            adm = admit_json_schema(schema)
        except BaseException as exc:  # admit_json_schema is documented never to raise; be safe
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            result.update(outcome="crash", reason={**classify_exception(exc, phase),
                                                   "traceback": traceback.format_exc()[-1500:]},
                          admission_ms=_now_ms() - t)
            return _finish(result, t_all, phase)
        result["admission_ms"] = _now_ms() - t
        result["admission"] = {
            "outcome": adm.outcome, "reason": (adm.reason or None) and adm.reason[:600],
            "violation": adm.violation.to_dict() if adm.violation is not None else None,
            "schema_complexity": adm.schema_complexity, "grammar_complexity": adm.grammar_complexity,
            "grammar_bytes": adm.grammar_bytes, "elapsed_ms": adm.elapsed_ms,
        }
        if not adm.admitted:
            result.update(outcome="rejected", reason=_admission_to_reason(adm))
            if adm.grammar_bytes:
                result["grammar_bytes"] = adm.grammar_bytes
            return _finish(result, t_all, phase)

    # --- schema -> Formatron schema object -----------------------------------
    phase = "create_schema"
    progress(phase)
    t = _now_ms()
    try:
        schema_obj = create_schema(schema)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase),
                      create_schema_ms=_now_ms() - t, schema_to_grammar_ms=_now_ms() - t)
        if hardened:
            result["reason"]["admitted_then_failed"] = True
        return _finish(result, t_all, phase)
    result["create_schema_ms"] = _now_ms() - t

    # --- Formatron schema object -> KBNF grammar text ----------------------------
    phase = "grammar_gen"
    progress(phase)
    t = _now_ms()
    try:
        builder = FormatterBuilder()
        builder.append_line(f"{builder.json(schema_obj, capture_name='json')}")
        grammar_src = builder.grammar_string()
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase),
                      grammar_gen_ms=_now_ms() - t,
                      schema_to_grammar_ms=result["create_schema_ms"] + (_now_ms() - t))
        if hardened:
            result["reason"]["admitted_then_failed"] = True
        return _finish(result, t_all, phase)
    result["grammar_gen_ms"] = _now_ms() - t
    result["schema_to_grammar_ms"] = result["create_schema_ms"] + result["grammar_gen_ms"]
    result["grammar_bytes"] = len(grammar_src.encode("utf-8"))

    # --- compile (kbnf.Engine construction) ---------------------------------------
    phase = "compile"
    progress(phase)
    t = _now_ms()
    try:
        decode = lambda ids: vocab.decode_bytes(tokens, ids).decode("utf-8", "replace")  # noqa: E731
        formatter = builder.build(vocabulary, decode, hardened=hardened)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase), compile_ms=_now_ms() - t)
        if hardened:
            result["reason"]["admitted_then_failed"] = True
        _inspect(result, grammar_src, inspect_grammar, progress)
        return _finish(result, t_all, phase)
    result["compile_ms"] = _now_ms() - t
    result["outcome"] = "admitted"
    _inspect(result, grammar_src, inspect_grammar, progress)

    # --- random-walk generation ----------------------------------------------------
    phase = "generate"
    progress(phase)
    gen = random_walk(formatter, tokens, seed=(options["seed"] ^ zlib.crc32(spec.id.encode())) & 0xFFFFFFFF,
                      cap=options["token_cap"], progress=progress)
    raw = gen.pop("output")
    if gen["completed"]:
        ok, err, preview = validate_output(raw, schema)
        gen["output_valid"] = ok
        gen["validation_error"] = err
        gen["output_preview"] = preview
    else:
        gen["output_valid"] = None
        gen["validation_error"] = None
        gen["output_preview"] = raw[:200].decode("utf-8", "replace")
    result["generation"] = gen
    return _finish(result, t_all, "done")


def _inspect(result: dict, grammar_src: str, inspect_grammar, progress) -> None:
    progress("inspect")
    t = _now_ms()
    try:
        c = inspect_grammar(grammar_src)
        result["inspect"] = c.to_dict() if hasattr(c, "to_dict") else {
            n: getattr(c, n) for n in dir(c) if not n.startswith("_") and isinstance(getattr(c, n), int)}
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result["inspect"] = None
        result["inspect_error"] = classify_exception(exc, "inspect")
    result["inspect_ms"] = _now_ms() - t


def _finish(result: dict, t_all: float, phase: str) -> dict:
    result["phase_reached"] = phase
    result["wall_ms"] = _now_ms() - t_all
    result["peak_rss_mb"] = _rss_mb()
    return result


# --------------------------------------------------------------------------
# External engines (compile-only differential check)
# --------------------------------------------------------------------------


def run_xgrammar(spec: corpus.Spec, schema: dict, options: dict, progress) -> dict:
    result: dict[str, typing.Any] = {"engine": "xgrammar", "config": "default", "phase_reached": "start"}
    t_all = _now_ms()
    progress("import")
    import xgrammar

    tokens = list(vocab.build_vocabulary(tuple(corpus.KEY_POOL))) + [vocab.EOS_TEXT]
    eos = len(tokens) - 1
    tokenizer_info = xgrammar.TokenizerInfo(tokens, vocab_type=xgrammar.VocabType.RAW, stop_token_ids=[eos])
    compiler = xgrammar.GrammarCompiler(tokenizer_info, max_threads=1, cache_enabled=False)
    result["vocab_size"] = len(tokens)
    result["vocab"] = {"name": "synthetic", "tokenizer": None, "size": len(tokens)}

    phase = "schema_to_grammar"
    progress(phase)
    t = _now_ms()
    try:
        text = _dumps(schema)
        grammar = xgrammar.Grammar.from_json_schema(text, any_whitespace=True, strict_mode=True)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase), schema_to_grammar_ms=_now_ms() - t)
        return _finish(result, t_all, phase)
    result["schema_to_grammar_ms"] = _now_ms() - t
    try:
        result["grammar_bytes"] = len(str(grammar).encode("utf-8"))
    except BaseException:  # pragma: no cover
        result["grammar_bytes"] = None

    phase = "compile"
    progress(phase)
    t = _now_ms()
    try:
        compiler.compile_grammar(grammar)
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase), compile_ms=_now_ms() - t)
        return _finish(result, t_all, phase)
    result["compile_ms"] = _now_ms() - t
    result["outcome"] = "admitted"
    return _finish(result, t_all, "done")


def run_llguidance(spec: corpus.Spec, schema: dict, options: dict, progress) -> dict:
    result: dict[str, typing.Any] = {"engine": "llguidance", "config": "default", "phase_reached": "start"}
    t_all = _now_ms()
    progress("import")
    import llguidance

    tokens = vocab.build_vocabulary(tuple(corpus.KEY_POOL))
    tokenizer = llguidance.LLTokenizer(llguidance.TokenizerWrapper(vocab.GreedyTokenizer(tokens)))
    result["vocab_size"] = tokenizer.vocab_size
    result["vocab"] = {"name": "synthetic", "tokenizer": None, "size": tokenizer.vocab_size}

    phase = "schema_to_grammar"
    progress(phase)
    t = _now_ms()
    try:
        grammar = llguidance.LLMatcher.grammar_from_json_schema(_dumps(schema))
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase), schema_to_grammar_ms=_now_ms() - t)
        return _finish(result, t_all, phase)
    result["schema_to_grammar_ms"] = _now_ms() - t
    result["grammar_bytes"] = len(grammar.encode("utf-8"))

    phase = "compile"
    progress(phase)
    t = _now_ms()
    try:
        matcher = llguidance.LLMatcher(tokenizer, grammar, log_level=0)
        err = matcher.get_error() if matcher.is_error() else ""
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result.update(outcome="rejected", reason=classify_exception(exc, phase), compile_ms=_now_ms() - t)
        return _finish(result, t_all, phase)
    result["compile_ms"] = _now_ms() - t
    if err:
        reason = classify_message(err, phase, "LLMatcher.error")
        if reason["kind"] == "python_exception":
            reason["kind"] = "engine_error"
        result.update(outcome="rejected", reason=reason)
    else:
        result["outcome"] = "admitted"
    return _finish(result, t_all, "done")


ENGINES = {"kbnf": run_kbnf, "xgrammar": run_xgrammar, "llguidance": run_llguidance}


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run_in_process(spec: corpus.Spec, options: dict, progress=lambda phase: None) -> dict:
    """Run one spec in the *current* process (used by the child and by tests)."""
    base = {"id": spec.id, "family": spec.family, "category": spec.category, "expect": spec.expect,
            "engine": options["engine"], "config": options.get("config", "default"),
            "options": {k: options.get(k) for k in ("timeout", "mem_mb", "token_cap", "workers", "seed")}}
    t = _now_ms()
    schema = corpus.materialize(spec, options.get("seed", corpus.SEED))
    base["materialize_ms"] = _now_ms() - t
    try:
        base["schema_bytes"] = len(_dumps(schema).encode("utf-8"))
    except BaseException:
        base["schema_bytes"] = None
    try:
        result = ENGINES[options["engine"]](spec, schema, options, progress)
    except MemoryError as exc:
        result = {"outcome": "oom", "reason": classify_exception(exc, "unknown"), "phase_reached": "unknown"}
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        result = {"outcome": "crash", "phase_reached": "unknown",
                  "reason": {**classify_exception(exc, "unknown"), "traceback": traceback.format_exc()[-1500:]}}
    base.update(result)
    return base


def child_main(conn, spec_dict: dict, options: dict) -> None:
    """``multiprocessing`` target."""
    rlimits = apply_rlimits(options.get("mem_mb"))
    started = time.perf_counter()

    def progress(phase: str) -> None:
        try:
            conn.send({"type": "progress", "phase": phase, "elapsed_ms": (time.perf_counter() - started) * 1000.0})
        except (BrokenPipeError, OSError):
            pass

    spec = corpus.Spec.from_dict(spec_dict)
    result = run_in_process(spec, options, progress)
    result["rlimits"] = rlimits
    try:
        conn.send({"type": "result", "result": result})
    finally:
        conn.close()
