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


def section_headline(data: dict[str, dict[str, dict]]) -> str:
    lines = ["## Headline numbers", ""]
    header = ["config", "n", "admitted", "rejected", "timeout", "crash/oom", "valid / completed walks", "compile p50", "p99", "max",
              "admitted & > 1 s", "normal/admit rejected", "expect=reject admitted", "expect=reject hung/crashed"]
    rows = []
    for stem, name in CONFIGS:
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


def section_per_family(data: dict[str, dict[str, dict]]) -> str:
    fams = family_order()
    lines = ["## Per family × configuration", ""]
    for stem, name in CONFIGS:
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
        lines += [f"### {name}", "", md_table(header, rows), ""]
    lines.append("Per-token *mask* latency is `Formatter.compute_allowed_tokens()` over the synthetic ~3k-token vocabulary "
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


def section_worst(data: dict[str, dict[str, dict]]) -> str:
    lines = ["## Worst cases per configuration (by end-to-end cost)", ""]
    for stem, name in CONFIGS:
        rs = data.get(stem)
        if not rs:
            continue
        worst = sorted(rs.values(), key=lambda r: -(compile_total(r) or r.get("wall_ms_parent") or 0))[:8]
        items = [f"`{r['id']}` — {r['outcome']} {fmt_ms(compile_total(r) or r.get('wall_ms_parent'))}, phase `{r.get('phase_reached')}`, "
                 f"peak RSS {r.get('peak_rss_mb_observed', 0):.0f} MB" for r in worst]
        lines += [f"### {name}", ""] + _bullets(items, 8) + [""]
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
    if not data:
        raise SystemExit(f"no results found in {results_dir}")
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
             "synthetic ~3k-token vocabulary; random walk capped at 512 tokens.", ""]
    lines.append(section_headline(data))
    lines.append("")
    lines.append(section_per_family(data))
    lines.append("")
    lines.append(section_differential(data))
    lines.append("")
    lines.append(section_cases(data))
    lines.append("")
    lines.append(section_worst(data))
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
