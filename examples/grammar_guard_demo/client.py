"""Drive the GrammarGuard demo scenarios against the proxy and print a transcript.

Each scenario sends one (or two) OpenAI-style chat completion requests, records the HTTP
status, elapsed time and the ``x-grammar-guard`` decision header, validates every model
output against the schema it was requested with (``jsonschema``), and prints either the
parsed JSON or the structured rejection body. A summary table closes the run; the exit
status is non-zero when any scenario did not behave as expected.

Run: ``python client.py --base-url http://127.0.0.1:8080`` (the proxy; see ``--help``).
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import sys
import time
import typing

import httpx
import jsonschema

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
SYSTEM_PROMPT = "You are a helpful assistant. When asked for JSON, answer with JSON only."


# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------


def order_schema() -> dict[str, typing.Any]:
    """A realistic e-commerce order: nested objects, an enum, optional fields, a bounded
    array and numeric ranges (``minimum``/``maximum``)."""
    return {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "minLength": 6, "maxLength": 12},
            "status": {"type": "string", "enum": ["pending", "paid", "shipped", "delivered", "cancelled"]},
            "customer": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "vip": {"type": "boolean"},
                    "address": {
                        "type": "object",
                        "properties": {
                            "street": {"type": "string"},
                            "city": {"type": "string"},
                            "postal_code": {"type": "string"},
                            "country": {"type": "string"},
                        },
                        "required": ["street", "city", "country"],
                    },
                },
                "required": ["name", "email", "address"],
            },
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "description": {"type": "string"},
                        "quantity": {"type": "integer", "minimum": 1, "maximum": 99},
                        "unit_price": {"type": "number", "minimum": 0, "maximum": 10000},
                    },
                    "required": ["sku", "quantity", "unit_price"],
                },
            },
            "discount_percent": {"type": "integer", "minimum": 0, "maximum": 100},
            "notes": {"type": "string"},
        },
        "required": ["order_id", "status", "customer", "items"],
    }


HOSTILE_PROPERTY = "comment' | #'.*"
"""The grammar-injection shape: if a property name were pasted into a KBNF literal
unescaped, ``'`` would close the literal and ``| #'.*'`` would add an "anything goes"
alternative to the grammar. Formatron escapes it, so it is just an odd key."""


def hostile_property_schema() -> dict[str, typing.Any]:
    return {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "integer", "minimum": 1, "maximum": 999999},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            HOSTILE_PROPERTY: {"type": "string"},
        },
        "required": ["ticket_id", "priority", HOSTILE_PROPERTY],
    }


def wide_enum_schema(members: int = 20_000) -> dict[str, typing.Any]:
    return {
        "type": "object",
        "properties": {"country_code": {"type": "string", "enum": [f"XX-{i:05d}" for i in range(members)]}},
        "required": ["country_code"],
    }


def deeply_nested_schema(levels: int = 500) -> dict[str, typing.Any]:
    node: dict[str, typing.Any] = {"type": "string"}
    for _ in range(levels):
        node = {"type": "object", "properties": {"child": node}, "required": ["child"]}
    return node


def huge_array_schema() -> dict[str, typing.Any]:
    return {
        "type": "object",
        "properties": {"ids": {"type": "array", "items": {"type": "integer"}, "maxItems": 10_000_000}},
        "required": ["ids"],
    }


HOSTILE_REGEX = "(a{1,200}){1,200}"


def strict(schema: typing.Any) -> typing.Any:
    """Validation copy that also forbids properties the schema does not list, so an
    injected key would fail validation instead of slipping through."""
    schema = copy.deepcopy(schema)

    def walk(node: typing.Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node.setdefault("additionalProperties", False)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema


# --------------------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------------------


def chat_request(user_prompt: str, *, schema: dict[str, typing.Any] | None = None, name: str = "response",
                 max_tokens: int = 200, **extra: typing.Any) -> dict[str, typing.Any]:
    body: dict[str, typing.Any] = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
    body.update(extra)
    return body


ORDER_PROMPT = (
    "Create an example order for the customer Ada Lovelace (ada@example.com), 12 Analytical Lane, London, GB. "
    "She bought two mechanical keyboards at 89.99 each and one USB-C cable at 9.5; the order has shipped."
)


@dataclasses.dataclass
class Expect:
    status: int
    header_prefix: str
    """Expected start of the ``x-grammar-guard`` header value."""
    code: str | None = None
    resources: tuple[str, ...] = ()
    """Acceptable ``violation.resource`` values (any one) for rejections."""

    def describe(self) -> str:
        parts = [f"{self.status}", self.header_prefix]
        if self.code:
            parts.append(self.code)
        if self.resources:
            parts.append("/".join(self.resources))
        return " ".join(parts)


@dataclasses.dataclass
class Scenario:
    key: str
    title: str
    why: str
    body: dict[str, typing.Any]
    expect: Expect
    schema: dict[str, typing.Any] | None = None
    """Schema used to validate a 200 response's content."""
    repeat: int = 1
    """Send the same request this many times; expectations apply to the last response."""


def scenarios() -> list[Scenario]:
    order = order_schema()
    hostile = hostile_property_schema()
    order_request = chat_request(ORDER_PROMPT, schema=order, name="order")
    return [
        Scenario("a", "Realistic order schema",
                 "nested objects, enum, optional fields, bounded array, minimum/maximum",
                 order_request, Expect(200, "admitted"), schema=order),
        Scenario("b", "Hostile property name (grammar-injection shape)",
                 f"property {HOSTILE_PROPERTY!r} must be escaped into the grammar, not interpreted",
                 chat_request("Create a support ticket about a broken keyboard with a short comment.",
                              schema=hostile, name="ticket"),
                 Expect(200, "admitted"), schema=hostile),
        Scenario("c", "Wide enum (20,000 members)",
                 "one enum member becomes one grammar alternative; 20k of them is not affordable",
                 chat_request("Pick a country code.", schema=wide_enum_schema(), name="country"),
                 Expect(400, "rejected", "resource_limit_exceeded", ("max_enum_members",))),
        Scenario("d", "Deeply nested schema (500 object levels)",
                 "nesting amplifies in every recursive step of schema conversion and parsing",
                 chat_request("Describe a tree.", schema=deeply_nested_schema(), name="deep"),
                 Expect(400, "rejected", "resource_limit_exceeded", ("json_nesting_depth", "max_depth"))),
        Scenario("e", f"guided_regex {HOSTILE_REGEX}",
                 "nested counted repetition explodes the DFA size estimate",
                 chat_request("Say a.", guided_regex=HOSTILE_REGEX),
                 Expect(400, "rejected", "resource_limit_exceeded", ("regex_size_estimate",))),
        Scenario("f", "maxItems: 10,000,000 array",
                 "Formatron emits one production per allowed item count",
                 chat_request("List some ids.", schema=huge_array_schema(), name="ids"),
                 Expect(400, "rejected", "resource_limit_exceeded", ("max_items_bound",))),
        Scenario("g", "Repeat of (a): admission cache hit",
                 "the same constraint is not re-checked; the decision cache answers",
                 copy.deepcopy(order_request), Expect(200, "cached"), schema=order, repeat=2),
        Scenario("h", "Free-form request (no schema)",
                 "nothing to admit; forwarded with x-grammar-guard: unconstrained",
                 chat_request("In one sentence, what does a grammar-constrained decoder do?"),
                 Expect(200, "unconstrained")),
    ]


# --------------------------------------------------------------------------------------
# Transcript
# --------------------------------------------------------------------------------------


def describe_constraint(body: dict[str, typing.Any]) -> str:
    response_format = body.get("response_format")
    if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
        schema = response_format["json_schema"]["schema"]
        old = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old, 20_000))
        try:
            size = len(json.dumps(schema, separators=(",", ":")))
        finally:
            sys.setrecursionlimit(old)
        props = schema.get("properties", {})
        detail = f"{len(props)} top-level propert{'y' if len(props) == 1 else 'ies'}"
        enum = next((v["enum"] for v in props.values() if isinstance(v, dict) and "enum" in v), None)
        if enum is not None and len(enum) > 10:
            detail += f", enum of {len(enum):,} members"
        return f"response_format=json_schema ({size:,} bytes, {detail})"
    if "guided_regex" in body:
        return f"guided_regex={body['guided_regex']!r}"
    return "none (free-form)"


def encode_body(body: dict[str, typing.Any]) -> bytes:
    """``json.dumps`` recurses; the 500-level schema needs more stack than the default."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 20_000))
    try:
        return json.dumps(body).encode("utf-8")
    finally:
        sys.setrecursionlimit(old)


def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def shorten(text: str, limit: int = 110) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclasses.dataclass
class Outcome:
    scenario: Scenario
    status: int
    header: str
    elapsed_ms: float
    ok: bool
    got: str


def run_scenario(client: httpx.Client, scenario: Scenario) -> Outcome:
    print(f"\n{'=' * 100}\n({scenario.key}) {scenario.title}\n{'=' * 100}")
    print(f"  why:        {scenario.why}")
    print(f"  expected:   HTTP {scenario.expect.describe()}")
    user = next(m["content"] for m in scenario.body["messages"] if m["role"] == "user")
    print(f"  prompt:     {shorten(user)}")
    print(f"  constraint: {describe_constraint(scenario.body)}")
    if scenario.repeat > 1:
        print(f"  repeat:     {scenario.repeat}x (identical request)")

    payload = encode_body(scenario.body)
    response: httpx.Response | None = None
    elapsed_ms = 0.0
    for attempt in range(1, scenario.repeat + 1):
        started = time.perf_counter()
        response = client.post("/v1/chat/completions", content=payload, headers={"content-type": "application/json"})
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        header = response.headers.get("x-grammar-guard", "<missing>")
        label = f"  send {attempt}/{scenario.repeat}: " if scenario.repeat > 1 else "  "
        print(f"{label}HTTP {response.status_code}  {elapsed_ms:8.1f} ms  x-grammar-guard: {header}")
        upstream = response.headers.get("x-grammar-guard-upstream")
        if upstream:
            print(f"  {' ' * (len(label) - 2)}x-grammar-guard-upstream: {upstream}")
    assert response is not None
    header = response.headers.get("x-grammar-guard", "<missing>")

    ok = response.status_code == scenario.expect.status and header.startswith(scenario.expect.header_prefix)
    got = f"{response.status_code} {header.split(';', 1)[0]}"

    try:
        body = response.json()
    except ValueError:
        print(indent(f"non-JSON response body: {response.text[:500]!r}"))
        return Outcome(scenario, response.status_code, header, elapsed_ms, False, got + " non-JSON body")

    if response.status_code == 200:
        timings = body.get("grammar_guard") or {}
        if timings.get("constrained"):
            cached = " (formatter cached)" if timings.get("engine_cached") else ""
            print(f"  server:     admission {timings.get('admission_ms')} ms · schema→grammar "
                  f"{timings.get('schema_to_grammar_ms')} ms · engine build {timings.get('engine_build_ms')} ms{cached}"
                  f" · generation {timings.get('generation_ms')} ms · {timings.get('tokens_per_s')} tok/s"
                  f" · grammar {timings.get('grammar_bytes'):,} bytes · completed={timings.get('grammar_completed')}")
        elif timings:
            print(f"  server:     unconstrained · generation {timings.get('generation_ms')} ms · "
                  f"{timings.get('tokens_per_s')} tok/s")
        usage = body.get("usage", {})
        choice = body["choices"][0]
        content = choice["message"]["content"]
        print(f"  usage:      prompt {usage.get('prompt_tokens')} · completion {usage.get('completion_tokens')} tokens"
              f" · finish_reason={choice.get('finish_reason')}")
        if scenario.schema is None:
            print("  content:")
            print(indent(content))
        else:
            print("  content (raw):")
            print(indent(content))
            try:
                parsed = json.loads(content)
            except ValueError as error:
                print(f"  json.loads: FAILED ✗ ({error})")
                ok = False
                got += " unparsable JSON"
            else:
                validator = jsonschema.Draft202012Validator(strict(scenario.schema))
                errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.path))
                if errors:
                    print("  jsonschema: INVALID ✗")
                    for error in errors[:5]:
                        print(f"      at /{'/'.join(map(str, error.path))}: {error.message}")
                    ok = False
                    got += " schema-invalid"
                else:
                    print("  jsonschema: valid ✓ (validated with additionalProperties=false)")
                    got += " valid ✓"
                if scenario.key == "b":
                    if HOSTILE_PROPERTY in parsed:
                        print(f"  injection:  key {HOSTILE_PROPERTY!r} present as a literal key; "
                              "no extra keys admitted ✓")
                    else:
                        print(f"  injection:  key {HOSTILE_PROPERTY!r} MISSING ✗")
                        ok = False
    else:
        error = body.get("error", body)
        print("  error body:")
        print(indent(json.dumps(body, indent=2)))
        violation = error.get("violation") or {}
        resource = violation.get("resource")
        got += f" {error.get('code')}" + (f" ({resource})" if resource else "")
        if scenario.expect.code and error.get("code") != scenario.expect.code:
            ok = False
        if scenario.expect.resources and resource not in scenario.expect.resources:
            ok = False

    print(f"  result:     {'PASS' if ok else 'FAIL'}")
    return Outcome(scenario, response.status_code, header, elapsed_ms, ok, got)


def print_summary(outcomes: list[Outcome]) -> None:
    rows = [(f"({o.scenario.key}) {o.scenario.title}", o.scenario.expect.describe(), o.got, f"{o.elapsed_ms:.0f}",
             "PASS" if o.ok else "FAIL") for o in outcomes]
    headers = ("scenario", "expected", "got", "ms", "result")
    widths = [max(len(r[i]) for r in rows + [headers]) for i in range(5)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(f"\n{'=' * 100}\nSummary\n{'=' * 100}")
    print(line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
    passed = sum(o.ok for o in outcomes)
    print(f"\n{passed}/{len(outcomes)} scenarios behaved as expected")


def print_proxy_stats(client: httpx.Client) -> None:
    try:
        stats = client.get("/grammar-guard/stats").json()
    except (httpx.HTTPError, ValueError):
        return
    cache = stats.get("cache", {})
    requests = stats.get("requests", {})
    latency = stats.get("admission_latency_ms", stats.get("latency_ms", {}))
    print(f"\nproxy /grammar-guard/stats: requests={json.dumps(requests, sort_keys=True)} "
          f"cache={json.dumps(cache, sort_keys=True)} admission_latency_ms={json.dumps(latency, sort_keys=True)}")


def main(argv: typing.Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GrammarGuard demo client")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="the proxy (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=300.0, help="per-request timeout in seconds")
    parser.add_argument("--only", default="", help="comma-separated scenario keys to run, e.g. a,b,g")
    args = parser.parse_args(argv)

    selected = {k.strip() for k in args.only.split(",") if k.strip()}
    todo = [s for s in scenarios() if not selected or s.key in selected]

    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        policy = client.get("/grammar-guard/policy").json()
        models = client.get("/v1/models").json()
        print(f"GrammarGuard demo — proxy {args.base_url} policy={policy.get('policy')} "
              f"fingerprint={str(policy.get('fingerprint'))[:12]} upstream={policy.get('upstream')}")
        print(f"upstream models: {[m['id'] for m in models.get('data', [])]}")
        outcomes = [run_scenario(client, scenario) for scenario in todo]
        print_summary(outcomes)
        print_proxy_stats(client)
    return 0 if all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
