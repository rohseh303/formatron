# GrammarGuard admission proxy

A small reverse proxy that sits in front of a vLLM (or any OpenAI-compatible) server and
checks every user-supplied decoding constraint — JSON schema, regex, choice list, grammar —
against a resource policy **before** the inference server compiles it. Pathological
constraints are rejected with a structured HTTP 400; everything else is forwarded
unchanged, including streamed (SSE) completions.

Constraint checks run in an isolated worker process
(`formatron.isolation.IsolatedGrammarChecker`) with a hard wall-clock timeout and
best-effort memory limits, so the worst case is a killed worker, never a stalled model
server.

```
client ──► grammar-guard proxy ──► vLLM
              │
              ├─ extract constraints from the request body
              ├─ schema-level limits (formatron.security.SchemaLimits)
              ├─ Formatron schema → KBNF grammar
              └─ kbnf.check_grammar under the hardened policy, in a worker process
```

## Install and run

```bash
pip install "formatron[proxy]"          # fastapi, httpx, uvicorn, anyio

# vLLM listening on :8000, proxy on :8080
python -m formatron.proxy --upstream http://127.0.0.1:8000 --host 0.0.0.0 --port 8080
```

Point clients at the proxy instead of vLLM; nothing else changes:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="…")
client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "Return a person."}],
    response_format={"type": "json_schema", "json_schema": {"name": "person", "schema": {
        "type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
)
```

Every flag has a `GRAMMAR_GUARD_*` environment variable equivalent
(`GRAMMAR_GUARD_UPSTREAM`, `GRAMMAR_GUARD_POLICY`, …). `python -m formatron.proxy --help`
lists them all; the important ones:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--upstream URL` | `http://127.0.0.1:8000` | Inference server requests are forwarded to. |
| `--policy hardened\|unlimited` | `hardened` | `unlimited` measures and never rejects (useful to size limits before enforcing them). |
| `--schema-limit NAME=VALUE` | | Override one `formatron.security.SchemaLimits` field, e.g. `max_enum_members=8192`. `VALUE` is an integer or `none`. Repeatable. |
| `--engine-limit NAME=VALUE` | | Override one hardened KBNF engine limit, e.g. `max_compile_millis=2000`, `regex_memory_bytes=33554432`. Repeatable. |
| `--proxy-limit NAME=VALUE` | | Override a proxy-level lexical limit (see below). |
| `--timeout-s` | `2.0` | Wall-clock limit of one grammar check in the worker; on expiry the worker is killed and respawned. |
| `--memory-mb` | `1024` | Best-effort `RLIMIT_AS`/`RLIMIT_DATA` for the worker (effective on Linux, largely ignored by macOS). `0` disables. |
| `--admission-timeout-s` | `workers × timeout + 2` | Budget for a whole request's admission (queueing included). Expiry → `constraint_check_timeout`. |
| `--admission-workers` | `4` | Threads that may run admissions concurrently; the worker process itself is serialized. |
| `--grammar-dialect passthrough\|kbnf` | `passthrough` | How `guided_grammar` is checked (see caveats). |
| `--on-invalid reject\|forward` | `reject` | Schemas Formatron cannot convert: fail closed, or forward unverified once the schema-level limits passed. |
| `--cache-size` | `1024` | Entries of the LRU decision cache. |
| `--max-body-mb` | `32` | Largest request body parsed; larger bodies get HTTP 413. |
| `--no-scan-all-json` | off | Only inspect `/v1/chat/completions` and `/v1/completions`; by default every JSON `POST`/`PUT`/`PATCH` is scanned too, so constraints cannot be smuggled through e.g. `/v1/responses`. |

### Embedding

```python
import uvicorn
from formatron.proxy import ProxySettings, create_app

app = create_app(ProxySettings(upstream="http://vllm:8000", grammar_dialect="kbnf"))
uvicorn.run(app, host="0.0.0.0", port=8080)
```

## What is checked

| Request field (vLLM / OpenAI) | Constraint kind | Check |
| --- | --- | --- |
| `response_format.json_schema.schema` | JSON schema | schema limits → Formatron conversion → grammar check |
| `guided_json` (object or JSON string) | JSON schema | same; string form is size-checked, then parsed strictly |
| `structured_outputs.json` / `.regex` / `.choice` / `.grammar` | as named | same as the legacy fields |
| `guided_regex` | regex | compiled as `start ::= #'<regex>';` under the hardened policy (`regex_size_estimate`, `regex_memory_bytes`, …) |
| `guided_choice` | choice | count/bytes limits, then `start ::= 'a' \| 'b';` |
| `guided_grammar` | grammar | byte size + lexical bracket nesting (`passthrough`) or a full KBNF check (`kbnf`) |
| `structural_tag` / `response_format: {"type": "structural_tag"}` | JSON schema | every embedded `schema`/`json_schema` object |
| `text.format.schema` (Responses API) | JSON schema | as above |
| `tools[*].function.parameters` | JSON schema | when `tool_choice` names a function or is `required` (`--check-all-tool-schemas` covers `auto`) |

All of these are also recognised under `extra_body`. `response_format: {"type": "json_object"}`
and `{"type": "text"}` carry no user schema and are ignored. When a request carries several
constraints they are checked in the order above; the first rejection is reported.

Schemas that omit `$id` / `$schema` (OpenAI `response_format` schemas usually do) are
checked with defaults filled in; the request body itself is forwarded byte for byte.

Request bodies are parsed fail-closed: malformed JSON and objects with duplicate keys are
rejected (`invalid_constraint`) instead of being interpreted differently from the upstream
parser.

## Error contract

Rejections are HTTP `400` with an OpenAI-style error object:

```json
{
  "error": {
    "message": "regex constraint at guided_regex was not admitted: resource limit exceeded during parsed: regex_size_estimate observed 40204, limit 20000",
    "type": "grammar_guard_rejected",
    "code": "resource_limit_exceeded",
    "param": "guided_regex",
    "violation": {
      "phase": "parsed",
      "resource": "regex_size_estimate",
      "observed": 40204,
      "limit": 20000,
      "path": ""
    },
    "elapsed_ms": 1.7
  }
}
```

| `code` | Meaning |
| --- | --- |
| `resource_limit_exceeded` | A schema, proxy, or engine limit was exceeded; `violation` says which (`phase` ∈ `schema`, `proxy`, `source`, `parsed`, `validated`, `simplified`, `isolation`). |
| `invalid_constraint` | The constraint cannot be interpreted: malformed JSON, wrong type, a schema Formatron cannot convert (root type not object/array, unsupported keyword, bad `$schema`), a KBNF syntax error. `violation` is `null`. |
| `constraint_check_timeout` | The worker exceeded `--timeout-s` (`violation.resource == "wall_clock_ms"`) or the request exceeded `--admission-timeout-s` (`admission_timeout_ms`). Fails closed. |
| `constraint_check_failed` | The worker died (`violation.resource == "worker_exit"`) or the proxy hit an internal error. Fails closed. |

`param` is the dotted request path of the offending field
(`response_format.json_schema.schema`, `extra_body.guided_choice`,
`tools[0].function.parameters`, …). Bodies larger than `--max-body-mb` get HTTP `413` with
the same shape (`violation.resource == "max_body_bytes"`). If the upstream cannot be reached
the proxy answers `502` with `type: grammar_guard_upstream_error`.

Every forwarded response carries `x-grammar-guard`:

- `admitted; elapsed_ms=<n>; constraints=<k>` — checked and forwarded;
- `cached; elapsed_ms=<n>; constraints=<k>` — every constraint was a cache hit;
- `unconstrained` — the body carried no constraint;
- `passthrough` — the request was not inspected (non-JSON, or not a guarded path with `--no-scan-all-json`).

Rejections carry `x-grammar-guard: rejected; code=<code>; elapsed_ms=<n>`. When a constraint
was admitted **without** a full grammar check the response also carries
`x-grammar-guard-unverified: <param>; reason=dialect-passthrough` (or `reason=unsupported-schema`
with `--on-invalid forward`).

Forwarding is otherwise transparent: method, path, query string, and body are relayed
verbatim; request headers are relayed minus hop-by-hop headers (`Authorization` is kept);
upstream status and headers are relayed; SSE streams are relayed chunk by chunk without
buffering.

## Introspection

- `GET /grammar-guard/policy` — the effective limits (schema, engine, proxy), isolation
  settings, and a `fingerprint` that changes whenever any of them do (it is part of the
  decision-cache key).
- `GET /grammar-guard/stats` — request counters, constraint outcomes by
  kind/code/violation resource, admission latency `p50`/`p99`/`max`/`mean`, and cache
  hits/misses/size.
- `GET /grammar-guard/health` — liveness and whether the worker process is up.

One structured log line (`formatron.proxy` logger, `INFO`) is emitted per decision; the
`grammar_guard` field of the record's `extra` carries the per-constraint verdicts for JSON
log handlers.

## Policy tuning

Start with `--policy unlimited` and watch `/grammar-guard/stats` and the logs: every
decision reports the observed complexity, so the hardened defaults can be compared with
real traffic before rejections are turned on. Then move to `hardened` and relax individual
limits:

```bash
python -m formatron.proxy --upstream http://127.0.0.1:8000 \
  --schema-limit max_enum_members=8192 --schema-limit max_items_span=1024 \
  --engine-limit max_compile_millis=2000 --engine-limit regex_memory_bytes=33554432 \
  --proxy-limit max_choices=4096 --timeout-s 4
```

Three layers of limits apply, cheapest first:

1. **Schema limits** (`formatron.security.SchemaLimits`, `--schema-limit`): document
   size/depth/node count, properties, enum members and literal bytes, `minItems`/`maxItems`
   bounds and span, `minLength`/`maxLength`, `pattern` bytes, combinator branches, `$ref`
   count. These bound Formatron's Python generator, which amplifies several keywords long
   before the engine sees a grammar.
2. **Proxy limits** (`--proxy-limit`): `max_constraint_bytes` (constraints sent as JSON
   strings), `max_regex_bytes`, `max_choices`, `max_choice_bytes`, `max_grammar_bytes`,
   `max_grammar_nesting`.
3. **Engine limits** (`kbnf.Config.hardened()`, `--engine-limit`): source bytes, AST nodes,
   nesting depth, regex size estimate and DFA memory, productions before/after
   simplification, compile time, and the per-token decode budgets. Names are listed in
   `--help` and reported by `/grammar-guard/policy`.

`--timeout-s` bounds a single check; keep it small (1–2 s) — a legitimate schema compiles in
milliseconds. Timeouts and crashes kill and respawn the worker, which costs a few hundred
milliseconds; both fail closed.

The decision cache is keyed by `(kind, canonical JSON of the constraint, policy fingerprint)`.
Deterministic verdicts, including worker timeouts, are cached; crashes and per-request budget
timeouts (which depend on load) are not.

## Caveats

- **Resource bounds only.** The proxy decides whether a constraint is *affordable* under the
  policy, not whether it is *correct* or matches what vLLM will do with it. A schema that
  passes may still be rejected by vLLM for semantic reasons, and a rejected schema may be
  perfectly fine for a server with more headroom — tune the limits to your hardware.
- **`guided_grammar` is checked in vLLM's dialect only by size.** vLLM accepts Lark/EBNF
  (xgrammar, guidance) grammars, which are not KBNF. With the default
  `--grammar-dialect passthrough` only `max_grammar_bytes` and `max_grammar_nesting` (lexical
  bracket depth) are enforced and the response is flagged `x-grammar-guard-unverified`. Use
  `--grammar-dialect kbnf` only when the upstream really consumes KBNF grammars (e.g. a
  Formatron-backed server); then the grammar is compiled in the isolated worker like any
  other constraint.
- **Formatron's schema coverage bounds what can be verified.** Schemas using keywords
  Formatron does not support (e.g. `oneOf`, `allOf`, `additionalProperties` other than the
  default, `patternProperties`) are `invalid_constraint` by default even though vLLM may
  accept them. `--on-invalid forward` relaxes this: such schemas are forwarded after the
  schema-level limits (layer 1) passed, flagged as unverified.
- **The grammar check mirrors Formatron's KBNF translation**, not xgrammar's or
  llguidance's compilers. The limits it enforces (enum width, counted repetition,
  regex size, nesting) are the ones that dominate every constrained-decoding backend, but
  the exact thresholds at which vLLM's backend becomes slow differ.
- **Memory limits are best-effort.** `RLIMIT_AS` works on Linux; macOS largely ignores it.
  The wall-clock timeout always applies.
- **Isolation is per proxy process.** One warm worker serves each proxy instance and checks
  are serialized through it; run several proxy replicas (or raise `--admission-workers`
  only together with a larger `--admission-timeout-s`) for high constraint throughput. A
  request whose admission exceeds the budget is rejected, and its in-flight check continues
  until the worker's own timeout frees it.
- The proxy holds the whole request body in memory (bounded by `--max-body-mb`) because it
  must parse it before forwarding. Responses are streamed.
