# Transcript of one full run

Verbatim output of `./run_demo.sh` on 2026-09-12: Apple M5 Pro, 48 GB unified memory, macOS,
Python 3.11.10, torch 2.14.0 (MPS, float16), transformers 5.17.0, kbnf grammar-guard fork.
Nothing below was edited; the model output is exactly what `Qwen/Qwen2.5-0.5B-Instruct`
produced under the grammar, and the rejection bodies are exactly what the proxy returned.
Regenerate with `python transcript.py` after a run.

- Client transcript: `client.py` talking to the proxy on `:8080` (`logs/client.log`).
- Server timing lines: the `grammar_guard_demo.server` logger on `:8000` (`logs/server.log`).
- Proxy decisions: the `formatron.proxy` logger on `:8080` (`logs/proxy.log`).

## Client transcript

```text
GrammarGuard demo — proxy http://127.0.0.1:8080 policy=hardened fingerprint=410643afba0d upstream=http://127.0.0.1:8000
upstream models: ['Qwen/Qwen2.5-0.5B-Instruct']

====================================================================================================
(a) Realistic order schema
====================================================================================================
  why:        nested objects, enum, optional fields, bounded array, minimum/maximum
  expected:   HTTP 200 admitted
  prompt:     Create an example order for the customer Ada Lovelace (ada@example.com), 12 Analytical Lane, London, GB. She …
  constraint: response_format=json_schema (976 bytes, 6 top-level properties)
  HTTP 200    4589.3 ms  x-grammar-guard: admitted; elapsed_ms=635.5; constraints=1
  x-grammar-guard-upstream: admitted; elapsed_ms=6.1
  server:     admission 6.077 ms · schema→grammar 3.645 ms · engine build 857.783 ms · generation 3070.4 ms · 53.1 tok/s · grammar 4,874 bytes · completed=True
  usage:      prompt 85 · completion 163 tokens · finish_reason=stop
  content (raw):
    {
      "order_id": "123456",
      "status": "shipped",
      "customer": {
        "name": "Ada Lovelace",
        "email": "ada@example.com"
      ,
      "address": {
        "street": "12 Analytical Lane",
        "city": "London",
        "country": "GB"
      }
    },
    "items": [
      {
        "sku": "MK-001",
        "quantity": 2,
        "unit_price": 89.99
      },
      {
        "sku": "USB-C Cable",
        "quantity": 1,
        "unit_price": 9.5
      }
    ],
    "notes": "The order was successfully placed."
    }
  jsonschema: valid ✓ (validated with additionalProperties=false)
  result:     PASS

====================================================================================================
(b) Hostile property name (grammar-injection shape)
====================================================================================================
  why:        property "comment' | #'.*" must be escaped into the grammar, not interpreted
  expected:   HTTP 200 admitted
  prompt:     Create a support ticket about a broken keyboard with a short comment.
  constraint: response_format=json_schema (242 bytes, 3 top-level properties)
  HTTP 200    1029.4 ms  x-grammar-guard: admitted; elapsed_ms=3.4; constraints=1
  x-grammar-guard-upstream: admitted; elapsed_ms=2.7
  server:     admission 2.704 ms · schema→grammar 1.882 ms · engine build 186.038 ms · generation 829.8 ms · 56.6 tok/s · grammar 1,351 bytes · completed=True
  usage:      prompt 42 · completion 47 tokens · finish_reason=stop
  content (raw):
    {
      "ticket_id": 12345,
      "priority": "high",
      "comment' | #'.*" : "The keyboard is not working properly and needs to be replaced."
    }
  jsonschema: valid ✓ (validated with additionalProperties=false)
  injection:  key "comment' | #'.*" present as a literal key; no extra keys admitted ✓
  result:     PASS

====================================================================================================
(c) Wide enum (20,000 members)
====================================================================================================
  why:        one enum member becomes one grammar alternative; 20k of them is not affordable
  expected:   HTTP 400 rejected resource_limit_exceeded max_enum_members
  prompt:     Pick a country code.
  constraint: response_format=json_schema (220,102 bytes, 1 top-level property, enum of 20,000 members)
  HTTP 400       3.6 ms  x-grammar-guard: rejected; code=resource_limit_exceeded; elapsed_ms=1.3
  error body:
    {
      "error": {
        "message": "json_schema constraint at response_format.json_schema.schema was not admitted: resource limit exceeded during schema at /properties/country_code: max_enum_members observed 20000, limit 2048",
        "type": "grammar_guard_rejected",
        "code": "resource_limit_exceeded",
        "param": "response_format.json_schema.schema",
        "violation": {
          "phase": "schema",
          "resource": "max_enum_members",
          "observed": 20000,
          "limit": 2048,
          "path": "/properties/country_code"
        },
        "elapsed_ms": 1.273
      }
    }
  result:     PASS

====================================================================================================
(d) Deeply nested schema (500 object levels)
====================================================================================================
  why:        nesting amplifies in every recursive step of schema conversion and parsing
  expected:   HTTP 400 rejected resource_limit_exceeded json_nesting_depth/max_depth
  prompt:     Describe a tree.
  constraint: response_format=json_schema (31,017 bytes, 1 top-level property)
  HTTP 400       1.2 ms  x-grammar-guard: rejected; code=resource_limit_exceeded; elapsed_ms=0.2
  error body:
    {
      "error": {
        "message": "resource limit exceeded during proxy at body: json_nesting_depth observed 1000, limit 1000",
        "type": "grammar_guard_rejected",
        "code": "resource_limit_exceeded",
        "param": "body",
        "violation": {
          "phase": "proxy",
          "resource": "json_nesting_depth",
          "observed": 1000,
          "limit": 1000,
          "path": "body"
        },
        "elapsed_ms": 0.201
      }
    }
  result:     PASS

====================================================================================================
(e) guided_regex (a{1,200}){1,200}
====================================================================================================
  why:        nested counted repetition explodes the DFA size estimate
  expected:   HTTP 400 rejected resource_limit_exceeded regex_size_estimate
  prompt:     Say a.
  constraint: guided_regex='(a{1,200}){1,200}'
  HTTP 400       1.1 ms  x-grammar-guard: rejected; code=resource_limit_exceeded; elapsed_ms=0.4
  error body:
    {
      "error": {
        "message": "regex constraint at guided_regex was not admitted: grammar resource limit exceeded during parsed: regex_size_estimate observed 8040004, limit 20000",
        "type": "grammar_guard_rejected",
        "code": "resource_limit_exceeded",
        "param": "guided_regex",
        "violation": {
          "phase": "parsed",
          "resource": "regex_size_estimate",
          "observed": 8040004,
          "limit": 20000,
          "path": ""
        },
        "elapsed_ms": 0.397
      }
    }
  result:     PASS

====================================================================================================
(f) maxItems: 10,000,000 array
====================================================================================================
  why:        Formatron emits one production per allowed item count
  expected:   HTTP 400 rejected resource_limit_exceeded max_items_bound
  prompt:     List some ids.
  constraint: response_format=json_schema (121 bytes, 1 top-level property)
  HTTP 400       1.1 ms  x-grammar-guard: rejected; code=resource_limit_exceeded; elapsed_ms=0.2
  error body:
    {
      "error": {
        "message": "json_schema constraint at response_format.json_schema.schema was not admitted: resource limit exceeded during schema at /properties/ids: max_items_bound observed 10000000, limit 4096",
        "type": "grammar_guard_rejected",
        "code": "resource_limit_exceeded",
        "param": "response_format.json_schema.schema",
        "violation": {
          "phase": "schema",
          "resource": "max_items_bound",
          "observed": 10000000,
          "limit": 4096,
          "path": "/properties/ids"
        },
        "elapsed_ms": 0.221
      }
    }
  result:     PASS

====================================================================================================
(g) Repeat of (a): admission cache hit
====================================================================================================
  why:        the same constraint is not re-checked; the decision cache answers
  expected:   HTTP 200 cached
  prompt:     Create an example order for the customer Ada Lovelace (ada@example.com), 12 Analytical Lane, London, GB. She …
  constraint: response_format=json_schema (976 bytes, 6 top-level properties)
  repeat:     2x (identical request)
  send 1/2: HTTP 200    2679.8 ms  x-grammar-guard: cached; elapsed_ms=0.0; constraints=1
            x-grammar-guard-upstream: admitted; elapsed_ms=5.4
  send 2/2: HTTP 200    2621.6 ms  x-grammar-guard: cached; elapsed_ms=0.1; constraints=1
            x-grammar-guard-upstream: admitted; elapsed_ms=5.5
  server:     admission 5.505 ms · schema→grammar 0.0 ms · engine build 0.0 ms (formatter cached) · generation 2610.8 ms · 62.4 tok/s · grammar 4,874 bytes · completed=True
  usage:      prompt 85 · completion 163 tokens · finish_reason=stop
  content (raw):
    {
      "order_id": "123456",
      "status": "shipped",
      "customer": {
        "name": "Ada Lovelace",
        "email": "ada@example.com"
      ,
      "address": {
        "street": "12 Analytical Lane",
        "city": "London",
        "country": "GB"
      }
    },
    "items": [
      {
        "sku": "MK-001",
        "quantity": 2,
        "unit_price": 89.99
      },
      {
        "sku": "USB-C Cable",
        "quantity": 1,
        "unit_price": 9.5
      }
    ],
    "notes": "The order was successfully placed."
    }
  jsonschema: valid ✓ (validated with additionalProperties=false)
  result:     PASS

====================================================================================================
(h) Free-form request (no schema)
====================================================================================================
  why:        nothing to admit; forwarded with x-grammar-guard: unconstrained
  expected:   HTTP 200 unconstrained
  prompt:     In one sentence, what does a grammar-constrained decoder do?
  constraint: none (free-form)
  HTTP 200     319.7 ms  x-grammar-guard: unconstrained
  x-grammar-guard-upstream: unconstrained
  server:     unconstrained · generation 315.2 ms · 73.0 tok/s
  usage:      prompt 42 · completion 23 tokens · finish_reason=stop
  content:
    A grammar-constrained decoder is a type of neural network designed to decode grammatically correct sentences from input text.
  result:     PASS

====================================================================================================
Summary
====================================================================================================
scenario                                             expected                                                           got                                                         ms    result
---------------------------------------------------  -----------------------------------------------------------------  ----------------------------------------------------------  ----  ------
(a) Realistic order schema                           200 admitted                                                       200 admitted valid ✓                                        4589  PASS  
(b) Hostile property name (grammar-injection shape)  200 admitted                                                       200 admitted valid ✓                                        1029  PASS  
(c) Wide enum (20,000 members)                       400 rejected resource_limit_exceeded max_enum_members              400 rejected resource_limit_exceeded (max_enum_members)     4     PASS  
(d) Deeply nested schema (500 object levels)         400 rejected resource_limit_exceeded json_nesting_depth/max_depth  400 rejected resource_limit_exceeded (json_nesting_depth)   1     PASS  
(e) guided_regex (a{1,200}){1,200}                   400 rejected resource_limit_exceeded regex_size_estimate           400 rejected resource_limit_exceeded (regex_size_estimate)  1     PASS  
(f) maxItems: 10,000,000 array                       400 rejected resource_limit_exceeded max_items_bound               400 rejected resource_limit_exceeded (max_items_bound)      1     PASS  
(g) Repeat of (a): admission cache hit               200 cached                                                         200 cached valid ✓                                          2622  PASS  
(h) Free-form request (no schema)                    200 unconstrained                                                  200 unconstrained                                           320   PASS  

8/8 scenarios behaved as expected

proxy /grammar-guard/stats: requests={"forwarded": 4, "rejected": 4, "too_large": 0, "total": 10, "unconstrained": 2, "upstream_errors": 0} cache={"capacity": 1024, "hits": 2, "misses": 5, "size": 5} admission_latency_ms={"max": 635.4988749999393, "mean": 91.55523257153878, "p50": 0.397417000385758, "p99": 635.4988749999393, "samples": 7}
```

## Server timing lines

```text
2026-09-12 21:58:31,204 INFO grammar_guard_demo.server model loaded model=Qwen/Qwen2.5-0.5B-Instruct device=mps dtype=torch.float16 load_s=0.81 vocabulary_s=0.61 vocab_size=151665
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
2026-09-12 21:58:38,015 INFO grammar_guard_demo.server request id=chatcmpl-d2309ea71bd7 constrained=True admission_ms=6.077 schema_to_grammar_ms=3.645 engine_build_ms=857.783 engine_cached=False generation_ms=3070.4 completion_tokens=163 tokens_per_s=53.1 finish=stop grammar_completed=True total_ms=3948.1
2026-09-12 21:58:39,046 INFO grammar_guard_demo.server request id=chatcmpl-3da776464f28 constrained=True admission_ms=2.704 schema_to_grammar_ms=1.882 engine_build_ms=186.038 engine_cached=False generation_ms=829.8 completion_tokens=47 tokens_per_s=56.6 finish=stop grammar_completed=True total_ms=1023.0
2026-09-12 21:58:41,736 INFO grammar_guard_demo.server request id=chatcmpl-ab1fb867a88c constrained=True admission_ms=5.38 schema_to_grammar_ms=0.0 engine_build_ms=0.0 engine_cached=True generation_ms=2668.5 completion_tokens=163 tokens_per_s=61.1 finish=stop grammar_completed=True total_ms=2677.2
2026-09-12 21:58:44,357 INFO grammar_guard_demo.server request id=chatcmpl-fc89940f9383 constrained=True admission_ms=5.505 schema_to_grammar_ms=0.0 engine_build_ms=0.0 engine_cached=True generation_ms=2610.8 completion_tokens=163 tokens_per_s=62.4 finish=stop grammar_completed=True total_ms=2619.0
2026-09-12 21:58:44,677 INFO grammar_guard_demo.server request id=chatcmpl-cdcf36e4a62a constrained=False admission_ms=- schema_to_grammar_ms=- engine_build_ms=- engine_cached=- generation_ms=315.2 completion_tokens=23 tokens_per_s=73.0 finish=stop grammar_completed=None total_ms=317.4
```

## Proxy decisions

```text
2026-09-12 21:58:32,733 INFO formatron.proxy grammar-guard proxy ready upstream=http://127.0.0.1:8000 policy=hardened dialect=passthrough fingerprint=410643afba0d649e
INFO:     127.0.0.1:50990 - "GET /grammar-guard/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:50991 - "GET /grammar-guard/policy HTTP/1.1" 200 OK
INFO:     127.0.0.1:50991 - "GET /v1/models HTTP/1.1" 200 OK
2026-09-12 21:58:34,064 INFO formatron.proxy decision path=/v1/chat/completions status=forwarded outcome=admitted kind=json_schema param=response_format.json_schema.schema code=None resource=None cached=False constraints=1 elapsed_ms=635.50
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-09-12 21:58:38,022 INFO formatron.proxy decision path=/v1/chat/completions status=forwarded outcome=admitted kind=json_schema param=response_format.json_schema.schema code=None resource=None cached=False constraints=1 elapsed_ms=3.38
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-09-12 21:58:39,051 INFO formatron.proxy decision path=/v1/chat/completions status=rejected outcome=rejected kind=json_schema param=response_format.json_schema.schema code=resource_limit_exceeded resource=max_enum_members cached=False constraints=1 elapsed_ms=1.27
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request
2026-09-12 21:58:39,054 INFO formatron.proxy decision path=/v1/chat/completions status=rejected code=resource_limit_exceeded param=body resource=json_nesting_depth
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request
2026-09-12 21:58:39,056 INFO formatron.proxy decision path=/v1/chat/completions status=rejected outcome=rejected kind=regex param=guided_regex code=resource_limit_exceeded resource=regex_size_estimate cached=False constraints=1 elapsed_ms=0.40
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request
2026-09-12 21:58:39,057 INFO formatron.proxy decision path=/v1/chat/completions status=rejected outcome=rejected kind=json_schema param=response_format.json_schema.schema code=resource_limit_exceeded resource=max_items_bound cached=False constraints=1 elapsed_ms=0.22
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request
2026-09-12 21:58:39,058 INFO formatron.proxy decision path=/v1/chat/completions status=forwarded outcome=admitted kind=json_schema param=response_format.json_schema.schema code=None resource=None cached=True constraints=1 elapsed_ms=0.05
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-09-12 21:58:41,738 INFO formatron.proxy decision path=/v1/chat/completions status=forwarded outcome=admitted kind=json_schema param=response_format.json_schema.schema code=None resource=None cached=True constraints=1 elapsed_ms=0.07
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 200 OK
2026-09-12 21:58:44,359 INFO formatron.proxy decision path=/v1/chat/completions status=unconstrained outcome=unconstrained kind=- param=- code=- resource=- cached=- constraints=0 elapsed_ms=0.03
INFO:     127.0.0.1:50991 - "POST /v1/chat/completions HTTP/1.1" 200 OK
INFO:     127.0.0.1:50991 - "GET /grammar-guard/stats HTTP/1.1" 200 OK
```
