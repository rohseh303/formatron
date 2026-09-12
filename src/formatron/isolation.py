"""Process isolation for compiling untrusted grammars.

The in-process limits in :mod:`formatron.security` are deterministic and cheap, but they
are cooperative: the compile deadline is only checked between construction phases and a
single native call (the KBNF parser, the regex compiler) cannot be interrupted. A service
that accepts arbitrary grammars therefore compiles them in a disposable worker process
with operating-system limits, so that the worst case is a killed worker rather than a
stalled or out-of-memory model server.

:class:`IsolatedGrammarChecker` keeps one warm worker per instance (spawned lazily, so the
~200 ms interpreter start-up is paid once), enforces a hard wall-clock timeout by killing
and respawning the worker, applies best-effort ``RLIMIT_AS``/``RLIMIT_DATA``/``RLIMIT_CPU``
limits inside the worker, and reports every outcome as an
:class:`formatron.security.AdmissionResult`.

Only the grammar text and plain limit overrides cross the process boundary; the engine
itself is built afterwards in the caller's process from a grammar that is now known to be
within budget.

Because the worker uses the ``spawn`` start method, the parent must be importable as a
module (the usual ``if __name__ == "__main__":`` guard in scripts); driving it from a
``python -`` stdin session fails when the child re-imports ``__main__``.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.connection
import os
import threading
import time
import typing

from formatron.security import AdmissionResult, LimitViolation, parse_limit_error


def _apply_rlimits(memory_bytes: int | None, cpu_seconds: int | None) -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return
    if memory_bytes is not None:
        for name in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit = getattr(resource, name, None)
            if limit is None:
                continue
            try:
                soft, hard = resource.getrlimit(limit)
                new_hard = memory_bytes if hard == resource.RLIM_INFINITY else min(hard, memory_bytes)
                resource.setrlimit(limit, (min(memory_bytes, new_hard), new_hard))
            except (ValueError, OSError):
                # macOS rejects or ignores some of these; the wall-clock timeout still applies.
                pass
    if cpu_seconds is not None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        except (ValueError, OSError):
            pass


def _worker_main(
    connection: multiprocessing.connection.Connection,
    memory_bytes: int | None,
    cpu_seconds: int | None,
) -> None:
    _apply_rlimits(memory_bytes, cpu_seconds)
    import kbnf  # noqa: F401  (import inside the worker so start-up cost is isolated)

    from formatron.security import hardened_engine_config

    while True:
        try:
            message = connection.recv()
        except (EOFError, OSError):
            return
        if message is None:
            return
        kind = message[0]
        started = time.perf_counter()
        if kind == "check":
            _, grammar, overrides = message
            try:
                config = hardened_engine_config(**overrides)
                complexity = kbnf.check_grammar(grammar, config).to_dict()
                reply: dict[str, typing.Any] = {"ok": True, "complexity": complexity}
            except ValueError as error:
                reply = {"ok": False, "error": str(error), "kind": "ValueError"}
            except MemoryError:
                reply = {"ok": False, "error": "MemoryError", "kind": "MemoryError"}
            except Exception as error:  # noqa: BLE001 - report anything, never hang
                reply = {"ok": False, "error": f"{type(error).__name__}: {error}", "kind": type(error).__name__}
        elif kind == "sleep":  # test hook: simulate a stuck native call
            time.sleep(message[1])
            reply = {"ok": True, "complexity": None}
        elif kind == "exit":  # test hook: simulate a crash
            os._exit(message[1])
        else:
            reply = {"ok": False, "error": f"unknown message {kind!r}", "kind": "ProtocolError"}
        reply["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        try:
            connection.send(reply)
        except (BrokenPipeError, OSError):
            return


class IsolatedGrammarChecker:
    """Runs hardened grammar checks in a disposable worker process.

    Args:
        timeout_s: Hard wall-clock limit per check. On expiry the worker is killed and the
            result reports ``timeout``.
        memory_bytes: Best-effort address-space limit applied inside the worker
            (effective on Linux; macOS largely ignores it).
        cpu_seconds: Best-effort CPU-time limit; exceeding it kills the worker.
        engine_overrides: Default :func:`hardened_engine_config` overrides for every check.
        start_method: ``multiprocessing`` start method. ``spawn`` is the safe default
            because the parent may hold native threads.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 2.0,
        memory_bytes: int | None = 1 << 30,
        cpu_seconds: int | None = None,
        engine_overrides: dict[str, int | None] | None = None,
        start_method: str = "spawn",
    ):
        self.timeout_s = timeout_s
        self.memory_bytes = memory_bytes
        self.cpu_seconds = cpu_seconds
        self.engine_overrides = dict(engine_overrides or {})
        self._context = multiprocessing.get_context(start_method)
        self._lock = threading.Lock()
        self._process: typing.Any = None
        self._connection: multiprocessing.connection.Connection | None = None
        self.restarts = 0

    # -- lifecycle ---------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        if self._process is not None:
            self.restarts += 1
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(
            target=_worker_main,
            args=(child, self.memory_bytes, self.cpu_seconds),
            daemon=True,
            name="formatron-grammar-checker",
        )
        process.start()
        child.close()
        self._process = process
        self._connection = parent

    def _kill_worker(self) -> None:
        process, connection = self._process, self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        if process is not None and process.is_alive():
            process.kill()
            process.join(timeout=5.0)

    def close(self) -> None:
        """Terminate the worker. The checker can still be reused; it respawns lazily."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.send(None)
                except (BrokenPipeError, OSError):
                    pass
            if self._process is not None:
                self._process.join(timeout=1.0)
            self._kill_worker()

    def __enter__(self) -> "IsolatedGrammarChecker":
        return self

    def __exit__(self, *exc_info: typing.Any) -> None:
        self.close()

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    # -- checks ------------------------------------------------------------------------

    def _roundtrip(self, message: tuple[typing.Any, ...], timeout_s: float | None) -> AdmissionResult:
        timeout_s = self.timeout_s if timeout_s is None else timeout_s
        started = time.perf_counter()
        with self._lock:
            self._ensure_worker()
            assert self._connection is not None
            try:
                self._connection.send(message)
                if not self._connection.poll(timeout_s):
                    self._kill_worker()
                    return AdmissionResult(
                        False,
                        "timeout",
                        f"grammar check exceeded {timeout_s:.3f}s wall clock; worker killed",
                        LimitViolation("isolation", "wall_clock_ms", int(timeout_s * 1000), int(timeout_s * 1000)),
                        elapsed_ms=(time.perf_counter() - started) * 1000.0,
                    )
                reply = self._connection.recv()
            except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
                process = self._process
                exit_code = process.exitcode if process is not None else None
                if process is not None:
                    process.join(timeout=1.0)
                    exit_code = process.exitcode
                self._kill_worker()
                return AdmissionResult(
                    False,
                    "crashed",
                    f"grammar checker worker died (exit code {exit_code})",
                    LimitViolation("isolation", "worker_exit", exit_code if exit_code is not None else -1, 0),
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if reply.get("ok"):
            return AdmissionResult(True, "admitted", None, None, None, reply.get("complexity"), 0, elapsed_ms)
        error = reply.get("error", "")
        violation = parse_limit_error(error)
        if violation is not None:
            return AdmissionResult(False, "rejected", error, violation, elapsed_ms=elapsed_ms)
        if reply.get("kind") == "MemoryError":
            return AdmissionResult(
                False,
                "rejected",
                error,
                LimitViolation("isolation", "memory_bytes", self.memory_bytes or 0, self.memory_bytes or 0),
                elapsed_ms=elapsed_ms,
            )
        return AdmissionResult(False, "invalid", error, elapsed_ms=elapsed_ms)

    def check(
        self,
        grammar: str,
        *,
        engine_overrides: dict[str, int | None] | None = None,
        timeout_s: float | None = None,
    ) -> AdmissionResult:
        """Run a full hardened grammar check in the worker and classify the outcome."""
        overrides = dict(self.engine_overrides)
        overrides.update(engine_overrides or {})
        result = self._roundtrip(("check", grammar, overrides), timeout_s)
        result.grammar_bytes = len(grammar.encode("utf-8"))
        return result

    def _simulate_stall(self, seconds: float, timeout_s: float | None = None) -> AdmissionResult:
        """Test hook: make the worker sleep to exercise the timeout path."""
        return self._roundtrip(("sleep", seconds), timeout_s)

    def _simulate_crash(self, exit_code: int = 3) -> AdmissionResult:
        """Test hook: make the worker exit abruptly to exercise the crash path."""
        return self._roundtrip(("exit", exit_code), None)


def check_grammar_isolated(
    grammar: str,
    *,
    timeout_s: float = 2.0,
    memory_bytes: int | None = 1 << 30,
    **engine_overrides: int | None,
) -> AdmissionResult:
    """One-shot convenience wrapper around :class:`IsolatedGrammarChecker`."""
    with IsolatedGrammarChecker(
        timeout_s=timeout_s, memory_bytes=memory_bytes, engine_overrides=engine_overrides
    ) as checker:
        return checker.check(grammar)
