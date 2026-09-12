# Security policy for custom formats

Formatron converts JSON Schema, Pydantic models, regexes, and custom builders into
KBNF grammars. If a client controls any of those inputs, grammar construction is an
untrusted compute workload.

Use `FormatterBuilder.build(..., hardened=True)` for the standard policy, or pass
`formatron.security.hardened_engine_config(...)` when the service needs tighter
tenant-specific limits. `formatron.security.inspect_grammar(...)` exposes cheap
pre-compilation metrics for admission logs and policy decisions.

The hardened KBNF fork limits source and AST size, lexical and AST depth, interned
string tables, regex source/DFA memory, estimated EBNF expansion, simplified grammar
size, and cooperative compile time. Errors fail closed before an engine is returned.

These checks cannot preempt a single native call. Production services that accept
arbitrary grammars must additionally compile them in a disposable worker process
with operating-system memory and wall-clock limits. Bound successful-artifact caches
and key them by the grammar, tokenizer, engine version, and complete policy.

This phase protects availability during syntactic constraint construction. It does
not enforce cross-field or application semantics; validate those separately after
generation.
