"""GrammarGuard adversarial JSON-schema benchmark.

See README.md in this directory. Modules:

- ``corpus``  – deterministic seeded generator for the schema corpus
- ``vocab``   – the synthetic token vocabulary shared by every engine
- ``worker``  – the code that runs inside the isolated child process
- ``runner``  – process pool, timeouts, memory watchdog, JSONL output
- ``report``  – aggregates results/*.jsonl into RESULTS.md
"""
