# GrammarGuard adversarial-schema benchmark — results

Generated 2026-09-12T22:43:28 by `benchmarks/grammar_guard/report.py` from `grammar_guard/results`.

Corpus: **1078 schemas** (610 normal, 468 adversarial), deterministic seed; see `README.md` for the families and what `expect` means.

Environment: python 3.11.10, platform macOS-26.6.2-arm64-arm-64bit, kbnf 0.5.7, formatron 0.5.0, xgrammar 0.2.6, llguidance 1.8.0, jsonschema 4.26.0.

Isolation: one fresh `spawn` child per schema, 10 s wall-clock kill, RSS watchdog (3–4 GB), 6 parallel workers; synthetic ~3k-token vocabulary; random walk capped at 512 tokens.

The sections up to *Worst cases* use the **synthetic vocabulary** (`hardened.jsonl`, `default.jsonl`, `xgrammar.jsonl`, `llguidance.jsonl`). [Real vocabulary (Qwen2.5, 151k tokens)](#real-vocabulary-qwen25-151k-tokens) re-runs the kbnf configs on `Qwen/Qwen2.5-0.5B-Instruct`.

## Headline numbers

| config | n | admitted | rejected | timeout | crash/oom | valid / completed walks | compile p50 | p99 | max | admitted & > 1 s | normal/admit rejected | expect=reject admitted | expect=reject hung/crashed |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened | 1078 | 75% | 25% | 0% | 0% | 761/763 (100%) | 7.13 | 78 | 449 | 0 | 0 | 2 | 0 |
| kbnf-default | 1078 | 88% | 5% | 4% | 3% | 839/844 (99%) | 8.33 | 3.9 s | 8.9 s | 52 | 0 | 34 | 73 |
| xgrammar | 1078 | 95% | 1% | 5% | 0% | – | 2.06 | 3.6 s | 7.5 s | 36 | 0 | 87 | 50 |
| llguidance | 1078 | 94% | 5% | 0% | 0% | – | 0.72 | 192 | 1.0 s | 1 | 0 | 94 | 4 |

*compile* = admission (hardened only) + schema→grammar + engine construction for admitted schemas; for xgrammar/llguidance it is schema→grammar + compile. *valid / completed* counts random walks that finished within the token cap and whose output passed `jsonschema` validation against the original schema. *admitted & > 1 s*: admitted schemas whose compile exceeded 1 s. *normal/admit rejected*: false positives.


## Per family × configuration

### kbnf-hardened

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 80/80 (100%) | 8.07 | 14 | 14 | 0.02 | 0.18 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 66/66 (100%) | 7.75 | 72 | 72 | 0.01 | 0.15 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 8.58 | 15 | 15 | 0.01 | 0.17 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 6.55 | 9.25 | 9.26 | 0.01 | 0.49 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 13 | 33 | 34 | 0.02 | 4.05 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 60/60 (100%) | 9.02 | 16 | 16 | 0.02 | 0.31 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 7.12 | 15 | 16 | 0.02 | 0.29 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 5.90 | 7.11 | 7.15 | 0.01 | 0.07 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 10/10 (100%) | 5.34 | 5.80 | 5.80 | 0.02 | 0.05 |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 8.11 | 15 | 16 | 0.03 | 0.17 |
| patterns | 50 | 100% | 0% | 0% | 0% | 47/47 (100%) | 5.48 | 6.45 | 6.60 | 0.01 | 0.10 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 8.39 | 12 | 13 | 0.01 | 0.14 |
| recursion | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 6.35 | 8.18 | 8.19 | 0.01 | 0.12 |
| tuples | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 5.75 | 8.57 | 8.71 | 0.02 | 0.24 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 9/9 (100%) | 9.55 | 10 | 10 | 0.01 | 0.13 |
| deep_nesting *(adv)* | 44 | 2% | 98% | 0% | 0% | 1/1 (100%) | 16 | 16 | 16 | 0.03 | 0.05 |
| wide_enum *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| giant_const *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| huge_items *(adv)* | 48 | 10% | 90% | 0% | 0% | 4/4 (100%) | 7.88 | 12 | 12 | 0.02 | 0.05 |
| huge_string_length *(adv)* | 40 | 12% | 88% | 0% | 0% | 5/5 (100%) | 43 | 49 | 49 | 0.02 | 0.12 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 23/23 (100%) | 4.98 | 8.26 | 8.28 | 0.01 | 0.12 |
| regex_counted_repetition *(adv)* | 32 | 38% | 62% | 0% | 0% | 7/7 (100%) | 7.81 | 445 | 449 | 0.01 | 0.06 |
| regex_alternation_blowup *(adv)* | 30 | 43% | 57% | 0% | 0% | 8/10 (80%) | 5.47 | 248 | 278 | 0.01 | 0.15 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 11 | 20 | 21 | 0.06 | 0.80 |
| thousands_of_props *(adv)* | 24 | 8% | 92% | 0% | 0% | 0/0 | 315 | 417 | 420 | 0.01 | 0.04 |
| recursive_ref_fanout *(adv)* | 24 | 83% | 17% | 0% | 0% | 6/6 (100%) | 19 | 105 | 110 | 0.00 | 0.04 |
| unicode_heavy *(adv)* | 20 | 80% | 20% | 0% | 0% | 11/11 (100%) | 13 | 88 | 90 | 0.02 | 4.88 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 4.67 | 5.53 | 5.66 | 0.02 | 0.07 |
| mixed_combo *(adv)* | 30 | 40% | 60% | 0% | 0% | 11/11 (100%) | 8.88 | 26 | 28 | 0.01 | 1.63 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 15/15 (100%) | 4.80 | 5.19 | 5.20 | 0.01 | 0.06 |

### kbnf-default

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 80/80 (100%) | 8.63 | 31 | 32 | 0.00 | 0.11 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 66/66 (100%) | 7.02 | 91 | 106 | 0.00 | 0.10 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 8.32 | 24 | 25 | 0.00 | 0.10 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 5.99 | 15 | 15 | 0.00 | 0.04 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 27 | 95 | 98 | 0.00 | 0.28 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 60/60 (100%) | 11 | 35 | 36 | 0.00 | 0.11 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 6.97 | 25 | 27 | 0.00 | 0.13 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 4.22 | 5.12 | 5.13 | 0.00 | 0.03 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 10/10 (100%) | 3.79 | 4.04 | 4.05 | 0.00 | 0.02 |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 19 | 45 | 48 | 0.01 | 0.11 |
| patterns | 50 | 100% | 0% | 0% | 0% | 47/47 (100%) | 4.23 | 6.07 | 6.12 | 0.00 | 0.06 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 8.82 | 14 | 15 | 0.00 | 0.09 |
| recursion | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 5.46 | 15 | 15 | 0.00 | 0.08 |
| tuples | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 4.26 | 17 | 18 | 0.00 | 0.11 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 9/9 (100%) | 16 | 21 | 21 | 0.00 | 0.09 |
| deep_nesting *(adv)* | 44 | 11% | 89% | 0% | 0% | 5/5 (100%) | 9.81 | 19 | 20 | 0.01 | 0.03 |
| wide_enum *(adv)* | 30 | 63% | 0% | 3% | 33% | 19/19 (100%) | 1.2 s | 5.1 s | 5.1 s | 0.01 | 14 |
| giant_const *(adv)* | 30 | 33% | 0% | 53% | 13% | 0/0 | 1.7 s | 3.1 s | 3.1 s | 0.00 | 0.01 |
| huge_items *(adv)* | 48 | 52% | 17% | 17% | 15% | 18/18 (100%) | 31 | 539 | 550 | 0.00 | 0.05 |
| huge_string_length *(adv)* | 40 | 48% | 0% | 25% | 28% | 14/14 (100%) | 869 | 7.9 s | 8.9 s | 0.00 | 0.11 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 23/23 (100%) | 3.62 | 8.72 | 8.93 | 0.00 | 0.08 |
| regex_counted_repetition *(adv)* | 32 | 75% | 6% | 19% | 0% | 14/16 (88%) | 74 | 4.3 s | 4.4 s | 0.00 | 0.03 |
| regex_alternation_blowup *(adv)* | 30 | 93% | 0% | 3% | 3% | 19/22 (86%) | 55 | 5.2 s | 5.4 s | 0.00 | 0.10 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 9.67 | 19 | 19 | 0.02 | 0.09 |
| thousands_of_props *(adv)* | 24 | 96% | 0% | 4% | 0% | 0/0 | 1.3 s | 7.0 s | 7.2 s | 0.00 | 0.03 |
| recursive_ref_fanout *(adv)* | 24 | 100% | 0% | 0% | 0% | 6/6 (100%) | 14 | 114 | 118 | 0.00 | 0.03 |
| unicode_heavy *(adv)* | 20 | 100% | 0% | 0% | 0% | 13/13 (100%) | 44 | 1.7 s | 1.8 s | 0.01 | 4.80 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 3.22 | 3.49 | 3.49 | 0.00 | 0.03 |
| mixed_combo *(adv)* | 30 | 90% | 10% | 0% | 0% | 23/23 (100%) | 15 | 1.5 s | 1.8 s | 0.00 | 2.25 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 15/15 (100%) | 3.54 | 3.89 | 3.90 | 0.00 | 0.03 |

### xgrammar

| family | n | admitted | rejected | timeout | crash/oom | compile p50 | p99 | max |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 3.18 | 39 | 40 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 2.02 | 89 | 121 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 2.32 | 23 | 24 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 0.71 | 1.30 | 1.30 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 1.29 | 4.13 | 4.26 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 7.24 | 42 | 44 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 1.76 | 30 | 31 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 1.17 | 1.91 | 1.92 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 0.96 | 1.01 | 1.01 |
| string_length | 40 | 100% | 0% | 0% | 0% | 22 | 71 | 75 |
| patterns | 50 | 100% | 0% | 0% | 0% | 1.11 | 6.02 | 6.21 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 2.60 | 8.89 | 9.00 |
| recursion | 30 | 100% | 0% | 0% | 0% | 0.99 | 14 | 14 |
| tuples | 20 | 100% | 0% | 0% | 0% | 1.21 | 18 | 19 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 16 | 26 | 26 |
| deep_nesting *(adv)* | 44 | 50% | 0% | 45% | 5% | 543 | 6.1 s | 6.3 s |
| wide_enum *(adv)* | 30 | 87% | 0% | 13% | 0% | 261 | 7.4 s | 7.5 s |
| giant_const *(adv)* | 30 | 33% | 0% | 67% | 0% | 615 | 1.4 s | 1.4 s |
| huge_items *(adv)* | 48 | 100% | 0% | 0% | 0% | 0.85 | 254 | 256 |
| huge_string_length *(adv)* | 40 | 100% | 0% | 0% | 0% | 59 | 63 | 64 |
| regex_nested_quantifiers *(adv)* | 30 | 100% | 0% | 0% | 0% | 0.66 | 1.46 | 1.48 |
| regex_counted_repetition *(adv)* | 32 | 91% | 6% | 3% | 0% | 87 | 4.2 s | 4.9 s |
| regex_alternation_blowup *(adv)* | 30 | 83% | 17% | 0% | 0% | 48 | 5.5 s | 6.8 s |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 3.20 | 8.86 | 9.44 |
| thousands_of_props *(adv)* | 24 | 79% | 0% | 21% | 0% | 684 | 4.3 s | 4.5 s |
| recursive_ref_fanout *(adv)* | 24 | 100% | 0% | 0% | 0% | 2.38 | 15 | 16 |
| unicode_heavy *(adv)* | 20 | 100% | 0% | 0% | 0% | 3.65 | 1.5 s | 1.7 s |
| hostile_literals *(adv)* | 40 | 100% | 0% | 0% | 0% | 0.36 | 0.48 | 0.49 |
| mixed_combo *(adv)* | 30 | 100% | 0% | 0% | 0% | 4.20 | 3.0 s | 3.7 s |
| grammar_injection *(adv)* | 16 | 100% | 0% | 0% | 0% | 0.40 | 0.67 | 0.68 |

### llguidance

| family | n | admitted | rejected | timeout | crash/oom | compile p50 | p99 | max |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 0.72 | 3.08 | 3.08 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 0.80 | 4.94 | 5.56 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 0.81 | 1.20 | 1.22 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 0.68 | 1.01 | 1.06 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 1.09 | 1.81 | 1.85 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 0.77 | 1.33 | 1.79 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 0.68 | 0.94 | 0.94 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 0.68 | 0.82 | 0.83 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 0.62 | 0.74 | 0.74 |
| string_length | 40 | 100% | 0% | 0% | 0% | 0.60 | 0.75 | 0.76 |
| patterns | 50 | 100% | 0% | 0% | 0% | 0.67 | 1.00 | 1.20 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 0.81 | 1.15 | 1.17 |
| recursion | 30 | 100% | 0% | 0% | 0% | 0.62 | 0.83 | 0.83 |
| tuples | 20 | 100% | 0% | 0% | 0% | 0.49 | 0.72 | 0.73 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 0.75 | 0.93 | 0.93 |
| deep_nesting *(adv)* | 44 | 9% | 91% | 0% | 0% | 1.10 | 1.26 | 1.26 |
| wide_enum *(adv)* | 30 | 83% | 17% | 0% | 0% | 26 | 148 | 149 |
| giant_const *(adv)* | 30 | 100% | 0% | 0% | 0% | 19 | 148 | 149 |
| huge_items *(adv)* | 48 | 75% | 17% | 0% | 8% | 6.65 | 731 | 1.0 s |
| huge_string_length *(adv)* | 40 | 100% | 0% | 0% | 0% | 0.59 | 0.66 | 0.66 |
| regex_nested_quantifiers *(adv)* | 30 | 100% | 0% | 0% | 0% | 0.62 | 0.74 | 0.75 |
| regex_counted_repetition *(adv)* | 32 | 100% | 0% | 0% | 0% | 0.62 | 3.82 | 4.39 |
| regex_alternation_blowup *(adv)* | 30 | 100% | 0% | 0% | 0% | 1.26 | 194 | 241 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 0.91 | 1.53 | 1.57 |
| thousands_of_props *(adv)* | 24 | 83% | 17% | 0% | 0% | 104 | 764 | 766 |
| recursive_ref_fanout *(adv)* | 24 | 100% | 0% | 0% | 0% | 1.03 | 1.99 | 1.99 |
| unicode_heavy *(adv)* | 20 | 100% | 0% | 0% | 0% | 1.16 | 188 | 226 |
| hostile_literals *(adv)* | 40 | 100% | 0% | 0% | 0% | 0.55 | 0.67 | 0.68 |
| mixed_combo *(adv)* | 30 | 97% | 3% | 0% | 0% | 1.51 | 46 | 48 |
| grammar_injection *(adv)* | 16 | 100% | 0% | 0% | 0% | 0.62 | 0.69 | 0.69 |

Per-token *mask* latency is `Formatter.compute_allowed_tokens()` over the synthetic ~3k-token vocabulary (p50 of per-schema p50s, p99 of per-schema p99s); it is only meaningful relative to other rows.

## Differential: kbnf-hardened vs kbnf-default vs xgrammar vs llguidance

| engine · subset | n | accept | reject | timeout | crash/oom | compile p50 | p99 | max | time-to-reject p50 | max |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened · all | 1078 | 75% | 25% | 0% | 0% | 7.13 | 78 | 449 | 0.08 | 1.3 s |
| kbnf-hardened · normal | 610 | 100% | 0% | 0% | 0% | 7.16 | 28 | 72 | – | – |
| kbnf-hardened · adversarial | 468 | 42% | 58% | 0% | 0% | 6.30 | 410 | 449 | 0.08 | 1.3 s |
| kbnf-default · all | 1078 | 88% | 5% | 4% | 3% | 8.33 | 3.9 s | 8.9 s | 1.94 | 5.0 s |
| kbnf-default · normal | 610 | 100% | 0% | 0% | 0% | 6.78 | 55 | 106 | – | – |
| kbnf-default · adversarial | 468 | 71% | 12% | 9% | 7% | 15 | 5.9 s | 8.9 s | 1.94 | 5.0 s |
| xgrammar · all | 1078 | 95% | 1% | 5% | 0% | 2.06 | 3.6 s | 7.5 s | 0.67 | 1.59 |
| xgrammar · normal | 610 | 100% | 0% | 0% | 0% | 1.77 | 54 | 121 | – | – |
| xgrammar · adversarial | 468 | 87% | 1% | 11% | 0% | 4.22 | 5.6 s | 7.5 s | 0.67 | 1.59 |
| llguidance · all | 1078 | 94% | 5% | 0% | 0% | 0.72 | 192 | 1.0 s | 1.22 | 1.7 s |
| llguidance · normal | 610 | 100% | 0% | 0% | 0% | 0.71 | 3.01 | 5.56 | – | – |
| llguidance · adversarial | 468 | 87% | 12% | 0% | 1% | 0.82 | 241 | 1.0 s | 1.22 | 1.7 s |

### Accept rate per family (timeout+crash rate in parentheses)

| family | kbnf-hardened accept (t/o+crash) | kbnf-default accept (t/o+crash) | xgrammar accept (t/o+crash) | llguidance accept (t/o+crash) |
|:---|---:|---:|---:|---:|
| flat_object | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| nested_object | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| array_of_objects | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| enum_fields | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| enum_medium | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| optional_fields | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| anyof_union | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| numeric_bounds | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| numeric_bounds_nonzero | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| string_length | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| patterns | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| refs_defs | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| recursion | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| tuples | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| mixed_realistic | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| deep_nesting *(adv)* | 2% (0%) | 11% (0%) | 50% (50%) | 9% (0%) |
| wide_enum *(adv)* | 0% (0%) | 63% (37%) | 87% (13%) | 83% (0%) |
| giant_const *(adv)* | 0% (0%) | 33% (67%) | 33% (67%) | 100% (0%) |
| huge_items *(adv)* | 10% (0%) | 52% (31%) | 100% (0%) | 75% (8%) |
| huge_string_length *(adv)* | 12% (0%) | 48% (52%) | 100% (0%) | 100% (0%) |
| regex_nested_quantifiers *(adv)* | 90% (0%) | 90% (0%) | 100% (0%) | 100% (0%) |
| regex_counted_repetition *(adv)* | 38% (0%) | 75% (19%) | 91% (3%) | 100% (0%) |
| regex_alternation_blowup *(adv)* | 43% (0%) | 93% (7%) | 83% (0%) | 100% (0%) |
| many_optional_props *(adv)* | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| thousands_of_props *(adv)* | 8% (0%) | 96% (4%) | 79% (21%) | 83% (0%) |
| recursive_ref_fanout *(adv)* | 83% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| unicode_heavy *(adv)* | 80% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| hostile_literals *(adv)* | 95% (0%) | 95% (0%) | 100% (0%) | 100% (0%) |
| mixed_combo *(adv)* | 40% (0%) | 90% (0%) | 100% (0%) | 97% (0%) |
| grammar_injection *(adv)* | 94% (0%) | 94% (0%) | 100% (0%) | 100% (0%) |

### Resource attacks (`expect: reject`)

| engine | expect=reject n | admitted | rejected | timeout | crash/oom | admitted compile max |
|:---|---:|---:|---:|---:|---:|---:|
| kbnf-hardened | 139 | 2 | 137 | 0 | 0 | 449 |
| kbnf-default | 139 | 34 | 32 | 40 | 33 | 8.9 s |
| xgrammar | 139 | 87 | 2 | 48 | 2 | 7.5 s |
| llguidance | 139 | 94 | 41 | 0 | 4 | 1.0 s |


## Interesting individual cases

### Hardened policy: hangs, crashes, OOMs (should be empty)

- none

### Hardened policy: admitted but compile > 1 s

- none

### kbnf-hardened: admitted, walk completed, output failed validation

- **error** × 1 — families: regex_alternation_blowup (1). Example `adv/regex_alternation_blowup/0025`: `error: bad escape \p at position 1` → `{⏎  "s":"Voiceabab}" }⏎`
- **json** × 1 — families: regex_alternation_blowup (1). Example `adv/regex_alternation_blowup/0026`: `json: Expecting ',' delimiter: line 2 column 15 (char 16)` → `{⏎  "s": "small"color":deadbeef"new1]are""groups":options"error":32Bird"index":storymanywa`

### kbnf-default: admitted, walk completed, output failed validation

- **error** × 3 — families: regex_counted_repetition (2), regex_alternation_blowup (1). Example `adv/regex_counted_repetition/0009`: `error: bad escape \p at position 0` → `⏎    {"s0":"sentenceThreecountryPowercustomerenabledpaintactKnowWhiteMoreoffsetkeyTurnfrie`
- **json** × 2 — families: regex_alternation_blowup (2). Example `adv/regex_alternation_blowup/0026`: `json: Expecting ',' delimiter: line 2 column 15 (char 16)` → `{⏎  "s": "small"color":deadbeef"new1]are""groups":options"error":32Bird"index":storymanywa`

### Generation aborted (dead end / decode limit / capture error)

- none

### Hardened policy: normal schemas rejected (false positives, by resource)

- none

### Default (unlimited) configuration: hangs, crashes, OOMs by family

- **huge_string_length**: {'oom': 11, 'timeout': 10} — e.g. `adv/huge_string_length/0003` oom during `compile` (peak RSS 3090 MB)
- **giant_const**: {'timeout': 16, 'oom': 4} — e.g. `adv/giant_const/0002` timeout during `compile` (peak RSS 1453 MB)
- **huge_items**: {'oom': 7, 'timeout': 8} — e.g. `adv/huge_items/0010` oom during `grammar_gen` (peak RSS 3386 MB)
- **wide_enum**: {'crash': 10, 'timeout': 1} — e.g. `adv/wide_enum/0004` crash during `compile` (peak RSS 213 MB)
- **regex_counted_repetition**: {'timeout': 6} — e.g. `adv/regex_counted_repetition/0001` timeout during `compile` (peak RSS 1404 MB)
- **regex_alternation_blowup**: {'oom': 1, 'timeout': 1} — e.g. `adv/regex_alternation_blowup/0029` oom during `compile` (peak RSS 3245 MB)
- **thousands_of_props**: {'timeout': 1} — e.g. `adv/thousands_of_props/0011` timeout during `compile` (peak RSS 1405 MB)

#### Default configuration: crashes (signals) in detail

- `adv/wide_enum/0004` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0005` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0010` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0011` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0016` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0017` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0022` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0023` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0028` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0029` — child_died: child exited with code -11 during phase compile without a result

### kbnf-hardened admits, an external engine rejects / hangs / crashes

- `adv/regex_alternation_blowup/0025` — hardened **admitted** (33); xgrammar rejected (unsupported_schema: [12:18:20] /Users/runner/work/xgrammar/xgrammar/cpp/regex_co); llguidance admitted (–)
- `adv/regex_alternation_blowup/0026` — hardened **admitted** (278); xgrammar rejected (unsupported_schema: [12:18:20] /Users/runner/work/xgrammar/xgrammar/cpp/regex_co); llguidance admitted (–)

### Normal schemas kbnf-hardened rejects but an external engine admits

- none

### xgrammar: hangs / crashes

- `adv/deep_nesting/0005` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 355 MB)
- `adv/deep_nesting/0006` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 482 MB)
- `adv/deep_nesting/0007` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 661 MB)
- `adv/deep_nesting/0008` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 894 MB)
- `adv/deep_nesting/0009` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 1701 MB)
- `adv/deep_nesting/0010` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 2832 MB)
- `adv/deep_nesting/0018` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 339 MB)
- `adv/deep_nesting/0019` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 388 MB)
- `adv/deep_nesting/0020` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 560 MB)
- `adv/deep_nesting/0021` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 803 MB)
- `adv/deep_nesting/0028` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 374 MB)
- `adv/deep_nesting/0029` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 472 MB)
- `adv/deep_nesting/0030` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 594 MB)
- `adv/deep_nesting/0031` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 1029 MB)
- `adv/deep_nesting/0032` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 1634 MB)
- `adv/deep_nesting/0037` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 394 MB)
- `adv/deep_nesting/0038` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 507 MB)
- `adv/deep_nesting/0039` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 829 MB)
- `adv/deep_nesting/0040` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 1283 MB)
- `adv/deep_nesting/0041` — **timeout** during `schema_to_grammar` (wall 10.0 s, peak RSS 1864 MB)
- `adv/deep_nesting/0042` — **oom** during `schema_to_grammar` (wall 3.1 s, peak RSS 3250 MB)
- `adv/deep_nesting/0043` — **oom** during `schema_to_grammar` (wall 3.3 s, peak RSS 3506 MB)
- `adv/giant_const/0002` — **timeout** during `compile` (wall 10.0 s, peak RSS 536 MB)
- `adv/giant_const/0003` — **timeout** during `compile` (wall 10.0 s, peak RSS 578 MB)
- `adv/giant_const/0004` — **timeout** during `compile` (wall 10.0 s, peak RSS 845 MB)
- `adv/giant_const/0005` — **timeout** during `compile` (wall 10.0 s, peak RSS 1385 MB)
- `adv/giant_const/0008` — **timeout** during `compile` (wall 10.0 s, peak RSS 566 MB)
- `adv/giant_const/0009` — **timeout** during `compile` (wall 10.0 s, peak RSS 591 MB)
- `adv/giant_const/0010` — **timeout** during `compile` (wall 10.0 s, peak RSS 819 MB)
- `adv/giant_const/0011` — **timeout** during `compile` (wall 10.0 s, peak RSS 1545 MB)
- … 22 more

#### xgrammar: admitted but compile > 1 s

- `adv/wide_enum/0005` — compile 7.5 s (grammar 1,690,329 B)
- `adv/wide_enum/0009` — compile 7.1 s (grammar 1,001,439 B)
- `adv/regex_alternation_blowup/0013` — compile 6.8 s (grammar 1,531 B)
- `adv/deep_nesting/0017` — compile 6.3 s (grammar 9,968,247 B)
- `adv/deep_nesting/0036` — compile 5.7 s (grammar 1,141,538 B)
- `adv/regex_counted_repetition/0000` — compile 4.9 s (grammar 1,521 B)
- `adv/deep_nesting/0027` — compile 4.6 s (grammar 2,569,423 B)
- `adv/thousands_of_props/0009` — compile 4.5 s (grammar 769,088 B)

#### xgrammar: rejection reasons

- **unsupported_schema** × 7 — e.g. `adv/regex_counted_repetition/0009`: [12:18:00] /Users/runner/work/xgrammar/xgrammar/cpp/regex_converter.cc:83: Regex parsing error at position 1: Unicode ch

### llguidance: hangs / crashes

- `adv/huge_items/0010` — **oom** during `compile` (wall 775, peak RSS 4196 MB)
- `adv/huge_items/0011` — **oom** during `compile` (wall 750, peak RSS 4078 MB)
- `adv/huge_items/0016` — **oom** during `compile` (wall 774, peak RSS 4205 MB)
- `adv/huge_items/0043` — **oom** during `compile` (wall 699, peak RSS 3747 MB)

#### llguidance: admitted but compile > 1 s

- `adv/huge_items/0047` — compile 1.0 s (grammar 354 B)

#### llguidance: rejection reasons

- **recursion_error** × 41 — e.g. `adv/deep_nesting/0001`: recursion limit exceeded at line 1 column 2576
- **engine_error** × 17 — e.g. `adv/wide_enum/0005`: initial lexer configuration (grammar) too big (limit for this grammar: 1000000)


## Worst cases per configuration (by end-to-end cost)

### kbnf-hardened

- `adv/regex_alternation_blowup/0028` — rejected 1.3 s, phase `admission`, peak RSS 722 MB
- `adv/huge_items/0027` — rejected 793, phase `admission`, peak RSS 1899 MB
- `adv/huge_items/0031` — rejected 781, phase `admission`, peak RSS 2755 MB
- `adv/regex_alternation_blowup/0027` — rejected 562, phase `admission`, peak RSS 325 MB
- `adv/regex_counted_repetition/0025` — rejected 508, phase `admission`, peak RSS 326 MB
- `adv/regex_counted_repetition/0009` — rejected 506, phase `admission`, peak RSS 313 MB
- `adv/regex_counted_repetition/0031` — admitted 449, phase `done`, peak RSS 343 MB
- `adv/thousands_of_props/0013` — admitted 420, phase `done`, peak RSS 218 MB

### kbnf-default

- `adv/giant_const/0021` — timeout 10.0 s, phase `compile`, peak RSS 1811 MB
- `adv/wide_enum/0009` — timeout 10.0 s, phase `compile`, peak RSS 1350 MB
- `adv/regex_counted_repetition/0017` — timeout 10.0 s, phase `compile`, peak RSS 1379 MB
- `adv/giant_const/0011` — timeout 10.0 s, phase `compile`, peak RSS 2906 MB
- `adv/regex_counted_repetition/0012` — timeout 10.0 s, phase `compile`, peak RSS 849 MB
- `adv/giant_const/0009` — timeout 10.0 s, phase `compile`, peak RSS 2415 MB
- `adv/huge_string_length/0016` — timeout 10.0 s, phase `compile`, peak RSS 1401 MB
- `adv/giant_const/0014` — timeout 10.0 s, phase `compile`, peak RSS 1327 MB

### xgrammar

- `adv/giant_const/0015` — timeout 10.0 s, phase `compile`, peak RSS 698 MB
- `adv/giant_const/0009` — timeout 10.0 s, phase `compile`, peak RSS 591 MB
- `adv/giant_const/0008` — timeout 10.0 s, phase `compile`, peak RSS 566 MB
- `adv/deep_nesting/0038` — timeout 10.0 s, phase `schema_to_grammar`, peak RSS 507 MB
- `adv/deep_nesting/0007` — timeout 10.0 s, phase `schema_to_grammar`, peak RSS 661 MB
- `adv/wide_enum/0010` — timeout 10.0 s, phase `compile`, peak RSS 678 MB
- `adv/wide_enum/0011` — timeout 10.0 s, phase `compile`, peak RSS 985 MB
- `adv/giant_const/0022` — timeout 10.0 s, phase `compile`, peak RSS 1110 MB

### llguidance

- `adv/huge_items/0039` — rejected 1.7 s, phase `done`, peak RSS 2161 MB
- `adv/huge_items/0047` — admitted 1.0 s, phase `done`, peak RSS 2171 MB
- `adv/huge_items/0009` — rejected 818, phase `done`, peak RSS 1069 MB
- `adv/huge_items/0008` — rejected 815, phase `done`, peak RSS 1068 MB
- `adv/huge_items/0023` — rejected 791, phase `done`, peak RSS 1003 MB
- `adv/huge_items/0021` — rejected 787, phase `done`, peak RSS 1052 MB
- `adv/huge_items/0010` — oom 775, phase `compile`, peak RSS 4196 MB
- `adv/huge_items/0016` — oom 774, phase `compile`, peak RSS 4205 MB


## Real vocabulary (Qwen2.5, 151k tokens)

kbnf + Formatron on the **real `Qwen/Qwen2.5-0.5B-Instruct` vocabulary** (151,665 tokens; built with `formatron.integrations.transformers.create_engine_vocabulary`, byte-level BPE unmangled, pickled once in the parent and reconstructed in every child) instead of the synthetic ~3k-token one. Same corpus (1078 schemas), same seed, same random walk — only the vocabulary changed. Files: `results/hardened-qwen2.5.jsonl`, `results/default-qwen2.5.jsonl`.

Isolation: one fresh `spawn` child per schema, 20.0 s wall-clock kill, RSS watchdog (4096 MB), 4 parallel workers; random walk capped at 512 tokens.

### Headline numbers

| config | n | admitted | rejected | timeout | crash/oom | valid / completed walks | compile p50 | p99 | max | admitted & > 1 s | normal/admit rejected | expect=reject admitted | expect=reject hung/crashed |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened | 1078 | 75% | 25% | 0% | 0% | 704/707 (100%) | 20 | 92 | 465 | 0 | 0 | 2 | 0 |
| kbnf-default | 1078 | 78% | 6% | 13% | 3% | 724/728 (99%) | 351 | 13.8 s | 18.7 s | 182 | 0 | 6 | 99 |

*compile* = admission (hardened only) + schema→grammar + engine construction for admitted schemas; for xgrammar/llguidance it is schema→grammar + compile. *valid / completed* counts random walks that finished within the token cap and whose output passed `jsonschema` validation against the original schema. *admitted & > 1 s*: admitted schemas whose compile exceeded 1 s. *normal/admit rejected*: false positives.


### Per family × configuration

#### kbnf-hardened

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 76/76 (100%) | 20 | 24 | 25 | 0.00 | 9.78 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 50/50 (100%) | 21 | 79 | 79 | 0.00 | 6.25 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 43/43 (100%) | 21 | 29 | 30 | 0.03 | 6.72 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 19 | 23 | 25 | 0.75 | 49 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 25 | 44 | 45 | 0.81 | 508 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 59/59 (100%) | 21 | 26 | 27 | 0.03 | 19 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 39/39 (100%) | 20 | 24 | 25 | 0.00 | 5.83 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 18 | 21 | 21 | 0.76 | 2.73 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 10/10 (100%) | 19 | 20 | 20 | 0.79 | 2.62 |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 21 | 29 | 30 | 0.88 | 3.39 |
| patterns | 50 | 100% | 0% | 0% | 0% | 36/36 (100%) | 18 | 22 | 22 | 0.00 | 2.52 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 36/36 (100%) | 22 | 27 | 27 | 0.36 | 3.45 |
| recursion | 30 | 100% | 0% | 0% | 0% | 28/28 (100%) | 20 | 23 | 23 | 0.05 | 3.03 |
| tuples | 20 | 100% | 0% | 0% | 0% | 19/19 (100%) | 20 | 24 | 24 | 0.00 | 4.08 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 8/8 (100%) | 22 | 24 | 24 | 0.39 | 3.79 |
| deep_nesting *(adv)* | 44 | 2% | 98% | 0% | 0% | 1/1 (100%) | 27 | 27 | 27 | 0.06 | 2.91 |
| wide_enum *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| giant_const *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| huge_items *(adv)* | 48 | 10% | 90% | 0% | 0% | 4/4 (100%) | 20 | 27 | 27 | 0.82 | 3.58 |
| huge_string_length *(adv)* | 40 | 12% | 88% | 0% | 0% | 4/4 (100%) | 53 | 60 | 60 | 2.47 | 2.92 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 20/21 (95%) | 18 | 22 | 23 | 0.75 | 2.55 |
| regex_counted_repetition *(adv)* | 32 | 38% | 62% | 0% | 0% | 5/5 (100%) | 20 | 461 | 465 | 0.84 | 2.24 |
| regex_alternation_blowup *(adv)* | 30 | 43% | 57% | 0% | 0% | 8/10 (80%) | 18 | 261 | 291 | 0.79 | 2.85 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 24 | 33 | 33 | 1.55 | 82 |
| thousands_of_props *(adv)* | 24 | 8% | 92% | 0% | 0% | 0/0 | 319 | 418 | 420 | 0.04 | 1.67 |
| recursive_ref_fanout *(adv)* | 24 | 83% | 17% | 0% | 0% | 3/3 (100%) | 33 | 117 | 123 | 0.01 | 2.67 |
| unicode_heavy *(adv)* | 20 | 80% | 20% | 0% | 0% | 12/12 (100%) | 26 | 97 | 97 | 0.74 | 550 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 17 | 19 | 19 | 0.80 | 4.94 |
| mixed_combo *(adv)* | 30 | 40% | 60% | 0% | 0% | 11/11 (100%) | 22 | 39 | 40 | 0.82 | 131 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 14/14 (100%) | 17 | 19 | 19 | 0.81 | 3.49 |

#### kbnf-default

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 76/76 (100%) | 402 | 2.0 s | 2.0 s | 0.00 | 0.34 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 50/50 (100%) | 359 | 7.2 s | 8.4 s | 0.00 | 0.27 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 43/43 (100%) | 445 | 1.6 s | 1.7 s | 0.01 | 0.22 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 290 | 918 | 923 | 0.01 | 0.23 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 2.0 s | 7.4 s | 7.7 s | 0.02 | 1.54 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 59/59 (100%) | 605 | 2.3 s | 2.3 s | 0.01 | 0.25 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 39/39 (100%) | 295 | 1.6 s | 1.7 s | 0.00 | 0.29 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 141 | 202 | 202 | 0.01 | 0.18 |
| numeric_bounds_nonzero | 10 | 100% | 0% | 0% | 0% | 10/10 (100%) | 114 | 126 | 126 | 0.01 | 0.12 |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 1.0 s | 3.1 s | 3.3 s | 0.03 | 0.33 |
| patterns | 50 | 100% | 0% | 0% | 0% | 36/36 (100%) | 137 | 207 | 208 | 0.00 | 0.09 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 36/36 (100%) | 403 | 1.0 s | 1.1 s | 0.01 | 0.28 |
| recursion | 30 | 100% | 0% | 0% | 0% | 28/28 (100%) | 181 | 688 | 691 | 0.01 | 0.27 |
| tuples | 20 | 100% | 0% | 0% | 0% | 19/19 (100%) | 190 | 1.3 s | 1.3 s | 0.00 | 0.22 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 8/8 (100%) | 1.0 s | 1.8 s | 1.9 s | 0.01 | 0.23 |
| deep_nesting *(adv)* | 44 | 11% | 89% | 0% | 0% | 4/4 (100%) | 703 | 1.4 s | 1.4 s | 0.01 | 0.15 |
| wide_enum *(adv)* | 30 | 3% | 0% | 67% | 30% | 1/1 (100%) | 17.5 s | 17.5 s | 17.5 s | 0.02 | 5.09 |
| giant_const *(adv)* | 30 | 0% | 0% | 80% | 20% | 0/0 | – | – | – | – | – |
| huge_items *(adv)* | 48 | 19% | 21% | 48% | 12% | 6/6 (100%) | 5.5 s | 15.7 s | 16.0 s | 0.01 | 0.13 |
| huge_string_length *(adv)* | 40 | 10% | 0% | 60% | 30% | 3/3 (100%) | 12.6 s | 14.4 s | 14.4 s | 0.06 | 0.25 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 18/21 (86%) | 101 | 360 | 368 | 0.01 | 0.11 |
| regex_counted_repetition *(adv)* | 32 | 50% | 6% | 44% | 0% | 11/11 (100%) | 1.9 s | 16.9 s | 18.1 s | 0.01 | 0.11 |
| regex_alternation_blowup *(adv)* | 30 | 67% | 0% | 27% | 7% | 15/16 (94%) | 707 | 17.2 s | 17.5 s | 0.01 | 0.22 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 829 | 2.6 s | 2.8 s | 0.08 | 0.30 |
| thousands_of_props *(adv)* | 24 | 25% | 0% | 75% | 0% | 0/0 | 4.8 s | 18.3 s | 18.7 s | 0.01 | 0.05 |
| recursive_ref_fanout *(adv)* | 24 | 100% | 0% | 0% | 0% | 3/3 (100%) | 516 | 2.4 s | 2.4 s | 0.01 | 0.07 |
| unicode_heavy *(adv)* | 20 | 75% | 0% | 25% | 0% | 11/11 (100%) | 1.0 s | 17.3 s | 18.4 s | 0.03 | 2.47 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 73 | 102 | 108 | 0.01 | 0.11 |
| mixed_combo *(adv)* | 30 | 70% | 10% | 20% | 0% | 16/16 (100%) | 1.4 s | 14.1 s | 14.4 s | 0.03 | 2.08 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 14/14 (100%) | 93 | 106 | 107 | 0.01 | 0.10 |

Per-token *mask* latency is `Formatter.compute_allowed_tokens()` over the real Qwen2.5 vocabulary (151k tokens) (p50 of per-schema p50s, p99 of per-schema p99s); it is only meaningful relative to other rows.

### Synthetic vs Qwen2.5 vocabulary

Paired on the schemas **admitted on both vocabularies** (same corpus ids, same seed). *compile* is the end-to-end cost (admission + schema→grammar + engine construction); *engine* is `FormatterBuilder.build` alone, i.e. `kbnf.Engine` construction, which is the only vocabulary-dependent part of compilation. *ratio* is the median of per-schema engine-construction ratios (real / synthetic).

#### Compile cost (ms unless noted; synthetic → real)

| config · subset | n paired | compile p50 | compile p99 | engine p50 | engine p99 | engine ratio (median) | admitted & > 1 s |
|:---|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened · all | 806 | 7.13 → 20 | 78 → 92 | 0.98 → 14 | 22 → 35 | ×13.7 | 0 → 0 |
| kbnf-hardened · normal | 610 | 7.16 → 20 | 28 → 41 | 0.98 → 14 | 7.24 → 20 | ×13.7 | 0 → 0 |
| kbnf-hardened · adversarial | 196 | 6.30 → 19 | 410 → 421 | 1.00 → 14 | 143 → 155 | ×13.1 | 0 → 0 |
| kbnf-default · all | 841 | 6.97 → 351 | 217 → 13.8 s | 3.93 → 348 | 170 → 13.7 s | ×72.0 | 3 → 182 |
| kbnf-default · normal | 610 | 6.78 → 330 | 55 → 4.2 s | 4.06 → 327 | 50 → 4.2 s | ×72.4 | 0 → 106 |
| kbnf-default · adversarial | 231 | 8.02 → 477 | 1.1 s → 17.9 s | 3.56 → 474 | 332 → 17.9 s | ×69.5 | 3 → 76 |

#### Per-token latency and walk outcome (synthetic → real)

| config · subset | n paired | mask p50 | mask p99 | accept p50 | allowed tokens (mean) | valid / completed walks | walk overhead p50 (real) |
|:---|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened · all | 806 | 0.01 → 0.73 | 2.21 → 263 | 0.00 → 0.00 | 52 → 379 | 761/763 → 704/707 | 9.01 |
| kbnf-hardened · normal | 610 | 0.01 → 0.71 | 2.11 → 261 | 0.00 → 0.00 | 71 → 17,012 | 602/602 → 554/554 | 46 |
| kbnf-hardened · adversarial | 196 | 0.02 → 0.79 | 2.62 → 235 | 0.00 → 0.00 | 10 → 236 | 159/161 → 150/153 | 1.01 |
| kbnf-default · all | 841 | 0.00 → 0.01 | 0.12 → 0.96 | 0.00 → 0.00 | 46 → 326 | 786/787 → 724/728 | 5.66 |
| kbnf-default · normal | 610 | 0.00 → 0.01 | 0.12 → 0.89 | 0.00 → 0.00 | 71 → 17,012 | 602/602 → 554/554 | 46 |
| kbnf-default · adversarial | 231 | 0.00 → 0.01 | 0.21 → 1.94 | 0.00 → 0.00 | 10 → 236 | 184/185 → 170/174 | 0.75 |

*mask* = `compute_allowed_tokens()`, *accept* = `accept_token()` (p50 of per-schema p50s, p99 of per-schema p99s). *walk overhead* is everything in the random walk that is not the engine (materialising the allowed-id list, biased sampling, chart probes) per schema; it is a harness cost, not an engine cost, and grows with the allowed set.

#### kbnf-hardened: per family (synthetic → real)

| family | n paired | compile p50 | compile p99 | engine ratio | mask p50 | mask p99 |
|:---|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 8.07 → 20 | 14 → 24 | ×10.9 | 0.02 → 0.00 | 0.18 → 9.78 |
| nested_object | 70 | 7.75 → 21 | 72 → 79 | ×13.5 | 0.01 → 0.00 | 0.15 → 6.25 |
| array_of_objects | 50 | 8.58 → 21 | 15 → 29 | ×12.1 | 0.01 → 0.03 | 0.17 → 6.72 |
| enum_fields | 50 | 6.55 → 19 | 9.25 → 23 | ×13.8 | 0.01 → 0.75 | 0.49 → 49 |
| enum_medium | 20 | 13 → 25 | 33 → 44 | ×4.4 | 0.02 → 0.81 | 4.05 → 508 |
| optional_fields | 60 | 9.02 → 21 | 16 → 26 | ×9.7 | 0.02 → 0.03 | 0.31 → 19 |
| anyof_union | 40 | 7.12 → 20 | 15 → 24 | ×13.5 | 0.02 → 0.00 | 0.29 → 5.83 |
| numeric_bounds | 40 | 5.90 → 18 | 7.11 → 21 | ×17.8 | 0.01 → 0.76 | 0.07 → 2.73 |
| numeric_bounds_nonzero | 10 | 5.34 → 19 | 5.80 → 20 | ×20.1 | 0.02 → 0.79 | 0.05 → 2.62 |
| string_length | 40 | 8.11 → 21 | 15 → 29 | ×6.4 | 0.03 → 0.88 | 0.17 → 3.39 |
| patterns | 50 | 5.48 → 18 | 6.45 → 22 | ×17.9 | 0.01 → 0.00 | 0.10 → 2.52 |
| refs_defs | 40 | 8.39 → 22 | 12 → 27 | ×12.4 | 0.01 → 0.36 | 0.14 → 3.45 |
| recursion | 30 | 6.35 → 20 | 8.18 → 23 | ×18.4 | 0.01 → 0.05 | 0.12 → 3.03 |
| tuples | 20 | 5.75 → 20 | 8.57 → 24 | ×21.2 | 0.02 → 0.00 | 0.24 → 4.08 |
| mixed_realistic | 10 | 9.55 → 22 | 10 → 24 | ×7.2 | 0.01 → 0.39 | 0.13 → 3.79 |
| deep_nesting *(adv)* | 1 | 16 → 27 | 16 → 27 | ×7.9 | 0.03 → 0.06 | 0.05 → 2.91 |
| huge_items *(adv)* | 5 | 7.88 → 20 | 12 → 27 | ×6.8 | 0.02 → 0.82 | 0.05 → 3.58 |
| huge_string_length *(adv)* | 5 | 43 → 53 | 49 → 60 | ×1.6 | 0.02 → 2.47 | 0.12 → 2.92 |
| regex_nested_quantifiers *(adv)* | 27 | 4.98 → 18 | 8.26 → 22 | ×21.5 | 0.01 → 0.75 | 0.12 → 2.55 |
| regex_counted_repetition *(adv)* | 12 | 7.81 → 20 | 445 → 461 | ×6.7 | 0.01 → 0.84 | 0.06 → 2.24 |
| regex_alternation_blowup *(adv)* | 13 | 5.47 → 18 | 248 → 261 | ×13.1 | 0.01 → 0.79 | 0.15 → 2.85 |
| many_optional_props *(adv)* | 30 | 11 → 24 | 20 → 33 | ×9.8 | 0.06 → 1.55 | 0.80 → 82 |
| thousands_of_props *(adv)* | 2 | 315 → 319 | 417 → 418 | ×1.8 | 0.01 → 0.04 | 0.04 → 1.67 |
| recursive_ref_fanout *(adv)* | 20 | 19 → 33 | 105 → 117 | ×7.5 | 0.00 → 0.01 | 0.04 → 2.67 |
| unicode_heavy *(adv)* | 16 | 13 → 26 | 88 → 97 | ×6.0 | 0.02 → 0.74 | 4.88 → 550 |
| hostile_literals *(adv)* | 38 | 4.67 → 17 | 5.53 → 19 | ×23.4 | 0.02 → 0.80 | 0.07 → 4.94 |
| mixed_combo *(adv)* | 12 | 8.88 → 22 | 26 → 39 | ×9.7 | 0.01 → 0.82 | 1.63 → 131 |
| grammar_injection *(adv)* | 15 | 4.80 → 17 | 5.19 → 19 | ×21.5 | 0.01 → 0.81 | 0.06 → 3.49 |

#### kbnf-default: per family (synthetic → real)

| family | n paired | compile p50 | compile p99 | engine ratio | mask p50 | mask p99 |
|:---|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 8.63 → 402 | 31 → 2.0 s | ×72.1 | 0.00 → 0.00 | 0.11 → 0.34 |
| nested_object | 70 | 7.02 → 359 | 91 → 7.2 s | ×80.7 | 0.00 → 0.00 | 0.10 → 0.27 |
| array_of_objects | 50 | 8.32 → 445 | 24 → 1.6 s | ×82.6 | 0.00 → 0.01 | 0.10 → 0.22 |
| enum_fields | 50 | 5.99 → 290 | 15 → 918 | ×70.9 | 0.00 → 0.01 | 0.04 → 0.23 |
| enum_medium | 20 | 27 → 2.0 s | 95 → 7.4 s | ×80.9 | 0.00 → 0.02 | 0.28 → 1.54 |
| optional_fields | 60 | 11 → 605 | 35 → 2.3 s | ×75.8 | 0.00 → 0.01 | 0.11 → 0.25 |
| anyof_union | 40 | 6.97 → 295 | 25 → 1.6 s | ×70.2 | 0.00 → 0.00 | 0.13 → 0.29 |
| numeric_bounds | 40 | 4.22 → 141 | 5.12 → 202 | ×68.4 | 0.00 → 0.01 | 0.03 → 0.18 |
| numeric_bounds_nonzero | 10 | 3.79 → 114 | 4.04 → 126 | ×64.2 | 0.00 → 0.01 | 0.02 → 0.12 |
| string_length | 40 | 19 → 1.0 s | 45 → 3.1 s | ×63.0 | 0.01 → 0.03 | 0.11 → 0.33 |
| patterns | 50 | 4.23 → 137 | 6.07 → 207 | ×60.0 | 0.00 → 0.00 | 0.06 → 0.09 |
| refs_defs | 40 | 8.82 → 403 | 14 → 1.0 s | ×73.8 | 0.00 → 0.01 | 0.09 → 0.28 |
| recursion | 30 | 5.46 → 181 | 15 → 688 | ×68.5 | 0.00 → 0.01 | 0.08 → 0.27 |
| tuples | 20 | 4.26 → 190 | 17 → 1.3 s | ×88.9 | 0.00 → 0.00 | 0.11 → 0.22 |
| mixed_realistic | 10 | 16 → 1.0 s | 21 → 1.8 s | ×78.4 | 0.00 → 0.01 | 0.09 → 0.23 |
| deep_nesting *(adv)* | 5 | 9.81 → 703 | 19 → 1.4 s | ×337.4 | 0.01 → 0.01 | 0.03 → 0.15 |
| wide_enum *(adv)* | 1 | 225 → 17.5 s | 225 → 17.5 s | ×80.8 | 0.00 → 0.02 | 0.27 → 5.09 |
| huge_items *(adv)* | 9 | 9.25 → 5.5 s | 26 → 15.7 s | ×514.2 | 0.00 → 0.01 | 0.03 → 0.13 |
| huge_string_length *(adv)* | 4 | 169 → 12.6 s | 177 → 14.4 s | ×75.5 | 0.00 → 0.06 | 0.08 → 0.25 |
| regex_nested_quantifiers *(adv)* | 27 | 3.62 → 101 | 8.72 → 360 | ×52.5 | 0.00 → 0.01 | 0.08 → 0.11 |
| regex_counted_repetition *(adv)* | 16 | 32 → 1.9 s | 2.2 s → 16.9 s | ×77.3 | 0.00 → 0.01 | 0.03 → 0.11 |
| regex_alternation_blowup *(adv)* | 20 | 16 → 707 | 207 → 17.2 s | ×65.4 | 0.00 → 0.01 | 0.07 → 0.22 |
| many_optional_props *(adv)* | 30 | 9.67 → 829 | 19 → 2.6 s | ×151.9 | 0.02 → 0.08 | 0.09 → 0.30 |
| thousands_of_props *(adv)* | 6 | 354 → 4.8 s | 1.2 s → 18.3 s | ×44.5 | 0.00 → 0.01 | 0.02 → 0.05 |
| recursive_ref_fanout *(adv)* | 24 | 14 → 516 | 114 → 2.4 s | ×72.5 | 0.00 → 0.01 | 0.03 → 0.07 |
| unicode_heavy *(adv)* | 15 | 16 → 1.0 s | 223 → 17.3 s | ×73.8 | 0.00 → 0.03 | 0.72 → 2.47 |
| hostile_literals *(adv)* | 38 | 3.22 → 73 | 3.49 → 102 | ×54.7 | 0.00 → 0.01 | 0.03 → 0.11 |
| mixed_combo *(adv)* | 21 | 11 → 1.4 s | 158 → 14.1 s | ×162.0 | 0.00 → 0.03 | 0.39 → 2.08 |
| grammar_injection *(adv)* | 15 | 3.54 → 93 | 3.89 → 106 | ×59.0 | 0.00 → 0.01 | 0.03 → 0.10 |

#### Outcome changes synthetic → real (same schema, same config)

A change here is either the vocabulary (engine construction now exceeds the timeout / memory cap, or a walk now completes) or a change in the generator between the two runs (the synthetic files are never re-run).

- kbnf-default: **admitted → timeout** × 103 — wide_enum (18), thousands_of_props (17), huge_items (16), huge_string_length (15), giant_const (10); e.g. `adv/wide_enum/0000` (phase `compile`)
- kbnf-default: **timeout → oom** × 4 — giant_const (2), huge_string_length (1), regex_alternation_blowup (1); e.g. `adv/giant_const/0005` (phase `compile`)
- kbnf-default: **crash → timeout** × 1 — wide_enum (1); e.g. `adv/wide_enum/0023` (phase `compile`)
- kbnf-default: **timeout → rejected** × 1 — huge_items (1); e.g. `adv/huge_items/0038` (unsupported_schema: The grammar and/or config's value range is not supported by the Engine.      Thi)
- kbnf-default: **oom → rejected** × 1 — huge_items (1); e.g. `adv/huge_items/0047` (unsupported_schema: The grammar and/or config's value range is not supported by the Engine.      Thi)


### Interesting individual cases

#### Hardened policy: hangs, crashes, OOMs (should be empty)

- none

#### kbnf-hardened: admitted but compile > 1 s

- none

#### kbnf-default: admitted but compile > 1 s

182 of 841 admitted schemas (22%); by family: nested_object (20), string_length (20), enum_medium (17), optional_fields (17), mixed_combo (13), flat_object (12), regex_counted_repetition (11), array_of_objects (9), regex_alternation_blowup (9), many_optional_props (8), unicode_heavy (8), huge_items (7), recursive_ref_fanout (7), mixed_realistic (6), thousands_of_props (6), huge_string_length (4), anyof_union (2), tuples (2), deep_nesting (2), refs_defs (1), wide_enum (1).

- `adv/thousands_of_props/0018` — compile 18.7 s (admission –, schema→grammar 89, **engine 18.6 s**; grammar 136,361 B, regexes 1011, mask p99 0.05 ms; synthetic: admitted, compile 234, engine 142)
- `adv/unicode_heavy/0014` — compile 18.4 s (admission –, schema→grammar 7.15, **engine 18.4 s**; grammar 28,833 B, regexes 1012, mask p99 2.76 ms; synthetic: admitted, compile 231, engine 226)
- `adv/regex_counted_repetition/0019` — compile 18.1 s (admission –, schema→grammar 2.38, **engine 18.1 s**; grammar 1,158 B, regexes 15, mask p99 0.07 ms; synthetic: admitted, compile 2.2 s, engine 2.2 s)
- `adv/regex_alternation_blowup/0014` — compile 17.5 s (admission –, schema→grammar 2.01, **engine 17.5 s**; grammar 860 B, regexes 13, mask p99 0.02 ms; synthetic: admitted, compile 198, engine 196)
- `adv/wide_enum/0012` — compile 17.5 s (admission –, schema→grammar 8.98, **engine 17.5 s**; grammar 31,723 B, regexes 2012, mask p99 5.09 ms; synthetic: admitted, compile 225, engine 216)
- `adv/huge_items/0041` — compile 16.0 s (admission –, schema→grammar 2.66, **engine 16.0 s**; grammar 250,843 B, regexes 13, mask p99 0.06 ms; synthetic: admitted, compile 27, engine 24)
- `adv/regex_alternation_blowup/0005` — compile 16.0 s (admission –, schema→grammar 2.86, **engine 16.0 s**; grammar 20,937 B, regexes 13, mask p99 0.05 ms; synthetic: admitted, compile 209, engine 205)
- `adv/huge_string_length/0026` — compile 14.4 s (admission –, schema→grammar 2.27, **engine 14.4 s**; grammar 1,493 B, regexes 16, mask p99 0.10 ms; synthetic: admitted, compile 93, engine 91)
- `adv/mixed_combo/0017` — compile 14.4 s (admission –, schema→grammar 51, **engine 14.4 s**; grammar 92,175 B, regexes 511, mask p99 2.37 ms; synthetic: admitted, compile 129, engine 77)
- `adv/mixed_combo/0024` — compile 12.8 s (admission –, schema→grammar 20, **engine 12.8 s**; grammar 36,375 B, regexes 1063, mask p99 0.25 ms; synthetic: admitted, compile 166, engine 148)
- `adv/huge_string_length/0000` — compile 12.6 s (admission –, schema→grammar 2.17, **engine 12.6 s**; grammar 904 B, regexes 13, mask p99 0.26 ms; synthetic: admitted, compile 167, engine 165)
- `adv/huge_string_length/0005` — compile 12.6 s (admission –, schema→grammar 2.03, **engine 12.6 s**; grammar 903 B, regexes 13, mask p99 0.10 ms; synthetic: admitted, compile 171, engine 169)
- `adv/huge_string_length/0034` — compile 12.4 s (admission –, schema→grammar 1.97, **engine 12.4 s**; grammar 907 B, regexes 13, mask p99 0.10 ms; synthetic: admitted, compile 177, engine 175)
- `adv/huge_items/0000` — compile 12.2 s (admission –, schema→grammar 2.23, **engine 12.2 s**; grammar 108,617 B, regexes 12, mask p99 0.13 ms; synthetic: admitted, compile 16, engine 14)
- `adv/huge_items/0012` — compile 11.2 s (admission –, schema→grammar 2.06, **engine 11.2 s**; grammar 32,919 B, regexes 12, mask p99 0.05 ms; synthetic: admitted, compile 9.25, engine 7.08)
- `adv/unicode_heavy/0017` — compile 10.7 s (admission –, schema→grammar 2.62, **engine 10.7 s**; grammar 14,857 B, regexes 13, mask p99 0.04 ms; synthetic: admitted, compile 173, engine 170)
- `adv/thousands_of_props/0016` — compile 10.5 s (admission –, schema→grammar 833, **engine 9.7 s**; grammar 1,492,475 B, regexes 531, mask p99 0.05 ms; synthetic: admitted, compile 1.3 s, engine 378)
- `adv/mixed_combo/0019` — compile 10.5 s (admission –, schema→grammar 2.24, **engine 10.5 s**; grammar 50,210 B, regexes 12, mask p99 0.16 ms; synthetic: admitted, compile 11, engine 9.10)
- `adv/regex_counted_repetition/0018` — compile 10.1 s (admission –, schema→grammar 2.28, **engine 10.1 s**; grammar 1,140 B, regexes 15, mask p99 0.05 ms; synthetic: admitted, compile 75, engine 73)
- `adv/regex_counted_repetition/0003` — compile 10.0 s (admission –, schema→grammar 2.05, **engine 10.0 s**; grammar 856 B, regexes 13, mask p99 0.06 ms; synthetic: admitted, compile 2.2 s, engine 2.2 s)
- `adv/regex_counted_repetition/0029` — compile 9.0 s (admission –, schema→grammar 2.51, **engine 9.0 s**; grammar 1,197 B, regexes 15, mask p99 0.04 ms; synthetic: admitted, compile 74, engine 72)
- `adv/mixed_combo/0010` — compile 8.5 s (admission –, schema→grammar 5.92, **engine 8.5 s**; grammar 43,232 B, regexes 11, mask p99 0.21 ms; synthetic: admitted, compile 12, engine 5.81)
- `normal/nested_object/0014` — compile 8.4 s (admission –, schema→grammar 23, **engine 8.4 s**; grammar 49,014 B, regexes 159, mask p99 0.07 ms; synthetic: admitted, compile 106, engine 81)
- `normal/enum_medium/0009` — compile 7.7 s (admission –, schema→grammar 5.91, **engine 7.7 s**; grammar 12,712 B, regexes 525, mask p99 1.57 ms; synthetic: admitted, compile 98, engine 94)
- `normal/nested_object/0029` — compile 6.7 s (admission –, schema→grammar 26, **engine 6.6 s**; grammar 57,247 B, regexes 166, mask p99 0.22 ms; synthetic: admitted, compile 84, engine 57)
- `adv/regex_alternation_blowup/0024` — compile 6.6 s (admission –, schema→grammar 1.98, **engine 6.6 s**; grammar 864 B, regexes 13, mask p99 0.03 ms; synthetic: admitted, compile 83, engine 81)
- `normal/enum_medium/0008` — compile 6.0 s (admission –, schema→grammar 5.44, **engine 6.0 s**; grammar 10,114 B, regexes 413, mask p99 1.40 ms; synthetic: admitted, compile 78, engine 74)
- `adv/regex_counted_repetition/0002` — compile 5.9 s (admission –, schema→grammar 2.04, **engine 5.9 s**; grammar 850 B, regexes 13, mask p99 0.05 ms; synthetic: admitted, compile 69, engine 67)
- `adv/huge_items/0040` — compile 5.7 s (admission –, schema→grammar 2.31, **engine 5.7 s**; grammar 112,043 B, regexes 13, mask p99 0.06 ms; synthetic: admitted, compile 15, engine 12)
- `adv/huge_items/0001` — compile 5.5 s (admission –, schema→grammar 2.34, **engine 5.5 s**; grammar 108,790 B, regexes 13, mask p99 0.10 ms; synthetic: admitted, compile 13, engine 11)
- … 152 more

#### kbnf-hardened: admitted, walk completed, output failed validation

- **validator limitation (re.error: jsonschema cannot compile the pattern, e.g. `\p{L}`)** × 2 — families: regex_alternation_blowup (2); ids: `adv/regex_alternation_blowup/0025`, `adv/regex_alternation_blowup/0026`. Example `adv/regex_alternation_blowup/0025`: `error: bad escape \p at position 1` → `{"s"⏎:"#(contract"⏎⏎⏎⏎	                 }⏎`
- **json: control character** × 1 — families: regex_nested_quantifiers (1); ids: `adv/regex_nested_quantifiers/0026`. Example `adv/regex_nested_quantifiers/0026`: `json: Invalid control character at: line 41 column 640 (char 881)` → ` {⏎⏎⏎⏎				                     "s0"⏎⏎⏎⏎:⏎⏎⏎⏎⏎⏎       ⏎⏎ ⏎ ⏎"",⏎		    ⏎            ⏎       `

#### kbnf-default: admitted, walk completed, output failed validation

- **json: control character** × 2 — families: regex_nested_quantifiers (2); ids: `adv/regex_nested_quantifiers/0012`, `adv/regex_nested_quantifiers/0026`. Example `adv/regex_nested_quantifiers/0012`: `json: Invalid control character at: line 3 column 131 (char 134)` → ` {⏎⏎ "s0":"/嬉しい Background bề頻 ProgrammeWF Zhenggeme-handed bright alumnos improvis(baseUr`
- **json: delimiter** × 1 — families: regex_nested_quantifiers (1); ids: `adv/regex_nested_quantifiers/0005`. Example `adv/regex_nested_quantifiers/0005`: `json: Expecting ',' delimiter: line 10 column 77 (char 125)` → ` {⏎ "s0":⏎⏎ "aaaaaaaaaaaaaaaaaaab"⏎⏎⏎⏎ ,⏎							⏎                                         `
- **validator limitation (re.error: jsonschema cannot compile the pattern, e.g. `\p{L}`)** × 1 — families: regex_alternation_blowup (1); ids: `adv/regex_alternation_blowup/0025`. Example `adv/regex_alternation_blowup/0025`: `error: bad escape \p at position 1` → `{"s"⏎:"#(contract"⏎⏎⏎⏎	                 }⏎`

#### kbnf-hardened: resource attacks (`expect: reject`) admitted

- `adv/regex_counted_repetition/0031` — compile 465 (engine 262), peak RSS 505 MB, walk hit token cap; synthetic: admitted, compile 449, engine 245
- `adv/regex_counted_repetition/0015` — compile 428 (engine 221), peak RSS 505 MB, walk hit token cap; synthetic: admitted, compile 409, engine 209

#### kbnf-default: resource attacks (`expect: reject`) admitted

- `adv/regex_alternation_blowup/0014` — compile 17.5 s (engine 17.5 s), peak RSS 1183 MB, walk hit token cap; synthetic: admitted, compile 198, engine 196
- `adv/huge_items/0041` — compile 16.0 s (engine 16.0 s), peak RSS 344 MB, walk hit token cap; synthetic: admitted, compile 27, engine 24
- `adv/thousands_of_props/0016` — compile 10.5 s (engine 9.7 s), peak RSS 610 MB, walk hit token cap; synthetic: admitted, compile 1.3 s, engine 378
- `adv/huge_items/0040` — compile 5.7 s (engine 5.7 s), peak RSS 346 MB, walk hit token cap; synthetic: admitted, compile 15, engine 12
- `adv/regex_alternation_blowup/0004` — compile 4.2 s (engine 4.2 s), peak RSS 611 MB, walk completed, valid; synthetic: admitted, compile 179, engine 137
- `adv/regex_alternation_blowup/0003` — compile 1.6 s (engine 1.6 s), peak RSS 428 MB, walk completed, valid; synthetic: admitted, compile 70, engine 52

#### Generation aborted (dead end / decode limit / capture error)

- none

#### Default (unlimited) configuration: hangs, crashes, OOMs by family

- **huge_string_length**: {'oom': 12, 'timeout': 24} — e.g. `adv/huge_string_length/0004` oom during `compile` (peak RSS 4270 MB)
- **giant_const**: {'timeout': 24, 'oom': 6} — e.g. `adv/giant_const/0000` timeout during `compile` (peak RSS 1250 MB)
- **wide_enum**: {'timeout': 20, 'crash': 9} — e.g. `adv/wide_enum/0000` timeout during `compile` (peak RSS 1242 MB)
- **huge_items**: {'timeout': 23, 'oom': 6} — e.g. `adv/huge_items/0002` timeout during `compile` (peak RSS 351 MB)
- **thousands_of_props**: {'timeout': 18} — e.g. `adv/thousands_of_props/0000` timeout during `compile` (peak RSS 830 MB)
- **regex_counted_repetition**: {'timeout': 14} — e.g. `adv/regex_counted_repetition/0000` timeout during `compile` (peak RSS 1089 MB)
- **regex_alternation_blowup**: {'timeout': 8, 'oom': 2} — e.g. `adv/regex_alternation_blowup/0006` timeout during `compile` (peak RSS 1353 MB)
- **mixed_combo**: {'timeout': 6} — e.g. `adv/mixed_combo/0003` timeout during `compile` (peak RSS 1298 MB)
- **unicode_heavy**: {'timeout': 5} — e.g. `adv/unicode_heavy/0010` timeout during `compile` (peak RSS 1345 MB)


### Worst cases per configuration (by end-to-end cost)

#### kbnf-hardened

- `adv/regex_alternation_blowup/0028` — rejected 1.2 s, phase `admission`, peak RSS 791 MB
- `adv/huge_items/0031` — rejected 788, phase `admission`, peak RSS 2439 MB
- `adv/huge_items/0027` — rejected 788, phase `admission`, peak RSS 2102 MB
- `adv/regex_alternation_blowup/0027` — rejected 553, phase `admission`, peak RSS 419 MB
- `adv/regex_counted_repetition/0009` — rejected 507, phase `admission`, peak RSS 381 MB
- `adv/regex_counted_repetition/0025` — rejected 504, phase `admission`, peak RSS 399 MB
- `adv/regex_counted_repetition/0031` — admitted 465, phase `done`, peak RSS 505 MB
- `adv/regex_counted_repetition/0015` — admitted 428, phase `done`, peak RSS 505 MB

#### kbnf-default

- `adv/regex_counted_repetition/0023` — timeout 20.0 s, phase `compile`, peak RSS 1371 MB
- `adv/mixed_combo/0005` — timeout 20.0 s, phase `compile`, peak RSS 343 MB
- `adv/mixed_combo/0025` — timeout 20.0 s, phase `compile`, peak RSS 1265 MB
- `adv/unicode_heavy/0019` — timeout 20.0 s, phase `compile`, peak RSS 1318 MB
- `adv/thousands_of_props/0020` — timeout 20.0 s, phase `compile`, peak RSS 885 MB
- `adv/thousands_of_props/0022` — timeout 20.0 s, phase `compile`, peak RSS 903 MB
- `adv/mixed_combo/0027` — timeout 20.0 s, phase `compile`, peak RSS 1299 MB
- `adv/huge_string_length/0024` — timeout 20.0 s, phase `compile`, peak RSS 1554 MB

