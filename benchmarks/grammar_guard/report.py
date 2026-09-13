"""Aggregate ``results/*.jsonl`` into ``RESULTS.md``.

Reads whichever of ``hardened.jsonl`` (kbnf + Formatron hardened policy),
``default.jsonl`` (kbnf + Formatron, no limits), ``xgrammar.jsonl`` and
``llguidance.jsonl`` exist in the results directory and writes:

- headline numbers per configuration,
- a per-family x configuration table (n, admitted/rejected/timeout/crash %,
  valid-output % of completed walks, compile p50/p99, per-token mask p50/p99),
- a differential table across engines (accept/timeout/crash %, compile p50/p99),
- lists of the most interesting individual cases (admitted-but-invalid output,
  admitted-but-slow, hangs/crashes under the hardened policy, false positives on
  normal schemas, disagreements between engines),
- for every real tokenizer vocabulary run (``hardened-<vocab>.jsonl`` /
  ``default-<vocab>.jsonl`` written by ``runner.py --tokenizer``): a top-level
  "Real vocabulary" section with its own headline and per-family tables, a
  paired synthetic-vs-real comparison of compile cost and per-token mask
  latency, the outcome shifts, and the interesting cases,
- an optional hand-written analysis section (``--analysis analysis.md``).

Usage::

    python -m benchmarks.grammar_guard.report                # -> benchmarks/grammar_guard/RESULTS.md
    python -m benchmarks.grammar_guard.report --results-dir R --out OUT.md --analysis analysis.md
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import platform
import re
import sys
import typing

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RESULTS_DIR = os.path.join(HERE, "results")
DEFAULT_OUT = os.path.join(HERE, "RESULTS.md")
DEFAULT_ANALYSIS = os.path.join(HERE, "analysis.md")

# (results file stem, display name)
CONFIGS: list[tuple[str, str]] = [
    ("hardened", "kbnf-hardened"),
    ("default", "kbnf-default"),
    ("xgrammar", "xgrammar"),
    ("llguidance", "llguidance"),
]
KBNF_CONFIGS: list[tuple[str, str]] = CONFIGS[:2]
REAL_VOCAB_FILE_RE = re.compile(r"^(hardened|default)-(.+)\.jsonl$")
SLOW_MS = 1000.0  # "admitted but slow" threshold on end-to-end compile cost
BAD = ("timeout", "crash", "oom")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def load_rows(path: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows[r["id"]] = r  # last write wins (resumed runs never duplicate, but be safe)
    return rows


def pct(values: list[float], q: float) -> float | None:
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return None
    if len(vs) == 1:
        return vs[0]
    pos = q * (len(vs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(vs) - 1)
    return vs[lo] + (vs[hi] - vs[lo]) * (pos - lo)


def fmt_ms(x: float | None) -> str:
    if x is None:
        return "–"
    if x >= 1000:
        return f"{x / 1000:.1f} s"
    if x >= 10:
        return f"{x:.0f}"
    return f"{x:.2f}"


def fmt_pct(num: int, den: int) -> str:
    return "–" if den == 0 else f"{100.0 * num / den:.0f}%"


def compile_total(r: dict) -> float | None:
    """End-to-end cost of deciding + compiling one schema, as a server would pay it."""
    parts = [r.get("admission_ms"), r.get("schema_to_grammar_ms"), r.get("compile_ms")]
    vals = [p for p in parts if isinstance(p, (int, float))]
    if r.get("outcome") in BAD:
        return r.get("wall_ms_parent")
    return sum(vals) if vals else None


def reason_text(r: dict, n: int = 110) -> str:
    reason = r.get("reason") or {}
    if reason.get("resource"):
        s = f"{reason.get('kind')}: {reason.get('limit_phase', '')}/{reason['resource']} {reason.get('observed')} > {reason.get('limit')}"
        if reason.get("path"):
            s += f" at {reason['path'][:40]}"
        return s
    msg = (reason.get("message") or "").replace("\n", " ").replace("|", "\\|")
    return f"{reason.get('kind', '?')}: {msg[:n]}"


def gen(r: dict) -> dict:
    return r.get("generation") or {}


def md_table(header: list[str], rows: list[list[str]], align_right_from: int = 1) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(("---:" if i >= align_right_from else ":---") for i in range(len(header))) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def family_order() -> list[tuple[str, str]]:
    try:
        from . import corpus

        return [(name, cat) for name, (cat, _) in corpus.FAMILIES.items()]
    except Exception:  # pragma: no cover
        return []


def versions() -> dict[str, str]:
    out = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        import importlib.metadata as md

        for name in ("kbnf", "formatron", "xgrammar", "llguidance", "jsonschema"):
            try:
                out[name] = md.version(name)
            except md.PackageNotFoundError:
                out[name] = "not installed"
    except Exception:  # pragma: no cover
        pass
    return out


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------


class Agg:
    """Counts and latency samples for one (config, subset) cell."""

    def __init__(self):
        self.n = 0
        self.by_outcome: collections.Counter = collections.Counter()
        self.compile_admitted: list[float] = []
        self.reject_latency: list[float] = []
        self.mask_p50: list[float] = []
        self.mask_p99: list[float] = []
        self.completed = 0
        self.valid = 0
        self.cap_hit = 0
        self.gen_error = 0
        self.slow = 0
        self.tokens: list[int] = []

    def add(self, r: dict) -> None:
        self.n += 1
        o = r.get("outcome", "crash")
        self.by_outcome[o] += 1
        ct = compile_total(r)
        if o == "admitted":
            if ct is not None:
                self.compile_admitted.append(ct)
                if ct > SLOW_MS:
                    self.slow += 1
            g = gen(r)
            if g:
                if g.get("mask_ms", {}).get("p50") is not None:
                    self.mask_p50.append(g["mask_ms"]["p50"])
                    self.mask_p99.append(g["mask_ms"]["p99"])
                self.tokens.append(g.get("tokens") or 0)
                if g.get("completed"):
                    self.completed += 1
                    if g.get("output_valid"):
                        self.valid += 1
                elif g.get("hit_token_cap"):
                    self.cap_hit += 1
                elif g.get("error"):
                    self.gen_error += 1
        elif o == "rejected" and ct is not None:
            self.reject_latency.append(ct)

    @property
    def bad(self) -> int:
        return sum(self.by_outcome[k] for k in BAD)

    def row(self, label: str, with_gen: bool) -> list[str]:
        cells = [label, str(self.n), fmt_pct(self.by_outcome["admitted"], self.n), fmt_pct(self.by_outcome["rejected"], self.n),
                 fmt_pct(self.by_outcome["timeout"], self.n), fmt_pct(self.by_outcome["crash"] + self.by_outcome["oom"], self.n)]
        if with_gen:
            cells.append(f"{self.valid}/{self.completed}" + (f" ({fmt_pct(self.valid, self.completed)})" if self.completed else ""))
        cells += [fmt_ms(pct(self.compile_admitted, 0.5)), fmt_ms(pct(self.compile_admitted, 0.99)), fmt_ms(pct(self.compile_admitted, 1.0))]
        if with_gen:
            cells += [fmt_ms(pct(self.mask_p50, 0.5)), fmt_ms(pct(self.mask_p99, 0.99))]
        return cells


def aggregate(rows: dict[str, dict], key: typing.Callable[[dict], str]) -> dict[str, Agg]:
    out: dict[str, Agg] = collections.defaultdict(Agg)
    for r in rows.values():
        out[key(r)].add(r)
    return out


# --------------------------------------------------------------------------
# report sections
# --------------------------------------------------------------------------


def section_headline(data: dict[str, dict[str, dict]], configs: list[tuple[str, str]] = CONFIGS, h: int = 2) -> str:
    lines = [f"{'#' * h} Headline numbers", ""]
    header = ["config", "n", "admitted", "rejected", "timeout", "crash/oom", "valid / completed walks", "compile p50", "p99", "max",
              "admitted & > 1 s", "normal/admit rejected", "expect=reject admitted", "expect=reject hung/crashed"]
    rows = []
    for stem, name in configs:
        rs = data.get(stem)
        if not rs:
            continue
        a = Agg()
        fp = 0
        rej_adm = 0
        rej_bad = 0
        for r in rs.values():
            a.add(r)
            if r["category"] == "normal" and r["expect"] == "admit" and r["outcome"] == "rejected":
                fp += 1
            if r["expect"] == "reject":
                if r["outcome"] == "admitted":
                    rej_adm += 1
                if r["outcome"] in BAD:
                    rej_bad += 1
        with_gen = stem in ("hardened", "default")
        row = a.row(name, with_gen=True) if with_gen else a.row(name, with_gen=False)
        if not with_gen:
            row.insert(6, "–")
            row += ["–", "–"]
        rows.append(row[:10] + [str(a.slow), str(fp), str(rej_adm), str(rej_bad)])
    lines.append(md_table(header, rows))
    lines += ["", "*compile* = admission (hardened only) + schema→grammar + engine construction for admitted schemas; "
                  "for xgrammar/llguidance it is schema→grammar + compile. *valid / completed* counts random walks that "
                  "finished within the token cap and whose output passed `jsonschema` validation against the original schema. "
                  "*admitted & > 1 s*: admitted schemas whose compile exceeded 1 s. *normal/admit rejected*: false positives.", ""]
    return "\n".join(lines)


def section_per_family(data: dict[str, dict[str, dict]], configs: list[tuple[str, str]] = CONFIGS, h: int = 2,
                       vocab_desc: str = "the synthetic ~3k-token vocabulary") -> str:
    fams = family_order()
    lines = [f"{'#' * h} Per family × configuration", ""]
    for stem, name in configs:
        rs = data.get(stem)
        if not rs:
            continue
        with_gen = stem in ("hardened", "default")
        aggs = aggregate(rs, lambda r: r["family"])
        header = ["family", "n", "admitted", "rejected", "timeout", "crash/oom"]
        if with_gen:
            header.append("valid/completed")
        header += ["compile p50", "p99", "max"]
        if with_gen:
            header += ["mask p50 (ms)", "mask p99 (ms)"]
        rows = []
        order = [f for f, _ in fams if f in aggs] + sorted(f for f in aggs if f not in dict(fams))
        cats = dict(fams)
        for fam in order:
            label = f"{fam}" + (" *(adv)*" if cats.get(fam) == "adversarial" else "")
            rows.append(aggs[fam].row(label, with_gen))
        lines += [f"{'#' * (h + 1)} {name}", "", md_table(header, rows), ""]
    lines.append(f"Per-token *mask* latency is `Formatter.compute_allowed_tokens()` over {vocab_desc} "
                 "(p50 of per-schema p50s, p99 of per-schema p99s); it is only meaningful relative to other rows.")
    return "\n".join(lines)


def section_differential(data: dict[str, dict[str, dict]]) -> str:
    lines = ["## Differential: kbnf-hardened vs kbnf-default vs xgrammar vs llguidance", ""]
    header = ["engine · subset", "n", "accept", "reject", "timeout", "crash/oom", "compile p50", "p99", "max", "time-to-reject p50", "max"]
    rows = []
    for stem, name in CONFIGS:
        rs = data.get(stem)
        if not rs:
            continue
        for subset in ("all", "normal", "adversarial"):
            a = Agg()
            for r in rs.values():
                if subset == "all" or r["category"] == subset:
                    a.add(r)
            rows.append([f"{name} · {subset}", str(a.n), fmt_pct(a.by_outcome['admitted'], a.n), fmt_pct(a.by_outcome['rejected'], a.n),
                         fmt_pct(a.by_outcome['timeout'], a.n), fmt_pct(a.by_outcome['crash'] + a.by_outcome['oom'], a.n),
                         fmt_ms(pct(a.compile_admitted, 0.5)), fmt_ms(pct(a.compile_admitted, 0.99)), fmt_ms(pct(a.compile_admitted, 1.0)),
                         fmt_ms(pct(a.reject_latency, 0.5)), fmt_ms(pct(a.reject_latency, 1.0))])
    lines += [md_table(header, rows), ""]

    # per-family accept matrix
    fams = family_order()
    present = [(stem, name) for stem, name in CONFIGS if data.get(stem)]
    header = ["family"] + [f"{name} accept (t/o+crash)" for _, name in present]
    rows = []
    all_fams = [f for f, _ in fams] + sorted({r["family"] for rs in data.values() for r in rs.values()} - {f for f, _ in fams})
    cats = dict(fams)
    for fam in all_fams:
        row = [fam + (" *(adv)*" if cats.get(fam) == "adversarial" else "")]
        any_data = False
        for stem, _ in present:
            rs = [r for r in data[stem].values() if r["family"] == fam]
            if not rs:
                row.append("–")
                continue
            any_data = True
            adm = sum(r["outcome"] == "admitted" for r in rs)
            bad = sum(r["outcome"] in BAD for r in rs)
            row.append(f"{fmt_pct(adm, len(rs))} ({fmt_pct(bad, len(rs))})")
        if any_data:
            rows.append(row)
    lines += ["### Accept rate per family (timeout+crash rate in parentheses)", "", md_table(header, rows), ""]

    # expect=reject handling
    header = ["engine", "expect=reject n", "admitted", "rejected", "timeout", "crash/oom", "admitted compile max"]
    rows = []
    for stem, name in present:
        rs = [r for r in data[stem].values() if r["expect"] == "reject"]
        if not rs:
            continue
        a = Agg()
        for r in rs:
            a.add(r)
        rows.append([name, str(a.n), str(a.by_outcome["admitted"]), str(a.by_outcome["rejected"]), str(a.by_outcome["timeout"]),
                     str(a.by_outcome["crash"] + a.by_outcome["oom"]), fmt_ms(pct(a.compile_admitted, 1.0))])
    lines += ["### Resource attacks (`expect: reject`)", "", md_table(header, rows), ""]
    return "\n".join(lines)


def _bullets(items: list[str], limit: int) -> list[str]:
    out = [f"- {s}" for s in items[:limit]]
    if len(items) > limit:
        out.append(f"- … {len(items) - limit} more")
    if not items:
        out.append("- none")
    return out


def section_cases(data: dict[str, dict[str, dict]]) -> str:
    lines = ["## Interesting individual cases", ""]
    hard = data.get("hardened", {})
    dflt = data.get("default", {})
    xg = data.get("xgrammar", {})
    llg = data.get("llguidance", {})

    # 1. hardened: hang / crash / oom
    items = []
    for r in sorted(hard.values(), key=lambda r: r["id"]):
        if r["outcome"] in BAD:
            items.append(f"`{r['id']}` — **{r['outcome']}** during `{r.get('phase_reached')}` "
                         f"(wall {fmt_ms(r.get('wall_ms_parent'))}, peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB): {reason_text(r)}")
    lines += ["### Hardened policy: hangs, crashes, OOMs (should be empty)", ""] + _bullets(items, 40) + [""]

    # 2. hardened: admitted but slow
    items = []
    for r in hard.values():
        ct = compile_total(r)
        if r["outcome"] == "admitted" and ct is not None and ct > SLOW_MS:
            g = gen(r)
            items.append((ct, f"`{r['id']}` — compile {fmt_ms(ct)} (admission {fmt_ms(r.get('admission_ms'))}, schema→grammar "
                              f"{fmt_ms(r.get('schema_to_grammar_ms'))}, engine {fmt_ms(r.get('compile_ms'))}; grammar {r.get('grammar_bytes', 0):,} B, "
                              f"simplified productions {((r.get('admission') or {}).get('grammar_complexity') or {}).get('simplified_productions', '?')}, "
                              f"chart peak {g.get('chart_peak_total', '?')}, mask p99 {fmt_ms((g.get('mask_ms') or {}).get('p99'))} ms)"))
    items.sort(key=lambda t: -t[0])
    lines += [f"### Hardened policy: admitted but compile > {SLOW_MS / 1000:.0f} s", ""] + _bullets([s for _, s in items], 30) + [""]

    # 3. admitted but output invalid (both kbnf configs), grouped by error signature
    for stem, name in (("hardened", "kbnf-hardened"), ("default", "kbnf-default")):
        rs = data.get(stem, {})
        groups: dict[str, list[dict]] = collections.defaultdict(list)
        for r in rs.values():
            g = gen(r)
            if r["outcome"] == "admitted" and g.get("completed") and not g.get("output_valid"):
                err = (g.get("validation_error") or "?")
                sig = err.split(":", 1)[0]
                if sig == "ValidationError":
                    sig += ": " + ("is not of type" if "is not of type" in err else
                                   "does not match" if "does not match" in err else
                                   "is not one of" if "is not one of" in err else
                                   "was expected" if "was expected" in err else
                                   "is too long/short" if ("too long" in err or "too short" in err) else "other")
                groups[sig].append(r)
        items = []
        for sig, lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            fams = collections.Counter(r["family"] for r in lst)
            ex = lst[0]
            preview = (gen(ex).get("output_preview") or "").replace("\n", "⏎").replace("|", "\\|")[:90]
            items.append(f"**{sig}** × {len(lst)} — families: {', '.join(f'{f} ({n})' for f, n in fams.most_common(6))}. "
                         f"Example `{ex['id']}`: `{(gen(ex).get('validation_error') or '')[:120].replace('|', '/')}` → `{preview}`")
        lines += [f"### {name}: admitted, walk completed, output failed validation", ""] + _bullets(items, 25) + [""]

    # 4. generation dead ends / decode-limit hits
    items = []
    for stem, name in (("hardened", "kbnf-hardened"), ("default", "kbnf-default")):
        cnt = collections.Counter()
        ex: dict[str, dict] = {}
        for r in data.get(stem, {}).values():
            e = gen(r).get("error")
            if r["outcome"] == "admitted" and e:
                cnt[e.get("kind", "?")] += 1
                ex.setdefault(e.get("kind", "?"), r)
        for kind, n in cnt.most_common():
            r = ex[kind]
            items.append(f"{name}: **{kind}** × {n} — e.g. `{r['id']}`: {(gen(r)['error'].get('message') or '')[:120]}")
    lines += ["### Generation aborted (dead end / decode limit / capture error)", ""] + _bullets(items, 20) + [""]

    # 5. false positives: normal/admit rejected by hardened
    items = []
    by_res: dict[str, list[dict]] = collections.defaultdict(list)
    for r in hard.values():
        if r["category"] == "normal" and r["expect"] == "admit" and r["outcome"] == "rejected":
            reason = r.get("reason") or {}
            by_res[reason.get("resource") or reason.get("kind", "?")].append(r)
    for res, lst in sorted(by_res.items(), key=lambda kv: -len(kv[1])):
        fams = collections.Counter(r["family"] for r in lst)
        ex = lst[0]
        items.append(f"**{res}** × {len(lst)} — families: {', '.join(f'{f} ({n})' for f, n in fams.most_common(5))}. "
                     f"Example `{ex['id']}`: {reason_text(ex, 140)}")
    lines += ["### Hardened policy: normal schemas rejected (false positives, by resource)", ""] + _bullets(items, 20) + [""]

    # 6. default config: hangs / crashes / OOM by family
    items = []
    fams = collections.defaultdict(collections.Counter)
    for r in dflt.values():
        if r["outcome"] in BAD:
            fams[r["family"]][r["outcome"]] += 1
    for fam, c in sorted(fams.items(), key=lambda kv: -sum(kv[1].values())):
        ex = next(r for r in dflt.values() if r["family"] == fam and r["outcome"] in BAD)
        items.append(f"**{fam}**: {dict(c)} — e.g. `{ex['id']}` {ex['outcome']} during `{ex.get('phase_reached')}` "
                     f"(peak RSS {ex.get('peak_rss_mb_observed', 0):.0f} MB)")
    lines += ["### Default (unlimited) configuration: hangs, crashes, OOMs by family", ""] + _bullets(items, 30) + [""]
    crashes = [r for r in dflt.values() if r["outcome"] == "crash"]
    items = [f"`{r['id']}` — {reason_text(r, 100)}" for r in sorted(crashes, key=lambda r: r["id"])]
    lines += ["#### Default configuration: crashes (signals) in detail", ""] + _bullets(items, 30) + [""]

    # 7. disagreements with external engines
    def out(rs, i):
        r = rs.get(i)
        return r["outcome"] if r else "n/a"

    items = []
    for i, r in sorted(hard.items()):
        ox, ol = out(xg, i), out(llg, i)
        if r["outcome"] == "admitted" and (ox in ("rejected",) + BAD or ol in ("rejected",) + BAD):
            items.append(f"`{i}` — hardened **admitted** ({fmt_ms(compile_total(r))}); xgrammar {ox} ({reason_text(xg[i], 60) if xg.get(i) and ox != 'admitted' else '–'}); "
                         f"llguidance {ol} ({reason_text(llg[i], 60) if llg.get(i) and ol != 'admitted' else '–'})")
    lines += ["### kbnf-hardened admits, an external engine rejects / hangs / crashes", ""] + _bullets(items, 40) + [""]

    items = []
    for i, r in sorted(hard.items()):
        if r["category"] == "normal" and r["outcome"] == "rejected":
            ox, ol = out(xg, i), out(llg, i)
            if ox == "admitted" or ol == "admitted":
                items.append(f"`{i}` — hardened rejected ({reason_text(r, 70)}); xgrammar {ox}; llguidance {ol}")
    lines += ["### Normal schemas kbnf-hardened rejects but an external engine admits", ""] + _bullets(items, 40) + [""]

    for stem, name in (("xgrammar", "xgrammar"), ("llguidance", "llguidance")):
        rs = data.get(stem, {})
        items = []
        for r in sorted(rs.values(), key=lambda r: r["id"]):
            if r["outcome"] in BAD:
                items.append(f"`{r['id']}` — **{r['outcome']}** during `{r.get('phase_reached')}` (wall {fmt_ms(r.get('wall_ms_parent'))}, "
                             f"peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB)")
        slow = sorted(((compile_total(r) or 0, r) for r in rs.values() if r["outcome"] == "admitted"), key=lambda t: -t[0])
        items2 = [f"`{r['id']}` — compile {fmt_ms(ct)} (grammar {r.get('grammar_bytes') or 0:,} B)" for ct, r in slow[:8] if ct > SLOW_MS]
        rej = collections.Counter((r.get("reason") or {}).get("kind", "?") for r in rs.values() if r["outcome"] == "rejected")
        rej_ex = {}
        for r in rs.values():
            if r["outcome"] == "rejected":
                rej_ex.setdefault((r.get("reason") or {}).get("kind", "?"), r)
        items3 = [f"**{k}** × {n} — e.g. `{rej_ex[k]['id']}`: {((rej_ex[k].get('reason') or {}).get('message') or '')[:120].replace('|', '/')}"
                  for k, n in rej.most_common()]
        lines += [f"### {name}: hangs / crashes", ""] + _bullets(items, 30) + ["", f"#### {name}: admitted but compile > 1 s", ""] + _bullets(items2, 8) + \
                 ["", f"#### {name}: rejection reasons", ""] + _bullets(items3, 12) + [""]
    return "\n".join(lines)


def section_worst(data: dict[str, dict[str, dict]], configs: list[tuple[str, str]] = CONFIGS, h: int = 2) -> str:
    lines = [f"{'#' * h} Worst cases per configuration (by end-to-end cost)", ""]
    for stem, name in configs:
        rs = data.get(stem)
        if not rs:
            continue
        worst = sorted(rs.values(), key=lambda r: -(compile_total(r) or r.get("wall_ms_parent") or 0))[:8]
        items = [f"`{r['id']}` — {r['outcome']} {fmt_ms(compile_total(r) or r.get('wall_ms_parent'))}, phase `{r.get('phase_reached')}`, "
                 f"peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB" for r in worst]
        lines += [f"{'#' * (h + 1)} {name}", ""] + _bullets(items, 8) + [""]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# real tokenizer vocabularies (runner.py --tokenizer)
# --------------------------------------------------------------------------


def discover_real_vocab_runs(results_dir: str) -> dict[str, dict[str, dict[str, dict]]]:
    """``{vocab_name: {"hardened": rows, "default": rows}}`` from ``<config>-<vocab>.jsonl`` files."""
    out: dict[str, dict[str, dict[str, dict]]] = {}
    if not os.path.isdir(results_dir):
        return out
    for fn in sorted(os.listdir(results_dir)):
        m = REAL_VOCAB_FILE_RE.match(fn)
        if not m:
            continue
        rows = load_rows(os.path.join(results_dir, fn))
        if rows:
            out.setdefault(m.group(2), {})[m.group(1)] = rows
    return out


def vocab_info(real: dict[str, dict[str, dict]], vocab_name: str) -> dict[str, typing.Any]:
    """Tokenizer id, size and run options as recorded in the rows (first row wins)."""
    info: dict[str, typing.Any] = {"name": vocab_name, "tokenizer": None, "size": None, "options": {}}
    for rs in real.values():
        for r in rs.values():
            v = r.get("vocab") or {}
            if v.get("tokenizer") and info["tokenizer"] is None:
                info["tokenizer"] = v["tokenizer"]
                info["size"] = v.get("size") or r.get("vocab_size")
            if r.get("options") and not info["options"]:
                info["options"] = r["options"]
            if info["tokenizer"] and info["options"]:
                return info
    return info


def pretty_vocab_name(info: dict[str, typing.Any]) -> str:
    """``Qwen/Qwen2.5-0.5B-Instruct`` -> ``Qwen2.5`` (falls back to the file-name label)."""
    tok = info.get("tokenizer")
    if tok:
        return tok.rstrip("/").split("/")[-1].split("-", 1)[0]
    return info["name"]


def real_section_title(info: dict[str, typing.Any]) -> str:
    size = info.get("size")
    size_txt = f"{size // 1000}k tokens" if isinstance(size, int) else "real tokenizer"
    return f"Real vocabulary ({pretty_vocab_name(info)}, {size_txt})"


def md_anchor(title: str) -> str:
    """GitHub-style heading slug."""
    slug = re.sub(r"[^\w\- ]", "", title.lower())
    return "#" + slug.replace(" ", "-")


def engine_ms(r: dict) -> float | None:
    v = r.get("compile_ms")
    return v if isinstance(v, (int, float)) else None


def _paired(syn: dict[str, dict], real: dict[str, dict], subset: str) -> list[tuple[dict, dict]]:
    out = []
    for i, r in real.items():
        s = syn.get(i)
        if s is None or (subset != "all" and r["category"] != subset):
            continue
        out.append((s, r))
    return out


def _arrow(a: str, b: str) -> str:
    return f"{a} → {b}"


def section_real_compare(synthetic: dict[str, dict[str, dict]], real: dict[str, dict[str, dict]], h: int, pretty: str) -> str:
    lines = [f"{'#' * h} Synthetic vs {pretty} vocabulary", "",
             "Paired on the schemas **admitted on both vocabularies** (same corpus ids, same seed). *compile* is the "
             "end-to-end cost (admission + schema→grammar + engine construction); *engine* is `FormatterBuilder.build` "
             "alone, i.e. `kbnf.Engine` construction, which is the only vocabulary-dependent part of compilation. "
             "*ratio* is the median of per-schema engine-construction ratios (real / synthetic).", ""]
    header = ["config · subset", "n paired", "compile p50", "compile p99", "engine p50", "engine p99", "engine ratio (median)",
              "admitted & > 1 s"]
    rows = []
    mask_rows = []
    for stem, name in KBNF_CONFIGS:
        syn, rl = synthetic.get(stem), real.get(stem)
        if not syn or not rl:
            continue
        for subset in ("all", "normal", "adversarial"):
            pairs = [(s, r) for s, r in _paired(syn, rl, subset) if s["outcome"] == "admitted" and r["outcome"] == "admitted"]
            if not pairs:
                continue
            cs = [compile_total(s) for s, _ in pairs]
            cr = [compile_total(r) for _, r in pairs]
            es = [engine_ms(s) for s, _ in pairs]
            er = [engine_ms(r) for _, r in pairs]
            ratios = [b / a for a, b in zip(es, er) if a and b and a > 0]
            slow_s = sum(1 for c in cs if c is not None and c > SLOW_MS)
            slow_r = sum(1 for c in cr if c is not None and c > SLOW_MS)
            rows.append([f"{name} · {subset}", str(len(pairs)),
                         _arrow(fmt_ms(pct(cs, 0.5)), fmt_ms(pct(cr, 0.5))), _arrow(fmt_ms(pct(cs, 0.99)), fmt_ms(pct(cr, 0.99))),
                         _arrow(fmt_ms(pct(es, 0.5)), fmt_ms(pct(er, 0.5))), _arrow(fmt_ms(pct(es, 0.99)), fmt_ms(pct(er, 0.99))),
                         f"×{pct(ratios, 0.5):.1f}" if ratios else "–", _arrow(str(slow_s), str(slow_r))])
            m50s = [gen(s).get("mask_ms", {}).get("p50") for s, _ in pairs]
            m50r = [gen(r).get("mask_ms", {}).get("p50") for _, r in pairs]
            m99s = [gen(s).get("mask_ms", {}).get("p99") for s, _ in pairs]
            m99r = [gen(r).get("mask_ms", {}).get("p99") for _, r in pairs]
            a50s = [gen(s).get("accept_ms", {}).get("p50") for s, _ in pairs]
            a50r = [gen(r).get("accept_ms", {}).get("p50") for _, r in pairs]
            als = [gen(s).get("allowed_mean") for s, _ in pairs]
            alr = [gen(r).get("allowed_mean") for _, r in pairs]
            comp_s = sum(1 for s, _ in pairs if gen(s).get("completed"))
            comp_r = sum(1 for _, r in pairs if gen(r).get("completed"))
            val_s = sum(1 for s, _ in pairs if gen(s).get("completed") and gen(s).get("output_valid"))
            val_r = sum(1 for _, r in pairs if gen(r).get("completed") and gen(r).get("output_valid"))
            ovh = [gen(r).get("walk_overhead_ms") for _, r in pairs if gen(r).get("walk_overhead_ms") is not None]
            mask_rows.append([f"{name} · {subset}", str(len(pairs)),
                              _arrow(fmt_ms(pct(m50s, 0.5)), fmt_ms(pct(m50r, 0.5))), _arrow(fmt_ms(pct(m99s, 0.99)), fmt_ms(pct(m99r, 0.99))),
                              _arrow(fmt_ms(pct(a50s, 0.5)), fmt_ms(pct(a50r, 0.5))),
                              _arrow(f"{pct(als, 0.5) or 0:.0f}", f"{pct(alr, 0.5) or 0:,.0f}"),
                              _arrow(f"{val_s}/{comp_s}", f"{val_r}/{comp_r}"), fmt_ms(pct(ovh, 0.5))])
    lines += [f"{'#' * (h + 1)} Compile cost (ms unless noted; synthetic → real)", "", md_table(header, rows), ""]
    header = ["config · subset", "n paired", "mask p50", "mask p99", "accept p50", "allowed tokens (mean)", "valid / completed walks",
              "walk overhead p50 (real)"]
    lines += [f"{'#' * (h + 1)} Per-token latency and walk outcome (synthetic → real)", "", md_table(header, mask_rows), "",
              "*mask* = `compute_allowed_tokens()`, *accept* = `accept_token()` (p50 of per-schema p50s, p99 of per-schema p99s). "
              "*walk overhead* is everything in the random walk that is not the engine (materialising the allowed-id list, "
              "biased sampling, chart probes) per schema; it is a harness cost, not an engine cost, and grows with the allowed set.", ""]

    # per-family, per config
    fams = family_order()
    cats = dict(fams)
    for stem, name in KBNF_CONFIGS:
        syn, rl = synthetic.get(stem), real.get(stem)
        if not syn or not rl:
            continue
        by_fam: dict[str, list[tuple[dict, dict]]] = collections.defaultdict(list)
        for s, r in _paired(syn, rl, "all"):
            if s["outcome"] == "admitted" and r["outcome"] == "admitted":
                by_fam[r["family"]].append((s, r))
        order = [f for f, _ in fams if f in by_fam] + sorted(f for f in by_fam if f not in cats)
        rows = []
        for fam in order:
            pairs = by_fam[fam]
            cs = [compile_total(s) for s, _ in pairs]
            cr = [compile_total(r) for _, r in pairs]
            es = [engine_ms(s) for s, _ in pairs]
            er = [engine_ms(r) for _, r in pairs]
            ratios = [b / a for a, b in zip(es, er) if a and b and a > 0]
            m50s = [gen(s).get("mask_ms", {}).get("p50") for s, _ in pairs]
            m50r = [gen(r).get("mask_ms", {}).get("p50") for _, r in pairs]
            m99s = [gen(s).get("mask_ms", {}).get("p99") for s, _ in pairs]
            m99r = [gen(r).get("mask_ms", {}).get("p99") for _, r in pairs]
            rows.append([fam + (" *(adv)*" if cats.get(fam) == "adversarial" else ""), str(len(pairs)),
                         _arrow(fmt_ms(pct(cs, 0.5)), fmt_ms(pct(cr, 0.5))), _arrow(fmt_ms(pct(cs, 0.99)), fmt_ms(pct(cr, 0.99))),
                         f"×{pct(ratios, 0.5):.1f}" if ratios else "–",
                         _arrow(fmt_ms(pct(m50s, 0.5)), fmt_ms(pct(m50r, 0.5))), _arrow(fmt_ms(pct(m99s, 0.99)), fmt_ms(pct(m99r, 0.99)))])
        header = ["family", "n paired", "compile p50", "compile p99", "engine ratio", "mask p50", "mask p99"]
        lines += [f"{'#' * (h + 1)} {name}: per family (synthetic → real)", "", md_table(header, rows), ""]

    # outcome shifts
    items = []
    for stem, name in KBNF_CONFIGS:
        syn, rl = synthetic.get(stem), real.get(stem)
        if not syn or not rl:
            continue
        shifts: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
        for s, r in _paired(syn, rl, "all"):
            if s["outcome"] != r["outcome"]:
                shifts[(s["outcome"], r["outcome"])].append(r)
        only_real = sorted(set(rl) - set(syn))
        for (a, b), lst in sorted(shifts.items(), key=lambda kv: -len(kv[1])):
            fam = collections.Counter(r["family"] for r in lst)
            ex = lst[0]
            detail = f"phase `{ex.get('phase_reached')}`" if b in BAD else (reason_text(ex, 80) if b == "rejected" else f"compile {fmt_ms(compile_total(ex))}")
            items.append(f"{name}: **{a} → {b}** × {len(lst)} — {', '.join(f'{f} ({n})' for f, n in fam.most_common(5))}; "
                         f"e.g. `{ex['id']}` ({detail})")
        if only_real:
            items.append(f"{name}: {len(only_real)} ids only in the real-vocabulary run (e.g. `{only_real[0]}`)")
    lines += [f"{'#' * (h + 1)} Outcome changes synthetic → real (same schema, same config)", "",
              "A change here is either the vocabulary (engine construction now exceeds the timeout / memory cap, or a walk "
              "now completes) or a change in the generator between the two runs (the synthetic files are never re-run).", ""] + _bullets(items, 30) + [""]
    return "\n".join(lines)


def section_real_cases(real: dict[str, dict[str, dict]], synthetic: dict[str, dict[str, dict]], h: int) -> str:
    lines = [f"{'#' * h} Interesting individual cases", ""]
    hard = real.get("hardened", {})
    dflt = real.get("default", {})

    def syn_note(stem: str, i: str) -> str:
        s = (synthetic.get(stem) or {}).get(i)
        if not s:
            return "synthetic: n/a"
        if s["outcome"] == "admitted":
            return f"synthetic: admitted, compile {fmt_ms(compile_total(s))}, engine {fmt_ms(engine_ms(s))}"
        return f"synthetic: {s['outcome']}"

    # 1. hardened: hang / crash / oom
    items = []
    for r in sorted(hard.values(), key=lambda r: r["id"]):
        if r["outcome"] in BAD:
            items.append(f"`{r['id']}` — **{r['outcome']}** during `{r.get('phase_reached')}` (wall {fmt_ms(r.get('wall_ms_parent'))}, "
                         f"peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB; {syn_note('hardened', r['id'])}): {reason_text(r)}")
    lines += [f"{'#' * (h + 1)} Hardened policy: hangs, crashes, OOMs (should be empty)", ""] + _bullets(items, 40) + [""]

    # 2. admitted but slow (both configs), with the synthetic timing of the same schema
    for stem, name in KBNF_CONFIGS:
        rs = real.get(stem, {})
        items = []
        for r in rs.values():
            ct = compile_total(r)
            if r["outcome"] == "admitted" and ct is not None and ct > SLOW_MS:
                g = gen(r)
                items.append((ct, f"`{r['id']}` — compile {fmt_ms(ct)} (admission {fmt_ms(r.get('admission_ms'))}, schema→grammar "
                                  f"{fmt_ms(r.get('schema_to_grammar_ms'))}, **engine {fmt_ms(r.get('compile_ms'))}**; grammar "
                                  f"{r.get('grammar_bytes', 0):,} B, regexes {(r.get('inspect') or {}).get('regexes', '?')}, "
                                  f"mask p99 {fmt_ms((g.get('mask_ms') or {}).get('p99'))} ms; {syn_note(stem, r['id'])})"))
        items.sort(key=lambda t: -t[0])
        slow_fams = collections.Counter(r["family"] for r in rs.values()
                                        if r["outcome"] == "admitted" and (compile_total(r) or 0) > SLOW_MS)
        n_adm = sum(r["outcome"] == "admitted" for r in rs.values())
        summary = (f"{len(items)} of {n_adm} admitted schemas ({fmt_pct(len(items), n_adm)}); by family: " +
                   ", ".join(f"{f} ({n})" for f, n in slow_fams.most_common()) + ".") if items else ""
        lines += [f"{'#' * (h + 1)} {name}: admitted but compile > {SLOW_MS / 1000:.0f} s", ""] + ([summary, ""] if summary else []) + \
                 _bullets([s for _, s in items], 30) + [""]

    # 3. admitted but output invalid, grouped by error signature
    for stem, name in KBNF_CONFIGS:
        rs = real.get(stem, {})
        groups: dict[str, list[dict]] = collections.defaultdict(list)
        for r in rs.values():
            g = gen(r)
            if r["outcome"] == "admitted" and g.get("completed") and not g.get("output_valid"):
                err = (g.get("validation_error") or "?")
                sig = err.split(":", 1)[0]
                if sig == "ValidationError":
                    sig += ": " + ("is not of type" if "is not of type" in err else
                                   "does not match" if "does not match" in err else
                                   "is not one of" if "is not one of" in err else
                                   "was expected" if "was expected" in err else
                                   "is too long/short" if ("too long" in err or "too short" in err) else "other")
                elif sig == "json":
                    sig += ": " + ("control character" if "control character" in err else
                                   "delimiter" if "delimiter" in err else "other")
                elif sig == "error" and "bad escape" in err:
                    sig = "validator limitation (re.error: jsonschema cannot compile the pattern, e.g. `\\p{L}`)"
                groups[sig].append(r)
        items = []
        for sig, lst in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            fams = collections.Counter(r["family"] for r in lst)
            ex = lst[0]
            preview = (gen(ex).get("output_preview") or "").replace("\n", "⏎").replace("|", "\\|")[:90]
            items.append(f"**{sig}** × {len(lst)} — families: {', '.join(f'{f} ({n})' for f, n in fams.most_common(6))}; ids: "
                         f"{', '.join('`' + r['id'] + '`' for r in sorted(lst, key=lambda r: r['id'])[:6])}"
                         f"{' …' if len(lst) > 6 else ''}. Example `{ex['id']}`: "
                         f"`{(gen(ex).get('validation_error') or '')[:120].replace('|', '/')}` → `{preview}`")
        lines += [f"{'#' * (h + 1)} {name}: admitted, walk completed, output failed validation", ""] + _bullets(items, 25) + [""]

    # 4. expect=reject admitted
    for stem, name in KBNF_CONFIGS:
        rs = real.get(stem, {})
        items = []
        for r in sorted(rs.values(), key=lambda r: -(compile_total(r) or 0)):
            if r["expect"] == "reject" and r["outcome"] == "admitted":
                g = gen(r)
                walk = ("completed, " + ("valid" if g.get("output_valid") else "invalid")) if g.get("completed") else (
                    "hit token cap" if g.get("hit_token_cap") else f"aborted ({(g.get('error') or {}).get('kind', '?')})")
                items.append(f"`{r['id']}` — compile {fmt_ms(compile_total(r))} (engine {fmt_ms(r.get('compile_ms'))}), "
                             f"peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB, walk {walk}; {syn_note(stem, r['id'])}")
        lines += [f"{'#' * (h + 1)} {name}: resource attacks (`expect: reject`) admitted", ""] + _bullets(items, 40) + [""]

    # 5. generation aborted
    items = []
    for stem, name in KBNF_CONFIGS:
        cnt = collections.Counter()
        ex: dict[str, dict] = {}
        for r in real.get(stem, {}).values():
            e = gen(r).get("error")
            if r["outcome"] == "admitted" and e:
                cnt[e.get("kind", "?")] += 1
                ex.setdefault(e.get("kind", "?"), r)
        for kind, n in cnt.most_common():
            r = ex[kind]
            items.append(f"{name}: **{kind}** × {n} — e.g. `{r['id']}`: {(gen(r)['error'].get('message') or '')[:120]}")
    lines += [f"{'#' * (h + 1)} Generation aborted (dead end / decode limit / capture error)", ""] + _bullets(items, 20) + [""]

    # 6. default: hangs / crashes / OOM by family
    items = []
    fams = collections.defaultdict(collections.Counter)
    for r in dflt.values():
        if r["outcome"] in BAD:
            fams[r["family"]][r["outcome"]] += 1
    for fam, c in sorted(fams.items(), key=lambda kv: -sum(kv[1].values())):
        ex = next(r for r in dflt.values() if r["family"] == fam and r["outcome"] in BAD)
        items.append(f"**{fam}**: {dict(c)} — e.g. `{ex['id']}` {ex['outcome']} during `{ex.get('phase_reached')}` "
                     f"(peak RSS {ex.get('peak_rss_mb_observed', 0):.0f} MB)")
    lines += [f"{'#' * (h + 1)} Default (unlimited) configuration: hangs, crashes, OOMs by family", ""] + _bullets(items, 30) + [""]
    return "\n".join(lines)


def section_real_vocab(vocab_name: str, real: dict[str, dict[str, dict]], synthetic: dict[str, dict[str, dict]]) -> str:
    info = vocab_info(real, vocab_name)
    pretty = pretty_vocab_name(info)
    size = info.get("size")
    size_txt = f"{size // 1000}k tokens" if isinstance(size, int) else "real tokenizer"
    opts = info.get("options") or {}
    n_ids = len({i for rs in real.values() for i in rs})
    lines = [f"## {real_section_title(info)}", "",
             f"kbnf + Formatron on the **real `{info.get('tokenizer') or vocab_name}` vocabulary** "
             f"({size:,} tokens; built with `formatron.integrations.transformers.create_engine_vocabulary`, byte-level BPE "
             f"unmangled, pickled once in the parent and reconstructed in every child) instead of the synthetic ~3k-token one. "
             f"Same corpus ({n_ids} schemas), same seed, same random walk — only the vocabulary changed. "
             f"Files: " + ", ".join(f"`results/{stem}-{vocab_name}.jsonl`" for stem, _ in KBNF_CONFIGS if stem in real) + ".", "",
             f"Isolation: one fresh `spawn` child per schema, {opts.get('timeout', '?')} s wall-clock kill, RSS watchdog "
             f"({opts.get('mem_mb', '?')} MB), {opts.get('workers', '?')} parallel workers; random walk capped at "
             f"{opts.get('token_cap', '?')} tokens.", "",
             section_headline(real, KBNF_CONFIGS, h=3), "",
             section_per_family(real, KBNF_CONFIGS, h=3, vocab_desc=f"the real {pretty} vocabulary ({size_txt})"), "",
             section_real_compare(synthetic, real, h=3, pretty=pretty), "",
             section_real_cases(real, synthetic, h=3), "",
             section_worst(real, KBNF_CONFIGS, h=3)]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_report(results_dir: str, analysis_path: str | None = None) -> str:
    data: dict[str, dict[str, dict]] = {}
    for stem, _ in CONFIGS:
        rows = load_rows(os.path.join(results_dir, f"{stem}.jsonl"))
        if rows:
            data[stem] = rows
    real_runs = discover_real_vocab_runs(results_dir)
    if not data and not real_runs:
        raise SystemExit(f"no results found in {results_dir}")
    if not data:  # only real-vocabulary runs: still produce the synthetic-style sections from them
        data = dict(next(iter(real_runs.values())))
    ids = set()
    for rs in data.values():
        ids |= set(rs)
    fam_counts = collections.Counter()
    cat_counts = collections.Counter()
    for rs in data.values():
        for r in rs.values():
            fam_counts[r["family"]] += 0
    for i in ids:
        for rs in data.values():
            if i in rs:
                cat_counts[rs[i]["category"]] += 1
                break
    v = versions()
    lines = ["# GrammarGuard adversarial-schema benchmark — results", "",
             f"Generated {datetime.datetime.now().isoformat(timespec='seconds')} by `benchmarks/grammar_guard/report.py` "
             f"from `{os.path.relpath(results_dir, os.path.dirname(HERE))}`.", "",
             f"Corpus: **{len(ids)} schemas** ({cat_counts['normal']} normal, {cat_counts['adversarial']} adversarial), "
             f"deterministic seed; see `README.md` for the families and what `expect` means.", "",
             "Environment: " + ", ".join(f"{k} {val}" for k, val in v.items()) + ".", "",
             "Isolation: one fresh `spawn` child per schema, 10 s wall-clock kill, RSS watchdog (3–4 GB), 6 parallel workers; "
             "synthetic ~3k-token vocabulary; random walk capped at 512 tokens."]
    if real_runs:
        lines += ["", "The sections up to *Worst cases* use the **synthetic vocabulary** (`hardened.jsonl`, `default.jsonl`, "
                  "`xgrammar.jsonl`, `llguidance.jsonl`). " +
                  "; ".join(f"[{real_section_title(vocab_info(real, name))}]({md_anchor(real_section_title(vocab_info(real, name)))}) "
                            f"re-runs the kbnf configs on `{vocab_info(real, name).get('tokenizer') or name}`"
                            for name, real in real_runs.items()) + "."]
    lines.append("")
    lines.append(section_headline(data))
    lines.append("")
    lines.append(section_per_family(data))
    lines.append("")
    lines.append(section_differential(data))
    lines.append("")
    lines.append(section_cases(data))
    lines.append("")
    lines.append(section_worst(data))
    for name, real in real_runs.items():
        lines += ["", section_real_vocab(name, real, data)]
    if analysis_path and os.path.exists(analysis_path):
        with open(analysis_path, encoding="utf-8") as f:
            lines += ["", f.read().rstrip(), ""]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--analysis", default=DEFAULT_ANALYSIS, help="markdown file appended verbatim (hand-written findings)")
    ap.add_argument("--no-analysis", action="store_true")
    args = ap.parse_args(argv)
    text = build_report(args.results_dir, None if args.no_analysis else args.analysis)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {args.out} ({len(text):,} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
