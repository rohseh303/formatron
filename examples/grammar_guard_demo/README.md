# GrammarGuard end-to-end demo

A real language model (`Qwen/Qwen2.5-0.5B-Instruct`) served behind the GrammarGuard
admission proxy. The demo shows two things at once:

- **Ordinary user schemas work.** A realistic order schema (nested objects, an enum,
  optional fields, a bounded array, `minimum`/`maximum` ranges) is admitted by the proxy,
  compiled into a Formatron grammar under the hardened KBNF engine config on the model
  server, and the model's output is **schema-valid JSON**, checked with `jsonschema`
  (with `additionalProperties: false` added, so nothing extra can slip in).
- **Hostile schemas never reach the model.** A 20,000-member enum, a 500-level nested
  schema, a `(a{1,200}){1,200}` regex and a `maxItems: 10000000` array are all rejected
  by the proxy with a structured HTTP 400 in about a millisecond, before any grammar is
  compiled and before the model runs. A property name shaped like a grammar injection
  (`comment' | #'.*`) is *not* rejected — it is escaped, and the output still validates.

```
client.py ──► formatron.proxy (:8080) ──► server.py (:8000, Qwen2.5-0.5B on MPS)
                 │                              │
                 ├─ schema/regex admission      ├─ admit_json_schema again (defense in depth)
                 ├─ isolated grammar check      ├─ JSON schema → Formatron grammar → KBNF engine
                 └─ decision cache              └─ constrained generate() via logits processor
```

## Files

| File | Role |
| --- | --- |
| `server.py` | Minimal OpenAI-compatible upstream: `POST /v1/chat/completions` (non-streaming), `GET /v1/models`, `GET /health`. Loads the model once; when `response_format.json_schema.schema` is present it admits the schema itself, builds a Formatron JSON formatter with `hardened=True`, and generates with the logits processor. Logs per-request timings and returns them in a `grammar_guard` field of the completion body. Rejected schemas get the proxy's error contract (HTTP 400, `error.code`, `error.violation`) so proxy and server visibly agree. |
| `client.py` | Runs scenarios (a)–(h) against the proxy with `httpx`, validates every model output with `jsonschema`, prints a transcript and a summary table. Exit status is non-zero if any scenario misbehaves. `--only a,b` runs a subset. |
| `run_demo.sh` | Starts the server on `:8000` and the proxy on `:8080`, waits for `/health` and `/grammar-guard/health`, runs the client, shuts both down. Logs go to `logs/`. |
| `TRANSCRIPT.md` | Verbatim output of one successful run (client transcript + server timing lines + proxy decisions), so the real model output and the real rejection bodies can be read without running anything. |

## Running it

```bash
source /path/to/.venv/bin/activate     # kbnf (grammar-guard fork), formatron, torch, transformers,
                                       # fastapi, httpx, uvicorn, jsonschema
cd formatron/examples/grammar_guard_demo
./run_demo.sh                          # ≈ 30 s on an M-series Mac once the model is cached
```

Environment knobs: `SERVER_PORT`, `PROXY_PORT`, `DEVICE=auto|mps|cuda|cpu`, `VENV`
(defaults to `../../../.venv`). Extra arguments are passed to `client.py`
(`./run_demo.sh --only a,g`). The pieces also run separately:

```bash
python server.py --port 8000                                   # model server
python -m formatron.proxy --upstream http://127.0.0.1:8000 --port 8080
python client.py --base-url http://127.0.0.1:8080
```

The model and tokenizer must already be in the Hugging Face cache: `server.py` sets
`HF_HUB_OFFLINE=1` by default so a missing network cannot turn into a hang (`HF_HUB_OFFLINE=0`
allows a download). Any chat model works with `--model`, as long as it fits.

## Scenarios

| | Scenario | Expected | What it demonstrates |
| --- | --- | --- | --- |
| a | Realistic order schema | `200`, `x-grammar-guard: admitted`, output valid | The normal path: nested objects, enum, optional fields, `minItems`/`maxItems`, integer and number ranges are all enforced during decoding. |
| b | Property named `comment' \| #'.*` | `200`, output valid, key present literally | The grammar-injection shape: an unescaped `'` would close a KBNF literal and `\| #'.*'` would add an "anything" alternative. Formatron escapes it (`"comment\' \\\| #\'\.\*"` in the grammar); the model emits it as an ordinary key and no extra keys are possible. |
| c | Enum with 20,000 members | `400 resource_limit_exceeded`, `violation.resource = max_enum_members` | Schema-level limit (`SchemaLimits.max_enum_members = 2048`), decided from the document alone. |
| d | 500 nested object levels | `400 resource_limit_exceeded`, `json_nesting_depth` | The proxy's fail-closed body parser refuses to recurse 1000 dict levels deep (500 schema levels × `properties`); had it parsed, `SchemaLimits.max_depth = 64` would reject it next. |
| e | `guided_regex: (a{1,200}){1,200}` | `400 resource_limit_exceeded`, `regex_size_estimate` | Nested counted repetition: the hardened KBNF engine estimates 8,040,004 DFA states against a 20,000 limit, in the isolated worker. |
| f | `maxItems: 10000000` | `400 resource_limit_exceeded`, `max_items_bound` | Formatron emits one production per allowed item count; the schema limit (4096) stops it. |
| g | (a) sent twice more | `200`, `x-grammar-guard: cached` | The proxy's decision cache: `elapsed_ms=0.0`; the server's formatter cache also skips the ~150–700 ms engine build. |
| h | No schema | `200`, `x-grammar-guard: unconstrained` | Free-form requests pass through untouched. |

Every response carries the proxy's `x-grammar-guard` header; the demo server adds
`x-grammar-guard-upstream` with its own decision, so the two verdicts sit next to each
other in the transcript.

## What the timings look like (Apple M-series, MPS, float16)

From `TRANSCRIPT.md`:

- Model load ≈ 0.8–0.9 s (weights already in the OS page cache; 2–3 s cold), engine
  vocabulary (151,665 tokens decoded to bytes) ≈ 0.5–0.6 s, done once at startup.
- Schema → grammar ≈ 2–4 ms; KBNF engine build ≈ 150–180 ms for the ticket schema and
  ≈ 680–830 ms for the order schema on first use (cached afterwards).
- Generation ≈ 50–85 tokens/s constrained, ≈ 60–85 tokens/s unconstrained: the grammar
  mask costs little next to the 0.5B forward pass. (The transcript was recorded while a
  CPU-heavy benchmark ran on the same machine; an idle machine is at the upper end.)
- Proxy admission ≈ 0.2–4 ms per decision after the first; the first check pays for the
  isolated worker's warm-up (≈ 550–650 ms in the transcript). Rejections take ≈ 1 ms end
  to end, and the model server never sees them.

## Hardware notes

- The 0.5B model runs comfortably on Apple Silicon through PyTorch MPS in float16
  (~1 GB of unified memory). `--device cpu` works too, at a few tokens per second.
- Upstream kbnf's torch fast path masked logits with `Tensor.take`, which has no MPS
  kernel; the fork's engine now uses `index_select`/`index_copy_`, so Formatron's
  `FormattersLogitsProcessor` runs directly on the MPS score row with no host round trip.
- The server serialises generations with a lock; it is a demo upstream, not a batch
  scheduler. Keep `max_tokens` modest (the default is 200, capped at 512).

## Caveat: content versus structure

The point of the demo is **structural** validity and **rejection behaviour**, not the
quality of the answers. Qwen2.5-0.5B-Instruct is a tiny model: it invents order ids,
prices, ticket numbers, and it decides where whitespace goes inside the JSON (the
transcript has a lone comma on its own line — legal JSON, odd style). Everything it emits
is nonetheless guaranteed to parse and to satisfy the schema, because tokens that would
leave the grammar are masked before sampling. Likewise, the free-form answer in scenario
(h) is whatever a 0.5B model says; the demo only checks that it was passed through
unconstrained.
