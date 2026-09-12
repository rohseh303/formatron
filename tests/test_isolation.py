import pytest

from formatron.isolation import IsolatedGrammarChecker, check_grammar_isolated
from formatron.security import admit_json_schema

NORMAL_SCHEMA = {
    "$id": "https://example.com/order.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"id": {"type": "integer"}, "name": {"type": "string", "maxLength": 32}},
    "required": ["id"],
}


@pytest.fixture(scope="module")
def checker():
    with IsolatedGrammarChecker(timeout_s=5.0, memory_bytes=None) as instance:
        yield instance


def test_admits_normal_grammar_and_reuses_worker(checker):
    first = checker.check("start ::= 'a' | #'[0-9]+';")
    assert first.admitted and first.outcome == "admitted"
    assert first.grammar_complexity["simplified_productions"] == 2
    assert first.grammar_bytes > 0
    pid = checker._process.pid
    second = checker.check("start ::= 'b';")
    assert second.admitted
    assert checker._process.pid == pid, "warm worker should be reused"
    assert checker.restarts == 0


def test_limit_violation_is_structured(checker):
    result = checker.check("start ::= 'a' | 'b' | 'c';", engine_overrides={"max_simplified_productions": 2})
    assert not result.admitted and result.outcome == "rejected"
    assert result.violation.resource == "simplified_productions"
    assert (result.violation.observed, result.violation.limit) == (3, 2)


def test_syntax_error_is_invalid_not_crash(checker):
    result = checker.check("start ::= ;;; nonsense")
    assert result.outcome == "invalid"
    assert not result.admitted
    assert checker.alive


def test_timeout_kills_and_respawns_worker(checker):
    stalled = checker._simulate_stall(5.0, timeout_s=0.2)
    assert stalled.outcome == "timeout"
    assert stalled.violation.resource == "wall_clock_ms"
    assert not checker.alive
    recovered = checker.check("start ::= 'ok';")
    assert recovered.admitted
    assert checker.restarts >= 1


def test_worker_crash_is_reported_and_recovered(checker):
    crashed = checker._simulate_crash(7)
    assert crashed.outcome == "crashed"
    assert crashed.violation.resource == "worker_exit"
    assert crashed.violation.observed == 7
    recovered = checker.check("start ::= 'ok';")
    assert recovered.admitted


def test_one_shot_helper():
    result = check_grammar_isolated("start ::= #'[a-z]{1,8}';", timeout_s=5.0, memory_bytes=None)
    assert result.admitted
    rejected = check_grammar_isolated(
        "start ::= #'(a{1,200}){1,200}';", timeout_s=5.0, memory_bytes=None
    )
    assert rejected.outcome == "rejected"
    assert rejected.violation.resource == "regex_size_estimate"


def test_admit_json_schema_through_isolated_checker(checker):
    result = admit_json_schema(NORMAL_SCHEMA, checker=checker)
    assert result.admitted
    assert result.schema_complexity["properties_total"] == 2
    assert result.grammar_complexity["simplified_productions"] > 0
