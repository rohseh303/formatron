"""Fast smoke test for the GrammarGuard adversarial-schema benchmark.

Runs a dozen schemas through the corpus generator, the in-process worker, the
isolated runner (tiny timeouts) and the report generator.  External engines are
exercised only when importable.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # ``benchmarks`` is a namespace package next to ``src``
    sys.path.insert(0, str(ROOT))

pytest.importorskip("kbnf")
jsonschema = pytest.importorskip("jsonschema")

from benchmarks.grammar_guard import corpus, report, runner, vocab, worker  # noqa: E402

KBNF_OPTIONS = {"engine": "kbnf", "seed": corpus.SEED, "token_cap": 96, "timeout": 5.0}


def _opts(**kw):
    o = dict(KBNF_OPTIONS)
    o.update(kw)
    return o


# ------------------------------------------------------------------ corpus


def test_corpus_is_large_deterministic_and_well_formed():
    specs = corpus.specs()
    assert len(specs) >= 1000
    ids = [s.id for s in specs]
    assert len(set(ids)) == len(ids)
    cats = {s.category for s in specs}
    assert cats == {"normal", "adversarial"}
    assert sum(s.category == "normal" for s in specs) >= 550
    assert sum(s.category == "adversarial" for s in specs) >= 350
    assert {s.expect for s in specs} <= {"admit", "reject", "either"}
    families = {s.family for s in specs}
    for required in ("deep_nesting", "wide_enum", "giant_const", "huge_items", "huge_string_length",
                     "regex_nested_quantifiers", "regex_counted_repetition", "many_optional_props",
                     "thousands_of_props", "recursive_ref_fanout", "unicode_heavy", "mixed_combo",
                     "flat_object", "patterns", "refs_defs", "recursion"):
        assert required in families
    # deterministic materialisation and a valid record shape on a small cheap sample
    sample = corpus.filter_specs(specs, per_family=1)
    sample = [s for s in sample if s.family not in ("giant_const", "huge_items", "huge_string_length", "wide_enum")]
    for spec in sample:
        a = corpus.materialize(spec)
        b = corpus.materialize(spec)
        assert a == b
        assert a["$id"].endswith(spec.id) and "$schema" in a
    rec = next(corpus.records(spec_list=[sample[0]]))
    assert set(rec) == {"id", "family", "category", "expect", "schema"}


def test_normal_schemas_are_valid_json_schema():
    validator = jsonschema.Draft202012Validator
    for spec in corpus.filter_specs(corpus.specs(), category="normal", per_family=1):
        validator.check_schema(corpus.materialize(spec))


# ------------------------------------------------------------------ worker (in-process)


@pytest.mark.parametrize("spec_id", ["normal/flat_object/0000", "normal/patterns/0003", "normal/recursion/0000",
                                     "normal/numeric_bounds/0000", "normal/nested_object/0001"])
def test_worker_hardened_admits_normal_schema_and_output_validates(spec_id):
    spec = corpus.get(spec_id)
    r = worker.run_in_process(spec, _opts(config="hardened", token_cap=512))
    assert r["outcome"] == "admitted", r.get("reason")
    assert r["admission"]["outcome"] == "admitted"
    assert r["compile_ms"] >= 0 and r["grammar_bytes"] > 0 and r["inspect"]["nonterminals"] > 0
    g = r["generation"]
    assert g["tokens"] > 0
    assert g["mask_ms"]["p50"] is not None
    if g["completed"]:
        assert g["output_valid"], g["validation_error"]


@pytest.mark.parametrize("spec_id,resource", [
    ("adv/wide_enum/0002", "max_enum_members"),      # 10k-member enum
    ("adv/huge_items/0000", "max_items_span"),       # maxItems 1000
    ("adv/deep_nesting/0000", "max_depth"),          # 50 nested objects
    ("adv/giant_const/0000", "max_literal_bytes"),   # 64 KB const
])
def test_worker_hardened_rejects_attacks_fast_with_structured_reason(spec_id, resource):
    spec = corpus.get(spec_id)
    r = worker.run_in_process(spec, _opts(config="hardened"))
    assert r["outcome"] == "rejected"
    assert r["phase_reached"] == "admission"
    assert r["reason"]["kind"] == "schema_limit"
    assert r["reason"]["resource"] == resource
    assert r["reason"]["observed"] > r["reason"]["limit"]
    assert r["admission_ms"] < 2000


def test_worker_both_configs_admit_medium_enum():
    spec = corpus.get("normal/enum_medium/0003")  # 129 members; alternation chains no longer count as nesting
    hard = worker.run_in_process(spec, _opts(config="hardened", token_cap=512))
    dflt = worker.run_in_process(spec, _opts(config="default", token_cap=512))
    for result in (hard, dflt):
        assert result["outcome"] == "admitted", result.get("reason")
        assert result["generation"]["completed"] and result["generation"]["output_valid"]


def test_classify_message_parses_limit_format():
    r = worker.classify_message("grammar resource limit exceeded during parsed: nesting_depth observed 129, limit 128", "compile", "ValueError")
    assert r["kind"] == "grammar_limit" and r["resource"] == "nesting_depth" and (r["observed"], r["limit"]) == (129, 128)
    r = worker.classify_message("resource limit exceeded during schema at /properties/x: max_enum_members observed 5, limit 2", "admission")
    assert r["kind"] == "schema_limit" and r["path"] == "/properties/x"
    r = worker.classify_message("pattern is mutually exclusive with min_length", "grammar_gen", "AssertionError")
    assert r["kind"] == "unsupported_schema"


def test_vocabulary_covers_every_byte_and_is_deduplicated():
    toks = vocab.build_vocabulary(tuple(corpus.KEY_POOL))
    assert len(set(toks)) == len(toks) and len(toks) > 2000
    assert all(bytes([i]) in toks for i in range(256))
    assert vocab.decode_bytes(toks, [toks.index(b"{"), toks.index(b"}")]) == b"{}"


# ------------------------------------------------------------------ runner (isolated)


def test_runner_isolates_timeouts_and_writes_resumable_jsonl(tmp_path):
    options = _opts(config="default", timeout=2.5, mem_mb=2048)
    # giant 8 MB const under the unlimited path takes far longer than 2.5 s (or OOMs) -> must be killed, never hang
    slow = corpus.get("adv/giant_const/0005")
    r = runner.run_isolated(slow, options)
    assert r["outcome"] in ("timeout", "oom", "crash"), r
    assert r["id"] == slow.id and r["wall_ms_parent"] < 15_000
    if r["outcome"] == "timeout":
        assert r["reason"]["kind"] == "timeout"

    out = tmp_path / "default.jsonl"
    specs = [corpus.get("normal/flat_object/0001"), corpus.get("normal/tuples/0000")]
    res = runner.run_batch(specs, options, str(out), workers=2, log=lambda s: None)
    assert {x["id"] for x in res} == {s.id for s in specs}
    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert len(rows) == 2 and all(x["outcome"] == "admitted" for x in rows)
    # resumable: nothing left to run
    assert runner.run_batch(specs, options, str(out), workers=2, log=lambda s: None) == []
    assert runner.load_done_ids(str(out)) == {s.id for s in specs}


# ------------------------------------------------------------------ report


def test_report_builds_from_partial_results(tmp_path):
    rows = []
    for sid, cfg in (("normal/flat_object/0000", "hardened"), ("adv/wide_enum/0002", "hardened"), ("normal/flat_object/0000", "default")):
        rows.append((cfg, worker.run_in_process(corpus.get(sid), _opts(config=cfg))))
    for cfg in ("hardened", "default"):
        with open(tmp_path / f"{cfg}.jsonl", "w") as f:
            for c, r in rows:
                if c == cfg:
                    r["wall_ms_parent"] = r["wall_ms"]
                    r["peak_rss_mb_observed"] = 0
                    f.write(json.dumps(r) + "\n")
    text = report.build_report(str(tmp_path), analysis_path=None)
    assert "## Headline numbers" in text and "flat_object" in text and "wide_enum" in text
    assert "kbnf-hardened" in text and "kbnf-default" in text and "Resource attacks" in text
    out = tmp_path / "RESULTS.md"
    report.main(["--results-dir", str(tmp_path), "--out", str(out), "--no-analysis"])
    assert out.exists() and out.stat().st_size > 1000


# ------------------------------------------------------------------ real tokenizer vocabulary (optional)

TOKENIZER_ID = "Qwen/Qwen2.5-0.5B-Instruct"


@pytest.fixture(scope="module")
def qwen_vocab_file(tmp_path_factory):
    """Pickle the real Qwen2.5 vocabulary once (skips when transformers or the cached tokenizer is missing)."""
    pytest.importorskip("transformers")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    path = str(tmp_path_factory.mktemp("vocab") / "vocab-qwen2.5.pkl")
    try:
        meta = vocab.build_vocab_file(TOKENIZER_ID, path)
    except Exception as exc:  # OSError from the hub when offline & uncached, or any transformers loading failure
        pytest.skip(f"tokenizer {TOKENIZER_ID} unavailable: {type(exc).__name__}: {str(exc)[:120]}")
    assert meta["size"] > 100_000 and meta["missing_single_bytes"] == 0 and meta["id_holes"] == 0
    return path


def test_vocab_name_and_results_path_for_tokenizer(tmp_path):
    assert vocab.vocab_name_from_tokenizer(TOKENIZER_ID) == "qwen2.5"
    assert vocab.vocab_name_from_tokenizer("meta-llama/Llama-3.1-8B-Instruct") == "llama"
    assert runner.results_path(str(tmp_path), "kbnf", "hardened", "qwen2.5").endswith("hardened-qwen2.5.jsonl")
    assert runner.results_path(str(tmp_path), "kbnf", "default").endswith(os.sep + "default.jsonl")
    assert vocab.token_table({0: b"a", 2: b"c"}) == (b"a", b"", b"c")


def test_worker_runs_on_real_tokenizer_vocabulary(qwen_vocab_file):
    meta = vocab.read_vocab_meta(qwen_vocab_file)
    assert meta["tokenizer"] == TOKENIZER_ID and meta["format"] == vocab.VOCAB_FILE_FORMAT
    tokens, kv, info = worker.load_kbnf_vocabulary({"vocab_file": qwen_vocab_file})
    assert info["tokenizer"] == TOKENIZER_ID and len(tokens) == info["size"] == kv.get_vocab_size()
    assert all(bytes([b]) in set(tokens) for b in (ord("{"), ord('"'), 0x00))  # single bytes survive unmangling
    for spec_id in ("normal/flat_object/0001", "normal/enum_fields/0000"):
        r = worker.run_in_process(corpus.get(spec_id), _opts(config="hardened", token_cap=256, vocab_file=qwen_vocab_file,
                                                             vocab_name="qwen2.5"))
        assert r["outcome"] == "admitted", r.get("reason")
        assert r["vocab"] == {**r["vocab"], "name": "qwen2.5", "tokenizer": TOKENIZER_ID, "size": meta["size"]}
        assert r["vocab_size"] == meta["size"] and r["vocab_load_ms"] >= 0 and r["compile_ms"] > 0
        g = r["generation"]
        assert g["tokens"] > 0 and g["walk_overhead_ms"] >= 0 and g["allowed_mean"] > 100  # real vocab: big allowed sets
        if g["completed"]:
            assert g["output_valid"], g["validation_error"]
    # the same schema through the isolated spawn child (the child must load the pickle, not the tokenizer)
    res = runner.run_isolated(corpus.get("normal/flat_object/0001"),
                              _opts(config="default", timeout=60.0, mem_mb=4096, vocab_file=qwen_vocab_file, vocab_name="qwen2.5"))
    assert res["outcome"] == "admitted" and res["vocab"]["tokenizer"] == TOKENIZER_ID, res.get("reason")


# ------------------------------------------------------------------ external engines (optional)


@pytest.mark.parametrize("engine", ["xgrammar", "llguidance"])
def test_external_engine_compiles_a_normal_schema(engine):
    pytest.importorskip(engine)
    r = worker.run_in_process(corpus.get("normal/mixed_realistic/0000"), {"engine": engine, "config": "default",
                                                                          "seed": corpus.SEED, "token_cap": 32, "timeout": 5.0})
    assert r["outcome"] == "admitted", r.get("reason")
    assert r["compile_ms"] >= 0 and r["schema_to_grammar_ms"] >= 0
