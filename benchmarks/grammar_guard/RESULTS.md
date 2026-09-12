# GrammarGuard adversarial-schema benchmark — results

Generated 2026-09-12T12:47:51 by `benchmarks/grammar_guard/report.py` from `grammar_guard/results`.

Corpus: **1078 schemas** (610 normal, 468 adversarial), deterministic seed; see `README.md` for the families and what `expect` means.

Environment: python 3.11.10, platform macOS-26.5.2-arm64-arm-64bit, kbnf 0.5.7, formatron 0.5.0, xgrammar 0.2.6, llguidance 1.8.0, jsonschema 4.26.0.

Isolation: one fresh `spawn` child per schema, 10 s wall-clock kill, RSS watchdog (3–4 GB), 6 parallel workers; synthetic ~3k-token vocabulary; random walk capped at 512 tokens.

## Headline numbers

| config | n | admitted | rejected | timeout | crash/oom | valid / completed walks | compile p50 | p99 | max | admitted & > 1 s | normal/admit rejected | expect=reject admitted | expect=reject hung/crashed |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kbnf-hardened | 1078 | 74% | 26% | 0% | 0% | 747/753 (99%) | 12 | 318 | 1.9 s | 3 | 0 | 2 | 0 |
| kbnf-default | 1078 | 86% | 6% | 4% | 3% | 823/832 (99%) | 11 | 6.3 s | 9.1 s | 65 | 0 | 32 | 75 |
| xgrammar | 1078 | 95% | 1% | 5% | 0% | – | 2.06 | 3.6 s | 7.5 s | 36 | 0 | 87 | 50 |
| llguidance | 1078 | 94% | 5% | 0% | 0% | – | 0.72 | 192 | 1.0 s | 1 | 0 | 94 | 4 |

*compile* = admission (hardened only) + schema→grammar + engine construction for admitted schemas; for xgrammar/llguidance it is schema→grammar + compile. *valid / completed* counts random walks that finished within the token cap and whose output passed `jsonschema` validation against the original schema. *admitted & > 1 s*: admitted schemas whose compile exceeded 1 s. *normal/admit rejected*: false positives.


## Per family × configuration

### kbnf-hardened

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 80/80 (100%) | 14 | 43 | 45 | 0.00 | 0.11 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 66/66 (100%) | 13 | 164 | 188 | 0.00 | 0.12 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 15 | 41 | 44 | 0.00 | 0.11 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 11 | 23 | 24 | 0.00 | 0.05 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 40 | 128 | 133 | 0.00 | 0.22 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 60/60 (100%) | 18 | 53 | 53 | 0.00 | 0.11 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 12 | 38 | 41 | 0.00 | 0.12 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 38/40 (95%) | 7.91 | 10 | 11 | 0.00 | 0.03 |
| numeric_bounds_nonzero | 10 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 24 | 65 | 68 | 0.01 | 0.11 |
| patterns | 50 | 100% | 0% | 0% | 0% | 47/47 (100%) | 7.71 | 10 | 10 | 0.00 | 0.07 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 15 | 25 | 25 | 0.00 | 0.12 |
| recursion | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 10 | 20 | 20 | 0.00 | 0.09 |
| tuples | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 8.62 | 28 | 29 | 0.01 | 0.13 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 9/9 (100%) | 24 | 37 | 38 | 0.00 | 0.10 |
| deep_nesting *(adv)* | 44 | 2% | 98% | 0% | 0% | 1/1 (100%) | 24 | 24 | 24 | 0.01 | 0.03 |
| wide_enum *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| giant_const *(adv)* | 30 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| huge_items *(adv)* | 48 | 10% | 90% | 0% | 0% | 4/4 (100%) | 23 | 131 | 136 | 0.00 | 0.03 |
| huge_string_length *(adv)* | 40 | 12% | 88% | 0% | 0% | 5/5 (100%) | 229 | 315 | 318 | 0.00 | 0.09 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 21/23 (91%) | 6.86 | 15 | 15 | 0.00 | 0.08 |
| regex_counted_repetition *(adv)* | 32 | 44% | 56% | 0% | 0% | 7/7 (100%) | 95 | 1.8 s | 1.9 s | 0.00 | 0.03 |
| regex_alternation_blowup *(adv)* | 30 | 43% | 57% | 0% | 0% | 8/10 (80%) | 14 | 624 | 696 | 0.00 | 0.11 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 22 | 49 | 51 | 0.02 | 0.10 |
| thousands_of_props *(adv)* | 24 | 8% | 92% | 0% | 0% | 0/0 | 359 | 472 | 474 | 0.00 | 0.02 |
| recursive_ref_fanout *(adv)* | 24 | 83% | 17% | 0% | 0% | 6/6 (100%) | 26 | 123 | 128 | 0.00 | 0.02 |
| unicode_heavy *(adv)* | 20 | 80% | 20% | 0% | 0% | 11/11 (100%) | 29 | 368 | 376 | 0.01 | 0.54 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 6.49 | 7.34 | 7.35 | 0.00 | 0.03 |
| mixed_combo *(adv)* | 30 | 40% | 60% | 0% | 0% | 11/11 (100%) | 21 | 62 | 64 | 0.00 | 0.08 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 15/15 (100%) | 6.54 | 8.18 | 8.23 | 0.00 | 0.03 |

### kbnf-default

| family | n | admitted | rejected | timeout | crash/oom | valid/completed | compile p50 | p99 | max | mask p50 (ms) | mask p99 (ms) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| flat_object | 80 | 100% | 0% | 0% | 0% | 80/80 (100%) | 11 | 35 | 37 | 0.00 | 0.12 |
| nested_object | 70 | 100% | 0% | 0% | 0% | 66/66 (100%) | 8.88 | 135 | 158 | 0.00 | 0.11 |
| array_of_objects | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 11 | 34 | 34 | 0.00 | 0.11 |
| enum_fields | 50 | 100% | 0% | 0% | 0% | 50/50 (100%) | 7.30 | 18 | 18 | 0.00 | 0.03 |
| enum_medium | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 33 | 114 | 119 | 0.00 | 0.25 |
| optional_fields | 60 | 100% | 0% | 0% | 0% | 60/60 (100%) | 14 | 41 | 41 | 0.00 | 0.12 |
| anyof_union | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 8.65 | 30 | 31 | 0.00 | 0.12 |
| numeric_bounds | 40 | 100% | 0% | 0% | 0% | 38/40 (95%) | 5.14 | 7.31 | 7.36 | 0.00 | 0.03 |
| numeric_bounds_nonzero | 10 | 0% | 100% | 0% | 0% | 0/0 | – | – | – | – | – |
| string_length | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 21 | 54 | 56 | 0.01 | 0.11 |
| patterns | 50 | 100% | 0% | 0% | 0% | 47/47 (100%) | 5.16 | 7.75 | 7.92 | 0.00 | 0.07 |
| refs_defs | 40 | 100% | 0% | 0% | 0% | 40/40 (100%) | 11 | 21 | 22 | 0.00 | 0.14 |
| recursion | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 7.40 | 16 | 16 | 0.00 | 0.10 |
| tuples | 20 | 100% | 0% | 0% | 0% | 20/20 (100%) | 5.61 | 25 | 27 | 0.01 | 0.14 |
| mixed_realistic | 10 | 100% | 0% | 0% | 0% | 9/9 (100%) | 20 | 32 | 32 | 0.00 | 0.11 |
| deep_nesting *(adv)* | 44 | 11% | 89% | 0% | 0% | 5/5 (100%) | 20 | 35 | 35 | 0.00 | 0.03 |
| wide_enum *(adv)* | 30 | 63% | 0% | 10% | 27% | 19/19 (100%) | 1.6 s | 6.6 s | 6.6 s | 0.01 | 13 |
| giant_const *(adv)* | 30 | 33% | 0% | 53% | 13% | 0/0 | 2.1 s | 3.6 s | 3.6 s | 0.00 | 0.01 |
| huge_items *(adv)* | 48 | 52% | 17% | 17% | 15% | 18/18 (100%) | 337 | 8.7 s | 8.8 s | 0.00 | 0.06 |
| huge_string_length *(adv)* | 40 | 45% | 0% | 28% | 28% | 13/13 (100%) | 1.2 s | 6.6 s | 6.8 s | 0.00 | 0.10 |
| regex_nested_quantifiers *(adv)* | 30 | 90% | 10% | 0% | 0% | 21/23 (91%) | 4.68 | 10 | 10 | 0.00 | 0.08 |
| regex_counted_repetition *(adv)* | 32 | 75% | 6% | 19% | 0% | 13/15 (87%) | 115 | 7.0 s | 7.6 s | 0.00 | 0.05 |
| regex_alternation_blowup *(adv)* | 30 | 93% | 0% | 3% | 3% | 19/22 (86%) | 69 | 6.5 s | 6.7 s | 0.00 | 0.13 |
| many_optional_props *(adv)* | 30 | 100% | 0% | 0% | 0% | 30/30 (100%) | 16 | 39 | 40 | 0.02 | 0.10 |
| thousands_of_props *(adv)* | 24 | 92% | 0% | 8% | 0% | 0/0 | 1.6 s | 9.0 s | 9.1 s | 0.00 | 0.02 |
| recursive_ref_fanout *(adv)* | 24 | 100% | 0% | 0% | 0% | 6/6 (100%) | 19 | 143 | 148 | 0.00 | 0.03 |
| unicode_heavy *(adv)* | 20 | 100% | 0% | 0% | 0% | 13/13 (100%) | 54 | 2.4 s | 2.5 s | 0.01 | 3.94 |
| hostile_literals *(adv)* | 40 | 95% | 5% | 0% | 0% | 38/38 (100%) | 3.96 | 4.63 | 4.63 | 0.00 | 0.05 |
| mixed_combo *(adv)* | 30 | 90% | 10% | 0% | 0% | 23/23 (100%) | 40 | 6.0 s | 7.4 s | 0.01 | 2.23 |
| grammar_injection *(adv)* | 16 | 94% | 6% | 0% | 0% | 15/15 (100%) | 4.45 | 4.89 | 4.90 | 0.00 | 0.06 |

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
| kbnf-hardened · all | 1078 | 74% | 26% | 0% | 0% | 12 | 318 | 1.9 s | 0.10 | 1.3 s |
| kbnf-hardened · normal | 610 | 98% | 2% | 0% | 0% | 12 | 82 | 188 | 2.60 | 2.91 |
| kbnf-hardened · adversarial | 468 | 42% | 58% | 0% | 0% | 13 | 1.2 s | 1.9 s | 0.09 | 1.3 s |
| kbnf-default · all | 1078 | 86% | 6% | 4% | 3% | 11 | 6.3 s | 9.1 s | 2.23 | 4.8 s |
| kbnf-default · normal | 610 | 98% | 2% | 0% | 0% | 8.85 | 69 | 158 | 2.51 | 2.82 |
| kbnf-default · adversarial | 468 | 71% | 12% | 10% | 7% | 30 | 8.3 s | 9.1 s | 2.01 | 4.8 s |
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
| numeric_bounds_nonzero | 0% (0%) | 0% (0%) | 100% (0%) | 100% (0%) |
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
| huge_string_length *(adv)* | 12% (0%) | 45% (55%) | 100% (0%) | 100% (0%) |
| regex_nested_quantifiers *(adv)* | 90% (0%) | 90% (0%) | 100% (0%) | 100% (0%) |
| regex_counted_repetition *(adv)* | 44% (0%) | 75% (19%) | 91% (3%) | 100% (0%) |
| regex_alternation_blowup *(adv)* | 43% (0%) | 93% (7%) | 83% (0%) | 100% (0%) |
| many_optional_props *(adv)* | 100% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| thousands_of_props *(adv)* | 8% (0%) | 92% (8%) | 79% (21%) | 83% (0%) |
| recursive_ref_fanout *(adv)* | 83% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| unicode_heavy *(adv)* | 80% (0%) | 100% (0%) | 100% (0%) | 100% (0%) |
| hostile_literals *(adv)* | 95% (0%) | 95% (0%) | 100% (0%) | 100% (0%) |
| mixed_combo *(adv)* | 40% (0%) | 90% (0%) | 100% (0%) | 97% (0%) |
| grammar_injection *(adv)* | 94% (0%) | 94% (0%) | 100% (0%) | 100% (0%) |

### Resource attacks (`expect: reject`)

| engine | expect=reject n | admitted | rejected | timeout | crash/oom | admitted compile max |
|:---|---:|---:|---:|---:|---:|---:|
| kbnf-hardened | 139 | 2 | 137 | 0 | 0 | 1.9 s |
| kbnf-default | 139 | 32 | 32 | 44 | 31 | 9.1 s |
| xgrammar | 139 | 87 | 2 | 48 | 2 | 7.5 s |
| llguidance | 139 | 94 | 41 | 0 | 4 | 1.0 s |


## Interesting individual cases

### Hardened policy: hangs, crashes, OOMs (should be empty)

- none

### Hardened policy: admitted but compile > 1 s

- `adv/regex_counted_repetition/0031` — compile 1.9 s (admission 220, schema→grammar 2.57, engine 1.7 s; grammar 1,152 B, simplified productions 5, chart peak 6, mask p99 0.01 ms)
- `adv/regex_counted_repetition/0015` — compile 1.3 s (admission 213, schema→grammar 1.90, engine 1.1 s; grammar 854 B, simplified productions 3, chart peak 6, mask p99 0.01 ms)
- `adv/regex_counted_repetition/0016` — compile 1.2 s (admission 44, schema→grammar 2.54, engine 1.2 s; grammar 1,143 B, simplified productions 5, chart peak 7, mask p99 0.01 ms)

### kbnf-hardened: admitted, walk completed, output failed validation

- **json** × 3 — families: regex_nested_quantifiers (2), regex_alternation_blowup (1). Example `adv/regex_nested_quantifiers/0005`: `json: Expecting ',' delimiter: line 1 column 27 (char 26)` → `{"s0": "ab", "s1": "color": "linefollow""node": "format": morning"help"order": "false""par`
- **ValidationError: other** × 2 — families: numeric_bounds (2). Example `normal/numeric_bounds/0009`: `ValidationError: 0.0 is less than or equal to the minimum of 0` → `{⏎    "timestamp":30190123456789e-52009990,"locale":-1.50123456789123e45672022141320002020`
- **error** × 1 — families: regex_alternation_blowup (1). Example `adv/regex_alternation_blowup/0025`: `error: bad escape \p at position 1` → `{⏎  "s":"Voiceabab}" }⏎`

### kbnf-default: admitted, walk completed, output failed validation

- **json** × 4 — families: regex_nested_quantifiers (2), regex_alternation_blowup (2). Example `adv/regex_nested_quantifiers/0005`: `json: Expecting ',' delimiter: line 1 column 27 (char 26)` → `{"s0": "ab", "s1": "color": "linefollow""node": "format": morning"help"order": "false""par`
- **error** × 3 — families: regex_counted_repetition (2), regex_alternation_blowup (1). Example `adv/regex_counted_repetition/0009`: `error: bad escape \p at position 0` → `⏎    {"s0":"sentenceThreecountryPowercustomerenabledpaintactKnowWhiteMoreoffsetkeyTurnfrie`
- **ValidationError: other** × 2 — families: numeric_bounds (2). Example `normal/numeric_bounds/0009`: `ValidationError: 0.0 is less than or equal to the minimum of 0` → `{⏎    "timestamp":30190123456789e-52009990,"locale":-1.50123456789123e45672022141320002020`

### Generation aborted (dead end / decode limit / capture error)

- none

### Hardened policy: normal schemas rejected (false positives, by resource)

- none

### Default (unlimited) configuration: hangs, crashes, OOMs by family

- **huge_string_length**: {'oom': 11, 'timeout': 11} — e.g. `adv/huge_string_length/0003` oom during `compile` (peak RSS 3100 MB)
- **giant_const**: {'timeout': 16, 'oom': 4} — e.g. `adv/giant_const/0002` timeout during `compile` (peak RSS 1318 MB)
- **huge_items**: {'oom': 7, 'timeout': 8} — e.g. `adv/huge_items/0011` oom during `grammar_gen` (peak RSS 3217 MB)
- **wide_enum**: {'crash': 8, 'timeout': 3} — e.g. `adv/wide_enum/0004` crash during `compile` (peak RSS 225 MB)
- **regex_counted_repetition**: {'timeout': 6} — e.g. `adv/regex_counted_repetition/0001` timeout during `compile` (peak RSS 868 MB)
- **regex_alternation_blowup**: {'oom': 1, 'timeout': 1} — e.g. `adv/regex_alternation_blowup/0029` oom during `compile` (peak RSS 3492 MB)
- **thousands_of_props**: {'timeout': 2} — e.g. `adv/thousands_of_props/0010` timeout during `compile` (peak RSS 1104 MB)

#### Default configuration: crashes (signals) in detail

- `adv/wide_enum/0004` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0005` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0010` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0011` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0016` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0017` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0022` — child_died: child exited with code -11 during phase compile without a result
- `adv/wide_enum/0028` — child_died: child exited with code -11 during phase compile without a result

### kbnf-hardened admits, an external engine rejects / hangs / crashes

- `adv/regex_alternation_blowup/0025` — hardened **admitted** (75); xgrammar rejected (unsupported_schema: [12:18:20] /Users/runner/work/xgrammar/xgrammar/cpp/regex_co); llguidance admitted (–)
- `adv/regex_alternation_blowup/0026` — hardened **admitted** (696); xgrammar rejected (unsupported_schema: [12:18:20] /Users/runner/work/xgrammar/xgrammar/cpp/regex_co); llguidance admitted (–)
- `adv/regex_counted_repetition/0016` — hardened **admitted** (1.2 s); xgrammar timeout (timeout: killed after 10.0 s during phase schema_to_grammar); llguidance admitted (–)

### Normal schemas kbnf-hardened rejects but an external engine admits

- `normal/numeric_bounds_nonzero/0000` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0001` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0002` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0003` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0004` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0005` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0006` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0007` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0008` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted
- `normal/numeric_bounds_nonzero/0009` — hardened rejected (unsupported_schema: ValueError: float metadata {'ge': 0.5} is not supported in json_genera); xgrammar admitted; llguidance admitted

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

- `adv/regex_counted_repetition/0031` — admitted 1.9 s, phase `done`, peak RSS 411 MB
- `adv/regex_alternation_blowup/0028` — rejected 1.3 s, phase `admission`, peak RSS 741 MB
- `adv/regex_counted_repetition/0015` — admitted 1.3 s, phase `done`, peak RSS 406 MB
- `adv/regex_counted_repetition/0016` — admitted 1.2 s, phase `done`, peak RSS 270 MB
- `adv/regex_counted_repetition/0000` — admitted 856, phase `done`, peak RSS 268 MB
- `adv/huge_items/0027` — rejected 845, phase `admission`, peak RSS 1657 MB
- `adv/huge_items/0031` — rejected 827, phase `admission`, peak RSS 1019 MB
- `adv/regex_alternation_blowup/0026` — admitted 696, phase `done`, peak RSS 299 MB

### kbnf-default

- `adv/regex_counted_repetition/0017` — timeout 10.0 s, phase `compile`, peak RSS 845 MB
- `adv/regex_counted_repetition/0012` — timeout 10.0 s, phase `compile`, peak RSS 805 MB
- `adv/giant_const/0011` — timeout 10.0 s, phase `compile`, peak RSS 2733 MB
- `adv/giant_const/0016` — timeout 10.0 s, phase `compile`, peak RSS 2162 MB
- `adv/giant_const/0003` — timeout 10.0 s, phase `compile`, peak RSS 1902 MB
- `adv/wide_enum/0009` — timeout 10.0 s, phase `compile`, peak RSS 1182 MB
- `adv/huge_items/0030` — timeout 10.0 s, phase `compile`, peak RSS 1439 MB
- `adv/thousands_of_props/0011` — timeout 10.0 s, phase `compile`, peak RSS 1282 MB

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

