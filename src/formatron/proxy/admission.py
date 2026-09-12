"""The admission service: checks constraints against the policy, caches decisions, keeps stats."""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import logging
import statistics
import threading
import time
import typing

import anyio
import anyio.to_thread

from formatron.security import AdmissionResult, LimitViolation, admit_json_schema

from .constraints import (
    KIND_CHOICE,
    KIND_GRAMMAR,
    KIND_JSON_SCHEMA,
    KIND_REGEX,
    Constraint,
    ConstraintError,
    ConstraintRejected,
    bracket_nesting_depth,
    choices_to_kbnf,
    parse_json_document,
    regex_to_kbnf,
)
from .policy import EffectivePolicy

logger = logging.getLogger("formatron.proxy")

CODE_RESOURCE_LIMIT = "resource_limit_exceeded"
CODE_INVALID = "invalid_constraint"
CODE_TIMEOUT = "constraint_check_timeout"
CODE_FAILED = "constraint_check_failed"

CODE_BY_OUTCOME = {
    "rejected": CODE_RESOURCE_LIMIT,
    "invalid": CODE_INVALID,
    "timeout": CODE_TIMEOUT,
    "crashed": CODE_FAILED,
}

OUTCOMES = ("admitted", "rejected", "invalid", "timeout", "crashed")


@dataclasses.dataclass
class Decision:
    """The proxy's verdict on one constraint."""

    constraint: Constraint
    result: AdmissionResult
    elapsed_ms: float
    """Wall time the proxy spent on this constraint (cache lookup, queueing, checking)."""
    cached: bool = False
    unverified: str | None = None
    """Set when the constraint was admitted without a full grammar check (``passthrough``
    grammars, or ``on_invalid=forward``)."""

    @property
    def admitted(self) -> bool:
        return self.result.admitted

    @property
    def outcome(self) -> str:
        return self.result.outcome

    @property
    def code(self) -> str | None:
        if self.result.admitted:
            return None
        return CODE_BY_OUTCOME.get(self.result.outcome, CODE_FAILED)

    @property
    def resource(self) -> str | None:
        return self.result.violation.resource if self.result.violation else None

    def error_body(self) -> dict[str, typing.Any]:
        """The OpenAI-style error document for a rejection."""
        code = self.code or CODE_FAILED
        violation = self.result.violation.to_dict() if self.result.violation else None
        message = f"{self.constraint.kind} constraint at {self.constraint.param} was not admitted"
        if self.result.reason:
            message += f": {self.result.reason}"
        return {
            "error": {
                "message": message,
                "type": "grammar_guard_rejected",
                "code": code,
                "param": self.constraint.param,
                "violation": violation,
                "elapsed_ms": round(self.elapsed_ms, 3),
            }
        }


class DecisionCache:
    """A small thread-safe LRU of admission results keyed by constraint + policy."""

    def __init__(self, capacity: int):
        self.capacity = max(int(capacity), 0)
        self._entries: collections.OrderedDict[str, tuple[AdmissionResult, str | None]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> tuple[AdmissionResult, str | None] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
            return entry

    def put(self, key: str, value: tuple[AdmissionResult, str | None]) -> None:
        if self.capacity == 0:
            return
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class Stats:
    """Counters and latency samples reported by ``GET /grammar-guard/stats``."""

    def __init__(self, latency_window: int = 4096):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.requests_total = 0
        self.requests_forwarded = 0
        self.requests_rejected = 0
        self.requests_unconstrained = 0
        self.requests_too_large = 0
        self.upstream_errors = 0
        self.constraints_checked = 0
        self.outcomes: collections.Counter[str] = collections.Counter({name: 0 for name in OUTCOMES})
        self.kinds: collections.Counter[str] = collections.Counter()
        self.codes: collections.Counter[str] = collections.Counter()
        self.resources: collections.Counter[str] = collections.Counter()
        self.cache_hits = 0
        self.cache_misses = 0
        self._latencies: collections.deque[float] = collections.deque(maxlen=max(int(latency_window), 1))

    def record_decision(self, decision: Decision) -> None:
        with self._lock:
            self.constraints_checked += 1
            self.outcomes[decision.outcome] += 1
            self.kinds[decision.constraint.kind] += 1
            if decision.cached:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
            if decision.code:
                self.codes[decision.code] += 1
            if decision.resource:
                self.resources[decision.resource] += 1
            self._latencies.append(decision.elapsed_ms)

    def record_request(self, status: str) -> None:
        with self._lock:
            self.requests_total += 1
            if status == "forwarded":
                self.requests_forwarded += 1
            elif status == "rejected":
                self.requests_rejected += 1
            elif status == "unconstrained":
                self.requests_unconstrained += 1
            elif status == "too_large":
                self.requests_too_large += 1

    def record_upstream_error(self) -> None:
        with self._lock:
            self.upstream_errors += 1

    @staticmethod
    def _percentile(samples: list[float], fraction: float) -> float | None:
        if not samples:
            return None
        index = max(0, min(len(samples) - 1, round(fraction * (len(samples) - 1))))
        return samples[index]

    def snapshot(self, cache: DecisionCache) -> dict[str, typing.Any]:
        with self._lock:
            samples = sorted(self._latencies)
            return {
                "uptime_s": round(time.time() - self.started_at, 3),
                "requests": {
                    "total": self.requests_total,
                    "forwarded": self.requests_forwarded,
                    "rejected": self.requests_rejected,
                    "unconstrained": self.requests_unconstrained,
                    "too_large": self.requests_too_large,
                    "upstream_errors": self.upstream_errors,
                },
                "constraints": {
                    "checked": self.constraints_checked,
                    "by_outcome": dict(self.outcomes),
                    "by_kind": dict(self.kinds),
                    "by_code": dict(self.codes),
                    "by_violation_resource": dict(self.resources),
                },
                "admission_latency_ms": {
                    "samples": len(samples),
                    "p50": self._percentile(samples, 0.50),
                    "p99": self._percentile(samples, 0.99),
                    "max": samples[-1] if samples else None,
                    "mean": statistics.fmean(samples) if samples else None,
                },
                "cache": {
                    "hits": self.cache_hits,
                    "misses": self.cache_misses,
                    "size": len(cache),
                    "capacity": cache.capacity,
                },
            }


class AdmissionService:
    """Checks constraints without blocking the event loop.

    ``checker`` is an :class:`formatron.isolation.IsolatedGrammarChecker` (anything with the
    same ``check(grammar, *, engine_overrides=...)`` signature works for tests). Its blocking
    call runs in a worker thread bounded by a capacity limiter, under a per-request budget
    that maps to ``constraint_check_timeout``.
    """

    def __init__(
        self,
        policy: EffectivePolicy,
        checker: typing.Any,
        *,
        cache_size: int = 1024,
        latency_window: int = 4096,
    ):
        self.policy = policy
        self.checker = checker
        self.cache = DecisionCache(cache_size)
        self.stats = Stats(latency_window)
        self._limiter: anyio.CapacityLimiter | None = None

    # -- async entry point --------------------------------------------------------------

    async def admit(self, constraints: typing.Sequence[Constraint]) -> list[Decision]:
        """Check ``constraints`` in order; stop at the first one that is not admitted."""
        decisions: list[Decision] = []
        for constraint in constraints:
            decision = await self.admit_one(constraint)
            decisions.append(decision)
            if not decision.admitted:
                break
        return decisions

    async def admit_one(self, constraint: Constraint) -> Decision:
        started = time.perf_counter()
        key = self.cache_key(constraint)
        if key is not None:
            hit = self.cache.get(key)
            if hit is not None:
                result, unverified = hit
                violation = result.violation
                if violation is not None and violation.phase == "proxy" and violation.path != constraint.param:
                    # Proxy-level violations name the request field they were found at; the
                    # cached entry may come from a request that carried it elsewhere.
                    result = dataclasses.replace(result, violation=dataclasses.replace(violation, path=constraint.param))
                decision = Decision(constraint, result, (time.perf_counter() - started) * 1000.0, True, unverified)
                self.stats.record_decision(decision)
                return decision

        if self._limiter is None:
            self._limiter = anyio.CapacityLimiter(self.policy.admission_workers)
        budget = self.policy.admission_timeout_s
        unverified: str | None = None
        try:
            with anyio.fail_after(budget):
                result, unverified = await anyio.to_thread.run_sync(
                    self.check_sync, constraint, abandon_on_cancel=True, limiter=self._limiter
                )
        except TimeoutError:
            budget_ms = int(budget * 1000)
            result = AdmissionResult(
                False,
                "timeout",
                f"admission exceeded the {budget:.3f}s per-request budget",
                LimitViolation("proxy", "admission_timeout_ms", budget_ms, budget_ms, constraint.param),
            )
        except Exception as error:  # noqa: BLE001 - a proxy bug must never admit a request
            logger.exception("admission check raised for %s at %s", constraint.kind, constraint.param)
            result = AdmissionResult(False, "crashed", f"admission check failed: {type(error).__name__}: {error}")

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        result.elapsed_ms = result.elapsed_ms or elapsed_ms
        decision = Decision(constraint, result, elapsed_ms, False, unverified)
        if key is not None and self._cacheable(result):
            self.cache.put(key, (result, unverified))
        self.stats.record_decision(decision)
        return decision

    # -- cache --------------------------------------------------------------------------

    @staticmethod
    def _cacheable(result: AdmissionResult) -> bool:
        """Deterministic verdicts are cached; crashes and load-dependent budget timeouts are not.

        A worker wall-clock timeout *is* cached: the same constraint would stall the worker
        again, and a cached rejection is far cheaper than another kill-and-respawn.
        """
        if result.outcome == "crashed":
            return False
        if result.outcome == "timeout":
            return result.violation is not None and result.violation.resource != "admission_timeout_ms"
        return True

    def cache_key(self, constraint: Constraint) -> str | None:
        if self.cache.capacity == 0:
            return None
        try:
            canonical = json.dumps(constraint.value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError, RecursionError):
            return None
        digest = hashlib.sha256()
        for part in (constraint.kind, canonical, self.policy.fingerprint):
            digest.update(part.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    # -- blocking checks (run in a worker thread) ------------------------------------------

    def check_sync(self, constraint: Constraint) -> tuple[AdmissionResult, str | None]:
        if constraint.kind == KIND_JSON_SCHEMA:
            return self._check_json_schema(constraint)
        if constraint.kind == KIND_REGEX:
            return self._check_regex(constraint), None
        if constraint.kind == KIND_CHOICE:
            return self._check_choice(constraint), None
        if constraint.kind == KIND_GRAMMAR:
            return self._check_grammar(constraint)
        return AdmissionResult(False, "invalid", f"unknown constraint kind {constraint.kind!r}"), None

    def _violation(self, resource: str, observed: int, param: str) -> AdmissionResult | None:
        limit = self.policy.limit(resource)
        if limit is None or observed <= limit:
            return None
        violation = LimitViolation("proxy", resource, observed, limit, param)
        return AdmissionResult(False, "rejected", str(violation), violation)

    def _check_json_schema(self, constraint: Constraint) -> tuple[AdmissionResult, str | None]:
        schema = constraint.value
        if isinstance(schema, str):
            rejected = self._violation("max_constraint_bytes", len(schema.encode("utf-8")), constraint.param)
            if rejected is not None:
                return rejected, None
            try:
                schema = parse_json_document(schema, param=constraint.param)
            except ConstraintRejected as error:
                return AdmissionResult(False, "rejected", str(error.violation), error.violation), None
            except ConstraintError as error:
                return AdmissionResult(False, "invalid", error.message), None
        if not isinstance(schema, dict):
            return AdmissionResult(False, "invalid", "JSON schema must be an object"), None

        prepared = dict(schema)
        prepared.setdefault("$id", self.policy.default_schema_id)
        prepared.setdefault("$schema", self.policy.default_schema_dialect)
        result = admit_json_schema(
            prepared,
            schema_limits=self.policy.schema_limits,
            engine_overrides=self.policy.engine_overrides,
            checker=self.checker,
        )
        if result.outcome == "invalid" and self.policy.on_invalid == "forward":
            reason = f"schema not convertible by Formatron, forwarded unverified: {result.reason}"
            forwarded = AdmissionResult(True, "admitted", reason, None, result.schema_complexity, None, 0, result.elapsed_ms)
            return forwarded, "unsupported-schema"
        return result, None

    def _check_regex(self, constraint: Constraint) -> AdmissionResult:
        regex = constraint.value
        if not isinstance(regex, str):
            return AdmissionResult(False, "invalid", "regex must be a string")
        rejected = self._violation("max_regex_bytes", len(regex.encode("utf-8")), constraint.param)
        if rejected is not None:
            return rejected
        return self.checker.check(regex_to_kbnf(regex), engine_overrides=self.policy.engine_overrides)

    def _check_choice(self, constraint: Constraint) -> AdmissionResult:
        choices = constraint.value
        if not isinstance(choices, list) or not all(isinstance(choice, str) for choice in choices):
            return AdmissionResult(False, "invalid", "choices must be a list of strings")
        if not choices:
            return AdmissionResult(False, "invalid", "choices must not be empty")
        rejected = self._violation("max_choices", len(choices), constraint.param)
        if rejected is not None:
            return rejected
        total_bytes = sum(len(choice.encode("utf-8")) for choice in choices)
        rejected = self._violation("max_choice_bytes", total_bytes, constraint.param)
        if rejected is not None:
            return rejected
        return self.checker.check(choices_to_kbnf(choices), engine_overrides=self.policy.engine_overrides)

    def _check_grammar(self, constraint: Constraint) -> tuple[AdmissionResult, str | None]:
        grammar = constraint.value
        if not isinstance(grammar, str):
            return AdmissionResult(False, "invalid", "grammar must be a string"), None
        grammar_bytes = len(grammar.encode("utf-8"))
        rejected = self._violation("max_grammar_bytes", grammar_bytes, constraint.param)
        if rejected is not None:
            return rejected, None
        if self.policy.grammar_dialect == "kbnf":
            return self.checker.check(grammar, engine_overrides=self.policy.engine_overrides), None
        rejected = self._violation("max_grammar_nesting", bracket_nesting_depth(grammar), constraint.param)
        if rejected is not None:
            return rejected, None
        result = AdmissionResult(
            True,
            "admitted",
            "grammar dialect not verified (passthrough): only byte size and bracket nesting were checked",
            grammar_bytes=grammar_bytes,
        )
        return result, "dialect-passthrough"
