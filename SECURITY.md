# Security policy for custom formats

Formatron converts JSON Schema, Pydantic models, regexes, and custom builders into
KBNF grammars. If a client controls any of those inputs, grammar construction and
decoding are untrusted compute workloads.

## Layers

1. **Schema admission** — `formatron.security.check_json_schema` measures a JSON
   Schema document iteratively (depth, nodes, properties, enum/const literals,
   `minItems`/`maxItems` bounds and spans, `minLength`/`maxLength`, pattern bytes,
   combinator branches, `$ref` count, serialized size) and rejects it against a
   `SchemaLimits` policy *before* conversion. This bounds the amplification that
   happens inside Formatron's own generator, which the KBNF engine can never see.
2. **Grammar construction** — the hardened KBNF fork's `GrammarLimits` bound source
   and AST size, lexical and AST depth, interned string tables, regex source bytes and
   estimated NFA size, DFA memory, estimated EBNF expansion, simplified grammar size,
   and cooperative compile time. `check_grammar` runs this pipeline without a
   vocabulary; `hardened_engine_config(**overrides)` tunes it.
3. **Decoding** — the fork's `DecodeLimits` cap Earley items per set and per chart
   after every accepted byte and bound the allowed-token cache, so ambiguous grammars
   cannot grow parser state with output length. Over-budget tokens are masked out; a
   forced token fails closed with `ResourceLimitExceeded`.
4. **Process isolation** — `formatron.isolation.IsolatedGrammarChecker` executes the
   grammar check in a disposable worker with a hard wall-clock timeout and best-effort
   `RLIMIT_AS`/`RLIMIT_DATA`/`RLIMIT_CPU` limits, kills and respawns it on timeout, and
   classifies crashes. In-process limits cannot preempt a single native call (parser,
   regex compiler, allocator); the worker boundary is what makes the worst case a
   killed process rather than a stalled model server.
5. **Edge enforcement** — `formatron.proxy` applies the layers above to OpenAI and
   vLLM structured-output request fields and rejects with a structured 400.

Use `FormatterBuilder.build(..., hardened=True)` for the standard engine policy and
`admit_json_schema(schema, checker=...)` for the end-to-end decision. Every rejection
carries a `LimitViolation` (phase, resource, observed, limit, path) suitable for logs,
metrics, and error bodies. Bound successful-artifact caches and key them by the
grammar, tokenizer, engine version, and complete policy.

## Non-goals

This phase protects availability during syntactic constraint construction and
decoding. It does not enforce cross-field or application semantics; validate those
separately after generation. It also does not verify grammars written in other
engines' dialects (for example vLLM's EBNF); the proxy only size-checks those unless
told the dialect is KBNF.

## Reporting

Open a private security advisory on the fork's GitHub repository with a minimal
schema or grammar that reproduces the resource exhaustion under the hardened policy.
