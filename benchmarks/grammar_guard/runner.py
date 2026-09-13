"""Benchmark runner: isolated child per schema, hard timeout, RSS watchdog.

Every schema is executed in a fresh ``multiprocessing`` "spawn" child.  The
parent enforces a wall-clock timeout (``--timeout``, default 10 s; the child is
SIGKILLed on expiry), a best-effort memory cap (``resource.setrlimit`` inside
the child *and* a parent-side RSS watchdog that kills the child when it exceeds
``--mem-mb``), and runs ``--workers`` children in parallel.

Results are appended to ``results/<config>.jsonl`` (``hardened.jsonl`` /
``default.jsonl`` for kbnf, ``xgrammar.jsonl`` / ``llguidance.jsonl`` for the
external engines) and the run is resumable: ids already present are skipped.

With ``--tokenizer <hf-id>`` the kbnf configs run on that tokenizer's *real*
vocabulary instead of the synthetic one: the parent loads the Hugging Face
tokenizer once, builds the ``kbnf.Vocabulary`` the way Formatron's
``create_engine_vocabulary`` does and pickles the raw maps to
``results/vocab-<name>.pkl``; every child reconstructs the vocabulary from that
file.  Results then go to ``results/<config>-<name>.jsonl``
(``hardened-qwen2.5.jsonl``), leaving the synthetic runs untouched.

Examples::

    python -m benchmarks.grammar_guard.runner --config hardened
    python -m benchmarks.grammar_guard.runner --config default --timeout 10
    python -m benchmarks.grammar_guard.runner --engines xgrammar,llguidance
    python -m benchmarks.grammar_guard.runner --family patterns --limit 5 --config hardened
    python -m benchmarks.grammar_guard.runner --config hardened --tokenizer Qwen/Qwen2.5-0.5B-Instruct --timeout 20 --workers 4
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
import typing

from . import corpus, vocab, worker

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS_DIR = os.path.join(HERE, "results")


# --------------------------------------------------------------------------
# RSS watchdog (parent side)
# --------------------------------------------------------------------------


class RssWatchdog(threading.Thread):
    """Polls ``ps`` for the RSS of every registered child and SIGKILLs any that
    exceed the cap.  Also records the peak RSS observed per pid."""

    def __init__(self, mem_mb: int | None, interval: float = 0.2):
        super().__init__(daemon=True, name="rss-watchdog")
        self.mem_mb = mem_mb
        self.interval = interval
        self._lock = threading.Lock()
        self._pids: dict[int, dict[str, typing.Any]] = {}
        self._stop = threading.Event()

    def register(self, pid: int) -> None:
        with self._lock:
            self._pids[pid] = {"peak_mb": 0.0, "killed": False}

    def unregister(self, pid: int) -> dict[str, typing.Any]:
        with self._lock:
            return self._pids.pop(pid, {"peak_mb": 0.0, "killed": False})

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - timing dependent
        while not self._stop.is_set():
            with self._lock:
                pids = list(self._pids)
            if pids:
                try:
                    out = subprocess.run(
                        ["ps", "-o", "pid=,rss=", "-p", ",".join(map(str, pids))],
                        capture_output=True, text=True, timeout=5,
                    ).stdout
                except (subprocess.SubprocessError, OSError):
                    out = ""
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) != 2:
                        continue
                    try:
                        pid, rss_kb = int(parts[0]), int(parts[1])
                    except ValueError:
                        continue
                    mb = rss_kb / 1024.0
                    with self._lock:
                        info = self._pids.get(pid)
                        if info is None:
                            continue
                        info["peak_mb"] = max(info["peak_mb"], mb)
                        if self.mem_mb and mb > self.mem_mb and not info["killed"]:
                            info["killed"] = True
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except OSError:
                                pass
            self._stop.wait(self.interval)


# --------------------------------------------------------------------------
# One isolated run
# --------------------------------------------------------------------------


def run_isolated(spec: corpus.Spec, options: dict, watchdog: RssWatchdog | None = None) -> dict:
    """Run one spec in a fresh spawn child with a hard timeout.  Never raises."""
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=worker.child_main, args=(child_conn, spec.to_dict(), options), daemon=True)
    t0 = time.perf_counter()
    proc.start()
    child_conn.close()
    if watchdog is not None:
        watchdog.register(proc.pid)
    deadline = t0 + options["timeout"]
    last_phase = "spawn"
    last_phase_ms = 0.0
    result: dict | None = None
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        try:
            if parent_conn.poll(min(remaining, 0.1)):
                msg = parent_conn.recv()
                if msg.get("type") == "progress":
                    last_phase = msg["phase"]
                    last_phase_ms = msg["elapsed_ms"]
                    continue
                if msg.get("type") == "result":
                    result = msg["result"]
                    break
        except (EOFError, OSError):
            break  # child died without sending a result
        if not proc.is_alive() and not parent_conn.poll():
            break
    wall_ms = (time.perf_counter() - t0) * 1000.0
    alive = proc.is_alive()
    if alive:
        proc.kill()
    proc.join(10)
    exitcode = proc.exitcode
    wd = watchdog.unregister(proc.pid) if watchdog is not None else {"peak_mb": 0.0, "killed": False}
    parent_conn.close()

    if result is None:
        result = {"id": spec.id, "family": spec.family, "category": spec.category, "expect": spec.expect,
                  "engine": options["engine"], "config": options.get("config", "default"),
                  "phase_reached": last_phase, "phase_reached_ms": last_phase_ms}
        if wd["killed"]:
            result["outcome"] = "oom"
            result["reason"] = {"kind": "rss_watchdog", "phase": last_phase,
                                "message": f"child RSS exceeded {options.get('mem_mb')} MB (peak {wd['peak_mb']:.0f} MB) during {last_phase}"}
        elif alive:
            result["outcome"] = "timeout"
            result["reason"] = {"kind": "timeout", "phase": last_phase,
                                "message": f"killed after {options['timeout']} s during phase {last_phase}"}
        elif exitcode is not None and exitcode < 0 and -exitcode in (signal.SIGKILL, signal.SIGSEGV, signal.SIGABRT, signal.SIGBUS) and wd["peak_mb"] > 0.8 * (options.get("mem_mb") or float("inf")):
            result["outcome"] = "oom"
            result["reason"] = {"kind": "killed", "phase": last_phase, "message": f"child killed by signal {-exitcode} near the memory cap (peak {wd['peak_mb']:.0f} MB)"}
        else:
            result["outcome"] = "crash"
            result["reason"] = {"kind": "child_died", "phase": last_phase,
                                "message": f"child exited with code {exitcode} during phase {last_phase} without a result"}
    result["wall_ms_parent"] = wall_ms
    result["peak_rss_mb_observed"] = wd["peak_mb"]
    result["exitcode"] = exitcode
    return result


# --------------------------------------------------------------------------
# Batch driver
# --------------------------------------------------------------------------


def results_path(results_dir: str, engine: str, config: str, vocab_name: str | None = None) -> str:
    """``hardened.jsonl`` / ``xgrammar.jsonl`` for the synthetic vocabulary,
    ``hardened-<vocab_name>.jsonl`` for a real tokenizer vocabulary."""
    name = config if engine == "kbnf" else engine
    if vocab_name:
        name = f"{name}-{vocab_name}"
    return os.path.join(results_dir, f"{name}.jsonl")


def load_done_ids(path: str) -> set[str]:
    done: set[str] = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def run_batch(spec_list: list[corpus.Spec], options: dict, out_path: str, workers: int,
              log: typing.Callable[[str], None] = print, resume: bool = True) -> list[dict]:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    done = load_done_ids(out_path) if resume else set()
    todo = [s for s in spec_list if s.id not in done]
    log(f"[{options['engine']}/{options.get('config', 'default')}/{options.get('vocab_name') or 'synthetic'}] "
        f"{len(todo)} to run, {len(spec_list) - len(todo)} already done -> {out_path}")
    if not todo:
        return []
    watchdog = RssWatchdog(options.get("mem_mb"))
    watchdog.start()
    lock = threading.Lock()
    results: list[dict] = []
    counts: dict[str, int] = {}
    t0 = time.perf_counter()
    mode = "a" if resume else "w"
    with open(out_path, mode, encoding="utf-8") as f, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_isolated, s, options, watchdog): s for s in todo}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            spec = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # pragma: no cover - defensive
                res = {"id": spec.id, "family": spec.family, "category": spec.category, "expect": spec.expect,
                       "engine": options["engine"], "config": options.get("config", "default"),
                       "outcome": "crash", "reason": {"kind": "runner_exception", "message": repr(exc)[:600]}}
            with lock:
                f.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
                f.flush()
                results.append(res)
                counts[res["outcome"]] = counts.get(res["outcome"], 0) + 1
                if i % 25 == 0 or i == len(todo):
                    elapsed = time.perf_counter() - t0
                    log(f"  {i}/{len(todo)} done in {elapsed:.0f}s  {counts}")
    watchdog.stop()
    return results


def build_options(args, vocab_file: str | None = None, vocab_name: str | None = None) -> dict:
    return {"timeout": args.timeout, "mem_mb": args.mem_mb, "token_cap": args.token_cap, "seed": args.seed,
            "workers": args.workers, "vocab_file": vocab_file, "vocab_name": vocab_name}


def prepare_vocab(tokenizer: str, results_dir: str, vocab_name: str | None = None, vocab_file: str | None = None,
                  rebuild: bool = False, log: typing.Callable[[str], None] = print) -> tuple[str, str]:
    """Build (or reuse) the pickled vocabulary for ``tokenizer``; returns ``(vocab_file, vocab_name)``."""
    name = vocab_name or vocab.vocab_name_from_tokenizer(tokenizer)
    path = vocab_file or vocab.default_vocab_file(results_dir, name)
    meta = None if rebuild else vocab.read_vocab_meta(path)
    if meta and meta.get("tokenizer") == tokenizer:
        log(f"[vocab] reusing {path}: {meta['tokenizer']} ({meta['size']:,} tokens, built {meta.get('created')})")
    else:
        if meta:
            log(f"[vocab] {path} was built from {meta.get('tokenizer')!r}, rebuilding for {tokenizer!r}")
        vocab.build_vocab_file(tokenizer, path, name, log=log)
    return path, name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="hardened", choices=["hardened", "default"], help="kbnf engine config")
    ap.add_argument("--engines", default="kbnf", help="comma separated: kbnf,xgrammar,llguidance")
    ap.add_argument("--timeout", type=float, default=10.0, help="hard wall-clock timeout per schema (s)")
    ap.add_argument("--mem-mb", type=int, default=4096, help="memory cap per child (RSS watchdog + rlimit)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--token-cap", type=int, default=512, help="random-walk token budget")
    ap.add_argument("--seed", type=int, default=corpus.SEED)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--tokenizer", metavar="HF_ID",
                    help="Hugging Face tokenizer id (e.g. Qwen/Qwen2.5-0.5B-Instruct): run the kbnf configs on its real "
                         "vocabulary instead of the synthetic one; results go to <config>-<vocab-name>.jsonl")
    ap.add_argument("--vocab-name", help="label for --tokenizer used in file names (default: derived, e.g. qwen2.5)")
    ap.add_argument("--vocab-file", help="pickle of the tokenizer vocabulary (default: <results-dir>/vocab-<vocab-name>.pkl)")
    ap.add_argument("--rebuild-vocab", action="store_true", help="rebuild the vocabulary pickle even if it exists")
    ap.add_argument("--family", action="append", help="restrict to family (repeatable)")
    ap.add_argument("--category", choices=["normal", "adversarial"])
    ap.add_argument("--ids", help="comma separated spec ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--per-family", type=int, help="take at most N specs per family")
    ap.add_argument("--no-resume", action="store_true", help="overwrite existing results file")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    spec_list = corpus.filter_specs(corpus.specs(args.seed), families=args.family, category=args.category,
                                    ids=args.ids.split(",") if args.ids else None, limit=args.limit,
                                    per_family=args.per_family)
    log = (lambda s: None) if args.quiet else (lambda s: print(s, flush=True))
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    for engine in engines:
        if engine not in worker.ENGINES:
            ap.error(f"unknown engine {engine!r}; choose from {sorted(worker.ENGINES)}")
    vocab_file = vocab_name = None
    if args.tokenizer:
        if any(e != "kbnf" for e in engines):
            ap.error("--tokenizer is only supported for the kbnf engine (xgrammar/llguidance runs use the synthetic vocabulary)")
        vocab_file, vocab_name = prepare_vocab(args.tokenizer, args.results_dir, args.vocab_name, args.vocab_file,
                                               rebuild=args.rebuild_vocab, log=log)
    for engine in engines:
        options = build_options(args, vocab_file, vocab_name)
        options["engine"] = engine
        options["config"] = args.config if engine == "kbnf" else "default"
        out_path = results_path(args.results_dir, engine, options["config"], vocab_name)
        run_batch(spec_list, options, out_path, args.workers, log=log, resume=not args.no_resume)


if __name__ == "__main__":
    main()
